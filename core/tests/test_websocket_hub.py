import asyncio
import unittest

from app.schemas.events import CoreEventEnvelope
from app.services.websocket_hub import ProjectWebSocketHub


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class ProjectWebSocketHubTests(unittest.TestCase):
    def test_broadcast_assigns_sequence_and_replay_works(self) -> None:
        async def scenario() -> None:
            hub = ProjectWebSocketHub()
            primary = _FakeWebSocket()
            secondary = _FakeWebSocket()

            connection_id = await hub.connect("proj_ws", primary)
            self.assertTrue(primary.accepted)
            self.assertTrue(connection_id.startswith("ws_"))

            first = CoreEventEnvelope(
                event="notification",
                project_id="proj_ws",
                payload={"message": "first"},
            )
            second = CoreEventEnvelope(
                event="workspace.chat.ready",
                project_id="proj_ws",
                payload={"message": "second"},
            )
            seq1 = await hub.broadcast(first)
            seq2 = await hub.broadcast(second)

            self.assertEqual(seq1, 1)
            self.assertEqual(seq2, 2)
            self.assertEqual(primary.messages[-1]["sequence"], 2)

            await hub.connect("proj_ws", secondary)
            replayed = await hub.replay("proj_ws", secondary, after_sequence=1)

            self.assertEqual(replayed, 1)
            self.assertEqual(len(secondary.messages), 1)
            self.assertEqual(secondary.messages[0]["sequence"], 2)
            self.assertEqual(await hub.current_sequence("proj_ws"), 2)

            await hub.disconnect("proj_ws", primary)
            await hub.disconnect("proj_ws", secondary)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
