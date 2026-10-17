"""Integration tests for live WebSocket connection between ros2_gcs_bridge and GCSClientWorker."""

import asyncio
import json
import threading
import time
import pytest
from PyQt6.QtCore import QCoreApplication

from gcs_client import GCSClientWorker
from ros2_gcs_bridge import EdithGCSBridge, websocket_handler
import websockets


@pytest.fixture(scope="module")
def standalone_server():
    """Spawns a background mock bridge WebSocket server on port 9099 for testing."""
    bridge = EdithGCSBridge()
    stop_event = threading.Event()

    async def run_server():
        server = await websockets.serve(
            lambda ws: websocket_handler(ws, bridge),
            "127.0.0.1",
            9099,
        )
        broadcast_task = asyncio.create_task(bridge.broadcast_loop())
        while not stop_event.is_set():
            await asyncio.sleep(0.05)
        broadcast_task.cancel()
        server.close()
        await server.wait_closed()

    def thread_target():
        asyncio.run(run_server())

    t = threading.Thread(target=thread_target, daemon=True)
    t.start()
    time.sleep(0.3)  # Give server a moment to bind
    yield bridge
    stop_event.set()
    time.sleep(0.2)


def test_client_connect_and_receive_telemetry(standalone_server):
    """Test that GCSClientWorker can connect to bridge and receive broadcast frames."""
    app = QCoreApplication.instance() or QCoreApplication([])

    worker = GCSClientWorker(url="ws://127.0.0.1:9099")
    received_frames = []

    def on_frame(frame):
        received_frames.append(frame)

    worker.frame_received_signal.connect(on_frame)
    worker.start()

    # Wait up to 2 seconds for connection and at least one telemetry frame
    start_t = time.monotonic()
    while time.monotonic() - start_t < 2.5:
        app.processEvents()
        if len(received_frames) >= 2:
            break
        time.sleep(0.05)

    assert worker.get_status() == "CONNECTED"
    assert len(received_frames) >= 1
    sample = received_frames[0]
    assert "drone" in sample
    assert "battery" in sample

    worker.stop()
    assert worker.isRunning() is False


def test_command_roundtrip_acknowledgement(standalone_server):
    """Test dispatching a command from client and receiving structured ACK from bridge."""
    app = QCoreApplication.instance() or QCoreApplication([])

    worker = GCSClientWorker(url="ws://127.0.0.1:9099")
    received_acks = []

    worker.command_ack_signal.connect(received_acks.append)
    worker.start()

    # Wait for connection
    start_t = time.monotonic()
    while time.monotonic() - start_t < 2.0 and worker.get_status() != "CONNECTED":
        app.processEvents()
        time.sleep(0.05)

    assert worker.get_status() == "CONNECTED"

    # Send command
    cmd_id = worker.send_command("ABORT")

    # Wait for ack
    start_t = time.monotonic()
    while time.monotonic() - start_t < 2.0:
        app.processEvents()
        if any(ack.get("command_id") == cmd_id for ack in received_acks):
            break
        time.sleep(0.05)

    worker.stop()

    matching_acks = [ack for ack in received_acks if ack.get("command_id") == cmd_id]
    assert len(matching_acks) == 1
    assert matching_acks[0]["status"] == "ACCEPTED"
    assert "abort" in matching_acks[0]["message"].lower()


def test_rejected_unknown_command(standalone_server):
    """Test that bridge rejects unknown command with status REJECTED."""
    app = QCoreApplication.instance() or QCoreApplication([])

    worker = GCSClientWorker(url="ws://127.0.0.1:9099")
    received_acks = []

    worker.command_ack_signal.connect(received_acks.append)
    worker.start()

    start_t = time.monotonic()
    while time.monotonic() - start_t < 2.0 and worker.get_status() != "CONNECTED":
        app.processEvents()
        time.sleep(0.05)

    cmd_id = worker.send_command("NON_EXISTENT_CMD")

    start_t = time.monotonic()
    while time.monotonic() - start_t < 2.0:
        app.processEvents()
        if any(ack.get("command_id") == cmd_id for ack in received_acks):
            break
        time.sleep(0.05)

    worker.stop()

    matching_acks = [ack for ack in received_acks if ack.get("command_id") == cmd_id]
    assert len(matching_acks) == 1
    assert matching_acks[0]["status"] == "REJECTED"
