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
7. Configure scoped CI credentials and enable production only after the
   concrete changes, artifacts and rollout commands are reviewable. The stack's
   AGENTS.md requires approval for hosted deployments and game publication.
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
  compares the actual compiler's product version with that pin and records its
  executable digest before/after the build. A runner image upgrade that changes
  the compiler stops the build until a deliberate pin update. The evidence
  consumer rejects an installer made with a different compiler version.
- The native workflow now locates accepted artifacts within the same run,
  checks their source commit, downloads and revalidates them before skipping
  any rebuild. Successful platform uploads have one stable name per run and
  cannot be overwritten; failed diagnostics have separate attempt names.
  Shared input artifacts are passed by ID, so rerunning failed jobs can consume
  their successful dependencies' original outputs. Real rerun verification is
  still required; Actionlint alone does not establish retry behavior.

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
