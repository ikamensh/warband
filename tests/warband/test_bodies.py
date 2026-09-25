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
        assert deaths.takes(family) >= 2 and (not FAMILIES[family].spent or deaths.takes(family, spent=True) >= 2), family
        for stage in FAMILIES[family].death + FAMILIES[family].spent:
            assert all(path.is_file() for path in pieces.paths(deaths.FOLDER, family, stage.kind)), (family, stage.kind)


def test_a_unit_whose_blow_is_its_end_has_that_end_as_well_as_a_death() -> None:
    """A sapper has two ends: its keg goes up (spent, the rules' ``blast``), or it is killed first and made no blast.
    Its family holds both, and nothing else has a spent end to play."""
    assert {UNITS[kind].sound for kind in UnitType if UNITS[kind].blast} == {name for name, body in FAMILIES.items() if body.spent}


#: Every body that is not one of a race's people: the machines, the creatures, and each race's own unit (a rider on a
#: gryphon, a goblin with a keg, a walking tree, a construct).
BODIES = frozenset(UnitType) - SOLDIERS


def test_no_creature_or_machine_is_one_of_a_races_people() -> None:
    assert not SOLDIERS & (WILD | MACHINES)
    for kind in BODIES:
        assert UNITS[kind].sound and UNITS[kind].sound not in RACE_FAMILIES, kind
        assert presence.cue(UNITS[kind].sound) is not None, kind  # a body answers its orders, a creature its camp's waking


def test_every_presence_has_takes_to_rotate() -> None:
    assert set(presence.KINDS) == {UNITS[kind].sound for kind in BODIES}
    assert all(presence.takes(family) >= 2 for family in presence.KINDS)


def test_a_blow_lands_on_what_the_body_is_made_of() -> None:
    def struck(target: UnitType, armor: int) -> str:
        return sound.impact_sound(Event("hit", (1.0, 1.0), source_type="footman", target_type=target.value, target_armor=armor))

    assert struck(UnitType.GOLEM, 2) == "sword_stone" and struck(UnitType.CATAPULT, 0) == "sword_wood"
    assert struck(UnitType.FLYING_MACHINE, 2) == "sword_wood"
    assert struck(UnitType.TREANT, 3) == "sword_wood" and struck(UnitType.RUNE_GOLEM, 4) == "sword_stone"
    assert struck(UnitType.GRYPHON, 2) == "sword_armor" and struck(UnitType.SAPPER, 0) == "sword_flesh"  # their armour decides
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


def flatness(clip: np.ndarray) -> float:
    """How like noise the last third of *clip* is, from 0 (one pure tone) to 1 (white noise): a hum is near nothing."""
    tail = clip[-len(clip) // 3:]
    freqs, power = spectrum(tail * np.hanning(len(tail)))
    band = power[(freqs > 80) & (freqs < 6000)] + 1e-20
    return float(np.exp(np.mean(np.log(band))) / np.mean(band))


def test_each_races_own_unit_sounds_as_it_is_built() -> None:
    """The four own units' deaths keep their bodies through a regeneration (WB-068): the gryphon and its rider land
    after the screech; the sapper's keg goes off at once with an explosion's weight, and a sapper shot down on its way
    has none of it, crying out in a goblin's voice, far above an orc's; a treant comes down as heavy timber; and the
    rune golem's runes hum as they go out, which sets it apart from the wild golem's rubble."""
    def cues(family: str, *, spent: bool = False) -> list[np.ndarray]:
        return [deaths.death(family, take, spent=spent) for take in range(deaths.takes(family, spent=spent))]

    assert all(fall_at(clip) > 0.5 for clip in cues("gryphon"))
    window = int(0.03 * SAMPLE_RATE)
    for clip in cues("sapper", spent=True):
        loudest = int(np.argmax(np.convolve(clip ** 2, np.ones(window) / window, mode="same"))) / SAMPLE_RATE
        assert loudest < 0.4 and bass(clip) > 0.4, (loudest, bass(clip))
    assert all(bass(clip) < 0.1 for clip in cues("sapper"))

    def low(race: str) -> float:
        """The share of a race's cries' power below 600 Hz, where an orc's chest voice sits and a goblin's squeal does not."""
        def share(clip: np.ndarray) -> float:
            freqs, power = spectrum(clip)
            return float(power[freqs < 600].sum() / power.sum())
        return float(np.mean([share(pieces.read(path)) for path in pieces.paths(deaths.FOLDER, race, "cry")]))

    assert low("sapper") < low("orc") / 4
    assert all(bass(clip) > 0.4 for clip in cues("treant"))
    assert np.mean([flatness(clip) for clip in cues("rune_golem")]) < np.mean([flatness(clip) for clip in cues("golem")]) / 2


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


def test_a_sapper_shot_down_on_its_way_dies_without_a_boom(match) -> None:
    """An archer shoots an orc sapper before it reaches anything: the rules make no blast, and none is heard.  It dies
    its family's death, a goblin's cry and fall and the fuse going out, and nothing the player hears is an explosion."""
    game, scene, world = match
    sapper = world.spawn_unit(1, UnitType.SAPPER, (13.5, 10.5))
    archer = world.spawn_unit(0, UnitType.ARCHER, (10.5, 10.5))
    sapper.hp = 1
    world.hold([sapper.id])  # it stands where it is shot
    scene.camera.center_on(*to_world(sapper.pos))
    world.attack([archer.id], sapper.id)
    while sapper.id in world.units:
        game.tick(0.1)
        assert world.time < 5.0, "the archer never shot the sapper down"
    heard = set(scene.recent_sounds)
    assert deaths.cue("sapper") in heard and not heard & deaths.LOUD, heard


@pytest.mark.parametrize("seen", [True, False])
def test_a_spent_sapper_is_heard_going_up_by_a_bystander_who_sees_it_over_a_battle(tmp_path, seen: bool) -> None:
    """A spent sapper leaves no death event: its blast is its end, the family's spent cue (a fuse and a boom).  The
    player at the keyboard, a bystander to an orc sapper going up at a third side's farm, hears it over a battle's
    crowd of blows, which fills the budget every other death shares, when a peasant of its own sees the spot, and hears
    nothing of it when nobody of its own does."""
    world = World(40, 24, [[Terrain.GRASS] * 40 for _ in range(24)], 3, rng=random.Random(1),
                  races=[Race.HUMAN, Race.ORC, Race.ELF])
    for player, at in enumerate(((1, 1), (34, 1), (34, 19))):
        world.place_building(player, BuildingType.TOWN_HALL, at)
    game = Game("Warband blast", backend="mock", save_dir=tmp_path / "saves")
    try:
        scene = GameScene(world, seed=1, settings={"tutorial": False})
        scene.brains = []
        game.push(scene)
        farm = world.place_building(2, BuildingType.FARM, (18, 12))
        if seen:
            world.spawn_unit(0, UnitType.PEASANT, (20.5, 16.5))  # beside the side the keg comes from
        sapper = world.spawn_unit(1, UnitType.SAPPER, (25.5, 13.0))
        scene.camera.center_on(*to_world(farm.center))
        world.attack([sapper.id], farm.id)
        while sapper.id in world.units:
            for name in sorted(sound.IMPACTS)[:8]:
                scene.sfx(name)  # a battle on screen: the crowd's budget is full on every step
            game.tick(0.05)
            assert world.time < 10.0, "the sapper never reached the farm"
        assert farm.hp < farm.max_hp  # it went up at the farm
        assert (deaths.cue("sapper", spent=True) in scene.recent_sounds) == seen
    finally:
        game.close()
