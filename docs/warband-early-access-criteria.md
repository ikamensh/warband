# Warband Early Access acceptance criteria

Status: **not release-ready**. Baseline: commit `575bb32` on branch `warband`, 2026-09-05.
Warband is a playable Warcraft 2-style RTS slice: one faction, four units, four
buildings, procedural maps, an AI opponent, fog, minimap, save/load, sound. That
proves the framework seam; it is not a product. Every gate below needs evidence
from the release candidate (a test, a fuzz report, an inspected screenshot, a
recorded run), never a plan or a count on its own.

## Product promise

A snappy, readable real-time strategy skirmish game: gather, build, train and
fight against an AI that plays a recognisable strategy, on maps that differ
enough to change the opening, with enough units, buildings and upgrades that
army composition is a decision. A match is 10–20 minutes. Everything has a
hotkey; the game teaches itself; nothing loses the player's progress.

Valve's Early Access guidance requires a playable product with value in its
current state and honest expectations about what is unfinished. The gates are
this project's quality bar, not Valve's numbers. Preparing a release candidate
is authorised here; publishing, store setup and purchases are separate actions
that need the user.

## Acceptance gates

| ID | Required result | Evidence required to pass | Baseline |
|---|---|---|---|
| W01 | A complete skirmish: economy, construction, training, upgrades, combat, elimination, victory and defeat, with three AI difficulties and 2–4 players on three map sizes. | Real-input matches through `tools/verify_warband.py` on each size; AI-vs-AI runs decide ≥ 80 % of matches within 20 minutes on Medium; Easy loses to a scripted human opening, Hard beats it. | Two players, one AI level, 5 of 8 fuzz matches undecided at 15 min. |
| W02 | Content floor with real roles: ≥ 7 unit types, ≥ 8 building types, ≥ 6 upgrades, a tech chain (stables → knights, workshop → siege, church → healers, blacksmith/mill → upgrades). No palette-swap units. | Every entry reachable through the UI, rendered, in the help codex, saved, and exercised by a model test and a scene test; a balance table with cost, counters and the unit each counters. | 4 units, 4 buildings, 0 upgrades. |
| W03 | Maps that change decisions: three sizes, three themes (summer, winter, wasteland), 2–4 players, seed choice; every base fair (mine, wood, open ground, reachable rivals). | 100 seeds per size × theme generated in a test with fairness assertions (mine distance, wood within reach, connectivity, expansion mines) and inspected screenshots per theme. | One theme; fairness only for 8 seeds. |
| W04 | The AI plays observably: expands, scouts, defends, uses upgrades and siege, attacks in waves whose size scales with difficulty, and never stalls or cheats on resources. | AI logs of decisions per minute; three difficulties behave differently in a seeded comparison; stall invariant holds over 200 fuzz matches; no negative resources. | One difficulty; waves too small on large maps. |
| W05 | Controls complete and discoverable: every command by mouse and keyboard, shift-queue, attack-move, patrol, hold, rally, double-click type select, ctrl-click, idle worker, groups, camera bookmarks, tooltips with reasons. | Scene tests per control, real-input verification, and the keycap hint strip covering each state. | Most present; no patrol, double-click, bookmarks. |
| W06 | The game teaches itself: an in-game objective strip walks a new player through the first minutes; blocked actions say why; a codex lists units, buildings and upgrades. | A scripted first run completes the objectives through the UI only; three independent first-run walkthroughs recorded (confusions and fixes). | Help screen and hint strip only. |
| W07 | Presentation: identifiable units and buildings, eight facings, walk/attack/death animation, arrows and siege shots, construction stages, burning damage, animated water, distinct sounds for every event, two music tracks, mute/volume that persist. | Inspected screenshots of every unit, building, theme, effect and overlay; a sound checklist; a short capture. | Four frames, one track, static water. |
| W08 | Settings persist across runs: volumes, edge scroll, scroll speed, fullscreen; the window is resizable and the HUD lays out at 1280×720, 1280×800, 1920×1080 and HiDPI without clipping. | Screenshot matrix at each size; a settings round trip test through a real file. | Fixed layout; settings live in the scene. |
| W09 | Progress protected: three manual slots plus a rolling autosave every two minutes, a save browser with map, players, clock and date, a versioned schema, corrupt or newer files refused with a message and no crash. | Tests for every case; a real-input save/load journey; fuzz through the browser. | One overwrite-only slot, unversioned. |
| W10 | Stable and responsive: no crash, soft-lock or data loss across 300 AI matches, 100 monkey runs of 1,000 steps, and a 30-minute real-backend soak; p95 frame time < 16 ms with 150 units on the reference Mac. | Fuzz and soak reports with seeds; a profile of a late-game frame. | 20 matches, 12 monkey runs, no profile. |
| W11 | Tests protect behaviour: public journeys, rules, failure paths and replayable seeds; Tribes and Shardbound stay green. | Suite runs in CI; each gate names its tests. | 117 Warband tests. |
| W12 | Saga2D stays small, learnable and useful: additions serve two games, have tiny documented interfaces and integration tests; no game rules or imports in the framework. | Cross-game review of each addition in DESIGN.md; the two games' overlay/settings/save code no longer duplicated where the framework can own it. | Nine additions from Warband so far. |
| W13 | A standalone build launches outside the repository without Python or a terminal on macOS (verified here); Windows is advertised only after verification. | Build script, a clean-directory launch with fonts, audio and saves working, recorded hash and OS. | Source checkout only. |
| W14 | Player-facing release pack: store description draft, controls, known issues, credits and asset provenance describing only the real candidate. | Audit against the build. | README only. |
| W15 | Independent review finds no blockers and the user has played the candidate. | Review notes and human playtest feedback resolved or assessed. | Not done. |

Counts never pass W02–W04 on their own; the evidence must show that the extra
content changes decisions. The bar is not lowered to match what exists.

## Framework/game split

Saga2D owns rendering, input, camera, UI widgets and layout, effects, sound
mechanics, fonts, resource lifetimes, settings and save-file I/O. Warband owns
its rules, content tables, AI, art generation, tutorial, HUD composition and
save schema. A widget or helper moves into saga2d when Tribes or Shardbound
would use it in the same form.

## Work order

1. Content and depth (W02, W01): units, buildings, upgrades, tech chain,
   difficulties; model and scene tests; AI uses the new content.
2. Maps and themes (W03), then AI behaviour and difficulty evidence (W04).
3. Controls, tutorial, codex (W05, W06); settings and save protection (W08,
   W09), with the reusable parts in saga2d (W12).
4. Presentation (W07), then stability and performance evidence (W10, W11).
5. Packaging and the release pack (W13, W14), then review (W15).

Evidence and open gaps are tracked in
[warband-early-access-progress.md](warband-early-access-progress.md).
