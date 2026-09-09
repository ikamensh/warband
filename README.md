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

```bash
uv sync --extra dev
uv run warband               # title screen; --seed 3 starts a match directly
uv run pytest -q
```

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

**M** on the title opens multiplayer: online rooms by code on the shared
server, or explicit LAN. Guides: [play together on Mac and Windows](docs/warband-play-together.md),
[Windows builds](docs/windows-warband.md), [scores](docs/warband-scores.md),
[art](docs/warband-art.md), [audio](docs/warband-audio.md) and
[music](docs/warband-music.md). The Early Access goal is defined in
[warband-early-access-criteria.md](docs/warband-early-access-criteria.md) and
tracked in [warband-early-access-progress.md](docs/warband-early-access-progress.md).

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
