# Adding a unit

What a new unit type needs before it is done. Three times on 2026-09-24 a unit
was added (the flying machines, then the four unique units of WB-068) and each
time it came in with its race's sounds and the render's art, because nothing
asked for more. This is the list, and the tests named under each step fail
when a unit type skips it, so the next unit cannot.

## The row and its names

A row in `warband/assets/constants/units.toml` (or `neutrals.toml` for a
creature): its numbers, `living`, `flying`, its armour class and attack. Its
name and summary for every race that fields it in `races.toml`, and its plural
in `IRREGULAR_PLURALS` (`warband/ui/scene.py`) if it is not the name plus "s"
(`tests/warband/test_cancel_mode.py` lists every name). Its codex line; the
card and the tech tree read the row.

## Its art

(WB-070 fills this section: the render, the painted sheet with its animation,
the exemption table and the test that holds every unit type to it.)

## Its sounds

(WB-069 fills this section: the body's sound family, its death, its presence,
its blow's impact material, and the tests that hold every unit type to them.)

## Its brains

Who trains it and when, what it is sent at, and what answers it: a test on a
staged world for each decision, and `tools/arena.py` or `tools/race_report.py`
before and after (`docs/ai-ladder.md`, `docs/balance.md`).

## Its checks

`tools/visual_lint.py` over the new screens and sprites, `tools/fuzz.py`, the
fingerprint and `tools/sim_bench.txt` refreshed in the same commit, and a frame
of it in play looked at.
