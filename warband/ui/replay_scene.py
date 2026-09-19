"""Watching a replay: the recorded match played back, with the clock and the fog in the viewer's hands."""

from __future__ import annotations

import math
import time
from typing import Any

from saga2d import Button, Label, Row
from warband.sim.model import RuleError
from warband.records.replay import Playback, Replay
from warband.sim.rules import SIM_DT
from warband.ui.scene import MAX_STEPS_PER_FRAME, GameScene, HelpScene, SettingsScene, _Overlay, _clock
from warband.ui.style import ACTION_BUTTON, BAD, GHOST_BUTTON, GOLD, GOOD, MUTED
from warband.ui.view import MapView

SPEEDS = (1, 2, 4, 8, 16)
SKIP_BUDGET = 0.4  # seconds of stepping per frame while skipping to the end, so the window keeps answering


class ReplayScene(GameScene):
    """The match as it was played, from the seat of the player who recorded it.

    Orders are the recording's; the viewer chooses the pace (PgUp/PgDn, F3
    pauses, End skips to the end) and whether the fog hides what the player
    could not see (F4).
    """

    controls = {**{key: method for key, method in GameScene.controls.items() if method not in ("quick_save", "quick_load", "hide_tutorial")},
                "pageup": "faster", "pagedown": "slower", "f4": "toggle_reveal", "end": "skip_to_end"}

    def __init__(self, replay: Replay, *, settings: dict[str, Any] | None = None) -> None:
        self.playback = Playback(replay)
        super().__init__(self.playback.world, replay.seed, difficulty=replay.difficulty, settings=settings, player=replay.human, ranked=False)
        self.brains = []
        self.tutorial = None
        self._autosave_at = math.inf
        self.reveal = True
        self.speed_index = 0
        self.skipping = False
        self.over = False

    def _make_view(self) -> MapView:
        return MapView(self, self.world, self.human, reveal=self.reveal)

    # -- The clock ---------------------------------------------------------------------

    @property
    def speed_factor(self) -> int:
        return SPEEDS[self.speed_index]

    @property
    def length(self) -> float:
        """Seconds of match the recording holds."""
        return self.playback.replay.end_tick * SIM_DT

    def _motion_fraction(self) -> float:
        return 1.0 if self.playback.done else self._acc / SIM_DT

    def _advance(self, dt: float) -> None:
        if self.paused or self.playback.done:
            return
        if self.skipping:
            deadline = time.monotonic() + SKIP_BUDGET
            while not self.playback.done and time.monotonic() < deadline:
                self._step()
            self._acc = 0.0
            if self.playback.done:
                self.skipping = False
            return
        self._acc += min(dt, 0.25) * self.speed_factor
        steps = 0
        while self._acc >= SIM_DT and steps < MAX_STEPS_PER_FRAME and not self.playback.done:
            self._step()
            self._acc -= SIM_DT
            steps += 1
        if steps == MAX_STEPS_PER_FRAME:
            self._acc = 0.0

    def _step(self) -> None:
        self.view.before_step()
        self.playback.step()
        if self.playback.world is not self.world:  # the match went on from a save here, and so does the playback
            self.world = self.playback.world
            self.view.reset(self.world, self.view.memory())  # the same match goes on: what the player had seen stays seen
            self.select([], quiet=True)  # and the card with it: what was selected belonged to the world before

    def _check_game_over(self) -> None:
        if self.over or not self.playback.done:
            return
        self.over = True
        self._finish(self.world.winner == self.human)
        self.game.push(ReplayEndScene(self))

    # -- What the viewer may do ------------------------------------------------------------------

    def order(self, action, *args, **kwargs):
        raise RuleError("This is a replay: its orders were given long ago")

    def open_menu(self) -> None:
        self.game.push(ReplayMenuScene(self))

    def faster(self) -> None:
        self.speed_index = min(self.speed_index + 1, len(SPEEDS) - 1)
        self.say(f"{self.speed_factor}× speed")

    def slower(self) -> None:
        self.speed_index = max(self.speed_index - 1, 0)
        self.say(f"{self.speed_factor}× speed")

    def toggle_reveal(self) -> None:
        self.reveal = not self.reveal
        self.view.set_reveal(self.reveal)
        self.say("Whole map shown" if self.reveal else f"The map as {self.player.name} saw it")

    def skip_to_end(self) -> None:
        self.skipping = True
        self.paused = False
        self.say("Skipping to the end…")

    def hint(self) -> list[tuple[str, str]]:
        return [("F3", "pause"), ("PgUp / PgDn", "speed"), ("F4", "fog on / off"), ("End", "skip to the end"), ("F10", "menu"), ("F1", "help")]

    def draw(self) -> None:
        super().draw()
        w, _ = self.game.resolution
        fog = "whole map" if self.reveal else f"as {self.player.name} saw it"
        pace = "paused" if self.paused else "skipping" if self.skipping else f"{self.speed_factor}×"
        self.draw_text(f"REPLAY · {_clock(self.world.time)} of {_clock(self.length)} · {pace} · {fog}", w - 16, 12, style="hud", color=GOLD,
                       anchor_x="right", anchor_y="top")


class ReplayMenuScene(_Overlay):
    pause_below = True
    controls = {"s": "settings", "f1": "help", "t": "back_to_title", "q": "quit"}

    def __init__(self, replay_scene: ReplayScene) -> None:
        self.replay_scene = replay_scene

    def on_enter(self) -> None:
        panel = self.panel("Replay")
        panel.add(Button("Resume", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=260))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=260))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=260))
        panel.add(Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=260))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=260))

    def settings(self) -> None:
        self.game.push(SettingsScene(self.replay_scene))

    def help(self) -> None:
        self.game.push(HelpScene(self.replay_scene.scheme))

    def back_to_title(self) -> None:
        from warband.ui.title import TitleScene

        self.game.clear_and_push(TitleScene(settings=self.replay_scene.settings))

    def quit(self) -> None:
        self.game.quit()


class ReplayEndScene(ReplayMenuScene):
    """The recording has run out: how the match ended, and whether playback got there faithfully."""

    pop_on_cancel = False
    controls = {"w": "again", "p": "profile", "t": "back_to_title", "q": "quit"}

    def on_enter(self) -> None:
        scene = self.replay_scene
        playback = scene.playback
        world = scene.world
        outcome = playback.replay.end["outcome"] if playback.replay.end is not None else "unfinished"
        winner = world.players[world.winner].name if world.winner is not None else None
        panel = self.panel("Replay over")
        line = {"victory": f"{scene.player.name} won", "defeat": f"{scene.player.name} was defeated" + (f" · {winner} prevails" if winner else ""),
                "resigned": f"{scene.player.name} resigned", "left": f"{scene.player.name} left the match here",
                "unfinished": "The recording stops here"}[outcome]
        panel.add(Label(f"{line} · {_clock(world.time)}", text_style="heading", text_color=GOOD if outcome == "victory" else MUTED))
        if playback.faithful is None:
            panel.add(Label("The recording was not finished, so there is nothing to check playback against.", text_style="sub"))
        elif playback.faithful:
            panel.add(Label("Playback matched the recording to the bit.", text_style="sub", text_color=GOOD))
        else:
            panel.add(Label("Playback drifted from the recording: the game's rules have changed since it was made.", text_style="body", text_color=BAD))
        panel.add(Row(Button("Watch again", hotkey="W", on_click=self.again, style=ACTION_BUTTON, width=200),
                      Button("Profile", hotkey="P", on_click=self.profile, style=GHOST_BUTTON, width=200), spacing=12))
        panel.add(Row(Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=200),
                      Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=200), spacing=12))

    def again(self) -> None:
        scene = self.replay_scene
        self.game.clear_and_push(ReplayScene(scene.playback.replay, settings=scene.settings))

    def profile(self) -> None:
        from warband.ui.profile_scene import ProfileScene
        from warband.ui.title import TitleScene

        settings = self.replay_scene.settings
        self.game.clear_and_push(TitleScene(settings=settings))
        self.game.push(ProfileScene(settings=settings))
