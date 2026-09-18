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

Execution resumed on 2026-09-18 at the user's request: items are taken one at
a time, each with its acceptance recorded here before implementation and its
evidence after. Presentation items go first because they publish without a
server rollout; the rules items (WB-017, WB-007) follow together, then one
reviewed rollout. WB-022 was done outside the queue on 2026-09-17: a crash on
the first match start in the shipped Windows build, with the coverage that
catches its class.

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-001 | First | done | Recover useful branch work and clean up local branches/worktrees | User |
| WB-002 | First | done | Publish tested main pushes through GitHub Actions to games.tachyon-ai.eu | User |
| WB-003 | Next | done | Diagnose and improve movement animation | User |
| WB-004 | Next | done | Give melee attacks readable weight and contact | User |
| WB-005 | Next | done | Replace the rotating-sprite death with convincing falls | User |
| WB-006 | Next | done | Add blood on damaging hits | User |
| WB-007 | Next | done | Leave grey abandoned buildings when a player resigns in FFA | User |
| WB-008 | Next | done | Improve health bars and building progress indicators | User |
| WB-015 | Next | done | Verify and complete durable local player storage outside game sources | User |
| WB-009 | Next | in progress | Establish current battle performance and fix measured bottlenecks | User / engine split |
| WB-010 | Later | proposed | Smooth online movement and make connection problems understandable | Suggested |
| WB-011 | Later | proposed | Keep fog-hidden state out of opponents' network snapshots | Suggested |
| WB-012 | Later | proposed | Support three- and four-human online FFA | Suggested |
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-014 | Later | proposed | Revalidate difficulty and race balance after recovered branch work | Suggested |
| WB-016 | Later | proposed | Assess and recover the six-mission Thornwood campaign | Recovered branch |
| WB-017 | Next | done | Preserve movement speed through path waypoints | WB-003 diagnosis |
| WB-018 | Next | done | Keep large selections inside the HUD | Native crowd capture |
| WB-019 | Next | done | Remove stray sprite-sheet lines from painted units | Native melee review |
| WB-020 | Later | proposed | Make interrupted release uploads easier to diagnose and recover | WB-004 publication |
| WB-021 | Next | blocked | Fit the window and HUD to a 4K Windows desktop | User report 2026-09-17 |
| WB-022 | Next | done | Start the first match on the window the OS handed back (Windows crash) | User report 2026-09-17 |
| WB-023 | Next | done | Remove the keying residue that tints a faint square around every painted unit | WB-019 survey |

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

- [x] Follow-up approved 2026-09-17: replace run-ID preview suffixes with
  automatic short patch versions. **0.2.2** is published and live; native builds,
  automatic promotion and fresh public Windows/Mac clients passed. See
  [the versioning acceptance record](docs/release-versioning.md). This focused
  follow-up does not resume the backlog beyond WB-004.

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

Completed 2026-09-17 in source `cac35b7`, published as
[0.2.0-preview.35244288044](https://github.com/ikamensh/warband/releases/tag/v0.2.0-preview.35244288044)
and promoted to [games.tachyon-ai.eu](https://games.tachyon-ai.eu/).
[Acceptance criteria, diagnosis and evidence](docs/melee-animation.md) were
recorded before implementation on `codex/wb004-melee-motion`.

Infantry, workers, scouts and heavy melee now shift their weight through a
weapon-specific swing and brief cached trail. Actual damaging hits produce
visible recoil that composes with movement. Workers fight with free hands while
retaining carried resources; the painted dwarf bear rider now carries its
intended hammer. Combat timing, damage, orders and the simulation fingerprint
are unchanged.

- [x] Recover visible hit recoil and verify movement, repeated hits and pause.
- [x] Accept the human sword prototype before expanding to all four races,
  infantry, workers, scouts and heavy melee. Inspect eight facings in painted
  and procedural art at normal/near/far zoom; verify all 72 corrected hammer
  art cells. Existing wolf-rider sheet lines remain separately tracked in WB-019.
- [x] Verify target changes/removal, fog/reveal, save loading, replay speed and
  pause, and real socket snapshots, including rejected/unreceived orders and
  repeated hit history.
- [x] Pass the ordinary 150-unit mixed-army performance gate with published
  Saga2D 0.3.3: whole-run p95 **15.58 ms**, late p95 **15.1 ms**, on the recorded
  Apple M4 setup. Preserve crowded-frame pixels and the simulation fingerprint.
  The first pathfinding burst still reaches 109 ms; this is not a worst-frame
  or long-soak guarantee. See the [engine record](../saga2d/docs/warband-renderer-performance.md).
- [x] Pass [main Linux tests](https://github.com/ikamensh/warband/actions/runs/35244288009)
  (1,048 passed, 12 skipped) and [Windows/Mac native packages](https://github.com/ikamensh/warband/actions/runs/35244288044),
  including independent archive validation and final native visual review.
- [x] Accept the compatible [shared-server rollout](../saga-online/docs/warband-melee-rollout.md),
  publish the immutable release through [CI](https://github.com/ikamensh/warband/actions/runs/35245660396),
  and complete [automatic site promotion](https://github.com/ikamensh/saga-online/actions/runs/35256004880).
- [x] Verify actual public Windows/Mac downloads in
  [run 35256113070](https://github.com/ikamensh/saga-online/actions/runs/35256113070):
  archive identity, frozen client/fonts, all eight public multiplayer checks,
  and unchanged live catalog/server attestation pass on both platforms.

**Accepted:** real-speed fights show readable swings and contact synchronized
with actual model hits. Cancelled attacks and network rejection do not fabricate
impacts. Upload recovery reused the exact accepted binaries; WB-020 records a
proposed follow-up for GitHub transfer/finalization diagnostics.

Execution is paused here. No further backlog item is started.

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

**Diagnosis 2026-09-18** (`tools/verify_deaths.py`, montages in
`docs/evidence/deaths/before/`): the body rotates as a rigid plank at one even
pace, with no lurch, no acceleration and no landing, so it reads as a sprite
turning rather than a figure falling. The scene never passes the blow's source,
so every body falls east: a footman killed from the east falls into its killer.
Mounted units and catapults get the same 88° topple, a horse standing on its
nose and a catapult tipped on end. Bodies do lie at the feet, darken, sort under
the living and fade; those parts stay.

**Done 2026-09-18**, commit `bd9dcb9`: every criterion below holds.
[Tests 35282713696](https://github.com/ikamensh/warband/actions/runs/35282713696),
[Native package checks 35282713708](https://github.com/ikamensh/warband/actions/runs/35282713708),
[Publish 35284011662](https://github.com/ikamensh/warband/actions/runs/35284011662) and Saga
Online's [promotion 35284127986](https://github.com/ikamensh/saga-online/actions/runs/35284127986):
live as Warband 0.2.4. Locally: the full suite (1068 passed), `tools/fuzz.py --games 2
--monkey 20` clean, the fingerprint unchanged, and the montages in
`docs/evidence/deaths/{before,after,after-near,after-procedural}/` inspected
(infantry, archer, mounted and siege from both sides, the mass scene, painted
and procedural).

**Acceptance (recorded 2026-09-18 before implementation):**

1. A killed unit falls away from the blow that killed it, melee or projectile,
   never onto its killer; the direction comes from the hit the view already
   sees, with the old default only when no blow is known.
2. The fall has weight: a lurch with the blow, a topple that accelerates like
   gravity, a landing that overshoots and settles with a dust puff at the
   feet. From the killing blow to lying still takes at most 0.6 s. The feet
   stay within 2 px of the death point throughout (no floating), the body
   never turns past lying, never snaps back and never reappears.
3. Outcomes per category: infantry, archers and casters topple; mounted units
   go down as the mount collapses (a low heap tilted under 50°, not a plank);
   siege engines collapse in place with dust and no topple (under 15°).
   Buildings are untouched.
4. Bodies lie darkened at the feet, sort under living units and stay under
   the fog; only visible deaths make bodies; painted and procedural art
   behave the same.
5. A bounded budget: at most 48 bodies lie at once, the oldest fading early
   past that; every body is gone within HOLD + FADE. Loading a save or
   leaving the match mid-fall leaves no sprite, timer or exception behind.
6. Evidence: before/after montages from `tools/verify_deaths.py` for each
   category from both sides and the mass-casualty scene, in painted and
   procedural art, inspected; scene-seam tests for direction (east and west),
   the timing envelope, each category's outcome, the body cap and a load
   mid-fall; the suite, `tools/fuzz.py` and an unchanged simulation
   fingerprint (no model change).

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

**Where it starts, 2026-09-18:** every melee hit on a unit shows the same
five light sparks and a recoil, whatever was hit; arrows show nothing at the
target; the rules never deal zero damage (`World._hit` deals at least one), so
"no blood" means no `hit` event: a miss, a cancelled swing or a stone that
found nothing. Hit events already carry the damage dealt, the target's type
and armour and whether the blow was ranged; the network scene skips events it
has shown (`_event_id`). The engine stays pinned at 0.3.3, so the effect is
built on what it has: the particle emitter's direction cone and retained
sprites.

**Done 2026-09-18**, commit `117fc8c`: every criterion below holds.
[Tests 35284452707](https://github.com/ikamensh/warband/actions/runs/35284452707),
[Native package checks 35284452663](https://github.com/ikamensh/warband/actions/runs/35284452663),
[Publish 35285652488](https://github.com/ikamensh/warband/actions/runs/35285652488) and Saga
Online's [promotion 35285820197](https://github.com/ikamensh/saga-online/actions/runs/35285820197):
live as Warband 0.2.5. Locally: the full suite (1076 passed), `tools/fuzz.py
--games 1 --monkey 12` clean, the fingerprint unchanged, `tools/perf.py` on
the 150-unit battle three times after against once before (p95 15.1–17.0 ms
against 16.0 ms, `effects.update` 0.24 against 0.14 ms per frame: within the
run-to-run spread, recorded in `docs/evidence/blood/perf-*.txt`), and the
montages in `docs/evidence/blood/{after,after-near}/` inspected (a knight's
blow, an arrow, a blow on a catapult, a crowded fight) together with a lying
body and its stain in `docs/evidence/deaths/after-near/`.

**Acceptance (recorded 2026-09-18 before implementation):**

1. A damaging hit on a flesh unit (every unit but the catapult) sprays a few
   dark red droplets away from the striker, sized by the damage dealt (light
   blows a few small drops, heavy blows more and larger), once per hit, for
   melee and for arrows alike. Armoured targets add a short spark; a catapult
   sheds wood chips instead of blood; buildings show what they show today.
2. Only real damage bleeds: no `hit` event, no effect. Hits out of sight show
   nothing, and a snapshot applied twice or a replayed event index shows each
   hit once.
3. A flesh unit's death leaves a dark stain under the body that fades over
   about half a minute; at most 64 stains lie at once, the oldest fading early
   past that; they sort under units and bodies and stay under the fog.
4. A **Blood** row in Settings (default on) turns sprays and stains off
   together, immediately, and persists like the other rows; sparks and wood
   chips stay.
5. Legibility and cost: the effect never hides the fighters (droplets are
   small and short-lived, stains low-contrast); `tools/perf.py` on the 150-unit
   battle before and after stays within the p95 < 16 ms gate with no
   meaningful change.
6. Evidence: native frames of a melee hit, an arrow hit, a catapult hit and a
   crowded fight at normal and near zoom, inspected; scene-seam tests for each
   criterion (direction and size by damage, no blood on siege and buildings,
   no effect out of sight or on a repeated snapshot, the stain cap and fade,
   the setting); the suite, `tools/fuzz.py` and an unchanged fingerprint.

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

**Decisions 2026-09-18** (on the `rules` branch with WB-017, one server
rollout for both): an abandoned building keeps its former owner's id with
`abandoned = True`, so it is never confused with a gold mine (`player None`),
ownership queries (`player_buildings`) leave it out, and every player's units
may attack it while nobody's brain targets it. Razing it rewards nothing and
raises no alarm. Automatic AI surrender follows the same rule. A two-player
match keeps the current removal: it ends there anyway.

**Done 2026-09-18**, commit `0ea2c1f` on `rules`, merged as Warband main
`0bbe4ae`: every criterion below holds. Its publication needed the shared
server first: Saga Online's [rules rollout](../saga-online/docs/warband-rules-rollout.md)
activated bundle `58f75c42…` (this commit, sagaforge `10f4d87`) at 02:01 UTC
after CI acceptance, a fresh verified backup, the retained-seat rehearsal,
public health, attestation, three-game smoke, native journeys and a live
rejoin of every retained seat. Then [Tests 35295716669](https://github.com/ikamensh/warband/actions/runs/35295716669),
[Native package checks 35295716718](https://github.com/ikamensh/warband/actions/runs/35295716718),
[Publish 35296736779](https://github.com/ikamensh/warband/actions/runs/35296736779) (release 0.2.11, refused
by the compatibility gate until the rollout), Saga Online's
[promotion 35297987598](https://github.com/ikamensh/saga-online/actions/runs/35297987598) and
[public download checks 35298112116](https://github.com/ikamensh/saga-online/actions/runs/35298112116):
live as Warband 0.2.11. Locally: the suite (1178 passed), `tools/fuzz.py --games 12 --monkey 12
--seed 1900` clean with the tile-based stall detector, the fingerprint refreshed deliberately,
`ai_report --seeds 3 --decide 0` unchanged in outcome, and the abandoned base's frame inspected.

**Acceptance (recorded 2026-09-18 before implementation):**

1. Rules: in a match of three or more players, a resignation keeps every
   building the player owned, finished or not, as abandoned: footprint and hit
   points stay; queue, research, construction, rally and any worker inside are
   dropped; it gives no vision, supply, income or production; the player is
   eliminated at once and victory is decided among the rest as before. In a
   two-player match buildings are removed as today. Automatic AI surrender in
   three or more follows the same rule.
2. Any player's units can attack an abandoned building and raze it; razing
   credits no kill, value, plunder or score to anyone, raises no
   "building lost" alarm, and clears the footprint; until then units path
   around it. Brains neither target nor fear abandoned buildings.
3. Presentation: an abandoned building draws grey (its painting desaturated,
   no team colour), the minimap marks it grey, the card names it "Abandoned
   <building>" with no commands, the tooltip says abandoned; the WB-008 bar
   rules apply to it (a bar when wounded or selected); it is seen through fog
   like any building.
4. Save and load carry the state; replays reproduce; the fingerprint is
   refreshed deliberately (same series as WB-017).
5. Tests: model tests on a four-player field for the resignation, the
   elimination and victory, attacking and razing without rewards, pathing
   around the footprint, brains ignoring it, AI surrender and the two-player
   removal; a save round trip; scene tests for the look, the minimap colour
   and the card; `tools/fuzz.py --games 6 --players 4` (or the equivalent
   seeds) and the suite; native frames of an abandoned base inspected.

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

**Where it starts, 2026-09-18** (`docs/evidence/health/before/`): bars exist
only for selected or hovered entities. In a crowded fight the eleven selected
units carry 4 px bars that overlap in the clump while every other wounded
unit, the enemy's included, shows nothing; at near zoom the bars read but
still only on the selection. A damaged farm and a tower under construction
show nothing unselected; a barracks training a footman shows its progress
only in the panel, and its own health bar (full, green) sits on its selection
outline.

**Done 2026-09-18**, commit `0d4bcce`: every criterion below holds, criterion 1 as revised.
[Tests 35289810567](https://github.com/ikamensh/warband/actions/runs/35289810567),
[Native package checks 35289810572](https://github.com/ikamensh/warband/actions/runs/35289810572),
[Publish 35291144567](https://github.com/ikamensh/warband/actions/runs/35291144567) and Saga
Online's [promotion 35291321096](https://github.com/ikamensh/saga-online/actions/runs/35291321096):
live as Warband 0.2.8. Locally: the full suite (1161 passed), `tools/fuzz.py
--monkey 10` clean, the fingerprint unchanged, and the frames in
`docs/evidence/health/{before,after}/` inspected: the crowded fight at zoom 1
and 2 by default and with every bar on, the town at work in summer, winter
and wasteland.

**Acceptance (recorded 2026-09-18 before implementation):**

1. Policy: a health bar shows over every visible unit and building that is
   wounded, over every selected or hovered one whatever its health, and over
   every visible unit and building while F11 has them on (F11 again turns them
   off) or while Alt is held on the pointer's motion. Revised during
   implementation: the engine drops a modifier key's own press and release
   before any scene sees them (`saga2d.input`), so Alt alone cannot be a
   hold-to-show control under the pinned engine; its flag on the events that
   do arrive still works, and F11 is the control that always does (F6 to F8
   are the camera bookmarks). Unwounded,
   unselected ones show nothing. A site under construction shows its progress
   instead of a health bar unless selected.
2. Rendering: a bar is 5 screen pixels tall with a 1 px dark outline at any
   zoom (its width follows the unit), anchored just above the sprite's top or
   the building's rect; green above half, amber above a quarter, red below;
   readable at far zoom (0.5) and in a clump at normal zoom without bars
   drawn over each other more than the sprites themselves overlap.
3. Progress is told apart from health by more than colour: a gold segmented
   bar (five segments) along the bottom edge of a site under construction,
   visible whenever the site is; an own building at work (training or
   research) shows the same segmented bar with a pulsing gold mark at its
   left, so the work is discoverable on an undamaged building without
   selecting it. A rival's work stays hidden; its sites still show progress.
4. Frames inspected: the crowded fight at zoom 1 and 2 by default and with
   every bar on, the town at work (damaged farm, training barracks, site), and
   the same town in winter and wasteland for contrast; the panel's strips
   from WB-018 unchanged. Abandoned buildings wait for WB-007.
5. Tests at the view seam through real input (selection, hover, Alt press and
   flag, F11): wounded shows, healthy hidden, selected and hovered show, Alt
   and F11 show all, a site shows progress not health, own work shows
   its bar and mark, a rival's work does not; visual lint gains
   `battle_bars` (Alt held) and `town_at_work` screens; the suite; the
   fingerprint unchanged (no model change).

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

**Audit 2026-09-18:** the profile, leaderboard, replays, saves and settings
all live under `Game.data_dir` (`~/.warband`, from the game's title, so the
same for a source checkout and the installed app whatever the working
directory), written through Saga2D's `SaveManager`: staged atomic writes, the
previous good file kept as `save_1.backup.json`, recovery explicit through
`load_backup`, damaged files reported and never overwritten (tested for the
profile, replays and saves; the title and the profile screen show the error).
`PROFILE_VERSION` and `SAVE_VERSION` mark the formats. What is missing: no
check crosses a process boundary, nothing proves the packaged build's path,
nothing exercises an interrupted write or a write failure at match end, the
profile's backup can only be restored by hand, the game never says where its
data lives, and the guide has no backup or restore steps.

**Done 2026-09-18**, commit `757bbc1`: every criterion below holds.
[Tests 35291350912](https://github.com/ikamensh/warband/actions/runs/35291350912),
[Native package checks 35291350922](https://github.com/ikamensh/warband/actions/runs/35291350922)
(the Windows and Mac receipts now carry the packaged data folder),
[Publish 35292501371](https://github.com/ikamensh/warband/actions/runs/35292501371) and Saga
Online's [promotion 35292613456](https://github.com/ikamensh/saga-online/actions/runs/35292613456):
live as Warband 0.2.9. Locally: the full suite (1165 passed), the fingerprint
unchanged, the cross-process journey in `tests/warband/test_storage_journeys.py`,
and the profile screen captured natively with a record and with a damaged
profile (`docs/evidence/storage/`), inspected. The guide records what is saved
and when, and how to back up and restore.

**Acceptance (recorded 2026-09-18 before implementation):**

1. A match played to a decision in one process, in an isolated data directory,
   leaves a result and rating in the profile, a leaderboard entry, a replay,
   a quicksave and a changed setting; a second, fresh process reloads all
   five: the title card shows the name and rating, the leaderboard lists the
   entry, the replay opens, the save loads, the setting holds.
2. Source and packaged builds resolve the same user-owned `~/.warband`
   whatever the working directory: the frozen smoke receipt carries the path
   and `tools/ci_package.py` requires it to be that folder under the home.
3. Damage and failure: a corrupt profile, leaderboard, replay or save is
   reported with its path and never overwritten; the profile screen offers
   **Restore backup**, which brings the last good profile back and says so;
   a leftover staged file from an interrupted write is ignored; loading twice
   never duplicates results; when the directory cannot be written at match
   end, the game says the result or replay was not recorded and goes on.
4. The profile screen says where the data lives and that copying the folder
   backs it up; the guide gains "What is saved and when" and "Backing up and
   restoring" with this evidence.
5. Tests at the scene seam for the journey across processes, each damage and
   failure case and the restore action, in temporary directories only; the
   suite; no model change (fingerprint unchanged).

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

**Where it starts, 2026-09-18:** the last figures are from the melee work
([melee-animation.md](docs/melee-animation.md)): on Saga2D 0.3.2 the
reference battle's late frames were p50 10.9 / p95 18.4 ms and the whole run
p95 17.8 ms; the WB-004 rollout measured the unchanged battle at whole-run
p95 15.58 ms on 0.3.3. Since then the units and buildings are painted sheets
(WB-019, WB-023), deaths leave bodies and blood (WB-005, WB-006), bars draw
over wounded units (WB-008), and movement changed (WB-017). CI has no frame
gate: W10 is measured by hand on the reference Mac.

**Acceptance (recorded 2026-09-18 before implementation), in progress on main:**

1. Evidence on this Mac, unpaced, without a profiler or another expensive job,
   naming host, resolution, commit and engine: `tools/perf.py` records p50,
   p95 and max of the late frames and the whole run with the phase breakdown
   (world step, view sync, scene draw, UI draw, batch draw and flip) for the
   150-unit reference battle and, through new scenarios of the same tool, a
   four-player battle of about 300 units, panning and zooming across a
   battle, a mass-death scene while its bodies and blood linger, and repeated
   match restarts (title → match, several times) with the first frames of each
   match separated from steady play; `tools/step_bench.py --repeat 3` records
   the model's step time and its profile.
2. The gate: the reference battle's late p95 is under 16 ms (W10). Every other
   scenario's steady p95 is under 16 ms as well, or its miss is reproducible,
   traced to a phase and either fixed here (model, view, scene) or, when the
   cost is the renderer's, filed in the Saga2D backlog (S2D-002 onward) with
   the numbers.
3. Speed-only changes keep `tools/sim_fingerprint.py --check` unchanged and
   the suite green; anything that changes a frame's look is looked at.
4. The figures, host and revisions are recorded here and in the W10 row of
   [warband-early-access-progress.md](docs/warband-early-access-progress.md);
   the logs are under `docs/evidence/perf/`.

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

**Blocked 2026-09-18:** this needs people who have not played before and a
Windows machine besides the reporter's; nothing to build until a playtest
happens. What unblocks it: one or two fresh players' sessions (a recording or
notes on what confused them) and the Windows report's follow-up.

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

**Where it starts, 2026-09-18:** `World._follow` walks one segment per tick:
when the distance to the next waypoint is under the tick's step it snaps
there and returns, so the rest of that tick's travel is lost. A footman at
2.4 tiles/s should cover 0.12 tiles every tick; at every tile centre it covers
about 0.04. The work happens on the `rules` branch (worktree
`~/saga/warband-rules`) together with WB-007, because both change the
authoritative modules and publication then waits for one reviewed server
rollout.

**Done 2026-09-18**, commits `bd60932` and `2974699` on `rules`, merged as
Warband main `0bbe4ae`: every criterion below holds, and the corner-bounce
deadlock its fuzz found ("Found on the way" below) is fixed in the same
series. Published and promoted together with WB-007 after the shared
server's [rules rollout](../saga-online/docs/warband-rules-rollout.md):
[Tests 35295716669](https://github.com/ikamensh/warband/actions/runs/35295716669),
[Native package checks 35295716718](https://github.com/ikamensh/warband/actions/runs/35295716718),
[Publish 35296736779](https://github.com/ikamensh/warband/actions/runs/35296736779), Saga Online's
[promotion 35297987598](https://github.com/ikamensh/saga-online/actions/runs/35297987598) and
[public download checks 35298112116](https://github.com/ikamensh/saga-online/actions/runs/35298112116):
live as Warband 0.2.11. Locally: `tests/warband/test_waypoints.py` and `test_off_course.py`, the
suite (1178 passed), `tools/fuzz.py --games 12 --monkey 12 --seed 1900` clean, the fingerprint
refreshed deliberately, `ai_report --seeds 3 --decide 0` before and after with every difficulty
still beating the script, the straight trace without short ticks (`docs/movement-diagnosis.md`).

**Acceptance (recorded 2026-09-18 before implementation):**

1. A tick's travel is spent in full along the path: reaching a waypoint with
   budget left, the unit goes on towards the next (through as many waypoints
   as the budget covers), turning as its turn rate allows at each; the final
   segment never overshoots the exact destination. Blocked steps, replanning,
   settling, the watchdog, harvesting approach and attack pursuit keep their
   decisions; only the leftover distance is carried.
2. On open ground, straight and diagonal walks of twenty tiles take the
   distance over the speed within one tick, and a per-tick trace of the
   distance covered is even within 2 % except across turns; the trace of the
   diagnosis (`tools/verify_movement.py --backend mock`) shows the old
   rhythm gone.
3. Proof: model tests for the carried budget, the final segment and a turn;
   the existing movement, combat, harvesting and crowd suites; seeded fuzz
   (`tools/fuzz.py --games 12 --monkey 12`); replay playback and host/client
   agreement (`tests/warband/test_replay.py`, `test_online.py`); the
   simulation fingerprint refreshed deliberately in the same commit.
4. `tools/ai_report.py --seeds 3 --decide 0` before and after shows no
   collapse of any difficulty (a full re-measure stays WB-014).
5. Compatibility: the change moves the authoritative contract, so main is not
   published until the reviewed server rollout that carries WB-007 as well,
   recorded in Saga Online's rollout notes.

**Found on the way, 2026-09-18:** the seeded fuzz of criterion 3 stopped on
two peasants "stalled" on their way home (seeds 1904 and 1908). The cause is
older than WB-017: a work trip walks against the grid (a plain walk does not),
and a crowd's shove onto the diagonal neighbour of the trip's next tile,
beside a building's corner, left the peasant bouncing between that tile's
centre and the corner it may not cut for the rest of the match, because
`_follow` recognised only a shove of more than a tile as being off the path.
The new pace made the bounce's period exactly the fuzz's sampling interval,
which is the only reason it was seen: with a detector that watches for a unit
staying within a tile for twenty seconds instead of standing on one point,
main has the bounce in six of the same twelve seeds. Fixed in the same
series: a diagonal step across a blocked corner counts as off the path and
plans again; a unit already at its centre waits there for the plan instead of
spending the tick's leftover towards the refused tile; the fuzz detector is
the tile-based one; `tests/warband/test_off_course.py` rebuilds seed 1908's
tiles and shove, and the leftover-at-a-waypoint case beside newly forbidden
ground.

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

**Where it starts, 2026-09-18** (`docs/evidence/movement/procedural-crowd-far/gameplay.png`):
a selection of 18 shows one row of twelve 34 px portraits (`MAX_PORTRAITS`)
that runs to the panel's right edge; the other six units have no portrait and
cannot be picked from the panel. Health is a 3 px strip under each portrait.

**Done 2026-09-18**, commit `15a533a`: every criterion below holds.
[Tests 35288251187](https://github.com/ikamensh/warband/actions/runs/35288251187),
[Native package checks 35288251308](https://github.com/ikamensh/warband/actions/runs/35288251308),
[Publish 35289342675](https://github.com/ikamensh/warband/actions/runs/35289342675) and Saga
Online's [promotion 35289463852](https://github.com/ikamensh/saga-online/actions/runs/35289463852):
live as Warband 0.2.7. Locally: the full suite (1155 passed), `tools/fuzz.py
--games 0 --monkey 16` clean, the fingerprint unchanged, and native frames of
18, 60 (page two) and a mixed selection at 1280×800 and 1200×680 inspected
(`docs/evidence/selection/`).

**Acceptance (recorded 2026-09-18 before implementation):**

1. Selections of 1, 12, 18, 26 and 60 units fit inside the selection panel at
   1280×800, 1280×720 and 1200×680: no portrait or strip outside the panel,
   nothing over the command card, minimap, tooltip or key hints, the panel's
   size unchanged.
2. Up to 26 units show as a grid of two rows of thirteen 30 px portraits, each
   with a 4 px health strip. Larger selections page: the heading says "N units
   · page i of k", the grid's last cell is a page tile that turns to the next
   page (wrapping), every unit is on some page, the page returns to the first
   when the selection changes and clamps when it shrinks.
3. Clicking a portrait picks that unit (shift adds), on any page.
4. Verified through real input: scene tests drive a click on the page tile, a
   pick on the second page and a shrinking selection; the fuzz monkey stays
   clean; visual lint gains `select_18_units` and `select_60_units` screens
   (kept clean by its test) and the layout test gains the same selections at
   every size; native frames of 18 and 60 selected at 1280×800 and 1200×680,
   and a mixed selection (peasants, footmen, knights, a catapult), inspected.
5. The suite; no model change (fingerprint unchanged). WB-008 takes the
   in-world health bars; the panel's strips only gain the width to read.

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

**Survey 2026-09-18** (every painted unit sheet, clusters of solid pixels
detached from the figure by 3 px or more): twelve subjects carry them, all at
the cell edge, none in the interior. The orc scout has thin guide lines along
the top of ten walk frames, the orc archer the same along the bottom of its
follow frames, the elf's gold-carrying peasant vertical slivers at the right
edge of nine frames, the human knight pieces of the neighbouring cell's lance
at its left and right edges; the rest are one to a few specks each. They are
what the cut brought in from beyond the figure: the sheet's own cell borders
and the neighbours' spill.

**Done 2026-09-18**, commits `e19d1ac` (Warband) and sagaforge `9db9701`,
`b65daa3`, `7e98912`: every criterion below holds, criterion 2 as refined.
[Tests 35287067407](https://github.com/ikamensh/warband/actions/runs/35287067407),
[Native package checks 35287067418](https://github.com/ikamensh/warband/actions/runs/35287067418),
[Publish 35288050978](https://github.com/ikamensh/warband/actions/runs/35288050978)
and Saga Online's [promotion 35288191313](https://github.com/ikamensh/saga-online/actions/runs/35288191313): live as Warband 0.2.6. Locally: the sagaforge suite (35) and the Warband suite (1125
passed, the lint's new `stray` finding included), 47 sheets cleaned with
17 thousand solid and 450 thousand faint pixels removed and every changed
pixel verified to be a stray, the boxed surveys inspected for every affected
subject, and the wolf rider captured natively before and after at normal and
near zoom (`docs/evidence/strays/`): the lines above it in stand, walk and
combat are gone. What the survey also exposed is WB-023.

**Acceptance (recorded 2026-09-18 before implementation):**

1. The wolf rider shows no floating lines in stand, walk or combat from any
   facing at normal, near and far zoom: native frames before and after,
   inspected.
2. Every painted sheet is free of border and guide slivers and neighbours'
   spill. Refined during implementation, since the wolf rider's lines proved
   to sit 7% into the cell, 130 px long and in the stand frames faint: a
   stray is a cluster separated from the figure by more than 3 px that is a
   thin line at any length or faintness, a speck of at most six solid pixels,
   a blob of at most 60 solid pixels in the outer 12% of the cell, or the
   faint long narrow band along a side that is the ghost of a border.
   Detached content that is none of those stays untouched (arrows, spear tips,
   antennae, shadows, thrown effects, keying residue), and so do team colours,
   cell geometry, origin, drop and every pixel of the figure itself.
3. The cleaning lives in the extraction (`sagaforge.restyle.declutter`,
   applied when a rendered sheet is cut), so a re-rendered sheet comes out
   clean; the committed sheets are cleaned once by that same function and the
   twelve subjects' diffs are only the removed clusters.
4. Visual lint reports comparable fragments as `stray` findings on painted
   frames, so `tests/warband/test_visual_lint.py` keeps the sheets clean; a
   regression test names the affected orc scout frame and walks every sheet.
5. Evidence: the sagaforge and Warband suites, the lint over every registered
   image, native frames inspected; Warband's sagaforge pin in
   `.github/release-pins.json` moved to the commit with the cleaner.

## WB-020 — Interrupted release upload recovery

WB-004 publication encountered both a response-read timeout and a request-write
timeout while uploading accepted archives to GitHub. An unfinished `starter`
asset advertised its intended nonzero size with no digest; in one case its
retrievable bytes already matched the independent CI receipt. The publisher
correctly refused to treat that state as accepted. Preserve the failure logs
and operator recovery evidence in `docs/evidence/melee/`.

Improve per-file transfer/finalization diagnostics and establish a bounded
recovery procedure for these states. Distinguish an active upload from a
terminal failed attempt, and prove the exact source, version and expected bytes
before retrying. Preserve completed assets and immutable published versions.
Do not simply relax digest/state validation or overwrite an ambiguous asset.

**Done when:** realistic HTTP integration checks cover partial uploads, fully
received bytes without final metadata, and interrupted retries. Recovery reuses
accepted archives, leaves completed assets untouched, and reaches a verified
immutable publication. Actual transfer/finalization progress and failures must
be understandable in CI logs. This item is proposed; no implementation is
started during the requested pause after WB-004.

## WB-021 — A 4K Windows desktop gets a window and HUD made for it

Reported 2026-09-17 with a screenshot: on a Windows 10 desktop at 3840×2160
the game opened as a window covering about half of the desktop, letterboxed
inside its own frame with black bands left and right, and the HUD drawn at
native pixels, so the title's menu and the player's card were tiny.
`python -m warband` asks the engine for a window that fits the screen
(`Game(resolution=None)`: the reported screen size minus a margin); the units
pyglet reports under Windows display scaling and what the OS then hands back
decide the rest, and neither has been checked on a scaled desktop. The engine
side is [S2D-015](../saga2d/BACKLOG.md); Tribes and Ninefold ask for their
windows the same way.

**Done when:** on a 4K Windows desktop (a session with display scaling, or a
scaled virtual desktop in CI) the window uses the desktop, letterboxes only
for an aspect mismatch and shows a readable HUD (the layouts are made for
1280 wide and up; a `scale_factor` of 2 keeps text sharp); the startup matrix
in `tests/warband/test_startup.py` names that desktop; a native frame from
such a window is inspected. Ready; not started during the pause after WB-004.

**Blocked 2026-09-18:** the fix needs a Windows desktop at 3840×2160 with
display scaling to measure what pyglet reports and what the OS hands back,
and to inspect the frame. GitHub's Windows runners cannot change their
session's DPI or resolution inside a job, so no scaled virtual desktop is
available in CI, and this Mac cannot stand in for Windows display scaling.
What unblocks it: a session on such a desktop (the reporter's machine or a
Windows VM with a 4K scaled display), starting with the desktop's scale and
resolution from Settings › Display and the output of
`python -c "import pyglet; s = pyglet.display.get_display().get_default_screen(); print(s.width, s.height, s.get_scale(), s.get_dpi())"`
in the game's environment. The startup matrix already names the desktop from
the report with the scale it is presumed to report.

## WB-022 — The first match starts on the window the OS handed back

Reported 2026-09-17 with the traceback: on Windows 10 the first Start from the
title crashed in `MapView._register` with `update_image: got (317, 317), the
image is 320x320`. The title's backdrop is a Medium map and so is the default
new game. The backdrop had registered the ground chunk images under keys of
map size alone; the OS then handed back a window a few pixels shorter than
requested (a scale of 951/960 = 0.990625: 317 px of 320), and the match redrew
the chunks at that scale into the old slots. Every Windows player whose window
is clipped under the taskbar hit it on their first match. CI was green
throughout: the suite started matches at requested sizes only, the native
package check started its match straight from code at 1280×800, and the mock
backend kept `scale_factor` at 1 whatever the window.

Done 2026-09-17. The fix: ground and edge images carry the window scale in
their key (`MapView._map_key`), so another scale is another image and the same
scale is still a redraw in place; the new-game preview keys its image by map
size instead of deleting from the engine's private cache. Coverage for the
class, not the instance:

- `tests/warband/test_startup.py` starts the game as `__main__` does
  (`resolution=None`) on the windows players get — as requested, clipped under
  a taskbar, maximised, small, a 4K desktop that reported scaled units — and
  title → match → title → match across a resize, a fullscreen toggle and a
  size change. The matrix fails on the old code exactly as the report did.
- Saga2D 0.3.4 (published, tag `v0.3.4`): the mock backend derives
  `scale_factor` from the window like the pyglet backend. Warband still pins
  0.3.3: the promotion gate requires the candidate's compatibility contract,
  engine version included, to equal the live server's (`verify_baseline` in
  Saga Online), so the pin moves with the next reviewed server rollout. Until
  then `test_startup.py` sets the scale pyglet would derive after each display
  change (`the_os_hands_back`) and drops that line with the pin bump.
- The packaged native check on both CI platforms resizes the window on the
  title and starts the next match through the new-game screen
  (`start_after_resize` in the receipt, required by `tools/ci_package.py`);
  `--selftest` does the same on the installed Mac app.
- The fuzz monkey resizes the window and toggles fullscreen at random moments.
- Process: `make ci` at the stack root (`tools/ci_status.py`) and the rule in
  the stack and Warband agent notes that a push is not done until CI is green.

Evidence, commit `82cb9c0`: [Tests 35278240645](https://github.com/ikamensh/warband/actions/runs/35278240645),
[Native package checks 35278240715](https://github.com/ikamensh/warband/actions/runs/35278240715)
(Windows and Mac both passed the resize-then-start step),
[Publish verified Warband 35279499839](https://github.com/ikamensh/warband/actions/runs/35279499839)
and Saga Online's [promotion 35279704806](https://github.com/ikamensh/saga-online/actions/runs/35279704806):
**Warband 0.2.3** is the live download. Locally: the full suite (1060 passed),
`tools/fuzz.py --games 0 --monkey 20` with the new window events, an unchanged
simulation fingerprint, and inspected native frames of the self-test after a
resize and of the new-game screen at each map size. Saga Online's promotion
gate now requires `start_after_resize` (`b4ef8fb`).

## WB-023 — Keying residue: a faint square around every painted unit

Found 2026-09-18 while cleaning the sheets for WB-019: the keyed background
of every painted cell is not fully transparent. A faint uniform alpha (about
8–16 of 255) covers the whole cell around the figure, so each unit carries a
faint darker square the size of its cell that moves with it. It is plain at
raised contrast (`docs/evidence/strays/` composites) and subtle on the green
field in play; the blurred cell border that WB-019 removed was the brighter
edge of the same residue. The cause is the hue key (`sagaforge.restyle.key_out`)
leaving a little of everything that was not exactly the key colour.

**Done when:** a painted frame's background is alpha 0 everywhere that is not
the figure, its soft edge or its shadow, on every committed sheet and on a
newly cut one; the figure's anti-aliased edge and the drawn shadows keep their
softness (compare frames at gameplay size before and after, painted against
procedural, and a crowd on light ground where a square would show most); the
lint reports residue so it cannot return; the sheets are re-cleaned once by the
same function and their diffs are only the residue.

**Measured 2026-09-18:** in a footman's stand frame 37,504 pixels lie farther
than 3 px from any solid pixel and still carry alpha (up to 17, 4.8 on
average); a wolf rider's walk frame 20,207 (up to 40), a town hall 14,134
(up to 27). Composited on grass at raised contrast that field is the square.

**Done 2026-09-18**, commit `b6446d4` (Warband) with sagaforge `2b0360d`,
`bb17eda`, `10f4d87`: every criterion below holds.
[Tests 35292660008](https://github.com/ikamensh/warband/actions/runs/35292660008),
[Native package checks 35292659985](https://github.com/ikamensh/warband/actions/runs/35292659985),
[Publish 35293821104](https://github.com/ikamensh/warband/actions/runs/35293821104) and Saga
Online's [promotion 35293968088](https://github.com/ikamensh/saga-online/actions/runs/35293968088):
live as Warband 0.2.10. Locally: the sagaforge suite (36) and the Warband
suite (1176 passed, the lint's `residue` finding included), all 48 sheets
cleaned once with 63.7 million residue pixels verified by the rule and 4,713
px of uncovered slivers decluttered after, and the winter crowd captured
before and after (`docs/evidence/residue/`): the squares are gone.

**Acceptance (recorded 2026-09-18 before implementation):**

1. A painted frame keeps alpha only where it belongs: every pixel farther
   than 3 px from any solid pixel (alpha above 40) and fainter than alpha 24
   becomes fully transparent; the figure's anti-aliased edge and the shadows
   drawn against it, which sit within that reach or above that floor, are
   untouched pixel for pixel.
2. The cleaning is part of the cut (`sagaforge.restyle.clear_residue`, after
   `declutter`), so a newly rendered sheet comes out clean; the committed
   sheets are cleaned once by the same function and every changed pixel is
   residue by that rule (verified in the cleaning pass, as for WB-019).
3. Visual lint reports residue (faint alpha far from the figure) as a
   `residue` finding on painted frames; `tests/warband/test_painted_sheets.py`
   asserts every committed sheet is free of it.
4. Frames inspected: the same footman, wolf rider and town hall composited at
   raised contrast before and after; a crowd on winter ground at normal
   contrast where a square shows most; the lint over every registered image.
5. The sagaforge and Warband suites; the sagaforge pin moved; no model change.
