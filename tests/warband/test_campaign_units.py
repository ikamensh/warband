"""Campaign characters have complete animated bodies, independent of the ordinary recruitment roster."""

from dataclasses import replace

import pytest

from warband.art import campaign_units, textures, visual_lint
from warband.sim.model import World
from warband.sim.rules import Difficulty, Terrain, UnitType
from warband.story.campaign import Run
from warband.story.mission_scene import MissionScene
from warband.story.new_campaign import CAMPAIGN


@pytest.mark.parametrize("name", campaign_units.CHARACTERS)
def test_every_character_has_a_complete_animated_body_in_the_asset_pipeline(game, name) -> None:
    """Each body supplies solid uncut frames and moves through the game's existing nine poses."""
    store = visual_lint.ImageStore(game)
    sheet, _ = campaign_units.painted_frames(name)
    pictures = []
    for frame in textures.FRAMES:
        key = campaign_units.unit_image(game, name, 0, 2, frame)
        image = store.image(key)
        placement = textures.placements[key]
        assert image.size == tuple(round(side * sheet.scale) for side in placement.size)
        assert not visual_lint.lint_image(key, image)
        pictures.append(image.tobytes())
    assert len(set(pictures)) == len(textures.FRAMES)


def test_story_links_choose_the_full_body_and_follow_a_replacement_without_repainting_the_roster(game) -> None:
    """A live scene changes the named body on rescue while another knight keeps the ordinary recruitment art."""
    mission = replace(CAMPAIGN.missions[0], objectives=(), triggers=(), win=lambda run: False, opening_focus=None)
    campaign = replace(CAMPAIGN, missions=(mission,))
    world = World(16, 16, [[Terrain.GRASS] * 16 for _ in range(16)], 2, scripted=True)
    first = world.spawn_unit(0, UnitType.KNIGHT, (6.5, 7.5))
    other = world.spawn_unit(0, UnitType.KNIGHT, (8.5, 7.5))
    run = Run(mission, world, flags={})
    run.set("issa", first.id)
    world.reveal_all(0)
    scene = MissionScene(campaign, run, difficulty=Difficulty.MEDIUM)
    scene.paused = True
    game.push(scene)
    game.tick(.1)
    assert scene.view.unit_sprite(first.id).image.startswith("campaign.unit.issa.")
    assert scene.view.unit_sprite(other.id).image.startswith("unit.")
    run.set("issa", other.id)
    game.tick(.1)
    assert scene.view.unit_sprite(other.id).image.startswith("campaign.unit.issa.")
    assert scene.view.unit_sprite(first.id).image.startswith("unit.")
    pell = world.spawn_unit(1, UnitType.FOOTMAN, (8.5, 9.5))
    run.set("pell", pell.id)
    scene.select([pell.id])
    game.tick(.1)
    assert scene.entity_name(pell) == "Pell"
    assert scene.view.unit_sprite(pell.id).image.startswith("campaign.unit.pell.")
    portrait = game.assets.image("story.portrait." + campaign.speakers["Pell"].portrait)
    assert any(item["image"] == portrait for item in game.backend.images)


@pytest.mark.slow
@pytest.mark.parametrize("name", campaign_units.CHARACTERS)
def test_the_entire_painted_animation_has_clear_gutters_and_separate_poses(game, name) -> None:
    """Slow: inspect every facing and pose of each complete production character sheet."""
    store = visual_lint.ImageStore(game)
    for facing in range(textures.FACINGS):
        pictures = []
        for frame in textures.FRAMES:
            key = campaign_units.unit_image(game, name, 0, facing, frame)
            image = store.image(key)
            assert not visual_lint.lint_image(key, image)
            pictures.append(image.tobytes())
        assert len(set(pictures)) == len(textures.FRAMES), (name, facing)
