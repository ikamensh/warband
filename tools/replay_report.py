"""Read a match as a story: what the units' thousands of steps add up to, and why the winner won.

    uv run python tools/replay_report.py match --agents grandmaster,medium --seed 7
    uv run python tools/replay_report.py replay ~/.warband/replays/save_r….json
    uv run python tools/replay_report.py compare --agents grandmaster,medium --seeds 12 --focus grandmaster

``match`` plays one fresh AI match and narrates it; ``replay`` plays a kept
recording back (a human's has no brain logs, so its episodes come from the
orders' effects and the fights alone); ``compare`` narrates a pairing over
seeds from both corners and aggregates: what the winner's numbers look like
against the loser's, how often an early lead holds, and — with ``--focus`` —
how one agent loses.  The engine is :mod:`warband.league.narrate`; the
ratings themselves stay with ``tools/arena.py``.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()

from warband.league import arena, narrate  # noqa: E402
from warband.league.arena import MatchSpec  # noqa: E402
from warband.league.narrate import Narrator, autopsy, factor_gaps, lead_holds, render  # noqa: E402


def _spec(agents: str, seed: int, minutes: float) -> MatchSpec:
    return MatchSpec(seed=seed, agents=tuple(agents.split(",")), minutes=minutes, **arena.board(seed))


def _match(args: argparse.Namespace) -> None:
    story = narrate.narrate(_spec(args.agents, args.seed, args.minutes))
    print(render(story, max_episodes=args.episodes))
    if args.save:
        Path(args.save).write_text(json.dumps(story.to_record()) + "\n", encoding="utf-8")
        print(f"\nstory saved to {args.save}")


def _replay(args: argparse.Namespace) -> None:
    from warband.records.replay import Playback, Replay  # the league cannot import records; a tool can

    data = json.loads(Path(args.path).expanduser().read_text(encoding="utf-8"))
    replay = Replay.from_dict(data.get("state", data))  # a kept file wraps the recording in a save envelope
    playback = Playback(replay)
    narrator = Narrator(playback.world)
    names = tuple("human" if seat == replay.human else replay.difficulty.value
                  for seat in range(playback.world.seats))
    while not playback.done:
        playback.step()
        narrator.observe(playback.world, playback.world.take_events())
    story = narrator.finish(playback.world, agent_names=names, seed=replay.seed,
                            winner=playback.world.winner)
    print(render(story, max_episodes=args.episodes))
    print(f"\nplayback faithful: {playback.faithful}")
    if args.save:
        Path(args.save).write_text(json.dumps(story.to_record()) + "\n", encoding="utf-8")
        print(f"story saved to {args.save}")


def _compare(args: argparse.Namespace) -> None:
    agents = tuple(args.agents.split(","))
    if len(agents) != 2:
        raise SystemExit("compare is for a duel: --agents A,B")
    stories = []
    started = time.perf_counter()
    total = 2 * args.seeds
    for seed in range(args.first_seed, args.first_seed + args.seeds):
        for pair in (agents, agents[::-1]):
            spec = MatchSpec(seed=seed, agents=pair, minutes=args.minutes, **arena.board(seed))
            if not arena.playable(spec):
                total -= 1
                continue
            story = narrate.narrate(spec)
            stories.append(story)
            claim = story.verdict[0].text if story.verdict else ""
            print(f"  seed {seed} {pair[0]} vs {pair[1]}: "
                  f"{'draw' if story.winner is None else pair[story.winner] + ' wins'} "
                  f"in {story.seconds / 60:.1f} min — {claim}")
    wins = statistics.fmean(1.0 if s.winner is not None and s.agents[s.winner] == agents[0] else 0.0
                            for s in stories) if stories else math.nan
    print(f"\n{agents[0]} took {wins:.0%} of {len(stories)} games "
          f"({time.perf_counter() - started:.0f}s, {total} playable)")
    print("\nmedian factor, winner against loser:")
    for name, (won, lost) in factor_gaps(stories).items():
        print(f"  {won:>10.2f}  {lost:>10.2f}  {name}" if name == "producer_idle_share"
              else f"  {won:>10.0f}  {lost:>10.0f}  {name}")
    for at in (180.0, 300.0, 480.0):
        for key in ("worth", "army_value", "workers"):
            held, n = lead_holds(stories, at, key)
            if n:
                print(f"  ahead on {key} at {at / 60:.0f} min won {held:.0%} (n={n})")
    if args.focus:
        print()
        for line in autopsy(stories, args.focus):
            print(line)
    if args.save:
        Path(args.save).write_text("\n".join(json.dumps(s.to_record()) for s in stories) + "\n",
                                   encoding="utf-8")
        print(f"\n{len(stories)} stories saved to {args.save}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    match = sub.add_parser("match", help="play one AI match and tell its story")
    match.add_argument("--agents", default="master,medium")
    match.add_argument("--seed", type=int, default=7)
    match.add_argument("--minutes", type=float, default=20.0)
    match.add_argument("--episodes", type=int, default=48)
    match.add_argument("--save", help="write the story as one JSON line here")
    match.set_defaults(run=_match)
    replay = sub.add_parser("replay", help="tell a kept recording's story")
    replay.add_argument("path")
    replay.add_argument("--episodes", type=int, default=48)
    replay.add_argument("--save", help="write the story as one JSON line here")
    replay.set_defaults(run=_replay)
    compare = sub.add_parser("compare", help="narrate a pairing over seeds and aggregate why games are won")
    compare.add_argument("--agents", default="grandmaster,medium")
    compare.add_argument("--seeds", type=int, default=12, help="boards, each from both corners")
    compare.add_argument("--first-seed", type=int, default=1)
    compare.add_argument("--minutes", type=float, default=20.0)
    compare.add_argument("--focus", help="also autopsy this agent's losses")
    compare.add_argument("--save", help="write every story as JSON lines here")
    compare.set_defaults(run=_compare)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
