"""Random play against Warband's rules and scene; any exception or broken invariant is a bug.

    uv run python tools/fuzz.py                 # 12 AI-vs-AI games and 12 random-input scene runs
    uv run python tools/fuzz.py --games 40 --monkey 0

AI games run every difficulty against every other — which is both kinds of
brain, since Hard and Master are :class:`warband.brains.pro_ai.ProBrain` — for up to fifteen simulated minutes,
checking the world every simulated second: units stand on open ground,
hit points and resources stay in range, buildings never overlap, the
blocked grid matches the map, hidden units are inside something real.
The monkey runs feed the game scene random keys, clicks, drags and scrolls
on the mock backend, including through every overlay.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.sim import mapgen  # noqa: E402
from warband.brains.ai import make_brain  # noqa: E402
from warband.brains.pro_ai import PRO, ProBrain, RaceBrain  # noqa: E402
from warband.sim.model import BLOCKING, World  # noqa: E402
from warband.sim.rules import BUILDINGS, SIM_DT, BuildingType, Difficulty  # noqa: E402
from saga2d.testing.cpu_budget import CpuBudget  # noqa: E402

GAME_MINUTES = 15


def check_world(world: World) -> None:
    blocked_by_building = set()
    for b in world.buildings.values():
        assert b.hp <= max(b.max_hp, 1) and (b.hp > 0 or b.info.mine is not None), ("building hp", b)
        assert 0 <= b.progress <= b.info.build_time, ("progress", b)
        for tile in b.tiles():
            assert world.in_bounds(tile), ("building off map", b)
            assert tile not in blocked_by_building, ("buildings overlap", b)
            blocked_by_building.add(tile)
            assert world._blocked[tile[1] * world.width + tile[0]], ("building tile not blocked", b)
        if b.builder is not None:
            builder = world.units.get(b.builder)
            assert builder is not None and builder.constructing == b.id, ("dangling builder", b)
        assert len(b.queue) <= 5
    for y in range(world.height):
        for x in range(world.width):
            blocked = world._blocked[y * world.width + x]
            expected = world.terrain[y][x] in BLOCKING or (x, y) in blocked_by_building
            assert bool(blocked) == expected, ("blocked grid mismatch", (x, y))
    for u in world.units.values():
        assert 0 < u.hp <= u.max_hp, ("unit hp", u)
        assert 0 <= u.x <= world.width and 0 <= u.y <= world.height, ("unit off map", u)
        if u.inside is not None:
            mine = world.buildings.get(u.inside)
            assert mine is not None and mine.info.mine is not None, ("inside a missing mine", u)
        elif u.constructing is not None:
            site = world.buildings.get(u.constructing)
            assert site is not None and site.builder == u.id and not site.done, ("constructing a missing site", u)
        else:
            assert world.passable(*u.tile), ("unit on a blocked tile", u, world.terrain_at(u.tile))
        assert world.players[u.player].alive, ("unit of a dead player", u)
    for p in world.players:
        assert p.gold >= 0 and p.lumber >= 0, ("negative resources", p)
        has_stuff = bool(world.player_units(p.id)) or bool(world.player_buildings(p.id))
        assert p.alive == has_stuff, ("alive without anything, or dead with something", p)
        visible, explored = world.visible[p.id], world.explored[p.id]
        assert all(explored[i] for i in range(len(visible)) if visible[i]), "visible but unexplored"


STALL_SECONDS = 20.0


def check_progress(world: World, stalled: dict[int, tuple[tuple[float, float], float]]) -> None:
    """A unit that is walking (has orders, is not hidden) must get somewhere: staying within a tile of
    where it was for STALL_SECONDS while in the move state is a deadlock in the movement code.  A
    tile, not a point: a unit bouncing between its tile centre and a corner it cannot cut is as stuck
    as one standing still, and a bounce whose period divides the sampling interval looks still."""
    for u in world.units.values():
        if not u.orders or u.hidden or u.state != "move":
            stalled.pop(u.id, None)
            continue
        origin, since = stalled.get(u.id, (None, world.time))
        if origin is None or math.dist(origin, u.pos) > 1.0:
            stalled[u.id] = (u.pos, world.time)
        elif world.time - since > STALL_SECONDS:
            raise AssertionError(f"unit {u.id} ({u.type.value}) of player {u.player} stuck for {STALL_SECONDS}s within a tile of "
                                 f"{origin} at {u.pos} with {u.orders[0]} path {u.path[:3]}")


def ai_games(seeds: range, *, budget: CpuBudget | None = None) -> int:
    failures = 0
    outcomes: Counter[str] = Counter()
    for seed in seeds:
        rng = random.Random(seed)
        players = rng.choice((2, 2, 3, 4, 6, 8, 16))
        width, height = mapgen.dimensions(rng.choice(mapgen.sizes_for(players)), players)
        try:
            world = mapgen.generate(seed=seed, width=width, height=height, players=players, human=None)
            # Every setting, which now means both kinds of brain: Hard and Master
            # are ProBrains, and they drive the model down paths the others never
            # take (several build orders in flight, wounded soldiers walking home,
            # peasants sent scouting). The invariants have to hold there too.
            brains = [make_brain(p.id, rng.choice(list(Difficulty)), seed) for p in world.players]
            check_world(world)
            stalled: dict[int, tuple[tuple[float, float], float]] = {}
            for tick in range(int(GAME_MINUTES * 60 / SIM_DT)):
                if budget:
                    budget.checkpoint()
                if world.winner is not None:
                    break
                for brain in brains:
                    brain.think(world, rng)
                world.step()
                world.take_events()
                if tick % 20 == 0:
                    check_world(world)
                    check_progress(world, stalled)
            kills = sum(1 for p in world.players if not p.alive)
            armies = [len([u for u in world.player_units(p.id) if not u.is_worker]) for p in world.players]
            buildings = [len(world.player_buildings(p.id)) for p in world.players]
            assert any(len(world.player_buildings(p.id, BuildingType.BARRACKS)) for p in world.players), "nobody built a barracks"
            assert sum(armies) > 0 or kills, "nobody trained an army"
            outcomes["decided" if world.winner is not None else "eliminations" if kills else "undecided"] += 1
            levels = "/".join("P" if isinstance(b, ProBrain) else "G" if isinstance(b, RaceBrain) else b.difficulty.value[0].upper() for b in brains)
            print(f"  seed {seed}: {players} players {width}x{height} [{levels}] → {world.time / 60:.1f} min, winner {world.winner}, armies {armies}, buildings {buildings}")
        except Exception:
            failures += 1
            print(f"AI game seed {seed} ({players} players, {width}x{height}):")
            traceback.print_exc(limit=5)
    print(f"AI games: {len(seeds)} played, {failures} failed, outcomes {dict(outcomes)}")
    return failures


def monkey_runs(seeds: range, steps: int = 500, *, budget: CpuBudget | None = None) -> int:
    from saga2d import Game
    from warband.ui.controls import SCHEMES
    from warband.ui.scene import DEFAULT_SETTINGS, GameScene, new_game
    from warband.ui.style import build_theme
    from warband.ui.title import TitleScene

    # The scene's own keys, every letter a card or a scheme gives a meaning, and the Modal scheme's punctuation.
    keys = sorted({k for keys in GameScene.controls for k in ((keys,) if isinstance(keys, str) else keys)}
                  | set("abcdefghklmpqrstuvwxz123456789") | {"return", "escape", "period", "comma"})
    failures = 0
    for seed in seeds:
        rng = random.Random(seed)
        controls = list(SCHEMES)[seed % len(SCHEMES)]  # each scheme in turn
        with tempfile.TemporaryDirectory() as save_dir:
            game = Game("Monkey", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=Path(save_dir) / "saves")  # high scores stay in the temp dir too
            try:
                game.push(TitleScene(settings=dict(DEFAULT_SETTINGS, controls=controls)))
                game.tick(1 / 60)
                for key in ("n", "return"):
                    game.backend.inject_key(key)
                    game.tick(1 / 60)
                assert isinstance(game.scene, GameScene), [type(s).__name__ for s in game.scenes]
                for _step in range(steps):
                    roll = rng.random()
                    if roll < 0.4:
                        game.backend.inject_key(rng.choice(keys), shift=rng.random() < 0.15, ctrl=rng.random() < 0.15)
                    elif roll < 0.75:
                        x, y = rng.randrange(1280), rng.randrange(800)
                        button = rng.choice(("left", "left", "right"))
                        game.backend.inject_click(x, y, button)
                        if rng.random() < 0.5:
                            game.backend.inject_drag(x + rng.randrange(-200, 200), y + rng.randrange(-200, 200), rng.uniform(-50, 50), rng.uniform(-50, 50), button=button)
                        game.backend.inject_release(x + rng.randrange(-200, 200), y + rng.randrange(-200, 200), button)
                    elif roll < 0.88:
                        game.backend.inject_mouse_move(rng.randrange(1280), rng.randrange(800))
                    elif roll < 0.97:
                        game.backend.inject_scroll(rng.randrange(1280), rng.randrange(800), 0, rng.uniform(-5, 5))
                    elif roll < 0.99:  # the OS has the last word on the window: any size, at any moment
                        game.backend.inject_resize(rng.randrange(640, 3841), rng.randrange(400, 2161))
                    else:
                        game.backend.set_fullscreen(not game.fullscreen)
                    for _ in range(rng.choice((1, 1, 2, 12))):
                        game.tick(1 / 60)
                        if budget:
                            budget.checkpoint()
                    if game.scene is None:
                        break
                assert len(game.scenes) <= 3, ("scene stack grew", [type(s).__name__ for s in game.scenes])
                scene = next((s for s in game.scenes if isinstance(s, GameScene)), None)
                if scene is not None:
                    check_world(scene.world)
            except Exception:
                failures += 1
                print(f"monkey seed {seed} ({controls} controls), stack {[type(s).__name__ for s in game.scenes]}:")
                traceback.print_exc(limit=6)
            finally:
                game.close()
    print(f"monkey runs: {len(seeds)} played, {failures} failed")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--monkey", type=int, default=12)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--steps", type=int, default=500, help="random inputs per monkey run")
    parser.add_argument("--cpu-percent", type=float, default=25, help="CPU allowance, percent of one core")
    args = parser.parse_args()
    try:
        budget = CpuBudget(args.cpu_percent)
    except ValueError as error:
        parser.error(str(error))
    failures = ai_games(range(args.seed, args.seed + args.games), budget=budget)
    if args.monkey:
        failures += monkey_runs(range(args.seed, args.seed + args.monkey), steps=args.steps, budget=budget)
    budget.checkpoint()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
