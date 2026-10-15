"""The Undertow: five missions down Vesskar Hollow, one for each of its Steps (``docs/campaign-setting.md``).

Each mission's ``setup`` replaces the generated world with a hand-authored one — its own terrain matrix,
races, theme, ley rifts, magic on — via :func:`_authored`, then places the bespoke board: landmarked
objective sites, story buildings owned by the side the story needs (every pylon the player must destroy
is hostile-owned, so ordinary attack orders work), and its remembered flags defaulted, so exiting after
victory can never skip one.  Choices are map actions (attack a pylon, salvage a camp, fell a strip of
trees, build a vault on a rift, repair the Keystone) that dialogue then confirms.  Wins are explicit:
a resolution trigger sets the mission's ``*_resolved`` variable only in its final phase, and ``win``
reads nothing else.  Sieges are finite scripted bands on one hostile side — no AI side ever fights its
own fictional engineers — and every wild elemental is spawned on a scripted hostile seat with a real
attack order, never left inert as a neutral.  Rebuilt story buildings are recognised by footprint, not
by entity id, so an ordinary rebuild always counts.  ``tools/play_undertow.py`` plays every mission
and ending with public orders; ``tests/warband/test_undertow.py`` drives it.
"""

from __future__ import annotations

import random
from typing import Any

from warband.story.campaign import (
    Campaign, Line, Mission, Objective, Run, Side, Speaker, Trigger,
    after, all_of, any_of, at, objective_done, var,
)
from warband.story import undertow_dialogue as dialogue
from warband.sim.model import Attack, AttackMove, Building, Point, Pos, World, dist, tile_center
from warband.sim.rules import (
    BuildingType as B, Layout, MapTheme, Race, Terrain, UnitType as U, Upgrade,
)

SPEAKERS = {
    "Issa": Speaker("Captain Issa Renn", Race.HUMAN, U.KNIGHT, portrait="campaign/issa.png"),
    "Hasp": Speaker("Mother Hasp", Race.HUMAN, U.PEASANT, portrait="campaign/hasp.png"),
    "Brakk": Speaker("Brakk of the Broken Tooth", Race.ORC, U.CLERIC, portrait="campaign/brakk.png"),
    "Ugga": Speaker("Ugga Salt-Tongue", Race.ORC, U.PEASANT),
    "Wrenna": Speaker("Wrenna Root-Reader", Race.ELF, U.CLERIC, portrait="campaign/wrenna.png"),
    "Pell": Speaker("Sergeant Pell", Race.HUMAN, U.FOOTMAN, player=1),
    "Dagna": Speaker("Dagna Leadhand", Race.DWARF, U.CLERIC, portrait="campaign/dagna.png"),
    "Sella": Speaker("Sella Voss, the Unclencher", Race.HUMAN, U.CLERIC, player=1, portrait="campaign/sella.png"),
}

ACT_1 = "Act I · The Breath Rises"
ACT_2 = "Act II · What the Locks Are For"
ACT_3 = "Act III · The Maw"

SEAM_THRESHOLD = 300  # gold actually hauled out of the endless seam that counts as working it (M4)
GROUND_AETHER = 450   # the aether store the Maw's three vaults must hold between them (M5)


# -- Authoring helpers ----------------------------------------------------------


def _terrain(width: int, height: int) -> list[list[Terrain]]:
    return [[Terrain.GRASS] * width for _ in range(height)]


def _fill(terrain: list[list[Terrain]], x0: int, y0: int, x1: int, y1: int, kind: Terrain) -> None:
    for y in range(max(0, y0), min(len(terrain), y1 + 1)):
        for x in range(max(0, x0), min(len(terrain[0]), x1 + 1)):
            terrain[y][x] = kind


def _disc(terrain: list[list[Terrain]], cx: int, cy: int, radius: int, kind: Terrain) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius and 0 <= y < len(terrain) and 0 <= x < len(terrain[0]):
                terrain[y][x] = kind


def _authored(run: Run, terrain: list[list[Terrain]], *, theme: MapTheme, races: tuple[Race, ...],
              rifts: tuple[Pos, ...], seed: int) -> World:
    """Install this mission's own hand-drawn world in the run, in place of the generated one."""
    world = World(len(terrain[0]), len(terrain), terrain, len(races), races=list(races), theme=theme,
                  magic=True, scripted=True, rng=random.Random(seed))
    world.lay_rifts(rifts)
    run.world = world
    return world


def _put(run: Run, side: int, building_type: B, pos: Pos, *, hp_share: float = 1.0) -> Building:
    """A finished building at exactly *pos*; an authored overlap is a mission bug, so it raises."""
    if not run.footprint_free(building_type, pos):
        raise RuntimeError(f"{building_type.value} at {pos} does not fit the authored map of {run.mission.id}")
    building = run.world.place_building(side, building_type, pos)
    run.world.players[side].alive = True
    if hp_share < 1.0:
        building.hp = max(1, int(building.max_hp * hp_share))
    return building


def _mine(run: Run, building_type: B, pos: Pos) -> Building:
    """A gold deposit at exactly *pos* (nobody's building, filled by the world itself)."""
    return run.world.place_building(None, building_type, pos)


def _purse(run: Run, side: int, gold: int, lumber: int, aether: int = 0) -> None:
    player = run.world.players[side]
    player.gold, player.lumber, player.aether = gold, lumber, aether


def _defaults(run: Run, **vars: Any) -> None:
    """The mission's remembered flags, and any counters, before the first order is given."""
    for key in run.mission.remember:
        run.set(key, False)
    for key, value in vars.items():
        run.set(key, value)


def _landmark(run: Run, id: str, name: str, point: Point, **kw: Any) -> None:
    from warband.story.landmarks import add_landmark

    add_landmark(run, id, name, point, **kw)


def _landmark_state(run: Run, id: str, state: str) -> None:
    from warband.story.landmarks import set_landmark_state

    set_landmark_state(run, id, state)


def _occupied(run: Run, id: str) -> bool:
    from warband.story.landmarks import occupied

    return occupied(run, id)


def _at_footprint(run: Run, side: int, building_type: B, pos: Pos) -> Building | None:
    """The side's finished building standing at *pos*, whoever built this one: rebuilds count."""
    for building in run.buildings(side, building_type):
        if building.pos == pos:
            return building
    return None


def _band_cleared(key: str):
    """Every unit whose id the variable lists is off the map."""
    return lambda run: bool(run.get(key)) and not any(uid in run.world.units for uid in run.get(key))


def _hero_rescue(hero_key: str, hero_type: U, name: str):
    """A downed keeper is dragged to the hall and returns at half health, once (M1/M4's mercy rule)."""

    def do(run: Run) -> None:
        hall = run.hall(0)
        if hall is None:
            return
        band = run.spawn(0, [hero_type], hall.center)
        band[0].hp = band[0].info.hp // 2
        run.set(hero_key, band[0].id)
        run.toast(f"{name} is back on her feet", "Dragged to the hall, half-mended. Once only.")
        run.look(hall.center)

    return do


def _wave(side: int, units: list[U], origin: Point, target_key: str, store_key: str, *say: Any):
    """A scripted band with a real attack order at the point *target_key* holds."""

    def do(run: Run) -> None:
        band = run.spawn(side, units, origin, attack=tuple(run.get(target_key)))
        run.set(store_key, [u.id for u in band])
        if say:
            run.say(*say)
        run.look(origin)

    return do


# -- 1. Millfield (undertow_mill) ------------------------------------------------

MILL_WAVE_ORIGINS = {"sw": (10.5, 27.5), "se": (36.5, 28.5), "s": (24.5, 34.5)}


def _setup_mill(run: Run) -> None:
    terrain = _terrain(48, 40)
    _fill(terrain, 0, 6, 47, 7, Terrain.WATER)          # the Sorrow across the north
    _fill(terrain, 22, 6, 25, 7, Terrain.GRASS)          # its one ford
    for cx, cy in ((5, 33), (24, 37), (42, 33), (3, 3), (44, 3), (38, 18)):
        _disc(terrain, cx, cy, 2, Terrain.TREES)         # groves the beasts come out of
    # Orchard rows frame the village and leave the south fields and both approaches open.
    for x in (7, 9, 11, 33, 35, 37):
        _fill(terrain, x, 20, x, 21, Terrain.TREES)
    _fill(terrain, 0, 12, 2, 27, Terrain.WATER)          # the millrace along the western fields
    for cx, cy in ((2, 10), (45, 12), (44, 23)):
        _disc(terrain, cx, cy, 1, Terrain.ROCK)
    world = _authored(run, terrain, theme=MapTheme.SUMMER, races=(Race.HUMAN, Race.ORC),
                      rifts=((20, 16),), seed=2101)
    hall = _put(run, 0, B.TOWN_HALL, (20, 10))
    _put(run, 0, B.FARM, (15, 10)); _put(run, 0, B.FARM, (26, 10)); _put(run, 0, B.FARM, (15, 20))
    _put(run, 0, B.BARRACKS, (26, 14))
    vault = _put(run, 0, B.VAULT, (20, 16))
    pylon = _put(run, 1, B.FARM, (23, 2))                # bloom-choked, hostile-held, at the race-head on the north bank:
    # attackable, and across the river from every beast-fight, so only a deliberate march fells it
    _mine(run, B.GOLD_MINE, (7, 12))
    band = run.spawn(0, [U.KNIGHT, U.CLERIC] + [U.FOOTMAN] * 3 + [U.ARCHER] * 2, (19.5, 23.5))
    band[2].hp = band[2].info.hp * 2 // 3             # a wounded outrider gives Mend an immediate purpose
    run.spawn(0, [U.PEASANT] * 3, (19.5, 12.5))
    run.spawn(0, [U.PEASANT], (16.5, 22.5))
    world.players[0].upgrades.add(Upgrade.MEND)
    _purse(run, 0, 900, 350, 60)
    _defaults(run, issa=band[0].id, mill_vault_id=vault.id, mill_pylon=pylon.id,
              mill_vault_pos=list(vault.pos), mill_vault_center=list(vault.center),
              mill_farm_center=[16.0, 21.0])
    _landmark(run, "mill_vault", "The straining vault", vault.center, kind="anchor", state="active")
    _landmark(run, "mill_pylon", "Mill lock-pylon", pylon.center, kind="gate", state="active")
    _landmark(run, "mill_hall", "Millfield Town Hall", hall.center, kind="bell", state="active")
    _landmark(run, "mill_fields", "Hasp's south field", (16.0, 21.0), kind="refuge", state="active")
    world.update_vision()


def _mill_shutter(run: Run) -> None:
    """The pylon is down (or the beasts took the vault): the scent dies, the surges stop coming."""
    run.set("mill_decided", True)
    run.set("undertow_mill_vault", False)
    vault = run.world.buildings.get(run.get("mill_vault_id"))
    lost = vault is None
    run.set("undertow_mill_shuttered", not lost)
    run.set("undertow_mill_lost", lost)
    if vault is not None:
        run.replace(vault, 0, B.FARM)  # the shuttered husk: same footprint, draws nothing
    _landmark_state(run, "mill_vault", "ruined")
    if run.get("mill_pylon") not in run.world.buildings:
        _landmark_state(run, "mill_pylon", "ruined")
    run.say(
        Line("Issa", "The vault fell. We lost the lock; we still have the village. Clear the beasts from the fields.",
             when="undertow_mill_lost"),
        Line("Issa", "There it goes. Feel that? The hum's stopped. Whatever they were smelling, it's gone.",
             when="undertow_mill_shuttered"),
        Line("Hasp", "Then we keep the farms and lose the spell-light. I can mill by daylight, Captain."),
    )
    run.toast("The vault fell" if lost else "The vault is shuttered", "Clear the beasts still in Millfield")


def _mill_reserve(run: Run) -> None:
    run.spawn(0, [U.FOOTMAN] * 2, run.home(0))
    run.toast("Millfield's reserve musters", "Two footmen at the hall. There are no more.")


def _mill_first_wave(run: Run) -> None:
    _wave(1, [U.WOLF] * 3, MILL_WAVE_ORIGINS["sw"], "mill_farm_center", "wave_1_band")(run)
    run.toast("Wolves in the south field", "Right-click a wolf to attack.")


def _mill_last_wave(run: Run) -> None:
    _wave(1, [U.WOLF] * 3 + [U.SPIDER] * 2, MILL_WAVE_ORIGINS["s"], "mill_vault_center", "wave_3_band")(run)
    run.toast("The last surge", "Keep the vault standing, or cross the ford to shutter it.")


def _mill_hold(run: Run) -> None:
    run.set("mill_decided", True)
    run.set("undertow_mill_vault", True)
    run.set("mill_resolved", True)
    run.say(Line("Issa", "That's the last of them, and the vault still stands. Millfield keeps its lock — and its crew."))


MILL = Mission(
    dialogue_art="campaign/scenes/millfield.webp",
    id="undertow_mill", title="Millfield", act=ACT_1,
    sides=(Side("Millfield", Race.HUMAN), Side("The Straining", Race.ORC)),
    size="Small", theme=MapTheme.SUMMER, layout=Layout.PLAINS, seed=2101,
    briefing=dialogue.MILL_BRIEFING,
    debrief=dialogue.MILL_DEBRIEF,
    setup=_setup_mill,
    objectives=(
        Objective("wave_1", "Defend Hasp's south field",
                  _band_cleared("wave_1_band")),
        Objective("mend", "Cast Mend on a wounded ally",
                  lambda run: Upgrade.MEND in run.world.players[0].cooldowns, optional=True),
        Objective("hold", "Hold the vault through the final surge",
                  lambda run: bool(run.get("undertow_mill_vault")),
                  shown=lambda run: "wave_2" in run.fired, optional=True),
        Objective("shutter", "Or destroy the north-bank lock-pylon",
                  lambda run: run.get("mill_pylon") not in run.world.buildings,
                  shown=lambda run: "wave_2" in run.fired, optional=True),
        Objective("clear", "Clear the last beasts from Millfield",
                  lambda run: bool(run.get("mill_resolved")),
                  shown=lambda run: "wave_2" in run.fired),
        Objective("issa", "Issa must survive (one rescue)", lambda run: bool(run.get("mill_resolved")),
                  failed=lambda run: "issa_rescue" in run.fired and run.unit("issa") is None, optional=True),
        Objective("hall", "The Town Hall must stand", lambda run: bool(run.get("mill_resolved")),
                  failed=lambda run: run.hall(0) is None, optional=True),
    ),
    triggers=(
        Trigger("wave_1", at(4), _mill_first_wave),
        Trigger("wave_2", all_of(after("wave_1", 25), any_of(objective_done("wave_1"), at(180)),
                                 lambda run: not run.get("mill_decided")),
                _wave(1, [U.SPIDER] * 2 + [U.WOLF] * 2, MILL_WAVE_ORIGINS["se"], "mill_vault_center", "wave_2_band",
                      Line("Hasp", "They ran past my farm. It's the vault they want. "
                                   "Don't spend my people saving a machine, Issa."),
                      Line("Issa", "Hold the vault through one last surge to keep our spell-light. "
                                   "Or cross the north ford and destroy the lock-pylon to stop the surges. "
                                   "You can change course until the pylon falls. The village comes first."))),
        Trigger("wave_3", all_of(after("wave_2", 60), any_of(_band_cleared("wave_2_band"), after("wave_2", 180)),
                                 lambda run: not run.get("mill_decided")),
                _mill_last_wave),
        Trigger("shuttered", all_of(lambda run: not run.get("mill_decided"),
                                    lambda run: run.get("mill_pylon") not in run.world.buildings
                                    or run.get("mill_vault_id") not in run.world.buildings), _mill_shutter),
        Trigger("held", all_of(_band_cleared("wave_3_band"), lambda run: not run.units(1),
                               lambda run: not run.get("mill_decided")), _mill_hold),
        Trigger("cleared", all_of(lambda run: bool(run.get("mill_decided")) and not run.get("undertow_mill_vault"),
                                  lambda run: not run.units(1)),
                lambda run: run.set("mill_resolved", True)),
        Trigger("issa_rescue", lambda run: run.unit("issa") is None and run.hall(0) is not None,
                _hero_rescue("issa", U.KNIGHT, "Captain Renn")),
        Trigger("reserve", all_of(at(20), lambda run: not run.soldiers(0), lambda run: not run.get("mill_resolved")),
                _mill_reserve),
    ),
    win=var("mill_resolved", True),
    remember=("undertow_mill_vault", "undertow_mill_shuttered", "undertow_mill_lost"),
    opening_focus=(20.0, 21.0),
)
# -- 2. The Salt Caravan (undertow_caravan) -------------------------------------

MESA = (44, 16, 58, 30)  # x0, y0, x1, y1 inclusive: where the new camp must stand
FORDS = {"north": 8, "middle": 23, "south": 38}  # y of each two-tile ford in the river x=30..33


def _in_mesa(x: float, y: float) -> bool:
    return MESA[0] <= x <= MESA[2] and MESA[1] <= y <= MESA[3]


def _caravan_camp_ready(run: Run) -> bool:
    return (any(_in_mesa(*hall.pos) for hall in run.buildings(0, B.TOWN_HALL))
            and sum(_in_mesa(*farm.pos) for farm in run.buildings(0, B.FARM)) >= 3)


def _caravan_drovers_ready(run: Run) -> bool:
    return sum(_in_mesa(worker.x, worker.y) for worker in run.units(0, U.PEASANT)) >= 5


def _setup_caravan(run: Run) -> None:
    terrain = _terrain(64, 48)
    _fill(terrain, 30, 0, 33, 47, Terrain.WATER)                       # the Sorrow, running south
    for row in FORDS.values():
        _fill(terrain, 30, row, 33, row + 1, Terrain.GRASS)            # three narrow fords, bank to bank
    _fill(terrain, 42, 14, 60, 14, Terrain.ROCK)                       # the Broken Tooth mesa's rim
    _fill(terrain, 42, 32, 60, 32, Terrain.ROCK)
    _fill(terrain, 42, 14, 42, 32, Terrain.ROCK)
    _fill(terrain, 60, 14, 60, 32, Terrain.ROCK)
    _fill(terrain, 42, 22, 43, 25, Terrain.GRASS)                      # its one ramp, facing the middle ford
    for cx, cy in ((10, 6), (20, 42), (52, 40), (6, 40)):
        _disc(terrain, cx, cy, 3, Terrain.TREES)
    world = _authored(run, terrain, theme=MapTheme.WASTELAND, races=(Race.ORC, Race.HUMAN, Race.ORC),
                      rifts=(), seed=2202)
    # The Old Camp: raised for the third side, then resigned — with three seats its buildings stand abandoned.
    _put(run, 2, B.TOWN_HALL, (6, 18)); _put(run, 2, B.BARRACKS, (12, 18))
    _put(run, 2, B.FARM, (6, 24)); _put(run, 2, B.FARM, (12, 24))
    run.spawn(2, [U.PEASANT], (10.5, 28.5))
    world.resign(2)
    world.take_events()
    # The Open Hand's dam crew on the north ford's east bank, and the south ford's bloom-spiders.
    dam_pylon = _put(run, 1, B.FARM, (36, 7))
    _put(run, 1, B.BARRACKS, (41, 4))
    run.spawn(1, [U.FOOTMAN] * 3, (38.5, 11.5), hold=True)
    run.spawn(1, [U.SPIDER] * 2, (37.5, 38.5), hold=True)
    band = run.spawn(0, [U.CLERIC] + [U.PEASANT] * 6 + [U.FOOTMAN] * 4 + [U.ARCHER] * 2 + [U.KNIGHT], (10.5, 33.5))
    _mine(run, B.GOLD_MINE, (54, 17))
    _purse(run, 0, 300, 200)
    _defaults(run, brakk=band[0].id, dam_pylon=dam_pylon.id, mesa_center=[51.0, 23.0],
              middle_ford=[31.5, 23.5], ford_east=[35.5, 23.5],
              north_ford=[31.5, FORDS["north"] + .5], south_ford=[31.5, FORDS["south"] + .5])
    _landmark(run, "old_camp", "The Old Camp (salvage it)", (10.5, 21.5), kind="memorial", state="active")
    _landmark(run, "mesa", "The Broken Tooth mesa", (51.0, 23.0), kind="refuge", radius=6, state="active")
    _landmark(run, "dam_pylon", "Hasp's millpond dam (blast floods the camp)", dam_pylon.center,
              kind="gate", state="active")
    _landmark(run, "middle_ford", "The causeway ford", (31.5, 23.5), kind="gate", state="open")
    world.update_vision()


def _caravan_rockfall(run: Run) -> None:
    # Two farm-sized tumbles side by side seal the four-wide ford bank to bank.
    rocks = [run.world.place_building(1, B.FARM, (x, FORDS["middle"])) for x in (30, 32)]
    run.set("rockfall", [rock.id for rock in rocks])
    _landmark_state(run, "middle_ford", "ruined")
    run.say(
        Line("Ugga", "Rockfall! Right across the causeway — and pennants stuck in it. Somebody signed that."),
        Line("Brakk", "The Open Hand. They drop stone on roads and wave people back. They have not chased one drover. "
                      "Think on why, while we blast through — or walk the south ford, past the spiders."),
    )
    run.look((31.5, 23.5))


def _caravan_sappers(run: Run) -> None:
    run.spawn(0, [U.SAPPER] * 2, (3.5, 24.5))
    run.toast("Goblin sappers join the caravan", "Their blast fells buildings. One for the rockfall — if you spend it")
    run.say(Line("Ugga", "Sappers! One blast opens the causeway. That leaves one spare. "
                         "Mind where he stands; I've only just packed those timbers."))


def _caravan_stores(run: Run) -> None:
    """Strip complete: what the drovers packed flat and carried — enough, with the salvage, for the new camp."""
    player = run.world.players[0]
    player.gold += 2600
    player.lumber += 1600
    _landmark_state(run, "old_camp", "ruined")
    run.say(
        Line("Ugga", "Last peg's out. I've kept the old doorpost too. Help me with this end, will you?"),
        Line("Brakk", "Up to the Tooth. Hall and three farms, with five drovers there to finish them. Check who's still on the road."),
    )
    run.toast("Packed stores unpacked", "+2600 gold, +1600 lumber for the mesa camp")


def _caravan_flood(run: Run) -> None:
    """The dam goes: the millpond takes the Open Hand's north camp off the map with it."""
    run.set("undertow_dam", True)
    run.world.resign(1)
    run.world.take_events()
    _landmark_state(run, "dam_pylon", "ruined")
    run.say(
        Line("Ugga", "The north camp's gone. That's our crossing. Come on, before the mud settles."),
        Line("Brakk", "Someone needs to tell Hasp before the night shift. We'll go back when our people are across."),
    )


def _caravan_stragglers(run: Run) -> None:
    run.spawn(0, [U.PEASANT] * 3, (3.5, 33.5))
    run.toast("Stragglers catch up", "Three more drovers from the pans. Mesa or bust.")


def _caravan_resolved(run: Run) -> None:
    run.set("caravan_resolved", True)
    _landmark_state(run, "mesa", "open")


CARAVAN = Mission(
    dialogue_art="campaign/scenes/saltmarch.webp",
    id="undertow_caravan", title="The Salt Caravan", act=ACT_1,
    sides=(Side("The Saltmarches", Race.ORC), Side("The Open Hand", Race.HUMAN), Side("The Old Camp", Race.ORC)),
    size="Medium", theme=MapTheme.WASTELAND, layout=Layout.CROSSINGS, seed=2202,
    briefing=dialogue.CARAVAN_BRIEFING + (
        Line("Ugga", "A finished Great Hall trains replacement drovers. Until then, stragglers can join us once. "
                     "Lose the last drover after that, with no hall to train another, and the caravan is lost."),
    ),
    debrief=dialogue.CARAVAN_DEBRIEF,
    setup=_setup_caravan,
    objectives=(
        Objective("strip", "Salvage the Old Camp's four ruins",
                  lambda run: not any(b.player == 2 for b in run.world.buildings.values())),
        Objective("camp", "Mesa: Hall + 3 Pig Farms",
                  _caravan_camp_ready,
                  shown=objective_done("strip"), ongoing=True),
        Objective("drovers", "5 drovers on the mesa",
                  _caravan_drovers_ready,
                  shown=objective_done("strip"), ongoing=True),
        Objective("dam", "Optional: blast the dam",
                  lambda run: bool(run.get("undertow_dam")), optional=True),
        Objective("brakk", "Brakk must survive", lambda run: bool(run.get("caravan_resolved")),
                  failed=lambda run: run.unit("brakk") is None, optional=True),
        Objective("builders", "Keep a drover or a Hall",
                  lambda run: bool(run.get("caravan_resolved")),
                  failed=lambda run: "stragglers" in run.fired and not run.units(0, U.PEASANT)
                  and run.hall(0) is None, optional=True),
    ),
    triggers=(
        Trigger("rockfall", any_of(lambda run: any(u.x >= 28 for u in run.units(0)), at(240)), _caravan_rockfall),
        Trigger("sappers", after("rockfall", 2), _caravan_sappers),
        Trigger("stores", objective_done("strip"), _caravan_stores),
        Trigger("flood", lambda run: run.get("dam_pylon") not in run.world.buildings, _caravan_flood),
        Trigger("harry_1", all_of(at(200), lambda run: run.world.players[1].alive),
                _wave(1, [U.FOOTMAN] * 3 + [U.ARCHER], (38.5, 9.5), "ford_east", "harry_1_band")),
        Trigger("harry_2", all_of(at(420), lambda run: run.world.players[1].alive),
                _wave(1, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, (38.5, 9.5), "ford_east", "harry_2_band")),
        Trigger("stragglers", all_of(at(30), lambda run: len(run.units(0, U.PEASANT)) < 5), _caravan_stragglers),
        Trigger("resolved", all_of(objective_done("strip"), _caravan_camp_ready, _caravan_drovers_ready),
                _caravan_resolved),
    ),
    win=var("caravan_resolved", True),
    remember=("undertow_dam",),
)


# -- 3. The Grove That Drinks (undertow_grove) ------------------------------------

STRIP: tuple[Pos, ...] = tuple((x, 27) for x in range(40, 48))  # the marked firebreak line
STRIP_NEEDED = 6


def _felled(run: Run) -> int:
    return sum(1 for tile in STRIP if run.world.terrain_at(tile) is not Terrain.TREES)


def _setup_grove(run: Run) -> None:
    terrain = [[Terrain.TREES] * 64 for _ in range(48)]
    _disc(terrain, 18, 14, 9, Terrain.GRASS)                    # the heart-clearing
    _fill(terrain, 10, 22, 56, 23, Terrain.GRASS)               # the spiral path, unrolled
    _fill(terrain, 17, 14, 55, 15, Terrain.GRASS)               # east arm, to the stone ring
    _fill(terrain, 29, 23, 30, 36, Terrain.GRASS)               # south arm, to the woodcutters
    _disc(terrain, 30, 38, 6, Terrain.GRASS)
    _disc(terrain, 52, 14, 5, Terrain.GRASS)                    # the Guardian's ring
    _fill(terrain, 38, 25, 52, 26, Terrain.GRASS)               # working ground north of the strip
    _fill(terrain, 44, 24, 45, 24, Terrain.GRASS)               # the ride joining it to the path
    world = _authored(run, terrain, theme=MapTheme.SUMMER, races=(Race.ELF, Race.HUMAN, Race.ORC),
                      rifts=((23, 17),), seed=2303)
    hall = _put(run, 0, B.TOWN_HALL, (13, 10))
    _put(run, 0, B.CHURCH, (19, 9))                             # the Moonwell
    _put(run, 0, B.FARM, (10, 16)); _put(run, 0, B.FARM, (14, 17)); _put(run, 0, B.FARM, (24, 10))
    _put(run, 0, B.BARRACKS, (20, 19))
    _put(run, 0, B.VAULT, (23, 17))                             # the grown Third Lock
    _mine(run, B.GOLD_MINE, (8, 8))
    band = run.spawn(0, [U.CLERIC] + [U.TREANT] * 2 + [U.FOOTMAN] * 4 + [U.ARCHER] * 3, (17.5, 14.5))
    run.spawn(0, [U.PEASANT] * 3, (15.5, 12.5))
    mill = _put(run, 1, B.LUMBER_MILL, (28, 36))
    cutters = run.spawn(1, [U.PEASANT] * 4, (30.5, 41.5))
    guard = run.spawn(1, [U.FOOTMAN] * 3, (33.5, 41.5), hold=True)  # south of the mill: a parley from the north stays out of idle bowshot
    for cutter, tile in zip(cutters, [(25, 42), (27, 45), (30, 45), (33, 45)]):
        world.harvest([cutter.id], tile)
    guardian = world.spawn_unit(world.neutral, U.ANCIENT_GUARDIAN, tile_center((52, 14)))
    guardian.hp = 700  # bloom-sick and old: a hard fight for two treants, not an impossible one
    world.players[0].upgrades.add(Upgrade.ENTANGLE)
    _purse(run, 0, 700, 300, 45)
    _defaults(run, wrenna=band[0].id, pell=guard[0].id, mill_id=mill.id, guardian=guardian.id,
              guardian_hp=700, guardian_pos=[52.5, 14.5], cutter_camp=[29.5, 37.5],
              grove_crew=[unit.id for unit in cutters + guard],
              moonwell_center=[20.5, 10.5], moon_hall_center=list(hall.center), strip_tiles=[list(t) for t in STRIP])
    _landmark(run, "moon_hall", "Moon Hall", hall.center, kind="bell", state="active")
    _landmark(run, "firebreak", "The marked firebreak line", (44.5, 27.5), kind="gate", radius=5, state="active")
    _landmark(run, "cutter_camp", "Woodcutters' camp", mill.center, kind="anchor", state="active")
    _landmark(run, "guardian_ring", "The Ancient in the stone ring", (52.5, 14.5), kind="memorial", radius=5, state="active")
    world.update_vision()


def _grove_parley(run: Run) -> None:
    run.set("parleyed", True)
    run.say(*dialogue.GROVE_PARLEY)
    run.toast("Parley at the woodcutters' camp", "Fell the marked line, or muster at the Moon Hall and weather the bloom")
    # The crew strikes camp and withdraws for good; the mill stands empty behind them.
    run.world.resign(1)
    run.world.take_events()
    _landmark_state(run, "cutter_camp", "ruined")


def _grove_hostilities(run: Run) -> bool:
    mill = run.world.buildings.get(run.get("mill_id"))
    return (mill is None or mill.hp < mill.max_hp
            or any(unit.hp < unit.max_hp for unit in run.units(1))
            or any(unit_id not in run.world.units for unit_id in run.get("grove_crew", [])))


def _grove_peaceful_approach(run: Run) -> bool:
    return any(dist(unit.pos, tuple(run.get("cutter_camp"))) <= 11
               and not any(isinstance(order, (Attack, AttackMove)) for order in unit.orders)
               for unit in run.units(0))


def _grove_rout_aftermath(run: Run) -> None:
    run.set("grove_order_revealed", True)
    _landmark_state(run, "cutter_camp", "ruined")
    run.say(*dialogue.GROVE_ROUT_AFTERMATH)


def _grove_bloom(run: Run) -> None:
    cut = _felled(run) >= STRIP_NEEDED
    run.set("undertow_grove_cut", cut)
    run.set("bloom_started", True)
    _landmark_state(run, "firebreak", "open" if cut else "ruined")
    roster = [U.WOLF] * 3 if cut else [U.WOLF] * 3 + [U.SPIDER] * 2
    band = run.spawn(2, roster, (55.5, 22.5), attack=tuple(run.get("moonwell_center")))
    run.set("bloom_1_band", [u.id for u in band])
    run.say(
        Line("Wrenna", "There — violet in the sap, uphill wind. The bloom-front is here." if not cut else
             "The bloom laps at the stumps and finds no road in. What's left of it is coming anyway — finish it."),
    )
    run.look((55.5, 22.5))


def _grove_bloom_2(run: Run) -> None:
    band = run.spawn(2, [U.AETHER_ELEMENTAL] * 2 + [U.SPIDER] * 2, (45.5, 22.5),
                     attack=tuple(run.get("moonwell_center")))
    run.set("bloom_2_band", [u.id for u in band])
    run.say(Line("Wrenna", "The rift is shedding elementals — pressure with nowhere to go. Hold the Moonwell!"))


def _grove_guardian_ally(run: Run) -> None:
    run.set("undertow_guardian_ally", True)
    # The Ancient leaves the ring for the deep trees until the Maw: an ally that stayed on the map as a
    # neutral body would be fought by accident by the first escort to walk through (no bounty, no core).
    run.world.clear_player(run.world.neutral)
    _landmark_state(run, "guardian_ring", "open")
    run.say(
        Line("Wrenna", "Easy, old one. Nobody's raising a blade. …There. Do you see? It kneels — and goes into the deep "
                       "trees to wait. When we go down to the Maw, Captain, the grove sends its eldest with us."),
    )
    run.toast("The Ancient Guardian kneels", "It will walk with the Keepers at the Maw")


def _grove_guardian_core(run: Run) -> None:
    run.set("undertow_guardian_core", True)
    _landmark_state(run, "guardian_ring", "ruined")
    run.say(Line("Wrenna", "Its heart is still warm. Wrap it. Dagna may be able to set it into the Maw's works. "
                           "I'll stay here a moment."))
    run.toast("The Guardian's heart-stone", "Carried to the Maw: a vault's worth of holding")


GROVE = Mission(
    dialogue_art="campaign/scenes/deep-grove.webp",
    id="undertow_grove", title="The Grove That Drinks", act=ACT_2,
    sides=(Side("Deep Grove", Race.ELF), Side("The Woodcutters", Race.HUMAN), Side("The Bloom-Front", Race.ORC)),
    size="Medium", theme=MapTheme.SUMMER, layout=Layout.FOREST, seed=2303,
    briefing=dialogue.GROVE_BRIEFING,
    debrief=dialogue.GROVE_DEBRIEF,
    setup=_setup_grove,
    objectives=(
        Objective("parley_or_rout", "Woodcutters: parley or raze their mill",
                  lambda run: bool(run.get("parleyed")) or run.get("mill_id") not in run.world.buildings),
        Objective("cut", f"Fell {STRIP_NEEDED} firebreak trees",
                  lambda run: _felled(run) >= STRIP_NEEDED,
                  shown=all_of(objective_done("parley_or_rout"), var("grove_intent", "cut")), optional=True),
        Objective("weather", "Muster at Moon Hall",
                  lambda run: bool(run.get("grove_resolved")) and not run.get("undertow_grove_cut"),
                  shown=all_of(objective_done("parley_or_rout"), var("grove_intent", "whole")), optional=True),
        Objective("guardian", "Ancient: courtesy or combat",
                  lambda run: bool(run.get("undertow_guardian_ally") or run.get("undertow_guardian_core")),
                  optional=True),
        Objective("survive_bloom", "Weather the bloom-front", lambda run: bool(run.get("grove_resolved")),
                  shown=lambda run: bool(run.get("bloom_started"))),
        Objective("wrenna", "Wrenna must survive", lambda run: bool(run.get("grove_resolved")),
                  failed=lambda run: run.unit("wrenna") is None, optional=True),
        Objective("hall", "The Moon Hall must stand", lambda run: bool(run.get("grove_resolved")),
                  failed=lambda run: run.hall(0) is None, optional=True),
    ),
    triggers=(
        Trigger("first_blood", all_of(lambda run: not run.get("parleyed"), _grove_hostilities),
                lambda run: run.set("grove_first_blood", True)),
        Trigger("parley", all_of(_grove_peaceful_approach, lambda run: not run.get("grove_first_blood")),
                _grove_parley),
        Trigger("rout_aftermath", all_of(lambda run: run.get("mill_id") not in run.world.buildings,
                                         lambda run: not run.get("parleyed")), _grove_rout_aftermath),
        Trigger("grove_plan", all_of(objective_done("parley_or_rout"),
                                     lambda run: bool(run.get("parleyed") or run.get("grove_order_revealed"))),
                lambda run: run.say(*dialogue.GROVE_PLAN)),
        Trigger("bloom", any_of(
            all_of(var("grove_intent", "cut"), lambda run: _felled(run) >= STRIP_NEEDED),
            all_of(var("grove_intent", "whole"), after("grove_plan", 15),
                   lambda run: _occupied(run, "moon_hall"))), _grove_bloom),
        Trigger("bloom_2", all_of(_band_cleared("bloom_1_band"), lambda run: not run.get("undertow_grove_cut"),
                                  lambda run: bool(run.get("bloom_started"))), _grove_bloom_2),
        Trigger("resolved", all_of(lambda run: bool(run.get("bloom_started")),
                                   lambda run: not run.units(2),
                                   lambda run: run.get("undertow_grove_cut") or "bloom_2" in run.fired),
                lambda run: run.set("grove_resolved", True)),
        Trigger("guardian_approach", all_of(lambda run: run.near("wrenna", tuple(run.get("guardian_pos")), 6.0),
                                            lambda run: not any(u.id != run.get("wrenna")
                                                                and dist(u.pos, tuple(run.get("guardian_pos"))) <= 9
                                                                for u in run.soldiers(0)),
                                            lambda run: (g := run.world.units.get(run.get("guardian"))) is not None
                                            and g.hp >= run.get("guardian_hp")), _grove_guardian_ally),
        Trigger("guardian_slain", all_of(lambda run: run.get("guardian") not in run.world.units,
                                         lambda run: not run.get("undertow_guardian_ally")), _grove_guardian_core),
    ),
    win=var("grove_resolved", True),
    remember=("undertow_grove_cut", "undertow_guardian_ally", "undertow_guardian_core"),
)
# -- 4. The Weight (undertow_weight) ----------------------------------------------

WEIGHT_RIFTS: tuple[Pos, ...] = ((24, 14), (36, 20), (24, 26))
SEAM_RIFT: Pos = (52, 11)
SEAM_POS: Pos = (52, 4)


def _weights_standing(run: Run) -> int:
    """Finished vaults on the Three Weights' rifts, rebuilt ones included (footprints, not ids)."""
    return sum(1 for rift in WEIGHT_RIFTS if _at_footprint(run, 0, B.VAULT, rift) is not None)


def _weight_siege_active(run: Run) -> bool:
    return not run.get("siege_broken") and run.get("enemy_hall") in run.world.buildings


def _weight_siege_destroyed(run: Run) -> bool:
    return (run.get("enemy_hall") not in run.world.buildings
            or run.get("enemy_workshop") not in run.world.buildings
            and all(_band_cleared(f"band_{i}_band")(run) for i in (1, 2, 3)))


def _weight_attackers_cleared(run: Run) -> bool:
    keys = [f"band_{i}_band" for i in (1, 2, 3)]
    keys.extend(f"shed_{rift[0]}_{rift[1]}" for rift in WEIGHT_RIFTS[:2])
    return not any(unit_id in run.world.units for key in keys for unit_id in run.get(key, []))


def _poll_seam(run: Run) -> int:
    """Count gold actually hauled out of the endless seam, trip by trip, into a saved variable.

    A worker is seen inside the seam, then seen carrying: that load is counted once.  No other gold
    source can contaminate the count, and spending cannot un-count it."""
    seam_id = run.get("seam_id")
    inside: dict[str, bool] = run.vars.setdefault("seam_inside", {})
    total = int(run.get("seam_gold", 0))
    for worker in run.units(0, U.PEASANT):
        key = str(worker.id)
        if worker.inside == seam_id:
            inside[key] = True
        elif inside.get(key) and worker.carrying is not None and worker.carry:
            total += worker.carry
            inside[key] = False
    stale = [k for k in inside if int(k) not in run.world.units]
    for key in stale:
        del inside[key]
    run.set("seam_gold", total)
    return total


def _setup_weight(run: Run) -> None:
    terrain = _terrain(64, 48)
    _fill(terrain, 0, 0, 63, 2, Terrain.ROCK)                       # the north wall of the basin
    _fill(terrain, 58, 3, 63, 20, Terrain.ROCK)                     # the seam's rock pocket shoulder
    _fill(terrain, 0, 33, 63, 34, Terrain.TREES)                    # the tree-ring, with two gates
    _fill(terrain, 20, 33, 23, 34, Terrain.GRASS)
    _fill(terrain, 40, 33, 43, 34, Terrain.GRASS)
    for cx, cy in ((8, 40), (56, 40), (46, 8)):
        _disc(terrain, cx, cy, 2, Terrain.TREES)
    world = _authored(run, terrain, theme=MapTheme.WINTER, races=(Race.DWARF, Race.HUMAN),
                      rifts=WEIGHT_RIFTS + (SEAM_RIFT,), seed=2404)
    hall = _put(run, 0, B.TOWN_HALL, (7, 5))
    _put(run, 0, B.BARRACKS, (13, 5)); _put(run, 0, B.BLACKSMITH, (7, 11)); _put(run, 0, B.WORKSHOP, (13, 11))
    _put(run, 0, B.FARM, (7, 17)); _put(run, 0, B.FARM, (11, 17)); _put(run, 0, B.FARM, (15, 17))
    _put(run, 0, B.TOWER, (20, 30)); _put(run, 0, B.TOWER, (41, 30))
    for rift in WEIGHT_RIFTS:
        _put(run, 0, B.VAULT, rift)
    seam = _mine(run, B.GOLD_SEAM, SEAM_POS)
    band = run.spawn(0, [U.CLERIC] + [U.FOOTMAN] * 4 + [U.ARCHER] * 2 + [U.CATAPULT], (18.5, 22.5))
    run.spawn(0, [U.PEASANT] * 5, (10.5, 15.5))
    enemy_hall = _put(run, 1, B.TOWN_HALL, (28, 40))
    workshop = _put(run, 1, B.WORKSHOP, (20, 40))
    _put(run, 1, B.BARRACKS, (35, 40)); _put(run, 1, B.FARM, (40, 41))
    run.spawn(1, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, (30.5, 38.5), hold=True)
    world.players[0].upgrades.update({Upgrade.FLAME_STRIKE, Upgrade.DEEP_MINING})
    _purse(run, 0, 1200, 600, 45)
    _defaults(run, dagna=band[0].id, seam_id=seam.id, seam_rift=list(SEAM_RIFT), seam_gold=0, seam_inside={},
              enemy_hall=enemy_hall.id, enemy_workshop=workshop.id, enemy_camp=list(enemy_hall.center),
              weight_target=[25.0, 15.0], hall_center=list(hall.center))
    for i, rift in enumerate(WEIGHT_RIFTS):
        _landmark(run, f"weight_{i + 1}", f"Weight {'I II III'.split()[i]}", (rift[0] + 1.0, rift[1] + 1.0),
                  kind="anchor", state="active")
    _landmark(run, "seam", "The endless seam", seam.center, kind="anchor", radius=5, state="active")
    _landmark(run, "seam_rift", "The seam's throat rift (cap it here)", (SEAM_RIFT[0] + 1.0, SEAM_RIFT[1] + 1.0),
              kind="gate", state="active")
    world.update_vision()


def _weight_band(units: list[U], store_key: str, *say: Any):
    return _wave(1, units, (30.5, 37.5), "weight_target", store_key, *say)


def _weight_confession(run: Run) -> None:
    run.say(*dialogue.WEIGHT_CONFESSION)
    run.look(run.world.buildings[run.get("seam_id")].center)


def _weight_shed(origin_rift: Pos):
    def do(run: Run) -> None:
        band = run.spawn(1, [U.AETHER_ELEMENTAL], (origin_rift[0] + 1.0, origin_rift[1] + 1.0),
                         attack=tuple(run.get("hall_center")))
        run.set(f"shed_{origin_rift[0]}_{origin_rift[1]}", [u.id for u in band])
        run.say(Line("Dagna", "There! The rift sheds its breath unshaped. That is what pressure looks like, Captain."))

    return do


def _weight_settle(kind: str):
    def do(run: Run) -> None:
        if kind == "cap":
            run.set("undertow_seam_capped", True)
            _landmark_state(run, "seam_rift", "open")
            run.say(Line("Dagna", "Cap's seated. Leave the complete survey with the watch. I'll sign it before we go."))
        elif kind == "mine":
            run.set("undertow_seam_mined", True)
            run.say(Line("Dagna", "Three hundred hauled. Pay the crews. Keep those weights; we'll need them to judge the pressure at the Maw."))
        else:
            run.set("undertow_seam_guarded", True)
            run.say(Line("Dagna", "Guard posted. No more carts. I'll leave the watch a gauge; the pressure still needs tending."))
        run.set("seam_settled", kind)
        _landmark_state(run, "seam", "open")

    return do


def _weight_siege_broken(run: Run) -> None:
    run.set("siege_broken", True)
    run.toast("The siege train is broken", "Clear its remaining attackers, then settle the seam")


WEIGHT = Mission(
    dialogue_art="campaign/scenes/tarnlock.webp",
    id="undertow_weight", title="The Weight", act=ACT_2,
    sides=(Side("Tarnlock", Race.DWARF), Side("The Open Hand", Race.HUMAN)),
    size="Medium", theme=MapTheme.WINTER, layout=Layout.BASTION, seed=2404,
    briefing=dialogue.WEIGHT_BRIEFING + (
        Line("", "Raze the southern hall, or raze the workshop and beat three bands. Clear the remaining attackers. "
                 "Settle the seam by building a Rune Vault on its rift, hauling 300 gold, or choosing a guard and posting soldiers at the face after the siege."),
    ),
    debrief=dialogue.WEIGHT_DEBRIEF,
    setup=_setup_weight,
    objectives=(
        Objective("weights", "Keep two Weights standing",
                  lambda run: bool(run.get("weight_resolved")),
                  failed=lambda run: _weights_standing(run) < 2, optional=True),
        Objective("siege", "Break siege; clear attack bands",
                  lambda run: bool(run.get("siege_broken")) and _weight_attackers_cleared(run)),
        Objective("seam", "Settle the endless seam", lambda run: bool(run.get("seam_settled"))),
        Objective("dagna", "Dagna: one rescue", lambda run: bool(run.get("weight_resolved")),
                  failed=lambda run: "dagna_rescue" in run.fired and run.unit("dagna") is None, optional=True),
        Objective("hall", "Keep the Deep Hold standing", lambda run: bool(run.get("weight_resolved")),
                  failed=lambda run: run.hall(0) is None, optional=True),
    ),
    triggers=(
        Trigger("sella_exchange", at(1), lambda run: run.say(*dialogue.WEIGHT_SELLA_EXCHANGE)),
        Trigger("band_1", all_of(at(20), _weight_siege_active), _weight_band([U.FOOTMAN] * 4 + [U.ARCHER] * 2, "band_1_band",
                                               Line("Dagna", "Past the towers, straight for Weight I. Wrenna's root-map showed her the connections. Get a crew over there."))),
        Trigger("band_2", all_of(_weight_siege_active, any_of(_band_cleared("band_1_band"), after("band_1", 180))),
                _weight_band([U.FOOTMAN] * 5 + [U.ARCHER] * 2, "band_2_band")),
        Trigger("band_3", all_of(_weight_siege_active, any_of(_band_cleared("band_2_band"), after("band_2", 180))),
                _weight_band([U.FOOTMAN] * 5 + [U.ARCHER] * 2 + [U.CATAPULT], "band_3_band",
                             Line("Dagna", "Their last band, and a thrower with it. Spend this and their powder's done."))),
        Trigger("confession", any_of(lambda run: "band_2" in run.fired,
                                      lambda run: int(run.get("seam_gold", 0)) >= 60,
                                      lambda run: bool(run.get("siege_broken") or run.get("seam_settled")),
                                      lambda run: any(dist(unit.pos, run.world.buildings[run.get("seam_id")].center) <= 8
                                                      for unit in run.units(0))),
                _weight_confession),
        Trigger("settle_cap", lambda run: _at_footprint(run, 0, B.VAULT, SEAM_RIFT) is not None, _weight_settle("cap")),
        Trigger("settle_mine", lambda run: _poll_seam(run) >= SEAM_THRESHOLD, _weight_settle("mine")),
        Trigger("shed_1", lambda run: _weights_standing(run) < 3, _weight_shed(WEIGHT_RIFTS[0])),
        Trigger("shed_2", lambda run: _weights_standing(run) < 2 or int(run.get("seam_gold", 0)) >= 150,
                _weight_shed(WEIGHT_RIFTS[1])),
        Trigger("siege_broken", _weight_siege_destroyed, _weight_siege_broken),
        Trigger("settle_guard", all_of(var("seam_intent", "guard"), lambda run: not run.get("seam_settled"),
                                       lambda run: _occupied(run, "seam"), lambda run: bool(run.get("siege_broken")),
                                       _weight_attackers_cleared),
                _weight_settle("guard")),
        Trigger("dagna_rescue", lambda run: run.unit("dagna") is None and run.hall(0) is not None,
                _hero_rescue("dagna", U.CLERIC, "Dagna Leadhand")),
        Trigger("resolved", all_of(lambda run: "confession" in run.fired, lambda run: bool(run.get("siege_broken")),
                                   lambda run: bool(run.get("seam_settled")), _weight_attackers_cleared),
                lambda run: run.set("weight_resolved", True)),
    ),
    win=var("weight_resolved", True),
    remember=("undertow_seam_capped", "undertow_seam_mined", "undertow_seam_guarded"),
)


# -- 5. The Maw (undertow_maw) -----------------------------------------------------

MAW_RIFTS: tuple[Pos, ...] = ((33, 26), (45, 26), (39, 36))
KEYSTONE_POS: Pos = (39, 29)
PYLON_POS: tuple[Pos, ...] = ((39, 47), (24, 31), (54, 31))  # south, west, east gates: none within idle sight of either camp
RELIEF_SLUICE: Point = (34.5, 22.5)


def _ground_eligible(run: Run) -> bool:
    """GROUND needs somewhere for the breath to go: the whole grove, the Guardian, or its heart-stone."""
    return not run.get("undertow_grove_cut") or bool(run.get("undertow_guardian_core")
           or run.get("undertow_guardian_ally") and run.units(0, U.ANCIENT_GUARDIAN))


def _setup_maw(run: Run) -> None:
    terrain = _terrain(80, 64)
    _fill(terrain, 28, 20, 52, 21, Terrain.ROCK)                    # the crater's broken ring
    _fill(terrain, 28, 43, 52, 44, Terrain.ROCK)
    _fill(terrain, 28, 20, 29, 44, Terrain.ROCK)
    _fill(terrain, 51, 20, 52, 44, Terrain.ROCK)
    _fill(terrain, 39, 20, 40, 21, Terrain.GRASS)                   # gates: north, west, east, south
    _fill(terrain, 28, 31, 29, 32, Terrain.GRASS)
    _fill(terrain, 51, 31, 52, 32, Terrain.GRASS)
    _fill(terrain, 39, 43, 40, 44, Terrain.GRASS)
    _fill(terrain, 10, 52, 14, 55, Terrain.WATER)                   # the Sorrow, falling in and not pooling
    for cx, cy in ((12, 12), (68, 12), (14, 44), (66, 46), (64, 30)):
        _disc(terrain, cx, cy, 3, Terrain.TREES)
    world = _authored(run, terrain, theme=MapTheme.WASTELAND, races=(Race.HUMAN, Race.HUMAN, Race.ORC),
                      rifts=MAW_RIFTS + ((24, 6), (56, 6), (48, 57)), seed=2505)
    hall = _put(run, 0, B.TOWN_HALL, (36, 3))
    _put(run, 0, B.BARRACKS, (42, 3)); _put(run, 0, B.BLACKSMITH, (30, 3))
    _put(run, 0, B.WORKSHOP, (30, 9)); _put(run, 0, B.CHURCH, (42, 9))
    _put(run, 0, B.VAULT, (24, 6))
    farm_spots = [(33, 8), (36, 8), (46, 3), (46, 6), (46, 9), (49, 9)]
    farms = farm_spots[:-1] if run.get("undertow_dam") else farm_spots  # a blown dam: one farm of dry millpond
    for spot in farms:
        _put(run, 0, B.FARM, spot)
    keystone = _put(run, 0, B.MAGE_TOWER, KEYSTONE_POS, hp_share=0.25)
    keystone_hp = keystone.hp
    pylons = [_put(run, 1, B.FARM, pos) for pos in PYLON_POS]
    _put(run, 1, B.TOWN_HALL, (36, 56)); _put(run, 1, B.BARRACKS, (30, 56))
    sella_tower = _put(run, 1, B.MAGE_TOWER, (42, 56))
    _put(run, 1, B.VAULT, (48, 57))
    _put(run, 1, B.TOWER, (33, 52)); _put(run, 1, B.TOWER, (44, 52)); _put(run, 1, B.FARM, (46, 60))
    run.spawn(1, [U.FOOTMAN] * 5 + [U.ARCHER] * 3 + [U.CLERIC], (39.5, 53.5), hold=True)
    _mine(run, B.GOLD_MINE, (9, 8)); _mine(run, B.GOLD_MINE, (67, 8))
    band = run.spawn(0, [U.KNIGHT, U.CLERIC] + [U.FOOTMAN] * 5 + [U.ARCHER] * 3 + [U.KNIGHT] * 2 + [U.CATAPULT],
                     (39.5, 13.5))
    run.spawn(0, [U.PEASANT] * 5, (37.5, 11.5))
    gold, aether, core_aether = 2000, 90, 0
    if run.get("undertow_mill_vault"):
        _put(run, 0, B.VAULT, (56, 6))                              # the mill-vault's crew, drawing already
        aether += 60
    else:
        run.spawn(0, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, (39.5, 17.5))  # Brakk's band, in the player's colours
    if run.get("undertow_dam"):
        gold += 800                                                 # salvaged millstones
    if run.get("undertow_guardian_ally"):
        run.spawn(0, [U.ANCIENT_GUARDIAN], (35.5, 16.5))
    if run.get("undertow_guardian_core"):
        capacity = world.aether_cap(0)
        core_aether = min(capacity, aether + 120) - min(capacity, aether)
        aether += 120
    if run.get("undertow_seam_mined"):
        gold = gold + 1000 if run.get("undertow_seam_capped") else gold + 2000
    world.players[0].upgrades.add(Upgrade.MEND)
    _purse(run, 0, gold, 800, min(world.aether_cap(0), aether))
    _defaults(run, issa=band[0].id, keystone_pos=list(KEYSTONE_POS), keystone_hp=keystone_hp,
              pylon_pos=[list(p) for p in PYLON_POS], maw_rifts=[list(r) for r in MAW_RIFTS],
              keystone_center=list(keystone.center), camp_center=list(hall.center),
              sella_tower=sella_tower.id, relief_sluice=list(RELIEF_SLUICE), maw_core_aether=core_aether)
    _landmark(run, "keystone", "The Keystone (repair it)", keystone.center, kind="bell", radius=4, state="active")
    for i, pylon in enumerate(pylons):
        _landmark(run, f"seal_pylon_{i + 1}", f"Seal-pylon {'I II III'.split()[i]} (destroy it)", pylon.center,
                  kind="gate", state="active")
    for i, rift in enumerate(MAW_RIFTS):
        _landmark(run, f"maw_rift_{i + 1}", f"Maw rift {'I II III'.split()[i]} (build a vault)",
                  (rift[0] + 1.0, rift[1] + 1.0), kind="anchor", state="active")
    _landmark(run, "keepers_camp", "The Keepers' camp", hall.center, kind="refuge", radius=6, state="active")
    _landmark(run, "relief_sluice", "Relief Sluice (Issa opens the surveyed bypass)", RELIEF_SLUICE,
              kind="gate", radius=4, state="active")
    _landmark(run, "refuge_tower", "Refuge: Tern's wounded crew", sella_tower.center,
              kind="refuge", radius=4, state="active")
    world.update_vision()


def _pylons_standing(run: Run) -> int:
    return sum(1 for pos in PYLON_POS if _at_footprint(run, 1, B.FARM, pos) is not None)


def _maw_vaults(run: Run) -> int:
    return sum(1 for rift in MAW_RIFTS if _at_footprint(run, 0, B.VAULT, rift) is not None)


def _keystone(run: Run) -> Building | None:
    return _at_footprint(run, 0, B.MAGE_TOWER, KEYSTONE_POS)


def _maw_commit(path: str, *lines: Line):
    def do(run: Run) -> None:
        run.set("ending_path", path)
        run.say(*lines)
        run.toast(f"{path.upper()} is chosen", "The objective panel now shows the committed works")

    return do


def _maw_ending_phase(run: Run) -> None:
    """Retire impossible objectives, including a committed save from an earlier version."""
    for alternative in ("sealed", "open", "ground"):
        if alternative != run.get("ending_path"):
            run.state[alternative] = "hidden"


def _maw_final_ground(run: Run) -> None:
    band = run.spawn(2, [U.AETHER_ELEMENTAL] * 3 + [U.SPIDER] * 3, (40.5, 40.5),
                     attack=tuple(run.get("keystone_center")))
    run.set("final_band", [u.id for u in band])


def _maw_muster(run: Run) -> None:
    notes = ["The Steps muster at the north rim"]
    if run.get("undertow_mill_vault"):
        notes.append("The mill-vault's crew draws on the east rift (+1 vault, +60 aether)")
    else:
        notes.append("Brakk's band stands on the north trail (6 soldiers)")
    if run.get("undertow_dam"):
        notes.append("A farm of dry millpond, and 800 gold of salvaged millstones")
    if run.get("undertow_guardian_ally"):
        notes.append("The Ancient Guardian walks with you")
    if run.get("undertow_guardian_core"):
        grant = f" (+{run.get('maw_core_aether')} aether)" if "maw_core_aether" in run.vars else " (aether reserves)"
        notes.append("The heart-stone hums in its crate" + grant)
    if run.get("undertow_seam_mined") and not run.get("undertow_seam_capped"):
        notes.append("Seam-gold in the purse — and the rifts will bloom for it")
    if run.get("undertow_seam_capped"):
        notes.append("The seam is capped: no blooms at the Maw")
    run.toast("The muster of consequences", *notes)


def _maw_bloom_hazard(index: int):
    def do(run: Run) -> None:
        rift = MAW_RIFTS[index % len(MAW_RIFTS)]
        band = run.spawn(2, [U.AETHER_ELEMENTAL] * 2, (rift[0] + 1.0, rift[1] + 1.0),
                         attack=tuple(run.get("camp_center")))
        run.set(f"bloom_hazard_{index}", [u.id for u in band])
        run.toast("A rift blooms", "Wild elementals — the thinned seam, spending itself")

    return do


def _maw_final_sealed(run: Run) -> None:
    band = run.spawn(1, [U.FOOTMAN] * 6 + [U.ARCHER] * 3 + [U.KNIGHT] * 2, (39.5, 50.5),
                     attack=tuple(run.get("keystone_center")))
    run.set("final_band", [u.id for u in band])
    run.say(*dialogue.MAW_FINAL_SEALED)


def _maw_opened(run: Run) -> None:
    if run.world.players[1].alive:
        run.world.resign(1)
    run.world.take_events()
    for i in range(3):
        _landmark_state(run, f"seal_pylon_{i + 1}", "ruined")
    band = run.spawn(2, [U.AETHER_ELEMENTAL] * 4 + [U.WOLF] * 3, (40.5, 32.5),
                     attack=tuple(run.get("camp_center")))
    run.set("final_band", [u.id for u in band])
    run.say(*dialogue.MAW_OPENED)


def _maw_relief_opened(run: Run) -> None:
    """Issa operates Dagna's measured bypass before the demolished pylons release the Maw."""
    run.set("maw_relief_open", True)
    _landmark_state(run, "relief_sluice", "open")
    run.say(*dialogue.MAW_RELIEF_OPENED)


def _maw_pressure_cleared(run: Run) -> bool:
    """Every seam-pressure band that has actually arrived is defeated before resolution."""
    return not any(uid in run.world.units for index in range(5) for uid in run.get(f"bloom_hazard_{index}", []))


def _maw_resolve(path: str):
    def do(run: Run) -> None:
        run.set(f"undertow_ending_{path}", True)
        run.set("undertow_sella_tower_spared", run.get("sella_tower") in run.world.buildings)
        run.set("maw_resolved", path)
        _landmark_state(run, "keystone", "open" if path == "sealed" else "ruined" if path == "open" else "open")

    return do


def _maw_relief(run: Run) -> None:
    run.spawn(0, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, tuple(run.get("camp_center")))
    run.world.players[0].gold += 400
    run.toast("The Steps' muster arrives", "Six soldiers and 400 gold. The valley remembers it was needed.")


MAW = Mission(
    dialogue_art="campaign/scenes/maw.webp",
    id="undertow_maw", title="The Maw", act=ACT_3,
    sides=(Side("Keepers", Race.HUMAN), Side("The Open Hand", Race.HUMAN), Side("The Bloom", Race.ORC)),
    size="Large", theme=MapTheme.WASTELAND, layout=Layout.KLONDIKE, seed=2505,
    briefing=dialogue.MAW_BRIEFING,
    debrief=dialogue.MAW_DEBRIEF,
    setup=_setup_maw,
    objectives=(
        Objective("sealed", "RESEAL: repair Keystone; beat assault",
                  lambda run: run.get("maw_resolved") == "sealed", optional=True),
        Objective("open", "OPEN: sluice, three pylons, bloom",
                  lambda run: run.get("maw_resolved") == "open", optional=True),
        Objective("ground", f"GROUND: 3 vaults, {GROUND_AETHER} aether + surge",
                  lambda run: run.get("maw_resolved") == "ground", optional=True),
        Objective("tower_spared", "Spare the crew's refuge tower", lambda run: bool(run.get("maw_resolved"))
                  and run.get("sella_tower") in run.world.buildings,
                  shown=lambda run: bool(run.get("ending_path")), optional=True),
        Objective("relief_sluice", "Issa operates the Relief Sluice", lambda run: bool(run.get("maw_relief_open")),
                  shown=lambda run: run.get("ending_path") == "open", optional=True),
        Objective("ground_guardian", "Keep the Ancient for GROUND", lambda run: bool(run.get("maw_resolved")),
                  failed=lambda run: not run.units(0, U.ANCIENT_GUARDIAN),
                  shown=lambda run: run.get("ending_path") == "ground" and bool(run.get("undertow_grove_cut"))
                  and not run.get("undertow_guardian_core"), optional=True),
        Objective("issa", "Issa must survive", lambda run: bool(run.get("maw_resolved")),
                  failed=lambda run: run.unit("issa") is None, optional=True),
        Objective("hall", "Your Town Hall must stand", lambda run: bool(run.get("maw_resolved")),
                  failed=lambda run: run.hall(0) is None, optional=True),
    ),
    triggers=(
        Trigger("muster", at(1), _maw_muster),
        Trigger("refuge_warning", lambda run: (tower := run.world.buildings.get(run.get("sella_tower"))) is not None
                and any(dist(unit.pos, tower.center) <= 16 for unit in run.soldiers(0)),
                lambda run: run.say(*dialogue.MAW_REFUGE_WARNING)),
        Trigger("assault_1", all_of(at(90), lambda run: "pylons_down" not in run.fired),
                _wave(1, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, (39.5, 50.5),
                                            "keystone_center", "assault_1_band")),
        Trigger("assault_2", all_of(lambda run: "pylons_down" not in run.fired,
                                    any_of(lambda run: bool(run.get("ending_path")) and after("assault_1", 60)(run), at(360))),
                _wave(1, [U.FOOTMAN] * 5 + [U.ARCHER] * 3 + [U.KNIGHT], (39.5, 50.5),
                      "keystone_center", "assault_2_band")),
        Trigger("commit_sealed", all_of(lambda run: not run.get("ending_path"),
                                        lambda run: (k := _keystone(run)) is not None and k.hp > int(run.get("keystone_hp")) + 5),
                _maw_commit("sealed", *dialogue.MAW_COMMIT_SEALED)),
        Trigger("commit_open", all_of(lambda run: not run.get("ending_path"), lambda run: _pylons_standing(run) < 3),
                _maw_commit("open", *dialogue.MAW_COMMIT_OPEN)),
        Trigger("commit_ground", all_of(lambda run: not run.get("ending_path"), lambda run: _maw_vaults(run) >= 1,
                                        lambda run: _ground_eligible(run)),
                _maw_commit("ground", *dialogue.MAW_COMMIT_GROUND)),
        Trigger("ending_phase", lambda run: bool(run.get("ending_path")), _maw_ending_phase),
        Trigger("ground_surge", all_of(lambda run: run.get("ending_path") == "ground",
                                       lambda run: not run.get("final_band")), _maw_final_ground),
        Trigger("bloom_hazard_0", all_of(lambda run: bool(run.get("ending_path")),
                                        lambda run: bool(run.get("undertow_seam_mined"))
                                        and not run.get("undertow_seam_capped")), _maw_bloom_hazard(0)),
        Trigger("ground_warned", all_of(lambda run: not run.get("ending_path"),
                                        lambda run: _maw_vaults(run) >= 1, lambda run: not _ground_eligible(run)),
                lambda run: run.say(Line("Wrenna", "Those vaults will draw, but they cannot ground the Maw alone — the grove was cut and no Guardian "
                                                   "stands with us, living or as stone. Reseal or open it instead."))),
        Trigger("keystone_full", all_of(lambda run: run.get("ending_path") == "sealed",
                                        lambda run: (k := _keystone(run)) is not None and k.hp >= k.max_hp),
                _maw_final_sealed),
        Trigger("relief_opened", all_of(lambda run: run.get("ending_path") == "open",
                                        lambda run: run.near("issa", RELIEF_SLUICE, 4)), _maw_relief_opened),
        Trigger("pylons_down", all_of(lambda run: run.get("ending_path") == "open",
                                      lambda run: bool(run.get("maw_relief_open")),
                                      lambda run: _pylons_standing(run) == 0), _maw_opened),
        Trigger("resolve_sealed", all_of(lambda run: run.get("ending_path") == "sealed",
                                         lambda run: "keystone_full" in run.fired, _band_cleared("final_band"),
                                         lambda run: (k := _keystone(run)) is not None and k.hp >= k.max_hp,
                                         _maw_pressure_cleared),
                _maw_resolve("sealed")),
        Trigger("resolve_open", all_of(lambda run: run.get("ending_path") == "open",
                                       lambda run: "pylons_down" in run.fired, _band_cleared("final_band"), _maw_pressure_cleared),
                _maw_resolve("open")),
        Trigger("resolve_ground", all_of(lambda run: run.get("ending_path") == "ground",
                                         lambda run: _ground_eligible(run), lambda run: _maw_vaults(run) == 3,
                                         lambda run: run.world.players[0].aether >= GROUND_AETHER,
                                         _band_cleared("final_band"), _maw_pressure_cleared),
                _maw_resolve("ground")),
        *(Trigger(f"bloom_hazard_{i}", all_of(at(100 + 100 * i), lambda run: bool(run.get("undertow_seam_mined"))
                                              and not run.get("undertow_seam_capped")), _maw_bloom_hazard(i))
          for i in range(1, 5)),
        Trigger("relief", all_of(at(60), lambda run: len(run.soldiers(0)) <= 1, lambda run: not run.get("maw_resolved")),
                _maw_relief),
    ),
    win=lambda run: bool(run.get("maw_resolved")),
    remember=("undertow_ending_sealed", "undertow_ending_open", "undertow_ending_ground", "undertow_sella_tower_spared"),
)


CAMPAIGN = Campaign(
    id="undertow",
    title="The Undertow",
    tagline="Every lock in the valley is a held breath. Someone has started letting go.",
    speakers=SPEAKERS,
    missions=(MILL, CARAVAN, GROVE, WEIGHT, MAW),
    cover="campaign/undertow.png",
    introduction="The locks feed the valley. Now they draw beasts uphill. "
                 "Lead four keepers to the Maw and choose what to save.",
    epilogue=dialogue.EPILOGUE,
)
