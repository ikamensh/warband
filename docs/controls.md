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
  peasant's build, repair and salvage), a building's card (what it trains, its
  research, cancel);
- the settlement's **catalogues**: Build, Train and Upgrade, which plan for the
  whole settlement (paid when work starts) or, with peasants selected, have
  those peasants build;
- a **pending order**: a target to click (move, attack, patrol, repair,
  salvage, the assembly point) or a building's site under the pointer.

Every scheme shares the modes, the mouse and the modifiers:

| | every scheme |
|---|---|
| Shift | keep going: queue an order after the others (one that never ends, a patrol, a hold or a harvest, gives way to it), place another building, and with a recruit's key train it endlessly |
| Esc | back one level: the pending order, the catalogue, the selection, then the menu |
| Ctrl (Cmd) + B / T / U / G / P | the Build, Train and Upgrade catalogues, the assembly point, every plan, from whatever card is up |
| Ctrl (Cmd) + X | cancel mode: a click takes back a plan, a site or a building's work, a box all of them ([below](#cancel-mode)) |
| a building's key again | while it is being placed: the planner picks the spot |
| right-click a recruit's button | train it endlessly, or no longer (Warcraft III toggled autocast this way) |
| 1-9, Ctrl/Shift+1-9, Tab, Ctrl+A, Space, F-keys | groups, the idle peasant, the army, the last alert, help, codex, pause, saves, bookmarks |

A scheme decides which plain keys give the card's commands and the global
actions, and how long a mode lasts. Settings → **Controls** switches them in a
match; the keycaps on every button, the hint bar, the help screen (F1) and the
tutorial follow at once.

### Classic

The letter of the name, as Warcraft II had it. A unit card is M move, S stop,
H hold, A attack, P patrol, B build, R repair, V salvage; the Build catalogue F farm,
B barracks, H hall, T tower, M mill, K smith, S stables, W workshop, C church;
recruits F footman, A archer, S scout, K knight, C catapult, H healer (the
cleric: L is Blessing at the church), P peasant; research K the Keep (at the
hall), B blades, A armour, R arrows, E siege and a letter for each race's art;
X cancels. The letters are
the roles', the same for every race (an orc's Grunt is F). B, T, U and G open
the catalogues and set the assembly point whenever the card leaves the letter
free, `.` finds the next idle soldier. The easiest to learn: the key is in the
name.

### Grid

The card is a three-column grid and its keys are its places, Q W E / A S D /
Z X C, whatever it shows: the left hand never moves. A unit card is Q move,
W stop, E hold, A attack-move, S patrol, D build, Z repair, X salvage (Attack
stays on A, as in every scheme); the Build catalogue's nine buildings fill the grid; a
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
second, a peasant's Repair and Salvage on the third. A building's recruits and research chains fill
from the first slot, a chain keeping its slot once all its tiers are done so
no key moves; Cancel ends the first row, or the second when three items fill
the first. The catalogues keep their table's order (the Upgrade catalogue gives
each chain one slot, which shows the next tier to order as a building's own
card does: the Keep, blades and armour on the first row, arrows, siege and
Marksmanship on the second, the race's two arts on the third; with the tiers
side by side, eight chains fill a nine-key grid and a ninth would not), with Back on Esc in
the bottom-right corner, or below it when
the nine slots are taken. A catalogue item that lacks what it needs (a
building's prerequisite, a recruit's building, an upgrade's building and every
upgrade it waits for — its lower tier, the Keep, or both; `warband/ui/tech.py`
reads them from the rules, and names the one nobody is making) carries a picture of that
in its corner and its name under the button, where the price was: behind a red
padlock while nothing of the kind is on its way, and the item is greyed out and
refused by click, key and Shift alike; behind a gold hourglass while it is
(going up, planned, a builder's next site; being researched or planned; a plan
only while what it waits for is on its way too), and the item can be ordered to
wait for it. A building's tooltip names what it unlocks, and
the codex's fifth page draws the whole tech tree (WB-054). The title screen
opens the same codex, on F2 there too, for the race New game is set to: outside
a match nobody holds anything, so the tree stands plainly lit rather than faint.
`test_every_card_gives_each_command_a_key_of_its_own`
brings up every card of every race in every scheme and holds each key to one
command, and Grid's keys to the grid.

A command that waits for a click — Move, Attack, Patrol, Repair, Salvage, the
assembly point — arms its mode: the status line says what the click will do and the card
lights that button in gold until the click or Esc, the way the Build catalogue
lights the building being placed. Pressing A or P changed nothing a player
could see before that.

## Reading the numbers

Every button that costs something — a catalogue item, and a building's own
recruits and research — carries its price under it in the top bar's own
symbols: the coin and its number, the log and its number, and no second number
at all for a thing that takes no lumber (it used to read "400 / 0"). A number
the purse cannot cover now is red; in a catalogue that greys nothing out, since
the plan is still worth making and waits for its money, while a building's own
card refuses the order until the money is there, as it always has. The symbols keep their own colours
wherever a price is drawn — a symbol says which resource, its number says how
that resource stands — and the codex and the Plans screen price things the same
way. A tooltip adds how long the thing takes and, for a building, how many it
feeds.

The top bar warns before a refusal does. Supply goes amber with two places left
and red once the farms are full; gold or lumber goes red for a second and a half
after an order was refused for want of it (the scene matches the words
`World.can_afford` refuses with, and `tests/warband/test_prices.py` holds the two
together). Hovering gold or lumber says how many peasants are on it.

A selected unit's numbers are what it was listed with, and what research or the
comrades at its elbows added stands beside them in gold; a melee unit's reach
reads "melee". `tests/warband/test_prices.py` and
`tests/warband/test_selection_panel.py` hold this reading, the lint walks
`hud_warnings`, `select_upgraded` and `pending_attack`, and because a price is drawn rather than
laid out as a label the lint measures what it needs against the box it was
given.

## Endless training

A building trains one or several unit types endlessly (`World.set_auto_train`,
a recorded order, so replays and the online authority see it); several take
turns, strictly, the next one first in `Building.auto`, and the one switched on
last goes next. A new building takes up what every building of its kind its
owner has trains endlessly (a player's second and third barracks once stood
idle beside the first one's endless archers). It starts a recruit only when it
stands idle: at once when switched on (a player who saw nothing happen clicked
again, and switched it off) or when the last recruit walks out, otherwise once
a second after the settlement's plans have had their turn, and only from what the
player's unpaid orders have not claimed (`World.committed`: sites builders are
walking to, then plans whose prerequisites stand, each from what those before
it left), per resource: what a player asked for is paid first, but a site
still short of lumber holds only lumber, so a farm waiting for lumber does not
hold back a peasant or a footman paid in gold; once its lumber is there it
holds its gold too, and endless training cannot starve it (a Barracks waiting
for lumber once stopped a player's endless peasants with a thousand gold in
the purse). Research planned at the building goes before its next recruit.
`World.auto_train_blocker` says why the next one waits; the building's
panel shows the rotation and that reason, and a loop marks each endless recruit
on the card. Shift with the recruit's key (or Shift+click, or a right-click on
its button) toggles it at the selected building; the same from the Train
catalogue toggles it at every building that trains it, finished or going up.
Cancel (X, or Grid's slot) cancels the last recruit and stops the building's
endless training, which would only start the next one. A rival's standing
orders are not in the seat's snapshot.

## Cancel mode

Asked for on 2026-09-24 (WB-065): one way to take back what was ordered, without
selecting each thing and finding its Cancel. **Ctrl+X** (Cmd+X on a Mac), or the
Cancel button beside Plans on the settlement row, turns it on; the button stands
red while it is. A red cross sits under the pointer's tip over the map (the
engine draws the system's arrow and offers no way to replace it), what a click
would take back is outlined in red, and the hint bar says what that is: "cancel
Barracks: a Footman and 2 Archers in training, endless Footmen". A click on

- a **plan** not yet started cancels the plan (`cancel_plan`; it was never paid);
- a **site** of the player's going up cancels the building, refunded in full
  (`cancel_building`; a plan whose site is dug goes with it);
- a finished building **at work** switches its endless training off
  (`set_auto_train` off, each type), empties its queue from the back
  (`cancel_train`, refunded) and cancels its research (`cancel_research`): one
  click, and the building makes nothing;
- anything else does nothing, and the hint says why: a unit, a rival's
  building, an idle building, open ground, and a peasant's next site. That one
  is the peasant's own queued order, not a plan, and no order takes back one
  site without the peasant's others; select the peasant and Stop it.

A box dragged in cancel mode is drawn red, outlines everything of the player's
whose centre it holds, and on release does the same to all of it (a row of
plans at once); it selects nothing. The mode stays on for the next click. Esc, a
right click (which then orders nobody anywhere) or Ctrl+X again leaves it; so
does arming any other mode (a unit's Move or Attack, placing a building, a
catalogue opened), and entering it disarms whatever order waited for its click.
Recalling a control group, Tab and Ctrl+A select as always and leave the mode on:
it is the settlement's, not the selection's.

**Why Ctrl+X.** The scene resolves a key as a control group, a Ctrl chord, the
card's command, then the scheme's global keys, so a chord is the same in all
three schemes by construction, and no card's letter, today's or a later race's,
recruit's or spell's, can ever shadow it. A plain key would have had to be free
on every card of every race in every scheme: of the letters only I, J, N, O
and Y are, none of them says cancel, and Grid would lose its one to the next
thing laid on the grid. X is what Classic and Modal already cancel with on a
building's card (that plain X stays the card's), and it is the cross the pointer
wears. Delete, the other obvious key, is missing on a Mac laptop (fn+⌫), and
Backspace already centres the camera on the base.

**What it gives.** Only orders that already exist, through `GameScene.attempt`,
so replays, the online authority's contract and the simulation fingerprint do
not move. A building's orders go in the order above: endless training off
first, so an emptied queue is not filled again at once; the queue from the
back, the recruit in training last; then the research. The first refusal stops
the click or the box there and its reason stays on the status line, so what it
interrupted is a prefix of that order: a building no longer endless, with its
recruit in training still at it, never a building still endless with its queue
gone. An online match (`NetworkGameScene.cancel_burst`) gives at most 20 of these
orders at once and 10 a second after that, whole targets only, because the room
server drops a connection past 40 at once; a box over more says how many are
left for the next one. Offline there is no such limit.
`tests/warband/test_cancel_mode.py` holds all of it.

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
but is on its way is planned, to wait for it (the planner sites it as the first
building of its size would be: ground depends on size alone); one whose
prerequisite nobody is making is refused, since its plan would wait for ever. Sites ordered and not begun, a
builder's next sites and the settlement's plans alike, are drawn as ghosts of their
buildings: the picture without its colour, seen through, on the ground under the
units, so a fight there shows, and without a caption (a row a tile apart once ran
its captions together); the ghost being placed refuses a site already taken, and a
catalogue counts them.

The planner's spot (`brains.ai.auto_site`) is the brains' own site search
around the player's hall nearest the camera, clear of the sites already planned
and keeping paths open; a hall goes by the nearest gold mine the player knows
that no hall of theirs, standing or planned, has claimed.

## Online

Both rules are in the authority's contract: live once a server rollout carries
this Warband; until then a client of this version and the live server disagree
on the order set (the promotion gate holds the published build back). The
authority checks `set_auto_train`'s building belongs to the seat and that `on`
and `plan_if_short` are booleans. `salvage` is a group order like `repair`: the
authority holds its peasants to the seat, and the rules refuse everything else
([salvage](salvage.md)).
