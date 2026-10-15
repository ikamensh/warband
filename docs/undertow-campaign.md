# The Undertow — player and design guide

The second Warband campaign (`warband/story/new_campaign.py`, id `undertow`, the catalogue's
default; *The Thornwood War* remains playable beside it). Five hand-authored missions descend
Vesskar Hollow's Five Steps — Humans, Orcs, Elves, Dwarves, Humans — each with a different verb,
choices fulfilled through ordinary orders, and flags the next Steps and the finale read back.
World and story design: `docs/campaign-setting.md`. This note records what shipped.
The entrance and Millfield's revised first playable sequence: [first impression criteria and design](undertow-opening.md).
Character voices, branch continuity and the revision's craft sources:
[narrative design](undertow-story.md).

Each playable keeper has a named map tag and an authored portrait in dialogue, the selection
card and the army grid. **F3** selects and centres the current keeper; that link follows a rescue
or saved mission. Detailed orders appear in dialogue; the HUD keeps the objectives compact. The first ending act
commits its course; the briefing names these acts before play begins. **J** opens the saved
mission journal from play or the pause menu: reread the briefing and witnessed dialogue or
chosen answers without replaying a decision. Hover a minimap diamond to read its charted name;
left-click looks there, right-click sends the selected units.

## The missions

| # | Mission (id) | You | Wins by | The choice (by action) |
|---|---|---|---|---|
| 1 | Millfield (`undertow_mill`) | Humans | Hold the straining vault through two surges, or shutter it and clear the fields | Hold (`undertow_mill_vault`), deliberately destroy the north-bank pylon (`undertow_mill_shuttered`), or lose the vault (`undertow_mill_lost`) |
| 2 | The Salt Caravan (`undertow_caravan`) | Orcs | Salvage the Old Camp, raise a hall + three farms on the Broken Tooth mesa, keep ≥5 live drovers on the mesa at completion | Blast the rockfall with a sapper or walk the south ford; optionally blast the mill-dam pylon, sweeping the Open Hand camp (`undertow_dam`) |
| 3 | The Grove That Drinks (`undertow_grove`) | Elves | Choose cut/whole in dialogue, then fell 6 of the 8 marked firebreak trees, or muster at the Moon Hall and weather both bloom waves | Cut/whole (`undertow_grove_cut`); the Ancient Guardian: Wrenna alone in peace (`undertow_guardian_ally`) or bring it down (`undertow_guardian_core`) |
| 4 | The Weight (`undertow_weight`) | Dwarves | Raze the Open Hand hall, or raze their workshop and break all three engineer bands — and settle the seam | Cap the seam's throat-rift with a vault (`undertow_seam_capped`), haul 300 gold out of it (`undertow_seam_mined`), or post soldiers on the seam landmark after the siege and close the face (`undertow_seam_guarded`) |
| 5 | The Maw (`undertow_maw`) | Humans | One committed ending (below) | The first ending act — repairing the Keystone, felling a seal-pylon, finishing a Maw vault — locks the others out |

## The three endings

- **RESEAL** — order **peasants to repair** the Keystone (a player Mage Tower at 25 % in the crater) to full, then break
  Sella's final assault on it. It must still stand fully repaired at victory; a rebuilt tower on
  the same footprint counts. The Mend spell heals units; it cannot repair buildings.
- **OPEN** — after the first pylon commits this ending, send **Issa to the marked Relief Sluice**
  inside the north rim. She opens the bypass using Dagna’s corrected seam survey. Destroy the
  three hostile seal-pylons (south, west, east gates); release waits for the bypass. Sella stands
  her side down permanently, and the Keepers must defeat the escaping bloom.
- **GROUND** — a finished vault on each of the three Maw rifts, held until the aether store reaches
  **450**, and defeat the final surge that begins at the first completed vault. Needs somewhere for the breath to go: the grove whole, or the Guardian, living or as
  heart-stone. With the grove cut and no stored core, keep the Ancient alive until grounding
  finishes; its fall loses a committed GROUND attempt. Before commitment, its loss leaves the
  other endings available. Without one, the mission says so in dialogue and the other endings remain.

Exactly one of `undertow_ending_sealed/open/ground` is remembered; the epilogue composes a verse
per flag. Sparing or destroying Sella’s refuge mage tower is also remembered and changes the closing
account of its engineers and wounded crews. The map charts this occupied refuge;
an approaching army hears who is inside before reaching ordinary siege range.
Every remembered flag defaults in setup and is set by an action before victory, so
leaving at the result screen never skips one.

## What carries into the Maw

- Mill vault held → a second north vault already drawing, +60 aether. Shuttered → Brakk's band
  (4 footmen, 2 archers) in the player's colours.
- Dam blown → one farm fewer, +800 gold of salvaged millstones.
- Guardian ally → a player-owned Ancient Guardian at the camp. Heart-stone → up to +120 starting aether, limited by the camp’s vault capacity; the muster
  reports the actual grant.
- Seam mined → +2000 gold and a wild-elemental bloom immediately on ending commitment, then
  further blooms at 200, 300, 400 and 500 seconds; all arrived pressure bands must be defeated;
  also capped → half the gold and no blooms. Capped alone → quiet rifts.
- Starting supply (hall + up to six farms) covers every combination of these arrivals; a test
  audits the combinations.

## Delivery

Open **Campaign** from the title (A), or run `uv run warband --campaign`.
`uv run warband --mission list` lists both campaigns; `--mission undertow_maw` starts that map
with saved choices. The title’s Continue and Load game discover both independent campaign
autosaves. Manual save browsers cannot overwrite those automatic slots.

The frozen native acceptance gate enters The Undertow through the title, displays its cover
and five authored keeper portraits, renders every mission’s objectives and landmarks, and
saves then resumes each mission through the ordinary Load controls. Its receipt requires
`native_campaign` and `campaign_autosave_load`; source playtests alone cannot satisfy those
packaged delivery checks.

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
standard-loader save, the ending choice-lock, and the Guardian retirement. Solver mission-time is measured by the public-order driver; a first human run is slower.
The campaign keeps five short missions rather than adding waiting time to reach the blueprint’s
original length target. Review regressions also cover current caravan occupancy, exhausted
builders, deliberate parley, outstanding siege attackers, keeper rescues, ending commitment,
the corrected release and a save during the final crisis.

Known simplifications against the design blueprint are listed at the top of
`docs/campaign-setting.md`.
