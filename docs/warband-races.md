# Warband races

Warband has four races.  They share one skeleton — the same seven unit roles
trained in the same buildings with the same hotkeys and costs, and one unit of
each race's own besides (below) — so the
AI, the settlement planner, saves and the online protocol never care who is
playing.  What differs: the names, a few numbers per role, two race arts
(upgrades only that race researches), one passive mechanic the simulation
applies, the look of every unit and building, the voice of the player's own
cues, and the march. `warband/assets/constants/races.toml` holds the data, loaded
once at startup. `warband/sim/rules.py` holds the skeleton and the arts; its tables
come from the same startup snapshot.

| Race    | Character                            | Passive                                             | Arts                                                        |
|---------|--------------------------------------|-----------------------------------------------------|-------------------------------------------------------------|
| Humans  | balanced, the baseline               | Drill: every unit trains 15 % faster                | Horse Breeding (+0.8 speed for knights), Blessing (clerics heal ×1.5) |
| Orcs    | tougher, harder-hitting, less armour | Rage: a soldier hurt below half health is enraged for ten seconds, +25 % damage, however well it is mended | Bloodlust (rage +50 %), Plunder (razing loots a fifth of the building's gold) |
| Elves   | lighter, faster, far-sighted         | Keen eyes: +2 sight, rangers shoot a tile farther   | Longbows (+1 range for rangers and towers), Regrowth (felled trees grow back after a minute) |
| Dwarves | sturdier, slower, housed in stone    | Stonework: buildings +25 % hit points and +2 armour | Deep Mining (150 gold per trip), Blasting Powder (mortar splash ×1.5) |

## Rosters

| Role      | Humans      | Orcs        | Elves        | Dwarves      |
|-----------|-------------|-------------|--------------|--------------|
| worker    | Peasant     | Peon        | Gatherer     | Miner        |
| line      | Footman     | Grunt       | Sentinel     | Ironguard    |
| ranged    | Archer      | Axethrower  | Ranger       | Crossbowman  |
| shock     | Knight      | Ogre        | Stag Knight  | Bear Rider   |
| siege     | Catapult    | Catapult    | Ballista     | Mortar       |
| eyes      | Flying Machine | Goblin Zeppelin | Leafwing Glider | Gyrocopter |
| healer    | Cleric      | Shaman      | Druid        | Runepriest   |

| Building   | Humans      | Orcs        | Elves        | Dwarves      |
|------------|-------------|-------------|--------------|--------------|
| hall       | Town Hall   | Great Hall  | Moon Hall    | Deep Hold    |
| supply     | Farm        | Pig Farm    | Orchard      | Brewhouse    |
| barracks   | Barracks    | War Camp    | Warden Lodge | Guard Hall   |
| tower      | Guard Tower | Watch Tower | Watch Tree   | Bolt Tower   |
| mill       | Lumber Mill | Sawmill     | Grove Mill   | Timber Works |
| smith      | Blacksmith  | Forge       | Silversmith  | Forge        |
| stables    | Stables     | Kennels     | Stag Pens    | Beast Pens   |
| workshop   | Workshop    | Siege Yard  | Siege Bower  | Engine Works |
| church     | Church      | Altar       | Moonwell     | Rune Shrine  |

The numbers: orc units have +15 % hit points (the ogre +20 %), and the grunt and
ogre +10 % damage and −1 / −2 armour;
elf units have −5 % hit points, +0.15 speed and +2 sight, and the ranger one
more tile of range; dwarf units have +10 % hit points and −0.15 speed, the
ironguard and bear rider +1 armour.  The codex (F2) shows the player's race's
tables and a fourth page comparing the races.

## Each race's own unit (WB-068)

Something exotic and expensive, and sometimes the answer: each race has one unit
no other race trains, after the Keep, at most three alive and queued at once.

| Race    | Unit          | Trained at  | What it does                                                             |
|---------|---------------|-------------|--------------------------------------------------------------------------|
| Humans  | Gryphon Rider | Stables     | the armed flyer: a storm hammer at ground and air; only shots reach it  |
| Orcs    | Goblin Sapper | Siege Yard  | its blow is its end: a blast of 1.5 tiles, 240 siege on buildings (360 on a wall), 60 on every unit on the ground, its own side's too |
| Elves   | Treant        | Moonwell    | walks through the forest, crushes buildings at ×2, mends 4 hp a second among trees out of the fight |
| Dwarves | Rune Golem    | Rune Shrine | the wild golem's slam, bound: splash round its mark that spares its side; a construct, never mended |

Each is a row of `units.toml` with the seams the next one reuses: `race` (who
may train it: its building's `trains` lists it and the card, the catalogue, the
codex and the tech tree offer it to that race alone, `RaceInfo.unit_allowed`),
`requires` (the upgrades it waits for, `World.lacks_for`, refused at `train`
and `set_auto_train` and waited for as a plan), `limit` (`World.at_limit`,
refused at `train`, `order_unit` and `set_auto_train`; an endless order waits at
it without holding up the building's other endless recruits and goes on when
one falls), `blast` and `blast_units` (`World._blast`; its owner sees and hears
the blast and what it struck wherever the fog stands, as the sapper's eyes go up
with it), `forest` (`World.ground_of`) and
`regen_in_trees`; the gryphon is `flying` with a shot, and the golem's slam is a
melee blow with `splash`.  The race's defaults apply to its own unit as to any
other: the treant sees two tiles farther, the rune golem walks at 1.25.  How the
computer players buy and use them is `warband/brains/unique.py`, bound by the
fog: it sends them at the buildings its side remembers, as it last saw them.

## Choosing a race

The new-game screen has a Race row (U humans, O orcs, V elves, A dwarves);
`--race` does the same on the command line.  Computer players draw their
races from the map seed, avoiding repeats while they can, so a seed
reproduces the whole match.  Online rooms carry the creator's race in the
room options (`races: [creator, null]`); the guest's seat is drawn from the
seed.  Races are stored per player in saves and snapshots; saves from before
races load as all Humans.

## Look and sound

Every unit keeps the same poses and articulation; a per-race `Look` in
`warband/art/textures.py` sets skin, hair, metal, cloth and the figure's
proportions (dwarves squat, orcs broad), and race branches draw the
distinctive parts: tusks and topknots, spiked pauldrons and cleavers, a
two-headed ogre and a wolf; long ears, winged helms and hoods, a deer, an
antlered stag and a ballista; beards, nasal helms and round shields, a
crossbow, a ram, a war bear and a mortar.  Buildings take per-race materials
and roof tints, race dressing around every yard (bone spikes and a skull pole,
saplings and a moon standard, rune pillars with copper caps) and their own
hall, supply building, tower, stable beast and shrine ornament.

The command card shows a portrait for every unit and building and a painted
emblem for every upgrade (`warband/art/production.py`), with the hotkey in the
corner and the name and cost under it; a selected building shows what it is
making as a portrait with its progress, then the portraits of its queue.  This
UI was first built on the unmerged `warband` branch and ported onto the races.

The player's own cues — select, command, attack, trained, built, under
attack — play in the race's voice (`warband/audio/voices.py`): drums and growls for
orcs, bells, harp and flute for elves, anvil and horn for dwarves; humans keep
the plain cues.  Combat Foley follows the striker: orc grunts and axethrowers
swing axes, the ogre and the bear rider hit with a blunt "hammer" weapon,
dwarven ironguards use axes.  A race's people die in its voice; its catapult and
flying machine die as the machines they are, whoever fields them
(`warband/audio/bodies.py`, [adding a unit](adding-a-unit.md#its-sounds)).  Each race marches to its own track
(`warband/audio/music.py`: `march`, `warpath`, `moonlight`, `anvil`); the title
plays the night watch (`vigil`).

## Balance

`tools/race_report.py` plays every pair of races head to head under the same
AI, sides swapped per seed.  With the Hard AI on Medium maps, two seeds per
pair (twelve matches per race, all decided within twenty minutes), the first
run gave Humans 8–4, Dwarves 7–5, Orcs 5–7 and Elves 4–8; the map side decided
more pairs than the race did.  The elven hit-point penalty was eased from 10 %
to 5 % after that run; the rerun gave Humans 8–4, Orcs 6–6, Dwarves 5–6 and
  Elves 4–7 with one match undecided.  Each AI plays its race's army plan and
  shifts training towards counters of the enemy composition it can see, so
  these numbers mix the rules with race-specific play; Drill (faster training)
  suits an AI that trains without pause, which is likely part of the human edge.

A pro-versus-pro race ladder on 2026-09-16 (96 matches, every pair both ways)
gave human 66.7 %, elf 66.7 %, dwarf 35.4 % and orc 31.2 %, and the elves beat
every other race three games in four.  Changing the training rates moved humans
and orcs but left the elves at 75 %: what the elves have is speed, and what the
dwarves lack is speed, in a game decided by who reaches the first clash with
more.  Both speed modifiers were halved (±0.3 → ±0.15) as a result; see
`docs/balance.md`.

That fixed the dwarves and left the orcs.  Re-run after the halving, the same
ladder gave human 62.5 %, elf 62.5 %, dwarf 50.0 % and orc 25.0 %: orcs took
19 % against both leaders.  They had been training 10 % slower for their
hit points, and a game decided by who reaches the first clash with more
punishes the slower trainer twice over.  At the common rate the ladder reads
elf 58.3 %, human 56.2 %, dwarf 43.8 %, orc 41.7 % — a spread of seventeen
points where it had been thirty-eight.  Ninety-six matches a run, so the
ordering inside that spread is not yet established.

## Verification

`tests/warband/test_races.py` covers the mechanics and the skeleton,
`test_race_ui.py` the title choice, cards, codex, regrowth sprites and room
options, `test_race_sound.py` the voices, weapons and tracks.  Real pyglet
frames of a settlement per race were rendered and inspected while the art was
made (`saga2d.testing.render_scene`); `tools/fuzz.py` plays AI matches
with seed-drawn races.
