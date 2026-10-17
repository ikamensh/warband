# Keeping older clients playable

Online compatibility is independent of the release number. Human clients,
headless AI clients and the authority share `warband.online.protocol.GAME_ID`
(currently `warband-v2`). Saga2D's transport protocol is tracked separately.
Keep both identities stable while existing clients can still play.

The server simulates the match; remote clients display snapshots and submit
orders. Clients do not need identical simulation source or deterministic
results to play on that server. They do need to understand its snapshots,
content and command semantics. LAN hosts run their own authority and use the
same game identity.

## Decide what a change does

| Change | Compatibility decision |
| --- | --- |
| Art, sound, campaign, local AI, release number | Compatible unless it also changes an online interface. |
| Simulation fixes, internal refactors, map generation | Usually compatible if existing snapshot values and orders keep their meaning. |
| Balance numbers | Review: the server owns outcomes, but clients use local costs, ranges, prerequisites and timing in the HUD. A change that makes old clients unable to issue valid orders or play correctly needs adaptation or a break. |
| Extra optional snapshot field | Compatible only when old decoders ignore it and new decoders accept its absence. |
| Removed/renamed field, different type, changed positional event/order fields | Breaking unless an adapter preserves the old representation. |
| New unit, building, race, spell, condition, terrain or other enum value | Breaking if it can reach a client whose catalogs or artwork cannot interpret it. Optional features need explicit negotiation before being sent to old clients. |
| New optional order/room option | Compatible if old clients still work and old servers safely handle new clients; do not silently change defaults or required options. |
| Transport change | Review the pinned engine; an incompatible transport requires a new protocol and game identity. |
| Checkpoint/save change | Separate persistence concern: restore old rooms or migrate them. A network epoch does not make saved rooms safe to discard. |

Prefer preserving a field, accepting an old order, or adding a small adapter
when that keeps old clients functional. A source edit alone never proves a
break. Do not register an old game ID as an alias for an incompatible match.
Supporting multiple epochs requires a real compatible adapter or separately
pinned authority for each, plus old-client and checkpoint tests.

## Record the decision

`.github/network-compatibility.json` retains explanations, reviewed input
hashes and pinned representative client sources/engine versions. The initial
matrix retains v0.2.232 (`a987830`, October 2, Saga2D 0.3.14) and the current
v2 client (`c9d74d8`, Saga2D 0.3.18). Both passed actual player play/resume and
event decoding against the current authority; the newer client also passed
observation. The older transport predates that optional capability. These
representatives establish a tested baseline, rather than proving every
intermediate historical release.

Earlier releases reused v2 despite real breaks. For example v0.2.211 predates
`ddbd24a` (October 1), which introduced `ancient_guardian` and `Event.amount2`.
That client cannot decode all current units/events. v0.2.199 additionally lacks
the Mage Tower, nine spells, Aether Elemental and seven conditions. They are
not claimed as supported; they would need real adapters before being added to
the matrix. Future changes of this kind require a recorded break or a
compatible representation.

After changing authoritative code/content/runtime or a tracked client
consumer, inspect the diff and record the decision:

```sh
uv run python tools/network_compatibility.py record --effect compatible --reason 'Explain why existing snapshots, catalogs, commands and options still work'
uv run python tools/network_compatibility.py check
```

A breaking change first increments `GAME_ID` (for example to `warband-v3`),
then records `--effect breaking` with the concrete incompatibility and why
preserving the old interface was impractical. A compatible change cannot
change the identity, and a breaking decision cannot reuse it. Do not change
Saga2D's transport number unless the engine itself changes its protocol.

A deliberate new game ID also needs coordinated Saga Online changes. Its
[catalog writer](../../saga-online/tools/warband_promotion.py), deployment
preparation/smoke checks, retained-room rehearsal and public acceptance tools
currently name `warband-v2`. Search that repository for the old ID and update
the active callers and their tests for the planned epoch. Follow its
[automatic rollout procedure](../../saga-online/deploy/README.md); the new
epoch must pass create/join/resume and retained-room checks before promotion.
Keep actual adapters or migrations for any older rooms the release retains.

Keep previous reviews and client pins. CI compares this history against the
push/PR base and checks the latest hashes against the actual checkout. A
compatible change in a new epoch requires a pinned representative release of
that epoch. The first breaking release has no historical client in its new
epoch yet; add its immutable source/engine pin once published, before the next
compatible change. Prior epoch pins remain in history even when unsupported.

## Verify older clients

The native package workflow tests every retained client before accepting its
release identity for packaging. It extracts immutable client sources from Git
and installs each client's pinned Python, engine and locked dependencies
separately from the current server. To run that complete gate locally:

```sh
uv run python tools/check_retained_clients.py
```

To probe an existing historical source checkout with the current interpreter:

```sh
uv run python tools/check_network_client.py --client-source /path/to/old/warband
```

Use `--client-python /path/to/old/venv/bin/python` to select its historical
engine too. The check uses the old source's actual world/event decoders and
online transport, compares content
catalogs, and exercises create, join, move, observe and resume over real
WebSockets. Decoder and protocol failures fail the job. These are headless
compatibility checks, not exhaustive native UI or whole-match coverage. New
features still need their own meaningful regression tests and the review
above. Add representative release pins when an engine or decoder changes;
retain the oldest tested client in each supported epoch.

## Deployment provenance stays exact

`tools/ci_compatibility.py` still hashes the full authoritative source and
runtime. Saga Online uses that digest to deploy and attest the exact published
server, including compatible rules fixes. A different digest means the server
needs deployment; it does not mean clients must update. Admission continues to
use the transport protocol, game ID and existing seat capability checks.
The server's ordinary backup, retained-room rehearsal and rollback checks
still apply to every deployment.
