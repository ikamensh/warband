# The Undertow — player and design guide

The second Warband campaign (`warband/story/new_campaign.py`, id `undertow`, the catalogue's
default; *The Thornwood War* remains playable beside it). Five hand-authored missions descend
Vesskar Hollow's Five Steps — Humans, Orcs, Elves, Dwarves, Humans — each with a different verb,
an on-map choice made with ordinary orders, and flags the next Steps and the finale read back.
World and story design: `docs/campaign-setting.md`. This note records what shipped.

## The missions

| # | Mission (id) | You | Wins by | The choice (by action) |
|---|---|---|---|---|
| 1 | Millfield (`undertow_mill`) | Humans | Hold the straining vault through two surges, or shutter it and clear the fields | Destroy the hostile lock-pylon on the north bank → vault shuttered (`undertow_mill_vault`) |
| 2 | The Salt Caravan (`undertow_caravan`) | Orcs | Salvage the Old Camp, raise a hall + three farms on the Broken Tooth mesa, bring ≥5 drovers up | Blast the rockfall with a sapper or walk the south ford; optionally blast the mill-dam pylon, sweeping the Open Hand camp (`undertow_dam`) |
| 3 | The Grove That Drinks (`undertow_grove`) | Elves | Fell 6 of the 8 marked firebreak trees, or muster at the Moon Hall and weather both bloom waves | Cut/whole (`undertow_grove_cut`); the Ancient Guardian: Wrenna alone in peace (`undertow_guardian_ally`) or bring it down (`undertow_guardian_core`) |
| 4 | The Weight (`undertow_weight`) | Dwarves | Raze the Open Hand hall, or raze their workshop and break all three engineer bands — and settle the seam | Cap the seam's throat-rift with a vault (`undertow_seam_capped`), haul 300 gold out of it (`undertow_seam_mined`), or post soldiers on the seam landmark and close the face |
| 5 | The Maw (`undertow_maw`) | Humans | One committed ending (below) | The first ending act — repairing the Keystone, felling a seal-pylon, finishing a Maw vault — locks the others out |

## The three endings

- **RESEAL** — repair the Keystone (a player Mage Tower at 25 % in the crater) to full, then break
  Sella's final assault on it. A rebuilt tower on the same footprint counts.
- **OPEN** — destroy the three hostile seal-pylons (south, west, east gates). Sella stands her side
  down; ride out one bloom wave of wild elementals and wolves.
- **GROUND** — a finished vault on each of the three Maw rifts, held until the aether store reaches
  **450**. Needs somewhere for the breath to go: the grove whole, or the Guardian, living or as
  heart-stone. Without one, the mission says so in dialogue and the other endings remain.

Exactly one of `undertow_ending_sealed/open/ground` is remembered; the epilogue composes a verse
per flag. Every remembered flag defaults in setup and is set by an action before victory, so
leaving at the result screen never skips one.

## What carries into the Maw

- Mill vault held → a second north vault already drawing, +60 aether. Shuttered → Brakk's band
  (4 footmen, 2 archers) in the player's colours.
- Dam blown → one farm fewer, +800 gold of salvaged millstones.
- Guardian ally → a player-owned Ancient Guardian at the camp. Heart-stone → +120 starting aether.
- Seam mined → +2000 gold and a wild-elemental bloom at a Maw rift every 100 s (five scripted);
  also capped → half the gold and no blooms. Capped alone → quiet rifts.
- Starting supply (hall + up to six farms) covers every combination of these arrivals; a test
  audits the combinations.

## How it is built, and how it is proven

Each `setup` replaces the generated world with an authored one (terrain matrix, races, theme,
hand-laid rifts, `magic=True, scripted=True`), places landmarked objective sites
(`warband/story/landmarks.py`), and defaults its flags. Story buildings the player must destroy are
hostile-owned; rebuildable ones (Weights, Keystone) are recognised by footprint, not entity id.
Enemies are finite scripted bands on one hostile seat per mission — no AI side ever fights its own
engineers — and every "wild" elemental spawns on a scripted hostile seat with a real attack order.
Seam gold is counted haul by haul (a worker seen inside the seam, then seen carrying) into a saved
variable, never as a purse delta. No simulation rules changed; the sim fingerprint does not move.

`tools/play_undertow.py` plays every mission and ending with public orders only (visible-enemy
knowledge, queued dialogue choices answered as the dialog scene does), and
`tests/warband/test_undertow.py` drives it: fast-tier build/supply/landmark invariants, slow-tier
whole-mission win paths for every fork and ending, loss paths, a mid-phase `Run` round-trip, a
standard-loader save, the ending choice-lock, and the Guardian retirement. Solver mission-time on
the source simulation (a first human run is slower): Millfield 108 s hold / 69 s shutter; Caravan
161 s ford / 186 s dam; Grove 109 s cut / 290 s whole (includes the boss and rebuilding); Weight
493 s cap / 110 s mine / 215 s guard; Maw 48 s reseal / 71 s open / 112 s ground.

Known simplifications against the design blueprint are listed at the top of
`docs/campaign-setting.md`.
