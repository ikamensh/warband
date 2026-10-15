# The Undertow: first impression

The selected campaign is **The Undertow**. Its painted valley, authored tactical maps and
keepers give it a stronger opening foundation than rebuilding Thornwood. The rework concentrates
on the entrance and Millfield; the remaining four chapters and their consequences continue intact.

## Acceptance criteria

These criteria were set before implementation. "AAA first impression" means an intentional,
polished entrance and first playable sequence; it is a design target, not a claim about budget.

1. A striking campaign entrance, a clear premise, and one obvious action to begin.
2. A concise opening establishing a character, a threat, and the player's immediate role.
3. A meaningful command within 30 seconds of taking control, then escalating pressure.
4. Readable objectives and story sites; no unnecessary interruption during the first fight.
5. A complete, winnable opening, with alternate outcomes and save/resume verified through
   ordinary orders and native screenshots.

## The sequence

The first visit lets the valley painting occupy the screen. A shaded left column introduces
Issa's role, previews the first command and offers Begin. The chapter itinerary and map preview
remain useful once a campaign is under way; both stories retain their independent progress.

Begin opens a three-line briefing **over Millfield itself**, paused. Mother Hasp's portrait and
her threatened field establish the human stakes before explanations of the wider world. The
last line names movement, attacking and Mend; **Take command** hands over the same camera and
selected seven-unit company. Reading or skipping the briefing cannot cost lives.

The company starts beside Hasp's south field, with a wounded outrider and enough spell-light
for Mend. Wolves arrive four seconds into play. The first and last wave announcements are
notices, so they leave the player in command. A successful campaign spell returns to the selected
company immediately. Orchard rows and the millrace frame the village; the field, vault and
lock-pylon have charted names on the map and minimap.

After the wolves, Hasp sees the next beasts ignore the farms and head for the vault. Two lines
explain the action-based fork: keep the vault through the final surge, or cross the north ford
and destroy its pylon to shutter it. There is no intention menu asking for a decision that only
subsequent orders can fulfil. The player can change course until the pylon falls. Holding,
deliberate shuttering and a lost vault remain distinct consequences in the later campaign.

The initial objectives show the current work; future objectives wait for their story beat.
Notices reserve room above the command card. Results clear transient effects so a sliding
warning cannot freeze half off screen behind the outcome.

Campaign and mission IDs, remembered flags and autosave identities are unchanged. Saved maps
keep their existing terrain and units. The removed intention choice was not a remembered flag;
an already queued old conversation still reads through the existing saved-dialogue format.
The shared simulation and its recorded fingerprint are unchanged.

## Reproduction

Use the stack slot for the following checks, with an explicit temporary output directory:

```sh
python3 ~/saga/tools/slot.py -- uv run python tools/verify_opening.py /tmp/undertow-opening --size 1200x680
python3 ~/saga/tools/slot.py -- uv run python tools/visual_lint.py --no-images --screens campaign_,mission_ --evidence /tmp/undertow-layout
python3 ~/saga/tools/slot.py -- uv run pytest -q --slow tests/warband/test_campaign_opening.py tests/warband/test_undertow.py
```

The native opening verifier enters through the menu, advances the briefing with actual keys,
casts Mend with Alt+1 and a mouse click, verifies that a native right-click really produces an
attack order, saves and resumes, then holds the vault with the existing public-order driver.
Its receipt records the first command, victory time and persisted campaign progress.
Automated times measure simulation time, not a human's reading time or first playthrough.
The layout walk includes the final briefing button and the opening after a first Mend.

## Hasp portrait provenance

Asset: `warband/assets/campaign/hasp.png`. Generated with the built-in image generation tool;
inspected at full size and in the actual native dialogue panel. The existing animated peasant
body remains her world representation. No additional unit type or animation was introduced.

Final prompt:

> Use case: stylized-concept. Asset type: square dialogue portrait for Warband's fantasy story
> campaign The Undertow. Generate Mother Hasp, a weathered human miller in her late fifties,
> grey hair tied beneath a faded linen headscarf, flour-dusted indigo work apron, strong broad
> face, kind but unwavering eyes looking toward the viewer. Head and shoulders fill the square;
> background is a softly blurred timber watermill and golden fields with distant violet storm
> light. Cinematic painted realism, textured cloth and skin, warm gold key light and subtle
> violet rim, grounded medieval fantasy, readable at 104 pixels. Match the dramatic portrait
> treatment of the campaign's Captain Issa: natural proportions, earthy colors, no cartoon
> outlines. No armor, no weapons, no text, no border. Save this new character asset; do not
> modify the existing characters.
