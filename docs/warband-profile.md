# Warband player profile, rating and replays

The title screen carries the player's card: name, rating, record and the
last few results, with **P** opening the profile. Every offline match against
the computer is rated when it ends — or when the player leaves it — and its
replay is kept. Online matches are neither rated nor recorded.

## The rating

The rating is on the Elo scale the difficulty settings are measured on
([docs/ai-ladder.md](ai-ladder.md)): Easy 740, Medium 1000, Hard 1250, Master 1510 at the time of writing (`warband.brains.ai.DIFFICULTY_ELO`). It is an
*estimate*, so it is updated by Glicko rather than plain Elo and shown with
its deviation: a new player starts at **1000 ± 350** and is *provisional*
until the deviation is under 150, which takes about five matches. Each match is
one observation against the difficulty played (a free-for-all against two or
three computer players of one difficulty is still one observation). The
difficulty's rating is stored with the result, so re-measuring the AI later
does not rewrite old results.

The profile stores the results themselves and folds the rating from them at
every read. A second result for the same match — a match left and then
finished from its autosave, or a saved position replayed to a different
ending — replaces the first, and the rating is re-folded consistently. The
results screen says when that happened.

## Leaving a match early

Resign, New game, Back to title and Quit on the pause menu ask first while a
rated match is undecided, and the confirmation states the cost before the
player chooses. The rule the user asked for:

| The player leaves… | Counts as |
| --- | --- |
| under attack: a blow landed on their units or buildings within the last 20 s, or an enemy fighter stands within 8 tiles of one of their buildings | a full loss |
| behind in material: their living units and finished buildings, at cost, are under 90 % of the strongest living rival's | a full loss |
| otherwise: nobody at the gates, no material disadvantage | **0.2 of a loss** |

A fraction of a loss is a fractional observation: it moves the rating by
about that share and narrows the deviation far less. Being eliminated is a
full loss whatever the standing. Closing the window is not leaving: the
autosave continues the match. Loading another save of the *same* match is a
rewind, not a departure.

## Replays

The simulation is deterministic to the float bit (lockstep online play needs
that), so a replay is the world the match began in plus every order given
since, at the tick it was given — the player's orders and the computer
players' alike — and the digest of the world at the end. `World.orders`
collects them through the `@recorded` wrapper on the order methods; the
brains' worker assignment is an order for the same reason. Nothing that
happens *inside* a step is logged. Loading a save mid-match rebuilds the
world from its dictionary; a `reload` row marks the moment so playback does
the same, and a save carries the recording so far.

Replays live under `~/.warband/replays/`, one JSON file per match, written
with Saga2D's atomic saves. The profile screen lists them beside their
results: **Watch** plays one back, **Delete** removes the file (the result
stays). In a replay **PgUp/PgDn** change the speed (1× to 16×), **F3**
pauses, **End** skips to the end, **F4** switches between the whole map and
the fog as the player saw it; orders cannot be given. When the recording runs
out the screen says how the match ended and whether playback matched the
recording — it drifts only if the game's rules have changed since.

## Storage

Everything of the player's lives under `~/.warband` (`%USERPROFILE%\.warband`
on Windows), the same folder for a source checkout and the installed app
whatever directory the game is started from (`Game.data_dir`, derived from
the game's title; the packaged build's smoke receipt records the path it
resolved and CI requires it to be that folder). Files are JSON, written
through Saga2D's `SaveManager`: the new file is staged beside the old one and
swapped in whole, the previous good file is kept as `save_1.backup.json`
next to it, and a damaged current file is reported with its path and never
overwritten or silently replaced by its backup.

| What | Where | Written when |
|---|---|---|
| Name and rated results (the rating is folded from them; `PROFILE_VERSION` 1) | `profile/save_1.json` | a rated match ends or is left; a rename |
| Local top ten | `high_scores/save_1.json` | the results screen of a decided match |
| One replay per rated match | `replays/<match>.json` | the match ends or is left |
| Saved games, quicksave and autosave (`SAVE_VERSION` 2) | `saves/` | F5, the save browser, every two minutes of play |
| Preferences | `settings.json` | the settings screen closes |

The name defaults to the login name and is changed from the profile screen
(up to 16 characters). An interrupted write leaves at most a `.tmp` file
beside the current one, which the game ignores. When the folder cannot be
written at the end of a match, the game says so ("Result not recorded",
"Replay not saved") and goes on; the result is lost, nothing else is.

### Backing up and restoring

Copy the whole `~/.warband` folder somewhere safe; copy it back, with the
game closed, to restore. A damaged profile shows "Profile unavailable" with
the reason on the profile screen (**P** on the title) and a **Restore backup**
button when `profile/save_1.backup.json` exists: it brings the last good
profile back and keeps the damaged file beside it as `save_1.damaged.json`.
For a damaged leaderboard, replay or save, rename the matching
`*.backup.json` over the damaged file while the game is closed. The profile
screen says where the folder is.

Verified 2026-09-18 (WB-015): `tests/warband/test_storage_journeys.py` plays
a match to a resignation in one process and reloads the result, rating,
leaderboard entry, replay, quicksave and a changed setting in another; loads
past a leftover staged file and loads twice without duplicating; damages the
profile and restores it through the profile screen; and makes the profile and
replay folders unwritable at match end to see the game say so and go on.

## Verification

`uv run pytest tests/warband/test_profile.py tests/warband/test_replay.py
tests/warband/test_rated_match.py tests/warband/test_replay_scene.py
tests/warband/test_profile_scene.py -q` covers the rating maths, the standing
rule, faithful playback across seeds and a mid-match reload, the confirmations,
the results screen, the profile screen and renaming. `tools/verify_profile.py
DIR` renders the screens through the real backend for inspection.
