"""What needs what: the tech tree as the rules tables give it, and where a player stands in it.

The rules keep each prerequisite beside what needs it (:mod:`warband.sim.rules`: a building's ``requires``, a
unit's ``trained_at``, an upgrade's lower tier and the building that researches it).  This reads them the other
way round for the HUD: what an item still needs, whether that is on its way, what a building opens, and the tree
the codex draws (:class:`TechTree`).  The world checks the same rules when an order arrives; nothing here decides
what the simulation does, and it lives outside ``warband/sim`` so the online contract, which hashes that folder,
does not move for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saga2d import Anchor, Component, Label
from warband.art.production import fit, production_image
from warband.sim.model import Build, World
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, UNITS, UPGRADES, BuildingType, Race, UnitType, Upgrade

Target = UnitType | BuildingType | Upgrade
Prerequisite = BuildingType | Upgrade


def researched_at(upgrade: Upgrade) -> BuildingType:
    return next(kind for kind, info in BUILDINGS.items() if upgrade in info.researches)


def prerequisites(target: Target) -> tuple[Prerequisite, ...]:
    """What *target* needs directly, in the order a player meets it: a unit its building, a building the one it
    requires, an upgrade the building that researches it and then its lower tier.  Every race shares these."""
    if isinstance(target, UnitType):
        return (UNITS[target].trained_at,)
    if isinstance(target, BuildingType):
        requires = BUILDINGS[target].requires
        return () if requires is None else (requires,)
    lower = UPGRADES[target].requires
    return (researched_at(target),) + (() if lower is None else (lower,))


def unlocks(building: BuildingType) -> list[BuildingType]:
    """The buildings that require *building*, in the rules' order."""
    return [kind for kind, info in BUILDINGS.items() if info.requires is building]


@dataclass(frozen=True)
class Need:
    """The first prerequisite of an item that the player lacks, and whether it is on its way: then an order for the
    item is planned and waits for it, where otherwise it would wait for something nobody is making."""

    target: Prerequisite
    coming: bool


def has(world: World, player: int, item: Prerequisite) -> bool:
    """A building of *item*'s kind stands finished, or the upgrade is researched."""
    if isinstance(item, BuildingType):
        return bool(world.player_buildings(player, item, done=True))
    return item in world.players[player].upgrades


def coming(world: World, player: int, item: Prerequisite) -> bool:
    """*item* is on its way: a building going up, planned or a builder's next site; an upgrade researched or planned."""
    if any(plan.type is item for plan in world.player_plans(player)):
        return True
    if isinstance(item, BuildingType):
        return (bool(world.player_buildings(player, item, done=False))
                or any(isinstance(order, Build) and order.type is item for unit in world.player_units(player) for order in unit.orders))
    return any(building.research is item for building in world.player_buildings(player))


def need(world: World, player: int, target: Target) -> Need | None:
    """What *target* waits for, or None when the player has everything it needs (or, an upgrade, has it already)."""
    if isinstance(target, Upgrade) and target in world.players[player].upgrades:
        return None
    for item in prerequisites(target):
        if not has(world, player, item):
            return Need(item, coming(world, player, item))
    return None


def tree() -> dict[BuildingType, tuple[int, float]]:
    """Each building's place in the tech tree, ``(column, row)``: the column is how many prerequisites deep it stands;
    a building that opens none takes a row of its own, one that opens several sits across the middle of theirs.  The
    roots, which need nothing, go top down, those that open something first."""
    places: dict[BuildingType, tuple[int, float]] = {}
    rows = 0

    def place(kind: BuildingType, column: int) -> float:
        nonlocal rows
        below = [place(child, column + 1) for child in unlocks(kind)]
        if below:
            row = (below[0] + below[-1]) / 2
        else:
            row, rows = rows, rows + 1
        places[kind] = (column, row)
        return row

    roots = [kind for kind, info in BUILDINGS.items() if info.requires is None and kind is not BuildingType.GOLD_MINE]
    for root in sorted(roots, key=lambda kind: not unlocks(kind)):
        place(root, 0)
    return places


#: How bright a picture in the tree is: the player has it (a recruit: can train it), it is on its way, or neither.
BRIGHT, COMING, FAINT = 1.0, 0.62, 0.3
OPEN, SHUT = (255, 214, 110, 210), (255, 255, 255, 56)  # a line from a prerequisite the player has, or not


def level(world: World, player: int, target: Target) -> float:
    """How bright *target* stands in the player's tree: a recruit as its building, the rest by what the player holds."""
    if isinstance(target, UnitType):
        return level(world, player, UNITS[target].trained_at)
    return BRIGHT if has(world, player, target) else COMING if coming(world, player, target) else FAINT


class _Picture(Component):
    """A portrait or an emblem in the tree, as bright as the player's hold on it, naming itself on hover."""

    def __init__(self, target: Target, player: int, race: Race, size: int, opacity: float, tooltip: str, **kwargs: Any) -> None:
        super().__init__(width=size, height=size, tooltip=tooltip, **kwargs)
        self.target, self.player, self.race, self.opacity = target, player, race, opacity

    def on_draw(self) -> None:
        if self._game is None:
            return
        game, (x, y, w, _h) = self._game, self.bounds
        key = production_image(game, self.target, self.player, self.race)
        game.backend.draw_image(game.assets.image(key), *fit(game, key, x, y, w), opacity=self.opacity, order=self._order)


class TechTree(Component):
    """The race's buildings as a tree, left to right: a line runs from each prerequisite into what it opens, and beside
    each building stand what it trains and researches.  Lit by the player's settlement as it stands when the tree is
    made (the codex pauses the match): bright what they have, dimmer what is on its way, faint the rest."""

    COLUMN = 292  # from one column's left edge to the next
    ROW = 70
    NODE = 216  # a building's portrait, its name and its pictures; the lines run in the rest of the column
    PORTRAIT = 44
    ICON = 28
    NAME = 26  # the name's line, above the building's pictures

    def __init__(self, world: World, player: int, **kwargs: Any) -> None:
        self.places = tree()
        columns = 1 + max(column for column, _row in self.places.values())
        rows = 1 + max(row for _column, row in self.places.values())
        super().__init__(width=(columns - 1) * self.COLUMN + self.NODE, height=round((rows - 1) * self.ROW) + self.NAME + self.ICON, **kwargs)
        race = world.players[player].race
        info = RACES[race]
        self.lit = {kind: level(world, player, kind) for kind in self.places}
        self.pictures: list[_Picture] = []

        def picture(target: Target, x: int, y: int, size: int, tooltip: str) -> None:
            self.pictures.append(_Picture(target, player, race, size, level(world, player, target), tooltip,
                                          anchor=Anchor.TOP_LEFT, margin=(x, y)))
            self.add(self.pictures[-1])

        for kind, (column, row) in self.places.items():
            building = info.buildings[kind]
            x, y = column * self.COLUMN, round(row * self.ROW)
            needs = f" · needs the {info.buildings[building.requires].name}" if building.requires is not None else ""
            picture(kind, x, y, self.PORTRAIT, f"{building.name} — {building.cost} · {building.summary}{needs}")
            self.add(Label(building.name, text_style="hud", anchor=Anchor.TOP_LEFT, margin=(x + self.PORTRAIT + 8, y)))
            work: list[Target] = [*building.trains, *(u for u in building.researches if info.upgrade_allowed(u))]
            for index, item in enumerate(work):
                if isinstance(item, UnitType):
                    tooltip = f"{info.units[item].name} — {info.units[item].cost} · {info.units[item].summary}"
                else:
                    upgrade = UPGRADES[item]
                    after = f" · after {UPGRADES[upgrade.requires].name}" if upgrade.requires is not None else ""
                    tooltip = f"{upgrade.name} — {upgrade.cost} · {upgrade.summary}{after}"
                picture(item, x + self.PORTRAIT + 8 + index * (self.ICON + 4), y + self.NAME, self.ICON, tooltip)

    def on_draw(self) -> None:
        """The lines, under the pictures: out of the prerequisite's column, down or up, and into the building with an arrow."""
        if self._game is None:
            return
        backend, (left, top, _w, _h) = self._game.backend, self.bounds
        for kind, (column, row) in self.places.items():
            requires = BUILDINGS[kind].requires
            if requires is None:
                continue
            from_column, from_row = self.places[requires]
            x1, y1 = left + from_column * self.COLUMN + self.NODE, top + round(from_row * self.ROW) + self.PORTRAIT / 2
            x2, y2 = left + column * self.COLUMN - 7, top + round(row * self.ROW) + self.PORTRAIT / 2
            bend = (x1 + x2) / 2
            color = OPEN if self.lit[requires] == BRIGHT else SHUT
            for a, b, c, d in ((x1, y1, bend, y1), (bend, y1, bend, y2), (bend, y2, x2, y2)):
                backend.draw_line(a, b, c, d, color, 2, order=self._order)
            backend.draw_polygon([(x2, y2 - 5), (x2 + 6, y2), (x2, y2 + 5)], color, order=self._order)
