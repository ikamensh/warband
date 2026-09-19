"""The dialogue overlay: who speaks, their portrait, the words, and the answers when the story asks.

One :class:`Line` at a time in a panel along the bottom of the screen; Space, Enter or a click moves on, Escape
skips to the next question or the end.  A :class:`Choice` shows its options as buttons with number keys; the answer
goes into the mission's variables under the choice's key, so later lines can depend on it.  The scene below is
paused while the panel is up.
"""

from __future__ import annotations

from typing import Any, Callable

from saga2d import Anchor, Button, Column, Component, InputEvent, KeyHints, Label, Row, Scene
from warband.story.campaign import Choice, Dialog, Item, Line, Speaker
from warband.art.production import ProductionIcon
from warband.audio.sound import play_sound
from warband.ui.style import ACTION_BUTTON, GHOST_BUTTON, MUTED, OVERLAY_STYLE

PORTRAIT = 104
PANEL_WIDTH = 980
BOTTOM = 44


class DialogScene(Scene):
    transparent = True
    pause_below = True
    controls = {("space", "return"): "advance", "escape": "skip"}

    def __init__(self, dialog: Dialog, speakers: dict[str, Speaker], vars: dict[str, Any], *,
                 on_done: Callable[[], None] | None = None) -> None:
        self.items: list[Item] = list(dialog)
        self.speakers = speakers
        self.vars = vars
        self.on_done = on_done
        self.index = 0
        self.finished = False

    @property
    def current(self) -> Item | None:
        """The item to show: lines whose condition does not hold (yet, or any more) are passed over."""
        while self.index < len(self.items):
            item = self.items[self.index]
            if isinstance(item, Choice) or item.spoken(self.vars):
                return item
            self.index += 1
        return None

    def on_enter(self) -> None:
        self._show()

    def _show(self) -> None:
        self.ui.clear()
        item = self.current
        if item is None:
            self._finish()
            return
        width = min(PANEL_WIDTH, self.game.width - 40)
        speaker = self.speakers.get(item.speaker) if item.speaker else None
        if item.speaker and speaker is None:
            raise KeyError(f"no speaker {item.speaker!r} in this campaign")
        text_width = width - 2 * OVERLAY_STYLE.padding - PORTRAIT - 18
        column = Column(spacing=10, width=text_width)
        column.add(Label(speaker.name if speaker is not None else "", text_style="title", width=text_width))
        if isinstance(item, Line):
            column.add(Label(item.text, text_style="body", wrap=True, width=text_width, text_color=None if speaker is not None else MUTED))
            column.add(Row(Button("Continue", hotkey="Space", on_click=self.advance, style=ACTION_BUTTON, width=150),
                           KeyHints([("Esc", "skip")]), spacing=14))
        else:
            column.add(Label(item.prompt, text_style="body", wrap=True, width=text_width))
            answers = Row(spacing=10)
            for number, option in enumerate(item.options, 1):
                answers.add(Button(option.label, shortcut=str(number), on_click=lambda value=option.value: self.choose(value),
                                   style=ACTION_BUTTON if number == 1 else GHOST_BUTTON, width=max(180, (text_width - 10 * (len(item.options) - 1)) // len(item.options))))
            column.add(answers)
        portrait: Component = (ProductionIcon(speaker.subject, speaker.player, speaker.race, size=PORTRAIT) if speaker is not None
                               else Component(width=PORTRAIT, height=PORTRAIT))
        self.ui.add(Row(portrait, column, spacing=18, anchor=Anchor.BOTTOM_CENTER, margin=(0, BOTTOM), style=OVERLAY_STYLE))

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (4, 6, 12, 130))

    def handle_input(self, event: InputEvent) -> bool:
        if event.type == "click" and event.button == "left" and isinstance(self.current, Line):
            self.advance()
            return True
        return False

    def advance(self) -> None:
        if isinstance(self.current, Choice):
            return  # a question wants an answer, not a nod
        play_sound("button")
        self.index += 1
        self._show()

    def choose(self, value: Any) -> None:
        item = self.current
        if not isinstance(item, Choice):
            return
        self.vars[item.key] = value
        play_sound("button")
        self.index += 1
        self._show()

    def skip(self) -> None:
        """Jump to the next question, or to the end when there is none."""
        if isinstance(self.current, Choice):
            return
        while self.index < len(self.items) and not isinstance(self.items[self.index], Choice):
            self.index += 1
        self._show()

    def _finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.game.pop()
        if self.on_done is not None:
            self.on_done()
