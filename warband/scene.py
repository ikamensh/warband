"""saga2d scenes for Warband: the match, its HUD, and the overlays stacked on it."""

from __future__ import annotations

import json
import math
import random
from collections import deque
from uuid import NAMESPACE_URL, uuid4, uuid5
from dataclasses import dataclass, field
from typing import Any, Callable

from saga2d import (
    Anchor, Button, Camera, Column, Component, InputEvent, KeyHints, Label, Layout, Minimap, MoveTo, Panel, Remove, RenderLayer, Row, Scene,
    Sequence, Sprite, Style,
)
from saga2d import SaveError
from saga2d.effects import Banner, Burst, Effects, FloatingText, HitReaction, Pulse, Toast
from warband import ambience, mapgen
from warband.ai import Brain
from warband.effects import UnitDeath
from warband.icons import Icon, draw_icon
from warband.model import Building, Entity, Event, Pos, RuleError, Unit, World
from warband.production import ProductionButton, ProductionTarget, draw_production_icon
from warband.races import RACES, RaceInfo
from warband.rules import BUILDINGS, SIM_DT, UPGRADES, BuildingType, Difficulty, MapTheme, Race, UnitType, Upgrade
from warband.scores import HighScores, score_breakdown
from warband.sound import IMPACTS, apply_volumes, impact_sound, play_music, play_sound
from warband.voices import voiced
from warband.style import (
    ACTION_BUTTON, BAD, CARD_BUTTON, DANGER_BUTTON, GHOST_BUTTON, GOLD, GOOD, LUMBER, MUTED, OVERLAY_STYLE, PANEL_STYLE, RESULTS_STYLE,
)
from warband.textures import TILE
from warband.tutorial import OBJECTIVES, Tutorial
from warband.view import MapView, Overlay, rgba, to_tiles, to_world

DEFAULT_SETTINGS: dict[str, Any] = {"music": 0.6, "sfx": 0.8, "edge_scroll": True, "scroll_speed": 1.0, "fullscreen": False, "tutorial": True}
SAVE_VERSION = 1
SAVE_SLOTS = 3
AUTOSAVE_EVERY = 120.0  # seconds of match time
TOAST_TOP = 280  # below the resource, settlement and objectives panels
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
CARD_COLS = 3
#: The build menu's order: the opening buildings first, then the tech chain as it unlocks.
BUILD_ORDER = (BuildingType.FARM, BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.TOWER, BuildingType.LUMBER_MILL,
               BuildingType.BLACKSMITH, BuildingType.STABLES, BuildingType.WORKSHOP, BuildingType.CHURCH)
#: Names that fit a card button (each race's are in :mod:`warband.races`); the tooltip and the codex use the full ones.
UPGRADE_NAMES = {Upgrade.BLADES_1: "Blades I", Upgrade.BLADES_2: "Blades II", Upgrade.ARMOR_1: "Armour I", Upgrade.ARMOR_2: "Armour II",
                 Upgrade.ARROWS_1: "Arrows I", Upgrade.ARROWS_2: "Arrows II", Upgrade.HORSES: "Horses", Upgrade.SIEGE: "Siege", Upgrade.BLESSING: "Blessing",
                 Upgrade.BLOODLUST: "Bloodlust", Upgrade.PLUNDER: "Plunder", Upgrade.LONGBOWS: "Longbows", Upgrade.REGROWTH: "Regrowth",
                 Upgrade.DEEP_MINING: "Mining", Upgrade.BLASTING_POWDER: "Powder"}
CARD_WIDTH = 116
CARD_ICON = 58  # height of a portrait button; the name sits under it
MINIMAP_WIDTH = 200
SELECTION_WIDTH = 470
SELECTION_HEIGHT = 128
MAX_PORTRAITS = 12


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


@dataclass
class Command:
    """One command-card button."""

    label: str
    hotkey: str
    action: Callable[[], None]
    tooltip: str = ""
    cost: str = ""
    blocked: Callable[[], str | None] = field(default=lambda: None)  # why it cannot be used right now
    style: Style = field(default_factory=lambda: CARD_BUTTON)
    target: ProductionTarget | None = None  # a unit, building or upgrade: the button shows its portrait or emblem

    @property
    def key(self) -> str:
        return {"Esc": "escape"}.get(self.hotkey, self.hotkey.lower())


class GameScene(Scene):
    """The whole match: map, selection, orders, HUD, the AI's turns and the game clock."""

    background_color = (8, 10, 14, 255)
    controls = {
        "escape": "cancel",
        "f1": "open_help",
        "f2": "open_codex",
        "f3": "toggle_pause",
        "f4": "hide_tutorial",
        "f5": "quick_save",
        "f9": "quick_load",
        "f10": "open_menu",
        "space": "jump_to_alert",
        ("home", "backspace"): "center_base",
        ("equal", "plus"): "zoom_in",
        "minus": "zoom_out",
        "tab": "next_idle_peasant",
        "period": "next_idle_soldier",
        "ctrl+a": "select_army",
        "f6": "recall_bookmark_1", "f7": "recall_bookmark_2", "f8": "recall_bookmark_3",
        "ctrl+f6": "set_bookmark_1", "ctrl+f7": "set_bookmark_2", "ctrl+f8": "set_bookmark_3",
    }

    def __init__(self, world: World, seed: int, *, difficulty: Difficulty = Difficulty.NORMAL, settings: dict[str, Any] | None = None,
                 player: int | None = None, run_id: str | None = None, ranked: bool = True) -> None:
        self.world = world
        self.run_id = run_id if run_id is not None else str(uuid4())  # one leaderboard row per match, however often it is reloaded
        self.ranked = ranked
        self.seed = seed
        self.difficulty = difficulty
        self.human = next(p.id for p in world.players if p.human) if player is None else player
        self.brains = [Brain(p.id, difficulty) for p in world.players if not p.human]
        self.rng = random.Random(seed)
        self.settings = settings if settings is not None else dict(DEFAULT_SETTINGS)  # a saga2d Settings when the game runs
        for key, value in DEFAULT_SETTINGS.items():
            self.settings.setdefault(key, value)
        self.tutorial = Tutorial() if self.settings["tutorial"] else None
        self._autosave_at = AUTOSAVE_EVERY
        self.selection: list[int] = []
        self.groups: dict[str, list[int]] = {}
        self.pending: str | None = None  # "move" | "attack" | "patrol" | "repair" | "build:<type>"
        self.build_menu = False
        self.settlement_menu: str | None = None
        self.paused = False
        self.speed = 1.0
        self.clock = 0.0
        self.effects = Effects()
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
        self._portraits: list[tuple[int, tuple[int, int, int, int]]] = []
        self._sound_times: dict[str, float] = {}
        self._battle_voices: deque[float] = deque()
        self._fights: deque[float] = deque()
        self._battle_until = -math.inf
        self._last_click: tuple[float, int | None] = (-10.0, None)
        self.bookmarks: dict[int, tuple[float, float]] = {}
        self._warm = None  # renders the unit images over the first frames

    # -- Lifecycle -------------------------------------------------------------

    def on_enter(self) -> None:
        self.view = MapView(self, self.world, self.human)
        self._setup_camera()
        self.apply_settings()
        self._build_hud()
        self.center_base(instant=True)
        rivals = ", ".join(f"the {RACES[p.race].name} of {p.name}" for p in self.world.players if p.id != self.human)
        self.effects.add(Banner("Warband", subtitle=f"The {self.race.name} of {self.player.name} against {rivals}", accent=rgba(self.player.color)))
        from warband import textures

        self._warm = textures.warm_units(self.game, [p.id for p in self.world.players], [p.race for p in self.world.players])
        play_music("peace", self.player.race)

    def _setup_camera(self) -> None:
        w, h = self.game.resolution
        world_w, world_h = self.world.width * TILE, self.world.height * TILE
        self.camera = Camera((w, h), world_bounds=(-TILE, -TILE, world_w + TILE, world_h + SELECTION_HEIGHT + 3 * TILE), zoom=1.0, min_zoom=0.75, max_zoom=2.0)
        self.camera.enable_key_scroll(speed=KEY_SPEED)

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
        if hasattr(self.settings, "save"):
            self.settings.save()

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
        combat = name in IMPACTS or name in ("impact", "death")
        key = "siege_impact" if name.startswith("stone_") else name
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
        self.ui.add(Panel(anchor=Anchor.TOP_LEFT, margin=12, layout=Layout.HORIZONTAL, spacing=12, style=PANEL_STYLE, children=[
            Label(player.name, text_style="title", text_color=rgba(player.color)),
            Label(self.race.name, text_style="sub"),
            *(row for row, _hint in self._resource_rows),
            Label(lambda: _clock(world.time), text_style="sub"),
            Label(lambda: "Paused" if self.paused else f"×{self.speed:g}" if self.speed != 1 else "", text_style="hud", text_color=BAD),
            self._idle_button(),
            Button("Menu", hotkey="F10", on_click=self.open_menu, style=GHOST_BUTTON),
        ]))
        self.ui.add(Row(Label("Settlement", text_style="heading", width=124),
                        Button("Build", shortcut="Ctrl+B", on_click=lambda: self.open_settlement(None if self.settlement_menu == "build" else "build"), style=GHOST_BUTTON, width=132),
                        Button("Train", shortcut="Ctrl+T", on_click=lambda: self.open_settlement(None if self.settlement_menu == "train" else "train"), style=GHOST_BUTTON, width=132),
                        Button("Upgrade", shortcut="Ctrl+U", on_click=lambda: self.open_settlement(None if self.settlement_menu == "upgrade" else "upgrade"), style=GHOST_BUTTON, width=142),
                        Button(lambda: f"Plans ({self._plan_count()})", shortcut="Ctrl+P", on_click=self.open_plans, style=GHOST_BUTTON, width=152),
                        Button("Assembly", shortcut="Ctrl+G", on_click=lambda: self.start_pending("assembly"), style=GHOST_BUTTON, width=152),
                        spacing=8, anchor=Anchor.TOP_LEFT, margin=(12, 84), style=PANEL_STYLE))
        world_w, world_h = self.world.width * TILE, self.world.height * TILE
        self.minimap = Minimap(self.view.minimap_key, (world_w, world_h), self.camera, width=MINIMAP_WIDTH,
                               height=round(MINIMAP_WIDTH * world_h / world_w), on_click=self.minimap_click,
                               anchor=Anchor.BOTTOM_LEFT, margin=PANEL_MARGIN, style=PANEL_STYLE)
        self.ui.add(self.minimap)
        self.selection_panel = Component(width=SELECTION_WIDTH, height=SELECTION_HEIGHT, anchor=Anchor.BOTTOM_CENTER, margin=PANEL_MARGIN)
        self.ui.add(self.selection_panel)
        self.card_panel = Column(spacing=6, anchor=Anchor.BOTTOM_RIGHT, margin=PANEL_MARGIN, style=PANEL_STYLE)
        self.ui.add(self.card_panel)
        # What a hovered command or queued job is, wrapped above the selection panel where a long line fits.
        self.command_tooltip = Panel(anchor=Anchor.BOTTOM_CENTER, margin=(0, PANEL_MARGIN[1] + SELECTION_HEIGHT + 8), layout=Layout.VERTICAL,
                                     style=PANEL_STYLE, visible=False,
                                     children=[Label(lambda: self.tooltip, text_style="body", wrap=True, width=SELECTION_WIDTH - 24)])
        self.ui.add(self.command_tooltip)
        self.ui.add(KeyHints(self._hint, anchor=Anchor.BOTTOM_CENTER, margin=5))
        self.ui.add(Label(lambda: self.status if self.status_timer > 0 else "", text_style="hud", anchor=Anchor.TOP_LEFT,
                          margin=(12, 146), width=760, wrap=True, text_color=GOLD))
        self.objectives = Column(spacing=4, anchor=Anchor.TOP_RIGHT, margin=(12, 146), style=PANEL_STYLE)
        self.objectives.add(Row(Label("Getting started", text_style="heading", width=290),
                                Button("Hide", hotkey="F4", on_click=self.hide_tutorial, style=GHOST_BUTTON, width=90), spacing=8))
        self.objective_label = Label("", text_style="body", width=390)
        self.objective_done = Label("", text_style="sub", width=390)
        self.objectives.add(self.objective_label)
        self.objectives.add(self.objective_done)
        self.objectives.visible = self.tutorial is not None
        self.ui.add(self.objectives)
        self._refresh_card()

    def hide_tutorial(self) -> None:
        self.tutorial = None
        self.objectives.visible = False
        self.sfx("button")

    def _update_tutorial(self) -> None:
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
        self.objective_label.text = f"{self.tutorial.step + 1}. {current.text}" if current is not None else ""
        self.objective_done.text = f"{self.tutorial.step} of {len(OBJECTIVES) - 1} done" if self.tutorial.step else "F4 hides this; the settings switch it off"

    def _idle_button(self) -> Button:
        self.idle_button = Button(lambda: f"Idle {self._idle_peasant_count()}", hotkey="Tab", on_click=self.next_idle_peasant, style=ACTION_BUTTON)
        return self.idle_button

    def _idle_peasant_count(self) -> int:
        return sum(1 for u in self.world.player_units(self.human) if u.is_worker and not u.orders and not u.hidden)

    def _hint(self) -> list[tuple[str, str]]:
        if self.pending is not None:
            return [("Click", "target"), ("Right click", "cancel"), ("Shift", "queue / keep placing")]
        if self.build_menu:
            return [("F B H T M K S W C", "choose a building"), ("Esc", "back")]
        if self.settlement_menu is not None:
            return [("Click", "add a plan"), ("Plans", "progress / cancel"), ("Esc", "unit commands")]
        if self._own_units():
            hints = [("Right click", "move / harvest / attack / repair"), ("A", "attack-move"), ("P", "patrol"), ("S", "stop")]
            if any(u.is_worker for u in self._own_units()):
                hints.append(("B / R", "build / repair"))
            return hints + [("Ctrl+1-9", "group"), ("Esc", "deselect")]
        building = self._own_building()
        if building is not None:
            keys = " ".join(dict.fromkeys(c.hotkey for c in self._card if c.hotkey not in ("X", "C")))
            return ([(keys, "train / research")] if keys else []) + [("Right click", "rally point"), ("F2", "codex"), ("Esc", "deselect")]
        return [("Drag", "select"), ("Tab", "idle peasant"), ("Space", "last alert"), ("Arrows", "scroll"), ("Wheel", "zoom"), ("F3", "pause"), ("F1", "help"), ("F2", "codex")]

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
        self.pending = None
        self.build_menu = False
        self.settlement_menu = None
        self._refresh_card()
        if alive and not quiet:
            self.sfx("select")

    def _prune_selection(self) -> None:
        before = list(self.selection)
        self.selection = [i for i in self.selection if self.world.entity(i) is not None]
        if self.selection != before:
            self._refresh_card()

    def click_select(self, point: tuple[float, float], shift: bool, ctrl: bool = False) -> None:
        entity = self.world.entity_at(point, visible_to=self.human)
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
        same = [u.id for u in self.world.units_in_rect(*to_tiles(left, top), *to_tiles(right, bottom), player=self.human) if u.type is unit.type]
        self.select(same if not add else [i for i in same if i not in self.selection], add=add)

    def select_army(self) -> None:
        soldiers = [u.id for u in self.world.player_units(self.human) if not u.is_worker and not u.hidden]
        if soldiers:
            self.select(soldiers)
        else:
            self.say("No soldiers yet")

    def box_select(self, a: tuple[float, float], b: tuple[float, float], shift: bool) -> None:
        units = self.world.units_in_rect(a[0], a[1], b[0], b[1], player=self.human)
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

    def say(self, text: str) -> None:
        self.status = text
        self.status_timer = 3.0

    def warn(self, text: str) -> None:
        self.say(text)
        self.sfx("error")

    def _marker(self, point: tuple[float, float], color: tuple[int, int, int, int]) -> None:
        wx, wy = to_world(point)
        self.effects.add(Pulse((wx, wy), color, radius=(4, 18), rings=2, duration=0.5))

    def order(self, action, *args, **kwargs):
        return getattr(self.world, action)(*args, **kwargs)

    def command_smart(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            verb = self.order("smart", [u.id for u in units], point, queue=queue)
            self._marker(point, (255, 80, 70, 220) if verb == "attack" else (120, 255, 140, 220))
            self.sfx("attack_command" if verb == "attack" else "command")
            return
        building = self._own_building()
        if building is not None and building.done:
            self.order("set_rally", building.id, point)
            self._marker(point, (255, 214, 110, 220))
            self.sfx("command")

    def command_repair(self, point: tuple[float, float], *, queue: bool = False) -> None:
        workers = [u.id for u in self._own_units() if u.is_worker]
        target = self.world.entity_at(point, visible_to=self.human)
        if not workers or not isinstance(target, Building):
            self.warn("Click one of your damaged buildings")
            return
        try:
            self.order("repair", workers, target.id, queue=queue)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self._marker(point, (120, 255, 140, 220))
        self.sfx("command")

    def command_move(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            self.order("move", [u.id for u in units], point, queue=queue)
            self._marker(point, (120, 255, 140, 220))
            self.sfx("command")

    def command_attack(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if not units:
            return
        ids = [u.id for u in units]
        target = self.world.entity_at(point, visible_to=self.human)
        try:
            if target is not None and target.player is not None and target.player != self.human:
                self.order("attack", ids, target.id, queue=queue)
            else:
                self.order("attack_move", ids, point, queue=queue)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self._marker(point, (255, 80, 70, 220))
        self.sfx("attack_command")

    def command_patrol(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            self.order("patrol", [u.id for u in units], point, queue=queue)
            self._marker(point, (120, 200, 255, 220))
            self.sfx("command")

    def command_stop(self) -> None:
        units = self._own_units()
        if units:
            self.order("stop", [u.id for u in units])
            self.sfx("command")

    def command_hold(self) -> None:
        units = self._own_units()
        if units:
            self.order("hold", [u.id for u in units])
            self.sfx("command")

    def start_pending(self, mode: str) -> None:
        self.pending = mode
        self.build_menu = False
        if mode == "assembly":
            self.settlement_menu = None
            self.say("Click the map to set an assembly point for new soldiers")
        self._refresh_card()

    def open_build_menu(self) -> None:
        self.build_menu = True
        self.pending = None
        self._refresh_card()

    def close_build_menu(self) -> None:
        self.build_menu = False
        self._refresh_card()

    def _ghost_site(self, building_type: BuildingType) -> Pos:
        size = BUILDINGS[building_type].size
        return (int(math.floor(self.hover[0] - size / 2 + 0.5)), int(math.floor(self.hover[1] - size / 2 + 0.5)))

    def place_building(self, building_type: BuildingType, point: tuple[float, float], *, keep: bool = False) -> None:
        peasants = [u for u in self._own_units() if u.is_worker]
        if not peasants:
            self.warn("Select a peasant to build")
            return
        size = BUILDINGS[building_type].size
        site = (int(math.floor(point[0] - size / 2 + 0.5)), int(math.floor(point[1] - size / 2 + 0.5)))
        builder = min(peasants, key=lambda u: (u.hidden, math.dist(u.pos, point)))
        try:
            self.order("build", builder.id, building_type, site, queue=keep)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.sfx("command")
        self._marker((site[0] + size / 2, site[1] + size / 2), (255, 214, 110, 220))
        if not keep:
            self.pending = None
            self._refresh_card()

    def unit_name(self, unit_type: UnitType) -> str:
        return self.race.units[unit_type].name

    def building_name(self, building_type: BuildingType) -> str:
        return self.race.buildings[building_type].name

    def train(self, unit_type: UnitType) -> None:
        building = self._own_building()
        if building is None:
            return
        try:
            self.order("train", building.id, unit_type)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.sfx("button")
        self._refresh_card()

    def cancel_work(self) -> None:
        building = self._own_building()
        if building is None:
            return
        if building.queue:
            self.order("cancel_train", building.id)
        elif building.research is not None:
            self.order("cancel_research", building.id)
        else:
            return
        self.sfx("button")
        self._refresh_card()

    def research(self, upgrade: Upgrade) -> None:
        building = self._own_building()
        if building is None:
            return
        try:
            self.order("research", building.id, upgrade)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.sfx("button")
        self._refresh_card()

    def cancel_construction(self) -> None:
        building = self._own_building()
        if building is None or building.done:
            return
        self.order("cancel_building", building.id)
        self.say(f"{building.info.name} cancelled, cost refunded")
        self.sfx("button")
        self.select([])

    def cancel(self) -> None:
        if self.pending is not None:
            self.pending = None
            self._refresh_card()
        elif self.settlement_menu is not None:
            self.open_settlement(None)
        elif self.build_menu:
            self.close_build_menu()
        elif self.selection:
            self.select([])
        else:
            self.open_menu()

    # -- Settlement plans ----------------------------------------------------------

    def _plan_count(self) -> int:
        return len(self.world.player_plans(self.human)) + sum(len(b.queue) + (b.research is not None)
                                                            for b in self.world.player_buildings(self.human))

    def open_settlement(self, menu: str | None) -> None:
        self.settlement_menu = menu
        self.build_menu = False
        self.pending = None
        self._refresh_card()

    def open_plans(self) -> None:
        self.game.push(SettlementPlansScene(self))

    def order_production(self, kind: str, item: UnitType | Upgrade) -> None:
        try:
            self.order("order_unit" if kind == "train" else "order_upgrade", self.human, item)
        except RuleError as exc:
            self.warn(str(exc))
            return
        info = self.race.units[item] if kind == "train" else UPGRADES[item]
        self.say(f"{info.name} ordered · pay when work starts · manage in Plans")
        self.sfx("button")

    def place_plan(self, building_type: BuildingType, point: tuple[float, float], *, keep: bool = False) -> None:
        size = BUILDINGS[building_type].size
        site = (int(math.floor(point[0] - size / 2 + 0.5)), int(math.floor(point[1] - size / 2 + 0.5)))
        try:
            self.order("plan_building", self.human, building_type, site)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.say(f"{self.building_name(building_type)} planned · a worker will build when ready")
        self.sfx("command")
        if not keep:
            self.pending = None
            self._refresh_card()

    def set_assembly(self, point: tuple[float, float] | None) -> None:
        try:
            self.order("set_assembly", self.human, point)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.say("Assembly point cleared" if point is None else "New soldiers will assemble here; workers keep working")
        self.sfx("command")

    def _upgrade_planned(self, upgrade: Upgrade) -> str | None:
        if upgrade in self.player.upgrades:
            return "Already researched"
        if (any(p.kind == "upgrade" and p.type is upgrade for p in self.world.player_plans(self.human))
                or any(b.research is upgrade for b in self.world.player_buildings(self.human))):
            return "Already ordered"
        return None

    def _upgrades(self) -> list[Upgrade]:
        """The shared upgrades and the player's race arts, in the order of the table."""
        return [u for u in Upgrade if self.race.upgrade_allowed(u)]

    def _settlement_commands(self) -> list[Command]:
        commands = []
        race = self.race
        catalogue = ((bt, race.buildings[bt]) for bt in BUILD_ORDER) if self.settlement_menu == "build" else (
            race.units.items() if self.settlement_menu == "train" else ((u, UPGRADES[u]) for u in self._upgrades()))
        for item, info in catalogue:
            if self.settlement_menu == "build":
                name, key = race.cards[item], info.hotkey.upper()
                action = lambda bt=item: self.start_pending(f"plan:{bt.value}")
            elif self.settlement_menu == "train":
                name, key = info.name, info.hotkey.upper()
                action = lambda ut=item: self.order_production("train", ut)
            else:
                name, key = UPGRADE_NAMES[item], ""
                action = lambda up=item: self.order_production("upgrade", up)
            commands.append(Command(name, key, action, tooltip=f"{info.name} — {info.cost} · {info.summary}",
                                    cost=f"{info.cost.gold} / {info.cost.lumber}",
                                    blocked=(lambda up=item: self._upgrade_planned(up)) if self.settlement_menu == "upgrade" else lambda: None,
                                    target=item))
        commands.append(Command("Back", "Esc", lambda: self.open_settlement(None), tooltip="Back to selection commands"))
        return commands

    # -- Command card ----------------------------------------------------------------

    def _commands(self) -> list[Command]:
        if self.settlement_menu is not None:
            return self._settlement_commands()
        world = self.world
        units = self._own_units()
        if self.build_menu and any(u.is_worker for u in units):
            commands = []
            for building_type in BUILD_ORDER:
                info = self.race.buildings[building_type]
                commands.append(Command(
                    self.race.cards[building_type], info.hotkey.upper(), lambda bt=building_type: self.start_pending(f"build:{bt.value}"),
                    tooltip=f"{info.name} — {info.cost} · {info.summary}", blocked=lambda bt=building_type: self._build_blocked(bt),
                    target=building_type,
                ))
            commands.append(Command("Back", "Esc", self.close_build_menu, tooltip="Back to the unit commands"))
            return commands
        if units:
            commands = [
                Command("Move", "M", lambda: self.start_pending("move"), tooltip="Move to a spot (right-click does this too)"),
                Command("Stop", "S", self.command_stop, tooltip="Drop every order"),
                Command("Attack", "A", lambda: self.start_pending("attack"), tooltip="Attack a target, or attack-move: fight everything on the way", style=DANGER_BUTTON),
                Command("Hold", "H", self.command_hold, tooltip="Stand here; fight what comes in range but never chase"),
                Command("Patrol", "P", lambda: self.start_pending("patrol"), tooltip="Walk between here and a spot, fighting whatever turns up"),
            ]
            if any(u.is_worker for u in units):
                commands.append(Command("Build", "B", self.open_build_menu, tooltip="Farms, barracks, halls, towers and the tech buildings", style=ACTION_BUTTON))
                commands.append(Command("Repair", "R", lambda: self.start_pending("repair"), tooltip="Mend one of your damaged buildings; a full repair costs half its price"))
            return commands
        building = self._own_building()
        if building is not None:
            if not building.done:
                return [Command("Cancel", "C", self.cancel_construction, tooltip="Tear the site down; the cost comes back", style=DANGER_BUTTON)]
            commands = []
            for unit_type in building.info.trains:
                info = self.race.units[unit_type]
                commands.append(Command(info.name, info.hotkey.upper(), lambda ut=unit_type: self.train(ut),
                                        tooltip=f"{info.name} — {info.cost} · {info.summary}",
                                        blocked=lambda ut=unit_type, b=building: world.can_train(b, ut), target=unit_type))
            for upgrade in building.info.researches:
                info = UPGRADES[upgrade]
                if upgrade in self.player.upgrades or not self.race.upgrade_allowed(upgrade):
                    continue
                if info.requires is not None and info.requires not in self.player.upgrades and any(
                        UPGRADES[u].requires is None and u not in self.player.upgrades and u in building.info.researches and UPGRADES[u].hotkey == info.hotkey
                        for u in building.info.researches):
                    continue  # the tier below has the same key; show it once its prerequisite is done
                commands.append(Command(UPGRADE_NAMES[upgrade], info.hotkey.upper(), lambda up=upgrade: self.research(up),
                                        tooltip=f"{info.name} — {info.cost} · {info.summary}",
                                        blocked=lambda up=upgrade, b=building: world.can_research(b, up), target=upgrade))
            if building.info.trains or building.info.researches:
                commands.append(Command("Cancel", "X", self.cancel_work, tooltip="Cancel the last unit queued, or the research",
                                        blocked=lambda b=building: None if b.queue or b.research is not None else "Nothing in progress"))
            return commands
        return []

    def _build_blocked(self, building_type: BuildingType) -> str | None:
        info = BUILDINGS[building_type]
        if info.requires is not None and not self.world.player_buildings(self.human, info.requires, done=True):
            return f"Requires a {self.building_name(info.requires)}"
        return self.world.can_afford(self.human, info.cost)

    def _refresh_card(self) -> None:
        commands = self._commands()
        self.card_panel.visible = bool(commands)
        signature = [(c.label, c.hotkey, c.cost, c.target) for c in commands]
        if signature == [(c.label, c.hotkey, c.cost, c.target) for c in self._card]:
            self._card = commands
            for command, button in zip(commands, self._card_buttons):
                button.on_click = command.action
            return
        self._card = commands
        self._card_buttons = []
        self.card_panel.clear()
        if not commands:
            self.card_panel.visible = False
            return
        self.card_panel.visible = True
        if self.settlement_menu is not None:
            self.card_panel.add(Label(f"{self.settlement_menu.title()} plans", text_style="heading"))
            self.card_panel.add(Label("Cost: gold / lumber · paid when work starts", text_style="caption", width=360, wrap=True))
        portraits = any(c.target is not None for c in commands)
        for start in range(0, len(commands), CARD_COLS):
            row = Row(spacing=6)
            for command in commands[start:start + CARD_COLS]:
                captions = []
                if command.target is not None:
                    # A portrait or emblem with the hotkey in its corner; the name and any cost sit under it.
                    button = ProductionButton(command.target, self.human, self.player.race, hotkey=command.hotkey or None, on_click=command.action,
                                              style=command.style, width=CARD_WIDTH, height=CARD_ICON)
                    captions.append(Label(command.label, text_style="caption", width=CARD_WIDTH, align="center"))
                else:
                    button = Button(command.label, hotkey=command.hotkey or None, on_click=command.action, style=command.style, width=CARD_WIDTH,
                                    height=CARD_ICON if portraits else None)
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
        for command in self._card:
            if command.key == key:
                if shift and self.settlement_menu == "train" and command.target is not None:
                    blocked = command.blocked()
                    if blocked is not None:
                        self.warn(blocked)
                        return True
                    try:
                        for _ in range(5):
                            self.order("order_unit", self.human, command.target)
                    except RuleError as exc:
                        self.warn(str(exc))
                        return True
                    self.say(f"5 x {self.race.units[command.target].name} ordered - pay when work starts - manage in Plans")
                    self.sfx("button")
                    return True
                blocked = command.blocked()
                if blocked is None:
                    command.action()
                else:
                    self.warn(blocked)
                return True
        return False

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
        self.game.push(PauseScene(self))

    def open_help(self) -> None:
        self.game.push(HelpScene())

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

    def _over_ui(self, x: float, y: float) -> bool:
        return any(child.visible and child.hit_test(x, y) for child in self.ui.children)

    def handle_input(self, event: InputEvent) -> bool:
        if event.type == "key_press" and event.key is not None:
            if event.key in GROUP_KEYS:
                self._group(event.key, assign=event.ctrl or event.meta, add=event.shift)
                return True
            if event.ctrl or event.meta or event.alt:
                return False
            return self._press_card_key(event.key, shift=event.shift)
        if not event.is_mouse:
            return False
        point = to_tiles(event.world_x, event.world_y)  # type: ignore[arg-type]
        if event.type == "move":
            self.mouse = (event.x, event.y)
            self.hover = point
            return True
        if event.type == "click" and event.button == "left":
            if self._over_ui(event.x, event.y):
                return False
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
            if self._over_ui(event.x, event.y):
                return False
            if self.pending is not None or self.build_menu or self.settlement_menu is not None:
                self.pending = None
                self.build_menu = False
                self.settlement_menu = None
                self._refresh_card()
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

    def _execute_pending(self, point: tuple[float, float], *, keep: bool) -> None:
        mode = self.pending
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
        elif mode is not None and mode.startswith("plan:"):
            self.place_plan(BuildingType(mode[5:]), point, keep=keep)
            return
        elif mode is not None and mode.startswith("build:"):
            self.place_building(BuildingType(mode[6:]), point, keep=keep)
            return
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
                    break
        self._advance(dt)
        self._handle_events(self.world.take_events())
        if not self._game_over:
            play_music(self.mood, self.player.race)
        self._prune_selection()
        self.effects.update(dt)
        self.view.sync(dt)
        self._update_card()
        self.idle_button.visible = self._idle_peasant_count() > 0
        self._update_tutorial()
        if self.world.time >= self._autosave_at and not self._game_over:
            self._autosave_at += AUTOSAVE_EVERY
            self.game.save("autosave", scene=self)
            self.say("Autosaved")
        self._check_game_over()

    def _advance(self, dt: float) -> None:
        if not self.paused and not self._game_over and self.world.winner is None and self.player.alive:  # a decided match stays frozen
            self._acc += min(dt, 0.25) * self.speed
            steps = 0
            while self._acc >= SIM_DT and steps < MAX_STEPS_PER_FRAME:
                for brain in self.brains:
                    brain.think(self.world, self.rng)
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
        view = self.view
        for e in events:
            mine = e.player == self.human
            if e.kind == "hit":
                if self._mine(e):
                    self._fights.append(self.clock)
                self._show_hit(e)
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
                self.effects.add(Pulse(to_world(e.pos), (140, 255, 160, 200), radius=(4, 16), rings=1, duration=0.4))
            elif e.kind == "tree_felled" and mine and self._audible(e.pos):
                self.sfx("chop", gap=2.5)
            elif e.kind == "under_attack" and mine:
                self.last_alert = e.pos
                self.minimap.ping(*to_world(e.pos))
                self.effects.add(Toast("Under attack!", ["Press Space to look"], hold=3.0, top=TOAST_TOP))
                self.sfx("under_attack")
            elif e.kind == "refused" and mine:
                self.warn(e.text)
            elif e.kind in ("eliminated", "surrendered") and not mine:
                self.effects.add(Toast("A rival falls", [e.text], accent=GOOD, hold=4.0, top=TOAST_TOP))
            elif e.kind == "exposed":
                self.effects.add(Toast(f"{e.text}'s last holdings are revealed", [e.text], hold=4.0, top=TOAST_TOP))
            elif e.kind == "exhausted":
                self.effects.add(FloatingText("Mine exhausted", (to_world(e.pos)[0], to_world(e.pos)[1] - TILE), MUTED, rise=20, duration=1.5))
            elif e.kind == "plunder" and mine:
                self.effects.add(FloatingText(f"+{e.amount} gold plundered", (to_world(e.pos)[0], to_world(e.pos)[1] - TILE), GOLD, rise=26, duration=1.8))
            elif e.kind == "tree_grown":
                view.tree_grown((int(e.pos[0]), int(e.pos[1])))

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
        if isinstance(target, Unit):
            sprite = self.view.unit_sprite(target.id)
            if sprite is not None and sprite.visible:
                self.effects.add(HitReaction(sprite, (1.0, 1.0, 1.0), knockback=0.0, wobble=6.0, duration=0.2))
        source = self.world.entity(e.entity) if e.entity is not None else None
        if e.text == "ranged" and source is not None:
            if isinstance(source, Unit) and source.info.splash > 0:
                flight = self._stone(source, e.pos)
            else:
                flight = self._arrow(source, e.pos)
            if flight is not None:
                self.after(flight, lambda: self._sound_hit(e))
        else:
            self._sound_hit(e)

    def _sound_hit(self, event: Event) -> None:
        if self._audible(event.pos):
            source = self.world.entity(event.entity) if event.entity is not None else None
            self.sfx(impact_sound(event, source.race if source is not None else Race.HUMAN))  # a striker dead with its blow keeps the common Foley

    def _arrow(self, source: Entity, target: tuple[float, float]) -> float:
        sx, sy = to_world(source.pos if isinstance(source, Unit) else source.center)
        tx, ty = to_world(target)
        sy -= TILE * 0.5
        ty -= TILE * 0.4
        if isinstance(source, Building):
            sy -= TILE * 1.2
        arrow = self.add_sprite(Sprite("arrow", position=(sx, sy), size=(22, 6), layer=RenderLayer.EFFECTS, rotation=math.degrees(math.atan2(ty - sy, tx - sx))))
        arrow.do(Sequence(MoveTo((tx, ty), speed=520), Remove()))
        return math.dist((sx, sy), (tx, ty)) / 520

    def _stone(self, source: Unit, target: tuple[float, float]) -> float | None:
        """A catapult stone: lobbed slowly, bursting where it lands (one per volley)."""
        if self.clock - self._sound_times.get("stone", -1.0) < 0.3:
            return
        self._sound_times["stone"] = self.clock
        sx, sy = to_world(source.pos)
        tx, ty = to_world(target)
        stone = self.add_sprite(Sprite("stone", position=(sx, sy - TILE * 0.8), size=(12, 12), layer=RenderLayer.EFFECTS))
        stone.do(Sequence(MoveTo((tx, ty - TILE * 0.2), speed=330), Remove()))
        flight = math.dist((sx, sy), (tx, ty)) / 330
        self.effects.add(Burst((tx, ty), (200, 190, 170, 255), 12, rng=self.rng, size=12, speed=(40, 140), delay=flight))
        return flight

    def _show_death(self, e: Event) -> None:
        if not self._visible(e.pos):
            return
        sprite = self.view.release_unit_sprite(e.entity) if e.entity is not None else None
        if sprite is not None:
            self.add_sprite(sprite)
            self.effects.add(UnitDeath(sprite, to_world(e.pos)))  # the body falls and lies there a while
        color = self.world.players[e.player].color if e.player is not None else (200, 200, 200)
        self.effects.add(Burst(to_world(e.pos), rgba(color), 10, rng=self.rng, size=10))
        if self._audible(e.pos):
            self.sfx("death")

    def _show_destroyed(self, e: Event) -> None:
        if e.player == self.human:
            self.effects.add(Toast("Building lost", [f"Your {self.building_name(BuildingType(e.text)).lower()} was destroyed"], hold=4.0, top=TOAST_TOP))
        if self._visible(e.pos):
            wx, wy = to_world(e.pos)
            self.effects.add(Burst((wx, wy), (255, 160, 80, 255), 18, rng=self.rng, size=16, speed=(40, 160)))
            self.effects.add(Burst((wx, wy - 10), (60, 60, 64, 255), 14, rng=self.rng, image="smoke", size=28, speed=(10, 50)))
            self.camera.shake(4, 0.3)
            if self._audible(e.pos):
                self.sfx("destroyed", gap=0.3)

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

    # -- Drawing ---------------------------------------------------------------------------

    def _ghost(self) -> tuple[BuildingType, Pos, bool] | None:
        if self.pending is None or not self.pending.startswith(("build:", "plan:")) or self._over_ui(*self.mouse):
            return None
        building_type = BuildingType(self.pending.split(":", 1)[1])
        site = self._ghost_site(building_type)
        builder = next((u.id for u in self._own_units() if u.is_worker), None)
        reason = (self.world.can_plan_building(building_type, site, self.human) if self.pending.startswith("plan:") else
                  self.world.can_place(building_type, site, self.human, builder=builder))
        ok = reason is None
        return (building_type, site, ok)

    def draw(self) -> None:
        hovered = None
        if not self._over_ui(*self.mouse) and self.pending is None:
            entity = self.world.entity_at(self.hover, visible_to=self.human)
            hovered = entity.id if entity is not None else None
        self.view.draw(Overlay(selected=list(self.selection), hovered=hovered, ghost=self._ghost(),
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
        for plan in self.world.player_plans(self.human):
            if plan.kind != "building" or plan.building is not None:
                continue
            x, y = to_world(plan.pos)
            size = BUILDINGS[plan.type].size * TILE
            self.draw_rect(x, y, size, size, (110, 190, 255, 28), border_color=(150, 210, 255, 220), border_width=2, space="world")
            self.draw_text(f"Planned {self.building_name(plan.type)}", x + size / 2, y - 5, style="caption",
                           color=(180, 220, 255, 255), anchor_x="center", space="world")
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
        if self.settlement_menu is not None:
            self.draw_text(f"{self.settlement_menu.title()} plans", x + 16, y + 30, style="heading")
            self.draw_paragraph("Choose a plan without selecting a worker or building. Plans wait for resources and prerequisites.",
                                x + 16, y + 46, w - 32, style="body")
            return
        entities = [e for e in (self.world.entity(i) for i in self.selection) if e is not None]
        if not entities:
            tile = (int(self.hover[0]), int(self.hover[1]))
            text = "Nothing selected"
            if self.world.in_bounds(tile) and self.world.is_explored(self.human, tile):
                text = f"{self.world.terrain_at(tile).value.title()} ({tile[0]}, {tile[1]})"
            self.draw_text(text, x + 16, y + 30, style="heading")
            self.draw_text("Drag to select units · right-click to order them", x + 16, y + 58, style="sub")
            return
        if len(entities) == 1:
            self._draw_entity_card(entities[0], x + 16, y + 14)
        else:
            self.draw_text(f"{len(entities)} units", x + 16, y + 30, style="heading")
            size, gap = 34, 4
            for i, entity in enumerate(entities[:MAX_PORTRAITS]):
                px, py = x + 16 + i * (size + gap), y + 46
                self._portraits.append((entity.id, (px, py, size, size)))
                self.draw_rect(px, py, size, size, (255, 255, 255, 18), border_color=(255, 255, 255, 40), border_width=1, radius=4)
                self._portrait(entity, px + 3, py + 2, size - 6)
                frac = entity.hp / max(1, entity.max_hp)
                self.draw_rect(px, py + size + 3, size, 3, (0, 0, 0, 160))
                self.draw_rect(px, py + size + 3, size * frac, 3, GOOD if frac > 0.5 else BAD)
        self.command_tooltip.visible = bool(self.tooltip)

    def _portrait(self, entity: Entity, x: float, y: float, size: float) -> None:
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

    def _draw_entity_card(self, entity: Entity, x: float, y: float) -> None:
        world = self.world
        self.draw_rect(x, y, 72, 72, (255, 255, 255, 16), border_color=(255, 255, 255, 40), border_width=1, radius=6)
        self._portrait(entity, x + 4, y + 4, 64)
        tx = x + 88
        owner = world.players[entity.player].name if entity.player is not None else "Neutral"
        name = entity.info.name
        self.draw_text(f"{name}", tx, y + 16, style="heading")
        color = rgba(world.players[entity.player].color) if entity.player is not None else GOLD
        self.draw_text(owner, tx + 6 + self.game.backend.measure_text(name, 17, "Nunito SemiBold")[0], y + 16, style="sub", color=color)
        lines: list[str] = []
        if isinstance(entity, Building) and entity.type is BuildingType.GOLD_MINE:
            lines.append(f"{entity.gold} gold left")
        else:
            self.draw_rect(tx, y + 26, 180, 8, (0, 0, 0, 160), radius=3)
            frac = entity.hp / max(1, entity.max_hp)
            self.draw_rect(tx, y + 26, 180 * frac, 8, GOOD if frac > 0.5 else (240, 200, 80, 255) if frac > 0.25 else BAD, radius=3)
            self.draw_text(f"{entity.hp}/{entity.max_hp}", tx + 188, y + 34, style="sub")
        if isinstance(entity, Unit):
            info = entity.info
            primary = (("health", f"{world.heal_rate(entity):g}/s", "Healing restored per second") if info.heal
                       else ("damage", str(world.damage_of(entity)), "Damage per strike"))
            stats = [primary, ("armor", str(world.armor_of(entity)), "Armour, subtracted from every blow"),
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
            if entity.inside is not None:
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
        elif isinstance(entity, Building):
            if not entity.done:
                frac = entity.progress / entity.info.build_time
                lines.append(f"Under construction {int(frac * 100)}%" + ("" if entity.builder is not None else " — no builder: right-click it with a peasant"))
            elif entity.queue or entity.research is not None:
                self._draw_production(entity, tx, y + 44)
            elif entity.player == self.human:
                lines.append(entity.info.summary)
                if entity.type is BuildingType.TOWN_HALL:
                    lines.append("Rally point set" if entity.rally is not None else "Right-click the map to set a rally point")
        ly = y + 82 if isinstance(entity, Unit) else y + 50
        for line in lines[:2]:
            self.draw_text(line, tx, ly, style="body")
            ly += 22

    # -- Save / load ------------------------------------------------------------------------

    def get_save_state(self) -> dict:
        return {"version": SAVE_VERSION, "seed": self.seed, "difficulty": self.difficulty.value, "world": self.world.to_dict(),
                "run_id": self.run_id, "ranked": self.ranked,
                "groups": self.groups, "tutorial": self.tutorial.step if self.tutorial is not None else None}

    def get_save_summary(self) -> dict:
        world = self.world
        size = next((name for name, (w, h) in mapgen.SIZES.items() if (w, h) == (world.width, world.height)), f"{world.width}×{world.height}")
        return {"map": f"{size} {world.theme.value}", "players": len(world.players), "difficulty": self.difficulty.value, "clock": _clock(world.time),
                "player": f"{self.player.name} ({self.race.name})"}

    def load_save_state(self, state: dict) -> None:
        world = check_save(state)
        if (world.width, world.height) != (self.world.width, self.world.height):
            self.game.clear_and_push(load_game(state, settings=self.settings))
            return
        self.world = world
        self.human = next(p.id for p in world.players if p.human)
        self.run_id = _saved_run_id(state)
        self.ranked = state.get("ranked", True)
        self.seed = state["seed"]
        self.difficulty = Difficulty(state["difficulty"])
        self.brains = [Brain(p.id, self.difficulty) for p in world.players if not p.human]
        self.groups = {k: list(v) for k, v in state.get("groups", {}).items()}
        self.tutorial = Tutorial() if state.get("tutorial") is not None and self.settings["tutorial"] else None
        if self.tutorial is not None:
            self.tutorial.step = state["tutorial"]
        self._autosave_at = (world.time // AUTOSAVE_EVERY + 1) * AUTOSAVE_EVERY
        self.effects.clear()
        self.selection = []
        self.pending = None
        self.build_menu = False
        self.settlement_menu = None
        self._game_over = False
        self.view.reset(world)
        self.ui.clear()
        self._build_hud()
        self.center_base(instant=True)
        self.say("Loaded")


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
        self.game.push(HelpScene())

    def resign(self) -> None:
        scene = self.game_scene
        if scene.world.can_resign(scene.human) is not None:
            return
        self.game.pop()
        scene.world.resign(scene.human)

    def new_game(self) -> None:
        scene = self.game_scene
        self.game.clear_and_push(new_game(scene.seed + 1, width=scene.world.width, height=scene.world.height, players=len(scene.world.players),
                                          difficulty=scene.difficulty, theme=scene.world.theme, settings=scene.settings,
                                          races=[p.race for p in scene.world.players]))

    def back_to_title(self) -> None:
        from warband.title import TitleScene

        self.game.clear_and_push(TitleScene(settings=self.game_scene.settings))

    def quit(self) -> None:
        self.game.quit()


class SettingsScene(_Overlay):
    """Keyboard-navigable options: ↑↓ pick a row, ←→ adjust or toggle.  Saved to the settings file."""

    pause_below = True
    controls = {"up": "focus_up", "down": "focus_down", "left": "decrease", "right": "increase", ("return", "space"): "increase"}
    ROWS: tuple[tuple[str, str, str], ...] = (
        ("Music volume", "music", "percent"), ("Sound volume", "sfx", "percent"), ("Edge scrolling", "edge_scroll", "toggle"),
        ("Scroll speed", "scroll_speed", "speed"), ("Fullscreen", "fullscreen", "toggle"), ("Tutorial", "tutorial", "toggle"),
    )

    def __init__(self, game_scene: GameScene) -> None:
        self.game_scene = game_scene
        self.focus = 0

    @property
    def settings(self) -> dict[str, Any]:
        return self.game_scene.settings

    def _shown(self, key: str, kind: str) -> str:
        value = self.settings[key]
        if kind == "percent":
            return f"{round(value * 100)}%"
        if kind == "speed":
            return f"×{value:g}"
        return "On" if value else "Off"

    def on_enter(self) -> None:
        panel = self.panel("Settings")
        for index, (name, key, kind) in enumerate(self.ROWS):
            marker = Label(lambda i=index: "›" if self.focus == i else "", text_style="hud", width=18, text_color=GOLD)
            panel.add(Row(marker, Label(name, text_style="body", width=170), Row(
                Button("−", on_click=lambda k=key: self._adjust(k, -1), style=GHOST_BUTTON, width=48),
                Label(lambda k=key, kd=kind: self._shown(k, kd), text_style="hud", width=70, align="center"),
                Button("+", on_click=lambda k=key: self._adjust(k, 1), style=GHOST_BUTTON, width=48),
                spacing=8,
            ), spacing=12))
        panel.add(Label("Settings are saved when you leave this screen.", text_style="sub"))
        panel.add(KeyHints([("↑↓", "select"), ("←→", "adjust"), ("Esc", "close")]))

    def _adjust(self, key: str, direction: int) -> None:
        kind = next(k for _n, k2, k in self.ROWS if k2 == key)
        if kind == "percent":
            self.settings[key] = round(max(0.0, min(1.0, self.settings[key] + 0.1 * direction)), 2)
            apply_volumes(self.settings["music"], self.settings["sfx"])
        elif kind == "speed":
            self.settings[key] = round(max(0.5, min(2.0, self.settings[key] + 0.25 * direction)), 2)
        else:
            self.settings[key] = not self.settings[key]
        self.game_scene.sfx("button")

    def on_exit(self) -> None:
        self.game_scene.apply_settings()

    def focus_up(self) -> None:
        self.focus = (self.focus - 1) % len(self.ROWS)

    def focus_down(self) -> None:
        self.focus = (self.focus + 1) % len(self.ROWS)

    def decrease(self) -> None:
        self._adjust(self.ROWS[self.focus][1], -1)

    def increase(self) -> None:
        self._adjust(self.ROWS[self.focus][1], 1)


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
                detail = f"{s.get('player', '')} · {s.get('map', '')} · {s.get('players', '?')} players · {s.get('difficulty', '')} · {s.get('clock', '')} · {entry['timestamp'][:16].replace('T', ' ')}"
                ok = True
            button = Button(name, hotkey=key, on_click=lambda sl=slot: self.pick(sl), style=ACTION_BUTTON if ok else GHOST_BUTTON, width=150)
            button.enabled = ok and not (self.mode == "save" and slot == "autosave")
            panel.add(Row(button, Label(detail, text_style="body", width=520), spacing=12))
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
    "Peasants gather and build automatically. Use Settlement to plan buildings, units and upgrades.",
    "Plans wait for money and prerequisites. Defeat the enemy by destroying its buildings and units.",
)
HELP_KEYS = (
    ("Settlement", "Ctrl+B build, Ctrl+T train, Ctrl+U upgrade without a selection; Ctrl+P Plans, Ctrl+G assembly; Shift+letter orders five in Train"),
    ("Assembly (Ctrl+G)", "choose a destination for new soldiers; workers keep working"),
    ("Left click / drag", "select a unit, a building, or every unit in the box"),
    ("Right click", "move, harvest, attack or resume building — the sensible thing for the target"),
    ("Shift", "add to the selection, or queue an order after the current one"),
    ("Double-click / Ctrl-click", "select every unit of that type on screen;  Ctrl+A: the whole army (Cmd-click on a Mac)"),
    ("Mac trackpad", "two-finger click or Ctrl+click is the right-click"),
    ("A / P", "attack-move: fight everything on the way / patrol between two spots"),
    ("S / H", "stop / hold position"),
    ("B", "build (peasants): F farm, B barracks, H town hall, T tower, M mill, K smith, S stables, W workshop, C church"),
    ("R", "repair (peasants): click one of your damaged buildings; a right-click on it does the same"),
    ("P / F / A / K", "train peasant / footman / archer / knight in the selected building"),
    ("Ctrl+1-9 / 1-9", "assign / recall a control group"),
    ("Tab / .", "next idle peasant / soldier"),
    ("Space", "jump to the last alert;  Ctrl+F6-F8 / F6-F8: set / return to a camera bookmark"),
    ("Arrows / edges / middle-drag", "scroll the map;  wheel / + / −  zoom"),
    ("Minimap", "left-click to look, right-click to send the selection there"),
    ("F3 / F5 / F9", "offline: pause / save / load; online uses a live match menu"),
    ("F2", "codex: every unit, building and upgrade"),
    ("Esc", "cancel, deselect, then the menu"),
)


class HelpScene(_Overlay):
    pause_below = True

    def on_enter(self) -> None:
        panel = self.panel("How to play")
        for line in HELP_INTRO:
            panel.add(Label(line, text_style="body", width=700))
        table = Column(spacing=4)
        for keys, what in HELP_KEYS:
            table.add(Row(Label(keys, text_style="hud", width=250, align="right", text_color=GOLD), Label(what, text_style="body", width=520), spacing=14))
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
            for cells in self._rows():
                table.add(Row(*[Label(text, text_style="hud" if i == 0 else "body", width=width, text_color=GOLD if i == 0 else None)
                                for i, (text, width) in enumerate(cells)], spacing=10))
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

    def _rows(self) -> list[list[tuple[str, int]]]:
        player = self.world.players[self.player]
        have = player.upgrades
        race = RACES[player.race]
        if self.page == 0:
            rows = [[("Unit", 120), ("Cost", 150), ("HP", 50), ("Dmg", 50), ("Arm", 50), ("Rng", 50), ("Spd", 50), ("Trained at", 120), ("Role", 320)]]
            for unit_type, info in race.units.items():
                rows.append([(info.name, 120), (str(info.cost), 190), (str(info.hp), 50), (str(info.damage) if info.damage else f"heal {info.heal}", 50),
                             (str(info.armor), 50), ("melee" if info.range < 1 else f"{info.range:g}", 50), (f"{info.speed:g}", 50),
                             (race.buildings[info.trained_at].name, 120), (info.summary, 320)])
            return rows
        if self.page == 1:
            rows = [[("Building", 120), ("Cost", 150), ("HP", 50), ("Arm", 50), ("Size", 50), ("Time", 50), ("Requires", 110), ("What it does", 400)]]
            for building_type, info in race.buildings.items():
                if building_type is BuildingType.GOLD_MINE:
                    continue
                rows.append([(info.name, 120), (str(info.cost), 190), (str(info.hp), 50), (str(info.armor), 50), (f"{info.size}×{info.size}", 50),
                             (f"{info.build_time:g}s", 50), (race.buildings[info.requires].name if info.requires else "—", 110),
                             (info.summary + (f" · supply +{info.supply}" if info.supply else ""), 400)])
            return rows
        if self.page == 2:
            rows = [[("Upgrade", 160), ("Cost", 150), ("Time", 50), ("Where", 110), ("Requires", 150), ("Effect", 320)]]
            for upgrade, info in UPGRADES.items():
                if not race.upgrade_allowed(upgrade):
                    continue
                where = next(b for b, binfo in BUILDINGS.items() if upgrade in binfo.researches)
                requires = UPGRADES[info.requires].name if info.requires else f"{race.adjective} art" if info.race is not None else "—"
                rows.append([(info.name + (" ✓" if upgrade in have else ""), 160), (str(info.cost), 190), (f"{info.time:g}s", 50),
                             (race.buildings[where].name, 110), (requires, 150), (info.summary, 320)])
            return rows
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
        panel.add(Row(Button("New game", hotkey="N", on_click=self.new_game, style=ACTION_BUTTON, width=210),
                      Button("High scores", hotkey="B", on_click=self.high_scores, style=GHOST_BUTTON, width=210),
                      Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=210),
                      Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=190), spacing=12))

    def high_scores(self) -> None:
        from warband.score_scene import HighScoreScene

        scene = self.game_scene
        self.game.push(HighScoreScene(difficulty=scene.difficulty, size=(scene.world.width, scene.world.height),
                                      players=len(scene.world.players), run_id=scene.run_id, error=self.score_error))

    def new_game(self) -> None:
        scene = self.game_scene
        self.game.clear_and_push(new_game(scene.seed + 1, width=scene.world.width, height=scene.world.height, players=len(scene.world.players),
                                          difficulty=scene.difficulty, theme=scene.world.theme, settings=scene.settings,
                                          races=[p.race for p in scene.world.players]))

    def back_to_title(self) -> None:
        from warband.title import TitleScene

        scene = self.game_scene
        size = next((name for name, dimensions in mapgen.SIZES.items() if dimensions == (scene.world.width, scene.world.height)), "Medium")
        self.game.clear_and_push(TitleScene(size=size, players=len(scene.world.players), difficulty=scene.difficulty, theme=scene.world.theme,
                                           race=scene.player.race, settings=scene.settings))

    def quit(self) -> None:
        self.game.quit()


def new_game(seed: int, width: int = 48, height: int = 40, players: int = 2, *, difficulty: Difficulty = Difficulty.NORMAL,
             theme: MapTheme = MapTheme.SUMMER, settings: dict[str, Any] | None = None, races: list[Race | None] | None = None) -> GameScene:
    return GameScene(mapgen.generate(seed=seed, width=width, height=height, players=players, theme=theme, races=races), seed, difficulty=difficulty,
                     settings=settings)


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


def load_game(state: dict[str, Any], *, settings: dict[str, Any] | None = None) -> GameScene:
    """A game scene from a save slot's ``state`` (see :meth:`GameScene.get_save_state`)."""
    world = check_save(state)
    scene = GameScene(world, state["seed"], difficulty=Difficulty(state["difficulty"]), settings=settings,
                      run_id=_saved_run_id(state), ranked=state.get("ranked", True))
    scene.groups = {k: list(v) for k, v in state.get("groups", {}).items()}
    if state.get("tutorial") is not None and scene.tutorial is not None:
        scene.tutorial.step = state["tutorial"]
    scene._autosave_at = (world.time // AUTOSAVE_EVERY + 1) * AUTOSAVE_EVERY
    return scene
