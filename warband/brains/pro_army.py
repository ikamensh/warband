"""Tactical commitments and exclusive soldier tasking for the stronger opponent.

The army owns engagements, retreat, camping and special errands. Intelligence
supplies observed facts; economy consumes recruitment needs. Neither owns or
mutates the army's assignments.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from warband.brains.pro_force import _tower_strength, _tower_strength_own, camp_strength, strength
from warband.brains.pro_profiles import ProProfile

from warband.brains.ai import ESCAPE_SECONDS, RAIDERS, answer_flyers, answering, camp_safe_point, camp_standing, camp_worth, can_reach_point, dodge_camp_slams, escape_warned_marches, known_camps, known_mines, lost_track, prepared_cohort, push_is_blind, rally_past, reachable_cohort, redirect_searchers, retry_force
from warband.sim.model import Attack, Build, Building, Move, Point, Repair, Salvage, Unit, World, dist, int_sum, plain_sum, rect_gap, tile_center
from warband.sim.rules import BuildingType, UnitType

from warband.brains.pro_intelligence import Intelligence
from warband.brains.pro_assignments import Assignments, Duty, WorkerErrands
from warband.brains.ai import Hunt
from warband.brains.magic import Magus
from warband.brains.unique import Commander
from warband.sim import camps

WALK_OVER: Final = 4.0

class Army:
    """Own tactical commitments and the roster granting each soldier one duty."""

    def __init__(self, player: int, profile: ProProfile, intel: Intelligence,
                 workers: WorkerErrands, commander: Commander) -> None:
        self.player = player
        self.profile = profile
        self.intel = intel
        self.workers = workers
        self.commander = commander
        self.assignments = Assignments()
        self.hunt = Hunt()
        self.magus = Magus(profile)
        self.attacking = False
        self.target: Point | None = None
        self.commit_strength = 0.0
        self.regroup_until = 0.0
        self._scout_leg = 0
        self._scout_leg_at = 0.0
        self._siege_by = 0.0
        self._intercept_owner: int | None = None
        self.creeping: int | None = None
        self.creep_strength = 0.0
        self.creep_until = 0.0
        self.camp_seen: dict[int, float] = {}
        self.camp_retry: dict[int, float] = {}
        self.camp_failed: dict[int, float] = {}
        self.camp_at_launch: dict[int, float] = {}

    def fit_units(self, world: World) -> list[Unit]:
        return self.assignments.fit_units(world, self.player)

    def camp_candidates(self, world: World) -> list[Unit]:
        """The force available to a camp decision, leaving detached duties alone."""
        return self.assignments.select(self.fit_units(world), (Duty.MAIN, Duty.GUARD, Duty.CREEP))

    def camp_obstructed(self, world: World) -> bool:
        """Whether a live rival commitment or a threat to the economy takes priority."""
        return ((self.attacking and not push_is_blind(world, self.player))
                or bool(self._threats(world)) or bool(self._home_towers(world)))

    @property
    def siege_requested(self) -> bool:
        return self._siege_by > 0.0

    def review_recruitment(self, world: World) -> None:
        if self._siege_by and not self.siege_wanted(world):
            self._siege_by = 0.0

    def prepare(self, world: World) -> None:
        """End completed duties and keep every escaping march safe between decisions."""
        self.assignments.sync(world, self.player)
        if self.attacking:
            excluded = {u.id for u in self.intel.units(world)
                        if self.assignments.duty(u.id) in (Duty.CREEP, Duty.HEAL, Duty.ESCAPE)}
            escaped = escape_warned_marches(world, self.player, self.fit_units(world), excluded)
            if escaped:
                self.assignments.assign(list(escaped), Duty.ESCAPE, until=world.time + ESCAPE_SECONDS)
                self.attacking = False
                self.regroup_until = max(self.regroup_until, world.time + self.profile.regroup_seconds)
                self.intel.note(world, "regroup outside newly sighted neutral guards")
        searches = self.workers.scouts + self.assignments.members(Duty.HUNT)
        if self.workers.prospector is not None:
            searches.append(self.workers.prospector)
        redirect_searchers(world, self.player, searches)

    def _catapults(self, world: World) -> int:
        """Catapults standing or on the stocks: what a siege answer counts itself short against."""
        return (int_sum(1 for u in self.intel.units(world) if u.type is UnitType.CATAPULT)
                + int_sum(b.queue.count(UnitType.CATAPULT) for b in world.player_buildings(self.player)))

    def siege_wanted(self, world: World) -> bool:
        """A towered target turned a push back and the catapults it called for are not there yet."""
        return (self.profile.siege_answer > 0 and world.time < self._siege_by
                and self._catapults(world) < self.profile.siege_answer)

    def _threats(self, world: World) -> list[Unit]:
        # A vault is out on a rift, the second one mid-map where the armies meet: a rival passing it is no raid on the
        # base, and the army that ran to it fought where the rival chose (WB-067).
        own = [b for b in world.player_buildings(self.player) if b.type is not BuildingType.VAULT]
        if not own:
            return []
        out = []
        for unit in self.intel.enemies(world):
            if not unit.info.damage:
                continue  # an unarmed flyer looking on is no raid: the shooters answer it (answer_flyers)
            if world.players[unit.player].neutral:
                continue  # a camp is leashed to its lair: it takes no ground, so there is nothing to answer
            if any(dist(unit.pos, b.center) < 9.0 for b in own):
                out.append(unit)
        return out

    def step(self, world: World) -> None:
        roster = self.assignments
        roster.sync(world, self.player)
        roster.release(Duty.GUARD)
        self._raid(world, roster.select(self.fit_units(world), (Duty.MAIN, Duty.RAID)))
        candidates = roster.select(self.fit_units(world), (Duty.MAIN, Duty.HUNT))
        excluded = {u.id for u in self.intel.units(world)
                    if roster.duty(u.id) not in (Duty.MAIN, Duty.HUNT)}
        self.hunt.step(world, self.player, candidates,
                       lost_track(world, self.player, self.intel.unexplored_corner(world)), exclude=excluded)
        roster.replace(Duty.HUNT, list(self.hunt.party))
        specialists = self.commander.step(world, self.player,
                                         roster.select(self.intel.units(world), (Duty.MAIN, Duty.COMMANDER)),
                                         self.target if self.attacking else None)
        roster.replace(Duty.COMMANDER, list(specialists))
        self._send_scout(world)
        army = roster.select(self.fit_units(world), (Duty.MAIN, Duty.CREEP))
        answer_flyers(world, self.player, army, 9.0)
        # Keep the historical world-order partition, but an expedition member
        # remains its expedition's until that commitment ends.
        guards, army = army[:self.profile.guards], army[self.profile.guards:]
        roster.assign([u.id for u in guards if roster.duty(u.id) is Duty.MAIN], Duty.GUARD)
        threats = self._threats(world)
        if (threats and not (self.attacking and strength(world, threats)
                             < self.profile.ignore_raid_ratio * strength(world, army))
                and not self._trade_bases(world, guards, threats)):
            outmatched = self._outmatched_at_home(world, guards + army, threats)
            if self.creeping is not None:
                point = self._fall_back_point(world, threats) if outmatched else None
                point = point or self._defend_point(world, threats)
                self._interrupt_camp(world, point, past=not outmatched)
            defenders = self.assignments.select(guards + army, (Duty.MAIN, Duty.GUARD))
            if outmatched:
                self._fall_back(world, defenders, threats)
            else:
                self._defend(world, defenders, threats)
            return
        if self._strike_towers(world, guards + ([] if self.attacking else army)):
            return
        if self._creep(world, guards + army):
            return
        guards = roster.select(guards, (Duty.MAIN, Duty.GUARD))
        army = roster.select(army, (Duty.MAIN, Duty.GUARD))
        self._post(world, guards)
        hall = self.intel.hall(world)
        mine = strength(world, army)
        if self.attacking:
            # Judge a push by how it is going, not by how big the enemy looks from
            # where the army happens to be standing. Estimating the defence again
            # each pass walks the army home the moment a tower comes into view, and
            # then straight back out once it is out of view again; an army that
            # oscillates like that never fights at all.
            outmatched = self._outmatched_at_target(world, army, mine)
            if len(army) < 3 or mine < self.profile.retreat_ratio * self.commit_strength or outmatched:
                self._intercept_owner = None
                self.attacking = False
                self.regroup_until = world.time + self.profile.regroup_seconds
                self.intel.note(world, f"withdraw at {mine:.0f} of {self.commit_strength:.0f}")
                if (outmatched and self.profile.siege_answer > 0 and self.target is not None
                        and self._catapults(world) < self.profile.siege_answer):
                    # Only a tower's answer is a stone: turned back by soldiers alone, the workshop is a detour.
                    # Holding the next push hostage to the catapults was priced too, and it cost games — the
                    # army walks again when it is ready and the stones join it as reinforcements do.
                    towers = _tower_strength(world, self.player, self.target)
                    if towers >= 0.4 * self._local_defence(world, self.target)[0]:
                        self._siege_by = world.time + 240.0
                        self.intel.note(world, f"siege answer: want {self.profile.siege_answer} catapults")
                if hall is not None:
                    home = self.intel.front_point(world, hall)
                    for unit in army:
                        world.move([unit.id], self._muster(world, home, unit))
                return
            if self._intercept_owner is not None:
                # The quarry moves: follow its middle while it stays in the open, and give the chase up for a
                # building once it reaches home or leaves our sight.
                quarry = [u for u in self.intel.enemies(world) if not u.is_worker and u.player == self._intercept_owner]
                centre = self._army_centre(world, quarry)
                buildings = [r.center for r in self.intel.known_buildings(world) if r.player == self._intercept_owner]
                if centre is None or (buildings and min(dist(centre, b) for b in buildings) <= 12.0):
                    self._intercept_owner = None
                    self.target = None
                else:
                    self.target = centre
            targets = self._attack_targets(world)
            if targets and self._intercept_owner is None and (self.target is None or not self._still_there(world, self.target)):
                self.target = self._pick_target(world, targets, hall.center if hall is not None else army[0].pos)
            if self.target is None:
                return
            # Reinforcements walk to the same place, so the push grows instead of
            # trickling. A soldier crossing the map alone arrives alone and dies
            # alone, so the ones still at home wait until there are enough to travel
            # together; the ones already at the front simply rejoin the fight.
            idle = [u for u in army if not u.orders and can_reach_point(world, u, self.target)]
            arrived = [u.id for u in idle if dist(u.pos, self.target) <= 12.0]
            if arrived:
                world.attack_move(arrived, self.target)
            waiting = [u for u in idle if dist(u.pos, self.target) > 12.0]
            if len(waiting) >= self.profile.reinforce_group:
                world.attack_move([u.id for u in waiting], self.target)
            elif waiting and hall is not None:
                point = self.intel.front_point(world, hall)
                for unit in waiting:
                    if dist(unit.pos, point) > 4.0:
                        self._send_to_muster(world, point, unit)
            return
        if world.time < self.regroup_until or self._push_waits(world):
            self._gather(world, army, hall)
            return
        intercept = self._intercept_point(world, mine, self._caution(world)) if len(army) >= self.profile.min_army else None
        if intercept is not None:
            point, quarry_owner = intercept
            self.attacking = True
            self._intercept_owner = quarry_owner
            self.target = point
            self.commit_strength = mine
            self.intel.note(world, f"attack {len(army)} strong — intercept their army in the open")
            world.attack_move([u.id for u in army], point)
            return
        targets = self._attack_targets(world)
        origin = hall.center if hall is not None else (army[0].pos if army else None)
        if not targets or origin is None:
            self._gather(world, army, hall)
            return
        target = self._pick_target(world, targets, origin)
        theirs = self._defenders_near(world, target)
        care = self._caution(world)
        owner = self._owner_of(world, target)
        blind = (world.time - self.intel.last_seen(owner) > self.profile.stale_seconds
                 if owner is not None else not self.intel.enemies(world))
        if blind:
            # An expedition is how a blind army gets the information needed for
            # a proper attack decision. Requiring the full FFA victory margin
            # before it has found anybody can keep it home for the entire game.
            care = 1.0 + 0.25 * (care - 1.0)
        if len(army) < self.profile.min_army * care:
            self._gather(world, army, hall)
            return
        ratio = self.profile.attack_ratio
        away = self.profile.punish and self._army_away(world, owner, target)
        if away:
            ratio *= self.profile.punish_ratio  # their relief has the map to cross; the window is the margin
        if mine >= ratio * care * theirs:
            self.attacking = True
            self.target = target
            self.commit_strength = mine
            self.intel.note(world, f"attack {len(army)} strong ({mine:.0f} against {theirs:.0f})"
                             f"{' — their army is away' if away else ''}")
            world.attack_move([u.id for u in army], target)
        else:
            self._gather(world, army, hall)

    def _camp_strength(self, world: World, record, army: list[Unit]) -> float:
        """The public roster/observed guard power, priced against the army's present composition."""
        base = camp_strength(world, self.player, record.center, [], record.id, self.camp_seen.get(record.id, 0.0))
        self.camp_seen[record.id] = base
        best = camp_strength(world, self.player, record.center, army, record.id, base)
        camp = world.camp_for(record.id)
        if camp is not None and camp.encounter:
            return best
        return max(best, self.profile.creep_prior * self._typical_soldier(world))

    def _end_camp(self, world: World, *, failed: bool) -> list[Unit]:
        """End the expedition and transfer its surviving members to the main force."""
        lair = self.creeping
        assert lair is not None
        party = self.assignments.select(self.fit_units(world), (Duty.CREEP,))
        if failed:
            self.camp_retry[lair] = world.time + self.profile.creep_retry
            self.camp_failed[lair] = self.creep_strength
            self.regroup_until = world.time + self.profile.regroup_seconds
        self.creeping = None
        self.assignments.release(Duty.CREEP)
        return party

    def _interrupt_camp(self, world: World, point: Point, *, past: bool, reason: str = "defend") -> None:
        """End a commitment safely before a higher-priority task or policy change."""
        lair = self.creeping
        assert lair is not None
        camp = world.camp_for(lair)
        party = self._end_camp(world, failed=True)
        if party:
            if camp is not None and lair not in world.worker_knowledge[self.player].cleared_encounters:
                self.assignments.assign([u.id for u in party], Duty.ESCAPE, until=world.time + ESCAPE_SECONDS)
                middle = camps.centre(world, camp)
                dest = camp_safe_point(world, self.player, rally_past(middle, point) if past else point)
                # A group march uses its slowest soldier's pace; separate walks
                # let every survivor keep its own lead over the pursuing guards.
                for unit in party:
                    world.move([unit.id], dest)
            else:
                world.stop([u.id for u in party])
        self.intel.note(world, f"break off the camp to {reason}")

    def _creep(self, world: World, army: list[Unit]) -> bool:
        """Clear a creature camp.  True when the army has been given that job and nothing else.

        The whole army commits until lair and guards are down. A push worn
        past ``creep_abort`` withdraws; a failed camp waits for a stronger army
        as well as ``creep_retry`` seconds, avoiding repeated costly assaults.
        """
        profile = self.profile
        if not profile.creep or (self.attacking and not push_is_blind(world, self.player)):
            if self.creeping is not None:
                hall = self.intel.hall(world)
                home = self._home_point(world, hall) if hall is not None else (world.width / 2, world.height / 2)
                self._interrupt_camp(world, home, past=False, reason="regroup")
            return False  # a push at something real keeps its army; a blind one yields to clearing a known camp
        camp = world.camp_for(self.creeping) if self.creeping is not None else None
        if self.creeping is not None and (camp is None or self.creeping in world.worker_knowledge[self.player].cleared_encounters):
            self.intel.note(world, "camp cleared")
            self._end_camp(world, failed=False)
            camp = None
        if camp is not None:
            party = self.assignments.select(army, (Duty.CREEP,))
            mine = strength(world, party)
            # The patience is not a nicety: a den the army cannot reach or cannot break would otherwise hold
            # the whole army at it for the rest of the match, and reinforcements keep the strength test from
            # ever tripping.  Fuzz reports that as an army of stalled units.
            minimum = 1 if self.camp_at_launch.get(camp.lair) == 0 else 3
            if len(party) < minimum or mine < profile.creep_abort * self.creep_strength or world.time >= self.creep_until:
                hall = self.intel.hall(world)
                home = self._home_point(world, hall) if hall is not None else (world.width / 2, world.height / 2)
                self._interrupt_camp(world, home, past=False, reason="regroup")
                self.intel.note(world, f"break off the camp at {mine:.0f} of {self.creep_strength:.0f}")
                if hall is not None:
                    front = self.intel.front_point(world, hall)
                    for unit in self.assignments.select(army, (Duty.MAIN, Duty.GUARD)):
                        world.move([unit.id], self._muster(world, front, unit))
                return True
            spot = self.intel.standable(world, camps.centre(world, camp), expedition=True)
            idle = [u.id for u in party if not u.orders]
            if idle:
                world.attack_move(idle, spot)
            return True
        if world.time < max(profile.creep_from, self.regroup_until):
            return False
        hall = self.intel.hall(world)
        origin = hall.center if hall is not None else (army[0].pos if army else None)
        if origin is None:
            return False
        # Price reward and travel only after filtering for a feasible assault.
        worth = {record.id: camp_worth(world, self.player, record) for record in known_camps(world, self.player)}
        options = []
        for record in known_camps(world, self.player):
            if not camp_standing(world, self.player, record):
                continue
            if world.time < self.camp_retry.get(record.id, 0.0):
                continue
            if dist(record.center, origin) > profile.creep_reach * worth[record.id]:
                continue
            spot = self.intel.standable(world, record.center, expedition=True)
            cohort = prepared_cohort(world, reachable_cohort(world, army, spot), profile.rejoin_hp)
            now = self._camp_strength(world, record, cohort)
            if len(cohort) < (1 if now == 0 else profile.creep_army):
                continue  # witnessed empty dens need cleanup, not a full combat wave
            force = strength(world, cohort)
            if force < retry_force(self.camp_failed.get(record.id, 0.0),
                                   self.camp_at_launch.get(record.id, 0.0), now):
                continue
            if force < profile.creep_ratio * now:
                continue
            options.append((record, cohort, force, now, spot))
        if not options:
            return False
        target, cohort, mine, theirs, spot = min(
            options, key=lambda item: dist(item[0].center, origin) / worth[item[0].id])
        # This concrete expedition replaces the blind PvP guess. The push's
        # target/flag must not reclaim the same soldiers when a rival is seen.
        self.attacking = False
        self.target = None
        self._intercept_owner = None
        self.creeping = target.id
        self.creep_strength = mine
        self.camp_at_launch[target.id] = theirs
        self.assignments.assign([u.id for u in cohort], Duty.CREEP)
        self.creep_until = world.time + profile.creep_patience
        self.intel.note(world, f"clear the camp with {len(cohort)} ({mine:.0f} against {theirs:.0f})")
        world.attack_move([u.id for u in cohort], spot)
        if hall is not None:
            home = self._home_point(world, hall)
            for unit in army:
                # Only the reachable stay home: an isolated soldier ordered
                # to a muster across the water would stall there for good.
                if self.assignments.duty(unit.id) is not Duty.CREEP and can_reach_point(world, unit, home):
                    if unit.hp < profile.rejoin_hp * unit.max_hp:
                        self.assignments.assign([unit.id], Duty.HEAL)
                    world.move([unit.id], self._muster(world, home, unit))
        return True

    def _outmatched_at_target(self, world: World, army: list[Unit], mine: float) -> bool:
        """Whether the push, where it fights, faces more than ``abort_ratio`` times what it has left: the defenders
        in sight round what it walked at and the towers known to cover it, against the soldiers of the push that
        are there.

        The push is otherwise judged by what it has lost of itself, which lets it lose half an army to two towers
        and a barracks that keeps answering before it turns round.  This reads the fight itself, only once the
        army stands in it (an estimate made on the way walks an army home each time a tower drifts out of sight),
        and the regrouping that follows a withdrawal keeps it from walking straight back."""
        if self.profile.abort_ratio <= 0.0 or self.target is None:
            return False
        target = self.target
        there = [u for u in army if dist(u.pos, target) <= 12.0]
        if len(there) < 3:
            return False  # not there yet
        defenders = [e for e in self.intel.enemies(world) if not e.is_worker and e.info.soldier and dist(e.pos, target) <= 12.0]
        theirs = strength(world, defenders) + _tower_strength(world, self.player, target, 9.0)
        return theirs > self.profile.abort_ratio * strength(world, there)

    def _push_waits(self, world: World) -> bool:
        """Whether a push is still held for the hour and the upgrades the posture times it with."""
        profile = self.profile
        if world.time >= profile.push_by:
            return False
        return world.time < profile.push_after or len(world.players[self.player].upgrades) < profile.push_upgrades

    def _still_there(self, world: World, point: Point) -> bool:
        """Whether anything of the enemy's is still standing where the push was aimed."""
        return any(dist(record.center, point) < 3.0 for record in self.intel.known_buildings(world))

    def _home_point(self, world: World, hall: Building) -> Point:
        """Somewhere a soldier can actually stand next to the hall.

        A hall's centre is inside its own footprint, which is blocked ground: a
        unit sent there paths towards it and stops a tile short for good. Fuzz
        caught an archer stalled twenty seconds on a move of two thirds of a
        tile, which is what that looks like from the outside.
        """
        tile = world.free_tile_near(hall.rect, prefer=hall.center)
        return tile_center(tile) if tile is not None else self.intel.front_point(world, hall)

    def _post(self, world: World, guards: list[Unit]) -> None:
        """Send the home guard back to the hall whenever it has nothing to do, and leave it at its post once it is
        standing there (:meth:`_send_to_muster`)."""
        hall = self.intel.hall(world)
        if hall is None:
            return
        home = self._home_point(world, hall)
        for guard in guards:
            if guard.orders or dist(guard.pos, hall.center) <= 6.0:
                continue
            self._send_to_muster(world, home, guard)

    def _caution(self, world: World) -> float:
        """How much more careful to be than in a duel.

        Starting a fight in a free-for-all pays for itself only if it is won
        cheaply: everything spent on it is a gift to the players who stayed out.
        The posture that rates 1562 Elo one against one rates 1022 in a four
        player game without this, which is barely ahead of the brain it
        replaced — so every extra opponent buys back some of the caution.

        Beyond a five-seat game the extra seats fight each other as much as
        they watch us, so caution stops growing: uncapped, sixteen seats need
        twelve times the strength and sixty soldiers to leave home, and no
        attack ever goes out.
        """
        bystanders = int_sum(1 for p in world.players[:world.seats] if p.id != self.player and p.alive) - 1
        return 1.0 + self.profile.ffa_caution * min(max(0, bystanders), 3)

    def _army_centre(self, world: World, army: list[Unit]) -> Point | None:
        if not army:
            return None
        return (plain_sum(u.x for u in army) / len(army), plain_sum(u.y for u in army) / len(army))

    def _gather(self, world: World, army: list[Unit], hall: Building | None) -> None:
        """Wait in one place. An army that trickles forward is an army that loses twice."""
        if hall is None:
            return
        point = self.intel.front_point(world, hall)
        for unit in army:
            if unit.orders or dist(unit.pos, point) <= 4.0:
                continue
            self._send_to_muster(world, point, unit)

    def _muster(self, world: World, point: Point, unit: Unit) -> Point:
        """*point*, nudged so the whole army is not walking at one tile.

        Twenty soldiers sent to the same coordinate cannot all stand on it. The
        ones that cannot keep a Move order they are unable to finish and stop
        taking part in the game — fuzz reports it as a stalled unit.
        """
        angle = (unit.id % 12) / 12.0 * 2.0 * math.pi
        spread = 1.0 + unit.id % 3
        return self.intel.standable(world, (point[0] + spread * math.cos(angle), point[1] + spread * math.sin(angle)))

    def _send_to_muster(self, world: World, point: Point, unit: Unit) -> None:
        """Send *unit* to its own place around *point*, and leave it alone once it stands there.

        Its place is nudged per unit and nudged again onto standable ground, so it can be several tiles from
        *point*: a soldier judged by its distance from *point* alone was ordered onto ground it was already
        standing on, every pass of the brain, for the rest of the match.  It finished the walk in one step,
        went idle, and was sent again; fuzz reads a unit ordered about once a second and never getting
        anywhere as a stalled unit, which is what it was (seed 81, an archer of a bred orc posture).

        Whether it is there is the world's answer (:meth:`~warband.sim.model.World.stands_at`), which is the
        same one the world ends the walk on: a brain with a tolerance of its own sent a footman after a post a
        knight was standing on every half second, and the world gave it up again every half second (seed 92)."""
        post = self._muster(world, point, unit)
        if not world.stands_at(unit, post) and can_reach_point(world, unit, post):
            world.move([unit.id], post)

    def _local_defence(self, world: World, point: Point) -> tuple[float, int]:
        """What is actually standing at *point*: visible enemy soldiers within reach of it and the towers
        covering it, as ``(strength, soldiers)``.  Where :meth:`_defenders_near` prices the owner's whole
        army (it walks home), this prices the ground itself — the difference between a main base and the
        expansion nobody is standing on.  Out of sight, the last look at the building there stands in for
        ninety seconds: from home every unseen expansion would otherwise price at nought."""
        local = [u for u in self.intel.enemies(world) if not u.is_worker and dist(u.pos, point) <= 14.0]
        force, count = strength(world, local), len(local)
        if not local:
            for record in self.intel.known_buildings(world):
                seen = self.intel.building_sighting(record.id)
                if seen is not None and dist(record.center, point) <= 3.0 and world.time - seen[0] <= 90.0:
                    force, count = seen[1], seen[2]
                    break
        return force + _tower_strength(world, self.player, point), count

    def _pick_target(self, world: World, targets: list[Point], origin: Point) -> Point:
        """Which of *targets* to walk at: the nearest, or with ``soft_target`` the weakest-defended first
        and the nearest of equals — an expansion razed before its army comes home is a mine and a hall
        the enemy paid for twice."""
        if not self.profile.soft_target:
            return min(targets, key=lambda t: dist(t, origin))
        return min(targets, key=lambda t: (self._local_defence(world, t)[0], dist(t, origin)))

    def _army_away(self, world: World, owner: int | None, target: Point) -> bool:
        """Their army was seen just now, most of it accounted for, and it is not at *target* (``punish``):
        what relief the target gets has the whole map to cross first."""
        sighting = self.intel.army_sighting(owner) if owner is not None else None
        if sighting is None:
            return False
        when, middle, seen = sighting
        if world.time - when > self.profile.stale_seconds:
            return False
        remembered = plain_sum(self.intel.remembered(owner).values())
        if remembered <= 0.0 or seen < 0.35 * remembered:
            return False  # a detachment in sight says nothing about where the rest stands
        return dist(middle, target) > 14.0 and self._local_defence(world, target)[1] <= 0.25 * seen

    def _intercept_point(self, world: World, mine: float, care: float) -> tuple[Point, int] | None:
        """Where an opponent's army stands in the open, seen fresh and the smaller (``intercept``): a field
        fight on even ground, without the towers every building push must price in.  The blob otherwise
        only ever walks at buildings or waits to be walked at."""
        if not self.profile.intercept:
            return None
        best: tuple[float, Point, int] | None = None
        for owner, (when, middle, seen) in self.intel.army_sightings():
            if world.time - when > self.profile.stale_seconds:
                continue
            remembered = plain_sum(self.intel.remembered(owner).values())
            if remembered <= 0.0 or seen < 0.35 * remembered:
                continue  # a detachment: the army it belongs to is somewhere else
            buildings = [r.center for r in self.intel.known_buildings(world) if r.player == owner]
            if buildings and min(dist(middle, b) for b in buildings) <= 16.0:
                continue  # at home under its towers is a building push by another name
            theirs = [u for u in self.intel.enemies(world) if not u.is_worker and u.player == owner]
            force = strength(world, theirs)
            if mine >= self.profile.attack_ratio * care * force and (best is None or force < best[0]):
                best = (force, middle, owner)
        return (best[1], best[2]) if best is not None else None

    def _trade_bases(self, world: World, guards: list[Unit], threats: list[Unit]) -> bool:
        """Let home hold itself and walk at theirs instead (``base_trade``): their army is committed at our
        towers, which with the guard price above what came, so the race is which base falls slower — and
        the brain that always answers a raid by coming home never starts that race at all."""
        if not self.profile.base_trade or self.attacking:
            return False
        hall = self.intel.hall(world)
        if hall is None or not self.intel.known_buildings(world):
            return False
        home = _tower_strength_own(world, self.player, hall.center) + strength(world, guards)
        return home >= 0.9 * strength(world, threats)

    def _defenders_near(self, world: World, point: Point, radius: float = 12.0) -> float:
        """What is waiting at *point*: the soldiers we can see, the towers covering it,
        and half of whatever the enemy was last seen with but is currently hidden.

        Strength is linear in the number of like units, so an unseen soldier can
        simply be priced at what one of ours is worth.
        """
        owner = self._owner_of(world, point)
        # Every soldier they have defends their base, not only the ones standing
        # in it: an army that is out on the map when the scout looks is an army
        # that walks home the moment the attack starts. Counting only what is
        # near the target is how a push goes out against an estimate of twelve
        # and meets two hundred.
        if owner is not None:
            theirs = [u for u in self.intel.enemies(world) if not u.is_worker and u.player == owner]
            counted = plain_sum(self.intel.remembered(owner).values())
            hidden = max(0.0, counted - len(theirs))
            seen = (strength(world, theirs) + _tower_strength(world, self.player, point)
                    + 0.5 * hidden * self._typical_soldier(world))
        else:
            # Unknown ground could hold any one opponent, not all of them at
            # once: summing every seat's army scales the pessimism with the
            # seat count and blocks every blind attack in a big game. Price
            # the strongest single opponent instead; with one opponent the
            # two are the same.
            foes = [u for u in self.intel.enemies(world) if not u.is_worker]
            by_player: dict[int, list[Unit]] = {}
            for foe in foes:
                by_player.setdefault(foe.player, []).append(foe)
            best = 0.0
            best_n = 0
            for group in by_player.values():
                s = strength(world, group)
                if s > best:
                    best, best_n = s, len(group)
            counted = 0.0
            for p in world.players[:world.seats]:
                if p.id != self.player and p.alive:
                    counted = max(counted, plain_sum(self.intel.remembered(p.id).values()))
            hidden = max(0.0, counted - best_n)
            seen = best + _tower_strength(world, self.player, point) + 0.5 * hidden * self._typical_soldier(world)
        if world.time - self.intel.last_seen(owner) > self.profile.stale_seconds:
            # An unseen opponent still has an army. Price one up to the size
            # this posture considers a viable expedition. Beyond that, tying
            # the estimate to our own growing force makes the attack condition
            # mathematically impossible for cautious FFA profiles.
            army = self.fit_units(world)
            prior = self.profile.symmetry_prior * min(len(army), self.profile.min_army) * self._typical_soldier(world)
            seen = max(seen, prior)
        return seen

    def _owner_of(self, world: World, point: Point) -> int | None:
        """Whose ground *point* is: the player owning the nearest building to it."""
        owned = self.intel.known_buildings(world)
        if not owned:
            return None
        return min(owned, key=lambda record: dist(record.center, point)).player

    def _typical_soldier(self, world: World) -> float:
        """What one average soldier of ours is worth, as a yardstick for unseen enemies."""
        army = [u for u in self.fit_units(world) if u.info.soldier]
        return strength(world, army) / len(army) if army else 20.0

    def _victim(self, world: World) -> int | None:
        """Which opponent to go after: the one we believe is weakest.

        With two players this is the only opponent there is. With three or four
        it is the whole game — walking at the nearest neighbour while a third
        player grows is how a free-for-all is lost by the one who started it.
        """
        seen = {record.player for record in self.intel.known_buildings(world)}
        living = [p.id for p in world.players[:world.seats] if p.id != self.player and p.alive and p.id in seen]
        if not living:
            return None
        return min(living, key=lambda p: plain_sum(self.intel.remembered(p).values()))

    def _attack_targets(self, world: World) -> list[Point]:
        """What is worth walking to: the weakest opponent's production, then anything of theirs."""
        wanted = (BuildingType.BARRACKS, BuildingType.STABLES, BuildingType.WORKSHOP,
                  BuildingType.CHURCH, BuildingType.TOWN_HALL)
        victim = self._victim(world)
        buildings = self.intel.known_buildings(world)
        theirs = [record for record in buildings if record.player == victim] or buildings
        # A structure we have seen, we know the kind of; one razed while we were
        # not looking reads as unknown and stays a place worth walking to.
        production = [record.center for record in theirs
                      if getattr(world.buildings.get(record.id), "type", None) in wanted]
        if production:
            return production
        if theirs:
            return [record.center for record in theirs]
        seen = [u.pos for u in self.intel.enemies(world)]
        # Under fog an army with no target simply stands at home until the clock
        # runs out. If nothing of theirs has been found, the place to go is the
        # ground we have not looked at.
        return seen or [self.intel.unexplored_corner(world)]

    def _defend_point(self, world: World, threats: list[Unit]) -> Point:
        """Whatever is nearest our buildings: where the defence meets the attack."""
        return min(threats, key=lambda u: min(dist(u.pos, b.center)
                                              for b in world.player_buildings(self.player))).pos

    def _defend(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        """Send the soldiers at whatever is nearest our buildings. The peasants keep mining.

        Calling peasants to fight was measured twice — once only when the army
        was already winning, once whenever the army alone could not win — and
        both cost about 35 Elo against the brain that leaves them on the gold.
        They die, and the economy that would have replaced the soldiers dies
        with them.
        """
        point = self._defend_point(world, threats)
        self.attacking = False
        stale = [u.id for u in army if not isinstance(u.order, Attack) and not answering(u, point)
                 and can_reach_point(world, u, point)]
        if stale:
            world.attack_move(stale, point)

    def _outmatched_at_home(self, world: World, army: list[Unit], threats: list[Unit]) -> bool:
        """Whether the attack on the base is more than the soldiers at home can meet (``defend_ratio``)."""
        if self.profile.defend_ratio <= 0.0:
            return False
        hall = self.intel.hall(world)
        if hall is None:
            return False
        ours = strength(world, army) + _tower_strength_own(world, self.player, hall.center)
        return strength(world, threats) > self.profile.defend_ratio * ours

    def _fall_back_point(self, world: World, threats: list[Unit]) -> Point | None:
        """Behind the hall, away from the attack: where an outmatched defence gathers. None with no hall."""
        hall = self.intel.hall(world)
        if hall is None:
            return None
        tx = plain_sum(u.x for u in threats) / len(threats)
        ty = plain_sum(u.y for u in threats) / len(threats)
        hx, hy = hall.center
        away = dist((hx, hy), (tx, ty)) or 1.0
        return self.intel.standable(world, (hx + (hx - tx) / away * 5.0, hy + (hy - ty) / away * 5.0))

    def _fall_back(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        """Gather behind the hall, away from the attack, rather than walk into it one soldier at a time: the ones
        the barracks turns out join there, and the defence goes in together once it is a match."""
        point = self._fall_back_point(world, threats)
        if point is None:
            return
        self.attacking = False
        for unit in army:
            if dist(unit.pos, point) > 3.0 and not (isinstance(unit.order, Move) and dist(unit.order.target, point) < 4.0):
                self._send_to_muster(world, point, unit)

    def _send_scout(self, world: World) -> None:
        """Keep one pair of eyes on the enemy: the flying machine if we have one (the workshop makes one first,
        :meth:`_choose_unit`), a peasant if not.  It flies over whatever lies between and circles their base; only
        their shooters and towers can reach it.

        Everything the brain decides about attacking rests on knowing what is
        over there, so a scout is cheap at almost any price — and one peasant
        is a much smaller loss than the army that would otherwise walk in blind.
        """
        if not self.profile.scout or world.time < self.profile.scout_from:
            return
        self.workers.scouts = [i for i in self.workers.scouts if i in world.units]
        if not self.workers.scouts or not world.units[self.workers.scouts[0]].flying:
            flyers = [u for u in self.intel.units(world) if u.flying and not u.info.damage]  # the eyes: an armed flyer hunts
            if flyers:
                self.workers.scouts = [flyers[0].id]  # the machine takes over from a peasant marked for want of one
            elif not self.workers.scouts:
                spare = [p for p in self.intel.peasants(world)
                         if not p.hidden and p.carrying is None and not isinstance(p.order, (Build, Repair, Salvage))
                         and not self.workers.answering(p.id)]
                if len(spare) > 3:
                    # Drafted with a harvest order in hand, the peasant keeps it:
                    # the ring move below is only given to a scout with nothing to
                    # do, and the gatherer policy refills an idle peasant before
                    # the next pass, so the peasant never goes and the brain knows
                    # nothing of the enemy until the enemy arrives. Sending it
                    # (stop it, keep it off the policy) was measured: 44% and 39%
                    # against Master for the two postures, against 55% blind. The
                    # engagement rule is tuned for not knowing, and given real
                    # sightings it waits while Master attacks; using them takes a
                    # different rule, not a scout. So the peasant stays home.
                    self.workers.scouts = [spare[-1].id]
        targets = [record.center for record in self.intel.known_buildings(world)]
        if not targets:
            targets = [self.intel.unexplored_corner(world)]  # nothing found yet: go and look
        for scout_id in self.workers.scouts:
            scout = world.units[scout_id]
            if scout.orders or self.assignments.duty(scout_id) is Duty.HUNT:  # a flyer on the hunt is the hunt's
                continue
            # Circle the enemy base rather than standing in it, so the sighting stays fresh; a flyer at the edge of its
            # sight, out of the reach of a tower at the middle.
            centre = min(targets, key=lambda c: dist(c, scout.pos))
            if self.profile.soft_target and scout.flying and len(targets) > 1:
                # A target choice is only as good as its last look at every place it might choose: tour them.
                ordered = sorted(targets)
                centre = ordered[self._scout_leg % len(ordered)]
                if dist(scout.pos, centre) <= scout.info.sight + 1.0 or world.time - self._scout_leg_at > 25.0:
                    self._scout_leg += 1
                    self._scout_leg_at = world.time
                    centre = ordered[self._scout_leg % len(ordered)]
            angle = (world.time / 12.0) % (2 * math.pi)
            reach = scout.info.sight - 1.0 if scout.flying else 7.0
            ring = (centre[0] + reach * math.cos(angle), centre[1] + reach * math.sin(angle))
            world.move([scout_id], self.intel.standable(world, (min(max(ring[0], 1.0), world.width - 1.0),
                                                           min(max(ring[1], 1.0), world.height - 1.0))))

    def _home(self, world: World) -> list[tuple[int, int, int, int]]:
        """The ground a tower would take from us: our halls and the mines they work."""
        halls = self.intel.halls(world)
        mines = [m.rect for m in known_mines(world, self.player)
                 if any(rect_gap((m.x + m.size / 2, m.y + m.size / 2), h.rect) <= 10.0 for h in halls)]
        return [h.rect for h in halls] + mines

    def _home_towers(self, world: World) -> list[Building]:
        """Enemy towers we can see, standing or going up, whose fire reaches a hall of ours or a mine it works."""
        home = self._home(world)
        towers = []
        for record in self.intel.known_buildings(world):
            tower = world.buildings.get(record.id)
            if tower is None or tower.type is not BuildingType.TOWER or not world.any_visible(self.player, tower.rect):
                continue
            if any(rect_gap(tower.center, rect) <= tower.info.range + tower.size / 2 for rect in home):
                towers.append(tower)
        return towers

    def _strike_towers(self, world: World, army: list[Unit]) -> bool:
        """Bring down a tower on our ground (WB-037): a young frame if the peasants and soldiers at hand can
        outpace its building, else the frame in its last ``strike_lead`` seconds, so the strike is there as it
        stands, fast enough to be done in ``strike_seconds``; whether anything was sent.

        A tower by the mine or the hall stops the gold for as long as it stands, and soldiers sent a few at a
        time die a few at a time. A peasant's blow does a point through its armour, so a dozen peasants take
        twelve points a second off it where the tower kills one of them every six seconds, and a frame gains
        only ten or twelve a second: a dozen peasants and a footman bring a young frame down before it stands,
        for nothing but the mining they miss. Not while enemy soldiers stand by it: the ordinary defence meets
        them first.
        """
        self.workers.strikers = {i for i in self.workers.strikers if i in world.units and isinstance(world.units[i].order, Attack)}
        if not self.profile.strike_seconds:
            return False
        towers = sorted(self._open_towers(world), key=lambda t: (t.hp, t.id))
        # Expedition members must escape before they can defend. Price the
        # strike using only soldiers who can participate immediately, before
        # choosing a young frame or ending an otherwise viable expedition.
        available = self.assignments.select(army, (Duty.MAIN, Duty.GUARD))
        fighters = [u for u in available if u.info.soldier]
        for tower in towers:
            armour = world.armor_of(tower)
            pace = self._strike_power(world, tower, fighters)
            spare = sorted(self.workers.free(world, self.player, miners=True),
                           key=lambda p: dist(p.pos, tower.center))[:self.profile.strikers_max]
            if tower.done:
                need = tower.hp / self.profile.strike_seconds
            else:
                info = tower.info
                left = info.build_time - tower.progress
                # Its growth, and its hit points spread over what is left of the building once they have walked over.
                need = (info.hp - max(1, info.hp // 10)) / info.build_time + tower.hp / max(1.0, left - WALK_OVER)
                if left > self.profile.strike_lead:
                    near = [p for p in spare if dist(p.pos, tower.center) <= 16.0]
                    reach = pace
                    for peasant in near:
                        reach += self._blows(world, peasant, armour)
                    if reach < need:
                        continue  # it stands whatever we do: meet it then
                    need, spare = math.inf, near  # everyone in reach: the sooner it falls, the sooner they mine again
                else:
                    need = tower.hp / self.profile.strike_seconds
            if self.creeping is not None:
                self._interrupt_camp(world, tower.center, past=True)
            drafted: list[int] = []
            for peasant in spare:
                if pace >= need:
                    break
                drafted.append(peasant.id)
                pace += self._blows(world, peasant, armour)
            if drafted:
                world.attack(drafted, tower.id)
                self.workers.strikers.update(drafted)
                self.intel.note(world, f"strike tower {tower.id}{'' if tower.done else ' frame'} with {len(drafted)} peasants "
                                 f"and {len(fighters)} soldiers")
            idle = [u.id for u in fighters if not (isinstance(u.order, Attack) and u.order.target == tower.id)]
            if idle:
                world.attack(idle, tower.id)
            return True
        return False

    def _strike_power(self, world: World, tower: Building, fighters: list[Unit]) -> float:
        pace = 0.0
        armour = world.armor_of(tower)
        for unit in fighters:
            pace += self._blows(world, unit, armour)
        for uid in self.workers.strikers:
            striker = world.units[uid]
            if isinstance(striker.order, Attack) and striker.order.target == tower.id:
                pace += self._blows(world, striker, armour)
        return pace

    def _open_towers(self, world: World) -> list[Building]:
        """The towers on our ground with no enemy soldier standing by."""
        soldiers = [e for e in self.intel.enemies(world) if not e.is_worker and e.info.soldier]
        return [t for t in self._home_towers(world) if not any(dist(e.pos, t.center) < 8.0 for e in soldiers)]

    @staticmethod
    def _blows(world: World, unit: Unit, armour: int) -> float:
        """What *unit* takes off something wearing *armour*, a second."""
        return max(1, world.damage_of(unit) - armour) / unit.info.period

    def _hunt_builders(self, world: World) -> None:
        """A lone enemy peasant inside our base is a tower or a barracks about to go up by the hall or the mine: the
        peasants nearest it drop their work and kill it while it is still walking or waiting (WB-037).

        Once it is inside its frame nothing reaches it, and a tower's frame gains ten hit points a second, more than
        two footmen take off it; on the way in, a party of peasants settles it in a few seconds if it can catch it,
        so the party is drawn from where it will be. They go only where no enemy soldier is near, and are let go
        once it is dead, out of sight or out of the base.
        """
        self.workers.hunters = {i: target for i, target in self.workers.hunters.items()
                        if i in world.units and isinstance(world.units[i].order, Attack)}
        if not self.profile.hunt_party:
            return
        home = self._home(world)
        if not home:
            return
        enemies = self.intel.enemies(world)
        soldiers = [e for e in enemies if not e.is_worker and e.info.soldier]
        intruders = {e.id: e for e in enemies if e.is_worker and min(rect_gap(e.pos, rect) for rect in home) <= 8.0
                     and not any(dist(s.pos, e.pos) < 6.0 for s in soldiers)}
        gone = [i for i, target in self.workers.hunters.items() if target not in intruders]
        if gone:
            world.release_workers(gone)
            for i in gone:
                del self.workers.hunters[i]
        for prey in intruders.values():
            want = self.profile.hunt_party - int_sum(1 for target in self.workers.hunters.values() if target == prey.id)
            if want <= 0:
                continue
            # A chase at the same speed never closes: the ones ahead of it, where it will be in a few seconds, meet it.
            ahead = (prey.x + 2.5 * prey.vx, prey.y + 2.5 * prey.vy)
            free = sorted((dist(p.pos, ahead), p.id) for p in self.workers.free(world, self.player) if dist(p.pos, prey.pos) <= 12.0)
            drafted = [i for _, i in free[:want]]
            if drafted:
                world.attack(drafted, prey.id)
                for i in drafted:
                    self.workers.hunters[i] = prey.id
                self.intel.note(world, f"hunt peasant {prey.id} with {len(drafted)}")

    def _threatening(self, world: World, foes: Sequence[Unit], unit: Unit) -> bool:
        """Whether anything armed is on *unit*: a rival, or a camp guard it can see.

        The PvP-only enemy list leaves guards out, but a wolf on a bleeding
        soldier kills it just as dead. Only visible guards count, as with
        every other decision under fog, and only blows that can land: a
        ground-only guard never threatens a wounded flyer home.
        """
        return any(world.can_strike(foe, unit) and dist(foe.pos, unit.pos) < world.strike_range(foe, unit) + 2.0
                   for foe in foes)

    def _withdraw_if_hurt(self, world: World, unit: Unit, foes: Sequence[Unit], healing_support: bool) -> bool:
        """Walk a nearly-dead soldier out of reach. A body that lives is damage next fight.

        Returns whether the unit is out of the fight, so the caller stops
        giving it targets. Finish the retreat before rejoining; once idle,
        a soldier without regeneration or a living/queued healer cannot
        recover by waiting. Camp preparation still requires healthy troops.
        """
        profile = self.profile
        if self.assignments.duty(unit.id) is Duty.HEAL:
            if (unit.hp >= profile.rejoin_hp * unit.max_hp
                    or (not unit.info.regen and not unit.orders
                        and (not unit.info.living or not healing_support))):
                self.assignments.assign([unit.id], Duty.MAIN)
                return False
            return True
        if unit.hp >= profile.retreat_hp * unit.max_hp:
            return False
        if not self._threatening(world, foes, unit):
            return False  # nothing is shooting at it; no reason to leave
        hall = self.intel.hall(world)
        if hall is None:
            return False
        self.assignments.assign([unit.id], Duty.HEAL)
        world.move([unit.id], self._muster(world, self._home_point(world, hall), unit))
        return True

    def _raid(self, world: World, army: list[Unit]) -> None:
        """Reserve cavalry for economy damage without stealing another duty's soldiers."""
        if not self.profile.raid:
            self.assignments.release(Duty.RAID)
            return
        raiders = self.assignments.members(Duty.RAID)
        spare = [u for u in army if u.type in RAIDERS and self.assignments.duty(u.id) is Duty.MAIN]
        while len(raiders) < self.profile.raiders and spare:
            rider = spare.pop()
            self.assignments.assign([rider.id], Duty.RAID)
            raiders.append(rider.id)
        prey = [u.pos for u in self.intel.enemies(world) if u.is_worker]
        if not prey:
            return
        for raider_id in raiders:
            rider = world.units[raider_id]
            if rider.orders:
                continue
            world.attack_move([raider_id], min(prey, key=lambda p: dist(p, rider.pos)))

    def combat(self, world: World) -> None:
        """Take the nearly dead out of the fight. The fighting itself is the model's."""
        self._hunt_builders(world)
        if self.creeping is not None:
            dodge_camp_slams(world, self.player, self.fit_units(world))
        if self.profile.magic:
            for spell, point in self.magus.cast(world, self.player):
                self.intel.note(world, f"cast {spell.value} at ({point[0]:.1f}, {point[1]:.1f})")
        if not self.profile.retreat_wounded:
            return
        units = world.player_units(self.player)
        army = [u for u in units if not u.is_worker and u.info.soldier and not u.info.blast]
        if not army:
            return
        foes = self.intel.enemies(world)
        foes += [u for u in world.units.values()
                 if u.player == world.neutral and u.hp > 0 and not u.hidden and u.info.damage
                 and world.is_visible(self.player, u.tile)]
        healing_support = (any(u.hp > 0 and u.info.heal for u in units)
                           or any(world.unit_info(self.player, kind).heal
                                  for building in world.player_buildings(self.player) for kind in building.queue))
        for unit in army:
            if self.assignments.duty(unit.id) is Duty.ESCAPE:
                continue  # walking out of an interrupted camp: mustering it elsewhere marches it back through the guards
            self._withdraw_if_hurt(world, unit, foes, healing_support)


