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
section; git history keeps the record. The last ID given is **WB-053**; a new
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
evidence ([`70ec7cb`](https://github.com/ikamensh/warband/blob/70ec7cb9089f0ad1bfbe42c4705f56a6ac0476a0/BACKLOG.md)); WB-038, merged as `75dc68f`, published as a preview ([`75dc68f`](https://github.com/ikamensh/warband/blob/75dc68f231810cdfe83d5ff6f5f47c48cfb5422f/BACKLOG.md); WB-052, merged as `a2212f5` ([`a2212f5`](https://github.com/ikamensh/warband/blob/a2212f53d78ae5c28ec64727eaabc2ac3142d183/BACKLOG.md); WB-049, merged as `9418ec5` ([`9418ec5`](https://github.com/ikamensh/warband/blob/9418ec5babcbf57aed2a2e5939a502fd8477a49d/BACKLOG.md)))); WB-039 and WB-044, merged as `f8ba0eb`
([`a8951a7`](https://github.com/ikamensh/warband/blob/a8951a7ca8b76c8df9b8e12b87ed8a9e235e7e1f/BACKLOG.md)).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-048 | Next | proposed | Show construction as a building site, and let a started building only finish or be cancelled | User 2026-09-19 |
| WB-050 | Next | proposed | Footmen hold a line: slower, better armoured, stronger with a neighbour at each side | User 2026-09-19 |
| WB-051 | Next | done | Clerics heal in visible single casts and carry a weak attack | User 2026-09-19 |
| WB-053 | Next | done | Systematic controls: three switchable schemes, endless training, Shift-placing and the planner's spot | User 2026-09-19 |

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

**Started 2026-09-19**, branch `cleric-cast`. **Acceptance (recorded before
implementation):**

1. A heal is a cast: the cleric faces its patient, winds up 0.5 s (the blow
   frames' wind-up), then restores `heal` hit points at once (15, half
   again with Blessing), then waits its 2 s cooldown. 15 every 2.5 s is
   today's 6 hp/s, so `heal_rate` and the AI's estimate are unchanged. A
   cast whose patient walks more than `WINDUP_SLACK` beyond reach, dies or
   is healed full meanwhile is lost; a new order breaks it off.
2. The cleric has a weak ranged blow (3, normal attack, the same range and
   rhythm). Left to itself it heals first and strikes only when no one in
   sight needs healing; one striking turns to heal as soon as someone does.
   A cleric is still no soldier: enemies pick it after soldiers (`_threat`),
   Arrows and Longbows skip it, frenzy skips an orc's, and the Master AI
   does not count it in its army.
3. Each cast is seen and heard: a ring and a rising burst of green sparks
   on the patient, a small ring on the cleric, "+15" floating up, and a soft
   chime (`SOUND_VERSION` bumped).
4. Tests pin the cast (its wind-up, amount, cooldown and the most-wounded
   choice), the attack used only when nobody needs healing, and the threat
   order. Frames of a cast are looked at. The fingerprint, `sim_bench`,
   fuzz, the fast and slow tiers and a ladder with the clerics archetype
   pass.

**Done 2026-09-19** (branch `cleric-cast`). `World._cast` replaces the
per-second trickle: face, wind up 0.5 s, restore `heal_amount` (15; 22 with
Blessing) at once, cool down 2 s; `heal_rate` is that over the period (6/s,
8.8 blessed). The cleric is 3 damage, 3 range, 0.5 + 2.0, a normal blow; a
cleric left to itself heals first, strikes only when no one in sight needs
it, and turns from striking to healing within a quarter second of a friend
being hurt. `UnitInfo.soldier` (damage and no healing) and a `ranged` that
excludes healers keep a cleric out of `_threat`'s soldiers, Arrows,
Longbows, frenzy, and the Master AI's army, soldier yardstick and tower
strike; the AI still counts a cleric by its healing. A player's attack
order now makes a cleric strike (it used to follow). On screen a cast shows
two rings and a green burst on the patient, a small ring on the cleric,
"+15" rising above the health bar, and a soft chime (`SOUND_VERSION` 11);
the wind-up raises the staff (the blow frames). Native frames of the
wind-up and the cast landing were looked at (the first "+15" sat on the
patient's head and was raised). `tests/warband/test_cleric_casts.py` (six
tests) pins the cast's amount, rhythm and wind-up, the last cast's
remainder, a cast broken off by an order, the most wounded first, the blow
only when no one needs healing, and soldiers before clerics; three triage
tests allow for the wind-up. Ladder (nine agents, 12 seeds, 864 matches,
branch against main): every move inside the intervals, clerics -33 the
largest. Fuzz is clean, the fingerprint and `sim_bench` refreshed, the fast
and slow tiers pass (1009 and 486). Hearing the chime in a match is left
for Ilya.

## WB-053 — Systematic controls

Ilya, 2026-09-19: make the hotkeys systematic and more convenient; train
some units endlessly ("auto-train archers", not twenty orders), several at
one building alternating; Shift-build (pick a farm, click many spots) and an
auto-build where the AI places the building; take it holistically, vim-like
(keys by mode and selection, most things one key), with two or three
control approaches switchable in the menu.

**Acceptance** (recorded as the goal was set, 2026-09-19; branch `controls`):

1. Rules: `World.set_auto_train` (recorded; the authority accepts it for a
   seat's own buildings and hides a rival's), strict turns among several
   types, training only from what unpaid orders have not claimed and after
   research planned there; `build(plan_if_short=True)` leaves a site its
   builder cannot pay for as a plan. Brains use neither: the fingerprint
   does not move. Atomicity rows, property tests and a replay to the bit.
2. Three schemes in `warband/ui/controls.py`, switched in Settings: Classic,
   Grid, Modal; every card lays out on fixed slots; each command of every
   card of every race has one key of its own in each scheme, and Grid's
   globals never meet the grid.
3. Endless training by Shift with the key, Shift+click or a right-click on
   the portrait (at a building, or from the Train catalogue at every
   producer), shown on the card and on the building's panel with why the
   next one waits; Cancel stops it.
4. One Build catalogue for peasants and plans that stays while placing;
   Shift keeps placing (Modal always), sites queue behind a peasant's other
   sites and spread over the selection, the ones short of money or a
   prerequisite become plans, queued sites are drawn and a taken site is
   refused; the building's key again lets the planner (`brains.ai.auto_site`)
   pick the spot, a hall by a free mine.
5. Help, hints, tutorial and keycaps follow the scheme; fuzz monkeys play all
   three; `tools/visual_lint.py` is clean with new screens; native frames
   through `tools/verify.py` with the new gestures are looked at.

**Done 2026-09-19** (branch `controls`, `00c3f2c`..`836bb04`): all five.
The design is `docs/controls.md`. On the way a real bug fell out: a build
queued with Shift behind a peasant's harvest never ran (a harvest order
never ends), so Shift-placing with a working peasant built nothing; sites now
queue only behind other sites. The cleric's key is H (healer): L was both
Cleric and Blessing at the church. Tests: `tests/warband/test_auto_train.py`
(13) and `tests/warband/test_controls.py` (35), the order atomicity,
property, snapshot, layout and lint suites extended; both tiers pass, the
fingerprint matches main's, fuzz (2 AI games, 12 monkeys over the three
schemes) is clean, `tools/visual_lint.py` finds nothing, and `tools/verify.py`
passes with frames of endless training, the planner's farm and Grid looked
at. Live online after the next server rollout (a contract change). Trying
the schemes in a real match is left for Ilya.

