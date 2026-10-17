"""Campaign landmarks are saveable objectives with presentation driven by their public story state."""

import json

import pytest

from saga2d import Anchor, Camera, Minimap, Scene
from PIL import Image

from warband.sim.model import World
from warband.sim.rules import Terrain, UnitType
from warband.story.campaign import Run
from warband.story.landmarks import add_landmark, landmark, occupied, set_landmark_state
from warband.story.missions import CAMPAIGN


class MapScene(Scene):
    def __init__(self, run):
        super().__init__()
        self.run, self.world, self.human = run, run.world, 0

    def on_enter(self):
        from warband.story.landmarks import LandmarkView

        self.camera = Camera(self.game.resolution)
        self.game.assets.image_from_pil("landmark-test-map", Image.new("RGBA", (32, 32), (28, 40, 44, 255)))
        self.minimap = Minimap("landmark-test-map", (self.world.width*32, self.world.height*32), self.camera,
                               width=160, height=160, anchor=Anchor.BOTTOM_LEFT, margin=12,
                               on_click=lambda x, y, button: self.camera.center_on(x, y) if button == "left" else None)
        self.ui.add(self.minimap)
        self.landmarks = LandmarkView(self)

    def update(self, dt):
        self.landmarks.update()

    def draw(self):
        self.landmarks.draw()


def empty_run() -> Run:
    world = World(32, 32, [[Terrain.GRASS] * 32 for _ in range(32)], 2, scripted=True)
    return Run(CAMPAIGN.missions[0], world, flags={})


def test_minimap_hover_names_charted_objectives_without_revealing_uncharted_ones(game):
    """Hover identifies a diamond in the fog while its usual left-click still moves the camera."""
    run = empty_run()
    add_landmark(run, "bell", "The Tide Bell (repair it)", (12.5, 12.5))
    add_landmark(run, "hidden", "The secret gate", (24.5, 24.5), revealed=False)
    scene = MapScene(run)
    game.push(scene)
    game.tick(.1)
    x, y = scene.minimap.to_screen(12.5*32, 12.5*32)
    game.backend.inject_mouse_move(x, y)
    game.tick(.1)
    assert any("The Tide Bell (repair it)" in item["text"] for item in game.backend.texts)
    game.backend.inject_click(x, y)
    game.backend.inject_release(x, y)
    game.tick(.1)
    assert scene.camera.world_to_screen(12.5*32, 12.5*32) == (game.resolution[0]/2, game.resolution[1]/2)
    game.backend.inject_mouse_move(*scene.minimap.to_screen(24.5*32, 24.5*32))
    game.tick(.1)
    assert not any("secret gate" in item["text"] for item in game.backend.texts)


def test_landmark_state_and_occupation_survive_the_real_world_and_run_save() -> None:
    """A mission resumed from JSON keeps both its monument state and the army holding it."""
    run = empty_run()
    add_landmark(run, "bell", "The Tide Bell", (12.5, 12.5), radius=2.0)
    run.world.spawn_unit(0, UnitType.FOOTMAN, (12.5, 12.5))
    set_landmark_state(run, "bell", "active")
    world = World.from_dict(json.loads(json.dumps(run.world.to_dict())))
    resumed = Run.from_dict(run.mission, world, json.loads(json.dumps(run.to_dict())))
    assert landmark(resumed, "bell") == landmark(run, "bell")
    assert landmark(resumed, "bell")["state"] == "active"
    assert occupied(resumed, "bell")


def test_holding_landmarks_requires_feet_on_the_ground_and_an_uncontested_radius() -> None:
    """Workers, dead soldiers and flyers do not secure a bell; guards and enemy workers contest it."""
    run = empty_run()
    add_landmark(run, "bell", "The Tide Bell", (12.5, 12.5), radius=2.0)
    worker = run.world.spawn_unit(0, UnitType.PEASANT, (12.5, 12.5))
    assert not occupied(run, "bell")
    assert occupied(run, "bell", soldiers_only=False)
    run.world.spawn_unit(0, UnitType.GRYPHON, (12.5, 12.5))
    assert not occupied(run, "bell")
    soldier = run.world.spawn_unit(0, UnitType.FOOTMAN, (12.5, 12.5))
    assert occupied(run, "bell")
    rival = run.world.spawn_unit(1, UnitType.PEASANT, (12.5, 12.5))
    assert not occupied(run, "bell") and occupied(run, "bell", contested=False)
    rival.hp = 0
    assert occupied(run, "bell")
    guard = run.world.spawn_unit(run.world.neutral, UnitType.WOLF, (12.5, 12.5))
    assert not occupied(run, "bell")
    guard.hp = 0
    soldier.hp = 0
    assert not occupied(run, "bell") and occupied(run, "bell", soldiers_only=False)
    worker.hp = 0
    assert not occupied(run, "bell", soldiers_only=False)


def test_the_scene_hears_state_changes_once_but_a_resumed_landmark_is_silent(game, monkeypatch) -> None:
    """Activation is a real scene cue; a loaded active bell does not ring again every frame or on resume."""
    from warband.audio import sound

    run = empty_run()
    add_landmark(run, "bell", "The Tide Bell", (12.5, 12.5))
    run.world.reveal_all(0)
    heard = []
    monkeypatch.setattr(sound, "sound_hook", heard.append)
    game.push(MapScene(run))
    game.tick(0.1)
    assert heard == []
    set_landmark_state(run, "bell", "active")
    game.tick(0.1)
    game.tick(0.1)
    assert heard == ["landmark_bell"]
    game.clear_and_push(MapScene(Run.from_dict(run.mission, run.world, json.loads(json.dumps(run.to_dict())))))
    game.tick(0.1)
    assert heard == ["landmark_bell"]
    assert "The Tide Bell" in [item["text"] for item in game.backend.texts]


def test_unexplored_and_offscreen_landmark_names_never_reach_the_overlay(game) -> None:
    """A charted objective does not name unexplored ground; panning it offscreen never submits clipped text."""
    run = empty_run()
    add_landmark(run, "charted", "Charted Sluice", (12.5, 12.5), kind="gate")
    add_landmark(run, "secret", "Forgotten Heart", (12.5, 15.5), kind="memorial", revealed=False)
    scene = MapScene(run)
    game.push(scene)
    game.tick(.1)
    assert scene.landmarks.known("charted") and not scene.landmarks.known("secret")
    assert not game.backend.texts
    run.world.reveal_all(0)
    game.tick(.1)
    assert {item["text"] for item in game.backend.texts} == {"Charted Sluice", "Forgotten Heart"}
    scene.camera.center_on(1800, 1800)
    game.tick(.1)
    assert not game.backend.texts


def test_landmark_nameplates_leave_the_hud_clear(game) -> None:
    """Objective panels consume the same rectangle visually and for input, so a nameplate never covers one."""
    from saga2d import Anchor, Button

    run = empty_run()
    run.world.reveal_all(0)
    add_landmark(run, "bell", "The Tide Bell", (12.5, 12.5))
    scene = MapScene(run)
    game.push(scene)
    scene.ui.add(Button("Mission panel", width=180, height=45, anchor=Anchor.TOP_LEFT, margin=(330, 420)))
    game.tick(.1)
    assert "Mission panel" in [item["text"] for item in game.backend.texts]
    assert "The Tide Bell" not in [item["text"] for item in game.backend.texts]


@pytest.mark.parametrize("kind", ("bell", "anchor", "gate", "refuge", "memorial"))
def test_navigation_cues_render_in_every_story_state_without_inventing_extra_bodies(game, kind) -> None:
    """Labels remain useful for every cue kind; named ground alone does not acquire a second monument."""
    run = empty_run()
    run.world.reveal_all(0)
    add_landmark(run, "object", "The Lock", (12.5, 12.5), kind=kind)
    game.push(MapScene(run))
    for state in ("dormant", "active", "ruined", "open"):
        set_landmark_state(run, "object", state)
        game.tick(.1)
        assert "The Lock" in [item["text"] for item in game.backend.texts]


def test_campaign_cues_generate_and_play_through_the_sound_bank(game, tmp_path) -> None:
    """The transition names have usable WAVs and reach the game's real audio manager through the bank."""
    import numpy as np
    from warband.audio import campaign
    from warband.audio.sound import SynthBank

    bank = SynthBank(game, tmp_path, version="campaign", sounds=campaign.SOUNDS)
    for name, generate in campaign.SOUNDS.items():
        data = generate()
        assert np.isfinite(data).all() and .1 <= np.abs(data).max() <= .95
        assert abs(data[0]) < .01 and abs(data[-1]) < .01
        bank.play(name)
    assert len(game.backend.sounds_played) == len(campaign.SOUNDS)


def test_charted_landmarks_stay_on_the_minimap_without_disclosing_undiscovered_sites(game) -> None:
    """A distant charted sluice remains a navigation target after transient pings expire; a secret site stays hidden."""
    run = empty_run()
    add_landmark(run, "charted", "Distant Sluice", (30.5, 30.5), kind="gate")
    add_landmark(run, "secret", "Forgotten Heart", (26.5, 30.5), kind="memorial", revealed=False)
    scene = MapScene(run)
    game.push(scene)
    for _ in range(50):
        game.tick(.1)
    charted = scene.minimap.to_screen(30.5*32, 30.5*32)
    secret = scene.minimap.to_screen(26.5*32, 30.5*32)
    centers = [(sum(x for x, _ in p["points"])/len(p["points"]), sum(y for _, y in p["points"])/len(p["points"]))
               for p in game.backend.polygons if p["space"] == "screen"]
    assert charted in centers
    assert secret not in centers
    assert "Distant Sluice" not in [item["text"] for item in game.backend.texts]
