# Warband

A small Warcraft 2-style real-time strategy game on [Saga2D](https://pypi.org/project/saga2d/).

Planned work and task order: [Warband backlog](BACKLOG.md).

A top-down map of meadows, woods and lakes under a soft fog of war, in
summer, winter or wasteland, in one of five layouts (open plains, deep
forest, a river with fords, a gold pit in the middle, walled bastions); a base
for each of two to sixteen players with a gold mine and a wood beside it, a
natural expansion of its own, and contested mines between, laid out by
symmetry — every seat holds one congruent cell of a grid — so every seat gets
the same ([docs/warband-maps.md](docs/warband-maps.md)). Four races — Humans, Orcs, Elves and Dwarves —
share one tech skeleton but differ in names, numbers, look, voice and march,
each with a passive mechanic and two arts of its own
([docs/warband-races.md](docs/warband-races.md)). Peasants mine gold and fell
trees; farms feed the army; a barracks, lumber mill, blacksmith, stables,
workshop and church open seven units and the upgrades; guard towers hold the
line. Five AI difficulties expand, upgrade, raid and attack; Master plays one of three postures, drawn with the map,
and Grandmaster a posture bred for the race it leads by a genetic search ([docs/ai-ladder.md](docs/ai-ladder.md)).
Every finished match is scored into a local top ten and rated into the
player's profile — an Elo-scale rating estimated against the difficulty
ladder, with every match's replay kept to watch again
([docs/warband-profile.md](docs/warband-profile.md)). A command card of
portraits and emblems with keycaps in three switchable control schemes,
endless training, rows of buildings placed with Shift or by the planner,
control groups, patrol, camera bookmarks,
a minimap that pans and orders, three save slots with an autosave, a tutorial
strip, a codex, a synthesised march per race, and the fallen lying where they
fell for a while.

## The campaign

**Campaign** on the title (A) opens *The Thornwood War*: six missions in three
acts for the Marches, with briefings, objectives, scripted raids and ambushes,
dialogue with portraits, three choices that carry across missions, and an
epilogue that reads them back. One mission is played as the dwarves. The
campaign's difficulty is chosen once and shifts every computer opponent a
step. Progress (the missions done and the choices) lives in
`~/.warband/campaign/` apart from the mission in play (the `campaign` save
slot), so a new version of Warband keeps your place even when it can no longer
read the saved mission: that mission starts again from its briefing. The
design and the persistence rules are in
[docs/warband-campaign.md](docs/warband-campaign.md);
`uv run warband --mission ID` starts one mission directly (`--mission list`).

## Play the latest version

Warband runs straight from this checkout on macOS and Windows; nothing is
installed system-wide. You need
[uv](https://docs.astral.sh/uv/getting-started/installation/) and the
sagaforge asset library checked out beside this one:

```bash
git clone https://github.com/ikamensh/sagaforge.git
git clone https://github.com/ikamensh/warband.git
cd warband
uv run warband
```

`uv run` creates `.venv`, fetches Python and the dependencies when they are
missing, and opens the title screen; the first start also synthesises the
sounds and music. **New game** picks map size (S, M, L or `[` and `]` through
all six), players (2, 3, 4 or `-` and `=` through 2, 3, 4, 6, 8, 12 and 16),
difficulty and race — it moves whichever of size and seats you did not touch
rather than offering a pairing with no fair map —
**Continue** resumes the autosave, **Profile & replays** shows your rating,
record and the replays of your matches, and **Codex** (F2) reads every unit,
building, upgrade and the tech tree of the race New game is set to, before one
is started. Saga2D comes from PyPI at the version pinned
in `pyproject.toml` and `uv.lock`. The asset library remains an editable path
dependency. Update the game and asset checkout, then start again:

```bash
git -C ../sagaforge pull && git pull
uv run warband
```

For an existing environment that used the editable engine, run
`uv sync --locked --extra dev --reinstall-package saga2d` once before launching.
A plain sync can retain an editable install of the same version. This also
restores the release after local engine testing.

Straight into a match, and the other options:

```bash
uv run warband --seed 3                    # skip the title: seed 3, you against one computer player
uv run warband --seed 3 --race orc --players 4 --size Large --difficulty hard --theme winter --layout forest
uv run warband --seed 3 --players 16 --size Epic              # sixteen seats need Giant or Epic; a size that cannot seat them is refused
uv run warband --fullscreen
uv run warband --help
```

Saves, settings, high scores and the generated audio live in `~/.warband`
(Windows: `%USERPROFILE%\.warband`). On a Mac trackpad, two-finger click or
Ctrl+click is the right-click.

The installed app (`/Applications/Warband.app`, or the Windows installer from
[games.tachyon-ai.eu](https://games.tachyon-ai.eu/warband/)) is the published
**0.2.0-preview.2**; later checkouts move ahead of it. Rebuild it from the
working tree with the shared packaging recipe; it refuses an uncommitted tree
unless you pass `--allow-dirty`:

```bash
uv run --extra package python tools/package.py install    # macOS: build, self-test, replace /Applications/Warband.app
```

The [release notes](docs/warband-release.md) cover the installer and its
verification; Windows builds come from the workflow described in
[windows-warband.md](docs/windows-warband.md).

## Play together

**M** on the title opens Multiplayer; every route also exists as a
command-line flag (`uv run warband --help`). Both sides need the same Warband
version.

- **Online**, the default: a two-seat room on the shared server, joined by
  code or invite link, with no port forwarding, VPN or account. The published
  builds play there, and so does a checkout while it still speaks the deployed
  game id (`warband-v2`) and options; after a rules change that moves them, a
  refresh is a deploy from [saga-online](../saga-online). Guide:
  [play together on Mac and Windows](docs/warband-play-together.md).
- **Your own server**, for checkout against checkout. Run the room server
  from this checkout (`--host 0.0.0.0` lets other computers in) and point
  both clients at it with `--server` or `SAGA2D_SERVER_URL`:

  ```bash
  uv run python -m saga2d.server --games warband.online.authority:ONLINE   # ws://127.0.0.1:8765
  uv run warband --online-host --server ws://127.0.0.1:8765           # prints the room code
  uv run warband --online-join CODE --server ws://127.0.0.1:8765
  ```

- **LAN or VPN**, without a server; the host's process is the authority:

  ```bash
  uv run warband --host                              # prints the port and room code
  uv run warband --join 192.168.1.20 --room CODE     # two processes on one computer: --join 127.0.0.1
  ```

## Controls

Three control schemes, switched under Settings → Controls in a match
([docs/controls.md](docs/controls.md)): **Classic** (the letter of the name,
the default), **Grid** (Q W E / A S D / Z X C by the card's position, the
left hand never moves) and **Modal** (vim-like: with nothing selected letters
recruit, placing keeps the next building ready until Esc, `.` repeats). Every
button shows its key; F1 lists the scheme's. The Classic keys:

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| Drag / click | select | Right click | move · harvest · attack · rally point |
| Shift | add to selection · queue orders · keep placing | A / P | attack-move / patrol |
| S / H / M | stop / hold / move | B then F B H T M K S W C | build farm · barracks · hall · tower · mill · smith · stables · workshop · church |
| The building's key again | the planner picks the spot | R | repair a damaged building (peasants) |
| Letters on the card | train and research in the selected building | Shift+letter, or right-click it | train that unit endlessly (several take turns) |
| B / T / U / G | plan buildings / units / upgrades, assembly point | Ctrl+B / T / U / G / P | the same from any card, and every plan |
| Tab / . | next idle peasant / soldier | Ctrl+A (Cmd+A) | select the whole army |
| Ctrl+1-9 / 1-9 | assign / recall a group | Double-click / Ctrl-click | every unit of that type on screen |
| Space | jump to the last alert | Mac trackpad | two-finger click or Ctrl+click is the right-click; Cmd-click selects a type |
| Arrows, edges, middle-drag | scroll | Wheel, + / − | zoom |
| F3 / F5 / F9 | pause / quicksave / quickload | Esc, F1, F2, F10 | back one level · help · codex · menu |

In Settings, Tab / Shift+Tab or ↑↓ select a row; ←→ adjust it. Clicking an
option selects that same row for the keyboard. Enter toggles or increases
the selected setting.

Guides: [scores](docs/warband-scores.md), [art](docs/warband-art.md),
[audio](docs/warband-audio.md) and [music](docs/warband-music.md). The Early
Access goal is defined in
[warband-early-access-criteria.md](docs/warband-early-access-criteria.md) and
tracked in [warband-early-access-progress.md](docs/warband-early-access-progress.md).

## Code

`warband/sim/model.py` is a 20 Hz fixed-step simulation; `path.py` is A*;
`mapgen.py` lays out and audits the bases; `ai.py` runs each computer player
from a difficulty profile; `textures.py` renders every prop and unit through
`sagaforge.render3d`; `sound.py`, `combat_sound.py`, `voices.py` and
`music.py` synthesise the effects, the Foley, the race voices and the marches
with `sagaforge.synth`; `scene.py`, `title.py` and `tutorial.py` are the
saga2d scenes. The tools: `tools/fuzz.py`, `tools/verify.py`,
`tools/ai_report.py`, `tools/map_report.py`, `tools/perf.py`, `tools/soak.py`
and `tools/package.py` (builds, verification and local installs through the
shared `saga2d.packaging` recipe).

```bash
uv run pytest -q             # headless suite on the mock backend, about three minutes
```

[AGENTS.md](AGENTS.md) lists the fuzz, verification, performance and
packaging commands and the rules for changing the game.
