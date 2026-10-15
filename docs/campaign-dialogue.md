# Campaign dialogue: the Aether Council and the field chronicle

Every campaign conversation gets the whole screen. The mission is hidden and
paused, its company and camera waiting exactly where the player left them.
Pre-mission words happen in a magical briefing chamber; words during or after
a mission happen over an illustration of that level's location. Both campaigns
use the same interaction and eleven individually authored briefing charts.

## The visual direction

The **Aether Council** is a wet-stone, brass-and-lockwork chamber. Three oval
portals overlook a luminous relief table. The current speaker arrives in the
left portal as a softly tinted projection: a short fade, gentle breathing
motion, drifting arcs and a travelling scan of aether. A previous speaker
remains faintly visible in the middle portal. Linked sigils under the portals
remember who has joined. Nobody appears before their first line.

A parchment field chart floats above the right side of the table. Its muted
blue waterways, green woodland, mountain hatching, paper grain and fold lines
belong to the same brass, teal and gold palette as the room. The chart uses
the level's real terrain, including crossings and obstructions. It is a survey,
not a live minimap: no unit positions, orders, economy or fog state update
while it is open. Only the locations the briefing discusses are annotated.

Each physical line has an authored chart beat, including conditional lines.
Advancing the conversation changes the caption, inks newly introduced
landmarks, pulses the current focus and draws a dashed directional route over
1.2 seconds where the narration calls for one. Earlier markers remain quietly
visible. Thus the Salt Caravan first locates the Old Camp and Broken Tooth,
then traces the journey through the causeway ford, and finally highlights the
river crossing and mill-dam pylon. The Maw introduces the Keystone, refuge,
Relief Sluice and different ways to work the broken ring in the same order as
the speakers discuss them. Animation uses a separate presentation clock and
random generator; it cannot affect simulation determinism.

The **field chronicle** gives the location painting most of the screen. The
image drifts slowly, with restrained motes and dark gradients behind the
chapter title and dialogue. Each level names its painting explicitly. Both
visits to Greywater share its landscape, and the Frostcomb journey and Karst
Hold share the mountain setting. The five Undertow levels each have their own
painting. These are establishing views of the location, not literal depictions
of every conditional event or claim that a particular ending occurred.

The bottom panel is dark blue-black, almost opaque, edged in antique brass.
A framed portrait and gold name identify the speaker; narration has a compass
seal and "The chronicle". Body text is 18 px, with generous line spacing and no
automatic advance or typing delay. The panel grows to hold the actual text or
answers. Its width caps at 1360 px and retains margins at 1200×680. The upper
right shows progress through the currently eligible lines.

## Interaction and continuity

- Space, Enter, the Continue button or a click outside the controls advances a
  line. The last briefing button says **Take command**.
- Escape or Skip goes to the next question or closes the conversation. It
  cannot skip an unanswered choice. Choices have numbered buttons and their
  original number keys; Space, Enter and background clicks cannot answer them.
- The original conditional lines, answer values, callbacks and witnessed
  journal entries remain authoritative. Rebuilding a layout does not add a
  second journal entry.
- Closing a conversation reveals the same mission scene. A debrief still
  saves its choices before the campaign advances. The epilogue uses the final
  location and returns to the campaign screen.
- The source assets are bundled in the game. No network or generation is
  required during a briefing, a mission, a save reload or packaged play.

## Where to author and verify

`Mission.dialogue_art` selects a location under `warband/assets/`.
`Line.chart` carries its optional `ChartBeat` beside the words in
`undertow_dialogue.py` or `missions.py`. Inserting or reordering a line moves its
annotation with it; a line without an annotation simply holds the chart quiet.
`story/briefing.py` resolves named places from that mission's authored landmarks,
points and initial settlements. A missing named place raises a clear error.
Routes are schematic directional links through the named waypoints, rather
than movement orders or promises of a walkable path. All route waypoints are
marked when the route is introduced.

`MissionScene.conversation` supplies the chapter, art, journal and optional
chart to `DialogScene`; every runtime entry uses that route. `dialog.py` owns
reading and choosing. `dialog_stage.py` owns scenery and projection animation.
The chart snapshots the terrain once; its texture key includes the terrain,
dimensions and seed. Paper is painted only when that texture is absent from
the game's asset cache, so reopening the same chart reuses the image. A replay
with different geography cannot reuse a stale painting. Map labels stay
inside the paper and avoid the compass and each other.

`tests/warband/test_briefing_views.py` checks all eleven charts against their
worlds without modifying the simulation, editing and reordering words, skipped conditional annotations, persistence
without art metadata, every eligible line and map label at the small window,
and a real mission's frozen briefing/command handoff.
`test_dialog_choices.py` covers opaque presentation and numbered answers;
existing campaign and journal integration tests cover triggers, choices,
saves, results and epilogues. The visual lint walks each level's briefing and
the field conversation and choice layouts at both supported lint resolutions.

Reproduce native frames with:

```bash
caffeinate -u -t 3
python3 ~/saga/tools/slot.py -- uv run python tools/verify_dialogue.py /tmp/warband-dialogue --size 1200x680 --animation
```

The generated scenery's final prompts are recorded in [campaign-art.md](campaign-art.md).
Verification output follows the Saga retention rules in `~/saga/evidence/warband/campaign-dialogue/`.
