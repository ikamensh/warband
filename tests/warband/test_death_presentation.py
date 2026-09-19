"""How a killed unit goes down (WB-005): away from the blow, with weight, by category, bounded, and cleanly on load."""

import math

import pytest

from saga2d import Game
from saga2d.effects import Burst
from warband.effects import OUTCOMES, UnitDeath
from warband.rules import UnitType
from warband.scene import GameScene
from warband.style import build_theme

from tests.warband.battlefield import SETTINGS, field, live_effects


@pytest.fixture
def play(tmp_path):
    game = Game("Warband deaths", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = GameScene(field(), 0, ranked=False, settings=SETTINGS)
    game.push(scene)
    scene.view.set_reveal(True)
    game.tick(1 / 60)
    yield game, scene
    game.close()


def tick(game: Game, seconds: float, dt: float = 1 / 60) -> None:
    """*seconds* of play in frames of *dt*; waiting for a body's next state takes tenths."""
    for _ in range(round(seconds / dt)):
        game.tick(dt)


def kill(game: Game, scene: GameScene, victim_type: UnitType, side: str) -> UnitDeath:
    """A victim at one hit point and a knight to the *side* of it; returns the body the moment the blow lands."""
    world = scene.world
    victim = world.spawn_unit(1, victim_type, (20.5, 12.5))
    victim.hp = 1
    knight = world.spawn_unit(0, UnitType.KNIGHT, (21.8 if side == "east" else 19.2, 12.5))
    world.attack([knight.id], victim.id)
    for _ in range(60 * 4):
        game.tick(1 / 60)
        if victim.id not in world.units:
            break
    assert victim.id not in world.units, "the knight never landed its blow"
    return scene.bodies[-1]


def bursts(scene: GameScene) -> int:
    return sum(isinstance(e, Burst) for e in live_effects(scene))


@pytest.mark.parametrize("side, sign", [("east", -1), ("west", 1)])
def test_the_body_falls_away_from_the_blow(play, side: str, sign: int) -> None:
    game, scene = play
    body = kill(game, scene, UnitType.FOOTMAN, side)
    tick(game, UnitDeath.DOWN)
    assert math.copysign(1, body.sprite.rotation) == sign and abs(body.sprite.rotation) == OUTCOMES["topple"].turn


def test_the_fall_has_weight_and_lands_at_the_feet(play) -> None:
    """A lurch, a fall that only speeds up, a landing with dust, then still: within 0.6 s, feet on the death point."""
    game, scene = play
    body = kill(game, scene, UnitType.FOOTMAN, "west")
    dust_before = bursts(scene)
    rotations, worst_feet = [], 0.0
    while not body.lying:
        game.tick(1 / 60)
        rotations.append(body.sprite.rotation)
        if body.elapsed > UnitDeath.LURCH:
            worst_feet = max(worst_feet, math.dist(body.feet, body.position))
        assert body.sprite.opacity == 255
    assert body.elapsed <= 0.6 and abs(body.sprite.rotation) == OUTCOMES["topple"].turn
    falling = [r for r, age in zip(rotations, range(len(rotations))) if (age + 1) / 60 <= UnitDeath.LURCH + UnitDeath.FALL]
    assert all(later >= earlier for earlier, later in zip(falling, falling[1:])), "the fall must only gather pace"
    assert max(rotations) <= OUTCOMES["topple"].turn + 1e-9, "the body never turns past lying"
    assert worst_feet <= 2.0, f"the feet drifted {worst_feet:.1f} px from the death point"
    assert body.landed and bursts(scene) > dust_before, "the landing raises dust"
    tick(game, UnitDeath.HOLD - 0.2, 0.1)
    assert body.sprite.opacity == 255 and body.sprite.rotation == body.turn, "lying still until the fade"
    tick(game, 0.2 + UnitDeath.FADE + 0.1, 0.1)
    assert body.done and body.sprite.is_removed and body not in scene.bodies + [b for b in live_effects(scene)]


@pytest.mark.parametrize("victim, outcome, turn, height", [
    (UnitType.ARCHER, "topple", (80, 90), (0.7, 0.85)),
    (UnitType.KNIGHT, "collapse", (20, 50), (0.5, 0.65)),
    (UnitType.CATAPULT, "wreck", (0, 15), (0.55, 0.75)),
])
def test_each_category_goes_down_its_own_way(play, victim, outcome, turn, height) -> None:
    game, scene = play
    body = kill(game, scene, victim, "west")
    tick(game, UnitDeath.DOWN)
    assert body.kind == outcome
    assert turn[0] <= abs(body.sprite.rotation) <= turn[1]
    assert height[0] <= body.sprite.size[1] / body.size[1] <= height[1]


def test_bodies_are_bounded_and_the_oldest_make_room(play) -> None:
    game, scene = play
    world = scene.world
    for row in range(4):  # 56 victims in four rows, each with its killer in the row below
        for col in range(14):
            victim = world.spawn_unit(1, UnitType.PEASANT, (12.5 + col, 8.5 + row * 2))
            victim.hp = 1
            knight = world.spawn_unit(0, UnitType.KNIGHT, (12.5 + col, 9.6 + row * 2))
            world.attack([knight.id], victim.id)
    tick(game, 2.5, 0.1)
    assert not world.player_units(1) and len(scene.bodies) == 56
    tick(game, UnitDeath.DOWN + UnitDeath.FADE + 0.2, 0.1)
    lying = [b for b in scene.bodies if not b.done and not b.cancelled]
    assert len(lying) == UnitDeath.BODIES and all(b.sprite.opacity == 255 for b in lying)
    tick(game, UnitDeath.HOLD + UnitDeath.FADE + 0.5, 0.1)
    assert not [b for b in scene.bodies if not b.done and not b.cancelled]


def test_loading_a_save_mid_fall_leaves_nothing_behind(play) -> None:
    game, scene = play
    body = kill(game, scene, UnitType.FOOTMAN, "west")
    tick(game, 0.2)
    assert not body.landed
    scene.save_to("quick")
    scene.load_from("quick")
    game.tick(1 / 60)
    loaded = game.scene  # a load is a new match scene
    assert loaded is not scene and body.sprite.is_removed and loaded.bodies == []
    dust = bursts(loaded)
    tick(game, 1.0)
    assert not body.landed and bursts(loaded) == dust and body not in live_effects(loaded)
