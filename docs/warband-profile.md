# Warband player profile, rating and replays

The title screen carries the player's card: name, rating, record and the
last few results, with **P** opening the profile. Every offline match against
the computer is rated when it ends — or when the player leaves it — and its
replay is kept. Online matches are neither rated nor recorded.

## The rating

The rating is on the Elo scale the difficulty settings are measured on
([docs/ai-ladder.md](ai-ladder.md)): Easy 770, Medium 1000, Hard 1220,
Master 1420 at the time of writing (`warband.ai.DIFFICULTY_ELO`). It is an
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

`~/.warband/profile/save_1.json` holds the name and results; a damaged
file is reported on the title, the results screen and the profile screen and
never overwritten. The name defaults to the login name and is changed from
the profile screen (up to 16 characters).

## Verification

`uv run pytest tests/warband/test_profile.py tests/warband/test_replay.py
tests/warband/test_rated_match.py tests/warband/test_replay_scene.py
tests/warband/test_profile_scene.py -q` covers the rating maths, the standing
rule, faithful playback across seeds and a mid-match reload, the confirmations,
the results screen, the profile screen and renaming. `tools/verify_profile.py
DIR` renders the screens through the real backend for inspection.
