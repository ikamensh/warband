"""Title screen and the match setup overlay.

The title drifts over a fully revealed map so the game shows what it is
before a button is pressed.  Every option has a hotkey.
"""

from __future__ import annotations

import random
from typing import Any

from saga2d import Anchor, Button, Camera, Column, Label, Row, Scene
from warband import mapgen
from warband.scene import HelpScene, load_game, new_game
from warband.sound import play_sound
from warband.style import ACTION_BUTTON, GHOST_BUTTON, MENU_BUTTON, OVERLAY_STYLE
from warband.textures import TILE
from warband.view import MapView, to_world

PLAYER_COUNTS = (2, 3, 4)
OPTION_WIDTH = 170
DRIFT_SECONDS = 24.0


class TitleScene(Scene):
    background_color = (8, 10, 14, 255)
    controls = {("n", "return"): "new_game", "c": "continue_game", "h": "how_to_play", "q": "quit"}

    def __init__(self, *, size: str = "Medium", players: int = 2, settings: dict[str, Any] | None = None) -> None:
        self.size = size
        self.players = players
        self.settings = settings
        self.time = 0.0
        self._stop = 0

    def on_enter(self) -> None:
        seed = random.randrange(1, 10_000)
        width, height = mapgen.SIZES["Medium"]
        self.backdrop = mapgen.generate(seed=seed, width=width, height=height, players=2)
        self.backdrop.reveal_all(0)
        self.view = MapView(self, self.backdrop, 0)
        w, h = self.game.resolution
        self.camera = Camera((w, h), world_bounds=(TILE, TILE, width * TILE - TILE, height * TILE - TILE), zoom=1.3, min_zoom=1.3, max_zoom=1.3)
        self._stops = [to_world(b.center) for b in self.backdrop.buildings.values()]
        self.camera.center_on(*self._stops[0])
        self._drift()
        self._build_menu()

    def _drift(self) -> None:
        self._stop = (self._stop + 1) % len(self._stops)
        self.camera.pan_to(*self._stops[self._stop], duration=DRIFT_SECONDS)
        self.after(DRIFT_SECONDS, self._drift)

    def _build_menu(self) -> None:
        has_save = self.game.save_manager.load(1) is not None
        menu = Column(spacing=10, anchor=Anchor.CENTER, margin=0)
        menu.add(Label("", height=150))
        menu.add(Button("New game", hotkey="N", on_click=self.new_game, style=ACTION_BUTTON, width=300))
        cont = Button("Continue", hotkey="C", on_click=self.continue_game, style=MENU_BUTTON, width=300)
        cont.enabled = has_save
        menu.add(cont)
        menu.add(Button("How to play", hotkey="H", on_click=self.how_to_play, style=MENU_BUTTON, width=300))
        menu.add(Button("Quit", hotkey="Q", on_click=self.quit, style=MENU_BUTTON, width=300))
        menu.add(Label("Continue resumes save slot 1" if has_save else "No saved game yet — F5 saves during play", text_style="caption"))
        self.ui.add(menu)
        self.ui.add(Label("Every command has a hotkey — the keycaps show them · F1 in game for help", text_style="caption", anchor=Anchor.BOTTOM_CENTER, margin=12))

    def update(self, dt: float) -> None:
        self.time += dt
        self.view.sync(dt)

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (6, 8, 14, 150))
        cy = h / 2 - 120
        for spread, alpha in ((3, 50), (2, 80)):
            self.draw_text("WARBAND", w / 2 + spread, cy + spread, style="hero", color=(0, 0, 0, alpha), anchor_x="center", anchor_y="center")
        self.draw_text("WARBAND", w / 2, cy, style="hero", anchor_x="center", anchor_y="center")
        self.draw_text("Gather · Build · Train · Conquer", w / 2, cy + 60, style="hero_sub", anchor_x="center", anchor_y="center")

    def sfx(self, name: str) -> None:
        if self.settings is None or self.settings["sfx"] > 0:
            play_sound(name)

    def new_game(self) -> None:
        self.sfx("button")
        self.game.push(NewGameScene(self))

    def continue_game(self) -> None:
        save = self.game.save_manager.load(1)
        if save is None:
            self.sfx("error")
            return
        self.sfx("button")
        self.game.clear_and_push(load_game(save["state"], settings=self.settings))

    def how_to_play(self) -> None:
        self.sfx("button")
        self.game.push(HelpScene())

    def quit(self) -> None:
        self.game.quit()


class NewGameScene(Scene):
    """Map size, number of players, the seed, then Start."""

    transparent = True
    pause_below = False
    pop_on_cancel = True
    controls = {"s": "size_small", "m": "size_medium", "l": "size_large", "2": "players_2", "3": "players_3", "4": "players_4",
                "r": "reroll", ("return", "space"): "start"}

    def __init__(self, title: TitleScene) -> None:
        self.title = title
        self.size = title.size
        self.players = title.players
        self.seed = random.randrange(1, 10_000)
        self._size_buttons: dict[str, Button] = {}
        self._player_buttons: dict[int, Button] = {}

    def on_enter(self) -> None:
        panel = Column(spacing=12, anchor=Anchor.CENTER, style=OVERLAY_STYLE)
        panel.add(Label("New game", text_style="title"))
        size_row = Row(Label("Map size", text_style="body", width=90), spacing=8)
        for name, (w, h) in mapgen.SIZES.items():
            button = Button(f"{name} {w}×{h}", hotkey=name[0], on_click=lambda n=name: self.set_size(n), style=GHOST_BUTTON, width=OPTION_WIDTH)
            self._size_buttons[name] = button
            size_row.add(button)
        panel.add(size_row)
        player_row = Row(Label("Players", text_style="body", width=90), spacing=8)
        for count in PLAYER_COUNTS:
            button = Button(f"{count}  (you + {count - 1} AI)", hotkey=str(count), on_click=lambda c=count: self.set_players(c), style=GHOST_BUTTON, width=OPTION_WIDTH)
            self._player_buttons[count] = button
            player_row.add(button)
        panel.add(player_row)
        panel.add(Row(Label(lambda: f"Seed {self.seed}", text_style="body", width=90 + 8 + OPTION_WIDTH),
                      Button("Reroll", hotkey="R", on_click=self.reroll, style=GHOST_BUTTON, width=OPTION_WIDTH), spacing=8))
        panel.add(Row(Button("Start", hotkey="Enter", on_click=self.start, style=ACTION_BUTTON, width=2 * OPTION_WIDTH + 8),
                      Button("Back", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=OPTION_WIDTH), spacing=8))
        self.ui.add(panel)
        self._restyle()

    def _restyle(self) -> None:
        for name, button in self._size_buttons.items():
            button.style = ACTION_BUTTON if name == self.size else GHOST_BUTTON
        for count, button in self._player_buttons.items():
            button.style = ACTION_BUTTON if count == self.players else GHOST_BUTTON

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (4, 6, 12, 140))

    def set_size(self, name: str) -> None:
        self.size = name
        self.title.sfx("button")
        self._restyle()

    def set_players(self, count: int) -> None:
        self.players = count
        self.title.sfx("button")
        self._restyle()

    def size_small(self) -> None:
        self.set_size("Small")

    def size_medium(self) -> None:
        self.set_size("Medium")

    def size_large(self) -> None:
        self.set_size("Large")

    def players_2(self) -> None:
        self.set_players(2)

    def players_3(self) -> None:
        self.set_players(3)

    def players_4(self) -> None:
        self.set_players(4)

    def reroll(self) -> None:
        self.seed = random.randrange(1, 10_000)
        self.title.sfx("button")

    def start(self) -> None:
        self.title.sfx("button")
        width, height = mapgen.SIZES[self.size]
        self.game.clear_and_push(new_game(self.seed, width=width, height=height, players=self.players, settings=self.title.settings))
