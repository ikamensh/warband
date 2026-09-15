# Warband

A small Warcraft 2-style real-time strategy game on [Saga2D](../saga2d).

A top-down map of meadows, woods and lakes under a soft fog of war, in
summer, winter or wasteland; a base for each of two to four players with a
gold mine and a wood beside it. Four races — Humans, Orcs, Elves and Dwarves —
share one tech skeleton but differ in names, numbers, look, voice and march,
each with a passive mechanic and two arts of its own
([docs/warband-races.md](docs/warband-races.md)). Peasants mine gold and fell
trees; farms feed the army; a barracks, lumber mill, blacksmith, stables,
workshop and church open seven units and the upgrades; guard towers hold the
line. Three AI difficulties expand, upgrade, raid and attack in growing waves.
Every finished match is scored into a local top ten. A command card of
portraits and emblems with keycaps, control groups, patrol, camera bookmarks,
a minimap that pans and orders, three save slots with an autosave, a tutorial
strip, a codex, a synthesised march per race, and the fallen lying where they
fell for a while.

## Play the latest version

Warband runs straight from this checkout on macOS and Windows; nothing is
installed system-wide. You need
[uv](https://docs.astral.sh/uv/getting-started/installation/) and the two
repositories Warband depends on, checked out beside this one:

```bash
git clone https://github.com/ikamensh/saga2d-framework.git saga2d
git clone https://github.com/ikamensh/sagaforge.git
git clone https://github.com/ikamensh/warband.git
cd warband
uv run warband
```

`uv run` creates `.venv`, fetches Python and the dependencies when they are
missing, and opens the title screen; the first start also synthesises the
sounds and music. **New game** picks map, players, difficulty and race,
**Continue** resumes the autosave. The framework and the asset library are
editable path dependencies, so moving to a newer version is a pull in the
three checkouts and another start:

```bash
git -C ../saga2d pull && git -C ../sagaforge pull && git pull
uv run warband
```

Straight into a match, and the other options:

```bash
uv run warband --seed 3                    # skip the title: seed 3, you against one computer player
uv run warband --seed 3 --race orc --players 4 --size Large --difficulty hard --theme winter
uv run warband --fullscreen
uv run warband --help
```

Saves, settings, high scores and the generated audio live in `~/.warband`
(Windows: `%USERPROFILE%\.warband`). On a Mac trackpad, two-finger click or
Ctrl+click is the right-click.

The installed app (`/Applications/Warband.app`, or the Windows installer from
[games.tachyon-ai.eu](https://games.tachyon-ai.eu/warband/)) is the published
**0.1.0-preview.4**, which is behind this checkout. Rebuild it from the
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
  builds play there. A room created from this checkout is refused with
  *Unknown match option* while the live server still runs preview.4; a
  refresh is a deploy from [saga-online](../saga-online). Guide:
  [play together on Mac and Windows](docs/warband-play-together.md).
- **Your own server**, for checkout against checkout. Run the room server
  from this checkout (`--host 0.0.0.0` lets other computers in) and point
  both clients at it with `--server` or `SAGA2D_SERVER_URL`:

  ```bash
  uv run python -m saga2d.server --games warband.multiplayer:ONLINE   # ws://127.0.0.1:8765
  uv run warband --online-host --server ws://127.0.0.1:8765           # prints the room code
  uv run warband --online-join CODE --server ws://127.0.0.1:8765
  ```

- **LAN or VPN**, without a server; the host's process is the authority:

  ```bash
  uv run warband --host                              # prints the port and room code
  uv run warband --join 192.168.1.20 --room CODE     # two processes on one computer: --join 127.0.0.1
  ```

## Controls

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| Drag / click | select | Right click | move · harvest · attack · rally point |
| Shift | add to selection / queue orders | A / P | attack-move / patrol |
| S / H | stop / hold | B then F B H T M K S W C | build farm · barracks · hall · tower · mill · smith · stables · workshop · church |
| R | repair a damaged building (peasants) | Mac trackpad | two-finger click or Ctrl+click is the right-click; Cmd-click selects a type |
| Letters on the card | train and research in the selected building | Ctrl+1-9 / 1-9 | assign / recall a group |
| Tab / . | next idle peasant / soldier | Space | jump to the last alert |
| Arrows, edges, middle-drag | scroll | Wheel, + / − | zoom |
| F3 / F5 / F9 | pause / quicksave / quickload | Esc, F1, F2, F10 | cancel · help · codex · menu |

Guides: [scores](docs/warband-scores.md), [art](docs/warband-art.md),
[audio](docs/warband-audio.md) and [music](docs/warband-music.md). The Early
Access goal is defined in
[warband-early-access-criteria.md](docs/warband-early-access-criteria.md) and
tracked in [warband-early-access-progress.md](docs/warband-early-access-progress.md).

## Code

`warband/model.py` is a 20 Hz fixed-step simulation; `path.py` is A*;
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
