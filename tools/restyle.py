"""Re-render Warband's unit and building sprites with an image model (see ``sagaforge.restyle``).

    uv run python tools/restyle.py dump DIR                 # one sheet + prompt per subject
    uv run python tools/restyle.py render DIR               # repaint the sheets (Codex by default)
    uv run python tools/restyle.py cut DIR                  # key, register, check; install into warband/assets/restyled
    uv run python tools/restyle.py preview DIR OUT_DIR      # walk/attack GIFs and building strips, original above restyled
    uv run python tools/restyle.py refresh DIR              # the whole procedure; previews land in DIR/previews
    uv run python tools/restyle.py check DIR [--fix|--patch]  # a vision judge compares every painted cell with its stand-in;
                                                            # --fix re-renders a sheet with the complaints in its prompt,
                                                            # --patch only the rows with questioned cells

A *subject* is one unit of one race (a carrying peasant is its own subject) or the nine
buildings of one race in one look: ``intact`` is painted from the low-poly stand-ins;
``active`` (producing) and ``damaged`` are painted from the installed intact painting, so
a building keeps its identity across its looks.  ``--race`` picks the race; ``--units``
and ``--buildings`` (with ``--looks``) narrow the subjects, which are all of the race by
default.  ``render --provider openrouter --model ...`` uses an OpenRouter image model
instead of Codex's built-in tool.  Sheets are rendered for player 0; the game recolours
them per player.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from sagaforge import render3d as r3  # noqa: E402
from sagaforge import restyle  # noqa: E402
from warband import textures  # noqa: E402
from warband.races import RACES  # noqa: E402
from warband.rules import BuildingType, Race, Resource, UnitType  # noqa: E402

RESTYLED = Path(__file__).resolve().parent.parent / "warband" / "assets" / "restyled"
SCALE = 2.0  # sheet pixels per logical unit (units)
BUILDING_SCALE = 2.5  # buildings are big and static, and nine of them fill Codex's output size at this scale
MARGIN = 6  # empty pixels around the widest frame inside a cell

STYLE = ("Re-render every cell as a polished, appealing game sprite in a rich hand-painted fantasy style "
         "(Warcraft 2 / Heroes of Might and Magic feel): readable silhouette, volumetric shading, metal highlights, "
         "cloth folds, light from the upper left, a small soft dark contact shadow under the feet. Sprites will be "
         "shown at about half this size, so keep shapes bold and edges crisp.")

FACINGS = "right, down-right, down (towards the viewer), down-left, left, up-left, up (away from the viewer), up-right"
FRAME_NAMES = {"stand": "standing at guard", "walk1": "walking, left foot forward (contact)", "walk2": "walking, passing with the right knee lifted",
               "walk3": "walking, right foot forward (contact)", "walk4": "walking, passing with the left knee lifted",
               "wind": "wind-up: weapon drawn back, torso twisted away, weight back", "strike": "strike: lunging forward, weapon driven at the enemy",
               "follow": "follow-through: weapon swept across the body, torso twisted the other way", "recover": "recovering back to guard",
               "chop1": "chopping a tree, axe raised", "chop2": "chopping, fast downswing", "chop3": "chopping, axe contact",
               "chop4": "chopping, recovery"}

TEAM = "blue is the team colour and must stay this blue"
SUBJECTS: dict[tuple[Race, UnitType], str] = {
    (Race.HUMAN, UnitType.PEASANT): f"a human peasant worker in a blue tunic ({TEAM}) and a cloth cap, carrying a woodcutter's axe",
    (Race.HUMAN, UnitType.FOOTMAN): f"a human footman: a stocky soldier in a steel helmet with a blue plume and mail, blue tunic ({TEAM}), "
                                    "a blue kite shield with a pale cross, and one sword with a gold crossguard",
    (Race.HUMAN, UnitType.ARCHER): f"a human archer in a dark green hooded cloak over a blue tunic ({TEAM}), with a longbow and a quiver of arrows",
    (Race.HUMAN, UnitType.KNIGHT): f"a human knight in full plate on an armoured warhorse with blue caparison and trim ({TEAM}), carrying a lance and a shield",
    (Race.HUMAN, UnitType.SCOUT): f"a human scout: a light rider in leather armour and a blue tunic ({TEAM}) on a fast unarmoured horse",
    (Race.HUMAN, UnitType.CATAPULT): f"a human catapult: a wooden siege engine on wheels with a throwing arm, a boulder and a blue team pennant ({TEAM}); "
                                     "the attack row swings the arm",
    (Race.HUMAN, UnitType.CLERIC): f"a human cleric: a healer in a pale hooded robe with a blue sash ({TEAM}), holding a staff",
    (Race.ORC, UnitType.PEASANT): f"an orc peon: a green-skinned, broad worker in a blue loincloth and harness ({TEAM}), carrying a crude axe",
    (Race.ORC, UnitType.FOOTMAN): f"an orc grunt: a hulking green axeman in dark iron with spiked pauldrons, a blue tabard ({TEAM}), a hide-bound round "
                                  "shield studded with bone spikes, and a heavy cleaver",
    (Race.ORC, UnitType.ARCHER): f"an orc axethrower: a green-skinned brute in dark red cloth and a blue sash ({TEAM}), hurling throwing axes from a belt",
    (Race.ORC, UnitType.KNIGHT): f"an orc ogre: a two-headed, unarmoured giant on foot with a blue loincloth ({TEAM}) swinging a huge spiked club",
    (Race.ORC, UnitType.SCOUT): f"an orc wolf rider: a green raider in leather and a blue sash ({TEAM}) on a great grey wolf, with a spear",
    (Race.ORC, UnitType.CATAPULT): f"an orc catapult: a crude, skull-decorated siege engine of dark wood and bone on wheels, a blue pennant ({TEAM}), "
                                   "with a throwing arm and a boulder",
    (Race.ORC, UnitType.CLERIC): f"an orc shaman: a hunched green mystic in dark robes and a blue sash ({TEAM}), with a totem staff and bone charms",
    (Race.ELF, UnitType.PEASANT): f"an elven gatherer: a slender fair-skinned worker in green leathers and a blue sash ({TEAM}), carrying a woodcutter's axe",
    (Race.ELF, UnitType.FOOTMAN): f"an elven sentinel: a slender warrior in silvery scale, a winged leaf helm, a blue tabard ({TEAM}), a leaf-shaped buckler "
                                  "and a curved blade",
    (Race.ELF, UnitType.ARCHER): f"an elven ranger in a green hooded cloak over a blue tunic ({TEAM}), with a tall recurve bow and a quiver",
    (Race.ELF, UnitType.KNIGHT): f"an elven stag knight in silvery scale with a blue caparison ({TEAM}) riding an antlered stag, carrying a lance and a buckler",
    (Race.ELF, UnitType.SCOUT): f"an elven outrider in green leathers and a blue sash ({TEAM}) riding a swift deer, with a spear",
    (Race.ELF, UnitType.CATAPULT): f"an elven ballista: a living-wood siege engine on wheels sprouting leaves at its tail, with a blue pennant ({TEAM}), "
                                   "that fires a great bolt; the attack row releases the bolt",
    (Race.ELF, UnitType.CLERIC): f"an elven druid in a green hooded robe with a blue sash ({TEAM}), holding a gnarled staff",
    (Race.DWARF, UnitType.PEASANT): f"a dwarven miner: a squat, broad, red-bearded worker in a blue smock ({TEAM}) and a cap, carrying a pick-axe",
    (Race.DWARF, UnitType.FOOTMAN): f"a dwarven ironguard: a squat, broad axeman in heavy bronze-trimmed plate, a horned nasal helm, a blue tabard "
                                    f"({TEAM}), a bossed round shield and a double-bitted axe",
    (Race.DWARF, UnitType.ARCHER): f"a dwarven crossbowman in a mail coat and a blue tabard ({TEAM}), with a heavy crossbow and a bolt case",
    (Race.DWARF, UnitType.KNIGHT): f"a dwarven bear rider in bronze-trimmed plate with a blue caparison ({TEAM}) on an armoured war bear, carrying a lance and a shield",
    (Race.DWARF, UnitType.SCOUT): f"a dwarven ram rider in leather and a blue sash ({TEAM}) on a shaggy mountain ram, with a spear",
    (Race.DWARF, UnitType.CATAPULT): f"a dwarven mortar: a squat iron mortar barrel on a wheeled carriage with a blue pennant ({TEAM}); the attack row fires "
                                     "with the barrel jolting back",
    (Race.DWARF, UnitType.CLERIC): f"a dwarven runepriest in a grey hooded robe with a blue sash ({TEAM}), holding a rune-carved staff",
}
CARRY = {Resource.GOLD: ", carrying a heavy sack of gold", Resource.LUMBER: ", carrying a bundle of lumber on the shoulder"}

#: Known shortcomings of the low-poly stand-ins that the painter is asked to correct in place.
FIXES: dict[tuple[UnitType, Resource | None], str] = {
    (UnitType.PEASANT, None): "the axe is gripped with both hands during the chop; the cap sits on the head",
    (UnitType.PEASANT, Resource.LUMBER): "the bundle of logs rests across the shoulder and is held from below with both hands; it never floats above the head",
    (UnitType.PEASANT, Resource.GOLD): "the sack is cradled in the arms against the chest, hands visible on it",
    (UnitType.FOOTMAN, None): "exactly one sword, gripped in the right hand; the shield is strapped to the left forearm and follows that arm; "
                              "the pale cross on the shield is a flat painted emblem, never a hilt or a second weapon; the only gold is the sword's crossguard",
    (UnitType.ARCHER, None): "the weapon is held in both hands, aimed in the wind-up and loosed in the strike; the ammunition hangs on the back or belt",
    (UnitType.KNIGHT, None): "the rider sits in a saddle with stirrups and holds the reins; the weapon is gripped and couched under the arm in the strike, not floating beside the mount",
    (UnitType.SCOUT, None): "the rider sits in a saddle and holds the reins; the spear is gripped",
    (UnitType.CATAPULT, None): "the projectile sits in or on its launcher, never on top of the arm like a mace head; the launcher is empty after the shot; "
                               "the wheels have spokes and the carriage has a windlass with rope",
    (UnitType.CLERIC, None): "the staff is gripped in one hand; the raised hand in the strike frames glows softly",
}
RACE_FIXES: dict[tuple[Race, UnitType], str] = {
    (Race.ORC, UnitType.KNIGHT): "the ogre stands on its own two feet with no mount; both heads look towards the facing; the club is gripped in both hands",
    (Race.ORC, UnitType.CATAPULT): "exactly one stone, inside the sling basket at the end of the arm; the small skull on the frame's front is bone with eye sockets, "
                                   "never a second stone; the basket is empty after the throw",
    (Race.ELF, UnitType.CATAPULT): "the bolt lies in the groove of the ballista and is gone after the shot; the wheels have spokes",
    (Race.DWARF, UnitType.CATAPULT): "exactly one barrel (one muzzle, one bore), a fat iron mortar tipped back in a low wooden bed with trunnion cheeks; "
                                     "no second tube, no tall frame; the bed carries a rack of shot; the barrel recoils in the strike with smoke at the muzzle",
}
#: What every painted cell must contain, for the judge to count.
INVENTORY: dict[UnitType, str] = {
    UnitType.PEASANT: "one figure, one tool (axe) or one carried load, no shield",
    UnitType.FOOTMAN: "one figure, exactly one sword (one hilt), exactly one shield",
    UnitType.ARCHER: "one figure, exactly one bow (or a throwing axe in hand for orcs, a crossbow for dwarves), no shield",
    UnitType.KNIGHT: "one rider on one mount (the orc ogre: one two-headed giant on foot), one lance or club, at most one shield",
    UnitType.SCOUT: "one rider on one mount, one spear, no shield",
    UnitType.CATAPULT: "one siege engine, one throwing arm or barrel, wheels, at most one projectile",
    UnitType.CLERIC: "one figure, one staff, no shield, no sword",
}
PLAUSIBLE = ("The reference is a rough low-poly stand-in. Where its construction is physically implausible (a load floating instead of "
             "held, a prop attached instead of resting, a weapon beside a hand instead of in it), draw the plausible version in the same "
             "place, at the same size, without changing the pose or moving the feet.")

# -- Buildings --------------------------------------------------------------------------

BUILDING_TYPES = [bt for bt in BuildingType if bt is not BuildingType.GOLD_MINE]
LOOKS = textures.BUILDING_LOOKS  # intact, active, damaged
ARCHITECTURE: dict[Race, str] = {
    Race.HUMAN: "human: a medieval kingdom that builds in grey stone, oak timber and white plaster under thatch and grey slate",
    Race.ORC: "orcish: crude dark timber and rough stone, hides stretched over frames, red-brown hide roofs, bone spikes at the corners "
              "of every yard and a skull on a pole",
    Race.ELF: "elven: pale stone and living wood with slender lines, leaf-green roofs, saplings at the corners of every yard and a gold moon standard",
    Race.DWARF: "dwarven: heavy granite blocks and dark timber, dark grey slate roofs, copper caps and domes, and squat rune pillars "
                "with copper caps at the corners of every yard",
}
_GATE = ("in front, twin round gate towers with battlements and blue banners flank an arched gate with a portcullis and steps")
_FARMYARD = "a round haystack and a fence along the front"
_STABLE = "a long timber stable with three arched stalls under a straw-coloured gable roof and a blue banner; a fenced paddock with {beast}, and a hay trough"
_CHURCH = ("a cross-shaped nave under green-teal shingle roofs, an octagonal bell tower with a conical spire topped by {top}, "
           "{window} arched window over the door, two blue banners, steps")
#: What each building is, per race (the prompt prefixes the race's name for it).
BUILDING_SUBJECTS: dict[tuple[Race, BuildingType], str] = {
    (Race.HUMAN, BuildingType.TOWN_HALL): f"a square stone keep under a dark blue pyramid roof with a small blue-roofed turret and a pennant on top; {_GATE}",
    (Race.ORC, BuildingType.TOWN_HALL): f"a square stone keep roofed by a hide dome ribbed with bone spikes and crowned with a skull, a pennant; {_GATE}",
    (Race.ELF, BuildingType.TOWN_HALL): f"a square stone keep under a tall pointed dark blue roof with a crown of leaves growing through its top, a pennant; {_GATE}",
    (Race.DWARF, BuildingType.TOWN_HALL): f"a square granite keep with a flat battlemented top carrying a copper dome with a gold finial, a pennant; {_GATE}",
    (Race.HUMAN, BuildingType.FARM): f"a small plastered cottage with a thatched roof, a door and a blue banner; rows of ripe wheat beside it, {_FARMYARD}",
    (Race.ORC, BuildingType.FARM): f"a small cottage with a hide roof, a door and a blue banner; a muddy fenced pen with three pink pigs beside it, {_FARMYARD}",
    (Race.ELF, BuildingType.FARM): f"a small cottage with a leaf-green roof, a door and a blue banner; an orchard of five small fruit trees with red fruit beside it, {_FARMYARD}",
    (Race.DWARF, BuildingType.FARM): f"a small stone cottage with a stout chimney, a door and a blue banner; wooden kegs stacked by the door, {_FARMYARD}",
    (Race.HUMAN, BuildingType.TOWER): "a tall round stone tower with battlements, arrow slits, a door and a blue banner, two buttresses, a pennant on top",
    (Race.ORC, BuildingType.TOWER): "a timber watchtower: four leaning posts cross-braced with beams carry a platform with a hide roof, bone spikes at its "
                                    "corners and a skull on top, a blue banner on the platform",
    (Race.ELF, BuildingType.TOWER): "a watch tree: a great living trunk carrying a railed wooden platform in its crown, leaves above it, a blue banner on the rail",
    (Race.DWARF, BuildingType.TOWER): "a squat granite tower with a battlemented top carrying a crossbow engine, a door and a blue banner",
    (Race.HUMAN, BuildingType.STABLES): _STABLE.format(beast="a brown horse standing side-on under a blue saddle blanket"),
    (Race.ORC, BuildingType.STABLES): _STABLE.format(beast="a great grey wolf standing side-on, saddled"),
    (Race.ELF, BuildingType.STABLES): _STABLE.format(beast="an antlered stag standing side-on, saddled"),
    (Race.DWARF, BuildingType.STABLES): _STABLE.format(beast="an armoured war bear standing side-on, saddled"),
    (Race.HUMAN, BuildingType.CHURCH): _CHURCH.format(top="a gold cross", window="an amber"),
    (Race.ORC, BuildingType.CHURCH): _CHURCH.format(top="a skull on a pole between bone spikes", window="an orange-lit"),
    (Race.ELF, BuildingType.CHURCH): _CHURCH.format(top="a gold crescent moon", window="an amber"),
    (Race.DWARF, BuildingType.CHURCH): _CHURCH.format(top="a copper hammer", window="an amber"),
}
for _race in Race:  # the same in every race but its materials
    BUILDING_SUBJECTS[(_race, BuildingType.BARRACKS)] = ("a long hall under a grey gable roof with an arched door between two blue banners; a palisade "
                                                         "wing, two round archery targets on posts, a rack of spears, a pennant")
    BUILDING_SUBJECTS[(_race, BuildingType.LUMBER_MILL)] = ("an open saw shed on four posts under an orange-brown gable roof with a blue banner; a stack "
                                                            "of logs with pale end grain, a log deck carrying a great round steel saw blade and a log")
    BUILDING_SUBJECTS[(_race, BuildingType.BLACKSMITH)] = ("a brick furnace house with a tall square chimney and a grey lean-to roof; the furnace mouth "
                                                           "glows with coals, an anvil stands on a stump with a hammer beside it, a wooden quench tub, a blue banner")
    BUILDING_SUBJECTS[(_race, BuildingType.WORKSHOP)] = ("a roofless engineering yard: a plank workbench, a tall timber crane with a stone counterweight, "
                                                         "a siege chassis with iron-rimmed wheels and a raised throwing arm under assembly, a blue banner and a pennant")
#: Where the stand-ins are physically dubious.
BUILDING_FIXES: dict[BuildingType, str] = {
    BuildingType.TOWN_HALL: "the gate towers stand on the ground in front of the keep and the portcullis hangs inside the gate arch",
    BuildingType.FARM: "the crops, animals or kegs stand on the ground beside the cottage",
    BuildingType.BARRACKS: "the targets stand on their posts and the spears lean in the rack",
    BuildingType.TOWER: "the tower stands on its base and the banner hangs on the wall",
    BuildingType.LUMBER_MILL: "the saw blade is mounted upright on the log deck and the logs lie on the ground",
    BuildingType.BLACKSMITH: "the coals glow inside the furnace mouth and the anvil rests on its stump",
    BuildingType.STABLES: "the animal stands on the ground inside the paddock, seen from the side",
    BuildingType.WORKSHOP: "the crane's jib rests on its post and brace, and the siege chassis stands on its wheels",
    BuildingType.CHURCH: "the bell tower is joined to the nave and the ornament on the spire stands upright",
}
#: How each building shows that it is at work (the *active* look).
ACTIVE: dict[BuildingType, str] = {
    BuildingType.TOWN_HALL: "the gate stands open with warm light inside and torches burn on the gate towers",
    BuildingType.FARM: "the door stands open with warm light inside",
    BuildingType.BARRACKS: "the door stands open with warm light inside, a brazier burns in the yard and the targets bristle with arrows",
    BuildingType.TOWER: "a brazier burns on the top",
    BuildingType.LUMBER_MILL: "the saw blade spins in a blur with sawdust flying and fresh planks lie stacked beside it",
    BuildingType.BLACKSMITH: "the furnace roars bright, sparks fly from the anvil and the chimney top glows",
    BuildingType.STABLES: "the stall doors stand open with warm light inside and the animal is saddled and bridled, ready to ride",
    BuildingType.WORKSHOP: "the crane hoists a beam, lanterns burn and tools lie out on the bench",
    BuildingType.CHURCH: "the window and door glow with warm light from inside and the bell swings in its tower",
}
#: How each building shows battle damage (the *damaged* look; the game adds smoke and flames).
DAMAGED: dict[BuildingType, str] = {
    BuildingType.TOWN_HALL: "the keep's roof is broken open, one gate tower has lost its battlements and the banners are torn",
    BuildingType.FARM: "the roof is half caved in, the yard is trampled and the fence is broken",
    BuildingType.BARRACKS: "the roof has a hole with rafters showing, a target is knocked over and the palisade is broken",
    BuildingType.TOWER: "the battlements are shattered on one side and the wall is cracked",
    BuildingType.LUMBER_MILL: "the shed roof is broken and the logs have tumbled",
    BuildingType.BLACKSMITH: "the chimney is broken off short and the lean-to roof has collapsed",
    BuildingType.STABLES: "the roof is broken open and the paddock fence is smashed; the animal is unhurt",
    BuildingType.WORKSHOP: "the crane is broken, the siege chassis has lost a wheel and the bench is overturned",
    BuildingType.CHURCH: "the spire is cracked and leaning, the roof is holed and the window is broken",
}
TEAM_BUILDINGS = ("Blue is the faction colour: it appears exactly where the stand-in has it (banners, pennants, flags, a saddle blanket, "
                  "the hall's roof) and must stay this blue; put no blue anywhere else: roofs are grey, brown, green or red, windows amber, "
                  "water dark green.")
BUILDING_STYLE = ("Re-render every cell as a polished, appealing building sprite in a rich hand-painted fantasy style (Warcraft 2 / Heroes of "
                  "Might and Magic feel): solid masonry and timber with visible texture, volumetric shading, light from the upper left, a soft "
                  "dark shadow on the ground at the foot of the walls. Each building's patch of trodden ground is part of the sprite: keep it "
                  "opaque and the same size and shape. Sprites will be shown at about a third of this size, so keep shapes bold, edges crisp "
                  "and details large.")
PLAUSIBLE_BUILDINGS = ("The reference is a rough low-poly stand-in. Where its construction is physically implausible (a beam floating, a roof "
                       "without support, a prop hanging in the air), draw the plausible version in the same place, at the same size, without "
                       "moving anything.")
LOOK_BRIEF = {
    "active": ("busy at work: windows and doorways glow with warm light from inside, doors and gates stand open, lanterns and torches are lit "
               "and the work of the building is visible. The change must read at a third of this size, so bright warm light in the openings "
               "is the main signal. No people, and no chimney smoke (smoke means damage in this game)."),
    "damaged": ("battle-damaged: roofs broken open with rafters showing, cracked and scorched walls, rubble at the foot of the walls, banners "
                "torn or fallen, dark scorch marks. The building must stay recognisable as the same building with the same footprint and "
                "outline; no flames and no smoke (the game draws them), no people."),
}
LOOK_DETAILS = {"active": ACTIVE, "damaged": DAMAGED}
BUILDING_JUDGE = """You are checking a repainted sprite sheet of buildings against its stand-ins. The image shows, for each row, the
low-poly stand-in buildings above and the painted buildings below, labelled "row N: ..." (naming the building in each column) and "col N".

Work cell by cell, painted row only. Compare each painted building with the stand-in directly above it and with its name. A cell is wrong if:
- it is a different kind of building than the stand-in (a house where a tower is expected), or holds two buildings;
- its footprint, height or silhouette differs clearly from the stand-in (a building that grew a storey, lost its tower, or left its ground patch);
- a major part is missing or added: a tower, dome, spire or roof, the gate, the yard machinery (saw, anvil, crane, siege engine), the animal in the pen;
- blue appears where the stand-in has none (a blue roof, blue water or glass), or a blue banner of the stand-in is missing or another colour;
- it contains people, smoke, flames outside a furnace, or text.
Style, material texture, proportion and detail may differ freely; the painter is allowed to make the building prettier.

Reply with one JSON object and nothing else:
{"cells": [{"row": 0, "col": 0, "banners": 2, "ok": true, "issue": ""}, ...]}
List every cell of the rows shown. Keep issues short and concrete, like "lost the bell tower" or "roof is blue"."""
LOOK_JUDGE = """You are checking a repainted sprite sheet of buildings against the painting it was made from. The image shows, for each row,
the intact painted buildings above and the same buildings repainted in the "{look}" look below, labelled "row N: ..." (naming the building
in each column) and "col N". The {look} look means: {brief}

Work cell by cell, lower row only. A cell is wrong if:
- it is not the same building as above (a different kind, footprint or silhouette beyond what the look changes);
- the look is not visible: the cell looks the same as the intact painting above it;
- it contains people, text, flames or smoke;
- blue appears where the painting above has none.

Reply with one JSON object and nothing else:
{{"cells": [{{"row": 0, "col": 0, "ok": true, "issue": ""}}, ...]}}
List every cell of the rows shown. Keep issues short and concrete."""


def geometry(sheet: restyle.Sheet, what: str) -> str:
    w, h = sheet.size
    grid = f"a single row of {sheet.cols}" if sheet.rows == 1 else f"a grid of {sheet.rows} rows x {sheet.cols} columns of"
    return (f"It is {w}x{h} px: {grid} {sheet.cell[0]}x{sheet.cell[1]} px cells, surrounded by an empty margin, on a flat magenta #FF00FF "
            f"background. Thin dark grey lines mark the cell borders; keep the lines and the margin exactly where they are, and keep each "
            f"{what} in its own cell exactly where it is now.")


def background(sheet: restyle.Sheet) -> str:
    w, h = sheet.size
    return (f"Every cell keeps the flat #FF00FF background with nothing else on it: no gradients, glows, outlines, text, borders "
            f"or extra objects. Output the same {w}x{h} layout.")


@dataclass(frozen=True)
class Unit:
    """One unit of one race in every facing and frame (a carrying peasant is its own subject)."""

    race: Race
    unit: UnitType
    carrying: Resource | None = None
    stage = 0  # painted from the stand-ins
    chunk = (2, 4)  # rows and columns per review image
    judge = restyle.JUDGE_INSTRUCTIONS

    @property
    def name(self) -> str:
        return f"{self.race.value}.{self.unit.value}" + (f".{self.carrying.value}" if self.carrying else "")

    @property
    def description(self) -> str:
        return SUBJECTS[(self.race, self.unit)] + CARRY.get(self.carrying, "")

    @property
    def inventory(self) -> str:
        return INVENTORY[self.unit]

    def frames(self) -> tuple[str, ...]:
        return textures.FRAMES + textures.CHOP_FRAMES if self.unit is UnitType.PEASANT and self.carrying is None else textures.FRAMES

    def build_sheet(self) -> tuple[restyle.Sheet, dict[str, Image.Image]]:
        """The unit's frames laid out facings across, frames down, every frame's feet on the same point."""
        frames = self.frames()
        meshes = {(frame, facing): r3.rotate_z(textures._unit(self.unit, 0, frame, self.carrying, self.race), facing * 45 - 90)
                  for frame in frames for facing in range(textures.FACINGS)}
        bounds = [r3.bounds(m, textures.PROJECTION) for m in meshes.values()]
        half_w = max(max(-b[0], b[2]) for b in bounds)
        top, below = max(-b[1] for b in bounds), max(b[3] for b in bounds)
        cell = (int(2 * half_w * SCALE) + 2 * MARGIN, int((top + below) * SCALE) + 2 * MARGIN)
        origin = (cell[0] / 2, MARGIN + top * SCALE)
        keys = [(textures.unit_key(self.unit, 0, facing, frame, self.carrying, self.race), {"frame": frame, "facing": facing})
                for frame in frames for facing in range(textures.FACINGS)]
        sheet = restyle.Sheet.layout(keys, cols=textures.FACINGS, cell=cell, origin=origin, scale=SCALE)
        images = {key: r3.render(meshes[(tags["frame"], tags["facing"])], textures.PROJECTION, scale=SCALE,
                                 canvas=(cell[0] / SCALE, cell[1] / SCALE), origin=(origin[0] / SCALE, origin[1] / SCALE))
                  for key, tags in keys}
        return sheet, images

    def prompt(self, sheet: restyle.Sheet) -> str:
        rows = ", ".join(FRAME_NAMES[f] for f in dict.fromkeys(c.tags["frame"] for c in sheet.cells))
        return (f"Edit target: the attached sprite sheet of one unit from a 2D real-time strategy game (Warcraft 2 style, 3/4 top-down camera). "
                f"{geometry(sheet, 'figure centred')} Rows, top to bottom: {rows}. Columns, left to right: the unit facing {FACINGS}.\n\n"
                f"The unit is {self.description}.\n\n{STYLE}\n\n"
                f"{PLAUSIBLE} In particular: {RACE_FIXES.get((self.race, self.unit), FIXES[(self.unit, self.carrying)])}.\n\n"
                f"Keep exactly: each figure's position, scale, pose, facing direction, lean, twist, limb and weapon placement, and feet position; "
                f"the poses differ from row to row on purpose (a walk cycle and the phases of a blow), so each row must keep its own pose. "
                f"{background(sheet)}")

    def row_names(self, sheet: restyle.Sheet) -> list[str]:
        carry = f", carrying {self.carrying.value} (no weapon out)" if self.carrying else ""
        return [FRAME_NAMES[f] + carry for f in dict.fromkeys(c.tags["frame"] for c in sheet.cells)]

    def cell_name(self, cell: restyle.Cell) -> str:
        return f"row {cell.row} ({FRAME_NAMES[cell.tags['frame']]}), column {cell.col}"

    def preview(self, sheet: restyle.Sheet, frames: dict[str, Image.Image], out: Path) -> Path:
        """A GIF strip per facing: the walk, then the blow (and the chop), stand-ins above the painting."""
        _, original = self.build_sheet()
        sequence = list(textures.WALK_FRAMES) * 2 + ["stand", "wind", "wind", "strike", "follow", "recover", "stand"]
        if self.unit is UnitType.PEASANT and self.carrying is None:
            sequence += list(textures.CHOP_FRAMES) * 2
        gif_frames = []
        for frame in sequence:
            keys = [sheet.find(frame=frame, facing=f).key for f in range(textures.FACINGS)]
            gif_frames.append(stacked([restyle.strip(original, keys, scale=0.5), restyle.strip(frames, keys, scale=0.5)]))
        path = out / f"{self.name}.gif"
        restyle.gif(gif_frames, path, ms=180)
        return path


@dataclass(frozen=True)
class Buildings:
    """The nine buildings of one race in one look.  The intact look is painted from the low-poly
    stand-ins; the other looks are painted from the installed intact painting."""

    race: Race
    look: str = "intact"
    chunk = (1, 3)

    @property
    def stage(self) -> int:
        return 0 if self.look == "intact" else 1

    @property
    def name(self) -> str:
        return f"{self.race.value}.buildings.{self.look}"

    @property
    def description(self) -> str:
        return f"the buildings of a faction that is {ARCHITECTURE[self.race]}"

    @property
    def inventory(self) -> str:
        return "one building per cell, the one the row label names for that column, on its own patch of ground"

    @property
    def judge(self) -> str:
        return BUILDING_JUDGE if self.look == "intact" else LOOK_JUDGE.format(look=self.look, brief=LOOK_BRIEF[self.look])

    def building_name(self, cell: restyle.Cell) -> str:
        return RACES[self.race].buildings[BuildingType(cell.tags["building"])].name

    def build_sheet(self) -> tuple[restyle.Sheet, dict[str, Image.Image]]:
        keys = [(textures.building_key(bt, 0, self.race, self.look), {"building": bt.value}) for bt in BUILDING_TYPES]
        if self.look != "intact":
            intact = Buildings(self.race)
            if not restyle.file(RESTYLED / intact.name, "png").exists():
                raise FileNotFoundError(f"{self.name} is painted from the intact painting: install {intact.name} first")
            base, painted = restyle.load_frames(RESTYLED / intact.name)
            sheet = restyle.Sheet.layout(keys, cols=base.cols, cell=base.cell, origin=base.origin, scale=base.scale)
            return sheet, {key: painted[textures.building_key(bt, 0, self.race)] for (key, _), bt in zip(keys, BUILDING_TYPES)}
        meshes = {bt: textures._building(bt, 0, self.race) for bt in BUILDING_TYPES}
        bounds = [r3.bounds(m, textures.PROJECTION) for m in meshes.values()]
        half_w = max(max(-b[0], b[2]) for b in bounds)
        top, below = max(-b[1] for b in bounds), max(b[3] for b in bounds)
        cell = (int(2 * half_w * BUILDING_SCALE) + 2 * MARGIN, int((top + below) * BUILDING_SCALE) + 2 * MARGIN)
        origin = (cell[0] / 2, MARGIN + top * BUILDING_SCALE)
        sheet = restyle.Sheet.layout(keys, cols=3, cell=cell, origin=origin, scale=BUILDING_SCALE)
        images = {key: r3.render(meshes[bt], textures.PROJECTION, scale=BUILDING_SCALE, canvas=(cell[0] / BUILDING_SCALE, cell[1] / BUILDING_SCALE),
                                 origin=(origin[0] / BUILDING_SCALE, origin[1] / BUILDING_SCALE))
                  for (key, _), bt in zip(keys, BUILDING_TYPES)}
        return sheet, images

    def prompt(self, sheet: restyle.Sheet) -> str:
        types = [BuildingType(c.tags["building"]) for c in sheet.cells]
        names = [RACES[self.race].buildings[bt].name for bt in types]
        head = (f"Edit target: the attached sprite sheet of {'the nine' if len(types) == 9 else len(types)} buildings of one faction from a 2D "
                f"real-time strategy game (Warcraft 2 style, a 3/4 top-down camera on square ground tiles; each building stands on its own "
                f"square patch of ground that is part of the sprite). {geometry(sheet, 'building')} The cells, row by row and left to right: ")
        if self.look == "intact":
            cells = "; ".join(f"{i + 1}, the {name}: {BUILDING_SUBJECTS[(self.race, bt)]}" for i, (bt, name) in enumerate(zip(types, names)))
            fixes = "; ".join(f"the {name}: {BUILDING_FIXES[bt]}" for bt, name in zip(types, names))
            return (f"{head}{cells}.\n\nThe faction is {ARCHITECTURE[self.race]}. {TEAM_BUILDINGS}\n\n{BUILDING_STYLE}\n\n"
                    f"{PLAUSIBLE_BUILDINGS} In particular: {fixes}.\n\n"
                    f"Keep exactly: each building's position, footprint and ground patch, overall height and silhouette, and where its doors, "
                    f"towers, roofs, banners and yard equipment are. No people; animals only where the stand-in shows them; no smoke, fire or "
                    f"text. {background(sheet)}")
        cells = "; ".join(f"{i + 1}, the {name}" for i, name in enumerate(names))
        details = "; ".join(f"the {name}: {LOOK_DETAILS[self.look][bt]}" for bt, name in zip(types, names))
        return (f"{head}{cells}. The buildings are already painted.\n\n"
                f"Repaint every building in exactly the same place, style, colours and shape, but {LOOK_BRIEF[self.look]} In particular: "
                f"{details}.\n\nBlue is the faction colour and stays exactly where it is; put no blue anywhere else. {background(sheet)}")

    def row_names(self, sheet: restyle.Sheet) -> list[str]:
        return [", ".join(f"col {c.col} {self.building_name(c)}" for c in sheet.cells if c.row == row) for row in range(sheet.rows)]

    def cell_name(self, cell: restyle.Cell) -> str:
        return f"row {cell.row}, column {cell.col} (the {self.building_name(cell)})"

    def preview(self, sheet: restyle.Sheet, frames: dict[str, Image.Image], out: Path) -> Path:
        """One PNG: the originals (stand-ins, or the intact painting for a look), the painting, and the
        painting recoloured to the second player, so a leaked team colour shows."""
        _, original = self.build_sheet()
        keys = [c.key for c in sheet.cells]
        recoloured = {k: restyle.recolor(v, textures.team_color(0), textures.team_color(1)) for k, v in frames.items()}
        path = out / f"{self.name}.png"
        stacked([restyle.strip(original, keys, scale=0.5), restyle.strip(frames, keys, scale=0.5), restyle.strip(recoloured, keys, scale=0.5)]).save(path)
        return path


Subject = Unit | Buildings


def stacked(strips: list[Image.Image]) -> Image.Image:
    out = Image.new("RGBA", (max(s.width for s in strips), sum(s.height for s in strips)))
    y = 0
    for s in strips:
        out.paste(s, (0, y))
        y += s.height
    return out


def selected(args: argparse.Namespace) -> list[Subject]:
    """The subjects the options name: every unit and building look of the race unless ``--units``
    or ``--buildings`` narrows them."""
    race = Race(args.race)
    everything = args.units is None and not args.buildings
    subjects: list[Subject] = []
    if args.units is not None or everything:
        units = list(UnitType) if args.units in (None, "all") else [UnitType(u) for u in args.units.split(",")]
        for unit in units:
            subjects.append(Unit(race, unit))
            if unit is UnitType.PEASANT:
                subjects += [Unit(race, unit, Resource.GOLD), Unit(race, unit, Resource.LUMBER)]
    if args.buildings or everything:
        looks = args.looks.split(",")
        unknown = [look for look in looks if look not in LOOKS]
        if unknown:
            raise SystemExit(f"unknown look {unknown[0]!r}; the looks are {', '.join(LOOKS)}")
        subjects += [Buildings(race, look) for look in looks]
    return subjects


def cmd_dump(args: argparse.Namespace, subjects: list[Subject]) -> None:
    args.dir.mkdir(parents=True, exist_ok=True)
    for subject in subjects:
        sheet, images = subject.build_sheet()
        sheet.save(args.dir / subject.name, images)
        (args.dir / f"{subject.name}.prompt.txt").write_text(subject.prompt(sheet))
        print(f"{subject.name}: {sheet.size[0]}x{sheet.size[1]}, {len(sheet.cells)} cells of {sheet.cell[0]}x{sheet.cell[1]}")


def cmd_render(args: argparse.Namespace, subjects: list[Subject]) -> None:
    def one(name: str) -> str:
        out = args.dir / name / f"{args.provider}.png"
        if out.exists() and not args.force:
            return f"{name}: kept {out.name}"
        text = (args.dir / f"{name}.prompt.txt").read_text()
        if args.provider == "codex":
            restyle.render_with_codex(args.dir / f"{name}.png", text, out)
        else:
            usage = restyle.render_with_openrouter(args.dir / f"{name}.png", text, out, model=args.model, api_key=restyle.openrouter_api_key())
            (args.dir / name / "usage.json").write_text(json.dumps(usage, indent=1))
        return f"{name}: wrote {out}"

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for line in pool.map(one, [subject.name for subject in subjects]):
            print(line)


def cmd_cut(args: argparse.Namespace, subjects: list[Subject]) -> None:
    RESTYLED.mkdir(parents=True, exist_ok=True)
    for subject in subjects:
        name = subject.name
        rendered = args.dir / name / f"{args.provider}.png"
        if not rendered.exists():
            print(f"{name}: no {rendered.name} yet")
            continue
        sheet = restyle.Sheet.load(args.dir / name)
        result = restyle.cut(sheet, Image.open(rendered), Image.open(args.dir / f"{name}.png"))
        flagged = result.flagged
        print(f"{name}: scale {result.registration.scale:.2f} shift ({result.registration.dx:.0f}, {result.registration.dy:.0f}), "
              f"{len(flagged)} of {len(result.report)} cells flagged")
        for r in flagged:
            print(f"   {r.key}: coverage {r.coverage:.3f} vs {r.original_coverage:.3f}, drift {r.drift:.0f}px, feet {r.feet_drift:+.0f}px, edge {r.touches_edge}")
        if len(flagged) > args.tolerate:
            print(f"   rejected (more than {args.tolerate} flagged); re-render or raise --tolerate")
            continue
        restyle.save_frames(result, sheet, RESTYLED / name)
        print(f"   installed {RESTYLED / name}.png")


def cmd_preview(args: argparse.Namespace, subjects: list[Subject]) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    for subject in subjects:
        if not restyle.file(RESTYLED / subject.name, "png").exists():
            continue
        sheet, frames = restyle.load_frames(RESTYLED / subject.name)
        print(f"{subject.name}: {subject.preview(sheet, frames, args.out)}")


def complaints_text(verdicts: list[dict], sheet: restyle.Sheet, subject: Subject) -> str:
    cells = {(c.row, c.col): c for c in sheet.cells}
    return "; ".join(f"{subject.cell_name(cells[(v['row'], v['col'])])}: {v['issue']}" for v in questioned(verdicts))


def check_one(args: argparse.Namespace, subject: Subject, sheets: Path) -> list[dict]:
    """Judge the sheet of one subject in *sheets* against its originals; writes DIR/name/check.json
    and returns the verdicts (empty when there is no sheet)."""
    name = subject.name
    if not restyle.file(sheets / name, "png").exists():
        print(f"{name}: no sheet in {sheets}")
        return []
    sheet, painted = restyle.load_frames(sheets / name)
    _, originals = subject.build_sheet()
    names = subject.row_names(sheet)
    (args.dir / name).mkdir(parents=True, exist_ok=True)
    chunk_rows, chunk_cols = subject.chunk
    chunks = [(list(range(r, min(r + chunk_rows, sheet.rows))), list(range(c, min(c + chunk_cols, sheet.cols))))
              for r in range(0, sheet.rows, chunk_rows) for c in range(0, sheet.cols, chunk_cols)]

    def judge(chunk: tuple[list[int], list[int]]) -> list[dict]:
        rows, cols = chunk
        review_png = args.dir / name / f"review-{rows[0]}-{cols[0]}.png"
        restyle.review_image(sheet, originals, painted, rows=rows, cols=cols, row_names=names).convert("RGB").save(review_png)
        return restyle.judge_with_codex(review_png, subject.description, sheet, rows=rows, cols=cols, inventory=subject.inventory,
                                        instructions=subject.judge)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        verdicts = [v for chunk in pool.map(judge, chunks) for v in chunk]
    (args.dir / name / "check.json").write_text(json.dumps(verdicts, indent=1))
    bad = questioned(verdicts)
    print(f"{name}: {len(bad)} of {len(verdicts)} cells questioned" + ("" if not bad else ":"))
    for v in bad:
        print(f"   row {v['row']} col {v['col']}: {v['issue']}")
    return verdicts


def questioned(verdicts: list[dict]) -> list[dict]:
    return [v for v in verdicts if not v.get("ok", True)]


def cmd_check(args: argparse.Namespace, subjects: list[Subject]) -> None:
    """Judge every selected sheet.  With --fix, re-render a questioned sheet with the complaints
    in its prompt and install the candidate only when the judge questions fewer of its cells;
    the best of the rounds ends up installed.  With --patch, re-render only the questioned rows."""
    for subject in subjects:
        name = subject.name
        verdicts = check_one(args, subject, args.sheets or RESTYLED)
        best = len(questioned(verdicts)) if verdicts else None
        if best is None or best == 0 or not (args.fix or args.patch):
            continue
        if best > args.max_bad and not args.patch:
            print(f"   {best} questioned cells is more than --max-bad {args.max_bad}: not re-rendering, look at the review images")
            continue
        sheet = restyle.Sheet.load(args.dir / name)
        prompt_text = (args.dir / f"{name}.prompt.txt").read_text()
        for attempt in range(1, (args.rounds if args.fix else 0) + 1):
            text = prompt_text + f"\n\nA previous attempt got these cells wrong; do not repeat them: {complaints_text(verdicts, sheet, subject)}."
            print(f"   round {attempt}: re-rendering with the complaints in the prompt")
            candidate = args.dir / name / f"candidate-{attempt}"
            candidate.mkdir(parents=True, exist_ok=True)
            restyle.render_with_codex(args.dir / f"{name}.png", text, candidate / f"{args.provider}.png")
            result = restyle.cut(sheet, Image.open(candidate / f"{args.provider}.png"), Image.open(args.dir / f"{name}.png"))
            if len(result.flagged) > args.tolerate:
                print(f"   the candidate failed the geometry checks ({len(result.flagged)} flagged)")
                continue
            restyle.save_frames(result, sheet, candidate / name)
            candidate_verdicts = check_one(args, subject, candidate)
            count = len(questioned(candidate_verdicts))
            if count < best:
                restyle.save_frames(result, sheet, RESTYLED / name)
                best, verdicts = count, candidate_verdicts
                print(f"   installed the candidate ({count} questioned)")
            else:
                print(f"   kept the installed sheet ({best} questioned) over the candidate ({count})")
            if best == 0:
                break
        if args.patch and best:
            for attempt in range(1, args.rounds + 1):
                print(f"   patch round {attempt}: re-rendering the rows with questioned cells")
                if not patch_cells(args, subject, verdicts):
                    break
                verdicts = check_one(args, subject, RESTYLED)
                best = len(questioned(verdicts))
                if best == 0:
                    break


def patch_cells(args: argparse.Namespace, subject: Subject, verdicts: list[dict]) -> int:
    """Re-render only the rows that hold questioned cells, as one-row sheets, judge them, and
    splice in the questioned cells that come back clean.  Returns how many cells were replaced."""
    name = subject.name
    sheet, painted = restyle.load_frames(RESTYLED / name)
    _, originals = subject.build_sheet()
    replaced = 0
    for row in sorted({v["row"] for v in questioned(verdicts)}):
        cells = [c for c in sheet.cells if c.row == row]
        row_sheet = restyle.Sheet.layout([(c.key, dict(c.tags)) for c in cells], cols=sheet.cols, cell=sheet.cell, origin=sheet.origin, scale=sheet.scale)
        folder = args.dir / name / f"patch-row{row}"
        folder.mkdir(parents=True, exist_ok=True)
        row_sheet.save(folder / "row", {c.key: originals[c.key] for c in cells})
        wanted = [v for v in questioned(verdicts) if v["row"] == row]
        text = subject.prompt(row_sheet)
        text += "\n\nIn a previous painting of this row these cells were wrong; do not repeat it: " + "; ".join(f"column {v['col']}: {v['issue']}" for v in wanted) + "."
        restyle.render_with_codex(folder / "row.png", text, folder / f"{args.provider}.png")
        result = restyle.cut(row_sheet, Image.open(folder / f"{args.provider}.png"), Image.open(folder / "row.png"))
        if len(result.flagged) > args.tolerate:
            print(f"   row {row}: the patch failed the geometry checks ({len(result.flagged)} flagged)")
            continue
        names = subject.row_names(row_sheet)
        clean: list[int] = []
        for start in range(0, sheet.cols, subject.chunk[1]):
            cols = list(range(start, min(start + subject.chunk[1], sheet.cols)))
            restyle.review_image(row_sheet, originals, result.frames, rows=[0], cols=cols, row_names=names).convert("RGB").save(folder / f"review-{start}.png")
            row_verdicts = restyle.judge_with_codex(folder / f"review-{start}.png", subject.description, row_sheet, rows=[0], cols=cols,
                                                    inventory=subject.inventory, instructions=subject.judge)
            clean += [v["col"] for v in row_verdicts if v.get("ok", True)]
        for v in wanted:
            key = next(c.key for c in cells if c.col == v["col"])
            if v["col"] in clean:
                painted[key] = result.frames[key]
                replaced += 1
                print(f"   row {row} col {v['col']}: patched")
            else:
                print(f"   row {row} col {v['col']}: the patch was questioned too; kept")
    if replaced:
        merged = restyle.Cut(painted, restyle.Registration(1.0, 0.0, 0.0), ())
        restyle.save_frames(merged, sheet, RESTYLED / name)
    return replaced


def cmd_refresh(args: argparse.Namespace, subjects: list[Subject]) -> None:
    """Dump, render, cut and preview in one go: the whole procedure for the selected subjects,
    the looks painted from an intact painting after the intact paintings are installed."""
    for stage in sorted({subject.stage for subject in subjects}):
        staged = [subject for subject in subjects if subject.stage == stage]
        cmd_dump(args, staged)
        cmd_render(args, staged)
        cmd_cut(args, staged)
    args.out = args.dir / "previews"
    cmd_preview(args, subjects)


def cmd_showcase(args: argparse.Namespace, subjects: list[Subject]) -> None:
    """A scripted skirmish through the real renderer, saved as a GIF: two armies (``--races``,
    the same race twice shows the recolouring) attack-move into each other while peasants
    chop the wood behind the line.  The display must be awake."""
    from saga2d import Game, fonts
    from warband.view import to_world
    from warband.rules import Terrain
    from warband.scene import new_game
    from warband.style import build_theme

    game = Game("Warband showcase", resolution=(960, 600), backend="pyglet", visible=False, theme=build_theme())
    try:
        fonts.load(game)
        races = [Race(r) for r in args.races.split(",")]
        scene = new_game(seed=3, races=races, settings={"tutorial": False, "edge_scroll": False})
        game.push(scene)
        world = scene.world
        for _ in range(160):  # the title banner passes
            game.tick(1 / 30)
        hall = world.player_buildings(0)[0]
        hx, hy = hall.center

        def open_ground(x0: int, y0: int, w: int, h: int) -> bool:
            return all(world.in_bounds((x, y)) and world.terrain_at((x, y)) is Terrain.GRASS and world.building_at((x, y)) is None
                       for x in range(x0, x0 + w) for y in range(y0, y0 + h))

        field = min(((x, y) for x in range(world.width - 12) for y in range(world.height - 8) if open_ground(x, y, 12, 8)),
                    key=lambda p: (p[0] - hx) ** 2 + (p[1] - hy) ** 2)  # the nearest meadow that fits two lines
        cx, cy = field[0] + 1.5, field[1] + 1.0
        line = [UnitType.FOOTMAN, UnitType.KNIGHT, UnitType.ARCHER, UnitType.FOOTMAN, UnitType.CLERIC, UnitType.SCOUT, UnitType.CATAPULT]
        north = [world.spawn_unit(0, unit, (cx + i * 1.3, cy)) for i, unit in enumerate(line)]
        south = [world.spawn_unit(1, unit, (cx + i * 1.3, cy + 6)) for i, unit in enumerate(line)]
        world.reveal_all(0)
        world.attack_move([u.id for u in north], (cx + 4, cy + 6))
        world.attack_move([u.id for u in south], (cx + 4, cy))
        trees = [(x, y) for x in range(int(cx) - 10, int(cx) + 16) for y in range(int(cy) - 8, int(cy) + 14)
                 if world.in_bounds((x, y)) and world.terrain_at((x, y)) is Terrain.TREES]
        for peasant in world.player_units(0):
            if peasant.type is UnitType.PEASANT and trees:
                nearest = min(trees, key=lambda t: (t[0] - peasant.x) ** 2 + (t[1] - peasant.y) ** 2)
                world.harvest([peasant.id], nearest)
        scene.camera.zoom = args.zoom
        scene.camera.center_on(*to_world((cx + 4, cy + 4.5)))
        frames = []
        for tick in range(int(args.seconds * 30)):
            game.tick(1 / 30)
            if tick % 2 == 0:
                frame = game.backend.capture_frame().convert("RGB")
                frames.append(frame.resize((frame.size[0] // 2, frame.size[1] // 2), Image.LANCZOS) if frame.size[0] > 1000 else frame)
        frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=66, loop=0)
        print(f"wrote {args.out}: {len(frames)} frames of {frames[0].size[0]}x{frames[0].size[1]}")
    finally:
        game.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--race", default="human")
    parser.add_argument("--units", default=None, help="comma-separated unit types, or 'all' (default with no --buildings: all)")
    parser.add_argument("--buildings", action="store_true", help="the race's building sheets (default with no --units: yes)")
    parser.add_argument("--looks", default=",".join(LOOKS), help=f"comma-separated building looks (default: {','.join(LOOKS)})")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("dump"); p.add_argument("dir", type=Path); p.set_defaults(run=cmd_dump)
    p = sub.add_parser("render"); p.add_argument("dir", type=Path); p.add_argument("--provider", default="codex", choices=["codex", "openrouter"])
    p.add_argument("--model", default="google/gemini-3.1-flash-image"); p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--force", action="store_true"); p.set_defaults(run=cmd_render)
    p = sub.add_parser("cut"); p.add_argument("dir", type=Path); p.add_argument("--provider", default="codex")
    p.add_argument("--tolerate", type=int, default=2, help="flagged cells allowed before a sheet is rejected"); p.set_defaults(run=cmd_cut)
    p = sub.add_parser("preview"); p.add_argument("dir", type=Path); p.add_argument("out", type=Path); p.set_defaults(run=cmd_preview)
    p = sub.add_parser("check"); p.add_argument("dir", type=Path); p.add_argument("--fix", action="store_true", help="re-render questioned sheets with the complaints in the prompt")
    p.add_argument("--patch", action="store_true", help="re-render only the rows with questioned cells and splice in the clean ones")
    p.add_argument("--rounds", type=int, default=3); p.add_argument("--max-bad", type=int, default=24, help="more questioned cells than this means the stand-in needs a look, not a re-roll (--patch ignores it)")
    p.add_argument("--provider", default="codex"); p.add_argument("--tolerate", type=int, default=2); p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--sheets", type=Path, default=None, help="judge sheets in this folder instead of the installed ones")
    p.set_defaults(run=cmd_check)
    p = sub.add_parser("refresh"); p.add_argument("dir", type=Path); p.add_argument("--provider", default="codex", choices=["codex", "openrouter"])
    p.add_argument("--model", default="google/gemini-3.1-flash-image"); p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--force", action="store_true"); p.add_argument("--tolerate", type=int, default=2); p.set_defaults(run=cmd_refresh)
    p = sub.add_parser("showcase"); p.add_argument("out", type=Path); p.add_argument("--seconds", type=float, default=6.0)
    p.add_argument("--zoom", type=float, default=1.5); p.add_argument("--races", default="human,human", help="the two players' races")
    p.set_defaults(run=cmd_showcase)
    args = parser.parse_args()
    args.run(args, selected(args))


if __name__ == "__main__":
    main()
