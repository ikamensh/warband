"""The player's profile: name, rating, record, every rated match and the replays kept of them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from saga2d import Button, Column, InputEvent, Label, Row, SaveError, Style
from warband.records.profile import OUTCOME_NAMES, Profile, RatingChange, plural
from warband.sim.races import RACES
from warband.records.replay import ReplayStore
from warband.sim.rules import Race
from warband.ui.scene import _Overlay, _clock
from warband.ui.style import ACTION_BUTTON, BAD, GHOST_BUTTON, GOLD, GOOD, MUTED, RESULTS_STYLE

PAGE = 8
#: Keys a name may be typed from, besides letters and digits.
NAME_KEYS = {"space": " ", "minus": "-", "period": ".", "apostrophe": "'", "underscore": "_"}


def outcome_color(outcome: str) -> tuple[int, int, int, int]:
    return GOOD if outcome == "victory" else BAD if outcome == "defeat" else MUTED


def form(changes: list[RatingChange], count: int = 10) -> str:
    """The last *count* results as letters, oldest first: W for a victory, L for a defeat, l for a match left."""
    return " ".join("W" if c.result.outcome == "victory" else "L" if c.result.outcome == "defeat" else "l" for c in changes[-count:])


def home_relative(path: Path) -> str:
    """*path* with the home directory shortened to ``~`` where it applies."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


class ProfileScene(_Overlay):
    """Rating and record at the top, the rated matches below, newest first; a kept replay can be watched or deleted."""

    pause_below = True
    controls = {"r": "rename", "pageup": "newer", "pagedown": "older", "w": "watch_latest"}

    def __init__(self, *, settings: dict[str, Any] | None = None, error: str = "") -> None:
        self.settings = settings
        self.error = error
        self.notice = ""
        self.page = 0
        self.profile: Profile | None = None

    def on_enter(self) -> None:
        try:
            self.profile = Profile.load(self.game.data_dir)
        except SaveError as error:
            self.error = str(error)
        self.store = ReplayStore(self.game.data_dir)
        self._build()

    def restore(self) -> None:
        """Bring the last good profile back over the damaged one."""
        try:
            self.profile = Profile.restore_backup(self.game.data_dir)
        except SaveError as error:
            self.error = str(error)
        else:
            self.error, self.notice = "", "Profile restored from its backup; the damaged file is kept as save_1.damaged.json."
        self._build()

    def _changes(self) -> list[RatingChange]:
        """Newest first."""
        return list(reversed(self.profile.history())) if self.profile is not None else []

    def _build(self) -> None:
        self.ui.clear()
        panel = self.panel("Profile")
        panel.style = RESULTS_STYLE
        if self.profile is None:
            panel.add(Label("Profile unavailable", text_style="heading", text_color=BAD))
            panel.add(Label(self.error, text_style="body", text_color=BAD, width=900, wrap=True))
            panel.add(Label("The existing profile file has been preserved.", text_style="body"))
            actions = Row(Button("Back", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=200), spacing=12)
            if Profile.has_backup(self.game.data_dir):
                actions.add(Button("Restore backup", shortcut="B", on_click=self.restore, style=GHOST_BUTTON, width=240))
                panel.add(Label("The last good profile is kept beside it; restoring keeps the damaged file as save_1.damaged.json.", text_style="sub"))
            panel.add(actions)
            panel.add(Label(f"Kept in {home_relative(self.game.data_dir)}", text_style="sub"))
            return
        profile = self.profile
        rating = profile.rating
        counts = profile.counts()
        panel.add(Row(Label(profile.name, text_style="banner", width=560), Button("Rename", shortcut="R", on_click=self.rename, style=GHOST_BUTTON, width=150),
                      spacing=12))
        panel.add(Label(f"Rating {rating}" + (" · provisional: play more rated matches to settle it" if rating.provisional else ""), text_style="heading",
                        text_color=GOLD))
        changes = self._changes()
        if not changes:
            panel.add(Label("No rated matches yet. Every match against the computer is rated when it ends, or when you leave it.",
                            text_style="body", text_color=MUTED))
        else:
            panel.add(Label(f"{plural(counts['victories'], 'victory', 'victories')} · {plural(counts['defeats'], 'defeat')} · "
                            f"{counts['left']} left early · form {form(changes[::-1])}", text_style="body"))
        rows = Column(spacing=6, width=1100)
        widths = (100, 80, 120, 60, 70, 140, 56, 180, 196)
        rows.add(Row(*(Label(name, text_style="body", width=width, height=24)
                       for name, width in zip(("Date", "Result", "Against", "Players", "Race", "Map", "Time", "Rating", "Replay"), widths)), spacing=10))
        for change in changes[self.page * PAGE:(self.page + 1) * PAGE]:
            run_id = change.result.run_id
            newest = change is changes[0]
            replay = (self._replay_controls(run_id, widths[-1], latest=newest) if self.store.exists(run_id)
                      else Label("—", text_style="sub", width=widths[-1], height=24))
            rows.add(Row(*self._cells(change, widths, newest=newest), replay, spacing=10))
        if changes:
            newest = changes[0]
            if newest.result.reason:
                rows.add(Label(f"Latest: {newest.result.reason}", text_style="sub"))
        panel.add(rows)
        total = max(1, (len(changes) + PAGE - 1) // PAGE)
        if self.notice:
            panel.add(Label(self.notice, text_style="sub", text_color=GOOD))
        panel.add(Label(f"Your profile, saves, replays and settings live in {home_relative(self.game.data_dir)}; copy that folder to back them up.",
                        text_style="sub"))
        panel.add(Row(Button("Newer", shortcut="PageUp", on_click=self.newer, style=GHOST_BUTTON, width=150, enabled=self.page > 0),
                      Label(f"Page {self.page + 1} of {total}", text_style="sub", width=120, height=24),
                      Button("Older", shortcut="PageDown", on_click=self.older, style=GHOST_BUTTON, width=150, enabled=self.page + 1 < total),
                      Label(f"Replays are kept under {self._where()}", text_style="caption", width=440, wrap=True),
                      Button("Back", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=150), spacing=12))

    def _where(self) -> str:
        """The replay directory, with the home directory as ~."""
        path, home = str(self.store.directory), str(Path.home())
        return "~" + path[len(home):] if path.startswith(home) else path

    def _cells(self, change: RatingChange, widths: tuple[int, ...], *, newest: bool) -> list[Label]:
        result = change.result
        size = f"{result.width}×{result.height} {result.theme.title()}"
        values = (result.played_at[:10], OUTCOME_NAMES[result.outcome], f"{result.difficulty.title()} {result.opponent}", str(result.opponents + 1),
                  RACES[Race(result.race)].name, size, _clock(result.seconds), str(change))
        colors = [GOLD if newest else None, outcome_color(result.outcome), None, None, None, None, None,
                  GOOD if change.delta > 0 else BAD if change.delta < 0 else None]
        return [Label(value, text_style="body", width=width, height=24, text_color=color) for value, width, color in zip(values, widths, colors)]

    def _replay_controls(self, run_id: str, width: int, *, latest: bool) -> Row:
        return Row(Button("Watch", shortcut="W" if latest else None, on_click=lambda: self.watch(run_id), style=ACTION_BUTTON, width=96),
                   Button("Delete", on_click=lambda: self.delete(run_id), style=GHOST_BUTTON, width=84), spacing=8, width=width, style=Style(padding=0))

    def watch_latest(self) -> None:
        changes = self._changes()
        if changes and self.store.exists(changes[0].result.run_id):
            self.watch(changes[0].result.run_id)

    def watch(self, run_id: str) -> None:
        from warband.ui.replay_scene import ReplayScene

        try:
            replay = self.store.load(run_id)
        except SaveError as error:
            self.error = str(error)
            self._build()
            self.ui.add(Label(self.error, text_style="body", text_color=BAD, width=900, wrap=True, margin=(0, 8)))
            return
        self.game.clear_and_push(ReplayScene(replay, settings=self.settings))

    def delete(self, run_id: str) -> None:
        self.store.delete(run_id)
        self._build()

    def rename(self) -> None:
        if self.profile is not None:
            self.game.push(NameScene(self.profile, on_done=self._build))

    def newer(self) -> None:
        if self.page > 0:
            self.page -= 1
            self._build()

    def older(self) -> None:
        if (self.page + 1) * PAGE < len(self._changes()):
            self.page += 1
            self._build()


class NameScene(_Overlay):
    """Type a name; Enter keeps it, Escape keeps the old one."""

    pause_below = True
    controls = {"return": "accept", "backspace": "erase"}

    def __init__(self, profile: Profile, *, on_done=lambda: None) -> None:
        self.profile = profile
        self.on_done = on_done
        self.text = profile.name
        self.notice = ""

    def on_enter(self) -> None:
        panel = self.panel("Your name")
        panel.add(Label(lambda: self.text + "▏", text_style="banner", width=560, height=56))
        panel.add(Label(lambda: self.notice or "Letters, digits, spaces and a few marks · up to 16 characters", text_style="sub", width=560))
        panel.add(Row(Button("Keep", hotkey="Enter", on_click=self.accept, style=ACTION_BUTTON, width=200),
                      Button("Cancel", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=200), spacing=12))

    def handle_input(self, event: InputEvent) -> bool:
        if event.type != "key_press" or event.key is None or event.ctrl or event.alt or event.meta:
            return False
        key = event.key
        if len(key) == 1 and key.isalnum():
            char = key.upper() if event.shift else key
        elif key in NAME_KEYS:
            char = "_" if key == "minus" and event.shift else NAME_KEYS[key]
        else:
            return False
        if len(self.text) < 16:
            self.text += char
            self.notice = ""
        return True

    def erase(self) -> None:
        self.text = self.text[:-1]

    def accept(self) -> None:
        try:
            self.profile.rename(self.text)
        except ValueError as error:
            self.notice = str(error)
            return
        except SaveError as error:
            self.notice = f"Could not save the name: {error}"
            return
        self.game.pop()
        self.on_done()
