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
