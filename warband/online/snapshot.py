"""What each audience of an online match may know, built field by field.

The seam is narrow: :func:`seat_world` for one seat and :func:`observer_world`
for a watcher each return a world record that :meth:`World.from_dict` decodes,
in the wire shape a save uses.  Every record below names the fields its audience
is permitted, read straight off the live objects; nothing here serializes the
saved world, so a field the save grows later has no record to ride in on until a
constructor here names it for an audience on purpose.  The authority keeps the
match itself — orders, events and the checkpoint (which *is* the save) — and
asks this module only for the knowledge projection it sends.
"""
import random

from warband.sim.model import Attack, AttackMove, Build, Deposit, Harvest, Heal, Hold, Move, Patrol, Repair, Salvage
from warband.sim.rules import BLOODLUST_RAGE, RAGE

#: What a seat is told of the server's random stream: a fixed state, so no client can read the damage rolls to come.
NO_DICE = random.Random(0).getstate()
#: The conditions a stranger's unit is shown carrying under another kind's name until the match is decided: a kind of
#: its own would tell its owner's research.  Rage under Bloodlust is Rage; a new kind like it gets a row here.
_KINDS_AS_STRANGERS_SEE_THEM = {BLOODLUST_RAGE.key: RAGE.key}


def terrain_rows(world):
    """The map's rows as letters, one string per row: the ground as it stands."""
    return ["".join(tile.value[0] for tile in row) for row in world.terrain]


def _point(point):
    return list(point) if point is not None else None


# -- Orders: a seat's own units carry theirs, in the save's spelling -----------------


def _order_record(order):
    """One order of a seat's own unit.  Harvest and Deposit carry their automatic routing beside the queue
    (:func:`_worker_order_records`), so here they name only what the queue itself says."""
    if isinstance(order, Harvest):
        return {"kind": "Harvest", "target": list(order.target) if isinstance(order.target, tuple) else order.target}
    if isinstance(order, Deposit):
        return {"kind": "Deposit"}
    if isinstance(order, Move):
        return {"kind": "Move", "target": list(order.target), "pace": order.pace, "offset": _point(order.offset)}
    if isinstance(order, AttackMove):
        return {"kind": "AttackMove", "target": list(order.target), "pace": order.pace, "offset": _point(order.offset)}
    if isinstance(order, Attack):
        return {"kind": "Attack", "target": order.target, "auto": order.auto}
    if isinstance(order, Build):
        record = {"kind": "Build", "type": order.type.value, "pos": list(order.pos), "building": order.building}
        if order.plan_if_short:  # only a player's own placements carry it
            record["plan_if_short"] = order.plan_if_short
        return record
    if isinstance(order, Hold):
        return {"kind": "Hold", "target": order.target}
    if isinstance(order, Heal):
        return {"kind": "Heal", "target": order.target, "auto": order.auto}
    if isinstance(order, Patrol):
        return {"kind": "Patrol", "start": list(order.start), "end": list(order.end), "outbound": order.outbound}
    if isinstance(order, Repair):
        return {"kind": "Repair", "target": order.target}
    if isinstance(order, Salvage):
        return {"kind": "Salvage", "target": order.target, "auto": order.auto}
    raise TypeError(f"no snapshot spelling for order {order!r}")


def _worker_order_records(unit):
    """The harvest/deposit routing that rides beside a seat's own unit's queue."""
    records = []
    for index, order in enumerate(unit.orders):
        if isinstance(order, Deposit):
            records.append({"index": index, "auto": order.auto, "target": order.target})
        elif isinstance(order, Harvest):
            records.append({"index": index, "auto": order.auto, "placed": order.placed})
    return records


# -- Units: one shared body of facts, three audiences' intentions --------------------


def _condition_records(unit, kinds):
    return [{"kind": kinds.get(condition.kind.key, condition.kind.key), "until": condition.until,
             "player": condition.player, "worn": condition.worn} for condition in unit.conditions]


def _unit_record(unit, *, orders, worker_orders, home, constructing, auto_work, commanded, conditions):
    """A unit as it stands and strikes: the facts every audience that may see it at all is told.  What it
    intends — orders, home, who held it lately — each audience's constructor supplies or withholds."""
    return {
        "id": unit.id, "type": unit.type.value, "player": unit.player, "x": unit.x, "y": unit.y, "hp": unit.hp,
        "facing": unit.facing, "orders": orders, "cooldown": unit.cooldown, "windup": unit.windup,
        "vx": unit.vx, "vy": unit.vy, "worker_orders": worker_orders,
        "carrying": unit.carrying.value if unit.carrying else None, "carry": unit.carry, "timer": unit.timer,
        "inside": unit.inside, "constructing": constructing, "home": home, "state": unit.state,
        "ease": _point(unit.ease), "charge": unit.charge, "auto_work": auto_work,
        "commanded": commanded, "struck": unit.struck, "conditions": conditions,
        "expires": unit.expires, "slam_point": _point(unit.slam_point),
    }


def _own_unit_record(unit):
    """All of a seat's own unit, its orders and routing included."""
    return _unit_record(unit, orders=[_order_record(order) for order in unit.orders],
                        worker_orders=_worker_order_records(unit),
                        home=list(unit.home) if unit.home else None, constructing=unit.constructing,
                        auto_work=unit.auto_work, commanded=unit.commanded,
                        conditions=_condition_records(unit, {}))


def _stranger_unit_record(unit, undecided):
    """A unit a seat sees and does not own: where it stands and how it moves and strikes, not where it is
    going nor how lately its owner had it in hand — no orders, worker routing, home, site or *commanded*.
    While the match is *undecided* its conditions go under the names a stranger may know them by, so Rage
    under Bloodlust does not tell its owner's research."""
    return _unit_record(unit, orders=[], worker_orders=[], home=None, constructing=None,
                        auto_work=False, commanded=None,
                        conditions=_condition_records(unit, _KINDS_AS_STRANGERS_SEE_THEM if undecided else {}))


def _observed_unit_record(unit):
    """A unit as a watcher sees it: no intentions either, but a builder's site names it already, so its post
    stays — stripping it would stand the builder back on the map where the authority has it inside."""
    return _unit_record(unit, orders=[], worker_orders=[], home=None, constructing=unit.constructing,
                        auto_work=False, commanded=None, conditions=_condition_records(unit, {}))


# -- Buildings, players, shots, camps, plans, memory --------------------------------


def _building_record(building, *, work, gold):
    """A building's footprint, hit points, construction and abandonment; its *work* — what it trains,
    researches and rallies to — only for an audience that may know it, and *gold* as that audience last saw it."""
    return {
        "id": building.id, "type": building.type.value, "player": building.player, "x": building.x, "y": building.y,
        "hp": building.hp, "max_hp": building.max_hp, "progress": building.progress,
        "queue": [kind.value for kind in building.queue] if work else [],
        "train_progress": building.train_progress if work else 0.0,
        "rally": _point(building.rally) if work else None,
        "gold": gold, "builder": building.builder, "cooldown": building.cooldown,
        "research": building.research.value if work and building.research else None,
        "research_progress": building.research_progress if work else 0.0,
        "abandoned": building.abandoned,
        "auto": [kind.value for kind in building.auto] if work else [],
    }


def _full_building_record(building):
    return _building_record(building, work=True, gold=building.gold)


def _stranger_building_record(building):
    """A building a seat sees and does not own: footprint, hit points, construction and abandonment, not its
    work — no queue, training, rally, research or endless training.  A site keeps its builder's id (the
    builder itself is inside, out of sight): a site with none is one from a save older than WB-048, and a
    load removes it."""
    return _building_record(building, work=False, gold=building.gold)


def _remembered_mine_record(building, gold):
    """A mine out of sight, as the seat last saw it: the deposit whole, its stock as remembered."""
    return _building_record(building, work=True, gold=gold)


def _player_record(player, *, revealed):
    """A player as a seat may know them.  Unrevealed — a rival while the match is undecided — their purse,
    research, spell cooldowns, scores, alarms and assembly point stay home: the record carries the names
    with blank values, never the facts."""
    return {
        "id": player.id, "name": player.name, "human": player.human, "race": player.race.value,
        "gold": player.gold if revealed else 0, "lumber": player.lumber if revealed else 0,
        "aether": player.aether if revealed else 0, "aether_charge": player.aether_charge if revealed else 0,
        "alive": player.alive, "neutral": player.neutral, "surrendered": player.surrendered,
        "stats": dict(player.stats) if revealed else dict.fromkeys(player.stats, 0),
        "last_alert": player.last_alert if revealed else None,
        "last_hit": player.last_hit if revealed else None,
        "upgrades": sorted(upgrade.value for upgrade in player.upgrades) if revealed else [],
        "cooldowns": {spell.value: ready for spell, ready in
                      sorted(player.cooldowns.items(), key=lambda cast: cast[0].value)} if revealed else {},
        "assembly": _point(player.assembly) if revealed else None,
    }


def _projectile_record(shot):
    """A shot in the air: where it was loosed, what it is headed for and what its blow carries."""
    return {
        "id": shot.id, "player": shot.player, "source": shot.source, "source_type": shot.source_type,
        "kind": shot.kind, "start": list(shot.start), "aim": list(shot.aim), "target": shot.target,
        "launched": shot.launched, "flight": shot.flight, "damage": shot.damage, "splash": shot.splash,
        "attack": shot.attack.value,
        "inflicts": shot.inflicts.key if shot.inflicts is not None else None,
        "spell": shot.spell.value if shot.spell is not None else None,
    }


def _camp_record(camp, *, guards, posts, origin, roused, cleared):
    """A creature camp's identity and reward.  Whose blows earned them and when the camp settles again are
    the authority's: no audience's record carries the damage ledger or the timers."""
    return {
        "lair": camp.lair, "kinds": list(camp.kinds), "posts": posts, "guards": guards,
        "origin": _point(origin), "watch": _point(camp.watch), "struck": -1000.0,
        "roused": roused, "quiet_since": -1.0, "encounter": camp.encounter,
        "gold": camp.gold, "lumber": camp.lumber, "cleared": cleared, "credit": {},
    }


def _observed_camp_record(camp):
    """A camp as a watcher sees it: its whole roster at its posts, as it stands."""
    return _camp_record(camp, guards=list(camp.guards), posts=[list(post) for post in camp.posts],
                        origin=camp.origin, roused=camp.roused, cleared=camp.cleared)


def _plan_record(plan):
    return {"id": plan.id, "player": plan.player, "kind": plan.kind, "type": plan.type.value,
            "pos": _point(plan.pos), "status": plan.status, "worker": plan.worker, "building": plan.building}


def _knowledge_record(knowledge):
    """A seat's own remembered ground: terrain, footprints, mines and what it has witnessed of the wilds."""
    return {
        "width": knowledge.width, "height": knowledge.height,
        "terrain": [terrain.value if terrain is not None else None for terrain in knowledge.terrain],
        "buildings": [{"id": building.id, "x": building.x, "y": building.y, "size": building.size,
                       "player": building.player, "threat_range": building.threat_range, "ruin": building.ruin,
                       "type": building.type.value if building.type is not None else None}
                      for building in knowledge.buildings.values()],
        "encounters": [[lair, list(point)] for lair, point in knowledge.encounters.items()],
        "watches": [[lair, list(point)] for lair, point in knowledge.watches.items()],
        "cleared_encounters": sorted(knowledge.cleared_encounters),
        "fallen_guards": [[lair, sorted(kills.items())] for lair, kills in knowledge.fallen_guards.items()],
        "guard_warnings": [[uid, list(point)] for uid, point in knowledge.guard_warnings.items()],
        "mines": [{"id": mine.id, "x": mine.x, "y": mine.y, "size": mine.size, "gold": mine.gold,
                   "trip": mine.trip, "slots": mine.slots, "endless": mine.endless}
                  for mine in knowledge.mines.values()],
    }


def _blank_knowledge_record(width, height):
    """No memory at all: what stands in for every other seat's, and for every seat's to a watcher."""
    return {"width": width, "height": height, "terrain": [None] * (width * height), "buildings": [],
            "encounters": [], "watches": [], "cleared_encounters": [], "fallen_guards": [],
            "guard_warnings": [], "mines": []}


# -- The two audiences ----------------------------------------------------------------


def _world_record(world, *, terrain, players, units, buildings, camps, projectiles, explored,
                  worker_knowledge, settlement, regrowth, exposures):
    """The world record's named fields, each already built for its audience.  The id counter says nothing
    beyond what was sent, and a fixed random state stands in for the server's stream."""
    return {
        "width": world.width, "height": world.height, "theme": world.theme.value, "layout": world.layout.value,
        "magic": world.magic, "wilds": world.wilds,
        "gates": [list(tile) for tile in sorted(world.gates)],
        "rifts": [list(rift) for rift in world.rifts],
        "gate_links": [[list(hall), list(natural)] for hall, natural in world.gate_links],
        "terrain": terrain, "players": players, "regrowth": regrowth, "camps": camps,
        "units": units, "buildings": buildings, "projectiles": projectiles,
        "explored": explored, "worker_knowledge": worker_knowledge, "settlement": settlement,
        "time": world.time, "tick": world.tick,
        "next_id": 1 + max((record["id"] for record in (*units, *buildings, *projectiles)), default=0),
        "winner": world.winner, "scripted": world.scripted, "rng": NO_DICE, "exposures": exposures,
    }


def _terrain_as_known(world, player, begun):
    """The map's rows with every tile *player* does not see now as it remembers it, or as it began (*begun*) if never seen."""
    width, visible = world.width, world.visible[player]
    remembered = world.worker_knowledge[player].terrain
    known = []
    for y, (now, began) in enumerate(zip(terrain_rows(world), begun)):
        base = y * width
        seen = visible[base:base + width]
        if seen.count(0) == 0:
            known.append(now)
            continue
        known.append("".join(letter if sees else (memory.value[0] if (memory := remembered[base + x]) is not None else first)
                             for x, (letter, sees, first) in enumerate(zip(now, seen, began))))
    return known


def _seat_camp_record(camp, knowledge, seen_units, world):
    """A camp as a seat may know it: identities and rewards public once the lair is observed, its guards
    only those the seat sees now (at where they stand now), completion only as the seat witnessed it."""
    guards = [uid for uid in camp.guards if uid in seen_units]
    remembered_origin = knowledge.encounters.get(camp.lair)
    origin = remembered_origin if remembered_origin is not None else world.buildings[camp.lair].center
    return _camp_record(camp, guards=guards, origin=origin,
                        posts=[[seen_units[uid].x, seen_units[uid].y] for uid in guards],
                        roused=any(seen_units[uid].state == 'attack' for uid in guards),
                        cleared=camp.lair in knowledge.cleared_encounters)


def seat_world(world, player, begun):
    """The match as seat *player* may know it (built afresh, the receiver may keep it).

    All of its own.  Of everyone else's, what it sees now, without intentions: a unit's orders and home, a
    building's work.  The ground and the mines out of sight as it last saw them, ground it never saw as the
    map began (*begun*), mines it never saw not at all.  Which rival lies exposed to it
    (:meth:`World.exposures`), which its world holds too little of its rivals to judge.  The other seats'
    purse, research (and the conditions that would tell it) and scores once the match is decided, their
    plans and memory never, and the server's random stream never."""
    undecided = world.winner is None
    visible, knowledge = world.visible[player], world.worker_knowledge[player]
    unexplored = bytes(world.width * world.height).hex()
    players = [_player_record(each, revealed=seat == player or not undecided)
               for seat, each in enumerate(world.players)]
    explored = [bytes(world.explored[player]).hex() if seat == player else unexplored
                for seat in range(len(world.players))]
    memory = [_knowledge_record(knowledge) if seat == player else _blank_knowledge_record(world.width, world.height)
              for seat in range(len(world.players))]
    seen_units, units = {}, []
    for unit in world.units.values():
        if unit.player == player:
            seen_units[unit.id] = unit
            units.append(_own_unit_record(unit))
        elif not unit.hidden and world.is_visible(player, unit.tile):
            seen_units[unit.id] = unit
            units.append(_stranger_unit_record(unit, undecided))
    buildings, seen_buildings = [], set()
    for building in world.buildings.values():
        if building.player == player:
            buildings.append(_full_building_record(building))
        elif knowledge.sees(visible, building.x, building.y, building.size):
            buildings.append(_full_building_record(building) if building.player is None
                             else _stranger_building_record(building))
        elif building.id in knowledge.mines:
            buildings.append(_remembered_mine_record(building, knowledge.mines[building.id].gold))
        else:
            continue
        seen_buildings.add(building.id)
    camps = [_seat_camp_record(camp, knowledge, seen_units, world) for camp in world.camps
             if camp.lair in seen_buildings or camp.lair in knowledge.encounters]
    projectiles = [_projectile_record(shot) for shot in world.projectiles.values()
                   if shot.player == player
                   or world.is_visible(player, _tile(world.shot_ground(shot, world.time)))]
    plans = [_plan_record(plan) for plan in world.settlement.plans if plan.player == player]
    settlement = {'next_id': 1 + max((plan['id'] for plan in plans), default=0), 'plans': plans}
    regrowth = [[list(tile), when] for tile, when in world.regrowth if world.is_visible(player, tile)]
    exposures = [[exposed, told] for exposed, told in world.exposures() if told == player]
    return _world_record(world, terrain=_terrain_as_known(world, player, begun), players=players, units=units,
                         buildings=buildings, camps=camps, projectiles=projectiles, explored=explored,
                         worker_knowledge=memory, settlement=settlement, regrowth=regrowth, exposures=exposures)


def observer_world(world):
    """The match as a watcher may see it (built afresh, the receiver may keep it).

    Watching is a deliberate omniscient role, not a third seat.  The observer sees the current map whole:
    every faction's units (a stranger's intentions withheld, as for a seat), buildings, shots, camps and
    regrowth, the ground as it stands, and every seat's purse, research and scores.  What would let the
    snapshot stand in for the authority never travels: the random stream, each seat's explored ground and
    worker memory, the settlement's plans, and a camp's damage ledger and timers.  It changes nothing."""
    unexplored = bytes(world.width * world.height).hex()
    return _world_record(
        world, terrain=terrain_rows(world),
        players=[_player_record(each, revealed=True) for each in world.players],
        units=[_observed_unit_record(unit) for unit in world.units.values()],
        buildings=[_full_building_record(building) for building in world.buildings.values()],
        camps=[_observed_camp_record(camp) for camp in world.camps],
        projectiles=[_projectile_record(shot) for shot in world.projectiles.values()],
        explored=[unexplored] * len(world.players),
        worker_knowledge=[_blank_knowledge_record(world.width, world.height) for _ in world.players],
        settlement={'next_id': 1, 'plans': []},
        regrowth=[[list(tile), when] for tile, when in world.regrowth],
        exposures=[[exposed, told] for exposed, told in world.exposures()])


def _tile(point):
    return int(point[0]), int(point[1])
