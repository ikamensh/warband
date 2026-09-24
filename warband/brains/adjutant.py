"""The adjutant: six commands a player gives the whole side with a key (WB-061, ``docs/controls.md``).

**Fortify**, **Withdraw**, **Scout**, **Harass**, **Gold** and **Lumber**.  Pressing one again within
:data:`LEVEL_WINDOW` seconds raises its level, up to three, and each press acts at once for its step of
:data:`LEVELS`: a level asks for so many in all, so the second press adds what the first left short of it, not as
many again.  Scout, Harass and Withdraw *stand*: the units handed to them are the adjutant's to steer, as a brain
steers its own, until they come home, die, or their player orders them by hand (the scene says so:
:meth:`Adjutant.release`).  Fortify, Gold and Lumber give their orders and are done.

It knows what the seat knows and nothing else: the side's own units and buildings, the rivals it sees now
(``World.is_visible``), the buildings, mines and trees it remembers (``World.worker_knowledge``) and when it last
saw each square of the map (:class:`warband.brains.ai.Squares`, the hunt's memory).  Online the world it reads is
the seat's snapshot, which holds no more than that; offline it asks the same questions of the whole world, as the
brains do.  Every order goes through the callable the scene hands it (``GameScene.attempt`` behind the scene's
allowance), so each is a recorded World order: replays and the online authority need nothing new, and a refusal is
the status line's.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from warband.brains.ai import CLAIM_DISTANCE, EXPAND_DISTANCE, HUNT_DUE, Squares, guarded, known_enemy_buildings, known_mines, site_search
from warband.sim.model import Attack, Build, Building, Harvest, Move, Point, Pos, Repair, Salvage, Unit, World, dist
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, BuildingType, Resource, Terrain, an

COMMANDS: Final = ("fortify", "withdraw", "scout", "harass", "gold", "lumber")
NAMES: Final = {"fortify": "Fortify", "withdraw": "Withdraw", "scout": "Scout", "harass": "Harass", "gold": "Gold",
                "lumber": "Lumber"}
#: What a unit working for a standing command wears above its head.
TAGS: Final = {"scout": "scouting", "harass": "harassing", "withdraw": "withdrawing"}
LEVEL_WINDOW: Final = 1.5  # seconds within which the same command pressed again is its next level
MAX_LEVEL: Final = 3
THINK_EVERY: Final = 0.5  # seconds of match between two looks at the standing commands
#: Seconds after the adjutant ordered a unit before it takes the unit's having no order as having stopped: online, the
#: order shows in the seat's snapshot only once the server has it.
ORDER_GRACE: Final = 1.0


@dataclass(frozen=True)
class Level:
    """One press's step of a command: how many of its *pool* it wants in all, a *count* or a *share* of the pool
    rounded up, and another command's level (*then*) carried out beside it."""

    pool: str
    count: int | None = None
    share: float = 0.0
    then: tuple[str, int] | None = None

    def wanted(self, pool: int) -> int:
        return self.count if self.count is not None else math.ceil(self.share * pool)


#: The commands' levels (``BACKLOG.md`` WB-061), and the pool each level is a share of:
#: *soldiers* every unit but the workers, flyers first; *fighters* the armed ones, fastest first; *wounded* the soldiers
#: below half their health; *outside* the soldiers away from the base, most exposed first; *towers* the towers this
#: press and the ones before it planned; *gold* and *lumber* the workers on that resource (the idle go at every press).
LEVELS: Final[dict[str, tuple[Level, Level, Level]]] = {
    "scout": (Level("soldiers", count=1), Level("soldiers", share=0.25), Level("soldiers", share=0.5)),
    "harass": (Level("fighters", count=3), Level("fighters", share=0.25), Level("fighters", share=0.5)),
    "withdraw": (Level("wounded", share=1.0), Level("outside", share=0.5), Level("soldiers", share=1.0)),
    "fortify": (Level("towers", count=1), Level("towers", count=3), Level("towers", count=6, then=("withdraw", 1))),
    "gold": (Level("lumber", share=0.25), Level("lumber", share=0.5), Level("lumber", share=1.0)),
    "lumber": (Level("gold", share=0.25), Level("gold", share=0.5), Level("gold", share=1.0)),
}

SCOUT_BASE_DUE: Final = 20.0  # seconds after which a square holding a rival building the side knows is due another look
TOWER_BERTH: Final = 1.0  # tiles a scout's look-out keeps beyond what a known tower's fire reaches
RAID_BERTH: Final = 2.0  # tiles from a known tower's reach at which raiders count it in sight and ride home
HARASS_WARY: Final = 8.0  # tiles from a raider within which a rival soldier in sight sends the party home
HARASS_REACH: Final = 9.0  # tiles from the party within which a rival worker in sight is struck
HARASS_LINGER: Final = 10.0  # seconds the party waits where it raids for workers to come out of their mine
ARRIVED: Final = 3.0  # tiles from its goal a party counts as there
HOME: Final = 3.0  # tiles beyond a hall's edge, or from its door, a soldier counts as home
BASE_RADIUS: Final = 10.0  # tiles from every building of the side's a soldier counts as outside the base
EXPOSED: Final = 8.0  # tiles within which a rival soldier in sight makes one of ours exposed
FORTIFY_TURN: Final = math.radians(40)  # between two approaches, spread from the one facing the nearest rival
#: The approaches in the order they are fortified: (turns of FORTIFY_TURN from the one facing the rival, tiles from the
#: hall).  The near ring is as far out as the brains' front point; the far one backs the three facing the rival.
APPROACHES: Final = ((0, 6.0), (1, 6.0), (-1, 6.0), (2, 6.0), (-2, 6.0), (0, 10.0), (1, 10.0), (-1, 10.0), (3, 6.0), (-3, 6.0),
                     (2, 10.0), (-2, 10.0))
FORTIFY_SPREAD: Final = 3.5  # tiles within which a tower of the side's already guards an approach
FORTIFY_SEARCH: Final = 3  # tiles round an approach a tower's site may be
LANE_CLEARANCE: Final = 1  # tiles either side of the walk from a hall to its mine no tower may take
TREE_CHOPPERS: Final = 2  # workers sent to one tree


@dataclass
class Report:
    """What a press did, as the status line says it; *refused* when it could do nothing, and why.  Nothing *said* of a
    refusal: the rules refused its orders, and their reason is on the status line already."""

    said: str
    refused: bool = False


@dataclass
class Raid:
    """Where the harassing party is bound, when it began to wait there, and the places it has raided."""

    target: Point | None = None
    waiting_since: float | None = None
    raided: list[Point] = field(default_factory=list)


#: Gives a World order: True once given, False when the rules refused it (the status line says why), None when it may
#: not be given yet (a match played elsewhere keeps to its server's rate: the allowance comes back in a moment).
Give = Callable[..., "bool | None"]


def rivals_in_sight(world: World, player: int) -> list[Unit]:
    """The units of the other seats *player* sees now: out of mines and sites, under its own sight.  Creatures are
    nobody's rivals."""
    return [u for u in world.units.values() if u.player != player and not world.players[u.player].neutral and not u.hidden
            and world.is_visible(player, u.tile)]


def known_towers(world: World, player: int) -> list:
    """The armed buildings of the other seats *player* remembers, with how far their fire reaches (``threat_range``)."""
    return [b for b in world.worker_knowledge[player].threats
            if b.player is not None and b.player != player and not world.players[b.player].neutral]


def under_fire(point: Point, towers: Sequence, berth: float = 0.0) -> bool:
    return any(dist(point, t.center) < t.threat_range + berth for t in towers)


def crosses_fire(a: Point, b: Point, towers: Sequence) -> bool:
    """Whether the straight line from *a* to *b* passes within reach of one of *towers*."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length = dx * dx + dy * dy
    for tower in towers:
        cx, cy = tower.center
        t = 0.0 if length == 0 else max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / length))
        if dist((ax + t * dx, ay + t * dy), (cx, cy)) < tower.threat_range:
            return True
    return False


def out_of_fire(world: World, point: Point, towers: Sequence) -> Point:
    """*point*, pushed straight out of every known tower's reach it lies in (a look-out at the edge of its fire)."""
    x, y = point
    for tower in towers:
        cx, cy = tower.center
        reach = tower.threat_range + TOWER_BERTH
        away = dist((x, y), (cx, cy))
        if away < reach:
            ux, uy = ((x - cx) / away, (y - cy) / away) if away > 0 else (1.0, 0.0)
            x, y = cx + ux * reach, cy + uy * reach
    return (min(max(x, 0.5), world.width - 0.5), min(max(y, 0.5), world.height - 0.5))


def gathering(worker: Unit) -> Resource | None:
    """What *worker* is harvesting, by its harvest order, while it has no building work in hand."""
    if worker.constructing is not None or any(isinstance(order, (Build, Repair, Salvage)) for order in worker.orders):
        return None
    harvest = next((order for order in worker.orders if isinstance(order, Harvest)), None)
    if harvest is None:
        return None
    return Resource.GOLD if isinstance(harvest.target, int) else Resource.LUMBER


def centroid(units: Sequence[Unit]) -> Point:
    return (sum(u.x for u in units) / len(units), sum(u.y for u in units) / len(units))


class Adjutant:
    """The player's side-wide commands, for seat *player*: :meth:`press` for a key, :meth:`think` every frame,
    :meth:`release` for the units the player ordered by hand.  *give* gives a World order and says whether it was
    given; *rng* breaks ties between a tower's sites."""

    def __init__(self, player: int, give: Give, rng: random.Random) -> None:
        self.player = player
        self.give = give
        self.rng = rng
        self.party: dict[int, str] = {}  # a unit's id -> the standing command it works for
        self.presses: dict[str, tuple[int, float]] = {}  # a command -> its level and when it was last pressed (the scene's clock)
        self.squares = Squares()  # when the side last saw each square: what the scouts look at
        self.bound: dict[int, tuple[int, float, Point]] = {}  # a scout -> the square it is bound for, since when, and where it looks from
        self.homes: dict[int, tuple[Point, bool]] = {}  # a withdrawing unit -> the door of the hall it walks to, and whether it was sent
        self.raid = Raid()
        self.planned = 0  # towers this press of Fortify and those before it within its window planned
        self.moved: dict[Resource, set[int]] = {Resource.GOLD: set(), Resource.LUMBER: set()}  # workers Gold / Lumber took from the other
        self.ordered: dict[int, float] = {}  # a unit -> when the adjutant last gave it an order (the match's time)
        self.next_think = 0.0
        self._acts: dict[str, Callable[[World, Level], Report]] = {
            "scout": self._scout, "harass": self._harass, "withdraw": self._withdraw, "fortify": self._fortify,
            "gold": lambda world, level: self._gather(world, level, Resource.GOLD),
            "lumber": lambda world, level: self._gather(world, level, Resource.LUMBER),
        }

    # -- What the scene asks ----------------------------------------------------------------------------------------

    def level(self, command: str, now: float) -> int:
        """The level *command* stands at while its window is open (pips on its button); 0 once it has closed."""
        level, at = self.presses.get(command, (0, -math.inf))
        return level if now - at <= LEVEL_WINDOW else 0

    def members(self, command: str) -> list[int]:
        """The units working for a standing *command*, in the order they joined."""
        return [uid for uid, working in self.party.items() if working == command]

    @property
    def tags(self) -> dict[int, str]:
        """What each unit working for a command wears above its head."""
        return {uid: TAGS[command] for uid, command in self.party.items()}

    def release(self, unit_ids: Sequence[int]) -> None:
        """Its player has these units in hand now: they leave whatever command they worked for."""
        for uid in unit_ids:
            self._leave(uid)
            for moved in self.moved.values():
                moved.discard(uid)

    # -- A press ----------------------------------------------------------------------------------------------------

    def press(self, world: World, command: str, now: float) -> Report:
        """*command*'s key or button at the scene's clock *now*: its next level if pressed within :data:`LEVEL_WINDOW`
        of the last press, else its first, carried out at once.  A press counts even when its level finds nothing to do:
        with nobody wounded, Withdraw pressed twice is still half the soldiers outside."""
        level, at = self.presses.get(command, (0, -math.inf))
        level = min(MAX_LEVEL, level + 1) if now - at <= LEVEL_WINDOW else 1
        if level == 1:  # a fresh start for what counts only within one run of presses
            if command == "fortify":
                self.planned = 0
            elif command in ("gold", "lumber"):
                self.moved[Resource(command)].clear()
        self.squares.look(world, self.player)
        self._prune(world)
        step = LEVELS[command][level - 1]
        report = self._acts[command](world, step)
        if step.then is not None and not report.refused:
            other, other_level = step.then
            also = self._acts[other](world, LEVELS[other][other_level - 1])
            if not also.refused:
                report.said += f" · {also.said}"
        self.presses[command] = (level, now)
        if level > 1 and report.said:
            report.said += f" (level {level})"
        return report

    # -- Every frame ------------------------------------------------------------------------------------------------

    def think(self, world: World) -> list[str]:
        """Keep the standing commands going, every :data:`THINK_EVERY` seconds of the match; what the status line
        should say of it."""
        self.squares.look(world, self.player)
        if world.time < self.next_think or world.winner is not None or not world.players[self.player].alive:
            return []
        self.next_think = world.time + THINK_EVERY
        self._prune(world)
        news: list[str] = []
        self._keep_scouting(world)
        self._keep_harassing(world, news)
        self._keep_withdrawing(world)
        return news

    def _prune(self, world: World) -> None:
        for uid in [uid for uid in self.party if uid not in world.units]:
            self._leave(uid)

    def _leave(self, uid: int) -> None:
        self.party.pop(uid, None)
        self.bound.pop(uid, None)
        self.homes.pop(uid, None)
        self.ordered.pop(uid, None)

    def _order(self, world: World, action: str, unit_ids: list[int], *args) -> bool | None:
        """Give *unit_ids* an order, and note when."""
        given = self.give(action, unit_ids, *args)
        if given:
            for uid in unit_ids:
                self.ordered[uid] = world.time
        return given

    def _settled(self, world: World, unit: Unit) -> bool:
        """Whether the last order the adjutant gave *unit* has had time to show."""
        return world.time - self.ordered.get(unit.id, -math.inf) >= ORDER_GRACE

    def _off_course(self, world: World, unit: Unit, goal: Point) -> bool:
        """Whether *unit* is no longer walking to *goal*, and has had time to show the last order the adjutant gave it:
        it got there, stopped short of it, or took up a fight of its own on the way."""
        order = unit.order
        return not (isinstance(order, Move) and dist(order.target, goal) < 0.5) and self._settled(world, unit)

    # -- The side as its seat knows it ------------------------------------------------------------------------------

    def _soldiers(self, world: World) -> list[Unit]:
        return [u for u in world.player_units(self.player) if not u.is_worker and not u.hidden]

    def _halls(self, world: World) -> list[Building]:
        return world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)

    @staticmethod
    def _hurt(unit: Unit) -> bool:
        return unit.hp * 2 < unit.max_hp

    def _free(self, units: list[Unit]) -> list[Unit]:
        """Those of *units* no command has and fit to be sent out."""
        return [u for u in units if u.id not in self.party and not self._hurt(u)]

    # -- Scout ------------------------------------------------------------------------------------------------------

    def _scout(self, world: World, level: Level) -> Report:
        """Send scouts up to *level*: flyers first, then the fastest soldiers."""
        soldiers = self._soldiers(world)
        scouts = self.members("scout")
        free = sorted(self._free(soldiers), key=lambda u: (not u.flying, -world.speed_of(u), u.id))
        if not scouts and not free:
            return Report("Nobody to scout with: train a soldier or a flying machine", refused=True)
        wanted = free[:max(0, level.wanted(len(soldiers)) - len(scouts))]
        sent = [u for u in wanted if self._send_scout(world, u) is not False]  # one not sent yet goes when it may
        for unit in sent:
            self.party[unit.id] = "scout"
        if not sent:
            return Report("" if wanted else f"{len(scouts)} already scouting", refused=bool(wanted))
        what = an(sent[0].info.name) if len(sent) == 1 else f"{len(sent)} more"
        return Report(f"Scouting: {what}" + (f", {len(scouts) + len(sent)} in all" if scouts else ""))

    def _send_scout(self, world: World, unit: Unit) -> bool | None:
        """Send *unit* to look at the nearest square due a look that no other scout is bound for, from a look-out
        clear of the towers the side knows and on a straight way clear of them too, where there is one."""
        squares = self.squares
        squares.look(world, self.player, now=True)  # what the side sees this moment is no place to send it
        towers = known_towers(world, self.player)
        taken = {square for uid, (square, _since, _at) in self.bound.items() if uid != unit.id}
        every = list(range(len(squares.seen)))
        free = [square for square in every if square not in taken] or every
        clear = [square for square in free
                 if not crosses_fire(unit.pos, out_of_fire(world, squares.middle(world, square), towers), towers)]
        bases = {squares.square_at(record.center): SCOUT_BASE_DUE for record in known_enemy_buildings(world, self.player)}
        square = squares.pick(world, unit.pos, clear or free, HUNT_DUE, bases)
        point = out_of_fire(world, squares.middle(world, square), towers)
        given = self._order(world, "move", [unit.id], point)
        if given:
            self.bound[unit.id] = (square, world.time, point)
        return given

    def _keep_scouting(self, world: World) -> None:
        """A scout hurt below half comes home; one that has come within sight of where it looks from, stopped short of
        it, or has a known tower's fire across its way goes on to the next.  One not sent yet goes first: the
        allowance of a match played elsewhere is spent on it before the others' next legs."""
        squares = self.squares
        towers = known_towers(world, self.player)
        for uid in sorted(self.members("scout"), key=lambda uid: uid in self.bound):
            unit = world.units[uid]
            if self._hurt(unit):
                self._send_home(world, [uid])
                continue
            bound = self.bound.get(uid)
            if bound is not None:
                square, _since, point = bound
                if self._off_course(world, unit, point):
                    squares.seen[square] = max(squares.seen[square], world.time)  # as near as the ground lets it come
                elif not self._settled(world, unit) or dist(unit.pos, point) > unit.info.sight - 1 and not crosses_fire(unit.pos, point, towers):
                    continue
            self._send_scout(world, unit)

    # -- Harass -----------------------------------------------------------------------------------------------------

    def _prey(self, world: World) -> list[Point]:
        """Where the side knows rival workers to be: those it sees, and the mines it remembers beside a rival's
        buildings; none under a known tower's fire, nor raided already by this party."""
        towers = known_towers(world, self.player)
        rivals = known_enemy_buildings(world, self.player)
        places = [u.pos for u in rivals_in_sight(world, self.player) if u.is_worker]
        places += [mine.center for mine in known_mines(world, self.player)
                   if mine.has_gold and any(dist(mine.center, b.center) <= CLAIM_DISTANCE + 2 for b in rivals)]
        return [p for p in places if not under_fire(p, towers, RAID_BERTH + ARRIVED)
                and not any(dist(p, done) < ARRIVED for done in self.raid.raided)]

    def _harass(self, world: World, level: Level) -> Report:
        """Send the fastest soldiers, up to *level*, at the nearest rival workers the side knows of."""
        prey = self._prey(world)
        if not prey:
            return Report("No rival workers known: scout first", refused=True)
        fighters = [u for u in self._soldiers(world) if u.info.damage]
        raiders = self.members("harass")
        free = sorted(self._free(fighters), key=lambda u: (-world.speed_of(u), u.id))
        if not raiders and not free:
            return Report("No soldiers to harass with", refused=True)
        joining = free[:max(0, level.wanted(len(fighters)) - len(raiders))]
        if not joining:
            return Report(f"{len(raiders)} already harassing")
        party = [world.units[uid] for uid in raiders] + joining
        target = self.raid.target
        if target is None:
            target = min(prey, key=lambda p: (dist(p, centroid(party)), p))
        if self._order(world, "move", [u.id for u in joining], target) is False:
            return Report("", refused=True)
        self.raid.target = target  # those not sent yet ride as soon as they may
        for unit in joining:
            self.party[unit.id] = "harass"
        return Report(f"Harassing with {len(party)}: raiders ride for the rival's workers")

    def _keep_harassing(self, world: World, news: list[str]) -> None:
        """Strike workers in reach first; run home the moment rival soldiers or a tower come into sight; wait a while
        where the raid went for workers to come out, then go on to the next place, or home when there is none."""
        raiders = self.members("harass")
        if not raiders:
            self.raid = Raid()
            return
        party = [world.units[uid] for uid in raiders]
        seen = rivals_in_sight(world, self.player)
        towers = known_towers(world, self.player)
        danger = any(dist(e.pos, u.pos) < HARASS_WARY for e in seen if e.info.damage and not e.is_worker for u in party)
        if danger or any(under_fire(u.pos, towers, RAID_BERTH) for u in party):
            self._send_home(world, raiders)
            news.append("Raiders ride home: " + ("rival soldiers in sight" if danger else "a tower in sight"))
            return
        hurt = [u.id for u in party if self._hurt(u)]
        if hurt:
            self._send_home(world, hurt)
            party = [u for u in party if u.id not in hurt]
            if not party:
                return
        middle = centroid(party)
        workers = [e for e in seen if e.is_worker and dist(e.pos, middle) <= HARASS_REACH]
        if workers:
            struck = {e.id for e in workers}
            idle = [u.id for u in party if not (isinstance(u.order, Attack) and u.order.target in struck) and self._settled(world, u)]
            if idle:
                self._order(world, "attack", idle, min(workers, key=lambda e: (dist(e.pos, middle), e.id)).id)
            self.raid.waiting_since = world.time  # workers about: the place is worth staying at
            return
        raid = self.raid
        if raid.target is not None and dist(middle, raid.target) > ARRIVED:
            target = raid.target
            astray = [u.id for u in party if not (isinstance(u.order, Move) and dist(u.order.target, target) < ARRIVED)
                      and self._settled(world, u)]
            if astray:
                self._order(world, "move", astray, target)
            return
        if raid.target is not None and raid.waiting_since is None:
            raid.waiting_since = world.time
        if raid.waiting_since is not None and world.time - raid.waiting_since < HARASS_LINGER:
            return
        if raid.target is not None:
            raid.raided.append(raid.target)
        places = self._prey(world)
        if not places:
            self._send_home(world, [u.id for u in party])
            news.append("The raid is over: the raiders ride home")
            return
        raid.target, raid.waiting_since = min(places, key=lambda p: (dist(p, middle), p)), None
        self._order(world, "move", [u.id for u in party], raid.target)

    # -- Withdraw ---------------------------------------------------------------------------------------------------

    def _withdraw(self, world: World, level: Level) -> Report:
        """Walk soldiers home, up to *level*: the wounded, then the most exposed of those outside the base, then all."""
        halls = self._halls(world)
        if not halls:
            return Report("No hall to withdraw to", refused=True)
        own = world.player_buildings(self.player)
        seen = [e for e in rivals_in_sight(world, self.player) if e.info.damage and not e.is_worker]

        def at_home(u: Unit) -> bool:
            hall = min(halls, key=lambda h: dist(h.center, u.pos))
            return dist(u.pos, hall.center) <= hall.size / 2 + HOME

        away = [u for u in self._soldiers(world) if not at_home(u)]
        pool = {"wounded": [u for u in away if self._hurt(u)],
                "outside": [u for u in away if all(dist(u.pos, b.center) > BASE_RADIUS for b in own)],
                "soldiers": away}[level.pool]
        pool.sort(key=lambda u: (-sum(dist(e.pos, u.pos) < EXPOSED for e in seen),
                                 -min(dist(u.pos, h.center) for h in halls), u.id))
        going = [u for u in pool if self.party.get(u.id) == "withdraw"]
        sending = [u.id for u in pool if self.party.get(u.id) != "withdraw"][:max(0, level.wanted(len(pool)) - len(going))]
        if not pool:
            return Report({"wounded": "Nobody wounded out there", "outside": "Nobody out of the base",
                           "soldiers": "Nobody to withdraw"}[level.pool], refused=True)
        sent = self._send_home(world, sending)
        if not sent:
            return Report("" if sending else f"{len(going)} already withdrawing", refused=bool(sending))
        return Report(f"Withdrawing {len(sent)}" + (" wounded" if level.pool == "wounded" else "") + " to the hall")

    def _send_home(self, world: World, unit_ids: list[int]) -> list[int]:
        """Walk *unit_ids* to their nearest hall (a move, not an attack-move), a group to each; those sent now work for
        Withdraw until they are there.  The ids sent."""
        halls = self._halls(world)
        if not halls or not unit_ids:
            return []
        groups: dict[int, list[int]] = {}
        for uid in unit_ids:
            hall = min(halls, key=lambda h: (dist(h.center, world.units[uid].pos), h.id))
            groups.setdefault(hall.id, []).append(uid)
        sent: list[int] = []
        for hall_id, ids in groups.items():
            hall = world.buildings[hall_id]
            tile = world.free_tile_near(hall.rect, prefer=centroid([world.units[uid] for uid in ids]))
            door = (tile[0] + 0.5, tile[1] + 0.5) if tile is not None else hall.center
            given = self._order(world, "move", ids, door)
            if given is False:
                continue
            for uid in ids:
                self._leave(uid)
                self.party[uid] = "withdraw"
                self.homes[uid] = (door, bool(given))  # one not sent yet goes when it may
            sent += ids
        return sent

    def _keep_withdrawing(self, world: World) -> None:
        """A withdrawing unit at its hall's door, or stopped on the way, is its player's again; one not sent yet is
        sent."""
        late: dict[Point, list[int]] = {}
        for uid in self.members("withdraw"):
            unit, (door, sent) = world.units[uid], self.homes[uid]
            if dist(unit.pos, door) <= HOME or (sent and self._off_course(world, unit, door)):
                self._leave(uid)
            elif not sent:
                late.setdefault(door, []).append(uid)
        for door, ids in late.items():
            given = self._order(world, "move", ids, door)
            for uid in ids:
                if given:
                    self.homes[uid] = (door, True)
                elif given is False:
                    self._leave(uid)

    # -- Fortify ----------------------------------------------------------------------------------------------------

    def _fortify(self, world: World, level: Level) -> Report:
        """Plan towers, up to *level*, at the approaches from the nearest rival the side knows of."""
        race = RACES[world.players[self.player].race]
        needs = BUILDINGS[BuildingType.TOWER].requires
        if needs is not None and not world.player_buildings(self.player, needs, done=True):
            return Report(f"No tower can be built yet: it needs {an(race.buildings[needs].name)}", refused=True)
        if not self._halls(world):
            return Report("No hall to fortify", refused=True)
        wanted = (level.count or 0) - self.planned
        if wanted <= 0:
            return Report(f"{self.planned} towers planned already")
        sites = self.tower_sites(world, wanted)
        if not sites:
            return Report("No room for another tower at the approaches", refused=True)
        given = sum(bool(self.give("plan_building", self.player, BuildingType.TOWER, site)) for site in sites)
        if not given:
            return Report("", refused=True)
        self.planned += given
        name = race.buildings[BuildingType.TOWER].name
        return Report(f"{given} {name}s planned at the approaches" if given != 1 else f"{an(name)} planned at the approach")

    def tower_sites(self, world: World, count: int) -> list[Pos]:
        """Up to *count* sites for towers between the side's hall nearest a rival it knows of (or the map's middle,
        with none known) and that rival: the approach facing it first, then those beside it, one tower an approach;
        never on the walk between a hall and its mine, nor crowding a site already planned."""
        halls = self._halls(world)
        rivals = [record.center for record in known_enemy_buildings(world, self.player)]
        middle = (world.width / 2, world.height / 2)
        if rivals:
            hall = min(halls, key=lambda h: (min(dist(h.center, r) for r in rivals), h.id))
            towards = min(rivals, key=lambda r: dist(r, hall.center))
        else:
            hall = halls[0]
            towards = middle
        hx, hy = hall.center
        facing = math.atan2(towards[1] - hy, towards[0] - hx) if dist(towards, hall.center) > 0 else 0.0
        size = BUILDINGS[BuildingType.TOWER].size
        guards = [b.center for b in world.player_buildings(self.player, BuildingType.TOWER)]
        taken = self._sites_ordered(world) + self._lanes(world)
        guards += [(pos[0] + size / 2, pos[1] + size / 2) for pos, kind in self._planned(world) if kind is BuildingType.TOWER]
        found: list[Pos] = []
        for turn, reach in APPROACHES:
            if len(found) == count:
                break
            angle = facing + turn * FORTIFY_TURN
            anchor = (min(max(hx + reach * math.cos(angle), 1.0), world.width - 1.0),
                      min(max(hy + reach * math.sin(angle), 1.0), world.height - 1.0))
            if any(dist(anchor, guard) < FORTIFY_SPREAD for guard in guards):
                continue  # this approach is guarded already
            site = site_search(world, BuildingType.TOWER, self.player, anchor, self.rng, -size, FORTIFY_SEARCH, taken)
            if site is None:
                continue
            found.append(site)
            taken.append((site, size))
            guards.append((site[0] + size / 2, site[1] + size / 2))
        return found

    def _planned(self, world: World) -> list[tuple[Pos, BuildingType]]:
        """Sites the side has ordered and not begun: its settlement's plans, then its builders' next sites."""
        sites = [(plan.pos, plan.type) for plan in world.player_plans(self.player)
                 if plan.building is None and plan.pos is not None and isinstance(plan.type, BuildingType)]
        for unit in world.player_units(self.player):
            sites += [(order.pos, order.type) for order in unit.orders if isinstance(order, Build) and order.building is None]
        return sites

    def _sites_ordered(self, world: World) -> list[tuple[Pos, int]]:
        return [(pos, BUILDINGS[kind].size) for pos, kind in self._planned(world)]

    def _lanes(self, world: World) -> list[tuple[Pos, int]]:
        """The walks between the side's halls and the mines they work, as blocks a tower's site may not crowd."""
        blocks: list[tuple[Pos, int]] = []
        width = 2 * LANE_CLEARANCE + 1
        for hall in world.player_buildings(self.player, BuildingType.TOWN_HALL):
            for mine in known_mines(world, self.player):
                length = dist(hall.center, mine.center)
                if length > EXPAND_DISTANCE:
                    continue
                steps = max(1, math.ceil(length))
                for i in range(steps + 1):
                    x = hall.center[0] + (mine.center[0] - hall.center[0]) * i / steps
                    y = hall.center[1] + (mine.center[1] - hall.center[1]) * i / steps
                    blocks.append(((int(x) - LANE_CLEARANCE, int(y) - LANE_CLEARANCE), width))
        return blocks

    # -- Gold and Lumber --------------------------------------------------------------------------------------------

    def _gather(self, world: World, level: Level, resource: Resource) -> Report:
        """Put the idle workers on *resource*, and those on the other resource up to *level*'s share of them."""
        other = Resource.LUMBER if resource is Resource.GOLD else Resource.GOLD
        moved = self.moved[resource]
        workers = [u for u in world.player_units(self.player) if u.is_worker]
        moved &= {u.id for u in workers}
        idle = [u for u in workers if not u.orders and not u.hidden and u.constructing is None]
        elsewhere = sorted((u for u in workers if gathering(u) is other and u.id not in moved),
                           key=lambda u: (u.carrying is not None, u.hidden, u.id))
        taking = elsewhere[:max(0, level.wanted(len(elsewhere) + len(moved)) - len(moved))]
        sending = idle + taking
        if not sending:
            return Report(f"No idle workers, nor any on {other.value}, to send to {resource.value}", refused=True)
        jobs = self._mines(world, sending) if resource is Resource.GOLD else self._trees(world, sending)
        if not jobs:
            return Report("No gold mine known by a hall" if resource is Resource.GOLD else "No trees known", refused=True)
        sent = 0
        taken = {u.id for u in taking}
        for target, ids in jobs.items():
            if self.give("harvest", ids, target):
                sent += len(ids)
                moved.update(uid for uid in ids if uid in taken)
        if not sent:
            return Report("", refused=True)
        return Report(f"{sent} more {'mining' if resource is Resource.GOLD else 'chopping'}")

    def _depots(self, world: World, resource: Resource) -> list[Point]:
        return [b.center for b in world.player_buildings(self.player, done=True) if resource in b.info.deposits]

    def _mines(self, world: World, workers: list[Unit]) -> dict[int | Pos, list[int]]:
        """Each worker's mine: the nearest the side knows of with gold in it by a hall of its own, clear of camps and of
        towers' fire."""
        depots = self._depots(world, Resource.GOLD)
        if not depots:
            return {}
        towers = known_towers(world, self.player)
        mines = [m for m in known_mines(world, self.player)
                 if m.has_gold and not guarded(world, self.player, m.center) and not under_fire(m.center, towers)]

        def from_depot(mine) -> float:
            return min(dist(mine.center, depot) for depot in depots)

        near = [m for m in mines if from_depot(m) <= EXPAND_DISTANCE] or sorted(mines, key=lambda m: (from_depot(m), m.id))[:1]
        jobs: dict[int | Pos, list[int]] = {}
        for worker in workers:
            if near:
                jobs.setdefault(min(near, key=lambda m: (dist(worker.pos, m.center), m.id)).id, []).append(worker.id)
        return jobs

    def _trees(self, world: World, workers: list[Unit]) -> dict[int | Pos, list[int]]:
        """Each worker's tree: of the remembered trees a worker can reach the side of, those nearest a depot taking
        lumber and clear of towers' fire, the nearest to the worker, :data:`TREE_CHOPPERS` to a tree."""
        depots = self._depots(world, Resource.LUMBER)
        if not depots:
            return {}
        knowledge, width, height = world.worker_knowledge[self.player], world.width, world.height
        towers = known_towers(world, self.player)

        def open_beside(x: int, y: int) -> bool:
            return any(0 <= x + dx < width and 0 <= y + dy < height and not knowledge.blocked[(y + dy) * width + x + dx]
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)

        trees: list[tuple[float, Pos]] = []
        for index in knowledge.trees:
            if knowledge.terrain[index] is not Terrain.TREES:
                continue
            y, x = divmod(index, width)
            centre = (x + 0.5, y + 0.5)
            if open_beside(x, y) and not under_fire(centre, towers):
                trees.append((min(dist(centre, depot) for depot in depots), (x, y)))
        trees.sort()
        choice = [pos for _far, pos in trees[:max(4, 3 * len(workers))]]
        jobs: dict[int | Pos, list[int]] = {}
        for worker in sorted(workers, key=lambda u: u.id):
            open_trees = [pos for pos in choice if len(jobs.get(pos, [])) < TREE_CHOPPERS]
            if not open_trees:
                break
            tree = min(open_trees, key=lambda pos: (dist(worker.pos, (pos[0] + 0.5, pos[1] + 0.5)), pos))
            jobs.setdefault(tree, []).append(worker.id)
        return jobs
