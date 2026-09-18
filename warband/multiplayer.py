"""LAN and online match scenes; authority lives in warband.authority."""
import math
import time

from saga2d import Button, CommandError, Label
from warband.model import Event, RuleError, World
from warband.rules import SIM_DT
from warband.scene import GameScene, HelpScene, SettingsScene, _Overlay, _clock
from warband.style import ACTION_BUTTON, GHOST_BUTTON


HIT_AUDIO_FIELDS = frozenset({'source_type', 'target_type', 'target_armor', 'target_complete'})


class NetworkGameScene(GameScene):
    def __init__(self, session, match=None, *, settings=None):
        self.session, self.match = session, match
        self._revision = session.revision
        self._event_id = 0
        self._basic_audio_notice = False
        self._network_steps = 0
        self._last_time = time.monotonic()
        self._elapsed = 0.
        data = session.state
        super().__init__(World.from_dict(data['world']), data['seed'], settings=settings, player=session.player, ranked=False)
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
            if getattr(self.session, 'online', False):
                self.say(self.session.error or 'Match paused — waiting for your partner to reconnect.')
            else:
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
        self.view.sync()
        self._check_game_over()

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

    def _hint(self):
        return [(key, label) for key, label in super()._hint() if key != 'F3']

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

    controls = {"s": "settings", "f1": "help", "t": "leave_match", "q": "quit"}

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
        panel.add(Button("Leave match", hotkey="T", on_click=self.leave_match, style=GHOST_BUTTON, width=280))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=280))

    def settings(self):
        self.game.push(SettingsScene(self.game_scene))

    def help(self):
        self.game.push(HelpScene())

    def leave_match(self):
        from warband.title import TitleScene

        self.game.clear_and_push(TitleScene(settings=self.game_scene.settings))

    def quit(self):
        self.game.quit()


class NetworkResultScene(NetworkMenuScene):
    """A finished online match leads back to multiplayer, never to a solo rematch."""

    pop_on_cancel = False
    controls = {("t", "escape"): "leave_match", "q": "quit"}

    def __init__(self, game_scene, won):
        super().__init__(game_scene)
        self.won = won

    def on_enter(self):
        scene = self.game_scene
        winner = scene.world.players[scene.world.winner].name if scene.world.winner is not None else "Nobody yet"
        panel = self.panel("Victory!" if self.won else f"Defeat — {winner} prevails")
        stats = scene.stats
        panel.add(Label(f"{_clock(scene.world.time)} played · {stats['units_killed']} kills · "
                        f"{stats['units_lost']} units lost", text_style="body"))
        panel.add(Label("For another match, choose Multiplayer on the title screen.", text_style="sub"))
        panel.add(Button("Back to title", hotkey="T", on_click=self.leave_match, style=ACTION_BUTTON, width=280))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=280))
