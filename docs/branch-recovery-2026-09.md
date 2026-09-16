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
| Warband `campaign` (`9dbc98f`) | 4 unique commits, clean; adds a six-mission campaign | Retain; campaign adoption needs its own playability/progression acceptance, beyond recovering visual fixes |
| Warband `ai-arena` (`0d635fb`) | Tip merged, but uncommitted AI changes | Retain dirty working material; inspect whether the AI changes are already covered by newer main/balance behavior |
| Warband `ai-2000` (`bb44c41`) | Tip merged; live tuning parent PID 49802 and follow-up PID 76879 | Retain while live; do not interrupt or remove its working directory |
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

Pending. No candidate has yet been accepted as integrated.
