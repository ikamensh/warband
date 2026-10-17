"""Campaign subjects rendered in the ordinary map entity pipeline.

Authored footprints, owners and rules types identify a subject across rebuilding.
Its Sighting supplies every damage/construction fact, including under fog. This
registry changes presentation alone: there are no simulation types or save fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from saga2d import Game
from warband.art import campaign_landmarks as art
from warband.sim.model import Pos
from warband.sim.rules import BuildingType as B
from warband.story.campaign import Run
from warband.ui.view import Sighting


@dataclass(frozen=True)
class Structure:
    owner: int
    type: B
    pos: Pos
    form: str
    title: str
    landmark: str | None = None
    rubble: bool = False
    shuttered: bool = False


@lru_cache(maxsize=8)
def structures(mission_id: str) -> tuple[Structure, ...]:
    """The physical subjects at each authored mission site; independent of live world state."""
    if mission_id == "undertow_mill":
        return (Structure(1, B.FARM, (23, 2), "pylon", "Mill lock-pylon", "mill_pylon", rubble=True),
                Structure(0, B.VAULT, (20, 16), "vault", "The straining vault", "mill_vault"),
                Structure(0, B.FARM, (20, 16), "vault", "The shuttered mill vault", "mill_vault", shuttered=True))
    if mission_id == "undertow_caravan":
        return (Structure(1, B.FARM, (36, 7), "dam", "Hasp's millpond dam", "dam_pylon", rubble=True),
                *(Structure(1, B.FARM, (x, 23), "rockfall", "Causeway rockfall") for x in (30, 32)))
    if mission_id == "undertow_grove":
        return (Structure(0, B.VAULT, (23, 17), "root_vault", "The grown Third Lock"),)
    if mission_id == "undertow_weight":
        from warband.story.new_campaign import WEIGHT_RIFTS

        return tuple(Structure(0, B.VAULT, pos, "vault", f"Weight {'I II III'.split()[i]}", f"weight_{i + 1}")
                     for i, pos in enumerate(WEIGHT_RIFTS))
    if mission_id == "undertow_maw":
        from warband.story.new_campaign import KEYSTONE_POS, PYLON_POS

        return (Structure(0, B.MAGE_TOWER, KEYSTONE_POS, "keystone", "The Keystone", "keystone", rubble=True),
                *(Structure(1, B.FARM, pos, "pylon", f"Seal-pylon {'I II III'.split()[i]}", f"seal_pylon_{i + 1}", rubble=True)
                  for i, pos in enumerate(PYLON_POS)),
                Structure(1, B.MAGE_TOWER, (42, 56), "refuge_tower", "Wounded crews' refuge", "refuge_tower", rubble=True))
    return ()


def _subject(run: Run, sighting: Sighting) -> Structure | None:
    return next((subject for subject in structures(run.mission.id)
                 if (subject.owner, subject.type, subject.pos) == (sighting.player, sighting.type, sighting.rect[:2])), None)


def building_image(run: Run, game: Game, sighting: Sighting) -> str | None:
    """A full sprite from remembered facts; rebuildable vaults retain their usual construction stages."""
    subject = _subject(run, sighting)
    if subject is None or (not sighting.done and sighting.type is not B.FARM):
        return None
    state = "damaged" if sighting.look == "damaged" else "active"
    if subject.form == "keystone" and run.get("maw_resolved"):
        state = run.vars["landmarks"]["keystone"]["state"]
    if subject.shuttered:
        state = "dormant"
    return art.register_image(game, subject.form, state, sighting.rect[2], sighting.player or 0)


def building_title(run: Run, sighting: Sighting) -> str | None:
    """The selected subject has the same physical identity as its map body and portrait."""
    subject = _subject(run, sighting)
    return subject.title if subject is not None else None


def scenery_form(run: Run, id: str) -> tuple[str, int] | None:
    """Only empty sites need scenery; buildings, trees, mines and rifts supply their own bodies."""
    return {("undertow_caravan", "mesa"): ("refuge", 3),
            ("undertow_maw", "relief_sluice"): ("sluice", 2),
            ("undertow_grove", "guardian_ring"): ("stone_ring", 10)}.get((run.mission.id, id))


def ruined_form(run: Run, id: str) -> tuple[str, int] | None:
    """A witnessed destroyed subject leaves its own materials, never a second standing body."""
    subject = next((subject for subject in structures(run.mission.id) if subject.landmark == id and subject.rubble), None)
    return (subject.form, 2) if subject is not None else None


def warm(run: Run, game: Game) -> None:
    """Extract this mission's structure paintings before combat or first destruction can need them."""
    forms = {subject.form for subject in structures(run.mission.id)}
    scenery = {body[0]: body[1] for id in run.vars.get("landmarks", {}) if (body := scenery_form(run, id)) is not None}
    forms.update(scenery)
    for form in forms:
        for state in ("active", "damaged", "ruined", "dormant", "open"):
            art.register_image(game, form, state, scenery.get(form, 2))
