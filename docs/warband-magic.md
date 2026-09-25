# Warband magic

Aether and the spells it pays for, built in three steps: WB-063 (the resource),
WB-066 (the Mage Tower and the spells), WB-067 (the brains cast).

## Aether (WB-063)

Aether is the third resource and nobody carries it: no worker fetches it and
it is no `rules.Resource`. It rises from **ley rifts**, squares of ground the
size of a vault (2 × 2) that the map generator lays by every hall and, where a
cell has room, out in the shared ground (`docs/warband-maps.md`, *Ley rifts*).
`World.rifts` holds their top-left tiles, fixed for the match.

The **Aether Vault** (Arcane Vault, Spirit Cage, Moon Reliquary, Rune Vault:
2 × 2, 400 gold 200 lumber, needs a hall) is the one building a rift takes: any
other footprint on a rift, or a vault half on one, is refused, so a rift holds
one vault and nobody can deny one with a farm.

| rule | where |
|---|---|
| a finished vault standing square on a rift draws one aether every `[aether].every` seconds (2) into its owner's store | `World._draw_aether`, `Player.aether`, `Player.aether_charge` |
| the store holds `[aether].store` (150) for every finished vault; drawing stops at the cap and saves nothing up | `World.aether_cap` |
| a vault lost (razed, abandoned) lowers the cap at once and spills what no longer fits; its owner hears `spilled` | `World._spill` |
| a vault anywhere else stores and reaches, and draws nothing | `World.taps` |
| a point within `[aether].reach` tiles (10) of a finished vault's middle is in reach | `World.in_reach` |
| aether a second the player's vaults draw now | `World.aether_rate` |

The store is an integer and the charge counts whole steps (one per drawing
vault per step, `rules.AETHER_TICKS` of them an aether), so the draw is exact in
lockstep, in replays and in the compiled simulation. Saves carry the rifts, the
store and the charge. A seat's snapshot keeps a rival's store and charge
private, like its gold; the rifts are public ground, as the map it began with is.

**Seen.** The rift is a glowing crack that streams motes; a drawing vault's cube
glows and draws them in, and a vault of the player's whose store is full goes
dim (whether a rival's store is full is theirs to know: theirs are drawn
drawing). The HUD shows aether as *stored / cap* beside gold and lumber; the
vault's card says what it draws and whether it stands on a rift;
`MapView.draw_reach` washes a selected vault's reach violet, and WB-066 uses it
for an aimed spell. Placing a vault lights the free rifts the player knows,
snaps onto the one under the pointer and says when a site off them would not
draw. `tools/verify_aether.py` renders all of it.

**Not yet.** The brains build no vault: with nothing to spend aether on, one
would only cost them. WB-067 has them build one on their own rift.

## The Mage Tower and the spells (WB-066)

The **Mage Tower** (Mage Tower, Spirit Lodge, Starwell Spire, Rune Tower; cards
Arcanum, Spirits, Starwell, Runes: 2 × 2, 900 gold 400 lumber, 700 hit points,
needs a vault) researches three **levels** of magic, and researching a level is
choosing one of its three spells: the other two are **closed** for the match
(while one is being researched they wait, and a cancel opens them again). Level
I costs 600/200 and 60 s, level II 1000/400 and 90 s and waits for the Keep and a
level I spell, level III 1600/600 and 120 s and waits for a level II spell. Each
level offers a spell that sets the tempo, one that holds a fight and one that
hurts, so the choice follows the posture:

| level | aether / cooldown | spell | what its row of `spells.toml` does |
|---|---|---|---|
| I | 30 / 30 s | Haste | own units within 3: `haste` (speed ×1.4, blows ×0.8, 10 s) |
| I | | Mend | own units within 3: `mend` (+5 hp a second, 6 s), and ends `bleeding` |
| I | | Flame Strike | rivals within 1.5: 25 through armour, then `burn` (−2 a second, 4 s); a building takes the 25 and the burn's 8 at once |
| II | 60 / 60 s | Stoneskin | own units within 3: `stoneskin` (+4 armour, 15 s) |
| II | | Entangle | rivals on the ground within 2.5: `entangled` (rooted, 4 s); flyers are out of reach |
| II | | Wither | rivals within 3: `withered` (damage ×0.7, speed ×0.8, 12 s) |
| III | 120 / 120 s | Meteor | falls 2 s after the cast: 120 at the point to 60 at 2 tiles, ×1.5 on buildings, on everyone |
| III | | Summon | three Aether Elementals, the caster's for 40 s |
| III | | Battle Fury | own units within 6: `battle_fury` (damage ×1.4, speed ×1.2, 12 s) |

**The cast.** `World.cast(player, spell, point)` is the one order, `@recorded`
and checked whole before it changes anything (`World.can_cast`): the side is a
seat still in the match, the spell is one it researched, the point is on the
map (in the fog too: the cast is blind), the spell is off its cooldown, the store
holds its price at that point, and a summoning has open ground there. Within the
reach of a finished vault of the caster's (`World.in_reach`) a cast costs its
level's aether and cooldown; beyond every vault's reach both are `far` (3) times
as much (`World.cast_price`). A vault holds 150, sized to the dearest plain
price, so one vault casts any spell within its reach, level III's 120 too. A price
above what the vaults hold (`World.aether_cap`) is one no wait pays, and beyond
reach that is the dearer price: a level II spell's 180 takes two vaults, a level
III's 360 three. The refusal then says what the vaults hold and what will pay (a
cast within reach when the plain price fits, or as many more vaults as the price
takes), and the aim, the tower's card and the codex say it too. A cooldown is kept as the step the spell is ready
again (`Player.cooldowns`), so it counts in whole steps. A spell is a side's, not
a unit's: nothing walks anywhere to cast it.

**A spell is data.** A row of `spells.toml` says whom it touches (`own`: the
caster's units; `rivals`: every other seat's and the wilds'; `all`: friend and
foe) within `radius` of the point, measured to a body's edge or a building's wall,
and whether flyers are among them; the `buffs.toml` rows it `lays` and those it
`cleanses`; a blow of `damage` falling to `edge` at the rim, through armour if it
`pierces` (a spell's blow rolls nothing: it lands as its row says), on the
`buildings` it reaches too, times `building_factor`, with the whole drain of what it
lays at once since a building carries no condition; a `delay` before it lands; and
what it `summons`. `World._land_spell` is the one function that carries a row out,
now or when its delay is over. A new spell is a row there, a row in `buffs.toml`
for what it lays, an emblem (`art/production.py`), a look (`view.CONDITION_LOOKS`)
and a sound (`audio/spells.py`).

**Choice as data.** Each spell is also an upgrade (`rules.Upgrade`), priced by its
level: its research row carries `choice` (its level) and `after` (the level below,
one spell of which must be researched first). `World.chosen_instead` answers which
spell of a choice was taken instead, and whether for good; `World.can_research`,
the settlement's plans and the HUD all ask it. The upgrades the brains research are
named in their research orders, so they never research a spell (WB-067 teaches
them).

**Root.** A kind with `roots = true` (Entangle's) holds its bearer where it stands.
It is a rule of the movement alone: a walk waits in `_follow` and `_steer`, and a
flight in `_fly_to`, without counting towards the progress watchdog (it is not
stuck behind anybody), no crowd shoves it (`_nudge`), and a marching line does not
dress on it (`_line`). Its speed is still its speed (`World.speed_of`): what weighs
a walk, a healer's to its patient or a friend's under a falling stone, weighs it as
ever, and left six tiles behind it lets the group's pace go as any straggler does.
It still turns and strikes (or heals) what is in its reach, and its order stands for
when the roots let go.

**Lifetime.** A unit type with a `lifetime` (`UnitInfo.lifetime`, the Aether
Elemental's 40 s) is gone at the end of the step its time runs out
(`Unit.expires`): an `expired` event, no kill for anybody and no loss for its
side, and it takes no supply. It is a unit like any other while it lasts: it
fights on its own, can be ordered, is struck and killed; its card counts the
seconds it has left, in the aether's violet before its conditions. Only its spell
brings one: its row names the tower, but no building's `trains` holds it, and
`World.can_train` and a settlement plan both refuse it (`World.never_trained`,
as they refuse a creature of the wilds). No race names it
(`model.RACELESS`), and it is drawn by the render for every race: it stands in
`textures.UNPAINTED_UNITS`, since `tools/restyle.py` has no subject for a unit no
race fields. Its body is a sound family of its own (`aether_elemental` in
`audio/bodies.py`, generated pieces like every body's): its crystal shatters and its
light fades when it is struck down or its time runs out, it hums when it is ordered,
and a blow on it lands on something as hard as stone.

**Quickened.** Haste and Battle Fury together (×1.68) carry a unit faster than any
listed speed, so the bound a siege crew's own-side check scans within for friends
that may walk under its stone (`model._FASTEST`) is the fastest listed speed times
every quickening kind in `buffs.toml`. The wider scan changed a few stones the brains
throw (`tools/sim_bench.txt` moved; the fingerprint's matches did not).

**Delayed effects.** A Meteor is a `Projectile` of kind `spell` carrying its spell,
launched at the point and aimed there, landing after its delay through the same
`_land_projectiles` as a stone, so saves, replays and snapshots carry it as they
carry a stone in flight. Its shadow on the ground grows as it falls, and its ring
is a warning's orange for everyone: it falls on friend and foe. Shadow and ring are
circles on the ground, as the rules measure its reach.

**Online.** `cast` is a seat's own order (`authority.SEAT_ORDERS`): a seat casts
its own spells and names its own number. A rival's research, aether and cooldowns
are blanked in a seat's snapshot as its gold is. A cast and a landing
(`SPELL_EVENTS`: `cast`, `spell`) are news for the caster and for every seat that
sees any of the ground the spell touches; they are neither private (a cast in sight
is no secret) nor public (a blind cast into the fog, or one far from a rival, is
not the rival's to hear of: the design's "public news" is kept to the seats that
see it). A Meteor in the air rides the snapshots of those who see the ground under
it, as a stone does. The conditions the spells lay show on a rival's units in sight
under their own names: they tell only what was cast where the seat saw it.

**Found.** Before a spell is chosen nothing on the map shows magic, so the words
say where it comes from: How to play (F1) says a vault on a ley rift draws aether
for the spells a Mage Tower researches and that Alt+1-3 aims them; the aether's
tooltip in the top bar names the tower; the
Build card shows the tower greyed with its padlock and "Requires an Arcane Vault"
until a vault stands, and its summary says its spells are cast with aether; the
codex's Spells page (F2, 6) gives the rules. The objectives panel folds to its
heading while the card reaches into it (`GameScene._fold_objectives`): the Build
catalogue's four rows and the tower's hid their top row under the tutorial strip.

**Seen and heard.** The spell bar stands over the minimap once a spell is chosen,
never higher than the command row (`GameScene._fill_spell_bar`):
each spell's emblem with its cooldown sweeping round it, its name, its aether (red
while the store cannot pay it, and the most the vaults hold beside it while that is
less, "max 0" before a vault stands) and its key; Alt with the level's number, or a click, arms it, the
next click on the map casts it and Esc or a right click takes it back
(`docs/controls.md`). While a spell is aimed the ring of its radius follows the
pointer, violet within reach and orange beyond it, with the price at that point
beside it (and what the vaults hold, when it is more), and every vault's reach is
washed violet. The ring is a circle on the ground, as the reach wash and the burst
are: a spell touches every body within its radius, north and south as far as east
and west (a ring flattened like a body's selection ring showed units it would land
on as outside it). A landing bursts in the spell's
ink over the ground it touches and sounds (`audio/spells.py`, synthesised); a
Meteor's cast sounds its fall, its landing shakes the ground. A spell's conditions
show on the units: haste streaks behind a walking unit, a green glow and sparks for
mend, flames licking a burning one, stone grey, roots coiled at the feet, a withering
mist, a fury's red; a summoned elemental glows violet, carries its caster's colour on
its fists and shoulders (both sides can summon into one melee), and breaks into light
when it is gone, in its own body's death (its crystal shattering, its light fading).
The Mage Tower's card lays the levels out a row each, the chosen spell
ticked in gold and the closed ones struck through with the reason (while one is
being researched the other two are veiled, "Waiting"), and a spell's research says
when casting it takes more vaults than one; the codex has a page of the spells (6),
whose legend says what a vault holds, and its tech tree draws the tower's spells a
level a line.
`tools/verify_spells.py` renders all of it.

**Where the build departs from the design.** The design gave the tower its price
and the elementals their hit points and blow; the rest are this build's: the tower
2 × 2, 700 hit points, 50 s to build, sight 5 (its card names are Arcanum, Spirits,
Starwell and Runes: a card holds eight letters); an elemental no armour of the light class,
walking 2.4, a blow a second, sight 5. A summoned unit takes no supply (a summoning
that filled the farms would stop a side's training), and one whose time runs out is
gone, not killed. A spell's blow rolls nothing. The Meteor is not said to pierce, so
armour is taken off it, and it falls on the flyers too (nothing says it spares
them). Mend mends the living only, as a healer does; Haste, Stoneskin, Entangle,
Wither and Battle Fury take machines as well. "A cast another seat can see is public
news" is kept to the seats that see it: `PUBLIC_EVENTS` would tell every seat of a
blind cast into the fog. Cast and landing are two events, so a Meteor is news where
it is called down and where it lands. The Mage Tower's Cancel stands below its nine
spells, the one card beside the Build catalogue to reach that row. The Aether
Elemental is not painted (`textures.UNPAINTED_UNITS`: `tools/restyle.py` has no
subject for a unit no race fields); its sounds are generated pieces of a body
family of its own, as every body's are since WB-069. The spell bar never rises above
the command row: a column too tall for the room over the minimap stands a level's
spells on a row, which only a world with more than a spell a level needs. The
design's prices are kept, and a vault holds 150 (100 in WB-063): with 100, level
III's 120 could never be cast from one vault. Now one vault casts any spell within
its reach; beyond it a level II cast takes two vaults and a level III three, and
every place that shows a far price says so, since no wait fills a store that small
(WB-067 measures whether those numbers should stay).

**Not yet.** The brains neither research nor cast (WB-067); the numbers are the
design's, unmeasured.
