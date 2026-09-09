"""Match outcomes through real combat, AI decisions, saves and scene input."""

import random

import pytest

from warband.ai import Brain
from warband.model import World
from warband.rules import UNITS, BuildingType, Difficulty, Terrain, UnitType, Upgrade


def battlefield(players=2):
    world = World(30, 24, [[Terrain.GRASS] * 30 for _ in range(24)], players, rng=random.Random(1))
    world.spawn_unit(0, UnitType.PEASANT, (2.5, 2.5))
    return world


def test_bankrupt_ai_surrenders_without_requiring_building_cleanup():
    """An armyless AI with no income or affordable recruit cannot recover."""
    world = battlefield()
    world.place_building(1, BuildingType.TOWN_HALL, (20, 16))
    world.place_building(1, BuildingType.TOWER, (24, 16))
    world.players[1].gold = 399
    world.step()
    assert world.winner == 0
    assert world.players[1].surrendered and not world.players[1].alive
    assert not world.player_buildings(1)
    assert [e.kind for e in world.take_events()].count("surrendered") == 1
    restored = World.from_dict(world.to_dict())
    assert restored.players[1].surrendered and restored.winner == 0


def test_ai_recovers_using_refunds_and_an_affordable_unit_outside_its_normal_plan():
    """An abandoned site can fund an archer even when the AI wanted a footman."""
    world = battlefield()
    world.place_building(1, BuildingType.FARM, (20, 16))
    barracks = world.place_building(1, BuildingType.BARRACKS, (24, 16))
    site = world.place_building(1, BuildingType.FARM, (20, 10))
    site.progress = 0
    world.players[1].gold = world.players[1].lumber = 0
    world.step()
    assert world.players[1].alive
    Brain(1).think(world, random.Random(1))
    assert barracks.queue == [UnitType.ARCHER]
    assert site.id not in world.buildings
    for _ in range(int(UNITS[UnitType.ARCHER].build_time / .05) + 2):
        world.step()
    assert any(u.type is UnitType.ARCHER for u in world.player_units(1))


@pytest.mark.parametrize("lifeline", ["worker", "miner", "builder", "queue", "affordable", "research", "human"])
def test_a_real_recovery_route_prevents_surrender(lifeline):
    """Living workers, paid production and refundable research all preserve a chance."""
    world = battlefield()
    hall = world.place_building(1, BuildingType.TOWN_HALL, (20, 16))
    world.players[1].gold = world.players[1].lumber = 0
    if lifeline in ("worker", "miner", "builder"):
        worker = world.spawn_unit(1, UnitType.PEASANT, (18.5, 16.5))
        if lifeline == "miner":
            mine = world.place_building(None, BuildingType.GOLD_MINE, (20, 10))
            worker.inside = mine.id
        if lifeline == "builder":
            site = world.place_building(1, BuildingType.FARM, (20, 10), done=False)
            site.builder, worker.constructing = worker.id, site.id
    elif lifeline == "queue":
        world.players[1].gold = UNITS[UnitType.PEASANT].cost.gold
        world.train(hall.id, UnitType.PEASANT)
    elif lifeline == "affordable":
        world.players[1].gold = UNITS[UnitType.PEASANT].cost.gold
    elif lifeline == "research":
        world.place_building(1, BuildingType.BARRACKS, (24, 16))
        smith = world.place_building(1, BuildingType.BLACKSMITH, (20, 10))
        world.players[1].gold, world.players[1].lumber = 500, 100
        world.research(smith.id, Upgrade.BLADES_1)
    else:
        world.players[1].human = True
    world.step()
    assert world.players[1].alive and world.winner is None
    if lifeline in ("research", "affordable"):
        Brain(1).think(world, random.Random(1))
        assert hall.queue == [UnitType.PEASANT]


@pytest.mark.parametrize("building", [BuildingType.FARM, BuildingType.BARRACKS])
def test_stockpiles_cannot_save_an_ai_without_production_or_supply(building):
    """Resources need both a working trainer and housing to become a unit."""
    world = battlefield()
    world.place_building(1, building, (20, 16))
    world.players[1].gold = world.players[1].lumber = 10000
    world.step()
    assert world.players[1].surrendered


def test_combat_credit_belongs_to_the_attacker_and_survives_a_save():
    """AI-versus-AI kills must not inflate the human's battle record."""
    world = battlefield(players=3)
    attacker = world.spawn_unit(1, UnitType.FOOTMAN, (12.5, 12.5))
    victim = world.spawn_unit(2, UnitType.PEASANT, (13.5, 12.5))
    victim.hp = 1
    world.attack([attacker.id], victim.id)
    for _ in range(30):
        world.step()
    assert victim.id not in world.units
    assert world.players[0].stats["units_killed"] == 0
    assert world.players[1].stats["units_killed"] == 1
    assert world.players[2].stats["units_lost"] == 1
    assert world.players[1].stats["destroyed_value"] == UNITS[victim.type].cost.gold
    restored = World.from_dict(world.to_dict())
    assert [p.stats for p in restored.players] == [p.stats for p in world.players]


def test_score_rewards_victory_and_speed_without_rewarding_stockpiles():
    """Only completed matches score; delaying a win or hoarding cannot improve it."""
    from warband.scores import score_breakdown

    world = battlefield()
    world.spawn_unit(1, UnitType.PEASANT, (20.5, 20.5))
    with pytest.raises(ValueError, match="finished"):
        score_breakdown(world, 0)
    world.winner = 0
    world.time = 300
    early = score_breakdown(world, 0)
    world.players[0].gold += 100000
    world.players[0].lumber += 100000
    assert score_breakdown(world, 0) == early
    world.time += 60
    assert sum(score_breakdown(world, 0).values()) < sum(early.values())
    world.winner = 1
    defeat = score_breakdown(world, 0)
    assert defeat["Victory"] == defeat["Swift victory"] == 0
    assert all(v >= 0 for v in defeat.values())


def test_local_scores_keep_one_best_finish_per_run_across_restarts(tmp_path):
    """Reloading a finished save must not create another leaderboard row."""
    from warband.scores import HighScores

    world = battlefield()
    world.winner = 0
    world.time = 600
    board = HighScores(tmp_path)
    kwargs = dict(player=0, seed=3, difficulty=Difficulty.NORMAL, run_id="same-campaign")
    assert board.record(world, **kwargs) == 1
    first = board.load()
    assert HighScores(tmp_path).load() == first
    assert board.record(world, **kwargs) == 1
    assert board.load() == first
    world.time = 800
    board.record(world, **kwargs)
    assert board.load() == first
    world.time = 400
    board.record(world, **kwargs)
    assert len(board.load()) == 1 and board.load()[0].score > first[0].score


def test_leaderboards_are_bounded_and_separate_match_settings(tmp_path):
    """An easy win cannot displace a hard win, and each board keeps ten records."""
    from warband.scores import HighScores

    board = HighScores(tmp_path)
    world = battlefield()
    world.winner = 0
    for i in range(12):
        world.time = 600 - i
        board.record(world, player=0, seed=i, difficulty=Difficulty.NORMAL, run_id=f"normal-{i}")
    assert len(board.load()) == 10
    assert board.load()[0].run_id == "normal-11"
    board.record(world, player=0, seed=3, difficulty=Difficulty.HARD, run_id="hard")
    larger = World(40, 32, [[Terrain.GRASS] * 40 for _ in range(32)], 3)
    larger.winner = 0
    board.record(larger, player=0, seed=3, difficulty=Difficulty.NORMAL, run_id="larger")
    assert len(board.load()) == 12
    assert len({entry.board for entry in board.load()}) == 3


@pytest.mark.parametrize("damage", ["json", "version", "entry"])
def test_damaged_high_scores_are_reported_and_preserved(tmp_path, damage):
    """A corrupt record must be visible as an error, never silently replaced."""
    import json
    from saga2d import SaveError
    from warband.scores import HighScores

    board = HighScores(tmp_path)
    world = battlefield()
    world.winner = 0
    kwargs = dict(player=0, seed=3, difficulty=Difficulty.NORMAL, run_id="first")
    board.record(world, **kwargs)
    data = json.loads(board.path.read_text())
    if damage == "version":
        data["state"]["version"] = 999
    elif damage == "entry":
        data["state"]["entries"][0]["score"] = -1
    damaged = "{broken" if damage == "json" else json.dumps(data)
    board.path.write_text(damaged)
    with pytest.raises(SaveError):
        board.record(world, **kwargs)
    assert board.path.read_text() == damaged


def test_result_leaderboard_and_loaded_finish_are_one_frozen_record(tmp_path):
    """Use the real scene stack and keyboard to finish, inspect, reload and return."""
    from saga2d import Game
    from warband.scene import GameOverScene, load_game, new_game
    from warband.score_scene import HighScoreScene
    from warband.scores import HighScores
    from warband.style import build_theme
    from warband.title import TitleScene

    game = Game("Warband scores test", backend="mock", resolution=(1280, 720), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(3, width=40, height=32)
        world = scene.world
        for unit in world.player_units(1):
            del world.units[unit.id]
        world.players[1].gold = world.players[1].lumber = 0
        world.step()
        finished = world.time
        game.push(scene)
        game.tick(.1)
        assert isinstance(game.scene, GameOverScene)
        assert world.time == finished
        records = HighScores(game.data_dir).load()
        assert len(records) == 1 and records[0].victory and records[0].race == "human"
        state = scene.get_save_state()
        for key, expected in (("b", HighScoreScene), ("escape", GameOverScene), ("t", TitleScene), ("b", HighScoreScene)):
            game.backend.inject_key(key)
            game.tick(.1)
            assert isinstance(game.scene, expected)
        for count in (3, 4, 2):
            game.backend.inject_key("p")
            game.tick(.1)
            assert game.scene.players == count
        restored = load_game(state)
        game.clear_and_push(restored)
        game.tick(.1)
        assert isinstance(game.scene, GameOverScene)
        assert restored.run_id == scene.run_id and restored.world.time == finished
        assert HighScores(game.data_dir).load() == records
    finally:
        game._teardown()


@pytest.mark.parametrize("field,value", [("run_id", None), ("run_id", ""), ("ranked", "false"), ("stats", -1)])
def test_invalid_score_metadata_in_a_match_save_is_rejected(field, value):
    """A broken campaign ID must not silently become a new leaderboard entry."""
    from saga2d import SaveError
    from warband.scene import GameScene, check_save

    state = GameScene(battlefield(), 1).get_save_state()
    if field == "stats":
        state["world"]["players"][0]["stats"]["destroyed_value"] = value
    else:
        state[field] = value
    with pytest.raises(SaveError, match="damaged"):
        check_save(state)


def test_old_saves_get_a_stable_identity_and_demos_stay_unranked():
    """Missing legacy fields are supported; an explicitly unranked save stays so."""
    from warband.scene import GameScene, load_game

    scene = GameScene(battlefield(), 1, ranked=False)
    state = scene.get_save_state()
    assert not load_game(state).ranked
    del state["run_id"]
    del state["ranked"]
    for player in state["world"]["players"]:
        del player["stats"]
        del player["surrendered"]
    first = load_game(state)
    assert first.run_id == load_game(state).run_id
    assert first.ranked and first.stats["destroyed_value"] == 0
