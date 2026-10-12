# Warband — neutral encounters

## Design

Camps are optional army expeditions. They offer a profitable use for a prepared army before or
between attacks on another player, and expose that army away from home while it earns the reward.
The choice is to scout, prepare, contest or bypass an objective. Safe opening mines, naturals and
routes between the starting economies remain outside their watch.

Three tiers ask for meaningfully different commitments. Raids are early opportunities; Strongholds
reward a mixed army, Tier I weapons/armour and suitable counters; an Ancient is a late expedition and a visible achievement.
An Ancient can be a shared central objective in three- and four-player Large matches, making the
army’s travel, timing and vulnerability relevant to opponents. Terrain must permit a route around it.
A protected river or a required Klondike economy takes priority over placing a boss.

Resources pay back losses and create a timing opportunity. They do not grant permanent army buffs,
free elite units or mandatory spells: the player still chooses how to spend the reward. Magic remains
an independent, default-off match option, and every encounter can be cleared without it.

## Encounters

The authoritative catalogue is `warband/assets/constants/encounters.toml`; creature numbers are in
`neutrals.toml`. The camp card and Wilds codex use that same catalogue.

| Encounter | Role | Tier | Guards | Gold / lumber | Lair HP | Preparation |
|---|---|---|---|---:|---:|---|
| Wolf Outpost | Expansion | Raid | 2 wolves | 800 / 100 | 250 | Clear the pack before workers approach the mine. |
| Venom Hollow | Expansion | Raid | Spider, wolf | 900 / 120 | 275 | Close on the spiders with a frontline. |
| Wolf Pack | Wilds | Raid | 4 wolves | 1,200 / 150 | 300 | Protect exposed archers with a frontline. |
| Venom Brood | Wilds | Raid | 3 spiders, 2 wolves | 1,500 / 200 | 350 | Cavalry closes on retreating spiders; heal between fights. |
| Troll Toll | Choke | Stronghold | 2 trolls, spider | 3,000 / 450 | 600 | Break the shortcut's guards or take its safe bypass. |
| Sentry Cairn | Choke | Stronghold | Golem, troll, spider | 3,200 / 475 | 625 | Leave marked slam ground, then punish recovery. |
| Troll Stronghold | Wilds | Stronghold | Troll, 2 wolves, spider | 2,800 / 400 | 550 | Focus piercing damage on the unarmoured troll. |
| Stone Sentinels | Wilds | Stronghold | Golem, 2 spiders | 3,200 / 450 | 600 | Spread out and dodge the marked slam. |
| The Ancient Guardian | Wilds | Ancient | Guardian, 2 golems | 6,000 / 900 | 900 | Upgraded mixed army, healers, siege and deliberate movement. |

The five bodies have distinct jobs. Wolves prioritize armed ranged troops over a closer frontline.
Spiders step away from nearby melee troops while their shot recovers. Trolls are durable but
unarmoured, so arrows retain their intended counter; their regeneration starts only out of combat.
Golems commit to a visible ground point for 1.8 seconds. The Ancient has 3,800 HP and a wider
2.7-tile slam with a 2.8-second tell, followed by recovery. Leaving the marked area avoids the blow,
even if the original target dies or moves. Ground slams spare friendly creatures and flyers.

The Ancient also throws tracking shards at armed flyers within six tiles, so one gryphon cannot
farm the apex encounter undefended. Unarmed flying scouts do not wake camps. The Guardian uses
its own crowned stone mesh and painted 72-frame sheet, with violet fissures and a front chest core;
its stone sounds reuse the matching golem sound family.

## Progress and payout

Guards rouse together, remain leashed to their home and return after disengagement. Fresh intruders
must cross the alarm; an ongoing fight does not extend it to unrelated passers. Existing targets and
actual attackers can still be pursued within the camp's leash. Surviving guards
mend after eight calm seconds. **Fallen guards stay dead.** A failed expedition can leave permanent
progress, rather than losing soldiers to an endlessly refilling sink. The lair remains a fortified
building, with substantially less cleanup health on ordinary camps.

**Both the lair and every guard must fall before payout.** Sniping the building alone earns nothing.
Actual damage on camp entities determines each seat’s share of gold and lumber; overkill earns no
extra credit. When a survivor heals, the credit for those restored wounds is removed proportionally.
Credit on defeated guards and the lair persists. Integer allocation conserves the whole bounty, with
seat number breaking equal remainder ties. The largest contributor gets the camp-clear achievement;
other contributors still receive their earned resources. A final hit cannot steal the expedition.

Completion, contribution and the fixed slam point survive saves and authoritative checkpoints.
A completed encounter pays once. Scripted removal with no contributing player grants no resources.
A named completion toast, resource floats, sound and match-result bounty totals make success visible.

## Placement and control

See [the map rules](warband-maps.md#optional-encounters-2026-10-01). Small maps attempt a Raid orbit;
Medium adds a Stronghold; Large attempts all three tiers where space and approach permit. Side
encounters are congruent per seat. A shared Ancient is placed once, with comparable approaches and
certified safe bypasses. Camps are wishes, not a reason to reject otherwise playable terrain.

An unrelated attack-move does not automatically select a settled camp merely because its guards
are visible. Explicit attacks and attack-moves aimed inside the camp remain expeditions; active
creatures are still answered. Gatherers avoid the remembered lair’s whole watch, as well as visible
mobile threats. Ordinary army routes and automatic combat movement also avoid remembered camp
watches; deliberately ordering a destination inside the watch remains possible. An armed creature seen
before its lair leaves a warning at its last observed position, so losing sight of it cannot reverse
a detour. Seeing that location empty removes the warning; observing its lair replaces a visible
guard’s broad warning with the precise camp watch. These are saved, private scouting facts. Scouted camp cards
remember identity, original guard count, bounty and tactical hint;
they do not read unseen current guard health. Online seat snapshots omit unscouted camps, hidden
guard IDs, recovery timers and contribution ledgers. Exact earned income is private to its recipient.
Discovered encounter anchors survive the lair's destruction, so surviving guards remain part of the
same expedition. Completion enters a seat's memory through its earned bounty, a visible completion
or a later visit to the cleared site; a completion hidden in fog does not update an observer's memory.

The wilds occupy `World.neutral`, one seat past `World.seats`, and stay outside victory, elimination,
supply, playing-seat fog and league ratings. Camps are not rival factions or incoming PvP raids.

## Computer players and verification

Both brains select feasible camps before considering distance, commit a healthy local cohort and
assess retreat against its committed cohort rather than fresh recruits elsewhere. After a failed
assault they wait for a stronger force; a retry timer alone is not permission to feed the same army.
They keep fighting surviving guards after the lair falls and can move out of marked stone slams.
The standard brain requires 70% health; Pro uses its posture's existing rejoin-health requirement.
Only soldiers within the existing muster breadth fund the same expedition; distant recruits cannot
arrive alone using an army elsewhere as their strength estimate. Wounded soldiers remain at home.
Soldiers already fighting a visible rival cannot fund a new camp assault.
Retreating soldiers finish their walk. At rest, those without regeneration or an alive/queued
healer return to PvP rather than wait forever; the camp health requirement remains unchanged.
A genuine base-defense interruption cancels the whole expedition and retains its
original force for the retry requirement, rather than leaving half the party fighting creatures.

`tools/creep_report.py --encounters` measures all four races against each encounter in early,
mid and prepared magic-free brackets: the curve across brackets is the calibration, and only the
prepared bracket gates. Stronghold preparation includes the mid bracket's ordinary Tier I weapons
and armour; Ancients require Tier II research. It records replacement costs, net resource return, casualties and
time, with slam-dodge re-aims at the cadence a brain can sustain. Whole-match reports cycle seats
through every race, print camps present, discovered and engaged per tier beside clear economics,
and fail losing slices or missing paid clears where a discovered camp was reachable by a ready,
free army. A map without such an opportunity reports that lack of coverage explicitly;
staged fights are evidence of achievable counterplay, not proof that ordinary bots use it correctly.
Clearing a guarded camp can unlock a contested expansion: the planner avoids halls on remembered camp ground
until completion, while a destroyed lair alone leaves the expansion guarded.

A camp's physical site remains the expedition target and the place where completion can be
observed. Expansion camps also remember the mine they defend. Ordinary rallies, scouts,
construction and worker routes avoid both circles through `camps.defended`; a deliberate
expedition excludes both by lair identity. Neither unseen deaths nor a hidden completion
change another seat's memory. Witnessed guard casualties lower the next assault's estimate;
surviving guards are still priced at full health because they mend after disengagement.
Expansion guards stand around their mine. Its quiet alarm is three tiles, covering every legal
mining mouth while allowing workers to discover the two guards before provoking them. The den's
alarm and other camps retain five tiles; remembered routes and map certificates keep that wider
five-tile safety margin around both defended points.

Single-player setup and room hosting offer **Monsters: On / Off**; `--no-wilds` turns them
off from the command line. Disabling camps preserves the seed's terrain, resource deposits,
rifts and fairness attempt. The option survives saves, checkpoints and subsequent matches.
Scripted campaign encounters are authored mission content and remain controlled by the mission.

```sh
uv run pytest -q tests/warband/test_neutral_encounters.py tests/warband/test_camps.py
uv run pytest -q tests/warband/test_creeping_strategy.py tests/warband/test_neutral_presentation.py
uv run pytest -q --slow tests/warband/test_encounter_maps.py
uv run python tools/creep_report.py --encounters --seeds 3 --gate
uv run python tools/creep_report.py --agents pro,pro --seeds 6 --gate
uv run python tools/creep_report.py --agents medium,medium --seeds 6 --gate
uv run python tools/verify_camp.py /tmp/warband-camp-check
```

Keep only the latest useful results and frames under `~/saga/evidence/warband/neutrals/`, with source
commit and reproduction command. Painted source assets remain in the repository.
