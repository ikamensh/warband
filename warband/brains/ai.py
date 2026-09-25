"""The computer opponent: keep the peasants busy, build in a sensible order,
train soldiers without pause, defend the base and attack in growing waves.

One :class:`Brain` per AI player thinks once a second of simulation
time; everything it does goes through :class:`World` commands, checked
with the matching ``can_*`` query first, so the model never raises here.
Each brain plays its race's army plan (see :data:`ARMY_PLANS`), shifted
towards counters of the enemy composition it can see. Strategic expansion
and military decisions retain their previous map knowledge.
Workers share the model's automatic policy, limited to known safe resources.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from warband.sim.model import (MINE_CLEARANCE, RIFT, Attack, AttackMove, Build, Building, Deposit, Harvest, Point, Pos, Repair, Salvage, Unit,
                           World, dist, int_sum, plain_sum, rect_gap, tile_center)
from warband.sim import mapgen
from warband.sim.races import RACES
from warband.sim.rules import (BUILDINGS, EXPANSION_GOLD, GOLD_PER_TRIP, MINE_SLOTS, PLAYABLE_UNITS, UPGRADES, BuildingType, Difficulty,
                               Race, Resource, Terrain, UnitType, Upgrade)
from warband.sim.worker_knowledge import KnownMine
from warband.brains.unique import Commander

try:
    from warband.sim import _native  # the site search in C, built only with the compiled simulation (warband/league/fastsim.py)
except ImportError:  # the source runs, as it does in the game
    _native = None  # type: ignore[assignment]

EXPAND_DISTANCE: Final = 14.0  # a mine farther than this from the hall gets a hall of its own
LOW_MINE_GOLD: Final = 6000  # a mine this low means the next hall is planned now, while gold still comes in


def pace(mine: KnownMine) -> float:
    """How fast a deposit pays against a gold mine: the gold its face gives with every place taken, *slots* trips of
    *trip* every mining time, over a mine's.  A mine is 1, a Mother Lode 1.5 (a mine's trip at twelve places), a seam
    0.3 (a fifth of the trip at twelve).  What a deposit is worth is its pace and its stock, never its kind."""
    return mine.slots * mine.trip / (MINE_SLOTS * GOLD_PER_TRIP)


def worth_a_hall(mine: KnownMine) -> bool:
    """Whether a deposit is worth putting a hall beside: one whose stock never runs out, or one holding the work
    :data:`LOW_MINE_GOLD` is to a mine at its own pace, so a lode seating twelve is low at nine thousand.

    A seam is always worth one -- it never runs dry -- but it pays a fifth of a mine's trip, so
    :func:`hall_first` ranks it behind every deposit a brain could take instead."""
    return mine.endless or mine.gold >= LOW_MINE_GOLD * pace(mine)


def hall_first(mine: KnownMine, away: float) -> tuple[bool, float]:
    """How a brain orders the deposits it could put its next hall at, by stock and then by pace: gold that runs out
    before gold that never does -- taking the seam ahead of a rich mine would trade a hundred gold a trip for twenty,
    and the seam does not run away while the mines are drunk -- and then the nearest for what it pays, the walk over
    the :func:`pace`, so a lode half as far again as a mine ranks with it.  Between mines that is the nearest, as it
    always was."""
    return (mine.endless, away / pace(mine))
CREEP_REACH: Final = 34.0  # tiles from home a camp has to be within before an army is walked to it
CREEP_RETRY: Final = 120.0  # seconds a camp that beat the army off is left alone
CREEP_PATIENCE: Final = 150.0  # seconds the army will stand at a den before giving it up, whatever it has left:
# a lair it cannot reach or cannot break would otherwise hold the whole army at it for the rest of the match
CLAIM_DISTANCE: Final = 8.0  # a mine with an own hall this near is claimed
MAX_HALLS: Final = 3
DEFEND_RADIUS: Final = 9.0
TOWER_STRIKERS: Final = 8  # peasants sent at an enemy tower frame going up on our ground (WB-044)
BUILD_MIN_DISTANCE: Final = 2
BUILD_MAX_DISTANCE: Final = 11
SPLIT_REACH: Final = 4  # tiles round a site within which the ground beside it must still join up (splits_ground)
NOOK: Final = 0  # open tiles a site may shut off whole: none, as a builder or a recruit is set down beside it
#: A building of each size that needs no other: the ground a site needs depends on its size alone, so the planner sites
#: a building whose prerequisite has not stood up yet as this one would be sited (:func:`auto_site`).
UNLOCKED_OF_SIZE: Final[dict[int, BuildingType]] = {info.size: kind for kind, info in BUILDINGS.items()
                                                   if info.requires is None and info.mine is None}
#: Shared upgrades first, then whatever arts the brain's race has (see :mod:`warband.sim.races`).  The Keep stands
#: where the first tier is bought out and the second is worth its gate; the master weapons come last of all.
RESEARCH_ORDER: Final = (Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                  Upgrade.KEEP, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE, Upgrade.BLESSING, Upgrade.BLOODLUST,
                  Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_3, Upgrade.ARROWS_3)


def with_prerequisites(researched: set[Upgrade], upgrade: Upgrade) -> list[Upgrade]:
    """*upgrade* behind every upgrade it waits for that the player has not got, lowest first.  A research order
    names the tier a brain wants, not the gates on the way to it: the rules moved the Keep in front of the second
    tier, and ``bred.py`` is bred once and never edited, so its orders would silently stop at the gate."""
    wanted: list[Upgrade] = []
    for needed in UPGRADES[upgrade].requires:
        if needed not in researched:
            for lower in with_prerequisites(researched, needed):
                if lower not in wanted:
                    wanted.append(lower)
    wanted.append(upgrade)
    return wanted

#: Target shares of the army by skeleton type: FOOTMAN line, ARCHER ranged,
#: KNIGHT shock, CATAPULT siege, CLERIC healer.  Shares of types the difficulty
#: profile does not use (cavalry without tech, siege without siege, healers
#: without clerics) are dropped and the rest renormalised.  The flying machine
#: is no share of an army: it is unarmed, the eyes a brain may keep (``ProProfile.scout``).
#: The scout rider's shares went with it (WB-064); the plans are renormalised
#: where they are used, so the rest keep their proportions.
ARMY_PLANS: Final[dict[Race, dict[UnitType, float]]] = {
    Race.HUMAN: {UnitType.FOOTMAN: 0.35, UnitType.ARCHER: 0.30, UnitType.KNIGHT: 0.20,
                 UnitType.CATAPULT: 0.05, UnitType.CLERIC: 0.05},
    Race.ORC: {UnitType.FOOTMAN: 0.45, UnitType.ARCHER: 0.15, UnitType.KNIGHT: 0.30,
               UnitType.CATAPULT: 0.05, UnitType.CLERIC: 0.00},
    Race.ELF: {UnitType.FOOTMAN: 0.25, UnitType.ARCHER: 0.45, UnitType.KNIGHT: 0.10,
               UnitType.CATAPULT: 0.05, UnitType.CLERIC: 0.00},
    Race.DWARF: {UnitType.FOOTMAN: 0.40, UnitType.ARCHER: 0.35, UnitType.KNIGHT: 0.05,
                 UnitType.CATAPULT: 0.15, UnitType.CLERIC: 0.05},
}

_MELEE_TYPES: Final = (UnitType.FOOTMAN, UnitType.KNIGHT)
RAIDERS: Final = (UnitType.KNIGHT,)  # what rides at the enemy's peasants: the fast melee the stables train


def fighters(units: list[Unit]) -> list[Unit]:
    """The army among *units*: what is armed and not a worker.  A flying machine is unarmed: eyes, not a soldier; a
    sapper's blow is its end, and it is never the army's (``unique.Commander`` runs it)."""
    return [u for u in units if not u.is_worker and u.info.damage and not u.info.blast]


def flyers_over(world: World, player: int, radius: float) -> list[Unit]:
    """Enemy flyers *player* sees within *radius* of one of its buildings."""
    own = world.player_buildings(player)
    return [u for u in world.units.values()
            if u.flying and u.player != player and u.hp > 0 and not world.players[u.player].neutral
            and world.is_visible(player, u.tile) and any(dist(u.pos, b.center) < radius for b in own)]


def answer_flyers(world: World, player: int, army: list[Unit], radius: float) -> None:
    """Shoot down what flies over our ground: the idle shooters within reach walk at an enemy flyer seen within
    *radius* of our buildings, ready to fire (an attack-move, so they come back rather than chase a faster flyer
    across the map).  Melee is never sent: nothing it could do there."""
    for flyer in flyers_over(world, player, radius):
        shooters = [u.id for u in army if not u.orders and world.can_strike(u, flyer) and dist(u.pos, flyer.pos) <= 12.0]
        if shooters:
            world.attack_move(shooters[:3], flyer.pos)


def known_enemy_buildings(world: World, player: int) -> list:
    """Enemy structures *player* has seen, as that player's own memory records them.

    The AI is bound by the fog the human plays under: every question it asks
    about the map goes through ``world.worker_knowledge``, which holds the last
    observed footprint of every structure this player has laid eyes on and
    nothing else. A razed building stays remembered until somebody looks at the
    ground again, which is exactly what a player would believe.
    """
    return [record for record in world.worker_knowledge[player].buildings.values()
            if record.player is not None and record.player != player and world.players[record.player].alive
            and not world.players[record.player].neutral]  # a lair is a camp to clear, never an opponent to beat


CAMP_REACH: Final = 10.0  # tiles from a remembered lair its guards hold: what a brain keeps its halls and peasants out of
#: The farthest a camp's worth takes an army, in ordinary creeping walks: a lode's hundred thousand is worth the walk to
#: the middle of a Huge map (57 tiles from home with two seats), and nothing is worth an army four minutes from home.
CAMP_WALK: Final = 2.0
#: Tiles a moving threat may drift from where a soldier is already attack-moving before the order is given again.  An order
#: given anew every pass to a soldier wedged in a crowd restarts its walk, and with it the watchdog that would have walked
#: it round the bodies in its way: fuzz seed 82 had a footman pressed into its own crowd for good.
REDIRECT: Final = 2.0


def heading_to(unit: Unit, point: Point) -> bool:
    """Whether *unit* is already attack-moving to within :data:`REDIRECT` of *point*."""
    order = unit.order
    return isinstance(order, AttackMove) and dist(order.target, point) <= REDIRECT


#: A side that has lost track of every rival goes hunting (:class:`Hunt`): these are the hunt's numbers.
HUNT_SQUARE: Final = 8  # tiles on a side of the squares whose last sighting a side keeps
HUNT_LOOK: Final = 2.0  # seconds between two looks at which of the squares' middles the side sees
HUNT_DUE: Final = 60.0  # a square unseen this long (or never seen) is due another look
HUNT_PARTY: Final = 3  # soldiers that join the flyers in the search
HUNT_FLYERS_ALONE: Final = 20.0  # seconds the flyers search alone before the soldiers join them


def lost_track(world: World, player: int, guess: Point) -> bool:
    """Whether *player* has lost every rival: no building of theirs remembered (``known_enemy_buildings``), none of
    them in sight, and the place its expedition guessed they started from (*guess*) already looked at.  Only the side's
    own fog and memory answer it.  At the start of a match nothing of the rival is known either, but the guess is
    still to be looked at: the expedition to it is the search then."""
    if known_enemy_buildings(world, player) or not world.is_explored(player, (int(guess[0]), int(guess[1]))):
        return False
    return not any(unit.player != player and not world.players[unit.player].neutral and not unit.hidden
                   and world.is_visible(player, unit.tile) for unit in world.units.values())


class Squares:
    """When a side last saw each square of :data:`HUNT_SQUARE` tiles, and which square a searcher goes to next: the
    memory the hunt (:class:`Hunt`) and the player's scouts (``warband.brains.adjutant``) search by.  A square counts as
    seen when the side sees its middle, from the first look on: its own sight, nothing else."""

    def __init__(self) -> None:
        self.seen: list[float] = []  # per square, row after row: when the side last saw its middle (-inf: never)
        self.columns = 0
        self.next_look = 0.0

    def middle(self, world: World, square: int) -> Point:
        """The middle of *square*'s tiles inside the map."""
        x = min((square % self.columns) * HUNT_SQUARE + HUNT_SQUARE // 2, world.width - 1)
        y = min((square // self.columns) * HUNT_SQUARE + HUNT_SQUARE // 2, world.height - 1)
        return (x + 0.5, y + 0.5)

    def square_at(self, point: Point) -> int:
        """The square *point* (tiles, inside the map) lies in."""
        return int(point[1]) // HUNT_SQUARE * self.columns + int(point[0]) // HUNT_SQUARE

    def look(self, world: World, player: int, *, now: bool = False) -> None:
        """Note the squares whose middle *player* sees now; every :data:`HUNT_LOOK` seconds, or *now*."""
        if world.time < self.next_look and not now:
            return
        self.next_look = world.time + HUNT_LOOK
        if not self.seen:
            self.columns = -(-world.width // HUNT_SQUARE)
            self.seen = [-math.inf] * (self.columns * -(-world.height // HUNT_SQUARE))
        visible, width = world.visible[player], world.width
        for square in range(len(self.seen)):
            x, y = self.middle(world, square)
            if visible[int(y) * width + int(x)]:
                self.seen[square] = world.time

    def pick(self, world: World, origin: Point, candidates: list[int], due: float,
             early: dict[int, float] | None = None) -> int:
        """The nearest of *candidates* that is due (unseen for *due* seconds, or for its own time in *early*); with
        none due, the least recently seen."""
        now = world.time
        ready = [square for square in candidates
                 if now - self.seen[square] >= (due if early is None else early.get(square, due))]
        if ready:
            return min(ready, key=lambda square: (dist(origin, self.middle(world, square)), square))
        return min(candidates, key=lambda square: (self.seen[square], dist(origin, self.middle(world, square)), square))


class Hunt:
    """The search a side makes for rivals it has lost track of (:func:`lost_track`): the last peasant of a razed base,
    or a hall raised where nobody has looked.  Without it a won match ran to the clock, the winner's army standing on
    the ground its expedition had guessed and cleared, and nobody going anywhere else (Master mirrors ran to the cap 36
    times in 288 once the scout riders that used to stumble on such a peasant were gone, WB-064).

    The side keeps, for each square of :data:`HUNT_SQUARE` tiles, when it last saw its middle (:class:`Squares`).
    While it has lost track, its flyers search, and after :data:`HUNT_FLYERS_ALONE` seconds (at once, with no flyer)
    its :data:`HUNT_PARTY` fastest soldiers join them.  A searcher with nothing to do takes the nearest square that is
    due (unseen for :data:`HUNT_DUE` seconds, or never seen) and nobody else is bound for, or with none due the least
    recently seen; the square it was bound for counts as seen once it stops, so ground it cannot reach is not asked for
    again and again.  Soldiers attack-move: what they find they fight, and the army follows up, because what they see
    is what the brain's attack targets are made of."""

    def __init__(self) -> None:
        self.squares = Squares()
        self.since = -1.0  # when the side lost track; negative while it has not
        self.party: dict[int, int] = {}  # a searcher's id -> the square it was sent to (-1: not sent yet)

    def step(self, world: World, player: int, soldiers: list[Unit], lost: bool) -> set[int]:
        """Look, and while *lost* keep the searchers searching; the ids of the searchers, which the brain's army leaves
        to the hunt.  *soldiers* are those the brain could spare for it."""
        squares = self.squares
        squares.look(world, player)
        if not lost:
            self.since = -1.0
            self.party.clear()
            return set()
        if self.since < 0.0:
            self.since = world.time
        party = {uid: square for uid, square in self.party.items() if uid in world.units}
        for unit in world.player_units(player):
            if unit.flying and unit.id not in party:
                party[unit.id] = -1
        if not any(world.units[uid].flying for uid in party) or world.time - self.since >= HUNT_FLYERS_ALONE:
            walking = int_sum(1 for uid in party if not world.units[uid].flying)
            spare = sorted((u for u in soldiers if u.id not in party), key=lambda u: (-world.speed_of(u), u.id))
            for unit in spare[:max(0, HUNT_PARTY - walking)]:
                party[unit.id] = -1
        taken = {square for square in party.values() if square >= 0}
        for uid in sorted(party):
            unit, square = world.units[uid], party[uid]
            if square >= 0 and unit.orders:
                continue
            if square >= 0:
                squares.seen[square] = world.time  # as near as the ground lets it come: looked at
                taken.discard(square)
            every = range(len(squares.seen))
            square = squares.pick(world, unit.pos, [square for square in every if square not in taken] or list(every), HUNT_DUE)
            party[uid] = square
            taken.add(square)
            point = squares.middle(world, square)
            if unit.info.damage:
                world.attack_move([uid], point)
            else:
                world.move([uid], point)
        self.party = party
        return set(party)


def known_camps(world: World, player: int) -> list:
    """The creature lairs *player* has laid eyes on, as its own memory records them.

    A camp is not an opponent -- it never grows, never attacks and never wins -- so it is kept out of
    :func:`known_enemy_buildings` and asked for separately by the brains that go and clear one.
    """
    return [record for record in world.worker_knowledge[player].buildings.values()
            if record.player is not None and world.players[record.player].neutral]


def camp_worth(world: World, player: int, record: Any) -> float:
    """How much farther than :data:`CREEP_REACH` (or a profile's ``creep_reach``) a brain walks to clear the camp
    in *record*: the stock of the deposit it guards -- the known deposit nearest its lair, within its guards' reach --
    over an expansion's, never less than one and never more than :data:`CAMP_WALK`.  A camp beside a third is worth
    the walk it always was; one beside a Mother Lode keeps a hundred thousand from whoever clears it, and is worth
    twice the walk, as long as the lode is ours to take: nearer one of our halls than anything of a rival's we know
    of, the rule an expansion is chosen by.  A seam holds no stock, so its camp is worth the ordinary walk: what it
    keeps is a trickle."""
    guarded = [m for m in known_mines(world, player) if dist(m.center, record.center) < CAMP_REACH]
    if not guarded:
        return 1.0
    deposit = min(guarded, key=lambda m: dist(m.center, record.center))
    worth = deposit.gold / EXPANSION_GOLD
    if worth <= 1.0:
        return 1.0
    halls = [b.center for b in world.player_buildings(player, BuildingType.TOWN_HALL)]
    rivals = [r.center for r in known_enemy_buildings(world, player)]
    if not halls or (rivals and min(dist(deposit.center, c) for c in rivals) < min(dist(deposit.center, c) for c in halls)):
        return 1.0  # not ours to take yet: the ordinary walk
    return min(worth, CAMP_WALK)


def guarded(world: World, player: int, point: Point, reach: float = CAMP_REACH) -> bool:
    """Whether a camp *player* knows about holds the ground at *point*.

    A deposit with a lair beside it is not an expansion: a hall put up there is a hall whose peasants
    walk into the guards, and the brain that does that feeds them one at a time for the whole match.
    Clear the camp first and the ground stops being guarded, because the lair leaves the memory with it.
    """
    return any(dist(record.center, point) < reach for record in known_camps(world, player)
               if record.id in world.buildings)


_RINGS: Final[dict[tuple[int, int], tuple[tuple[float, int, int], ...]]] = {}


def keeps_paths_open(world: World, player: int, pos: Pos, size: int) -> bool:
    """Whether a building at *pos* leaves a tile of clearance to every one of *player*'s, so peasants can always get through."""
    for b in world.player_buildings(player):
        gap_x = max(b.x - (pos[0] + size), pos[0] - (b.x + b.size), 0)
        gap_y = max(b.y - (pos[1] + size), pos[1] - (b.y + b.size), 0)
        if max(gap_x, gap_y) < 1:
            return False
    return True


def splits_ground(world: World, pos: Pos, size: int) -> bool:
    """Whether a building of *size* at *pos* cuts the open ground beside it in two: the tiles along its sides no longer
    reach each other round it within :data:`SPLIT_REACH` tiles, bar a nook of at most :data:`NOOK` tiles shut off whole.

    A farm filling a gap between two woods is such a cut, and so is a blacksmith across the one way out of a base
    between the trees: fuzz seeds 98 and 110 walled a computer player's base in that way, and every attack after it
    piled the army into the corner of the base nearest the target.  Only the side tiles matter, as a path through the
    site enters and leaves by them; and a walker steps diagonally only where both tiles beside the step are open, so
    tiles joined by a walk are joined edge to edge.  A way round further off than the reach counts as a cut.  So does a
    nook of three tiles between a barracks and the water: the recruits it set down there never came out (seed 106)."""
    width, height, blocked = world.width, world.height, world._blocked
    left, top, right, bottom = pos[0], pos[1], pos[0] + size, pos[1] + size
    x0, y0 = max(0, left - SPLIT_REACH), max(0, top - SPLIT_REACH)
    x1, y1 = min(width - 1, right - 1 + SPLIT_REACH), min(height - 1, bottom - 1 + SPLIT_REACH)
    sides = [(x, top - 1) for x in range(left, right)] + [(x, bottom) for x in range(left, right)]
    sides += [(left - 1, y) for y in range(top, bottom)] + [(right, y) for y in range(top, bottom)]
    seen: set[Pos] = set()
    ways = 0  # pieces of the ground beside the site that are more than a nook
    for start in sides:
        sx, sy = start
        if not (x0 <= sx <= x1 and y0 <= sy <= y1) or blocked[sy * width + sx] or start in seen:
            continue
        seen.add(start)
        piece, tiles, open_edge = [start], 1, False
        while piece:
            x, y = piece.pop()
            if (x == x0 and x0 > 0) or (x == x1 and x1 < width - 1) or (y == y0 and y0 > 0) or (y == y1 and y1 < height - 1):
                open_edge = True  # it goes on past the window
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (x0 <= nx <= x1 and y0 <= ny <= y1 and not (left <= nx < right and top <= ny < bottom)
                        and not blocked[ny * width + nx] and (nx, ny) not in seen):
                    seen.add((nx, ny))
                    piece.append((nx, ny))
                    tiles += 1
        if open_edge or tiles > NOOK:
            ways += 1
            if ways > 1:
                return True
    return False


def crowds(pos: Pos, size: int, other: Pos, other_size: int) -> bool:
    """Whether two sites are within a tile of each other, counting the clearance."""
    return abs(pos[0] - other[0]) < size + other_size - 1 and abs(pos[1] - other[1]) < size + other_size - 1


def site_search(world: World, building_type: BuildingType, player: int, anchor: Point, rng: random.Random,
                near: int, far: int, taken: Sequence[tuple[Pos, int]] = ()) -> Pos | None:
    """Where *player* should put *building_type* near *anchor*: every spot at least *near* tiles plus the building's
    size out and at most *far* (Chebyshev), scored by its distance plus a tiebreak of up to two tiles drawn from *rng*
    in :func:`site_ring`'s order, and the best that :func:`first_site` allows.  The compiled simulation draws and
    searches in C (``warband.sim._native.site_search``), from :func:`site_inputs`."""
    size = BUILDINGS[building_type].size
    left, top = int(anchor[0]) - size // 2, int(anchor[1]) - size // 2
    ring = site_ring(near + size, far)
    if _native is not None and not world.gates:
        # The native scanner only knows ground and nearby bodies.  Bastion
        # sites also have to preserve a walkable route through the gate.
        return _native.site_search(ring, left, top, rng.random, *site_inputs(world, building_type, player, taken))
    candidates = [(distance + rng.random() * 2, (left + dx, top + dy)) for distance, dx, dy in ring]
    return first_site(world, building_type, player, candidates, taken)


def first_site(world: World, building_type: BuildingType, player: int, candidates: list[tuple[float, Pos]],
               taken: Sequence[tuple[Pos, int]] = ()) -> Pos | None:
    """The first of *candidates* (``(score, spot)`` pairs), in their sorted order, that no site in *taken* crowds,
    where :meth:`World.placeable` lets *player* put *building_type*, that :func:`keeps_paths_open` and that does not
    cut the ground in two (:func:`splits_ground`)."""
    size = BUILDINGS[building_type].size
    candidates.sort()
    free = (pos for _score, pos in candidates if not any(crowds(pos, size, other, other_size) for other, other_size in taken))
    for pos in world.placeable(building_type, player, free):
        if keeps_paths_open(world, player, pos, size) and not splits_ground(world, pos, size):
            return pos
    return None


def site_inputs(world: World, building_type: BuildingType, player: int, taken: Sequence[tuple[Pos, int]]) -> tuple[Any, ...]:
    """What ``warband.sim._native.site_search`` needs beside the ring to search as :func:`first_site` does: first whether
    any spot can do at all (the prerequisite stands), then the ground and what stands on it, the ley rifts, which
    only a vault may stand on, square, and the reach and nook of :func:`splits_ground`."""
    blockers = world.placement_blockers(building_type, player)
    standing, mines = blockers if blockers is not None else ([], [])
    return (blockers is not None, BUILDINGS[building_type].size, taken, world.terrain, Terrain.GRASS, world._blocked,
            world.explored[player], standing, mines, [b.rect for b in world.player_buildings(player)], world.width,
            world.height, MINE_CLEARANCE, world.rifts, RIFT, building_type is BuildingType.VAULT, SPLIT_REACH, NOOK)


def site_ring(inner: int, outer: int) -> tuple[tuple[float, int, int], ...]:
    """``(math.hypot(dx, dy), dx, dy)`` for every offset out to *outer* tiles and at least *inner* away
    (Chebyshev), row by row: the spots a site search draws a random tiebreak for, in the order it draws."""
    ring = _RINGS.get((inner, outer))
    if ring is None:
        ring = _RINGS[(inner, outer)] = tuple((math.hypot(dx, dy), dx, dy)
                                              for dy in range(-outer, outer + 1) for dx in range(-outer, outer + 1)
                                              if max(abs(dx), abs(dy)) >= inner)
    return ring


def known_mines(world: World, player: int) -> list[KnownMine]:
    """Gold *player* has found; its contents are what they were when last seen."""
    return list(world.worker_knowledge[player].mines.values())


def auto_site(world: World, building_type: BuildingType, player: int, near: Point, rng: random.Random,
              planned: Sequence[tuple[BuildingType, Pos]] = ()) -> Pos | None:
    """Where the planner puts *building_type* when a player lets it choose, looking from *near* (their camera): a hall
    by the nearest gold mine they know that no hall of theirs, standing or planned in *planned*, has claimed; anything
    else about their hall nearest *near*, the way the brains place their own (:func:`site_search`), clear of *planned*.
    A building whose prerequisite does not stand yet is sited as :data:`UNLOCKED_OF_SIZE` would be, for a plan that
    waits for the prerequisite: the world's own search offers no spot at all before it stands."""
    halls = [b.center for b in world.player_buildings(player, BuildingType.TOWN_HALL)]
    halls += [(pos[0] + BUILDINGS[kind].size / 2, pos[1] + BUILDINGS[kind].size / 2) for kind, pos in planned if kind is BuildingType.TOWN_HALL]
    own = [b.center for b in world.player_buildings(player)]
    anchor = min(halls or own, key=lambda point: dist(point, near)) if halls or own else near
    if building_type is BuildingType.TOWN_HALL:
        free = [mine for mine in known_mines(world, player)
                if worth_a_hall(mine) and not any(dist(mine.center, hall) <= CLAIM_DISTANCE for hall in halls)
                and not guarded(world, player, mine.center)]
        if not free:
            return None
        anchor = min(free, key=lambda mine: hall_first(mine, dist(mine.center, anchor))).center
    taken = [(pos, BUILDINGS[kind].size) for kind, pos in planned]
    requires = BUILDINGS[building_type].requires
    stands = requires is None or bool(world.player_buildings(player, requires, done=True))
    sited = building_type if stands else UNLOCKED_OF_SIZE[BUILDINGS[building_type].size]
    return site_search(world, sited, player, anchor, rng, BUILD_MIN_DISTANCE, BUILD_MAX_DISTANCE, taken)


def _shift(plan: dict[UnitType, float], deltas: dict[UnitType, float]) -> None:
    """Move share between plan entries in place.  A shift whose types are not
    all in the plan is skipped; the survivors are clamped at zero and
    renormalised so the shares still add up to one."""
    if any(t not in plan for t in deltas):
        return
    for unit_type, delta in deltas.items():
        plan[unit_type] += delta
    for unit_type in plan:
        plan[unit_type] = max(0.0, plan[unit_type])
    total = plain_sum(plan.values())
    if total > 0:
        for unit_type in plan:
            plan[unit_type] /= total


@dataclass(frozen=True)
class Profile:
    """How a difficulty plays: economy size, tempo and which parts of the tech tree it uses."""

    peasants: int
    think_every: float
    first_wave: int
    wave_growth: int
    barracks: int
    towers: int
    tech: bool  # mill, blacksmith, stables, upgrades
    siege: bool  # workshop and catapults
    clerics: bool  # church and clerics
    harass: bool  # the first two knights sent at the enemy's peasants
    reserve: int  # gold kept back before research
    repair: bool  # peasants mend damaged buildings once the fighting there is over
    first_attack: float = 0.0  # seconds of play before its first wave may go out
    creep: bool = False  # sends its army to clear a creature camp when it is plainly big enough
    unique: bool = True  # buys its race's own unit when what it sees says so (WB-068, warband.brains.unique)


PROFILES: Final[dict[Difficulty, Profile]] = {
    # Easy leaves a plain opening its first eight minutes (WB-014). Since soldiers fight soldiers first (b26e016,
    # 2026-09-15), its wave of ten at four and a half minutes killed a plain opening's first soldiers and then its
    # peasants, and ai_report's scripted opening beat it 5 times in 32 where it had beaten it 6 in 8; held to
    # minute eight, 23 in 32.
    Difficulty.EASY: Profile(peasants=7, think_every=2.0, first_wave=10, wave_growth=2, barracks=1, towers=0, tech=False, siege=False,
                             clerics=False, harass=False, reserve=1500, repair=False, first_attack=480.0),
    # Medium is what Normal and Hard both used to be. They measured 994 and 1000
    # Elo and split their games 55/45, so the fuller of the two plays for both:
    # it techs, sieges, fields healers and sends raiders, which makes a more
    # interesting opponent at the same strength.
    Difficulty.MEDIUM: Profile(peasants=14, think_every=0.5, first_wave=8, wave_growth=4, barracks=3, towers=3, tech=True, siege=True,
                               clerics=True, harass=True, reserve=500, repair=True, creep=True),
}


def make_brain(player: int, difficulty: Difficulty, seed: int = 0, *, own_units: bool = True):
    """The opponent a difficulty setting means; without *own_units*, one that never buys its race's own unit (WB-068),
    for the tools that price it.

    Easy and Medium are this module's :class:`Brain`; Hard and Master are
    :class:`warband.brains.pro_ai.ProBrain`, which is a different and much stronger
    player; Grandmaster is a ProBrain too, on a posture bred for the race it leads
    (:class:`warband.brains.pro_ai.RaceBrain`). Master has three postures of about one strength, and *seed* — the
    map's — draws which one this player gets, a third of the games each, so
    every client of an online match and every replay of a seed agree, and two
    Master players in one game differ.
    Imported late because ``pro_ai`` imports this module.
    """
    from dataclasses import replace

    from warband.brains.pro_ai import PRO_PROFILES, ProBrain, RaceBrain

    if difficulty in PROFILES:
        brain = Brain(player, difficulty)
        if not own_units:
            brain.profile = replace(brain.profile, unique=False)
        return brain
    if difficulty is Difficulty.GRANDMASTER:
        from warband.brains.bred import BRED, BRED_FOR_LAYOUT  # tables of profiles, imported late as pro_ai is

        return RaceBrain(player, BRED, seed, BRED_FOR_LAYOUT, own_units=own_units)
    postures = PRO_FOR[difficulty]
    profile = PRO_PROFILES[postures[(seed + player) % len(postures)]]
    return ProBrain(player, profile if own_units else replace(profile, unique=False))


#: Which ProBrain profiles stand behind each of the upper difficulties.
PRO_FOR: Final[dict[Difficulty, tuple[str, ...]]] = {Difficulty.HARD: ("pro-hard",),
                                              Difficulty.MASTER: ("pro-vanguard", "pro-warden", "pro-rush")}

#: What each setting is worth, measured on the ladder and anchored at Medium =
#: 1000, over every map size and all five layouts. Produced by
#: ``tools/arena.py``; the games behind the numbers are in ``docs/ai-ladder.md``. Shown on the New game screen so a player can see what
#: they are picking rather than guess from a word.
DIFFICULTY_ELO: Final[dict[Difficulty, int]] = {
    Difficulty.EASY: 559,
    Difficulty.MEDIUM: 1000,
    Difficulty.HARD: 1378,
    Difficulty.MASTER: 1573,
    Difficulty.GRANDMASTER: 1917,
}

#: One line per setting, for the same screen. Kept short enough to fit beside
#: the map preview.
DIFFICULTY_NOTES: Final[dict[Difficulty, str]] = {
    Difficulty.EASY: "Seven peasants, one barracks, no attack before minute eight.",
    Difficulty.MEDIUM: "Techs, sieges, heals and raids. The old Normal and Hard, in one.",
    Difficulty.HARD: "Strong, but slow to think and short of workers.",
    Difficulty.MASTER: "Marches at five, towers up at home, or raises a tower by your mine.",
    Difficulty.GRANDMASTER: "Bred by a genetic search: an opening and an army of its race's own.",
}


class Brain:
    def __init__(self, player: int, difficulty: Difficulty = Difficulty.MEDIUM) -> None:
        self.player = player
        self.saving = False  # a hall for the next mine comes before more soldiers
        self.difficulty = difficulty
        self.profile = PROFILES[difficulty]
        self.next_think = 0.0
        self.wave = self.profile.first_wave
        self.waves_sent = 0
        self.attacking = False
        self.raiders: list[int] = []
        self.hunt = Hunt()  # the search for rivals it has lost track of
        self.log: list[tuple[float, str]] = []  # (time, what) — the evidence of how it plays
        self._last_defend = 0  # threat size of the last logged "defend with" line
        self._wave_capped = False
        self._last_workforce_target: int | None = None
        self.strikers: set[int] = set()  # our peasants sent at an enemy tower frame
        self._plan_logged = False
        self.creeping: int | None = None  # the lair the army is clearing
        self.creep_size = 0  # how many soldiers set out to clear it
        self.creep_until = 0.0  # when it gives that camp up whatever it has left
        self.camp_retry: dict[int, float] = {}  # lair id -> when that camp is worth trying again
        self.commander = Commander()  # the race's own unit: when to buy it and what it is for

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    def think(self, world: World, rng: random.Random) -> None:
        """Act if a think is due; call this every simulation step."""
        if world.time < self.next_think or not world.players[self.player].alive or world.winner is not None:
            return
        self.next_think = world.time + self.profile.think_every
        if not self._plan_logged:
            self._plan_logged = True
            self.note(world, f"army plan {world.players[self.player].race.value}")
        if not self._units(world):
            self._recover(world)
            return
        self._economy(world)
        self._strike_towers(world)
        self._repairs(world)
        self._construction(world, rng)
        self._training(world)
        self._research(world)
        self._military(world, rng)

    def _recover(self, world: World) -> None:
        """With no units left, spend refundable work on a recruit before resuming the normal plan."""
        buildings = world.player_buildings(self.player)
        if any(b.done and b.queue for b in buildings):
            return
        recruit = world.recovery_recruit(self.player)
        if recruit is None:
            return  # the next simulation step resolves surrender
        building, unit_type = recruit
        if world.can_train(building, unit_type) is not None:
            for b in buildings:
                if not b.done:
                    world.cancel_building(b.id)
                elif b.research is not None:
                    world.cancel_research(b.id)
        world.train(building.id, unit_type)
        self.note(world, f"recover with {unit_type.value}")

    # -- Helpers -----------------------------------------------------------------

    def _units(self, world: World) -> list[Unit]:
        return world.player_units(self.player)

    def _peasants(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if u.is_worker]

    def _army(self, world: World) -> list[Unit]:
        return fighters(self._units(world))

    def _hall(self, world: World) -> Building | None:
        halls = world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)
        return halls[0] if halls else None

    @staticmethod
    def _job(unit: Unit) -> Resource | None:
        """What a peasant is gathering, if anything."""
        if unit.inside is not None or unit.carrying is Resource.GOLD:
            return Resource.GOLD
        if unit.carrying is Resource.LUMBER:
            return Resource.LUMBER
        for order in unit.orders:
            if isinstance(order, Harvest):
                return Resource.GOLD if isinstance(order.target, int) else Resource.LUMBER
            if isinstance(order, Deposit):
                continue
        return None

    # -- Economy -----------------------------------------------------------------

    def _economy(self, world: World) -> None:
        world.assign_workers(self.player)

    def _repairs(self, world: World) -> None:
        """One peasant mends the most damaged building, once no enemy is near it."""
        if not self.profile.repair or any(isinstance(p.order, Repair) for p in self._peasants(world)):
            return
        damaged = [b for b in world.player_buildings(self.player, done=True) if b.hp < b.max_hp * 0.7 and b.info.mine is None]
        if not damaged:
            return
        b = min(damaged, key=lambda b: b.hp / b.max_hp)
        if world._nearest_enemy(self.player, b.center, 8.0, air=False) is not None:  # a flyer overhead does not stop the hammer
            return
        spare = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, Build)]
        if not spare:
            return
        peasant = min(spare, key=lambda p: dist(p.pos, b.center))
        world.repair([peasant.id], b.id)
        self.log.append((world.time, f"repair {b.type.value} at {b.hp}/{b.max_hp}"))

    def _strike_towers(self, world: World) -> None:
        """The tower rush's basic answer: peasants pull down an enemy tower frame whose fire would reach a hall
        of ours or the mine beside it. A frame wears no armour; once the tower stands, they go back to work."""
        home = [h.rect for h in world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)]
        home += [m.rect for m in known_mines(world, self.player)
                 if any(rect_gap((m.x + m.size / 2, m.y + m.size / 2), rect) <= EXPAND_DISTANCE for rect in home)]
        frames: list[Building] = []
        for record in known_enemy_buildings(world, self.player):
            tower = world.buildings.get(record.id)
            if tower is None or tower.type is not BuildingType.TOWER or tower.done or not world.any_visible(self.player, tower.rect):
                continue
            if any(rect_gap(tower.center, rect) <= tower.info.range + tower.size / 2 for rect in home):
                frames.append(tower)
        striking: set[int] = set()
        standing: list[int] = []
        for i in sorted(self.strikers):
            order = world.units[i].order if i in world.units else None
            if isinstance(order, Attack):
                target = world.buildings.get(order.target)
                if target is not None and target.done:
                    standing.append(i)
                else:
                    striking.add(i)
        if standing:
            world.release_workers(standing)
        self.strikers = striking
        for tower in frames:
            spare = [p for p in self._peasants(world) if p.id not in self.strikers and p.constructing is None
                     and not isinstance(p.order, (Build, Repair, Salvage))]
            drafted = sorted(spare, key=lambda p: dist(p.pos, tower.center))[:TOWER_STRIKERS - len(self.strikers)]
            if drafted:
                world.attack([p.id for p in drafted], tower.id)
                self.strikers.update(p.id for p in drafted)
                self.note(world, f"strike tower frame {tower.id} with {len(drafted)} peasants")

    # -- Construction -----------------------------------------------------------------

    def _construction(self, world: World, rng: random.Random) -> None:
        if any(not b.done for b in world.player_buildings(self.player)):
            return  # one site at a time; a builder in trouble would otherwise stall the whole plan
        peasants = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, (Repair, Salvage))]
        if not peasants:
            return
        hall = self._hall(world)
        plan = self._next_building(world, hall, peasants[0].pos)
        if plan is None:
            return
        wanted, anchor = plan
        site = self._site(world, wanted, anchor, rng)
        if site is None:
            return
        builder = min(peasants, key=lambda p: (self._job(p) is Resource.GOLD, dist(p.pos, (site[0], site[1]))))
        world.build(builder.id, wanted, site)
        self.note(world, f"build {wanted.value} at {site}")

    def _next_building(self, world: World, hall: Building | None, fallback: Point) -> tuple[BuildingType, Point] | None:
        """``(what to build, where near)`` or None."""
        player = self.player
        profile = self.profile
        gold = world.players[player].gold
        found = known_mines(world, player)
        anchor_point = hall.center if hall is not None else fallback
        mine = min(found, key=lambda m: dist(m.center, anchor_point)) if found else None
        self.saving = False
        if hall is None:
            wanted, anchor = BuildingType.TOWN_HALL, (mine.center if mine is not None else fallback)
        else:
            used, cap = world.supply(player)
            have = lambda t: len(world.player_buildings(player, t, done=True))  # noqa: E731
            army = len(self._army(world))
            anchor = hall.center
            if used + 2 > cap:
                wanted = BuildingType.FARM
            elif not have(BuildingType.BARRACKS):
                wanted = BuildingType.BARRACKS
            elif (claim := self._mine_to_claim(world, hall, mine)) is not None:
                wanted, anchor = BuildingType.TOWN_HALL, claim.center
                self.saving = world.can_afford(player, BUILDINGS[wanted].cost) is not None  # the army waits for the hall
            elif profile.tech and not have(BuildingType.LUMBER_MILL):
                wanted = BuildingType.LUMBER_MILL
            elif (own := self._own_building(world)) is not None:
                wanted = own  # its race's own unit is the answer (WB-068): what trains it, or what that needs
            elif profile.tech and not have(BuildingType.BLACKSMITH) and gold > 900:
                wanted = BuildingType.BLACKSMITH
            elif profile.tech and not have(BuildingType.STABLES) and gold > 1200:
                wanted = BuildingType.STABLES
            elif have(BuildingType.BARRACKS) < profile.barracks and gold > 1500:
                wanted = BuildingType.BARRACKS
            elif profile.siege and have(BuildingType.BLACKSMITH) and not have(BuildingType.WORKSHOP) and gold > 1400:
                wanted = BuildingType.WORKSHOP
            elif profile.clerics and not have(BuildingType.CHURCH) and gold > 1400:
                wanted = BuildingType.CHURCH
            elif army >= 6 and have(BuildingType.TOWER) < profile.towers and gold > 1200:
                wanted = BuildingType.TOWER
            else:
                return None
        if world.can_afford(player, BUILDINGS[wanted].cost) is not None:
            return None
        return wanted, anchor

    def _own_building(self, world: World) -> BuildingType | None:
        """The building the race's own unit is trained at, or the one that building needs, when the unit is the answer
        and none stands or goes up."""
        own = self.commander.building(world, self.player, self._seen_now(world)) if self.profile.unique else None
        if own is None:
            return None
        needs = BUILDINGS[own].requires
        return own if needs is None or world.player_buildings(self.player, needs, done=True) else needs

    def _mine_to_claim(self, world: World, hall: Building, worked: KnownMine | None) -> KnownMine | None:
        """The nearest unclaimed mine when the one the hall works is far, running low or gone, up to
        MAX_HALLS halls in all and one at a time."""
        player = self.player
        halls = world.player_buildings(player, BuildingType.TOWN_HALL)
        if len(halls) >= MAX_HALLS or any(not h.done for h in halls):
            return None
        if worked is not None and worth_a_hall(worked) and dist(worked.center, hall.center) <= EXPAND_DISTANCE:
            return None
        free = [m for m in known_mines(world, self.player) if worth_a_hall(m)
                and not any(dist(m.center, h.center) <= CLAIM_DISTANCE for h in halls)
                and not guarded(world, self.player, m.center)]
        return min(free, key=lambda m: hall_first(m, dist(m.center, hall.center))) if free else None

    def _site(self, world: World, building_type: BuildingType, anchor: Point, rng: random.Random) -> Pos | None:
        return site_search(world, building_type, self.player, anchor, rng, BUILD_MIN_DISTANCE, BUILD_MAX_DISTANCE)

    # -- Training ------------------------------------------------------------------

    def _workforce_target(self, world: World) -> int:
        """Peasants wanted: the profile plus five per extra hall, capped by supply
        left after reserving the next wave, never below the profile."""
        halls = len(world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True))
        base = self.profile.peasants + 5 * max(0, halls - 1)
        _used, cap = world.supply(self.player)
        return max(self.profile.peasants, min(base, cap - self.wave))

    def _training(self, world: World) -> None:
        player = self.player
        halls = world.player_buildings(player, BuildingType.TOWN_HALL, done=True)
        target = self._workforce_target(world)
        if target != self._last_workforce_target:
            self.note(world, f"workforce target {target}")
            self._last_workforce_target = target
        peasants = len(self._peasants(world))
        waits = self.commander.waits_for(world, player, self._seen_now(world)) if self.profile.unique else ()
        free = self.commander.kept_free(world, player, waits) if waits and all(
            world.can_afford(player, UPGRADES[u].cost) is None for u in waits) else set()
        for hall in halls:
            if peasants >= target:
                break
            if hall.id in free:
                continue  # its own unit is the answer: the hall is to be raised to the Keep first
            if not hall.queue and world.can_train(hall, UnitType.PEASANT) is None:
                world.train(hall.id, UnitType.PEASANT)
        first = halls[0] if halls else None
        army = self._army(world)
        counts = {t: int_sum(1 for u in army if u.type is t) for t in PLAYABLE_UNITS}
        for building in world.player_buildings(player, done=True):
            if not building.info.trains or building.type is BuildingType.TOWN_HALL or self.saving:
                continue
            if building.rally is None and first is not None:
                world.set_rally(building.id, self._muster_point(world, first))
            if building.queue or building.research is not None:
                continue
            choice = self.commander.wish(world, player, building, self._seen_now(world)) if self.profile.unique else None
            choice = choice or self._choose_unit(world, building, counts)
            if choice is not None and world.can_train(building, choice) is None:
                world.train(building.id, choice)
                counts[choice] = counts.get(choice, 0) + 1
                self.note(world, f"train {choice.value}")

    def _army_targets(self, world: World) -> dict[UnitType, float]:
        """Target army shares for the brain's race, renormalised to what the
        difficulty profile uses and shifted towards counters of the visible
        enemy soldiers: raiders and shock against archer masses, line and
        ranged against knights."""
        plan = dict(ARMY_PLANS[world.players[self.player].race])
        if not self.profile.tech:
            plan.pop(UnitType.KNIGHT, None)
        if not self.profile.siege:
            plan.pop(UnitType.CATAPULT, None)
        if not self.profile.clerics:
            plan.pop(UnitType.CLERIC, None)
        total = plain_sum(plan.values())
        if total > 0:
            plan = {unit_type: share / total for unit_type, share in plan.items()}
        archers = melee = knights = 0
        for unit in world.units.values():
            if unit.player == self.player or unit.is_worker or unit.hidden or unit.hp <= 0:
                continue
            if not world.is_visible(self.player, unit.tile):
                continue
            if unit.type is UnitType.ARCHER:
                archers += 1
            if unit.type in _MELEE_TYPES:
                melee += 1
            if unit.type is UnitType.KNIGHT:
                knights += 1
        if archers > 0 and archers >= 2 * melee:
            _shift(plan, {UnitType.FOOTMAN: -0.15, UnitType.KNIGHT: 0.15})
        if knights >= 3:
            _shift(plan, {UnitType.KNIGHT: -0.15, UnitType.FOOTMAN: 0.075, UnitType.ARCHER: 0.075})
        return plan

    def _choose_unit(self, world: World, building: Building, counts: dict[UnitType, int]) -> UnitType | None:
        soldiers = int_sum(counts.values())
        if building.type is BuildingType.WORKSHOP:
            threshold = 4 if world.players[self.player].race is Race.DWARF else 6
            if soldiers < threshold:
                return None
        targets = self._army_targets(world)
        best: UnitType | None = None
        best_gap = -math.inf
        for unit_type in targets:
            if unit_type not in building.info.trains:
                continue
            if world.can_train(building, unit_type) is None:
                share = counts.get(unit_type, 0) / soldiers if soldiers else 0.0
                if targets[unit_type] - share > best_gap:
                    best, best_gap = unit_type, targets[unit_type] - share
        return best

    def _seen_now(self, world: World) -> dict[UnitType, float]:
        """How many of each kind the rivals have in sight now: all Medium knows of what they field."""
        seen: dict[UnitType, float] = {}
        for unit in world.units.values():
            if (unit.player != self.player and unit.player < world.seats and not unit.is_worker and not unit.hidden and unit.hp > 0
                    and world.is_visible(self.player, unit.tile)):
                seen[unit.type] = seen.get(unit.type, 0.0) + 1.0
        return seen

    def _research(self, world: World) -> None:
        if not self.profile.tech:
            return
        player = world.players[self.player]
        if player.gold < self.profile.reserve or self.saving:
            return
        buildings = world.player_buildings(self.player, done=True)  # nothing changes until the one order below
        first = self.commander.waits_for(world, self.player, self._seen_now(world)) if self.profile.unique else ()
        for wanted in (*first, *RESEARCH_ORDER):
            if wanted in player.upgrades or not RACES[player.race].upgrade_allowed(wanted):
                continue
            for upgrade in with_prerequisites(player.upgrades, wanted):
                for building in buildings:
                    if upgrade in building.info.researches and world.can_research(building, upgrade) is None:
                        world.research(building.id, upgrade)
                        self.note(world, f"research {upgrade.value}")
                        return

    def _muster_point(self, world: World, hall: Building) -> Point:
        """Between the hall and the map centre: the side the enemy comes from."""
        cx, cy = world.width / 2, world.height / 2
        hx, hy = hall.center
        d = dist((hx, hy), (cx, cy)) or 1.0
        return (hx + (cx - hx) / d * 6, hy + (cy - hy) / d * 6)

    def _required_wave(self, world: World) -> int:
        """The army the brain waits for: the wave, bounded by what farms and halls can feed."""
        if self.waves_sent == 0:
            return self.profile.first_wave
        _used, cap = world.supply(self.player)
        bound = cap - len(self._peasants(world)) - 2
        floor = self.profile.first_wave // 2
        required = min(self.wave, bound)
        if required < floor:
            required = floor
        elif bound < self.wave and not self._wave_capped:
            self._wave_capped = True
            self.note(world, f"wave capped at {required}")
        return required

    def _enemy_soldiers(self, world: World) -> int:
        """Living enemy soldiers (units that are not workers) of alive players."""
        return int_sum(1 for u in world.units.values() if u.player != self.player and world.players[u.player].alive
                       and not u.is_worker and u.info.damage and u.hp > 0 and not u.hidden
                       and world.is_visible(self.player, u.tile))

    # -- Military --------------------------------------------------------------------

    def _creep(self, world: World, army: list[Unit]) -> bool:
        """Clear a creature camp.  True when the army has been given the job.

        The whole army goes at once and stays until the lair is down: a camp that mends its wounded and
        calls its dead back out of the den is a bottomless sink for soldiers fed into it a few at a time,
        which is the one failure mode worth writing a rule against.  An army worn down past half of what
        it set out with gives the camp up and does not come back to that one for a while.
        """
        lair = world.buildings.get(self.creeping) if self.creeping is not None else None
        if self.creeping is not None and lair is None:
            self.note(world, "camp cleared")
            self.creeping = None
        if lair is not None:
            if len(army) < max(2, self.creep_size // 2) or world.time >= self.creep_until:
                self.camp_retry[lair.id] = world.time + CREEP_RETRY
                self.creeping = None
                self.note(world, f"break off the camp with {len(army)} left")
                hall = self._hall(world)
                if hall is not None:
                    world.move([u.id for u in army], self._muster_point(world, hall))
                return True
            idle = [u.id for u in army if not u.orders]
            if idle:
                world.attack_move(idle, self._beside(world, lair.rect, lair.center))
            return True
        if len(army) < self._required_wave(world):
            return False
        here = [record for record in known_camps(world, self.player)
                if record.id in world.buildings and world.time >= self.camp_retry.get(record.id, 0.0)]
        if not here:
            return False
        hall = self._hall(world)
        origin = hall.center if hall is not None else army[0].pos
        worth = {record.id: camp_worth(world, self.player, record) for record in here}
        target = min(here, key=lambda record: dist(record.center, origin) / worth[record.id])  # the nearest for what it keeps
        if dist(target.center, origin) > CREEP_REACH * worth[target.id]:
            return False
        self.creeping = target.id
        self.creep_size = len(army)
        self.creep_until = world.time + CREEP_PATIENCE
        world.attack_move([u.id for u in army], self._beside(world, target.rect, target.center))
        self.note(world, f"clear the camp with {len(army)}")
        return True

    @staticmethod
    def _beside(world: World, rect: tuple[int, int, int, int], center: Point) -> Point:
        """Somewhere a soldier can stand next to a footprint.  A building's centre is inside its own
        blocked ground: a unit sent there paths towards it and stops a tile short for good, which fuzz
        reports as a stalled unit."""
        tile = world.free_tile_near(rect, prefer=center)
        return tile_center(tile) if tile is not None else center

    def _military(self, world: World, rng: random.Random) -> None:
        army = self._army(world)
        answer_flyers(world, self.player, army, DEFEND_RADIUS)
        if self.profile.harass:
            self._raid(world)
            army = [u for u in army if u.id not in self.raiders]
        hunting = self.hunt.step(world, self.player, army, lost_track(world, self.player, self._far_guess(world)))
        hunting |= self.commander.step(world, self.player, [u for u in self._units(world) if u.id not in hunting],
                                       self._push(world, army) if self.attacking else None)
        army = [u for u in army if u.id not in hunting]
        threats = self._threats(world)
        if self.profile.creep and not threats and self._creep(world, army):
            return
        if threats:
            threat = self._threat_point(world, threats)
            size = len(threats)
            if 2 * size >= len(army):
                self.attacking = False
                for unit in army:
                    if not isinstance(unit.order, Attack) and not heading_to(unit, threat):
                        world.attack_move([unit.id], threat)
                if size != self._last_defend:
                    self.note(world, f"defend with {len(army)} against {size}")
                    self._last_defend = size
                return
            want = min(len(army), max(2, math.ceil(1.5 * size)))
            engaged_ids = {u.id for u in army if self._aimed_at(world, u, threat)}
            responders = len(engaged_ids)
            if responders < want:
                rest = [u for u in army if u.id not in engaged_ids]
                rest.sort(key=lambda u: dist(u.pos, threat))
                for unit in rest[: want - responders]:
                    world.attack_move([unit.id], threat)
                    responders += 1
            if size != self._last_defend:
                self.note(world, f"defend with {responders} against {size}")
                self._last_defend = size
            return
        self._last_defend = 0
        targets = self._enemy_targets(world)
        if not targets:
            return
        required = self._required_wave(world)
        if self.attacking:
            if len(army) < 3:
                self.attacking = False
                hall = self._hall(world)
                if hall is not None:
                    world.move([u.id for u in army], self._muster_point(world, hall))
                return
            idle = [u for u in army if not u.orders]
            if idle:
                target = min(targets, key=lambda t: dist(t, idle[0].pos))
                world.attack_move([u.id for u in idle], target)
            return
        if world.time < self.profile.first_attack:
            return
        if len(army) >= 3 and self._enemy_soldiers(world) < 3 and (
            self.profile.harass or (self.profile.tech and self.waves_sent > 0)
        ):
            self.attacking = True
            self.waves_sent += 1
            hall = self._hall(world)
            origin = hall.center if hall is not None else army[0].pos
            target = min(targets, key=lambda t: dist(t, origin))
            world.attack_move([u.id for u in army], target)
            self.note(world, f"attack with {len(army)} towards {tuple(round(c) for c in target)}")
            return
        if len(army) >= required:
            self.attacking = True
            self.waves_sent += 1
            self.wave += self.profile.wave_growth
            hall = self._hall(world)
            origin = hall.center if hall is not None else army[0].pos
            target = min(targets, key=lambda t: dist(t, origin))
            world.attack_move([u.id for u in army], target)
            self.note(world, f"attack with {len(army)} towards {tuple(round(c) for c in target)}")

    def _push(self, world: World, army: list[Unit]) -> Point | None:
        """Where an attack goes: the enemy target nearest the hall, as a wave is sent at."""
        targets = self._enemy_targets(world)
        hall = self._hall(world)
        if not targets or (hall is None and not army):
            return None
        home = hall.center if hall is not None else army[0].pos
        return min(targets, key=lambda t: dist(t, home))

    def _raid(self, world: World) -> None:
        """The first two knights go for the enemy's peasants and keep at it."""
        self.raiders = [i for i in self.raiders if i in world.units]
        riders = [u for u in self._army(world) if u.type in RAIDERS and u.id not in self.raiders]
        while len(self.raiders) < 2 and riders:
            self.raiders.append(riders.pop().id)
        idle = [i for i in self.raiders if not world.units[i].orders]
        if not idle:
            return
        seen = [u for u in world.units.values()
                if u.player != self.player and u.is_worker and not u.hidden and world.is_visible(self.player, u.tile)]
        mines = [m.center for m in known_mines(world, self.player)
                 if any(dist(u.pos, m.center) < 8 for u in seen)]
        prey = mines or [u.pos for u in seen]
        if prey:
            target = min(prey, key=lambda p: dist(p, world.units[idle[0]].pos))
            world.attack_move(idle, target)
            self.note(world, f"raid towards {tuple(round(c) for c in target)}")

    def _enemy_targets(self, world: World) -> list[Point]:
        """Enemy buildings of alive players; once those are gone, whatever enemy units remain."""
        buildings = [record.center for record in known_enemy_buildings(world, self.player)]
        if buildings:
            return buildings
        seen = [u.pos for u in world.units.values()
                if u.player != self.player and world.players[u.player].alive
                and not u.hidden and world.is_visible(self.player, u.tile)]
        if seen:
            return seen
        # Nothing of theirs found yet: walk at the far corner rather than stand
        # at home until the clock runs out. Starts sit in the corners.
        return [self._far_guess(world)]

    def _far_guess(self, world: World) -> Point:
        """Where the rival started, guessed from the map's shape: the start furthest from our hall."""
        hall = self._hall(world)
        here = hall.center if hall is not None else (world.width / 2, world.height / 2)
        return max(mapgen.start_guesses(world.width, world.height, world.seats), key=lambda c: dist(c, here))

    def _threats(self, world: World) -> list[Unit]:
        """Visible enemies within DEFEND_RADIUS of one of our buildings.

        A creature is never one: a camp is leashed to its lair and comes at nobody who has not walked
        into it, so answering one as a raid would march the army out at ground it was never losing.
        Clearing a camp is :meth:`_creep`'s decision, taken once and carried through.
        """
        own = world.player_buildings(self.player)
        out: list[Unit] = []
        for unit in world.units.values():
            if unit.player == self.player or unit.hidden or not world.is_visible(self.player, unit.tile):
                continue
            if world.players[unit.player].neutral or not unit.info.damage:  # an unarmed flyer looking on is no raid
                continue
            for b in own:
                if dist(unit.pos, b.center) < DEFEND_RADIUS:
                    out.append(unit)
                    break
        return out

    def _threat_point(self, world: World, threats: list[Unit]) -> Point:
        """Where to answer: the position of the threat nearest to one of our buildings."""
        buildings = world.player_buildings(self.player)
        return min(threats, key=lambda u: min(dist(u.pos, b.center) for b in buildings)).pos

    @staticmethod
    def _aimed_at(world: World, unit: Unit, point: Point) -> bool:
        """Whether the soldier's current order already answers the threat point."""
        order = unit.order
        if isinstance(order, AttackMove):
            return dist(order.target, point) <= DEFEND_RADIUS
        if isinstance(order, Attack):
            target = world.units.get(order.target)
            pos = target.pos if target is not None else None
            if pos is None:
                building = world.buildings.get(order.target)
                pos = building.center if building is not None else None
            return pos is not None and dist(pos, point) <= DEFEND_RADIUS
        return False

    def _threat(self, world: World) -> Point | None:
        """The nearest visible enemy close to one of our buildings."""
        threats = self._threats(world)
        if not threats:
            return None
        return self._threat_point(world, threats)
