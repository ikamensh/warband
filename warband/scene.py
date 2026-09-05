"""saga2d scenes for Warband: the match, its HUD, and the overlays stacked on it."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from saga2d import (
    Anchor, Button, Camera, Column, InputEvent, KeyHints, Label, Layout, Minimap, MoveTo, Panel, Remove, RenderLayer, Row, Scene,
    Sequence, Sprite, Style,
)
from saga2d import SaveError
from saga2d.effects import Banner, Burst, Dissolve, Effects, FloatingText, HitReaction, Pulse, Toast
from warband import mapgen
from warband.ai import Brain
from warband.model import Building, Entity, Event, Pos, RuleError, Unit, World
from warband.rules import BUILDINGS, SIM_DT, UNITS, UPGRADES, BuildingType, Difficulty, MapTheme, UnitType, Upgrade
from warband.sound import apply_volumes, play_sound
from warband.style import ACTION_BUTTON, BAD, CARD_BUTTON, DANGER_BUTTON, GHOST_BUTTON, GOLD, GOOD, LUMBER, MUTED, OVERLAY_STYLE, PANEL_STYLE
from warband.textures import TILE
from warband.tutorial import OBJECTIVES, Tutorial
from warband.view import MapView, Overlay, rgba, to_tiles, to_world

DEFAULT_SETTINGS: dict[str, Any] = {"music": 0.6, "sfx": 0.8, "edge_scroll": True, "scroll_speed": 1.0, "fullscreen": False, "tutorial": True}
SAVE_VERSION = 1
SAVE_SLOTS = 3
AUTOSAVE_EVERY = 120.0  # seconds of match time
TOAST_TOP = 150  # below the objectives strip
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
CARD_WIDTH = 108
MINIMAP_WIDTH = 200
SELECTION_WIDTH = 470
SELECTION_HEIGHT = 128
MAX_PORTRAITS = 12
SOUND_GAP = 0.08  # seconds between repeats of the same battle sound


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


@dataclass
class Command:
    """One command-card button."""

    label: str
    hotkey: str
    action: Callable[[], None]
    tooltip: str = ""
    blocked: Callable[[], str | None] = field(default=lambda: None)  # why it cannot be used right now
    style: Style = field(default_factory=lambda: CARD_BUTTON)

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
                 stats: dict[str, int] | None = None) -> None:
        self.world = world
        self.seed = seed
        self.difficulty = difficulty
        self.human = next(p.id for p in world.players if p.human)
        self.brains = [Brain(p.id, difficulty) for p in world.players if not p.human]
        self.rng = random.Random(seed)
        self.settings = settings if settings is not None else dict(DEFAULT_SETTINGS)  # a saga2d Settings when the game runs
        for key, value in DEFAULT_SETTINGS.items():
            self.settings.setdefault(key, value)
        self.stats: dict[str, int] = {"units_lost": 0, "units_killed": 0, "buildings_lost": 0, "buildings_razed": 0, **(stats or {})}
        self.tutorial = Tutorial() if self.settings["tutorial"] else None
        self._autosave_at = AUTOSAVE_EVERY
        self.selection: list[int] = []
        self.groups: dict[str, list[int]] = {}
        self.pending: str | None = None  # "move" | "attack" | "build:<type>"
        self.build_menu = False
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
        self._last_click: tuple[float, int | None] = (-10.0, None)
        self.bookmarks: dict[int, tuple[float, float]] = {}

    # -- Lifecycle -------------------------------------------------------------

    def on_enter(self) -> None:
        self.view = MapView(self, self.world, self.human)
        self._setup_camera()
        self.apply_settings()
        self._build_hud()
        self.center_base(instant=True)
        self.effects.add(Banner("Warband", subtitle=f"{self.player.name} against {', '.join(p.name for p in self.world.players if p.id != self.human)}",
                                accent=rgba(self.player.color)))

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

    def sfx(self, name: str, *, gap: float = 0.0) -> None:
        """Every sound event passes through here; *gap* rate-limits battle noise."""
        if gap and self.clock - self._sound_times.get(name, -1.0) < gap:
            return
        self._sound_times[name] = self.clock
        self.recent_sounds.append(name)
        if self.settings["sfx"] > 0:
            play_sound(name)

    # -- HUD ---------------------------------------------------------------------

    def _build_hud(self) -> None:
        world, player = self.world, self.player

        def supply_text() -> str:
            used, cap = world.supply(self.human)
            return f"Supply {used}/{cap}"

        self.ui.add(Panel(anchor=Anchor.TOP_LEFT, margin=12, layout=Layout.HORIZONTAL, spacing=18, style=PANEL_STYLE, children=[
            Label(player.name, text_style="title", text_color=rgba(player.color)),
            Label(lambda: f"Gold {player.gold}", text_style="hud", text_color=GOLD),
            Label(lambda: f"Lumber {player.lumber}", text_style="hud", text_color=LUMBER),
            Label(supply_text, text_style="hud"),
            Label(lambda: _clock(world.time), text_style="sub"),
            Label(lambda: "Paused" if self.paused else f"×{self.speed:g}" if self.speed != 1 else "", text_style="hud", text_color=BAD),
            self._idle_button(),
            Button("Menu", hotkey="F10", on_click=self.open_menu, style=GHOST_BUTTON),
        ]))
        world_w, world_h = self.world.width * TILE, self.world.height * TILE
        self.minimap = Minimap(self.view.minimap_key, (world_w, world_h), self.camera, width=MINIMAP_WIDTH,
                               height=round(MINIMAP_WIDTH * world_h / world_w), on_click=self.minimap_click,
                               anchor=Anchor.BOTTOM_LEFT, margin=PANEL_MARGIN, style=PANEL_STYLE)
        self.ui.add(self.minimap)
        self.selection_panel = Panel(width=SELECTION_WIDTH, height=SELECTION_HEIGHT, anchor=Anchor.BOTTOM_CENTER, margin=PANEL_MARGIN, style=PANEL_STYLE)
        self.ui.add(self.selection_panel)
        self.card_panel = Column(spacing=6, anchor=Anchor.BOTTOM_RIGHT, margin=PANEL_MARGIN, style=PANEL_STYLE)
        self.ui.add(self.card_panel)
        self.ui.add(KeyHints(self._hint, anchor=Anchor.BOTTOM_CENTER, margin=5))
        self.ui.add(Label(lambda: self.status if self.status_timer > 0 else "", text_style="hud", anchor=Anchor.TOP_CENTER, margin=(0, 70), text_color=GOLD))
        self.objectives = Column(spacing=4, anchor=Anchor.TOP_RIGHT, margin=12, style=PANEL_STYLE)
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
            return [("F B H T", "choose a building"), ("Esc", "back")]
        if self._own_units():
            return [("Right click", "move / harvest / attack"), ("A", "attack-move"), ("P", "patrol"), ("S", "stop"), ("Ctrl+1-9", "group"), ("Esc", "deselect")]
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

    def command_smart(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            verb = self.world.smart([u.id for u in units], point, queue=queue)
            self._marker(point, (255, 80, 70, 220) if verb == "attack" else (120, 255, 140, 220))
            self.sfx("attack_command" if verb == "attack" else "command")
            return
        building = self._own_building()
        if building is not None and building.done:
            self.world.set_rally(building.id, point)
            self._marker(point, (255, 214, 110, 220))
            self.sfx("command")

    def command_move(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            self.world.move([u.id for u in units], point, queue=queue)
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
                self.world.attack(ids, target.id, queue=queue)
            else:
                self.world.attack_move(ids, point, queue=queue)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self._marker(point, (255, 80, 70, 220))
        self.sfx("attack_command")

    def command_patrol(self, point: tuple[float, float], *, queue: bool = False) -> None:
        units = self._own_units()
        if units:
            self.world.patrol([u.id for u in units], point, queue=queue)
            self._marker(point, (120, 200, 255, 220))
            self.sfx("command")

    def command_stop(self) -> None:
        units = self._own_units()
        if units:
            self.world.stop([u.id for u in units])
            self.sfx("command")

    def command_hold(self) -> None:
        units = self._own_units()
        if units:
            self.world.hold([u.id for u in units])
            self.sfx("command")

    def start_pending(self, mode: str) -> None:
        self.pending = mode
        self.build_menu = False
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
            self.world.build(builder.id, building_type, site, queue=keep)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.sfx("command")
        self._marker((site[0] + size / 2, site[1] + size / 2), (255, 214, 110, 220))
        if not keep:
            self.pending = None
            self._refresh_card()

    def train(self, unit_type: UnitType) -> None:
        building = self._own_building()
        if building is None:
            return
        try:
            self.world.train(building.id, unit_type)
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
            self.world.cancel_train(building.id)
        elif building.research is not None:
            self.world.cancel_research(building.id)
        else:
            return
        self.sfx("button")
        self._refresh_card()

    def research(self, upgrade: Upgrade) -> None:
        building = self._own_building()
        if building is None:
            return
        try:
            self.world.research(building.id, upgrade)
        except RuleError as exc:
            self.warn(str(exc))
            return
        self.sfx("button")
        self._refresh_card()

    def cancel_construction(self) -> None:
        building = self._own_building()
        if building is None or building.done:
            return
        self.world.cancel_building(building.id)
        self.say(f"{building.info.name} cancelled, cost refunded")
        self.sfx("button")
        self.select([])

    def cancel(self) -> None:
        if self.pending is not None:
            self.pending = None
            self._refresh_card()
        elif self.build_menu:
            self.close_build_menu()
        elif self.selection:
            self.select([])
        else:
            self.open_menu()

    # -- Command card ----------------------------------------------------------------

    def _commands(self) -> list[Command]:
        world = self.world
        units = self._own_units()
        if self.build_menu and any(u.is_worker for u in units):
            commands = []
            for building_type in (BuildingType.FARM, BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.TOWER):
                info = BUILDINGS[building_type]
                commands.append(Command(
                    info.name, info.hotkey.upper(), lambda bt=building_type: self.start_pending(f"build:{bt.value}"),
                    tooltip=f"{info.name} — {info.cost} · {info.summary}", blocked=lambda bt=building_type: self._build_blocked(bt),
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
                commands.append(Command("Build", "B", self.open_build_menu, tooltip="Farm, barracks, town hall or tower", style=ACTION_BUTTON))
            return commands
        building = self._own_building()
        if building is not None:
            if not building.done:
                return [Command("Cancel", "C", self.cancel_construction, tooltip="Tear the site down; the cost comes back", style=DANGER_BUTTON)]
            commands = []
            for unit_type in building.info.trains:
                info = UNITS[unit_type]
                commands.append(Command(info.name, info.hotkey.upper(), lambda ut=unit_type: self.train(ut),
                                        tooltip=f"{info.name} — {info.cost} · {info.summary}",
                                        blocked=lambda ut=unit_type, b=building: world.can_train(b, ut)))
            for upgrade in building.info.researches:
                info = UPGRADES[upgrade]
                if upgrade in self.player.upgrades:
                    continue
                if info.requires is not None and info.requires not in self.player.upgrades and any(
                        UPGRADES[u].requires is None and u not in self.player.upgrades and u in building.info.researches and UPGRADES[u].hotkey == info.hotkey
                        for u in building.info.researches):
                    continue  # the tier below has the same key; show it once its prerequisite is done
                commands.append(Command(info.name, info.hotkey.upper(), lambda up=upgrade: self.research(up),
                                        tooltip=f"{info.name} — {info.cost} · {info.summary}",
                                        blocked=lambda up=upgrade, b=building: world.can_research(b, up)))
            if building.info.trains or building.info.researches:
                commands.append(Command("Cancel", "X", self.cancel_work, tooltip="Cancel the last unit queued, or the research",
                                        blocked=lambda b=building: None if b.queue or b.research is not None else "Nothing in progress"))
            return commands
        return []

    def _build_blocked(self, building_type: BuildingType) -> str | None:
        info = BUILDINGS[building_type]
        if info.requires is not None and not self.world.player_buildings(self.human, info.requires, done=True):
            return f"Requires a {BUILDINGS[info.requires].name}"
        return self.world.can_afford(self.human, info.cost)

    def _refresh_card(self) -> None:
        commands = self._commands()
        signature = [(c.label, c.hotkey) for c in commands]
        if signature == [(c.label, c.hotkey) for c in self._card]:
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
        for start in range(0, len(commands), CARD_COLS):
            row = Row(spacing=6)
            for command in commands[start:start + CARD_COLS]:
                button = Button(command.label, hotkey=command.hotkey, on_click=command.action, style=command.style, width=CARD_WIDTH)
                self._card_buttons.append(button)
                row.add(button)
            self.card_panel.add(row)

    def _update_card(self) -> None:
        self.tooltip = ""
        for command, button in zip(self._card, self._card_buttons):
            blocked = command.blocked()
            button.enabled = blocked is None
            if button.state == "hovered":
                self.tooltip = command.tooltip + (f"  ({blocked})" if blocked else "")

    def _press_card_key(self, key: str) -> bool:
        for command in self._card:
            if command.key == key:
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
            return self._press_card_key(event.key)
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
            if self.pending is not None or self.build_menu:
                self.pending = None
                self.build_menu = False
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
        if not self.paused and not self._game_over:
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
        self._handle_events(self.world.take_events())
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

    def _handle_events(self, events: list[Event]) -> None:
        world, view = self.world, self.view
        for e in events:
            mine = e.player == self.human
            if e.kind == "hit":
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
            elif e.kind == "tree_felled" and mine:
                self.sfx("chop", gap=0.3)
            elif e.kind == "deposit" and mine and e.text == "gold":
                self.sfx("gold", gap=0.6)
            elif e.kind == "under_attack" and mine:
                self.last_alert = e.pos
                self.minimap.ping(*to_world(e.pos))
                self.effects.add(Toast("Under attack!", ["Press Space to look"], hold=3.0, top=TOAST_TOP))
                self.sfx("under_attack")
            elif e.kind == "refused" and mine:
                self.warn(e.text)
            elif e.kind == "eliminated" and not mine:
                self.effects.add(Toast("A rival falls", [e.text], accent=GOOD, hold=4.0, top=TOAST_TOP))
            elif e.kind == "exhausted":
                self.effects.add(FloatingText("Mine exhausted", (to_world(e.pos)[0], to_world(e.pos)[1] - TILE), MUTED, rise=20, duration=1.5))
        _ = (world, view)

    def _visible(self, point: tuple[float, float]) -> bool:
        return self.world.is_visible(self.human, (int(point[0]), int(point[1])))

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
                self._stone(source, e.pos)
            else:
                self._arrow(source, e.pos)
                self.sfx("arrow", gap=SOUND_GAP)
        else:
            self.sfx("hit", gap=SOUND_GAP)

    def _arrow(self, source: Entity, target: tuple[float, float]) -> None:
        sx, sy = to_world(source.pos if isinstance(source, Unit) else source.center)
        tx, ty = to_world(target)
        sy -= TILE * 0.5
        ty -= TILE * 0.4
        if isinstance(source, Building):
            sy -= TILE * 1.2
        arrow = self.add_sprite(Sprite("arrow", position=(sx, sy), size=(22, 6), layer=RenderLayer.EFFECTS, rotation=math.degrees(math.atan2(ty - sy, tx - sx))))
        arrow.do(Sequence(MoveTo((tx, ty), speed=520), Remove()))

    def _stone(self, source: Unit, target: tuple[float, float]) -> None:
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
        self.after(flight, lambda: self.sfx("destroyed", gap=0.3))

    def _show_death(self, e: Event) -> None:
        if e.player == self.human:
            self.stats["units_lost"] += 1
        else:
            self.stats["units_killed"] += 1
        if not self._visible(e.pos):
            return
        sprite = self.view.release_unit_sprite(e.entity) if e.entity is not None else None
        if sprite is not None:
            self.add_sprite(sprite)
            self.effects.add(Dissolve(sprite, duration=0.5))
        color = self.world.players[e.player].color if e.player is not None else (200, 200, 200)
        self.effects.add(Burst(to_world(e.pos), rgba(color), 10, rng=self.rng, size=10))
        self.sfx("death", gap=SOUND_GAP)

    def _show_destroyed(self, e: Event) -> None:
        if e.player == self.human:
            self.stats["buildings_lost"] += 1
            self.effects.add(Toast("Building lost", [f"Your {BUILDINGS[BuildingType(e.text)].name.lower()} was destroyed"], hold=4.0, top=TOAST_TOP))
        elif e.player is not None:
            self.stats["buildings_razed"] += 1
        if self._visible(e.pos):
            wx, wy = to_world(e.pos)
            self.effects.add(Burst((wx, wy), (255, 160, 80, 255), 18, rng=self.rng, size=16, speed=(40, 160)))
            self.effects.add(Burst((wx, wy - 10), (60, 60, 64, 255), 14, rng=self.rng, image="smoke", size=28, speed=(10, 50)))
            self.camera.shake(4, 0.3)
            self.sfx("destroyed")

    def _check_game_over(self) -> None:
        if self._game_over:
            return
        if self.world.winner is not None or not self.player.alive:
            self._game_over = True
            won = self.world.winner == self.human
            self.sfx("victory" if won else "defeat")
            self.game.push(GameOverScene(self, won))

    # -- Drawing ---------------------------------------------------------------------------

    def _ghost(self) -> tuple[BuildingType, Pos, bool] | None:
        if self.pending is None or not self.pending.startswith("build:") or self._over_ui(*self.mouse):
            return None
        building_type = BuildingType(self.pending[6:])
        site = self._ghost_site(building_type)
        builder = next((u.id for u in self._own_units() if u.is_worker), None)
        ok = self.world.can_place(building_type, site, self.human, builder=builder) is None
        return (building_type, site, ok)

    def draw(self) -> None:
        hovered = None
        if not self._over_ui(*self.mouse) and self.pending is None:
            entity = self.world.entity_at(self.hover, visible_to=self.human)
            hovered = entity.id if entity is not None else None
        self.view.draw(Overlay(selected=list(self.selection), hovered=hovered, ghost=self._ghost(),
                               rally_for=[b.id for b in [self._own_building()] if b is not None]))
        if self._drag_start is not None and self._drag_end is not None and math.dist(self._drag_start, self._drag_end) >= DRAG_THRESHOLD:
            (x0, y0), (x1, y1) = self._drag_start, self._drag_end
            self.draw_rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), (120, 255, 140, 40), border_color=(120, 255, 140, 220), border_width=1)
        w, h = self.game.resolution
        self.draw_rect(0, h - HINT_BAR, w, HINT_BAR, (8, 10, 14, 180))
        self._draw_selection_panel()
        self.effects.draw(self)

    def _draw_selection_panel(self) -> None:
        panel = self.selection_panel
        x, y, w, h = panel.bounds
        self._portraits = []
        entities = [e for e in (self.world.entity(i) for i in self.selection) if e is not None]
        if not entities:
            tile = (int(self.hover[0]), int(self.hover[1]))
            text = "Nothing selected"
            if self.world.in_bounds(tile) and self.world.is_explored(self.human, tile):
                text = f"{self.world.terrain_at(tile).value.title()} ({tile[0]}, {tile[1]})"
            self.draw_text(text, x + 16, y + 30, style="heading")
            self.draw_text(self.tooltip or "Drag to select units · right-click to order them", x + 16, y + 58, style="sub")
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
        self.draw_text(self.tooltip, x + 16, y + h - 16, style="sub", color=GOLD)

    def _portrait(self, entity: Entity, x: float, y: float, size: float) -> None:
        from warband import textures

        key = textures.portrait_image(self.game, entity.type, entity.player)
        pw, ph = self.game.backend.get_image_size(self.game.assets.image(key))
        scale = min(size / pw, size / ph)
        self.draw_image(key, x + (size - pw * scale) / 2, y + (size - ph * scale) / 2, pw * scale, ph * scale)

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
            if info.heal:
                lines.append(f"Heals {world.heal_rate(entity):g}/s  Range {info.range:g}  Armor {world.armor_of(entity)}  Speed {world.speed_of(entity):g}")
            else:
                lines.append(f"Damage {world.damage_of(entity)}  Armor {world.armor_of(entity)}  Range {world.range_of(entity):g}  Speed {world.speed_of(entity):g}")
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
            elif entity.queue:
                progress = entity.train_progress / UNITS[entity.queue[0]].build_time
                lines.append(f"Training {UNITS[entity.queue[0]].name} {int(progress * 100)}%" + (f" (+{len(entity.queue) - 1} queued)" if len(entity.queue) > 1 else ""))
                self.draw_rect(tx, y + 62, 180, 6, (0, 0, 0, 160), radius=3)
                self.draw_rect(tx, y + 62, 180 * progress, 6, GOLD, radius=3)
            elif entity.research is not None:
                progress = entity.research_progress / UPGRADES[entity.research].time
                lines.append(f"Researching {UPGRADES[entity.research].name} {int(progress * 100)}%")
                self.draw_rect(tx, y + 62, 180, 6, (0, 0, 0, 160), radius=3)
                self.draw_rect(tx, y + 62, 180 * progress, 6, GOLD, radius=3)
            elif entity.player == self.human:
                lines.append(entity.info.summary)
            if entity.type is BuildingType.TOWN_HALL and entity.player == self.human:
                lines.append("Rally point set" if entity.rally is not None else "Right-click the map to set a rally point")
        ly = y + 50
        for line in lines[:2]:
            self.draw_text(line, tx, ly, style="body")
            ly += 22

    # -- Save / load ------------------------------------------------------------------------

    def get_save_state(self) -> dict:
        return {"version": SAVE_VERSION, "seed": self.seed, "difficulty": self.difficulty.value, "world": self.world.to_dict(), "stats": self.stats,
                "groups": self.groups, "tutorial": self.tutorial.step if self.tutorial is not None else None}

    def get_save_summary(self) -> dict:
        world = self.world
        size = next((name for name, (w, h) in mapgen.SIZES.items() if (w, h) == (world.width, world.height)), f"{world.width}×{world.height}")
        return {"map": f"{size} {world.theme.value}", "players": len(world.players), "difficulty": self.difficulty.value, "clock": _clock(world.time),
                "player": self.player.name}

    def load_save_state(self, state: dict) -> None:
        world = check_save(state)
        if (world.width, world.height) != (self.world.width, self.world.height):
            self.game.clear_and_push(load_game(state, settings=self.settings))
            return
        self.world = world
        self.seed = state["seed"]
        self.difficulty = Difficulty(state["difficulty"])
        self.brains = [Brain(p.id, self.difficulty) for p in world.players if not p.human]
        self.stats = {**self.stats, **state.get("stats", {})}
        self.groups = {k: list(v) for k, v in state.get("groups", {}).items()}
        self.tutorial = Tutorial() if state.get("tutorial") is not None and self.settings["tutorial"] else None
        if self.tutorial is not None:
            self.tutorial.step = state["tutorial"]
        self._autosave_at = (world.time // AUTOSAVE_EVERY + 1) * AUTOSAVE_EVERY
        self.effects.clear()
        self.selection = []
        self.pending = None
        self.build_menu = False
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


class PauseScene(_Overlay):
    pause_below = True
    controls = {"n": "new_game", "q": "quit", "f5": "save", "f9": "load", "s": "settings", "t": "back_to_title", "f1": "help"}

    def __init__(self, game_scene: GameScene) -> None:
        self.game_scene = game_scene

    def on_enter(self) -> None:
        panel = self.panel("Paused")
        panel.add(Button("Resume", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=260))
        panel.add(Button("Save game…", hotkey="F5", on_click=self.save, style=GHOST_BUTTON, width=260))
        panel.add(Button("Load game…", hotkey="F9", on_click=self.load, style=GHOST_BUTTON, width=260))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=260))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=260))
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

    def new_game(self) -> None:
        scene = self.game_scene
        self.game.clear_and_push(new_game(scene.seed + 1, width=scene.world.width, height=scene.world.height, players=len(scene.world.players),
                                          difficulty=scene.difficulty, theme=scene.world.theme, settings=scene.settings))

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
    "Mine gold and chop lumber with peasants, build farms for supply and a barracks for soldiers,",
    "then raze every enemy building and hunt down what is left.",
)
HELP_KEYS = (
    ("Left click / drag", "select a unit, a building, or every unit in the box"),
    ("Right click", "move, harvest, attack or resume building — the sensible thing for the target"),
    ("Shift", "add to the selection, or queue an order after the current one"),
    ("Double-click / Ctrl-click", "select every unit of that type on screen;  Ctrl+A: the whole army"),
    ("A / P", "attack-move: fight everything on the way / patrol between two spots"),
    ("S / H", "stop / hold position"),
    ("B", "build (peasants): F farm, B barracks, H town hall, T tower"),
    ("P / F / A / K", "train peasant / footman / archer / knight in the selected building"),
    ("Ctrl+1-9 / 1-9", "assign / recall a control group"),
    ("Tab / .", "next idle peasant / soldier"),
    ("Space", "jump to the last alert;  Ctrl+F6-F8 / F6-F8: set / return to a camera bookmark"),
    ("Arrows / edges / middle-drag", "scroll the map;  wheel / + / −  zoom"),
    ("Minimap", "left-click to look, right-click to send the selection there"),
    ("F3 / F5 / F9", "pause / save / load"),
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


CODEX_PAGES = ("Units", "Buildings", "Upgrades")


class CodexScene(_Overlay):
    """Every unit, building and upgrade with its numbers; 1/2/3 or Tab switch pages."""

    pause_below = True
    controls = {"1": "page_units", "2": "page_buildings", "3": "page_upgrades", "tab": "next_page", "f2": "close"}

    def __init__(self, world: World, player: int, page: int = 0) -> None:
        self.world = world
        self.player = player
        self.page = page

    def on_enter(self) -> None:
        panel = self.panel("Codex")
        tabs = Row(spacing=8)
        for i, name in enumerate(CODEX_PAGES):
            tabs.add(Button(name, hotkey=str(i + 1), on_click=lambda i=i: self.show(i), style=ACTION_BUTTON if i == self.page else GHOST_BUTTON, width=150))
        panel.add(tabs)
        table = Column(spacing=3)
        for cells in self._rows():
            table.add(Row(*[Label(text, text_style="hud" if i == 0 else "body", width=width, text_color=GOLD if i == 0 else None)
                            for i, (text, width) in enumerate(cells)], spacing=10))
        panel.add(table)
        panel.add(KeyHints([("1 2 3", "page"), ("Tab", "next"), ("Esc", "close")]))

    def _rows(self) -> list[list[tuple[str, int]]]:
        have = self.world.players[self.player].upgrades
        if self.page == 0:
            rows = [[("Unit", 110), ("Cost", 150), ("HP", 50), ("Dmg", 50), ("Arm", 50), ("Rng", 50), ("Spd", 50), ("Trained at", 120), ("Role", 330)]]
            for unit_type, info in UNITS.items():
                rows.append([(info.name, 110), (str(info.cost), 150), (str(info.hp), 50), (str(info.damage) if info.damage else f"heal {info.heal}", 50),
                             (str(info.armor), 50), ("melee" if info.range < 1 else f"{info.range:g}", 50), (f"{info.speed:g}", 50),
                             (BUILDINGS[info.trained_at].name, 120), (info.summary, 330)])
            return rows
        if self.page == 1:
            rows = [[("Building", 120), ("Cost", 150), ("HP", 50), ("Size", 50), ("Time", 50), ("Requires", 110), ("What it does", 430)]]
            for building_type, info in BUILDINGS.items():
                if building_type is BuildingType.GOLD_MINE:
                    continue
                rows.append([(info.name, 120), (str(info.cost), 150), (str(info.hp), 50), (f"{info.size}×{info.size}", 50), (f"{info.build_time:g}s", 50),
                             (BUILDINGS[info.requires].name if info.requires else "—", 110), (info.summary + (f" · supply +{info.supply}" if info.supply else ""), 430)])
            return rows
        rows = [[("Upgrade", 160), ("Cost", 150), ("Time", 50), ("Where", 110), ("Requires", 150), ("Effect", 320)]]
        for upgrade, info in UPGRADES.items():
            where = next(b for b, binfo in BUILDINGS.items() if upgrade in binfo.researches)
            rows.append([(info.name + (" ✓" if upgrade in have else ""), 160), (str(info.cost), 150), (f"{info.time:g}s", 50), (BUILDINGS[where].name, 110),
                         (UPGRADES[info.requires].name if info.requires else "—", 150), (info.summary, 320)])
        return rows

    def show(self, page: int) -> None:
        self.game.replace(CodexScene(self.world, self.player, page))

    def page_units(self) -> None:
        self.show(0)

    def page_buildings(self) -> None:
        self.show(1)

    def page_upgrades(self) -> None:
        self.show(2)

    def next_page(self) -> None:
        self.show((self.page + 1) % len(CODEX_PAGES))

    def close(self) -> None:
        self.game.pop()


class GameOverScene(_Overlay):
    pause_below = True
    pop_on_cancel = False
    controls = {"n": "new_game", "q": "quit", ("t", "escape"): "back_to_title"}

    def __init__(self, game_scene: GameScene, won: bool) -> None:
        self.game_scene = game_scene
        self.won = won

    def on_enter(self) -> None:
        scene = self.game_scene
        world = scene.world
        winner = world.players[world.winner].name if world.winner is not None else "Nobody yet"
        panel = self.panel("Victory!" if self.won else f"Defeat — {winner} prevails")
        stats = scene.stats
        panel.add(Label(f"{_clock(world.time)} played · {stats['units_killed']} kills · {stats['units_lost']} units lost · "
                        f"{stats['buildings_razed']} buildings razed · {stats['buildings_lost']} lost", text_style="body"))
        panel.add(Button("New game", hotkey="N", on_click=self.new_game, style=ACTION_BUTTON, width=260))
        panel.add(Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=260))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=260))

    def new_game(self) -> None:
        scene = self.game_scene
        self.game.clear_and_push(new_game(scene.seed + 1, width=scene.world.width, height=scene.world.height, players=len(scene.world.players),
                                          difficulty=scene.difficulty, theme=scene.world.theme, settings=scene.settings))

    def back_to_title(self) -> None:
        from warband.title import TitleScene

        self.game.clear_and_push(TitleScene(settings=self.game_scene.settings))

    def quit(self) -> None:
        self.game.quit()


def new_game(seed: int, width: int = 48, height: int = 40, players: int = 2, *, difficulty: Difficulty = Difficulty.NORMAL,
             theme: MapTheme = MapTheme.SUMMER, settings: dict[str, Any] | None = None) -> GameScene:
    return GameScene(mapgen.generate(seed=seed, width=width, height=height, players=players, theme=theme), seed, difficulty=difficulty, settings=settings)


def check_save(state: dict[str, Any]) -> World:
    """The world in a save's ``state``, or a SaveError saying what is wrong with it."""
    if not isinstance(state, dict) or state.get("version") != SAVE_VERSION:
        raise SaveError(f"this save is from another version of Warband (format {state.get('version') if isinstance(state, dict) else '?'}, expected {SAVE_VERSION})")
    try:
        world = World.from_dict(state["world"])
        Difficulty(state["difficulty"])
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise SaveError(f"the save file is damaged ({type(exc).__name__}: {exc})") from exc
    if not any(p.human for p in world.players):
        raise SaveError("the save has no human player")
    return world


def load_game(state: dict[str, Any], *, settings: dict[str, Any] | None = None) -> GameScene:
    """A game scene from a save slot's ``state`` (see :meth:`GameScene.get_save_state`)."""
    world = check_save(state)
    scene = GameScene(world, state["seed"], difficulty=Difficulty(state["difficulty"]), settings=settings, stats=state.get("stats"))
    scene.groups = {k: list(v) for k, v in state.get("groups", {}).items()}
    if state.get("tutorial") is not None and scene.tutorial is not None:
        scene.tutorial.step = state["tutorial"]
    scene._autosave_at = (world.time // AUTOSAVE_EVERY + 1) * AUTOSAVE_EVERY
    return scene
