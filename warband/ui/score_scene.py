"""Local top tens, accessible from the title and the finished battle."""

from __future__ import annotations

from saga2d import Button, Column, Label, Row, SaveError, Style
from warband.sim import mapgen
from warband.sim.races import RACES
from warband.sim.rules import Difficulty, Race
from warband.ui.scene import _Overlay, _clock
from warband.records.scores import HighScores
from warband.ui.style import BAD, GHOST_BUTTON, GOLD, MUTED, RESULTS_STYLE


class HighScoreScene(_Overlay):
    """Ten best finishes per difficulty, map size and player count; D, M and P cycle the board."""

    pause_below = True
    controls = {"d": "cycle_difficulty", "m": "cycle_size", "p": "cycle_players"}

    def __init__(self, *, difficulty: Difficulty = Difficulty.MEDIUM, size: tuple[int, int] = (48, 40), players: int = 2,
                 run_id: str | None = None, error: str = "") -> None:
        self.difficulty, self.size, self.players = difficulty, size, players
        self.run_id, self.error = run_id, error

    def on_enter(self) -> None:
        self.entries = []
        try:
            self.entries = HighScores(self.game.data_dir).load()
        except SaveError as error:
            self.error = str(error)
        self.sizes = list(dict.fromkeys([*(mapgen.dimensions(n, self.players) for n in mapgen.SIZES),
                                         *((e.width, e.height) for e in self.entries), self.size]))
        self._build()

    def _build(self) -> None:
        self.ui.clear()
        panel = self.panel("High scores")
        panel.style = RESULTS_STYLE
        panel.add(Label("Local top 10 · best finish per match · ties favour the faster battle", text_style="body"))
        size_name = mapgen.size_name(*self.size, self.players)
        panel.add(Row(Button(f"AI: {self.difficulty.value.title()}", hotkey="D", on_click=self.cycle_difficulty, style=GHOST_BUTTON, width=230),
                      Button(f"Map: {size_name}", hotkey="M", on_click=self.cycle_size, style=GHOST_BUTTON, width=230),
                      Button(f"{self.players} players", hotkey="P", on_click=self.cycle_players, style=GHOST_BUTTON, width=230), spacing=12))
        rows = Column(spacing=5, width=960)
        widths = (46, 90, 80, 80, 80, 60, 100, 120, 120)

        def row(values, *, current=False):
            return Row(*(Label(value, text_style="body", width=width, height=24, text_color=GOLD if current else None)
                         for value, width in zip(values, widths)), spacing=12,
                       style=Style(background_color=(255, 214, 110, 18)) if current else None)

        rows.add(row(("Rank", "Warband", "Race", "Points", "Result", "Time", "Land", "Seed", "Date")))
        board = (self.difficulty.value, *self.size, self.players)
        entries = [e for e in self.entries if e.board == board]
        if self.error:
            rows.add(Label("High scores unavailable", text_style="heading", text_color=BAD))
            rows.add(Label(self.error, text_style="body", text_color=BAD, width=960, wrap=True))
            rows.add(Label("The existing score file has been preserved.", text_style="body"))
        elif not entries:
            rows.add(Label("No scores for these settings yet.", text_style="heading", height=60))
            rows.add(Label("Finish a battle to set the first record.", text_style="body", text_color=MUTED))
        else:
            for rank, entry in enumerate(entries, 1):
                rows.add(row((str(rank), entry.player, RACES[Race(entry.race)].name, f"{entry.score:,}", "Victory" if entry.victory else "Defeat",
                              _clock(entry.seconds), entry.theme.title(), str(entry.seed), entry.completed_at[:10]),
                             current=entry.run_id == self.run_id))
        panel.add(rows)
        panel.add(Label("Gold and lumber count equally. Unspent resources earn no points.", text_style="sub"))
        panel.add(Button("Back", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=200))

    def cycle_difficulty(self) -> None:
        values = list(Difficulty)
        self.difficulty = values[(values.index(self.difficulty) + 1) % len(values)]
        self._build()

    def cycle_size(self) -> None:
        self.size = self.sizes[(self.sizes.index(self.size) + 1) % len(self.sizes)]
        self._build()

    def cycle_players(self) -> None:
        counts = mapgen.SEAT_COUNTS
        self.players = counts[(counts.index(self.players) + 1) % len(counts)] if self.players in counts else counts[0]
        self._build()
