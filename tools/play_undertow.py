"""Play The Undertow's missions headlessly, the way a player must be able to.

    uv run python tools/play_undertow.py                  # every mission, one path each, timings printed
    uv run python tools/play_undertow.py undertow_maw open # one mission, one path

Every action is an ordinary public ``World`` order (move, attack-move, attack, harvest, salvage,
build, repair, train, cast) given between ``world.step()`` and ``run.tick()``, exactly as
``MissionScene`` drives a mission.  Dialogue choices queued in ``run.pending`` are answered by
writing the chosen value, as ``DialogScene`` does.  Nothing is teleported, no objective is marked
done by hand, and no purse is edited: if a solver path wins here, the mission is attainable through
the normal controls.  ``tests/warband/test_undertow.py`` drives these same solvers.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warband.story.campaign import Choice, Run  # noqa: E402
from warband.story.mission_scene import build_world  # noqa: E402
from warband.story.new_campaign import CAMPAIGN  # noqa: E402
from warband.sim.model import Hold, dist  # noqa: E402
from warband.sim.rules import BUILDINGS, BuildingType as B, SIM_DT, Terrain, UnitType as U, Upgrade  # noqa: E402

CHUNK = int(round(1.0 / SIM_DT))  # one simulated second between solver decisions


def _state(run: Run) -> str:
    heroes = {k: (u.hp if (u := run.unit(k)) else None) for k in ("issa", "brakk", "wrenna", "dagna") if k in run.vars}
    return (f"t={run.world.time:.0f}s objectives={run.state} fired={sorted(run.fired)} "
            f"soldiers={[len(run.soldiers(s)) for s in range(run.world.seats)]} heroes={heroes} "
            f"gold={run.world.players[0].gold} lumber={run.world.players[0].lumber} aether={run.world.players[0].aether}")


def play_until(run: Run, done: Callable[[Run], bool], *, seconds: float, act: Callable[[Run], None] | None = None,
               what: str = "condition") -> float:
    """Step the mission in one-second chunks (acting between them) until *done* or the clock runs out."""
    start = run.world.time
    while run.world.time - start < seconds:
        if done(run):
            return run.world.time - start
        if run.lost is not None:
            raise AssertionError(f"mission lost ({run.lost}) waiting for {what}: {_state(run)}")
        for _ in range(CHUNK):
            run.world.step()
            run.tick()
        run.world.take_events()
        if act is not None and not run.won:
            act(run)
    if done(run):
        return run.world.time - start
    raise AssertionError(f"timed out after {seconds:.0f}s waiting for {what}: {_state(run)}")


def answer(run: Run, key: str, value: Any) -> None:
    """Answer a queued dialogue choice the way DialogScene does: store the value, drop the dialogue."""
    for dialog in list(run.pending):
        for item in dialog:
            if isinstance(item, Choice) and item.key == key:
                assert value in [o.value for o in item.options], f"{value!r} is not an answer to {key}"
                run.set(key, value)
                run.pending.remove(dialog)
                return


def _idle(unit) -> bool:
    return not unit.orders and not unit.hidden


def _free(unit) -> bool:
    """Idle, or merely holding position: a worker the solver may put to a new job."""
    return not unit.hidden and all(isinstance(order, Hold) for order in unit.orders)


def _last(run: Run) -> dict[str, float]:
    state = getattr(run, "_solver_last", None)
    if state is None:
        state = run._solver_last = {}
    return state


def _every(run: Run, key: str, interval: float) -> bool:
    last = _last(run)
    if run.world.time - last.get(key, -1e9) >= interval:
        last[key] = run.world.time
        return True
    return False


def fight(run: Run, point, *, sides: tuple[int, ...] = (1,), exclude: tuple[int, ...] = ()) -> None:
    """Soldiers attack-move to the nearest visible enemy's ground, or to *point* when the field is clear.

    Orders are re-issued only to idle soldiers, plus a slow refresh for soldiers not mid-blow, so a
    fight in progress is never interrupted by the solver's own bookkeeping."""
    world = run.world
    soldiers = [u for u in run.soldiers(0) if not u.hidden and u.id not in exclude]
    if not soldiers:
        return
    enemies = [u for side in sides for u in run.units(side)
               if not u.hidden and world.is_visible(0, u.tile)]  # what the player can actually see
    if enemies:
        cx = sum(u.x for u in soldiers) / len(soldiers)
        cy = sum(u.y for u in soldiers) / len(soldiers)
        target = min(enemies, key=lambda e: dist(e.pos, (cx, cy))).pos
    else:
        target = tuple(point)
    refresh = _every(run, f"fight:{target}", 8.0)
    ids = [u.id for u in soldiers if _idle(u) or (refresh and u.state not in ("attack",))]
    if ids:
        world.attack_move(ids, target)


def attack_building(run: Run, building_id: int) -> None:
    """Idle soldiers who can strike a building are set on it; the rest follow the fight to its walls."""
    building = run.world.buildings.get(building_id)
    if building is None:
        return
    idle = [u for u in run.soldiers(0) if _idle(u)]
    strikers = [u.id for u in idle if run.world.can_strike(u, building)]
    if strikers:
        run.world.attack(strikers, building_id)
    elif idle:
        run.world.attack_move([u.id for u in idle], building.center)


def train(run: Run, building_type: B, unit_type: U, want_soldiers: int) -> None:
    """Keep one producer training toward *want_soldiers* total soldiers, when the world allows it."""
    world = run.world
    queued = sum(len(b.queue) for b in run.buildings(0))
    if len(run.soldiers(0)) + queued >= want_soldiers:
        return
    for building in run.buildings(0, building_type):
        if world.can_train(building, unit_type) is None:
            world.train(building.id, unit_type)
            return


def cast_at(run: Run, spell: Upgrade, point) -> bool:
    """Cast if the world allows it right now; a refusal is the spell bar's answer, not a solver error."""
    world = run.world
    if world.can_cast(0, spell, tuple(point)) is not None:
        return False
    world.cast(0, spell, tuple(point))
    return True


def mend_wounded(run: Run) -> None:
    wounded = [u for u in run.soldiers(0) if u.hp < u.max_hp * 0.6]
    if wounded:
        cast_at(run, Upgrade.MEND, min(wounded, key=lambda u: u.hp).pos)


def workers(run: Run) -> list:
    return run.units(0, U.PEASANT)


def ensure_buildings(run: Run, plans: list[tuple[B, tuple[int, int]]], *, seconds: float = 900,
                     act: Callable[[Run], None] | None = None) -> None:
    """Raise each (type, pos) with ordinary scout-then-build orders, different workers in parallel."""
    world = run.world
    builders: dict[tuple[int, int], int] = {}

    def built(btype: B, pos: tuple[int, int]) -> bool:
        return any(b.type is btype and b.pos == pos and b.done for b in run.buildings(0, btype, done=None))

    def work(r: Run) -> None:
        if act is not None:
            act(r)
        for btype, pos in plans:
            if built(btype, pos):
                continue
            site = next((b for b in r.buildings(0, btype, done=None) if b.pos == pos), None)
            if site is not None:
                helpers = [w for w in workers(r) if _free(w)][:2]
                if helpers and not site.done:  # helping raise a site is the repair order's other half
                    world.repair([w.id for w in helpers], site.id)
                continue
            # A bystander on the footprint is moved off it, as a player would: otherwise it blocks the site for good.
            size = BUILDINGS[btype].size
            bystanders = [u.id for u in r.units(0) if _idle(u)
                          and pos[0] <= int(u.x) < pos[0] + size and pos[1] <= int(u.y) < pos[1] + size]
            if bystanders:
                world.move(bystanders, (pos[0] + size / 2, pos[1] + size + 2.0))
            taken = set(builders.values())
            free = [w for w in workers(r) if w.id not in taken]
            if not free:
                continue
            centre = (pos[0] + 1.0, pos[1] + 1.0)
            worker = builders.get(pos) and world.units.get(builders[pos]) or min(free, key=lambda w: dist(w.pos, centre))
            builders[pos] = worker.id
            if world.can_place(btype, pos, 0) is None and world.can_afford(0, BUILDINGS[btype].cost) is None:
                if _idle(worker) or _every(r, f"build:{pos}", 6.0):
                    world.build(worker.id, btype, pos)
            elif _idle(worker):
                world.move([worker.id], centre)  # walk there first: unexplored ground cannot be built on

    play_until(run, lambda r: all(built(t, p) for t, p in plans), seconds=seconds, act=work,
               what=f"buildings {plans}")


def building_at(run: Run, side: int, btype: B, pos: tuple[int, int]):
    return next((b for b in run.buildings(side, btype, done=None) if b.pos == pos), None)


def _hold_workers(run: Run) -> None:
    ids = [w.id for w in workers(run)]
    if ids:
        run.world.hold(ids)


# -- Missions ----------------------------------------------------------------------


def solve_mill(run: Run, *, shutter: bool) -> float:
    """Millfield: fight the surges at the vault, or fell its pylon after the fork and clear the fields."""
    world = run.world
    mine = next(b for b in world.mines())
    for w in workers(run)[:3]:
        world.harvest([w.id], mine.id)

    def act(r: Run) -> None:
        answer(r, "mill_intent", not shutter)
        train(r, B.BARRACKS, U.FOOTMAN, 10)
        mend_wounded(r)
        if shutter and "wave_2" in r.fired and r.get("mill_pylon") in r.world.buildings:
            # The whole band marches on the pylon at once: the shutter choice is an expedition, not a side errand.
            if _every(r, "pylon_march", 10.0) and (pylon := r.world.buildings.get(r.get("mill_pylon"))) is not None:
                r.world.attack([u.id for u in r.soldiers(0) if r.world.can_strike(u, pylon)], pylon.id)
        else:
            fight(r, tuple(r.get("mill_vault_center")))

    return play_until(run, lambda r: r.won, seconds=900, act=act, what="Millfield won")


def solve_caravan(run: Run, *, blast_dam: bool) -> float:
    """The Salt Caravan: salvage the ruins, blast the rockfall, raise the mesa camp, bring the drovers up."""
    world = run.world
    start = world.time

    def guard(r: Run) -> None:
        enemies = [u for u in r.units(1) if r.world.is_visible(0, u.tile)
                   and any(dist(u.pos, w.pos) < 16 for w in r.units(0))]
        if enemies:
            fight(r, enemies[0].pos)
        else:
            ids = [u.id for u in r.soldiers(0) if _idle(u)]
            if ids:
                r.world.attack_move(ids, (14.5, 27.5))

    def strip(r: Run) -> None:
        guard(r)
        ruins = [b for b in r.world.buildings.values() if b.player == 2]
        for w in workers(r):
            if _idle(w) and ruins:
                r.world.salvage([w.id], ruins[0].id)

    play_until(run, lambda r: r.state.get("strip") == "done", seconds=900, act=strip, what="Old Camp stripped")

    party = [u.id for u in run.units(0)]
    world.move(party, (28.5, 23.5))
    play_until(run, lambda r: "rockfall" in r.fired and "sappers" in r.fired, seconds=300, act=guard,
               what="rockfall dropped and sappers arrived")

    def blast(r: Run) -> None:
        guard(r)
        rocks = [i for i in r.get("rockfall", []) if i in r.world.buildings]
        sappers = r.units(0, U.SAPPER)
        if rocks:
            if sappers and _every(r, "sapper_blast", 5.0):
                r.world.attack([sappers[0].id], rocks[0])
            attack_building(r, rocks[0])

    play_until(run, lambda r: not any(i in r.world.buildings for i in r.get("rockfall", [])), seconds=600,
               act=blast, what="causeway reopened")

    if blast_dam:
        def dam(r: Run) -> None:
            enemies = [u for u in r.units(1) if u.y < 20 and r.world.is_visible(0, u.tile)]
            if enemies:
                fight(r, enemies[0].pos)
            sappers = r.units(0, U.SAPPER)
            if sappers and _every(r, "dam_blast", 5.0) and r.get("dam_pylon") in r.world.buildings:
                r.world.attack([sappers[0].id], r.get("dam_pylon"))
            attack_building(r, r.get("dam_pylon"))

        soldiers = [u.id for u in run.soldiers(0)] + [u.id for u in run.units(0, U.SAPPER)]
        world.attack_move(soldiers, (37.0, 8.0))
        play_until(run, lambda r: bool(r.get("undertow_dam")), seconds=600, act=dam, what="mill-dam blasted")

    everyone = [u.id for u in run.units(0)]
    world.move(everyone, tuple(run.get("mesa_center")))
    play_until(run, lambda r: sum(1 for u in r.units(0, U.PEASANT) if u.x >= 44) >= 4, seconds=600, act=guard,
               what="drovers on the mesa")

    def camp_guard(r: Run) -> None:
        enemies = [u for u in r.units(1) if r.world.is_visible(0, u.tile)
                   and any(dist(u.pos, w.pos) < 18 for w in r.units(0))]
        if enemies:
            fight(r, enemies[0].pos)

    ensure_buildings(run, [(B.TOWN_HALL, (46, 19)), (B.FARM, (46, 24)), (B.FARM, (50, 24)), (B.FARM, (54, 24))],
                     seconds=1200, act=camp_guard)

    def settle(r: Run) -> None:
        camp_guard(r)
        stray = [w.id for w in r.units(0, U.PEASANT) if _idle(w)]
        if stray:
            r.world.move(stray, tuple(r.get("mesa_center")))

    play_until(run, lambda r: r.won, seconds=600, act=settle, what="caravan won")
    return world.time - start


def solve_grove(run: Run, *, cut: bool, guardian: str | None = None) -> float:
    """The Grove That Drinks: answer the Ancient first, then parley — and cut the strip or rout the crew."""
    world = run.world
    start = world.time
    mine = next(b for b in world.mines())
    for w in workers(run):  # the grove's purse: gold for replacements while the story walks east and south
        world.harvest([w.id], mine.id)

    if guardian == "ally":
        # Wrenna goes alone, on a move order: an escorting archer's idle shot would close this path.
        world.move([run.get("wrenna")], (47.5, 14.5))
        play_until(run, lambda r: bool(r.get("undertow_guardian_ally")), seconds=420,
                   what="Wrenna reaches the Guardian")
    elif guardian == "core":
        def boss(r: Run) -> None:
            g = r.world.units.get(r.get("guardian"))
            if g is None:
                return
            cast_at(r, Upgrade.ENTANGLE, g.pos)
            fighters = [u.id for u in r.soldiers(0)
                        if _idle(u) and u.id != r.get("wrenna") and r.world.can_strike(u, g)]
            if fighters:
                r.world.attack(fighters, g.id)
            for church in r.buildings(0, B.CHURCH):
                if r.world.can_train(church, U.TREANT) is None:
                    r.world.train(church.id, U.TREANT)
            wrenna = r.unit("wrenna")
            if wrenna is not None and _idle(wrenna) and dist(wrenna.pos, g.pos) < 16:
                r.world.move([wrenna.id], (30.5, 14.5))

        army = [u.id for u in run.soldiers(0) if u.id != run.get("wrenna")]
        world.move(army, (47.5, 14.5))
        world.move([run.get("wrenna")], (30.5, 14.5))  # one blow from the Ancient fells her: she waits well west
        play_until(run, lambda r: bool(r.get("undertow_guardian_core")), seconds=900, act=boss,
                   what="Guardian brought down")

        def rebuild(r: Run) -> None:
            train(r, B.BARRACKS, U.FOOTMAN, 12)
            for church in r.buildings(0, B.CHURCH):
                if r.world.can_train(church, U.TREANT) is None:
                    r.world.train(church.id, U.TREANT)

        play_until(run, lambda r: len(r.soldiers(0)) >= 11, seconds=900, act=rebuild,
                   what="the grove's guard rebuilt after the Ancient")

    # Wrenna parleys alone, as with the Guardian: a formed band idling by the camp would start the fight itself.
    world.move([run.get("wrenna")], (29.5, 27.5))  # parley hails her en route; she stops outside bowshot of the mill
    play_until(run, lambda r: "parley" in r.fired, seconds=420, what="parley at the woodcutters' camp")

    if cut:
        def fell(r: Run) -> None:
            standing = [tuple(t) for t in r.get("strip_tiles") if r.world.terrain_at(tuple(t)) is Terrain.TREES]
            if standing and _every(r, "fell_assign", 4.0):
                for i, w in enumerate(workers(r)):
                    current = next((o.target for o in w.orders if type(o).__name__ == "Harvest"), None)
                    if current not in standing:  # includes miners and workers whose tree was felled under them
                        r.world.harvest([w.id], standing[i % len(standing)])
            fight(r, (44.5, 25.5), sides=(2,))

        play_until(run, lambda r: bool(r.get("bloom_started")), seconds=1200, act=fell, what="firebreak finished")
    else:
        def rout(r: Run) -> None:
            # The crew struck camp at the parley; keeping the grove whole is chosen by mustering at the hall.
            train(r, B.BARRACKS, U.FOOTMAN, 12)
            ids = [u.id for u in r.soldiers(0) if _idle(u)]
            if ids:
                r.world.move(ids, (16.5, 12.5))

        play_until(run, lambda r: bool(r.get("bloom_started")), seconds=900, act=rout, what="muster at the Moon Hall")

    def weather(r: Run) -> None:
        train(r, B.BARRACKS, U.FOOTMAN, 12)
        mend_wounded(r)
        wrenna = r.unit("wrenna")
        fight(r, tuple(r.get("moonwell_center")), sides=(2,),
              exclude=(wrenna.id,) if wrenna is not None else ())
        if wrenna is not None and _idle(wrenna):
            r.world.move([wrenna.id], tuple(r.get("moonwell_center")))  # the healer holds the well, not the front

    play_until(run, lambda r: r.won, seconds=1200, act=weather, what="bloom weathered")
    return world.time - start


def solve_weight(run: Run, *, seam: str) -> float:
    """The Weight: beat off the engineer bands, break the siege, and settle the seam by hand."""
    assert seam in ("cap", "mine", "guard")
    world = run.world
    start = world.time
    seam_building = world.buildings[run.get("seam_id")]
    if seam == "mine":
        for w in workers(run):
            world.harvest([w.id], seam_building.id)
    elif seam == "cap":
        for w in workers(run)[-2:]:  # a little seam income keeps the purse alive while the cap is raised
            world.harvest([w.id], seam_building.id)
    else:
        _hold_workers(run)

    def defend(r: Run, *, engage: bool = True) -> None:
        answer(r, "seam_intent", seam)
        if seam != "cap" or r.get("seam_settled") or r.world.players[0].gold >= 850:
            train(r, B.BARRACKS, U.FOOTMAN, 12)  # before the cap, never train away the vault's own price
        mend_wounded(r)
        damaged = [b for b in r.buildings(0, B.VAULT) + r.buildings(0, B.TOWN_HALL) if b.hp < b.max_hp]
        free = [w for w in workers(r) if _free(w)]
        if damaged and free:
            r.world.repair([free[0].id], damaged[0].id)
        if engage:
            fight(r, tuple(r.get("weight_target")))

    if seam == "cap":
        ensure_buildings(run, [(B.VAULT, tuple(run.get("seam_rift")))], seconds=900, act=defend)
        play_until(run, lambda r: bool(r.get("seam_settled")), seconds=120, act=defend, what="seam capped")

    def besiege(r: Run) -> None:
        # The counter-assault is a march of the whole band, not an errand for whoever is idle:
        # the defence orders would otherwise recall it to the Weights every few seconds.
        if seam == "mine":  # the defensive win still has to raze the workshop it spends
            target = r.get("enemy_workshop") if all(f"band_{i}" in r.fired for i in (1, 2, 3)) else None
        else:
            target = r.get("enemy_hall") if "band_1" in r.fired else None
        building = r.world.buildings.get(target) if target is not None else None
        if building is None:
            defend(r)
            return
        defend(r, engage=False)
        near = [u for u in r.units(1) if r.world.is_visible(0, u.tile)
                and any(dist(u.pos, w.pos) < 9 for w in r.soldiers(0))]
        if near:
            fight(r, near[0].pos)
        elif _every(r, f"assault:{target}", 10.0):
            r.world.attack([u.id for u in r.soldiers(0) if r.world.can_strike(u, building)], building.id)

    play_until(run, lambda r: bool(r.get("siege_broken")), seconds=1800, act=besiege, what="siege broken")

    if seam == "guard":
        ids = [u.id for u in run.soldiers(0)]
        world.move(ids, seam_building.center)
        play_until(run, lambda r: bool(r.get("seam_settled")), seconds=600, act=defend, what="seam guard posted")
    play_until(run, lambda r: r.won, seconds=900, act=besiege if seam == "mine" else defend, what="Tarnlock won")
    return world.time - start


def solve_maw(run: Run, *, ending: str) -> float:
    """The Maw, three ways: repair the Keystone, fell the pylons, or ring the rifts with vaults."""
    assert ending in ("sealed", "open", "ground")
    world = run.world
    start = world.time
    _hold_workers(run)
    keystone_pos = tuple(run.get("keystone_pos"))

    def enemies_near(r: Run) -> list:
        return [u for side in (1, 2) for u in r.units(side)
                if not u.hidden and u.y < 50 and r.world.is_visible(0, u.tile)]

    def defend(r: Run, point) -> None:
        train(r, B.BARRACKS, U.FOOTMAN, 16)
        if ending != "ground":
            mend_wounded(r)
        near = enemies_near(r)
        fight(r, near[0].pos if near else point, sides=(1, 2))

    if ending == "sealed":
        def repair_act(r: Run) -> None:
            defend(r, tuple(r.get("keystone_center")))
            keystone = building_at(r, 0, B.MAGE_TOWER, keystone_pos)
            if keystone is not None and keystone.hp < keystone.max_hp:
                free = [w.id for w in workers(r) if _free(w)][:3]
                if free:
                    r.world.repair(free, keystone.id)

        play_until(run, lambda r: r.won, seconds=1800, act=repair_act, what="Maw resealed")
    elif ending == "open":
        def demolish(r: Run) -> None:
            near = enemies_near(r)
            if near:
                defend(r, near[0].pos)
                return
            train(r, B.BARRACKS, U.FOOTMAN, 16)
            for pos in (tuple(p) for p in r.get("pylon_pos")):
                pylon = building_at(r, 1, B.FARM, pos)
                if pylon is not None:
                    attack_building(r, pylon.id)
                    ids = [u.id for u in r.soldiers(0) if _idle(u)]
                    if ids:
                        r.world.attack_move(ids, pylon.center)
                    return
            fight(r, tuple(r.get("camp_center")), sides=(1, 2))

        play_until(run, lambda r: r.won, seconds=1800, act=demolish, what="Maw opened")
    else:
        army = [u.id for u in run.soldiers(0)]
        world.move(army, tuple(run.get("keystone_center")))
        plans = [(B.VAULT, tuple(r)) for r in run.get("maw_rifts")]
        ensure_buildings(run, plans, seconds=1200, act=lambda r: defend(r, tuple(r.get("keystone_center"))))

        def hold(r: Run) -> None:
            defend(r, tuple(r.get("keystone_center")))
            for pos in (tuple(p) for p in r.get("maw_rifts")):
                vault = building_at(r, 0, B.VAULT, pos)
                if vault is not None and vault.hp < vault.max_hp:
                    free = [w.id for w in workers(r) if _free(w)][:1]
                    if free:
                        r.world.repair(free, vault.id)

        play_until(run, lambda r: r.won, seconds=1200, act=hold, what="Maw grounded")
    return world.time - start


PATHS: dict[str, dict[str, Callable[[Run], float]]] = {
    "undertow_mill": {"hold": lambda r: solve_mill(r, shutter=False), "shutter": lambda r: solve_mill(r, shutter=True)},
    "undertow_caravan": {"ford": lambda r: solve_caravan(r, blast_dam=False), "dam": lambda r: solve_caravan(r, blast_dam=True)},
    "undertow_grove": {"cut": lambda r: solve_grove(r, cut=True, guardian="ally"),
                       "whole": lambda r: solve_grove(r, cut=False, guardian="core")},
    "undertow_weight": {"cap": lambda r: solve_weight(r, seam="cap"), "mine": lambda r: solve_weight(r, seam="mine"),
                        "guard": lambda r: solve_weight(r, seam="guard")},
    "undertow_maw": {"sealed": lambda r: solve_maw(r, ending="sealed"), "open": lambda r: solve_maw(r, ending="open"),
                     "ground": lambda r: solve_maw(r, ending="ground")},
}
DEFAULT_PATHS = {"undertow_mill": "hold", "undertow_caravan": "ford", "undertow_grove": "cut",
                 "undertow_weight": "cap", "undertow_maw": "sealed"}


def main(argv: list[str]) -> int:
    chosen = [(argv[0], argv[1] if len(argv) > 1 else DEFAULT_PATHS[argv[0]])] if argv else list(DEFAULT_PATHS.items())
    for mission_id, path in chosen:
        run = build_world(CAMPAIGN.mission(mission_id), flags={})
        seconds = PATHS[mission_id][path](run)
        print(f"{mission_id} via {path}: won={run.won} in {seconds:.0f}s of mission time; remembered={run.remembered()}")
        assert run.won
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
