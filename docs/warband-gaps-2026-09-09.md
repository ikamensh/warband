# Warband: significant gaps, 2026-09-09

An audit of the game at `41ee08f` (races, composed soundtrack, portrait
command card) against the product promise in
[warband-early-access-criteria.md](warband-early-access-criteria.md) and
what a skirmish player expects from a Warcraft 2-style RTS.  Gaps are ranked
by how much they change a match.  Seven are scheduled as one hive plan
([hive/warband-plan-2026-09-09.toml](hive/warband-plan-2026-09-09.toml))
built by the free OpenCode Muse Spark model, in an order that starts with the
files no other session is editing; one is being ported by another session as
this is written; the rest need the owner, the framework or a stronger agent.

## Scheduled

| # | Gap | Where it shows | Plan item |
|---|-----|----------------|-----------|
| 1 | No way to concede a lost match; the player must quit or be razed. | `PauseScene` offers save, load, settings, new game, quit. | `resign` |
| 2 | One enemy scout at a farm recalls the computer's whole army from its attack. | `Brain._military`: any threat sets `attacking = False` and sends every soldier. | `ai-defence` |
| 3 | Matches on large maps go undecided: the AI's wave requirement grows without bound past what its farms can feed, it waits at home while a beaten enemy rebuilds, and the last hidden farm must be found by hand. | Known issue in `warband-release.md`; `Brain.wave`, `World.supply`, fog. | `ai-endgame` |
| 4 | An expansion hall adds no workers; the computer's income stays at the first hall's. | `Brain._training` trains peasants only from `_hall()` up to `profile.peasants`. | `ai-economy` |
| 5 | The AI plays every race the same way (recorded in `warband-races.md`), so races differ in look, not in the fight. | `Brain._choose_unit` alternates footman/archer. | `ai-race-play` |
| 6 | The new-game screen shows a seed number; the map is a surprise. | `NewGameScene`. | `map-preview` |
| 7 | Mixed groups string out: knights arrive alone and die. | `World.move`/`attack_move` pace each unit by its own speed. | `group-move` |
| 8 | The Settlement row (Build, Train, Upgrade, Plans, Assembly) is mouse-only; the user asked for keyboard scheduling. | `GameScene.on_enter` settlement `Row`. | `settlement-hotkeys` (appended, `docs/hive/warband-plan-2026-09-09-settlement-hotkeys.toml`) |

## Not scheduled

- **The AI knows where everything is.** `Brain._enemy_targets` reads every
  enemy building regardless of fog; only defence uses visibility.  Honest
  scouting would be a real change to how the AI feels, but it also risks the
  stalls item 3 removes; do it after item 3 lands and measure with
  `tools/ai_report.py`.
- **The online guest cannot choose a race.** Room options carry the creator's
  race and the guest's seat is drawn from the seed (`warband/multiplayer.py` `ONLINE`,
  `warband/title.py`).  Needs a per-seat option at join time in
  `saga2d.online` and the server, plus a server redeploy.
- **Race balance.** `tools/race_report.py` gave Humans 8–4 and Elves 4–7;
  Drill suits an AI that trains without pause.  Re-measure after item 6, since
  race-specific play changes the result.
- **Frame time.** The art overhaul measured p95 18.4 ms against the 16 ms
  gate on a 150-unit battle; needs the real backend and an idle machine.
- **Window scaling.** The HUD is a fixed logical canvas; resizing does not
  rearrange panels.  Framework work (`saga2d.ui` layout).
- **Two online seats, no chat, no ready screen.** All need transport changes
  in `saga2d.online`.
- **First-run walkthroughs (W06) and the human-versus-human playtest (W15)**
  need people.
- **The game-over screen is one line of the human's counters.** Another
  session is porting the `codex/warband-scores` work onto main as this is
  written (per-player `Player.stats`, a scored result screen with a summary,
  local high scores, AI surrender when it cannot recruit), so no plan item
  covers it.  That branch's combat wind-up, readable arrows and lingering
  bodies remain a merge for a person to judge.
