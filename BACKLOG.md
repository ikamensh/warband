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
evidence ([`70ec7cb`](https://github.com/ikamensh/warband/blob/70ec7cb9089f0ad1bfbe42c4705f56a6ac0476a0/BACKLOG.md)); WB-038, merged as `75dc68f`, published as a preview
([`75dc68f`](https://github.com/ikamensh/warband/blob/75dc68f231810cdfe83d5ff6f5f47c48cfb5422f/BACKLOG.md)); WB-052, merged as `a2212f5`
([`a2212f5`](https://github.com/ikamensh/warband/blob/a2212f53d78ae5c28ec64727eaabc2ac3142d183/BACKLOG.md)); WB-049, merged as `9418ec5`
([`9418ec5`](https://github.com/ikamensh/warband/blob/9418ec5babcbf57aed2a2e5939a502fd8477a49d/BACKLOG.md); WB-051, merged as `0a820ff` ([`0a820ff`](https://github.com/ikamensh/warband/blob/0a820ffdfe3b18f8e06a5ed5ac3f89223943f70c/BACKLOG.md))); WB-039 and WB-044, merged as `f8ba0eb`
([`a8951a7`](https://github.com/ikamensh/warband/blob/a8951a7ca8b76c8df9b8e12b87ed8a9e235e7e1f/BACKLOG.md)); WB-053, merged as `7158d46`
([`dbbb2d1`](https://github.com/ikamensh/warband/blob/dbbb2d132a56e60a7aa4db0fcb66de70a5000aa0/BACKLOG.md)).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-048 | Next | done | Show construction as a building site, and let a started building only finish or be cancelled | User 2026-09-19 |
| WB-050 | Next | done | Footmen hold a line: slower, better armoured, stronger with a neighbour at each side | User 2026-09-19 |

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

**Done 2026-09-19** (branch `building-sites`). The acceptance is the
done-when above, taken as written; the open question of a dead builder's
refund is answered as the full cost.

Rules: an order to a builder waits behind its work (`_issue` keeps the
Build order at the front; a stop drops only what was to come), so a started
building is finished or cancelled. `cancel_building` refunds the whole cost
and frees the builder, which then does what it was told meanwhile. A
builder removed while building cancels its site with the full refund, and
a planned request stands and starts anew. `resume_construction`, its smart
order and its settlement path are deleted. A save from before, holding a
shell whose builder walked off, cancels and refunds it on load. `resign`
now removes buildings before units, since a builder's removal cancels its
site. Tests: `test_a_builder_finishes_what_it_started...` and
`test_a_site_whose_builder_is_gone...` (`test_model.py`) and the settlement
pair; the resume rows are gone from the properties and atomicity tables.
The AIs never walked a builder off, so the fingerprint and `sim_bench`
digest are unchanged, and the ladder has nothing to measure. Fuzz (two AI
games and three monkey runs) is clean.

Art: two painted looks per race, `founded` and `raised` (eight sheets,
`warband/assets/restyled/<race>.buildings.{founded,raised}`), made with
`tools/restyle.py --looks founded,raised` on OpenRouter; `docs/warband-art.md`
says how. A site wears them whole, not the finished building faded; with the
procedural art it keeps the plain site. `ambience.py` draws the builder
hammering just off the site's front corner (the peasant's blow frames),
dust rising from the work, and a spark at each blow. Native frames of a
farm, barracks and hall at a quarter, half and three quarters, for all four
races, were looked at (first frames put the builder behind the walls, so it
was moved out and drawn above). `tools/visual_lint.py` finds nothing. The
fast and slow tiers pass (1073 and 511).

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

**Started 2026-09-19**, branch `footman-line`. WB-049 is merged; the flank
bonus adds to the armour number and does not touch the classes.
**Acceptance (recorded before implementation):**

1. Numbers: the footman walks 2.0 (was 2.4) and wears 3 armour (was 2);
   the elf Sentinel and dwarf Ironguard keep their tweaks on top (2.15
   and 3; 1.85 and 4). The orc grunt keeps what it had, 2.4 and 1 armour,
   its frenzy, and no formation: the fast brawler beside the others' line.
2. Flank: a footman (not a grunt) wears `FORMATION_ARMOR` (1) more for a
   friendly footman at its left and 1 more for one at its right, measured
   across its facing (beside it, not ahead or behind). The unit panel's
   armour shows it.
3. Line: a move or attack-move that sends two or more footmen gives them
   slots in a line across the way they are going, `FORMATION_SPACING`
   (1 tile) apart, up to `FORMATION_WIDTH` (8) a row with further rows
   behind, keeping their order from left to right so no two cross. The
   order keeps its shared target, so group pace still works. On the way a
   footman more than `FORMATION_SLACK` nearer its slot than the one
   furthest from its own walks at `FORMATION_HOLD` of its speed, until the
   line has closed up, unless the line has broken (more than 6 tiles
   apart).
4. Tests pin the numbers, the flank bonus (alone, one neighbour, two,
   one ahead instead), the slots (a line across the march, no crossing),
   and a line of five keeping its shape over a march of at least 20 tiles
   around an obstacle; frames of that march are looked at. Saves from
   before load. The ladder shows the footmen archetype still worth
   playing and the orcs still a real choice; fuzz, the fingerprint,
   `sim_bench` and both tiers pass.

**Done 2026-09-19** (branch `footman-line`). Numbers as in 1 (the grunt's
tweak is now speed +0.4, armour -2, `formation=False`). `World.flanks` and
`armor_of` give the flank bonus. `World._line_slots` gives the slots (the
foremost make the front row; no line under `FORMATION_MARCH`, 4 tiles; a
slot in the trees or across water goes to the target). `World._march` walks
straight at each unit's place 3 tiles ahead of the line's middle while the
way is clear, else paths to its final slot, and the row hold paces the
line; `docs/unit-motion.md` part 6 has the why of each choice. Three things
turned up and were fixed. A waypoint within `ARRIVE` snapped every unit
slower than 2.4 on to it, a small speed-up at every waypoint; now only the
end of a walk does. The built-in `sum` over floats is compensated since
Python 3.12 and not in the compiled simulation, so the two parted in the
last bit; `model._middle` adds up in a loop (`docs/fast-simulation.md`).
Fuzz found a march stalled by a moving goal replanned every step in the
woods; the march now only steers at its moving place.

Measured: round a 3-tile rock the five split three and two and are dressed
again (under 1.5 tiles front to back, each on its side) 5 tiles past it,
then end in their slots in order; the worst spread on the way is 3.3 tiles
(it was 5.1 in single file, which lasted to the end). Frames of the start,
the rock, past it and arrival were looked at. A fleeing peasant now
outruns a footman, so two tests hold their victim; three triage-free tests
were adapted to the line (sixteen footmen stand in two rows of eight
within 5 of the spot). Ladder (nine agents, 12 seeds, 864 matches, branch
against main): footmen 1179 to 1235, siege 1381 to 1453, the rest within
their intervals. Race report (Master mirror, 8 seeds a pair, sides
swapped): orcs 21-25 (22-24 before), humans 28-17 (30-14), elves 20-24
(19-26), dwarves 22-25 (20-27): the grunt is still a real choice. Fuzz
(ten AI games on seeds 81, 300 and 500) is clean; step time in a
150-unit battle is unchanged within noise. The fingerprint and `sim_bench`
are refreshed, and the fast and slow tiers pass (1016 and 486).
