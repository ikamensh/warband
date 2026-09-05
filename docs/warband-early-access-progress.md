# Warband Early Access progress and evidence

Criteria: [warband-early-access-criteria.md](warband-early-access-criteria.md).
A gate is incomplete until evidence below proves it.

## Where it stands — 2026-09-06

Evidence in place: W01, W02, W03, W04, W05, W07, W08, W09, W10 (frame
times, monkey; the 300-match fuzz and the 30-minute soak are running on
the final code), W13 (macOS), W14. Ongoing by nature: W11, W12. Open:
W06 needs first-run walkthroughs by people, W13 has no Windows build,
W15 needs an independent review and the user's playtest of the
candidate. Nothing found in the last audit blocks a playtest.

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
| W01 skirmish, difficulties, sizes | **evidence in place** | Three difficulties (`d4465fe`); 2–4 players on three sizes (`c8d0aec`); real-input match steps in `tools/verify_warband.py`. `tools/ai_report.py --seeds 6 --decide 20` (2026-09-05): the scripted human opening beat Easy 6/6, lost to Normal 5/6 and to Hard 5/6; Normal-vs-Normal on Medium decided 20/20 within 20 minutes, mean 10.7 min. |
| W02 content floor | **evidence in place** | 7 units, 9 buildings + mine, 9 upgrades, tech chain (`d4465fe`): every entry reachable through the card, rendered (inspected sheet and base frame), in the F2 codex, saved, and covered by `tests/warband/test_content.py` and `test_scene.py`. Balance table in `warband/rules.py`. Peasants repair damaged buildings for half the price pro rata (`22afdc9`; model, scene and AI tests). Compositions in play: the ladder shows Hard's siege, clerics and harass beating Normal 5/8, Normal's tech beating Easy 7/8. |
| W03 maps | **evidence in place** | Three themes, three sizes, 2–4 players, seed choice (`c8d0aec`); `tests/warband/test_maps.py` checks 40 seeds × 3 sizes × 3 themes for open ground, mine and wood distance, connectivity, expansions and terrain mix; winter and wasteland frames inspected. `tools/map_report.py --seeds 100` (900 maps, 2026-09-05): every base has 129–149 open tiles of 169 around its hall, its mine 5 tiles away, wood 5–7 tiles away, two expansion mines, no disconnected map, no base without wood; wasteland has fewer trees and less water than summer. |
| W04 AI | **evidence in place** | Profiles per difficulty with decision logs (`d4465fe`). Scripted-opening results above separate Easy from the rest; the head-to-head ladder in `tools/ai_report.py --ladder` (sides swapped per seed) (`--ladder 4`, 2026-09-05): Normal beat Easy 7/8, Hard beat Easy 8/8, Hard beat Normal 5/8. Stall invariant: every fuzz match checks it (120 matches so far, the 300-match run in progress). |
| W05 controls | **evidence in place** | Patrol, double-click / ctrl-click type selection, Ctrl+A, bookmarks, idle button (`feb8046`); shift-queue, attack-move, hold, rally, groups, tooltips with reasons (`7cea876`); scene tests per control; hint strip per state. |
| W06 teaches itself | partial | Tutorial strip with eight objectives ticked from world state, F4 to hide, settings toggle (`b24f6d3`); blocked actions explain themselves; F2 codex. Missing: independent first-run walkthroughs. |
| W07 presentation | **evidence in place** | Eight facings × four frames, dissolve deaths, arrows and stones, bursts, three themes; construction sites rise through stages (`22423d1`); battered buildings smoke under half health and burn under a quarter (`029a61b`, frame inspected); water moves through three shoreline phases (`32e05a8`, phases inspected side by side); second track `vigil` alternates with `march`; 17 sounds with a checklist in `tests/warband/test_sound.py`. Capture: a 6-second GIF of the 150-unit battle recorded from the real backend (scratchpad `warband_battle.gif`, 72 frames at 12 fps; sent to the user). |
| W08 settings | **evidence in place** | `saga2d.settings.Settings` file, six-row settings screen applied on close and persisted (`b24f6d3`), test `test_progress.py::test_settings_screen_changes_persist…`. HUD matrix rendered and inspected at 1280×720, 1280×800 and 1920×1080 on a HiDPI backing store (scratchpad `hud_sizes.png`): card, minimap, resource strip and hint strip anchor to the edges without clipping. |
| W09 progress protected | **evidence in place** | Three slots + quicksave + autosave every two minutes, browser with summaries, versioned schema, damaged/foreign files refused with a message and no crash (`b24f6d3`, `test_progress.py`). |
| W10 stability, performance | **evidence in place** (300-match run and soak in progress) | Fuzz across the increments: 120 AI matches and 182 monkey runs; five movement deadlocks found and fixed with regression tests (head-on separation `feb8046`; corner steering `bbdbd53`; a walk held short of its spot by a pinned crowd `7c7f3cd`; a crowd shoving units through a tree wall into an isolated clearing, and a detour that kept aiming at a spot across a blocked corner, `1b46664` — seeds 2203 and 2277 of the 300-match run, each replayed clean on the run's own code with the fix swapped in). Monkey: `tools/fuzz_warband.py --games 0 --monkey 100 --steps 1000 --seed 1000` → 100 played, 0 failed. Frame times from `tools/perf_warband.py` (150 units of six types between twelve farms, real backend, images pre-rendered as after the opening's warm-up): `setup frame 195 ms; 720 frames: p50 5.9 ms, p95 13.1 ms, max 30.7 ms; last 120 frames: p50 4.6 ms, p95 11.6 ms` on the reference Mac (M-series, 2026-09-05); with two other CPU-bound processes running, p95 rises to 17 ms. The gate is met on an idle reference Mac. Cuts that got there: GL error checking off, pooled `draw_image` sprites, appearance setters that skip unchanged values, `Y_SORT_STEP` groups, grid A*, direct steering, cached panel geometry. The earlier 126 ms p95 figure was measured under `tracemalloc`, which the tool avoids. 300-match run (`--seed 2000`, pre-fix code): 300 played, 2 failed (the two clearing deadlocks above), 229 decided, 37 eliminations, 32 undecided. Soak (`tools/soak_warband.py --minutes 30`, real backend, the human side played by a brain, on a loaded machine): 4 matches, no crash, heap growth −0.2 MB, p50 9–14 ms, p95 16–26 ms, worst frame 384 ms at a match start; frames saved per match and inspected. Queued on the final code: a 300-match fuzz, the AI report, an idle-machine perf run. |
| W11 tests | ongoing | 607 tests green at `7e36c4b` (Warband 118, after merging main's audio lifecycle and button shortcuts); CI runs `uv run pytest`. Each fuzz finding has a named regression test built from the seed's exact tiles and positions. |
| W12 framework split | ongoing | Additions in this phase: `saga2d.settings`, named save slots with summaries and `get_save_summary` (merged with main's validated envelopes and backups in `76619dd`), `Game.data_dir`/`settings`, backend fullscreen toggle, `Toast(top=)`, `render3d.scale`, `Y_SORT_STEP` grouping and view-matrix caching, GL error checking off, pooled immediate images, change-only sprite setters, a pixel-level pyglet backend test, and `saga2d.testing.FrameTimer`. Each is used by Warband and offered to Tribes/Shardbound (see `docs/coordination.md`). |
| W13 packaging | **evidence in place (macOS)** | `tools/build_warband.py` builds `dist/Warband` with PyInstaller and launches it with `--selftest` from a clean home: fonts, generated art, generated sounds and a rendered frame outside the repository. Built 2026-09-05: 7.2 MB executable, sha256 `c25fc4535ac4c36e`, macOS 15 arm64, selftest frame saved. Windows/Linux not produced. |
| W14 release pack | **evidence in place** | `docs/warband-release.md`: store description, controls, known issues (no repair, long 4-player games, macOS only, English only), credits and provenance (all art and audio generated in-repo; Nunito under OFL). Audited 2026-09-05 against the bindings in `warband/scene.py` and the counts in `warband/rules.py`; the build is being refreshed to include today's changes. |
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
- 2026-09-05/06: `d270bbb` the build menu offers all nine buildings (the
  player could not raise the tech chain before); `0630136` frame times
  under 16 ms (GL checks off, pooled immediate images, change-only
  setters, `tools/perf_warband.py`); `32e05a8` moving water; `029a61b`
  burning buildings; `7c7f3cd` walks settle against a pinned crowd (fuzz
  seed 2016); `08b45ca` difficulty ladder; `d3be67f`
  `saga2d.testing.FrameTimer`; `1e9a07c` map audit in mapgen and
  `tools/map_report.py`; README covers the whole game.  Inspected
  artefacts: build menu at 1280×800, three water phases side by side, a
  smoking and a burning building, a 72-frame battle capture.

## Reproducing the evidence

Every number above comes from one of these, run from the repository root
with the display awake (`caffeinate -u -t 3` wakes it):

```bash
uv run python -m pytest tests -q                                   # W11
uv run python -u tools/fuzz_warband.py --games 300 --monkey 0 --seed 3000   # W10 matches
uv run python -u tools/fuzz_warband.py --games 0 --monkey 100 --steps 1000 --seed 1000  # W10 monkey
uv run python tools/soak_warband.py --minutes 30 --out /tmp/warband_soak    # W10 soak
uv run python tools/perf_warband.py                                # W10 frame times
uv run python tools/verify_warband.py /tmp/warband_verify          # W01/W05 real input, frames to look at
uv run python tools/ai_report.py --seeds 6 --decide 20 --ladder 4  # W01/W04
uv run python tools/map_report.py --seeds 100                      # W03
uv run --with pyinstaller python tools/build_warband.py            # W13
uv run python -m warband --selftest /tmp/selftest.png              # a packaged build's self-check
```
