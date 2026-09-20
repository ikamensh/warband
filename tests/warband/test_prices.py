"""What a thing costs, told in symbols: the command card, the codex, and the red of a purse that cannot pay.

An RTS player reads a price at a glance — StarCraft's cards carry a mineral and a gas symbol with their numbers,
and turn a number red when the purse is short.  These hold Warband's cards and codex to the same reading.
"""

import pytest

from saga2d import Game
from warband.sim.rules import BUILDINGS, UNITS, BuildingType, UnitType
from warband.ui.icons import COLORS
from warband.ui.scene import DEFAULT_SETTINGS, CodexScene, GameScene, new_game
from warband.ui.style import BAD, BODY, GOLD, build_theme


@pytest.fixture
def game(tmp_path):
    g = Game("Warband prices", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def match(game: Game) -> GameScene:
    """Seed 3 at its start: a town hall, three peasants and the purse the map gives."""
    scene = new_game(seed=3, settings=dict(DEFAULT_SETTINGS, tutorial=False, sfx=0.0, music=0.0), races=[None, None])
    game.push(scene)
    game.tick(1 / 60)
    return scene


def press(game: Game, key: str) -> None:
    game.backend.inject_key(key)
    game.tick(1 / 60)


def button_of(scene: GameScene, target):
    return next(button for command, button in zip(scene.card, scene.card_buttons) if command.target is target)


def under(game: Game, button) -> list[tuple[str, tuple[int, int, int, int]]]:
    """The lines drawn under *button*, left to right: the name, then each number of the price with its ink."""
    x, y, w, h = button.bounds
    lines = [t for t in game.backend.texts if x <= t["x"] < x + w and y + h <= t["y"] < y + h + 40]
    return [(t["text"], tuple(t["color"])) for t in sorted(lines, key=lambda t: (t["y"], t["x"]))]


def symbols_under(game: Game, button) -> list[str]:
    """The resource symbols drawn under *button*, left to right; each is told by the colour of its own facets."""
    x, y, w, h = button.bounds
    inks = {COLORS[name]: name for name in ("gold", "lumber", "supply")}
    leftmost: dict[str, float] = {}
    for polygon in game.backend.polygons:
        name = inks.get(tuple(polygon["color"]))
        px, py = min(p[0] for p in polygon["points"]), min(p[1] for p in polygon["points"])
        if name is not None and x <= px < x + w and y + h <= py < y + h + 40:
            leftmost[name] = min(leftmost.get(name, px), px)
    return sorted(leftmost, key=lambda name: leftmost[name])


def test_a_price_is_a_symbol_and_a_number_for_each_resource_it_takes(game) -> None:
    """The barracks costs gold and lumber and shows both symbols; a peasant costs no lumber and shows no second
    number (the card once read "400 / 0", which says nothing about which number is which)."""
    scene = match(game)
    scene.player.gold, scene.player.lumber = 5000, 5000
    press(game, "b")
    barracks = BUILDINGS[BuildingType.BARRACKS].cost
    assert under(game, button_of(scene, BuildingType.BARRACKS))[1:] == [(str(barracks.gold), BODY), (str(barracks.lumber), BODY)]
    assert symbols_under(game, button_of(scene, BuildingType.BARRACKS)) == ["gold", "lumber"]
    press(game, "escape")
    press(game, "t")
    assert under(game, button_of(scene, UnitType.PEASANT))[1:] == [(str(UNITS[UnitType.PEASANT].cost.gold), BODY)]
    assert symbols_under(game, button_of(scene, UnitType.PEASANT)) == ["gold"]


def test_a_number_the_purse_cannot_pay_is_red_and_goes_plain_when_it_can(game) -> None:
    """The red says "not now" without greying the item out: a plan is still worth making, and waits for the money.
    It follows the purse from frame to frame, so paying for one thing reddens the next."""
    scene = match(game)
    hall = BUILDINGS[BuildingType.TOWN_HALL].cost
    scene.player.gold, scene.player.lumber = hall.gold, hall.lumber - 1
    press(game, "b")
    assert under(game, button_of(scene, BuildingType.TOWN_HALL))[1:] == [(str(hall.gold), BODY), (str(hall.lumber), BAD)]
    scene.player.lumber = hall.lumber
    scene.player.gold = hall.gold - 1
    game.tick(1 / 60)
    assert under(game, button_of(scene, BuildingType.TOWN_HALL))[1:] == [(str(hall.gold), BAD), (str(hall.lumber), BODY)]


def test_a_building_says_what_its_recruits_cost_on_its_own_card(game) -> None:
    """Selecting the hall used to show a portrait and a name and no price at all: the price of what a building
    makes belongs on the card that makes it, as it does in the catalogue."""
    scene = match(game)
    scene.player.gold, scene.player.lumber = 5000, 5000
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    scene.select([hall.id])
    game.tick(1 / 60)
    peasant = UNITS[UnitType.PEASANT].cost
    assert under(game, button_of(scene, UnitType.PEASANT))[1:] == [(str(peasant.gold), BODY)]
    assert symbols_under(game, button_of(scene, UnitType.PEASANT)) == ["gold"]


def supply_pair(game: Game, scene: GameScene) -> tuple[str, tuple[int, int, int, int], set[tuple[int, int, int, int]]]:
    """What the top bar's supply pair says, the ink of its number, and the colours its symbol is drawn in (each
    facet is a shade of the one ink the symbol is given, and that ink is among them)."""
    row = scene.supply_row.bounds
    inside = lambda x, y: row[0] <= x < row[0] + row[2] and row[1] <= y < row[1] + row[3]  # noqa: E731
    number = next(t for t in game.backend.texts if "/" in str(t["text"]) and inside(t["x"], t["y"]))
    facets = {tuple(p["color"]) for p in game.backend.polygons
              if inside(min(q[0] for q in p["points"]), min(q[1] for q in p["points"]))}
    return number["text"], tuple(number["color"]), facets


def test_the_supply_pair_warns_as_the_farms_fill_and_reddens_when_they_are_full(game) -> None:
    """Being supply-blocked is the commonest reason an RTS player's production stops; the bar says so before the
    refusal does, amber with room for two and red with none."""
    scene = match(game)
    world = scene.world
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    world.place_building(scene.human, BuildingType.FARM, (hall.x + 5, hall.y + 5))
    game.tick(1 / 60)
    used, cap = world.supply(scene.human)
    assert cap - used > 2
    text, ink, facets = supply_pair(game, scene)
    assert text == f"{used}/{cap}" and ink not in (BAD, GOLD) and COLORS["supply"] in facets
    for i in range(cap - used - 2):  # fill the farms to within two of the cap
        world.spawn_unit(scene.human, UnitType.PEASANT, (hall.x + 2 + i, hall.y + 2))
    game.tick(1 / 60)
    _text, ink, facets = supply_pair(game, scene)
    assert ink == GOLD and GOLD in facets
    for i in range(2):
        world.spawn_unit(scene.human, UnitType.PEASANT, (hall.x - 2 - i, hall.y + 2))
    game.tick(1 / 60)
    _text, ink, facets = supply_pair(game, scene)
    assert world.supply(scene.human)[0] >= cap and ink == BAD and BAD in facets


def test_the_codex_prices_things_in_the_same_symbols_as_the_card(game) -> None:
    """A page of "600 gold, 50 lumber" is a page nobody scans; the codex says a price the way the HUD does, and
    a building's supply with the symbol the top bar uses for it."""
    scene = match(game)
    game.push(CodexScene(scene.world, scene.human, page=1))  # buildings
    game.tick(1 / 60)
    drawn = {str(t["text"]) for t in game.backend.texts}
    facets = {tuple(p["color"]) for p in game.backend.polygons}
    barracks, farm = BUILDINGS[BuildingType.BARRACKS], BUILDINGS[BuildingType.FARM]
    assert str(barracks.cost) not in drawn and "Cost" in drawn
    assert {str(barracks.cost.gold), str(barracks.cost.lumber)} <= drawn
    assert f"+{farm.supply}" in drawn and {COLORS["gold"], COLORS["lumber"], COLORS["supply"]} <= facets
