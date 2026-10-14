# Match ownership

The match scene presents a match and translates input. Its mutable execution
and durable record have separate owners:

| Owner | Responsibility | Interface used by the scene |
| --- | --- | --- |
| `ui.match.MatchExecution` | Displayed world, pause, pace, fixed-step clock and dropped time | `advance`, `world`, `fraction`, `paused`, `speed`, `stopped`, `behind` |
| `ui.match_record.MatchRecord` | Run identity, recording, profile, rating, high scores and autosave cadence | `start`, `leaving`, `resign`, `conclude`, `keep_score`, `save_state`, `restore_clock`, `autosave_due` |
| `ui.scene.GameScene` | Input, selection, camera, HUD, audio/effects and scene transitions | The player's commands and the presented state |

`LocalMatch` owns the brains and their random stream. One frame gives every
brain a turn before each fixed simulation step. A playing seat stops when it
is eliminated; an observer keeps watching until a winner. Missions supply the
brains for their scripted sides. Slow frames keep the existing six-step cap
and report discarded match seconds through telemetry.

`ReplayMatch` owns recorded-order playback, speed changes and bounded skipping.
A reload can replace its world. The only rendering hook receives the world
about to step; the scene resets its remembered view when that identity changes
and takes interpolation positions before the step. `RemoteMatch` never steps
its snapshot world: the room continues to own decisions and time, including
while a local menu is open. Snapshot interpolation remains in the network
presentation, where arrival times are known.

Neither execution nor the record receives a scene. Execution receives only a
pre-step callback and telemetry phase context manager. The record receives the
current world and its data directory, and returns storage notices for display.
This keeps the same execution usable without a window and prevents recording
or rating from depending on HUD fields.

A scene's save state combines the record's match metadata and serialized world
with presentation state: groups, tutorial progress, remembered sightings and
camera bookmarks. Save validation and restored run identity live with the
record; choosing a skirmish scene or a campaign scene stays in `load_game`.
Autosave deadlines are match time, resume at the next interval after a load,
and are disabled for observers, network scenes and replays.

`test_match_execution.py` checks clocks, direct-versus-framed AI decisions,
observer elimination, remote authority and replay reloads. `test_match_record.py`
exercises actual profile/replay storage, run identity and autosave resumption.
The scene, campaign, replay, rated-match, storage and frame-telemetry tests
exercise their integration through the game loop.
