"""The neutral creatures: every frame renders, nothing is empty or cut off, and nobody owns them."""

import pytest

from saga2d import Game
from warband.art import monsters, textures, visual_lint
from warband.art.monsters import Monster
from warband.sim.rules import PLAYERS, Race, UnitType
from warband.ui.style import build_theme

TEAM_COLOURS = {info.color for info in PLAYERS}
#: How far a standing creature's feet may sit from where its other facings put them, in logical
#: pixels.  The lint's own threshold is 6, tuned for a figure standing on two feet; the game's own
#: procedural units already reach 10.1, and a creature on four or eight feet reaches further still
#: because at a diagonal facing its nearest foot is a corner of the stance rather than its middle.
#: What the budget is for is a body so long that turning swings it off its anchor altogether: the
#: wolf's first draft, twice as long as this one, slid 18.2 px.
TURN_SLIDE_BUDGET = 12.0


def mock_game(tmp_path) -> Game:
    return Game("Monsters", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")


def frames_of(game: Game, monster: Monster, store: visual_lint.ImageStore, facings: range) -> dict:
    return {(facing, frame): (key, store.image(key))
            for facing in facings for frame in textures.FRAMES
            for key in [monsters.monster_image(game, monster, facing, frame)]}


@pytest.mark.parametrize("monster", list(Monster))
def test_every_frame_renders_solid_and_uncut(tmp_path, monster: Monster) -> None:
    """One facing of every creature in the fast tier: the nine frames exist, each at the size its
    placement promises, each with solid content that its canvas does not clip."""
    game = mock_game(tmp_path)
    try:
        store = visual_lint.ImageStore(game)
        frames = frames_of(game, monster, store, range(2, 3))
        assert len(frames) == len(textures.FRAMES)
        findings = []
        for key, image in frames.values():
            placement = textures.placements[key]
            assert image.size == (round(placement.size[0] * game.backend.scale_factor),
                                  round(placement.size[1] * game.backend.scale_factor)), key
            findings += visual_lint.lint_image(key, image)
        assert not findings, [str(finding) for finding in findings]
    finally:
        game.close()


@pytest.mark.parametrize("monster", list(Monster))
def test_the_walk_and_the_blow_are_nine_different_pictures(tmp_path, monster: Monster) -> None:
    """A frame table that quietly returns the same mesh for every frame would animate nothing."""
    game = mock_game(tmp_path)
    try:
        store = visual_lint.ImageStore(game)
        pictures = {frame: store.image(monsters.monster_image(game, monster, 2, frame)).tobytes()
                    for frame in textures.FRAMES}
        assert len(set(pictures.values())) == len(textures.FRAMES), sorted(pictures)
    finally:
        game.close()


@pytest.mark.parametrize("monster", list(Monster))
def test_a_neutral_creature_wears_no_team_colour(tmp_path, monster: Monster) -> None:
    """Nobody owns a monster.  No mesh here takes a player, and none of its faces may carry one of
    the four team hues — a wolf recoloured to Azure would read as somebody's unit."""
    for frame in textures.FRAMES:
        worn = {face.color[:3] for face in monsters.monster_mesh(monster, frame)} & TEAM_COLOURS
        assert not worn, (monster, frame, worn)


def test_the_api_a_rules_agent_calls(tmp_path) -> None:
    """Every creature is reached by the name a rule table would hold, has a portrait for the
    selection panel and says how it goes down."""
    game = mock_game(tmp_path)
    try:
        for monster in Monster:
            assert Monster(monster.value) is monster
            assert game.assets.has_image(monsters.monster_portrait_image(game, monster))
        assert set(monsters.DEATH_OUTCOME) == set(Monster)
    finally:
        game.close()


@pytest.mark.slow
def test_the_warm_up_registers_the_whole_set_one_render_at_a_time(tmp_path) -> None:
    """A scene spreads this over its opening frames instead of hitching at the first sighting.
    Slow: it is every creature image there is, 288 renders."""
    game = mock_game(tmp_path)
    try:
        keys = list(monsters.warm_monsters(game))
        assert len(keys) == len(set(keys)) == len(Monster) * textures.FACINGS * len(textures.FRAMES)
        assert all(game.assets.has_image(key) for key in keys)
    finally:
        game.close()


def tallest(mesh) -> float:
    return max(p[2] for face in mesh for p in face.points)


def widest(mesh) -> float:
    xs = [p[0] for face in mesh for p in face.points]
    return max(xs) - min(xs)


def test_the_creatures_are_sized_against_the_units_they_stand_beside(tmp_path) -> None:
    """Drawn at the same UNIT_SCALE as a footman, and each a size nobody else in the game is.

    The troll stands over a mounted knight — and so over the orc knight, which *is* an ogre; the
    golem is shorter than the troll and far broader, the shape of neither; the wolf comes up to a
    man's waist and the spider stays lower still.  The heights come off the geometry rather than
    the sprites, because a unit with a painted sheet is drawn from a cell far taller than its
    figure (`textures._unit` is the render the creatures are modelled against)."""
    footman = textures._unit(UnitType.FOOTMAN, 0, "stand", None)
    knight = textures._unit(UnitType.KNIGHT, 0, "stand", None)
    ogre = textures._unit(UnitType.KNIGHT, 0, "stand", None, Race.ORC)  # the orc knight is an Ogre
    shape = {monster: (tallest(monsters.monster_mesh(monster, "stand")),
                       widest(monsters.monster_mesh(monster, "stand"))) for monster in Monster}
    assert shape[Monster.TROLL][0] > max(tallest(knight), tallest(ogre)), shape
    assert shape[Monster.GOLEM][0] < shape[Monster.TROLL][0], shape
    assert shape[Monster.GOLEM][1] > shape[Monster.TROLL][1], shape
    assert shape[Monster.GOLEM][1] > widest(knight), shape
    assert shape[Monster.GOLEM][0] > tallest(footman), shape
    assert shape[Monster.WOLF][0] < tallest(footman) * 0.8, shape
    assert shape[Monster.SPIDER][0] < shape[Monster.WOLF][0], shape


def test_no_creature_is_wider_than_two_tiles(tmp_path) -> None:
    """A sprite wider than two tiles would overhang the neighbours it is drawn between."""
    game = mock_game(tmp_path)
    try:
        store = visual_lint.ImageStore(game)
        for monster in Monster:
            image = store.image(monsters.monster_image(game, monster, 2, "stand"))
            box = visual_lint.solid_box(image)
            assert box is not None, monster
            assert (box[2] - box[0]) / game.backend.scale_factor <= 2 * textures.TILE, (monster, box)
    finally:
        game.close()


@pytest.mark.slow
@pytest.mark.parametrize("monster", list(Monster))
def test_a_creature_keeps_its_feet_through_every_facing(tmp_path, monster: Monster) -> None:
    """All eight facings of all nine frames through the art lint.  Slow: 288 renders.

    What must not happen is a frame that is empty, cut off by its canvas, floating above the
    ground it stands on, or identical to another frame of the same facing.

    ``hop`` and ``slide`` are left out: they fire on the lunge and the stride that :data:`POSES`
    gives every figure, and the game's own procedural units raise between 12 and 60 of them
    apiece.  ``turn-slide`` is kept but budgeted at :data:`TURN_SLIDE_BUDGET`, because it reads
    the horizontal centre of the figure's lowest quarter, and a creature standing on four or
    eight feet puts its nearest foot off to one side at a diagonal facing — the game's own
    mounted units sit at 6.6 to 10.1 px against a threshold of 6."""
    game = mock_game(tmp_path)
    try:
        store = visual_lint.ImageStore(game)
        frames = frames_of(game, monster, store, range(textures.FACINGS))
        findings = [finding for key, image in frames.values() for finding in visual_lint.lint_image(key, image)]
        for finding in visual_lint.lint_subject(monster.value, frames, textures.placements[next(iter(frames.values()))[0]]):
            if finding.check in ("hop", "slide"):
                continue
            slid = finding.check == "turn-slide" and abs(float(finding.detail.split()[2])) <= TURN_SLIDE_BUDGET
            if not slid:
                findings.append(finding)
        assert not findings, [str(finding) for finding in findings]
    finally:
        game.close()
