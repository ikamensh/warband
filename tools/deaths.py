"""Generate the death pieces under warband/assets/deaths with Stable Audio 3, and a file to listen to them.

    uv run python tools/deaths.py refresh            # generate what is missing or changed; manifest updated
    uv run python tools/deaths.py sampler OUT.wav    # every piece back to back, cries first, with a label list

Needs STABLE_AUDIO_MLX (see ../sagaforge/docs/foley.md).  The prompts below are the source of
truth; the manifest records what was actually generated.  A rejected piece (silent, or a click)
is reported at the end: give it a new seed here and run refresh again.  After a refresh, bump
``SOUND_VERSION`` in warband/sound.py so the cached cues are mixed again, and run the tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sagaforge.foley import BuildError, Piece, StableAudioMLX, build, sampler  # noqa: E402
from warband.deaths import ASSETS, STAGES  # noqa: E402
from warband.rules import Race  # noqa: E402

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
RESEEDED = {"elf_cry_2": 1122, "human_settle_1": 4311}


def pieces() -> list[Piece]:
    wanted = []
    for r, race in enumerate(Race):
        for i, prompt in enumerate(CRIES[race]):
            name = f"{race.value}_cry_{i}"
            wanted.append(Piece(name, f"{prompt}, {CRY_STYLE}", seconds=2.0, seed=RESEEDED.get(name, 1000 + 10 * r + i), shape="voice", peak=0.72))
        for s, stage in enumerate(STAGES):
            for i in range(STAGE_TAKES):
                name = f"{race.value}_{stage}_{i}"
                wanted.append(Piece(name, f"{FALLS[stage][race]}, {STAGE_STYLE}", seconds=1.6, seed=RESEEDED.get(name, 4000 + 100 * s + 10 * r + i), shape="impact"))
    return wanted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("refresh", help="generate missing or changed pieces")
    refresh.add_argument("--model", default="medium", choices=sorted(StableAudioMLX.MODELS))
    listen = commands.add_parser("sampler", help="write every piece back to back")
    listen.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "refresh":
        try:
            manifest = build(pieces(), ASSETS, StableAudioMLX(args.model), license=LICENSE)
        except BuildError as failure:
            sys.exit(f"{failure}\nEverything else is written; add the rejected names to RESEEDED with a fresh seed.")
        print(f"{len(manifest['pieces'])} pieces under {ASSETS}; bump SOUND_VERSION and run the tests")
    else:
        names = [p.name for p in pieces() if (ASSETS / f"{p.name}.wav").exists()]
        labels = sampler(ASSETS, names, args.out)
        args.out.with_suffix(".txt").write_text("".join(f"{start:7.2f}s  {name}\n" for start, name in labels))
        print(f"{len(labels)} pieces, {labels[-1][0]:.0f} s: {args.out} (labels in {args.out.with_suffix('.txt').name})")


if __name__ == "__main__":
    main()
