# Warband backlog

Created 2026-09-16. This is the working queue for taking one task at a time.
The [Early Access criteria](docs/warband-early-access-criteria.md) remain the
release gates; [progress](docs/warband-early-access-progress.md) holds their
evidence. Shared engine work belongs in the [Saga2D backlog](../saga2d/BACKLOG.md).

Keep IDs stable and never reuse one. When starting an item, change its status
to `in progress` and record the branch; record its acceptance before
implementing and its evidence after, and split larger discoveries into new
IDs. `proposed` items still need scope selection. Within each priority, the
order is the suggested sequence, not a requirement to finish every earlier
item first. Once an item is done and merged into main, delete its row and
section; git history keeps the record. The last ID given is **WB-052**; a new
item takes the next one and updates this line.

Done and removed 2026-09-18, every one merged into main (whose code is live as
Warband 0.2.30): WB-001 to WB-009, WB-015, WB-017 to WB-023 and WB-025 to
WB-034. Their acceptance and evidence are in
[the backlog at `1a6e08b`](https://github.com/ikamensh/warband/blob/1a6e08b73872cb595756a9d4ba7bc96c685c5ef0/BACKLOG.md).
Removed later the same day, each with its record in the backlog at the
commit named: WB-011 and WB-016, live as Warband 0.2.32
([`8a13fae`](https://github.com/ikamensh/warband/blob/8a13faeb65a0457ec0cd65d53e0461f01a734b49/BACKLOG.md));
WB-010, live as 0.2.33
([`5cb5959`](https://github.com/ikamensh/warband/blob/5cb5959df79bc09042e6f597736d7e43240a15a2/BACKLOG.md));
WB-012, live as 0.2.34
([`12ecf88`](https://github.com/ikamensh/warband/blob/12ecf88fef5ba74fe6c29a76bdf4defcf0774a02/BACKLOG.md)).
Removed 2026-09-19: WB-040, merged as `9c5caa4`
([`c49badb`](https://github.com/ikamensh/warband/blob/c49badb5f2baaca0d882f500caa09b38b4139864/BACKLOG.md)); WB-035, merged as `464328e`
([`2ad4dcb`](https://github.com/ikamensh/warband/blob/2ad4dcb7723c7d46d7c611fd254caa387a0df3e4/BACKLOG.md)); WB-043, merged as `66d35a5`
([`0680eb5`](https://github.com/ikamensh/warband/blob/0680eb570c73abba14d3c431f89bedeba5846246/BACKLOG.md)); WB-037, merged as `1b9880f`, live as 0.2.53
([`5a57cb9`](https://github.com/ikamensh/warband/blob/5a57cb94292cd1e39a20969cfe7c4a3b827fac61/BACKLOG.md)); WB-036, merged as `4a77498`, live as 0.2.55
([`3f22525`](https://github.com/ikamensh/warband/blob/3f22525a4db442d7f8d0d2c02b7532375ad1e075/BACKLOG.md)); WB-024, closed on its evidence as `dd7cf5f`
([`896c6ea`](https://github.com/ikamensh/warband/blob/896c6eab99fb426d7f0aa02588b0fd1dc1463d07/BACKLOG.md)); WB-014, merged as `18eaf4a`, live as 0.2.59
([`5fd2ef4`](https://github.com/ikamensh/warband/blob/5fd2ef41798f8162811b9eb0d286c80c65c9bb26/BACKLOG.md)); WB-045, merged as `6ad2779`, live as 0.2.61
([`493e3bf`](https://github.com/ikamensh/warband/blob/493e3bfb3df8eaefc809dbc0a86c80683eb490a1/BACKLOG.md)); WB-042, merged as `13db600`, published as 0.2.63
([`13c9911`](https://github.com/ikamensh/warband/blob/13c991194c5b73d2babbd74c931681aee3c4b8a7/BACKLOG.md)); WB-046, merged as `59455cc`, live as 0.2.65
([`70b57b2`](https://github.com/ikamensh/warband/blob/70b57b2048b4a0986aecfad4ad5999e7292c0da6/BACKLOG.md)); WB-041, merged as `62e4970`, live as 0.2.67 on
bundle `3e3dfda8` ([`79bc783`](https://github.com/ikamensh/warband/blob/79bc78340bf30dcabb3a333f6df85b176bc4dcd3/BACKLOG.md)); WB-047, closed on its
evidence ([`70ec7cb`](https://github.com/ikamensh/warband/blob/70ec7cb9089f0ad1bfbe42c4705f56a6ac0476a0/BACKLOG.md)); WB-038, merged as `75dc68f`, published as a preview ([`75dc68f`](https://github.com/ikamensh/warband/blob/75dc68f231810cdfe83d5ff6f5f47c48cfb5422f/BACKLOG.md)); WB-039 and WB-044, merged as `f8ba0eb`
([`a8951a7`](https://github.com/ikamensh/warband/blob/a8951a7ca8b76c8df9b8e12b87ed8a9e235e7e1f/BACKLOG.md)).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-048 | Next | proposed | Show construction as a building site, and let a started building only finish or be cancelled | User 2026-09-19 |
| WB-049 | Next | done | Armour and attack types; archers strike the unarmoured harder | User 2026-09-19 |
| WB-050 | Next | proposed | Footmen hold a line: slower, better armoured, stronger with a neighbour at each side | User 2026-09-19 |
| WB-051 | Next | proposed | Clerics heal in visible single casts and carry a weak attack | User 2026-09-19 |
| WB-052 | Next | done | Catapults look for a useful shot instead of standing idle in a melee | User 2026-09-19 |

## WB-013 — Fresh-player and cross-platform acceptance

Refresh W06/W15 with the current candidate: observe first launch, first economy,
first battle, loss/resign, save/resume and the website-to-online-match journey.
Include a complete human match on the published Mac/Windows candidate and
record hardware, version and obstacles. Use `tools/visual_lint.py` for what it
can find, while retaining human assessment of animation and clarity.

**Done when:** each blocker becomes a reproducible ticket and is resolved or
explicitly deferred; current evidence replaces stale gate claims. Automated
checks cannot mark the human playtest complete.

**Blocked 2026-09-18:** this needs people who have not played before; nothing
to build until a playtest happens. What unblocks it: one or two fresh players'
sessions (a recording or notes on what confused them), on a Mac or on Windows.
The Windows report that came first is closed (WB-021, WB-022), and a Windows
desktop for scripted checks is [a runbook away](../saga-online/docs/windows-test-box.md).

## WB-048 — A building site, not a ghost; no abandoned shells

Ilya, 2026-09-19: an unfinished building should not be a see-through copy of
the finished one. It should have its own under-construction look, maybe
dust and some sign of the work going on. He also wants no abandoned
construction: it confuses players. Once a building is started it is either
finished or cancelled.

Today a builder ordered away (`_abandon_construction`, `warband/sim/model.py`)
leaves the shell where it stands, and another peasant can pick it up with
`resume_construction`. A cancelled building returns its whole cost
(`cancel_building`).

**Proposed scope:** the builder stays on the site until it is finished.
Orders to it are refused or queued until then, and the only way off the site
is to cancel. If the builder dies, the site is cancelled with the normal refund
(or a smaller one; to be decided). `resume_construction`, and the code and
tests for picking up an abandoned site, are deleted. The art is a site for
each building footprint and race: scaffold and foundations that grow in
steps with the build's progress, with puffs of dust and a hammering
animation while the work goes on. It is made the same way as the other
building art (`docs/warband-art.md`).

**Done when:** no rule path leaves an unfinished building with no builder.
Tests cover moving the builder, the builder dying, and cancelling. The AIs
and the settlement queue no longer rely on resuming. Frames of the sites at
three stages of progress, for each race, have been looked at. The rule change
changes the online simulation, so it goes live through a server rollout.

## WB-049 — Armour types and attack types

Ilya, 2026-09-19: archers should do extra damage to clerics, catapults and
peasants, the unarmoured. To do that, introduce armour types and attack
types, but leave most pairings at 100% for now so the balance is not upset
too much.

Today armour is a single number subtracted from damage (`armor_of`,
`_hit`); the only multiplier is the siege factor against buildings.

**Proposed scope:** each unit gets an armour class (for example unarmoured,
light, heavy, building) and each attacker an attack type (for example
normal, piercing, siege). One table of multipliers replaces today's
`siege` factor. At the start, the only multiplier other than 100% besides
siege is piercing against unarmoured (a first guess is 150%). The unit panel
and the help table show the classes.

**Done when:** the table is in `warband/sim/rules.py` and is the one place
the multipliers live. The native twins match the source (the fast-simulation
fingerprints). The league shows no race and no unit pushed out of use,
measured as the WB-balance league measures it. The rule change goes live
through a server rollout.

**Started 2026-09-19**, branch `armour-types`. **Acceptance (recorded before
implementation):**

1. `rules.py` gains `ArmorClass` (unarmoured, light, heavy, fortified) and
   `AttackType` (normal, piercing, siege), and one table, `DAMAGE_FACTORS`,
   is the only place a pairing's multiplier lives. It holds siege against
   fortified at 1.5 (today's `siege` field, which is deleted) and piercing
   against unarmoured at 1.5; every other pairing is 1.0. Peasants, clerics
   and catapults are unarmoured, archers and scouts light, footmen and
   knights heavy; every building is fortified. Archers (every race's) pierce,
   catapults siege, the rest strike normally. Towers keep a normal attack,
   because WB-037/WB-044's rush answers were measured on it.
2. The multiplier applies before armour, as the siege factor did. A frame
   still wears no armour (`test_a_frame_wears_no_armour_and_a_standing_tower_does`).
   A save made before the change, with a stone in flight, still loads.
3. Tests pin: an archer strikes a peasant, a cleric and a catapult for half
   again its blow and a footman as before; a catapult strikes buildings as
   before; a tower's arrow strikes a peasant as before; the table covers
   every unit. The unit panel's armour and damage hints and the codex name
   the classes. The native twins, the compiled simulation and the fast and
   slow tiers pass; the fingerprint and `sim_bench` are refreshed. A ladder
   with the archer, footman and siege archetypes shows none pushed out of use.

**Done 2026-09-19** (branch `armour-types`). `ArmorClass`, `AttackType`,
`DAMAGE_FACTORS` and `damage_factor` are in `rules.py`; `World._hit` applies
the factor before armour, and `UnitInfo.siege` is deleted. Projectiles carry
their attack type, and a save made before the change still loads with its
shots in flight: a stone is read as siege, an archer's arrow as piercing,
anything else as normal. `tests/warband/test_armour_types.py` (eight tests)
pins the archer against peasant, cleric and catapult (half again), against
a footman (as listed), a footman against a peasant, a tower's arrow against
a peasant, a stone against a farm, the table and the old save. The frame
test still passes. The unit panel's damage hint names the attack and what
it does ("piercing, ×1.5 against unarmoured"), its armour hint the class;
the codex's role column adds the class and any attack that is not normal.
Both were looked at, and `tools/visual_lint.py` passes `codex_0` at
1280x800 and 1200x680 (a longer first wording overflowed 1200x680 and was
shortened). Ladder, nine agents with the archer, footman, siege, raider
and cleric archetypes, 12 seeds, 864 matches, branch against main: every
move is inside the 90% intervals. The siege archetype drops 68 (its
catapults are unarmoured now) and the raiders 47; the archers -11, the
clerics -30, the footmen -14, Hard -9, the Vanguard -25, the Warden +6. No
agent is pushed out of use. Fuzz (seed 81) is clean; the fingerprint and
`sim_bench` are refreshed. Fast and slow tiers pass (1003 and 486).

## WB-050 — Footmen hold a line

Ilya, 2026-09-19: footmen should be slower but more heavily armoured, with a
formation skill: armour bonus when other footmen stand to their right or
left. They should also move in a way that keeps the formation. This is for
every race except the orcs; grunts get a different balance of their own.

**Proposed scope:** footmen get lower speed (below today's 2.4) and more
armour (above today's 2). A footman gets bonus armour for each friendly
footman beside it, one to the left and one to the right, measured across its
facing. Groups of footmen that are ordered to move keep their places in a
line or block: they move at the speed of the slowest and do not string out.
This has to fit the elbow-room and step-away spacing (see
`docs/unit-motion.md`). The grunt keeps today's speed and gets a different
trait. Its "hits harder as it bleeds" can stay its identity, retuned to fit
(to be decided with Ilya).

**Done when:** a line of five footmen keeps its shape across a march of at
least 20 tiles around an obstacle, which is seen in frames. A test pins the
flank bonus (a footman alone, with one neighbour, with two). The ladder and
league show the footman is still worth building and the grunt is still a
real choice. The change goes live through a server rollout. This depends on
WB-049 if the armour classes change what "armour" means.

## WB-051 — Clerics cast their heals

Ilya, 2026-09-19: healing should be animated, a single cast with a short
cooldown that restores about 15 hp at a time. Clerics should also have a
weak attack of their own so they are not sent in to fight at the front.

Today a cleric heals 6 hp/s continuously (`heal_rate`) and has no attack.

**Proposed scope:** a heal is a wind-up, then a visible cast on one wounded
ally, then a cooldown. The rate stays near today's (15 hp every 2.5 s is
6 hp/s), so the balance does not move. The cast has an animation on the
cleric and on its patient, and a sound cue. The cleric gets a weak ranged
attack, used only when there is no one to heal. `pro_ai`'s
`retreat_wounded` estimate follows the new rate.

**Done when:** tests pin the cast (its cooldown, the amount, choosing the
most wounded ally in range) and the attack being used only when no one
needs healing. The cast has been seen in frames and heard in a match. The
change goes live through a server rollout.

## WB-052 — Catapults find something useful to do

Ilya, 2026-09-19: catapults seem not to attack when the melee lines meet.
They should look for somewhere they can shoot usefully and always try to do
something useful.

Why this happens: a crew firing on its own judgement aims only at its chosen
target (or where that target is heading). `_aim_point` returns None when a
friendly unit is within the splash radius plus `FRIENDLY_MARGIN`
(`warband/sim/model.py`), which is always true in a melee, and the crew then
waits.

**Proposed scope:** when its target cannot be hit without splashing its own
side, the crew looks for the best landing point in range. It scores each
point by the enemy value inside the splash (with extra weight for archers,
clerics and catapults) and allows no ally inside the splash. It also takes
buildings in range as targets. If there is no such point, it moves to a place
from which it can shoot the enemy's back ranks. It never walks into the enemy
lines inside its minimum range.

**Done when:** in a scripted clash (eight footmen a side, the enemy's
archers two tiles behind their line, one catapult six tiles back), the
catapult fires at least every other cooldown and never hits its own side.
The ladder shows no loss. The change goes live through a server rollout.

**Done 2026-09-19** (branch `catapult-aim`). Measured before the change on
the clash of the done-when (`tests/warband/test_siege_judgement.py`): one
stone in half a minute. From contact the crew stayed locked on the enemy
soldier in front of its own line, and every aim was refused. When the line
fell it chased a footman into a map corner, inside its own minimum range.
Now a crew on its own judgement chooses by what a clear stone would do
(`World._siege_choice`): every visible enemy within reach plus `SIEGE_STEP`
(3) tiles is scored by the enemies under the stone (`SIEGE_WORTH`: archers
2, clerics and catapults 3, anyone else 1, splash at 60%), with a walk to
reach it counting against it. Buildings count only when no unit can be
struck, at `SIEGE_BUILDING_WORTH`. The crew may drop the stone a tile beyond
a unit, where the splash still catches it, and when its target has no clear
stone it rolls closer, stopping two splashes outside its minimum range. It
chooses again while its target has no clear stone or stands inside that
range. The check against friendly fire (`_clear_of_friends`) now also
catches a friend whose velocity carries it under the stone, and one on its
way to fight an enemy within arm's length of the landing point (a footman
after an archer that steps back between shots).

On six seeds of the clash the catapult throws at least every other reload
(two to four stones in 17 to 21 s, the whole fight), hits its own side
never, and our side wins with five to seven footmen left. Before, it lost.
The ladder (`tools/arena.py ladder`, seven agents, 12 seeds, 504 matches,
branch against main): the siege archetype rises from 1346 to 1428, and every
other agent stays within noise (Vanguard -20, Warden -36, Hard -16, archers
+11, footmen 0). No agent loses, and none is pushed out of use. Fuzz (seed
81, two AI games) is clean. The fingerprint is unchanged (its matches field
no catapult); `tools/sim_bench.txt` is refreshed. The fast and slow tiers
pass (995 and 486). `docs/unit-motion.md` describes the crew's judgement.
Under the policy of 2026-09-19 the change goes live in the next batched
server rollout, not one of its own.

