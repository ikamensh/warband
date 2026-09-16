"""The player's profile: a name, a rating estimated from every rated match, and the record behind it.

The rating is on the Elo scale the difficulty settings are measured on
(:data:`warband.ai.DIFFICULTY_ELO`), updated by Glicko so that it also
carries how sure the estimate is: a new player starts at 1000 with a
deviation of 350 and each match narrows it.  A match is one observation
against the difficulty played; a match left early counts a fraction of a loss
unless the leaver was under attack or behind in material, see :func:`standing`.
The profile keeps the results themselves and folds the rating from them, so
a result that replaces an earlier one for the same match (a match finished
after it was left, or replayed from a save) re-rates everything consistently.
Stored at ``<data_dir>/profile/save_1.json`` with Saga2D's atomic saves.
"""

from __future__ import annotations

import getpass
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from saga2d import SaveError, SaveManager
from warband.model import World
from warband.rules import UNDER_ATTACK_COOLDOWN, Difficulty, Layout, MapTheme, Race

PROFILE_VERSION = 1
RATING_START = 1000.0
DEVIATION_START = 350.0
DEVIATION_FLOOR = 40.0  # the estimate never gets so sure that a result stops moving it
PROVISIONAL_ABOVE = 150.0  # a deviation still this wide is shown as provisional
OPPONENT_DEVIATION = 50.0  # how sure the ladder is of a difficulty's rating (docs/ai-ladder.md)
EARLY_EXIT_WEIGHT = 0.2  # a match left with no enemy at the gates and no material disadvantage: this much of a loss
MATERIAL_MARGIN = 0.9  # under this share of the strongest rival's material, the leaver was behind
GATES = 8.0  # tiles: an enemy fighter this close to one of your buildings is at your gates
NAME_LENGTH = 16
OUTCOMES = ("victory", "defeat", "resigned", "left")
OUTCOME_NAMES = {"victory": "Victory", "defeat": "Defeat", "resigned": "Resigned", "left": "Left"}
_Q = math.log(10) / 400


@dataclass(frozen=True)
class Rating:
    value: float
    deviation: float

    @property
    def provisional(self) -> bool:
        return self.deviation > PROVISIONAL_ABOVE

    def __str__(self) -> str:
        return f"{round(self.value)} ± {round(self.deviation)}"


def _g(deviation: float) -> float:
    return 1 / math.sqrt(1 + 3 * _Q * _Q * deviation * deviation / (math.pi * math.pi))


def expected_score(rating: Rating, opponent: float) -> float:
    """The chance of beating an opponent rated *opponent* (a difficulty's measured rating)."""
    return 1 / (1 + 10 ** (-_g(OPPONENT_DEVIATION) * (rating.value - opponent) / 400))


def rated(rating: Rating, opponent: float, score: float, weight: float = 1.0) -> Rating:
    """*rating* after one match against *opponent* that scored *score* (1 a win, 0 a loss).

    *weight* under 1 makes the match that fraction of an observation: it moves
    the rating and narrows the deviation by about that share.
    """
    g = _g(OPPONENT_DEVIATION)
    e = expected_score(rating, opponent)
    precision = 1 / (rating.deviation * rating.deviation) + weight * _Q * _Q * g * g * e * (1 - e)
    value = rating.value + _Q / precision * weight * g * (score - e)
    return Rating(value, max(DEVIATION_FLOOR, math.sqrt(1 / precision)))


@dataclass(frozen=True)
class MatchResult:
    """One rated match as the profile remembers it."""

    run_id: str
    played_at: str
    outcome: str  # victory | defeat | resigned | left
    weight: float  # the share of an observation it is (1 unless left early on even terms)
    reason: str  # why it weighs what it weighs
    difficulty: str
    opponent: int  # the difficulty's rating when the match was played
    opponents: int  # how many computer players
    race: str
    width: int
    height: int
    theme: str
    layout: str
    seed: int
    seconds: int
    replay: bool  # whether a recording was kept

    def __post_init__(self) -> None:
        for name in ("run_id", "played_at", "reason"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"Match {name} must be text")
        if not self.run_id.strip():
            raise ValueError("Match run_id must be nonempty text")
        if self.outcome not in OUTCOMES:
            raise ValueError(f"Match outcome must be one of {OUTCOMES}")
        if type(self.weight) not in (int, float) or not 0 < self.weight <= 1:
            raise ValueError("Match weight must be a number in (0, 1]")
        for name in ("opponent", "opponents", "width", "height", "seed", "seconds"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"Match {name} must be an integer")
        if self.opponents < 1 or min(self.width, self.height) < 1 or self.seconds < 0:
            raise ValueError("Invalid match values")
        if type(self.replay) is not bool:
            raise ValueError("Match replay must be a boolean")
        Difficulty(self.difficulty)
        Race(self.race)
        MapTheme(self.theme)
        Layout(self.layout)
        datetime.fromisoformat(self.played_at)

    @property
    def score(self) -> float:
        return 1.0 if self.outcome == "victory" else 0.0

    @property
    def won(self) -> bool:
        return self.outcome == "victory"


@dataclass(frozen=True)
class RatingChange:
    """What one result did to the rating."""

    result: MatchResult
    before: Rating
    after: Rating
    replaced: bool  # the match had a result already, which this one replaces

    @property
    def delta(self) -> int:
        return round(self.after.value) - round(self.before.value)

    def __str__(self) -> str:
        return f"{round(self.before.value)} → {round(self.after.value)} ({self.delta:+d})"


def fold(results: Iterable[MatchResult]) -> Rating:
    rating = Rating(RATING_START, DEVIATION_START)
    for result in results:
        rating = rated(rating, result.opponent, result.score, result.weight)
    return rating


def plural(count: int, noun: str, nouns: str | None = None) -> str:
    """``1 defeat``, ``2 defeats``."""
    return f"{count} {noun if count == 1 else nouns or noun + 's'}"


def default_name() -> str:
    """The account's login name, or Warlord when there is none to read."""
    try:
        name = getpass.getuser().strip()
    except OSError:
        name = ""
    return clean_name(name) or "Warlord"


def clean_name(name: str) -> str:
    """*name* trimmed to what a profile accepts: printable text, at most :data:`NAME_LENGTH` characters."""
    return "".join(c for c in name if c.isprintable()).strip()[:NAME_LENGTH].strip()


class Profile:
    """The one local player: their name and every rated result, with the rating folded from them.

    A damaged file raises SaveError at load and is never overwritten.
    """

    def __init__(self, data_dir: Path, *, name: str, results: list[MatchResult]) -> None:
        self.path = data_dir / "profile" / "save_1.json"
        self.saves = SaveManager(self.path.parent)
        self.name = name
        self.results = results

    @classmethod
    def load(cls, data_dir: Path) -> Profile:
        """The profile on disk, or a fresh one named after the login when there is none yet."""
        path = data_dir / "profile" / "save_1.json"
        saved = SaveManager(path.parent).load(1)
        if saved is None:
            return cls(data_dir, name=default_name(), results=[])
        try:
            state = saved["state"]
            if state["version"] != PROFILE_VERSION:
                raise ValueError(f"unsupported profile version {state['version']!r}")
            name = clean_name(state["name"])
            if not name:
                raise ValueError("the profile has no name")
            results = [MatchResult(**row) for row in state["results"]]
            if len({r.run_id for r in results}) != len(results):
                raise ValueError("a match has two results")
        except (KeyError, TypeError, ValueError) as error:
            raise SaveError(f"Cannot read the profile at {path}: {error}") from error
        return cls(data_dir, name=name, results=results)

    def save(self) -> None:
        self.saves.save(1, {"version": PROFILE_VERSION, "name": self.name, "results": [asdict(r) for r in self.results]}, "WarbandProfile")

    @property
    def rating(self) -> Rating:
        return fold(self.results)

    def rename(self, name: str) -> None:
        name = clean_name(name)
        if not name:
            raise ValueError("A name needs at least one character")
        self.name = name
        self.save()

    def record(self, result: MatchResult) -> RatingChange:
        """Add *result* (replacing an earlier result of the same match) and say what it did to the rating."""
        before = self.rating
        replaced = any(r.run_id == result.run_id for r in self.results)
        self.results = [r for r in self.results if r.run_id != result.run_id] + [result]
        self.save()
        return RatingChange(result, before, self.rating, replaced)

    def history(self) -> list[RatingChange]:
        """Every result with the rating before and after it, oldest first."""
        changes = []
        rating = Rating(RATING_START, DEVIATION_START)
        for result in self.results:
            after = rated(rating, result.opponent, result.score, result.weight)
            changes.append(RatingChange(result, rating, after, False))
            rating = after
        return changes

    def counts(self) -> dict[str, int]:
        """Victories, defeats and matches left early (resigned or abandoned)."""
        return {"victories": sum(r.outcome == "victory" for r in self.results), "defeats": sum(r.outcome == "defeat" for r in self.results),
                "left": sum(r.outcome in ("resigned", "left") for r in self.results)}


# -- Leaving a match -------------------------------------------------------------------


@dataclass(frozen=True)
class Standing:
    """Where a player stands at the moment they leave: what decides how much the leaving counts."""

    material: int  # the cost of the player's living units and finished buildings
    rival: int  # the same for the strongest living rival
    under_attack: bool  # a blow landed on them lately, or an enemy fighter is at their gates

    @property
    def behind(self) -> bool:
        return self.material < MATERIAL_MARGIN * self.rival

    @property
    def weight(self) -> float:
        return 1.0 if self.under_attack or self.behind else EARLY_EXIT_WEIGHT

    @property
    def reason(self) -> str:
        if self.under_attack:
            return "left under attack: a full loss"
        if self.behind:
            return f"left behind in material ({self.material:,} against {self.rival:,}): a full loss"
        return f"left with no enemy at the gates and no material disadvantage: {EARLY_EXIT_WEIGHT:g} of a loss"


def material(world: World, player: int) -> int:
    """Gold and lumber standing on the map for *player*: living units and finished buildings at cost."""
    units = sum(u.info.cost.gold + u.info.cost.lumber for u in world.player_units(player) if u.hp > 0)
    buildings = sum(b.info.cost.gold + b.info.cost.lumber for b in world.player_buildings(player, done=True) if b.hp > 0)
    return units + buildings


def under_attack(world: World, player: int) -> bool:
    """A blow landed on *player* within the alert cooldown, or an enemy fighter stands within :data:`GATES` of their buildings."""
    if world.time - world.players[player].last_alert < UNDER_ATTACK_COOLDOWN:
        return True
    for building in world.player_buildings(player):
        for unit in world.units_near(building.center, GATES):
            if unit.player != player and not unit.is_worker and unit.hp > 0:
                return True
    return False


def standing(world: World, player: int) -> Standing:
    rivals = [p.id for p in world.players if p.id != player and p.alive]
    return Standing(material(world, player), max((material(world, rival) for rival in rivals), default=0), under_attack(world, player))
