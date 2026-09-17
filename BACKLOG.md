# Warband backlog

Created 2026-09-16. This is the working queue for taking one task at a time.
The [Early Access criteria](docs/warband-early-access-criteria.md) remain the
release gates; [progress](docs/warband-early-access-progress.md) holds their
evidence. Shared engine work belongs in the [Saga2D backlog](../saga2d/BACKLOG.md).

Keep IDs stable. When starting an item, change its status to `in progress` and
record the branch. On completion, mark it `done` here with the commit and
verification evidence; split larger discoveries into new IDs. Statuses below
record the current state; `proposed` items still need scope selection. Within
each priority, the order is the suggested sequence, not a requirement to finish
every earlier item first.

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-001 | First | done | Recover useful branch work and clean up local branches/worktrees | User |
| WB-002 | First | done | Publish tested main pushes through GitHub Actions to games.tachyon-ai.eu | User |
| WB-003 | Next | done | Diagnose and improve movement animation | User |
| WB-004 | Next | in progress | Give melee attacks readable weight and contact | User |
| WB-005 | Next | ready | Replace the rotating-sprite death with convincing falls | User |
| WB-006 | Next | ready | Add blood on damaging hits | User |
| WB-007 | Next | ready | Leave grey abandoned buildings when a player resigns in FFA | User |
| WB-008 | Next | ready | Improve health bars and building progress indicators | User |
| WB-015 | Next | ready | Verify and complete durable local player storage outside game sources | User |
| WB-009 | Next | proposed | Establish current battle performance and fix measured bottlenecks | User / engine split |
| WB-010 | Later | proposed | Smooth online movement and make connection problems understandable | Suggested |
| WB-011 | Later | proposed | Keep fog-hidden state out of opponents' network snapshots | Suggested |
| WB-012 | Later | proposed | Support three- and four-human online FFA | Suggested |
| WB-013 | Next | proposed | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-014 | Later | proposed | Revalidate difficulty and race balance after recovered branch work | Suggested |
| WB-016 | Later | proposed | Assess and recover the six-mission Thornwood campaign | Recovered branch |
| WB-017 | Next | ready | Preserve movement speed through path waypoints | WB-003 diagnosis |
| WB-018 | Next | ready | Keep large selections inside the HUD | Native crowd capture |
| WB-019 | Next | ready | Remove stray sprite-sheet lines from painted units | Native melee review |

## WB-001 — Recover branch work, then clean up

Completed 2026-09-16: merged the useful visual candidate as `db3ed40`, with
845 passing tests, unchanged simulation fingerprint, passing input fuzz and
inspected native frames. Removed its clean, inactive worktree/branch after
preserving the local lockfile edit and evidence; also removed the redundant
stack-root worktree and the temporary recovery worktree. Active balance/AI
experiments remain under WB-014, the campaign under WB-016, and engine candidates
under S2D-001. Acceptance, review, limits and exact dispositions are in
[the branch recovery record](docs/branch-recovery-2026-09.md).

Review committed differences and dirty worktrees before beginning new feature
work. Classify each as integrate, already integrated, retain, or discard with a
reason. Test worthwhile changes against current main before merging; preserve
unmerged commits and uncommitted work. An old name or a merged tip alone is not
enough to remove a worktree that another task is using.

Local read-only inventory on 2026-09-16, compared with main at `5c277f1`:

| Branch / worktree | Commits ahead of main | Finding |
|---|---:|---|
| `balance` / `../warband-balance` | 15 | Balance experiments, mine capacity and AI expansion; three modified files |
| `campaign` / `../warband-campaign` | 4 | Six-mission Thornwood campaign, scripted outcomes and title entry; clean |
| `visual-defects` / `../warband-visual` | 3 | Visual lint and fixes; modified `uv.lock` |
| `ai-arena` / `../warband-arena` | 0 | Committed tip integrated, but `warband/pro_ai.py` modified |
| `ai-2000` / `../warband-elo` | 0 | Committed tip integrated; clean at inspection |
| `player-profile` / `../warband-profile` | 0 | Profile/replays integrated during this planning session; clean |

This is a changing snapshot, not a safety decision or a quality endorsement.
Refresh `git worktree list`, status, ancestry and patch-equivalence before acting.
Include stack-root and sibling-repo local refs in the sweep; engine candidates
are recorded in S2D-001. Do not infer remote merge state from stale tracking refs.

**Done when:** every candidate has a recorded disposition, useful work is
integrated with its required checks, and only confirmed inactive/redundant
branches and clean worktrees are removed. Record retained work as follow-up
items rather than silently losing it. Campaign adoption is a product decision
to assess here, not an instruction to merge it wholesale.

## WB-002 — Publish tested pushes through GitHub Actions

Completed 2026-09-17. The implementation from `codex/backlog-wb002` (Warband)
and `codex/warband-publishing` (Saga Online) is integrated on both mains.
Warband `e38618d` passed the complete main-push journey; Saga Online `1be6068`
passed all 135 server/publication checks, and automated catalog commit `3fcb79a`
published the accepted release. Acceptance, operating policy and detailed
evidence are in [the CI publication plan](docs/ci-publication.md) and
[Saga Online's publication record](../saga-online/docs/warband-ci-publication.md).

Milestones completed on 2026-09-17:

- [x] Pin release inputs and verify native Windows/Mac packages. Source
  `2361f79` passed [native run 35149564980](https://github.com/ikamensh/warband/actions/runs/35149564980):
  901 tests per platform, portable/installed launch and socket checks, native
  input, Mac app verification, and Windows shortcut/uninstall checks.
- [x] Implement immutable release preparation, source/receipt validation and
  separate producer/publisher wiring; independently download and validate the
  accepted native artifacts. Actual main publication remains below.
- [x] Implement the independent Saga Online release consumer and catalog
  updates with retry/order checks. Saga Online `21f31c4` passed
  [83 Linux publication checks](https://github.com/ikamensh/saga-online/actions/runs/35154907841).
- [x] Verify the pinned server package, real orders for all three games,
  checkpoint/rejoin, root preparation and unchanged-release retry on Mac/Linux.
  Saga Online `126f220` passed [103 Linux checks](https://github.com/ikamensh/saga-online/actions/runs/35158657345);
  the independently downloaded Linux archive matched the Mac archive byte for byte.
- [x] Verify atomic site publication/rollback, shared server/site locking,
  crash recovery and compatibility rechecks. Saga Online `7bb5411` passed
  [112 Linux checks and host exclusion acceptance](https://github.com/ikamensh/saga-online/actions/runs/35160355976).
- [x] Implement and verify the restricted CI upload account and SSH caller.
  Saga Online `f8222e5` passed [133 Linux checks and real SSH acceptance](https://github.com/ikamensh/saga-online/actions/runs/35194126106),
  including upload/retry, restricted commands/forwarding, host-key checks,
  compatibility refusal and rollback. Production account setup remains below.
- [x] Wire Saga Online's promotion workflow, including stable archive bytes
  and recovery after the catalog is committed but site publication is interrupted.
  Saga Online `3843a4e` passed [135 Linux checks and the real Git/SSH journey](https://github.com/ikamensh/saga-online/actions/runs/35196347871);
  the default read-only CI token also verified Warband provenance. Enabling
  the main workflow and public deployment remain below.
- [x] Complete server rollout/restore acceptance and record the actual live
  compatibility baseline. Saga Online `f7d3c61` passed [135 Linux checks](https://github.com/ikamensh/saga-online/actions/runs/35199018970),
  including a regression for RTS ticks during rejoin. Live bundle `c5193bd5`
  passed public Mac client checks for all three games; the two retained
  campaigns are preserved, and live database/configuration rollback passed.
- [x] Configure and enable production CI publishing. Both environments allow
  only `main`; the dedicated Saga Online Actions token and restricted website
  SSH key are installed. Both publishing flags are enabled. The actual release
  journey and public download acceptance remain below.
- [x] Exercise the complete main-push journey: [native build 35203328191](https://github.com/ikamensh/warband/actions/runs/35203328191)
  → [publisher 35204501320](https://github.com/ikamensh/warband/actions/runs/35204501320)
  → [site promotion 35204667815](https://github.com/ikamensh/saga-online/actions/runs/35204667815).
  Immutable preview `0.2.0-preview.35203328191` is live. [Public Windows/Mac
  downloads 35205462324](https://github.com/ikamensh/saga-online/actions/runs/35205462324)
  matched the tested bytes and passed all eight packaged online checks with
  fresh profiles. Publisher retry reused immutable artifacts; a GitHub artifact
  upload failure retried successfully before activation. Live rollback, restore,
  repeated publication and stale-upload refusal all passed; the live page was
  inspected. Main-only CI publishing is enabled without manual approval.

The user authorized autonomous releases, CI publishing setup and hosted
deployments on 2026-09-17. Proceed after the required verification without
another go-ahead. All milestones above have verified completion evidence.

Make a push to `main` produce an immutable preview release and update the
Warband download page at [games.tachyon-ai.eu](https://games.tachyon-ai.eu/warband/).
Use `main` as the publishing branch; ordinary feature-branch pushes
should run checks. Use one pinned Windows/Mac native build workflow and a
separate publisher, replacing the former Windows-only release path; retain the
[test workflow](.github/workflows/tests.yml). Site/catalog publication belongs in `saga-online`; start from its
[distribution plan](../saga-online/docs/game-distribution-plan.md) and
[deployment tool](../saga-online/tools/deploy_online.py).

Pin the game, engine and Sagaforge revisions used by a build. Derive unique
versions from recorded release identity; retries must be idempotent. Run tests
and packaged launch checks before promoting catalog links, publish hashes and
source revisions, serialize promotion so an older run cannot replace a newer
one, and retain the previous known-good catalog/site for rollback. A failure
must leave the last working download available.

Decide server compatibility as part of this task: a rules-changing client must
not become the recommended online download against an incompatible server.
Treat static-site promotion and room-server activation as separate operations,
with an explicit compatible rollout/draining policy. Document the CI credential
handoff from today's laptop-operated deployment and the chosen preview/stable
policy. Enabling unattended production publication is an authorized rollout
step of this task, completed with both publishing flags enabled.

**Done when:** a main push passes the complete build → verify → release →
catalog → website journey; downloaded Windows/Mac artifacts match the tested
bytes; compatible clients create/join; failed, repeated and out-of-order runs
and rollback are exercised. The enabled trigger and publication policy are
documented so future main pushes need no manual publishing steps.

## WB-003 — Movement animation: diagnose before authoring more frames

Completed 2026-09-17. Implementation `fae77d9` and `35b851f` is integrated on
main at `2e31cda` and published as **0.2.0-preview.35214358368**. Local and replay
movement interpolate between simulation steps; picking follows displayed units,
and saved/replayed timing is stable. The simulation fingerprint is unchanged.
Native before/after capture reduces stationary intervals during steady travel
from 39/59 to 0/59. Both art styles, turns/stops, crowds, obstacles, pointer input
and pause were inspected; separate network and waypoint issues remain below.

[Main native build](https://github.com/ikamensh/warband/actions/runs/35214358368)
→ [immutable publisher](https://github.com/ikamensh/warband/actions/runs/35215555895)
→ [website promotion](https://github.com/ikamensh/saga-online/actions/runs/35215726975)
all passed. [Public Windows/Mac downloads](https://github.com/ikamensh/saga-online/actions/runs/35215886199)
matched the accepted hashes and passed all eight packaged online checks against
server `99e28517…54609f7`. The three retained campaigns are preserved. The
[diagnosis](docs/movement-diagnosis.md) and
[server rollout](../saga-online/docs/warband-movement-rollout.md) record the
complete acceptance and its limits. Follow-ups are WB-010, WB-017 and WB-018.

Started on `codex/wb003-movement`, from main `1a6def9`.
Acceptance and the repeatable capture matrix are recorded before changes in
[the movement diagnosis](docs/movement-diagnosis.md).

First verified increment: local fixed-step interpolation removes the 20 Hz
stop–jump pattern (39/59 stationary frame intervals became 0/59 in the native
capture). Nine movement cases and the full 910-test suite pass; the simulation
fingerprint is unchanged, and native battle/selection frames were inspected.
The follow-up fixes replay interpolation, the load-time clock reset and
presented selection. Smart orders preserve the displayed target (including
empty ground); 101 relevant scene/view/replay/socket tests pass. This optional
command field required the accepted server compatibility update below.
The separate waypoint-speed finding is WB-017.

The follow-up full suite passes 917 tests (12 skips), two input-fuzz journeys
pass and the simulation fingerprint remains unchanged. The 2× native turn capture
shows attached selection markers and stationary stand poses during both stops.
The full painted/procedural turn, crowd and obstacle matrix is recorded and
inspected at near/normal/far zoom. Real native mouse and F3 events also verify
presented selection, empty-ground movement, enemy targeting and pause.
Candidate `35b851f` also passed [Windows/Mac native checks](https://github.com/ikamensh/warband/actions/runs/35210630105)
and the Linux game test workflow. The staged server suite passes 135 tests;
the hosted server rollout is accepted as `99e28517…54609f7`. Public pointer
commands and all three downloaded Mac clients pass, and the three retained
campaigns are preserved. [The rollout record](../saga-online/docs/warband-movement-rollout.md)
and baseline are integrated in Saga Online main `89fe348`; main publication and
public Windows/Mac download acceptance are complete as recorded above.

The current [motion notes](docs/unit-motion.md), [view](warband/view.py) and
[pose generation](warband/textures.py) already provide four walk frames,
distance-driven cadence and gradual turning. Reproduce what still looks wrong
in the current build instead of assuming the earlier diagnosis still applies.

Capture short native recordings and frame strips of infantry, workers and
mounted units: straight travel, diagonal travel, turns, start/stop, crowded
arrival and obstruction, at normal zoom and both close/far zoom. Compare
painted and procedural art, solo movement and groups, offline and online.
Trace model positions/velocity, render positions, facing, travelled distance,
frame choice and frame times. Separate pose/silhouette, stride/foot sliding,
frame timing, facing changes, crowd pushes and simulation/network cadence.

**Done when:** the dominant causes are demonstrated with evidence, the first
bounded fixes have before/after recordings at gameplay scale, and follow-up
art or engine needs have their own tasks. Validate that stopped units do not
walk, turns do not pop, and motion looks consistent across speeds. Presentation
changes preserve the simulation fingerprint; deliberate rule changes need
their own acceptance. Depends on S2D-002 only if profiling proves an engine issue.

## WB-004 — Stronger melee attacks

Started 2026-09-17 on `codex/wb004-melee-motion`, from main `7655d0e`.
[Acceptance and initial evidence](docs/melee-animation.md) are recorded before
implementation. Native painted/procedural captures reproduce the weak swing;
model damage and strike poses agree. A separate measurable fault is confirmed:
the view overwrites hit knockback before drawing (zero rendered displacement
through three hits). The first regression must preserve visible contact and
moving-unit continuity; fixing recoil alone will not complete this item.
The first increment now renders the intended recoil (~3 px in native capture),
follows newly issued movement and freezes under F3. It passes 82 relevant tests,
input fuzz, the unchanged fingerprint and native layout checks. The human
footman's next prototype adds a continuous weight shift and a brief sword
afterimage. Six melee regressions and an image-clipping regression pass;
the final complete suite passes 924 tests (12 skips).
Native captures cover eight facings and both art paths. A 150-footman timing
comparison rejected the expensive polygon version in favour of one cached
image per trail. Other melee weapons and complete WB-004 acceptance remain
open; [the prototype record](docs/melee-animation.md) states the limits.

Current milestones:

Execution note (2026-09-17): finish WB-004, mark its accepted work done,
then pause before selecting another backlog item, as requested by the user.

- [x] Recover visible hit recoil and compose it with movement and pause.
- [x] Accept the human sword prototype with native frames and measured cost.
- [x] Extend weight and weapon-specific trails to orc, elf and dwarf infantry;
  135 relevant checks pass, with all eight facings inspected in both art paths
  at normal/near/far zoom. The human trail images remain identical.
- [x] Give workers weight and an axe cut, including when carrying. Real
  harvest/fight/stop/deposit checks preserve both resources for all races;
  194 relevant tests pass, the simulation fingerprint is unchanged, and all
  eight facings were inspected in both art paths at normal/near/far zoom.
- [x] Give scouts a spear trail and weight shift using the mounted rig;
  222 relevant checks pass, with native review for every race/facing in both
  art paths at normal/near/far zoom. Existing wolf-rider sheet lines are WB-019.
- [x] Give heavy melee its lance, hammer and club trails and weight shift;
  correct the painted bear rider's lance to its intended hammer. All 72 art
  cells pass extraction and runtime checks; 215 relevant tests pass, the
  fingerprint is unchanged, and native review covers all races/facings/zooms.
- [x] Verify target changes/removal, fog/reveal, save loading, replay speed and
  pause, and real socket snapshots (including rejection and repeated hit history);
  144 scene/network/replay/benchmark-fixture tests pass.
- [ ] Pass the ordinary mixed-army performance gate, full-suite checks and
  complete WB-004 release acceptance. Correct faction warm-up is in place.
  The focused [engine work](../saga2d/docs/warband-renderer-performance.md)
  now passes the full-run gate at p95 15.58 ms, preserving crowd pixels and
  the simulation fingerprint. All 1048 game tests pass (12 skips); the
  native final review and compatible server/client release are being verified.

The existing wind/strike/follow/recover cycle and sparks still read as timid.
After WB-003 establishes the timing/art baseline, improve silhouette,
anticipation, body weight, weapon arc, contact and recovery. Prototype one
infantry weapon before expanding across races/types; consider extra keys or a
smear only where they solve an observed gap. Evaluate brief presentation-only
hit-stop and damage-scaled feedback without delaying simulation or orders.

**Done when:** real-speed close fights and crowded battles show a clear swing
and impact synchronized to the model's hit event and audio; misses, cancelled
wind-ups and moving targets remain honest. Inspect every affected facing and
preserve combat timings/damage unless a separate rules change is agreed.

## WB-005 — Death animations

[UnitDeath](warband/effects.py) currently rotates and squashes the live sprite,
then leaves a fading body. Try authored stagger/fall/lie sprite keys per facing,
or a smaller rig solution that looks convincing at normal zoom. Establish the
look on one infantry unit, then cover mounted units and siege equipment with
appropriate outcomes rather than applying the same topple to everything.

**Done when:** bodies land at the feet and away from the blow without floating,
spinning or reappearing; layering/fog are correct; corpses expire within a
bounded budget. Inspect death sequences and mass-casualty scenes with painted
and procedural art, including loading a save or leaving the scene mid-effect.

## WB-006 — Blood on damaging hits

Add readable, restrained directional blood feedback on organic targets, keyed
to confirmed damage rather than the start of a swing. Distinguish flesh from
armour sparks, buildings and siege impacts. Consider short-lived ground stains
only after the hit effect works; bound their count and lifetime. Provide a
blood-off setting if the effect becomes a persistent part of the presentation.

**Done when:** melee and projectile contact show the appropriate effect once,
with sensible intensity; missed/zero-damage blows and buildings do not bleed;
fog, reconnects and repeated snapshots do not leak or duplicate effects. A
busy battle remains legible and meets the measured frame budget.

## WB-007 — FFA resignation leaves abandoned buildings

[World.resign](warband/model.py) currently removes every owned unit and
building; AI surrender also removes buildings. In three-/four-player FFA,
retain the resigning player's buildings and show them as grey, inactive
abandoned structures while the remaining players continue.

Proposed first scope: preserve footprint, damage and race silhouette; stop
production, research, construction, attacks, vision and economic contribution;
eliminate the former owner from victory checks. Keep current unit removal.
Decide and record whether abandoned structures can be attacked/cleared, and
whether automatic AI surrender follows the same rule. Capture/reuse is a
separate mechanic, not implicit in abandonment. Handle unfinished buildings,
queues and workers inside buildings explicitly; do not confuse abandoned
structures with neutral gold mines.

**Done when:** a seeded four-player match continues correctly after resignation,
the minimap/selection/tooltip agree on the abandoned state, remaining armies
respect footprints, and save/load preserves it. Verify victory, AI targeting,
pathing and absence of destruction rewards/effects on abandonment. Run rules
integration tests and fuzz; keep two-player match completion correct. Online
FFA is separate (WB-012), not a prerequisite for this local-game change.

## WB-008 — Health bars and building progress

Currently [view.py](warband/view.py) draws world health bars for selected or
hovered entities, including undamaged ones. Default health bars to wounded
units/buildings, with clear access
for selection/hover or a temporary show-all control. Choose the exact policy
after seeing a crowded battle. Improve contrast, outline, thickness, anchoring
and zoom behavior; distinguish health from construction, training and research
progress by more than colour. Active work should remain discoverable even on
an undamaged building.

**Done when:** damaged, selected, hovered and full-health cases look deliberate;
construction/production/research progress is understandable without overlapping
bars or labels. Inspect real frames across themes, zooms and crowded fights,
including grey abandoned buildings from WB-007. Verify the policy through real
selection and pointer journeys as well as drawing tests.

## WB-015 — Durable local player storage

Keep player data as readable text files in the user's home/data directory,
separate from source checkouts and installed application files. It must survive
quitting, restarting, updating or replacing the game, and switching between
source and packaged launches. No account or server should be required.

**Existing baseline, verified by source inspection on main (`17b5160`):** the
profile/Elo work is already merged. [Profile](warband/profile.py),
[leaderboard](warband/scores.py) and [replay storage](warband/replay.py) already
use JSON beneath `game.data_dir`, which defaults to `~/.warband/`
(`%USERPROFILE%\.warband\` on Windows):

| Data | Existing location relative to that directory |
|---|---|
| Player name and rated match results; Elo is derived from these results | `profile/save_1.json` |
| Local leaderboard | `high_scores/save_1.json` |
| Recorded matches | `replays/` (one JSON file per match) |
| Saved games and autosave | `saves/` |
| Preferences | `settings.json` |

Build on this storage rather than introducing another persistence mechanism.
Audit the actual write/load journeys and fill any gaps. Document what is saved
and when, make the data folder discoverable from the game, and give simple
backup/restore instructions. Keep files human-readable and versioned; preserve
existing data if a schema or location changes. Reuse atomic writes and explicit
backup recovery; report damaged/unsupported files or write failures clearly
without silently replacing the player's history with a fresh profile.
Current rated results/replays cover offline play; online recording/rating is a
separate feature, not an assumed part of this storage audit.

**Done when:** a real match produces a result, rating and leaderboard entry;
a new game process reloads them along with the player name and settings; a
saved match and its replay can be opened after restart. Verify source and
packaged builds use the same user-owned directory independent of working
directory, and an upgrade preserves the data. Integration checks use an
isolated temporary user directory, cover interrupted writes, corrupt files,
explicit recovery and repeat loading without duplicate results, and never
modify the developer's real profile. Record current evidence in the
[profile storage guide](docs/warband-profile.md).

## WB-009 — Current performance baseline and targeted fixes

Refresh the W10 evidence after the painted-art and combat changes. Use
[tools/perf.py](tools/perf.py) for native frame timings and
[tools/step_bench.py](tools/step_bench.py) for simulation cost. Include the
150-unit reference battle, a large four-player battle, pan/zoom, many deaths
and repeated match restarts. Record host, resolution, revisions, warmup,
p50/p95/max and phase breakdown; separate startup stalls from steady play.

**Done when:** current evidence establishes the existing p95 < 16 ms reference
gate, or identifies reproducible misses and fixes them. Put shared renderer
findings into S2D-002 onward; keep model/view-specific fixes here. Speed-only
changes preserve the simulation fingerprint. Never benchmark under a profiler
or another expensive verification job.

## WB-010 — Online responsiveness and connection feedback

The online path publishes full world snapshots at 10 Hz; distinguish that
cadence from local 20 Hz simulation and frame pacing. Measure command-to-visible
response and jitter under controlled latency; evaluate bounded presentation
interpolation separately from prediction. Keep hit/death events synchronized,
and show useful reconnect/stall status while avoiding unbounded queued orders.

WB-003's real-socket capture reproduces 49/59 stationary display intervals at
60 FPS, then jumps up to 7.68 px for infantry/workers and 10.88 px for knights
at normal zoom (`docs/evidence/movement/online-trace/`). Local interpolation
does not fix this separate path; see [the diagnosis](docs/movement-diagnosis.md).

**Done when:** two real clients under delay/disconnection/rejoin have measured,
improved movement and correct orders/events, with no stale motion after resume.
Use S2D-010 for genuinely shared transport/rate work.

## WB-011 — Player-specific network visibility

`WarbandMatch.snapshot(player)` currently copies the full world regardless of
player. Before public competitive play, send only the information that player
is allowed to know, including safe event payloads and remembered discoveries.
Rendering fog over a complete snapshot does not protect hidden information.

**Done when:** serialized snapshots/events cannot reveal unexplored enemy units,
orders, economy or research; exploration, remembered buildings, combat and
reconnection still work in real two-client tests. Keep this separate from
compression and from claims of comprehensive anti-cheat.

## WB-012 — Three-/four-human online FFA

Local skirmish supports two to four players; current hosted rooms and
WarbandMatch are two-seat. Generalize seats, lobby/race choices, ready/start,
disconnect/rejoin and results through S2D-011, then adapt the game. Reuse WB-007
for resignation. Spectators, teams and ranked matchmaking can wait.

**Done when:** three and four actual clients complete seeded matches, recover a
disconnection and handle a resignation without premature victory or seat leaks.
Require WB-011 before presenting this as public competitive play.

## WB-013 — Fresh-player and cross-platform acceptance

Refresh W06/W15 with the current candidate: observe first launch, first economy,
first battle, loss/resign, save/resume and the website-to-online-match journey.
Include a complete human match on the published Mac/Windows candidate and
record hardware, version and obstacles. Use the visual-defects branch's useful
checks after WB-001, while retaining human assessment of animation and clarity.

**Done when:** each blocker becomes a reproducible ticket and is resolved or
explicitly deferred; current evidence replaces stale gate claims. Automated
checks cannot mark the human playtest complete.

## WB-014 — Difficulty and race-balance evidence

WB-001 retained the active `balance` work and local AI experiments. Audit their
commits, dirty files and completed reports against current main before choosing
changes to integrate; the mine-capacity, economy and settled-match rules require
their own acceptance rather than an automatic branch merge. Preserve the
experiment evidence and retire those worktrees only once inactive and recovered.
After integrating accepted changes, rerun the existing arena/AI-report tools
over adequate seeded samples. Check
Easy against a basic opening, the ordering of difficulties, race/map/seat bias,
and FFA endings. Keep economy/crowding failures distinct from numerical balance.

**Done when:** a recorded report supports the displayed difficulty expectations;
concrete regressions become small fixes with rule tests, fuzz and refreshed
fingerprints where appropriate. Do not retune from a few observed matches.

## WB-016 — Assess the Thornwood campaign

The retained `campaign` branch at `9dbc98f` contains four unique commits: a
six-mission campaign, scripted outcomes, briefings, dialogue, choices and saved
progress. Review its product fit and playability before adoption. Integrate
against the current profile/title UI and the pinned engine; preserve ordinary
skirmish and replay behavior. Coordinate durable campaign progress with WB-015.

**Done when:** each mission's start, objectives, win and loss paths are verified;
choices and unlocked missions survive a new process and an upgrade; the title
and briefing screens fit supported resolutions and have inspected native frames.
Run the full suite and test scripted outcomes separately from normal elimination.
Record whether the campaign is accepted or retained with specific remaining
issues, and clean up the branch only after its work is safely accounted for.

## WB-017 — Consistent speed through path waypoints

WB-003's [movement trace](docs/movement-diagnosis.md) demonstrates that
`World._walk_to` discards unused movement when reaching an intermediate waypoint.
A footman moving at 2.4 tiles/s normally covers 0.12 tiles per tick but periodically
covers only 0.04; the rendered result slows rhythmically at each tile center.
Preserve the tick's remaining travel budget across intermediate waypoints while
respecting turn rates, collision clearance and the actual final destination.
This changes authoritative rules and needs a new compatibility baseline.

**Done when:** straight and diagonal paths over many tiles preserve the intended
distance/time budget, small final segments never overshoot, and turns, obstacles,
crowds, terrain boundaries, harvesting and attack pursuit remain correct. Prove
the rules change with integration tests and seeded fuzz, audit affected movement/
combat expectations, deliberately refresh the simulation fingerprint, and verify
replay/online agreement and compatible client/server rollout before publication.

## WB-018 — Large selection HUD

The native 18-unit crowd capture at 1280×800 shows the selected-unit portraits
and their health strips extending under the command card. The selection panel
must fit the available space while retaining access to every selected unit.
Choose a compact grid or explicit paging from real gameplay needs; coordinate
its health indicators with WB-008. Evidence: `docs/evidence/movement/procedural-crowd-far/`.

**Done when:** 1, 12, 18 and large army selections fit at 1280×800 and 1200×680;
portraits/health indicators, commands, minimap and hints do not overlap; each
unit remains reachable by the chosen interaction. Verify selection changes,
mixed unit types and shrinking selections through real input, extend visual
lint to include the reproduced case, and inspect native frames before closing.

## WB-019 — Stray lines in painted sprite sheets

WB-004's scout review exposes faint horizontal lines floating above the orc
wolf riders. They are visible in the existing `warband/assets/restyled/orc.scout.png`
itself, especially across the walk and attack rows, and in the native capture
`docs/evidence/melee/scouts-painted-orc/1.0/wind.png`. The current sheet and its
cell extraction retain those pixels; the combat changes do not modify the sheet.
Inspect other painted sheets for the same detached border/guide fragments.

**Done when:** the wolf rider has no floating lines in stand, walk or combat
from any facing at normal/near/far zoom. Clean the affected art or extraction
without erasing legitimate spears, antennae, shadows or detached effects; add
a regression using the actual affected frame and a visual-lint check that
reports comparable stray fragments. Preserve team colours, frame geometry and
placement, and inspect native frames after the correction.
