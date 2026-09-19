"""The campaign screen: the story's title, the missions in order with their state, a map of the next one, and the way in.

A fresh campaign asks for its difficulty and begins; a campaign under way continues from its saved mission when
that save can be read and from the mission's briefing when it cannot, so no version of Warband loses the player's
place.  Start over erases the progress after a second press.
"""

from __future__ import annotations

from typing import Any

from saga2d import Anchor, Button, Column, Image, KeyHints, Label, Row, SaveError, Scene
from warband.story.campaign import Campaign, Mission, Progress, ProgressStore
from warband.story.dialog import DialogScene
from warband.story.mission_scene import CAMPAIGN_SLOT, MissionScene, build_world, start_mission
from warband.story.missions import CAMPAIGN
from warband.sim.rules import Difficulty
from warband.ui.scene import _clock, load_game
from warband.audio.sound import play_sound
from warband.ui.style import ACTION_BUTTON, BAD, DIM, GHOST_BUTTON, GOLD, GOOD, MUTED, OVERLAY_STYLE

PREVIEW_KEY = "campaign.preview"
PREVIEW_SIZE = (256, 192)
LIST_WIDTH = 470


class CampaignScene(Scene):
    background_color = (8, 10, 14, 255)
    controls = {("return", "c"): "continue_campaign", "r": "restart_mission", "escape": "back", "e": "easy", "n": "medium", "h": "hard"}

    def __init__(self, settings: dict[str, Any] | None = None, *, campaign: Campaign = CAMPAIGN) -> None:
        self.settings = settings
        self.campaign = campaign
        self.progress: Progress | None = None
        self.difficulty = Difficulty.MEDIUM
        self.notice = ""
        self.confirm_reset = False
        self.resume: MissionScene | None = None
        self._difficulty_buttons: dict[Difficulty, Button] = {}

    def on_enter(self) -> None:
        self.store = ProgressStore(self.game.data_dir)
        try:
            self.progress = self.store.load()
        except SaveError as error:
            self.progress = None
            self.notice = f"The campaign progress could not be read: {error}"
        if self.progress is not None:
            self.difficulty = self.progress.difficulty
        self._build()

    @property
    def next_mission(self) -> Mission | None:
        return self.campaign.missions[0] if self.progress is None else self.progress.next_mission(self.campaign)

    def _resumable(self) -> MissionScene | None:
        """The next mission as the campaign slot saved it, loaded and ready; a save this version cannot play
        (another format, damage) is reported here, and Continue opens the briefing instead."""
        mission = self.next_mission
        if mission is None:
            return None
        try:
            saved = self.game.save_manager.load(CAMPAIGN_SLOT)
            if saved is None or saved["state"].get("mission", {}).get("id") != mission.id:
                return None
            scene = load_game(saved["state"], settings=self.settings)
        except SaveError as error:
            self.notice = f"The saved mission cannot be played by this version of Warband ({error}); Continue starts it again from its briefing"
            return None
        if not isinstance(scene, MissionScene):
            return None
        return scene

    def _preview(self, mission: Mission) -> None:
        from warband.ui.title import preview_image

        run = build_world(mission, flags=self.progress.flags if self.progress is not None else {})
        image = preview_image(run.world)
        if self.game.assets.has_image(PREVIEW_KEY):
            try:
                self.game.assets.update_image(PREVIEW_KEY, image)
            except ValueError:
                del self.game.assets._images[PREVIEW_KEY]  # the map size changed: register again under the same key
                self.game.assets.image_from_pil(PREVIEW_KEY, image)
        else:
            self.game.assets.image_from_pil(PREVIEW_KEY, image)

    def _build(self) -> None:
        self.ui.clear()
        panel = Column(spacing=12, anchor=Anchor.CENTER, style=OVERLAY_STYLE)
        panel.add(Label(self.campaign.title, text_style="title"))
        panel.add(Label(self.campaign.tagline, text_style="sub"))
        if self.progress is None:
            self._build_fresh(panel)
        else:
            self._build_under_way(panel)
        panel.add(Label(lambda: self.notice, text_style="body", text_color=BAD, width=760, wrap=True))
        self.ui.add(panel)

    def _build_fresh(self, panel: Column) -> None:
        panel.add(Label(f"{len(self.campaign.missions)} missions in three acts. The difficulty shifts every computer opponent one step; it is set for the whole campaign.",
                        text_style="body", width=760, wrap=True))
        row = Row(Label("Difficulty", text_style="body", width=110), spacing=8)
        for difficulty, key in ((Difficulty.EASY, "E"), (Difficulty.MEDIUM, "N"), (Difficulty.HARD, "H")):
            button = Button(difficulty.value.title(), hotkey=key, on_click=lambda d=difficulty: self.set_difficulty(d), style=GHOST_BUTTON, width=150)
            self._difficulty_buttons[difficulty] = button
            row.add(button)
        panel.add(row)
        self._restyle()
        first = self.campaign.missions[0]
        panel.add(Row(self._mission_list(), Column(Label(f"1. {first.title}", text_style="heading"), Label(first.act, text_style="sub"),
                                                    Image(PREVIEW_KEY, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1]), spacing=8), spacing=24))
        self._preview(first)
        panel.add(Row(Button("Begin the campaign", hotkey="Enter", on_click=self.continue_campaign, style=ACTION_BUTTON, width=300),
                      Button("Back", hotkey="Esc", on_click=self.back, style=GHOST_BUTTON, width=150), spacing=8))

    def _build_under_way(self, panel: Column) -> None:
        mission = self.next_mission
        if mission is None:
            panel.add(Row(self._mission_list(), Column(Label("The war is over", text_style="heading"),
                                                        Label(f"{self.difficulty.value.title()} · every mission complete", text_style="sub"), spacing=8), spacing=24))
            panel.add(Row(Button("Read the epilogue", hotkey="Enter", on_click=self.continue_campaign, style=ACTION_BUTTON, width=300),
                          Button("Start over", on_click=self.start_over, style=GHOST_BUTTON, width=150),
                          Button("Back", hotkey="Esc", on_click=self.back, style=GHOST_BUTTON, width=150), spacing=8))
            return
        self.resume = self._resumable()
        state = f"Saved at {_clock(self.resume.world.time)} · Continue resumes it" if self.resume is not None else "Continue opens its briefing"
        side = Column(Label(f"{self.campaign.index(mission)}. {mission.title}", text_style="heading"), Label(mission.act, text_style="sub"),
                      Image(PREVIEW_KEY, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1]), Label(state, text_style="sub"), spacing=8)
        panel.add(Row(self._mission_list(), side, spacing=24))
        self._preview(mission)
        panel.add(Row(Button("Continue", hotkey="Enter", on_click=self.continue_campaign, style=ACTION_BUTTON, width=200),
                      Button("Restart mission", hotkey="R", on_click=self.restart_mission, style=GHOST_BUTTON, width=190),
                      Button(lambda: "Really start over?" if self.confirm_reset else "Start over", on_click=self.start_over, style=GHOST_BUTTON, width=190),
                      Button("Back", hotkey="Esc", on_click=self.back, style=GHOST_BUTTON, width=120), spacing=8))
        panel.add(KeyHints([("Enter", "continue"), ("R", "restart the mission"), ("Esc", "back")]))

    def _mission_list(self) -> Column:
        completed = self.progress.completed if self.progress is not None else []
        nxt = self.next_mission
        column = Column(spacing=6, width=LIST_WIDTH)
        act = None
        for mission in self.campaign.missions:
            if mission.act != act:
                act = mission.act
                column.add(Label(act, text_style="sub", width=LIST_WIDTH))
            if mission.id in completed:
                glyph, color = "✓", GOOD
            elif mission is nxt:
                glyph, color = "▶", GOLD
            else:
                glyph, color = "·", DIM
            column.add(Row(Label(glyph, text_style="hud", width=22, text_color=color),
                           Label(f"{self.campaign.index(mission)}. {mission.title}", text_style="body", width=LIST_WIDTH - 30,
                                 text_color=color if mission is nxt else (MUTED if mission.id in completed else DIM)), spacing=6))
        return column

    def _restyle(self) -> None:
        for difficulty, button in self._difficulty_buttons.items():
            button.style = ACTION_BUTTON if difficulty == self.difficulty else GHOST_BUTTON

    def draw(self) -> None:
        w, h = self.game.resolution
        self.draw_rect(0, 0, w, h, (6, 8, 14, 150))

    # -- Actions --------------------------------------------------------------------------

    def set_difficulty(self, difficulty: Difficulty) -> None:
        if self.progress is not None:
            return
        self.difficulty = difficulty
        play_sound("button")
        self._restyle()

    def easy(self) -> None:
        self.set_difficulty(Difficulty.EASY)

    def medium(self) -> None:
        self.set_difficulty(Difficulty.MEDIUM)

    def hard(self) -> None:
        self.set_difficulty(Difficulty.HARD)

    def continue_campaign(self) -> None:
        """Begin, resume the saved mission, open the next briefing, or read the epilogue: whatever comes next."""
        play_sound("button")
        if self.progress is None:
            self.progress = Progress(self.campaign.id, self.difficulty)
            try:
                self.store.save(self.progress)
            except SaveError as error:
                self.notice = f"The campaign progress could not be written: {error}"
                self.progress = None
                return
        mission = self.next_mission
        if mission is None:
            self.game.push(DialogScene(self.campaign.epilogue, self.campaign.speakers, dict(self.progress.flags)))
            return
        if self.resume is not None:
            self.game.clear_and_push(self.resume)
            return
        start_mission(self.game, self.campaign, mission, self.progress, self.settings)

    def restart_mission(self) -> None:
        mission = self.next_mission
        if self.progress is None or mission is None:
            return
        play_sound("button")
        self.game.save_manager.delete(CAMPAIGN_SLOT)
        start_mission(self.game, self.campaign, mission, self.progress, self.settings)

    def start_over(self) -> None:
        """Erase the progress and the saved mission; the first press only asks."""
        if not self.confirm_reset:
            self.confirm_reset = True
            self.notice = "Press Start over again to erase the campaign's progress and its saved mission"
            return
        play_sound("button")
        self.store.clear()
        self.game.save_manager.delete(CAMPAIGN_SLOT)
        self.progress = None
        self.confirm_reset = False
        self.notice = ""
        self._build()

    def back(self) -> None:
        if len(self.game.scenes) > 1:
            self.game.pop()
        else:
            from warband.ui.title import TitleScene

            self.game.clear_and_push(TitleScene(settings=self.settings))
