"""The dens: one per creature, named by the toughest guard in the camp.

Every creature resolves to a lair of its own; a mixed roster takes the toughest guard's den,
so the wolf pack gets an earth den, the spider-led camp a silk nest and the big seam camp its
troll mound.  Every den keeps the camps' shared footprint and affordance (three tiles, a dark
mouth, a bone-white mark) while differing in silhouette and palette, wears intact and damaged
looks like any other building, and has a portrait and a name of its own for the selection panel.
"""

import pytest

from saga2d import Game
from warband.art import monsters, textures, visual_lint
from warband.art.monsters import LAIR_ANCHORS, LAIR_LOOKS, LAIR_NAMES, LairKind
from warband.sim import camps, mapgen
from warband.sim.model import World
from warband.sim.rules import BUILDINGS, BuildingType, Terrain, UnitType
from warband.ui.style import build_theme
from warband.ui.view import Sighting, building_look

import random


def mock_game(tmp_path) -> Game:
    return Game("Warband lairs", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")


def flat_world(width: int = 40, height: int = 32, players: int = 2) -> World:
    return World(width, height, [[Terrain.GRASS] * width for _ in range(height)], players, rng=random.Random(1))


def test_every_creature_resolves_to_a_lair_of_its_own() -> None:
    """One den per creature, reached by the name a rule table would hold."""
    assert {LairKind(unit.value) for unit in (UnitType.WOLF, UnitType.SPIDER, UnitType.TROLL, UnitType.GOLEM)} == set(LairKind)
    assert len({monsters.lair_key(kind) for kind in LairKind}) == len(LairKind)


def test_the_toughest_guard_names_a_mixed_den() -> None:
    """The map's own rosters, and the custom camps the tools stage."""
    assert monsters.lair_kind_for_roster([UnitType.WOLF] * 4) is LairKind.WOLF
    assert monsters.lair_kind_for_roster([UnitType.SPIDER, UnitType.SPIDER, UnitType.WOLF, UnitType.WOLF]) is LairKind.SPIDER
    assert monsters.lair_kind_for_roster([UnitType.TROLL, UnitType.GOLEM, UnitType.SPIDER, UnitType.SPIDER]) is LairKind.TROLL
    assert monsters.lair_kind_for_roster([UnitType.GOLEM, UnitType.GOLEM]) is LairKind.GOLEM
    assert monsters.lair_kind_for_roster([UnitType.TROLL]) is LairKind.TROLL


def test_a_generated_maps_camps_take_the_dens_they_were_raised_for() -> None:
    """The third-mine camps read wolf or spider; the seam camp, where there is one, reads troll."""
    world = mapgen.generate(9, 64, 48, 2)
    assert world.camps
    kinds = {monsters.lair_kind_for_camp(camp) for camp in world.camps}
    assert kinds <= {LairKind.WOLF, LairKind.SPIDER, LairKind.TROLL}, kinds
    assert LairKind.WOLF in kinds or LairKind.SPIDER in kinds


def test_a_den_with_no_known_guards_reads_as_the_common_wolf_den() -> None:
    assert monsters.lair_kind_for_roster([]) is LairKind.WOLF


def test_an_unknown_guard_is_a_loud_failure_not_another_den() -> None:
    with pytest.raises(ValueError):
        monsters.lair_kind_for_roster(["dragon"])  # type: ignore[list-item]
    with pytest.raises(ValueError):
        monsters.lair_mesh(LairKind.WOLF, "burning")
    with pytest.raises(ValueError):
        monsters.LairKind("dragon")


def test_every_den_keeps_the_camps_shared_footprint() -> None:
    """A new silhouette must never move a wall: placement, leash and collision never hear of it."""
    assert BUILDINGS[BuildingType.LAIR].size == 3
    world = flat_world()
    for kind in LairKind:
        camp = camps.place(world, (5 + 6 * list(LairKind).index(kind), 5),
                           [UnitType(kind.value)], 500)
        lair = world.buildings[camp.lair]
        assert (lair.size, lair.rect[2], lair.rect[3]) == (3, 3, 3)


def test_a_den_wears_intact_and_damaged_like_any_other_building(tmp_path) -> None:
    """Torn down to half its hit points, a den shows its damage; whole again, it does not."""
    world = flat_world()
    camp = camps.place(world, (20, 16), [UnitType.WOLF] * 3, 500)
    lair = world.buildings[camp.lair]
    assert building_look(lair) == "intact"
    lair.hp = lair.max_hp // 2 - 1
    assert building_look(lair) == "damaged"
    game = mock_game(tmp_path)
    try:
        store = visual_lint.ImageStore(game)
        for kind in LairKind:
            for look in LAIR_LOOKS:
                key = monsters.lair_image(game, kind, look)
                findings = visual_lint.lint_image(key, store.image(key))
                assert not findings, (kind, look, [str(f) for f in findings])
                placement = textures.placements[key]
                assert placement.front == 1.5 * textures.TILE, (kind, look, placement)
    finally:
        game.close()


def test_every_den_has_a_portrait_and_a_name_of_its_own(tmp_path) -> None:
    """No two dens share a card picture, and no card says one shared 'Lair'."""
    assert len(set(LAIR_NAMES.values())) == len(LairKind)
    game = mock_game(tmp_path)
    try:
        store = visual_lint.ImageStore(game)
        pictures = {kind: store.image(monsters.lair_portrait_image(game, kind)).tobytes() for kind in LairKind}
        assert len(set(pictures.values())) == len(LairKind)
        looks = {kind: store.image(monsters.lair_image(game, kind)).tobytes() for kind in LairKind}
        assert len(set(looks.values())) == len(LairKind), "four kinds, one picture each, no two alike"
    finally:
        game.close()


def test_every_den_knows_where_it_breathes_from() -> None:
    """The ambience draws each den's life from anchors on its own mesh: a mouth, glints, a halo tint."""
    assert set(LAIR_ANCHORS) == set(LairKind)
    for kind, anchors in LAIR_ANCHORS.items():
        assert len(anchors["glints"]) >= 2, kind
        assert len(anchors["halo"]) == 3, kind


def test_a_sighting_remembers_whose_den_it_saw(tmp_path) -> None:
    """The map shows a den as it was last seen, kind included; saves from before the dens diverged
    remember none and read as the common wolf den."""
    world = flat_world()
    camp = camps.place(world, (20, 16), [UnitType.SPIDER, UnitType.SPIDER, UnitType.WOLF, UnitType.WOLF], 600)
    lair = world.buildings[camp.lair]
    sighting = Sighting.of(lair)
    sighting.lair_kind = monsters.lair_kind_for_camp(camp).value
    assert sighting.lair_kind == "spider"
    again = Sighting.from_dict(sighting.to_dict())
    assert again.lair_kind == "spider"
    old = {k: v for k, v in sighting.to_dict().items() if k != "lair_kind"}
    assert Sighting.from_dict(old).lair_kind == "wolf"
    with pytest.raises(ValueError):
        Sighting.from_dict({**sighting.to_dict(), "lair_kind": "dragon"})


def test_every_den_breathes_its_own_tint(tmp_path) -> None:
    """The animate half: each den gets a halo pulse, motes off its mouth and glints on its tips,
    in its own tint, drawn through the same ambience pass as the mines."""
    from warband.art import ambience
    from warband.ui.scene import GameScene

    from tests.warband.battlefield import SETTINGS, field

    game = Game("Warband den breath", backend="mock", resolution=(1280, 800), theme=build_theme(),
                save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        world = scene.world
        world.reveal_all(0)
        tints = {}
        for kind, roster in ((LairKind.WOLF, [UnitType.WOLF] * 3), (LairKind.SPIDER, [UnitType.SPIDER] * 3),
                             (LairKind.TROLL, [UnitType.TROLL]), (LairKind.GOLEM, [UnitType.GOLEM])):
            camp = camps.place(world, (5 + 7 * list(LairKind).index(kind), 25), roster, 500)
            lair = world.buildings[camp.lair]
            scene.camera.center_on(lair.center[0] * 32, lair.center[1] * 32)
            game.backend.circles.clear()
            ambience.draw(scene, world, 0)
            drawn = list(game.backend.circles)
            assert len(drawn) >= 7, (kind, len(drawn))  # the halo, five motes and the breath
            tints[kind] = {tuple(circle["color"][:3]) for circle in drawn}
        assert tints[LairKind.WOLF] != tints[LairKind.SPIDER], "a wolf den must not breathe spider violet"
    finally:
        game.close()


def test_the_view_draws_each_den_in_its_own_kind_and_look(tmp_path) -> None:
    """Through the real sprite path: four camps, four dens, each key naming its kind."""
    from warband.ui.scene import GameScene

    from tests.warband.battlefield import SETTINGS, field

    game = Game("Warband dens", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        world = scene.world
        rosters = [(UnitType.WOLF,) * 3, (UnitType.SPIDER,) * 3, (UnitType.TROLL,), (UnitType.GOLEM,)]
        placed = [camps.place(world, (5 + 7 * i, 5), list(roster), 500) for i, roster in enumerate(rosters)]
        world.reveal_all(0)
        for _ in range(3):
            game.tick(1 / 60)
        for camp in placed:
            key = scene.view._building_keys[camp.lair]
            assert monsters.lair_kind_for_camp(camp).value in key, (camp, key)
        lair = world.buildings[placed[0].lair]
        lair.hp = 1
        for _ in range(3):
            game.tick(1 / 60)
        assert scene.view._building_keys[placed[0].lair].endswith(".damaged"), scene.view._building_keys[placed[0].lair]
    finally:
        game.close()
