# Warband results and local high scores

Every finished offline match shows its score, battle record and each warband's
race and outcome; online matches are not ranked. Press **B** on the results or title screen for high scores. **D**, **M**
and **P** cycle difficulty, map size and player count; **Esc** returns.

## Scoring

| Component | Points |
| --- | --- |
| Victory | 5,000 |
| Enemy units and buildings destroyed by your forces | Combined gold and lumber cost ÷ 10 |
| Your surviving units and completed buildings | Combined cost ÷ 20 |
| Completed research | Combined cost ÷ 10 |
| Swift victory | 2 per second before 20:00, maximum 2,400 |

Each component rounds down. Gold and lumber count equally. Stockpiles,
unfinished buildings and queued units earn no preservation points. Defeats
retain combat, preservation and research points, but earn no victory or speed
bonus. Kills belong to the force landing the lethal hit, including towers and
siege splash; rival-versus-rival kills never count as yours. Cancellation and
surrender do not award destruction points.

The simulation stops at the decisive step.
A human eliminated from a three- or four-player match gets a defeat record even
when the remaining rivals have not determined a winner.

## AI surrender

An AI concedes when it has no living units, no paid unit in production, and no
recruit it can afford and supply at a completed training building. Living units
include workers inside mines or construction sites. Refunds from abandoned
construction and ongoing research count toward recovery. The AI cancels work
and recruits an affordable unit when that saves it, preferring a peasant to
restart the economy. Resources alone cannot rescue missing production or supply.

Remaining buildings are abandoned on surrender, ending tower fire and avoiding
cleanup. Humans never automatically concede just because they cannot recruit;
normal elimination still requires losing their units and buildings.

## Local records

The game keeps ten scores per difficulty, map dimensions and total player count.
The player's race, land and seed are shown with each entry; races share a board. Higher scores lead; ties prefer faster
finishes, then the earlier record. Each saved campaign carries an ID, so
reopening a finished save does not add a duplicate. Replaying a saved position
can improve that campaign's best finish. Demo battles are excluded.

Records use Saga2D's atomic saves and backup at
`~/.warband/high_scores/save_1.json`, separate from match slots and preferences.
A damaged or unwritable file produces a visible error; it is not silently reset.
Older saves still load and receive a stable identity when first opened. Their
combat totals start from that save because earlier versions credited unrelated
enemy deaths to the player.

## Verification

`uv run python -m pytest tests/warband -q` exercises the model, AI, persisted
records and scene transitions. `tools/fuzz_warband.py` runs randomized games
and UI input at a default 25% CPU allowance. The native screenshot playback is:

```sh
uv run python tools/verify_warband_scores.py /tmp/warband-score-shots
```

It covers victory, ten-row rankings, empty boards, title access, a defeat while
rivals remain, saved-result deduplication and corrupt storage at 1280×800 and
1280×720. It uses temporary storage and paced pyglet frames.

This system was built on the unmerged `warband` branch on 2026-09-06 and
ported onto the race build on 2026-09-09.
