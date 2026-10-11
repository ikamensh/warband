"""The command line opens the campaign screen and missions, not the skirmish title.

Regression: the multiplayer CLI refactor dropped the ``--campaign``/``--mission``
branch, so those flags fell through to the title screen.  Both tests route real
parsed flags through the launch helper and read the scene handed to the public
``Game.run`` seam on a mock backend: no window, no server, no sound device beyond
what the game itself installs.  (The helper is module-private because ``main()``
parses ``sys.argv`` and compiles the simulation; it is the only seam that reaches
launch routing.)
"""

from saga2d import Game

from warband.__main__ import _run_with_args, cli_parser
from warband.story.campaign_scene import CampaignScene
from warband.story.mission_scene import MissionScene
from warband.story.missions import CAMPAIGN


def launch(tmp_path, monkeypatch, argv):
    """The scenes real CLI routing hands to ``Game.run`` for *argv*."""
    ran, made = [], []
    real_game = Game

    def factory(*args, **kwargs):
        game = real_game(*args, backend="mock", save_dir=tmp_path / "saves", **kwargs)
        made.append(game)
        return game

    monkeypatch.setattr("saga2d.Game", factory)
    monkeypatch.setattr(Game, "run", lambda self, scene, **kwargs: ran.append(scene))
    parser = cli_parser()
    try:
        _run_with_args(parser.parse_args(argv), parser)
    finally:
        for game in made:
            game.close()
    return ran


def test_campaign_flag_opens_the_campaign_screen(tmp_path, monkeypatch):
    """--campaign runs the campaign screen, never the skirmish title."""
    (ran,) = launch(tmp_path, monkeypatch, ["--campaign"])
    assert isinstance(ran, CampaignScene)


def test_mission_id_starts_that_mission(tmp_path, monkeypatch):
    """--mission ID starts that campaign mission with the saved progress's choices."""
    mission = CAMPAIGN.missions[0].id
    (ran,) = launch(tmp_path, monkeypatch, ["--mission", mission])
    assert isinstance(ran, MissionScene)
