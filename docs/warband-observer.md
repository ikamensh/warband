# Watching AI-only matches

Skirmish / New game offers **Play** and **Observe** beside Watch/Start. Observe
keeps the seed, race, difficulty and map, but every seat plays itself at the
chosen difficulty: one real brain per seat, no human seat, and nothing is
rated, recorded, autosaved or scored.

## Controls

- The speed button in the Watching strip reads the pace (`1×`, `1.2×`,
  `1.5×`, `2×`, `3×`); click it to cycle 1 → 1.2 → 1.5 → 2 → 3 → 1.
  `PgUp` / `PgDn` step bounded through the same paces without wrapping.
  Played matches stay at 1×.
- `[` / `]`, or the `<` / `>` buttons: inspect the previous / next seat. The
  top bar, stores and codex follow the viewed seat; the camera stays put.
  A fallen seat stays watchable; the match ends only at a winner.
- Clicks and boxes select any side's forces to inspect them. The right button
  selects too. Camera, minimap, `F3` pause, `F10` menu, settings and `F1` help
  work as in a played match. The key bar and selection panel say so: no build
  / train / rally / cancel instructions while watching.

## Restrictions

- Orders, catalogues, aims, cancel mode, settlement plans, adjutant commands,
  train / build / research / spells, saves and resigning are refused (the
  order rows, spell bar and command card are hidden, not just blocked).
- Leaving from the pause menu costs nothing: there is no rating to protect
  and no LeaveScene. The result names the winner (`<name> wins`) with every
  side's fate; never "you won/lost".
- Notices stay honest from every seat: loss toasts name the owner's race,
  distant casts still burst, and the key bar promises inspecting, never orders.
- Pace scales the fixed-step accumulator only; the step, rules and brains run
  unchanged, so replays and fingerprints are untouched.

## Reuse seam for network observers

`warband/ui/observer.py` holds the read-only behaviour in `WatchScene`
(a `GameScene` subclass): revealed whole-map view, fog-free audibility,
owner-named loss toasts, all-seat selection, blocked order/plans/save/resign
paths, null adjutant, winner-only ending, unrated pause menu and result.
`ObserverScene` adds the live world (all-seat brains, `_steps_running`
without the played match's side-alive gate, pace controls). A network
observer reuses `WatchScene` and only feeds the world another way
(snapshots at fixed 1× authoritative time: override `_fill_pace` for its
own pace display).

## Network observer presentation

`WarbandMatch.observer_snapshot()` is the authority's presentation snapshot for a watcher:
the same `{seed, world, events}` envelope a seat receives, describing the whole current map and
every faction. It loads through `World.from_dict` after a JSON wire round trip, for a viewer to
look at — never to step, order, or restore the running match.

Watching is a deliberate omniscient role, not a third seat. The observer sees current
units, buildings, projectiles, camps and regrowth, the ground as it stands, and every
seat's purse, research and scores. Recent news of every kind rides along except a seat's
own affairs (`PRIVATE_EVENTS`): blows no seat saw are the observer's, alarms and refusals
never are.

What would let the snapshot stand in for the authority never travels: the random stream
(`NO_DICE` stands in, as for a seat), each seat's explored ground and worker memory, the
settlement's plans, unit intentions (`STRANGER_UNIT`, as for a stranger), and a camp's
damage ledger and timers. The envelope carries no checkpoint keys (`event_id`, `event_seen`,
`begun`) and no session or account credentials — there are none on the match to leak.
Taking it changes nothing: fog, seats, time, the stream, the seat snapshots and the
checkpoint read the same after. Covered by `tests/warband/test_observer_snapshot.py`.

## Network observer: Online and LAN

Multiplayer offers **Observe room** beside Join, on the same code/address
entry, for Online rooms and LAN hosts. Observing takes no seat: the lobby,
a full running room and a finished room all open read-only, without
changing readiness, ratings or seats. The scene is `NetworkObserverScene`
(`warband/ui/multiplayer.py`), a `WatchScene` fed by the shared
`_apply_network_state` seam, so arrivals land exactly as on a playing seat.

Controls match local watching — clicks inspect any side, `[` / `]` (or
`<` / `>`) change the followed seat — except the pace strip reads `1× live`
(the room's own clock; nothing to pause) and `F10` opens the watcher's menu
(settings, help, stop watching, quit). Orders never travel, so there is no
Idle count and `Tab` says why; a selected unit's card names its observed
state instead. A viewed seat's refusals and alarms never present as the
watcher's. The watched seat may fall: watching continues, and only the
room's winner ends it. The result names the winner and every side's fate
and scores, never AI difficulty and never you won/lost.

Watching writes nothing: no identity token or profile, no last-room seat,
no fog memory — the player's saved files stay byte-for-byte intact, and a
damaged identity record neither blocks nor changes observing. Leaving
closes the watch only; nobody resigns. Watching again is a fresh Observe;
a dropped transport reconnects in the observer role. Covered by
`tests/warband/test_network_observer.py` (LAN live, Online slow).
