"""Settlement planning crosses the same authority boundary as individual orders."""

from websockets.sync.client import connect

from saga2d.testing.online import command, handshake, receive, server_fixture

server_url = server_fixture('warband.multiplayer:ONLINE')
from warband.model import World
from warband.rules import BuildingType


def test_online_building_plans_need_no_worker_id_and_reject_foreign_player(server_url):
    """A real peer plans for its settlement; spoofing the other faction is rejected."""
    with connect(server_url, proxy=None, max_queue=None) as host, connect(server_url, proxy=None) as guest:
        room = handshake(host, game="warband-v1", options={"seed": 3, "width": 40, "height": 32})
        handshake(guest, "join", game="warband-v1", room=room["room"])
        state = receive(host, predicate=lambda message: message["ready"])
        world = World.from_dict(state["state"]["world"])
        pos = next((x, y) for y in range(world.height) for x in range(world.width)
                   if world.can_plan_building(BuildingType.FARM, (x, y), 0) is None)
        command(host, {"action": "plan_building", "args": [0, "farm", pos]})
        planned = receive(host, predicate=lambda message: bool(message["state"]["world"]["settlement"]["plans"]))
        plans = World.from_dict(planned["state"]["world"]).player_plans(0)
        assert len(plans) == 1 and plans[0].pos == pos
        command(host, {"action": "plan_building", "args": [1, "farm", pos]})
        assert "own settlement" in receive(host, "error")["error"]


def test_online_global_production_assembly_and_cancellation_are_owned_by_the_player(server_url):
    """A client queues future production without a producer and controls only its own plans."""
    with connect(server_url, proxy=None, max_queue=None) as host, connect(server_url, proxy=None, max_queue=None) as guest:
        room = handshake(host, game="warband-v1", options={"seed": 3, "width": 40, "height": 32})
        handshake(guest, "join", game="warband-v1", room=room["room"])
        receive(host, predicate=lambda message: message["ready"])
        command(host, {"action": "order_unit", "args": [0, "footman"]})
        command(host, {"action": "order_upgrade", "args": [0, "blades_1"]})
        point = (11.5, 11.5)
        command(host, {"action": "set_assembly", "args": [0, point]})
        planned = receive(host, predicate=lambda message:
                          len(message["state"]["world"]["settlement"]["plans"]) == 2
                          and message["state"]["world"]["players"][0]["assembly"] == list(point))
        world = World.from_dict(planned["state"]["world"])
        plans = world.player_plans(0)
        assert {plan.kind for plan in plans} == {"unit", "upgrade"}
        assert world.players[0].assembly == point
        command(guest, {"action": "cancel_plan", "args": [1, plans[0].id]})
        assert receive(guest, "error")["error"]
        for plan in plans:
            command(host, {"action": "cancel_plan", "args": [0, plan.id]})
        receive(host, predicate=lambda message: not message["state"]["world"]["settlement"]["plans"])
        # Invalid coordinate/type data is rejected before reaching the model.
        for payload in (
            {"action": "set_assembly", "args": [0, [-1, 4]]},
            {"action": "plan_building", "args": [0, "farm", [7.5, 12]]},
            {"action": "order_unit", "args": [True, "footman"]},
            {"action": "cancel_plan", "args": [0, "1"]},
            {"action": "set_assembly", "args": [0, [10 ** 400, 4]]},
        ):
            command(host, payload)
            assert receive(host, "error")["error"]
        command(host, {"action": "set_assembly", "args": [0, None]})
        receive(host, predicate=lambda message: message["state"]["world"]["players"][0]["assembly"] is None)
