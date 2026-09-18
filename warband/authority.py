"""Authoritative RTS matches and server registration, independent of client scenes."""
import inspect
from copy import deepcopy

from saga2d import CommandError
from warband import mapgen
from warband.model import World, RuleError
from saga2d.server.games import GameSpec, option_choice, option_int, option_keys, option_seed
from warband.rules import BuildingType, UnitType, Upgrade, SIM_DT, Layout, MapTheme, Race

GROUP_ORDERS = {'smart', 'move', 'attack_move', 'patrol', 'attack', 'repair', 'stop', 'hold'}
BUILDING_ORDERS = {'set_rally', 'train', 'research', 'cancel_train', 'cancel_research', 'cancel_building'}
SETTLEMENT_ORDERS = {'plan_building', 'order_unit', 'order_upgrade', 'set_assembly', 'cancel_plan'}
ORDERS = GROUP_ORDERS | BUILDING_ORDERS | SETTLEMENT_ORDERS | {'build'}


class WarbandMatch:
    def __init__(self, seed=3, width=48, height=40, theme=MapTheme.SUMMER, races=None, layout=None):
        """*races* names the two seats' races; a ``None`` seat is drawn from the seed, and so is a ``None`` *layout*."""
        self.seed = seed
        self.world = mapgen.generate(seed, width, height, players=2, theme=theme, races=races, layout=layout)
        for player in self.world.players:
            player.human = True
        self.events = []
        self.event_id = 0

    def _events(self):
        for event in self.world.take_events():
            self.event_id += 1
            self.events.append([self.event_id, vars(event)])
        self.events = self.events[-128:]

    def snapshot(self, player):
        return {'seed': self.seed, 'world': deepcopy(self.world.to_dict()), 'events': deepcopy(self.events)}

    def step(self):
        if self.world.winner is None:
            self.world.step()
            self._events()

    def apply(self, player, command):
        if player not in (0, 1) or self.world.winner is not None or not self.world.players[player].alive:
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
        if action in SETTLEMENT_ORDERS:
            if type(values['player']) is not int or values['player'] != player:
                raise CommandError('You can only order your own settlement.')
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
        if action == 'cancel_train' and type(values.get('index', -1)) is not int:
            raise CommandError('Choose an item in the training queue.')
        for field, enum in [('building_type', BuildingType), ('unit_type', UnitType), ('upgrade', Upgrade)]:
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
    option_keys(options, {'seed', 'width', 'height', 'theme', 'races', 'layout'})
    races = options.get('races', [None, None])
    if (not isinstance(races, list) or len(races) != 2
            or any(race is not None and (not isinstance(race, str) or race not in {r.value for r in Race})
                   for race in races)):
        raise CommandError('races must name two seats, each a race or null.')
    layout = option_choice(options, 'layout', 'any', {each.value for each in Layout} | {'any'})
    return WarbandMatch(option_seed(options, 3), width=option_int(options, 'width', 48, 48, 80),
                        height=option_int(options, 'height', 40, 40, 64),
                        theme=MapTheme(option_choice(options, 'theme', 'summer', {t.value for t in MapTheme})),
                        races=[Race(race) if race is not None else None for race in races],
                        layout=None if layout == 'any' else Layout(layout))


def _checkpoint(match):
    return {'seed': match.seed, 'world': deepcopy(match.world.to_dict()), 'events': deepcopy(match.events)}


def _restore(snapshot):
    match = WarbandMatch.__new__(WarbandMatch)
    match.seed, match.world = snapshot['seed'], World.from_dict(snapshot['world'])
    match.events = snapshot['events']
    match.event_id = max((event[0] for event in match.events), default=0)
    return match


ONLINE = {'warband-v2': GameSpec(_create, _checkpoint, _restore, realtime=True)}
