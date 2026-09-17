# WB-002 — Verified publication on a main push

Acceptance recorded 2026-09-16 before implementation. Baselines: Warband
`e710ed8`, Saga Online `c33c195`. This item remains in progress until the actual
GitHub-to-download journey below passes; local helpers and green unit tests
alone do not complete it.

## Acceptance

1. A main push selects one immutable identity: the exact Warband commit,
   a committed Sagaforge SHA, the locked Saga2D release and Python/build tools,
   and a unique preview version stable across attempts of the same run.
   Feature branches/PRs run checks without publication credentials.
2. Native Windows x64 and Apple Silicon macOS runners build from that identity.
   Regression tests pass before publication. Extracted executables and the
   installed Windows program/Mac app run outside the checkout in isolated user
   directories, with real socket and native rendering checks. The Windows
   installer also passes shortcut/uninstall checks. Inspect the captured PNGs.
3. Publication consumes both platforms' passing receipts and checks every
   uploaded file's hash/size and source identity. No mixed commits, missing
   platform, stale receipt, dirty source or changed dependency is accepted.
   Published versioned bytes are immutable. A retry reuses accepted artifacts;
   an interrupted upload resumes without replacing them.
4. Saga Online independently validates the completed release, downloads the
   accepted bytes and updates only Warband's catalog entry. The site and catalog
   agree. Serial promotion checks source order explicitly so an older queued
   run cannot replace a newer release. Failed builds/verification/promotion
   preserve the last working public downloads.
5. A game-rules/state change cannot be advertised against an incompatible room
   server just because it still says `warband-v2`. Gate promotion on an explicit
   verified server compatibility baseline plus packaged create/join/order/rejoin
   checks. Static-site publication never restarts the room server. A changed
   compatibility baseline requires a separately reviewed server rollout with
   room draining/checkpoint and rollback evidence.
6. Site activation is atomic and serialized, retains the previous known-good
   release and rolls back on a failed public-byte/health check. Exercise failed,
   repeated, out-of-order and rollback publication using temporary roots/local
   servers before the live rollout.
7. Configure scoped CI credentials and enable production after verifying the
   concrete changes, artifacts and rollout commands. Under the stack's standing
   authorization of 2026-09-17, agents perform game publication, CI setup and
   hosted deployments without another user approval request.
   After activation, an actual main push must complete builds, GitHub release,
   catalog and site; unauthenticated downloads must match the tested hashes and
   packaged compatible clients must create/join. Record the run URLs and evidence.

## Implementation decisions

- Keep the existing pinned packaging recipe and Windows installer checks.
  Add the missing native Mac path and share release preparation between them.
- Store sibling source pins in the game repository rather than resolving a
  moving branch independently on each runner. Preview versions use the
  project's base version and the GitHub run ID; retry attempts do not change it.
- Keep binaries on GitHub Releases. Saga Online owns catalog validation, site
  construction and promotion, using a narrowly scoped cross-repository GitHub
  credential and a separate static-site deploy credential. Cloud/DNS/admin
  credentials are not CI inputs.
- Build/verify jobs have read permissions. Credentials are available only to
  trusted main publication jobs. Pin Actions and dependency checkouts by SHA.
- Concurrency alone is insufficient: compare candidate source identity/order
  at promotion time. Preserve other games' current catalog entries, and record
  desired catalog changes in Saga Online's Git history for audit/rollback.
- Treat the existing unsigned/ad-hoc-signed preview policy honestly. This task
  does not claim publisher signing, notarization or a human usability playtest.

## Findings before implementation

The current Windows workflow runs on tags/manual dispatch, follows Sagaforge
main, and publishes only Windows assets. Mac builds and website updates are
manual. There are no repository Actions secrets/variables configured in either
Warband or Saga Online at inspection. Both repositories are public, with
administrative access available through the local GitHub CLI.

The current site installer swaps its symlink without a transaction/rollback
around the public verification. The compatibility gate currently uses protocol
and game IDs, which are too weak to establish equivalent rules/state.

Saga Online's environment also has conflicting exact engine requirements:
its own/Shardbound pin is 0.3.1 while current Warband/Tribes pin 0.3.2. Site
publication should have its own small dependency environment, independent of
installing every hosted game; server dependency alignment belongs to the
separate compatibility rollout and must not be hidden by ignoring lockfiles.

## Primary references checked

- [GitHub concurrency and workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub runner architecture](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Windows 2025 runner tools](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
- [Triggering workflows and token restrictions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [Saga Online distribution plan](../../saga-online/docs/game-distribution-plan.md)

## Evidence and status

Implemented locally so far:

- `tools/ci_release.py prepare` records one clean source commit, the committed
  sibling/Python/uv pins, the exact locked engine and the lockfile digest. It
  keeps retries byte-identical and refuses to rebind an existing run identity.
  Six CLI integration checks using real temporary Git repositories pass,
  including dirty/untracked source, a stale engine lock and a moving sibling.
  Preparation also succeeded against the actual committed candidate checkout.
- The branch-check workflow now consumes those pins with read-only permissions
  and pinned Actions. Its changed workflow passes Actionlint 1.7.12. A fresh
  environment resolved with the exact CI Python 3.13.2 and uv 0.12.10.
- Saga Online has a separate locked `publishing/` environment and a read-only
  website-check workflow. Its 15 existing catalog/site integration tests pass;
  it renders all seven pages, images, fonts and the exact catalog without
  installing the hosted games. Its workflow also passes Actionlint.
- `tools/ci_package.py validate` checks a native candidate against the expected
  identity and committed lock. It requires both distribution formats, verifies
  artifact and regression-log digests, compares archived executable bytes with
  the smoke/native receipts, and requires the platform's install checks and
  captured images. Ten CLI checks pass using deliberately non-executable file
  fixtures, including stale receipts, changed archives/dependencies, missing
  app checks, Windows shortcut/uninstall acceptance and replacing an executable
  while regenerating its checksums.
  These tests verify the consumer, not native Windows/Mac execution.
- `tools/ci_package.py build` checks the actual interpreter, dependency versions,
  editable game/Sagaforge locations and clean pinned commits before testing,
  freezing and verification. It archives the Mac app with `ditto`, extracts
  that archive into a temporary Applications directory, verifies its ad-hoc
  signature and runs its socket/native diagnostics with isolated profiles.
  Only complete accepted evidence produces `candidate.json`.
- The read-only [native workflow](../.github/workflows/native-packages.yml)
  shares one prepared identity between Windows x64 and Apple Silicon jobs and
  independently validates both downloaded candidates on Linux. Actions are
  pinned by SHA; Actionlint passes. No release/promotion job is enabled in it.
- Inno Setup 6.7.1 is part of the shared identity. Windows input validation
  compares the actual compiler engine's version with that pin and records its
  executable digest before/after the build. A runner image upgrade that changes
  the compiler stops the build until a deliberate pin update. The evidence
  consumer rejects an installer made with a different compiler version.
  ISCC's Windows product-version resource is `0.0.0.0`; the second native CI
  run exposed that difference. The check now compiles a minimal stdin script
  with output disabled and reads the engine banner, rather than the launcher
  resource. The corrected path passed native CI in attempt 1 of run `35143620725`.
- The native workflow now locates accepted artifacts within the same run,
  checks their source commit, downloads and revalidates them before skipping
  any rebuild. Successful platform uploads have one stable name per run and
  cannot be overwritten; failed diagnostics have separate attempt names.
  Shared input artifacts are passed by ID, so rerunning failed jobs can consume
  their successful dependencies' original outputs. The real full-run retry exposed lost prior-attempt artifacts (details below).
  A retry now refuses to rebuild when accepted artifacts are unavailable; durable
  publication recovery still needs to be connected before production.

### Local native Mac evidence

Source `6ecd2ed6538b5e58398ec289d18339d0e3febe70`, local test identity
`0.2.0-preview.35100000125`, Python 3.13.2 / uv 0.12.10 / Saga2D 0.3.2 /
Sagaforge `2fa6fadfd28e2457f2f264b7b071cac7f7566ee5`:

- Full suite: **860 passed, 12 skipped**, one intended stale-painted-sheet
  warning, 157.79 seconds. The added Windows evidence-format check subsequently
  passed with the complete 16-test CI-helper selection.
- Extracted portable and installed app: socket acceptance, native rendering,
  clipboard join, live match menu and settlement planning passed. The app's
  extracted signature passed `codesign --verify --deep --strict`. All 18 native
  captures were inspected (title, multiplayer/code/paste, online match,
  training/plans/menu, offline match); fonts, art and controls rendered.
- Initial native verification stopped because Cocoa reported no available
  display. Waking and holding the display with `caffeinate -u -d -i` allowed
  verification of the **same** frozen portable bytes, then the app archive.
  CI uses that display assertion. No failed receipt was accepted.
- Portable ZIP: 139193756 bytes, SHA-256
  `e4338c88b2a518eaf5ec3cdec4369a1c3697786e3c202fd89a7eb220573af07f`.
  App ZIP: 135488376 bytes, SHA-256
  `c52e4a2407885063cb252785c06e268220e1f54364d4eea0814019a773f220e7`.
- The source host was Apple M4 / macOS 26.6.2. This establishes local native
  behavior, not the minimum supported macOS version or GitHub runner behavior.
  Receipts, regression log and captures are retained under
  `docs/evidence/ci-publication/mac-6ecd2ed/`; archives remain under
  `dist/ci-acceptance/mac-35100000125/` in the implementation worktree.

Still required: actual native GitHub runs (including the Windows compiler check),
exercising accepted-artifact reuse across retries, immutable binary publication,
compatibility-gated catalog promotion, transaction/rollback implementation,
scoped credentials, approved activation and a verified actual main-push journey.
The existing Windows publication workflow is not yet changed. No production
credential, live server or public download has changed as part of WB-002.

### Native GitHub evidence and the retry finding

[Run 35141350074](https://github.com/ikamensh/warband/actions/runs/35141350074)
at `5edb8366052d86c980a9ab5de45e85231d8718e8` passed both native runners and the
independent Linux validator. Each native suite passed **861 tests, 12 skipped**
with the intended stale-sheet warning (Windows 506.52 s; Mac 321.32 s).
The extracted portable packages, installed Windows executable, Windows shortcut
and uninstall, and extracted Mac app all passed their required checks. Windows
used test-only llvmpipe; Mac reported Apple Software Renderer. All 27 downloaded
PNGs were inspected. Art, bundled fonts and the tested controls render correctly;
the existing training hint extending beneath the right card and the match-intro
banner beneath overlays remain visual polish observations for WB-013.

All four downloaded distributions were independently rehashed against their
receipts. Evidence is retained locally under
`docs/evidence/ci-publication/github-35141350074/`; the binaries remain under
`dist/ci-acceptance/github-35141350074/`.

| Distribution | Bytes | SHA-256 |
|---|---:|---|
| Windows portable | 144478511 | `4e3a9206a6603d1ea04ead266d2fced464833308afcde9587d835fcd255ba9a9` |
| Windows installer | 136071306 | `bc9803cbef1c860891c475988599e4a610e1e2271acf1ae109bcb32847870ed8` |
| Mac portable | 139339028 | `15c43da7fe6a6ce19e0d687bade59e2074ae0d2bd6921103199237395864de2a` |
| Mac app | 135416986 | `b0ca5fe2f905d0781d2af2f81ec267d10533e1531a977ceb24cf135eaed73681` |

[Run 35143620725, attempt 1](https://github.com/ikamensh/warband/actions/runs/35143620725/attempts/1)
at `70e15ad2841e41b9c0abd1663c557b9f065c379d` subsequently passed both native builds
and Linux validation with the corrected Inno Setup engine check. A full rerun
made accepted artifact IDs `10466364557` (Windows) and `10466113897` (Mac)
unavailable: both the run listing and direct artifact lookup no longer returned
them. The original metadata/digests were saved before rerunning. The rerun began
fresh builds and was cancelled before new candidates were accepted. This is a
failed reuse acceptance check, not proof of idempotence. The workflow now stops
if a later attempt cannot find accepted bytes. Use a new run/version for a new
build; publication must recover from durable release assets when Actions no
longer retains them. Never infer that a missing artifact means no earlier bytes
were accepted.

### Offline release staging and tested publication protocol

`tools/ci_publish.py stage` revalidates both native candidates and assembles four
downloads, two deterministic evidence archives and `release.json`. Repeating
staging accepts only identical output. `publish` revalidates the complete native
evidence before any remote mutation, binds a lightweight version tag to the
source SHA, creates/resumes a draft and downloads every uploaded asset to check
its bytes. It never overwrites a completed asset. Only an empty draft asset in
GitHub's documented `starter` state can be deleted and retried. Publication
requires a complete asset set; a retry of an already published release performs
only reads, and successful output requires immutable status plus unauthenticated
download checks for every asset.

Fourteen CLI/HTTP integration checks cover staging, mixed/incomplete candidates,
lost upload and publication responses, changed local/remote bytes, conflicting
tags/identity, empty versus nonempty failed uploads and corrupt public downloads.
These use a local HTTP implementation of the documented GitHub contract and
non-executable package fixtures; they do not establish the real GitHub release
journey. The command is not connected to a write-enabled workflow yet.

The repository's release-immutability setting was read as disabled. Enabling it
is part of the explicit production rollout, not done here. The runtime checks a
published release's `immutable` flag rather than granting the job admin access
to read or change repository settings. Draft recovery outside Actions retention,
Saga Online's independent consumer, source-order/compatibility gates and the
approved live journey remain outstanding.

API contracts checked against [GitHub releases](https://docs.github.com/en/rest/releases/releases),
[release assets](https://docs.github.com/en/rest/releases/assets) and
[immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

### Publication workflow separation

The write-enabled publisher will run as a separate workflow consuming the
completed native workflow's immutable run ID and source SHA. Rerunning a
publication attempt must not rerun its native producer: native Actions artifacts
belong to that other run and can be downloaded and revalidated again. Native
full-run retries still fail closed if their original artifacts disappear; a new
build gets a new run/version. Complete GitHub release assets provide the durable
copy after publication. Recovery must never interpret missing native artifacts
as permission to regenerate a version that has already been staged or published.
This wiring and its real failed-publication retry remain to be implemented and
verified before WB-002 can pass acceptance.

### Review limits

An implementation review through the local `second-opinion` CLI was attempted.
The configured Google and OpenAI keys were rejected; the primary Anthropic
account reported insufficient credits. No outside-review answer was obtained for
this publication increment. Local self-review, the integration checks and actual
native CI evidence above remain the available validation; the earlier WB-001
outside review does not cover this code.

### Verified staged release from the latest native build

[Run 35145401921, attempt 1](https://github.com/ikamensh/warband/actions/runs/35145401921/attempts/1)
at `7970b18e2e0c4a9bedc58a3d89d6453c8fb6afb9` passed both native builders and Linux
validation. Each platform passed **875 tests, 12 skipped**, one intended warning
(Windows 494.71 s; Mac 410.76 s). The ordinary Tests workflow also passed.
Both artifact sets were downloaded and preserved before the deliberate rerun.
Representative Windows title/planning and Mac portable/app match captures were
inspected; rendering agrees with the earlier native evidence.

The actual `ci_publish.py stage` command accepted these real native artifacts,
and the publication entry point's offline inspection revalidated the complete
staged files and receipts. Local binaries/staged release are retained under
`dist/ci-acceptance/github-35145401921/`; receipts, images, the manifest and
inspection result are under `docs/evidence/ci-publication/github-35145401921/`.
No release was created or published in GitHub.

| Distribution | Bytes | SHA-256 |
|---|---:|---|
| Windows portable | 144477557 | `f4ebc9963821292ab4e8cc3e8ddfdf03628131161682743c9be0c40723fade9c` |
| Windows installer | 136065756 | `e5be4e180bb0a0e051217424cdb90f0e7eb3301acf776f203978fda7de6cda22` |
| Mac portable | 139337879 | `8dc502ea3097165698125280bebce6347bbb3c36d6401b42971d502940b36597` |
| Mac app | 135415834 | `6ccbce72057406d032dc8e82d77574c74f41cc7b8671e4562bd99953611e80e4` |

The staged `release.json` digest is
`ce280828eeae3c79a3da3d789249cfedda9df813250b35f7c6144c8954e496a3`.

The final staging format stores evidence ZIP entries without recompressing them,
with fixed timestamps, permissions and creator OS. This removes host/zlib
variation across publication retries. Thirty focused integration checks still
pass, including restaging after source-file metadata changes. The real native
artifacts were staged and inspected again in `release-final/`; the manifest
digest above refers to that final format. This small archive-format change was
verified locally after the 875-test native run; it does not rebuild game binaries.

[Attempt 2](https://github.com/ikamensh/warband/actions/runs/35145401921/attempts/2)
then exercised the missing-artifact safeguard. Both native jobs failed at
“Find already accepted bytes from this run” with “Refusing to rebuild this
version”; both actual build steps were skipped. Logs and step results are saved
in the same evidence directory. The workflow's latest red status is this
intentional refusal test; attempt 1 is the successful native build. This proves
safe refusal, not successful publication retry. The separate publication
workflow and end-to-end promotion remain unfinished.

### Separate producer/publisher wiring

`publish.yml` now consumes a successful main native run through `workflow_run`,
or accepts that producer run ID through manual dispatch for publication retries.
`ci_source.py` reads provenance from GitHub's API: repository and head repository,
main branch/event, the exact native workflow ID/path, all four successful jobs,
and both unexpired artifacts bound to the same source commit. It follows API
pagination. Thirteen CLI/HTTP checks reject untrusted, incomplete or mismatched
sources; all 43 focused release checks pass. The changed workflow passes Actionlint.

Preparation downloads from the separate producer run and stages exact accepted
bytes. Only a main-ref job with `WARBAND_PUBLISH_ENABLED=true` enters the
`warband-release` environment and obtains `contents: write`. It revalidates the
staged release, publishes/verifies its immutable bytes, retains the receipt, and
requests Saga Online's `warband-promotion.yml` via a token scoped to Actions write
in that repository. No repository settings, environment, secret or enable flag
has been changed. The new workflow has not yet run from the default branch;
actual separated-run retry and publication remain required acceptance evidence.

### Compatibility implementation boundary

Before implementing compatibility promotion, separate the authoritative match
rules/registration from the multiplayer scene. The compatibility digest will
cover that authority module and its transitive game-code imports, plus the exact
engine release and relevant runtime dependency versions. Cosmetic-only modules
must not change it; rule, state, order validation, map generation and automatic
worker behavior must change it. A new local import must join the digest without
an operator remembering to edit a manual file list. Unsupported dynamic imports
or external data in this path must fail clearly rather than silently omit input.

The server's reviewed baseline will record this digest and exact deployment
identity. Promotion will require a matching live baseline and packaged socket
checks; a digest mismatch requires the separate room-draining/server rollout
already specified above. This is deliberately conservative: it proves identical
relevant inputs, not a claim that arbitrary different rules are compatible.

### Authoritative compatibility contract

`warband.authority:ONLINE` is now the server/package entry point. `WarbandMatch`
and the create/checkpoint/restore functions were moved without changing their
ASTs; multiplayer scenes remain in `warband.multiplayer`. Importing the server
registry does not import those scenes or artwork. All game, package and test
callers use the new entry point. Saga Online's service/check scripts and the
stack-root `make server` command must change to the new registry when these
branches are integrated; the deployed server has not changed.

`tools/ci_compatibility.py` computes a contract offline from the static import
closure rooted at the authority module, including package initializers,
relative and function-local imports. It follows Python's preference for a
package over a same-named module. Every included source byte contributes; a
comment-only edit can conservatively require reapproval. Client scenes/artwork
do not contribute unless authoritative code starts importing them. Python
sources are checked out as LF on every platform for consistent native hashes.

The contract also includes the pinned Python version and exact PyPI versions
of Saga2D and its transitive runtime dependencies. This is the required runtime,
not a claim about the Python used to run the inspection CLI. A server baseline
must verify its actual interpreter and installed dependencies against this
contract. The existing deployment cannot be declared compatible by copying its
game ID or by recording these desired pins without checking the server.

Imports outside the supported simulation standard-library set and the small
engine registration interface fail explicitly. Dynamic loading/execution and
file-reading forms are rejected; new external rules/data need explicit contract
support. These source conventions are not a sandbox for hostile Python or a
proof against arbitrary reflection. Reviewed code plus the trusted producer's
full regression and packaged socket checks remain necessary.

Release preparation now embeds the full contract in the immutable identity.
Native build/validation and publication staging recompute it from the exact
source checkout. Matching supplied receipts cannot substitute a different
contract. The first live baseline, compatibility-gated promotion and actual
separated publication retry are still pending; WB-002 remains in progress.

Local verification: 900 tests passed, 12 skipped, with the expected stale-sheet
warning (`docs/evidence/ci-publication/authority-regression.log`). After the
package/module resolution regression was added and corrected, all 56 focused
compatibility/release/source/publication checks passed again. The existing
real-socket multiplayer/online selection passed 38 checks including the initial
compatibility cases. Native Windows/Mac verification of this refactor is next.

### Native acceptance of the authority refactor

[Native package run 35149564980](https://github.com/ikamensh/warband/actions/runs/35149564980)
passed all four jobs on `2361f79cecf5a584562847bdc25e2be4d2f353c8`.
Windows and Mac each passed **901 tests, 12 skipped**, with the expected
stale-sheet warning (537.76s and 291.02s respectively). Portable and installed
socket checks, native input/clipboard/menu/planning checks, Mac app verification,
and Windows shortcut/uninstall checks all passed. The separate regular
[Tests run 35149564991](https://github.com/ikamensh/warband/actions/runs/35149564991)
also passed. Native graphics used the runners' software renderers; this is not
physical-GPU or listening acceptance.

Both complete accepted artifacts were downloaded and independently validated
locally against the producer identity. The producer's identity exactly matches
local preparation from that committed checkout, including compatibility digest
`ffdfe856c27cf2c9d7f507d9e1caa54e631d41cdb283e367c2e08b954bd49524`.
Staging and inspection passed on the actual four binaries and both evidence
archives. The staged `release.json` SHA-256 is
`f9587ae7c6d38eb6fbabfdaca6fea15b0aac22fc4bca893bbfded79ef88bc303`.
Receipts, logs, file digests and captures are under
`docs/evidence/ci-publication/github-35149564980/`; the complete downloads and
staged release are under `dist/ci-acceptance/github-35149564980/`.
The Mac online-match/app-plans and Windows title/plans captures were inspected.
The existing intro-under-overlay observation remains for WB-013.

This was a branch run; no GitHub game release or hosted promotion occurred.
The separate publisher must still be exercised from main after coordinated
integration. The first server baseline is also pending: Shardbound's isolated
0.3.2 alignment candidate `cc070e3` has 19 failures that all reproduce on 0.3.1,
plus the same incomplete native verification journey on both engines. Those
findings are recorded in its release guide and Saga Online's publication plan;
neither that candidate nor the shared server has been accepted or deployed.

### Shared server package acceptance

Saga Online now builds a clean pinned server package with this native Warband
source and compatibility contract. Its deployment launcher verifies actual
source hashes and runtime versions before opening game sockets and serves the
live compatibility response from that same process. The candidate package
passed all three games' real orders, SIGTERM checkpoint flushing and private-seat
rejoin locally and on Ubuntu 24.04. The Linux run also exercised the actual
installer preparation command as root, verification as the unprivileged service
account, and an unchanged-release retry.

[Server Tests 35158657345](https://github.com/ikamensh/saga-online/actions/runs/35158657345)
passed all 103 checks without skips on Saga Online `126f220`. The downloaded
server archive is byte-identical to the Mac build, SHA-256
`cce03f0b961a05269c364a840274cf9a505d9ed46e062d0177c7a2baf2f03a10`.
The [server publication record](../../saga-online/docs/warband-ci-publication.md)
contains the exact inputs and evidence. This accepts server package preparation;
Shardbound's existing client failures, common server/site locking, production
rollout and public packaged-client acceptance remain outstanding. No main push,
release publication or live deployment was performed for this milestone.
