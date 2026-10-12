"""Watching matches instead of playing them: a local AI-only observer, and the seam a network one reuses.

A watched match runs every seat by computer while the viewer looks on: the
whole map is shown, the viewed seat is inspection context only (its stores and
forces are shown, never commanded), and leaving costs nothing because nothing
is rated.  :class:`WatchScene` holds every read-only behaviour behind one
seam; :class:`ObserverScene` adds the live world and its brains, while a
future network observer reuses the seam and only feeds the world another way
(snapshots at fixed 1x authoritative time).
"""

from __future__ import annotations

import math
from typing import Any

from saga2d import Anchor, Button, Label, Row
from saga2d import Scene
from saga2d.effects import Burst, Toast
from warband.audio import wreckage
from warband.online.authority import PRIVATE_EVENTS
from warband.brains.ai import make_brain
from warband.sim import mapgen
from warband.sim.model import RuleError, Unit, World
from warband.sim.races import RACES
from warband.sim.rules import SIM_DT, BUILDINGS, BuildingType, Difficulty, MapTheme, Race
from warband.sim.rules import Layout as MapLayout
from warband.ui.scene import (
    SELECT_GAP,
    GameScene,
    PauseScene,
    _clock,
    _Overlay,
    fair_map,
)
from warband.ui.style import ACTION_BUTTON, GHOST_BUTTON, GOLD, GOOD, MUTED, PANEL_STYLE
from warband.ui.view import MapView, to_tiles, to_world

#: The paces a local AI-only match may be watched at, as multiples of real
#: time.  Human-played matches stay at 1x: nothing here touches their clock.
OBSERVER_SPEEDS: tuple[float, ...] = (1.0, 1.2, 1.5, 2.0, 3.0)

NO_ORDERS = "Observers give no orders — every seat plays itself"


class _NoAdjutant:
    """The watcher's adjutant: no commands, no standing parties, no news.

    :meth:`GameScene.update` asks it every frame, and :meth:`GameScene.draw`
    reads its tags, so the seam keeps the calls and empties the answers
    instead of scattering ``if observing`` through the scene.
    """

    @property
    def tags(self) -> dict[int, str]:
        return {}

    def think(self, world: World) -> list[str]:
        return []

    def release(self, unit_ids: object) -> None:
        return None


class WatchScene(GameScene):
    """A match watched read-only: the whole map, one viewed seat, no orders.

    The viewed seat (:attr:`viewed`, mirrored in :attr:`human` so the HUD,
    the view and the sounds follow it) is inspection context only — the core
    choice is observer versus playing authority, and a watcher is never the
    latter.  Orders, catalogues, aims, cancel mode, plans, saves, resigning
    and the rated-leave paths are refused or hidden; the match ends only at a
    winner, whatever happens to the viewed seat.  Nothing is recorded,
    rated or autosaved.
    """

    controls = {**{key: method for key, method in GameScene.controls.items()
                if method not in ("quick_save", "quick_load", "hide_tutorial")},
                "[": "watch_prev", "]": "watch_next"}

    def __init__(self, world: World, seed: int, *, viewed: int = 0,
                 difficulty: Difficulty = Difficulty.MEDIUM,
                 settings: dict[str, Any] | None = None) -> None:
        """*viewed* is the seat watched first; every seat stays computer-led.

        The world needs no human seat (and gains none): ``player=viewed``
        only points the inherited machinery at the inspected side.
        """
        super().__init__(world, seed, difficulty=difficulty, settings=settings,
                         player=viewed, ranked=False)
        self.viewed = viewed
        self.adjutant: Any = _NoAdjutant()
        self.tutorial = None
        self._autosave_at = math.inf

    # -- What the watcher sees -------------------------------------------------

    def _make_view(self) -> MapView:
        return MapView(self, self.world, self.human, reveal=True)

    def _visible(self, point: tuple[float, float]) -> bool:
        """The whole map is known: effects and toasts never consult the fog."""
        return True

    def _audible(self, point: tuple[float, float]) -> bool:
        """Encounters are heard across every seat, near the camera."""
        return self._on_screen(point)

    def _sees_spell(self, e: Any) -> bool:
        """Every cast lands in sight: the watcher's map has no fog."""
        return True

    def _show_destroyed(self, e: Any) -> None:
        """A loss named for its owner, in its owner's words, never the watcher's."""
        destroyed = BuildingType(e.text)
        players = self.world.players
        owner = players[e.player] if e.player is not None and e.player < len(players) else None
        if owner is None:
            # Nobody's buildings (mines, lairs) stand outside the catalogue.
            known = BUILDINGS[destroyed].name if destroyed in BUILDINGS else destroyed.value.replace("_", " ")
            line = f"The {known.lower()} was destroyed"
        else:
            names = RACES[owner.race].buildings
            kind = names[destroyed].name if destroyed in names else self.building_name(destroyed)
            line = f"{owner.name}'s {kind.lower()} was destroyed"
        self.effects.add(Toast("Building lost", [line], hold=4.0, top=self.toast_top))
        wx, wy = to_world(e.pos)
        self.effects.add(Burst((wx, wy), (255, 160, 80, 255), 18, rng=self.fx_rng, size=16, speed=(40, 160)))
        self.effects.add(Burst((wx, wy - 10), (60, 60, 64, 255), 14, rng=self.fx_rng, image="smoke", size=28, speed=(10, 50)))
        self.camera.shake(4, 0.3)
        # Nobody's buildings have no wreckage material; their losses still burst, silently.
        if self._audible(e.pos) and destroyed in wreckage.BUILDING_MATERIALS:
            self.sfx(wreckage.cue(wreckage.material(destroyed)), gap=0.3)

    def watch_seat(self, seat: int) -> None:
        """Inspect *seat* instead: its stores, forces and codex lead the HUD.

        The camera stays where it was; only the inspection context moves, and
        an eliminated seat stays watchable while its side's fate is decided.
        """
        if not 0 <= seat < self.world.seats or seat == self.viewed:
            return
        self.human = seat
        self.viewed = seat
        self.view.player = seat
        self.select([], quiet=True)
        self._refresh_side_identity()
        self.say(f"Watching {self.player.name}")

    def watch_prev(self) -> None:
        self.watch_seat((self.viewed - 1) % self.world.seats)

    def watch_next(self) -> None:
        self.watch_seat((self.viewed + 1) % self.world.seats)

    # -- Selection inspects every side ------------------------------------------

    def select(self, ids: list[int], *, add: bool = False, toggle: bool = False, quiet: bool = False) -> None:
        """Select anything on the map: sides are never filtered out."""
        alive = [i for i in ids if self.world.entity(i) is not None]
        if add or toggle:
            merged = list(self.selection)
            for i in alive:
                if i not in merged:
                    merged.append(i)
                elif toggle:
                    merged.remove(i)
            alive = merged
        if len(alive) > 1:
            units = [i for i in alive if isinstance(self.world.entity(i), Unit)]
            alive = units or alive[-1:]
        self.selection = alive
        self._portrait_page = 0
        self.pending = None
        self.catalogue = None
        self._refresh_card()
        if alive and not quiet:
            self.sfx("select", gap=SELECT_GAP)

    def click_select(self, point: tuple[float, float], shift: bool, ctrl: bool = False) -> None:
        entity = self.view.entity_at(point)
        if entity is None:
            if not shift:
                self.select([])
            return
        last_time, last_id = self._last_click
        double = last_id == entity.id and self.clock - last_time < 0.4
        self._last_click = (self.clock, entity.id)
        if (double or ctrl) and isinstance(entity, Unit):
            self.select_same_type(entity, add=shift)
        elif shift:
            self.select([entity.id], toggle=True)
        else:
            self.select([entity.id])

    def box_select(self, a: tuple[float, float], b: tuple[float, float], shift: bool) -> None:
        found: list[int] = []
        for seat in range(self.world.seats):
            found.extend(u.id for u in self.view.units_in_rect(a, b, player=seat))
        if found:
            self.select(found, add=shift)
        elif not shift:
            self.select([])

    def select_same_type(self, unit: Unit, *, add: bool = False) -> None:
        """Every unit of *unit*'s type on screen, of any seat."""
        left, top, right, bottom = self.camera.visible_world_rect()
        same = [u.id for seat in range(self.world.seats)
                for u in self.view.units_in_rect(to_tiles(left, top), to_tiles(right, bottom), player=seat)
                if u.type is unit.type]
        self.select(same, add=add)

    def command_smart(self, point: tuple[float, float], *, queue: bool = False) -> None:
        """The right button selects too: there is nothing to command."""
        self.click_select(point, shift=queue)

    def _click_panel(self, x: float, y: float, button: str, *, shift: bool) -> bool:
        """Portraits select and producers centre; queued work is never cancelled."""
        if button == "left":
            for entity_id, (px, py, size, _) in self._portraits:
                if px <= x < px + size and py <= y < py + size:
                    self.select([entity_id], toggle=shift)
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
                self.warn(NO_ORDERS)
            elif button == "left" and entry.goto is not None:
                entry.goto()
            return True
        return False

    # -- Nothing the watcher touches reaches the world ---------------------------

    def _handle_events(self, events: list) -> None:
        """A viewed seat's private affairs are never the watcher's: refusals, alarms and the rest
        of :data:`PRIVATE_EVENTS` stay off the status line and out of the effects, exactly as the
        network snapshot withholds them.  Everything public — blows, casts, losses, concessions —
        presents as before, and the world's own event stream is untouched."""
        super()._handle_events([e for e in events if e.kind not in PRIVATE_EVENTS])

    def order(self, action: object, *args: object, **kwargs: object) -> None:
        raise RuleError(NO_ORDERS)

    def attempt(self, action: str, *args: object, **kwargs: object) -> bool:
        self.warn(NO_ORDERS)
        return False

    def _on_behalf(self, action: str, *args: object, **kwargs: object) -> bool | None:
        return False

    def command(self, name: str, *, strength: int | None = None) -> None:
        self.warn(NO_ORDERS)

    def toggle_catalogue(self, kind: str) -> None:
        self.warn(NO_ORDERS)

    def open_catalogue(self, kind: str | None) -> None:
        if kind is not None:
            self.warn(NO_ORDERS)

    def aim_spell(self, spell: object) -> None:
        self.warn(NO_ORDERS)

    def aim_level(self, level: int) -> None:
        self.warn(NO_ORDERS)

    def start_pending(self, mode: str) -> None:
        self.warn(NO_ORDERS)

    def toggle_cancel_mode(self) -> None:
        self.warn(NO_ORDERS)

    def cancel_at(self, point: tuple[float, float]) -> None:
        self.warn(NO_ORDERS)

    def cancel_in_box(self, a: object, b: object) -> None:
        self.warn(NO_ORDERS)

    def open_plans(self) -> None:
        self.warn(NO_ORDERS)

    def repeat_last(self) -> None:
        self.warn(NO_ORDERS)

    def save_to(self, slot: int | str) -> None:
        self.warn("Observers keep no saves")

    def load_from(self, slot: int | str) -> None:
        self.warn("Observers keep no saves")

    def resign(self, where: object) -> None:
        """A watcher never concedes: leaving is free (see :meth:`leaving`)."""
        self.warn("Observers don't resign — leave freely from the menu")

    def leaving(self) -> None:
        return None

    def conclude(self, outcome: str, where: object | None = None) -> None:
        return None

    # -- The match ends only at a winner ------------------------------------------

    def _motion_fraction(self) -> float:
        if self._game_over or self.world.winner is not None:
            return 1.0
        return self._acc / SIM_DT

    def _check_game_over(self) -> None:
        if self._game_over or self.world.winner is None:
            return
        self._game_over = True
        self.game.push(ObserverEndScene(self))

    def on_background(self) -> None:
        if (self.auto_pause_on_background and not self.paused and not self._auto_paused
                and not self._game_over and self.world.winner is None):
            self._auto_paused = True
            self.paused = True

    def pause_menu(self) -> Scene:
        return ObserverPauseScene(self)

    # -- What the watcher is told ----------------------------------------------------

    def hint(self) -> list[tuple[str, str]]:
        """Inspect, look around, switch seats, leave: never order.

        No pace or pause here: a snapshot-fed watcher reuses this seam and
        must not advertise the local match's clock.
        """
        return [("Drag / Right click", "select any side"), ("[ / ]", "watch a seat"),
                ("F10", "menu"), ("F1", "help")]

    def _empty_selection_note(self) -> str:
        return "Drag to select any side's units · clicks only inspect"

    def _queue_footer_note(self) -> str:
        return "Hover for details · click to go there"

    # -- The HUD watches: no order controls ----------------------------------------

    def _commands(self) -> list:
        """No card: inspection needs no buttons."""
        return []

    def _fill_settlement_row(self) -> None:
        super()._fill_settlement_row()
        assert self.settlement_row is not None
        self.settlement_row.clear()
        self.settlement_row.visible = False

    def _fill_command_row(self) -> None:
        super()._fill_command_row()
        self.command_row.clear()
        self.command_row.visible = False

    def _fill_spell_bar(self) -> None:
        super()._fill_spell_bar()
        self.spell_bar.clear()
        self.spell_bar.visible = False

    def _update_card(self) -> None:
        """Tooltips for the stores; the card and its buttons are gone."""
        mx, my = self.mouse
        hovered = next((hint for row, hint in self._resource_rows if row.hit_test(mx, my)), None)
        self.tooltip = hovered() if hovered is not None else ""

    def _build_hud(self) -> None:
        super()._build_hud()
        assert self.settlement_row is not None
        self.settlement_row.visible = False
        self.command_row.visible = False
        self.spell_bar.visible = False
        # Top-right, above the status line's row: the settlement and command rows are hidden,
        # so nothing else lives in this corner while watching.
        strip = Row(spacing=8, anchor=Anchor.TOP_RIGHT, margin=(12, 12),
                    style=PANEL_STYLE, blocks_pointer=True)
        strip.add(Button("<", on_click=self.watch_prev, style=GHOST_BUTTON, width=40))
        strip.add(Label(lambda: f"Watching {self.player.name}", text_style="sub", width=150, wrap=True))
        strip.add(Button(">", on_click=self.watch_next, style=GHOST_BUTTON, width=40))
        self._fill_pace(strip)
        self.ui.add(strip)

    def _fill_pace(self, strip: Row) -> None:
        """The pace controls beside the seat switcher; a snapshot-fed watcher shows its own."""


class ObserverScene(WatchScene):
    """A local AI-only match: every seat computer-led, watched at several paces.

    One real brain per playing seat; the pace scales the fixed-step
    accumulator only — the step, the rules and the brains never hear of it —
    so fractional paces keep time exactly across frames.
    """

    controls = {**WatchScene.controls, "pageup": "faster", "pagedown": "slower"}

    def __init__(self, world: World, seed: int, *, viewed: int = 0,
                 difficulty: Difficulty = Difficulty.MEDIUM,
                 settings: dict[str, Any] | None = None) -> None:
        super().__init__(world, seed, viewed=viewed, difficulty=difficulty, settings=settings)
        self.brains = [make_brain(p.id, difficulty, seed) for p in world.players[:world.seats]]
        self.speed_index = 0
        self.speed = OBSERVER_SPEEDS[0]

    @property
    def pace(self) -> float:
        """The multiple of real time the match is watched at."""
        return OBSERVER_SPEEDS[self.speed_index]

    def hint(self) -> list[tuple[str, str]]:
        return [("PageUp / PageDown", "pace"), ("F3", "pause")] + super().hint()

    def _fill_pace(self, strip: Row) -> None:
        strip.add(Label(lambda: f"×{self.pace:g}", text_style="hud", width=52))
        strip.add(Button("-", on_click=self.slower, style=GHOST_BUTTON, width=40))
        strip.add(Button("+", on_click=self.faster, style=GHOST_BUTTON, width=40))

    def faster(self) -> None:
        self.speed_index = min(self.speed_index + 1, len(OBSERVER_SPEEDS) - 1)
        self.speed = OBSERVER_SPEEDS[self.speed_index]
        self.say(f"{self.pace:g}× pace")

    def slower(self) -> None:
        self.speed_index = max(self.speed_index - 1, 0)
        self.speed = OBSERVER_SPEEDS[self.speed_index]
        self.say(f"{self.pace:g}× pace")

    def _steps_running(self) -> bool:
        """Steps keep coming whatever became of the viewed seat; only a winner stops them."""
        return not self.paused and not self._game_over and self.world.winner is None


class ObserverPauseScene(PauseScene):
    """Paused while watching: settings and help, never saves or resigning."""

    controls = {key: method for key, method in PauseScene.controls.items()
                if method not in ("save", "load", "resign")}

    def on_enter(self) -> None:
        from warband.ui.version import running_build

        panel = self.panel("Paused — observing")
        panel.add(Button("Resume", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=260))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=260))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=260))
        panel.add(Button("Watch again", hotkey="N", on_click=self.new_game, style=GHOST_BUTTON, width=260))
        panel.add(Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=260))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=260))
        panel.add(Label(f"Warband {running_build()}", text_style="caption"))

    def new_game(self) -> None:
        self.game.clear_and_push(next_observer(self.game_scene))


class ObserverEndScene(_Overlay):
    """The watched result: who won, and every side's fate.  Unrated."""

    pause_below = True
    pop_on_cancel = False
    controls = {"n": "watch_again", "q": "quit", ("t", "escape"): "back_to_title"}

    def __init__(self, scene: WatchScene) -> None:
        self.watch_scene = scene

    def on_enter(self) -> None:
        scene = self.watch_scene
        world = scene.world
        winner = world.players[world.winner] if world.winner is not None else None
        title = f"{winner.name} wins" if winner is not None else "No winner"
        panel = self.panel(title)
        panel.add(Label(f"{RACES[winner.race].name if winner is not None else '—'} · "
                        f"{scene.difficulty.value.title()} AI · {world.width}×{world.height} · "
                        f"{world.seats} players · {world.theme.value.title()} · Seed {scene.seed} · {_clock(world.time)}",
                        text_style="body"))
        for player in world.players[:world.seats]:
            status = ("Won" if world.winner == player.id else "Surrendered" if player.surrendered
                      else "Standing" if player.alive else "Eliminated")
            colour = GOOD if player.id == world.winner else MUTED
            panel.add(Row(Label(f"{player.name} · {RACES[player.race].name}", text_style="body", width=280),
                          Label(status, text_style="body", text_color=colour), spacing=10))
        panel.add(Label("Unrated — watching keeps no record, rating or high score.", text_style="body", text_color=GOLD))
        panel.add(Row(Button("Watch again", hotkey="N", on_click=self.watch_again, style=ACTION_BUTTON, width=210),
                      Button("Back to title", hotkey="T", on_click=self.back_to_title, style=GHOST_BUTTON, width=210),
                      Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=190), spacing=12))

    def watch_again(self) -> None:
        self.game.clear_and_push(next_observer(self.watch_scene))

    def back_to_title(self) -> None:
        from warband.ui.title import TitleScene

        scene = self.watch_scene
        size = mapgen.size_name(scene.world.width, scene.world.height, scene.world.seats)
        size = size if size in mapgen.SIZES else (mapgen.sizes_for(scene.world.seats) or ("Medium",))[0]
        self.game.clear_and_push(TitleScene(size=size, players=scene.world.seats, difficulty=scene.difficulty,
                                            theme=scene.world.theme, race=scene.player.race,
                                            layout=scene.world.layout, settings=scene.settings))

    def quit(self) -> None:
        self.game.quit()


def observe_game(seed: int, width: int = 48, height: int = 40, players: int = 2,
                 *, difficulty: Difficulty = Difficulty.MEDIUM, theme: MapTheme = MapTheme.SUMMER,
                 settings: dict[str, Any] | None = None, races: list[Race | None] | None = None,
                 layout: MapLayout | None = None, magic: bool = False, wilds: bool = True) -> ObserverScene:
    """A local AI-only match nobody plays: every seat computer-led, seat 0 watched first.

    *layout* ``None`` draws one from the seed.  The world is built with no
    human seat, and gains none: the watcher is not a player.
    """
    return ObserverScene(mapgen.generate(seed, width, height, players, human=None, theme=theme,
                                         races=races, layout=layout, magic=magic, wilds=wilds),
                         seed, difficulty=difficulty, settings=settings)


def next_observer(scene: WatchScene) -> ObserverScene:
    """Another watched match with *scene*'s settings and races, on the next fair seed."""
    world = scene.world
    seed, fresh = fair_map(scene.seed + 1, world.width, world.height, world.seats, theme=world.theme,
                           races=[p.race for p in world.players[:world.seats]], layout=world.layout,
                           magic=world.magic, wilds=world.wilds)
    # fair_map builds played matches (seat 0 leads); watching keeps every seat computer-led.
    for player in fresh.players[:fresh.seats]:
        player.human = False
    return ObserverScene(fresh, seed, difficulty=scene.difficulty, settings=scene.settings)
