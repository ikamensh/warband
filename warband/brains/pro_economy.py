"""Economy, construction, training and research decisions for the stronger brain."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Final

from warband.brains.ai import (ARMY_PLANS, RESEARCH_ORDER, _shift, guarded, hall_first, pace, site_search, with_prerequisites)
from warband.sim import mapgen
from warband.sim.model import Build, Building, Harvest, Move, Point, Pos, Repair, Resource, Salvage, Unit, World, dist, int_sum, plain_sum, rect_gap
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, PLAYABLE_UNITS, UPGRADES, BuildingType, Cost, UnitType, Upgrade
from warband.sim.worker_knowledge import KnownMine

from warband.brains.pro_core import _ProBrainCore

_MELEE_TYPES: Final = (UnitType.FOOTMAN, UnitType.KNIGHT)
STRICT_SLACK: Final = 0.1
BUILD_MIN_DISTANCE: Final = 2
BUILD_MAX_DISTANCE: Final = 12

class _ProBrainEconomy(_ProBrainCore):
    """Turn known resources into workers, buildings, soldiers and upgrades."""

    def _worked_mines(self, world: World) -> list[KnownMine]:
        """Deposits with gold still coming out of them inside reach of one of our halls."""
        halls = self._halls(world)
        if not halls:
            return []
        return [m for m in self._known_mines(world) if m.has_gold and min(dist(m.center, h.center) for h in halls) < 14.0]

    def _worker_target(self, world: World) -> int:
        """Peasants worth having: what the mines being worked can absorb.

        Hired as fast as the halls will make them. Feeding them in gradually
        instead was measured and is simply worse — 1516 Elo against 1329 for the
        same target reached over forty seconds a worker — because the economy
        that pays for the army is the thing being delayed.
        """
        # A deposit is worth the hands its pace is worth (ai.pace: its face's gold a second over a mine's): a lode
        # seats a crew and a half, an endless seam pays a fifth of a mine's trip at twelve places, so it earns
        # three tenths of the crew.  Hiring ten peasants for a seam would be paying a mine's wages for it.
        mines = max(1.0, plain_sum(pace(m) for m in self._worked_mines(world)))
        wanted = round(mines * self.profile.workers_per_mine / (1.0 - self.profile.lumber_share))
        return min(self.profile.max_workers, wanted)

    def _economy(self, world: World) -> None:
        world.assign_workers(self.player)
        self._chop(world)
        self._prospect(world)

    def _prospect(self, world: World) -> None:
        """Send a peasant to look for gold while the mines being worked run low and no other is known.

        An expansion goes to a mine the player has seen, and a brain that does not scout has seen its own.  On
        Klondike, where home holds twenty thousand and the rest lies in a pit in the middle, the bred postures
        mined out in four minutes, never learnt of the pit, stalled at ten soldiers short of the army they wait
        for and lost to Easy: most of what Grandmaster lost to anyone.  The middle of the map first, then its
        corners, nearest first; the peasant goes back to work when a mine is found or the places run out."""
        profile = self.profile
        if profile.prospect_floor <= 0 or not profile.expand:
            return
        found = self._expansion_site(world) is not None
        low = int_sum(mine.gold for mine in self._worked_mines(world)) < profile.prospect_floor
        if self.prospector is not None and (found or not low or self.prospector not in world.units):
            if self.prospector in world.units:
                world.release_workers([self.prospector])
            self.prospector = None
        if found or not low:
            return
        hall = self._hall(world)
        if hall is None:
            return
        places = [(world.width / 2, world.height / 2)] + sorted(
            mapgen.start_guesses(world.width, world.height, world.seats, 3.5),
            key=lambda corner: dist(corner, hall.center))[1:]
        if self._prospect_leg >= 2 * len(places):
            return  # looked everywhere twice: there is nothing to find
        if self.prospector is None:
            spare = [p for p in self._free_peasants(world) if p.carrying is None and not p.hidden]
            if len(spare) < 4:
                return
            self.prospector = min(spare, key=lambda p: dist(p.pos, places[0])).id
        walker = world.units[self.prospector]
        if not isinstance(walker.order, Move):
            world.move([walker.id], self._standable(world, places[self._prospect_leg % len(places)]))
            self._prospect_leg += 1
            self.note(world, f"prospect: peasant {walker.id} looks for gold")

    @staticmethod
    def _on_lumber(peasant: Unit) -> bool:
        """Whether this peasant is working wood: a tree is a tile, a mine is an id."""
        if peasant.carrying is Resource.LUMBER:
            return True
        return any(isinstance(order, Harvest) and not isinstance(order.target, int) for order in peasant.orders)

    def _chop(self, world: World) -> None:
        """Hands follow scarcity both ways: to the trees when the wood runs out, back to the gold when it piles up.

        A fixed share of the workforce on lumber is worse than the model's own
        policy, and measured so twice: as a standing share it cost 40 to 180
        Elo depending on the share, because every hand on wood is gold not
        coming in during the minutes that decide the game. What the policy
        does not handle is the map where the wood near home is gone — lumber
        sits at zero, no farm can be built, the supply cap freezes, and a bank
        of fifteen thousand gold buys nothing at all — so the rule fires on the
        symptom rather than running all the time.

        The model's policy only ever places a peasant once, so a crew sent to the
        trees stayed there for the rest of the game: the balance league's losers
        ended with five to sixteen thousand lumber banked while gold was what they
        lacked. Above ``lumber_stock`` all but one chopper go back to the mine.
        """
        player = world.players[self.player]
        peasants = [p for p in self._peasants(world)
                    if not p.hidden and not isinstance(p.order, (Build, Repair, Salvage)) and p.id not in self.scouts
                    and not self._answering(p)]
        if player.lumber >= self.profile.lumber_stock:
            # Let go of the axe and let the model's own policy place them. Naming a
            # mine here crashed a league sixty matches in: the brain chose from the
            # player's memory, which keeps a mine nobody has looked at lately, and a
            # harvest order on ground that no longer holds one is refused.
            world.release_workers([p.id for p in peasants if self._on_lumber(p) and p.carrying is None][1:])
            return
        crew = self.profile.wood_crew if len(peasants) >= self.profile.wood_from else 0
        if self.profile.wood_lead:
            choppers = [p for p in peasants if self._on_lumber(p)]
            if self.lumber_short > 0:
                crew = max(crew, min(len(peasants) // 2, -(-self.lumber_short // self.profile.wood_per_hand)))
            elif player.lumber >= self.profile.wood_release and len(choppers) > crew:
                world.release_workers([p.id for p in choppers if p.carrying is None][:len(choppers) - crew])
                return
        if player.lumber >= self.profile.lumber_floor_panic or player.gold < self.profile.panic_gold:
            want = crew
        else:
            # Never everyone: gold still has to come in, or the next peasant never does.
            want = max(crew, min(len(peasants) // 2, max(0, len(peasants) - 2)))
        short = want - int_sum(1 for p in peasants if self._on_lumber(p))
        if short <= 0:
            return
        for peasant in [p for p in peasants if not self._on_lumber(p) and p.carrying is None][:short]:
            tree = world.nearest_tree(peasant.pos, 24)
            if tree is not None:
                world.harvest([peasant.id], tree)

    def _repairs(self, world: World) -> None:
        damaged = [b for b in world.player_buildings(self.player, done=True)
                   if b.hp < b.max_hp * 0.6 and b.info.mine is None]
        if not damaged or any(isinstance(p.order, Repair) for p in self._peasants(world)):
            return
        target = min(damaged, key=lambda b: b.hp / b.max_hp)
        if world._nearest_enemy(self.player, target.center, 8.0, air=False) is not None:  # a flyer overhead does not stop the hammer
            return
        spare = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, Build)
                 and not self._answering(p)]
        if spare:
            world.repair([min(spare, key=lambda p: dist(p.pos, target.center)).id], target.id)

    def _wish_list(self, world: World) -> list[tuple[BuildingType, Point]]:
        """What to put up next, best first. Nothing here waits on a round number of gold."""
        player = self.player
        profile = self.profile
        halls = self._halls(world)
        hall = halls[0] if halls else None
        peasants = self._peasants(world)
        fallback = peasants[0].pos if peasants else (world.width / 2, world.height / 2)
        if hall is None:
            mines = self._known_mines(world)
            nearest = min(mines, key=lambda m: dist(m.center, fallback)) if mines else None
            return [(BuildingType.TOWN_HALL, nearest.center if nearest is not None else fallback)]

        have = lambda t: len(world.player_buildings(player, t, done=True))  # noqa: E731
        # A building that has been ordered does not exist until the peasant walks
        # to the site and pays for it, so the orders in flight have to be counted
        # too — otherwise the same barracks is wished for again on the next pass.
        going_up = ([b.type for b in world.player_buildings(player) if not b.done]
                    + [order.type for order in self._ordered(world)])
        count = lambda t: have(t) + going_up.count(t)  # noqa: E731
        anchor = hall.center
        wishes: list[tuple[BuildingType, Point]] = []

        used, cap = world.supply(player)
        producers = int_sum(count(t) for t in (BuildingType.BARRACKS, BuildingType.STABLES,
                                               BuildingType.WORKSHOP, BuildingType.CHURCH))
        headroom = profile.supply_slack + int(profile.supply_per_producer * producers)
        farms_coming = going_up.count(BuildingType.FARM) + going_up.count(BuildingType.TOWN_HALL)
        if cap - used + 4 * farms_coming < headroom:
            wishes.append((BuildingType.FARM, anchor))
        self._opening_next = None
        listed: dict[BuildingType, int] = {}
        # An opening counts each building once. ``count`` sees a site twice while it goes up, as the building and as
        # its builder's order, which the knobs above were tuned with; a list that names the second barracks cannot
        # take the first one's frame for it.
        begun = [b.type for b in world.player_buildings(player) if not b.done] + [o.type for o in self._ordered(world) if o.building is None]
        for step in profile.opening:
            listed[step] = listed.get(step, 0) + 1
            needs = BUILDINGS[step].requires
            if have(step) + begun.count(step) >= listed[step] or (needs is not None and not have(needs)):
                continue  # up already, or waiting for what it needs: the next of the opening goes up meanwhile
            where = self._front_point(world, hall) if step is BuildingType.TOWER else anchor
            if step is BuildingType.TOWN_HALL:
                site = self._expansion_site(world)
                if site is None:
                    continue
                where = site
            # One at a time, in order, and nothing else but farms: an opening is a plan, and the cheaper building
            # further down the list is what the bank would otherwise buy first.
            self._opening_next = step
            wishes.append((step, where))
            return wishes
        if count(BuildingType.BARRACKS) < 1:
            wishes.append((BuildingType.BARRACKS, anchor))
            # The mill sits behind the barracks here and costs a hundred gold
            # less, so whenever the bank is between the two it is the mill that
            # gets bought — and its 450 lumber is the barracks' 450 lumber, a
            # minute of chopping later. Both brains in a mirror trace had their
            # first barracks at three minutes for exactly this reason.
            if profile.barracks_first:
                return wishes
        if count(BuildingType.TOWER) < profile.towers_early:
            # A tower is two footmen's worth of fight for less than one footman's
            # gold, for as long as the enemy comes to it — and Master comes to it.
            wishes.append((BuildingType.TOWER, self._front_point(world, hall)))
        if count(BuildingType.LUMBER_MILL) < 1:
            # Beside the hall, where the site search puts it. Siting it at the
            # edge of the nearest wood measured level (52–56% against Master,
            # where barracks-first alone took 59%): the wood is six tiles from
            # every start, and a second mill at the wood front no better.
            wishes.append((BuildingType.LUMBER_MILL, anchor))
        # A posture built around one branch of the tree — knights, siege, healers —
        # cannot wait for the bank to overflow before it is allowed that branch.
        for tech in set(profile.early_tech):
            needs = BUILDINGS[tech].requires
            if count(tech) < profile.early_tech.count(tech) and (needs is None or have(needs)):
                wishes.append((tech, anchor))
        # Everything past here is optional, and optional buildings are what lose games:
        # each one is an army that was not trained. They are unlocked only once the
        # production already standing cannot keep up with the money coming in.
        expansion = self._expansion_site(world) if profile.expand else None
        room_for_a_hall = expansion is not None and count(BuildingType.TOWN_HALL) < profile.max_halls
        if expansion is not None and room_for_a_hall and (profile.expand_early or self._mines_failing(world)):
            # Scarcity opens this gate as well as plenty. A brain whose mines are
            # spent or full has no income to saturate its production with, so
            # waiting for saturation meant never expanding at all: the dry-mine
            # league saw no second hall in 336 seats. A hall takes a minute to
            # build and a peasant longer to walk, so the move starts while the
            # old mine still has gold in it.
            wishes.append((BuildingType.TOWN_HALL, expansion))
        if not self._producers_saturated(world):
            return wishes
        if expansion is not None and room_for_a_hall and not profile.expand_early:
            wishes.append((BuildingType.TOWN_HALL, expansion))
        if count(BuildingType.BLACKSMITH) < 1:
            wishes.append((BuildingType.BLACKSMITH, anchor))
        # Production capacity is what the bank is short of, not money. A barracks
        # turns out about four soldiers a minute; gold piling up past that is an
        # army that does not exist. Tie the target to what is actually unspent.
        barracks_target = min(profile.max_producers,
                              max(profile.barracks_per_hall * max(1, len(halls)),
                                  1 + world.players[player].gold // profile.gold_per_barracks))
        if count(BuildingType.BARRACKS) < barracks_target:
            wishes.append((BuildingType.BARRACKS, anchor))
        if count(BuildingType.STABLES) < 1:
            wishes.append((BuildingType.STABLES, anchor))
        if profile.siege and have(BuildingType.BLACKSMITH) and count(BuildingType.WORKSHOP) < 1:
            wishes.append((BuildingType.WORKSHOP, anchor))
        if profile.clerics and count(BuildingType.CHURCH) < 1:
            wishes.append((BuildingType.CHURCH, anchor))
        if count(BuildingType.TOWER) < profile.tower_count and len(self._army(world)) >= 4:
            wishes.append((BuildingType.TOWER, self._front_point(world, hall)))
        return wishes

    def _mines_failing(self, world: World) -> bool:
        """Whether the mines being worked can no longer grow this economy: spent, or every place at the face taken."""
        mines = self._worked_mines(world)
        if not mines:
            return True
        # A seam brings up no stock at all, so it counts for nothing here on purpose: an economy that
        # rests on one is exactly an economy that has to go and find another mine.
        if int_sum(mine.gold for mine in mines) < self.profile.mine_floor * len(mines):
            return True
        miners = int_sum(1 for p in self._peasants(world)
                         if p.inside is not None or any(isinstance(o, Harvest) and isinstance(o.target, int) for o in p.orders))
        return miners >= int_sum(mine.slots for mine in mines)

    def _producers_saturated(self, world: World) -> bool:
        """Whether the buildings already standing are the bottleneck rather than the bank.

        A barracks that is always mid-queue is worth another barracks; one that
        idles for want of gold is not, and neither is a stables next to it.
        """
        producers = [b for b in world.player_buildings(self.player, done=True)
                     if b.info.trains and b.type is not BuildingType.TOWN_HALL]
        if not producers:
            return False
        if any(not b.queue and b.research is None for b in producers):
            return False
        player = world.players[self.player]
        return player.gold >= self.profile.surplus_gold

    def _expansion_site(self, world: World) -> Point | None:
        """An unclaimed deposit still giving gold, nearest to home for what it pays; a seam only once no mine will do.

        A lode pays half as fast again as a mine and is taken over one that is not two thirds of its walk; a seam
        pays a fifth of a mine's trip and never runs out, so it is the expansion to take when the mines are drunk
        or claimed, not the one to take first (:func:`~warband.brains.ai.hall_first`)."""
        halls = self._halls(world)
        if not halls:
            return None
        claimed = [h.center for h in world.player_buildings(self.player, BuildingType.TOWN_HALL)]
        best, best_rank = None, (True, math.inf)
        for mine in self._known_mines(world):
            if not mine.has_gold or min(dist(mine.center, c) for c in claimed) < 12.0:
                continue
            if guarded(world, self.player, mine.center):
                continue  # a deposit with a live camp beside it is not an expansion; clear it first
            away = min(dist(mine.center, h.center) for h in halls)
            enemy_halls = [r.center for r in self._known_enemy_buildings(world)]
            if enemy_halls and min(dist(mine.center, c) for c in enemy_halls) < away:
                continue  # not ours to take yet
            rank = hall_first(mine, away)
            if rank < best_rank:
                best, best_rank = mine.center, rank
        return best

    def _ordered(self, world: World) -> list[Build]:
        """The build orders already given and not yet begun.

        ``World.build`` only hands a peasant an order: the building appears, and
        is paid for, when that peasant arrives. Between the two it is invisible
        to ``player_buildings``, and a brain that does not remember giving the
        order re-gives it every pass — which sends peasant after peasant off the
        gold to start the same barracks in four different places.
        """
        return [p.order for p in self._peasants(world) if isinstance(p.order, Build)]

    def _shortfall(self, world: World, wishes: Sequence[tuple[BuildingType, Point]]) -> int:
        """The lumber the wished-for buildings lack while the gold for them is in the bank, the list walked in order
        with what is left: the symptom of a bank of three thousand gold that buys nothing because every barracks
        and farm on the list wants wood the brain is not chopping."""
        gold, lumber = self._spendable(world)
        lumber -= self.profile.lumber_floor
        short = 0
        for wanted, _anchor in wishes:
            cost = BUILDINGS[wanted].cost
            if gold < cost.gold:
                break  # gold binds from here on: more wood would buy nothing
            gold -= cost.gold
            if lumber < cost.lumber:
                short += cost.lumber - max(0, lumber)
            lumber -= cost.lumber
        return short

    def _construction(self, world: World, rng: random.Random) -> None:
        wishes = self._wish_list(world)
        if self.profile.wood_lead:
            self.lumber_short = self._shortfall(world, wishes)
        sites = [b for b in world.player_buildings(self.player) if not b.done]
        free = self.profile.max_sites - len(sites) - len(self._ordered(world))
        if free <= 0:
            return
        builders = [p for p in self._peasants(world)
                    if not p.hidden and not isinstance(p.order, (Build, Repair, Salvage)) and not self._answering(p)]
        if not builders:
            return
        # Ground already spoken for by an order in flight: can_place cannot know
        # about it, so two buildings would otherwise be sent to the same tile.
        taken = [(o.pos, BUILDINGS[o.type].size) for o in self._ordered(world)]
        for wanted, anchor in wishes:
            if free <= 0 or not builders:
                break
            cost = BUILDINGS[wanted].cost
            if world.can_afford(self.player, cost) is not None or not self._payable(world, cost):
                continue
            if self._spendable(world)[1] - cost.lumber < self.profile.lumber_floor and wanted is not self._opening_next:
                continue
            site = self._site(world, wanted, anchor, rng, taken)
            if site is None:
                continue
            builder = min(builders, key=lambda p: dist(p.pos, (site[0] + 1.0, site[1] + 1.0)))
            world.build(builder.id, wanted, site)
            taken.append((site, BUILDINGS[wanted].size))
            builders.remove(builder)
            free -= 1
            self.note(world, f"build {wanted.value} at {site}")

    def _site(self, world: World, building_type: BuildingType, anchor: Point, rng: random.Random,
              taken: Sequence[tuple[Pos, int]] = ()) -> Pos | None:
        return site_search(world, building_type, self.player, anchor, rng, BUILD_MIN_DISTANCE, BUILD_MAX_DISTANCE, taken)

    def _held(self, world: World) -> tuple[int, int]:
        """What orders in flight will pay on arrival: every build order not begun yet, and a rush tower whose
        builder is still walking to its site. A build order is paid at the site, and a bank spent during the
        walk drops it there: a quarter of Master's orders died so before this held them (WB-043)."""
        gold = lumber = 0
        for peasant in self._peasants(world):
            order = peasant.order
            if isinstance(order, Build) and order.building is None and (self.profile.hold_builds or peasant.id in self.rushers):
                cost = BUILDINGS[order.type].cost
                gold, lumber = gold + cost.gold, lumber + cost.lumber
            elif peasant.id in self.rushers and peasant.constructing is None and not isinstance(order, Build):
                cost = BUILDINGS[BuildingType.TOWER].cost
                gold, lumber = gold + cost.gold, lumber + cost.lumber
        for saved in self._saving_for(world):
            gold, lumber = gold + saved.gold, lumber + saved.lumber
        return (gold, lumber)

    def _research_order(self) -> tuple[Upgrade, ...]:
        return self.profile.research_order if self.profile.research_order is not None else RESEARCH_ORDER

    def _saving_for(self, world: World) -> list[Cost]:
        """The prices held for what the posture buys ahead of soldiers: the next building of its opening.  The
        purchase itself is paid out of what was held for it."""
        saved = []
        if self.profile.opening_hold and self._opening_next is not None:
            saved.append(BUILDINGS[self._opening_next].cost)
        return saved

    def _payable(self, world: World, cost: Cost) -> bool:
        """Whether *cost* can be paid now: one of the prices being saved for out of the whole bank but for the other
        holds, anything else out of what is left."""
        if not any(cost is saved for saved in self._saving_for(world)):
            return self._affordable(world, cost)
        gold, lumber = self._spendable(world)
        return gold >= 0 and lumber >= 0  # what is left once every hold is counted, its own among them

    def _spendable(self, world: World) -> tuple[int, int]:
        bank, (gold, lumber) = world.players[self.player], self._held(world)
        return (bank.gold - gold, bank.lumber - lumber)

    def _affordable(self, world: World, cost: Cost) -> bool:
        gold, lumber = self._spendable(world)
        return gold >= cost.gold and lumber >= cost.lumber

    def _enemy_mine_guess(self, world: World) -> Point | None:
        """Where the one opponent's main mine must be: a two-seat map is the point reflection of itself
        through the centre, so it is the reflection of our own main mine."""
        hall = self._hall(world)
        mines = self._known_mines(world)
        if hall is None or not mines or world.seats != 2:
            return None
        ours = min(mines, key=lambda m: dist((m.x + m.size / 2, m.y + m.size / 2), hall.center))
        return (world.width - (ours.x + ours.size / 2), world.height - (ours.y + ours.size / 2))

    def _rush_mine(self, world: World, guess: Point) -> KnownMine | None:
        """The enemy's main mine, once seen."""
        seen = [m for m in self._known_mines(world) if dist((m.x + m.size / 2, m.y + m.size / 2), guess) < 3]
        return seen[0] if seen else None

    def _enemy_start(self, world: World) -> Point | None:
        """Where the one opponent started: the point reflection of our own start through the centre."""
        hall = self._hall(world)
        if hall is None or world.seats != 2:
            return None
        return (world.width - hall.center[0], world.height - hall.center[1])

    def _behind(self, mine: Point, start: Point, reach: float) -> Point:
        """*reach* tiles beyond *mine* seen from *start*: the side their gatherers do not walk."""
        away = (mine[0] - start[0], mine[1] - start[1])
        length = math.hypot(*away) or 1.0
        return (mine[0] + away[0] / length * reach, mine[1] + away[1] / length * reach)

    def _rush_site(self, world: World, mine: KnownMine, start: Point) -> Pos | None:
        """A tower site 1.5 to 3 tiles from the enemy's mine, as far round it from their hall as there is."""
        size = BUILDINGS[BuildingType.TOWER].size
        best: tuple[float, Pos] | None = None
        for y in range(mine.y - 6, mine.y + mine.size + 6):
            for x in range(mine.x - 6, mine.x + mine.size + 6):
                centre = (x + size / 2, y + size / 2)
                gap = rect_gap(centre, mine.rect) - size / 2
                if not 1.5 <= gap <= 3.0 or world.can_place(BuildingType.TOWER, (x, y), self.player) is not None:
                    continue
                score = dist(centre, start)
                if best is None or score > best[0]:
                    best = (score, (x, y))
        return None if best is None else best[1]

    def _tower_rush(self, world: World) -> None:
        """Towers beside the enemy's main mine, raised by a peasant who walks to where they must have started.

        A tower needs a barracks, so the walk starts when one stands. The peasant is kept off the
        gatherer policy (holding while it waits), and the tower's price is held from everything the
        brain buys until the peasant has paid it on arrival."""
        profile = self.profile
        if profile.rush_towers <= 0 or self.rush_over:
            return
        start, guess = self._enemy_start(world), self._enemy_mine_guess(world)
        # The walk takes most of a minute, so it starts as the barracks goes up; the tower is ordered when it stands.
        if start is None or guess is None or not world.player_buildings(self.player, BuildingType.BARRACKS):
            return
        barracks = bool(world.player_buildings(self.player, BuildingType.BARRACKS, done=True))
        mine = self._rush_mine(world, guess)
        if mine is not None and int_sum(1 for b in world.player_buildings(self.player, BuildingType.TOWER)
                                        if rect_gap(b.center, mine.rect) <= 4.5) >= profile.rush_towers:
            self._end_rush(world)
            return
        self.rushers = [i for i in self.rushers if i in world.units]
        while len(self.rushers) < profile.rush_builders and self.rush_drafted < profile.rush_tries:
            spare = [p for p in self._peasants(world) if not p.hidden and p.id not in self.rushers
                     and not isinstance(p.order, (Build, Repair, Salvage)) and p.constructing is None and not self._answering(p)]
            if not spare:
                break
            drafted = min(spare, key=lambda p: dist(p.pos, start))
            self.rushers.append(drafted.id)
            self.rush_drafted += 1
            self.note(world, f"rush: drafted peasant {drafted.id}")
        if not self.rushers:
            if self.rush_drafted >= profile.rush_tries:
                self._end_rush(world)  # every try spent and none of them left alive
            return  # nobody to spare this tick (all of them building, mending or answering a raid): look again next one
        post = self._standable(world, self._behind(guess, start, 4.0))
        for rusher in [world.units[i] for i in self.rushers]:
            if rusher.constructing is not None or isinstance(rusher.order, Build):
                continue
            site = self._rush_site(world, mine, start) if mine is not None and barracks else None
            if site is not None and world.can_afford(self.player, BUILDINGS[BuildingType.TOWER].cost) is None:
                world.build(rusher.id, BuildingType.TOWER, site)
                self.note(world, f"rush: tower at {site}")
            elif dist(rusher.pos, post) > 1.5:
                if not rusher.orders or rusher.path_goal is None:
                    world.move([rusher.id], post)
            else:
                world.hold([rusher.id])  # there, and waiting: off the gatherer policy

    def _end_rush(self, world: World) -> None:
        """The rush is done or given up: its builders go back to work and its price is no longer held."""
        self.rush_over = True
        self.rushers = []
        self.note(world, "rush: over")

    def _training(self, world: World) -> None:
        player = self.player
        army = self._army(world)
        halls = self._halls(world)
        # Peasants come first only while there is something to defend them with.
        # Raiders killing workers is exactly the moment the hall wants to replace
        # them, and replacing them is what pays for the soldiers that would stop
        # the raid — bases have been lost at sixteen workers, four thousand gold
        # and no army at all.
        rebuilding = (len(army) < self.profile.soldiers_before_workers
                      and any(b.info.trains and b.type is not BuildingType.TOWN_HALL
                              for b in world.player_buildings(player, done=True)))
        if not rebuilding:
            target = self._worker_target(world)
            peasants = len(self._peasants(world))
            for hall in halls:
                if peasants + int_sum(len(h.queue) for h in halls) >= target:
                    break
                if len(hall.queue) < 2 and world.can_train(hall, UnitType.PEASANT) is None and self._affordable(world, world.unit_info(player, UnitType.PEASANT).cost):
                    world.train(hall.id, UnitType.PEASANT)
        counts = {t: int_sum(1 for u in army if u.type is t) for t in PLAYABLE_UNITS}
        # The eyes are no share of the army: the one flying machine a scouting posture keeps is counted apart, those in
        # training with it, or a workshop would start another while the first is still on the stocks.
        counts[UnitType.FLYING_MACHINE] = (int_sum(1 for u in self._units(world) if u.type is UnitType.FLYING_MACHINE)
                                           + int_sum(b.queue.count(UnitType.FLYING_MACHINE) for b in world.player_buildings(player)))
        targets = self._army_targets(world)
        wishes: list[tuple[float, UnitType, Building]] = []
        for building in world.player_buildings(player, done=True):
            if not building.info.trains or building.type is BuildingType.TOWN_HALL:
                continue
            if building.rally is None and halls:
                world.set_rally(building.id, self._front_point(world, halls[0]))
            if building.research is not None or len(building.queue) >= 2:
                continue
            wish = self._choose_unit(building, counts, targets)
            if wish is not None:
                wishes.append((*wish, building))
        # The unit the army is shortest of has first claim on the bank. Buying
        # whatever was affordable at the moment instead had the stables turn out
        # a scout rider every time the knight it wanted was a few hundred gold away:
        # fifteen scouts to eight knights, in a posture that asked for knights.
        gold, lumber = self._spendable(world)
        for _gap, choice, building in sorted(wishes, key=lambda w: -w[0]):
            cost = world.unit_info(player, choice).cost
            if gold >= cost.gold and lumber >= cost.lumber and world.can_train(building, choice) is None:
                world.train(building.id, choice)
                counts[choice] = counts.get(choice, 0) + 1
            elif not self.profile.save_for_wanted:
                continue
            gold -= cost.gold
            lumber -= cost.lumber

    def _army_targets(self, world: World) -> dict[UnitType, float]:
        """Shares of the army to aim for, shifted towards counters of what the enemy is remembered fielding."""
        plan = dict(self.profile.army_plan or ARMY_PLANS[world.players[self.player].race])
        if not self.profile.siege:
            plan.pop(UnitType.CATAPULT, None)
        if not self.profile.clerics:
            plan.pop(UnitType.CLERIC, None)
        # A catapult out-ranges everything in the game and hits buildings for half
        # again; a healer makes every other soldier last longer. Both are worth
        # more to an army that has to break into a defended base than the race's
        # own plan allows, so the profile can overrule it.
        for unit_type, share in ((UnitType.CATAPULT, self.profile.siege_share),
                                 (UnitType.CLERIC, self.profile.cleric_share)):
            if share > 0 and unit_type in plan:
                rest = plain_sum(v for t, v in plan.items() if t is not unit_type) or 1.0
                plan = {t: (share if t is unit_type else v * (1.0 - share) / rest) for t, v in plan.items()}
        total = plain_sum(plan.values())
        if total > 0:
            plan = {t: share / total for t, share in plan.items()}
        seen = self.remembered()
        archers = seen.get(UnitType.ARCHER, 0.0)
        knights = seen.get(UnitType.KNIGHT, 0.0)
        melee = plain_sum(seen.get(t, 0.0) for t in _MELEE_TYPES)
        total = archers + melee
        # Answer shooters with whatever closes the distance, in proportion to how
        # many of them there are. The old rule only fired when archers outnumbered
        # everything else two to one, which no race on this map ever fields — so
        # against the Elves, who are half archers and the matchup this brain loses
        # most, it never fired at all.
        if total > 0:
            excess = archers / total - self.profile.counter_from
            if excess > 0:
                swing = min(0.3, excess * self.profile.counter_strength)
                _shift(plan, {UnitType.FOOTMAN: -swing, UnitType.KNIGHT: swing})
        if knights >= 3:
            _shift(plan, {UnitType.KNIGHT: -0.15, UnitType.FOOTMAN: 0.075, UnitType.ARCHER: 0.075})
        return plan

    def _choose_unit(self, building: Building, counts: dict[UnitType, int],
                     targets: dict[UnitType, float]) -> tuple[float, UnitType] | None:
        """What *building* should train next and how short of it the army is: ``(gap, unit)``, affordable or not.
        A scouting posture's workshop makes its one flying machine before anything else."""
        if building.type is BuildingType.WORKSHOP and self.profile.scout and counts.get(UnitType.FLYING_MACHINE, 0) < 1:
            return math.inf, UnitType.FLYING_MACHINE
        soldiers = int_sum(n for t, n in counts.items() if t is not UnitType.FLYING_MACHINE)
        best: tuple[float, UnitType] | None = None
        for unit_type in targets:
            if unit_type not in building.info.trains:
                continue
            share = counts.get(unit_type, 0) / soldiers if soldiers else 0.0
            gap = targets[unit_type] - share
            if self.profile.strict_plan and gap < -STRICT_SLACK:
                continue
            if best is None or gap > best[0]:
                best = (gap, unit_type)
        return best

    def _research(self, world: World) -> None:
        if not self.profile.research:
            return
        player = world.players[self.player]
        buildings = world.player_buildings(self.player, done=True)  # nothing changes until the one order below
        for wanted in self._research_order():
            if wanted in player.upgrades or not RACES[player.race].upgrade_allowed(wanted):
                continue
            for upgrade in with_prerequisites(player.upgrades, wanted):
                cost = UPGRADES[upgrade].cost
                for building in buildings:
                    if upgrade in building.info.researches and world.can_research(building, upgrade) is None and self._payable(world, cost):
                        world.research(building.id, upgrade)
                        return
