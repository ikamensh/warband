# Warband Early Access progress and evidence

Criteria: [warband-early-access-criteria.md](warband-early-access-criteria.md).
A gate is incomplete until evidence below proves it.

## Baseline audit — 2026-09-05, commit `575bb32`

- Playable slice: 4 units, 4 buildings, one AI, procedural summer maps, fog,
  minimap, one save slot, 17 sounds, one track. 403 tests in the repo (117 for
  Warband), `tools/fuzz_warband.py` 20 matches + 12 monkey runs clean,
  `tools/verify_warband.py` seven real-input steps with inspected frames.
- Known gaps: matches on large maps often undecided at 15 minutes; no
  upgrades, siege, healing or tech chain; settings not persisted; one save
  slot, unversioned; fixed 1280×800 HUD layout; four animation frames.

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| W01–W15 | incomplete | see increments below |

## Increments

(appended as work lands; each names its commit, tests and inspected artefacts)
