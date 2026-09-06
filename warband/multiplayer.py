"""Host-clocked RTS matches. The transport knows nothing about units or ticks."""
import inspect
import math
import time
from copy import deepcopy

from saga2d import CommandError
from warband import mapgen
from warband.model import World, RuleError, Event
from warband.rules import BuildingType, UnitType, Upgrade, SIM_DT, MapTheme

GROUP_ORDERS = {'smart', 'move', 'attack_move', 'patrol', 'attack', 'repair', 'stop', 'hold'}
BUILDING_ORDERS = {'set_rally', 'train', 'research', 'cancel_train', 'cancel_research', 'cancel_building'}
ORDERS = GROUP_ORDERS | BUILDING_ORDERS | {'build'}


class WarbandMatch:
    def __init__(self, seed=3, width=48, height=40, theme=MapTheme.SUMMER):
        self.seed = seed
        self.world = mapgen.generate(seed, width, height, players=2, theme=theme)
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
        if action in GROUP_ORDERS:
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
            if point is None and action == 'set_rally':
                continue
            if (not isinstance(point, (tuple, list)) or len(point) != 2
                    or any(type(n) not in (int, float) or not math.isfinite(n) for n in point)
                    or not (0 <= point[0] < self.world.width and 0 <= point[1] < self.world.height)
                    or (action == 'build' and any(type(n) is not int for n in point))):
                raise CommandError('Choose a position inside the map.')
            values[field] = tuple(point)
        for field in ('target_id', 'building_id'):
            if field in values and type(values[field]) is not int:
                raise CommandError('Invalid target.')
        if action == 'cancel_train':
            index = values.get('index', -1)
            size = len(self.world.buildings[values['building_id']].queue)
            if type(index) is not int or not -size <= index < size:
                raise CommandError('Choose an item in the training queue.')
        for field, enum in [('building_type', BuildingType), ('unit_type', UnitType), ('upgrade', Upgrade)]:
            if field in values:
                try:
                    values[field] = enum(values[field])
                except (ValueError, TypeError) as exc:
                    raise CommandError(f'Unknown {field}.') from exc
        # Trial on a copy also makes group orders atomic if a rule rejects one unit.
        trial = World.from_dict(deepcopy(self.world.to_dict()))
        values['self'] = trial
        try:
            method(*bound.args, **bound.kwargs)
        except RuleError as exc:
            raise CommandError(str(exc)) from exc
        self.world = trial
        self._events()


from warband.scene import GameScene


class NetworkGameScene(GameScene):
    def __init__(self, session, match=None, *, settings=None):
        self.session, self.match = session, match
        self._revision = session.revision
        self._event_id = 0
        self._network_steps = 0
        self._last_time = time.monotonic()
        self._elapsed = 0.
        data = session.state
        super().__init__(World.from_dict(data['world']), data['seed'], settings=settings, player=session.player)
        self.brains = []
        self.tutorial = None
        self._autosave_at = math.inf

    def on_enter(self):
        super().on_enter()
        self.every(1 / 60, self._poll)

    def on_close(self):
        self.session.close()

    def _step_match(self):
        now = time.monotonic()
        dt, self._last_time = min(.25, now - self._last_time), now
        if self.match is None or not self.session.ready:
            self._elapsed = 0.
            return
        self._elapsed += dt
        while self._elapsed >= SIM_DT:
            self.match.step()
            self._elapsed -= SIM_DT
            self._network_steps += 1
            if self._network_steps % 2 == 0:
                self.session.publish()

    def _advance(self, dt):
        pass  # The host match advances through its scene-owned timer, including under menus.

    def _poll(self):
        self.session.poll()
        self._step_match()
        if self.session.error and self.session.ready:
            self.say(self.session.error)
            self.session.error = ""
        if not self.session.ready:
            self.say('Match paused — waiting for your partner.' if self.session.player == 0 else
                     'Disconnected — return to the title and rejoin the host.')
        if self._revision == self.session.revision:
            return
        self._revision = self.session.revision
        data = self.session.state
        fresh = World.from_dict(data['world'])
        for old, new in zip(self.world.players, fresh.players):
            old.__dict__.update(new.__dict__)
        fresh.players = self.world.players
        self.world.__dict__.update(fresh.__dict__)
        events = []
        for index, event in data['events']:
            if index > self._event_id:
                events.append(Event(**{**event, 'pos': tuple(event['pos'])}))
                self._event_id = index
        self._handle_events(events)
        self._prune_selection()
        self._refresh_card()
        self.view.sync()
        self._check_game_over()

    def order(self, action, *args, **kwargs):
        fields = [arg.value if hasattr(arg, 'value') else arg for arg in args]
        try:
            self.session.submit({'action': action, 'args': fields, 'kwargs': kwargs})
        except CommandError as exc:
            self.warn(str(exc))
        return 'move' if action == 'smart' else None

    def toggle_pause(self):
        self.say('Online matches continue while menus are open.')

    def save_to(self, slot):
        self.say('Multiplayer runs live on the host; offline saves are separate.')

    def load_from(self, slot):
        self.say('Rejoin the host to resume this multiplayer match.')
