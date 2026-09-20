"""What a thing costs, told in symbols: the command card, the codex, and the red of a purse that cannot pay.

An RTS player reads a price at a glance — StarCraft's cards carry a mineral and a gas symbol with their numbers,
and turn a number red when the purse is short.  These hold Warband's cards and codex to the same reading.
"""

import pytest

from saga2d import Game
from warband.sim.rules import BUILDINGS, UNITS, BuildingType, Cost, UnitType
from warband.ui.icons import COLORS
from warband.ui.scene import DEFAULT_SETTINGS, SHORT_FLASH, SHORT_OF, CodexScene, GameScene, new_game
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


def shades(color: tuple[int, int, int, int]) -> set[tuple[int, int, int, int]]:
    """The lighter and darker facets a symbol is drawn with beside its own colour."""
    return {tuple(round(c * 0.6) for c in color[:3]) + (color[3],), tuple(min(255, round(c * 1.2)) for c in color[:3]) + (color[3],)}


def top_bar(game: Game, scene: GameScene, name: str) -> tuple[str, tuple[int, int, int, int], set[tuple[int, int, int, int]]]:
    """What the top bar's pair for *name* says, the ink of its number, and the colours its symbol is drawn in
    (each facet is a shade of the one ink the symbol is given, and that ink is among them)."""
    icon, label = scene.resource_pair(name)
    ix, iy, iw, ih = icon.bounds
    lx, ly, lw, lh = label.bounds
    number = next(t for t in game.backend.texts if lx <= t["x"] < lx + lw and ly <= t["y"] < ly + lh)
    facets = {tuple(p["color"]) for p in game.backend.polygons
              if ix <= min(q[0] for q in p["points"]) < ix + iw and iy <= min(q[1] for q in p["points"]) < iy + ih}
    return str(number["text"]), tuple(number["color"]), facets


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
    text, ink, facets = top_bar(game, scene, "supply")
    assert text == f"{used}/{cap}" and ink not in (BAD, GOLD) and COLORS["supply"] in facets
    for i in range(cap - used - 2):  # fill the farms to within two of the cap
        world.spawn_unit(scene.human, UnitType.PEASANT, (hall.x + 2 + i, hall.y + 2))
    game.tick(1 / 60)
    _text, ink, facets = top_bar(game, scene, "supply")
    assert ink == GOLD and facets == {COLORS["supply"], *shades(COLORS["supply"])}, "the symbol keeps its own colour"
    for i in range(2):
        world.spawn_unit(scene.human, UnitType.PEASANT, (hall.x - 2 - i, hall.y + 2))
    game.tick(1 / 60)
    _text, ink, facets = top_bar(game, scene, "supply")
    assert world.supply(scene.human)[0] >= cap and ink == BAD and BAD not in facets


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


def test_an_order_refused_for_want_of_gold_reddens_the_gold_in_the_top_bar(game) -> None:
    """An RTS answers "not enough minerals" and reddens the counter; a line of status text on the far side of the
    screen is easy to miss while the eye is on the card.  The red fades on its own."""
    scene = match(game)
    scene.player.gold = 0
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    scene.select([hall.id])
    game.tick(1 / 60)
    press(game, UNITS[UnitType.PEASANT].hotkey)
    assert scene.status.startswith(SHORT_OF["gold"])
    assert top_bar(game, scene, "gold")[1] == BAD and top_bar(game, scene, "lumber")[1] != BAD
    game.tick(SHORT_FLASH)
    game.tick(1 / 60)
    assert top_bar(game, scene, "gold")[1] != BAD


def test_the_top_bar_knows_the_words_the_rules_refuse_with(game) -> None:
    """The flash reads the refusal the simulation wrote; a reword there would quietly end it, so hold the two
    together here rather than leave a dead feature."""
    scene = match(game)
    world = scene.world
    assert world.can_afford(scene.human, Cost(scene.player.gold + 1)).startswith(SHORT_OF["gold"])
    assert world.can_afford(scene.human, Cost(0, scene.player.lumber + 1)).startswith(SHORT_OF["lumber"])
