# Warband campaign: The Thornwood War

Design note and record, 2026-09-15. Implemented: `warband/story/campaign.py` (the
engine and the progress file), `warband/story/missions.py` (the six missions),
`warband/story/dialog.py` (the dialogue overlay), `warband/story/mission_scene.py` (a
mission as a match, its result, its loader), `warband/story/campaign_scene.py` (the
campaign screen). Tests: `tests/warband/test_campaign.py`; screens rendered by
`tools/verify_campaign.py DIR`.

## What the player gets

**Campaign** on the title (A) opens the campaign screen: the story's title,
the six missions in their three acts with what is done, next and still to
come, a map of the next mission, and one button that does the right thing:
begin (after choosing the campaign's difficulty), resume the saved mission,
open the next briefing, or read the epilogue once the war is over.

Every mission has a **briefing** (a dialogue over the campaign screen), an
**objectives panel** on the HUD in place of the tutorial strip (ticks for done,
crosses for failed, lines that appear when the story reaches them), **scripted
events** during play (bands arriving, a warning from the captain, a camera cue
and a minimap ping, a notice), **dialogue** that pauses the match and shows who
speaks with their portrait, **questions** with two answers on number keys, a
**result screen** (the objectives as they ended, the battle record, Continue
or Retry), and a **debrief**. The pause menu of a mission offers Restart
mission and Campaign (which saves first) instead of New game and Resign.
Missions are not ranked: the leaderboard is for skirmishes.

## The plot

Ten years of quiet on the Greywater end when orc warbands cross the river and
burn Hollowmere. Held at the ford, the orcs turn out to be refugees: the
Thornwood elves' forest is *growing* over the wastes (the elven Regrowth art,
written large), and the dwarves of Karst Hold, in its path, have gone silent.
The company crosses the winter moor to Karst, breaks the siege as the dwarves
themselves, comes home to find the ford under leaves, and marches on the Court
of Thorns.

| # | Mission | Act | Map | You | Against | Objective | Story beat |
|---|---------|-----|-----|-----|---------|-----------|------------|
| 1 | Hollowmere | I · The Marches | Small, summer, Plains | Humans, a burned village | a raiders' camp, no AI | build a farm and a barracks, train four soldiers, then hold three raids (or raze the camp) | the raiders carry pots, blankets, children's things |
| 2 | Greywater Ford | I | Medium, wasteland, Crossings | Humans with a barracks and three footmen | orc base (Easy) plus two scripted probes | hold the ford until 10:00; the chieftain comes to parley | **Choice: grant the truce** (the orcs withdraw) **or no quarter** (raze the camp) |
| 3 | The Silent Hold | II · The Silent Hold | Medium, winter, Plains | a company on foot: a knight, Sister Maren, six footmen, two archers, no base | warden patrols, an outpost, an ambush past the middle | bring Sister Maren to the pass; she must survive | the forest came up the valley in a month |
| 4 | Karst Hold | II | Medium, winter, Plains | **the Dwarves** of Karst: towers, a guard hall, a mortar, gold | elf base (Medium) with a garrison; an assault at the walls at once | break the siege | **Choice: take the blasting powder south or leave it** |
| 5 | Greywater Retaken | III · The Thornwood | Medium, summer, Crossings | Humans with a barracks and a band | elf base (Medium; **Easy with the truce**, plus 1000 gold of tribute) with a head start | retake the ford | the felled trees grow back |
| 6 | The Court of Thorns | III | Large, summer, Forest | Humans; **with the powder** a workshop, Siege Engineering and two catapults, **without** 2000 gold | elf base (Hard) with a big head start; **without the truce** an orc base (Medium) too | destroy the Court (and drive off the orcs) | **Choice: burn the wood back or bind the Court by treaty**; the epilogue reads the three choices |

The campaign's difficulty (Easy, Medium, Hard, chosen once) shifts every AI
side one step from the mission's base level along Easy, Medium, Hard and
Master: on Hard the Court of Thorns is Master, on Easy the ford's orcs stay
Easy. Hard and Master are the stronger `ProBrain`, made by `make_brain` like a
skirmish's opponents. Speakers: Captain Aldric Vane
(knight), Sister Maren (cleric), Reeve Tomas (peasant), Gorrash Ironjaw (orc),
Thane Brunna Stonebrow (dwarf), Lady Ysolde of the Thornwood (elf ranger), a
Thornwood warden. Their portraits are the units' own painted frames.

## How a mission is written

A `Mission` is data plus a few small functions in `warband/story/missions.py`:
sides (name, race, base AI level or scripted), map size, theme, layout and seed, the
briefing and debrief dialogues, a `setup(run)` that reshapes the generated map
(`run.place`, `run.spawn`, `world.clear_player`, variables for later), the
objectives (`done`, `failed`, `shown` predicates on the run) and triggers
(`when` and `do`, fired once). Predicates are composed from `at`, `after`,
`var`, `objective_done`, `side_out`, `any_of`, `all_of`. A trigger asks the
scene for things through the run: `run.say(...)` queues a dialogue,
`run.toast(...)` a notice, `run.look(point)` a camera cue and minimap ping
(the camera goes only to ground the player has explored; the ping and Space
always point there).
`Line.when` and `Line.unless` name variables, so one dialogue branches on a
choice made now or in an earlier mission. `Mission.remember` lists the
variables (the choices) copied into the campaign's flags on completion.

Maps are generated from the seed and the mission's layout, then reshaped in
code. The layout is always named: one drawn from the seed would put a
hand-placed camp in a river or a rock ring. So a mission is a few
hundred bytes of source, never a stored terrain blob, and a change to the map
generator changes a mission's map only when it is next started; a saved mission
keeps the world it was saved with. The model gained `World.scripted` (elimination
happens, but no winner is declared: the mission decides) and `World.clear_player`
(a side taken off the map quietly, revived by its next unit or building).

## Persistence: keep playing across versions

Two files, kept apart on purpose.

**Campaign progress** (`~/.warband/campaign/save_1.json`, `ProgressStore`, a
`SaveManager` envelope with durable writes and a backup): the campaign id, the
difficulty, the completed mission ids in order, the flags (the choices), and a
`format` number. A few hundred bytes of stable ids and JSON values, no world
state, nothing about art. Rules:

- Keys this version does not know are read and written back untouched.
- Completed mission ids the catalogue no longer has are kept; the next mission
  is the first in the current order that is not completed.
- Unknown flags are kept; a mission reads only the flags it names.
- Missing keys take defaults (`difficulty` Medium, empty lists).
- Only a `format` *newer* than the game's is refused, with a message that says
  to update the game. Bump `FORMAT` only when an older Warband could misread a
  newer file; adding keys never needs it.
- A refused or damaged file is never written over: the campaign screen says
  why and offers only Start over, which first moves the file aside to
  `save_1.unreadable.json`.

**The mission in play** (slot `campaign`, `save_campaign.json`; the numbered
slots and quicksave hold mission saves too): an ordinary match save with a
`mission` block: the mission id, the triggers that fired (with their times),
the objectives' states, the mission's variables, the AI levels the setup chose.
It depends on the world format like every save (`SAVE_VERSION`), so it is the
part that can go stale. The campaign screen loads it before offering to
resume; when it cannot (another format, damage, a mission this version no
longer has), it says so and Continue opens the mission's briefing instead.
The cost of a breaking change is therefore one mission replayed, never the
campaign. Progress is written at the moment of victory, before the debrief;
a choice made in the debrief is written after it.

**Art** never enters either file: portraits, sprites and buildings are looked
up by race and unit type at draw time, so new graphics change nothing about a
saved campaign or a saved mission (`tests/warband/test_campaign.py` loads a
mission save through the title's Continue and a foreign-version save through
the campaign screen).

## Evidence

- `uv run pytest -q tests/warband/test_campaign.py`: progress round trip with
  unknown keys and ids, a newer format refused, a newer or damaged file never
  written over, mission 1's three raids and its two ways to win, the truce
  granted through the dialogue and refused, the flags shaping missions 5 and 6,
  a replayed mission asking again, a mission save resumed through Continue with
  its script intact, a mission lost in the frame before its save still lost
  after it, a loaded mission keeping what the player had seen, their control
  groups and the autosave clock (one restore step with the skirmish's), a save
  from another version costing the mission and not the campaign, Start over,
  the escort won and lost, the dialogue's branching and skipping. `tests/warband/test_layout.py` checks the campaign screen
  (fresh, under way and over unreadable progress), a mission with its
  objectives, a line, a choice, both results and the mission pause menu for
  text drawn over text at five window sizes.
- `tools/verify_campaign.py DIR [--size WxH]` renders the title, the campaign
  screen fresh and under way, the briefing, the first mission's banner and
  then its objectives, Aldric's warning, the raid, a question and the result
  on the real backend, then every mission's opening beside a map of the whole
  mission drawn from the model. The frames were inspected on 2026-09-15 and,
  after the campaign joined main (WB-016), at 1280×800 and 1200×680 on
  2026-09-18.
- Since joining main every mission is tested both ways: missions 2, 4, 5 and 6
  gained win and loss tests beside 1 and 3; Karst's powder and the Court's
  burn go through their debriefs into the progress file, which a second
  process reads back; the epilogue speaks the three choices. A mission opens on
  its title banner alone, then the objectives panel comes in (at 680 tall the
  banner crosses where the panel reaches), and a notice hangs under the panel
  however tall it grows.

## Not yet

- The missions were tuned on paper and by scripted play, not by a person: the
  hold times, the bands and the head starts need playtests, mission by mission.
- Since the campaign was written, Normal and Hard became one level (Medium,
  about 1000 Elo) and Hard and Master became the `ProBrain` (1353 and 1589):
  the Court of Thorns is Hard at base and Master on a Hard campaign, far above
  what it was tuned against. Four missions also start above their supply cap
  (Greywater 6/5, Karst 8/5, Retaken 9/5, the Court 13/5). Both are for the
  playtests to judge.
- Allies are not modelled: every other side is an enemy, so the orcs' help and
  the dwarves' engineers arrive as resources and units of the player's own race.
- One campaign, for the humans (with one mission as the dwarves). An orc or
  elf campaign reuses everything but `missions.py`.
