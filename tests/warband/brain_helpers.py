"""Shared behavioral scenarios run against classic brains and composed stronger brains."""
from warband.brains.pro_ai import ProBrain
from warband.brains.pro_assignments import Duty


def military(brain):
    return brain.army if isinstance(brain, ProBrain) else brain


def workers(brain):
    return brain.army.workers if isinstance(brain, ProBrain) else brain


def members(brain, duty):
    if isinstance(brain, ProBrain):
        return brain.army.assignments.members(duty)
    names = {Duty.CREEP: "creep_party", Duty.ESCAPE: "camp_escape", Duty.RAID: "raiders",
             Duty.HUNT: "hunt", Duty.HEAL: "_hurt"}
    if duty is Duty.HUNT:
        return list(brain.hunt.party)
    return list(getattr(brain, names[duty]))
