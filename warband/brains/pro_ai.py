"""A stronger computer opponent that plans an economy and commits to fights.

:class:`ProBrain` is the public brain interface. Profile data lives in
:mod:`pro_profiles`, force estimates in :mod:`pro_force`, and the private
core/economy classes hold the noncombat decisions.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Final

from warband.brains.pro_force import _tower_strength, _tower_strength_own, strength
from warband.brains.pro_profiles import PRO, PRO_PROFILES, PRO_RUSH, PRO_VANGUARD, PRO_WARDEN, ProProfile

from warband.brains.ai import CAMP_REACH, RAIDERS, answer_flyers, heading_to, known_camps, known_mines, lost_track
from warband.sim.model import Attack, Build, Building, Move, Point, Repair, Salvage, Unit, World, dist, rect_gap, tile_center
from warband.sim.rules import BuildingType, Layout, Race, UnitType

from warband.brains.pro_economy import _ProBrainEconomy

WALK_OVER: Final = 4.0

class ProBrain(_ProBrainEconomy):
    """One per AI player; ``think`` every simulation step."""

    def think(self, world: World, rng: random.Random) -> None:
        if not world.players[self.player].alive or world.winner is not None:
            return
        if world.time >= self.next_combat:
            self.next_combat = world.time + self.profile.combat_every
            self._combat(world)
        if world.time < self.next_think:
            return
        self.next_think = world.time + self.profile.think_every
        if not world.player_units(self.player):
            self._recover(world)
            return
        self._observe(world)
        self._economy(world)
        self._tower_rush(world)    # a rush tower's price is held from everything below
        self._training(world)      # soldiers get first call on the bank…
        self._construction(world, rng)  # …and buildings buy what is left
        self._research(world)
        self._repairs(world)
        self._military(world)

    def _threats(self, world: World) -> list[Unit]:
        own = world.player_buildings(self.player)
        if not own:
            return []
        out = []
        for unit in self._enemies(world):
            if not unit.info.damage:
                continue  # an unarmed flyer looking on is no raid: the shooters answer it (answer_flyers)
            if world.players[unit.player].neutral:
                continue  # a camp is leashed to its lair: it takes no ground, so there is nothing to answer
            if any(dist(unit.pos, b.center) < 9.0 for b in own):
                out.append(unit)
        return out

    def _military(self, world: World) -> None:
        army = self._army(world)
        busy = set(self._raid(world, army))
        busy |= self.hunt.step(world, self.player, [u for u in army if u.id not in busy],
                               lost_track(world, self.player, self._unexplored_corner(world)))
        self._send_scout(world)
        army = [u for u in army if u.id not in busy]
        answer_flyers(world, self.player, army, 9.0)
        # A couple of soldiers never leave. Riders picking off peasants cost more
        # than they are worth to chase with an army that is somewhere else, and a
        # base with nothing in it is what an early raid is looking for.
        guards, army = army[:self.profile.guards], army[self.profile.guards:]
        threats = self._threats(world)
        if threats and not (self.attacking and strength(world, threats)
                            < self.profile.ignore_raid_ratio * strength(world, army)):
            if self._outmatched_at_home(world, guards + army, threats):
                self._fall_back(world, guards + army, threats)
            else:
                self._defend(world, guards + army, threats)
            return
        if self._strike_towers(world, guards + ([] if self.attacking else army)):
            return
        if self._creep(world, guards + army):
            return
        self._post(world, guards)
        hall = self._hall(world)
        mine = strength(world, army)
        if self.attacking:
            # Judge a push by how it is going, not by how big the enemy looks from
            # where the army happens to be standing. Estimating the defence again
            # each pass walks the army home the moment a tower comes into view, and
            # then straight back out once it is out of view again; an army that
            # oscillates like that never fights at all.
            if len(army) < 3 or mine < self.profile.retreat_ratio * self.commit_strength or self._outmatched_at_target(world, army, mine):
                self.attacking = False
                self.regroup_until = world.time + self.profile.regroup_seconds
                self.note(world, f"withdraw at {mine:.0f} of {self.commit_strength:.0f}")
                if hall is not None:
                    home = self._front_point(world, hall)
                    for unit in army:
                        world.move([unit.id], self._muster(world, home, unit))
                return
            targets = self._attack_targets(world)
            if targets and (self.target is None or not self._still_there(world, self.target)):
                self.target = min(targets, key=lambda t: dist(t, hall.center if hall is not None else army[0].pos))
            if self.target is None:
                return
            # Reinforcements walk to the same place, so the push grows instead of
            # trickling. A soldier crossing the map alone arrives alone and dies
            # alone, so the ones still at home wait until there are enough to travel
            # together; the ones already at the front simply rejoin the fight.
            idle = [u for u in army if not u.orders]
            arrived = [u.id for u in idle if dist(u.pos, self.target) <= 12.0]
            if arrived:
                world.attack_move(arrived, self.target)
            waiting = [u for u in idle if dist(u.pos, self.target) > 12.0]
            if len(waiting) >= self.profile.reinforce_group:
                world.attack_move([u.id for u in waiting], self.target)
            elif waiting and hall is not None:
                point = self._front_point(world, hall)
                for unit in waiting:
                    if dist(unit.pos, point) > 4.0:
                        self._send_to_muster(world, point, unit)
            return
        if world.time < self.regroup_until or self._push_waits(world):
            self._gather(world, army, hall)
            return
        targets = self._attack_targets(world)
        origin = hall.center if hall is not None else (army[0].pos if army else None)
        if not targets or origin is None:
            self._gather(world, army, hall)
            return
        target = min(targets, key=lambda t: dist(t, origin))
        theirs = self._defenders_near(world, target)
        care = self._caution(world)
        owner = self._owner_of(world, target)
        blind = (world.time - self.last_seen(owner) > self.profile.stale_seconds
                 if owner is not None else not self._enemies(world))
        if blind:
            # An expedition is how a blind army gets the information needed for
            # a proper attack decision. Requiring the full FFA victory margin
            # before it has found anybody can keep it home for the entire game.
            care = 1.0 + 0.25 * (care - 1.0)
        if len(army) < self.profile.min_army * care:
            self._gather(world, army, hall)
            return
        if mine >= self.profile.attack_ratio * care * theirs:
            self.attacking = True
            self.target = target
            self.commit_strength = mine
            self.note(world, f"attack {len(army)} strong ({mine:.0f} against {theirs:.0f})")
            world.attack_move([u.id for u in army], target)
        else:
            self._gather(world, army, hall)

    def _camp_strength(self, world: World, record) -> float:
        """What a camp is reckoned to be worth: the most its guards were ever seen to be worth at once,
        and never less than :attr:`ProProfile.creep_prior` soldiers of ours.

        A camp never grows, so the high-water mark is the whole truth once it has been looked at.  Until
        then the floor is what keeps two soldiers from strolling into a troll: a brain that priced an
        unseen camp at nothing would feed the army in a few at a time, and a camp that mends its wounded
        and calls its dead back out of the den takes that for ever.
        """
        here = [u for u in world.units.values()
                if world.players[u.player].neutral and u.hp > 0 and not u.hidden
                and dist(u.pos, record.center) <= CAMP_REACH and world.is_visible(self.player, u.tile)]
        best = max(self.camp_seen.get(record.id, 0.0), strength(world, here))
        self.camp_seen[record.id] = best
        return max(best, self.profile.creep_prior * self._typical_soldier(world))

    def _creep(self, world: World, army: list[Unit]) -> bool:
        """Clear a creature camp.  True when the army has been given that job and nothing else.

        The whole army goes at once and stays until the lair is down, because the lair is both the
        payout and the thing that puts the camp back together.  A push worn past ``creep_abort`` of what
        it set out with gives up and leaves that camp alone for ``creep_retry`` seconds: trickling
        soldiers into a camp that heals and respawns is a sink with no bottom to it.
        """
        profile = self.profile
        if not profile.creep or self.attacking:
            return False
        lair = world.buildings.get(self.creeping) if self.creeping is not None else None
        if self.creeping is not None and lair is None:
            self.note(world, "camp cleared")
            self.creeping = None
        if lair is not None:
            mine = strength(world, army)
            # The patience is not a nicety: a den the army cannot reach or cannot break would otherwise hold
            # the whole army at it for the rest of the match, and reinforcements keep the strength test from
            # ever tripping.  Fuzz reports that as an army of stalled units.
            if len(army) < 3 or mine < profile.creep_abort * self.creep_strength or world.time >= self.creep_until:
                self.camp_retry[lair.id] = world.time + profile.creep_retry
                self.creeping = None
                self.regroup_until = world.time + profile.regroup_seconds
                self.note(world, f"break off the camp at {mine:.0f} of {self.creep_strength:.0f}")
                hall = self._hall(world)
                if hall is not None:
                    home = self._front_point(world, hall)
                    for unit in army:
                        world.move([unit.id], self._muster(world, home, unit))
                return True
            spot = self._standable(world, lair.center)
            idle = [u.id for u in army if not u.orders]
            if idle:
                world.attack_move(idle, spot)
            return True
        if world.time < max(profile.creep_from, self.regroup_until) or self._push_waits(world):
            return False
        hall = self._hall(world)
        origin = hall.center if hall is not None else (army[0].pos if army else None)
        if origin is None:
            return False
        here = [record for record in known_camps(world, self.player)
                if record.id in world.buildings and world.time >= self.camp_retry.get(record.id, 0.0)
                and dist(record.center, origin) <= profile.creep_reach]
        if not here:
            return False
        target = min(here, key=lambda record: dist(record.center, origin))
        mine = strength(world, army)
        theirs = self._camp_strength(world, target)
        if len(army) < profile.creep_army or mine < profile.creep_ratio * theirs:
            return False
        self.creeping = target.id
        self.creep_strength = mine
        self.creep_until = world.time + profile.creep_patience
        self.note(world, f"clear the camp with {len(army)} ({mine:.0f} against {theirs:.0f})")
        world.attack_move([u.id for u in army], self._standable(world, target.center))
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
        defenders = [e for e in self._enemies(world) if not e.is_worker and e.info.soldier and dist(e.pos, target) <= 12.0]
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
        return any(dist(record.center, point) < 3.0 for record in self._known_enemy_buildings(world))

    def _home_point(self, world: World, hall: Building) -> Point:
        """Somewhere a soldier can actually stand next to the hall.

        A hall's centre is inside its own footprint, which is blocked ground: a
        unit sent there paths towards it and stops a tile short for good. Fuzz
        caught an archer stalled twenty seconds on a move of two thirds of a
        tile, which is what that looks like from the outside.
        """
        tile = world.free_tile_near(hall.rect, prefer=hall.center)
        return tile_center(tile) if tile is not None else self._front_point(world, hall)

    def _post(self, world: World, guards: list[Unit]) -> None:
        """Send the home guard back to the hall whenever it has nothing to do, and leave it at its post once it is
        standing there (:meth:`_send_to_muster`)."""
        hall = self._hall(world)
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
        bystanders = sum(1 for p in world.players[:world.seats] if p.id != self.player and p.alive) - 1
        return 1.0 + self.profile.ffa_caution * min(max(0, bystanders), 3)

    def _army_centre(self, world: World, army: list[Unit]) -> Point | None:
        if not army:
            return None
        return (sum(u.x for u in army) / len(army), sum(u.y for u in army) / len(army))

    def _gather(self, world: World, army: list[Unit], hall: Building | None) -> None:
        """Wait in one place. An army that trickles forward is an army that loses twice."""
        if hall is None:
            return
        point = self._front_point(world, hall)
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
        return self._standable(world, (point[0] + spread * math.cos(angle), point[1] + spread * math.sin(angle)))

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
        if not world.stands_at(unit, post):
            world.move([unit.id], post)

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
            theirs = [u for u in self._enemies(world) if not u.is_worker and u.player == owner]
            counted = sum(self.remembered(owner).values())
            hidden = max(0.0, counted - len(theirs))
            seen = (strength(world, theirs) + _tower_strength(world, self.player, point)
                    + 0.5 * hidden * self._typical_soldier(world))
        else:
            # Unknown ground could hold any one opponent, not all of them at
            # once: summing every seat's army scales the pessimism with the
            # seat count and blocks every blind attack in a big game. Price
            # the strongest single opponent instead; with one opponent the
            # two are the same.
            foes = [u for u in self._enemies(world) if not u.is_worker]
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
                    counted = max(counted, sum(self.remembered(p.id).values()))
            hidden = max(0.0, counted - best_n)
            seen = best + _tower_strength(world, self.player, point) + 0.5 * hidden * self._typical_soldier(world)
        if world.time - self.last_seen(owner) > self.profile.stale_seconds:
            # An unseen opponent still has an army. Price one up to the size
            # this posture considers a viable expedition. Beyond that, tying
            # the estimate to our own growing force makes the attack condition
            # mathematically impossible for cautious FFA profiles.
            army = self._army(world)
            prior = self.profile.symmetry_prior * min(len(army), self.profile.min_army) * self._typical_soldier(world)
            seen = max(seen, prior)
        return seen

    def _owner_of(self, world: World, point: Point) -> int | None:
        """Whose ground *point* is: the player owning the nearest building to it."""
        owned = self._known_enemy_buildings(world)
        if not owned:
            return None
        return min(owned, key=lambda record: dist(record.center, point)).player

    def _typical_soldier(self, world: World) -> float:
        """What one average soldier of ours is worth, as a yardstick for unseen enemies."""
        army = [u for u in self._army(world) if u.info.soldier]
        return strength(world, army) / len(army) if army else 20.0

    def _victim(self, world: World) -> int | None:
        """Which opponent to go after: the one we believe is weakest.

        With two players this is the only opponent there is. With three or four
        it is the whole game — walking at the nearest neighbour while a third
        player grows is how a free-for-all is lost by the one who started it.
        """
        seen = {record.player for record in self._known_enemy_buildings(world)}
        living = [p.id for p in world.players[:world.seats] if p.id != self.player and p.alive and p.id in seen]
        if not living:
            return None
        return min(living, key=lambda p: sum(self.remembered(p).values()))

    def _attack_targets(self, world: World) -> list[Point]:
        """What is worth walking to: the weakest opponent's production, then anything of theirs."""
        wanted = (BuildingType.BARRACKS, BuildingType.STABLES, BuildingType.WORKSHOP,
                  BuildingType.CHURCH, BuildingType.TOWN_HALL)
        victim = self._victim(world)
        buildings = self._known_enemy_buildings(world)
        theirs = [record for record in buildings if record.player == victim] or buildings
        # A structure we have seen, we know the kind of; one razed while we were
        # not looking reads as unknown and stays a place worth walking to.
        production = [record.center for record in theirs
                      if getattr(world.buildings.get(record.id), "type", None) in wanted]
        if production:
            return production
        if theirs:
            return [record.center for record in theirs]
        seen = [u.pos for u in self._enemies(world)]
        # Under fog an army with no target simply stands at home until the clock
        # runs out. If nothing of theirs has been found, the place to go is the
        # ground we have not looked at.
        return seen or [self._unexplored_corner(world)]

    def _defend(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        """Send the soldiers at whatever is nearest our buildings. The peasants keep mining.

        Calling peasants to fight was measured twice — once only when the army
        was already winning, once whenever the army alone could not win — and
        both cost about 35 Elo against the brain that leaves them on the gold.
        They die, and the economy that would have replaced the soldiers dies
        with them.
        """
        point = min(threats, key=lambda u: min(dist(u.pos, b.center)
                                               for b in world.player_buildings(self.player))).pos
        self.attacking = False
        stale = [u.id for u in army if not isinstance(u.order, Attack) and not heading_to(u, point)]
        if stale:
            world.attack_move(stale, point)

    def _outmatched_at_home(self, world: World, army: list[Unit], threats: list[Unit]) -> bool:
        """Whether the attack on the base is more than the soldiers at home can meet (``defend_ratio``)."""
        if self.profile.defend_ratio <= 0.0:
            return False
        hall = self._hall(world)
        if hall is None:
            return False
        ours = strength(world, army) + _tower_strength_own(world, self.player, hall.center)
        return strength(world, threats) > self.profile.defend_ratio * ours

    def _fall_back(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        """Gather behind the hall, away from the attack, rather than walk into it one soldier at a time: the ones
        the barracks turns out join there, and the defence goes in together once it is a match."""
        hall = self._hall(world)
        if hall is None:
            return
        tx = sum(u.x for u in threats) / len(threats)
        ty = sum(u.y for u in threats) / len(threats)
        hx, hy = hall.center
        away = dist((hx, hy), (tx, ty)) or 1.0
        point = self._standable(world, (hx + (hx - tx) / away * 5.0, hy + (hy - ty) / away * 5.0))
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
        self.scouts = [i for i in self.scouts if i in world.units]
        if not self.scouts or not world.units[self.scouts[0]].flying:
            flyers = [u for u in self._units(world) if u.flying]
            if flyers:
                self.scouts = [flyers[0].id]  # the machine takes over from a peasant marked for want of one
            elif not self.scouts:
                spare = [p for p in self._peasants(world)
                         if not p.hidden and p.carrying is None and not isinstance(p.order, (Build, Repair, Salvage))
                         and not self._answering(p)]
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
                    self.scouts = [spare[-1].id]
        targets = [record.center for record in self._known_enemy_buildings(world)]
        if not targets:
            targets = [self._unexplored_corner(world)]  # nothing found yet: go and look
        for scout_id in self.scouts:
            scout = world.units[scout_id]
            if scout.orders or scout_id in self.hunt.party:  # a flyer on the hunt is the hunt's
                continue
            # Circle the enemy base rather than standing in it, so the sighting stays fresh; a flyer at the edge of its
            # sight, out of the reach of a tower at the middle.
            centre = min(targets, key=lambda c: dist(c, scout.pos))
            angle = (world.time / 12.0) % (2 * math.pi)
            reach = scout.info.sight - 1.0 if scout.flying else 7.0
            ring = (centre[0] + reach * math.cos(angle), centre[1] + reach * math.sin(angle))
            world.move([scout_id], self._standable(world, (min(max(ring[0], 1.0), world.width - 1.0),
                                                           min(max(ring[1], 1.0), world.height - 1.0))))

    def _home(self, world: World) -> list[tuple[int, int, int, int]]:
        """The ground a tower would take from us: our halls and the mines they work."""
        halls = self._halls(world)
        mines = [m.rect for m in known_mines(world, self.player)
                 if any(rect_gap((m.x + m.size / 2, m.y + m.size / 2), h.rect) <= 10.0 for h in halls)]
        return [h.rect for h in halls] + mines

    def _home_towers(self, world: World) -> list[Building]:
        """Enemy towers we can see, standing or going up, whose fire reaches a hall of ours or a mine it works."""
        home = self._home(world)
        towers = []
        for record in self._known_enemy_buildings(world):
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
        self.strikers = {i for i in self.strikers if i in world.units and isinstance(world.units[i].order, Attack)}
        if not self.profile.strike_seconds:
            return False
        towers = sorted(self._open_towers(world), key=lambda t: (t.hp, t.id))
        fighters = [u for u in army if u.info.soldier]
        for tower in towers:
            armour = world.armor_of(tower)
            pace = 0.0  # what the strike takes off the tower a second
            for unit in fighters:
                pace += self._blows(world, unit, armour)
            for i in self.strikers:
                striker = world.units[i]
                if isinstance(striker.order, Attack) and striker.order.target == tower.id:
                    pace += self._blows(world, striker, armour)
            spare = sorted(self._free_peasants(world, miners=True),
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
            drafted: list[int] = []
            for peasant in spare:
                if pace >= need:
                    break
                drafted.append(peasant.id)
                pace += self._blows(world, peasant, armour)
            if drafted:
                world.attack(drafted, tower.id)
                self.strikers.update(drafted)
                self.note(world, f"strike tower {tower.id}{'' if tower.done else ' frame'} with {len(drafted)} peasants "
                                 f"and {len(fighters)} soldiers")
            idle = [u.id for u in fighters if not (isinstance(u.order, Attack) and u.order.target == tower.id)]
            if idle:
                world.attack(idle, tower.id)
            return True
        return False

    def _open_towers(self, world: World) -> list[Building]:
        """The towers on our ground with no enemy soldier standing by."""
        soldiers = [e for e in self._enemies(world) if not e.is_worker and e.info.soldier]
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
        self.hunters = {i: target for i, target in self.hunters.items()
                        if i in world.units and isinstance(world.units[i].order, Attack)}
        if not self.profile.hunt_party:
            return
        home = self._home(world)
        if not home:
            return
        enemies = self._enemies(world)
        soldiers = [e for e in enemies if not e.is_worker and e.info.soldier]
        intruders = {e.id: e for e in enemies if e.is_worker and min(rect_gap(e.pos, rect) for rect in home) <= 8.0
                     and not any(dist(s.pos, e.pos) < 6.0 for s in soldiers)}
        gone = [i for i, target in self.hunters.items() if target not in intruders]
        if gone:
            world.release_workers(gone)
            for i in gone:
                del self.hunters[i]
        for prey in intruders.values():
            want = self.profile.hunt_party - sum(1 for target in self.hunters.values() if target == prey.id)
            if want <= 0:
                continue
            # A chase at the same speed never closes: the ones ahead of it, where it will be in a few seconds, meet it.
            ahead = (prey.x + 2.5 * prey.vx, prey.y + 2.5 * prey.vy)
            free = sorted((dist(p.pos, ahead), p.id) for p in self._free_peasants(world) if dist(p.pos, prey.pos) <= 12.0)
            drafted = [i for _, i in free[:want]]
            if drafted:
                world.attack(drafted, prey.id)
                for i in drafted:
                    self.hunters[i] = prey.id
                self.note(world, f"hunt peasant {prey.id} with {len(drafted)}")

    def _withdraw_if_hurt(self, world: World, unit: Unit) -> bool:
        """Walk a nearly-dead soldier out of reach. A body that lives is damage next fight.

        Returns whether the unit is out of the fight, so the caller stops
        giving it targets.
        """
        profile = self.profile
        if unit.id in self._hurt:
            if unit.hp >= profile.rejoin_hp * unit.max_hp:
                self._hurt.discard(unit.id)
                return False
            return True
        if unit.hp >= profile.retreat_hp * unit.max_hp:
            return False
        if not any(e.info.damage and dist(e.pos, unit.pos) < world.range_of(e) + 2.0 for e in self._enemies(world)):
            return False  # nothing is shooting at it; no reason to leave
        hall = self._hall(world)
        if hall is None:
            return False
        self._hurt.add(unit.id)
        world.move([unit.id], self._muster(world, self._home_point(world, hall), unit))
        return True

    def _raid(self, world: World, army: list[Unit]) -> list[int]:
        """Knights sent at the peasants. Economy damage costs the enemy the whole game,
        not just the units lost."""
        if not self.profile.raid:
            return []
        self.raiders = [i for i in self.raiders if i in world.units]
        spare = [u for u in army if u.type in RAIDERS and u.id not in self.raiders]
        while len(self.raiders) < self.profile.raiders and spare:
            self.raiders.append(spare.pop().id)
        prey = [u.pos for u in self._enemies(world) if u.is_worker]
        if not prey:
            return list(self.raiders)
        for raider_id in self.raiders:
            rider = world.units[raider_id]
            if rider.orders:
                continue
            world.attack_move([raider_id], min(prey, key=lambda p: dist(p, rider.pos)))
        return list(self.raiders)

    def _combat(self, world: World) -> None:
        """Take the nearly dead out of the fight. The fighting itself is the model's."""
        self._hunt_builders(world)
        if not self.profile.retreat_wounded:
            return
        army = [u for u in world.player_units(self.player) if not u.is_worker and u.info.soldier]
        if not army:
            return
        if not self._enemies(world):
            self._hurt.clear()
            return
        for unit in army:
            self._withdraw_if_hurt(world, unit)


class RaceBrain:
    """A player whose posture is its race's own: bred brains are bred per race, so which one plays is settled at the
    first pass, once the world says whom this player leads.  A race with several postures draws one from the map's
    seed and the player's seat, as Master draws its three."""

    def __init__(self, player: int, postures: Mapping[Race, Sequence[ProProfile]], seed: int = 0,
                 by_layout: Mapping[tuple[Race, Layout], Sequence[ProProfile]] | None = None) -> None:
        self.player = player
        self.postures = postures
        self.by_layout = by_layout or {}  # a race's postures for one kind of map, where it was bred for it; the New game screen names the map
        self.seed = seed
        self.brain: ProBrain | None = None

    @property
    def log(self) -> list[tuple[float, str]]:
        return self.brain.log if self.brain is not None else []

    def think(self, world: World, rng: random.Random) -> None:
        if self.brain is None:
            race = world.players[self.player].race
            options = self.by_layout.get((race, world.layout)) or self.postures[race]
            self.brain = ProBrain(self.player, options[(self.seed + self.player) % len(options)])
        self.brain.think(world, rng)
