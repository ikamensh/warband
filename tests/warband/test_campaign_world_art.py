"""Story structures use complete map sprites, with the same identity and fog memory as buildings."""

import json

import pytest

from saga2d import Anchor, Camera, Game, Minimap, Scene

from warband.art import ambience, campaign_landmarks, textures, visual_lint
from warband.sim.model import World
from warband.sim.rules import BuildingType, Difficulty, Terrain, UnitType
from warband.story.campaign import Run
from warband.story.landmarks import LandmarkView, add_landmark
from warband.story.new_campaign import CAMPAIGN
from warband.ui.style import build_theme
from warband.ui.view import MapView


@pytest.fixture
def game(tmp_path):
    game = Game("Campaign map art", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    yield game
    game.close()


class StoryMap(Scene):
    """A small live map exercises the real art binding without building the whole mission HUD."""

    def __init__(self, run, *, memory=None):
        super().__init__()
        self.run, self.world, self.human = run, run.world, 0
        self.mission, self.campaign = run.mission, CAMPAIGN
        self.memory = memory

    def on_enter(self):
        from warband.story.campaign_visuals import building_image

        self.camera = Camera(self.game.resolution)
        self.view = MapView(self, self.world, self.human, memory=self.memory,
                            building_art=lambda sighting: building_image(self.run, self.game, sighting))
        self.minimap = Minimap(self.view.minimap_key, (self.world.width*32, self.world.height*32), self.camera,
                               width=120, height=90, anchor=Anchor.BOTTOM_LEFT)
        self.ui.add(self.minimap)
        self.landmarks = LandmarkView(self)

    def update(self, dt):
        self.view.sync(dt)
        self.landmarks.update()

    def draw(self):
        ambience.draw(self, self.world, self.human)


def small_run(mission_id="undertow_mill", *, width=32, height=24):
    mission = CAMPAIGN.mission(mission_id)
    world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], len(mission.sides),
                  races=[side.race for side in mission.sides], scripted=True)
    return Run(mission, world, flags={})


def test_mill_pylon_is_one_complete_building_sprite_while_village_buildings_keep_their_art(game):
    """The attackable lock is a pylon itself, without a farm and a separate gate occupying its footprint."""
    run = small_run()
    pylon = run.world.place_building(1, BuildingType.FARM, (23, 2))
    hall = run.world.place_building(0, BuildingType.TOWN_HALL, (4, 8))
    farm = run.world.place_building(0, BuildingType.FARM, (10, 10))
    add_landmark(run, "mill_pylon", "Mill lock-pylon", pylon.center, kind="gate", state="active")
    add_landmark(run, "mill_hall", "Millfield Town Hall", hall.center, kind="bell", state="active")
    add_landmark(run, "mill_fields", "Hasp's south field", farm.center, kind="refuge", state="active")
    run.world.reveal_all(0)
    scene = StoryMap(run)
    game.push(scene)
    game.tick(.1)
    sprite = scene.view.building_sprite(pylon.id)
    assert sprite.image.startswith("campaign.structure.pylon.")
    image = game.assets.image(sprite.image)
    assert sum(item["image"] == image for item in game.backend.sprites.values()) == 1
    for kind in ("gate", "bell", "refuge"):
        if game.assets.has_image(f"landmark.{kind}.active"):
            prop = game.assets.image(f"landmark.{kind}.active")
            assert not any(item["image"] == prop for item in game.backend.sprites.values())
    farm_key = textures.building_key(pylon.type, pylon.player, pylon.race, "intact")
    if game.assets.has_image(farm_key):
        farm_image = game.assets.image(farm_key)
        assert not any(item["image"] == farm_image for item in game.backend.sprites.values())
    assert not scene.view.building_sprite(hall.id).image.startswith("campaign.structure.")
    assert not scene.view.building_sprite(farm.id).image.startswith("campaign.structure.")


def test_a_pylon_remembers_its_seen_body_and_resumes_without_presentation_save_fields(game):
    """A pylon damaged in the fog keeps its last seen art and health, including on the first resumed frame."""
    run = small_run()
    world = run.world
    pylon = world.place_building(1, BuildingType.FARM, (23, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (27, 18))
    scout = world.spawn_unit(0, UnitType.FOOTMAN, (22.5, 5.5))
    add_landmark(run, "mill_pylon", "Mill lock-pylon", pylon.center, kind="gate", state="active")
    world.update_vision()
    before_presentation = json.loads(json.dumps(run.to_dict()))
    scene = StoryMap(run)
    game.push(scene)
    game.tick(.1)
    original = scene.view.building_sprite(pylon.id).image
    assert original.startswith("campaign.structure.pylon.")
    scout.x, scout.y = 2.5, 20.5
    world.update_vision()
    assert not world.any_visible(0, pylon.rect)
    pylon.hp = pylon.max_hp // 4
    game.tick(.1)
    assert scene.view.building_sprite(pylon.id).image == original
    assert scene.view.sighting(pylon.id).hp == pylon.max_hp
    assert run.to_dict() == before_presentation

    saved = json.loads(json.dumps({"world": world.to_dict(), "run": run.to_dict(), "memory": scene.view.memory()}))
    resumed_world = World.from_dict(saved["world"])
    resumed = Run.from_dict(run.mission, resumed_world, saved["run"])
    restored = StoryMap(resumed, memory=saved["memory"])
    game.clear_and_push(restored)
    assert restored.view.building_sprite(pylon.id).image == original
    assert restored.view.sighting(pylon.id).hp == pylon.max_hp
    game.tick(.1)
    assert restored.view.building_sprite(pylon.id).image == original
    resumed_world.units[scout.id].x, resumed_world.units[scout.id].y = 22.5, 5.5
    resumed_world.update_vision()
    game.tick(.1)
    assert restored.view.building_sprite(pylon.id).image != original
    assert restored.view.sighting(pylon.id).hp == pylon.hp


def test_destroying_a_pylon_in_the_fog_reveals_one_rubble_body_only_after_rescouting(game):
    """A hidden destruction keeps the last seen pylon; seeing the empty site replaces it with its own rubble once."""
    run = small_run()
    world = run.world
    pylon = world.place_building(1, BuildingType.FARM, (23, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (27, 18))
    scout = world.spawn_unit(0, UnitType.FOOTMAN, (22.5, 5.5))
    record = add_landmark(run, "mill_pylon", "Mill lock-pylon", pylon.center, kind="gate", state="active")
    world.update_vision()
    scene = StoryMap(run)
    game.push(scene)
    game.tick(.1)
    standing = game.assets.image(scene.view.building_sprite(pylon.id).image)
    rubble_key = f"campaign.structure.pylon.ruined.2.0.{game.backend.scale_factor:g}"

    def rubble_count():
        if not game.assets.has_image(rubble_key):
            return 0
        rubble = game.assets.image(rubble_key)
        return sum(item["image"] == rubble for item in game.backend.sprites.values())

    scout.x, scout.y = 2.5, 20.5
    world.update_vision()
    assert not world.any_visible(0, pylon.rect)
    pylon.hp = 0
    world.step()
    game.tick(.1)
    assert pylon.id not in world.buildings
    assert scene.view.building_sightings[pylon.id].hp == pylon.max_hp
    assert sum(item["image"] == standing for item in game.backend.sprites.values()) == 1
    assert rubble_count() == 0

    scout.x, scout.y = 22.5, 5.5
    world.update_vision()
    game.tick(.1)
    assert scene.view.building_sprite(pylon.id) is None
    assert pylon.id not in scene.view.building_sightings
    assert not any(item["image"] == standing for item in game.backend.sprites.values())
    assert rubble_count() == 1
    game.tick(.1)
    assert rubble_count() == 1
    assert record["state"] == "active"


def test_rebuilding_a_weight_restores_its_body_by_footprint_instead_of_entity_id(game):
    """A destroyed and freshly built objective vault has the same complete art; a different site stays ordinary."""
    run = small_run("undertow_weight")
    world = run.world
    vault = world.place_building(0, BuildingType.VAULT, (24, 14))
    ordinary = world.place_building(0, BuildingType.VAULT, (10, 14))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    add_landmark(run, "weight_1", "Weight I", vault.center, kind="anchor", state="active")
    scene = StoryMap(run)
    game.push(scene)
    game.tick(.1)
    original = scene.view.building_sprite(vault.id).image
    assert original.startswith("campaign.structure.vault.")
    assert not scene.view.building_sprite(ordinary.id).image.startswith("campaign.structure.")
    vault.hp = 0
    world.step()
    game.tick(.1)
    assert vault.id not in world.buildings
    assert scene.view.building_sprite(vault.id) is None
    replacement = world.place_building(0, BuildingType.VAULT, vault.pos)
    game.tick(.1)
    assert replacement.id != vault.id
    assert scene.view.building_sprite(replacement.id).image == original


def test_caravan_rockfall_blockers_have_boulder_bodies_instead_of_farms(game):
    """Both attackable ford blockers share the rockfall art, while an unrelated hostile farm keeps its body."""
    run = small_run("undertow_caravan", width=40, height=28)
    rocks = [run.world.place_building(1, BuildingType.FARM, (x, 23)) for x in (30, 32)]
    ordinary = run.world.place_building(1, BuildingType.FARM, (35, 23))
    add_landmark(run, "middle_ford", "The causeway ford", (31.5, 23.5), kind="gate", state="ruined")
    run.world.reveal_all(0)
    scene = StoryMap(run)
    game.push(scene)
    game.tick(.1)
    assert all(scene.view.building_sprite(rock.id).image.startswith("campaign.structure.rockfall.") for rock in rocks)
    assert not scene.view.building_sprite(ordinary.id).image.startswith("campaign.structure.")


@pytest.mark.parametrize("mission_id, building_type, player, pos, glows", [
    ("undertow_grove", BuildingType.VAULT, 0, (23, 17), True),
    ("undertow_maw", BuildingType.MAGE_TOWER, 0, (39, 29), True),
    ("undertow_maw", BuildingType.MAGE_TOWER, 1, (42, 56), False),
])
def test_campaign_aether_light_stays_inside_its_body_and_the_refuge_has_no_mage_crown(
        game, mission_id, building_type, player, pos, glows):
    """The live ambience pass anchors small lights inside the custom body, with no inherited floating tower crown."""
    run = small_run(mission_id, width=max(32, pos[0]+8), height=max(24, pos[1]+8))
    if building_type is BuildingType.VAULT:
        run.world.lay_rifts((pos,))
    building = run.world.place_building(player, building_type, pos)
    run.world.reveal_all(0)
    scene = StoryMap(run)
    game.push(scene)
    scene.camera.center_on(building.center[0]*textures.TILE, building.center[1]*textures.TILE)
    for time in (0.0, 1.0, 2.5):
        run.world.time = time
        game.tick(.1)
        sprite = scene.view.building_sprite(building.id)
        assert sprite.image.startswith("campaign.structure.")
        circles = [circle for circle in game.backend.circles if circle["space"] == "world"]
        assert bool(circles) is glows
        x, bottom = sprite.position
        width, height = sprite.size
        for circle in circles:
            cx, cy, radius = circle["x"], circle["y"], circle["radius"]
            assert radius <= 12
            assert x-width/2 <= cx-radius <= cx+radius <= x+width/2
            assert bottom-height <= cy-radius <= cy+radius <= bottom


@pytest.mark.slow
@pytest.mark.parametrize("mission_id, structures", [
    ("undertow_mill", (("mill_pylon", "pylon"), ("mill_vault", "vault"))),
    ("undertow_caravan", (("dam_pylon", "dam"),)),
    ("undertow_grove", ((None, "root_vault"),)),
    ("undertow_weight", (("weight_1", "vault"), ("weight_2", "vault"), ("weight_3", "vault"))),
    ("undertow_maw", (("keystone", "keystone"), ("seal_pylon_1", "pylon"), ("seal_pylon_2", "pylon"),
                       ("seal_pylon_3", "pylon"), ("refuge_tower", "refuge_tower"))),
])
def test_every_mission_shows_its_story_structures_through_the_actual_match_scene(game, mission_id, structures):
    """Slow: build and render each complete campaign map, including its real HUD and character asset pipeline."""
    from warband.story.mission_scene import MissionScene, build_world

    run = build_world(CAMPAIGN.mission(mission_id), flags={})
    run.world.reveal_all(0)
    scene = MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM)
    scene.paused = True
    game.push(scene)
    game.tick(.1)
    for landmark_id, form in structures:
        if landmark_id is None:  # The Grove's grown lock is a real vault, without a separate landmark record.
            building = run.world.vaults(0)[0]
        else:
            center = tuple(run.vars["landmarks"][landmark_id]["point"])
            building = next(building for building in run.world.buildings.values() if building.center == center)
        assert scene.view.building_sprite(building.id).image.startswith(f"campaign.structure.{form}.")


@pytest.mark.parametrize("form", campaign_landmarks.FORMS)
def test_structure_states_keep_their_scale_and_ground_registration(game, form):
    """Damage changes real pixels while a shared canvas and placement keep the mechanism grounded."""
    pictures = [campaign_landmarks.image(form, state) for state in ("active", "damaged", "ruined")]
    assert len({picture.size for picture in pictures}) == 1
    assert len({picture.tobytes() for picture in pictures}) == 3
    keys = [campaign_landmarks.register_image(game, form, state) for state in ("active", "damaged", "ruined")]
    assert len({textures.placements[key] for key in keys}) == 1
    assert not [finding for picture in pictures for finding in visual_lint.lint_image(form, picture, painted=True)]
