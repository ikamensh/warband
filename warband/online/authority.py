"""Authoritative RTS matches and server registration, independent of client scenes."""
import inspect
import random

from saga2d import CommandError
from warband.sim import mapgen
from warband.sim.model import Unit, World, RuleError, field_values
from warband.sim.worker_knowledge import WorkerKnowledge
from saga2d.server.games import GameSpec, option_choice, option_int, option_keys, option_seed
from warband.sim.rules import BLOODLUST_RAGE, RAGE, SPELLS, BuildingType, UnitType, Upgrade, SIM_DT, Layout, MapTheme, Race

GROUP_ORDERS = {'smart', 'move', 'attack_move', 'patrol', 'attack', 'repair', 'salvage', 'stop', 'hold', 'release_workers'}
BUILDING_ORDERS = {'set_rally', 'train', 'research', 'cancel_train', 'cancel_research', 'cancel_building', 'set_auto_train'}
SETTLEMENT_ORDERS = {'plan_building', 'order_unit', 'order_upgrade', 'set_assembly', 'cancel_plan'}
SEAT_ORDERS = SETTLEMENT_ORDERS | {'resign', 'cast'}  # orders about the seat's own player, named in the order
ORDERS = GROUP_ORDERS | BUILDING_ORDERS | SEAT_ORDERS | {'build'}
#: Ticks an event rides the snapshots (five seconds): long enough for a client that hiccups, not for ever.
EVENT_TICKS = 100
#: What a seat is told of the server's random stream: a fixed state, so no client can read the damage rolls to come.
NO_DICE = random.Random(0).getstate()
#: News for its owner alone: what it trains and researches, what it is refused or left to plans, its deposits, what it
#: salvages, its alarms, its plunder and the aether a lost vault spilled.
PRIVATE_EVENTS = frozenset({'trained', 'researched', 'refused', 'deferred', 'deposit', 'salvage', 'under_attack', 'plunder', 'spilled'})
#: The match's public news, told to every seat wherever it happened.
PUBLIC_EVENTS = frozenset({'victory', 'eliminated', 'surrendered', 'resigned', 'exposed'})
#: A spell cast and landing (WB-066): news for its caster and for every seat that sees the ground it touches, which
#: tells them the spell and the point.  Neither private (a cast in sight is no secret) nor public: a blind cast into
#: the fog, or one far from a rival, is not that rival's to hear of.
SPELL_EVENTS = frozenset({'cast', 'spell'})
#: What a seat learns of a unit it sees but does not own is where it stands and how it moves and strikes, not where it is
#: going, nor how lately its owner had it in hand.
STRANGER_UNIT = {'orders': [], 'worker_orders': [], 'home': None, 'constructing': None, 'auto_work': False, 'commanded': None}
#: The conditions a stranger's unit is shown carrying under another kind's name until the match is decided: a kind of
#: its own would tell its owner's research.  Rage under Bloodlust is Rage.
STRANGER_KINDS = {BLOODLUST_RAGE.key: RAGE.key}
#: Of a building it sees but does not own: footprint, hit points, construction and abandonment, not its work.  A site
#: keeps its builder's id (the builder itself is inside, out of sight): a site with none is one from a save older than
#: WB-048, and a load removes it.
STRANGER_BUILDING = {'queue': [], 'train_progress': 0.0, 'rally': None, 'research': None, 'research_progress': 0.0, 'auto': []}


def _stranger_unit(d, undecided):
    """What a seat is told of the unit *d* it sees and does not own: :data:`STRANGER_UNIT`, and while the match is
    *undecided* its conditions as :data:`STRANGER_KINDS` names them."""
    stranger = {**d, **STRANGER_UNIT}
    if undecided and d['conditions']:
        stranger['conditions'] = [{**c, 'kind': STRANGER_KINDS.get(c['kind'], c['kind'])} for c in d['conditions']]
    return stranger


def _terrain_rows(world):
    return ["".join(t.value[0] for t in row) for row in world.terrain]


#: The most seats a Warband room can hold.  The offline game seats sixteen, but every client
#: declares ``saga2d.online.SEATS`` in its hello and the server refuses a room with more seats than
#: the client can play; that number is 4 in the Saga2D this pins, so a room is four whatever the
#: authority would allow.  Raising it is an engine release, not a Warband change — and a snapshot
#: that is not one whole world per seat per tick.  See docs/warband-maps.md, "Sixteen seats online".
ONLINE_SEATS = 4
#: The largest map a room may ask for.  The offline game goes to 180x132; a room stays where it was
#: so that the options in :data:`ONLINE` keep the shape and the range the live server already
#: speaks, and one seat's snapshot stays the size it is today.
ONLINE_SIZE = (80, 64)


class WarbandMatch:
    def __init__(self, seed=3, width=48, height=40, theme=MapTheme.SUMMER, races=None, layout=None, players=2):
        """*players* humans, two to :data:`ONLINE_SEATS`; *races* names each seat's race, a ``None`` seat drawn from
        the seed, and so is a ``None`` *layout*."""
        self.seed = seed
        self.world = mapgen.generate(seed, width, height, players=players, theme=theme, races=races, layout=layout)
        for player in self.world.players[:self.world.seats]:  # never the wilds: no client sits in that seat
            player.human = True
        self.events = []  # [number, fields] of the recent ones, oldest first
        self.event_ticks = []  # the tick each of them happened at
        self.event_seen = []  # the seats that may hear of each: decided when it happens, not when a snapshot goes out
        self.event_id = 0
        self.begun = _terrain_rows(self.world)  # the map as it began: what a seat is told of ground it never saw

    def _events(self):
        """Number the world's new events and drop the old ones: a snapshot carries the recent ones only, for a client
        cannot say which it has seen, and a burst never more than 128 of them."""
        tick = self.world.tick
        blasts = {}  # a keg gone up this step -> its side: the blows it strikes follow it the same step
        for event in self.world.take_events():
            self.event_id += 1
            self.events.append([self.event_id, field_values(event)])
            self.event_ticks.append(tick)
            if event.kind == 'blast':
                blasts[event.entity] = event.player
            self.event_seen.append(self._witnesses(event, blasts.get(event.entity) if event.kind == 'hit' else None))
        fresh = next((i for i, born in enumerate(self.event_ticks) if tick - born < EVENT_TICKS), len(self.events))
        keep = max(fresh, len(self.events) - 128)
        self.events, self.event_ticks, self.event_seen = self.events[keep:], self.event_ticks[keep:], self.event_seen[keep:]

    def _witnesses(self, event, striker=None):
        """The seats that may hear of *event*: all of them for public news, its owner alone for its private
        affairs, otherwise its owner, every seat that sees where it happens and the *striker*'s side of a blow
        struck by a keg: a sapper's eyes go up with it, and its side hears what its blast did wherever that was."""
        seats = range(self.world.seats)
        if event.kind in PUBLIC_EVENTS:
            return list(seats)
        if event.kind in PRIVATE_EVENTS:
            return [event.player]
        if event.kind in SPELL_EVENTS:
            return [seat for seat in seats if seat == event.player or self._sees_spell(seat, event)]
        tile = (int(event.pos[0]), int(event.pos[1]))
        return [seat for seat in seats if seat == event.player or seat == striker or self.world.is_visible(seat, tile)]

    def _sees_spell(self, seat, event):
        """Whether *seat* sees a spell cast or landing: any tile of the ground it touches, so a seat that sees the edge
        of a Wither on its own soldiers hears of it though the point is in its fog."""
        world, info = self.world, SPELLS[Upgrade(event.text)]
        (px, py), reach = event.pos, info.radius + 0.5
        x0, y0 = max(0, int(px - reach)), max(0, int(py - reach))
        x1, y1 = min(world.width - 1, int(px + reach)), min(world.height - 1, int(py + reach))
        return world.any_visible(seat, (x0, y0, x1 - x0 + 1, y1 - y0 + 1)) and any(
            world.is_visible(seat, (x, y)) and (x + 0.5 - px) ** 2 + (y + 0.5 - py) ** 2 <= reach * reach
            for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))

    def snapshot(self, player):
        """The match as seat *player* may know it (``to_dict`` builds it afresh, the receiver may keep it).

        All of its own.  Of everyone else's, what it sees now, without intentions: a unit's orders and home, a
        building's work.  The ground and the mines out of sight as it last saw them, ground it never saw as the
        map began, mines it never saw not at all.  Of the news, what it saw happen, its own affairs and what is
        public.  Which rival lies exposed to it (:meth:`World.exposures`), which its world holds too little of its
        rivals to judge.  The other seats' purse (gold, lumber and aether), research (and the conditions that would
        tell it) and scores once the match is decided, their plans and memory never, and the server's random stream
        never: a fixed state stands in for it."""
        world = self.world
        data = world.to_dict()
        data['rng'] = NO_DICE
        unexplored = bytes(world.width * world.height).hex()
        unknown = WorkerKnowledge(world.width, world.height).to_dict()
        for seat, record in enumerate(data['players']):
            if seat != player:
                data['explored'][seat], data['worker_knowledge'][seat] = unexplored, unknown
                if world.winner is None:
                    record.update(gold=0, lumber=0, aether=0, aether_charge=0, upgrades=[], cooldowns={},
                                  stats=dict.fromkeys(record['stats'], 0), last_alert=None, last_hit=None, assembly=None)
        visible, knowledge = world.visible[player], world.worker_knowledge[player]
        data['units'] = [d if unit.player == player else _stranger_unit(d, world.winner is None)
                         for unit, d in zip(world.units.values(), data['units'])
                         if unit.player == player or (not unit.hidden and world.is_visible(player, unit.tile))]
        buildings = []
        for building, d in zip(world.buildings.values(), data['buildings']):
            if building.player == player:
                buildings.append(d)
            elif knowledge.sees(visible, building.x, building.y, building.size):
                buildings.append(d if building.player is None else {**d, **STRANGER_BUILDING})
            elif building.id in knowledge.mines:
                buildings.append({**d, 'gold': knowledge.mines[building.id].gold})
        data['buildings'] = buildings
        data['projectiles'] = [d for shot, d in zip(world.projectiles.values(), data['projectiles'])
                               if shot.player == player or world.is_visible(player, _tile(world.shot_ground(shot, world.time)))]
        data['next_id'] = 1 + max((d['id'] for key in ('units', 'buildings', 'projectiles') for d in data[key]), default=0)
        plans = [plan for plan in data['settlement']['plans'] if plan['player'] == player]
        data['settlement'] = {'next_id': 1 + max((plan['id'] for plan in plans), default=0), 'plans': plans}
        data['terrain'] = self._terrain_as_known(player, data['terrain'])
        data['regrowth'] = [entry for entry in data['regrowth'] if world.is_visible(player, tuple(entry[0]))]
        data['exposures'] = [[exposed, told] for exposed, told in world.exposures() if told == player]
        return {'seed': self.seed, 'world': data, 'events': self._recent_events(player)}

    def _terrain_as_known(self, player, rows):
        """The map's rows with every tile *player* does not see now as it remembers it, or as it began if never seen."""
        width, visible = self.world.width, self.world.visible[player]
        remembered = self.world.worker_knowledge[player].terrain
        known = []
        for y, (now, began) in enumerate(zip(rows, self.begun)):
            base = y * width
            seen = visible[base:base + width]
            if seen.count(0) == 0:
                known.append(now)
                continue
            known.append("".join(letter if sees else (memory.value[0] if (memory := remembered[base + x]) is not None else first)
                                 for x, (letter, sees, first) in enumerate(zip(now, seen, began))))
        return known

    def _knows(self, player, entity):
        """Whether seat *player* may name *entity* in an order: all of its own, what its snapshot shows it now, and
        the buildings it remembers.  Anything else is no target to it, just as an id nobody has is none: an answer
        that told the two apart would tell it which ids stand on the map, and an order on one would walk its forces
        there through the fog."""
        if entity is None:
            return False
        if entity.player == player:
            return True
        world = self.world
        if isinstance(entity, Unit):
            return not entity.hidden and world.is_visible(player, entity.tile)
        knowledge = world.worker_knowledge[player]
        return entity.id in knowledge.buildings or knowledge.sees(world.visible[player], entity.x, entity.y, entity.size)

    def _recent_events(self, player=None):
        """The news that still rides the snapshots: all of it for the checkpoint, what *player* may hear for a seat."""
        return [[index, dict(fields)] for (index, fields), seen in zip(self.events, self.event_seen) if player is None or player in seen]

    def step(self):
        if self.world.winner is None:
            self.world.step()
            self._events()

    def apply(self, player, command):
        if player not in range(self.world.seats) or self.world.winner is not None or not self.world.players[player].alive:
            raise CommandError('This faction cannot issue orders.')
        action, args, kwargs = command.get('action'), command.get('args'), command.get('kwargs', {})
        if not isinstance(action, str) or action not in ORDERS or not isinstance(args, list) or not isinstance(kwargs, dict):
            raise CommandError('Invalid Warband order.')
        method = getattr(World, action)
        try:
            bound = inspect.signature(method).bind(self.world, *args, **kwargs)
        except TypeError as exc:
            raise CommandError('Invalid order arguments.') from exc
        values = bound.arguments
        def own(entity_id, collection):
            entity = collection.get(entity_id) if type(entity_id) is int else None
            if entity is None or entity.player != player:
                raise CommandError('You can only order your own units and buildings.')
        if action in SEAT_ORDERS:
            if type(values['player']) is not int or values['player'] != player:
                raise CommandError({'resign': 'You can only resign yourself.', 'cast': 'You can only cast your own spells.'}
                                   .get(action, 'You can only order your own settlement.'))
        elif action in GROUP_ORDERS:
            ids = values['unit_ids']
            if not isinstance(ids, list) or not 1 <= len(ids) <= 256:
                raise CommandError('Select between one and 256 units.')
            for unit_id in ids:
                own(unit_id, self.world.units)
        else:
            own(values['unit_id'] if action == 'build' else values['building_id'],
                self.world.units if action == 'build' else self.world.buildings)
        if 'queue' in kwargs and type(kwargs['queue']) is not bool:
            raise CommandError('Queue must be true or false.')
        if 'plan_if_short' in kwargs and type(kwargs['plan_if_short']) is not bool:
            raise CommandError('plan_if_short must be true or false.')
        if action == 'set_auto_train' and type(values['on']) is not bool:
            raise CommandError('Endless training is switched on or off.')
        for field in ('target', 'point', 'pos'):
            if field not in values:
                continue
            point = values[field]
            if point is None and action in ('set_rally', 'set_assembly'):
                continue
            if (not isinstance(point, (tuple, list)) or len(point) != 2
                    or any(type(n) not in (int, float) for n in point)
                    or not (0 <= point[0] < self.world.width and 0 <= point[1] < self.world.height)
                    or (action in ('build', 'plan_building') and any(type(n) is not int for n in point))):
                raise CommandError('Choose a position inside the map.')
            values[field] = tuple(point)
        for field in ('target_id', 'building_id', 'plan_id'):
            if action == 'smart' and field == 'target_id' and values.get(field) is None:
                continue  # An explicit empty-ground pick must not target a newer unit position.
            if field in values and type(values[field]) is not int:
                raise CommandError('Invalid target.')
        if action == 'smart' and 'target_id' not in values:
            # A right-click that names nothing picks here, as the seat knows the map: not a farm raised out of its sight.
            picked = self.world.entity_at(values['point'], visible_to=player)
            values['target_id'] = picked.id if self._knows(player, picked) else None
        elif values.get('target_id') is not None and not self._knows(player, self.world.entity(values['target_id'])):
            raise CommandError('No such target')
        if action == 'cancel_train' and type(values.get('index', -1)) is not int:
            raise CommandError('Choose an item in the training queue.')
        for field, enum in [('building_type', BuildingType), ('unit_type', UnitType), ('upgrade', Upgrade), ('spell', Upgrade)]:
            if field in values:
                try:
                    values[field] = enum(values[field])
                except (ValueError, TypeError) as exc:
                    raise CommandError(f'Unknown {field}.') from exc
        # The order goes to the running world: a copy rebuilt from its save would come back without the paths,
        # plan throttles and stuck clocks of every unit on the map.  A world order checks before it changes
        # anything, so one the rules refuse leaves no trace (tests/warband/test_order_atomicity.py).
        try:
            method(*bound.args, **bound.kwargs)
        except RuleError as exc:
            raise CommandError(str(exc)) from exc
        self._events()


def _create(options):
    """Validate resource-bounded creation options before generating any map."""
    option_keys(options, {'seed', 'width', 'height', 'theme', 'races', 'layout', 'players'})
    players = option_int(options, 'players', 2, 2, ONLINE_SEATS)
    races = options.get('races', [None] * players)
    if (not isinstance(races, list) or len(races) != players
            or any(race is not None and (not isinstance(race, str) or race not in {r.value for r in Race})
                   for race in races)):
        raise CommandError(f'races must name {players} seats, each a race or null.')
    layout = option_choice(options, 'layout', 'any', {each.value for each in Layout} | {'any'})
    try:
        return WarbandMatch(option_seed(options, 3), width=option_int(options, 'width', 48, 48, ONLINE_SIZE[0]),
                            height=option_int(options, 'height', 40, 40, ONLINE_SIZE[1]),
                            theme=MapTheme(option_choice(options, 'theme', 'summer', {t.value for t in MapTheme})),
                            races=[Race(race) if race is not None else None for race in races],
                            layout=None if layout == 'any' else Layout(layout), players=players)
    except mapgen.NoFairMap as exc:
        raise CommandError(f'{exc} Choose a larger map or another layout.') from exc


def _tile(point):
    return int(point[0]), int(point[1])


def _checkpoint(match):
    return {'seed': match.seed, 'world': match.world.to_dict(), 'events': match._recent_events(), 'event_id': match.event_id,
            'event_seen': match.event_seen, 'begun': match.begun}


def _restore(snapshot):
    match = WarbandMatch.__new__(WarbandMatch)
    match.seed, match.world = snapshot['seed'], World.from_dict(snapshot['world'])
    match.events = snapshot['events']
    match.event_ticks = [match.world.tick] * len(match.events)  # a restored match tells its last news once more
    # The count goes on where it was, or a client would take the news after a restart for news it has had.
    match.event_id = snapshot.get('event_id', max((event[0] for event in match.events), default=0))  # older checkpoints carry none
    # A checkpoint from before WB-011 kept no record of who saw what, nor of the map's beginning: its last news
    # goes to every seat once, and the ground as it stands now stands for how it began.
    match.event_seen = snapshot.get('event_seen', [list(range(match.world.seats))] * len(match.events))
    match.begun = snapshot.get('begun', _terrain_rows(match.world))
    return match


def _needed(match, player):
    """A seat is needed while its player is in an undecided match: one who resigned or fell may leave."""
    return match.world.winner is None and match.world.players[player].alive


ONLINE = {'warband-v2': GameSpec(_create, _checkpoint, _restore, realtime=True,
                                 seats=lambda match: match.world.seats, needed=_needed)}
