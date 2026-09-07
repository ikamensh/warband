# Warband sound direction

Routine gold/resource deposits are silent. Completion, orders and under-attack
alerts keep their useful cues. Nearby tree felling uses a quieter chop at 25%
gain, at most once every 2.5 seconds. Deaths use a body fall and settling gear
at 40% gain instead of a musical cue.

Combat combines the weapon's movement and weight with the material it hits.
There are three independently seeded takes for every weapon/material pair;
successive plays avoid repeating the same take and vary pitch slightly.
Impacts play at 65% gain to leave room for a busy battle and alerts.

| Attacker | Weapon |
| --- | --- |
| Peasant | Axe |
| Footman | Sword |
| Scout | Spear |
| Knight | Lance |
| Archer, guard tower | Arrow |
| Catapult | Siege stone |

| Target | Material |
| --- | --- |
| Unarmored units | Flesh and cloth |
| Armored units, including soldiers with armor upgrades | Armor |
| Catapult, including upgraded catapults | Wood |
| Farm, barracks, lumber mill, stables, workshop | Wood |
| Town hall, guard tower, blacksmith, church | Stone |
| Any unfinished building | Wood construction frame |

The scene admits at most four battle voices in 0.12 seconds and eight in
0.5 seconds, including deaths. Identical impacts have a short repeat gap;
siege impacts share a 0.3-second gap across materials, keeping splash damage
from producing a sound for every victim. Important alerts use their own
timing. The sound bank regenerates its cached WAVs when `SOUND_VERSION` changes.
Ordinary battle and harvesting sounds follow the camera and fog visibility;
under-attack alerts remain audible across the map. Projectile impacts wait
for the visible arrow or stone to arrive.

Hit events carry source type, target type, effective armor and construction
state from the instant of the strike. Killing blows therefore retain the right
sound after a participant disappears. Multiplayer hosts and online servers
must run the updated model so their snapshots include these facts. A client
connected to an older server uses a neutral contact sound and shows one notice
that weapon/material audio requires a server update. Malformed partial metadata
is an error. Update multiplayer clients alongside hosts; older clients do not
understand the additional event fields.

## Preview and verification

```sh
uv run python tools/verify_warband_audio.py /tmp/warband-audio
```

The tool writes `comparison.wav`, a timestamped `comparison.txt` and matching
`comparison.json`. The comparison starts with sword against flesh, armor, wood
and stone, then demonstrates the other weapons. Each example includes all
three takes, followed by a short mixed skirmish. The combined WAV stays below
clipping and retains the relative weapon gains.

Native verification keeps its pyglet window hidden and forces the silent
audio driver: it never plays through the speakers. It routes every impact
family through the real sound bank, checks player start, natural end of source
and cleanup, simulates a small fight through `GameScene`, and writes
`battle.png` and `native.json`. It also checks cleanup of an active effect when
the game closes. Bank assets stay under the chosen output directory. The
display must be awake for native rendering; open the captured PNG to review it.

Use `--preview-only` to generate the comparison without native verification.
Run this separately from other expensive test or native verification jobs.

Validated on 2026-09-07: 269 tests passed across Warband, multiplayer and the
shared audio/synth tests; one 80-input scene fuzz run passed at the default
25% CPU allowance. Native verification exercised all 24 impact families,
32 natural playback completions, scene combat and shutdown of an active
player. The captured battle frame was inspected. The silent driver verifies
playback mechanics; the comparison WAV is provided for listening review.

Evidence: [audio comparison](evidence/warband-audio/comparison.wav),
[cue sheet](evidence/warband-audio/comparison.txt),
[native report](evidence/warband-audio/native.json),
[battle frame](evidence/warband-audio/battle.png).
