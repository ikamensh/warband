# Short automatic release versions

Started 2026-09-17 after user approval. This is a focused publication change;
the game-feature backlog remains paused after WB-004.

## Acceptance recorded before implementation

- New public versions are plain MAJOR.MINOR.PATCH, starting at 0.2.1.
  Package names, embedded versions, tags and the live catalog must agree.
- Derive the patch from the native workflow's small run counter, anchored in
  committed release pins. Keep its large run ID and source SHA as metadata.
  Retries preserve identity and accepted bytes; failed/branch runs may leave
  gaps. Only verified main builds are published.
- Independent publication resolves the producer's counter from GitHub, never
  from the publisher's own run or an untrusted archive. Preserve native,
  archive, source and server-compatibility gates and reject version rollback.
- Existing immutable preview releases remain intact. Transition the live
  catalog forward to the new scheme and preserve exact-version retry checks.
- Present Early access independently of the numeric version on the website.
  Inspect the actual rendered page before accepting that wording change.
- Exercise real CLI/Git/HTTP integration paths for numbering, retries,
  conflicting identity, invalid counters and promotion ordering. Require both
  native platforms, CI publication/promotion and public download checks before
  calling the rollout complete.

## Numbering

`patch = project base patch + native run number - version_run_base`.
The initial project base is 0.2.0 and the committed counter anchor is 25;
native run 26 therefore produces 0.2.1. This needs no write token, remote
counter, reserved tag or automatic version-bump commit during packaging.
GitHub keeps the run number fixed across retries. Branch verification uses
the same counter, so public versions need not be consecutive.

For a deliberate minor/major milestone, change the project base and set
`version_run_base` to the intended first build's run number to start at .0.
Check the most recent native run number first. Never move the anchor alone to
reuse an existing version; promotion must reject older or rebound versions.

The numeric version is separate from release maturity: this remains an early
access game and the existing unsigned/notarized build notices remain honest.

## Rollout checks

Local release CLI/Git/HTTP checks pass, as do 115 independent publication,
website and activation checks. The local website preview was rendered and
inspected: Early access and Version are separate, and download labels are short.

The first native candidate (run 26, 0.2.1) was cancelled before publication:
Linux Tests run 35269801032 exposed its separate setup step still calling the
old CLI. That job only needs committed dependency pins, so it now reads those
directly rather than constructing a native release identity from its unrelated
workflow counter. A regression executes the actual Linux setup block with an
independent counter below the native version anchor. The failed candidate's
version is not reused; the next native run produces 0.2.2.

## Completed public acceptance — 2026-09-17

The first published short version is **0.2.2**, from Warband
`f6e3b28c447017c85145c9dcb56b794da09bc053`, native run number 27.

- [x] The 51 local release CLI/Git/HTTP checks passed. Linux
  [Tests 35270068163](https://github.com/ikamensh/warband/actions/runs/35270068163)
  passed 1,054 tests with 12 skips. Saga Online `5da5fbe` passed
  [142 server/publication checks and real host acceptance](https://github.com/ikamensh/saga-online/actions/runs/35269772417)
  and its [website checks](https://github.com/ikamensh/saga-online/actions/runs/35269772371).
- [x] Both native platforms and combined artifact validation passed in
  [build 35270068161](https://github.com/ikamensh/warband/actions/runs/35270068161).
  [Publisher 35271641922](https://github.com/ikamensh/warband/actions/runs/35271641922)
  succeeded on its first attempt and created immutable
  [release v0.2.2](https://github.com/ikamensh/warband/releases/tag/v0.2.2)
  (release ID 391043050). Its manifest SHA-256 is
  `0b8aef83704c275a2639456cc6cfde1e500f6d3d62ba44c1731521b87e049a3b`.
- [x] Automatic [promotion 35271825201](https://github.com/ikamensh/saga-online/actions/runs/35271825201)
  independently verified the release, committed catalog `d0ad911` and activated
  site `3abd8bdea211c66966211d75c246cf660bb1b5b08792ca484be5552e99123f19`
  at generation 10. The prior site remains available for rollback. The server
  compatibility fingerprint is unchanged, so no room-server refresh was needed.
- [x] The actual [public page](https://games.tachyon-ai.eu/warband/) was opened
  and its screenshot inspected: Early access is separate from Version 0.2.2;
  all four download labels and filenames use the short version.
- [x] Fresh anonymous Windows/Mac downloads passed
  [public acceptance 35272034238](https://github.com/ikamensh/saga-online/actions/runs/35272034238).
  Archive hashes, embedded source/version, executable identity and bundled fonts
  matched; all eight live online checks passed from fresh user directories.

Evidence is retained under `docs/evidence/versioning/` in both repositories,
including native input identity, logs, public manifest, activation receipt and
both public-client receipts. This completes the separately approved versioning
change; backlog execution remains paused after WB-004.
