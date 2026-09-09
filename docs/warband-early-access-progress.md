# Warband Early Access progress and evidence

Criteria: [warband-early-access-criteria.md](warband-early-access-criteria.md).
A gate is incomplete until evidence below proves it.

## Where it stands — 2026-09-08

Evidence in place: W01, W02, W03, W04, W05, W07, W08, W09, W10 (frame
times, monkey, the 300-match fuzz and the 30-minute soak), W13 (automated
macOS and Windows packaging checks), W14. Ongoing by nature: W11, W12. Open:
W06 needs first-run walkthroughs by people; physical Windows GPU/audio
playtesting and a Linux desktop package remain unverified. W15 needs an
independent review and the user's playtest, including a complete
human-versus-human match. The [published `0.1.0-preview.3` prerelease](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.3)
includes Windows and macOS arm64 packages from the immutable
`85becd0fda8493fffc14ad33baee32f4fccdee64` source.

Preview.3 adds automatic worker gathering and settlement plans, regional map
generation, a textured rim, terrain seam fixes and stable cameras beneath
transparent panels. The final Windows suite passed 357 scoped tests; separate
local camera/scene integration and native-pixel checks passed. A bounded run
of one AI match and one 100-input scene run found no failures. An independent
agent inspected 19 source map/UI captures and the final Mac and Windows
package frames. See the [visual review](evidence/warband-map-workers-2026-09-08/visual-review.md)
and [release acceptance](warband-release.md#acceptance-preview3).

The Paris multiplayer server is updated and healthy. The temporary Amsterdam
AI VM, its disk and reserved IP were retired after the earlier remote-play
verification; the multiplayer server remains available for two-player games.

Earlier performance, balance and soak results below retain their recorded
dates and commits; the new packaging evidence does not rerun those gates.

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
| W01 skirmish, difficulties, sizes | **evidence in place** | Three difficulties (`d4465fe`); 2–4 players on three sizes (`c8d0aec`); real-input match steps in `tools/verify_warband.py` (pass on the final code). `tools/ai_report.py --seeds 6 --decide 20 --ladder 4` on the final code (2026-09-06, Normal toned down so a plain opening has a chance): the scripted opening beat Easy 5/6, Normal 2/6, Hard 1/6; Normal-vs-Normal on Medium decided 19/20 within 20 minutes, mean 11.5 min. |
| W02 content floor | **evidence in place** | 7 units, 9 buildings + mine, 9 upgrades, tech chain (`d4465fe`): every entry reachable through the card, rendered (inspected sheet and base frame), in the F2 codex, saved, and covered by `tests/warband/test_content.py` and `test_scene.py`. Balance table in `warband/rules.py`. Peasants repair damaged buildings for half the price pro rata (`22afdc9`; model, scene and AI tests). Compositions in play: the ladder shows Hard's siege, clerics and harass beating Normal 5/8, Normal's tech beating Easy 7/8. |
| W03 maps | **evidence in place** | Three themes, three sizes, 2–4 players, seed choice (`c8d0aec`); `tests/warband/test_maps.py` checks 40 seeds × 3 sizes × 3 themes for open ground, mine and wood distance, connectivity, expansions and terrain mix; winter and wasteland frames inspected. `tools/map_report.py --seeds 100` (900 maps, 2026-09-05): every base has 129–149 open tiles of 169 around its hall, its mine 5 tiles away, wood 5–7 tiles away, two expansion mines, no disconnected map, no base without wood; wasteland has fewer trees and less water than summer. |
| W04 AI | **evidence in place** | Profiles per difficulty with decision logs (`d4465fe`); Normal and Hard repair, Easy does not. Head-to-head ladder on the final code (sides swapped per seed): Normal beat Easy 7/8, Hard beat Easy 7/8, Hard beat Normal 6/8. Stall invariant: every fuzz match checks it; the final 300-match run on the current code passed it in all 300. |
| W05 controls | **evidence in place** | Patrol, double-click / ctrl-click type selection, Ctrl+A, bookmarks, idle button (`feb8046`); shift-queue, attack-move, hold, rally, groups, tooltips with reasons (`7cea876`); scene tests per control; hint strip per state. |
| W06 teaches itself | partial | Tutorial strip with eight objectives ticked from world state, F4 to hide, settings toggle (`b24f6d3`); blocked actions explain themselves; F2 codex. Missing: independent first-run walkthroughs. |
| W07 presentation | **evidence in place** | Eight facings × four frames, dissolve deaths, arrows and stones, bursts, three themes; construction sites rise through stages (`22423d1`); battered buildings smoke under half health and burn under a quarter (`029a61b`, frame inspected); water moves through three shoreline phases (`32e05a8`, phases inspected side by side); second track `vigil` alternates with `march`; 17 sounds with a checklist in `tests/warband/test_sound.py`. Capture: a 6-second GIF of the 150-unit battle recorded from the real backend (scratchpad `warband_battle.gif`, 72 frames at 12 fps; sent to the user). |
| W08 settings | **evidence in place** | `saga2d.settings.Settings` file (main's store since the merge), six-row settings screen applied on close and persisted (`b24f6d3`), test `test_progress.py::test_settings_screen_changes_persist…`. HUD matrix: `tests/warband/test_layout.py` checks thirteen screens at 1280×720, 1280×800, 1440×900, 1728×922 and 1920×1080 for text drawn over text (`saga2d.testing.assert_no_text_overlap`); frames at 1280×720, 1280×800 and 1920×1080 inspected on a HiDPI backing store. Windows narrower than 1280 are not laid out for (noted in the release pack). |
| W09 progress protected | **evidence in place** | Three slots + quicksave + autosave every two minutes, browser with summaries, versioned schema, damaged/foreign files refused with a message and no crash (`b24f6d3`, `test_progress.py`). |
| W10 stability, performance | **evidence in place** (300-match run and soak in progress) | Fuzz across the increments: 120 AI matches and 182 monkey runs; five movement deadlocks found and fixed with regression tests (head-on separation `feb8046`; corner steering `bbdbd53`; a walk held short of its spot by a pinned crowd `7c7f3cd`; a crowd shoving units through a tree wall into an isolated clearing, and a detour that kept aiming at a spot across a blocked corner, `1b46664` — seeds 2203 and 2277 of the 300-match run, each replayed clean on the run's own code with the fix swapped in). Monkey: `tools/fuzz_warband.py --games 0 --monkey 100 --steps 1000 --seed 1000` → 100 played, 0 failed. Frame times from `tools/perf_warband.py` (150 units of six types between twelve farms, real backend, images pre-rendered as after the opening's warm-up): final code, 2026-09-06, load average 5 from other work: `720 frames: p50 5.2 ms, p95 10.9 ms, max 29.8 ms; last 120 frames: p50 4.7 ms, p95 9.5 ms, max 19.2 ms` (the 2026-09-05 run on the same Mac gave p95 13.1 ms; a run alongside two other CPU-bound processes gave 17–20 ms). The gate is met on an idle reference Mac. Cuts that got there: GL error checking off, pooled `draw_image` sprites, appearance setters that skip unchanged values, `Y_SORT_STEP` groups, grid A*, direct steering, cached panel geometry. The earlier 126 ms p95 figure was measured under `tracemalloc`, which the tool avoids. 300-match run (`--seed 2000`, pre-fix code): 300 played, 2 failed (the two clearing deadlocks above), 229 decided, 37 eliminations, 32 undecided. Soak (`tools/soak_warband.py --minutes 30`, real backend, the human side played by a brain, on a loaded machine): 4 matches, no crash, heap growth −0.2 MB, p50 9–14 ms, p95 16–26 ms, worst frame 384 ms at a match start; frames saved per match and inspected. Final 300-match run on the current code (`--seed 3000`, after the clearing fixes, repair and the merges): 300 played, 0 failed, 216 decided, 39 eliminations, 45 undecided. Queued on the final code: the AI report and an idle-machine perf run. |
| W11 tests | ongoing | 607 tests green at `7e36c4b` (Warband 118, after merging main's audio lifecycle and button shortcuts); CI runs `uv run pytest`. Each fuzz finding has a named regression test built from the seed's exact tiles and positions. |
| W12 framework split | ongoing | Additions in this phase: `saga2d.settings`, named save slots with summaries and `get_save_summary` (merged with main's validated envelopes and backups in `76619dd`), `Game.data_dir`/`settings`, backend fullscreen toggle, `Toast(top=)`, `render3d.scale`, `Y_SORT_STEP` grouping and view-matrix caching, GL error checking off, pooled immediate images, change-only sprite setters, a pixel-level pyglet backend test, and `saga2d.testing.FrameTimer`. Each is used by Warband and offered to Tribes/Shardbound (see `docs/coordination.md`). |
| W13 packaging | **automated evidence in place (macOS and Windows)** | Preview.3 at `85becd0` passed [Windows CI 34216123836](https://github.com/ikamensh/saga2d/actions/runs/34216123836), including installer/portable, public TLS, native planning, shortcut and uninstall checks. The [installed Mac app](evidence/warband-map-workers-2026-09-08/mac-package/README.md) passed native/public TLS, archive extraction and signature checks. [Public downloads](evidence/warband-map-workers-2026-09-08/published-release.json) match the tested binaries. Historical preview.1 platform scope remains below. Physical Windows GPU/audio playtests and a standalone Linux package remain unverified. |
| W14 release pack | **evidence in place** | [Release pack](warband-release.md): store description, controls, known issues, credits and provenance (art/audio generated in-repo; Nunito under OFL). Updated 2026-09-08 with the published preview, exact source/artifact hashes, matching macOS evidence and platform limitations. Original controls/content audit: 2026-09-05 against `warband/scene.py` and `warband/rules.py`. |
| W15 review | incomplete | |

## W13 packaging scope — preview.3, 2026-09-08

Published version `0.1.0-preview.3` uses immutable source
`85becd0fda8493fffc14ad33baee32f4fccdee64` on both platforms and the public server.
[Windows acceptance](evidence/warband-map-workers-2026-09-08/windows-package/README.md)
records 357 regression passes and the actual extracted/installed EXE checks.
[Mac acceptance](evidence/warband-map-workers-2026-09-08/mac-package/README.md)
records the final installed app, preserved backup, native Apple M4 rendering,
public multiplayer and extracted archive signature/hash checks.

These flows exercise global planning, automatic construction assignment,
assembly, cancellation, native room-code clipboard input and seat recovery.
All nine Windows and eighteen Mac package frames were visually inspected.
The [public download receipt](evidence/warband-map-workers-2026-09-08/published-release.json)
matches the three shipping downloads to the tested artifact hashes.
The [server receipt](evidence/warband-map-workers-2026-09-08/server-deployment.json)
records the final source deployment and preserved checkpoints. This is
automated integration acceptance; a complete two-human match remains open.

## Historical W13 packaging scope — preview.1, 2026-09-08

The published preview.1 Windows package was built at
`fd6e0c911fa68aa0355d4b56dd8e4f0885c739d8`. The successful
[Windows run](https://github.com/ikamensh/saga2d/actions/runs/34202934123)
records provenance in `build-manifest.json` and `workflow-build.json`, and
runtime acceptance in `verification.json`. Both extracted and installed EXEs
created/joined rooms, moved authoritative units, rejected foreign orders and
reclaimed private seats over local sockets; the installed EXE repeated those
checks over the public TLS endpoint. Installation, Start menu shortcut and
uninstallation also passed.

Native title, multiplayer input and match rendering passed on the Windows
Server 2025 runner using Mesa 26.2.0 llvmpipe. The two driver DLLs were provided
only for CI and are absent from the setup EXE and portable ZIP. The check
loaded/generated 87 sounds with audio muted. It establishes neither audible
quality nor GPU coverage beyond the recorded software renderer. See
[Windows package verification](windows-warband.md) and the
[historical artifact hashes](warband-release.md#historical-acceptance-preview1).

The [prerelease](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.1)
is published. Its macOS app archive matches source `fd6e0c9` and has
[native Apple M4 and public-network evidence](evidence/warband-internet-2026-09-08/mac-release/README.md),
plus archive extraction and deep ad-hoc signature checks. It is not Developer
ID signed or notarized. This delivered archive supersedes the older Mac
candidate at `90f3067`.
The [Mac-to-remote-AI run](evidence/warband-internet-2026-09-08/README.md)
proves public connection and early economic orders, not a complete
human-versus-human match. Linux server/headless-client operation is separate
from desktop packaging; no standalone Linux release has been verified.

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
uv run --extra package python tools/package.py build --version 0.1.0-preview.4  # W13; add --installer on Windows
uv run --extra package python tools/package.py verify dist/warband --native
uv run python -m warband --selftest /tmp/selftest.png              # a packaged build's self-check
```
