"""Title screen and the match setup overlay.

The title drifts over a fully revealed map so the game shows what it is
before a button is pressed.  Every option has a hotkey.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np
from PIL import Image as PilImage

from saga2d import Anchor, Button, Camera, Column, Image, Label, Row, SaveError, Scene
from warband.sim import mapgen
from warband.sim.model import World
from warband.sim.races import RACES
from warband.brains.ai import DIFFICULTY_ELO, DIFFICULTY_NOTES
from warband.records.profile import OUTCOME_NAMES, Profile, plural
from warband.sim.rules import BuildingType, Difficulty, Layout, MapTheme, Race
from warband.ui.controls import DEFAULT, SCHEMES
from warband.ui.scene import SAVE_SLOTS, CodexScene, HelpScene, SaveBrowserScene, codex_world, fair_map, load_game, new_game
from warband.audio.sound import play_music, play_sound
from warband.ui.style import ACTION_BUTTON, BAD, GHOST_BUTTON, GOLD, GOOD, MENU_BUTTON, MUTED, OVERLAY_STYLE, PANEL_STYLE
from warband.art.textures import TILE
from warband.ui.view import NEUTRAL_MINIMAP, MapView, minimap_terrain, to_world

OPTION_WIDTH = 180
SIZE_WIDTH = 86  # six sizes on one row, as wide as three options: a second row of them stood the panel off a 680-pixel screen
COUNT_WIDTH = 72  # seven seat counts share the width three options take
RACE_WIDTH = 125
#: Only the three sizes that shipped have a letter of their own; the rest are reached with the
#: stepper keys, because the screen's free letters ran out before the sizes did.
SIZE_KEYS = {"Small": "S", "Medium": "M", "Large": "L"}
RACE_KEYS = {Race.HUMAN: "U", Race.ORC: "O", Race.ELF: "V", Race.DWARF: "A"}
#: Not the first letter: Medium and Master share one, and M is already the map size.
DIFFICULTY_KEYS = {Difficulty.EASY: "E", Difficulty.MEDIUM: "N", Difficulty.HARD: "H", Difficulty.MASTER: "T", Difficulty.GRANDMASTER: "X"}
NOTE_WIDTH = 90 + 8 + 3 * OPTION_WIDTH + 2 * 8  # a note under a row of options spans the row and wraps beside the preview
PREVIEW_KEY = "newgame.preview"
PREVIEW_BOX = (320, 240)  # the preview fits this many pixels: whole pixels per tile, as many as fit
LAYOUT_KEYS: dict[Layout | None, str] = {Layout.PLAINS: "P", Layout.FOREST: "F", Layout.CROSSINGS: "C", Layout.KLONDIKE: "K", Layout.BASTION: "B", None: "Y"}


def preview_image(world: World) -> PilImage.Image:
    """A small picture of *world*: terrain, a 3x3 block per start hall in the
    owner's colour and every gold deposit in gold, at as many whole pixels per tile as fit ``PREVIEW_BOX``."""
    img = minimap_terrain(world)
    for b in world.buildings.values():
        if b.type is BuildingType.TOWN_HALL and b.player is not None:
            img[b.y:b.y + b.size, b.x:b.x + b.size] = world.players[b.player].color
        elif b.info.mine is not None:
            img[b.y:b.y + b.size, b.x:b.x + b.size] = NEUTRAL_MINIMAP
    scale = min(PREVIEW_BOX[0] // world.width, PREVIEW_BOX[1] // world.height)
    pixels = np.repeat(np.repeat(img.clip(0, 255).astype(np.uint8), scale, 0), scale, 1)
    return PilImage.fromarray(pixels, "RGB")
DRIFT_SECONDS = 24.0
CARD_WIDTH = 400
RECENT = 4  # results shown on the title card


class TitleScene(Scene):
    background_color = (8, 10, 14, 255)
    controls = {("n", "return"): "new_game", "c": "continue_game", "l": "load_game", "p": "profile_screen", "b": "high_scores", "h": "how_to_play", "q": "quit"}

    def __init__(self, *, size: str = "Medium", players: int = 2, difficulty: Difficulty = Difficulty.MEDIUM, theme: MapTheme = MapTheme.SUMMER,
                 race: Race = Race.HUMAN, layout: Layout | None = None, settings: dict[str, Any] | None = None) -> None:
        """*layout* ``None`` is Any: each seed draws its own."""
        self.size = size
        self.players = players
        self.difficulty = difficulty
        self.theme = theme
        self.race = race
        self.layout = layout
        self.settings = settings
        self.time = 0.0
        self._stop = 0
        self.notice = ""
        self.profile: Profile | None = None
        self.profile_error = ""

    def on_enter(self) -> None:
        try:
            self.profile = Profile.load(self.game.data_dir)
        except SaveError as error:
            self.profile, self.profile_error = None, str(error)
        width, height = mapgen.SIZES["Medium"]
        _, self.backdrop = fair_map(mapgen.fresh_seed(), width, height, 2, theme=random.choice(list(MapTheme)))
        self.backdrop.reveal_all(0)
        self.view = MapView(self, self.backdrop, 0)
        w, h = self.game.resolution
        self.camera = Camera((w, h), world_bounds=(TILE, TILE, width * TILE - TILE, height * TILE - TILE), zoom=1.3, min_zoom=1.3, max_zoom=1.3)
        self._stops = [to_world(b.center) for b in self.backdrop.buildings.values()]
        self.camera.center_on(*self._stops[0])
        self._drift()
        self._build_menu()
        play_music("title")

    def _drift(self) -> None:
        self._stop = (self._stop + 1) % len(self._stops)
        self.camera.pan_to(*self._stops[self._stop], duration=DRIFT_SECONDS)
        self.after(DRIFT_SECONDS, self._drift)

    def _newest_save(self) -> int | str | None:
        """The slot saved most recently, whatever kind it is."""
        entries = [e for e in self.game.save_manager.list_slots(SAVE_SLOTS, names=("quick", "autosave", "campaign")) if e is not None and "error" not in e]
        return max(entries, key=lambda e: e["timestamp"])["slot"] if entries else None

    def _build_menu(self) -> None:
        """The menu on the left, the player's card on the right, under the title."""
        newest = self._newest_save()
        menu = Column(spacing=10, margin=0)
        menu.add(Button("New game", hotkey="N", on_click=self.new_game, style=ACTION_BUTTON, width=300))
        menu.add(Button("Campaign", shortcut="A", on_click=self.campaign, style=MENU_BUTTON, width=300))
        cont = Button("Continue", hotkey="C", on_click=self.continue_game, style=MENU_BUTTON, width=300)
        cont.enabled = newest is not None
        menu.add(cont)
        menu.add(Button("Multiplayer", shortcut="M", on_click=self.multiplayer, style=MENU_BUTTON, width=300))
        menu.add(Button("Load game", hotkey="L", on_click=self.load_game, style=MENU_BUTTON, width=300))
        menu.add(Button("High scores", hotkey="B", on_click=self.high_scores, style=MENU_BUTTON, width=300))
        # The two screens that explain the game share a row: a ninth full-width button pushed the title off a 680 px window.
        menu.add(Row(Button("How to play", hotkey="H", on_click=self.how_to_play, style=MENU_BUTTON, width=180),
                     Button("Codex", shortcut="F2", on_click=self.codex, style=MENU_BUTTON, width=112), spacing=8))
        menu.add(Button("Quit", hotkey="Q", on_click=self.quit, style=MENU_BUTTON, width=300))
        where = f"slot {newest}" if isinstance(newest, int) else "the campaign mission" if newest == "campaign" else f"the {newest}" if newest else None
        menu.add(Label(f"Continue resumes {where}" if where else "No saved game yet — the match autosaves every two minutes", text_style="caption"))
        self._block = Column(Label("", height=150), Row(menu, self._card(), spacing=36), spacing=0, anchor=Anchor.CENTER, margin=0)
        self.ui.add(self._block)
        self.ui.add(Label("Every command has a hotkey — the keycaps show them · F1 in game for help", text_style="caption", anchor=Anchor.BOTTOM_CENTER, margin=12))

    def _card(self) -> Column:
        """Who is playing and how they stand: name, rating, record and the last few results."""
        card = Column(spacing=8, margin=0, width=CARD_WIDTH, style=PANEL_STYLE)
        if self.profile is None:
            card.add(Label("Profile unavailable", text_style="heading", text_color=BAD))
            card.add(Label(self.profile_error, text_style="sub", text_color=BAD, width=CARD_WIDTH - 24, wrap=True))
            card.add(Label("The profile file has been preserved.", text_style="sub"))
            return card
        profile = self.profile
        rating = profile.rating
        counts = profile.counts()
        card.add(Label(profile.name, text_style="title"))
        card.add(Label(f"Rating {rating}" + (" · provisional" if rating.provisional else ""), text_style="heading", text_color=GOLD))
        history = profile.history()
        if not history:
            card.add(Label("No rated matches yet. Beat the computer to earn a rating; leaving a match early counts against it.",
                           text_style="sub", width=CARD_WIDTH - 24, wrap=True))  # no hard break: the wrapper orphans what is left of the line
        else:
            card.add(Label(f"{plural(counts['victories'], 'victory', 'victories')} · {plural(counts['defeats'], 'defeat')} · {counts['left']} left early",
                           text_style="body"))
            for change in reversed(history[-RECENT:]):
                result = change.result
                color = GOOD if change.delta > 0 else BAD if change.delta < 0 else MUTED
                card.add(Row(Label(f"{change.delta:+d}", text_style="body", text_color=color, width=48),
                             Label(f"{OUTCOME_NAMES[result.outcome]} · {result.difficulty.title()} · {result.opponents + 1} players · {result.played_at[:10]}",
                                   text_style="sub", width=CARD_WIDTH - 90),
                             spacing=6))
        card.add(Button("Profile & replays", hotkey="P", on_click=self.profile_screen, style=MENU_BUTTON, width=CARD_WIDTH - 24))
        return card

    def update(self, dt: float) -> None:
        self.time += dt
        self.view.sync(dt)

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (6, 8, 14, 150))
        # The UI's bounds are laid out after draw(), so measure the centred block
        # here instead of using the previous frame's (initially empty) bounds.
        cy = (h - self._block.get_preferred_size()[1]) / 2 + 58
        for spread, alpha in ((3, 50), (2, 80)):
            self.draw_text("WARBAND", w / 2 + spread, cy + spread, style="hero", color=(0, 0, 0, alpha), anchor_x="center", anchor_y="center")
        self.draw_text("WARBAND", w / 2, cy, style="hero", anchor_x="center", anchor_y="center")
        self.draw_text("Gather · Build · Train · Conquer", w / 2, cy + 70, style="hero_sub", anchor_x="center", anchor_y="center")
        if self.notice:
            self.draw_text(self.notice, w / 2, h - 60, style="hud", color=(240, 130, 110, 255), anchor_x="center", anchor_y="center")

    def sfx(self, name: str) -> None:
        if self.settings is None or self.settings["sfx"] > 0:
            play_sound(name)

    def room_refusal(self) -> str | None:
        """Why a room cannot be made of New game's settings, or ``None``.

        Playing against other people is the game engine's to size, not Warband's: a LAN host takes
        one guest (``saga2d.network.MatchHost``) and an online room holds what every client declares
        it can join (``saga2d.online.SEATS``, four in the release Warband pins, which the room server
        enforces).  Sixteen seats are a match against the computer on one machine.  Saying so is
        better than quietly seating four of them.  See docs/warband-maps.md, "Sixteen seats online"."""
        from warband.online.authority import ONLINE_SEATS, ONLINE_SIZE
        width, height = mapgen.dimensions(self.size, self.players)
        if self.players > ONLINE_SEATS:
            return (f"An online room seats {ONLINE_SEATS} and a LAN host 2, not {self.players}: how many can play "
                    f"together is the game engine's limit, not Warband's. Play {self.players} against the computer, "
                    f"or set Players to {ONLINE_SEATS} or fewer for multiplayer.")
        if (width, height) > ONLINE_SIZE:
            return (f"A room plays maps up to {ONLINE_SIZE[0]}×{ONLINE_SIZE[1]}, not {width}×{height}. "
                    f"Choose Large or smaller for multiplayer.")
        return None

    def multiplayer(self) -> None:
        from saga2d import MatchMenu
        from warband.online.authority import WarbandMatch
        from warband.ui.multiplayer import NetworkGameScene
        refused = self.room_refusal()
        if refused is not None:
            self.notice = refused
            self.sfx("error")
            return
        # The room's creator leads the race chosen under New game; the others' are drawn from the seed.  An online
        # room has New game's player count; a LAN host has two seats.
        seats = self.players
        lan = self.map_size(2)
        room = self.map_size(seats)
        self.notice = ""
        self.game.push(MatchMenu("Warband multiplayer", "warband-v2",
                                lambda: WarbandMatch(self.fair_seed(2), *lan, self.theme, races=(self.race, None),
                                                     layout=None if self.room_layout(2) == 'any' else Layout(self.room_layout(2))),
                                lambda session, match: NetworkGameScene(session, match, settings=self.settings),
                                create_options=lambda: {'seed': self.fair_seed(seats), 'width': room[0], 'height': room[1],
                                                        'theme': self.theme.value, 'players': seats,
                                                        'races': [self.race.value] + [None] * (seats - 1),
                                                        'layout': self.room_layout(seats)}))

    def map_size(self, players: int) -> tuple[int, int]:
        """The map New game's size makes for *players* seats, moved to a size that seats them if it does not."""
        size = self.size if self.size in mapgen.sizes_for(players) else mapgen.sizes_for(players)[0]
        return mapgen.dimensions(size, players)

    def room_layout(self, players: int) -> str:
        """The layout a room of *players* asks for: ``any`` where the chosen one does not fit their grid."""
        width, height = self.map_size(players)
        return self.layout.value if self.layout in mapgen.layouts_for(width, height, players) else 'any'

    def fair_seed(self, players: int) -> int:
        """A fresh seed that makes a fair map of New game's settings for *players* seats, the room's creator first."""
        width, height = self.map_size(players)
        chosen = self.room_layout(players)
        return fair_map(mapgen.fresh_seed(), width, height, players, theme=self.theme, races=[self.race] + [None] * (players - 1),
                        layout=None if chosen == 'any' else Layout(chosen))[0]

    def new_game(self) -> None:
        self.sfx("button")
        self.game.push(NewGameScene(self))

    def campaign(self) -> None:
        from warband.story.campaign_scene import CampaignScene

        self.sfx("button")
        self.game.push(CampaignScene(self.settings))

    def continue_game(self) -> None:
        newest = self._newest_save()
        if newest is None:
            self.sfx("error")
            return
        self.load_slot(newest)

    def load_game(self) -> None:
        self.sfx("button")
        self.game.push(SaveBrowserScene(self.game, "load", on_pick=self.load_slot))

    def load_slot(self, slot: int | str) -> None:
        try:
            save = self.game.save_manager.load(slot)
            if save is None:
                raise SaveError("that slot is empty")
            scene = load_game(save["state"], settings=self.settings)
        except SaveError as exc:
            self.sfx("error")
            self.notice = f"Could not load: {exc}"
            return
        self.sfx("button")
        self.game.clear_and_push(scene)

    def how_to_play(self) -> None:
        self.sfx("button")
        self.game.push(HelpScene(SCHEMES[self.settings["controls"] if self.settings is not None else DEFAULT]))

    def codex(self) -> None:
        """Every unit, building and upgrade before a match is started, for the race chosen under New game."""
        self.sfx("button")
        self.game.push(CodexScene(codex_world(self.race), 0, in_match=False))

    def profile_screen(self) -> None:
        from warband.ui.profile_scene import ProfileScene

        self.sfx("button")
        self.game.push(ProfileScene(settings=self.settings, error=self.profile_error))

    def high_scores(self) -> None:
        from warband.ui.score_scene import HighScoreScene

        self.sfx("button")
        self.game.push(HighScoreScene(difficulty=self.difficulty, size=mapgen.SIZES[self.size], players=self.players))

    def quit(self) -> None:
        self.game.quit()


class NewGameScene(Scene):
    """Map size, number of players, the land and its layout, your race, the seed, then Start.
    The computer players' races are drawn from the seed, and so is the layout under Any."""

    transparent = True
    pause_below = False
    pop_on_cancel = True
    controls = {"s": "size_small", "m": "size_medium", "l": "size_large", "bracketleft": "smaller", "bracketright": "bigger",
                "2": "players_2", "3": "players_3", "4": "players_4", "minus": "fewer_seats", "equal": "more_seats",
                "e": "easy", "n": "medium", "h": "hard", "t": "master", "x": "grandmaster", "g": "summer", "w": "winter", "d": "wasteland", "r": "reroll", ("return", "space"): "start",
                "u": "humans", "o": "orcs", "v": "elves", "a": "dwarves",
                "p": "plains", "f": "forest", "c": "crossings", "k": "klondike", "b": "bastion", "y": "any_layout"}

    def __init__(self, title: TitleScene) -> None:
        self.title = title
        self.size = title.size
        self.players = title.players
        self.difficulty = title.difficulty
        self.theme = title.theme
        self.race = title.race
        self.layout = title.layout
        self.seed = mapgen.fresh_seed()
        self._preview_world: World | None = None
        self._preview_pil: PilImage.Image | None = None
        self._theme_buttons: dict[MapTheme, Button] = {}
        self._size_buttons: dict[str, Button] = {}
        self._player_buttons: dict[int, Button] = {}
        self._difficulty_buttons: dict[Difficulty, Button] = {}
        self._race_buttons: dict[Race, Button] = {}
        self._layout_buttons: dict[Layout | None, Button] = {}
        self._moved = ""  # what the screen had to move to keep the settings playable, for the note under them

    def _layout_text(self) -> str:
        if self._preview_world is None:
            return "…"
        drawn = self._preview_world.layout
        promise = mapgen.PROMISES[drawn]
        return promise if self.layout is not None else f"Any drew {drawn.value.title()} · {promise}"

    @property
    def preview_world(self) -> World | None:
        """The map the New game screen previews: the one Start will play."""
        return self._preview_world

    @property
    def preview_picture(self) -> PilImage.Image | None:
        """The preview as drawn beside the settings."""
        return self._preview_pil

    def _preview_races(self) -> list[Race | None]:
        return [self.race] + [None] * (self.players - 1)

    @property
    def dimensions(self) -> tuple[int, int]:
        """The map this size makes for this many seats: the nominal size rounded up to whole cells."""
        return mapgen.dimensions(self.size, self.players)

    def _settings_note(self) -> str:
        """What the seat count means, and what the screen moved to keep it playable."""
        width, height = self.dimensions
        note = f"{self.size} is {width}×{height} tiles here: you and {plural(self.players - 1, 'computer player')}"
        keys = f"{', '.join(SIZE_KEYS.values())} and [ ] choose the size; 2, 3, 4 and − + the players."
        return f"{note}. {self._moved}. {keys}" if self._moved else f"{note}. {keys}"

    def _difficulty_text(self) -> str:
        """The rating beside the chosen setting, and what it plays like."""
        return DIFFICULTY_NOTES[self.difficulty]

    def _opponents_text(self) -> str:
        if self._preview_world is None:
            return "Opponents: …"
        races = [RACES[p.race].name for p in self._preview_world.players[1:]]
        tally = {name: races.count(name) for name in dict.fromkeys(races)}
        # A sixteen-seat list of races would run off the panel, so beyond a handful they are counted.
        shown = races if len(races) <= 4 else [f"{n}× {name}" for name, n in tally.items()]
        return "Opponents: " + ", ".join(shown)

    def _refresh_preview(self) -> None:
        """Regenerate the preview world and its image under one asset key."""
        if getattr(self, "game", None) is None:
            return
        width, height = self.dimensions
        # The screen chose the seed, so a seed that makes no fair map of these settings gives way to the next (WB-046).
        self.seed, world = fair_map(self.seed, width, height, self.players, theme=self.theme, races=self._preview_races(), layout=self.layout)
        self._preview_world = world
        image = preview_image(world)
        self._preview_pil = image
        # One image slot whatever the map size: the picture sits centred in its box, so the slot is redrawn in place.
        canvas = PilImage.new("RGBA", PREVIEW_BOX, (0, 0, 0, 0))
        canvas.paste(image, ((PREVIEW_BOX[0] - image.width) // 2, (PREVIEW_BOX[1] - image.height) // 2))
        if self.game.assets.has_image(PREVIEW_KEY):
            self.game.assets.update_image(PREVIEW_KEY, canvas)
        else:
            self.game.assets.image_from_pil(PREVIEW_KEY, canvas)

    def on_enter(self) -> None:
        """The options in a column on the left, the preview and the opponents beside them, Start below."""
        self._settle("players")  # the title may carry a pair the sizes no longer offer
        self._refresh_preview()
        options = Column(spacing=6, margin=0)
        size_row = Row(Label("Map size", text_style="body", width=90), spacing=8)
        for name in mapgen.SIZES:
            # The tiles a size makes are the seats' business too, so they are named in the note beside
            # the preview rather than on the button, which keeps the six of them to one row.
            # No keycap on the button: six of them across the width three options take leaves no room for
            # one, and the note beside the preview names the keys instead.
            button = Button(name, on_click=lambda n=name: self.set_size(n), style=GHOST_BUTTON, width=SIZE_WIDTH)
            self._size_buttons[name] = button
            size_row.add(button)
        options.add(size_row)
        player_row = Row(Label("Players", text_style="body", width=90), spacing=8)
        for count in mapgen.SEAT_COUNTS:
            button = Button(str(count), hotkey=str(count) if count <= 4 else None, on_click=lambda c=count: self.set_players(c),
                            style=GHOST_BUTTON, width=COUNT_WIDTH)
            self._player_buttons[count] = button
            player_row.add(button)
        options.add(player_row)
        settings = list(Difficulty)
        for first in range(0, len(settings), 3):
            # Three to a row like the rows around it: five settings on rows of two stood a screen of 680 off its bottom.
            row = Row(Label("AI, Elo" if first == 0 else "", text_style="body", width=90), spacing=8)
            shown = settings[first:first + 3]
            width = (3 * OPTION_WIDTH + 2 * 8 - (len(shown) - 1) * 8) // len(shown)  # a shorter row fills the same width, so the column lines up
            for difficulty in shown:
                button = Button(f"{difficulty.value.title()} {DIFFICULTY_ELO[difficulty]}", hotkey=DIFFICULTY_KEYS[difficulty],
                                on_click=lambda d=difficulty: self.set_difficulty(d), style=GHOST_BUTTON, width=width)
                self._difficulty_buttons[difficulty] = button
                row.add(button)
            options.add(row)
        options.add(Label(lambda: self._difficulty_text(), text_style="sub", width=NOTE_WIDTH, wrap=True))
        theme_row = Row(Label("Land", text_style="body", width=90), spacing=8)
        for theme, key in ((MapTheme.SUMMER, "G"), (MapTheme.WINTER, "W"), (MapTheme.WASTELAND, "D")):
            button = Button(theme.value.title(), hotkey=key, on_click=lambda t=theme: self.set_theme(t), style=GHOST_BUTTON, width=OPTION_WIDTH)
            self._theme_buttons[theme] = button
            theme_row.add(button)
        options.add(theme_row)
        layouts = list(LAYOUT_KEYS.items())
        for first in (0, 3):
            row = Row(Label("Map" if first == 0 else "", text_style="body", width=90), spacing=8)
            for layout, key in layouts[first:first + 3]:
                button = Button("Any" if layout is None else layout.value.title(), hotkey=key, on_click=lambda chosen=layout: self.set_layout(chosen),
                                style=GHOST_BUTTON, width=OPTION_WIDTH)
                self._layout_buttons[layout] = button
                row.add(button)
            options.add(row)
        options.add(Label(lambda: self._layout_text(), text_style="sub", width=NOTE_WIDTH, wrap=True))
        race_row = Row(Label("Race", text_style="body", width=90), spacing=8)
        for race, key in RACE_KEYS.items():
            button = Button(RACES[race].name, hotkey=key, on_click=lambda r=race: self.set_race(r), style=GHOST_BUTTON, width=RACE_WIDTH)
            self._race_buttons[race] = button
            race_row.add(button)
        options.add(race_row)
        options.add(Row(Label(lambda: f"Seed {self.seed}", text_style="body", width=90 + 8 + OPTION_WIDTH),
                        Button("Reroll", hotkey="R", on_click=self.reroll, style=GHOST_BUTTON, width=OPTION_WIDTH), spacing=8))
        side = Column(Image(PREVIEW_KEY, width=PREVIEW_BOX[0], height=PREVIEW_BOX[1]),
                      Label(lambda: self._opponents_text(), text_style="sub", width=PREVIEW_BOX[0], wrap=True),
                      Label(lambda: self._settings_note(), text_style="sub", width=PREVIEW_BOX[0], wrap=True),
                      spacing=8, margin=0)
        # The race's character runs under the whole row: beside the preview it would wrap, and the panel must fit a 680 px window.
        race_note = Label(lambda: f"{RACES[self.race].tagline} · {RACES[self.race].passive}", text_style="sub", width=NOTE_WIDTH + 24 + PREVIEW_BOX[0])
        panel = Column(Label("New game", text_style="title"), Row(options, side, spacing=24), race_note,
                       Row(Button("Start", hotkey="Enter", on_click=self.start, style=ACTION_BUTTON, width=2 * OPTION_WIDTH + 8),
                           Button("Back", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=OPTION_WIDTH), spacing=8),
                       spacing=8, anchor=Anchor.CENTER, style=OVERLAY_STYLE)
        self.ui.add(panel)
        self._restyle()

    def _restyle(self) -> None:
        for name, button in self._size_buttons.items():
            button.style = ACTION_BUTTON if name == self.size else GHOST_BUTTON
        for count, button in self._player_buttons.items():
            button.style = ACTION_BUTTON if count == self.players else GHOST_BUTTON
        for layout, button in self._layout_buttons.items():
            button.enabled = layout is None or layout in mapgen.layouts_for(*self.dimensions, self.players)
        for difficulty, button in self._difficulty_buttons.items():
            button.style = ACTION_BUTTON if difficulty == self.difficulty else GHOST_BUTTON
        for theme, button in self._theme_buttons.items():
            button.style = ACTION_BUTTON if theme == self.theme else GHOST_BUTTON
        for race, button in self._race_buttons.items():
            button.style = ACTION_BUTTON if race == self.race else GHOST_BUTTON
        for layout, button in self._layout_buttons.items():
            button.style = ACTION_BUTTON if layout is self.layout else GHOST_BUTTON

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (4, 6, 12, 140))

    def _settle(self, moving: str) -> None:
        """Keep size, seats and layout a combination that makes a fair map, and say what moved.

        Size and seats constrain each other — sixteen seats do not fit a Small map and two seats
        rattle around an Epic one — so whichever the player did not just touch gives way; greying
        out both rows instead would leave the screen with no way from one end to the other.  A
        layout the pair cannot hold falls back to Any, which draws from the ones it can."""
        moved = []
        if mapgen.refusal(*self.dimensions, self.players, None) is not None:
            if moving == "players":
                sizes = mapgen.sizes_for(self.players)
                order = list(mapgen.SIZES)
                self.size = min(sizes, key=lambda n: abs(order.index(n) - order.index(self.size)))
                moved.append(f"{self.players} seats need {self.size}")
            else:
                counts = mapgen.offered(self.size)
                self.players = min(counts, key=lambda c: abs(c - self.players))
                moved.append(f"a {self.size} map seats {self.players}")
        if self.layout is not None and self.layout not in mapgen.layouts_for(*self.dimensions, self.players):
            moved.append(f"{self.layout.value.title()} wants another grid of seats, so the map is Any")
            self.layout = None
            self.title.layout = None
        self._moved = "; ".join(moved)

    def set_size(self, name: str) -> None:
        self.size = name
        self._settle("size")
        self.title.sfx("button")
        self._restyle()
        self._refresh_preview()

    def set_players(self, count: int) -> None:
        self.players = count
        self._settle("players")
        self.title.sfx("button")
        self._restyle()
        self._refresh_preview()

    def _step_size(self, by: int) -> None:
        names = list(mapgen.SIZES)
        self.set_size(names[max(0, min(len(names) - 1, names.index(self.size) + by))])

    def _step_players(self, by: int) -> None:
        counts = mapgen.SEAT_COUNTS
        self.set_players(counts[max(0, min(len(counts) - 1, counts.index(self.players) + by))])

    def smaller(self) -> None:
        self._step_size(-1)

    def bigger(self) -> None:
        self._step_size(1)

    def fewer_seats(self) -> None:
        self._step_players(-1)

    def more_seats(self) -> None:
        self._step_players(1)

    def set_difficulty(self, difficulty: Difficulty) -> None:
        self.difficulty = difficulty
        self.title.sfx("button")
        self._restyle()

    def set_theme(self, theme: MapTheme) -> None:
        self.theme = theme
        self.title.sfx("button")
        self._restyle()
        self._refresh_preview()

    def set_race(self, race: Race) -> None:
        self.race = race
        self.title.race = race  # multiplayer rooms lead the race chosen here
        self.title.sfx("button")
        self._restyle()
        self._refresh_preview()

    def set_layout(self, layout: Layout | None) -> None:
        if layout is not None and layout not in mapgen.layouts_for(*self.dimensions, self.players):
            return  # the button is greyed out; a key press must not reach past it either
        self.layout = layout
        self.title.layout = layout  # multiplayer rooms use the layout chosen here
        self.title.sfx("button")
        self._restyle()
        self._refresh_preview()

    def plains(self) -> None:
        self.set_layout(Layout.PLAINS)

    def forest(self) -> None:
        self.set_layout(Layout.FOREST)

    def crossings(self) -> None:
        self.set_layout(Layout.CROSSINGS)

    def klondike(self) -> None:
        self.set_layout(Layout.KLONDIKE)

    def bastion(self) -> None:
        self.set_layout(Layout.BASTION)

    def any_layout(self) -> None:
        self.set_layout(None)

    def humans(self) -> None:
        self.set_race(Race.HUMAN)

    def orcs(self) -> None:
        self.set_race(Race.ORC)

    def elves(self) -> None:
        self.set_race(Race.ELF)

    def dwarves(self) -> None:
        self.set_race(Race.DWARF)

    def summer(self) -> None:
        self.set_theme(MapTheme.SUMMER)

    def winter(self) -> None:
        self.set_theme(MapTheme.WINTER)

    def wasteland(self) -> None:
        self.set_theme(MapTheme.WASTELAND)

    def easy(self) -> None:
        self.set_difficulty(Difficulty.EASY)

    def medium(self) -> None:
        self.set_difficulty(Difficulty.MEDIUM)

    def hard(self) -> None:
        self.set_difficulty(Difficulty.HARD)

    def master(self) -> None:
        self.set_difficulty(Difficulty.MASTER)

    def grandmaster(self) -> None:
        self.set_difficulty(Difficulty.GRANDMASTER)

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
        self.seed = mapgen.fresh_seed()
        self.title.sfx("button")
        self._refresh_preview()

    def start(self) -> None:
        self.title.sfx("button")
        width, height = self.dimensions
        self.game.clear_and_push(new_game(self.seed, width=width, height=height, players=self.players, difficulty=self.difficulty, theme=self.theme,
                                          settings=self.title.settings, races=[self.race] + [None] * (self.players - 1), layout=self.layout))
