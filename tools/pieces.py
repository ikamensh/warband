"""Generate Warband's sound pieces with Stable Audio 3: combat impacts, unit deaths, presences and building wreckage, and files to listen to them.

    uv run python tools/pieces.py refresh              # generate what is missing or changed; manifests updated
    uv run python tools/pieces.py sampler DIR          # every folder's pieces back to back, one WAV each, with label lists
    uv run python tools/pieces.py cues DIR [--families catapult,wolf]   # each family's mixed cues: WAV, spectrogram PNG, stats

Needs STABLE_AUDIO_MLX (see ../sagaforge/docs/foley.md).  The prompts below are the source of
truth; each folder's manifest records what was actually generated.  A rejected piece (silent, or
a click) is reported at the end: give it a new seed here and run refresh again.  After a refresh,
bump ``SOUND_VERSION`` in warband/audio/sound.py so the cached cues are mixed again, and run the tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sagaforge.foley import BuildError, Piece, StableAudioMLX, build, sampler  # noqa: E402
from sagaforge.synth import SAMPLE_RATE, write_wav  # noqa: E402
from warband.audio.bodies import FAMILIES, RACE_FAMILIES  # noqa: E402
from warband.audio.pieces import ROOT  # noqa: E402
from warband.sim.rules import Race  # noqa: E402

# The game modules (warband.audio.combat_sound, deaths, wreckage) expect these folders and names; they are
# spelled out here rather than imported because those modules refuse to load without their pieces, and this
# is the tool that makes them.  They are the one place the stage names live: the modules name their own
# stages where they place them, and each kept a STAGES nothing read, which looked like this table's source.
# The sound families are the exception: warband.audio.bodies reads no file, so their stages are its FAMILIES'.
DEATHS, DEATH_STAGES, PRESENCE = "deaths", ("weapon", "body", "settle"), "presence"
WRECKAGE, WRECK_STAGES, MATERIALS = "wreckage", ("crack", "collapse", "debris"), ("wood", "stone")
IMPACTS, WEAPONS, TARGETS, IMPACT_TAKES = "impacts", ("sword", "axe", "spear", "lance", "arrow", "stone", "hammer"), ("flesh", "armor", "wood", "stone"), 3

LICENSE = "Stability AI Community License: outputs are owned by the licensee and free to commercialise; training data licensed by Stability AI"
CRY_STYLE = "medieval fantasy battlefield, close, dry, no music, no reverb"
STAGE_STYLE = "one short sound then silence, close, dry, no music, no reverb, no voice"

#: One sentence per take: the same prompt with different seeds gives near-identical takes.
CRIES = {
    Race.HUMAN: ["a human soldier's short death cry, a pained shout cut off",
                 "a man screams briefly as he is struck down, then goes silent",
                 "a wounded soldier's choked groan, falling",
                 "a soldier's last gasp, breath knocked out, short"],
    Race.ORC: ["a large man with a deep gravelly voice cries out in pain and dies, a short groan cut off",
               "a deep-voiced brute gasps, chokes and goes silent, dying, short",
               "a big warrior's guttural grunt of agony trailing into a death rattle",
               "a deep hoarse shout of pain, then a last breath, short"],
    Race.ELF: ["an elf's sharp gasp and a fading sigh, high clear voice",
               "an elven warrior cries out briefly, a high pained note",
               "a soft elf's dying breath, a whispered exhale",
               "an elf's short shriek, cut off"],
    Race.DWARF: ["a dwarf warrior's gruff death grunt, deep chesty voice",
                 "a stocky dwarf roars in pain and falls, short",
                 "a gruff bearded man's cough and groan, dying",
                 "a dwarf's angry final shout, brief and hoarse"],
}
#: The fall, one prompt per stage and race; two takes each from different seeds.
FALLS = {
    "weapon": {Race.HUMAN: "a steel sword dropped onto stone, one clatter",
               Race.ORC: "a heavy iron axe dropped onto packed dirt, one thud with a metallic clink",
               Race.ELF: "a wooden bow dropped onto grass, a light clatter",
               Race.DWARF: "a heavy war hammer dropped onto rock, one heavy clank"},
    "body": {Race.HUMAN: "a man in chainmail collapses onto the ground, one heavy body thud",
             Race.ORC: "a very large heavy body slumps onto packed dirt, one deep thud",
             Race.ELF: "a light body crumples onto leaves, a soft thud and cloth rustle",
             Race.DWARF: "a stocky armored body falls onto stone, one dull heavy thud"},
    "settle": {Race.HUMAN: "chainmail rattles briefly and settles",
               Race.ORC: "a wooden shield rolls once and settles on dirt",
               Race.ELF: "a quiver of arrows scatters onto the ground",
               Race.DWARF: "a steel helmet drops and rolls briefly on stone"},
}
STAGE_TAKES = 2
#: Seeds that produced a rejected piece, and the seed that replaced them.
RESEEDED = {"elf_cry_2": 1122, "human_settle_1": 4311,
            "lance_flesh_1": 7351, "arrow_flesh_1": 7451}  # the first seeds gave bright hits on flesh, no contrast with armour


# -- The bodies that are not a race's soldiers: machines and creatures --------------------------------------

CREATURE_STYLE = "fantasy creature, close, dry, no music, no reverb, no human voice, no speech"
MACHINE_STYLE = "medieval, close, dry, no music, no reverb, no voice"
BEAST_STYLE = "close, dry, no music, no reverb, no voice"
RUNE_STYLE = "fantasy magic sound effect, close, no melody, no music, no voice"
#: Per family and stage (the stage names are warband.audio.bodies.FAMILIES', its death's and its spent end's): how the
#: clip is cut, the seconds asked for, the style, and one prompt per take.  The first stage has three takes, so three
#: cues, and so has a stage long enough to be most of the cue (a crash, a whistle): with two, cues 0 and 2 would sound
#: alike; the rest have two.  A family's stages are seeded in the order they stand here, so a stage added later goes
#: at the end, where it reseeds none of the others.
BODY_DEATHS = {
    "catapult": {
        "splinter": ("impact", 1.6, STAGE_STYLE, ["a heavy wooden siege engine's beam cracks and splinters, one loud splintering crack",
                                                  "thick oak timbers split apart with a sharp splintering snap",
                                                  "a wooden catapult arm breaks with a loud crack of splintering wood"]),
        "snap": ("impact", 1.6, STAGE_STYLE, ["a thick taut rope snaps with a sharp twang",
                                              "a heavy hemp rope under tension breaks with a whip-like snap"]),
        "crash": ("collapse", 3.0, MACHINE_STYLE, ["a large wooden catapult frame collapses, heavy timbers crashing to the ground, a wheel clattering",
                                                   "a heavy wooden frame slams down onto the ground at once, one big crash of breaking timber, then planks clattering",
                                                   "a wooden war machine smashes to the ground with one loud crash of splintering beams and a rolling wheel"]),
    },
    "flying_machine": {
        "sputter": ("impact", 2.0, MACHINE_STYLE, ["a small clockwork engine coughs, sputters and dies, its whirring rotor slowing down",
                                                   "a steam-driven propeller engine chokes and sputters out with a hiss",
                                                   "flapping canvas wings and a rattling motor falter and stall"]),
        "whistle": ("voice", 2.0, MACHINE_STYLE, ["a descending whistle of a heavy object falling fast through the air",
                                                  "a falling whine dropping in pitch as something plummets from the sky",
                                                  "a high whistle falling in pitch, something dropping out of the sky fast"]),
        # The first wording ("crashes into the ground, wood splintering...") built up for a second before its loudest
        # moment; asking for one heavy crash first puts the blow where the body lands.
        "crash": ("collapse", 3.0, MACHINE_STYLE, ["a small flying machine of wood and iron slams into the ground with one heavy crash, then metal parts clatter",
                                                   "one heavy crashing impact of timber and iron hitting the ground, splintering wood and a clanging metal rattle",
                                                   "a wooden contraption smashes into the earth with a loud crunch and bang, metal pieces bouncing"]),
    },
    "wolf": {
        "yelp": ("voice", 2.0, CREATURE_STYLE, ["a large wolf yelps in pain and whimpers, dying",
                                                "a big dog's sharp pained yelp, cut short",
                                                "a wounded wolf's high whine trailing off into a last breath"]),
        "body": ("impact", 1.6, STAGE_STYLE, ["a large dog's body drops onto dirt, one soft heavy thud",
                                              "a furry animal body slumps onto grass, one dull thud"]),
    },
    "spider": {
        "screech": ("voice", 2.0, CREATURE_STYLE, ["a giant insect's shrill dying screech, chittering",
                                                   "a monstrous spider's high rasping hiss and squeal of pain",
                                                   "a huge bug's clicking chitter rising to a screech, then silence"]),
        # "a beetle shell crunches wetly" came back as a second of bright hiss; the body falling is what gives it weight.
        "crunch": ("impact", 1.6, STAGE_STYLE, ["a giant spider's body slumps onto dirt with a wet heavy squelch and a crunch",
                                                "one heavy wet splat and crunch of a big insect falling dead onto dirt"]),
    },
    "troll": {
        "bellow": ("voice", 2.0, CREATURE_STYLE, ["a huge beast's deep bellowing roar of pain, dying",
                                                  "a giant brute's very deep guttural groan of agony, fading",
                                                  "an enormous creature's low rumbling howl, cut off"]),
        "fall": ("impact", 1.6, STAGE_STYLE, ["a huge heavy body crashes down onto the ground, one very deep thud",
                                              "a giant slumps and falls hard onto packed earth, one massive heavy impact"]),
    },
    "golem": {
        # Without "heavy" and "deep" the stone came back as sparse bright clicks, no weight below 500 Hz.
        "grind": ("collapse", 3.0, MACHINE_STYLE, ["a giant stone statue cracks and crumbles, heavy blocks grinding apart with a deep rumble",
                                                   "huge boulders grind together and split with a heavy crunching crack and a low rumble",
                                                   "a stone giant crashes apart, massive rocks cracking and grinding with a deep heavy rumble"]),
        "rubble": ("collapse", 3.0, MACHINE_STYLE, ["heavy stone rubble tumbles down onto the ground with a deep thud and settles, dust",
                                                    "heavy rocks tumble onto a pile with a deep rumbling thud, then small stones settle"]),
    },
    # Each race's own unit (WB-068).
    "gryphon": {
        "screech": ("voice", 2.0, CREATURE_STYLE, ["a giant eagle's piercing screech of pain, dying",
                                                   "a huge bird of prey shrieks shrilly and falters, a harsh dying cry",
                                                   "a great raptor's hoarse scream, cut short"]),
        "wings": ("impact", 1.6, BEAST_STYLE, ["huge feathered wings flap wildly and falter, heavy feathers beating the air",
                                               "big wings beat frantically a few times, a rush of feathers"]),
        "fall": ("impact", 1.6, STAGE_STYLE, ["a huge winged beast and its armoured rider crash onto the ground, one heavy thud and a rattle of armour",
                                              "a heavy body falls from the sky and slams into the earth, one deep thud"]),
    },
    "sapper": {  # its spent end, the keg going up, then its death when it is shot down on its way
        "fuse": ("impact", 1.6, STAGE_STYLE, ["a short lit fuse fizzes and hisses, crackling sparks",
                                              "a burning fuse sputters with a sharp sizzle",
                                              "a black powder fuse hisses and spits sparks"]),
        "blast": ("collapse", 3.0, MACHINE_STYLE, ["a powder keg explodes with a huge deep boom and a blast of splintering wood",
                                                   "a keg of gunpowder explodes with one deep thunderous boom that shakes the ground",
                                                   "a big gunpowder explosion, a sharp crack and a deep booming blast"]),
        "debris": ("collapse", 3.0, MACHINE_STYLE, ["dirt, stones and wooden splinters rain down and patter onto the ground after an explosion",
                                                    "debris falls and scatters, pebbles and wooden shards clattering down"]),
        # A goblin, not an orc: small, with the high voice its giggle has (the orc cries are a deep-voiced brute's).
        "cry": ("voice", 2.0, CRY_STYLE, ["a small goblin's shrill squeal of pain, cut short",
                                          "a little goblin shrieks in pain and falls silent, a high raspy cry",
                                          "a small creature's high screechy yelp of agony, then a gasp"]),
        # A small body, and the keg it carried knocking down beside it.
        "fall": ("impact", 1.6, STAGE_STYLE, ["a small body and a wooden keg drop onto packed dirt, a soft thud and a hollow wooden knock",
                                              "a little body slumps onto dirt as a small barrel thumps down beside it"]),
        # The fuse goes out: no boom follows.
        "fizzle": ("impact", 1.6, STAGE_STYLE, ["a burning fuse sputters weakly and goes out, a last short hiss dying away",
                                                "a lit fuse fizzles out in the dirt, a feeble sputter and a soft pop"]),
    },
    "treant": {
        "split": ("collapse", 3.0, MACHINE_STYLE, ["a huge old tree trunk creaks loudly and splits apart, wood cracking and splintering",
                                                   "a giant living tree groans and its trunk cracks open with a deep splintering crack",
                                                   "a massive oak creaks under strain and breaks with a loud crack of wood"]),
        "fall": ("collapse", 3.0, MACHINE_STYLE, ["a huge tree trunk crashes down onto the ground with one deep heavy thud, branches snapping",
                                                  "a great tree trunk slams into the earth with one deep booming thud"]),
        # Kept to one settling (the impact cut): a collapse's two and a half seconds of rustle made the cue too long.
        "leaves": ("impact", 1.6, MACHINE_STYLE, ["leaves and twigs rustle and settle after a tree falls, a soft rustling",
                                                    "dry leaves shower down and settle with a gentle rustle"]),
    },
    # Carved and bound where the wild golem is rough rock: dressed blocks and brass, and the hum of its runes going out.
    "rune_golem": {
        "grind": ("collapse", 3.0, MACHINE_STYLE, ["heavy carved stone blocks crack apart and grind with a deep rumble, a brass band snapping with a clang",
                                                   "a great statue of dressed stone breaks, massive blocks grinding and cracking with a deep heavy rumble",
                                                   "a stone giant bound in metal bands shatters, heavy rock cracking and a metal clang, a low rumble"]),
        "rubble": ("collapse", 3.0, MACHINE_STYLE, ["carved stone blocks thud down onto a pile one after another and settle",
                                                    "heavy stone blocks tumble with deep thuds, then small chips settle"]),
        "runes": ("voice", 3.0, RUNE_STYLE, ["a deep magical humming drone slowly fading into silence",
                                             "a glowing crystal's resonant hum dies away, a fading magical ring"]),
    },
}
#: Per family with a presence: its cut, seconds, style and three prompts (the kind is the family's ``presence``).
PRESENCES = {
    "catapult": ("impact", 2.0, MACHINE_STYLE, ["a heavy wooden siege engine creaks and its winch ratchets, wooden gears clicking",
                                                "old timber creaking under strain and a rope winch cranking",
                                                "a wooden cart's axle groans and a crank ratchets a few clicks"]),
    "flying_machine": ("impact", 2.0, MACHINE_STYLE, ["a small propeller engine whirs up briefly",
                                                      "a steam rotor spins up with a chuffing mechanical whirr",
                                                      "large canvas wings beat twice on a creaking wooden frame"]),
    "wolf": ("voice", 2.0, CREATURE_STYLE, ["a wolf's low menacing snarl and growl",
                                            "an angry big dog barks once and snarls",
                                            "a wolf growls deeply, baring its teeth"]),
    "spider": ("voice", 2.0, CREATURE_STYLE, ["a giant spider's sharp threatening hiss",
                                              "a huge insect's angry clicking chitter and hiss",
                                              "a monstrous bug rasps and hisses"]),
    "troll": ("voice", 2.0, CREATURE_STYLE, ["a huge brute's deep angry roar",
                                             "a giant beast bellows a furious war cry",
                                             "an enormous creature's thunderous low roar"]),
    "golem": ("collapse", 3.0, MACHINE_STYLE, ["heavy stone grinding and rumbling as a rock giant stirs",
                                               "a deep stony rumble of boulders shifting",
                                               "large rocks scrape and grind together with a low rumble"]),
    "gryphon": ("voice", 2.0, CREATURE_STYLE, ["a great eagle's fierce screech",
                                               "a gryphon's shrill cry, a raptor's call",
                                               "a large hawk's piercing scream, once"]),
    # A fuse fizzing, and once a goblin's giggle: the cackle is a voice, so the style forbids no voice.
    "sapper": ("voice", 1.6, "close, dry, no music, no reverb", ["a match is struck and a short fuse catches, a fizzing sputter",  # crackling sparks were a click, a steady hiss all above 9 kHz
                                                                 "a small mischievous goblin giggles, a short high cackle",
                                                                 "a short fuse sizzles and pops, sparks crackling"]),
    "treant": ("impact", 2.0, MACHINE_STYLE, ["old wooden timbers creak slowly under strain, one long low creak",  # "creaks and groans as it bends" came back as a rustle
                                              "a giant tree's branches creak and its leaves rustle",
                                              "a deep wooden groan of a huge tree swaying"]),
    "rune_golem": ("voice", 2.0, RUNE_STYLE, ["a deep magical hum pulses and swells briefly",
                                              "a low resonant arcane drone swells and fades",
                                              "a heavy stone thrum and a glowing magical hum"]),
}
BODIES = [name for name in FAMILIES if name not in RACE_FAMILIES]


def body_pieces() -> list[Piece]:
    wanted = []
    for f, family in enumerate(BODIES):
        prompts, body = BODY_DEATHS[family], FAMILIES[family]
        if set(prompts) != {stage.kind for stage in body.death + body.spent}:
            raise ValueError(f"{family}: prompts for {list(prompts)}, but its ends place {[stage.kind for stage in body.death + body.spent]}")
        for s, (stage, (shape, seconds, style, takes)) in enumerate(prompts.items()):
            for i, prompt in enumerate(takes):
                name = f"{family}_{stage}_{i}"
                wanted.append(Piece(name, f"{prompt}, {style}", seconds=seconds, seed=RESEEDED.get(name, 20000 + 1000 * f + 100 * s + i),
                                    shape=shape, peak=0.72 if shape == "voice" else 0.8))
    return wanted


def presence_pieces() -> list[Piece]:
    wanted = []
    for f, family in enumerate(BODIES):
        kind = FAMILIES[family].presence
        if kind is None:
            continue
        shape, seconds, style, takes = PRESENCES[family]
        for i, prompt in enumerate(takes):
            name = f"{family}_{kind}_{i}"
            wanted.append(Piece(name, f"{prompt}, {style}", seconds=seconds, seed=RESEEDED.get(name, 30000 + 100 * f + i),
                                shape=shape, peak=0.72 if shape == "voice" else 0.8))
    return wanted


def death_pieces() -> list[Piece]:
    wanted = []
    for r, race in enumerate(Race):
        for i, prompt in enumerate(CRIES[race]):
            name = f"{race.value}_cry_{i}"
            wanted.append(Piece(name, f"{prompt}, {CRY_STYLE}", seconds=2.0, seed=RESEEDED.get(name, 1000 + 10 * r + i), shape="voice", peak=0.72))
        for s, stage in enumerate(DEATH_STAGES):
            for i in range(STAGE_TAKES):
                name = f"{race.value}_{stage}_{i}"
                wanted.append(Piece(name, f"{FALLS[stage][race]}, {STAGE_STYLE}", seconds=1.6, seed=RESEEDED.get(name, 4000 + 100 * s + 10 * r + i), shape="impact"))
    return wanted + body_pieces()


# -- Building wreckage: two materials, three stages, two takes each -------------------------------------

WRECK_STYLE = "medieval, close, dry, no music, no reverb, no voice"
#: One prompt per take; the collapse and debris stages are allowed to rumble on (shape ``collapse``).
WRECK_PROMPTS = {
    "crack": {"wood": ["a heavy wooden beam cracks and splinters under load, one loud crack", "old timber creaks and snaps with a sharp crack"],
              "stone": ["stone masonry cracks and grinds, one deep crack before a collapse", "a stone wall groans and splits with a sharp crack"]},
    "collapse": {"wood": ["a wooden building collapses, timber and planks crashing down in a heap", "a wooden roof caves in, beams crashing and boards tumbling down"],
                 "stone": ["a stone building collapses, heavy blocks crashing down with a deep rumble", "a stone tower falls, masonry thundering down into a heap"]},
    "debris": {"wood": ["planks and boards clatter down and settle, a wooden bucket rolls away", "loose timber settles, a few last boards fall, dust"],
               "stone": ["rubble and small stones tumble and settle with a dust hiss", "loose stones roll off a rubble heap and settle, dust"]},
}
WRECK_SHAPES = {"crack": ("impact", 2.0), "collapse": ("collapse", 3.0), "debris": ("collapse", 3.0)}


def wreckage_pieces() -> list[Piece]:
    wanted = []
    for s, stage in enumerate(WRECK_STAGES):
        shape, seconds = WRECK_SHAPES[stage]
        for m, material in enumerate(MATERIALS):
            for i, prompt in enumerate(WRECK_PROMPTS[stage][material]):
                name = f"{material}_{stage}_{i}"
                wanted.append(Piece(name, f"{prompt}, {WRECK_STYLE}", seconds=seconds, seed=RESEEDED.get(name, 6000 + 100 * s + 10 * m + i), shape=shape))
    return wanted


# -- Combat impacts: every weapon on every material, three phrasings each ---------------------------------

IMPACT_STYLE = "one short hit then silence, close, dry, no music, no reverb, no voice"
#: One verb phrase per take, so the three takes of a pair are three different blows.
STRIKES = {
    "sword": ["a steel sword swings and slashes into", "a sword blade hacks into", "a quick sword cut strikes"],
    "axe": ["a heavy axe swings and chops into", "a broad axe blade bites into", "an axe hacks hard into"],
    "spear": ["a spear thrusts and stabs into", "a spear point jabs into", "a spear thrust pierces"],
    "lance": ["a charging knight's lance drives into", "a heavy lance slams into", "a lance thrust punches into"],
    "arrow": ["a light arrow whistles in and strikes with a quick sharp thwack", "a thin arrow snaps into, a short sharp tick", "an arrow hits with a brief crisp thwack and sticks in"],
    "stone": ["a massive catapult boulder crashes with a deep heavy thud into", "a huge siege stone slams with a low booming impact into", "a heavy boulder thunders down onto"],
    "hammer": ["a war hammer swings and smashes into", "a heavy hammer head slams into", "a war hammer crushes"],
}
#: What is struck, in two wordings that alternate across takes.
STRUCK = {
    "flesh": ["a body, a wet meaty thump", "a man's body, a dull fleshy hit"],
    "armor": ["chainmail and plate armor, a metallic clang", "steel armor plates, a ringing metallic hit"],
    "wood": ["wooden planks, a splintering wooden crack", "a wooden wall, a hollow wooden thud and crack"],
    "stone": ["stone masonry, a hard stone crack with chips flying", "a stone wall, a sharp stony crack"],
}


def impact_pieces() -> list[Piece]:
    wanted = []
    for w, weapon in enumerate(WEAPONS):
        for m, target in enumerate(TARGETS):
            for i in range(IMPACT_TAKES):
                name = f"{weapon}_{target}_{i}"
                prompt = f"{STRIKES[weapon][i]} {STRUCK[target][i % 2]}, {IMPACT_STYLE}"
                wanted.append(Piece(name, prompt, seconds=1.6, seed=RESEEDED.get(name, 7000 + 100 * w + 10 * m + i), shape="impact", peak=0.75))
    return wanted


FOLDERS = {IMPACTS: impact_pieces, DEATHS: death_pieces, PRESENCE: presence_pieces, WRECKAGE: wreckage_pieces}


def cues(out: Path, families: list[str]) -> None:
    """Each family's death, spent-end and presence cues as the bank mixes them: a WAV and a stats row per cue,
    ``sheet.png`` with every cue's spectrogram (a row each), and ``cues.wav`` with every cue back to back and its label list."""
    from PIL import Image, ImageDraw
    from music import spectrogram, stats  # the music tool's picture: log frequency over time, the loudness above it
    from warband.audio import deaths, presence

    out.mkdir(parents=True, exist_ok=True)
    print(f"{'cue':26s} {'length':>6s} {'rms dB':>7s} {'peak':>5s} {'crest':>6s} {'centr':>6s} {'<120':>5s} {'>6k':>5s}")
    rows = []
    for family in families:
        ends = [[(f"{deaths.cue(family, spent=spent)}_{take}", deaths.death(family, take, spent=spent))
                 for take in range(deaths.takes(family, spent=spent))] for spent in (False, True) if (family, spent) in deaths.ENDS]
        alive = [(f"{family}_presence_{take}", presence.presence(family, take)) for take in range(presence.takes(family))] if presence.cue(family) else []
        rows += [*ends, alive]
        for name, clip in [cue for row in (*ends, alive) for cue in row]:
            write_wav(out / f"{name}.wav", clip)
            s = stats(clip[:, None])
            print(f"{name:26s} {len(clip) / SAMPLE_RATE:6.2f} {s['rms_db']:7.1f} {s['peak']:5.2f} {s['crest_db']:6.1f} {s['centroid_hz']:6.0f} "
                  f"{s['low_share']:5.2f} {s['high_share']:5.3f}")
    rows = [row for row in rows if row]
    width, height = 480, 180
    sheet = Image.new("RGB", (max(map(len, rows)) * (width + 8), len(rows) * (height + 78)), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for r, row in enumerate(rows):
        for c, (name, clip) in enumerate(row):
            x, y = c * (width + 8), r * (height + 78)
            sheet.paste(spectrogram(clip, width=width, height=height), (x, y + 18))
            draw.text((x + 4, y + 3), f"{name}  {len(clip) / SAMPLE_RATE:.2f} s", fill=(255, 255, 255))
    sheet.save(out / "sheet.png")
    labels = sampler(out, [name for row in rows for name, _clip in row], out / "cues.wav", gap=0.6)
    (out / "cues.txt").write_text("".join(f"{start:7.2f}s  {name}\n" for start, name in labels))
    print(f"{len(labels)} cues, {labels[-1][0]:.0f} s: {out / 'cues.wav'}; spectrograms: {out / 'sheet.png'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("refresh", help="generate missing or changed pieces")
    refresh.add_argument("--model", default="medium", choices=sorted(StableAudioMLX.MODELS))
    listen = commands.add_parser("sampler", help="write every folder's pieces back to back")
    listen.add_argument("out", type=Path, help="directory for impacts.wav, deaths.wav, presence.wav, wreckage.wav and their label lists")
    look = commands.add_parser("cues", help="render the families' death and presence cues with spectrograms and stats")
    look.add_argument("out", type=Path)
    look.add_argument("--families", default=",".join(BODIES), help="comma-separated family names (default: the machines and creatures)")
    args = parser.parse_args()
    if args.command == "refresh":
        generator = StableAudioMLX(args.model)
        failures = []
        for folder, spec in FOLDERS.items():
            try:
                manifest = build(spec(), ROOT / folder, generator, license=LICENSE)
                print(f"{len(manifest['pieces'])} pieces under {ROOT / folder}")
            except BuildError as failure:
                failures.append(str(failure))
        if failures:
            sys.exit("\n".join(failures) + "\nEverything else is written; add the rejected names to RESEEDED with a fresh seed.")
        print("bump SOUND_VERSION and run the tests")
    elif args.command == "cues":
        cues(args.out, args.families.split(","))
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        for folder, spec in FOLDERS.items():
            names = [p.name for p in spec() if (ROOT / folder / f"{p.name}.wav").exists()]
            out = args.out / f"{folder}.wav"
            labels = sampler(ROOT / folder, names, out)
            out.with_suffix(".txt").write_text("".join(f"{start:7.2f}s  {name}\n" for start, name in labels))
            print(f"{len(labels)} pieces, {labels[-1][0]:.0f} s: {out}")


if __name__ == "__main__":
    main()
