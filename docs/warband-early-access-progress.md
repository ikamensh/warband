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
| W07 presentation | partial | Eight facings × four frames, dissolve deaths, arrows and stones, bursts, three themes; construction sites rise through stages and battered buildings smoke, second track `vigil` alternates with `march` (`22423d1`, frames inspected). Water moves: shoreline lapping and drifting ripples through three chunk images painted over the first frames and cycled (`tests/warband/test_view.py::test_water_moves…`, three phases rendered and inspected side by side). 17 sounds, a checklist in `tests/warband/test_sound.py`. Missing: burning damage, a capture. |
| W08 settings | **evidence in place** | `saga2d.settings.Settings` file, six-row settings screen applied on close and persisted (`b24f6d3`), test `test_progress.py::test_settings_screen_changes_persist…`. HUD matrix rendered and inspected at 1280×720, 1280×800 and 1920×1080 on a HiDPI backing store (scratchpad `hud_sizes.png`): card, minimap, resource strip and hint strip anchor to the edges without clipping. |
| W09 progress protected | **evidence in place** | Three slots + quicksave + autosave every two minutes, browser with summaries, versioned schema, damaged/foreign files refused with a message and no crash (`b24f6d3`, `test_progress.py`). |
| W10 stability, performance | **evidence in place** (300-match run and soak still to do) | Fuzz across the increments: 120 AI matches and 82 monkey runs, 2 movement deadlocks found and fixed with regression tests (head-on separation `feb8046`; corner steering `bbdbd53`). Frame times from `tools/perf_warband.py` (150 units of six types between twelve farms, real backend, images pre-rendered as after the opening's warm-up): `setup frame 195 ms; 720 frames: p50 5.9 ms, p95 13.1 ms, max 30.7 ms; last 120 frames: p50 4.6 ms, p95 11.6 ms` on the reference Mac (M-series, 2026-09-05); with two other CPU-bound processes running, p95 rises to 17 ms. The gate is met on an idle reference Mac. Cuts that got there: GL error checking off, pooled `draw_image` sprites, appearance setters that skip unchanged values, `Y_SORT_STEP` groups, grid A*, direct steering, cached panel geometry. The earlier 126 ms p95 figure was measured under `tracemalloc`, which the tool avoids. Still to run: 300-match fuzz, 100 × 1,000-step monkey, 30-minute soak (`tools/soak_warband.py`). |
| W11 tests | ongoing | 523 tests green at `bbdbd53` (Warband 112 after the merge with main's save hardening); CI runs `uv run pytest`. Each fuzz finding has a named regression test. |
| W12 framework split | ongoing | Additions in this phase: `saga2d.settings`, named save slots with summaries and `get_save_summary` (merged with main's validated envelopes and backups in `76619dd`), `Game.data_dir`/`settings`, backend fullscreen toggle, `Toast(top=)`, `render3d.scale`, `Y_SORT_STEP` grouping and view-matrix caching in the pyglet backend. Each is used by Warband and offered to Tribes/Shardbound (see `docs/coordination.md`). |
| W13 packaging | **evidence in place (macOS)** | `tools/build_warband.py` builds `dist/Warband` with PyInstaller and launches it with `--selftest` from a clean home: fonts, generated art, generated sounds and a rendered frame outside the repository. Built 2026-09-05: 7.2 MB executable, sha256 `c25fc4535ac4c36e`, macOS 15 arm64, selftest frame saved. Windows/Linux not produced. |
| W14 release pack | draft | `docs/warband-release.md`: store description, controls, known issues (static water, no repair, long 4-player games, macOS only, English only), credits and provenance (all art and audio generated in-repo; Nunito under OFL). Audit against the build still to do. |
| W15 review | incomplete | |

## Increments

- `d4465fe` content and depth; `c8d0aec` map themes; `feb8046` controls and
  framework settings/saves; `b24f6d3` settings screen, save browser,
  autosave, schema checks, tutorial. Inspected artefacts: unit/building
  sheets, base frame, winter/wasteland frames, tutorial/settings/browser
  screens (this session's scratchpad).
- `8dc7ce5` catapult stone, every unit variant rendered in tests; `22423d1`
  performance pass (grid A*, direct steering, plans aimed at passable tiles,
  cached panel geometry, y-sort groups), construction stages, smoke, second
  track, `--selftest`, build/report/soak tools, release pack; `76619dd` merge
  with main's hardened saves; `bbdbd53` corner-steering deadlock from fuzz
  seed 203.
