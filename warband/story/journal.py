"""The current mission's briefing and witnessed conversation, kept beside its saved script.

The history contains only lines actually displayed and answers actually chosen. Reading the
initial briefing never replays a choice or mutates the mission. Older saves still have that
briefing even when they predate conversation recording.
"""

from __future__ import annotations

from typing import Any

from saga2d import Anchor, Button, Column, Component, Image, KeyHints, Label, Row, Scene
from warband.art.production import ProductionIcon
from warband.story.campaign import Line, Run, Speaker
from warband.ui.style import ACTION_BUTTON, GHOST_BUTTON, MUTED, OVERLAY_STYLE

JOURNAL_KEY = "story_journal"


def remember(variables: dict[str, Any], speaker: str, text: str) -> None:
    """Append one witnessed line or selected answer; Run's ordinary save carries the history."""
    variables.setdefault(JOURNAL_KEY, []).append({"speaker": speaker, "text": text})


class JournalScene(Scene):
    transparent = True
    pause_below = True
    controls = {"left": "previous", "right": "next", "home": "first", "end": "last",
                "b": "briefing", "e": "latest", "escape": "back"}

    def __init__(self, run: Run, speakers: dict[str, Speaker]) -> None:
        self.run = run
        self.speakers = speakers
        self.history = run.vars.get(JOURNAL_KEY, [])
        self.introduction = [{"speaker": line.speaker, "text": line.text} for line in run.mission.briefing
                             if isinstance(line, Line) and line.spoken(run.vars)]
        self.entries = self.history if self.history else self.introduction
        self.mode = "History" if self.history else "Briefing"
        self.index = max(0, len(self.entries) - 1) if self.history else 0

    def on_enter(self) -> None:
        self._show()

    def _show(self) -> None:
        from warband.story.dialog import PORTRAIT, speaker_portrait

        self.ui.clear()
        width = min(980, self.game.width - 40)
        text_width = width - 2 * OVERLAY_STYLE.padding - PORTRAIT - 18
        panel = Column(spacing=12, anchor=Anchor.CENTER, style=OVERLAY_STYLE)
        panel.add(Label("Mission journal", text_style="title"))
        panel.add(Label(self.run.mission.title, text_style="sub"))
        entry = self.entries[self.index] if self.entries else {"speaker": "", "text": "No conversation recorded yet."}
        speaker = self.speakers[entry["speaker"]] if entry["speaker"] else None
        key = speaker_portrait(self.game, speaker) if speaker is not None else None
        portrait = (Image(key, width=PORTRAIT, height=PORTRAIT) if key is not None else
                    ProductionIcon(speaker.subject, speaker.player, speaker.race, size=PORTRAIT) if speaker is not None else
                    Component(width=PORTRAIT, height=PORTRAIT))
        text = Column(spacing=10, width=text_width)
        text.add(Label(speaker.name if speaker is not None else "", text_style="heading", width=text_width))
        text.add(Label(entry["text"], text_style="body", width=text_width, wrap=True,
                       text_color=None if speaker is not None else MUTED))
        panel.add(Row(portrait, text, spacing=18))
        panel.add(Label(f"{self.mode} · {self.index + 1 if self.entries else 0} / {len(self.entries)}", text_style="sub"))
        previous = Button("Previous", shortcut="Left", on_click=self.previous, style=GHOST_BUTTON, width=160)
        previous.enabled = self.index > 0
        next_button = Button("Next", shortcut="Right", on_click=self.next, style=GHOST_BUTTON, width=160)
        next_button.enabled = self.index + 1 < len(self.entries)
        panel.add(Row(previous, next_button,
                      Button("Briefing", shortcut="B", on_click=self.briefing, style=GHOST_BUTTON, width=150),
                      Button("Latest", shortcut="E", on_click=self.latest, style=GHOST_BUTTON, width=140),
                      Button("Back", hotkey="Esc", on_click=self.back, style=ACTION_BUTTON, width=120), spacing=8))
        panel.add(KeyHints([("Home / End", "first / last"), ("Esc", "return to mission")]))
        self.ui.add(panel)

    def draw(self) -> None:
        self.draw_rect(0, 0, *self.game.resolution, (4, 6, 12, 150))

    def previous(self) -> None:
        self.index = max(0, self.index - 1)
        self._show()

    def next(self) -> None:
        self.index = min(max(0, len(self.entries) - 1), self.index + 1)
        self._show()

    def first(self) -> None:
        self.index = 0
        self._show()

    def last(self) -> None:
        self.index = max(0, len(self.entries) - 1)
        self._show()

    def briefing(self) -> None:
        self.entries, self.mode, self.index = self.introduction, "Briefing", 0
        self._show()

    def latest(self) -> None:
        self.entries, self.mode = self.history, "History"
        self.last()

    def back(self) -> None:
        self.game.pop()
