# The Undertow — world and story design for a second Warband campaign

**Status: implemented (phase 2).** The playable campaign lives in
`warband/story/new_campaign.py`, exporting `CAMPAIGN`
(`id='undertow'`, `cover='campaign/undertow.png'`), registered first and as
the default in `warband/story/catalog.py` beside *The Thornwood War*
(`warband/story/missions.py`), which stays fully playable. This document
remains the world/story design record; `docs/undertow-campaign.md` is the
player/design guide to what shipped, with solver-measured durations.

Deviations from this blueprint, each forced by a reproduced engine behaviour
rather than taste: idle/attack-move acquisition fights any hostile body in
sight, so the Mill pylon stands across the river on the north bank (not
beside the vault), Pell's crew strikes camp and withdraws at the parley
(resign; the mill stands empty), the grove's cut/whole plan is chosen in
dialogue before cutting or mustering at Moon Hall (the initial garrison must
never make that choice for the player), and the kneeling Guardian retires off-map and
returns as a player unit at the Maw. Salvage alone cannot fund the mesa camp
(hall + three farms costs more than the ruins yield), so stripping the Old
Camp also unpacks the caravan's packed stores. M4/M5 enemies are finite
scripted bands on one hostile seat (two "Open Hand" seats would fight each
other; Sella does not cast). Seam gold is counted per haul trip into a saved
variable with a 300 threshold, plus a third settle act (post a guard).
GROUND reads an explicit 450-aether threshold, and the first committed
ending locks the other two resolutions out. Solver mission-time for a full
run is roughly 15–25 minutes across all forks, well under the 50–65 below —
the blueprint's rosters and timers were compressed, not padded.
Every mechanic, file, and seam named below was checked against the code as it
stands: `warband/story/{campaign,missions,mission_scene,dialog}.py`,
`docs/warband-{campaign,magic,races,maps}.md`, `docs/controls.md`,
`docs/salvage.md`, and the constants in `warband/assets/constants/`.

| | |
|---|---|
| Campaign id (progress files, `--mission`) | `undertow` |
| Title | **The Undertow** |
| Tagline | *Every lock in the valley is a held breath. Someone has started letting go.* |
| Missions | 5, one per Step of the valley, descending |
| Length | 50–65 minutes on Medium, first time through |
| You play | Humans, Orcs, Elves, Dwarves, Humans — one Step's keeper per mission |
| New unit types | **None.** Every body on screen already has painted art and a voice |
| New simulation rules | **None.** Story-layer only; the sim fingerprint must not move |

## 1. The player-facing premise

*Catalog text (what the campaign screen shows over the mission list):*

> Below the farmlands of Millfield, the ground of Vesskar Hollow is cracked
> open. Violet aether breathes out of the cracks — the stuff spells are made
> of — and for two hundred years a chain of great locks has metered that
> breath so the valley could live on top of it. This spring the locks began
> to fail. Beasts are coming uphill out of the low Steps, the river is running
> violet, and Sella Voss, who built half the locks herself, has raised a
> company to open them all at once and finish it.
>
> Walk the Five Steps down to the Maw as each Step's keeper — miller, herder,
> grove-tender, lockwright — and decide, with your hands on the works, what
> the valley breathes next: seal it, open it, or spend the breath before it
> spends you.

## 2. Design pillars

1. **The map is the argument.** Every revelation is something the player can
   see on the ground (beasts running *at* a vault, not at a farm) and every
   choice is something the player *does* with units — attack a pylon, salvage
   a ruin, fell a tree line, build a vault on a rift, repair a keystone.
   Dialogue confirms choices; it never makes them in a menu the map
   contradicts.
2. **Five missions, five verbs.** Defend-and-decide, pack-up-and-move,
   parley-in-a-forest, hold-the-works, choose-the-ending. No two missions win
   the same way; only one (M4) can be won by razing an enemy base, and even it
   has a second win.
3. **Nobody is the villain of their own Step.** Each race is played from
   inside its own reasonable position. The antagonist's plan is the most
   defensible bad idea in the valley, and the player may end up carrying it
   out — better than she would have.
4. **Choices compound visibly.** Each mission's action-choice changes the next
   missions' starting forces, buildings, prices, or hazards, and all four
   feed the finale's starting board and its three endings. The campaign
   screen's epilogue reads every flag back.
5. **Teach by needing.** M1 needs training, repair, and one spell. M2 needs
   salvage, escorts, and sappers. M3 needs vision, forest-walking, and tree
   felling. M4 needs towers, mortars, repair-under-fire, and rift building.
   M5 needs all of it. Nothing is taught in a mission that exists only to
   teach, and nothing is unwinnable by script.
6. **Fail forward inside a mission; fail honestly at its edges.** Losing a
   vault, a drover, or a lock changes the mission and the flag — it rarely
   ends it. A mission ends in defeat only where the objective panel said it
   would: a hall fallen, a named keeper dead.

Non-goals: no new race, no hero abilities/inventory/XP, no alliance system,
no naval or transport play, no hidden-information puzzles, no timed
"survive N minutes" as a primary activity (every hold is against a finite,
countable set of waves the objectives name).

## 3. The world

### 3.1 Geography: Vesskar Hollow and the Five Steps

Vesskar Hollow is a terraced basin a week's walk across, cut into five broad
Steps that descend southward like a giant's stair. The river **Sorrow** rises
in the north hills, spills Step to Step in mill-races and fords, and at the
bottom falls into **the Maw**: a crater of cracked, violet-glowing ground
where the world's largest ley rifts meet. The water that falls in does not
pool. It comes back as the Hollow's closed weather — low mist at dawn, and,
when the aether pressure rises, a warm violet rain the valley calls a
**bloom**. A bloom is not weather to shelter from; it is the ground exhaling
through everything standing on it. Beasts go mad-eyed and uphill, dead stone
remembers it was once spelled (the wilds' golems and guardians), trees grow a
season in a night, and loose aether gathers itself into elementals that live
for half a minute and spend it hitting things.

```
        N — the north hills (the Sorrow rises)
  ┌──────────────────────────────────────────────┐
  │ STEP 5 · MILLFIELD        humans · farmland  │  M1
  │   mill-race, First Lock (the Mill Lock)      │
  ├─ the Lick (salt pans, three fords) ──────────┤
  │ STEP 4 · THE SALTMARCHES  orcs · herd camps  │  M2
  │   mesa of the Broken Tooth, Second Lock      │
  ├─ the Deep Grove closes over the road ────────┤
  │ STEP 3 · THE DEEP GROVE   elves · the filter │  M3
  │   Moon Hall, Third Lock grown, not built     │
  ├─ the Tarnstair (a road of dwarf causeways) ──┤
  │ STEP 2 · TARNLOCK         dwarves · the works│  M4
  │   lock basin, the endless seam, Fourth Lock  │
  ├─ the Ashen Slope (nothing grows; rifts) ─────┤
  │ STEP 1 · THE MAW          nobody's · crater  │  M5
  │   the Keystone, three seal-pylons, the rifts │
  └──────────────────────────────────────────────┘
        S — beyond the rim, dead salt desert
```

Each Step is one hand-authored mission map (section 7). The campaign descends:
the player always knows the next mission is *lower, warmer, more violet* than
the last, and the campaign screen's previews show the descent.

### 3.2 The aether, the locks, and the Weight (canon that binds the mechanics)

These are the rules of the world, written so that existing game mechanics are
their direct expression. Phase 2 must not contradict them in dialogue.

- **Ley rifts are where the ground breathes out.** A vault built square on a
  rift (the existing rule) is a *lung with a lid*: it draws the breath in at a
  measured rate and stores it (aether). A rift with no vault breathes free —
  beautiful, and how blooms start.
- **The Chain of Locks** is the treaty-works of the Compact (section 3.3): on each
  Step, a cluster of vaults, a mage tower, and a **lock-pylon** — a squat
  rune-carved anchor that ties the Step's vaults to the Keystone at the Maw.
  A lock does not stop the breath; it *spends* it slowly — on spells, on
  warmth in the mill-races, on the grove's growth. That is why the valley is
  rich: it lives on metered magic.
- **The Weight** is what the breath becomes when it cannot rise: over
  centuries, aether pressed down under Tarnlock has crystallised into the
  **endless gold seam**. The seam is literally the lid. Mining it (the
  existing endless deposit) is profitable beyond dreams and thins the cap a
  cartload at a time. The dwarves know. The dwarves have known for thirty
  years. This is the campaign's central secret, revealed in M4.
- **The Deep Grove is the overflow.** Elven Regrowth, written valley-large:
  the grove drinks surplus breath and spends it growing, which is why felled
  grove trees stand again in a minute and why the grove's border creeps after
  every wet spring. The grove is not scenery; it is a safety valve with
  opinions.
- **The wilds are the early warning.** Bloom-touched wolves, spiders, trolls
  — and older, worse things near the Maw — are creatures that have breathed
  too much. They are drawn *toward* free aether (an untapped rift, a straining
  vault) and flee *uphill* from a bloom front. Both behaviours are readable on
  the map and are used as storytelling in M1 and M3.
- **Aether elementals are the breath with nowhere to go** — which is why a
  spell can summon them deliberately (shaped, loyal, brief) and why a straining
  rift sheds them wild (unshaped, furious, brief). Same body, same sounds,
  opposite meaning. A wild elemental on screen always means: *pressure here*.

### 3.3 History: why there is a war, and why now

| When | What |
|---|---|
| ~400 years ago | The Hollow is settled from the top down; the Maw is a wonder, then a hazard, then a graveyard of two expeditions. |
| 212 years ago | **The First Bloom.** A wet spring, a violet week, a quarry outside Tarnlock stands up and walks (the first golems). The Maw Steps are abandoned for a generation. |
| 200 years ago | **The Lockwrights' Compact.** All four peoples build the Chain of Locks under the first First Lockwright, a dwarf named Tarn. Each Step gets a keeper-people and a keeper's duty: millers, herders, grove-tenders, lockwrights. The Keystone is set at the Maw. The valley prospers on metered magic. |
| 60 years ago | The mage towers are rebuilt tall. Spell-craft becomes a trade, then a monopoly: kingdoms outside the Hollow buy castings; villages inside it queue. The locks' surplus increasingly serves whoever can pay gold for a tower. |
| 30 years ago | Tarnlock's miners, following a rich vein *down*, break into the endless seam. The Hold's council classifies what it is. Mining continues, quietly, at "survey" scale. The seam's gold quietly funds two generations of lock maintenance — the original sin comes with receipts. |
| 6 years ago | **The Ashford Account.** A minor bloom is coming up Step 4 during lambing. Captain Issa Renn, young Lockwatch officer on duty, signs the order that vents it through an orc lambing camp rather than through Millfield's mill-race: fewer buildings, more warning time, defensible arithmetic. Nine herders die, among them Brakk's sister. The order was lawful. Brakk has the paperwork. |
| Last winter | Sella Voss, First Lockwright for nineteen years, completes her private survey of the *symptoms* — rifts drawing faster year on year, lock-vaults straining, the grove creeping and drinking at its limit — and lays the numbers before the Compact council: the next big breath bursts a Step. Her remedy (open everything now, controlled, while controlled is still possible) is voted down, 4 peoples to 0. She resigns the same evening, taking her tools, her maps, and half the Lockwatch's engineers who believe her arithmetic. What her survey never contained is Tarnlock's classified half of the picture (see section 4, Sella Voss). |
| This spring (M1) | The Mill Lock's vault begins to strain — drawing faster than it should, glowing at night. Bloom-touched beasts come uphill into Millfield. Somewhere below, Sella's company, **the Open Hand**, has started work on the Chain — from the bottom up. |

**Why the war exists, in one sentence each:**

- The Compact says: *the locks have held for two hundred years; mend them.*
- Sella Voss says: *the locks are a dam across a rising river, metered for
  the rich; open them now, by hand, at a cost we choose — or the river opens
  them for us at a cost it chooses.*
- The valley says nothing. It breathes.

### 3.4 The four peoples of the Hollow

Warband's four races are the Compact's four keeper-peoples. Each mission is
played as that Step's keeper, with that race's full existing roster, voice,
music, and arts; their racial mechanics are story facts:

| People | Step & duty | What they want | What they fear | Their race as story |
|---|---|---|---|---|
| **Humans of Millfield** | Step 5: mill the Sorrow, keep the First Lock, feed the Hollow | A harvest, a working mill, no excitement | Being the valley's shield: everything comes uphill to them first | Drill (fast training) is a militia that has drilled against bloom-beasts for 200 years; the Gryphon Riders are the Lockwatch's own |
| **Orcs of the Saltmarches** | Step 4: herd the pans, watch the beasts, keep the Second Lock | To move camp uphill *before* the bloom, for once, instead of being vented through | Another Ashford Account with their name on the small side of the arithmetic | Rage is bloom-sickness turned useful: a hurt herder burns aether and hits harder; Plunder is a people who have salvaged three drowned camps' worth of their own history |
| **Elves of the Deep Grove** | Step 3: tend the filter, read the roots, keep the Third Lock grown | The grove whole; the breath spent as growth, as it has always been | That the grove has a limit, and that they are the ones who will be asked to spend it | Keen eyes: two centuries of watching a dark wood for violet light. Regrowth *is* the overflow (section 3.2). Treants are the grove's own lock-wardens |
| **Dwarves of Tarnlock** | Step 2: the works, the weights, the Fourth Lock, the Keystone's drawings | The Chain mended, the seam's secret kept one more generation | The half of the picture Sella was never shown is *theirs* — and she reached the right diagnosis without it | Stonework is lock-building as a culture; Deep Mining is the sin itself (150 a trip, out of the lid); Rune Golems are quarry-stone bound *properly* this time |

## 4. The cast

Five principals, three supporting voices. Every speaker is an existing painted,
voiced unit type; the speaker table is a phase-2 `Speaker` dict exactly as
Thornwood's. No character requires a new model, sheet, or sound family.
Dialogue budget for the whole campaign: ~180 lines, none over three sentences,
no briefing over 6 lines, no in-mission interruption over 4.

### Captain Issa Renn — Human Knight (`U.KNIGHT`), the player's through-line

Lockwatch captain, Millfield militia. Competent, plain-spoken, allergic to
ceremony. Signed the Ashford Account at twenty-four and has been paying it off
in diligence ever since: she knows every lock-wrench in the valley by weight
because she intends never to do arithmetic with lives again. **Want:** the
valley safe and her signature off anything like that order, ever. **Fear:** the
arithmetic was right. **Arc:** from *hold every Step* (M1) through *the Steps
hold each other or none* (M3–M4), to the player deciding at the Maw what kind
of right she can live with. Her Knight is a real unit in M1 and M5.

> Issa: "Nobody dies for a metaphor on my watch. The vault is a *lid*. We mend
> lids."

### Brakk the Unbitten — Orc Shaman (`U.CLERIC`, orc), Step 4's keeper

Herd-priest and de facto chief of the Saltmarch camps; called Unbitten because
he walks bloom-touched wolf country unarmed and comes back, season after
season, carrying their sick pups to be doctored or buried. Lost his sister to
the Ashford venting. Keeps the order — Issa's signature — folded in his
medicine pouch, not as a weapon; as a *receipt*. **Want:** his people moved
uphill on their own feet, in their own time, before anyone vents anything
through them again. **Fear:** that he'll forgive Issa before she's earned it,
or after it's too late to matter. **Arc:** the receipt is produced in M2's
debrief; what Issa (the player) has done at the Mill Lock in M1 decides how
that conversation lands, and what Brakk brings to the Maw in M5.

> Brakk: "You vented your bloom through my sister's lambing camp, Captain. The
> paper says it was the smaller number. I have carried the paper six years,
> waiting to meet someone it was smaller *to*."

### Wrenna Root-Reader — Elf Druid (`U.CLERIC`, elf), Step 3's keeper

Grove-tender who reads pressure the way millers read water: by root, ring, and
the violet in the sap. Cheerful in the specific way of people who deliver bad
news professionally. She found, years ago, that the grove's deepest root-map
*is* the Chain's plan — the trees grew along the locks' lines, or the locks
were built along the trees'; she no longer knows which, and she showed the map
to Sella Voss in friendship the winter before the resignation. **Want:** the
grove unspent. **Fear:** she already spent it, with a map and a pot of tea.
**Arc:** in M3 she must choose (through the player's hands) between cutting
her own grove's throat to save its heart, or defending the whole wood and
trusting it to drink a bloom at full strength.

> Wrenna: "The grove is not *near* the Third Lock, Captain. The grove is what
> the Third Lock is *for*. Cut your firebreak, and bring a saw that weeps."

### Dagna Leadhand — Dwarf Runepriest (`U.CLERIC`, dwarf), Step 2's keeper

Lockwright-engineer of Tarnlock, fourth of her line to hold the Fourth Lock's
keys, granddaughter of the surveyor who found the seam. Devout about torque.
She has read Sella's survey — and the classified seam profile behind it,
which her family *wrote* and Sella was never shown — and
she has come to the works this spring to do the thing her council will not
vote for: cap the seam with a vault and take the blame in writing. Then Sella's
siege arrives and gives her a war instead. **Want:** the Chain whole and the
secret out — in that order, which is the problem. **Fear:** there is no order
that gets both. **Arc:** the confession lands in M4 whichever way the player
plays the seam; whether it lands as courage or as an epitaph is the player's
doing.

> Dagna: "Every cart of that gold bought a lock-gasket, Captain. We have been
> selling the lid to pay for the pot. I am done not saying it."

### Sella Voss, the Unclencher — Human Cleric portrait in Open Hand colours (`U.CLERIC`, `player=1`), the antagonist

First Lockwright for nineteen years; Issa's teacher; the valley's best living
engineer of aether. Not a tyrant, not a cultist: a woman who did the survey,
believed it, lost the vote, and decided that being voted down is not the same
as being wrong. Her company, the **Open Hand**, is engineers, discharged
Lockwatch, bloom-widows, and the kind of young person who has buried two
Step-villages and would like the dying to be *for* something. Her plan is
precise and, on her numbers, merciful:

**Open every lock in one rising sequence, bottom to top, over nine days** —
vent the accumulated breath of two centuries as one long, managed bloom the
valley has been warned about, evacuated for, and dug in against — and end the
age of locks altogether: no more metering, no more mage-tower monopolies, no
more Ashford arithmetic, because no one holds a lid anyone else can be vented
through. The bloom will take the lower Steps' works, the mill-races, probably
the grove. People, moved in time, it need not take. Afterward the Hollow is
wilder, poorer, honest weather under everyone's feet.

Her logic is sound on every point the player can check, and the campaign lets
the player check all of them. She is wrong about exactly one thing, and it is
not arithmetic: **the Weight — specifically the seam's geometry, which she
was never given.** What her survey *did* know, from surface instruments
anyone may take: rift draw-rates rising, vault strain, grove creep — the
symptoms of rising pressure. What it did *not* know, because Tarnlock's
council has classified it for thirty years and fed her redacted summaries:
the endless seam's depth profile and what it is made of. In the summaries
she was allowed to see, the seam is an ordinarily rich vein that happens to
sit above the deep aether — *wealth sitting on the problem*. In truth it is
the problem's lid (section 3.2): crystallised breath under load. Her
sequence opens the locks first and leaves the "vein" for last, which means
the breath she vents from below would meet two hundred years of crystallised
breath venting through a thinned cap from above — roughly double the
pressure she planned for, at Tarnlock, occupied. She knows the valley is
running out of time; she does not know her chosen order of operations is
the one order that bursts a Step. That distinction — right diagnosis,
withheld mechanism, fatal sequence — is the whole tragedy, and dialogue in
M4/M5 must keep it exact. When the player can prove it (M4's
debrief, with Dagna's own surveys), her plan does not become evil — it becomes
*unfinished*, and M5 is the argument about how to finish it. She never lies to
the player. She lies once, by omission, to her own sappers — about how long
the Tarnlock step of the sequence gives them to get clear — and that lie is
what her own people walk away from her over, if the player gives them the
chance (section 7, M4/M5).

> Sella: "I am not opening the valley to hurt it, Issa. I am opening it the way
> you open a hand that has held a coal too long. Count my dead when I'm done.
> Then count the Compact's, and take your time — they're better filed."

### Supporting voices

| Speaker | Type | Role |
|---|---|---|
| **Mother Hasp**, miller-reeve of Millfield | `U.PEASANT` (human) | The valley's ground-level voice: flour, rents, funerals. Delivers M1's stakes and, in the epilogue, its verdict. |
| **Ugga Salt-Tongue**, drover | `U.PEASANT` (orc) | M2's comic-practical voice; the caravan's needs in one sentence at a time. |
| **Sergeant Pell**, Lockwatch militia | `U.FOOTMAN` (human) | Leads the M3 woodcutter party acting on Issa's standing orders. Not a villain: a man with a saw, a warrant, and a sister in Millfield. |

## 5. The plot, and how each revelation changes the play

### 5.1 Shape

Three acts, five missions, descending. Act I (*The Breath Rises*, M1–M2) is
defence and flight: the valley's top two Steps react. Act II (*What the Locks
Are For*, M3–M4) is the middle: the player learns what the grove filters and
what the seam caps, each time by having to *use* the knowledge inside the same
mission. Act III (*The Maw*, M5) converges every keeper, every flag, and the
antagonist on one crater, where the ending is a thing the player builds,
repairs, or destroys — three different final missions sharing one map.

### 5.2 The revelation ladder

Each row: what the player learns, where, and — the design rule — **what it
changes about the orders they give in the following minutes.**

| # | Revelation | Mission & moment | What changes in play |
|---|---|---|---|
| 1 | The beasts are not hunting the village; they are drawn to the straining vault, and the rest are fleeing uphill from something *below* | M1, wave 2 visibly paths past farms to the vault | M1 forks: defend the vault as bait-and-livelihood, or shutter it by attacking its lock-pylon and let the scent die — different fights, different village, different flag |
| 2 | The "raiders" on Step 4 are the Open Hand *warning* the camps and sabotaging the road south — toward the locks, away from people | M2, rockfall drops on the caravan's ford but no pursuit presses the drovers | M2's enemy stops being a base to raze (there isn't one) and becomes a timetable to beat: blast through, detour, or open the mill-dam and flood *their* camp at Millfield's expense |
| 3 | Ashford was not a rumour: Brakk has Issa's signed order | M2 debrief | No order changes — instead it reprices every later "hold the lock" line, and M5's orc contribution is keyed to how M1 treated a village of strangers |
| 4 | The woodcutters in the grove are Issa's own militia, cutting a firebreak on her standing orders against a bloom-front — both sides are the player's people | M3, parley trigger at the woodcutters' camp | M3 forks: join the cutting (your gatherers fell a marked line; less bloom, wounded grove) or drive your own side off and take the bloom at full strength through the Moonwell |
| 5 | The grove's roots map the Chain; Wrenna gave that map to Sella | M3 debrief | Explains the Open Hand's precision in M4 (their sappers know exactly which vaults are locks) and sets the Maw's seal-pylon geography |
| 6 | The endless seam is crystallised breath — the lid. Mining it thins the cap; Sella's sequence, designed in ignorance of it, would burst Tarnlock | M4, mid-siege, when the player first works the seam or caps it | M4's economy becomes the argument: mine the seam for the gold to win the siege (and spawn wild elementals with every few hundred drawn) or cap it with a vault and win poorer. M5's hazard table is written here |
| 7 | Sella lied to her sappers about their margin at Tarnlock | M4 debrief (captured sapper, named in one line) | M5: the Open Hand can be *split*, not just beaten — destroying their mage tower ends the siege; sparing it while finishing any ending brings their engineers over in the epilogue |
| 8 | There is a third way to spend a breath: give it somewhere to *go* that is not up — the grove's roots, an Ancient's hollow heart-stone, a ring of vaults drinking at the Maw itself | M5 briefing, assembled from which of those the player still has | The GROUND ending (section 6.2) exists only from the parts the player preserved; the briefing names what's missing and why, in dialogue, before a shot is fired |

### 5.3 Resolution

The war ends at the Maw in one of three player-built endings (section 6.2): the
Chain **resealed** (the Compact survives, chastened, with the seam capped or
still quietly mined behind it), the valley **opened** (Sella's plan, executed
by the player's hand with the Weight accounted for — which is more than she
could have done), or the breath **grounded** (spent into root, stone, and
vault at the Maw: the locks stay, but as plumbing rather than as a dam). Sella
survives every ending unless the player razes her tower in M5; her last lines
are keyed to whether she was beaten, joined, or answered. No ending is the
"good" one: each epilogue (section 6.3) pays for what it chose, in the flags' own
coin.

## 6. Choices, flags, and endings

### 6.1 The flag table

All flags are booleans (the dialogue layer's `Line.when`/`unless` reads
truthiness; §11). Every flag is set by a *map action*, never by a dialogue
menu alone; dialogue confirms irreversible commitments in M5 only. Flags are
namespaced so they can never collide with Thornwood's `truce`/`powder`/`burn`.

| Flag | Set in | By this action | Read in | Visible effect |
|---|---|---|---|---|
| `undertow_mill_vault` | M1 | Hold the straining vault through both surges (vs. shutter it via its pylon) | M2 briefing, M5 start, epilogue | M5: the mill-vault's crew arrives as a pre-placed second Arcane Vault on a side rift + 60 starting aether. Shuttered instead: Brakk's trust (§6.1 note) and Millfield's farms stand — M5 starts +2 Farms built and +400 gold of sold flour |
| `undertow_dam` | M2 | Blast the mill-dam pylon to flood the Open Hand camp (vs. spare it) | M5 start, epilogue | Blown: Millfield's millpond is dry — M5 starts one Farm fewer, +800 gold (salvaged millstones), Mother Hasp's epilogue line turns. Spared: M5's mill-race rift taps at double story weight — expressed as +1 pre-placed Vault |
| `undertow_grove_cut` | M3 | Fell the firebreak line (vs. drive off the woodcutters and channel the bloom) | M5 GROUND terms, epilogue | Cut: the grove cannot help ground the breath; M5's GROUND needs the Guardian or the core. Whole: GROUND is open on grove alone, and a wild Treant camp guards one Maw approach *for* nobody — it attacks Open Hand bands that stray in (a wilds camp, existing behaviour) |
| `undertow_guardian_ally` | M3 | Bring Wrenna to the Ancient Guardian without attacking it | M5 | A player-controlled Ancient Guardian joins at the Maw (§9.2 probe + fallback); GROUND is open |
| `undertow_guardian_core` | M3 | Kill the Guardian (optional boss) | M5 | Its heart-stone: one Maw vault pre-built, +120 starting aether; GROUND is open. (Ally and core are exclusive by construction) |
| `undertow_seam_capped` | M4 | Build a Rune Vault square on the seam-rift | M5 hazards, epilogue | No wild-elemental blooms at the Maw; Dagna's confession goes to the council in writing |
| `undertow_seam_mined` | M4 | Mine ≥1,500 gold from the endless seam during the siege | M5 start + hazards, epilogue | +2,000 gold at the Maw — and a wild elemental bloom at a random Maw rift every ~90 s of M5, forever, until an ending lands. Mutually exclusive with capped (capping after mining sets capped and clears the M5 gate for mined's gold but keeps a reduced bloom rate — implemented as: capped wins the hazard, mined keeps half the gold; the setup reads both) |
| `undertow_ending_sealed` / `_open` / `_ground` | M5 | The ending the player builds (§6.2) | Epilogue | Exactly one is set; each picks the epilogue's spine |

Note on Brakk's trust: deliberately *not* a numeric reputation. Its whole
expression is M1's flag read in M2's briefing/debrief wording and in what the
Saltmarches send to the Maw: if Millfield's vault was shuttered to spare a
village (people over works — the opposite arithmetic to Ashford), Brakk sends
a band expressed as player-owned reinforcements in M5 (4 Footmen + 2 Archers
at the north trail, in the player's colours per the no-allies rule, §9.1);
if the vault was held at the village's risk, he sends gold and a colder line.
Either way he comes. The receipt conversation happens either way; only its
temperature is earned.

### 6.2 The three endings are three final missions

M5 opens with all three endings on the objectives panel as mutually exclusive
optional objectives, each phrased as the physical act it is. The first
*committed* act (first repair order on the Keystone / first seal-pylon
destroyed / first vault completed on a Maw rift) fires a 3-line confirmation
dialogue naming what is being chosen and what it forecloses; the other two
objectives then hide. This is the only dialogue-gated commitment in the
campaign, and it confirms an act already begun rather than replacing it.

| Ending | The act (all existing orders) | The fight it makes | Needs |
|---|---|---|---|
| **RESEAL** | Peasants **repair the Keystone** landmark from 40 % to full while ≥2 of your vaults stand, then break the Open Hand's final assault on it | A defence of one point against Sella's whole remaining strength; her mage tower casts throughout | Nothing but hands: always available |
| **OPEN** | **Destroy the three seal-pylons** (attack; catapults and knights shine) in any order | An offensive demolition under fire; at the third pylon Sella stands her people down (her side resigns) and the finale becomes riding out one scripted bloom-wave of wild elementals with her engineers' towers now silent | Nothing: always available. Faster with `undertow_seam_mined` gold, bloodier with its blooms |
| **GROUND** | **Build a vault square on each of the three Maw rifts** and keep all three standing until your aether store first reaches its cap (3 × 150) — the breath, given somewhere to go, goes there | An economy-under-fire mission: every spell cast delays the ending, every vault razed restarts a third of it; the Open Hand prioritises your builders (scripted bands, then their AI) | Grove whole, **or** Guardian ally, **or** Guardian core (any one). If the player has none, the objective is shown struck-through in the briefing dialogue with its reason — never silently absent |

### 6.3 Epilogue structure

Eight to ten narration lines, composed from the ending spine plus one verse
per flag — the exact mechanism Thornwood's epilogue already uses
(`Line.when`/`unless` over progress flags). Each ending pays: RESEAL keeps the
Compact and names the next survey it cannot dodge; OPEN takes the lower
Steps' works and gives the Hollow wild weather and free magic; GROUND keeps
the locks as plumbing and makes the keepers a maintenance rota forever ("a
lesser priesthood, with wrenches"). Sella's verse, Brakk's, the grove's, and
the seam's each turn on their flag. Mother Hasp gets the last line in all
three worlds, and it is about flour.

## 7. Mission blueprints

### 7.0 How every mission is built (the shared seam)

Each mission's `setup(run)` **constructs its own hand-authored `World`** from
a terrain matrix written in `new_campaign.py`, assigns it to `run.world`, and
then places the bespoke board on it. This is the confirmed phase-2 seam:
`build_world`'s rift cleanup and side naming operate on `run.world` *after*
setup, so a crafted world survives. Consequences the designs below rely on:

- **Geography is authored, not generated.** The `Mission`'s `size`/`theme`/
  `layout`/`seed` fields still must be valid (the interim generated world is
  built and discarded); each blueprint below names values whose dimensions
  match its matrix, so the campaign-screen preview (which renders
  `build_world`, i.e. the *setup* world) shows the true map. No mission may
  depend on generated terrain, generated mines, or generated rift positions.
- The crafted `World` is built with `magic=True` (ley rifts, vaults, spells),
  `wilds` only where camps are wanted (camps are then placed deliberately,
  never left to the generator), `scripted=True` set by `build_world`'s
  existing line — setup must set it too if it replaces the world after that
  line runs; phase 2 orders this explicitly. Side names are reapplied after
  setup by the fixed `build_world`.
- **Rifts are placed by hand** with the public `World.lay_rifts` (already
  used by `mission_scene.build_world`): every rift in this campaign is where
  it is for a story reason, and its 2×2 footprint is drawn in the matrix.
- Everything after setup is today's engine: `Objective` predicates and
  one-shot `Trigger`s over `Run`, `run.spawn`/`run.place` for arrivals,
  scripted sides (`ai=None`) moved only by triggers, AI sides via
  `make_brain` with the campaign difficulty shift, dialogue via `run.say`,
  camera cues via `run.look` (explored ground only — design cues
  accordingly), and player orders exclusively through the ordinary card.
- **Ownership rule for every destructible story object:** the player cannot
  attack their own buildings under ordinary orders, and this design never
  asks them to. Every pylon or landmark the player must destroy is owned by
  a hostile or scripted side from the start — the Mill pylon stands in side
  1's colours, overgrown and claimed by the bloom-growth choking it; the
  mill-dam pylon is held by the Open Hand crew that seized the dam; the
  Maw's seal-pylons are Open Hand works. Things the player owns are only
  ever repaired, rebuilt, or lost. No demolition dialogue-menu, no new
  order.
- **No terrain changes mid-mission, ever.** Floods, rockfalls, and blooms
  are real placed/removed buildings and units plus effects — never a
  narrated water level. The M2 flood is a building destroyed and a camp
  resigned in the same trigger; the map's water never moves.

Terrain legend for the sketches: `.` grass of the Step's theme, `T` trees,
`~` water, `#` rock, `*` ley rift (2×2), `$` gold deposit, letters are
landmarks and starts keyed under each sketch. Sketches are topology, not
tiles: phase 2 draws the true matrices at the named sizes and playtests the
pathing (§13).

### 7.1 M1 — Millfield (`undertow_mill`, Act I · The Breath Rises)

*Verb: defend — then decide what you were defending.*

- **Play:** Humans (Issa). **Sides:** 0 Millfield (human), 1 The Straining
  (scripted, orc colours for beast-bands — the bodies are `WOLF`/`SPIDER`/
  `TROLL`, raceless). **Map:** 48×40, `SUMMER`, declared `Layout.PLAINS`,
  seed 2101. **Time:** 8–11 min.
- **Terrain:** a mill-village in an open bowl. The Sorrow crosses the north
  third under one bridge-ford; the mill-race runs to the Town Hall. One rift,
  beside the race, already carrying the village's Arcane Vault. Open farmland
  south; beast-trails enter from three groves (SE, S, SW). No rock walls:
  this Step is exposed on purpose, and the player learns the bowl by
  defending all of it.

```
   TTT....~~~~~~..TT......TTT
   .....H.......~~.....T.....
   ..$..F.F......g...........     H hall   F farms   g gold
   ......*V+p.....B......T..      V vault on rift *   p lock-pylon
   ..T.......................     B barracks
   .......t.........t....T..      t beast-trails (groves)
   .T.........t...........TT
```

- **Start:** Town Hall, 2 Farms, Barracks, the Vault on its rift (drawing,
  visibly overbright — §8), the **Mill Lock-pylon** landmark beside it
  (scripted-side, attackable, inert). Issa (Knight, id in vars), 3 Footmen,
  2 Archers, 1 Cleric, 4 Peasants. 900 gold / 350 lumber / 60 aether.
  **Mend pre-researched** (setup adds the upgrade; no Mage Tower needed or
  built — lumber is short enough that beelining one is a real but poor
  choice). Supply must exceed the start force — phase 2 counts the farms
  (Thornwood's over-cap starts are a recorded bug class, §14).
- **Objectives, as they appear:**
  1. *Drive the beasts out of Millfield* (wave 1: wolves at the farms —
     teaches selection, attack-move, the Cleric).
  2. *Mend the wounded* (shown after wave 1 leaves the Cleric's patients:
     completed by casting Mend with Alt+1 or by the Cleric's work —
     predicate: no starting soldier below half health; teaches the spell bar
     with a target that stands still).
  3. After revelation 1, two optional objectives shown together, either wins:
     *Hold the vault through the surges* (two further waves, named and
     counted in the text — spiders, then a troll with wolves) **or**
     *Shutter the vault: destroy its lock-pylon*.
  4. *The Town Hall must stand* (fail line, always visible).
     *Issa must survive* is **not** a fail line here: if her Knight falls she
     is dragged to the hall and returns at half health after 20 s, once per
     mission, here and in M4 — heroes matter from M2 onward, and M1 says so.
- **Reversal:** wave 2 spawns at a grove, paths *past* an undefended farm,
  and attacks the vault. Camera cue to the vault (explored ground), 3-line
  dialogue (Issa / Hasp / Issa) naming what the player just saw. The two
  fork objectives appear in the same frame.
- **The choice in controls:** attack the pylon with anything (it is a
  rival-side building; the ordinary Attack order, taught by its objective
  line and a minimap ping). On its destruction the trigger shutters the
  vault: the vault is removed standing (setup-phase `Run.replace` precedent —
  phase 2 gives triggers the same small helper; §9.2), a **lock-turn** effect
  and sound play (§8–9), remaining beasts lose their target and are resigned
  off the south edge, and the mission resolves after a short cleanup wave
  that is now hunting farms, briefly and beatably. Holding instead keeps the
  aether income for Mend through two escalating waves and sets
  `undertow_mill_vault`.
- **Failure & recovery:** the vault's own destruction never fails the
  mission — it *decides* it (flag false, Hasp's debrief line: "It decided for
  us, then"), with the farms' damage as the price. Hall fallen = defeat.
  If the player's soldiers are wiped, Millfield's reserve (2 Footmen, once)
  musters at the hall with a toast — the recovery is in-fiction and finite.
- **Dialogue beats:** briefing 5 lines (Hasp's flour, Issa's lid); reversal 3;
  pylon-first-hit warning 1 (Issa: "Once that pylon's down, the vault's dark
  for good. Be sure."); debrief 4 + Brakk's arrival (2) regardless of fork,
  temperature keyed to the flag.
- **Implementation seam:** matrix world; waves are `Trigger`s on
  `objective_done`/timers with a floor timer so a turtling player is never
  waited on (wave 3 fires on wave 2 cleared *or* +120 s); beast targeting is
  `spawn(..., attack=vault.center)`; Mend objective is a plain `Run`
  predicate over unit health; shutter path uses the building-removal helper
  (§9.2, R2). No AI side. **Tuning knobs:** wave rosters, pylon HP (target:
  ~25 s for the starting band to fell — long enough to reconsider, never a
  sponge).

### 7.2 M2 — The Salt Caravan (`undertow_caravan`, Act I)

*Verb: pack up a people and move them, under harassment, uphill.*

- **Play:** Orcs (Brakk). **Sides:** 0 The Saltmarches (orc), 1 The Open Hand
  (scripted, human — outrider bands and one lock-crew camp; no AI, nothing to
  raze for the win), 2 The Old Camp (scripted, resigned in setup: its
  buildings stand as **ruins to salvage**, §9.2 R3). A wilds spider nest
  (existing camp) guards the south ford. **Map:** 64×48, `WASTELAND`,
  declared `Layout.CROSSINGS`, seed 2202. **Time:** 10–13 min.
- **Terrain:** the Sorrow runs diagonally SW→NE with three fords (north by
  the mill-dam, middle by the causeway, south past the spider nest). West
  bank: the salt pans and the Old Camp. East bank: the Broken Tooth mesa —
  high, dry, one gentle ramp, room for a camp. The caravan's road is drawn by
  the pans' white causeway tiles (grass of the wasteland palette) so the
  route reads at a glance.

```
   ....~~~~~~~~.........#####.
   .C.......fd.......##..M...#     C old camp (ruins)   M mesa camp site
   ..$.....~~~~.....#...._....     d mill-dam + pylon   f fords
   ......f~~~~~~~~......._..#.     _ mesa ramp
   ..T...~~~~~~~~~...n........     n spider nest
   ............f~~~~...T......
```

- **Start:** no hall, no buildings of your own. Brakk (Shaman, must-survive),
  Ugga among **9 Peons** (the drovers — workers: they salvage, build, and are
  the escorted), 5 Grunts, 3 Axethrowers, 1 Ogre. 300 gold / 200 lumber.
  The Old Camp's ruins: a Great Hall, 2 Pig Farms, a War Camp — abandoned,
  salvageable, worth (at salvage's quarter-share) roughly a new camp.
- **Objectives:**
  1. *Strip the Old Camp* (salvage: Peons' Salvage order on the ruins;
     done at ≥600 combined resources gained or all four ruins gone. Teaches
     salvage as an economy, once, where it is the *only* economy).
  2. *Raise the mesa camp: a Great Hall and two Pig Farms on the Broken
     Tooth* (building existence within the mesa rect — a plain predicate).
  3. *Bring the drovers up: at least 6 of 9 Peons alive on the mesa*
     (proximity predicate; the count is the objective's own text so losses
     are priced visibly, not discovered at a fail screen).
  4. *Brakk must survive* (fail line).
- **Reversal:** at the first ford crossing, the Open Hand drops the
  **causeway rockfall** (a landmark placed by trigger on the middle ford,
  with rockfall effect/sound — §8–9) and their outriders show on the north
  bank: 4 lines establish revelation 2 (they sabotage roads, wave the caravan
  back, and do not chase drovers). Simultaneously the Saltmarches' own
  answer arrives from the west edge: **2 Goblin Sappers** (player-owned,
  toast + camera cue; their card and blast are taught by the rockfall
  standing in the road).
- **The choices in controls:** (a) **Blast the rockfall** — a Sapper's Attack
  on the landmark (its blast is built for exactly this: 240 siege on a
  building) reopens the middle ford in one glorious beat; the second sapper
  is then a spare life. (b) **Walk the south ford** through the spider nest —
  longer, keeps both sappers. And standing over the north ford, optional the
  whole mission: the **mill-dam pylon**. Blasting or battering it down
  triggers the flood: the Open Hand's lock-crew camp is swept (scripted side
  resigned, its bands removed), the north bank is safe — and
  `undertow_dam` is set, with a 2-line horror from Brakk, who knows whose
  millpond that was. Nothing requires it; everything about the north-bank
  harassment tempts it.
- **Failure & recovery:** Brakk dead = defeat (on the panel from the start).
  Drovers below 6 is *not* defeat: stragglers (3 Peons) arrive once from the
  west with the Mesa-or-bust toast. Both Sappers wasted: the rockfall can
  still be battered down by Grunts (it is a building; slow, safe) or the
  south ford taken — the mission has no single-point failure. Outrider
  harassment is scripted bands on timers against the *crossing*, finite in
  number and named in toasts, never an economy to out-build.
- **Dialogue beats:** briefing 5 (Brakk/Ugga: what a homeland weighs);
  rockfall 4; sapper arrival 1; dam-blasted 2 (branch); debrief 6 — the
  Ashford receipt (revelation 3), with two Issa lines keyed to
  `undertow_mill_vault`. Sella is named here for the first time, by a captured
  outrider who is politely furious that the caravan wasn't warned *sooner*.
- **Implementation seam:** matrix world with `wilds=True` for the nest only,
  camp placed deliberately; resign-in-setup for side 2 (probe R3: buildings
  must stand *abandoned* and salvageable, not vanish — fallback in §14);
  rockfall is `run.place` from a trigger (placement is already a Run-level
  act); mesa rect and drover count are predicates over `run.units`;
  harassment bands `spawn(..., attack=ford)`. **Tuning knobs:** ruin values
  vs. camp cost (the mission's whole economy — balance so salvage-all ≈
  hall + 2 farms + a small remainder), outrider rosters, rockfall HP
  (one sapper blast + a few blows).

### 7.3 M3 — The Grove That Drinks (`undertow_grove`, Act II · What the Locks Are For)

*Verb: choose what to wound — the grove, your own orders, or an Ancient.*

- **Play:** Elves (Wrenna). **Sides:** 0 The Deep Grove (elf), 1 The
  Woodcutters (scripted, human — Sergeant Pell's militia: workers felling a
  marked line under a small guard, on `hold`), 2 The Bloom-Front (scripted,
  elf colours; bodies are wilds and elementals). The Ancient Guardian is a
  wilds encounter (existing camp machinery) east of the heart-grove — solo,
  with no lair-guards to complicate the approach. **Map:** 64×48, `SUMMER`,
  declared `Layout.FOREST`, seed 2303. **Time:** 11–14 min.
- **Terrain:** a spiral grove. The Moon Hall sits in a heart-clearing with
  the Moonwell, a rift carrying the grove's Vault (the grown Third Lock),
  and one gold mine. A single two-tile path spirals out through deep trees —
  everything off-path is forest, which means: Sentinels crawl, **Treants
  walk where they like**, Rangers see absurdly far down the path's bends,
  and the woodcutters' firebreak line is a visible scar of stumps crossing
  the spiral's south arm. The Guardian's clearing is a ring of standing
  stones off the path's east: reachable on foot down a short spur, or
  through the trees by Treants, which is the intended scare and delight.

```
   TTTTTTT...TTTTTTTTTTT
   T....TTT.TTTTTTT...TT
   T.TT.T...TTTTTT.TT..T     H Moon Hall   W Moonwell
   T.TT...H.....TT....T      * rift + Vault (Third Lock)
   T..TTTT..W*..TTT.G.T      G Guardian ring   --- firebreak line
   T.......TTTT.....T..      P woodcutters' camp (S, on the road)
   TTTTT-----TTTT..P.T..
```

- **Start:** Moon Hall, Moonwell, Vault on the rift, 2 Orchards. Wrenna
  (Druid, must-survive), 2 Treants, 4 Sentinels, 3 Rangers, 3 Gatherers.
  700 gold / 300 lumber / 45 aether. **Entangle pre-researched** (roots, on
  theme, and the mission's control tool against both soldiers and beasts).
  The woodcutters are already at work in the south: 4 Peasants harvesting,
  3 Footmen + Pell holding.
- **Objectives:**
  1. *Drive off the woodcutters* — the misdirect. It completes **either**
     by force (their camp's Lumber Mill razed or guard broken) **or** by
     parley (below), and its completion text differs by branch in the toast.
  2. After the parley or the rout, the fork, shown as two optional lines:
     *Finish the firebreak: fell the marked line* (a counted strip of tree
     tiles, 10 of 12 felled — Gatherers' harvest orders, Pell's crew helps
     if parleyed, stands off if routed) **or** *Keep the grove whole:
     the Moonwell must stand through the bloom* (two bloom-waves, named).
  3. Optional, always visible: *The Ancient in the stone ring: bring Wrenna
     to it — or bring it down* (one line, two resolutions).
  4. *Wrenna must survive; the Moon Hall must stand* (fail lines).
- **Reversal (parley):** bringing any elf — in practice Wrenna's band —
  within sight of the woodcutters' camp *without first blood* fires Pell's
  parley: 4 lines, revelation 4 (the warrant is Issa's standing order; Pell
  would rather be sawing than fighting). If the player attacks first, the
  same information arrives bloodier at the guard's breaking point (a
  surrender dialogue). Both roads reach the fork; only the price list
  changes (parleyed crews fell at double speed beside yours).
- **The choices in controls:** felling is worker Harvest on marked trees —
  the objectives panel and a minimap ping mark the strip, and felled-count
  ticks in a toast every three trees, so progress is never opaque. Cutting
  sets `undertow_grove_cut` and the bloom arrives diminished (one small wave
  lapping at the stumps). Refusing leaves the grove whole and the bloom
  arrives twice at strength: wild wolves and spiders first, then **wild
  Aether Elementals shed from the rift itself** — the pressure made visible
  — while the player defends Moonwell and Vault with Treants healing among
  the trees they stand in (`regen_in_trees`, existing). **The Guardian:**
  walking Wrenna within 6 tiles of it, never having attacked it, fires the
  approach (dialogue 3 lines; the Guardian kneels — scripted removal; flag
  `undertow_guardian_ally`). Attacking it instead is the campaign's one
  optional boss fight (Treants tank it among trees; Entangle does not root
  the flying — it isn't — but its slam punishes a ball: spread out); killing
  it sets `undertow_guardian_core`. Ignoring it is fully viable.
- **Failure & recovery:** Wrenna or Moon Hall = defeat. Treants lost can be
  replaced from the Moonwell if the economy is minded (limit 3, existing) —
  the mission teaches that unique units are precious, not irreplaceable.
  If the firebreak is half-cut when the bloom-front timer arrives, the bloom
  is scaled to the fraction felled: partial work is partial safety, never a
  wasted subplot.
- **Dialogue beats:** briefing 5 (Wrenna's saw that weeps); parley 4 /
  surrender 3; Guardian approach 3 (Wrenna mostly listening); bloom arrival
  2; debrief 6 — the root-map and the tea (revelation 5), ending on Wrenna
  naming Sella's next Step before Issa can ask.
- **Implementation seam:** matrix world, `wilds=True`; the Guardian is
  placed as the existing Ancient encounter, minus retinue — if camp
  machinery insists on a lair and guards, place a solo scripted-side
  `ANCIENT_GUARDIAN` on `hold` instead (probe R4, §14). Firebreak count is a
  predicate reading the matrix world's terrain over a fixed tile list
  (trees felled become grass by the ordinary harvest loop — no terrain API
  needed). Approach trigger: `run.near("wrenna", guardian_pos, 6.0)` gated
  on a never-attacked var that a damage-watcher trigger clears. Pell's
  crew: scripted side, workers given real harvest orders by setup.
  **Tuning knobs:** strip length vs. bloom clock (the cut must be finishable
  with ~60 s to spare at parley speed), Guardian HP as a two-Treant fight.

### 7.4 M4 — The Weight (`undertow_weight`, Act II)

*Verb: hold the works — and decide what the works are sitting on.*

- **Play:** Dwarves (Dagna). **Sides:** 0 Tarnlock (dwarf), 1 The Open Hand
  (human, **Medium AI** with a head-started siege base south — the campaign's
  first full enemy economy), 2 Open Hand sappers (scripted, human colours of
  a second seat so their scripted precision never tangles with the AI's
  plans; their bodies are human Peasants and Footmen — a consequence of the
  race-lock: orc Sappers belong to orcs, so Sella's "sappers" are engineer
  bands with powder-carts, played as Footmen whose target is always a
  lock-vault, §9.1). **Map:** 64×48, `WINTER`, declared `Layout.BASTION`,
  seed 2404. **Time:** 13–16 min — the campaign's long mission.
- **Terrain:** a stone lock-basin in a snow valley. The Deep Hold terraces
  against the north rock; three rifts form a triangle across the basin
  floor, each already carrying one of the Fourth Lock's Rune Vaults
  (landmarks: **the Three Weights**). North-east, in a rock pocket: the
  **endless seam** (the existing `GOLD_SEAM` deposit) with its own small
  **separate rift beside it** — the 2x2 seam-rift sits clear of the deposit's
  footprint by the ordinary mine clearance, so a Rune Vault placed square on
  that rift caps the seam's throat under unmodified placement rules and
  never overlaps a live mine. Two gates in the tree-ring south; the Open Hand's camp beyond.
  Mortar ground: two rock spurs overlook the gates, in Bolt Tower range of
  neither.

```
   #########..S*..#########
   #...H.....(seam).......#     H Deep Hold   S endless seam
   #..B...*V.........*V...#     V the Three Weights (vaults on rifts)
   #.....T.....*V....T..$.#     B Guard Hall  T towers  $ ordinary mine
   .TTTT..g....TT....g.TTTT     g gates
   .........Open Hand camp..
```

- **Start:** Deep Hold, Guard Hall, Engine Works, 2 Bolt Towers, 2
  Brewhouses, the Three Weights (drawing; store 450). Dagna (Runepriest —
  wounded-rescue rule as M1), 4 Ironguards, 2 Crossbowmen, 1 Mortar,
  5 Miners. 1,200 gold / 600 lumber / 45 aether. **Flame Strike
  pre-researched.** The enemy: hall, barracks, workshop, extra gold, and a
  siege that begins at once (first assault trigger at 0:05).
- **Objectives:**
  1. *Keep at least two of the Three Weights standing* (a standing-wound
     objective: `done` never true, `failed` when two are down *at once* —
     razed vaults can be rebuilt on their rifts, so the line pressures
     triage and repair, not perfection; defeat text names the moment).
  2. Win, either: *Break the siege: raze the Open Hand's hall* **or**
     *Spend their powder: destroy their workshop and three engineer bands*
     (the defensive win: outlast a counted asset, not a clock).
  3. The seam, shown after the midpoint revelation as two optional lines:
     *Cap the seam: build a Rune Vault on the seam-rift* **or** *Work the
     seam* (progress shown in toasts per 500 gold drawn from it).
  4. *The Deep Hold must stand* (fail line).
- **Reversals:** (a) The first engineer band ignores the gates' towers and
  goes straight for a Weight — Sella's people know which vaults are locks
  (revelation 5, cashed). (b) At the midpoint — second engineer band, or the
  player's first 300 seam-gold, whichever first — Dagna's confession
  (revelation 6, 4 lines) opens objective 3 and changes what the seam's gold
  *means* under the player's cursor. (c) Whenever a Weight is razed, its
  rift **sheds a wild Aether Elemental** (neutral side, 25 s lifetime,
  attacks whoever is nearest — including the Open Hand): the pressure,
  weaponised against everyone, exactly as §3.2 promises.
- **The choices in controls:** capping is the ordinary Build → Vault placed
  square on the seam-rift (the placement UI already snaps and explains); it
  completes as a building, sets `undertow_seam_capped`, and stops the rift's
  shedding. Mining is the ordinary haul loop to the seam (a second Deep Hold
  beside it is the greedy line): every 500 drawn spawns a wild elemental at
  a random Tarnlock rift and toasts the running total — the player feels the
  exchange rate. 1,500 sets `undertow_seam_mined`. Repair of the Weights
  under fire is the mission's taught skill (Peasant Repair, pro-rata cost
  pressure against mortar production).
- **Failure & recovery:** Deep Hold, or two Weights down at once = defeat.
  A single Weight lost is an insult with a rebuild order attached; the AI's
  siege can be bled by the defensive win if the counter-attack is beyond the
  player; Dagna's rescue rule keeps one bad mortar volley from ending the
  mission. On Easy campaign difficulty the AI drops to Easy (existing shift)
  and the engineer bands thin — phase 2 tunes band rosters per `run.ai`
  only through the existing difficulty, no new knobs.
- **Dialogue beats:** briefing 5 (torque and truth); first engineers 2;
  confession 4; first shed elemental 1; debrief 6 — the captured engineer's
  margin (revelation 7) and Dagna putting the confession in writing,
  wording keyed to seam flags. Sella speaks once, by messenger stone
  (a `Line` with her portrait over a held gate): courteous, exact, wrong.
- **Implementation seam:** matrix world; seam placed as a `GOLD_SEAM`
  building via `run.place(None, ...)` — the deposit path of `Run.place`
  already supports side `None` for mines; seam-gold accounting is a trigger
  polling the delta of a setup baseline against `Player` totals the world
  already keeps, or (simpler and exact) polling seam-adjacent haul
  completions is over-engineering: phase 2 picks the poll-baseline form and
  tests it (§13, R5). Shed elementals: `run.spawn(world.neutral,
  [AETHER_ELEMENTAL], rift)` — probe R6 (lifetime and neutral behaviour come
  from the row; fallback: scripted side 2). Engineer bands: scripted side,
  `spawn(..., attack=weight.center)`. **Tuning knobs:** AI head start, band
  cadence, Weight HP is the vault row's own — do not special-case it.

### 7.5 M5 — The Maw (`undertow_maw`, Act III · The Maw)

*Verb: finish the argument — with a repair crew, a demolition, or a ring of vaults.*

- **Play:** Humans (Issa, with every keeper present in dialogue and,
  per flags, in kind). **Sides:** 0 The Keepers (human), 1 The Open Hand
  (human, **Hard AI** — a `ProBrain`, so Sella researches and *casts* through
  `brains.magic` from her pre-placed vault and Mage Tower; she is given
  Flame Strike and Entangle researched in setup so the threat is live from
  minute one, §9.2 R7), 2 The Bloom (scripted; wild elementals and
  bloom-touched beasts shed by the rifts). **Map:** 80×64, `WASTELAND`,
  declared `Layout.KLONDIKE` (its pit grammar is the Maw's), seed 2505.
  **Time:** 15–20 min.
- **Terrain:** the crater. The Maw proper is a cross of **three 2×2 rifts**
  around a centre court, inside a broken rock ring with three gates (Klondike
  grammar, hand-drawn). On the court stands the **Keystone** landmark
  (player-owned, damaged to 40 %, repairable — mechanically a building of
  the player's whose repair is the RESEAL act). At each gate, a
  **seal-pylon** landmark (Open Hand colours, attackable — the OPEN act).
  The player's camp terraces the north rim (hall, barracks, workshop, one
  vault on a side rift — plus whatever the flags bring, §6.1); Sella's works
  hold the south rim: hall, Mage Tower, vault, towers. Two ordinary mines on
  the outer slopes; nothing inside the ring but rifts, so every ending is
  fought over the same three acres of glowing ground.

```
   ....HHHH......~~~~........       H keepers' camp (N rim)
   ..TTTT....##########......       K Keystone    p seal-pylons
   .......##....K*....##.....       * three Maw rifts (2x2 each)
   ..p...#...*......*...#.p..       S Sella's works (S rim)
   .......##...........##....
   ...TTTT...##..p..##.......
   ...........SSSSSS......T..
```

- **Start (before flags):** Town Hall, Barracks, Workshop, Church, 2 Farms,
  1 Vault on the north side-rift, Issa (Knight, **must-survive here** —
  the panel says why: the Compact's seal is on her sword-arm), Sister-Cleric,
  5 Footmen, 3 Archers, 2 Knights, 1 Catapult, 5 Peasants. 2,000 gold /
  800 lumber / 90 aether. Spells researched: Mend (carried in fiction from
  M1 — setup grants), and the player's *choice yet to make* at the Mage
  Tower the camp does not start with: building one and choosing a II/III
  line is part of the mission's own tech play. Flag additions per §6.1
  (vault, farms, gold, Brakk's band as player units, the Guardian, the core
  vault, seam hazards) are applied in setup and **announced in the briefing
  line by line** — the player is shown their own consequences as a muster.
- **Objectives:** the three endings of §6.2 as optional lines (GROUND struck
  through in dialogue, not in the panel, when its parts are missing — its
  panel line names the missing part); *Your Town Hall must stand* and *Issa
  must survive* as fail lines. A fourth optional line, never required and
  priced in the epilogue: *Leave the Open Hand their tower* (done when any
  ending lands with Sella's Mage Tower standing).
- **How each ending plays (the differences are the point):**
  - **RESEAL** is a repair siege in reverse: Peasants on the Keystone (Repair
    order, pro-rata gold burn the whole camp feels) behind a held ring,
    Gryphon Riders (trainable: Stables are the mission's mid-tech) killing
    Sella's casters' *targets* — her Magus judges clumps, so formation
    discipline is the counter-spell. At full repair, one final Open Hand
    assault (scripted roster + her AI army) must break against the ring.
  - **OPEN** is three demolitions as a raid plan: pylons have building
    armour; Catapults and the Catapult-and-cavalry mix race her repair-free
    (she cannot rebuild a landmark) — every pylon down also sheds a wild
    elemental, so haste has a visible price per gate. At the third, Sella
    resigns her side (dialogue 3 lines: she recognises her own plan done
    *correctly*, Weight and all), and the finale inverts: defend the camp
    against one counted bloom-wave from the open Maw.
  - **GROUND** is Warband's economy as an exorcism: vaults on all three Maw
    rifts (builders walking into the crater under Entangle weather), then
    the store filling 1/1s/vault toward 450 while every defensive cast
    (Mend for the builders!) visibly delays the ending. The predicate is
    public state the HUD already shows (aether vs. cap), so progress needs
    no bespoke bar — the objective line and the top bar are the same number.
- **Reversals:** at any ending's commitment point, Sella escalates once:
  her second vault (scripted placement on her stance's rift, announced by
  toast and ping) doubles her far-cast threat — the player can answer by
  razing it (a raid objective appears, optional). If `undertow_seam_mined`,
  rift-blooms punctuate everything every ~90 s (§6.1). If the Guardian walks
  with the player, Sella's first cast sequence targets it by the Magus's own
  judgement — the biggest body on the field does what big bodies are for.
- **Failure & recovery:** hall or Issa. A razed Maw vault delays GROUND, a
  wiped assault delays RESEAL's repair (the Keystone keeps every repaired
  hit point — progress is never confiscated), a lost demolition band delays
  OPEN. No ending can be locked *out* mid-mission by damage; only the clock
  of her growing army argues. If the player is reduced to the hall and
  peasants, one relief column (the Steps' muster: 4 Footmen, 2 Archers,
  400 gold) arrives once — and the debrief remembers it was needed.
- **Dialogue beats:** briefing 6 (the muster of consequences; Sella's terms,
  delivered by her own engineer under flag — she offers the OPEN sequence's
  timetable as a courtesy); commitment confirmations 3 each; Sella-at-third-
  pylon 3; per-ending debrief 5, with her voice in all three and Dagna's,
  Wrenna's, and Brakk's verses keyed to presence-by-flag. Total M5 lines
  ≈ 30, the campaign's densest mission and still under budget.
- **Implementation seam:** matrix world, `magic=True`; Sella's casting is
  `ProBrain` + `brains.magic` unmodified — she must be *played against* in
  phase-2 tuning, not scripted around (§13). Ending predicates: Keystone
  `hp >= max_hp` ∧ final-assault side-out; three pylon building-ids gone;
  `world.aether_cap(0) >= 450 ∧ players[0].aether >= cap` with all three
  Maw vaults done — all public `World`/`Player` reads from `Run` predicates.
  Commitment detection: triggers on first-repair-progress delta, first
  pylon gone, first Maw vault done. **Tuning knobs:** Sella's head start
  and spell grants, bloom cadence, relief-column trigger threshold.

### 7.6 The five at a glance

| # | Mission | You | Core verb | Wins by | Choice (by action) | Min |
|---|---|---|---|---|---|---|
| 1 | Millfield | Humans | Defend & mend | Hold the surges **or** shutter the vault | Vault held / shuttered | 8–11 |
| 2 | The Salt Caravan | Orcs | Salvage, move, rebuild | Mesa camp raised + drovers up | Blast rockfall vs. south ford; the dam | 10–13 |
| 3 | The Grove That Drinks | Elves | Parley, fell, channel | Firebreak finished **or** bloom weathered | Cut / whole; the Guardian | 11–14 |
| 4 | The Weight | Dwarves | Hold, repair, besiege | Enemy hall **or** their powder spent | Cap / mine the seam | 13–16 |
| 5 | The Maw | Humans | Choose & build the ending | One of three constructions | Seal / Open / Ground | 15–20 |

Total: **57–74 minutes of mission time at the outside edges, 50–65 for a
first Medium run that doesn't stall** — inside the 45–70 brief, with the
overage risk concentrated in M4/M5 and owned by their tuning knobs (§13.3).

## 8. Visual and audio direction

### 8.1 The identity: violet under ash

One sentence for every art decision: **the world is its own weather, and the
weather is violet.** Warband already renders the ingredients — glowing rift
cracks streaming motes, vaults that brighten as they draw and dim at a full
store, violet reach-washes and spell-bursts, elemental light. The Undertow
uses *no new palette*: each Step pairs an existing theme with a rising share
of that violet, so the descent is readable in screenshots alone.

| Step | Theme | The look | Signature shot (for §13's rendered evidence) |
|---|---|---|---|
| 5 Millfield (`SUMMER`) | Green farmland, one violet wound | Golden farms, the straining vault overbright beside the mill-race, wolves coming out of evening groves | Wave 2 pathing past a farm to the glowing vault |
| 4 Saltmarches (`WASTELAND`) | White pans, iron sky | A caravan strung along a white causeway; the river running faintly violet at the fords; red mesa at the end | The rockfall going up under a Sapper's blast |
| 3 Deep Grove (`SUMMER`, deep trees) | Green dark, violet sap-light | A two-tile spiral of path in a sea of canopy; Treants shouldering through trees; the stump-scar of the firebreak | The Guardian kneeling in its stone ring |
| 2 Tarnlock (`WINTER`) | Snow, stone, three violet eyes | The triangular Weights glowing in a white basin; mortar arcs over the gates; wild elementals shedding like sparks off a grindstone | A Weight falling and its elemental rising |
| 1 The Maw (`WASTELAND`) | Ash crater, the breath itself | Three rift-crosses under a rock ring; whichever ending the player is building is *visible from the minimap*: repair scaffolds, falling pylons, or a closing triangle of vaults | All three endings, one frame each |

Readability rules (phase 2 holds the line on these in the visual pass):
violet is reserved for *aether and pressure* — never a team colour, never
decoration; a wild elemental on screen must always mean §3.2's promise;
every landmark (§8.2) is nameable at arm's length from its silhouette plus
its label, and interactable ones read their verb off the objectives panel,
not off a tooltip hunt.

### 8.2 Landmarks: the bespoke objects

The root landmark system (section 10) names, marks, and sounds these; this
section is their spec. Each is a real building or building-cluster owned by
a named side (section 7.0's ownership rule), so it has HP, blocks movement,
saves, and dies by ordinary rules. None is a new building *type*; each
dresses an existing one, and each is registered with `add_landmark` in setup
so the objective layer can mark it.

| Landmark | Where | Body (existing type) | Look (over the body) | Sound | The player's verb |
|---|---|---|---|---|---|
| **Lock-pylon** (Mill, Dam, three Seals at the Maw) | M1, M2, M5 | `FARM`-footprint building of the opposing/scripted side, inert | A squat rune anchor: stone collar, copper cap, a hanging chain toward its rift; team-colour pennant so ownership reads. Label on hover/selection via the landmark layer | Struck: stone-and-bell (existing building-hit families). Falls: the **lock-turn** (§8.3) | Attack |
| **The straining vault** | M1 | Player `VAULT` on a rift | The vault's own drawing animation run *hot*: brighter cube, mote-stream doubled, a faint violet `Stain` scorch that grows each surge (effect layer, no sim state) | A rising hum under the existing vault ambience; each surge, the **bloom-surge** sting | Defend — or shutter via its pylon |
| **Causeway rockfall** | M2 | `LAIR`-footprint building placed by trigger | A tumbled rockfall across the ford: grey boulders, dust that settles over 20 s (effect), two warning pennants of the Open Hand stuck in it like a signature | Rockfall crash on placement (collapse family); Sapper blast is its existing spent-end | Attack (sapper or muscle), or walk around |
| **Firebreak strip** | M3 | Twelve marked tree tiles — terrain, not a building | Landmark layer overlays a dying-orange count glyph over unfelt strip tiles; stumps are what felled trees already leave | Ordinary felling; a wind-shift sting when the bloom-front clock starts | Harvest (workers) |
| **The Three Weights** | M4 | Player `VAULT`s on three rifts | Each dressed with hanging lock-chains to ground anchors and a numbered stone (I·II·III in the landmark label) so toasts can name which Weight is under attack | Vault hum; a Weight at <25 % HP adds a strained creak to its ambience loop (one new piece) | Repair, defend, rebuild |
| **The endless seam** | M4 (read at the Maw) | `GOLD_SEAM` deposit | As shipped, but its rift neighbour is dressed as the seam's *throat*: violet light breathing slower as gold per trip leaves — phase 2 may implement this as ambience intensity keyed to the mission's mined counter (view-only) | Deep Mining's existing haul sounds; each 500 drawn, the bloom-surge sting, quieter | Mine it, or cap its rift with a vault |
| **The Keystone** | M5 | Player `MAGE_TOWER`-footprint building at 40 % HP, inert (research queues unused) | A squat ring-wall of fitted stone round a hanging bell-weight; repair scaffolds are what construction sites already draw; at 100 % a final `Flare` and the lock-turn | Repair's existing work sounds; completion: lock-turn, full | Repair |
| **Maw rifts (×3)** | M5 | Ley rifts (ground) | As shipped — the crater needs no help — with a shared, slowly rotating mote gyre effect over the court while any ending is uncommitted | The Maw hum (§8.3) | Build vaults on them (GROUND) |

Landmark labels are the one screen novelty: the presentation layer draws the
name over each (objective-panel wording and landmark wording are the *same
strings* — a phase-2 test asserts it), dimming a name whose objective is
done. Nothing else in the HUD changes.

### 8.3 Audio: three new pieces, everything else is the game

The campaign is scored by what ships: each mission's player-race already
carries its peace/battle tracks through `music.Director` (humans *hearth /
banners / clash*, orcs *bonfire / warpath / bloodrush*, elves *moonlight /
starfall / wildhunt*, dwarves *deepforge / stonehall / ironwall*) — changing
race per mission changes the score's bones for free, which is a deliberate
part of "playing the next Step down". Victory/defeat stings exist. Spell
sounds exist (`audio/spells.py`). Bodies all exist. New work is exactly
three generated pieces through the existing `tools/pieces.py` pipeline
(prompts, generated takes, `SOUND_VERSION` bump, spectrogram review — the
ordinary body-piece discipline, added as *event* pieces beside the collapse
family, not as a new unit family):

1. **`lock_turn`** (0.8–1.4 s): a great stone-and-bronze mechanism engaging —
   low clunk, chain-tension rising a fourth, one bell partial. Played on:
   pylon felled (any), vault shuttered, seam capped, Keystone completed,
   third Maw vault standing. This is the campaign's full stop; the player
   should be able to hum its shape by M4.
2. **`bloom_surge`** (1.5–2.5 s): breath through a cracked pipe organ — air
   noise swelling under a detuned fifth, ending *unresolved*. Played on:
   wild elemental shed, bloom-wave arrival, seam 500-marks, Maw blooms.
3. **`maw_hum`** (looping ambience bed, M5 only, under the music): sub-bass
   pulse at a resting heart's tempo with a high, thin aether shimmer; its
   tempo is fixed (no dynamic audio state) and it stops — the most eloquent
   cut in the campaign — the frame any ending lands.

One new music track is *optional* and explicitly cuttable: **`undertow`**, a
title/campaign-screen variant of `vigil` (same bones, a low aether shimmer
voice) so the catalog's two campaigns sound like cousins. If phase-2 scope
tightens, this is the first thing overboard; the three pieces above are not
cuttable, because two of them carry gameplay information (a lock changed
state; pressure arrived) in missions where the player's eyes are elsewhere.

### 8.4 Portraits and screens

Speaker portraits are the units' own painted frames via `ProductionIcon`,
exactly as Thornwood — Sella in Open Hand colours is a `Speaker.player` of 1
away. The campaign screen (in its catalog form) lists *The Undertow* with
the tagline of §1 and a 5-mission, 3-act roster; act names: I *The Breath
Rises*, II *What the Locks Are For*, III *The Maw*. Mission previews render
the hand-authored worlds (§7.0), so the screen itself teaches the descent.

## 9. Units, allies, and engine truth

### 9.1 The roster: everything already walks and talks

**Zero new unit types.** The full cast list against what ships:

| Used as | Type(s) | First taught |
|---|---|---|
| The four keepers' armies | Each race's seven roles (worker/line/ranged/shock/siege/eyes/healer) | Their own mission; M5 assumes all four lessons |
| Issa / Brakk / Wrenna / Dagna as units | Knight / Shaman / Druid / Runepriest (`KNIGHT`, `CLERIC`×3) — ordinary units whose ids live in `Run.vars` (Thornwood's Aldric/Maren pattern) | M1 |
| Race-unique showcases | Goblin Sapper (M2), Treant (M3), Rune Golem (trainable M4), Gryphon Rider (trainable M5) | One per race-mission — the campaign is a guided tour of WB-068 |
| Bloom-touched wilds | Wolf, Spider, Troll (+ Golem at one M4 gate if tuning wants weight) | M1 |
| The Ancient Guardian | `ANCIENT_GUARDIAN` — wilds encounter in M3; potential player unit in M5 | M3 |
| Wild & summoned pressure | `AETHER_ELEMENTAL` (25 s lifetime row does the work) | M3 (wild), M5 (either) |

Because every type above already satisfies `docs/adding-a-unit.md` in full
(painted sheets or the summoned unit's single sheet, death/presence sound
families, brain routines), the campaign owes **no art or audio debt per
unit** — `test_painted_sheets.py` and `test_bodies.py` should pass untouched.
If, against this design, phase 2 *insists* on one new body, the only
candidate with a story claim is a dedicated Open Hand engineer replacing §7.4's
Footman-bands — and this design's position is that it fails the
indispensability test: the bands read perfectly through objective text and
targeting. Do not build it.

**Allies:** the engine has none — every other side is a rival, and this
design never asks for one. Help between peoples is expressed only as (a)
resources, research, and pre-placed buildings of the player's own side,
(b) player-owned reinforcement bands in the player's colours, or
(c) scripted sides acting on geography the player isn't sharing. Thornwood
established exactly this convention; §6.1 follows it.

### 9.2 Engine needs, itemised (all story-layer; no sim change)

| # | Need | Where it lands | Size / risk |
|---|---|---|---|
| E1 | Hand-authored worlds survive `build_world` (cleanup + naming after setup) | `mission_scene.build_world` — supervisor-owned, confirmed | Done elsewhere |
| E2 | Campaign catalog + per-campaign progress/autosave slots | Catalog work — supervisor-owned; this design assumes `Progress(campaign="undertow")` in its own slot | Done elsewhere |
| E3 | Landmark presentation (names, dressing, landmark sounds) | Supervisor's presentation layer; spec §8.2 | Done elsewhere |
| E4 | A `Run`-level "remove/replace a standing building" usable from triggers (M1's shutter) | `campaign.py` beside `Run.replace`, which already does the sim bookkeeping at setup time; phase 2 generalises its use, adds a mid-mission test | Small |
| E5 | Matrix-world construction helpers in `new_campaign.py` (parse legend → terrain grid → `World`, set `scripted`, lay rifts, stitch side colours/races) | New code inside the story folder only | Medium; the campaign's main bulk |
| E6 | Three event pieces + hum (§8.3) wired through the existing sound paths (mission scene event playback) | `tools/pieces.py`, `audio/`, `mission_scene.py` trigger-side `run` signalling or scene-side cues on objective/building events | Small–medium (generation time) |
| E7 | **Nothing** in `warband/sim/`: no new order, no `World` field, no constants row. | — | The fingerprint must not move (§13) |

Explicitly *not* needed and not to be built: alliances, unit XP/hero powers,
a general terrain-editing rule (matrices are authored at setup; the one
mid-mission ground change, felled trees, is the ordinary harvest loop), new
spells, new buffs, new layouts, a new map theme, dialogue tech beyond
`Line`/`Choice` as shipped, or any change to `Progress` format (section 11).

## 10. Landmarks: the API this design uses

One system, no bespoke per-mission graphics APIs:
`from warband.story.landmarks import add_landmark, set_landmark_state,
landmark, occupied`. `add_landmark(run, id, name, point, kind, radius,
state, revealed)` stores a JSON record in `run.vars["landmarks"]`, so it
saves with the mission for free; `set_landmark_state` drives
`dormant → active → ruined/open`; `occupied(run, id, side=0, contested=True,
soldiers_only=True)` is the zone predicate. Registration and state changes:

| Landmark (§8.2) | `kind` | States used | `occupied` use |
|---|---|---|---|
| Mill lock-pylon; mill-dam pylon; Maw seal-pylons ×3 | `anchor` | `active → ruined` on destruction | — (building-gone predicate) |
| Causeway rockfall | `gate` | `active` (placed by trigger) `→ open` (blasted/battered) | Side-0 crossing check may *also* use it; the ford trigger is drover positions |
| Mesa camp site (M2) | `refuge` | `dormant → active` when the Great Hall completes there | Drovers up: `occupied(..., soldiers_only=False)` plus the ≥6 count from `run.units` |
| Firebreak strip (M3) | `gate` | `dormant → active` at the fork `→ open` at 10/12 felled | — (terrain-count predicate) |
| Moonwell third lock (M3); the Three Weights I–III (M4) | `anchor` ×4 | `active`; `ruined` if razed, back to `active` if rebuilt (M4) | — |
| Endless seam throat (M4) | `anchor` | `dormant → active` (capped) | — |
| The Keystone (M5) | `bell` | `dormant` (damaged) `→ active` (first repair) `→ open` is wrong for a seal — phase 2 uses `active` at full repair with the lock-turn; state name only, no semantics invented | RESEAL's final assault may check the player still *holds* the court via `occupied` |
| Maw rifts ×3 (M5) | `anchor` ×3 | `dormant → active` per vault completed | — (aether-cap predicate) |
| Ashford lambing ground (M2 scenery, passed on the road) | `memorial` | `dormant` entire mission; revealed, labelled, never an objective | — |

The Guardian's stone ring is deliberately *not* a landmark: it is a wilds
encounter with its own presentation, and its objective line names it.

## 11. Progress and save compatibility

- **This campaign never touches Thornwood's bytes.** Separate catalog entry,
  campaign id `undertow`, its own keyed progress and autosave slots
  (supervisor's catalog work, E2). A player mid-Thornwood keeps their place;
  a player who finished it keeps their epilogue. `Progress.FORMAT` stays 1:
  this design adds only ids and flag keys, which the format already carries
  forward unknown.
- **Mission ids are new and prefixed** (`undertow_mill`, `undertow_caravan`,
  `undertow_grove`, `undertow_weight`, `undertow_maw`) and, once shipped,
  stable forever, retired never reused — the same discipline as Thornwood's.
  Flags are likewise `undertow_`-prefixed (section 6.1), so even a shared
  flags dict could not cross-contaminate campaigns.
- **Mission saves** carry the ordinary world save plus the `mission` block;
  a hand-authored matrix world is still an ordinary `World` by the time it
  saves, so `SAVE_VERSION` behaviour is Thornwood's: a future breaking world
  format costs one mission replayed from its briefing, never the campaign.
  Landmark records ride inside `Run.vars` (JSON), so they need no save
  version of their own; a save from before a landmark existed simply has
  fewer records, and `landmark()` reads must tolerate absence.
- **`--mission undertow_grove`** starts that mission standalone with empty
  flags (existing behaviour): every mission's setup must therefore be
  playable with *no* flags — and by design each is (flags only ever add or
  price, never gate entry), with M5's GROUND unavailable and its briefing
  saying so. Phase 2 tests the empty-flags start of all five.
- **Difficulty** is the campaign's own one-time choice shifting AI sides one
  step (existing `shifted`): M4's siege is Easy/Medium/Hard, Sella at the
  Maw is Medium/Hard/Master. Master Sella is a *tuning risk*, flagged §14.
- **Art and audio never enter either file** (existing rule): all §8 dressing
  is looked up at draw time by type, race, and landmark id.

## 12. Phase-2 scope, in build order

1. **Probes first** (§14 R1–R7): each is a small test-world check; any probe
   that fails switches its design element to the named fallback *before*
   missions are written around it.
2. `new_campaign.py` skeleton: matrix helpers (E5), speakers, campaign
   shell with five stub missions that load, start, and end. Catalog
   registration (supervisor's seam).
3. Missions in order M1 → M5, each with its tests as written (§13.1); M4/M5
   AI tuning after their scripts stand.
4. The three audio pieces (E6) and landmark dressing pass over §8.2; the
   optional `undertow` track last, cuttable.
5. Visual pass and playtests (§13.2–13.3); timing trims to the 50–65 band.
6. `docs/warband-campaign.md` gains an Undertow record section on landing;
   this document stays the design of record.

Rough size: one new module of Thornwood's order (~500–700 lines with
matrices), one test file, three sound pieces, no sim diff.

## 13. Verification plan (phase 2)

### 13.1 Automated, per mission (fast tier unless a whole match is required)

Mirror `tests/warband/test_campaign.py`'s discipline for a second campaign:
for *each* mission — a win by every win path, a loss by every fail line,
every flag set by its action and absent otherwise (including M5 run under
at least three flag combinations), choices surviving a save/resume through
the real loader, progress written at victory and debrief choices after it,
empty-flags standalone starts, and the campaign screen over fresh /
under-way / finished / unreadable progress in `test_layout.py`'s manner.
Specifically: the M1 pylon is attackable by the starting band and its loss
shutters the vault; M2's salvage economy can afford the mesa camp (an
arithmetic test, not a playthrough); M3's firebreak count and Guardian
approach triggers both fire and exclude each other; M4's seam accounting
fires at 500/1000/1500 and a razed Weight sheds exactly one elemental;
M5's three ending predicates are reachable and mutually exclusive once
committed. `tools/fuzz.py` over the finished scene input, and
`tools/sim_fingerprint.py --check` must pass **unchanged** — proof of E7.

### 13.2 Looked-at, per the project's visual rules

`tools/verify_campaign.py` extended (or its Undertow sibling) renders: the
campaign screen, every briefing, and the five signature shots of §8.1 plus
one frame per M5 ending at 1280×800 and 1200×680; the PNGs are opened and
judged, then one `tools/visual_lint.py` walk over the campaign screens.
Sound pieces are judged from `tools/pieces.py cues` spectrograms and stats
before anyone listens, per `docs/adding-a-unit.md`'s discipline.

### 13.3 Played

Each mission played start-to-finish on Medium by a person (or a scripted
stand-in *plus* one human pass before handoff) with three recorded numbers:
wall-clock to victory per win path (target bands in §7.6; campaign total
50–65), deaths of named keepers (target: zero surprise fails — every
must-survive death was visibly coming), and Sella's mastery in M5 on Hard
campaign difficulty (target: beatable on RESEAL; if Master-ProBrain casting
makes her oppressive, trim her setup grants and head start, never her
brain). AI-strength claims, if any are made, go through `tools/arena.py`
per project rules — this design makes none.

## 14. Risks and probes (each with its fallback)

| # | Risk / unknown | Probe (phase 2, first) | Fallback |
|---|---|---|---|
| R1 | Hand-authored `World` from a matrix: constructor demands (terrain validity, races, seats vs. the wilds) and `build_world` ordering | Build M1's world in a test; start, save, resume it | Supervisor's seam is built for this; if a constructor gap appears, it is one story-layer helper, not a sim change |
| R2 | Removing a standing vault mid-mission (M1 shutter) upsets aether bookkeeping (cap/spill blocks) or vision | Trigger-removal test asserting cap drops, spill event, no crash over 60 s of steps | Replace the vault with an inert same-footprint ruin via `Run.replace` semantics instead of deleting it — same fiction, gentler bookkeeping |
| R3 | A side resigned in setup leaves buildings *gone*, not abandoned (M2's salvage ruins) | Setup-resign test: buildings remain, `abandoned`, salvage pays out | Place ruins as side-2 buildings *without* resigning (a dormant scripted side that never acts); salvage of a rival's standing building is legal at the slower rate — retune the ≥600 threshold |
| R4 | Wilds camp machinery requires lair+retinue (M3's solo Guardian); or the Guardian, spawned for side 0 in M5, is unorderable/undrawable as a player unit | Two probes: solo-Ancient placement; side-0 spawn → order it, draw it, save/load it | M3: scripted-side Guardian on `hold`. M5: the ally flag becomes a *scripted* arrival — the Guardian walks the crater rim as a wilds unit whose camp the Open Hand must cross (existing behaviour), and GROUND keeps the core/grove gates. The story survives; only the toy changes hands |
| R5 | Seam-gold accounting (M4) has no clean public counter | Poll a baseline total the world already keeps; verify haul-by-haul against a one-mine test world | Count completed hauls by miner proximity per trip-window in a trigger (approximate at 500-grain — acceptable: thresholds are story beats, not prices) |
| R6 | Neutral-side `AETHER_ELEMENTAL` spawn misbehaves (lifetime, targeting, draw) | Spawn one wilds elemental; watch 30 s of steps and one rendered frame | Spawn on scripted side 2 ("The Bloom") with attack orders at the nearest building — identical fiction |
| R7 | Sella (Hard/Master `ProBrain` + `brains.magic`, pre-researched spells) is far stronger than M5's tuning assumes — the known post-WB-067 difficulty jump that over-armed Thornwood's finale | Play M5-RESEAL on Hard campaign early, before other polish | Trim in order: her setup spell grants, her head-start gold, her second-vault escalation. Never below the campaign-shifted brain — Easy players get Medium Sella by construction |
| R8 | Start forces exceed supply (Thornwood shipped four such starts) | An automated supply audit over all five setups in the test file | Add the missing farm/orchard/brewhouse per mission — the audit is the fix's guard |
| R9 | M4+M5 length pushes the campaign past 70 min | §13.3 wall-clocks per win path | Trim enemy head starts and band counts before touching objectives; M4's defensive win is the pressure valve |
| R10 | `run.look` cues to unexplored ground show nothing (M2 rockfall, M3 Guardian spur) | Check each cue target is inside starting vision or a scout's path | Toast + minimap ping only (already the fallback behaviour) — design cues were placed accordingly |

**Consistency self-check (done for this document):** every flag in §6.1 is
set and read exactly where its mission section says; the revelation ladder
(§5.2) and the five blueprints agree row for row; Sella's knowledge is the
same in §3.3, §4, and M4/M5 (symptoms yes, seam geometry no); no mission
requires attacking a player-owned building, terrain mutation, an ally side,
a unit type that does not ship, or a dialogue feature beyond
`Line`/`Choice`; durations sum inside the brief; and every sim behaviour
invoked (salvage of ruins, vault-on-rift placement and snapping, aether
cap/rate, spell grants via upgrades, sapper blast vs. buildings, treant
forest-walking and tree-regen, repair pro-rata, scripted-side resign,
`ProBrain` casting, `World.lay_rifts`) was read in the code or its design
notes during writing, with the uncertain ones isolated above as probes.






