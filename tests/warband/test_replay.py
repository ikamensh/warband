"""Replays: the world a match began in plus every order given since is the match itself."""

import json
import random

import pytest

from saga2d import SaveError
from warband import mapgen
from warband.ai import make_brain
from warband.model import RuleError, World
from warband.replay import Playback, Replay, ReplayStore, digest
from warband.rules import SIM_DT, BuildingType, Difficulty, Terrain, UnitType


def played_match(seconds: float = 60.0, *, seed: int = 7, brains=(Difficulty.HARD, Difficulty.MEDIUM), reload_at: float | None = None) -> tuple[World, Replay]:
    """A recorded match between two brains on a generated map; *reload_at* seconds in, the match goes on
    from a save of that moment with fresh brains, as the game does when a slot is loaded."""
    world = mapgen.generate(seed=seed, players=2, human=None)
    replay = Replay.begin(world, seed=seed, difficulty=brains[1], human=0)
    minds = [make_brain(i, difficulty) for i, difficulty in enumerate(brains)]
    rng = random.Random(seed)
    for step in range(int(seconds / SIM_DT)):
        if reload_at is not None and step == int(reload_at / SIM_DT):
            world = World.from_dict(world.to_dict())
            replay.reloaded(world)
            minds = [make_brain(i, difficulty) for i, difficulty in enumerate(brains)]
        for brain in minds:
            brain.think(world, rng)
        world.step()
        world.take_events()
    return world, replay


@pytest.mark.parametrize("seed, brains", [(7, (Difficulty.HARD, Difficulty.MEDIUM)), (11, (Difficulty.EASY, Difficulty.MASTER)), (23, (Difficulty.MASTER, Difficulty.HARD))])
def test_replaying_the_logged_orders_reproduces_the_match(seed, brains):
    """Property: giving the logged orders at their ticks to the start snapshot ends in the same world, bit for bit,
    and the recording survives JSON — which is what makes a replay file a replay at all."""
    world, replay = played_match(seed=seed, brains=brains)
    assert len(replay.orders) > 20, "the brains give orders"
    replay.finish(world, "victory")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    assert playback.run() is playback.world
    assert playback.done and playback.faithful
    assert digest(playback.world) == digest(world)
    assert playback.world.tick == world.tick


def test_a_match_that_went_on_from_a_save_still_replays_faithfully():
    """Loading a save rebuilds the world from its dictionary; the log marks the moment so playback does the same."""
    world, replay = played_match(60.0, reload_at=25.0)
    replay.finish(world, "victory")
    assert [row[1] for row in replay.orders].count("reload") == 1
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    playback.run()
    assert playback.faithful


def test_only_orders_from_outside_the_simulation_are_logged():
    """A smart order on a peasant at a mine is one log row, not the harvest it turns into; the walk a trained
    unit takes to its rally point is the simulation's own doing and is not logged either."""
    world = World(20, 20, [[Terrain.GRASS] * 20 for _ in range(20)], 2, rng=random.Random(1))
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (10, 10))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (6.5, 6.5))
    replay = Replay.begin(world, seed=1, difficulty=Difficulty.EASY, human=0)
    world.smart([peasant.id], mine.center)
    world.set_rally(hall.id, (8.5, 3.5))
    world.train(hall.id, UnitType.PEASANT)
    for _ in range(int(40 / SIM_DT)):
        world.step()
    assert len(world.player_units(0)) == 2, "the recruit came out and walked off"
    assert [row[1] for row in replay.orders] == ["smart", "set_rally", "train"]
    assert replay.orders[0][2] == [[peasant.id], [10.0 + 1.5, 10.0 + 1.5]] or replay.orders[0][2][1] == list(mine.center)


def test_a_refused_order_is_logged_and_refused_again_on_playback():
    """The log records what was asked, not what was granted, so a replay meets the same rule at the same tick."""
    world = World(20, 20, [[Terrain.GRASS] * 20 for _ in range(20)], 2, rng=random.Random(1))
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.players[0].gold = 0
    replay = Replay.begin(world, seed=1, difficulty=Difficulty.EASY, human=0)
    with pytest.raises(RuleError):
        world.train(hall.id, UnitType.PEASANT)
    world.step()
    assert [row[1] for row in replay.orders] == ["train"]
    replay.finish(world, "left")
    playback = Playback(replay)
    playback.run()
    assert playback.faithful and not playback.world.buildings[hall.id].queue


def test_replays_are_kept_per_match_and_a_damaged_file_is_reported(tmp_path):
    world, replay = played_match(10.0)
    replay.finish(world, "victory")
    store = ReplayStore(tmp_path)
    assert not store.exists("match-1")
    store.save("match-1", replay, {"outcome": "victory"})
    assert store.exists("match-1")
    loaded = store.load("match-1")
    assert loaded.orders == replay.orders and loaded.end == replay.end and loaded.difficulty is Difficulty.MEDIUM
    assert Playback(loaded).run().tick == world.tick
    store.path("match-1").write_text("{broken", encoding="utf-8")
    with pytest.raises(SaveError):
        store.load("match-1")
    store.delete("match-1")
    assert not store.exists("match-1")
    with pytest.raises(SaveError):
        store.load("match-1")


def test_a_replay_from_another_format_or_with_a_bad_log_is_refused():
    world, replay = played_match(5.0)
    data = replay.to_dict()
    with pytest.raises(ValueError):
        Replay.from_dict({**data, "version": 99})
    with pytest.raises(ValueError):
        Replay.from_dict({**data, "orders": [[0, "spawn_unit", [0, "peasant", [1.0, 1.0]], {}]]})
    with pytest.raises(ValueError):
        Replay.from_dict({**data, "orders": list(reversed(data["orders"]))})
