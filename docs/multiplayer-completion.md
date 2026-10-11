# Multiplayer completion

Warband's multiplayer path is a first-class game mode: open Multiplayer, set
up a room or paste an invitation, meet the other players in the lobby, play,
and return with an authoritative result. Offline skirmish ratings remain a
separate record.

## Acceptance

- The title puts Multiplayer first and keeps skirmish, campaign, saves,
  replays, profiles and help reachable.
- Multiplayer owns its room settings: two to four players, map size and
  layout, season, race and magic. Opening it does not depend on offline
  settings. LAN is an explicit secondary mode.
- The online lobby shows actual connected seats, names and ratings; only
  room codes and public invite links are shareable.
- An identity is server-issued and persists privately on the client per
  endpoint. Its display name is not its credential. The local AI rating is
  never presented as an online rating.
- Ranked results come from the server's game result hook. A stable match ID
  makes accounting idempotent across repeated snapshots and restarts.
- Two to four players can play ranked. A winner is rated against each other
  participant; losers tie. Changes are normalized to the field size. Casual
  and LAN matches do not change online ratings.
- Reconnection retains the seat, identity and match. A ranked player absent
  past the grace period forfeits when an active rival remains. A lobby that
  never started and a match with nobody connected do not fabricate a winner.
- Public status and rating queries contain no private seat or identity
  tokens, orders, fogged state or room codes.
- `warband --server-info` and its JSON form run without a window or compiled
  simulation. Failure is explicit and returns a nonzero exit status.
- Remote AI clients on separate Scaleway computers use the public TLS
  endpoint, seat snapshots and validated player orders. Acceptance observes
  authoritative progress, reconnect and a complete result, checks rating
  persistence, and retires the task's temporary cloud resources.

## Verification

Use real client/server integration tests for identity, room creation and
joining, result accounting, reconnection, forfeit and server restart. Exercise
the CLI in a subprocess against an HTTP server, including malformed and
unreachable responses. UI tests drive the exposed controls and check settings
that actually reach the authority.

Inspect real screenshots of the title, multiplayer form and lobby, then walk
those screens with `tools/visual_lint.py`. Run the relevant slow tests and the
fast suite on the finished integrated code, plus the scene-input fuzz gate.
Publish the verified engine, deliberately update exact game/server pins and
lockfiles, and activate the server through the automatic rollout. Finish with
public endpoint and remote-client acceptance on the deployed candidate.

Retain only the useful final reports and frames under
`~/saga/evidence/warband/multiplayer-*`, with their source commits and
reproduction commands. A local test or a rollout request is not evidence that
the public service passed acceptance.
