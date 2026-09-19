"""Blood on damaging hits (WB-006): away from the striker, sized by the damage, only for flesh, only when seen, once, bounded, optional."""

import pytest

from saga2d import Game
from saga2d.effects import Burst
from warband.art.effects import Flare, Spray, Stain
from warband.sim.rules import BuildingType, UnitType
from warband.ui.scene import GameScene
from warband.ui.style import build_theme

from tests.warband.battlefield import SETTINGS, field, live_effects

RED, WOOD = (172, 22, 26), (222, 184, 118)


@pytest.fixture
def play(tmp_path):
    game = Game("Warband blood", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = GameScene(field(3), 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    scene.view.set_reveal(True)
    game.tick(1 / 60)
    yield game, scene
    game.close()


def sprays(scene: GameScene) -> list[Spray]:
    return [e for e in live_effects(scene) if isinstance(e, Spray)]


def first_hit(game: Game, scene: GameScene, attacker: UnitType, target, side: str = "west", *, attacker_player: int = 0, target_player: int = 1,
              hold: bool = False):
    """*attacker* strikes *target* (a unit type or a building type) from the *side*; returns the sprays the first blow made.
    With *hold* a victim stands where it is, so a slow striker's first blow is not answered before it lands."""
    world = scene.world
    at = (20.5, 12.5)
    if isinstance(target, UnitType):
        victim = world.spawn_unit(target_player, target, at)
        victim.hp = victim.max_hp = 500
        if hold:
            world.hold([victim.id])
        target_id, health = victim.id, lambda: world.units[victim.id].hp
    else:
        building = world.place_building(target_player, target, (20, 12))
        target_id, health = building.id, lambda: world.buildings[building.id].hp
    before, full = set(sprays(scene)), health()
    distance = 6 if attacker in (UnitType.ARCHER, UnitType.CATAPULT) else 1.3
    striker = world.spawn_unit(attacker_player, attacker, (at[0] - distance if side == "west" else at[0] + distance, at[1]))
    world.attack([striker.id], target_id)
    for _ in range(60 * 8):
        game.tick(1 / 60)
        if health() < full:
            break
    else:
        raise AssertionError("no blow landed")
    for _ in range(2):
        game.tick(1 / 60)
    return [s for s in sprays(scene) if s not in before]


@pytest.mark.parametrize("side, east", [("west", True), ("east", False)])
def test_a_melee_blow_sprays_blood_away_from_the_striker(play, side: str, east: bool) -> None:
    game, scene = play
    (spray,) = first_hit(game, scene, UnitType.KNIGHT, UnitType.FOOTMAN, side)
    assert spray.image == "drop" and spray.color == RED and 3 <= spray.count <= 9
    assert (spray.direction[0] > 0.5) == east


def test_an_arrow_sprays_and_a_heavier_blow_sprays_more(play) -> None:
    game, scene = play
    (arrow,) = first_hit(game, scene, UnitType.ARCHER, UnitType.PEASANT)
    assert arrow.color == RED and arrow.direction[0] > 0.5
    (blow,) = first_hit(game, scene, UnitType.KNIGHT, UnitType.PEASANT, target_player=2)
    assert blow.count >= arrow.count and blow.emitter is not arrow.emitter


def test_a_catapult_sheds_chips_and_a_building_shows_nothing(play) -> None:
    game, scene = play
    (chips,) = first_hit(game, scene, UnitType.KNIGHT, UnitType.CATAPULT)
    assert chips.color == WOOD and chips.image == "drop"
    assert first_hit(game, scene, UnitType.KNIGHT, BuildingType.FARM, target_player=2) == []


def test_armour_sparks_and_flesh_alone_does_not(play) -> None:
    game, scene = play
    scene.settings["blood"] = False
    first_hit(game, scene, UnitType.KNIGHT, UnitType.FOOTMAN)  # plate: sparks
    assert [e for e in live_effects(scene) if isinstance(e, Burst)] and not sprays(scene)


@pytest.mark.parametrize("target", [UnitType.PEASANT, UnitType.FOOTMAN, BuildingType.FARM])
def test_a_mote_of_light_flares_where_it_lands_and_opens_no_wound(play, target) -> None:
    """A healer strikes with light: whatever it lands on, a body bare or in plate or a wall, the mote goes out in a flare
    with a few sparks thrown onward, and nothing bleeds or sparks off armour as under steel."""
    game, scene = play
    (sparks,) = first_hit(game, scene, UnitType.CLERIC, target, hold=True)
    assert sparks.image == "spark" and sparks.color != RED and sparks.direction[0] > 0.5
    (flare,) = [e for e in live_effects(scene) if isinstance(e, Flare)]
    assert flare.image == "mote"
    assert not [e for e in live_effects(scene) if isinstance(e, Burst)]


def test_a_hit_out_of_sight_shows_nothing(play) -> None:
    game, scene = play
    scene.view.set_reveal(False)
    world = scene.world
    victim = world.spawn_unit(1, UnitType.FOOTMAN, (30.5, 5.5))  # a fight between two rivals, far from anything of ours
    striker = world.spawn_unit(2, UnitType.KNIGHT, (29.2, 5.5))
    world.attack([striker.id], victim.id)
    for _ in range(30):  # three seconds in tenths: a spray lives over half a second, so none slips between two looks
        game.tick(0.1)
        assert not sprays(scene)
    assert victim.hp < victim.max_hp, "the blow landed"


@pytest.mark.slow
def test_a_death_stains_the_ground_and_stains_are_bounded(play) -> None:
    """The stains' whole life is over forty seconds of a field of seventy knights, about five seconds to play:
    the slow tier."""
    game, scene = play
    world = scene.world
    for row in range(5):  # 70 peasants die under 70 knights; a catapult dies too, leaving no stain
        for col in range(14):
            victim = world.spawn_unit(1, UnitType.PEASANT, (12.5 + col, 6.5 + row * 2))
            victim.hp = 1
            knight = world.spawn_unit(0, UnitType.KNIGHT, (12.5 + col, 7.6 + row * 2))
            world.attack([knight.id], victim.id)
    engine = world.spawn_unit(1, UnitType.CATAPULT, (30.5, 20.5))
    engine.hp = 1
    world.attack([world.spawn_unit(0, UnitType.KNIGHT, (29.2, 20.5)).id], engine.id)
    for _ in range(30):  # in tenths: stains are states on a clock, not frames to look at
        game.tick(0.1)
    assert not world.player_units(1)
    live = [s for s in scene.stains if not s.done and not s.cancelled]
    assert len(scene.stains) == 70 and len(live) == 70 and sum(s.hurried for s in live) == 6
    assert all(s.sprite.opacity == Stain.OPACITY for s in live if not s.hurried)
    for _ in range(round((Stain.FADE + 0.5) * 10)):
        game.tick(0.1)
    assert len([s for s in scene.stains if not s.done]) == Stain.STAINS
    for _ in range(round((Stain.HOLD + Stain.FADE) * 10)):
        game.tick(0.1)
    assert not [s for s in scene.stains if not s.done] and all(s.sprite.is_removed for s in live)


def test_the_blood_setting_turns_sprays_and_stains_off(play) -> None:
    game, scene = play
    scene.settings["blood"] = False
    world = scene.world
    victim = world.spawn_unit(1, UnitType.PEASANT, (20.5, 12.5))
    victim.hp = 1
    world.attack([world.spawn_unit(0, UnitType.KNIGHT, (19.2, 12.5)).id], victim.id)
    for _ in range(30):  # three seconds in tenths: a spray lives over half a second
        game.tick(0.1)
        assert not sprays(scene)
    assert victim.id not in world.units and scene.bodies and not scene.stains
