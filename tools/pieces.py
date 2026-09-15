"""Generate Warband's sound pieces with Stable Audio 3: combat impacts, unit deaths and building wreckage, and files to listen to them.

    uv run python tools/pieces.py refresh              # generate what is missing or changed; manifests updated
    uv run python tools/pieces.py sampler DIR          # deaths.wav and wreckage.wav, every piece back to back, with label lists

Needs STABLE_AUDIO_MLX (see ../sagaforge/docs/foley.md).  The prompts below are the source of
truth; each folder's manifest records what was actually generated.  A rejected piece (silent, or
a click) is reported at the end: give it a new seed here and run refresh again.  After a refresh,
bump ``SOUND_VERSION`` in warband/sound.py so the cached cues are mixed again, and run the tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sagaforge.foley import BuildError, Piece, StableAudioMLX, build, sampler  # noqa: E402
from warband.pieces import ROOT  # noqa: E402
from warband.rules import Race  # noqa: E402

# The game modules (warband.combat_sound, deaths, wreckage) expect these folders and names; they are
# spelled out here rather than imported because those modules refuse to load without their pieces.
DEATHS, DEATH_STAGES = "deaths", ("weapon", "body", "settle")
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
    return wanted


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


FOLDERS = {IMPACTS: impact_pieces, DEATHS: death_pieces, WRECKAGE: wreckage_pieces}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("refresh", help="generate missing or changed pieces")
    refresh.add_argument("--model", default="medium", choices=sorted(StableAudioMLX.MODELS))
    listen = commands.add_parser("sampler", help="write every folder's pieces back to back")
    listen.add_argument("out", type=Path, help="directory for deaths.wav, wreckage.wav and their label lists")
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
