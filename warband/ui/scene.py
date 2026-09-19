"""saga2d scenes for Warband: the match, its HUD, and the overlays stacked on it."""

from __future__ import annotations

import gc
import json
import math
import random
from collections import deque
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5
from dataclasses import dataclass, field
from typing import Any, Callable

from saga2d import (
    Anchor, Button, Camera, Column, Component, InputEvent, KeyHints, Label, Layout, Minimap, Panel, RenderLayer, Row, Scene, Sprite, Style,
)
from saga2d import SaveError
from saga2d.effects import Banner, Burst, Effects, FloatingText, Pulse, Toast
from warband.art import ambience
from warband.audio import deaths, wreckage
from warband.sim import mapgen
from warband.brains.ai import DIFFICULTY_ELO, auto_site, make_brain
from warband.art.effects import Flare, Spray, Stain, UnitDeath, death_outcome
from warband.ui.icons import Icon, draw_icon, loop_parts
from warband.sim.model import Build, Building, Entity, Event, Pos, RuleError, Unit, World
from warband.art.production import ProductionButton, ProductionTarget, draw_production_icon
from warband.sim.races import RACES, RaceInfo
from warband.sim.rules import (BUILDINGS, DAMAGE_FACTORS, SIM_DT, UNITS, UPGRADES, ArmorClass, AttackType, BuildingType, Difficulty, MapTheme, Race,
                               UnitType, Upgrade)
from warband.sim.rules import Layout as MapLayout
from warband.records.profile import MatchResult, Profile, RatingChange, Standing, rated, standing
from warband.records.replay import Replay, ReplayStore
from warband.records.scores import HighScores, score_breakdown
from warband.audio.sound import IMPACTS, apply_volumes, impact_sound, play_music, play_sound
from warband.audio.voices import voiced
from warband.ui.controls import CARD_COLS, CHORDS, GRID_KEYS, SCHEMES, Scheme, label as key_label
from warband.ui.style import (
    ACTION_BUTTON, BAD, CARD_BUTTON, DANGER_BUTTON, GHOST_BUTTON, GOLD, GOOD, LUMBER, MUTED, OVERLAY_STYLE, PANEL_STYLE, RESULTS_STYLE,
)
from warband.art.textures import TILE
from warband.ui.tutorial import OBJECTIVES, Tutorial
from warband.ui.view import SHOT_LOOKS, SHOT_SIZE, MapView, Overlay, Sighting, check_memory, rgba, to_tiles, to_world

DEFAULT_SETTINGS: dict[str, Any] = {"music": 0.6, "sfx": 0.8, "edge_scroll": True, "scroll_speed": 1.0, "fullscreen": False, "tutorial": True, "blood": True,
                                    "controls": "classic"}
FLESH = {u.value for u in UnitType} - {UnitType.CATAPULT.value}  # what bleeds when hit
SAVE_VERSION = 2  # 2: the world records its layout
SAVE_SLOTS = 3
AUTOSAVE_EVERY = 120.0  # seconds of match time
SELECT_GAP = 30.0  # seconds: selecting is constant, and its cue answers only the first selection in a while (WB-039)
TOAST_TOP = 280  # below the resource, settlement and objectives panels
HUD_TOP = 158  # just under the Settlement row (which ends at 150): the status line starts here, and the map can scroll clear of it
HINT_BAR = 28
PANEL_MARGIN = (12, HINT_BAR + 10)
MAX_STEPS_PER_FRAME = 6
ZOOM_PER_LINE = 1.06
ZOOM_PER_KEY = 1.25
MAX_LINES_PER_EVENT = 4.0
EDGE_MARGIN = 12
EDGE_SPEED = 900
KEY_SPEED = 800
DRAG_THRESHOLD = 5
GROUP_KEYS = "123456789"
#: The Build catalogue's order, one per slot of the card: the opening buildings first, then the tech chain as it unlocks.
BUILD_ORDER = (BuildingType.FARM, BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.TOWER, BuildingType.LUMBER_MILL,
               BuildingType.BLACKSMITH, BuildingType.STABLES, BuildingType.WORKSHOP, BuildingType.CHURCH)
#: The unit card's slots: moving on the top row (Q W E in Grid), fighting and a peasant's work below.
UNIT_SLOTS = {"move": 0, "stop": 1, "hold": 2, "attack": 3, "patrol": 4, "build": 5, "repair": 6}
#: The Upgrade catalogue's slots: each chain's tiers side by side; None stands for the race's two arts.
UPGRADE_ROWS = ((Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.SIEGE), (Upgrade.ARMOR_1, Upgrade.ARMOR_2, None),
                (Upgrade.ARROWS_1, Upgrade.ARROWS_2, None))
#: Names that fit a card button (each race's are in :mod:`warband.sim.races`); the tooltip and the codex use the full ones.
UPGRADE_NAMES = {Upgrade.BLADES_1: "Blades I", Upgrade.BLADES_2: "Blades II", Upgrade.ARMOR_1: "Armour I", Upgrade.ARMOR_2: "Armour II",
                 Upgrade.ARROWS_1: "Arrows I", Upgrade.ARROWS_2: "Arrows II", Upgrade.HORSES: "Horses", Upgrade.SIEGE: "Siege", Upgrade.BLESSING: "Blessing",
                 Upgrade.BLOODLUST: "Bloodlust", Upgrade.PLUNDER: "Plunder", Upgrade.LONGBOWS: "Longbows", Upgrade.REGROWTH: "Regrowth",
                 Upgrade.DEEP_MINING: "Mining", Upgrade.BLASTING_POWDER: "Powder"}
CARD_WIDTH = 116
CARD_GAP = 6
CARD_PANEL_WIDTH = CARD_COLS * CARD_WIDTH + (CARD_COLS - 1) * CARD_GAP + 2 * PANEL_STYLE.padding  # the widest command card
CARD_ICON = 58  # height of a portrait button; the name sits under it
CARD_PLAIN = 32  # height of a button without a portrait (the unit card's)
MINIMAP_WIDTH = 200
SELECTION_WIDTH = 470
SELECTION_HEIGHT = 128
PORTRAIT = 30  # a selected unit's portrait in the panel
PORTRAIT_GAP = 3
PORTRAIT_COLS = 13
PORTRAIT_ROWS = 2
PORTRAITS_PER_PAGE = PORTRAIT_COLS * PORTRAIT_ROWS  # a larger selection pages; the grid's last cell turns the page


def armour_name(armor: ArmorClass) -> str:
    return armor.value if armor is ArmorClass.UNARMORED else f"{armor.value} armour"


def attack_hint(attack: AttackType) -> str:
    """What a kind of blow does beyond its number, from :data:`DAMAGE_FACTORS`, for the unit panel."""
    better = [f"×{factor:g} against {armor.value if armor is not ArmorClass.FORTIFIED else 'buildings'}" for (kind, armor), factor in DAMAGE_FACTORS.items() if kind is attack]
    return attack.value + (f", {', '.join(better)}" if better else "")


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


@dataclass
class Command:
    """One command-card button.  *letter* is its key in the lettered schemes and *slot* its place on the card, the
    Grid scheme's key; :attr:`hotkey` is the key it answers to now, given as the card is built."""

    label: str
    letter: str
    action: Callable[[], None]
    slot: int
    tooltip: str = ""
    cost: str = ""
    blocked: Callable[[], str | None] = field(default=lambda: None)  # why it cannot be used right now
    style: Style = field(default_factory=lambda: CARD_BUTTON)
    target: ProductionTarget | None = None  # a unit, building or upgrade: the button shows its portrait or emblem
    count: Callable[[], int] = field(default=lambda: 0)  # how many are already ordered: shown after the name
    alt: Callable[[], None] | None = None  # what Shift with its key or click does (a recruit: endless training, or no longer)
    endless: Callable[[], bool] | None = None  # a recruit: whether it is being trained endlessly (right-click toggles)
    hotkey: str = ""  # as its keycap shows it

    @property
    def key(self) -> str:
        """The key's name, as input events carry it."""
        return self.hotkey.lower()


class CardButton(ProductionButton):
    """A command's portrait button: a click gives the command, Shift+click its alternative, and a right-click on a
    recruit toggles its endless training, as Warcraft III toggled autocast.  A loop in the corner marks it endless."""

    def __init__(self, command: Command, player: int, race: Race, **kwargs: Any) -> None:
        super().__init__(command.target, player, race, hotkey=command.hotkey or None, on_click=command.action, style=command.style, **kwargs)
        self.command = command
        self.add(_EndlessMark(self, anchor=Anchor.TOP_LEFT, margin=4))

    def handle_event(self, event: InputEvent) -> bool:
        """The alternative goes ahead of the enabled check: a recruit the purse cannot pay for yet can still be trained
        endlessly, which waits for the money; its plain click stays blocked."""
        command = self.command
        if (self.visible and event.type == "click" and command.alt is not None and self.hit_test(event.x, event.y)
                and ((event.button == "right" and command.endless is not None) or (event.button == "left" and event.shift))):
            command.alt()
            return True
        return super().handle_event(event)


class _EndlessMark(Component):
    """Two arrows chasing each other round, in gold, on a recruit trained endlessly."""

    SIZE = 16

    def __init__(self, button: CardButton, **kwargs: Any) -> None:
        super().__init__(width=self.SIZE, height=self.SIZE, **kwargs)
        self.button = button

    def on_draw(self) -> None:
        endless = self.button.command.endless
        if self._game is None or endless is None or not endless():
            return
        x, y, w, h = self.bounds
        backend = self._game.backend
        backend.draw_rect(x - 2, y - 2, w + 4, h + 4, (22, 20, 24, 230), order=self._order)
        for points, ink in loop_parts():
            backend.draw_polygon([(x + u * w, y + v * h) for u, v in points], ink, order=self._order)


class _Slot(Component):
    """An empty place on the card, keeping the others where their keys say; the Grid scheme draws it faintly."""

    def __init__(self, faint: bool, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.faint = faint

    def on_draw(self) -> None:
        if self._game is None or not self.faint:
            return
        x, y, w, h = self.bounds
        self._game.backend.draw_rect(x, y, w, h, (255, 255, 255, 8), order=self._order)


@dataclass
class QueueEntry:
    """One item of the production overview: what is being made or waited for, and what a click does about it."""

    target: ProductionTarget
    hint: str
    state: str  # "working" | "queued" | "waiting"
    progress: float  # of the work; 0 while queued or waiting
    goto: Callable[[], None] | None  # left click: select the producer or look at the site
    cancel: Callable[[], bool]  # right click; whether the rules allowed it


class _SelectionPanel(Component):
    """Route the immediate-drawn portraits and production queue through the UI tree."""

    def __init__(self, scene: GameScene, **kwargs: Any) -> None:
        super().__init__(blocks_pointer=True, **kwargs)
        self.scene = scene

    def on_event(self, event: InputEvent) -> bool:
        if event.type == "click" and self.hit_test(event.x, event.y):
            return self.scene._click_panel(event.x, event.y, event.button, shift=event.shift)
        return False


class GameScene(Scene):
    """The whole match: map, selection, orders, HUD, the AI's turns and the game clock."""

    background_color = (8, 10, 14, 255)
    AUTOSAVE_SLOT = "autosave"
    controls = {
        "escape": "cancel",
        "f1": "open_help",
        "f2": "open_codex",
        "f3": "toggle_pause",
        "f4": "hide_tutorial",
        "f11": "toggle_bars",
        "f5": "quick_save",
        "f9": "quick_load",
        "f10": "open_menu",
        "space": "jump_to_alert",
        ("home", "backspace"): "center_base",
        ("equal", "plus"): "zoom_in",
        "minus": "zoom_out",
        "tab": "next_idle_peasant",
        ("ctrl+a", "meta+a"): "select_army",
        "f6": "recall_bookmark_1", "f7": "recall_bookmark_2", "f8": "recall_bookmark_3",
        "ctrl+f6": "set_bookmark_1", "ctrl+f7": "set_bookmark_2", "ctrl+f8": "set_bookmark_3",
    }

    def __init__(self, world: World, seed: int, *, difficulty: Difficulty = Difficulty.MEDIUM, settings: dict[str, Any] | None = None,
                 player: int | None = None, run_id: str | None = None, ranked: bool = True, replay: Replay | None = None,
                 seen: dict | None = None) -> None:
        """A *ranked* match is recorded from here on (or *replay* goes on recording it, after a load) and rated when it ends.
        *seen* is what a save's view remembered of ground out of sight (:meth:`MapView.memory`)."""
        self.world = world
        self.view: MapView | None = None  # made on entry: it needs the game
        self._seen = seen
        self.run_id = run_id if run_id is not None else str(uuid4())  # one leaderboard row per match, however often it is reloaded
        self.ranked = ranked
        self.seed = seed
        self.difficulty = difficulty
        self.human = next(p.id for p in world.players if p.human) if player is None else player
        self.replay: Replay | None = None  # recording from entry on, when ranked
        self._saved_replay = replay
        self.profile: Profile | None = None  # loaded on entry: the scene needs the data directory
        self.profile_error = ""
        self.rating_change: RatingChange | None = None  # what the finished or abandoned match did to the rating
        self._resignation: Standing | None = None  # where the player stood when they resigned
        self.brains = [make_brain(p.id, difficulty, seed) for p in world.players if not p.human]
        self.rng = random.Random(seed)  # the computer players' stream, and nothing else's: what is drawn must not move the match
        self.fx_rng = random.Random(seed)  # sparks, blood and dust
        self.settings = settings if settings is not None else dict(DEFAULT_SETTINGS)  # a saga2d Settings when the game runs
        for key, value in DEFAULT_SETTINGS.items():
            self.settings.setdefault(key, value)
        self.tutorial = Tutorial() if self.settings["tutorial"] else None
        self._autosave_at = AUTOSAVE_EVERY
        self.selection: list[int] = []
        self.groups: dict[str, list[int]] = {}
        self.pending: str | None = None  # "move" | "attack" | "patrol" | "repair" | "assembly" | "place:<building type>"
        self.catalogue: str | None = None  # "build" | "train" | "upgrade": the settlement's catalogue, over the selection's card
        self._repeat: Callable[[], None] | None = None  # the last recruit or placement once more: the Modal scheme's "."
        self._site_rng = random.Random(f"sites:{seed}")  # where the planner puts what the player lets it place: not the brains' stream
        self.settlement_row: Row | None = None  # made with the HUD
        self.paused = False
        self.speed = 1.0
        self.clock = 0.0
        self.effects = Effects()
        self.bodies: list[UnitDeath] = []  # lying where they fell, oldest first
        self.all_bars = False  # F11: every visible unit's and building's health, not only the wounded
        self.alt_held = False  # Alt on the latest input shows the same while it lasts
        self.stains: list[Stain] = []  # under the bodies, oldest first
        self._blows: dict[int, tuple[float, float]] = {}  # unit id -> where its last visible blow came from (tiles)
        self.recent_sounds: deque[str] = deque(maxlen=48)
        self.status = ""
        self.status_timer = 0.0
        self.tooltip = ""
        self.mouse = (0, 0)
        self.hover: tuple[float, float] = (0.0, 0.0)  # in tiles
        self.last_alert: tuple[float, float] | None = None
        self._acc = 0.0
        self._drag_start: tuple[int, int] | None = None
        self._drag_end: tuple[int, int] | None = None
        self._game_over = False
        self._card: list[Command] = []
        self._card_buttons: list[Button] = []
        self._card_signature: tuple | None = None
        self._portraits: list[tuple[int, tuple[int, int, int, int]]] = []
        self._portrait_page, self._portrait_pages = 0, 1  # of a selection too large for one grid
        self._page_tile: tuple[float, float, float, float] | None = None
        self._queue_hits: list[tuple[tuple[float, float, float, float], QueueEntry]] = []
        self._sound_times: dict[str, float] = {}
        self._battle_voices: deque[float] = deque()
        self._fights: deque[float] = deque()
        self._battle_until = -math.inf
        self._last_click: tuple[float, int | None] = (-10.0, None)
        self.bookmarks: dict[int, tuple[float, float]] = {}
        self._warm = None  # renders the unit images over the first frames

    # -- Lifecycle -------------------------------------------------------------

    def on_enter(self) -> None:
        self._load_profile()
        if self.ranked:
            self.replay = self._recording(self._saved_replay)
            self._saved_replay = None
        self.view = self._make_view()
        self._setup_camera()
        self.apply_settings()
        self._build_hud()
        self.center_base(instant=True)
        rivals = ", ".join(f"the {RACES[p.race].name} of {p.name}" for p in self.world.players if p.id != self.human)
        self.effects.add(Banner("Warband", subtitle=f"The {self.race.name} of {self.player.name} against {rivals}", accent=rgba(self.player.color)))
        from warband.art import textures

        self._warm = textures.warm_units(self.game, [p.id for p in self.world.players], [p.race for p in self.world.players])
        play_music("peace", self.player.race)

    def on_reveal(self) -> None:
        self._refresh_card()  # the Plans overlay may have cancelled what the card's keys and counts describe

    def _make_view(self) -> MapView:
        return MapView(self, self.world, self.human, memory=self._seen)

    def _setup_camera(self) -> None:
        """The map plus its rim, scrollable clear of the HUD: the top rows above, the selection panel and minimap below.
        A map narrower than the window, or shorter than the room between the HUD's rows and panels, opens zoomed in
        until it fills it, rather than lying in dark margins (a Small map on a 4K desktop)."""
        w, h = self.game.resolution
        world_w, world_h = self.world.width * TILE, self.world.height * TILE
        hud_bottom = PANEL_MARGIN[1] + max(SELECTION_HEIGHT, self._minimap_height())
        fill = max(w / (world_w + 2 * TILE), (h - HUD_TOP - hud_bottom) / (world_h + 2 * TILE))
        zoom = max(1.0, fill)
        self.camera = Camera((w, h), world_bounds=(-TILE, -TILE, world_w + TILE, world_h + TILE), insets=(0, HUD_TOP, 0, hud_bottom),
                             zoom=zoom, min_zoom=0.75, max_zoom=max(2.0, zoom))
        self.camera.enable_key_scroll(speed=KEY_SPEED)

    def _minimap_height(self) -> int:
        return round(MINIMAP_WIDTH * self.world.height / self.world.width)

    def apply_settings(self) -> None:
        """Push the settings into the things they control; called on entry and after the settings screen."""
        apply_volumes(self.settings["music"], self.settings["sfx"])
        speed = float(self.settings["scroll_speed"])
        self.camera.enable_key_scroll(speed=KEY_SPEED * speed)
        if self.settings["edge_scroll"]:
            self.camera.enable_edge_scroll(EDGE_MARGIN, EDGE_SPEED * speed)
        else:
            self.camera.disable_edge_scroll()
        self.game.set_fullscreen(bool(self.settings["fullscreen"]))
        if self.tutorial is not None and not self.settings["tutorial"]:
            self.tutorial = None
        if self.settlement_row is not None:  # the controls may have changed: every keycap follows
            self._fill_settlement_row()
            self._refresh_card()
        if hasattr(self.settings, "save"):
            self.settings.save()

    @property
    def scheme(self) -> Scheme:
        """The control scheme the settings choose (:mod:`warband.ui.controls`)."""
        return SCHEMES[self.settings["controls"]]

    @property
    def player(self):
        return self.world.players[self.human]

    @property
    def race(self) -> RaceInfo:
        """The human player's race: its names and numbers are what the HUD shows."""
        return RACES[self.player.race]

    @property
    def stats(self) -> dict[str, int]:
        """The player's battle record, kept by the simulation so kills are attributed to the striker."""
        return self.player.stats

    def sfx(self, name: str, *, gap: float = 0.0) -> None:
        """Bound battle density across materials/takes; alerts bypass that budget.  Cues speak in the player's race's voice."""
        name = voiced(name, self.player.race)
        combat = name in IMPACTS or name == "impact" or name in deaths.CUES
        key = "siege_impact" if name in IMPACTS and name.startswith("stone_") else name  # the siege family, not a stone building falling
        if combat:
            gap = max(gap, 0.3 if key == "siege_impact" else 0.09)
        if gap and self.clock - self._sound_times.get(key, -math.inf) < gap:
            return
        if combat:
            while self._battle_voices and self.clock - self._battle_voices[0] >= 0.5:
                self._battle_voices.popleft()
            if len(self._battle_voices) >= 8 or sum(self.clock - t < 0.12 for t in self._battle_voices) >= 4:
                return
            self._battle_voices.append(self.clock)
        self._sound_times[key] = self.clock
        self.recent_sounds.append(name)
        if self.settings["sfx"] > 0:
            play_sound(name)

    # -- HUD ---------------------------------------------------------------------

    def _build_hud(self) -> None:
        world, player = self.world, self.player

        def supply_text() -> str:
            used, cap = world.supply(self.human)
            return f"{used}/{cap}"

        # Resources as symbol + number; hovering a symbol names it in the tooltip panel.
        self._resource_rows = [
            (Row(Icon("gold", size=22), Label(lambda: str(player.gold), text_style="hud", text_color=GOLD), spacing=6),
             "Gold — mined by workers; every unit, building and upgrade costs some"),
            (Row(Icon("lumber", size=22), Label(lambda: str(player.lumber), text_style="hud", text_color=LUMBER), spacing=6),
             "Lumber — felled by workers; buildings, upgrades and engines need it"),
            (Row(Icon("supply", size=22), Label(supply_text, text_style="hud"), spacing=6),
             "Supply used / capacity — farms and halls feed the army"),
        ]
        self.ui.add(Panel(anchor=Anchor.TOP_LEFT, margin=12, layout=Layout.HORIZONTAL, spacing=12, style=PANEL_STYLE, blocks_pointer=True, children=[
            Label(player.name, text_style="title", text_color=rgba(player.color)),
            Label(self.race.name, text_style="sub"),
            *(row for row, _hint in self._resource_rows),
            Label(lambda: _clock(world.time), text_style="sub"),
            Label(lambda: "Paused" if self.paused else f"×{self.speed:g}" if self.speed != 1 else "", text_style="hud", text_color=BAD),
            self._idle_button(),
            self._army_button(),
            Button("Menu", hotkey="F10", on_click=self.open_menu, style=GHOST_BUTTON),
        ]))
        self.settlement_row = Row(spacing=8, anchor=Anchor.TOP_LEFT, margin=(12, 84), style=PANEL_STYLE, blocks_pointer=True)
        self._fill_settlement_row()
        self.ui.add(self.settlement_row)
        world_w, world_h = self.world.width * TILE, self.world.height * TILE
        self.minimap = Minimap(self.view.minimap_key, (world_w, world_h), self.camera, width=MINIMAP_WIDTH,
                               height=self._minimap_height(), on_click=self.minimap_click,
                               anchor=Anchor.BOTTOM_LEFT, margin=PANEL_MARGIN, style=PANEL_STYLE, blocks_pointer=True)
        self.ui.add(self.minimap)
        # Centre the selection between the minimap and the widest command card.
        width = self.game.resolution[0]
        left = max(PANEL_MARGIN[0] + MINIMAP_WIDTH + 12,
                   min((width - SELECTION_WIDTH) // 2,
                       width - PANEL_MARGIN[0] - CARD_PANEL_WIDTH - 8 - SELECTION_WIDTH))
        self.selection_panel = _SelectionPanel(self, width=SELECTION_WIDTH, height=SELECTION_HEIGHT,
                                               anchor=Anchor.BOTTOM_LEFT, margin=(left, PANEL_MARGIN[1]))
        self.ui.add(self.selection_panel)
        self.card_panel = Column(spacing=CARD_GAP, anchor=Anchor.BOTTOM_RIGHT, margin=PANEL_MARGIN, style=PANEL_STYLE, blocks_pointer=True)
        self.ui.add(self.card_panel)
        # What a hovered command or queued job is, wrapped above the selection panel where a long line fits.
        self.command_tooltip = Panel(anchor=Anchor.BOTTOM_LEFT, margin=(left, PANEL_MARGIN[1] + SELECTION_HEIGHT + 8), layout=Layout.VERTICAL,
                                     style=PANEL_STYLE, visible=False, blocks_pointer=True,
                                     children=[Label(lambda: self.tooltip, text_style="body", wrap=True, width=SELECTION_WIDTH - 24)])
        self.ui.add(self.command_tooltip)
        self.ui.add(KeyHints(self.hint, anchor=Anchor.BOTTOM_CENTER, margin=5, blocks_pointer=True))
        self.ui.add(Label(lambda: self.status if self.status_timer > 0 else "", text_style="hud", anchor=Anchor.TOP_LEFT,
                          margin=(12, HUD_TOP), width=760, wrap=True, text_color=GOLD, blocks_pointer=True))
        self.objectives = self._build_objectives()
        self.ui.add(self.objectives)
        self._refresh_card()

    def _fill_settlement_row(self) -> None:
        """The settlement's buttons, each with the key that reaches it whatever the card shows in this scheme: Ctrl with
        a letter where the letters belong to the card (Classic, Modal), the plain key beside the grid in Grid."""
        row, scheme = self.settlement_row, self.scheme
        assert row is not None
        row.clear()
        row.add(Label("Settlement", text_style="heading", width=124))
        for action, text, click, width in (
                ("build", "Build", lambda: self.toggle_catalogue("build"), None),
                ("train", "Train", lambda: self.toggle_catalogue("train"), None),
                ("upgrade", "Upgrade", lambda: self.toggle_catalogue("upgrade"), None),
                ("plans", lambda: f"Plans ({self._plan_count()})", self.open_plans, 152),
                ("assembly", "Assembly", lambda: self.start_pending("assembly"), None)):
            row.add(Button(text, hotkey=scheme.shortcut(action), on_click=click, style=GHOST_BUTTON, width=width))

    def _build_objectives(self) -> Column:
        """The panel under the top-right corner: the tutorial strip here, a mission's objectives in the campaign."""
        panel = Column(spacing=4, anchor=Anchor.TOP_RIGHT, margin=(12, HUD_TOP), style=PANEL_STYLE, blocks_pointer=True)
        panel.add(Row(Label("Getting started", text_style="heading", width=290),
                      Button("Hide", hotkey="F4", on_click=self.hide_tutorial, style=GHOST_BUTTON, width=90), spacing=8))
        self.objective_label = Label("", text_style="body", width=390, wrap=True)
        self.objective_done = Label("", text_style="sub", width=390)
        panel.add(self.objective_label)
        panel.add(self.objective_done)
        panel.visible = self.tutorial is not None
        return panel

    def hide_tutorial(self) -> None:
        self.tutorial = None
        self.objectives.visible = False
        self.sfx("button")

    def toggle_bars(self) -> None:
        """F11: health over every visible unit and building, or over the wounded and the selected only."""
        self.all_bars = not self.all_bars
        self.say("Health bars: everyone" if self.all_bars else "Health bars: the wounded and the selected")

    def _update_objectives(self) -> None:
        if self.tutorial is None:
            self.objectives.visible = False
            return
        if self.tutorial.update(self):
            self.sfx("built")
            if self.tutorial.finished:
                self.settings["tutorial"] = False
                if hasattr(self.settings, "save"):
                    self.settings.save()
        current = self.tutorial.current
        self.objective_label.text = f"{self.tutorial.step + 1}. {current.text.format(**self.tutorial_keys())}" if current is not None else ""
        self.objective_done.text = f"{self.tutorial.step} of {len(OBJECTIVES) - 1} done" if self.tutorial.step else "F4 hides this; the settings switch it off"

    def tutorial_keys(self) -> dict[str, str]:
        """The keys the tutorial names, as this scheme has them: B then F builds a farm in Classic, D then Q in Grid."""
        def key(letter: str, slot: int) -> str:
            return key_label(self.scheme.card_key(letter, slot))
        return {"build": key("b", UNIT_SLOTS["build"]), "farm": key(BUILDINGS[BuildingType.FARM].hotkey, BUILD_ORDER.index(BuildingType.FARM)),
                "barracks": key(BUILDINGS[BuildingType.BARRACKS].hotkey, BUILD_ORDER.index(BuildingType.BARRACKS)),
                "footman": key(UNITS[UnitType.FOOTMAN].hotkey, BUILDINGS[BuildingType.BARRACKS].trains.index(UnitType.FOOTMAN)),
                "attack": key("a", UNIT_SLOTS["attack"])}

    def _idle_button(self) -> Button:
        self.idle_button = Button(lambda: f"Idle {self._idle_peasant_count()}", hotkey="Tab", on_click=self.next_idle_peasant, style=ACTION_BUTTON)
        return self.idle_button

    def _idle_peasant_count(self) -> int:
        return sum(1 for u in self.world.player_units(self.human) if u.is_worker and not u.orders and not u.hidden)

    def _army_button(self) -> Button:
        self.army_button = Button(lambda: f"Army {len(self._army())}", hotkey="Ctrl+A", on_click=self.select_army, style=ACTION_BUTTON)
        return self.army_button

    def _army(self) -> list[Unit]:
        """Every soldier of the player's, wherever it stands: what the Army button and Ctrl+A select."""
        return [u for u in self.world.player_units(self.human) if not u.is_worker and not u.hidden]

    @property
    def card(self) -> tuple[Command, ...]:
        """The command card as it shows now."""
        return tuple(self._card)

    @property
    def card_buttons(self) -> tuple[Button, ...]:
        """The command card's buttons, in the card's order."""
        return tuple(self._card_buttons)

    @property
    def portraits(self) -> tuple[tuple[int, tuple[int, int, int, int]], ...]:
        """The selection panel's portraits on the page shown: each entity's id and its rectangle."""
        return tuple(self._portraits)

    @property
    def page_tile(self) -> tuple[float, float, float, float] | None:
        """The tile that turns the portrait page, when the selection needs more than one."""
        return self._page_tile

    @property
    def portrait_page(self) -> int:
        """The page of the selection's portraits shown; setting it turns to that page, as the page tile would."""
        return self._portrait_page

    @portrait_page.setter
    def portrait_page(self, page: int) -> None:
        self._portrait_page = page

    @property
    def queue_hits(self) -> tuple[tuple[tuple[float, float, float, float], QueueEntry], ...]:
        """The production queue's entries on the panel and where each can be clicked."""
        return tuple(self._queue_hits)

    @property
    def autosave_at(self) -> float:
        """The match time of the next autosave."""
        return self._autosave_at

    def hint(self) -> list[tuple[str, str]]:
        """The bar at the bottom: what the keys do in the mode the card is in, named as this scheme names them."""
        scheme = self.scheme
        placing = self.placing
        if placing is not None:
            hints = [("Click", "place"), (self._key_of(placing) + " again", "the planner picks the spot")]
            return hints + [("Esc", "stop placing") if scheme.sticky else ("Shift+click", "keep placing"), ("Right click", "back")]
        if self.pending is not None:
            return [("Click", "target"), ("Shift+click", "queue"), ("Right click", "cancel")]
        keys = " ".join(c.hotkey.upper() for c in self._card if c.hotkey)
        catalogue = self.shown_catalogue
        if catalogue == "build":
            return [(keys, "choose a building"), ("Shift+click", "keep placing"), ("Esc", "back")]
        if catalogue == "train":
            hints = [(keys, "order one"), ("Shift+key", "train endlessly")]
            if catalogue == self.catalogue:
                return hints + [("Esc", "back")]
            return hints + [(f"{key_label(scheme.keys['build'])} / {key_label(scheme.keys['upgrade'])}", "build / upgrade"),
                            (key_label(scheme.keys["repeat"]), "repeat"), ("Tab", "idle peasant"), ("Esc", "menu")]
        if catalogue == "upgrade":
            return [(keys, "order"), ("Esc", "back")]
        units = self._own_units()
        if units:
            hints = [("Right click", "move / harvest / attack / repair"), (self._slot_key("attack"), "attack-move"),
                     (self._slot_key("patrol"), "patrol"), (self._slot_key("stop"), "stop")]
            if any(u.is_worker for u in units):
                hints.append((f"{self._slot_key('build')} / {self._slot_key('repair')}", "build / repair"))
            return hints + [("Ctrl+1-9", "group"), ("Esc", "deselect")]
        building = self._own_building()
        if building is not None:
            work = " ".join(c.hotkey.upper() for c in self._card if c.hotkey and c.label != "Cancel")
            hints = [(work, "train / research")] if work else []
            if any(c.endless is not None for c in self._card):
                hints.append(("Shift+key", "train endlessly"))
            return hints + [("Right click", "rally point"), ("Esc", "deselect")]
        plan = " / ".join(key_label(scheme.keys[action]) for action in ("build", "train", "upgrade"))
        return [("Drag", "select"), (plan, "plan buildings / units / upgrades"), (key_label(scheme.keys["assembly"]), "assembly"),
                ("Tab", "idle peasant"), ("Ctrl+A", "army"), ("Space", "last alert"), ("F3", "pause"), ("F1", "help")]

    def _slot_key(self, command: str) -> str:
        """The key of a command of the unit card, by its name in :data:`UNIT_SLOTS`."""
        return next((c.hotkey.upper() for c in self._card if c.slot == UNIT_SLOTS[command] and c.target is None), "")

    def _key_of(self, target: ProductionTarget) -> str:
        """The key of the card's command for *target*."""
        return next((c.hotkey.upper() for c in self._card if c.target == target), "")

    @property
    def placing(self) -> BuildingType | None:
        """The building whose site the next click places, if one is chosen."""
        return BuildingType(self.pending[6:]) if self.pending is not None and self.pending.startswith("place:") else None

    @property
    def shown_catalogue(self) -> str | None:
        """The catalogue on the card: the one opened, or the scheme's home catalogue (the Modal scheme's Train) while
        nothing that has a card of its own is selected."""
        if self.catalogue is not None:
            return self.catalogue
        if self.scheme.home is not None and not self._own_units() and self._own_building() is None:
            return self.scheme.home
        return None

    # -- Selection -----------------------------------------------------------------

    def _own_units(self) -> list[Unit]:
        return [u for u in (self.world.units.get(i) for i in self.selection) if u is not None and u.player == self.human]

    def _own_building(self) -> Building | None:
        if len(self.selection) == 1:
            b = self.world.buildings.get(self.selection[0])
            if b is not None and b.player == self.human:
                return b
        return None

    def select(self, ids: list[int], *, add: bool = False, quiet: bool = False) -> None:
        alive = [i for i in ids if self.world.entity(i) is not None]
        if add:
            merged = list(self.selection)
            for i in alive:
                if i in merged:
                    merged.remove(i)
                else:
                    merged.append(i)
            alive = merged
        own = [i for i in alive if getattr(self.world.entity(i), "player", None) == self.human]
        if own and len(alive) > len(own):
            alive = own  # mixing in enemies makes no sense; keep what is ours
        if len(alive) > 1:
            alive = [i for i in alive if isinstance(self.world.entity(i), Unit)]  # buildings are selected alone
        self.selection = alive
        self._portrait_page = 0
        self.pending = None
        self.catalogue = None
        self._refresh_card()
        if alive and not quiet:
            self.sfx("select", gap=SELECT_GAP)

    def _prune_selection(self) -> None:
        """Drop what is gone; a building razed out of sight stays selected as the player remembers it, until they look."""
        before = list(self.selection)
        self.selection = [i for i in self.selection if self.world.entity(i) is not None or self.view.sighting(i) is not None]
        if self.selection != before:
            self._refresh_card()

    def click_select(self, point: tuple[float, float], shift: bool, ctrl: bool = False) -> None:
        entity = self.view.entity_at(point)
        if entity is None:
            if not shift:
                self.select([])
            return
        last_time, last_id = self._last_click
        double = last_id == entity.id and self.clock - last_time < 0.4
        self._last_click = (self.clock, entity.id)
        if (double or ctrl) and isinstance(entity, Unit) and entity.player == self.human:
            self.select_same_type(entity, add=shift)
        elif shift and entity.player == self.human:
            self.select([entity.id], add=True)
        else:
            self.select([entity.id])

    def select_same_type(self, unit: Unit, *, add: bool = False) -> None:
        """Every unit of *unit*'s type that is on screen (a double-click or ctrl-click)."""
        left, top, right, bottom = self.camera.visible_world_rect()
        same = [u.id for u in self.view.units_in_rect(to_tiles(left, top), to_tiles(right, bottom), player=self.human) if u.type is unit.type]
        self.select(same if not add else [i for i in same if i not in self.selection], add=add)

    def select_army(self) -> None:
        """The Army button, Ctrl+A or Cmd+A on a Mac."""
        soldiers = [u.id for u in self._army()]
        if soldiers:
            self.select(soldiers)
        else:
            self.say("No soldiers yet")

    def box_select(self, a: tuple[float, float], b: tuple[float, float], shift: bool) -> None:
        units = self.view.units_in_rect(a, b, player=self.human)
        if units:
            self.select([u.id for u in units], add=shift)
        elif not shift:
            self.select([])

    def next_idle_peasant(self) -> None:
        self._cycle_idle(lambda u: u.is_worker, "No idle peasants")

    def next_idle_soldier(self) -> None:
        self._cycle_idle(lambda u: not u.is_worker, "No idle soldiers")

    def _cycle_idle(self, wanted: Callable[[Unit], bool], nothing: str) -> None:
        idle = sorted((u for u in self.world.player_units(self.human) if wanted(u) and not u.orders and not u.hidden), key=lambda u: u.id)
        if not idle:
            self.say(nothing)
            return
        ids = [u.id for u in idle]
        current = self.selection[0] if len(self.selection) == 1 and self.selection[0] in ids else None
        unit = idle[(ids.index(current) + 1) % len(ids)] if current is not None else idle[0]
        self.select([unit.id])
        self.camera.pan_to(*to_world(unit.pos), duration=0.25)

    # -- Orders ---------------------------------------------------------------------

    @property
    def toast_top(self) -> int:
        """Where notices slide in: under the objectives panel, which a mission makes taller than the tutorial strip."""
        if not self.objectives.visible:
            return TOAST_TOP
        _x, y, _w, _h = self.objectives.bounds
        return max(TOAST_TOP, y + self.objectives.get_preferred_size()[1] + 10)  # the preferred height follows a change at once

    def say(self, text: str) -> None:
        self.status = text
        self.status_timer = 3.0

    def warn(self, text: str) -> None:
        self.say(text)
        self.sfx("error")

    def _marker(self, point: tuple[float, float], color: tuple[int, int, int, int]) -> None:
        wx, wy = to_world(point)
        self.effects.add(Pulse((wx, wy), color, radius=(4, 18), rings=2, duration=0.5))

    def order(self, action, *args, **kwargs) -> None:
        """Give the match an order; a match played elsewhere (:class:`warband.ui.multiplayer.NetworkGameScene`) sends it there."""
        getattr(self.world, action)(*args, **kwargs)

    def attempt(self, action: str, *args, **kwargs) -> bool:
        """Give an order for the player.  When the rules refuse it, the status line says why and this is False.
        Every button, key and click goes through here, so a refusal is never an exception in the frame."""
        try:
            self.order(action, *args, **kwargs)
        except RuleError as exc:
            self.warn(str(exc))
            return False
        return True

    def _enemy(self, target: Entity | None) -> bool:
        return target is not None and target.player is not None and target.player != self.human

    def command_smart(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            ids = [u.id for u in units]
            target = self.view.entity_at(point)
            attack = self._enemy(target)  # the only context order that strikes: smart on anything else moves, mends, mines or builds
            if attack:
                given = self.attempt("attack", ids, target.id, queue=queue)
            else:
                given = self.attempt("smart", ids, point, queue=queue, target_id=target.id if target is not None else None)
            if given:
                self._marker(point, (255, 80, 70, 220) if attack else (120, 255, 140, 220))
                self.sfx("attack_command" if attack else "command")
            return
        building = self._own_building()
        if building is not None and building.done and self.attempt("set_rally", building.id, point):
            self._marker(point, (255, 214, 110, 220))
            self.sfx("command")

    def command_repair(self, point: tuple[float, float], *, queue: bool = False) -> None:
        workers = [u.id for u in self._own_units() if u.is_worker]
        target = self.view.entity_at(point)
        if not workers or not isinstance(target, Building):
            self.warn("Click one of your damaged buildings")
        elif self.attempt("repair", workers, target.id, queue=queue):
            self._marker(point, (120, 255, 140, 220))
            self.sfx("command")

    def command_move(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units and self.attempt("move", [u.id for u in units], point, queue=queue):
            self._marker(point, (120, 255, 140, 220))
            self.sfx("command")

    def command_attack(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if not units:
            return
        ids = [u.id for u in units]
        target = self.view.entity_at(point)
        if self._enemy(target):
            given = self.attempt("attack", ids, target.id, queue=queue)
        else:
            given = self.attempt("attack_move", ids, point, queue=queue)
        if given:
            self._marker(point, (255, 80, 70, 220))
            self.sfx("attack_command")

    def command_patrol(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units and self.attempt("patrol", [u.id for u in units], point, queue=queue):
            self._marker(point, (120, 200, 255, 220))
            self.sfx("command")

    def command_stop(self) -> None:
        units = self._own_units()
        if units and self.attempt("stop", [u.id for u in units]):
            self.sfx("command")

    def command_hold(self) -> None:
        units = self._own_units()
        if units and self.attempt("hold", [u.id for u in units]):
            self.sfx("command")

    def start_pending(self, mode: str) -> None:
        """Wait for the click that gives the order *mode*: "move", "attack", "patrol", "repair" or "assembly"."""
        self.pending = mode
        if mode == "assembly":
            self.catalogue = None
            self.say("Click the map to set an assembly point for new soldiers")
        self._refresh_card()

    # -- Placing buildings -------------------------------------------------------------

    def choose_building(self, building_type: BuildingType, *, keep: bool = False) -> None:
        """A building from the Build catalogue: its site follows the pointer until a click places it.  Chosen again
        while it is being placed, the planner picks the spot (*keep*, from Shift: and the next one stays ready)."""
        if self.placing is building_type:
            self.auto_place(building_type, keep=keep)
            return
        self.pending = f"place:{building_type.value}"
        self._refresh_card()

    def place(self, building_type: BuildingType, point: tuple[float, float], *, keep: bool = False) -> None:
        """A click while placing: *building_type* centred on *point*; *keep* (Shift) leaves the next one ready to place,
        as the Modal scheme always does."""
        if self._place_at(building_type, self._site_at(building_type, point)) and not (keep or self.scheme.sticky):
            self._end_placement()

    def auto_place(self, building_type: BuildingType, *, keep: bool = False) -> None:
        """Let the planner pick the spot (:func:`warband.brains.ai.auto_site`): about the hall nearest the camera, a hall
        by the nearest free mine."""
        planned = [(kind, pos) for kind, pos, _queued in self.pending_sites()]
        site = auto_site(self.world, building_type, self.human, to_tiles(*self.camera.center), self._site_rng, planned)
        if site is None:
            name = self.building_name(building_type)
            self.warn(f"No free gold mine known for a {name}" if building_type is BuildingType.TOWN_HALL else f"No room for a {name} near your hall")
            return
        if self._place_at(building_type, site) and not (keep or self.scheme.sticky):
            self._end_placement()

    def _site_at(self, building_type: BuildingType, point: tuple[float, float]) -> Pos:
        size = BUILDINGS[building_type].size
        return (int(math.floor(point[0] - size / 2 + 0.5)), int(math.floor(point[1] - size / 2 + 0.5)))

    def _builders(self) -> list[Unit]:
        """The selected peasants: who builds what is placed now.  With none, the settlement plans it."""
        return [u for u in self._own_units() if u.is_worker]

    def _by_plan(self, building_type: BuildingType) -> bool:
        """Whether a site placed now becomes a settlement plan: no peasant is selected, or its prerequisite does not stand
        yet (a plan waits for it; a peasant would be refused)."""
        requires = BUILDINGS[building_type].requires
        return not self._builders() or (requires is not None and not self.world.player_buildings(self.human, requires, done=True))

    def _place_at(self, building_type: BuildingType, site: Pos) -> bool:
        """Put *building_type* at *site*: the selected peasant with the fewest sites ahead of it goes (one that cannot pay
        when it gets there leaves the site as a plan), or the settlement plans it.  Whether it was placed."""
        size = BUILDINGS[building_type].size
        center = (site[0] + size / 2, site[1] + size / 2)
        if self._site_taken(building_type, site):
            self.warn("Another building is planned here")
            return False
        name = self.building_name(building_type)
        if not self._by_plan(building_type):
            builder = min(self._builders(), key=lambda u: (sum(isinstance(o, Build) for o in u.orders), u.hidden, math.dist(u.pos, center)))
            queue = any(isinstance(order, Build) for order in builder.orders)  # after its other sites, never after a harvest: that one never ends
            if not self.attempt("build", builder.id, building_type, site, queue=queue, plan_if_short=True):
                return False
        elif self.attempt("plan_building", self.human, building_type, site):
            requires = BUILDINGS[building_type].requires
            waits = requires is not None and not self.world.player_buildings(self.human, requires, done=True)
            self.say(f"{name} planned · it waits for a {self.building_name(requires)}" if waits and requires is not None else
                     f"{name} planned · a worker builds it when the money is there")
        else:
            return False
        self.sfx("command")
        self._marker(center, (255, 214, 110, 220))
        self._repeat = lambda: self.auto_place(building_type, keep=True)
        return True

    def _end_placement(self) -> None:
        """The site is placed: the pointer is free again, and the Build catalogue stays until Esc, as every catalogue does."""
        self.pending = None
        self._refresh_card()

    def pending_sites(self) -> list[tuple[BuildingType, Pos, bool]]:
        """Sites ordered and not yet begun, as ``(building, site, queued)``: the settlement's plans, then the sites the
        player's builders are on their way to (queued)."""
        sites = [(plan.type, plan.pos, False) for plan in self.world.player_plans(self.human) if plan.kind == "building" and plan.building is None]
        planned = {(kind, pos) for kind, pos, _queued in sites}
        for unit in self.world.player_units(self.human):
            for order in unit.orders:
                if isinstance(order, Build) and order.building is None and (order.type, order.pos) not in planned:
                    sites.append((order.type, order.pos, True))
        return sites

    def _site_taken(self, building_type: BuildingType, site: Pos) -> bool:
        size = BUILDINGS[building_type].size
        return any(site[0] < pos[0] + BUILDINGS[kind].size and pos[0] < site[0] + size and site[1] < pos[1] + BUILDINGS[kind].size
                   and pos[1] < site[1] + size for kind, pos, _queued in self.pending_sites())

    def _placement_reason(self, building_type: BuildingType, site: Pos) -> str | None:
        """Why *building_type* cannot be placed at *site* now, as the ghost shows it."""
        if self._site_taken(building_type, site):
            return "Another building is planned here"
        if self._by_plan(building_type):
            return self.world.can_plan_building(building_type, site, self.human)
        center = (site[0] + BUILDINGS[building_type].size / 2, site[1] + BUILDINGS[building_type].size / 2)
        builder = min(self._builders(), key=lambda u: math.dist(u.pos, center))
        return self.world.can_place(building_type, site, self.human, builder=builder.id)

    # -- Endless training ----------------------------------------------------------------

    def toggle_endless(self, building: Building, unit_type: UnitType) -> None:
        """Shift with a recruit's key, Shift+click or a right-click at a building: train it endlessly there, or no longer."""
        on = unit_type not in building.auto
        if not self.attempt("set_auto_train", building.id, unit_type, on):
            return
        self.sfx("button")
        name = self.building_name(building.type)
        rotation = [t for t in building.auto if t is not unit_type] + [unit_type] if on else [t for t in building.auto if t is not unit_type]
        if on:
            self.say(f"{name}: {', '.join(self.unit_name(t) for t in rotation)} endlessly" + (" in turn" if len(rotation) > 1 else ""))
        else:
            self.say(f"{name}: no more endless {self.unit_name(unit_type)}")
        self._refresh_card()

    def toggle_endless_everywhere(self, unit_type: UnitType) -> None:
        """The Train catalogue's Shift or right-click: every building that trains *unit_type* trains it endlessly, or
        none does when every one of them already did."""
        producers = self._producers(unit_type)
        where = self.building_name(UNITS[unit_type].trained_at)
        if not producers:
            self.warn(f"Requires a {where}")
            return
        on = not all(unit_type in b.auto for b in producers)
        given = sum(self.attempt("set_auto_train", b.id, unit_type, on) for b in producers)
        if given:
            self.sfx("button")
            self.say(f"{self.unit_name(unit_type)} endlessly at {given} {where}" if on else f"No more endless {self.unit_name(unit_type)}")
        self._refresh_card()

    def _producers(self, unit_type: UnitType) -> list[Building]:
        """The player's buildings that train *unit_type*, finished or going up."""
        return [b for b in self.world.player_buildings(self.human) if unit_type in b.info.trains and not b.abandoned]

    def repeat_last(self) -> None:
        """The Modal scheme's ".": the last recruit or placement once more."""
        if self._repeat is None:
            self.say("Nothing to repeat yet: train a unit or place a building first")
            return
        self._repeat()

    def unit_name(self, unit_type: UnitType) -> str:
        return self.race.units[unit_type].name

    def building_name(self, building_type: BuildingType) -> str:
        return self.race.buildings[building_type].name

    def train(self, unit_type: UnitType) -> None:
        building = self._own_building()
        if building is not None:
            self._train_at(building.id, unit_type)

    def _train_at(self, building_id: int, unit_type: UnitType) -> None:
        if self.attempt("train", building_id, unit_type):
            self.sfx("button")
            self._repeat = lambda: self._train_at(building_id, unit_type)
            self._refresh_card()

    def cancel_work(self) -> None:
        """Cancel the last recruit queued, or the research, and the building's endless training with it: it would only
        start the next one."""
        building = self._own_building()
        if building is None:
            return
        stopped = [unit_type for unit_type in list(building.auto) if self.attempt("set_auto_train", building.id, unit_type, False)]
        if building.queue or building.research is not None:
            if not self.attempt("cancel_train" if building.queue else "cancel_research", building.id):
                return
        elif not stopped:
            return
        if stopped:
            self.say("Endless training stopped")
        self.sfx("button")
        self._refresh_card()

    def research(self, upgrade: Upgrade) -> None:
        building = self._own_building()
        if building is not None and self.attempt("research", building.id, upgrade):
            self.sfx("button")
            self._refresh_card()

    def cancel_construction(self) -> None:
        building = self._own_building()
        if building is None or building.done or not self.attempt("cancel_building", building.id):
            return
        self.say(f"{building.info.name} cancelled, cost refunded")
        self.sfx("button")
        self.select([])

    def cancel(self) -> None:
        """Esc: back one level — the pending order (a building being placed goes back to the catalogue), the catalogue,
        the selection, and then the menu."""
        if self.pending is not None:
            self.pending = None
            self._refresh_card()
        elif self.catalogue is not None:
            self.open_catalogue(None)
        elif self.selection:
            self.select([])
        else:
            self.open_menu()

    # -- Settlement plans ----------------------------------------------------------

    def _plan_count(self) -> int:
        return len(self.world.player_plans(self.human)) + sum(len(b.queue) + (b.research is not None)
                                                            for b in self.world.player_buildings(self.human))

    def open_catalogue(self, kind: str | None) -> None:
        """Show the Build, Train or Upgrade catalogue on the card; None: the selection's card again."""
        self.catalogue = kind
        self.pending = None
        self._refresh_card()

    def toggle_catalogue(self, kind: str) -> None:
        """Open a catalogue, or close it when it is the one on the card."""
        self.open_catalogue(None if self.shown_catalogue == kind else kind)

    def do(self, action: str) -> None:
        """A global action (:data:`warband.ui.controls.ACTIONS`), from its key or its Ctrl chord."""
        if action in ("build", "train", "upgrade"):
            self.toggle_catalogue(action)
        elif action == "assembly":
            self.start_pending("assembly")
        elif action == "plans":
            self.open_plans()
        elif action == "idle_soldier":
            self.next_idle_soldier()
        elif action == "repeat":
            self.repeat_last()
        else:
            raise ValueError(f"No such action: {action}")

    def open_plans(self) -> None:
        self.game.push(SettlementPlansScene(self))

    def order_production(self, kind: str, item: UnitType | Upgrade) -> None:
        if not self.attempt("order_unit" if kind == "train" else "order_upgrade", self.human, item):
            return
        info = self.race.units[item] if kind == "train" else UPGRADES[item]
        self.say(f"{info.name} ordered · pay when work starts · manage in Plans")
        self.sfx("button")
        if kind == "train":
            self._repeat = lambda: self.order_production(kind, item)
        self._refresh_card()

    def set_assembly(self, point: tuple[float, float] | None) -> None:
        if not self.attempt("set_assembly", self.human, point):
            return
        self.say("Assembly point cleared" if point is None else "New soldiers will assemble here; workers keep working")
        self.sfx("command")

    def _look_at(self, building: Building) -> None:
        self.select([building.id])
        self.camera.pan_to(*to_world(building.center), duration=0.25)

    def _queue_entries(self) -> list[QueueEntry]:
        """Everything in training, research or construction, building by building, then the plans still waiting."""
        world, human, race = self.world, self.human, self.race
        plans = world.player_plans(human)
        sites = {p.pos for p in plans if p.kind == "building"}  # a plan's site, once dug, is listed with its plan
        entries = []
        for building in sorted(world.player_buildings(human), key=lambda b: b.id):
            look = lambda b=building: self._look_at(b)
            if not building.done:
                if building.pos not in sites:
                    progress = building.progress / building.info.build_time
                    entries.append(QueueEntry(building.type, f"{building.info.name} · building {int(progress * 100)}%", "working", progress, look,
                                              lambda b=building: self.attempt("cancel_building", b.id)))
                continue
            for index, unit_type in enumerate(building.queue):
                info = race.units[unit_type]
                cancel = lambda b=building, i=index: self.attempt("cancel_train", b.id, i)
                if index == 0:
                    progress = building.train_progress / info.build_time
                    entries.append(QueueEntry(unit_type, f"{info.name} · training {int(progress * 100)}% at the {building.info.name}", "working",
                                              progress, look, cancel))
                else:
                    entries.append(QueueEntry(unit_type, f"{info.name} · queued at the {building.info.name}, {index} ahead", "queued", 0.0, look, cancel))
            if building.research is not None:
                info = UPGRADES[building.research]
                progress = building.research_progress / info.time
                entries.append(QueueEntry(building.research, f"{info.name} · researching {int(progress * 100)}% at the {building.info.name}", "working",
                                          progress, look, lambda b=building: self.attempt("cancel_research", b.id)))
        for plan in plans:
            info = {"building": race.buildings, "unit": race.units, "upgrade": UPGRADES}[plan.kind][plan.type]
            cancel = lambda pid=plan.id: self.attempt("cancel_plan", human, pid)
            site = next((b for b in world.player_buildings(human, plan.type) if b.pos == plan.pos), None) if plan.kind == "building" else None
            if site is not None:
                progress = site.progress / site.info.build_time
                entries.append(QueueEntry(plan.type, f"{info.name} · building {int(progress * 100)}%", "working", progress, lambda b=site: self._look_at(b), cancel))
                continue
            goto = None
            if plan.kind == "building":
                size = BUILDINGS[plan.type].size
                goto = lambda p=plan, s=size: self.camera.pan_to(*to_world((p.pos[0] + s / 2, p.pos[1] + s / 2)), duration=0.25)
            entries.append(QueueEntry(plan.type, f"{info.name} · {plan.status}", "waiting", 0.0, goto, cancel))
        return entries

    def _upgrade_planned(self, upgrade: Upgrade) -> str | None:
        if upgrade in self.player.upgrades:
            return "Already researched"
        if (any(p.kind == "upgrade" and p.type is upgrade for p in self.world.player_plans(self.human))
                or any(b.research is upgrade for b in self.world.player_buildings(self.human))):
            return "Already ordered"
        return None

    def _ordered(self, target: UnitType | BuildingType) -> int:
        """How many of *target* are planned, queued or under construction."""
        world, human = self.world, self.human
        plans = [p for p in world.player_plans(human) if p.type is target]
        if isinstance(target, UnitType):
            return len(plans) + sum(b.queue.count(target) for b in world.player_buildings(human))
        planned = {p.pos for p in plans}  # a plan's site, once dug, is one of these buildings
        queued = sum(1 for kind, _pos, by_builder in self.pending_sites() if by_builder and kind is target)  # a builder's next sites
        return len(plans) + queued + sum(1 for b in world.player_buildings(human, target) if not b.done and b.pos not in planned)

    def _upgrades(self) -> list[Upgrade]:
        """The shared upgrades and the player's race arts, in the order of the table."""
        return [u for u in Upgrade if self.race.upgrade_allowed(u)]

    def _upgrade_keys(self) -> dict[Upgrade, str]:
        """Tiers share a letter: it goes to the lowest tier still to order, or stays on the top one so the key keeps answering."""
        chains: dict[str, list[Upgrade]] = {}
        for upgrade in self._upgrades():
            chains.setdefault(UPGRADES[upgrade].hotkey, []).append(upgrade)
        return {next((u for u in chain if self._upgrade_planned(u) is None), chain[-1]): letter.upper() for letter, chain in chains.items()}

    def _catalogue_commands(self, kind: str) -> list[Command]:
        """The Build, Train or Upgrade catalogue: everything the settlement can plan, each in its slot."""
        race, commands = self.race, []
        if kind == "build":
            for slot, building_type in enumerate(BUILD_ORDER):
                info = race.buildings[building_type]
                requires = info.requires
                waits = (f" · waits for a {self.building_name(requires)}"
                         if requires is not None and not self.world.player_buildings(self.human, requires, done=True) else "")
                commands.append(Command(race.cards[building_type], info.hotkey, lambda bt=building_type: self.choose_building(bt), slot,
                                        tooltip=f"{info.name} — {info.cost} · {info.summary}{waits} · its key again: the planner picks the spot",
                                        cost=f"{info.cost.gold} / {info.cost.lumber}", target=building_type,
                                        style=ACTION_BUTTON if self.placing is building_type else CARD_BUTTON,
                                        count=lambda bt=building_type: self._ordered(bt), alt=lambda bt=building_type: self.choose_building(bt, keep=True)))
        elif kind == "train":
            for slot, (unit_type, info) in enumerate(race.units.items()):
                commands.append(Command(info.name, info.hotkey, lambda ut=unit_type: self.order_production("train", ut), slot,
                                        tooltip=f"{info.name} — {info.cost} · {info.summary} · Shift or right-click: endlessly at every "
                                                f"{self.building_name(info.trained_at)}",
                                        cost=f"{info.cost.gold} / {info.cost.lumber}", target=unit_type, count=lambda ut=unit_type: self._ordered(ut),
                                        alt=lambda ut=unit_type: self.toggle_endless_everywhere(ut),
                                        endless=lambda ut=unit_type: any(ut in b.auto for b in self._producers(ut))))
        else:
            letters, arts = self._upgrade_keys(), iter(race.arts)
            for row, chain in enumerate(UPGRADE_ROWS):
                for column, listed in enumerate(chain):
                    upgrade = listed if listed is not None else next(arts)
                    info = UPGRADES[upgrade]
                    commands.append(Command(UPGRADE_NAMES[upgrade], letters.get(upgrade, ""), lambda up=upgrade: self.order_production("upgrade", up),
                                            row * CARD_COLS + column, tooltip=f"{info.name} — {info.cost} · {info.summary}",
                                            cost=f"{info.cost.gold} / {info.cost.lumber}", blocked=lambda up=upgrade: self._upgrade_planned(up),
                                            target=upgrade))
        return commands

    # -- Command card ----------------------------------------------------------------

    def _commands(self) -> list[Command]:
        """The card as it stands: the catalogue shown, else the selection's own commands."""
        catalogue = self.shown_catalogue
        if catalogue is not None:
            return self._catalogue_commands(catalogue)
        units = self._own_units()
        if units:
            return self._unit_commands(units)
        building = self._own_building()
        return self._building_commands(building) if building is not None else []

    def _unit_commands(self, units: list[Unit]) -> list[Command]:
        commands = [
            Command("Move", "m", lambda: self.start_pending("move"), UNIT_SLOTS["move"], tooltip="Move to a spot (right-click does this too)"),
            Command("Stop", "s", self.command_stop, UNIT_SLOTS["stop"], tooltip="Drop every order"),
            Command("Hold", "h", self.command_hold, UNIT_SLOTS["hold"], tooltip="Stand here; fight what comes in range but never chase"),
            Command("Attack", "a", lambda: self.start_pending("attack"), UNIT_SLOTS["attack"],
                    tooltip="Attack a target, or attack-move: fight everything on the way", style=DANGER_BUTTON),
            Command("Patrol", "p", lambda: self.start_pending("patrol"), UNIT_SLOTS["patrol"],
                    tooltip="Walk between here and a spot, fighting whatever turns up"),
        ]
        if any(u.is_worker for u in units):
            commands.append(Command("Build", "b", lambda: self.open_catalogue("build"), UNIT_SLOTS["build"],
                                    tooltip="Farms, barracks, halls, towers and the tech buildings, built by these peasants", style=ACTION_BUTTON))
            commands.append(Command("Repair", "r", lambda: self.start_pending("repair"), UNIT_SLOTS["repair"],
                                    tooltip="Mend one of your damaged buildings; a full repair costs half its price"))
        return commands

    def _building_commands(self, building: Building) -> list[Command]:
        """What it trains, then its research, one chain of tiers a slot, from the first slot on (a chain all researched
        keeps its slot, so no key moves); Cancel ends the first row, or the second when the work fills the first."""
        world = self.world
        if not building.done:
            return [Command("Cancel", "x", self.cancel_construction, CARD_COLS - 1, tooltip="Tear the site down; the cost comes back",
                            style=DANGER_BUTTON)]
        commands = []
        work: list[UnitType | Upgrade | None] = [*building.info.trains, *self._research_here(building)]
        for slot, item in enumerate(work):
            if isinstance(item, UnitType):
                info = self.race.units[item]
                commands.append(Command(info.name, info.hotkey, lambda ut=item: self.train(ut), slot,
                                        tooltip=f"{info.name} — {info.cost} · {info.summary} · Shift or right-click: train endlessly",
                                        blocked=lambda ut=item, b=building: world.can_train(b, ut), target=item,
                                        alt=lambda ut=item, b=building: self.toggle_endless(b, ut), endless=lambda ut=item, b=building: ut in b.auto))
            elif item is not None:  # None: every tier of the chain is researched, and its slot stays empty
                upgrade = UPGRADES[item]
                commands.append(Command(UPGRADE_NAMES[item], upgrade.hotkey, lambda up=item: self.research(up), slot,
                                        tooltip=f"{upgrade.name} — {upgrade.cost} · {upgrade.summary}",
                                        blocked=lambda up=item, b=building: world.can_research(b, up), target=item))
        if work:
            commands.append(Command("Cancel", "x", self.cancel_work, CARD_COLS - 1 if len(work) < CARD_COLS else 2 * CARD_COLS - 1,
                                    tooltip="Cancel the last unit queued or the research, and endless training",
                                    blocked=lambda b=building: None if b.queue or b.research is not None or b.auto else "Nothing in progress"))
        return commands

    def _research_here(self, building: Building) -> list[Upgrade | None]:
        """*building*'s research slots: each chain of tiers (they share a letter) shows its next tier, None once all are done."""
        chains: dict[str, list[Upgrade]] = {}
        for upgrade in building.info.researches:
            if self.race.upgrade_allowed(upgrade):
                chains.setdefault(UPGRADES[upgrade].hotkey, []).append(upgrade)
        return [next((u for u in chain if u not in self.player.upgrades), None) for chain in chains.values()]

    def _catalogue_title(self) -> str | None:
        """The settlement's catalogue on the card, as the production overview's heading names it (a peasant's Build shows
        the peasants instead: they build what is placed)."""
        return f"{self.shown_catalogue.title()} plans" if self.shown_catalogue is not None else None

    def _refresh_card(self) -> None:
        """Lay the card out afresh when what it holds changed: each command in its slot, three to a row, with the keys
        of the scheme on them; empty slots before the last keep the others in place."""
        commands = sorted(self._commands(), key=lambda c: c.slot)
        scheme = self.scheme
        for command in commands:
            key = scheme.card_key(command.letter, command.slot)
            command.hotkey = key_label(key) if key else ""
        back = self.catalogue is not None  # a catalogue opened over the card, not the Modal scheme's home
        signature = (back, scheme.positional, tuple((c.label, c.hotkey, c.cost, c.target, c.slot, c.style) for c in commands))
        if signature == self._card_signature:
            self._card = commands
            for command, button in zip(commands, self._card_buttons):
                button.on_click = command.action
                if isinstance(button, CardButton):
                    button.command = command
            return
        self._card_signature = signature
        self._card = commands
        self._card_buttons = []
        self.card_panel.clear()
        self.card_panel.visible = bool(commands)
        if not commands:
            return
        portraits = any(c.target is not None for c in commands)
        by_slot = {c.slot: c for c in commands}
        grid = len(GRID_KEYS)
        back_slot = (grid - 1 if grid - 1 not in by_slot else grid + CARD_COLS - 1) if back else None  # the bottom-right corner, or below it
        last = max(commands[-1].slot, back_slot if back_slot is not None else 0)
        for first in range(0, last + 1, CARD_COLS):
            row = Row(spacing=CARD_GAP)
            for slot in range(first, first + CARD_COLS):
                command = by_slot.get(slot)
                if slot == back_slot:
                    row.add(Button("Back", hotkey="Esc", on_click=self.cancel, style=GHOST_BUTTON, width=CARD_WIDTH,
                                   height=CARD_ICON if portraits else CARD_PLAIN))
                    continue
                if command is None:
                    row.add(_Slot(scheme.positional and slot < grid, width=CARD_WIDTH, height=CARD_ICON if portraits else CARD_PLAIN))
                    continue
                captions = []
                if command.target is not None:
                    # A portrait or emblem with the key in its corner; the name and any cost sit under it.
                    button = CardButton(command, self.human, self.player.race, width=CARD_WIDTH, height=CARD_ICON)

                    def caption(c=command) -> str:
                        ordered = c.count()
                        return f"{c.label} ×{ordered}" if ordered else c.label

                    captions.append(Label(caption, text_style="caption", width=CARD_WIDTH, align="center"))
                else:
                    button = Button(command.label, hotkey=command.hotkey or None, on_click=command.action,
                                    style=command.style, width=CARD_WIDTH, height=CARD_ICON if portraits else CARD_PLAIN)
                if command.cost:
                    captions.append(Label(command.cost, text_style="caption", width=CARD_WIDTH, align="center"))
                self._card_buttons.append(button)
                row.add(Column(button, *captions, spacing=3) if captions else button)
            self.card_panel.add(row)

    def _update_card(self) -> None:
        mx, my = self.mouse
        self.tooltip = next((hint for row, hint in self._resource_rows if row.hit_test(mx, my)), "")
        for command, button in zip(self._card, self._card_buttons):
            blocked = command.blocked()
            button.enabled = blocked is None
            x, y, w, h = button.bounds
            if x <= mx < x + w and y <= my < y + h:  # a disabled button still explains itself
                self.tooltip = command.tooltip + (f"  ({blocked})" if blocked else "")

    def _press_card_key(self, key: str, *, shift: bool = False) -> bool:
        """The card's command for *key*, if it has one: its action, or with Shift its alternative (endless training, or
        placing and staying ready to place)."""
        command = next((c for c in self._card if c.hotkey and c.key == key), None)
        if command is None:
            return False
        if shift and command.alt is not None:
            command.alt()
            return True
        blocked = command.blocked()
        if blocked is None:
            command.action()
        else:
            self.warn(blocked)
        return True

    # -- Groups ----------------------------------------------------------------------

    def _group(self, key: str, *, assign: bool, add: bool) -> None:
        if assign:
            units = [u.id for u in self._own_units()]
            if units:
                self.groups[key] = units
                self.say(f"Group {key}: {len(units)} units")
                self.sfx("button")
            return
        ids = [i for i in self.groups.get(key, []) if i in self.world.units]
        self.groups[key] = ids
        if ids:
            self.select(ids, add=add)

    # -- Navigation ---------------------------------------------------------------------

    def center_base(self, instant: bool = False) -> None:
        halls = self.world.player_buildings(self.human, BuildingType.TOWN_HALL)
        target = halls[0].center if halls else next((u.pos for u in self.world.player_units(self.human)), (self.world.width / 2, self.world.height / 2))
        if instant:
            self.camera.center_on(*to_world(target))
        else:
            self.camera.pan_to(*to_world(target), duration=0.3)

    def jump_to_alert(self) -> None:
        if self.last_alert is not None:
            self.camera.pan_to(*to_world(self.last_alert), duration=0.25)

    def _set_bookmark(self, slot: int) -> None:
        self.bookmarks[slot] = self.camera.center
        self.say(f"Camera bookmark {slot} set (F{5 + slot} to return)")
        self.sfx("button")

    def _recall_bookmark(self, slot: int) -> None:
        if slot in self.bookmarks:
            self.camera.pan_to(*self.bookmarks[slot], duration=0.2)
        else:
            self.say(f"No bookmark {slot}: Ctrl+F{5 + slot} sets one here")

    def set_bookmark_1(self) -> None:
        self._set_bookmark(1)

    def set_bookmark_2(self) -> None:
        self._set_bookmark(2)

    def set_bookmark_3(self) -> None:
        self._set_bookmark(3)

    def recall_bookmark_1(self) -> None:
        self._recall_bookmark(1)

    def recall_bookmark_2(self) -> None:
        self._recall_bookmark(2)

    def recall_bookmark_3(self) -> None:
        self._recall_bookmark(3)

    def minimap_click(self, wx: float, wy: float, button: str) -> None:
        if button == "right":
            self.command_smart(to_tiles(wx, wy))
        else:
            self.camera.center_on(wx, wy)

    def zoom_in(self) -> None:
        self._zoom_by(ZOOM_PER_KEY)

    def zoom_out(self) -> None:
        self._zoom_by(1 / ZOOM_PER_KEY)

    def _zoom_by(self, factor: float, at: tuple[float, float] | None = None) -> None:
        if at is None:
            w, h = self.game.resolution
            at = (w / 2, h / 2)
        self.camera.zoom_toward(self.camera.zoom_target * factor, *at)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.sfx("button")

    def open_menu(self) -> None:
        self.game.push(self.pause_menu())

    def pause_menu(self) -> Scene:
        return PauseScene(self)

    def open_help(self) -> None:
        self.game.push(HelpScene(self.scheme))

    def open_codex(self) -> None:
        self.game.push(CodexScene(self.world, self.human))

    def quick_save(self) -> None:
        self.save_to("quick")

    def quick_load(self) -> None:
        self.load_from("quick")

    def save_to(self, slot: int | str) -> None:
        self.game.save(slot, scene=self)
        self.say("Quicksaved (F9 loads it)" if slot == "quick" else f"Saved to slot {slot}")
        self.sfx("button")

    def load_from(self, slot: int | str) -> None:
        try:
            if self.game.load(slot, scene=self) is None:
                self.warn("Nothing saved there" if slot != "quick" else "No quicksave yet — F5 makes one")
        except SaveError as exc:
            self.warn(f"Could not load: {exc}")

    def open_saves(self, mode: str) -> None:
        self.game.push(SaveBrowserScene(self.game, mode, on_pick=self.save_to if mode == "save" else self.load_from))

    # -- Raw input ----------------------------------------------------------------------

    def handle_input(self, event: InputEvent) -> bool:
        self.alt_held = bool(event.alt)  # the engine keeps modifier keys' own presses; their flag on any input is what arrives
        if event.type == "key_press" and event.key is not None:
            return self.press(event.key, shift=event.shift, chord=event.ctrl or event.meta, alt=event.alt)
        if not event.is_mouse:
            return False
        point = to_tiles(event.world_x, event.world_y)  # type: ignore[arg-type]
        if event.type == "move":
            self.mouse = (event.x, event.y)
            self.hover = point
            return True
        if event.type == "click" and event.button == "left":
            if self.pending is not None:
                self._execute_pending(point, keep=event.shift)
                return True
            self._drag_start = self._drag_end = (event.x, event.y)
            return True
        if event.type == "drag" and event.button == "left":
            if self._drag_start is not None:
                self._drag_end = (event.x, event.y)
                self.mouse = (event.x, event.y)
            return True
        if event.type == "release" and event.button == "left":
            if self._drag_start is None:
                return True
            start, end = self._drag_start, self._drag_end or self._drag_start
            self._drag_start = self._drag_end = None
            if math.dist(start, end) < DRAG_THRESHOLD:
                self.click_select(point, event.shift, event.ctrl or event.meta)
            else:
                self.box_select(to_tiles(*self.camera.screen_to_world(*start)), to_tiles(*self.camera.screen_to_world(*end)), event.shift)
            return True
        if event.type == "click" and event.button == "right":
            if self.pending is not None:
                self.cancel()  # back one level, as Esc: a building being placed goes back to its catalogue
            else:
                self.command_smart(point, queue=event.shift)
            return True
        if event.type == "drag" and event.button == "middle":
            self.camera.scroll(-event.dx / self.camera.zoom, -event.dy / self.camera.zoom)
            return True
        if event.type == "scroll":
            lines = max(-MAX_LINES_PER_EVENT, min(MAX_LINES_PER_EVENT, event.dy))
            self._zoom_by(ZOOM_PER_LINE ** lines, (event.x, event.y))
            return True
        return False

    def press(self, key: str, *, shift: bool = False, chord: bool = False, alt: bool = False) -> bool:
        """A key: a control group, a Ctrl chord to the settlement, then the card's command, then the scheme's global
        keys (in Classic and Modal those letters answer only while the card leaves them free)."""
        if key in GROUP_KEYS:
            self._group(key, assign=chord, add=shift)
            return True
        if chord:
            if key in CHORDS:
                self.do(CHORDS[key])
                return True
            return False
        if alt:
            return False
        if self._press_card_key(key, shift=shift):
            return True
        action = self.scheme.action(key)
        if action is None:
            return False
        self.do(action)
        return True

    def _click_panel(self, x: float, y: float, button: str, *, shift: bool) -> bool:
        """Clicks on the selection panel's portraits: pick a unit out of a group, jump to a producer, or cancel its work."""
        if button == "left":
            for entity_id, (px, py, size, _) in self._portraits:
                if px <= x < px + size and py <= y < py + size:
                    self.select([entity_id], add=shift)
                    return True
            if self._page_tile is not None:
                px, py, pw, ph = self._page_tile
                if px <= x < px + pw and py <= y < py + ph:
                    self._portrait_page = (self._portrait_page + 1) % self._portrait_pages
                    return True
        for (px, py, pw, ph), entry in self._queue_hits:
            if not (px <= x < px + pw and py <= y < py + ph):
                continue
            if button == "right":
                if entry.cancel():
                    self.sfx("button")
                    self._refresh_card()
            elif button == "left" and entry.goto is not None:
                entry.goto()
            return True
        return False

    def _execute_pending(self, point: tuple[float, float], *, keep: bool) -> None:
        mode = self.pending
        placing = self.placing
        if placing is not None:
            self.place(placing, point, keep=keep)
            return
        if mode == "move":
            self.command_move(point, queue=keep)
        elif mode == "attack":
            self.command_attack(point, queue=keep)
        elif mode == "patrol":
            self.command_patrol(point, queue=keep)
        elif mode == "repair":
            self.command_repair(point, queue=keep)
        elif mode == "assembly":
            self.set_assembly(point)
        if not keep:
            self.pending = None
        self._refresh_card()

    # -- Frame ---------------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        self.status_timer = max(0.0, self.status_timer - dt)
        if self._warm is not None:
            for _ in range(6):
                if next(self._warm, None) is None:
                    self._warm = None
                    # The match's world, sprites and images are long-lived: freeze them out of the collector's
                    # scans, or every full collection walks them (26 ms and growing in a 150-unit battle, every
                    # two seconds).  What the previous match froze is thawed and buried first, so a session of
                    # many matches keeps only the current one out of reach.
                    gc.unfreeze()
                    gc.collect()
                    gc.freeze()
                    break
        self._advance(dt)
        self._handle_events(self.world.take_events())
        if not self._game_over:
            play_music(self.mood, self.player.race)
        self._prune_selection()
        self.effects.update(dt)
        self.bodies = [b for b in self.bodies if not b.done]
        self.stains = [s for s in self.stains if not s.done]
        self.view.sync(0.0 if self.paused else dt, fraction=self._motion_fraction())
        self._update_card()
        self.idle_button.visible = self._idle_peasant_count() > 0
        self.army_button.visible = bool(self._army())
        self._update_objectives()
        if self.world.time >= self._autosave_at and not self._game_over:
            self._autosave_at += AUTOSAVE_EVERY
            self.game.save(self.AUTOSAVE_SLOT, scene=self)
            self.say("Autosaved")
        self._check_game_over()

    def _motion_fraction(self) -> float:
        if self._game_over or self.world.winner is not None or not self.player.alive:
            return 1.0
        return self._acc / SIM_DT

    def _advance(self, dt: float) -> None:
        if not self.paused and not self._game_over and self.world.winner is None and self.player.alive:  # a decided match stays frozen
            self._acc += min(dt, 0.25) * self.speed
            steps = 0
            while self._acc >= SIM_DT and steps < MAX_STEPS_PER_FRAME:
                for brain in self.brains:
                    brain.think(self.world, self.rng)
                self.view.before_step()
                self.world.step()
                self._acc -= SIM_DT
                steps += 1
            if steps == MAX_STEPS_PER_FRAME:
                self._acc = 0.0

    @property
    def mood(self) -> str:
        """``"battle"`` after three blows struck by or on the player's forces within three
        seconds, and for ten seconds past the last; otherwise ``"peace"``."""
        while self._fights and self.clock - self._fights[0] > 3.0:
            self._fights.popleft()
        if len(self._fights) >= 3:
            self._battle_until = self.clock + 10.0
        return "battle" if self.clock < self._battle_until else "peace"

    def _mine(self, event: Event) -> bool:
        """Whether the player's forces struck or took this blow."""
        if event.player == self.human:
            return True
        striker = self.world.entity(event.entity) if event.entity is not None else None
        return striker is not None and striker.player == self.human

    def _handle_events(self, events: list[Event]) -> None:
        for index, e in enumerate(events):
            mine = e.player == self.human
            if e.kind == "hit":
                if self._mine(e):
                    self._fights.append(self.clock)
                self._show_hit(e)
            elif e.kind == "impact":
                self._show_impact(e, struck=any(h.kind == "hit" and h.entity == e.entity for h in events[index + 1:]))
            elif e.kind == "death":
                self._show_death(e)
            elif e.kind == "destroyed":
                self._show_destroyed(e)
            elif e.kind == "trained" and mine:
                self.sfx("trained", gap=0.5)
                self.effects.add(Pulse(to_world(e.pos), rgba(self.player.color, 160), radius=(6, 22), rings=1, duration=0.5))
            elif e.kind == "built" and mine:
                self.sfx("built")
                wx, wy = to_world(e.pos)
                self.effects.add(FloatingText(e.text, (wx, wy - TILE), GOLD, rise=26, duration=1.6))
            elif e.kind == "construction" and mine:
                self.sfx("build_start")
            elif e.kind == "researched" and mine:
                self.sfx("built")
                wx, wy = to_world(e.pos)
                self.effects.add(FloatingText(f"{e.text} researched", (wx, wy - TILE), GOLD, rise=26, duration=1.8))
                self._refresh_card()
            elif e.kind == "heal" and self._visible(e.pos):
                self._show_heal(e)
            elif e.kind == "tree_felled":
                self.view.tree_felled((int(e.pos[0]), int(e.pos[1])))
                if mine and self._audible(e.pos):
                    self.sfx("chop", gap=2.5)
            elif e.kind == "under_attack" and mine:
                self.last_alert = e.pos
                self.minimap.ping(*to_world(e.pos))
                self.effects.add(Toast("Under attack!", ["Press Space to look"], hold=3.0, top=self.toast_top))
                self.sfx("under_attack")
            elif e.kind == "refused" and mine:
                self.warn(e.text)
            elif e.kind in ("eliminated", "surrendered") and not mine:
                # Results pause this scene: a new toast would freeze mid-slide underneath them.
                if self.world.winner is None and self.player.alive:
                    self.effects.add(Toast("A rival falls", [e.text], accent=GOOD, hold=4.0, top=self.toast_top))
            elif e.kind == "exposed":
                self.effects.add(Toast(f"{e.text}'s last holdings are revealed", [e.text], hold=4.0, top=self.toast_top))
            elif e.kind == "exhausted":
                self.effects.add(FloatingText("Mine exhausted", (to_world(e.pos)[0], to_world(e.pos)[1] - TILE), MUTED, rise=20, duration=1.5))
            elif e.kind == "plunder" and mine:
                self.effects.add(FloatingText(f"+{e.amount} gold plundered", (to_world(e.pos)[0], to_world(e.pos)[1] - TILE), GOLD, rise=26, duration=1.8))

    def _visible(self, point: tuple[float, float]) -> bool:
        return self.world.is_visible(self.human, (int(point[0]), int(point[1])))

    def _audible(self, point: tuple[float, float]) -> bool:
        """Local action stays near the camera; strategic warnings bypass this check."""
        x, y = self.camera.world_to_screen(*to_world(point))
        width, height = self.game.resolution
        return self._visible(point) and 0 <= x <= width and 0 <= y <= height - SELECTION_HEIGHT

    def _show_hit(self, e: Event) -> None:
        if not self._visible(e.pos):
            return
        target = self.world.entity(e.other) if e.other is not None else None
        source = self.world.entity(e.entity) if e.entity is not None else None
        origin = (source.pos if isinstance(source, Unit) else source.center) if source is not None else None
        if e.other is not None and origin is not None:
            self._blows[e.other] = origin  # a killing blow has already removed its target: its death falls away from this
        if isinstance(target, Unit):
            self.view.hit_reaction(target, origin)
        wx, wy = to_world(e.pos)
        struck = (wx, wy - TILE * 0.45)
        if SHOT_LOOKS.get(e.source_type) == "mote":  # light opens no wound and chips nothing: it flares where it lands, body or wall
            self.effects.add(Flare(struck, "mote", SHOT_SIZE["mote"][0]))
            self.effects.add(Spray(struck, self._away(e.pos, origin), "spark", (255, 232, 150), 5, rng=self.fx_rng, speed=(40, 130),
                                   size=(3, 6), spread=55.0, lifetime=(0.15, 0.3)))
        elif e.target_type in FLESH or e.target_type == UnitType.CATAPULT.value:  # a unit, alive or just killed by this
            away = self._away(e.pos, origin)
            if e.target_type == UnitType.CATAPULT.value:
                self.effects.add(Spray(struck, away, "drop", (222, 184, 118), 10, rng=self.fx_rng, size=(3, 6)))  # pale wood chips off the dark frame
            elif self.settings["blood"]:
                self.effects.add(Spray(struck, away, "drop", (172, 22, 26), min(9, 3 + e.amount // 2), rng=self.fx_rng,
                                       size=(3, 5 + min(e.amount, 12) / 4)))  # a few drops for a light blow, a splash for a heavy one
            if e.target_armor > 0:
                self.effects.add(Burst(struck, (255, 236, 190, 255), 3, rng=self.fx_rng, size=5, speed=(50, 140)))  # off the armour
        self._sound_hit(e)  # a shot's blow is raised when the shot lands, so its sound is due now

    def _away(self, point: tuple[float, float], origin: tuple[float, float] | None) -> tuple[float, float]:
        """The unit direction from *origin* to *point* in world pixels; straight up when the blow's origin is unknown."""
        if origin is None:
            return (0.0, -1.0)
        (px, py), (ox, oy) = to_world(point), to_world(origin)
        length = math.hypot(px - ox, py - oy)
        return ((px - ox) / length, (py - oy) / length) if length else (0.0, -1.0)

    def _show_impact(self, e: Event, *, struck: bool) -> None:
        """A stone comes down: dust where it lands, and a thud of its own when it found nothing to hit."""
        if not self._visible(e.pos):
            return
        wx, wy = to_world(e.pos)
        self.effects.add(Burst((wx, wy), (200, 190, 170, 255), 12, rng=self.fx_rng, size=12, speed=(40, 140)))
        self.camera.shake(2, 0.15)
        if not struck and self._audible(e.pos):
            self.sfx("impact")

    def _sound_hit(self, event: Event) -> None:
        if self._audible(event.pos):
            source = self.world.entity(event.entity) if event.entity is not None else None
            self.sfx(impact_sound(event, source.race if source is not None else Race.HUMAN))  # a striker dead with its blow keeps the common Foley

    def _show_heal(self, e: Event) -> None:
        """A cleric's cast lands: rings and rising sparks on the patient, a small ring on the cleric, the amount
        floating up, and a soft chime."""
        wx, wy = to_world(e.pos)
        self.effects.add(Pulse((wx, wy), (140, 255, 160, 220), radius=(6, 26), rings=2, duration=0.7))
        self.effects.add(Burst((wx, wy), (170, 255, 180, 240), 14, size=12.0, speed=(40, 120)))
        self.effects.add(FloatingText(f"+{e.amount}", (wx, wy - TILE * 1.3), (150, 255, 170, 255), rise=22, duration=1.0))
        cleric = self.world.units.get(e.entity) if e.entity is not None else None
        if cleric is not None:
            self.effects.add(Pulse(to_world(cleric.pos), (200, 255, 210, 180), radius=(4, 14), rings=1, duration=0.45))
        if self._audible(e.pos):
            self.sfx("heal", gap=0.2)

    def _show_death(self, e: Event) -> None:
        blow = self._blows.pop(e.entity, None)
        if not self._visible(e.pos):
            return
        sprite = self.view.release_unit_sprite(e.entity) if e.entity is not None else None
        if sprite is not None:
            self.add_sprite(sprite)
            body = UnitDeath(sprite, to_world(e.pos), source=to_world(blow) if blow is not None else None,
                             outcome=death_outcome(UnitType(e.text)), on_land=self._dust)
            self.effects.add(body)  # the body falls and lies there a while
            self.bodies = [b for b in self.bodies if not b.done and not b.cancelled] + [body]
            for old in self.bodies[:-UnitDeath.BODIES]:
                old.hurry()
            if self.settings["blood"] and e.text in FLESH:
                self._stain((body.position[0] + 10 * math.copysign(1, body.turn), body.position[1]))
        color = self.world.players[e.player].color if e.player is not None else (200, 200, 200)
        self.effects.add(Burst(to_world(e.pos), rgba(color), 10, rng=self.fx_rng, size=10))
        if self._audible(e.pos):
            self.sfx(deaths.cue(self.world.players[e.player].race))

    def _stain(self, point: tuple[float, float]) -> None:
        """A dark pool under a body, on the ground under everything that walks; the oldest make room past the cap."""
        sprite = self.add_sprite(Sprite("stain", position=point, size=(30, 19), layer=RenderLayer.OBJECTS))
        sprite.tint, sprite.opacity = (.42, .06, .07), Stain.OPACITY
        stain = Stain(sprite)
        self.effects.add(stain)
        self.stains = [s for s in self.stains if not s.done and not s.cancelled] + [stain]
        for old in self.stains[:-Stain.STAINS]:
            old.hurry()

    def _dust(self, feet: tuple[float, float], outcome: str) -> None:
        """The landing raises dust at the feet; a wreck raises more, and smoke."""
        self.effects.add(Burst(feet, (200, 190, 170, 255), 14 if outcome == "wreck" else 6, rng=self.fx_rng, size=8, speed=(30, 90)))
        if outcome == "wreck":
            self.effects.add(Burst((feet[0], feet[1] - 10), (150, 146, 140, 170), 5, rng=self.fx_rng, image="smoke", size=14, speed=(8, 30)))

    def _show_destroyed(self, e: Event) -> None:
        if e.player == self.human:
            self.effects.add(Toast("Building lost", [f"Your {self.building_name(BuildingType(e.text)).lower()} was destroyed"], hold=4.0, top=self.toast_top))
        if self._visible(e.pos):
            wx, wy = to_world(e.pos)
            self.effects.add(Burst((wx, wy), (255, 160, 80, 255), 18, rng=self.fx_rng, size=16, speed=(40, 160)))
            self.effects.add(Burst((wx, wy - 10), (60, 60, 64, 255), 14, rng=self.fx_rng, image="smoke", size=28, speed=(10, 50)))
            self.camera.shake(4, 0.3)
            if self._audible(e.pos):
                self.sfx(wreckage.cue(wreckage.material(BuildingType(e.text))), gap=0.3)

    def _check_game_over(self) -> None:
        if self._game_over:
            return
        if self.world.winner is not None or not self.player.alive:
            won = self.world.winner == self.human
            self._finish(won)
            self.game.push(GameOverScene(self))

    def _finish(self, won: bool) -> None:
        self._game_over = True
        self.sfx("victory" if won else "defeat")
        play_music("victory" if won else "defeat")
        if self._resignation is not None:
            self.conclude("resigned", self._resignation)
        else:
            self.conclude("victory" if won else "defeat")

    # -- The record of the match -------------------------------------------------------------

    def _recording(self, replay: Replay | None) -> Replay:
        """The recording of this match: the one a save carried, taken up again, or a fresh one from here."""
        if replay is None:
            return Replay.begin(self.world, seed=self.seed, difficulty=self.difficulty, human=self.human)
        replay.reloaded(self.world)
        return replay

    def _load_profile(self) -> None:
        """The profile a rated match is played under; its name is the player's.  An unreadable one is reported at the end."""
        if not self.ranked:
            return
        try:
            self.profile = Profile.load(self.game.data_dir)
        except SaveError as error:
            self.profile, self.profile_error = None, str(error)
            return
        self.player.name = self.profile.name

    def leaving(self) -> Standing | None:
        """What leaving the match now would count as, or None when leaving costs nothing: the match is decided or not rated."""
        if self.replay is None or self.profile is None or self._game_over or self.world.winner is not None or not self.player.alive:
            return None
        return standing(self.world, self.human)

    def resign(self, where: Standing) -> None:
        """Concede from *where* the player stands, which is what the resignation will be rated on."""
        self._resignation = where
        self.world.resign(self.human)

    def conclude(self, outcome: str, where: Standing | None = None) -> RatingChange | None:
        """Close the record of the match: the replay to disk, the result and its weight to the profile.

        Returns what the result did to the rating, or None when the match is not rated.  A result for a
        match already rated (a save of it reopened, a match finished after it was left) replaces the old one.
        """
        if self.replay is None or self.profile is None:
            return None
        world = self.world
        self.replay.finish(world, outcome)
        try:
            ReplayStore(self.game.data_dir).save(self.run_id, self.replay, {
                "name": self.player.name, "outcome": outcome, "race": self.player.race.value, "difficulty": self.difficulty.value,
                "players": len(world.players), "size": f"{world.width}×{world.height}", "clock": _clock(world.time), "seed": self.seed})
            kept = True
        except SaveError as error:
            kept = False
            self.say(f"Replay not saved: {error}")
        weight, reason = (where.weight, where.reason) if where is not None else (1.0, "")
        result = MatchResult(self.run_id, datetime.now(timezone.utc).isoformat(), outcome, weight, reason, self.difficulty.value,
                             DIFFICULTY_ELO[self.difficulty], len(world.players) - 1, self.player.race.value, world.width, world.height,
                             world.theme.value, world.layout.value, self.seed, int(world.time), kept)
        try:
            self.rating_change = self.profile.record(result)
        except SaveError as error:
            self.profile_error = str(error)
            self.say(f"Result not recorded: {error}")
            return None
        return self.rating_change

    # -- Drawing ---------------------------------------------------------------------------

    def ghost(self) -> tuple[BuildingType, Pos, bool] | None:
        """The building being placed where a click would put it, and whether it may go there."""
        building_type = self.placing
        if building_type is None or self.ui.pointer_target(*self.mouse) is not None:
            return None
        site = self._site_at(building_type, self.hover)
        return (building_type, site, self._placement_reason(building_type, site) is None)

    def draw(self) -> None:
        hovered = None
        if self.ui.pointer_target(*self.mouse) is None and self.pending is None:
            entity = self.view.entity_at(self.hover)
            hovered = entity.id if entity is not None else None
        self.view.draw(Overlay(selected=list(self.selection), hovered=hovered, ghost=self.ghost(), bars_for_all=self.all_bars or self.alt_held,
                               rally_for=[b.id for b in [self._own_building()] if b is not None]))
        ambience.draw(self, self.world, self.human)
        self._draw_settlement_markers()
        if self._drag_start is not None and self._drag_end is not None and math.dist(self._drag_start, self._drag_end) >= DRAG_THRESHOLD:
            (x0, y0), (x1, y1) = self._drag_start, self._drag_end
            self.draw_rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), (120, 255, 140, 40), border_color=(120, 255, 140, 220), border_width=1)
        w, h = self.game.resolution
        self.draw_rect(0, h - HINT_BAR, w, HINT_BAR, (8, 10, 14, 180))
        self._draw_selection_panel()
        self.effects.draw(self)

    def _draw_settlement_markers(self) -> None:
        """Sites ordered and not yet begun: a plan's in blue, a builder's next sites in gold."""
        for kind, pos, queued in self.pending_sites():
            x, y = to_world(pos)
            size = BUILDINGS[kind].size * TILE
            fill, border, text = ((255, 214, 110, 26), (255, 214, 110, 210), GOLD) if queued else ((110, 190, 255, 28), (150, 210, 255, 220), (180, 220, 255, 255))
            self.draw_rect(x, y, size, size, fill, border_color=border, border_width=2, space="world")
            self.draw_text(f"{'Next' if queued else 'Planned'} {self.building_name(kind)}", x + size / 2, y - 5, style="caption",
                           color=text, anchor_x="center", space="world")
        if self.player.assembly is not None:
            x, y = to_world(self.player.assembly)
            self.draw_line(x, y, x, y - 32, GOLD, width=3, space="world")
            self.draw_polygon([(x, y - 32), (x + 20, y - 25), (x, y - 18)], GOLD, space="world")
            self.draw_circle(x, y, 5, GOLD, space="world")
            self.draw_text("Assembly", x + 7, y + 14, style="caption", color=GOLD, space="world")

    def _draw_selection_panel(self) -> None:
        panel = self.selection_panel
        x, y, w, h = panel.bounds
        self.command_tooltip.visible = bool(self.tooltip)  # set again below: the production readout adds hover hints while drawing
        self.draw_rect(x, y, w, h, PANEL_STYLE.background_color, border_color=PANEL_STYLE.border_color,
                       border_width=1, radius=10)
        self._portraits = []
        self._page_tile = None
        self._queue_hits = []
        # A unit as it is; a building as the player knows it, which under the fog is as they last saw it.
        entities = [e for e in (self.world.units.get(i) or self.view.sighting(i) for i in self.selection) if e is not None]
        if not entities or (self.shown_catalogue is not None and not self._builders()):  # planning for the settlement: what it has in hand
            self._draw_queue(x, y, w)
            self.command_tooltip.visible = bool(self.tooltip)
            return
        if len(entities) == 1:
            self._draw_entity_card(entities[0], x + 16, y + 14)
        else:
            self._draw_portrait_grid(entities, x, y)
        self.command_tooltip.visible = bool(self.tooltip)

    def _draw_portrait_grid(self, entities: list[Entity], x: float, y: float) -> None:
        """Two rows of portraits with a health strip each; a selection too large for the grid pages, its last cell turning the page."""
        per_page = PORTRAITS_PER_PAGE if len(entities) <= PORTRAITS_PER_PAGE else PORTRAITS_PER_PAGE - 1
        self._portrait_pages = pages = max(1, math.ceil(len(entities) / per_page))
        self._portrait_page = page = min(self._portrait_page, pages - 1)
        self._page_tile = None
        heading = f"{len(entities)} units" + (f" · page {page + 1} of {pages}" if pages > 1 else "")
        self.draw_text(heading, x + 16, y + 30, style="heading")
        size, gap = PORTRAIT, PORTRAIT_GAP
        cells = list(entities[page * per_page:(page + 1) * per_page])
        for i in range(len(cells) + (1 if pages > 1 else 0)):
            px, py = x + 16 + (i % PORTRAIT_COLS) * (size + gap), y + 44 + (i // PORTRAIT_COLS) * (size + 9)
            self.draw_rect(px, py, size, size, (255, 255, 255, 18), border_color=(255, 255, 255, 40), border_width=1, radius=4)
            if i == len(cells):  # the page tile
                self._page_tile = (px, py, size, size)
                self.draw_polygon([(px + size * .36, py + size * .26), (px + size * .72, py + size * .5), (px + size * .36, py + size * .74)], GOLD)
                continue
            entity = cells[i]
            self._portraits.append((entity.id, (px, py, size, size)))
            self._portrait(entity, px + 3, py + 2, size - 6)
            frac = entity.hp / max(1, entity.max_hp)
            self.draw_rect(px, py + size + 2, size, 4, (0, 0, 0, 160))
            self.draw_rect(px, py + size + 2, size * frac, 4, GOOD if frac > 0.5 else BAD)

    def _draw_queue(self, x: float, y: float, w: float) -> None:
        """The production overview where the selection would be: one portrait per item being made or waited for."""
        entries = self._queue_entries()
        title = self._catalogue_title()
        if not entries:
            if title is not None:
                self.draw_text(title, x + 16, y + 30, style="heading")
                self.draw_text("Nothing planned · plans wait for money and prerequisites", x + 16, y + 58, style="sub")
                return
            tile = (int(self.hover[0]), int(self.hover[1]))
            text = "Nothing selected"
            if self.world.in_bounds(tile) and self.world.is_explored(self.human, tile):
                text = f"{self.view.terrain_at(tile).value.title()} ({tile[0]}, {tile[1]})"
            self.draw_text(text, x + 16, y + 30, style="heading")
            self.draw_text("Drag to select units · right-click to order them", x + 16, y + 58, style="sub")
            return
        working = sum(e.state != "waiting" for e in entries)
        waiting = len(entries) - working
        summary = " · ".join(part for part in (f"{working} in progress" if working else "", f"{waiting} waiting" if waiting else "") if part)
        self.draw_text(f"{title or 'Production'} · {summary}", x + 16, y + 30, style="heading")
        size, gap = 34, 4
        room = int((w - 32 + gap) // (size + gap))
        shown = entries if len(entries) <= room else entries[:room - 1]
        mx, my = self.mouse
        for i, entry in enumerate(shown):
            px, py = x + 16 + i * (size + gap), y + 46
            self._queue_hits.append(((px, py, size, size + 6), entry))
            hovered = px <= mx < px + size and py <= my < py + size + 6
            border = (255, 214, 110, 200) if entry.state == "working" else (255, 255, 255, 90 if hovered else 40)
            self.draw_rect(px, py, size, size, (255, 255, 255, 30 if hovered else 18), border_color=border, border_width=1, radius=4)
            draw_production_icon(self, entry.target, self.human, self.player.race, px + 3, py + 2, size - 6, opacity=1.0 if entry.state != "waiting" else 0.45)
            if entry.state != "waiting":
                self.draw_rect(px, py + size + 3, size, 3, (0, 0, 0, 160))
                self.draw_rect(px, py + size + 3, size * entry.progress, 3, GOLD)
            if hovered:
                self.tooltip = entry.hint
        if len(shown) < len(entries):
            self.draw_text(f"+{len(entries) - len(shown)}", x + 16 + len(shown) * (size + gap), y + 46 + size / 2, style="body", anchor_y="center")
        self.draw_text("Hover for details · click to go there · right-click to cancel", x + 16, y + 106, style="sub")

    def _endless_line(self, building: Building) -> str:
        """What *building* trains endlessly, the next one first."""
        names = [self.unit_name(unit_type) for unit_type in building.auto]
        return "Endless: " + ", ".join(names) + (" in turn" if len(names) > 1 else "")

    def _portrait(self, entity: Unit | Sighting, x: float, y: float, size: float) -> None:
        draw_production_icon(self, entity.type, entity.player, entity.race, x, y, size)

    def _draw_production(self, building: Building, x: float, y: float) -> None:
        """What a building is making: the target's portrait with its progress, then the queue's portraits."""
        world = self.world
        if building.queue:
            target = building.queue[0]
            info = world.unit_info(building.player, target)
            progress, hint = building.train_progress / info.build_time, f"Training {info.name}"
        else:
            target = building.research
            assert target is not None
            progress, hint = building.research_progress / UPGRADES[target].time, f"Researching {UPGRADES[target].name}"
        self.draw_rect(x, y, 36, 36, (255, 214, 110, 18), border_color=(255, 214, 110, 140), border_width=1, radius=5)
        draw_production_icon(self, target, building.player, building.race, x + 3, y + 3, 30)
        self.draw_text(f"{int(progress * 100)}%", x + 44, y + 15, style="body")
        self.draw_rect(x + 44, y + 24, 94, 6, (0, 0, 0, 160), radius=3)
        self.draw_rect(x + 44, y + 24, 94 * progress, 6, GOLD, radius=3)
        mx, my = self.mouse
        if x <= mx < x + 138 and y <= my < y + 36:
            self.tooltip = f"{hint} · {int(progress * 100)}%"
        if len(building.queue) > 1:
            self.draw_text("›", x + 144, y + 25, style="heading")
        for i, queued in enumerate(building.queue[1:]):
            qx, qy = x + 164 + i * 40, y + 3
            self.draw_rect(qx, qy, 30, 30, (255, 255, 255, 12), border_color=(255, 255, 255, 40), border_width=1, radius=4)
            draw_production_icon(self, queued, building.player, building.race, qx + 2, qy + 2, 26)
            if qx <= mx < qx + 30 and qy <= my < qy + 30:
                self.tooltip = f"Queued {i + 1}: {world.unit_info(building.player, queued).name}"

    def _draw_entity_card(self, entity: Unit | Sighting, x: float, y: float) -> None:
        """One selected unit or building.  What a rival's unit is ordered to do and what their building is
        making are theirs to know: the card says them of the player's own only."""
        world = self.world
        own = entity.player == self.human
        self.draw_rect(x, y, 72, 72, (255, 255, 255, 16), border_color=(255, 255, 255, 40), border_width=1, radius=6)
        self._portrait(entity, x + 4, y + 4, 64)
        tx = x + 88
        abandoned = isinstance(entity, Sighting) and entity.abandoned
        owner = "Abandoned" if abandoned else world.players[entity.player].name if entity.player is not None else "Neutral"
        name = entity.info.name if isinstance(entity, Unit) else RACES[entity.race].buildings[entity.type].name
        self.draw_text(f"{name}", tx, y + 16, style="heading")
        color = MUTED if abandoned else rgba(world.players[entity.player].color) if entity.player is not None else GOLD
        heading = self.game.theme.get_text_style("heading")  # the name's style: the owner follows wherever the theme ends it
        self.draw_text(owner, tx + 6 + self.game.backend.measure_text(name, heading.font_size, heading.font)[0], y + 16, style="sub", color=color)
        lines: list[str] = []
        if isinstance(entity, Sighting) and entity.type is BuildingType.GOLD_MINE:
            lines.append(f"{entity.gold} gold left")
        else:
            self.draw_rect(tx, y + 26, 180, 8, (0, 0, 0, 160), radius=3)
            frac = entity.hp / max(1, entity.max_hp)
            self.draw_rect(tx, y + 26, 180 * frac, 8, GOOD if frac > 0.5 else (240, 200, 80, 255) if frac > 0.25 else BAD, radius=3)
            self.draw_text(f"{entity.hp}/{entity.max_hp}", tx + 188, y + 34, style="sub")
        if isinstance(entity, Unit):
            info = entity.info
            primary = (("health", f"+{world.heal_amount(entity)}", f"Healing per cast, one every {info.period:g} s; its own blow is {world.damage_of(entity)}")
                       if info.heal
                       else ("damage", str(world.damage_of(entity)), f"Damage per strike; {attack_hint(info.attack)}"))
            stats = [primary, ("armor", str(world.armor_of(entity)),
                               f"{armour_name(info.armor_class).capitalize()}; armour is subtracted from every blow"),
                     ("range", f"{world.range_of(entity):g}", "Healing range in tiles" if info.heal else "Attack range in tiles"),
                     ("speed", f"{world.speed_of(entity):g}", "Speed in tiles per second")]
            mx, my = self.mouse
            for i, (icon, value, hint) in enumerate(stats):
                sx = tx + i * 78
                draw_icon(self, icon, sx, y + 45, 19)
                self.draw_text(value, sx + 24, y + 60, style="body")
                if sx <= mx < sx + 74 and y + 42 <= my < y + 64:
                    self.tooltip = hint
            if world.frenzied(entity):
                self.draw_text("Frenzy!", tx + 4 * 78, y + 60, style="body", color=BAD)
            order = entity.order
            if not own:
                pass
            elif entity.inside is not None:
                lines.append("Mining")
            elif entity.constructing is not None:
                lines.append("Building")
            elif entity.carrying is not None:
                lines.append(f"Carrying {entity.carry} {entity.carrying.value}")
            elif order is not None:
                lines.append(type(order).__name__.replace("AttackMove", "Attack-moving").replace("Move", "Moving").replace("Attack", "Attacking")
                             .replace("Harvest", "Harvesting").replace("Build", "Going to build").replace("Hold", "Holding position").replace("Heal", "Healing")
                             .replace("Patrol", "Patrolling"))
            else:
                lines.append("Idle")
        else:
            building = world.buildings.get(entity.id) if own else None  # the player's own, as it is: what it is making, who builds it
            if not entity.done:
                unmanned = building is not None and building.builder is None
                lines.append(f"Under construction {int(entity.built * 100)}%" + (" — no builder: right-click it with a peasant" if unmanned else ""))
            elif building is not None and (building.queue or building.research is not None):
                self._draw_production(building, tx, y + 44)
                if building.auto:
                    self.draw_text(self._endless_line(building), tx, y + 96, style="body", color=GOLD)
            elif building is not None and building.auto:
                lines.append(self._endless_line(building))
                reason = world.auto_train_blocker(building)  # the first named is the next, and waits for this
                if reason is not None:
                    lines.append(reason)
            elif building is not None:
                lines.append(building.info.summary)
                if building.type is BuildingType.TOWN_HALL:
                    lines.append("Rally point set" if building.rally is not None else "Right-click the map to set a rally point")
        ly = y + 82 if isinstance(entity, Unit) else y + 50
        for line in lines[:2]:
            self.draw_text(line, tx, ly, style="body")
            ly += 22

    # -- Save / load ------------------------------------------------------------------------

    def get_save_state(self) -> dict:
        return {"version": SAVE_VERSION, "seed": self.seed, "difficulty": self.difficulty.value, "world": self.world.to_dict(),
                "run_id": self.run_id, "ranked": self.ranked, "replay": self.replay.to_dict() if self.replay is not None else None,
                "groups": self.groups, "tutorial": self.tutorial.step if self.tutorial is not None else None, "seen": self._memory()}

    def _memory(self) -> dict | None:
        """What the player had seen of buildings now out of sight: the view's once there is one, until then what a save brought."""
        return self.view.memory() if self.view is not None else self._seen

    def get_save_summary(self) -> dict:
        world = self.world
        size = next((name for name, (w, h) in mapgen.SIZES.items() if (w, h) == (world.width, world.height)), f"{world.width}×{world.height}")
        return {"map": f"{size} {world.theme.value} {world.layout.value}", "players": len(world.players), "difficulty": self.difficulty.value, "clock": _clock(world.time),
                "player": f"{self.player.name} ({self.race.name})"}

    def load_save_state(self, state: dict) -> None:
        """A load is a new match scene, in the match as from the title: nothing of the timeline left behind
        (its last alert, its battle mood, where its brains' random stream had got to) follows into the loaded one."""
        scene = load_game(state, settings=self.settings)
        scene.say("Loaded")
        self.game.clear_and_push(scene)


class _Overlay(Scene):
    """Transparent modal panel; Escape closes.  The match keeps running below unless it pauses it."""

    transparent = True
    pause_below = False
    pop_on_cancel = True

    def panel(self, title: str) -> Column:
        panel = Column(spacing=10, anchor=Anchor.CENTER, style=OVERLAY_STYLE)
        panel.add(Label(title, text_style="title"))
        self.ui.add(panel)
        return panel

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (4, 6, 12, 150))


class SettlementPlansScene(_Overlay):
    """A live, paged view of waiting plans and the production they start."""

    PAGE_SIZE = 5

    def __init__(self, game_scene: GameScene) -> None:
        self.game_scene = game_scene
        self.page = 0
        self._signature = None
        self._row_controls = []
        self.notice = ""

    def on_enter(self) -> None:
        panel = self.panel("Plans & production")
        panel.add(Label("Plans wait for resources, prerequisites and workers. Costs are paid when work starts.",
                        text_style="body", width=660, wrap=True))
        panel.add(Label("The match continues while this panel is open.", text_style="sub", width=660))
        self.rows = Column(spacing=12, width=660)
        panel.add(self.rows)
        self.previous = Button("Previous", on_click=lambda: self.change_page(-1), style=GHOST_BUTTON, width=120)
        self.next = Button("Next", on_click=lambda: self.change_page(1), style=GHOST_BUTTON, width=120)
        self.page_label = Label("", text_style="sub", width=150, align="center")
        panel.add(Row(self.previous, self.page_label, self.next, spacing=12))
        panel.add(Label(lambda: self.notice, text_style="sub", width=660, wrap=True, text_color=BAD))
        self.clear_assembly = Button("Clear assembly point", on_click=lambda: self.game_scene.set_assembly(None),
                                     style=GHOST_BUTTON, width=240)
        panel.add(Row(self.clear_assembly, Button("Back", shortcut="Esc", on_click=self.game.pop,
                                                style=ACTION_BUTTON, width=180), spacing=12))
        self._refresh()

    def change_page(self, direction: int) -> None:
        self.page += direction
        self._refresh()

    def _cancel(self, action: str, *args) -> None:
        try:
            self.game_scene.order(action, *args)
        except RuleError as exc:
            self.notice = str(exc)
            return
        self.notice = ""
        self.game_scene.sfx("button")
        self._refresh()

    def _entries(self):
        world, human = self.game_scene.world, self.game_scene.human
        entries = []
        race = self.game_scene.race
        for plan in world.player_plans(human):
            catalogue = {"building": race.buildings, "unit": race.units, "upgrade": UPGRADES}[plan.kind]
            info = catalogue[plan.type]
            building = world.buildings.get(plan.building)
            status = plan.status
            if building is not None:
                status = f"Building {int(100 * building.progress / building.info.build_time)}%"
            detail = f"{status} · {'Paid' if building is not None else 'Cost'} {info.cost}"
            entries.append((("plan", plan.id), info.name, detail, "Cancel",
                            lambda pid=plan.id: self._cancel("cancel_plan", human, pid)))
        for building in world.player_buildings(human):
            if building.queue:
                info = race.units[building.queue[0]]
                progress = int(100 * building.train_progress / info.build_time)
                entries.append((("train", building.id), f"{building.info.name}: {info.name}",
                                f"Training {progress}% · {len(building.queue)} in queue · current cost {info.cost} paid", "Cancel last",
                                lambda bid=building.id: self._cancel("cancel_train", bid)))
            if building.research is not None:
                info = UPGRADES[building.research]
                progress = int(100 * building.research_progress / info.time)
                entries.append((("research", building.id), f"{building.info.name}: {info.name}",
                                f"Researching {progress}% · {info.cost} paid", "Cancel",
                                lambda bid=building.id: self._cancel("cancel_research", bid)))
        return entries

    def _refresh(self) -> None:
        entries = self._entries()
        pages = max(1, math.ceil(len(entries) / self.PAGE_SIZE))
        self.page = max(0, min(self.page, pages - 1))
        visible = entries[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        signature = tuple(entry[0] for entry in visible)
        if signature != self._signature:
            self._signature = signature
            self.rows.clear()
            self._row_controls = []
            if not visible:
                self.rows.add(Label("No pending plans or production.", text_style="heading", width=660))
            for _key, title, detail, label, action in visible:
                heading = Label(title, text_style="body", width=510)
                status = Label(detail, text_style="sub", width=510, wrap=True)
                cancel = Button(label, on_click=action, style=GHOST_BUTTON, width=130)
                self.rows.add(Row(Column(heading, status, spacing=3), cancel, spacing=20))
                self._row_controls.append((heading, status, cancel))
        for (_key, title, detail, label, action), (heading, status, cancel) in zip(visible, self._row_controls):
            heading.text, status.text, cancel.text, cancel.on_click = title, detail, label, action
        self.page_label.text = f"{self.page + 1} / {pages}"
        self.previous.enabled, self.next.enabled = self.page > 0, self.page + 1 < pages
        self.clear_assembly.enabled = self.game_scene.player.assembly is not None

    def update(self, dt: float) -> None:
        self._refresh()


class PauseScene(_Overlay):
    pause_below = True
    controls = {"n": "new_game", "q": "quit", "f5": "save", "f9": "load", "s": "settings", "t": "back_to_title", "f1": "help", "r": "resign"}

    def __init__(self, game_scene: GameScene) -> None:
        self.game_scene = game_scene

    def on_enter(self) -> None:
        panel = self.panel("Paused")
        panel.add(Button("Resume", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=260))
        panel.add(Button("Save game…", hotkey="F5", on_click=self.save, style=GHOST_BUTTON, width=260))
        panel.add(Button("Load game…", hotkey="F9", on_click=self.load, style=GHOST_BUTTON, width=260))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=260))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=260))
        panel.add(Button("Resign", hotkey="R", on_click=self.resign, style=GHOST_BUTTON, width=260))
        panel.add(Button("New game", hotkey="N", on_click=self.new_game, style=GHOST_BUTTON, width=260))
        panel.add(Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=260))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=260))

    def save(self) -> None:
        self.game.pop()
        self.game_scene.open_saves("save")

    def load(self) -> None:
        self.game.pop()
        self.game_scene.open_saves("load")

    def settings(self) -> None:
        self.game.push(SettingsScene(self.game_scene))

    def help(self) -> None:
        self.game.push(HelpScene(self.game_scene.scheme))

    def resign(self) -> None:
        scene = self.game_scene
        if scene.world.can_resign(scene.human) is not None:
            return
        where = scene.leaving()
        if where is None:
            self.game.pop()
            scene.world.resign(scene.human)
            return
        self.game.push(LeaveScene(scene, where, "Resign", lambda: (self.game.pop_to(scene), scene.resign(where))))

    def _leave(self, verb: str, then: Callable[[], None]) -> None:
        """Do *then* now, or after the player has agreed to what leaving the match costs."""
        where = self.game_scene.leaving()
        if where is None:
            then()
            return
        scene = self.game_scene
        self.game.push(LeaveScene(scene, where, verb, lambda: (scene.conclude("left", where), then())))

    def new_game(self) -> None:
        self._leave("New game", lambda: self.game.clear_and_push(next_game(self.game_scene)))

    def back_to_title(self) -> None:
        from warband.ui.title import TitleScene

        self._leave("Back to title", lambda: self.game.clear_and_push(TitleScene(settings=self.game_scene.settings)))

    def quit(self) -> None:
        self._leave("Quit", self.game.quit)


class LeaveScene(_Overlay):
    """What leaving the match now costs, and the choice to do it anyway."""

    pause_below = True
    controls = {("return", "space"): "confirm"}

    def __init__(self, game_scene: GameScene, where: Standing, verb: str, then: Callable[[], None]) -> None:
        self.game_scene, self.where, self.verb, self.then = game_scene, where, verb, then

    def on_enter(self) -> None:
        scene = self.game_scene
        profile = scene.profile
        assert profile is not None
        before = profile.rating
        after = rated(before, DIFFICULTY_ELO[scene.difficulty], 0.0, self.where.weight)
        panel = self.panel(f"{self.verb}: leave the match?")
        panel.add(Label("The match is not decided. Leaving counts against your rating.", text_style="body"))
        panel.add(Label(self.where.reason[0].upper() + self.where.reason[1:], text_style="body", text_color=BAD if self.where.weight == 1.0 else GOLD,
                        width=560, wrap=True))
        panel.add(Label(f"Rating {round(before.value)} → {round(after.value)} ({round(after.value) - round(before.value):+d}) · "
                        f"the replay is kept either way", text_style="heading"))
        panel.add(Row(Button(self.verb, hotkey="Enter", on_click=self.confirm, style=DANGER_BUTTON, width=260),
                      Button("Stay", hotkey="Esc", on_click=self.game.pop, style=GHOST_BUTTON, width=200), spacing=12))

    def confirm(self) -> None:
        self.then()


class SettingsScene(_Overlay):
    """Keyboard-navigable options: ↑↓ pick a row, ←→ adjust or toggle.  Saved to the settings file."""

    pause_below = True
    controls = {"left": "decrease", "right": "increase", ("return", "space"): "increase"}
    ROWS: tuple[tuple[str, str, str], ...] = (
        ("Music volume", "music", "percent"), ("Sound volume", "sfx", "percent"), ("Edge scrolling", "edge_scroll", "toggle"),
        ("Scroll speed", "scroll_speed", "speed"), ("Fullscreen", "fullscreen", "toggle"), ("Tutorial", "tutorial", "toggle"),
        ("Blood", "blood", "toggle"), ("Controls", "controls", "scheme"),
    )

    def __init__(self, game_scene: GameScene) -> None:
        self.game_scene = game_scene
        self.row_keys: dict[Row, str] = {}

    @property
    def settings(self) -> dict[str, Any]:
        return self.game_scene.settings

    def _shown(self, key: str, kind: str) -> str:
        value = self.settings[key]
        if kind == "percent":
            return f"{round(value * 100)}%"
        if kind == "speed":
            return f"×{value:g}"
        if kind == "scheme":
            return SCHEMES[value].name
        return "On" if value else "Off"

    def on_enter(self) -> None:
        self.ui.enable_focus(navigation="vertical", activate=())
        panel = self.panel("Settings")
        for name, key, kind in self.ROWS:
            row = Row(spacing=12, focusable=True)
            self.row_keys[row] = key
            row.add(Label(lambda r=row: "›" if r.focused else "", text_style="hud", width=18, text_color=GOLD))
            row.add(Label(name, text_style="body", width=170))
            row.add(Row(
                Button("−", on_click=lambda k=key: self._adjust(k, -1), style=GHOST_BUTTON, width=48, focusable=False),
                Label(lambda k=key, kd=kind: self._shown(k, kd), text_style="hud", width=70, align="center"),
                Button("+", on_click=lambda k=key: self._adjust(k, 1), style=GHOST_BUTTON, width=48, focusable=False),
                spacing=8,
            ))
            panel.add(row)
        self.ui.focus(next(iter(self.row_keys)))
        panel.add(Label(lambda: SCHEMES[self.settings["controls"]].summary, text_style="sub", width=420, wrap=True))
        panel.add(Label("Settings are saved when you leave this screen.", text_style="sub"))
        panel.add(KeyHints([("Tab / ↑↓", "select"), ("←→", "adjust"), ("Esc", "close")]))

    def _adjust(self, key: str, direction: int) -> None:
        kind = next(k for _n, k2, k in self.ROWS if k2 == key)
        if kind == "percent":
            self.settings[key] = round(max(0.0, min(1.0, self.settings[key] + 0.1 * direction)), 2)
            apply_volumes(self.settings["music"], self.settings["sfx"])
        elif kind == "speed":
            self.settings[key] = round(max(0.5, min(2.0, self.settings[key] + 0.25 * direction)), 2)
        elif kind == "scheme":
            order = list(SCHEMES)
            self.settings[key] = order[(order.index(self.settings[key]) + direction) % len(order)]
        else:
            self.settings[key] = not self.settings[key]
        self.game_scene.sfx("button")

    def on_exit(self) -> None:
        self.game_scene.apply_settings()

    def decrease(self) -> None:
        self._adjust(self.row_keys[self.ui.focused], -1)

    def increase(self) -> None:
        self._adjust(self.row_keys[self.ui.focused], 1)


class SaveBrowserScene(_Overlay):
    """Three manual slots, the quicksave and the autosave with what they hold; a key or a click picks one."""

    pause_below = True
    controls = {"1": "pick_1", "2": "pick_2", "3": "pick_3", "q": "pick_quick", "a": "pick_auto"}

    def __init__(self, game: Any, mode: str, *, on_pick: Callable[[int | str], None]) -> None:
        self.mode = mode
        self.on_pick = on_pick
        self.listing = game.save_manager.list_slots(SAVE_SLOTS, names=("quick", "autosave"))

    def on_enter(self) -> None:
        panel = self.panel("Save game" if self.mode == "save" else "Load game")
        for entry, slot, key in zip(self.listing, [*range(1, SAVE_SLOTS + 1), "quick", "autosave"], ("1", "2", "3", "Q", "A")):
            name = f"Slot {slot}" if isinstance(slot, int) else slot.title()
            if entry is None:
                detail, ok = "empty", self.mode == "save"
            elif "error" in entry:
                detail, ok = "corrupt file — cannot be loaded", self.mode == "save"
            else:
                s = entry["summary"]
                head = f"Campaign · {s['mission']}" if "mission" in s else s.get("player", "")
                detail = f"{head} · {s.get('map', '')} · {s.get('players', '?')} players · {s.get('difficulty', '')} · {s.get('clock', '')} · {entry['timestamp'][:16].replace('T', ' ')}"
                ok = True
            button = Button(name, hotkey=key, on_click=lambda sl=slot: self.pick(sl), style=ACTION_BUTTON if ok else GHOST_BUTTON, width=150)
            button.enabled = ok and not (self.mode == "save" and slot == "autosave")
            panel.add(Row(button, Label(detail, text_style="body", width=560, wrap=True), spacing=12))
        panel.add(KeyHints([("1 2 3 Q A", "pick"), ("Esc", "back")]))

    def pick(self, slot: int | str) -> None:
        self.game.pop()
        self.on_pick(slot)

    def pick_1(self) -> None:
        self.pick(1)

    def pick_2(self) -> None:
        self.pick(2)

    def pick_3(self) -> None:
        self.pick(3)

    def pick_quick(self) -> None:
        self.pick("quick")

    def pick_auto(self) -> None:
        if self.mode == "load":
            self.pick("autosave")


HELP_INTRO = (
    "Peasants gather and build on their own. Plan buildings, units and upgrades for the whole settlement: plans wait for money,",
    "prerequisites and a free worker, and are paid when work starts. Defeat the enemy by destroying its buildings and units.",
)


def help_keys(scheme: Scheme) -> list[tuple[str, str]]:
    """The How to play table for *scheme*: its own keys first, then what every scheme shares."""
    idle = key_label(scheme.keys["idle_soldier"])
    if scheme.positional:
        own = [("Q W E / A S D / Z X C", "the card's buttons by their place, whatever it shows"),
               ("Units", "Q move, W stop, E hold, A attack-move, S patrol;  peasants: D build, Z repair"),
               ("A building", "its recruits, then its research, from Q on;  Cancel ends the row (E, or D below a full one)"),
               ("B / T / G / R / F / V", "Build / Train / Upgrade, the assembly point, every plan, the next idle soldier: beside the grid")]
    else:
        own = [("A M P S H / B R", "attack-move, move, patrol, stop, hold;  a peasant's build and repair"),
               ("A building's letters", "train or research there, as its card shows;  X cancels the last and stops endless training")]
        if scheme.home is not None:
            own += [("Nothing selected", "the Train catalogue is open: a letter orders a recruit;  B build, U upgrade, G assembly point"),
                    ("Modes last", f"placing leaves the next building ready until Esc;  {key_label(scheme.keys['repeat'])} repeats the last "
                                   f"recruit or placement;  {idle} idle soldier")]
        else:
            own += [("B / T / U / G / " + idle, "Build / Train / Upgrade, the assembly point, the next idle soldier, where the card leaves the key free")]
    return own + [
        ("Shift", "keep going: queue orders, place more buildings;  with a recruit's key: train it endlessly (right-click too)"),
        ("A building's key again", "while it is being placed: the planner picks the spot by your hall (a hall: by a free gold mine)"),
        ("Ctrl + B / T / U / G / P", "Build / Train / Upgrade, the assembly point, every plan, from any card;  Ctrl+A: the army (Mac: Cmd)"),
        ("Click / drag / right-click", "select;  box-select;  order what fits the target;  double-click or Ctrl-click: that type on screen"),
        ("1-9 / Ctrl / Shift", "recall / assign / add to a control group;  Tab: the next idle peasant;  Space: the last alert"),
        ("Arrows / edges / wheel", "scroll (middle-drag too);  wheel or + / −: zoom;  minimap: left-click looks, right-click sends"),
        ("F1 F2 F3 F5 F9 F11", "help, codex, pause, save, load (offline), health bars;  F6-F8: camera bookmarks, Ctrl+F6-F8 sets"),
        ("Esc", "back one level: the order, the catalogue, the selection, then the menu"),
    ]


HELP_KEY_WIDTH, HELP_TEXT_WIDTH = 230, 860  # the longest line fits unwrapped, and the panel fits a 1200 px window


class HelpScene(_Overlay):
    """How to play, with the keys of the control scheme in use."""

    pause_below = True

    def __init__(self, scheme: Scheme) -> None:
        self.scheme = scheme

    def on_enter(self) -> None:
        panel = self.panel(f"How to play · {self.scheme.name} controls")
        panel.add(Label(" ".join(HELP_INTRO), text_style="body", width=HELP_KEY_WIDTH + 14 + HELP_TEXT_WIDTH, wrap=True))
        table = Column(spacing=4)
        for keys, what in help_keys(self.scheme):
            table.add(Row(Label(keys, text_style="hud", width=HELP_KEY_WIDTH, align="right", text_color=GOLD),
                          Label(what, text_style="body", width=HELP_TEXT_WIDTH, wrap=True), spacing=14))
        panel.add(table)
        panel.add(KeyHints([("Esc", "close")]))


CODEX_PAGES = ("Units", "Buildings", "Upgrades", "Races")


class CodexScene(_Overlay):
    """The player's race: every unit, building and upgrade with its numbers, then the four races side by side;
    1/2/3/4 or Tab switch pages."""

    pause_below = True
    controls = {"1": "page_units", "2": "page_buildings", "3": "page_upgrades", "4": "page_races", "tab": "next_page", "f2": "close"}

    def __init__(self, world: World, player: int, page: int = 0) -> None:
        self.world = world
        self.player = player
        self.page = page

    def on_enter(self) -> None:
        race = RACES[self.world.players[self.player].race]
        panel = self.panel(f"Codex — the {race.name}" if self.page < 3 else "Codex — the four races")
        tabs = Row(spacing=8)
        for i, name in enumerate(CODEX_PAGES):
            tabs.add(Button(name, hotkey=str(i + 1), on_click=lambda i=i: self.show(i), style=ACTION_BUTTON if i == self.page else GHOST_BUTTON, width=150))
        panel.add(tabs)
        table = Column(spacing=3)
        if self.page == 3:
            table = self._race_table(race.name)
        else:
            widths, rows = self._rows()
            for cells in rows:
                table.add(Row(*[Label(text, text_style="hud" if i == 0 else "body", width=width, text_color=GOLD if i == 0 else None,
                                      wrap=i == len(cells) - 1)
                                for i, (text, width) in enumerate(zip(cells, widths))], spacing=8))
        panel.add(table)
        panel.add(KeyHints([("1 2 3 4", "page"), ("Tab", "next"), ("Esc", "close")]))

    def _race_table(self, own: str) -> Column:
        """The four races side by side: character, passive and arts, wrapped so every window fits."""
        table = Column(spacing=8)
        for race in Race:
            info = RACES[race]
            block = Column(spacing=2)
            block.add(Row(Label(info.name + (" ✓" if info.name == own else ""), text_style="hud", width=120, text_color=GOLD),
                          Label(info.tagline, text_style="body", width=700), spacing=10))
            block.add(Row(Label("", width=120), Label(info.passive, text_style="body", width=700, wrap=True), spacing=10))
            for art in info.arts:
                block.add(Row(Label("", width=120), Label(f"{UPGRADES[art].name} — {UPGRADES[art].summary}", text_style="sub", width=700, wrap=True), spacing=10))
            table.add(block)
        return table

    def _rows(self) -> tuple[tuple[int, ...], list[list[str]]]:
        """The page's column widths and its rows, the header first.  The widths fit the widest
        name, cost and building of every race at 1200 px; the last column wraps."""
        player = self.world.players[self.player]
        have = player.upgrades
        race = RACES[player.race]
        if self.page == 0:
            rows = [["Unit", "Cost", "HP", "Dmg", "Arm", "Rng", "Spd", "Trained at", "Role"]]
            for unit_type, info in race.units.items():
                rows.append([info.name, str(info.cost), str(info.hp), f"heal {info.heal}" if info.heal else str(info.damage),  # its blow is in its role
                             str(info.armor), "melee" if info.range < 1 else f"{info.range:g}", f"{info.speed:g}",
                             race.buildings[info.trained_at].name,
                             f"{info.summary} · {armour_name(info.armor_class)}"
                             + (f", {info.attack.value}" if info.damage and info.attack is not AttackType.NORMAL else "")])
            return (150, 198, 40, 66, 40, 55, 42, 140, 361), rows  # "heal 15" is the widest Dmg
        if self.page == 1:
            rows = [["Building", "Cost", "HP", "Arm", "Size", "Time", "Requires", "What it does"]]
            for building_type, info in race.buildings.items():
                if building_type is BuildingType.GOLD_MINE:
                    continue
                rows.append([info.name, str(info.cost), str(info.hp), str(info.armor), f"{info.size}×{info.size}", f"{info.build_time:g}s",
                             race.buildings[info.requires].name if info.requires else "—",
                             info.summary + (f" · supply +{info.supply}" if info.supply else "")])
            return (150, 198, 50, 40, 50, 50, 130, 420), rows
        if self.page == 2:
            rows = [["Upgrade", "Cost", "Time", "Where", "Requires", "Effect"]]
            for upgrade, info in UPGRADES.items():
                if not race.upgrade_allowed(upgrade):
                    continue
                where = next(b for b, binfo in BUILDINGS.items() if upgrade in binfo.researches)
                requires = UPGRADES[info.requires].name if info.requires else f"{race.adjective} art" if info.race is not None else "—"
                rows.append([info.name + (" ✓" if upgrade in have else ""), str(info.cost), f"{info.time:g}s", race.buildings[where].name, requires,
                             info.summary])
            return (190, 198, 50, 130, 165, 383), rows
        raise ValueError(f"no table for page {self.page}")

    def show(self, page: int) -> None:
        self.game.replace(CodexScene(self.world, self.player, page))

    def page_units(self) -> None:
        self.show(0)

    def page_buildings(self) -> None:
        self.show(1)

    def page_upgrades(self) -> None:
        self.show(2)

    def page_races(self) -> None:
        self.show(3)

    def next_page(self) -> None:
        self.show((self.page + 1) % len(CODEX_PAGES))

    def close(self) -> None:
        self.game.pop()


class GameOverScene(_Overlay):
    """The result: the score and how it was earned, the battle record, every warband's fate, and the local rank."""

    pause_below = True
    pop_on_cancel = False
    controls = {"n": "new_game", "b": "high_scores", "q": "quit", ("t", "escape"): "back_to_title"}

    def __init__(self, game_scene: GameScene) -> None:
        self.game_scene = game_scene
        self.won = game_scene.world.winner == game_scene.human
        self.score_error = ""

    def on_enter(self) -> None:
        scene = self.game_scene
        world = scene.world
        points = score_breakdown(world, scene.human)
        panel = self.panel("Victory!" if self.won else "Defeat")
        panel.style = RESULTS_STYLE
        panel.add(Label(f"{scene.race.name} · {scene.difficulty.value.title()} AI · {world.width}×{world.height} · {len(world.players)} players · "
                        f"{world.theme.value.title()} · Seed {scene.seed}", text_style="body"))
        score = Column(spacing=10, width=420)
        score.add(Label(f"{sum(points.values()):,} points", text_style="banner"))
        for name, value in points.items():
            score.add(Row(Label(name, text_style="body", width=300), Label(f"{value:,}", text_style="heading", width=100), spacing=12))
        score.add(Label("Combat: 1 point per 10 resources destroyed.\nSurvivors: 1 per 20; research: 1 per 10.\nSwift victory: 2 per second before 20:00.",
                        text_style="sub", width=420, wrap=True))
        summary = Column(spacing=12, width=420)
        summary.add(Label(f"Battle record · {_clock(world.time)}", text_style="heading"))
        stats = scene.stats
        summary.add(Label(f"{stats['units_killed']} enemy units defeated · {stats['units_lost']} units lost", text_style="body"))
        summary.add(Label(f"{stats['buildings_razed']} buildings razed · {stats['buildings_lost']} lost", text_style="body"))
        summary.add(Label("Warbands", text_style="heading"))
        for player in world.players:
            status = ("Victorious" if world.winner == player.id else "Surrendered" if player.surrendered
                      else "Still fighting" if player.alive else "Eliminated")
            summary.add(Row(Label(f"{player.name} · {RACES[player.race].name}", text_style="body", width=200),
                            Label(status, text_style="body", text_color=GOOD if player.id == world.winner else MUTED), spacing=10))
        if any(p.surrendered for p in world.players):
            summary.add(Label("Surrender: no units or queued recruits,\nand no affordable way to train another.", text_style="sub", width=420, wrap=True))
        panel.add(Row(score, summary, spacing=28))
        notice = "Demo battle · not ranked"
        if scene.ranked:
            try:
                rank = HighScores(self.game.data_dir).record(world, player=scene.human, seed=scene.seed, difficulty=scene.difficulty, run_id=scene.run_id)
                notice = f"Your best finish ranks #{rank} on this local board" if rank else "Outside this board's top 10"
            except SaveError as error:
                self.score_error = str(error)
                notice = "High score could not be saved · open High scores for the error"
        panel.add(Label(notice, text_style="body", text_color=GOLD))
        panel.add(Label(self._rating_text(), text_style="body", text_color=GOLD if scene.rating_change is not None else MUTED, width=880, wrap=True))
        panel.add(Row(Button("New game", hotkey="N", on_click=self.new_game, style=ACTION_BUTTON, width=210),
                      Button("High scores", hotkey="B", on_click=self.high_scores, style=GHOST_BUTTON, width=210),
                      Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=210),
                      Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=190), spacing=12))

    def _rating_text(self) -> str:
        scene = self.game_scene
        change = scene.rating_change
        if change is None:
            return (f"Profile could not be updated · {scene.profile_error}" if scene.profile_error else
                    "Not rated" if scene.replay is None else "Rating unchanged")
        result = change.result
        weight = f" · {result.reason}" if result.reason else ""
        replaced = " · replaces this match's earlier result" if change.replaced else ""
        replay = " · replay saved to your profile" if result.replay else ""
        return f"Rating {change} against {result.difficulty.title()} ({result.opponent}){weight}{replaced}{replay}"

    def high_scores(self) -> None:
        from warband.ui.score_scene import HighScoreScene

        scene = self.game_scene
        self.game.push(HighScoreScene(difficulty=scene.difficulty, size=(scene.world.width, scene.world.height),
                                      players=len(scene.world.players), run_id=scene.run_id, error=self.score_error))

    def new_game(self) -> None:
        self.game.clear_and_push(next_game(self.game_scene))

    def back_to_title(self) -> None:
        from warband.ui.title import TitleScene

        scene = self.game_scene
        size = next((name for name, dimensions in mapgen.SIZES.items() if dimensions == (scene.world.width, scene.world.height)), "Medium")
        self.game.clear_and_push(TitleScene(size=size, players=len(scene.world.players), difficulty=scene.difficulty, theme=scene.world.theme,
                                           race=scene.player.race, layout=scene.world.layout, settings=scene.settings))

    def quit(self) -> None:
        self.game.quit()


def new_game(seed: int, width: int = 48, height: int = 40, players: int = 2, *, difficulty: Difficulty = Difficulty.MEDIUM,
             theme: MapTheme = MapTheme.SUMMER, settings: dict[str, Any] | None = None, races: list[Race | None] | None = None,
             layout: MapLayout | None = None) -> GameScene:
    """*layout* ``None`` draws one from the seed."""
    return GameScene(mapgen.generate(seed=seed, width=width, height=height, players=players, theme=theme, races=races, layout=layout), seed,
                     difficulty=difficulty, settings=settings)


FAIR_TRIES = 20


def fair_map(seed: int, width: int, height: int, players: int, *, theme: MapTheme = MapTheme.SUMMER,
             races: list[Race | None] | None = None, layout: MapLayout | None = None) -> tuple[int, World]:
    """The first seed from *seed* on that makes a fair map of these settings, and its map: for a seed the game
    chooses. A few seeds in a thousand make none at some settings (WB-046); a seed the player gives goes to
    :func:`mapgen.generate` as given, and fails there."""
    for candidate in range(seed, seed + FAIR_TRIES):
        try:
            return candidate, mapgen.generate(candidate, width, height, players, theme=theme, races=races, layout=layout)
        except mapgen.NoFairMap:
            continue
    raise mapgen.NoFairMap(f"No fair map at {width}x{height} for {players} players from any seed of {seed} to {seed + FAIR_TRIES - 1}.")


def next_game(scene: GameScene) -> GameScene:
    """A new match with *scene*'s settings and races on the next seed that makes a fair map."""
    world = scene.world
    seed, fresh = fair_map(scene.seed + 1, world.width, world.height, len(world.players), theme=world.theme,
                           races=[p.race for p in world.players], layout=world.layout)
    return GameScene(fresh, seed, difficulty=scene.difficulty, settings=scene.settings)


def check_save(state: dict[str, Any]) -> World:
    """The world in a save's ``state``, or a SaveError saying what is wrong with it."""
    if not isinstance(state, dict) or state.get("version") != SAVE_VERSION:
        raise SaveError(f"this save is from another version of Warband (format {state.get('version') if isinstance(state, dict) else '?'}, expected {SAVE_VERSION})")
    try:
        world = World.from_dict(state["world"])
        Difficulty(state["difficulty"])
        if "run_id" in state and (not isinstance(state["run_id"], str) or not state["run_id"].strip()):
            raise ValueError("run_id must be nonempty text")
        if "ranked" in state and type(state["ranked"]) is not bool:
            raise ValueError("ranked must be a boolean")
        _saved_replay(state)
        if state.get("seen") is not None:  # saves from before the view remembered carry none
            check_memory(state["seen"], world)
        if any(type(value) is not int or value < 0 for player in world.players for value in player.stats.values()):
            raise ValueError("battle statistics must be nonnegative integers")
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise SaveError(f"the save file is damaged ({type(exc).__name__}: {exc})") from exc
    if not any(p.human for p in world.players):
        raise SaveError("the save has no human player")
    return world


def _saved_run_id(state: dict[str, Any]) -> str:
    # Saves from before scoring carry no match ID; the same old save reopened still counts once.
    return state["run_id"] if "run_id" in state else str(uuid5(NAMESPACE_URL, "warband:" + json.dumps(state, sort_keys=True)))


def _saved_replay(state: dict[str, Any]) -> Replay | None:
    """The recording a save carries, if it has one (saves from before replays record from where they are loaded)."""
    return Replay.from_dict(state["replay"]) if state.get("replay") is not None else None


def load_game(state: dict[str, Any], *, settings: dict[str, Any] | None = None) -> GameScene:
    """A game scene from a save slot's ``state`` (see :meth:`GameScene.get_save_state`); a campaign mission's save
    (it carries a ``mission`` block) comes back as its mission scene."""
    if isinstance(state, dict) and "mission" in state:
        from warband.story.mission_scene import load_mission

        return load_mission(state, settings=settings)
    world = check_save(state)
    scene = GameScene(world, state["seed"], difficulty=Difficulty(state["difficulty"]), settings=settings,
                      run_id=_saved_run_id(state), ranked=state.get("ranked", True), replay=_saved_replay(state), seen=state.get("seen"))
    scene.groups = {k: list(v) for k, v in state.get("groups", {}).items()}
    if state.get("tutorial") is not None and scene.tutorial is not None:
        scene.tutorial.step = state["tutorial"]
    scene._autosave_at = (world.time // AUTOSAVE_EVERY + 1) * AUTOSAVE_EVERY
    return scene
