"""A campaign mission as a match: the mission's objectives on the HUD, its triggers and dialogues, and its own ending.

:func:`build_world` draws the mission's map and lets the mission reshape it; :class:`MissionScene` plays it and asks
the :class:`~warband.story.campaign.Run` what to show after every frame; :class:`MissionResultScene` closes it, records
the progress and plays the debrief.  A mission's saves (the ``campaign`` slot autosaves, the numbered slots too)
carry the run beside the world and come back through :func:`~warband.ui.scene.load_game` like any save, which hands
them to :func:`load_mission`.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

from saga2d import Anchor, Button, Column, Component, KeyHints, Label, Row, SaveError, Scene, Style
from saga2d.effects import Banner, Toast
from warband.sim import mapgen
from warband.brains.ai import make_brain
from warband.ui.match import LocalMatch
from warband.ui.match_record import check_save, saved_run_id
from warband.story.campaign import LEGACY_CAMPAIGN_ID, Campaign, Mission, Progress, ProgressStore, Run, Speaker, shifted
from warband.story.dialog import DialogScene, speaker_portrait
from warband.story.journal import JournalScene
from warband.story.landmarks import LandmarkView
from warband.sim.model import Event, Unit, World
from warband.art import textures
from warband.art.production import fit
from warband.sim.rules import BuildingType, Difficulty
from warband.ui.scene import CARD_GAP, CARD_PANEL_WIDTH, HINT_BAR, HUD_TOP, OBJECTIVES_GAP, PANEL_MARGIN, GameScene, HelpScene, PauseScene, _clock, _Overlay
from warband.ui.style import ACTION_BUTTON, BAD, GHOST_BUTTON, GOLD, GOOD, MUTED, PANEL_STYLE, RESULTS_STYLE, TEXT
from warband.ui.view import Sighting, rgba, to_world

CAMPAIGN_SLOT = "campaign"
NOTICE_HOLD = 4.0
MARK = 18
MARK_COLORS = {"open": (255, 255, 255, 40), "done": GOOD, "failed": BAD}
TEXT_COLORS = {"open": TEXT, "done": MUTED, "failed": BAD}


def campaign_save_slot(campaign: Campaign) -> str:
    """Thornwood keeps its original save slot; every other story autosaves independently."""
    return CAMPAIGN_SLOT if campaign.id == LEGACY_CAMPAIGN_ID else f"campaign_{campaign.id}"


def name_sides(world: World, mission: Mission) -> None:
    for player, side in zip(world.players, mission.sides):
        player.name = side.name


def build_world(mission: Mission, *, flags: dict[str, Any]) -> Run:
    """The generated map reshaped by setup, or the authored World setup installs in the run."""
    width, height = mapgen.SIZES[mission.size]
    world = mapgen.generate(mission.seed, width, height, len(mission.sides), theme=mission.theme, races=[side.race for side in mission.sides],
                           layout=mission.layout)
    world.scripted = True
    name_sides(world, mission)
    run = Run(mission, world, flags=flags)
    mission.setup(run)
    world = run.world
    world.scripted = True
    name_sides(world, mission)
    # A mission raises what it needs where it needs it: a rift one of its buildings now stands on (a tower of the
    # Court of Thorns) is the mission's ground, not a rift nobody can ever tap.
    world.lay_rifts(rift for rift in world.rifts
                    if not any(world.rift_at(tile) == rift and not (b.type is BuildingType.VAULT and b.pos == rift)
                               for b in world.buildings.values() for tile in b.tiles()))
    world.update_vision()
    world.take_events()
    return run


def current_progress(game, campaign: Campaign, difficulty: Difficulty) -> Progress:
    """The saved progress, or a fresh one when a mission was started on its own (``--mission``)."""
    progress = ProgressStore(game.data_dir, campaign.id).load()
    return progress if progress is not None else Progress(campaign.id, difficulty)


def restart_mission(game, scene: MissionScene) -> str | None:
    """Play *scene*'s mission again from its start, with the choices the campaign's progress holds; the reason it cannot
    when that progress cannot be read.  The campaign screen says why in full and offers to set the file aside."""
    try:
        progress = current_progress(game, scene.campaign, scene.record.difficulty)
    except SaveError:
        return "Cannot restart: the campaign progress is unreadable. Campaign says why."
    game.save_manager.delete(scene.AUTOSAVE_SLOT)
    start_mission(game, scene.campaign, scene.mission, progress, scene.settings, briefing=False)
    return None


def start_mission(game, campaign: Campaign, mission: Mission, progress: Progress, settings, *, briefing: bool = True) -> None:
    """Brief over the actual battlefield, paused, then give the player the same company and camera."""
    if progress.campaign != campaign.id or mission not in campaign.missions:
        raise ValueError("mission and progress must belong to the selected campaign")
    run = build_world(mission, flags=progress.flags)
    scene = MissionScene(campaign, run, difficulty=progress.difficulty, settings=settings)
    game.clear_and_push(scene)
    if briefing:
        game.push(DialogScene(mission.briefing, campaign.speakers, run.vars, record=True,
                              heading=f"CHAPTER {campaign.index(mission):02} / {mission.title}", end_label="Take command"))


class _Notice(Toast):
    """A toast that keeps under the objectives panel however the panel grows after it was raised."""

    def draw_below(self, scene: Scene, below: float) -> float:  # the effects layer draws toasts through this, stacked
        self.top = scene.toast_top
        return super().draw_below(scene, below)

    def height(self, scene: Scene) -> int:
        """Toast's title, padding and unwrapped lines, used to reserve space before it draws."""
        heading, body = (scene.game.theme.get_text_style(style) for style in ("heading", "body"))
        return 2 * self.PAD + heading.font_size + 10 + (body.font_size + 8) * len(self.lines)


class _Mark(Component):
    """A small square before an objective: hollow while open, a tick when done, a cross when failed."""

    def __init__(self) -> None:
        super().__init__(width=MARK, height=MARK)
        self.state = "open"

    def on_draw(self) -> None:
        if self._game is None:
            return
        x, y, w, h = self.bounds
        backend = self._game.backend
        backend.draw_polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], MARK_COLORS[self.state], order=self._order)
        if self.state == "open":
            backend.draw_polygon([(x + 2, y + 2), (x + w - 2, y + 2), (x + w - 2, y + h - 2), (x + 2, y + h - 2)], (22, 20, 24, 255), order=self._order)
        elif self.state == "done":
            backend.draw_polygon([(x + .2 * w, y + .5 * h), (x + .32 * w, y + .38 * h), (x + .45 * w, y + .55 * h), (x + .72 * w, y + .22 * h),
                                  (x + .84 * w, y + .34 * h), (x + .45 * w, y + .8 * h)], (10, 30, 14, 255), order=self._order)
        else:
            backend.draw_polygon([(x + .25 * w, y + .35 * h), (x + .35 * w, y + .25 * h), (x + .75 * w, y + .65 * h), (x + .65 * w, y + .75 * h)],
                                 (40, 10, 10, 255), order=self._order)
            backend.draw_polygon([(x + .65 * w, y + .25 * h), (x + .75 * w, y + .35 * h), (x + .35 * w, y + .75 * h), (x + .25 * w, y + .65 * h)],
                                 (40, 10, 10, 255), order=self._order)


class MissionScene(GameScene):
    """The match with the mission's script on top.  Not ranked: the leaderboard is for skirmishes."""

    AUTOSAVE_SLOT = CAMPAIGN_SLOT
    controls = {**GameScene.controls, "f3": "focus_keeper", "j": "open_journal"}

    def __init__(self, campaign: Campaign, run: Run, *, difficulty: Difficulty, settings=None, run_id: str | None = None) -> None:
        execution = LocalMatch(run.world, run.mission.seed, difficulty=difficulty, player=run.human,
                               brains=[make_brain(side, shifted(level, difficulty), run.mission.seed)
                                       for side, level in run.ai.items() if run.world.players[side].alive])
        super().__init__(run.world, run.mission.seed, difficulty=difficulty, settings=settings, ranked=False, execution=execution, run_id=run_id)
        self.campaign = campaign
        self.AUTOSAVE_SLOT = campaign_save_slot(campaign)
        self.run = run
        self.mission = run.mission
        self.tutorial = None
        self.progress: Progress | None = None
        self.progress_error = ""
        self._rows: dict[str, tuple[Row, _Mark, Label]] = {}
        self._panel_state: dict[str, str] = {}
        self._notices: deque[tuple[str, list[str], tuple[int, int, int, int]]] = deque()  # one toast at a time, so none hides another
        self._notice: _Notice | None = None
        self._banner_until = -math.inf  # the mission's title has the screen to itself until then

    def on_enter(self) -> None:
        super().on_enter()
        self.landmarks = LandmarkView(self)
        banner = Banner(f"Mission {self.campaign.index(self.mission)}: {self.mission.title}", subtitle=self.mission.act,
                        accent=rgba(self.player.color), hold=2.0)
        self.effects.add(banner)
        # The band crosses the window at 40 % of its height, where a short window's objectives panel reaches: the
        # panel and the script's first notices wait for it to pass.
        self._banner_until = self.clock + banner.duration
        if self.world.time == 0 and self.mission.opening_focus is not None:
            self.select([unit.id for unit in self.run.soldiers(self.human)], quiet=True)
            self.camera.center_on(*to_world(self.mission.opening_focus))
        self._update_objectives()
        self._fold_objectives()

    def draw(self) -> None:
        super().draw()
        self.landmarks.draw()
        self._draw_keeper_labels()

    def _keeper_links(self) -> list[tuple[str, Speaker, Unit]]:
        """Resolve saved story links afresh: a rescued or loaded keeper can have a different living unit id."""
        return [(name, speaker, unit) for name, speaker in self.campaign.speakers.items()
                if (unit := self.run.unit(name.lower())) is not None
                and unit.player == self.human and unit.hp > 0 and not unit.hidden]

    def entity_name(self, entity: Unit | Sighting) -> str:
        return next((name for name, _, unit in self._keeper_links() if unit is entity), super().entity_name(entity))

    def _portrait(self, entity: Unit | Sighting, x: float, y: float, size: float) -> None:
        speaker = next((speaker for _, speaker, unit in self._keeper_links() if unit is entity), None)
        key = speaker_portrait(self.game, speaker) if speaker is not None else None
        if key is not None:
            self.draw_image(key, *fit(self.game, key, x, y, size))
        else:
            super()._portrait(entity, x, y, size)

    def focus_keeper(self) -> None:
        """F3 brings the current keeper into the clear and selects them; an unlinked legacy mission keeps Pause."""
        links = self._keeper_links()
        if not links:
            self.toggle_pause()
            return
        _, _, unit = links[0]
        self.open_catalogue(None)
        self.select([unit.id])
        x, y = to_world(self.view.unit_position(unit))
        sprite = self.view.unit_sprite(unit.id)
        if sprite is not None:
            y -= textures.placements[sprite.image].head / 2
        self.camera.center_on(x, y)

    def hint(self) -> list[tuple[str, str]]:
        links = self._keeper_links()
        return [(key, f"focus {links[0][0]}" if key == "F3" and links else text) for key, text in super().hint()]

    def open_help(self) -> None:
        self.game.push(HelpScene(self.scheme, magic=self.world.magic,
                                 f3_action="focus keeper" if self._keeper_links() else "pause", mission=True))

    def open_journal(self) -> None:
        """Read the briefing and witnessed choices without changing the current mission."""
        self.game.push(JournalScene(self.run, self.campaign.speakers))

    def cast_at(self, point: tuple[float, float]) -> None:
        """A successful campaign spell gives the company back its next order immediately."""
        super().cast_at(point)
        if self.aiming is None and self.catalogue == "spells":
            self.open_catalogue(None)

    def _draw_keeper_labels(self) -> None:
        if self.clock < self._banner_until:
            return
        for index, (name, _, unit) in enumerate(self._keeper_links()):
            sprite = self.view.unit_sprite(unit.id)
            if sprite is None or not sprite.visible or not self.world.is_visible(self.human, unit.tile):
                continue
            placement = textures.placements[sprite.image]
            top = sprite.y-placement.drop-placement.head-13/self.camera.zoom
            self.landmarks.draw_label(name + (" · F3" if index == 0 else ""), (sprite.x, top), color=GOLD[:3], above=True)

    def _handle_events(self, events: list[Event]) -> None:
        """The script announces departures and victories; an empty future wave is not a defeated faction."""
        super()._handle_events([event for event in events
                               if event.kind not in {"eliminated", "surrendered", "exposed"}
                               and not (event.kind == "resigned" and event.entity is None)])

    # -- Objectives panel ---------------------------------------------------------------

    def _build_objectives(self) -> Column:
        # Share the command card's right-hand column, clear of the selection panel even on a short window.
        width = CARD_PANEL_WIDTH - 2 * PANEL_STYLE.padding
        panel = Column(spacing=OBJECTIVES_GAP, anchor=Anchor.TOP_RIGHT, margin=(12, HUD_TOP), style=PANEL_STYLE, blocks_pointer=True)
        panel.add(Label(f"{self.campaign.index(self.mission)}. {self.mission.title}", text_style="heading", width=width))
        self.objectives_body = Column(spacing=6)
        self._rows = {}
        for objective in self.mission.objectives:
            mark, label = _Mark(), Label(objective.text, text_style="body", width=width - MARK - 8, wrap=True)
            row = Row(mark, label, spacing=8)
            self._rows[objective.id] = (row, mark, label)
            self.objectives_body.add(row)
        panel.add(self.objectives_body)
        self._panel_state = {}
        return panel

    def _update_objectives(self) -> None:
        if self.run.state == self._panel_state:
            return
        self._panel_state = dict(self.run.state)
        for objective in self.mission.objectives:
            row, mark, label = self._rows[objective.id]
            state = self.run.state[objective.id]
            row.visible = state != "hidden"
            if state != "hidden":
                mark.state = state
                label.style = Style(text_color=TEXT_COLORS[state])
        self.objectives.invalidate_layout()

    # -- The script ----------------------------------------------------------------------

    def _objectives_shown(self) -> bool:
        return self.clock >= self._banner_until

    def _fold_objectives(self) -> None:
        # Completion stays on the HUD when it fits. A keeper's card on a short
        # window needs the current work first; this affects rows, never Run.state.
        for objective in self.mission.objectives:
            self._rows[objective.id][0].visible = self.run.state[objective.id] != "hidden"
        super()._fold_objectives()
        if not self.objectives_body.visible:
            for objective in self.mission.objectives:
                if self.run.state[objective.id] == "done":
                    self._rows[objective.id][0].visible = False
            super()._fold_objectives()
        # A story notice shares the column with the command card as well as the objectives.
        bottom = self.game.height - HINT_BAR - 6
        if self.card_panel.visible:
            bottom = min(bottom, self.game.height - PANEL_MARGIN[1] - self.card_panel.get_preferred_size()[1] - CARD_GAP)
        if (self._notice is not None and not self._notice.done
                and self.toast_top + self._notice.height(self) > bottom):
            self.objectives_body.visible = False

    def update(self, dt: float) -> None:
        super().update(dt)
        if not self._game_over:
            self._script()

    def _script(self) -> None:
        run = self.run
        run.tick()
        self.landmarks.update()
        if run.completed:
            texts = [next(o.text for o in self.mission.objectives if o.id == objective_id) for objective_id in run.completed]
            self._notices.append(("Objective complete" if len(texts) == 1 else "Objectives complete", texts, GOOD))
            self.sfx("built")
            run.completed.clear()
        for title, lines in run.notes:
            self._notices.append((title, lines, GOLD))
        run.notes.clear()
        if self._notices and self.clock >= self._banner_until and (self._notice is None or self._notice.done):
            title, lines, accent = self._notices.popleft()
            self._notice = _Notice(title, lines, accent=accent, hold=NOTICE_HOLD)
            self.effects.add(self._notice)
        for point in run.looks:
            wx, wy = to_world(point)
            if self.world.is_explored(self.human, (int(point[0]), int(point[1]))):
                self.camera.pan_to(wx, wy, 0.8)  # never into the dark: ground not yet explored shows the player nothing
            self.minimap.ping(wx, wy)
            self.last_alert = point
        run.looks.clear()
        if run.pending:
            self.game.push(DialogScene(run.pending.pop(0), self.campaign.speakers, run.vars, record=True))

    def _check_game_over(self) -> None:
        if self._game_over:
            return
        if self.run.won:
            self.world.winner = self.human
            self._finish(True)
            self._record()
            self.game.push(MissionResultScene(self, won=True))
        elif self.run.lost is not None or not self.player.alive:
            self._finish(False)
            self.game.push(MissionResultScene(self, won=False, reason=self.run.lost or "Your forces were destroyed"))

    def _finish(self, won: bool) -> None:
        # The result pauses this scene: a sliding warning must not freeze halfway off screen behind it.
        self.effects.clear()
        self._notices.clear()
        super()._finish(won)

    def _record(self) -> None:
        """Write the mission into the progress at the moment of victory; the debrief is a story, not a condition."""
        store = ProgressStore(self.game.data_dir, self.campaign.id)
        try:
            progress = store.load()
            if progress is None:
                progress = Progress(self.campaign.id, self.record.difficulty)
            progress.complete(self.mission, self.run.remembered())
            store.save(progress)
            self.game.save_manager.delete(self.AUTOSAVE_SLOT)
        except SaveError as error:
            self.progress_error = str(error)
            return
        self.progress = progress

    def pause_menu(self) -> Scene:
        return MissionPauseScene(self)

    # -- Saves -------------------------------------------------------------------------------

    def get_save_state(self) -> dict:
        return {**super().get_save_state(), "campaign": self.campaign.id, "mission": self.run.to_dict()}

    def get_save_summary(self) -> dict:
        return {**super().get_save_summary(), "mode": "campaign", "mission": f"{self.campaign.index(self.mission)}. {self.mission.title}"}


def load_mission(state: dict[str, Any], *, settings=None) -> MissionScene:
    """The mission scene a save holds, or a SaveError saying why it cannot be played by this version.  Called only by
    :func:`~warband.ui.scene.load_game`, which then restores what every save keeps beside the world."""
    from warband.story.catalog import get_campaign

    world = check_save(state)
    block = state["mission"]
    if not isinstance(block, dict) or not isinstance(block.get("id"), str):
        raise SaveError("the save's mission block is damaged")
    campaign_id = state.get("campaign")
    if not isinstance(campaign_id, str):
        raise SaveError("the save names no campaign")
    try:
        campaign = get_campaign(campaign_id)
        mission = campaign.mission(block["id"])
    except KeyError as error:
        raise SaveError(f"this save's campaign or mission cannot be played ({error})") from None
    try:
        run = Run.from_dict(mission, world, block)
    except (KeyError, TypeError, ValueError) as error:
        raise SaveError(f"the save's mission block is damaged ({error})") from error
    name_sides(world, mission)
    return MissionScene(campaign, run, difficulty=Difficulty(state["difficulty"]), settings=settings, run_id=saved_run_id(state))


class MissionPauseScene(PauseScene):
    controls = {"q": "quit", "f5": "save", "f9": "load", "s": "settings", "f1": "help", "r": "restart", "c": "campaign", "j": "journal"}

    def on_enter(self) -> None:
        scene: MissionScene = self.game_scene  # type: ignore[assignment]
        panel = self.panel("Paused")
        panel.add(Label(f"{scene.campaign.index(scene.mission)}. {scene.mission.title} · {scene.mission.act}", text_style="sub"))
        panel.add(Button("Resume", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=260))
        panel.add(Button("Save game…", hotkey="F5", on_click=self.save, style=GHOST_BUTTON, width=260))
        panel.add(Button("Load game…", hotkey="F9", on_click=self.load, style=GHOST_BUTTON, width=260))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=260))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=260))
        panel.add(Button("Mission journal", hotkey="J", on_click=self.journal, style=GHOST_BUTTON, width=260))
        panel.add(Button("Restart mission", hotkey="R", on_click=self.restart, style=GHOST_BUTTON, width=260))
        panel.add(Button("Campaign", hotkey="C", on_click=self.campaign, style=GHOST_BUTTON, width=260))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=260))
        self.notice = Label("", text_style="body", text_color=BAD, width=260, wrap=True)
        panel.add(self.notice)

    def restart(self) -> None:
        self.notice.text = restart_mission(self.game, self.game_scene) or ""  # type: ignore[arg-type]

    def journal(self) -> None:
        self.game_scene.open_journal()  # type: ignore[attr-defined]

    def campaign(self) -> None:
        """Back to the campaign screen; the mission is saved first so Continue picks it up where it was."""
        from warband.story.campaign_scene import CampaignScene

        scene: MissionScene = self.game_scene  # type: ignore[assignment]
        self.game.save(scene.AUTOSAVE_SLOT, scene=scene)
        self.game.clear_and_push(CampaignScene(scene.settings, campaign=scene.campaign))


class MissionResultScene(_Overlay):
    """Mission complete or failed: the objectives as they ended, the battle record, and the way on."""

    pause_below = True
    pop_on_cancel = False
    controls = {("return", "space"): "proceed", "r": "retry", "c": "campaign", "q": "quit"}

    def __init__(self, scene: MissionScene, *, won: bool, reason: str | None = None) -> None:
        self.scene = scene
        self.won = won
        self.reason = reason

    def on_enter(self) -> None:
        scene = self.scene
        mission, world = scene.mission, scene.world
        panel = self.panel("Mission complete" if self.won else "Mission failed")
        panel.style = RESULTS_STYLE
        panel.add(Label(f"{scene.campaign.index(mission)}. {mission.title} · {mission.act} · {_clock(world.time)}", text_style="body"))
        if self.reason:
            panel.add(Label(f"Failed: {self.reason}", text_style="body", text_color=BAD))
        objectives = Column(spacing=6, width=520)
        for objective in mission.objectives:
            state = scene.run.state[objective.id]
            if state == "hidden":
                continue
            mark = _Mark()
            mark.state = state
            objectives.add(Row(mark, Label(objective.text, text_style="body", width=490, wrap=True, text_color=TEXT_COLORS[state]), spacing=8))
        panel.add(objectives)
        stats = scene.stats
        panel.add(Label(f"{stats['units_killed']} enemy units defeated · {stats['units_lost']} lost · {stats['buildings_razed']} buildings razed",
                        text_style="sub"))
        if self.won and scene.progress_error:
            panel.add(Label(f"Progress could not be saved: {scene.progress_error}", text_style="body", text_color=BAD, width=520, wrap=True))
        if self.won:
            last = scene.progress is not None and scene.progress.next_mission(scene.campaign) is None
            panel.add(Row(Button("The war is over" if last else "Continue", hotkey="Enter", on_click=self.proceed, style=ACTION_BUTTON, width=260),
                          Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=150), spacing=12))
        else:
            panel.add(Row(Button("Retry mission", hotkey="R", on_click=self.retry, style=ACTION_BUTTON, width=200),
                          Button("Campaign", hotkey="C", on_click=self.campaign, style=GHOST_BUTTON, width=150),
                          Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=150), spacing=12))
        self.notice = Label("", text_style="body", text_color=BAD, width=520, wrap=True)
        panel.add(self.notice)
        panel.add(KeyHints([("Enter", "continue")] if self.won else [("R", "retry"), ("C", "campaign")]))

    def proceed(self) -> None:
        if not self.won:
            return
        scene = self.scene
        self.game.push(DialogScene(scene.mission.debrief, scene.campaign.speakers, scene.run.vars,
                                   on_done=self._after_debrief, record=True))

    def _after_debrief(self) -> None:
        scene = self.scene
        # A choice made in the debrief is part of the mission's memory, so it is recorded after the words are said.
        if scene.progress is not None and scene.mission.remember:
            try:
                store = ProgressStore(self.game.data_dir, scene.campaign.id)
                scene.progress.complete(scene.mission, scene.run.remembered())
                store.save(scene.progress)
            except SaveError as error:
                scene.progress_error = str(error)
        if scene.progress is not None and scene.progress.next_mission(scene.campaign) is None:
            self.game.push(DialogScene(scene.campaign.epilogue, scene.campaign.speakers, dict(scene.progress.flags), on_done=self.campaign))
        else:
            self.campaign()

    def retry(self) -> None:
        if self.won:
            return
        self.notice.text = restart_mission(self.game, self.scene) or ""

    def campaign(self) -> None:
        from warband.story.campaign_scene import CampaignScene

        self.game.clear_and_push(CampaignScene(self.scene.settings, campaign=self.scene.campaign))

    def quit(self) -> None:
        self.game.quit()
