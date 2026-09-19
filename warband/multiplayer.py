"""LAN and online match scenes; authority lives in warband.authority."""
import math
import time

from saga2d import Button, CommandError, Label, Settings
from warband.model import Event, RuleError, World
from warband.rules import SIM_DT
from warband.scene import GameScene, HelpScene, SettingsScene, _Overlay, _clock
from warband.style import ACTION_BUTTON, GHOST_BUTTON
from warband.view import check_memory


HIT_AUDIO_FIELDS = frozenset({'source_type', 'target_type', 'target_armor', 'target_complete'})
#: The room publishes every other 20 Hz tick: the interval to present over until arrivals have been measured.
SNAPSHOT_INTERVAL = 0.1
#: Units cover what the latest snapshot says a little more slowly than snapshots come, so one that is a little late
#: finds them still moving instead of stopped.
SLACK = 1.25
#: A gap longer than this is a stall, a pause or a resume: what arrives after it is placed, not slid into.
STALL = 0.5
#: Silence this long from a ready room is said on the status line.
QUIET = 1.0


def _room_memory(game):
    """What the player had seen of buildings out of sight in the online room they last played.  A room tells a seat
    only what it sees now (WB-011), so rejoining it from the title would otherwise forget the rival's base."""
    return Settings(game.data_dir / 'online-memory.json', {'room': '', 'player': -1, 'seen': {'buildings': []}})


class NetworkGameScene(GameScene):
    def __init__(self, session, match=None, *, settings=None):
        self.session, self.match = session, match
        self._revision = session.revision
        self._event_id = 0
        self._basic_audio_notice = False
        self._network_steps = 0
        self._last_time = time.monotonic()
        self._elapsed = 0.
        self._snapshot_at = 0.0  # scene clock of the latest snapshot
        self._quiet_said = False  # the status line says the server has gone quiet
        self._interval = SNAPSHOT_INTERVAL  # measured time between snapshots, smoothed
        data = session.state
        super().__init__(World.from_dict(data['world']), data['seed'], settings=settings, player=session.player, ranked=False)
        self.brains = []
        self.tutorial = None
        self._autosave_at = math.inf

    def on_enter(self):
        if getattr(self.session, 'online', False):
            record = _room_memory(self.game)
            if (record['room'], record['player']) == (self.session.room, self.session.player):
                check_memory(record['seen'], self.world)
                self._seen = record['seen']
        super().on_enter()
        self.every(1 / 60, self._poll)

    def on_close(self):
        if getattr(self.session, 'online', False) and self.session.room:
            record = _room_memory(self.game)
            record.update(room=self.session.room, player=self.session.player, seen=self.view.memory())
            record.save()
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
            if getattr(self.session, 'online', False):
                self.say(self.session.error or 'Match paused — waiting for your partner to reconnect.')
            else:
                self.say('Match paused — waiting for your partner.' if self.session.player == 0 else
                         'Disconnected — return to the title and rejoin the host.')
        elif self.clock - self._snapshot_at > QUIET:
            self.say(f'No word from the server for {self.clock - self._snapshot_at:.0f} s — the match goes on when it answers.')
            self._quiet_said = True
        if self._revision == self.session.revision:
            return
        self._revision = self.session.revision
        if self._quiet_said:  # word came: the silence is over, and the line must not go on saying it
            self.status_timer, self._quiet_said = 0.0, False
        gap = self.clock - self._snapshot_at
        drawn = self.view.drawn_positions() if gap <= STALL else {}  # after a stall or a resume, place; never slide stale motion
        if gap <= STALL:
            self._interval = min(.25, max(.05, .8 * self._interval + .2 * gap))
        self._snapshot_at = self.clock
        data = self.session.state
        fresh = World.from_dict(data['world'])
        for old, new in zip(self.world.players, fresh.players):
            old.__dict__.update(new.__dict__)
        fresh.players = self.world.players
        self.world.__dict__.update(fresh.__dict__)
        events = []
        for index, event in data['events']:
            if index > self._event_id:
                if event['kind'] == 'hit':
                    audio_fields = HIT_AUDIO_FIELDS.intersection(event)
                    if not audio_fields:
                        event = {**event, 'source_type': 'unknown', 'target_type': 'unknown'}
                        if not self._basic_audio_notice:
                            self.say('Server uses basic battle audio; update the server for weapon and material sounds.')
                            self._basic_audio_notice = True
                    elif audio_fields != HIT_AUDIO_FIELDS:
                        raise ValueError('Hit event has incomplete battle audio metadata.')
                events.append(Event(**{**event, 'pos': tuple(event['pos'])}))
                self._event_id = index
        self._handle_events(events)
        self._prune_selection()
        self._refresh_card()
        self.view.present_from(drawn)
        self.view.sync(fraction=self._motion_fraction())
        self._check_game_over()

    def _motion_fraction(self):
        """How far units have moved on from where they were drawn towards the latest snapshot."""
        if self._game_over or self.world.winner is not None or not self.player.alive:
            return 1.0
        return min(1.0, (self.clock - self._snapshot_at) / (self._interval * SLACK))

    def order(self, action, *args, **kwargs):
        """Send the order to the match's authority.  One that cannot be sent is refused here and now; what the
        authority refuses comes back later as the session's error."""
        fields = [arg.value if hasattr(arg, 'value') else arg for arg in args]
        try:
            self.session.submit({'action': action, 'args': fields, 'kwargs': kwargs})
        except CommandError as exc:
            raise RuleError(str(exc)) from exc

    def open_menu(self):
        self.game.push(NetworkMenuScene(self))

    def hint(self):
        return [(key, label) for key, label in super().hint() if key != 'F3']

    def _check_game_over(self):
        if self._game_over:
            return
        if self.world.winner is not None or not self.player.alive:
            won = self.world.winner == self.human
            self._finish(won)
            self.game.push(NetworkResultScene(self, won))

    def toggle_pause(self):
        self.say('Online matches continue while menus are open.')

    def save_to(self, slot):
        self.say('This multiplayer match runs live; offline saves are separate.')

    def load_from(self, slot):
        self.say('Use Multiplayer → Rejoin last room to resume online play.' if getattr(self.session, 'online', False)
                 else 'Rejoin the host to resume this multiplayer match.')


class NetworkMenuScene(_Overlay):
    """A live match menu: local preferences and explicit room departure only."""

    controls = {"s": "settings", "f1": "help", "r": "resign", "t": "leave_match", "q": "quit"}

    def __init__(self, game_scene):
        self.game_scene = game_scene

    def on_enter(self):
        panel = self.panel("Match menu")
        panel.add(Label("The match continues while this menu is open.", text_style="body"))
        rejoin = ("Rejoin from Multiplayer → Rejoin last room." if getattr(self.game_scene.session, "online", False)
                  else "Rejoin the host from Multiplayer → LAN.")
        panel.add(Label(rejoin, text_style="sub"))
        panel.add(Button("Return to match", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=280))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=280))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=280))
        if self._can_resign():
            panel.add(Button("Resign", hotkey="R", on_click=self.resign, style=GHOST_BUTTON, width=280))
        panel.add(Button("Leave match", hotkey="T", on_click=self.leave_match, style=GHOST_BUTTON, width=280))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=280))

    def _can_resign(self):
        scene = self.game_scene
        return scene.world.can_resign(scene.human) is None

    def resign(self):
        if self._can_resign():
            self.game.push(ResignScene(self.game_scene))

    def settings(self):
        self.game.push(SettingsScene(self.game_scene))

    def help(self):
        self.game.push(HelpScene())

    def leave_match(self):
        from warband.title import TitleScene

        self.game.clear_and_push(TitleScene(settings=self.game_scene.settings))

    def quit(self):
        self.game.quit()


class ResignScene(_Overlay):
    """Resigning online asks first: it cannot be taken back."""

    controls = {("return", "y"): "confirm", ("escape", "n"): "cancel"}

    def __init__(self, game_scene):
        self.game_scene = game_scene

    def on_enter(self):
        world = self.game_scene.world
        panel = self.panel("Resign the match?")
        others = ("Your forces lay down their arms. Your buildings stay, abandoned, and the others fight on."
                  if len(world.players) >= 3 else "Your forces lay down their arms, and your opponent wins.")
        panel.add(Label(others, text_style="body", width=520, wrap=True))
        panel.add(Button("Resign", hotkey="Enter", on_click=self.confirm, style=ACTION_BUTTON, width=280))
        panel.add(Button("Keep fighting", hotkey="Esc", on_click=self.cancel, style=GHOST_BUTTON, width=280))

    def confirm(self):
        scene = self.game_scene
        self.game.pop()  # this question
        self.game.pop()  # the match menu
        scene.attempt('resign', scene.human)

    def cancel(self):
        self.game.pop()


class NetworkResultScene(NetworkMenuScene):
    """A finished online match leads back to multiplayer, never to a solo rematch.  A player who is out while
    the others fight on may stay and watch."""

    pop_on_cancel = False
    controls = {("t", "escape"): "leave_match", "q": "quit", "w": "watch"}

    def __init__(self, game_scene, won):
        super().__init__(game_scene)
        self.won = won

    def on_enter(self):
        scene = self.game_scene
        decided = scene.world.winner is not None
        title = ("Victory!" if self.won else f"Defeat — {scene.world.players[scene.world.winner].name} prevails" if decided
                 else "You are out — the others fight on")
        panel = self.panel(title)
        stats = scene.stats
        panel.add(Label(f"{_clock(scene.world.time)} played · {stats['units_killed']} kills · "
                        f"{stats['units_lost']} units lost", text_style="body"))
        panel.add(Label("For another match, choose Multiplayer on the title screen.", text_style="sub"))
        if not decided:
            panel.add(Button("Watch", hotkey="W", on_click=self.watch, style=ACTION_BUTTON, width=280))
        panel.add(Button("Back to title", hotkey="T", on_click=self.leave_match, style=ACTION_BUTTON if decided else GHOST_BUTTON, width=280))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=280))

    def watch(self):
        if self.game_scene.world.winner is None:
            self.game.pop()
