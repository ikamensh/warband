"""Dedicated campaign conversations, with a portal briefing or a painted location.

Space, Enter or a click advances. Escape skips to the next question, never past
it. Numbered answers retain their authored values and journal entries. The
mission beneath is hidden and frozen until the conversation is finished.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PIL import Image as PILImage

from saga2d import Anchor, Button, Column, Component, Image, InputEvent, KeyHints, Label, Row, Scene, Style, TextStyle, fonts
from saga2d.rendering.shapes import draw_box
from warband.story.campaign import Choice, Dialog, Item, Line, Speaker
from warband.story.journal import remember
from warband.story.briefing import BriefingChart
from warband.story.dialog_stage import DialogStage
from warband.art.production import ProductionIcon
from warband.audio.sound import play_sound
from warband.ui.style import BODY, GOLD, TEXT

PORTRAIT = 116
BOTTOM = 0
DIALOG_PANEL = Style(background_color=(10, 19, 27, 248), border_color=(156, 130, 78, 180),
                     border_width=1, padding=20, radius=0)
PORTRAIT_FRAME = Style(background_color=(15, 28, 35, 255), border_color=(166, 139, 81, 255),
                       border_width=1, padding=5, radius=3)
CONTINUE = Style(font=fonts.SEMIBOLD, font_size=15, background_color=(142, 106, 47, 255),
                 hover_color=(174, 134, 64, 255), press_color=(195, 155, 80, 255),
                 border_color=(226, 194, 121, 210), border_width=1, padding=11, radius=3)
ANSWER = Style(font=fonts.SEMIBOLD, font_size=14, background_color=(26, 46, 56, 255),
               hover_color=(43, 72, 83, 255), press_color=(65, 96, 106, 255),
               border_color=(140, 176, 177, 110), border_width=1, padding=10, radius=3)
SKIP = Style(font_size=14, background_color=(0, 0, 0, 0), hover_color=(255, 255, 255, 18), padding=10)


class _Answer(Button):
    """A real numbered button, with a fixed key gutter and the same pointer/shortcut behaviour as any button."""

    def __init__(self, label: str, number: int, width: int, on_click: Callable[[], None]) -> None:
        super().__init__(label, shortcut=str(number), on_click=on_click, style=ANSWER, width=width, height=42)
        self.add(Row(KeyHints([(str(number), "")]), Label(label, font_size=14, font=fonts.SEMIBOLD, width=width - 76),
                     spacing=12, anchor=Anchor.LEFT_CENTER, margin=(16, 0)))

    def on_draw(self) -> None:
        resolved = self._game.theme.resolve_button_style(self.style, self.state)
        draw_box(self._game.backend, *self.bounds, resolved.background_color,
                 border_color=GOLD if self.state != "normal" else resolved.border_color,
                 border_width=2 if self.state != "normal" else 1, radius=3, order=self._order)


class _Seal(Component):
    """The chronicler's small compass seal, used when no character speaks."""

    def on_draw(self) -> None:
        x, y, w, h = self.bounds
        self._game.backend.draw_circle(x + w / 2, y + h / 2, w * .28, (156, 130, 78, 90), order=self._order)
        self._game.backend.draw_polygon([(x + w / 2, y + h * .18), (x + w * .64, y + h / 2),
                                         (x + w / 2, y + h * .82), (x + w * .36, y + h / 2)], GOLD, order=self._order)


def speaker_portrait(game, speaker: Speaker) -> str | None:
    """Register authored character art once, shared by the dialogue and the linked unit's selection portraits."""
    if speaker.portrait is None:
        return None
    key = f"story.portrait.{speaker.portrait}"
    if not game.assets.has_image(key):
        with PILImage.open(Path(__file__).resolve().parents[1] / "assets" / speaker.portrait) as picture:
            game.assets.image_from_pil(key, picture)
    return key


class DialogScene(Scene):
    transparent = False
    pause_below = True
    background_color = (5, 12, 20, 255)
    controls = {("space", "return"): "advance", "escape": "skip"}

    def __init__(self, dialog: Dialog, speakers: dict[str, Speaker], vars: dict[str, Any], *,
                 on_done: Callable[[], None] | None = None, record: bool = False,
                 heading: str = "", end_label: str = "Continue",
                 backdrop: str = "campaign/scenes/millfield.webp", chart: BriefingChart | None = None) -> None:
        self.items: list[Item] = list(dialog)
        self.speakers = speakers
        self.vars = vars
        self.on_done = on_done
        self.index = 0
        self.finished = False
        self.record = record
        self.heading = heading
        self.end_label = end_label
        self._remembered: set[int] = set()
        self.backdrop = backdrop
        self.chart = chart

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
        self.stage = DialogStage(self, self.backdrop, self.chart)
        self._resolution = self.game.resolution
        self._measure_briefing()
        self._show()

    def update(self, dt: float) -> None:
        self.stage.update(dt)
        if self.game.resolution != self._resolution:
            self._resolution = self.game.resolution
            self._measure_briefing()
            self._show()

    def _show(self) -> None:
        self.ui.clear()
        item = self.current
        if item is None:
            self._finish()
            return
        if self.record and isinstance(item, Line) and self.index not in self._remembered:
            remember(self.vars, item.speaker, item.text)
            self._remembered.add(self.index)
        speaker = self.speakers.get(item.speaker) if item.speaker else None
        if item.speaker and speaker is None:
            raise KeyError(f"no speaker {item.speaker!r} in this campaign")
        self.stage.attend(speaker, self.index)
        header_width = self.game.width - 250
        header = Column(spacing=8, width=header_width, anchor=Anchor.TOP_LEFT, margin=(40, 24))
        header.add(Label("AETHER COUNCIL  /  MISSION BRIEFING" if self.chart else "WARBAND  /  CAMPAIGN CHRONICLE",
                         font_size=11, font=fonts.SEMIBOLD, text_color=GOLD, width=header_width))
        if self.heading:
            header.add(Label(self.heading, font_size=26, font=fonts.EXTRABOLD, text_color=TEXT, width=header_width, wrap=True))
        self.ui.add(header)
        spoken = [n for n, line in enumerate(self.items) if isinstance(line, Choice) or line.spoken(self.vars)]
        position = spoken.index(self.index) + 1
        self.ui.add(Label(f"{position:02}  /  {len(spoken):02}", font_size=15, text_color=GOLD,
                          anchor=Anchor.TOP_RIGHT, margin=(40, 28)))
        if self.chart and (beat := self.chart.beats[self.index]) is not None:
            self.ui.add(Label(beat.caption, font_size=12, font=fonts.SEMIBOLD, text_color=TEXT,
                              width=round(self.game.width * .38) - 64, wrap=True,
                              anchor=Anchor.TOP_RIGHT, margin=(46, 142)))
        last = not any(isinstance(following, Choice) or following.spoken(self.vars) for following in self.items[self.index+1:])
        self.panel = self._make_panel(item, speaker, last=last, height=self._briefing_height)
        self.ui.add(self.panel)

    def _measure_briefing(self) -> None:
        """Reserve one tray height for the whole briefing so its map never jumps between beats."""
        self._briefing_height: int | None = None
        if self.chart is None:
            return
        heights = []
        for item in self.items:
            speaker = self.speakers[item.speaker] if item.speaker else None
            panel = self._make_panel(item, speaker)
            self.ui.add(panel)  # attach for the game's real font metrics; this is removed before any frame draws
            heights.append(panel.get_preferred_size()[1])
            self.ui.remove(panel)
        self._briefing_height = max(heights, default=0)

    def _make_panel(self, item: Item, speaker: Speaker | None, *, last: bool = False, height: int | None = None) -> Row:
        width = self.game.width
        has_portrait = self.chart is None
        text_width = min(960, width - 2 * DIALOG_PANEL.padding - (PORTRAIT + 32 if has_portrait else 72))
        column = Column(spacing=10, width=text_width)
        column.add(Label(speaker.name if speaker else "The chronicle", font_size=20, font=fonts.EXTRABOLD,
                         text_color=GOLD, width=text_width, wrap=True))
        if isinstance(item, Line):
            column.add(Label(item.text, text_style=TextStyle(18, BODY, fonts.REGULAR), wrap=True, width=text_width))
            column.add(Row(Component(width=text_width - 352), Button(self.end_label if last else "Continue", hotkey="Space", on_click=self.advance,
                                  style=CONTINUE, width=220),
                           Button("Skip", hotkey="Esc", on_click=self.skip, style=SKIP, width=116), spacing=8))
        else:
            column.add(Label(item.prompt, font_size=18, wrap=True, width=text_width))
            answers = Column(spacing=7, width=text_width)
            answer_width = min(760, text_width)
            for number, option in enumerate(item.options, 1):
                answers.add(Row(_Answer(option.label, number, answer_width, lambda value=option.value: self.choose(value)),
                                Component(width=text_width - answer_width), spacing=0))
            column.add(answers)
        children: list[Component] = []
        if has_portrait:
            key = speaker_portrait(self.game, speaker) if speaker is not None else None
            if key is not None:
                portrait: Component = Image(key, width=PORTRAIT, height=PORTRAIT)
            else:
                portrait = (ProductionIcon(speaker.subject, speaker.player, speaker.race, size=PORTRAIT) if speaker is not None
                            else _Seal(width=PORTRAIT, height=PORTRAIT))
            framed = Column(style=PORTRAIT_FRAME)
            framed.add(portrait)
            children.append(framed)
        children.append(column)
        return Row(*children, width=width, height=height, spacing=22, anchor=Anchor.BOTTOM_CENTER,
                   margin=(0, BOTTOM), style=DIALOG_PANEL)

    def draw(self) -> None:
        # A scene pushed by this frame's input draws before the UI tree's first layout.
        # Measure its content rather than reading last frame's (or zero) panel bounds.
        _, height = self.panel.get_preferred_size()
        self.stage.draw(self.index, self.game.height - BOTTOM - height)

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
        if self.record:
            answer = next(option.label for option in item.options if option.value == value)
            remember(self.vars, item.speaker, f"{item.prompt}\nAnswer: {answer}")
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
