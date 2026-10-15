# The Undertow — narrative revision

The playable source is `warband/story/new_campaign.py` and
`warband/story/undertow_dialogue.py`. This revision keeps the five Steps, playable
races, campaign/mission ids and existing outcomes. Permission to change levels is
used where a player's action can carry a story beat better than another speech.

## Craft sources

Inspected source, rather than search snippets:

- [jwynia/agent-skills: Worldbuilding](https://github.com/jwynia/agent-skills/tree/e02ec7e226a6e4f8419fd3b88a1d8e472d421b32/skills/creative/fiction/worldbuilding/worldbuilding): trace magic into livelihoods, institutions and ordinary customs; give an opposing faction internal disagreements.
- [jwynia/agent-skills: Dialogue](https://github.com/jwynia/agent-skills/tree/e02ec7e226a6e4f8419fd3b88a1d8e472d421b32/skills/creative/fiction/character/dialogue): distinguish syntax and motives; let an exchange change a relationship as well as deliver information.
- [danjdewhurst/story-skills: Scene Craft](https://github.com/danjdewhurst/story-skills/tree/4b8019d7fa08e1e1866be360fadab2a2f7cbcf11/skills/scene-craft), especially dialogue/subtext: plan the spoken and hidden wants before rewriting, and test whether lines still identify their speaker without a name.

The Skills CLI search reported 717 installs for jwynia's Worldbuilding and 805
for danjdewhurst's Worldbuilding; their repositories had 172 and 314 stars when
inspected. These are small fiction-focused collections, not official standards.
The game keeps its existing Python content and design notes; book-project
scaffolding and the Story CLI are not part of its runtime or authoring pipeline.
The requested revisions are written directly into the game, using the diagnostic
skills to evaluate them.

## Diagnosis and scene plan

The world already has a strong causal premise: metered aether feeds the valley,
and the profitable seam is its weakening lid. The writing overexplains the
verdict. Several voices fall back on accounts, public records and promises, and
Sella's eventual admission is too frictionless. Keep the facts; dramatise who is
trying to get what from whom.

| Scene | Spoken want | Unspoken pressure | Turn the player earns |
|---|---|---|---|
| Millfield | Issa wants the fields defended; Hasp wants her fieldhands home | Issa reaches for a familiar repair job; Hasp needs her to look at people first | The wolves' target reveals that the useful lock is drawing danger |
| Salt Caravan | Brakk wants a camp above the pans; Ugga wants enough hands to raise it | Brakk refuses to be somebody else's expendable number; Ugga conceals fear in practical jokes | Before blasting the dam, the player knows whose millpond will be spent |
| Ashford confrontation | Issa offers responsibility; Brakk asks about his sister | Issa wants something she can repair; Brakk will not supply absolution | They agree to travel together without pretending the debt is settled |
| Grove parley/rout | Wrenna wants the saws stopped; Pell has a signed order | Wrenna wants Issa to own the damage; Pell needs permission to disobey | Issa owns her warrant on both paths; the player learns the firebreak tradeoff before choosing |
| Tarnlock | Dagna wants two Weights standing; Sella wants the locks opened | Dagna's family concealed the missing survey; Sella needs her old pupil to trust her | The seam explains both Tarnlock's wealth and its failing works; no faction gets a clean account |
| Maw | Each keeper offers a way to survive | Issa must protect people while fighting their commander; Sella fears that stopping means betraying her crews | A named, charted refuge and an approach warning make restraint legible; each ending retains a cost and a dissenting voice |

## Voice and continuity constraints

- **Issa:** short, useful commands. Under pressure she names a task she can fix.
  At Ashford she stops hiding behind the passive voice. No instant forgiveness.
- **Hasp:** flour, daylight, fieldhands and working hours. Practical authority over
  the village; she can challenge a captain without becoming a second captain.
- **Brakk:** names, animals, footing, a count made aloud. Slow to answer a request
  for trust. His sister is Orra; this name personalises the established Ashford loss.
- **Ugga:** pegs, loads, boots, a joke with work behind it. Not a disposable comic.
- **Wrenna:** observable growth and dry warmth. She asks what a claim means for a
  particular tree or root, rather than delivering the campaign's thesis.
- **Pell:** a procedural soldier until obeying stops making sense. The warrant is
  genuine; Issa cannot blame Sella for her own order.
- **Dagna:** workshop language and exact measures. Her evasions collapse into
  first-person admissions. The seam was hidden from Sella, not from herself.
- **Sella:** a capable teacher who tests her pupil; certainty hardens into urgency.
  She was right about rising pressure and wrong to steal her crews' choice.
  Opposition to RESEAL survives her confession and defeat.

World detail should do work: rationed spell-light affects milling hours; a camp's
history fits in reusable pegs; root growth records a spill; maintenance wages come
from the destructive seam. No new cosmology, magic rule or unit asset is needed.
Branch rejoins must never assume a shuttered vault, whole grove, living Guardian,
spared tower that the player's path did not produce.

## Mission changes and review

The caravan briefing identifies Hasp's millpond before the player can destroy
the dam; Ugga argues for the quick crossing, Brakk identifies who pays, and the
causeway and south ford remain alternatives. Its map label identifies the owner.
The grove's peaceful and violent routes both confront Issa with her warrant;
the plan names the easier fight versus lost roots before the player chooses.
Seam answers name the quiet-rift versus extra-bloom consequence before the haul.

The Maw charts the existing occupied refuge, and a one-time warning names Tern's
apprentices when soldiers approach within sixteen tiles, before ordinary siege
range. The original survival flag still records whether the tower stands at
victory. No escort, reward, new flag or forced detour is added. The warning's
trigger state survives a mission save. Tactical commitment instructions remain
available before action and in the journal, in narration rather than a captain's
speech. Each ending's dialogue keeps an objection or a loss: Brakk demands the
actual valve key, Dagna loses her workshops, Wrenna must leave tenders behind.

An independent Claude review through `second-opinion --primary codex` confirmed
the shared abstract vocabulary, the missing peaceful-path confrontation, and
cost-free ending reactions. It challenged the proposed refuge escort as a
checklist added to an already busy finale. The final revision uses a named
landmark and warning instead. Concrete findings were checked against both the
dialogue file and inline mission script before editing.
