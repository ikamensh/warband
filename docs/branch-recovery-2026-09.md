# Branch recovery — September 2026

WB-001 execution began from main `04fbcfd` on 2026-09-16, in the isolated
`codex/backlog-wb001` worktree. This record distinguishes inspected candidates
from verified integrations. The entire backlog remains the goal; this is its
first work item.

## Acceptance before changes

1. Inventory local refs and worktrees across the stack, including dirty files,
   ancestry and live processes. Record integrate/retain/already-integrated
   dispositions. Never remove dirty or actively used worktrees.
2. Recover the visual-defects candidate against current main: depth sorting
   follows unit feet/building front edges; inspected layouts fit 1280×800 and
   1200×680 without losing profile/replay entry points, global shortcuts,
   command-card actions or the current engine pin.
3. Visual regression checks, the full game suite and the unchanged simulation
   fingerprint pass on the integrated candidate. Run bounded input fuzz and
   inspect native title/new-game/HUD/help/codex/results frames. Record any
   failure rather than loosening assertions to hide it.
4. Retain larger/active gameplay experiments with named next steps. Remove only
   clean, fully integrated, inactive worktrees and refs after rechecking them.
   Preserve commits and unique local material before removal.
5. Self-review the resulting implementation and commit each verified unit.
   Update WB-001 with evidence and the exact dispositions before marking done.

## Initial inventory and decisions

| Repository / ref | Observed state | Disposition / next action |
|---|---|---|
| Warband `visual-defects` (`15983c9`) | 3 unique commits; only its lockfile is dirty | Integrate committed visual fixes and diagnostic tool, adapting to current main; preserve the original dirty worktree during review |
| Warband `balance` (`9125b05`) | 18 unique commits, recently active evaluation processes | Retain; audit gameplay/economy changes and their evidence under WB-014 once that work settles |
| Warband `campaign` (`9dbc98f`) | 4 unique commits, clean; adds a six-mission campaign | Retain for WB-016, with mission/progression acceptance before adoption |
| Warband `ai-arena` (`0d635fb`) | Tip merged, but uncommitted AI changes | Retain for WB-014; compare dirty working material with newer main/balance behavior |
| Warband `ai-2000` (`bb44c41`) | Tip merged; live tuning parent PID 49802 and follow-up PID 76879 | Retain for WB-014 while live; preserve the tuning job and its working directory |
| Warband `player-profile` | Branch/worktree already removed; commits on main | Already integrated; preserve profile/replay behavior during recovery |
| Stack `claude/infallible-poincare-9f0282` | Tip merged; live app/agent processes use the worktree | Retain active worktree |
| Stack `claude/youthful-shaw-71b594` | Tip merged, clean; no cwd process found | Candidate for cleanup after checking ignored/local material |
| Saga2D `codex/fix-openal-lifetime`, `codex/reuse-text-labels`, detached audio-control | Unique audio and renderer candidates overlap | Retain for S2D-001; independently verify audio correctness and rendering performance before adoption |
| Absolution detached memory investigation | Tip is an ancestor of main, clean | Retain until local evidence and ownership are checked |
| Sagaforge, Tribes, Shardbound, Ninefold, Saga Online | Main only, clean | No branch recovery needed |

The PID and ref observations are dated evidence, not permanent locks. Recheck
authoritative process/ref state before cleanup or starting expensive jobs.
AI tuning was already using three CPU workers at inspection; no new expensive
local validation job is started alongside it.

## Execution evidence

### Visual candidate

Recovered `35479a3`, `9a22078` and `15983c9` against main, preserving current
profile/replay entry points, the pointer-blocking selection panel, army button,
Ctrl shortcuts and `saga2d==0.3.2`. The changes correct sprite sorting to use
feet/building front edges, remove chroma fringe, fit procedural unit poses,
and repair HUD/help/codex/new-game/save-browser layouts.

Integration exposed a title bug on its first frame: it used UI bounds before
layout, putting the title off screen until the next draw. A regression test
failed at both supported resolutions before the fix; the title now measures
the centered menu before drawing. The visual tool now uses separate temporary
storage for mock/native runs, so inspecting the same victory twice does not
inflate the captured rating. Result fixtures resign through the real model API.

A real resignation also exposed inconsistent lint scope: overlap checks
examined the top scene but off-screen checks included paused animations beneath
it. A small transparent-overlay regression reproduced the problem; both checks
now inspect the active scene, and the regression still detects off-screen text
in the overlay. Waiting longer was tested and rejected because covered effects
are intentionally paused. This does not validate background animations beneath
overlays; native inspection remains necessary.

Native inspection then confirmed that the final rival's new notice was visibly
clipped at the right edge behind the results panel. The game now announces a
fallen rival only while the match continues. A real two-/three-player resignation
regression fails before the fix and passes after it: victory shows its result
without the redundant toast, while continuing FFA still announces the rival.

The final full suite passes: **845 passed, 12 skipped** (`uv run --locked pytest -q`,
162.92 s). Its single warning is the existing stale-painted-sheet test exercising
its warning path. Logs are under `docs/evidence/branch-recovery/`; the earlier
failed run is retained alongside `full-suite-accepted.log`.

Native title/new-game/HUD/help/codex frames were rendered at 1280×800 and
1200×680 and opened for inspection. The first-frame title and native layout
metrics also pass. Final results were rerendered and opened at both resolutions
after the notification fix (`native-results-accepted/`): no lint findings or
off-screen toast warnings, and the profile starts at 1000 in each isolated run.

The recorded simulation fingerprint still matches
`1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`.
Bounded input fuzz (`--games 0 --monkey 2 --steps 250 --seed 81`) completed both
runs with zero failures. No model, rule, engine-pin or lockfile changes are part
of this recovery. The native army and wooded-scene captures at both resolutions
were opened and inspected; all six army/woods/results lint runs reported no
findings, with the results-background issue above separately found and fixed.

### Review and limits

An advisory review using the `second-opinion` skill and Claude Opus 4.8 led to
native metric checks and explicit documentation that PIL font measurements
are approximate. Source inspection of the pinned engine confirmed its sorting
formula uses image-bottom minus `ground`; `Placement.front` defaults to zero
and `ground` is derived from `drop - front`. The mock allocates unique handles
for PIL images, so the suggested handle-deduplication failure does not occur
on this version. Speculative exception handling was not added.

The imported source branch's art scan reported four painted strike-frame drift
findings and eight weak team-recolour findings. Those are historical evidence,
not newly passing checks: review strike drift under WB-003/WB-004 and team
readability under WB-013. This integration claims verified layouts/depth and
recovered diagnostics, not completion of the animation/art backlog.

WB-014 now explicitly owns the retained balance/AI experiments. The balance
branch advanced to `741158b` during this work, confirming that it remains active.
WB-016 records the retained campaign and its acceptance. Engine candidates
remain with S2D-001. The clean, merged, inactive stack-root worktree and branch
`claude/youthful-shaw-71b594` were removed; the active sibling worktree remains.

The old visual worktree's seven logs and dirty lockfile patch are preserved in
the main checkout under `docs/evidence/branch-recovery/source-visual/`. Its
single lockfile edit is also retained as the named stash
`93e647723f8a3362b3b8569a246640516b275734` ("WB-001 preserve visual-defects local
lockfile metadata"). It changes old Sagaforge dev-dependency metadata, so it
was preserved rather than applied over the current game's lockfile.

Background tuning/balance jobs were temporarily paused during expensive
validation and resumed in a `finally` block; no paused jobs remain. Final
branch/worktree removal followed the verified merge to main.

## Completion

Accepted into main as merge commit `db3ed4090b3fb36724faf914a4e5f41619df76b1`.
After fresh clean-status, ancestry and process checks, removed the
`warband-visual` worktree and `visual-defects` branch using ordinary safe Git
removal (no force). Copied all 39 recovery evidence files to the main checkout
and verified their SHA-256 contents before removing the clean temporary
`warband-backlog` worktree and `codex/backlog-wb001` branch.

Warband's remaining worktrees are main, `ai-arena`, `ai-2000`, `balance` and
`campaign`, with the follow-ups recorded above. Engine audio/rendering candidates,
the active stack-root worktree and the detached Absolution investigation remain
retained, with no unique work discarded. WB-001 is complete; this does not mark
the retained experiments or the rest of the roadmap complete.
