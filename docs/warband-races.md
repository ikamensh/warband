# Warband races

Warband has four races.  They share one skeleton — the same seven unit roles
trained in the same nine buildings with the same hotkeys and costs — so the
AI, the settlement planner, saves and the online protocol never care who is
playing.  What differs: the names, a few numbers per role, two race arts
(upgrades only that race researches), one passive mechanic the simulation
applies, the look of every unit and building, the voice of the player's own
cues, and the march.  `warband/races.py` holds the data; `warband/rules.py`
holds the skeleton and the arts.

| Race    | Character                            | Passive                                             | Arts                                                        |
|---------|--------------------------------------|-----------------------------------------------------|-------------------------------------------------------------|
| Humans  | balanced, the baseline               | Drill: every unit trains 15 % faster                | Horse Breeding (+0.8 speed for cavalry), Blessing (clerics heal ×1.5) |
| Orcs    | tougher, harder-hitting, less armour | Frenzy: soldiers below half health deal +25 % damage | Bloodlust (frenzy +50 %), Plunder (razing loots a fifth of the building's gold) |
| Elves   | lighter, faster, far-sighted         | Keen eyes: +2 sight, rangers shoot a tile farther   | Longbows (+1 range for rangers and towers), Regrowth (felled trees grow back after a minute) |
| Dwarves | sturdier, slower, housed in stone    | Stonework: buildings +25 % hit points and +2 armour | Deep Mining (150 gold per trip), Blasting Powder (mortar splash ×1.5) |

## Rosters

| Role      | Humans      | Orcs        | Elves        | Dwarves      |
|-----------|-------------|-------------|--------------|--------------|
| worker    | Peasant     | Peon        | Gatherer     | Miner        |
| line      | Footman     | Grunt       | Sentinel     | Ironguard    |
| ranged    | Archer      | Axethrower  | Ranger       | Crossbowman  |
| raider    | Scout       | Wolf Rider  | Outrider     | Ram Rider    |
| shock     | Knight      | Ogre        | Stag Knight  | Bear Rider   |
| siege     | Catapult    | Catapult    | Ballista     | Mortar       |
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

The numbers: orc units have +15 % hit points (the ogre +20 %), the grunt and
ogre +10 % damage and −1 / −2 armour, and all orc soldiers train 10 % slower;
elf units have −5 % hit points, +0.3 speed and +2 sight, and the ranger one
more tile of range; dwarf units have +10 % hit points and −0.3 speed, the
ironguard and bear rider +1 armour.  The codex (F2) shows the player's race's
tables and a fourth page comparing the races.

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
`warband/textures.py` sets skin, hair, metal, cloth and the figure's
proportions (dwarves squat, orcs broad), and race branches draw the
distinctive parts: tusks and topknots, spiked pauldrons and cleavers, a
two-headed ogre and a wolf; long ears, winged helms and hoods, a deer, an
antlered stag and a ballista; beards, nasal helms and round shields, a
crossbow, a ram, a war bear and a mortar.  Buildings take per-race materials
and roof tints, race dressing around every yard (bone spikes and a skull pole,
saplings and a moon standard, rune pillars with copper caps) and their own
hall, supply building, tower, stable beast and shrine ornament.

The player's own cues — select, command, attack, trained, built, under
attack — play in the race's voice (`warband/voices.py`): drums and growls for
orcs, bells, harp and flute for elves, anvil and horn for dwarves; humans keep
the plain cues.  Combat Foley follows the striker: orc grunts and axethrowers
swing axes, the ogre and the bear rider hit with a blunt "hammer" weapon,
dwarven ironguards use axes.  Each race marches to its own track
(`warband/music.py`: `march`, `warpath`, `moonlight`, `anvil`); the title
plays the night watch (`vigil`).

## Balance

`tools/race_report.py` plays every pair of races head to head under the same
AI, sides swapped per seed.  With the Hard AI on Medium maps, two seeds per
pair (twelve matches per race, all decided within twenty minutes), the first
run gave Humans 8–4, Dwarves 7–5, Orcs 5–7 and Elves 4–8; the map side decided
more pairs than the race did.  The elven hit-point penalty was eased from 10 %
to 5 % after that run; the rerun gave Humans 8–4, Orcs 6–6, Dwarves 5–6 and
Elves 4–7 with one match undecided.  The AI plays every race the same way, so
this measures the rules, not race-specific play; Drill (faster training) suits
an AI that trains without pause, which is the likely source of the human edge.

## Verification

`tests/warband/test_races.py` covers the mechanics and the skeleton,
`test_race_ui.py` the title choice, cards, codex, regrowth sprites and room
options, `test_race_sound.py` the voices, weapons and tracks.  Real pyglet
frames of a settlement per race were rendered and inspected while the art was
made (`saga2d.testing.render_scene`); `tools/fuzz_warband.py` plays AI matches
with seed-drawn races.
