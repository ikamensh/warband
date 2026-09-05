# Warband Early Access progress and evidence

Criteria: [warband-early-access-criteria.md](warband-early-access-criteria.md).
A gate is incomplete until evidence below proves it.

## Baseline audit — 2026-09-05, commit `575bb32`

- Playable slice: 4 units, 4 buildings, one AI, procedural summer maps, fog,
  minimap, one save slot, 17 sounds, one track. 403 tests in the repo (117 for
  Warband), `tools/fuzz_warband.py` 20 matches + 12 monkey runs clean,
  `tools/verify_warband.py` seven real-input steps with inspected frames.
- Known gaps: matches on large maps often undecided at 15 minutes; no
  upgrades, siege, healing or tech chain; settings not persisted; one save
  slot, unversioned; fixed 1280×800 HUD layout; four animation frames.

## Gate status

| Gate | Status | Evidence so far |
|---|---|---|
| W01 skirmish, difficulties, sizes | partial | Three difficulties (`d4465fe`); 2–4 players on three sizes (`c8d0aec`); real-input match steps in `tools/verify_warband.py`. Missing: scripted-opening comparison per difficulty, the 80 % decided-in-20-minutes figure. |
| W02 content floor | **evidence in place** | 7 units, 9 buildings + mine, 9 upgrades, tech chain (`d4465fe`): every entry reachable through the card, rendered (inspected sheet and base frame), in the F2 codex, saved, and covered by `tests/warband/test_content.py` and `test_scene.py`. Balance table in `warband/rules.py`. Still to show: that compositions change decisions (AI-vs-AI comparisons with and without siege/clerics). |
| W03 maps | **evidence in place** | Three themes, three sizes, 2–4 players, seed choice (`c8d0aec`); `tests/warband/test_maps.py` checks 40 seeds × 3 sizes × 3 themes for open ground, mine and wood distance, connectivity, expansions and terrain mix; winter and wasteland frames inspected. Report tool for 100 seeds still to add. |
| W04 AI | partial | Profiles per difficulty with decision logs (`d4465fe`); fuzz with mixed difficulties: 8 matches, 0 failures, Normal beat Easy in all four pairings (~8.4 min). Missing: seeded three-way comparison, 200-match stall run. |
| W05 controls | **evidence in place** | Patrol, double-click / ctrl-click type selection, Ctrl+A, bookmarks, idle button (`feb8046`); shift-queue, attack-move, hold, rally, groups, tooltips with reasons (`7cea876`); scene tests per control; hint strip per state. |
| W06 teaches itself | partial | Tutorial strip with eight objectives ticked from world state, F4 to hide, settings toggle (`b24f6d3`); blocked actions explain themselves; F2 codex. Missing: independent first-run walkthroughs. |
| W07 presentation | partial | Eight facings × four frames, dissolve deaths, arrows and stones, bursts, construction sites, three themes, 17 sounds, one track. Missing: construction stages, burning damage, animated water, a second track, a capture. |
| W08 settings | **evidence in place** | `saga2d.settings.Settings` file, six-row settings screen applied on close and persisted (`b24f6d3`), test `test_progress.py::test_settings_screen_changes_persist…`. Missing: the display-size screenshot matrix. |
| W09 progress protected | **evidence in place** | Three slots + quicksave + autosave every two minutes, browser with summaries, versioned schema, damaged/foreign files refused with a message and no crash (`b24f6d3`, `test_progress.py`). |
| W10 stability, performance | partial | Fuzz so far: 36 AI matches and 24 monkey runs across the increments, 0 failures. Missing: 300-match run, 100 × 1,000-step monkey, 30-minute soak, frame-time profile (in progress). |
| W11 tests | ongoing | 439 tests green at `b24f6d3` (Warband 131); CI runs `uv run pytest`. |
| W12 framework split | ongoing | Additions in this phase: `saga2d.settings`, named save slots with summaries and `get_save_summary`, `Game.data_dir`/`settings`, backend fullscreen toggle, `Toast(top=)`, `render3d.scale`. Each is used by Warband and offered to Tribes/Shardbound (see `docs/coordination.md`). |
| W13 packaging | incomplete | |
| W14 release pack | incomplete | |
| W15 review | incomplete | |

## Increments

- `d4465fe` content and depth; `c8d0aec` map themes; `feb8046` controls and
  framework settings/saves; `b24f6d3` settings screen, save browser,
  autosave, schema checks, tutorial. Inspected artefacts: unit/building
  sheets, base frame, winter/wasteland frames, tutorial/settings/browser
  screens (this session's scratchpad).
