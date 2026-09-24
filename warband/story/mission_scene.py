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
from warband.story.campaign import Campaign, Mission, Progress, ProgressStore, Run, shifted
from warband.story.dialog import DialogScene
from warband.sim.model import World
from warband.sim.rules import BuildingType, Difficulty
from warband.ui.scene import HUD_TOP, GameScene, PauseScene, _clock, _Overlay, check_save
from warband.ui.style import ACTION_BUTTON, BAD, GHOST_BUTTON, GOLD, GOOD, MUTED, PANEL_STYLE, RESULTS_STYLE, TEXT
from warband.ui.view import rgba, to_world

CAMPAIGN_SLOT = "campaign"
NOTICE_HOLD = 4.0
MARK = 18
MARK_COLORS = {"open": (255, 255, 255, 40), "done": GOOD, "failed": BAD}
TEXT_COLORS = {"open": TEXT, "done": MUTED, "failed": BAD}


def name_sides(world: World, mission: Mission) -> None:
    for player, side in zip(world.players, mission.sides):
        player.name = side.name


def build_world(mission: Mission, *, flags: dict[str, Any]) -> Run:
    """The mission's map from its seed, reshaped by its setup; the run that plays it."""
    width, height = mapgen.SIZES[mission.size]
    world = mapgen.generate(mission.seed, width, height, len(mission.sides), theme=mission.theme, races=[side.race for side in mission.sides],
                           layout=mission.layout)
    world.scripted = True
    name_sides(world, mission)
    run = Run(mission, world, flags=flags)
    mission.setup(run)
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
    progress = ProgressStore(game.data_dir).load()
    return progress if progress is not None else Progress(campaign.id, difficulty)


def restart_mission(game, scene: MissionScene) -> str | None:
    """Play *scene*'s mission again from its start, with the choices the campaign's progress holds; the reason it cannot
    when that progress cannot be read.  The campaign screen says why in full and offers to set the file aside."""
    try:
        progress = current_progress(game, scene.campaign, scene.difficulty)
    except SaveError:
        return "Cannot restart: the campaign progress is unreadable. Campaign says why."
    start_mission(game, scene.campaign, scene.mission, progress, scene.settings, briefing=False)
    return None


def start_mission(game, campaign: Campaign, mission: Mission, progress: Progress, settings, *, briefing: bool = True) -> None:
    """Build the mission and play its briefing over the current screen, then replace everything with the match."""
    run = build_world(mission, flags=progress.flags)
    scene = MissionScene(campaign, run, difficulty=progress.difficulty, settings=settings)
    if briefing:
        game.push(DialogScene(mission.briefing, campaign.speakers, run.vars, on_done=lambda: game.clear_and_push(scene)))
    else:
        game.clear_and_push(scene)


class _Notice(Toast):
    """A toast that keeps under the objectives panel however the panel grows after it was raised."""

    def draw_below(self, scene: Scene, below: float) -> float:  # the effects layer draws toasts through this, stacked
        self.top = scene.toast_top
        return super().draw_below(scene, below)


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

    def __init__(self, campaign: Campaign, run: Run, *, difficulty: Difficulty, settings=None) -> None:
        super().__init__(run.world, run.mission.seed, difficulty=difficulty, settings=settings, ranked=False)
        self.campaign = campaign
        self.run = run
        self.mission = run.mission
        self.tutorial = None
        self.brains = [make_brain(side, shifted(level, difficulty), run.mission.seed) for side, level in run.ai.items() if run.world.players[side].alive]
        self.progress: Progress | None = None
        self.progress_error = ""
        self._rows: dict[str, tuple[Row, _Mark, Label]] = {}
        self._panel_state: dict[str, str] = {}
        self._notices: deque[tuple[str, list[str], tuple[int, int, int, int]]] = deque()  # one toast at a time, so none hides another
        self._notice_until = -math.inf
        self._banner_until = -math.inf  # the mission's title has the screen to itself until then

    def on_enter(self) -> None:
        super().on_enter()
        banner = Banner(f"Mission {self.campaign.index(self.mission)}: {self.mission.title}", subtitle=self.mission.act,
                        accent=rgba(self.player.color), hold=2.0)
        self.effects.add(banner)
        # The band crosses the window at 40 % of its height, where a short window's objectives panel reaches: the
        # panel and the script's first notices wait for it to pass.
        self._banner_until = self.clock + banner.duration
        self._notice_until = max(self._notice_until, self._banner_until)

    # -- Objectives panel ---------------------------------------------------------------

    def _build_objectives(self) -> Column:
        panel = Column(spacing=6, anchor=Anchor.TOP_RIGHT, margin=(12, HUD_TOP), style=PANEL_STYLE, blocks_pointer=True)
        panel.add(Label(f"{self.campaign.index(self.mission)}. {self.mission.title}", text_style="heading", width=390))
        self._rows = {}
        for objective in self.mission.objectives:
            mark, label = _Mark(), Label(objective.text, text_style="body", width=390 - MARK - 8, wrap=True)
            row = Row(mark, label, spacing=8)
            self._rows[objective.id] = (row, mark, label)
            panel.add(row)
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

    def update(self, dt: float) -> None:
        super().update(dt)
        self.objectives.visible = self.clock >= self._banner_until
        if not self._game_over:
            self._script()

    def _script(self) -> None:
        run = self.run
        run.tick()
        if run.completed:
            texts = [next(o.text for o in self.mission.objectives if o.id == objective_id) for objective_id in run.completed]
            self._notices.append(("Objective complete" if len(texts) == 1 else "Objectives complete", texts, GOOD))
            self.sfx("built")
            run.completed.clear()
        for title, lines in run.notes:
            self._notices.append((title, lines, GOLD))
        run.notes.clear()
        if self._notices and self.clock >= self._notice_until:
            title, lines, accent = self._notices.popleft()
            self.effects.add(_Notice(title, lines, accent=accent, hold=NOTICE_HOLD))
            self._notice_until = self.clock + NOTICE_HOLD + 2 * Toast.SLIDE
        for point in run.looks:
            wx, wy = to_world(point)
            if self.world.is_explored(self.human, (int(point[0]), int(point[1]))):
                self.camera.pan_to(wx, wy, 0.8)  # never into the dark: ground not yet explored shows the player nothing
            self.minimap.ping(wx, wy)
            self.last_alert = point
        run.looks.clear()
        if run.pending:
            self.game.push(DialogScene(run.pending.pop(0), self.campaign.speakers, run.vars))

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

    def _record(self) -> None:
        """Write the mission into the progress at the moment of victory; the debrief is a story, not a condition."""
        store = ProgressStore(self.game.data_dir)
        try:
            progress = store.load()
            if progress is None:
                progress = Progress(self.campaign.id, self.difficulty)
            progress.complete(self.mission, self.run.remembered())
            store.save(progress)
            self.game.save_manager.delete(CAMPAIGN_SLOT)
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
    from warband.story.missions import CAMPAIGN

    world = check_save(state)
    block = state["mission"]
    if not isinstance(block, dict) or not isinstance(block.get("id"), str):
        raise SaveError("the save's mission block is damaged")
    try:
        mission = CAMPAIGN.mission(block["id"])
    except KeyError:
        raise SaveError(f"this save's mission ({block['id']}) is not in this version of the campaign") from None
    try:
        run = Run.from_dict(mission, world, block)
    except (KeyError, TypeError, ValueError) as error:
        raise SaveError(f"the save's mission block is damaged ({error})") from error
    name_sides(world, mission)
    return MissionScene(CAMPAIGN, run, difficulty=Difficulty(state["difficulty"]), settings=settings)


class MissionPauseScene(PauseScene):
    controls = {"q": "quit", "f5": "save", "f9": "load", "s": "settings", "f1": "help", "r": "restart", "c": "campaign"}

    def on_enter(self) -> None:
        scene: MissionScene = self.game_scene  # type: ignore[assignment]
        panel = self.panel("Paused")
        panel.add(Label(f"{scene.campaign.index(scene.mission)}. {scene.mission.title} · {scene.mission.act}", text_style="sub"))
        panel.add(Button("Resume", hotkey="Esc", on_click=self.game.pop, style=ACTION_BUTTON, width=260))
        panel.add(Button("Save game…", hotkey="F5", on_click=self.save, style=GHOST_BUTTON, width=260))
        panel.add(Button("Load game…", hotkey="F9", on_click=self.load, style=GHOST_BUTTON, width=260))
        panel.add(Button("Settings", hotkey="S", on_click=self.settings, style=GHOST_BUTTON, width=260))
        panel.add(Button("How to play", hotkey="F1", on_click=self.help, style=GHOST_BUTTON, width=260))
        panel.add(Button("Restart mission", hotkey="R", on_click=self.restart, style=GHOST_BUTTON, width=260))
        panel.add(Button("Campaign", hotkey="C", on_click=self.campaign, style=GHOST_BUTTON, width=260))
        panel.add(Button("Quit", hotkey="Q", on_click=self.quit, style=GHOST_BUTTON, width=260))
        self.notice = Label("", text_style="body", text_color=BAD, width=260, wrap=True)
        panel.add(self.notice)

    def restart(self) -> None:
        self.notice.text = restart_mission(self.game, self.game_scene) or ""  # type: ignore[arg-type]

    def campaign(self) -> None:
        """Back to the campaign screen; the mission is saved first so Continue picks it up where it was."""
        from warband.story.campaign_scene import CampaignScene

        scene: MissionScene = self.game_scene  # type: ignore[assignment]
        self.game.save(CAMPAIGN_SLOT, scene=scene)
        self.game.clear_and_push(CampaignScene(scene.settings))


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
        self.game.push(DialogScene(scene.mission.debrief, scene.campaign.speakers, scene.run.vars, on_done=self._after_debrief))

    def _after_debrief(self) -> None:
        scene = self.scene
        # A choice made in the debrief is part of the mission's memory, so it is recorded after the words are said.
        if scene.progress is not None and scene.mission.remember:
            try:
                store = ProgressStore(self.game.data_dir)
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

        self.game.clear_and_push(CampaignScene(self.scene.settings))

    def quit(self) -> None:
        self.game.quit()
