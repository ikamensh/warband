"""Finished-match scoring and local records, separate from game saves."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from saga2d import SaveError, SaveManager
from warband.model import World
from warband.rules import UPGRADES, Difficulty, MapTheme, Race


def score_breakdown(world: World, player: int) -> dict[str, int]:
    """Reward winning, combat, preservation and research, never idle stockpiling.

    Gold and lumber have equal score value.  Unfinished buildings and queued
    units do not count as surviving assets.  Only victories earn pace points:
    two per second remaining before twenty minutes.
    """
    owner = world.players[player]
    if world.winner is None and owner.alive:
        raise ValueError("The player's match has not finished")
    assets = [*world.player_units(player), *world.player_buildings(player, done=True)]
    preserved = sum(e.info.cost.gold + e.info.cost.lumber for e in assets if e.hp > 0)
    research = sum(UPGRADES[u].cost.gold + UPGRADES[u].cost.lumber for u in owner.upgrades)
    won = world.winner == player
    return {
        "Victory": 5000 if won else 0,
        "Enemies defeated": owner.stats["destroyed_value"] // 10,
        "Forces preserved": preserved // 20,
        "Research": research // 10,
        "Swift victory": 2 * max(0, 1200 - int(world.time)) if won else 0,
    }


@dataclass(frozen=True)
class ScoreEntry:
    run_id: str
    player: str
    race: str
    score: int
    seconds: int
    width: int
    height: int
    players: int
    difficulty: str
    theme: str
    seed: int
    victory: bool
    completed_at: str

    def __post_init__(self) -> None:
        for name in ("score", "seconds", "width", "height", "players", "seed"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"High-score {name} must be an integer")
        if min(self.score, self.seconds) < 0 or min(self.width, self.height) < 1 or self.players not in (2, 3, 4):
            raise ValueError("Invalid high-score match values")
        for name in ("run_id", "player", "completed_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"High-score {name} must be nonempty text")
        if type(self.victory) is not bool:
            raise ValueError("High-score victory must be a boolean")
        Difficulty(self.difficulty)
        MapTheme(self.theme)
        Race(self.race)
        datetime.fromisoformat(self.completed_at)

    @property
    def board(self) -> tuple[str, int, int, int]:
        return self.difficulty, self.width, self.height, self.players


class HighScores:
    """Top ten per difficulty, map size and player count; one best finish per run.

    Ties prefer the faster match, then the earlier record.  SaveManager provides
    atomic writes and backups; a damaged file is reported, never overwritten.
    """

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "high_scores" / "save_1.json"
        self.saves = SaveManager(self.path.parent)

    def load(self) -> list[ScoreEntry]:
        saved = self.saves.load(1)
        if saved is None:
            return []
        try:
            state = saved["state"]
            if type(state["version"]) is not int or state["version"] != 1:
                raise ValueError("Unsupported high-score version; expected 1")
            if not isinstance(state["entries"], list):
                raise ValueError("High-score entries must be a list")
            entries = [ScoreEntry(**entry) for entry in state["entries"]]
            if len({e.run_id for e in entries}) != len(entries):
                raise ValueError("Duplicate high-score run IDs")
            return sorted(entries, key=self._order)
        except (KeyError, TypeError, ValueError) as error:
            raise SaveError(f"Cannot read high scores at {self.path}: {error}") from error

    def record(self, world: World, *, player: int, seed: int, difficulty: Difficulty, run_id: str) -> int | None:
        """Record the finished match's score under *run_id* and return its rank on its board, if it made the top ten."""
        points = score_breakdown(world, player)
        owner = world.players[player]
        entry = ScoreEntry(run_id, owner.name, owner.race.value, sum(points.values()), int(world.time), world.width, world.height,
                           len(world.players), difficulty.value, world.theme.value, seed, world.winner == player,
                           datetime.now(timezone.utc).isoformat())
        entries = self.load()
        original = entries
        previous = next((e for e in entries if e.run_id == run_id), None)
        if previous is None or self._order(entry) < self._order(previous):
            entries = sorted([e for e in entries if e.run_id != run_id] + [entry], key=self._order)
            counts: Counter[tuple[str, int, int, int]] = Counter()
            kept = []
            for candidate in entries:
                counts[candidate.board] += 1
                if counts[candidate.board] <= 10:
                    kept.append(candidate)
            entries = kept
            if entries != original:
                self.saves.save(1, {"version": 1, "entries": [asdict(e) for e in entries]}, "WarbandHighScores")
        table = [e for e in entries if e.board == entry.board]
        return next((i for i, e in enumerate(table, 1) if e.run_id == run_id), None)

    @staticmethod
    def _order(entry: ScoreEntry) -> tuple:
        return -entry.score, entry.seconds, entry.completed_at, entry.run_id
