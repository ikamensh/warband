"""The wilds wear the landscape: a wolf reads pale on snow and sandy on waste.

Every creature and every den keeps its summer picture and gains one coat per other landscape
(procedural tints in :mod:`warband.art.monsters`, keyed by :class:`~warband.sim.rules.MapTheme`),
the view and the selection cards draw the world's own coat, the den breathes landscape air, and
the minimap keeps its one shared neutral mark.  The rosters are the same on every landscape, so
the same seed draws the same camps whatever the theme — which is what keeps the creep gate
theme-blind.
"""

import numpy as np
import pytest

from saga2d import Game
from warband.art import ambience, monsters, textures, visual_lint
from warband.art.monsters import LAIR_ANCHORS, LAIR_LOOKS, LAIR_NAMES, LairKind, Monster
from warband.art.production import production_image
from warband.sim import camps, mapgen
from warband.sim.rules import BuildingType, MapTheme, Race, UnitType
from warband.ui.scene import GameScene
from warband.ui.style import build_theme
from warband.ui.view import NEUTRAL_MINIMAP

from tests.warband.battlefield import SETTINGS, field

THEMES = list(MapTheme)
FACING, FRAME = 2, "stand"


def picture(store: visual_lint.ImageStore, key: str):
    """The PIL image behind an asset key on the mock backend (what the player would see)."""
    return store.image(key)


def opaque_mean(image) -> np.ndarray:
    """Mean RGB over the solid pixels: the coat moves the animal, not its shadow."""
    arr = np.asarray(image.convert("RGBA")).astype(float)
    solid = arr[..., 3] >= 128
    assert solid.any()
    return arr[solid][..., :3].mean(axis=0)


@pytest.mark.parametrize("monster", list(Monster))
def test_every_creature_wears_a_coat_per_landscape(game, monster: Monster) -> None:
    """Summer keeps the sheet's own key; winter and waste are their own suffixed images, each a
    different picture with the sheet's own geometry."""
    store = visual_lint.ImageStore(game)
    summer = monsters.monster_image(game, monster, FACING, FRAME)
    assert summer == f"monster.{monster.value}.{FACING}.{FRAME}"
    summer_placement = textures.placements[summer]
    summer_pixels = opaque_mean(picture(store, summer))
    seen = {summer_pixels.tobytes()}
    for theme in (MapTheme.WINTER, MapTheme.WASTELAND):
        key = monsters.monster_image(game, monster, FACING, FRAME, theme)
        assert key == f"{summer}.{theme.value}", key
        placement = textures.placements[key]
        assert (placement.size, placement.drop, placement.front) == (summer_placement.size, summer_placement.drop, summer_placement.front)
        pixels = opaque_mean(picture(store, key))
        assert pixels.tobytes() not in seen, (monster, theme, "a coat that changes nothing is no coat")
        seen.add(pixels.tobytes())


@pytest.mark.parametrize("kind", list(LairKind))
@pytest.mark.parametrize("look", LAIR_LOOKS)
def test_every_den_wears_a_coat_per_landscape(game, kind: LairKind, look: str) -> None:
    """Dens match the creatures: the summer key bare, each other landscape suffixed and distinct."""
    store = visual_lint.ImageStore(game)
    summer = monsters.lair_image(game, kind, look)
    assert summer == f"building.lair.{kind.value}.{look}"
    summer_placement = textures.placements[summer]
    summer_pixels = opaque_mean(picture(store, summer))
    for theme in (MapTheme.WINTER, MapTheme.WASTELAND):
        key = monsters.lair_image(game, kind, look, theme)
        assert key == f"{summer}.{theme.value}", key
        placement = textures.placements[key]
        assert (placement.size, placement.drop, placement.front) == (summer_placement.size, summer_placement.drop, summer_placement.front)
        pixels = opaque_mean(picture(store, key))
        assert (pixels != summer_pixels).any(), (kind, look, theme)


def test_an_unknown_landscape_falls_back_to_summer(game) -> None:
    """A landscape the coats do not know wears summer rather than failing: the fallback is the rule."""
    assert monsters.coerce_theme("desert") is MapTheme.SUMMER
    assert monsters.coerce_theme(MapTheme.WINTER) is MapTheme.WINTER
    for monster in Monster:
        assert monsters.monster_image(game, monster, FACING, FRAME, "desert") == f"monster.{monster.value}.{FACING}.{FRAME}"
        assert monsters.monster_portrait_image(game, monster, "desert") == f"portrait.monster.{monster.value}"
    for kind in LairKind:
        assert monsters.lair_image(game, kind, "intact", "desert") == f"building.lair.{kind.value}.intact"
        assert monsters.lair_portrait_image(game, kind, "desert") == f"portrait.lair.{kind.value}"
    assert ambience.landscape_halo((150, 140, 120), "desert") == (150, 140, 120)


def test_winter_cools_and_waste_warms_every_coat(game) -> None:
    """The mapping means something: winter frames run brighter and bluer than summer, waste warmer."""
    store = visual_lint.ImageStore(game)
    for monster in Monster:
        summer = opaque_mean(picture(store, monsters.monster_image(game, monster, FACING, FRAME)))
        winter = opaque_mean(picture(store, monsters.monster_image(game, monster, FACING, FRAME, MapTheme.WINTER)))
        waste = opaque_mean(picture(store, monsters.monster_image(game, monster, FACING, FRAME, MapTheme.WASTELAND)))
        assert winter.mean() > summer.mean(), (monster, "snow should lighten the coat")
        assert winter[2] - winter[0] > summer[2] - summer[0], (monster, "snow should cool it")
        assert waste[0] - waste[2] > summer[0] - summer[2], (monster, "waste should warm it")


def test_the_coats_keep_the_dark(game) -> None:
    """A den's dark mouth is the shared camp affordance: the weather may dust the stones, never fill the hole."""
    store = visual_lint.ImageStore(game)
    for kind in LairKind:
        for theme in THEMES:
            dark = np.asarray(picture(store, monsters.lair_image(game, kind, "intact", theme)).convert("RGBA")).astype(float)
            solid = dark[..., 3] >= 128
            darkest = np.sort(dark[solid][..., :3].mean(axis=1))[: max(1, solid.sum() // 20)]
            assert darkest.mean() < 60, (kind, theme, darkest.mean())


@pytest.mark.parametrize("seed", [9, 10, 11])
def test_the_same_seed_draws_the_same_camps_on_every_landscape(seed: int) -> None:
    """The theme never enters mapgen's arithmetic: same seed, same deposits guarded by the same
    rosters for the same hoards — which is why the creep gate holds on every landscape by construction."""
    from warband.sim.rules import Layout

    worlds = [mapgen.generate(seed, 64, 48, 2, theme=theme, layout=Layout.PLAINS) for theme in THEMES]

    def camps_of(world) -> list:
        return sorted((world.buildings[camp.lair].rect, tuple(camp.kinds), world.buildings[camp.lair].gold, len(camp.guards))
                      for camp in world.camps)

    first = camps_of(worlds[0])
    assert first, "plains seeds 9-11 must draw camps to compare"
    for other in worlds[1:]:
        assert camps_of(other) == first


def scene_on(game: Game, theme: MapTheme) -> GameScene:
    """A real match scene on *theme*, its camps revealed, a few frames in."""
    world = mapgen.generate(9, 64, 48, 2, theme=theme)
    assert world.camps
    scene = GameScene(world, 9, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    scene.view.reveal = True
    world.reveal_all(0)
    for _ in range(3):
        game.tick(1 / 60)
    return scene


def test_the_view_draws_the_worlds_own_coats(tmp_path) -> None:
    """Through the real sprite path: on winter every guard and den key wears the winter coat,
    on summer none does."""
    for theme, suffix in ((MapTheme.SUMMER, None), (MapTheme.WINTER, ".winter"), (MapTheme.WASTELAND, ".wasteland")):
        game = Game(f"Warband coats {theme.value}", backend="mock", resolution=(1280, 800), theme=build_theme(),
                    save_dir=tmp_path / "saves")
        try:
            scene = scene_on(game, theme)
            world = scene.world
            # The view offers no public getter for the key a sprite was drawn with; the keys are the assertion.
            guard_keys = {scene.view._unit_keys[u.id] for camp in world.camps for u in camps.guards(world, camp)}
            assert guard_keys, theme
            lair_keys = {scene.view._building_keys[camp.lair] for camp in world.camps}
            for key in guard_keys | lair_keys:
                assert (suffix is None and ".winter" not in key and ".wasteland" not in key) or (suffix is not None and key.endswith(suffix)), (theme, key)
        finally:
            game.close()


def test_the_minimap_keeps_one_neutral_mark_on_every_landscape(tmp_path) -> None:
    """The minimap deliberately does not distinguish dens or coats: a den wears its seat's colour —
    the wilds' bone grey, nobody's yellow for a bare mine — on every landscape, while the ground
    itself still changes with it."""
    grounds, marks = {}, set()
    for theme in THEMES:
        game = Game(f"Warband minimap {theme.value}", backend="mock", resolution=(1280, 800), theme=build_theme(),
                    save_dir=tmp_path / "saves")
        try:
            scene = scene_on(game, theme)
            pixels = np.asarray(scene.view.minimap_image())
            lair = scene.world.buildings[scene.world.camps[0].lair]
            mark = tuple(int(v) for v in pixels[lair.y * 2, lair.x * 2, :3])
            assert mark == tuple(scene.world.players[scene.world.neutral].color), (theme, mark)
            marks.add(mark)
            grounds[theme] = tuple(pixels[4, 4, :3])
        finally:
            game.close()
    assert len(marks) == 1, marks
    assert len(set(grounds.values())) > 1, grounds


def test_a_den_breathes_landscape_air(tmp_path) -> None:
    """The ambience unifies with the bodies: each den's halo keeps its kind's hue breathed through
    the landscape's air — violet everywhere for the nest, frosted on snow and dusty on waste."""
    game = Game("Warband den air", backend="mock", resolution=(1280, 800), theme=build_theme(),
                save_dir=tmp_path / "saves")
    try:
        from tests.warband.battlefield import SETTINGS as _SETTINGS

        scene = GameScene(field(), 0, ranked=False, settings=dict(_SETTINGS))
        game.push(scene)
        world = scene.world
        world.reveal_all(0)
        camp = camps.place(world, (20, 16), [UnitType.SPIDER] * 3, 500)
        lair = world.buildings[camp.lair]
        scene.camera.center_on(lair.center[0] * 32, lair.center[1] * 32)
        violet = LAIR_ANCHORS[LairKind.SPIDER]["halo"]
        seen = {}
        for theme in THEMES:
            world.theme = theme
            game.backend.circles.clear()
            ambience.draw(scene, world, 0)
            colours = {tuple(circle["color"][:3]) for circle in game.backend.circles}
            assert ambience.landscape_halo(violet, theme) in colours, (theme, colours)
            seen[theme] = ambience.landscape_halo(violet, theme)
        assert seen[MapTheme.WINTER] != seen[MapTheme.SUMMER] != seen[MapTheme.WASTELAND]
    finally:
        game.close()


def test_cards_show_the_coat_but_keep_the_names(game) -> None:
    """Card consistency: the portrait wears the landscape, the names do not — a wolf reads as a
    wolf everywhere, and a Wolf Den is a Wolf Den on snow and on waste."""
    from warband.sim.rules import UNITS

    for monster in Monster:
        keys = {monsters.monster_portrait_image(game, monster, theme) for theme in THEMES}
        assert len(keys) == len(THEMES)
        assert "winter" not in UNITS[UnitType(monster.value)].name.lower()
    assert len(set(LAIR_NAMES.values())) == len(LairKind)
    for kind in LairKind:
        keys = {monsters.lair_portrait_image(game, kind, theme) for theme in THEMES}
        assert len(keys) == len(THEMES)
        assert production_image(game, UnitType.WOLF, None, Race.HUMAN, MapTheme.WINTER) == \
            monsters.monster_portrait_image(game, Monster.WOLF, MapTheme.WINTER)


@pytest.mark.slow
def test_the_warm_up_covers_one_landscape_per_world(tmp_path) -> None:
    """Slow: it registers every creature image and den there is on winter, 296 renders."""

    game = Game("Warband winter warm", backend="mock", resolution=(640, 480), theme=build_theme(),
                save_dir=tmp_path / "saves")
    try:
        keys = list(monsters.warm_monsters(game, MapTheme.WINTER)) + list(monsters.warm_lairs(game, MapTheme.WINTER))
        assert len(keys) == len(set(keys)) == len(Monster) * textures.FACINGS * len(textures.FRAMES) + len(LairKind) * len(LAIR_LOOKS)
        assert all(key.endswith(".winter") for key in keys)
        assert all(game.assets.has_image(key) for key in keys)
    finally:
        game.close()
