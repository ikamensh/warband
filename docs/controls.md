# Controls

Asked for on 2026-09-19: hotkeys that follow a system instead of accreting,
units trained endlessly instead of ordered twenty at a time, a row of farms
placed with Shift, the computer choosing where a building goes, and two or
three different ways of laying the game out on the keyboard to switch
between in the menu. This note is the design; `warband/ui/controls.py` holds
the schemes, `warband/ui/scene.py` the card and the input, and
`tests/warband/test_controls.py` pins them down.

## One system, three keyboards

The keyboard works in **modes**, and the command card always shows the mode's
commands with their keys on them:

- the **selection's card**: a unit card (move, stop, hold, attack, patrol; a
  peasant's build and repair), a building's card (what it trains, its
  research, cancel);
- the settlement's **catalogues**: Build, Train and Upgrade, which plan for the
  whole settlement (paid when work starts) or, with peasants selected, have
  those peasants build;
- a **pending order**: a target to click (move, attack, patrol, repair, the
  assembly point) or a building's site under the pointer.

Every scheme shares the modes, the mouse and the modifiers:

| | every scheme |
|---|---|
| Shift | keep going: queue an order after the others, place another building, and with a recruit's key train it endlessly |
| Esc | back one level: the pending order, the catalogue, the selection, then the menu |
| Ctrl (Cmd) + B / T / U / G / P | the Build, Train and Upgrade catalogues, the assembly point, every plan, from whatever card is up |
| a building's key again | while it is being placed: the planner picks the spot |
| right-click a recruit's button | train it endlessly, or no longer (Warcraft III toggled autocast this way) |
| 1-9, Ctrl/Shift+1-9, Tab, Ctrl+A, Space, F-keys | groups, the idle peasant, the army, the last alert, help, codex, pause, saves, bookmarks |

A scheme decides which plain keys give the card's commands and the global
actions, and how long a mode lasts. Settings → **Controls** switches them in a
match; the keycaps on every button, the hint bar, the help screen (F1) and the
tutorial follow at once.

### Classic

The letter of the name, as Warcraft II had it. A unit card is M move, S stop,
H hold, A attack, P patrol, B build, R repair; the Build catalogue F farm,
B barracks, H hall, T tower, M mill, K smith, S stables, W workshop, C church;
recruits F footman, A archer, S scout, K knight, C catapult, H healer (the
cleric: L is Blessing at the church), P peasant; research B blades, A armour,
R arrows, E siege and a letter for each race's art; X cancels. The letters are
the roles', the same for every race (an orc's Grunt is F). B, T, U and G open
the catalogues and set the assembly point whenever the card leaves the letter
free, `.` finds the next idle soldier. The easiest to learn: the key is in the
name.

### Grid

The card is a three-column grid and its keys are its places, Q W E / A S D /
Z X C, whatever it shows: the left hand never moves. A unit card is Q move,
W stop, E hold, A attack-move, S patrol, D build, Z repair (Attack stays on A,
as in every scheme); the Build catalogue's nine buildings fill the grid; a
building's recruits and research fill it from Q, Cancel ending the row. The
global actions sit beside the grid where no card reaches: B build, T train,
G upgrade, R assembly point, F plans, V the next idle soldier. The fastest once
learned, and the same for every race. It assumes a QWERTY keyboard: pyglet
reports keys by their letter, not their place.

### Modal

Vim's way: the letters again, in modes that last. With nothing selected the
Train catalogue is open (the home mode), so a letter orders that recruit and
Shift+letter trains it endlessly; B builds, U upgrades, G sets the assembly
point. A building placed leaves the next one ready to place until Esc, so a
row of farms is B, F, then a click per farm. `.` repeats the last recruit or
placement (a placement is repeated where the planner picks), `,` finds the next
idle soldier. The fewest keys for running the economy.

## The card

Every card is laid out on the same grid of slots, so the Grid keys are the
places and the other schemes see the same layout: an empty slot keeps the
others where their keys say (Grid draws it faintly). A unit card fills
Move, Stop, Hold on the first row, Attack, Patrol and a peasant's Build on the
second, Repair on the third. A building's recruits and research chains fill
from the first slot, a chain keeping its slot once all its tiers are done so
no key moves; Cancel ends the first row, or the second when three items fill
the first. The catalogues keep their table's order (the Upgrade catalogue puts
each chain's tiers side by side, the race's two arts at the ends of the second
and third rows), with Back on Esc in the bottom-right corner, or below it when
the nine slots are taken. `test_every_card_gives_each_command_a_key_of_its_own`
brings up every card of every race in every scheme and holds each key to one
command, and Grid's keys to the grid.

## Endless training

A building trains one or several unit types endlessly (`World.set_auto_train`,
a recorded order, so replays and the online authority see it); several take
turns, strictly, the next one first in `Building.auto`. It starts a recruit
only when it stands idle, once a second after the settlement's plans have had
their turn or at once when the last recruit walks out, and only from what the
player's unpaid orders have not claimed (`World.committed`: sites builders are
walking to, plans whose prerequisites stand), per resource: what a player
asked for is paid first, and a farm waiting for lumber does not hold back a
footman paid in gold. Research planned at the building goes before its next
recruit. `World.auto_train_blocker` says why the next one waits; the building's
panel shows the rotation and that reason, and a loop marks each endless recruit
on the card. Shift with the recruit's key (or Shift+click, or a right-click on
its button) toggles it at the selected building; the same from the Train
catalogue toggles it at every building that trains it, finished or going up.
Cancel (X, or Grid's slot) cancels the last recruit and stops the building's
endless training, which would only start the next one. A rival's standing
orders are not in the seat's snapshot.

## Placing buildings

The Build catalogue is one for peasants and plans: with peasants selected the
site is theirs to build, otherwise the settlement plans it. It stays on the
card while a site follows the pointer, so another letter switches the building
and the building's own key again lets the planner choose. A click places one
site and frees the pointer (Modal keeps it); Shift+click places it and keeps
the next ready. With peasants selected, each site goes to the selected peasant
with the fewest sites ahead of it, queued behind its other sites and never
behind its harvest (a harvest never ends, so Shift-placed sites used to wait
forever). A builder sets out whatever the purse holds (`build(plan_if_short=True)`),
and a site it cannot pay for when it gets there is left as a settlement plan
(a private "deferred" event), built by a free worker once the money is there:
what a player places gets built. A site whose prerequisite does not stand yet
is planned, to wait for it. Sites ordered and not begun are drawn: a
builder's next sites in gold, the settlement's plans in blue; the ghost refuses
a site already taken, and a catalogue counts them.

The planner's spot (`brains.ai.auto_site`) is the brains' own site search
around the player's hall nearest the camera, clear of the sites already planned
and keeping paths open; a hall goes by the nearest gold mine the player knows
that no hall of theirs, standing or planned, has claimed.

## Online

Both rules are in the authority's contract: live once a server rollout carries
this Warband; until then a client of this version and the live server disagree
on the order set (the promotion gate holds the published build back). The
authority checks `set_auto_train`'s building belongs to the seat and that `on`
and `plan_if_short` are booleans.
