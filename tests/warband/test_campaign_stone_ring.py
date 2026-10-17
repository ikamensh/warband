"""The Ancient's named stone ring is physical scenery around its existing unit, not another monument."""

import json

from saga2d import Anchor, Camera, Minimap, Scene

from warband.art import campaign_landmarks, visual_lint
from warband.sim.model import World
from warband.sim.rules import Terrain, UnitType
from warband.story.campaign import Run
from warband.story.landmarks import LandmarkView, add_landmark
from warband.story.new_campaign import CAMPAIGN
from warband.ui.view import MapView


class RingScene(Scene):
    def __init__(self, run):
        super().__init__()
        self.run, self.world, self.human = run, run.world, 0

    def on_enter(self):
        self.camera = Camera(self.game.resolution)
        self.view = MapView(self, self.world, self.human)
        self.minimap = Minimap(self.view.minimap_key, (self.world.width*32, self.world.height*32), self.camera,
                               width=120, height=90, anchor=Anchor.BOTTOM_LEFT)
        self.ui.add(self.minimap)
        self.landmarks = LandmarkView(self)

    def update(self, dt):
        self.view.sync(dt)
        self.landmarks.update()


def test_the_guardian_stands_inside_a_visible_hollow_stone_ring_without_new_world_objects(game):
    """The live map adds the missing stones while the Ancient remains the only unit and the ground stays passable."""
    world = World(32, 32, [[Terrain.GRASS] * 32 for _ in range(32)], 3, scripted=True)
    run = Run(CAMPAIGN.mission("undertow_grove"), world, flags={})
    guardian = world.spawn_unit(world.neutral, UnitType.ANCIENT_GUARDIAN, (16.5, 16.5))
    add_landmark(run, "guardian_ring", "The Ancient in the stone ring", guardian.pos,
                 kind="memorial", radius=5, state="active")
    world.reveal_all(0)
    before = json.loads(json.dumps({"world": world.to_dict(), "run": run.to_dict()}))
    scene = RingScene(run)
    game.push(scene)
    game.tick(.1)
    key = f"campaign.structure.stone_ring.active.10.0.{game.backend.scale_factor:g}"
    assert game.assets.has_image(key)
    ring = game.assets.image(key)
    assert sum(sprite["image"] == ring and sprite["visible"] for sprite in game.backend.sprites.values()) == 1
    assert scene.view.unit_sprite(guardian.id).visible
    assert world.passable(16, 12)
    assert json.loads(json.dumps({"world": world.to_dict(), "run": run.to_dict()})) == before


def test_standing_stones_keep_a_clear_center_and_clean_painted_edges():
    """The separated stones frame the live Guardian; their alpha never supplies a second ground or central body."""
    image = campaign_landmarks.image("stone_ring")
    alpha = image.getchannel("A")
    assert alpha.getbbox() is not None
    assert alpha.crop((image.width*.35, image.height*.3, image.width*.65, image.height*.7)).getbbox() is None
    assert not visual_lint.lint_image("campaign.stone_ring", image, painted=True)
