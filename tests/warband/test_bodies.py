"""Every body sounds like what it is (WB-069): the sound family a unit type names, its death, its presence and what a
blow on it lands on.

The first two tests are the protocol's (``docs/adding-a-unit.md``, "Its sounds"): a unit type added to the rules
fails here until its body has a death of its own with two takes on disk, unless it is one of a race's people, a
decision :data:`SOLDIERS` records.  They walk the rules' own tables, so the day a unit type is added they try it.
"""

import math
import random

import numpy as np
import pytest

from saga2d import Game
from sagaforge.synth import SAMPLE_RATE
from warband.audio import bodies, deaths, pieces, presence, sound
from warband.audio.bodies import FAMILIES, RACE_FAMILIES
from warband.sim import camps
from warband.sim.model import WILD, Event, World
from warband.sim.rules import CAMP_WATCH, UNITS, BuildingType, Race, Terrain, UnitType
from warband.ui.scene import ANSWER_GAP, ROUSE_GAP, GameScene
from warband.ui.view import to_world

#: The people of a race, who die in the voice of the race that fields them.  Adding a unit type here is the decision
#: the protocol asks for: a rider on a beast, a walking tree, a construct or a machine is not one of them.
SOLDIERS = frozenset({UnitType.PEASANT, UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT, UnitType.CLERIC})
#: What is built rather than born: nothing mends it, or it is a siege engine.
MACHINES = frozenset(kind for kind, info in UNITS.items() if not info.living or info.siege)


@pytest.mark.parametrize("unit_type", list(UnitType), ids=lambda kind: kind.value)
def test_every_unit_type_dies_in_a_cue_of_its_own_body_with_two_takes_on_disk(unit_type: UnitType) -> None:
    for race in Race:  # whoever fields it; a creature's is its own whatever the wilds' race
        family = bodies.family(unit_type, race)
        assert (family in RACE_FAMILIES) == (unit_type in SOLDIERS), (
            f"{unit_type.value} dies as {family!r}: name its body's family in its row (sound = ...), or add it to SOLDIERS")
        assert deaths.takes(family) >= 2, family
        for stage in FAMILIES[family].death:
            assert all(path.is_file() for path in pieces.paths(deaths.FOLDER, family, stage.kind)), (family, stage.kind)


def test_no_creature_or_machine_is_one_of_a_races_people() -> None:
    assert not SOLDIERS & (WILD | MACHINES)
    for kind in WILD | MACHINES:
        assert UNITS[kind].sound and UNITS[kind].sound not in RACE_FAMILIES, kind
        assert presence.cue(UNITS[kind].sound) is not None, kind  # a machine answers its orders, a creature its camp's waking


def test_every_presence_has_takes_to_rotate() -> None:
    assert set(presence.KINDS) == {UNITS[kind].sound for kind in WILD | MACHINES}
    assert all(presence.takes(family) >= 2 for family in presence.KINDS)


def test_a_blow_lands_on_what_the_body_is_made_of() -> None:
    def struck(target: UnitType, armor: int) -> str:
        return sound.impact_sound(Event("hit", (1.0, 1.0), source_type="footman", target_type=target.value, target_armor=armor))

    assert struck(UnitType.GOLEM, 2) == "sword_stone" and struck(UnitType.CATAPULT, 0) == "sword_wood"
    assert struck(UnitType.FLYING_MACHINE, 2) == "sword_wood"
    assert struck(UnitType.TROLL, 0) == "sword_flesh" and struck(UnitType.FOOTMAN, 3) == "sword_armor"


def spectrum(clip: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Frequencies and power, over a power of two: a clip's own length can be a prime, and its transform slow."""
    n = 1 << (len(clip) - 1).bit_length()
    return np.fft.rfftfreq(n, 1 / SAMPLE_RATE), np.abs(np.fft.rfft(clip, n)) ** 2


def centroid(clip: np.ndarray) -> float:
    freqs, power = spectrum(clip)
    return float((freqs * power).sum() / power.sum())


def bass(clip: np.ndarray) -> float:
    """The share of the power below 120 Hz."""
    freqs, power = spectrum(clip)
    return float(power[freqs < 120].sum() / power.sum())


def fall_at(clip: np.ndarray) -> float:
    """When the energy below 70 Hz peaks, as a share of the cue: a body hitting the ground; no cry reaches down there."""
    n = 1 << (len(clip) - 1).bit_length()
    low = np.fft.irfft(np.where(np.fft.rfftfreq(n, 1 / SAMPLE_RATE) < 70, np.fft.rfft(clip, n), 0), n)[:len(clip)]
    window = int(0.05 * SAMPLE_RATE)
    return int(np.argmax(np.convolve(low ** 2, np.ones(window) / window, mode="same"))) / len(clip)


def pitch(clip: np.ndarray) -> float:
    """The loudest frequency of *clip*."""
    magnitude = np.abs(np.fft.rfft(clip * np.hanning(len(clip))))
    return float(np.fft.rfftfreq(len(clip), 1 / SAMPLE_RATE)[np.argmax(magnitude)])


def test_the_bodies_sound_as_they_are_built() -> None:
    """What the generated pieces must keep through a regeneration, means over takes where one take cannot carry it:
    a creature's body lands after its cry, the flyer's whistle falls, and the heavy bodies sit far below the spider."""
    def cues(family: str, module=deaths) -> list[np.ndarray]:
        make = module.death if module is deaths else module.presence
        return [make(family, take) for take in range(module.takes(family))]

    for family in ("wolf", "spider", "troll"):
        assert all(fall_at(clip) > 0.5 for clip in cues(family)), family
    for take in range(len(pieces.paths(deaths.FOLDER, "flying_machine", "whistle"))):
        whistle = pieces.take(deaths.FOLDER, "flying_machine", "whistle", take, 0.8)
        sixth = len(whistle) // 6
        assert pitch(whistle[-sixth:]) < 0.8 * pitch(whistle[:sixth]), take
    spider = np.mean([centroid(clip) for clip in cues("spider", presence)])
    for heavy in ("troll", "golem"):
        assert np.mean([centroid(clip) for clip in cues(heavy, presence)]) < spider / 4, heavy
    assert np.mean([centroid(clip) for clip in cues("troll")]) < np.mean([centroid(clip) for clip in cues("spider")]) / 2
    assert np.mean([bass(clip) for clip in cues("golem", presence)]) > np.mean([bass(clip) for clip in cues("spider", presence)]) + 0.2


# -- In the scene ------------------------------------------------------------------------------------


def a_match(tmp_path, width: int = 32, height: int = 24, halls=((4, 4), (25, 18))) -> tuple[Game, GameScene, World]:
    """Humans (player 0, at the keyboard) against orcs on open grass, silent: the scene's own record of what it sounded
    is what is read."""
    world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], 2, rng=random.Random(1),
                  races=[Race.HUMAN, Race.ORC])
    for player, at in enumerate(halls):
        world.place_building(player, BuildingType.TOWN_HALL, at)
    game = Game("Warband bodies", backend="mock", save_dir=tmp_path / "saves")
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    return game, scene, world


@pytest.fixture
def match(tmp_path):
    game, scene, world = a_match(tmp_path)
    yield game, scene, world
    game.close()


def test_an_orc_catapult_and_a_wolf_die_in_their_own_bodies(match) -> None:
    game, scene, world = match
    for player, kind in ((1, UnitType.CATAPULT), (world.neutral, UnitType.WOLF)):
        body = world.spawn_unit(player, kind, (10.5, 10.5))
        world.spawn_unit(0, UnitType.PEASANT, (8.5, 10.5))  # its eyes: the death is heard where the player sees
        world.update_vision()
        body.hp = 0
        game.tick(0.1)
        assert world.entity(body.id) is None and deaths.cue(kind.value) in scene.recent_sounds, kind
    assert not {"orc_death", "human_death"} & set(scene.recent_sounds)


def test_ordered_machines_answer_once_a_family_and_soldiers_leave_it_to_the_race(match) -> None:
    game, scene, world = match
    engines = [world.spawn_unit(0, UnitType.CATAPULT, (8.5 + i, 10.5)).id for i in range(6)]
    footmen = [world.spawn_unit(0, UnitType.FOOTMAN, (8.5 + i, 12.5)).id for i in range(3)]
    scene.select(footmen)
    scene.command_move((12.5, 14.5))
    assert "command" in scene.recent_sounds and not any(name.endswith("_presence") for name in scene.recent_sounds)
    scene.select(engines + footmen)
    scene.command_move((12.5, 14.5))
    scene.command_move((13.5, 14.5))  # a second click at once: the answer is not heard twice
    assert list(scene.recent_sounds).count("catapult_presence") == 1
    game.tick(ANSWER_GAP + 0.1)
    scene.command_attack((14.5, 14.5))
    assert list(scene.recent_sounds).count("catapult_presence") == 2


@pytest.mark.parametrize("side", [0, 90, 180, 225, 270])  # 225: straight across the lair from the first post
def test_a_camp_woken_from_any_side_is_heard_once_for_each_kind_of_guard(tmp_path, side: int) -> None:
    """A footman (sight 5) walks up to a camp of four from *side*, with nothing of the player's over it: the guards it
    wakes stand up to 9.6 tiles away on the far side of the lair, out of its sight, and are heard as they charge into
    it, each kind once however long the camp stays awake."""
    game, scene, world = a_match(tmp_path, halls=((0, 0), (29, 21)))  # the town halls in the corners, far out of the camp's sight
    try:
        camp = camps.place(world, (14, 10), [UnitType.TROLL, UnitType.WOLF, UnitType.WOLF, UnitType.SPIDER], 500)
        lair = world.buildings[camp.lair]
        scene.camera.center_on(*to_world(lair.center))
        angle = math.radians(side)
        (cx, cy), reach = lair.center, CAMP_WATCH + 1.0
        footman = world.spawn_unit(0, UnitType.FOOTMAN, (cx + math.cos(angle) * reach, cy + math.sin(angle) * reach))
        footman.hp = 100 * footman.max_hp  # it stands the whole camp's charge, so the camp stays awake
        world.move([footman.id], lair.center)
        while not camp.roused:
            game.tick(0.25)
            assert world.time < 3.0, "the footman never woke the camp"
        woke = world.time
        while world.time < woke + 3.0:
            game.tick(0.25)
        heard = sorted(name for name in scene.recent_sounds if name.endswith("_presence"))
        assert heard == ["spider_presence", "troll_presence", "wolf_presence"]
        while world.time < woke + 3.0 + ROUSE_GAP + 0.5:  # awake past the cue's own gap: still once a kind
            game.tick(0.25)
        assert camp.roused and sorted(name for name in scene.recent_sounds if name.endswith("_presence")) == heard
    finally:
        game.close()


def test_a_camp_woken_where_the_player_sees_nothing_wakes_in_silence(match) -> None:
    game, scene, world = match
    camp = camps.place(world, (14, 14), [UnitType.TROLL, UnitType.WOLF], 500)
    lair = world.buildings[camp.lair]
    scene.camera.center_on(*to_world(lair.center))  # on screen, under the fog
    world.spawn_unit(1, UnitType.KNIGHT, (lair.center[0] + CAMP_WATCH - 1.0, lair.center[1]))
    for _ in range(8):
        game.tick(0.25)
    assert camp.roused and not any(name.endswith("_presence") for name in scene.recent_sounds)
