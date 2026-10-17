"""Tests for GCSClientWorker: message parsing, schema validation, stale detection, command dispatching."""

import json
import time
from pathlib import Path
import pytest

from gcs_client import GCSClientWorker


def test_command_id_generation():
    worker = GCSClientWorker(url="ws://127.0.0.1:9090")
    cmd_id1 = worker.send_command("ABORT")
    cmd_id2 = worker.send_command("RTL")

    assert cmd_id1.startswith("cmd_")
    assert cmd_id2.startswith("cmd_")
    assert cmd_id1 != cmd_id2


def test_dispatch_incoming_valid_frame():
    worker = GCSClientWorker()
    captured_frames = []
    captured_telemetry = []
    captured_detections = []
    captured_sensors = []

    worker.frame_received_signal.connect(captured_frames.append)
    worker.telemetry_received_signal.connect(captured_telemetry.append)
    worker.detections_received_signal.connect(captured_detections.append)
    worker.sensors_received_signal.connect(captured_sensors.append)

    sample_frame = {
        "type": "telemetry",
        "drone": {"x": 5.0, "y": 6.0, "altitude": 2.1},
        "battery": {"percent": 75, "voltage": 22.1},
        "targets": [{"id": "S01", "confidence": 92}],
        "sensors": {"lidar": "ACTIVE", "wifi": "CONNECTED"},
    }

    worker._dispatch_incoming_data(sample_frame)

    assert len(captured_frames) == 1
    assert len(captured_telemetry) == 1
    assert len(captured_detections) == 1
    assert len(captured_sensors) == 1
    assert captured_detections[0][0]["id"] == "S01"


def test_dispatch_command_acknowledgement():
    worker = GCSClientWorker()
    captured_acks = []
    worker.command_ack_signal.connect(captured_acks.append)

    ack_payload = {
        "type": "command_ack",
        "command_id": "cmd_abc123",
        "command": "ABORT",
        "status": "ACCEPTED",
        "message": "Emergency abort executed",
        "timestamp": time.time(),
    }

    worker._dispatch_incoming_data(ack_payload)

    assert len(captured_acks) == 1
    assert captured_acks[0]["command_id"] == "cmd_abc123"
    assert captured_acks[0]["status"] == "ACCEPTED"


def test_stale_detection_logic():
    worker = GCSClientWorker()
    worker._current_status = "CONNECTED"
    worker._last_msg_timestamp = time.monotonic() - 4.5  # 4.5 seconds ago

    assert worker.is_stale() is True

    worker._last_msg_timestamp = time.monotonic() - 0.5  # 0.5 seconds ago
    assert worker.is_stale() is False
