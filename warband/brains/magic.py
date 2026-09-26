"""Magic in a computer player's hands (WB-067): the vaults it raises, the spell it takes at each level, and when and
where it casts.  Hard, Master and the bred postures (``pro_ai.ProBrain``) use it; Easy and Medium never touch magic.

Everything here reads what the side knows: its own units, buildings, store and cooldowns in full; of its rivals only the
units it sees now (``World.is_visible``) and the buildings it remembers (``World.worker_knowledge``, as it last saw
them); the ley rifts are public ground.  So a brain decides the same on a seat's online snapshot, where a rival's
research and aether are blanked, as on the whole world.

**The economy** (``pro_economy``'s wish list and research).  From ``ProProfile.vault_from`` seconds, once a barracks
stands, a vault goes up square on the side's own rift (:func:`own_rift`); once it stands, a Mage Tower by the hall; once
the tower stands, a second vault where it pays (:func:`second_rift`: a contested rift nearer our hall than any rival's,
which draws as well as stores).  A vault holds ``AETHER_STORE`` (150), so one casts any spell within its reach and a
level II spell beyond it too (120); a level III beyond it takes two (240).  The tower researches one spell a level, in order (:func:`spells`: the profile's
choice, or its posture's, :func:`posture_spells`).

**The casts** (:meth:`Magus.cast`, every combat pass).  Each spell the side has, off its cooldown, is judged where it
would do most (:data:`JUDGES`), and what landing there is worth is counted in bodies weighed as a siege crew weighs them
(``rules.SIEGE_WORTH``: a soldier one, an archer two, a catapult or a healer three):

| spell | cast | at |
|---|---|---|
| Haste, Stoneskin, Battle Fury | over our army once its fight is joined: :data:`JOINED` of our fighting units round it within their reach and :data:`ENGAGED` of an armed rival, or of a rival tower | the point covering most of our fighting units, one already carrying the kind counting nothing |
| Mend | over our army in a fight, joined or not, each living unit weighed by its wounds: in full once it has lost half its life, or all the mend gives | |
| Flame Strike | on rivals in sight: a clump, workers at a mine, whatever its blow takes most of the life of | the rival it takes most round |
| Meteor | the same, led by where they walk before it falls (no further than where they stop to strike), and a building by the half a siege crew gives a wall (twice for a tower); less ``FRIENDLY_WORTH`` for each of ours under it, the siege crew's own weighing (``World.friendly_cost``), every one of them in full since its rim fells a soldier | |
| Entangle | on rivals on the run from our army, or chasing ours that are | |
| Wither | on the rival soldiers of a joined fight | the point covering most of them |
| Summon | into a joined fight within a vault's reach, the base's own included | between our side of it and theirs, worth the rival soldiers there, :data:`SUMMONED_WORTH` a body it brings at most |

A cast is made when it is worth at least ``ProProfile.cast_worth`` bodies for a level I spell, times the square root of
how many times dearer its level is (so a level III spell wants twice a level I's), and ``far_worth`` times that again
beyond every vault's reach, where the aether is ``SPELL_FAR`` times as much: a near cast that would do ranks ahead of a
far one, by worth for its aether.  A full store halves the bar (drawing stops at the cap, so aether unspent is aether
lost).  A lower cast leaves what the level III spell will need once its research or cooldown is over and the vaults
cannot draw by then, but never so much that a full store could not pay for it.
Nothing is cast into nothing: every judge needs a body of ours in a fight, or a rival it sees.  Every cast asks
``World.can_cast`` first and is skipped when refused, so a refusal the brain could not foresee (online, the server's
world is not the seat's snapshot) never breaks it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Final

from warband.brains.ai import fighters, guarded, known_enemy_buildings
from warband.brains.pro_profiles import ProProfile
from warband.sim import mapgen
from warband.sim.model import Build, Building, Point, Pos, Unit, World, dist, int_sum, rect_gap
from warband.sim.rules import (AETHER_EVERY, CHOICES, FRIENDLY_WORTH, LEVEL_NAMES, SIEGE_BUILDING_WORTH, SIEGE_WORTH, SIM_DT, SPELLS,
                               UPGRADES, BuildingType, SpellInfo, Touch, Upgrade)

#: The postures' spells, a level each (``ProProfile.spell_1``..``spell_3`` overrule them one by one).  The rush and the
#: vanguard take the tempo and the blow: Haste for the rush and Flame Strike for the vanguard (both are level I, and a
#: level is one spell), Entangle to hold what runs from their push, Battle Fury; a warden holds: Mend, Stoneskin,
#: Meteor; the rest mix a blow, a hold on the rival army and a summoning.
RUSH_SPELLS: Final = (Upgrade.HASTE, Upgrade.ENTANGLE, Upgrade.BATTLE_FURY)
VANGUARD_SPELLS: Final = (Upgrade.FLAME_STRIKE, Upgrade.ENTANGLE, Upgrade.BATTLE_FURY)
WARDEN_SPELLS: Final = (Upgrade.MEND, Upgrade.STONESKIN, Upgrade.METEOR)
MIXED_SPELLS: Final = (Upgrade.FLAME_STRIKE, Upgrade.WITHER, Upgrade.SUMMON)
#: What magic raises: none of it takes a site of the build order's (``pro_economy``), one of it in flight at a time.
BUILDINGS: Final = (BuildingType.VAULT, BuildingType.MAGE_TOWER)
#: Tiles beyond its own reach an armed rival stands for a unit of ours to be in the fight.
ENGAGED: Final = 3.0
#: Tiles round a fight whose units are its two sides, when who is winning is weighed.
FIGHT: Final = 8.0
#: The share of our fighting units round a fight that must be in it before a buff is cast over it.
JOINED: Final = 0.6
#: What a summoned body is worth to a fight, in the bodies :func:`weight` counts: an elemental counts three, so the two a
#: Summon brings meet the level III bar as a Meteor's or a Battle Fury's six do (at two, it waited for a full store).
SUMMONED_WORTH: Final = 3.0
#: Tiles per second a rival must walk to be on the run or on a chase; and how near a unit of ours it has to be.
MOVING: Final = 0.3
CHASE: Final = 8.0


def posture_spells(profile: ProProfile) -> tuple[Upgrade, Upgrade, Upgrade]:
    """The spells *profile*'s posture takes: a tower rush or an early, light march the tempo, a posture that towers up,
    falls back, or waits for a big army or a big edge the hold, anything between the mix."""
    if profile.rush_towers:
        return RUSH_SPELLS
    if profile.min_army <= 6 and profile.attack_ratio < 1.0:
        return VANGUARD_SPELLS
    if profile.towers_early or profile.defend_ratio > 0.0 or profile.min_army >= 12 or profile.attack_ratio >= 1.4:
        return WARDEN_SPELLS
    return MIXED_SPELLS


def spells(profile: ProProfile) -> tuple[Upgrade, Upgrade, Upgrade]:
    """The spell *profile* researches at each level: its own choice where it makes one, else its posture's."""
    posture = posture_spells(profile)
    chosen = (profile.spell_1 or posture[0], profile.spell_2 or posture[1], profile.spell_3 or posture[2])
    for level, spell in zip(LEVEL_NAMES, chosen):
        if spell not in CHOICES[level]:
            raise ValueError(f"{profile.name}: {spell.value} is no level {level} spell")
    return chosen


def rift_centre(rift: Pos) -> Point:
    return (rift[0] + 1.0, rift[1] + 1.0)


def own_rift(world: World, player: int) -> Pos | None:
    """The side's own ley rift: the one nearest its first hall, which the map lays within eight tiles of it."""
    halls = world.player_buildings(player, BuildingType.TOWN_HALL, done=True)
    if not halls or not world.rifts:
        return None
    hall = halls[0].center
    return min(world.rifts, key=lambda rift: dist(rift_centre(rift), hall))


def taken(world: World, player: int, rift: Pos) -> bool:
    """Whether *rift* is spoken for as far as *player* knows: a building of its own there, standing, going up or ordered,
    or one of a rival's it remembers."""
    for b in world.player_buildings(player):
        if b.pos == rift:
            return True
    for unit in world.player_units(player):
        order = unit.order
        if isinstance(order, Build) and order.type is BuildingType.VAULT and order.pos == rift:
            return True
    return any((record.x, record.y) == rift for record in world.worker_knowledge[player].buildings.values()
               if record.player != player)


def second_rift(world: World, player: int) -> Pos | None:
    """Where a second vault pays: the contested rift nearest our hall of those nearer it than any rival's hall (a hall
    remembered, or where a rival not yet found must have started), with no camp guarding it and nobody's vault on it."""
    halls = world.player_buildings(player, BuildingType.TOWN_HALL, done=True)
    own = own_rift(world, player)
    if not halls or own is None:
        return None
    theirs = [record.center for record in known_enemy_buildings(world, player) if record.type is BuildingType.TOWN_HALL]
    if not theirs:
        guesses = mapgen.start_guesses(world.width, world.height, world.seats)
        home = halls[0].center
        mine = min(guesses, key=lambda point: dist(point, home))
        theirs = [point for point in guesses if point != mine]
    best: Pos | None = None
    best_away = math.inf
    for rift in world.rifts:
        if rift == own or taken(world, player, rift):
            continue
        centre = rift_centre(rift)
        away = min(dist(centre, hall.center) for hall in halls)
        if theirs and min(dist(centre, point) for point in theirs) <= away:
            continue  # nearer a rival: theirs to hold
        if guarded(world, player, centre) or away >= best_away:
            continue
        best, best_away = rift, away
    return best


def rift_site(world: World, player: int, anchor: Point, crowded: Callable[[Pos], bool]) -> Pos | None:
    """The rift under *anchor* when a vault of *player*'s can go up square on it now, and no site in flight crowds it."""
    rift = world.rift_at((int(anchor[0]), int(anchor[1])))
    if rift is None or crowded(rift) or world.can_place(BuildingType.VAULT, rift, player) is not None:
        return None
    return rift


def next_spell(world: World, player: int, profile: ProProfile) -> Upgrade | None:
    """The spell the tower is to research next: the lowest level of *profile*'s not researched yet, once what it waits
    for besides the level below is researched; None once all three are, while it waits, or while no tower of ours
    stands.  Level II waits for the Keep, which comes in the research order it always did: researched ahead of that
    order for the spell, it changed none of 500 Master matches, for by the time a level I spell is known the order has
    reached the Keep anyway (docs/balance.md, WB-067)."""
    if not world.player_buildings(player, BuildingType.MAGE_TOWER, done=True):
        return None
    known = world.players[player].upgrades
    for spell in spells(profile):
        if spell not in known:
            return spell if all(needed in known for needed in UPGRADES[spell].requires) else None
    return None


def weight(unit: Unit) -> float:
    """A body as a siege crew weighs it."""
    return SIEGE_WORTH.get(unit.type, 1.0)


class Sides:
    """What one pass of the caster sees: our fighting units, those of them in a fight, and the rivals in sight."""

    def __init__(self, world: World, player: int) -> None:
        self.army = [u for u in fighters(world.player_units(player)) if u.hp > 0 and not u.hidden]
        self.rivals = [u for u in world.units.values()
                       if u.player != player and u.player < world.seats and u.hp > 0 and not u.hidden
                       and world.players[u.player].alive and world.is_visible(player, u.tile)]
        self.armed = [u for u in self.rivals if not u.is_worker and u.info.damage]
        towers = [b for b in world.buildings.values()
                  if b.player is not None and b.player != player and b.player < world.seats and b.info.damage and b.done
                  and b.hp > 0 and not b.abandoned and world.any_visible(player, b.rect)]
        self.engaged = [u for u in self.army
                        if any(dist(u.pos, foe.pos) <= world.range_of(u) + ENGAGED for foe in self.armed)
                        or any(rect_gap(u.pos, tower.rect) <= world.range_of(u) + ENGAGED for tower in towers)]

    def fight_near(self, point: Point) -> tuple[list[Unit], list[Unit]]:
        """Our fighting units and the armed rivals within :data:`FIGHT` of *point*."""
        return ([u for u in self.army if dist(u.pos, point) <= FIGHT], [u for u in self.armed if dist(u.pos, point) <= FIGHT])


def _centre(units: list[Unit]) -> Point:
    x = y = 0.0
    for u in units:
        x += u.x
        y += u.y
    return (x / len(units), y / len(units))


def _fresh(unit: Unit, info: SpellInfo) -> bool:
    """Whether *unit* carries none of what *info* lays: a kind laid again only starts over."""
    return not any(unit.condition(kind) is not None for kind in info.lays)


Candidates = list[tuple[Point, float]]  # the points a spell could land on, and what landing on each is worth


def _buff(world: World, player: int, info: SpellInfo, sides: Sides) -> Candidates:
    """Haste, Stoneskin, Battle Fury and Mend: points over our army in a fight, each worth the units of it it covers,
    a unit Mend covers by its wounds: in full once it has lost half its life or all the mend gives."""
    mend = 0.0
    for kind in info.lays:
        if kind.hp_per_second > 0.0:
            mend += kind.hp_per_second * kind.duration
    worth: dict[int, float] = {}
    for u in sides.engaged:
        if mend:
            if not u.info.living:
                continue
            share = min(1.0, (u.max_hp - u.hp) / min(mend, u.max_hp / 2.0))
        else:
            share = 1.0 if _fresh(u, info) else 0.0
        if share > 0.0:
            worth[u.id] = weight(u) * share
    out: Candidates = []
    for centre in sides.engaged:
        if not mend and not _joined(sides, centre.pos):
            continue  # cast at first contact over the few in front, a buff had run out by the time the rest came up
        total = 0.0
        for u in sides.engaged:
            if u.id in worth and dist(centre.pos, u.pos) - u.radius <= info.radius:
                total += worth[u.id]
        if total > 0.0:
            out.append((centre.pos, total))
    return out


def _landing(world: World, info: SpellInfo, unit: Unit, gap: float) -> float:
    """What of *unit*'s life *info*'s blow takes, *gap* tiles from its edge to the point."""
    damage = world._spell_damage(info, gap)
    if not info.pierces:
        damage = max(1.0, damage - world.armor_of(unit))
    for kind in info.lays:
        if kind.hp_per_second < 0.0 and (unit.info.living or not kind.living):
            damage -= kind.hp_per_second * kind.duration
    return min(1.0, damage / max(1, unit.hp))


def _led(world: World, unit: Unit, delay: float, ours: list[Unit]) -> Point:
    """Where *unit* stands *delay* seconds from now as far as a caster can tell: where its walk carries it, but no
    further than the nearest of *ours* within its reach, where a soldier walking to a fight stops to strike (an archer
    led a full two seconds past where it halts to shoot left a Meteor's crater empty in a third of the bench's fights)."""
    speed = math.hypot(unit.vx, unit.vy)
    if not delay or speed <= 0.0:
        return unit.pos
    walk = delay
    reach = world.range_of(unit) + unit.radius
    for u in ours:
        gap = dist(unit.pos, u.pos) - u.radius - reach
        walk = min(walk, max(0.0, gap) / speed)
    return (unit.x + unit.vx * walk, unit.y + unit.vy * walk)


def _blow(world: World, player: int, info: SpellInfo, sides: Sides) -> Candidates:
    """Flame Strike and Meteor: points among the rivals in sight, each worth what of their lives its blow takes, a
    delayed blow led by where they walk and the rivals' buildings in sight weighed as a siege crew weighs a wall; a blow
    on everyone less what it would cost our own side (``World.friendly_cost``, the siege crew's weighing)."""
    targets = [u for u in sides.rivals if info.flyers or not u.flying]
    spots = [_led(world, u, info.delay, sides.army) for u in targets]
    walls: list[Building] = []
    if info.buildings and targets:
        for b in world.buildings.values():
            if (b.player is not None and b.player != player and b.player < world.seats and b.hp > 0 and not b.abandoned
                    and world.any_visible(player, b.rect)):
                walls.append(b)
    out: Candidates = []
    for spot in spots:
        point = world._clamp(spot)
        total = 0.0
        for u, at in zip(targets, spots):
            gap = dist(point, at) - u.radius
            if gap <= info.radius:
                total += weight(u) * _landing(world, info, u, gap)
        for b in walls:
            gap = rect_gap(point, b.rect)
            if gap <= info.radius:
                damage = world._spell_damage(info, gap) * info.building_factor
                wall = SIEGE_BUILDING_WORTH * (2.0 if b.info.damage and b.done else 1.0)
                total += wall * min(1.0, damage / max(1, b.hp))
        if info.touches is Touch.ALL and total > 0.0:
            # A Meteor's rim still fells a soldier, where a stone's splash only wounds one: the whole of it counts in full.
            total -= FRIENDLY_WORTH * world.friendly_cost(player, point, info.radius, info.delay, full=info.radius, air=info.flyers)
        if total > 0.0:
            out.append((point, total))
    return out


def _cover_rivals(info: SpellInfo, chosen: list[Unit]) -> Candidates:
    """Points among *chosen*, rivals *info* lays a kind on, each worth those it covers, one carrying it already
    counting nothing."""
    fresh = [u for u in chosen if (info.flyers or not u.flying) and _fresh(u, info)]
    out: Candidates = []
    for centre in fresh:
        total = 0.0
        for u in fresh:
            if dist(centre.pos, u.pos) - u.radius <= info.radius:
                total += weight(u)
        out.append((centre.pos, total))
    return out


def _entangle(world: World, player: int, info: SpellInfo, sides: Sides) -> Candidates:
    """Entangle: rivals on the run from our army (walking away from the nearest of ours), or chasing ours that are
    (walking at one of ours that walks away from them)."""
    running: list[Unit] = []
    for foe in sides.rivals:
        if foe.is_worker or math.hypot(foe.vx, foe.vy) < MOVING:
            continue
        near = [u for u in sides.army if dist(u.pos, foe.pos) <= CHASE]
        if not near:
            continue
        ours = min(near, key=lambda u: dist(u.pos, foe.pos))
        dx, dy = foe.x - ours.x, foe.y - ours.y
        away = foe.vx * dx + foe.vy * dy
        if away > 0.0 or (away < 0.0 and ours.vx * dx + ours.vy * dy < 0.0):
            running.append(foe)
    return _cover_rivals(info, running)


def _joined(sides: Sides, point: Point) -> bool:
    """Whether the fight round *point* is joined: :data:`JOINED` of our fighting units within :data:`FIGHT` of it are in
    it, as a player waits for before casting what lasts the length of a fight."""
    near = int_sum(1 for u in sides.army if dist(point, u.pos) <= FIGHT)
    joined = int_sum(1 for u in sides.engaged if dist(point, u.pos) <= FIGHT)
    return near > 0 and joined >= JOINED * near


def _wither(world: World, player: int, info: SpellInfo, sides: Sides) -> Candidates:
    """Wither: the rival soldiers of a joined fight, where it covers most of them."""
    fighting = [foe for foe in sides.armed if any(dist(foe.pos, u.pos) <= FIGHT and _joined(sides, u.pos) for u in sides.engaged)]
    return _cover_rivals(info, fighting)


def _summon(world: World, player: int, info: SpellInfo, sides: Sides) -> Candidates:
    """Summon: into a joined fight within a vault's reach, our army's or the base's own, between our side of it and
    theirs; worth the rival soldiers it is summoned against, as many as it brings bodies (an elemental two a piece)."""
    if sides.engaged:
        ours = _centre(sides.engaged)
        if not _joined(sides, ours):
            return []
    else:
        home = [b for b in world.player_buildings(player) if any(dist(b.center, foe.pos) <= FIGHT for foe in sides.armed)]
        if not home:
            return []
        ours = home[0].center
    theirs = [foe for foe in sides.armed if dist(foe.pos, ours) <= FIGHT]
    if not theirs or not world.in_reach(player, ours):
        return []
    there = _centre(theirs)
    point = world._clamp(((ours[0] + there[0]) / 2.0, (ours[1] + there[1]) / 2.0))
    worth = 0.0
    for foe in theirs:
        worth += weight(foe)
    return [(point, min(worth, SUMMONED_WORTH * info.count))]


def _judge(info: SpellInfo) -> Callable[[World, int, SpellInfo, Sides], Candidates]:
    if info.summons is not None:
        return _summon
    if info.touches is Touch.OWN:
        return _buff
    if info.damage:
        return _blow
    if any(kind.roots for kind in info.lays):
        return _entangle
    return _wither


#: Each spell's judge: the points it could land on, and what each is worth.
JUDGES: Final = {spell: _judge(info) for spell, info in SPELLS.items()}
#: A level I spell's plain price, which the bar for a cast of a dearer level is scaled from.
BASE_AETHER: Final = min(info.aether for info in SPELLS.values())


class Magus:
    """A brain's caster: one per brain, keeping what it cast for the brain's log."""

    def __init__(self, profile: ProProfile) -> None:
        self.profile = profile
        self.spells = spells(profile)
        self.casts = 0

    def reserve(self, world: World, player: int, info: SpellInfo) -> int:
        """The aether a cast of *info* must leave: for a spell below level III, what of the level III spell's price the
        vaults cannot draw again before that spell is ready (its research or its cooldown over), and never so much that
        a full store could not pay the lower cast, for drawing stops at the cap.  Kept whole, the price held a level II
        cast at 180 aether, more than one vault holds, and a level I cast at a full store, while the level III spell
        cooled for ninety seconds and the store filled anyway."""
        top = self.spells[2]
        if info.level >= 3:
            return 0
        if top in world.players[player].upgrades:
            wait = world.cooldown_left(player, top) * SIM_DT
        else:
            left = [UPGRADES[top].time - b.research_progress for b in world.player_buildings(player, BuildingType.MAGE_TOWER)
                    if b.research is top]
            if not left:
                return 0
            wait = min(left)
        drawn = int_sum(1 for b in world.vaults(player) if world.taps(b)) * wait / AETHER_EVERY
        return max(0, min(math.ceil(SPELLS[top].aether - drawn), world.aether_cap(player) - info.aether))

    def bar(self, info: SpellInfo, aether: int, full: bool) -> float:
        """The least a cast of *info* for *aether* must be worth: ``cast_worth`` for a level I spell within reach, times
        the root of how much dearer its level is, ``far_worth`` times that beyond reach, half of it on a full store."""
        bar = self.profile.cast_worth * math.sqrt(info.aether / BASE_AETHER)
        if aether > info.aether:
            bar *= self.profile.far_worth
        return bar * 0.5 if full else bar

    def cast(self, world: World, player: int) -> list[tuple[Upgrade, Point]]:
        """Cast what is worth casting now, best worth for its aether first; what was cast.  Each spell is cast at the
        point of its judge's that is worth most for its price and clears the bar (:meth:`bar`): a near cast that
        would do is taken over a far one."""
        store = world.players[player]
        ready = [spell for spell in world.spells_of(player) if not world.cooldown_left(player, spell)]
        if not ready or store.aether <= 0:
            return []
        sides = Sides(world, player)
        if not sides.rivals:
            return []
        full = store.aether >= world.aether_cap(player)
        options: list[tuple[float, Upgrade, Point]] = []
        for spell in ready:
            info = SPELLS[spell]
            best: tuple[float, Point] | None = None
            for point, worth in JUDGES[spell](world, player, info, sides):
                aether = world.cast_price(player, spell, point)[0]
                if aether > store.aether or worth < self.bar(info, aether, full):
                    continue
                if best is None or worth / aether > best[0]:
                    best = (worth / aether, point)
            if best is not None:
                options.append((best[0], spell, best[1]))
        done: list[tuple[Upgrade, Point]] = []
        for _rate, spell, point in sorted(options, key=lambda option: -option[0]):
            aether = world.cast_price(player, spell, point)[0]
            if store.aether - aether < self.reserve(world, player, SPELLS[spell]) or world.can_cast(player, spell, point) is not None:
                continue
            world.cast(player, spell, point)
            self.casts += 1
            done.append((spell, point))
        return done
