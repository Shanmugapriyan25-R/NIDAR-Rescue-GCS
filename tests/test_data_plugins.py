"""Tests for gcs_data_plugins: DataPluginManager, SimulationPlugin, JsonFilePlugin, and schema validation."""

import json
from pathlib import Path
import pytest

from gcs_data_plugins import (
    DataPluginManager,
    SimulationPlugin,
    JsonFilePlugin,
    default_frame,
    ARENA_WIDTH_M,
    ARENA_HEIGHT_M,
)


def test_default_frame_schema():
    frame = default_frame()
    assert "source_type" in frame
    assert "drone" in frame
    assert "telemetry" in frame
    assert "sensors" in frame
    assert "health" in frame
    assert "survivors" in frame
    assert frame["drone"]["x"] <= ARENA_WIDTH_M
    assert frame["drone"]["y"] <= ARENA_HEIGHT_M


def test_simulation_plugin_lifecycle():
    sim = SimulationPlugin()
    assert sim.is_running is True
    assert sim.is_paused is False

    sim.pause()
    assert sim.is_paused is True

    sim.resume()
    assert sim.is_paused is False

    sim.reset()
    assert sim.flight_mode == "RTL / LAND"
    assert len(sim.staged_waypoints) == 0


def test_simulation_poll_frame_data():
    sim = SimulationPlugin()
    result = sim.poll()

    assert result.status == "SIMULATION"
    frame = result.frame
    assert frame is not None

    drone = frame["drone"]
    assert 0.0 <= drone["x"] <= ARENA_WIDTH_M
    assert 0.0 <= drone["y"] <= ARENA_HEIGHT_M
    assert 0.0 <= drone["heading"] <= 360.0

    telem = frame["telemetry"]
    assert 0 <= telem["battery"] <= 100
    assert 18.0 <= telem["voltage"] <= 25.2

    # Survivor discovery
    survivors = frame["survivors"]
    assert isinstance(survivors, list)
    assert len(survivors) >= 1  # S01 discovered at sec 0


def test_simulation_command_handling():
    sim = SimulationPlugin()

    # 1. Abort
    ack = sim.send_command("ABORT")
    assert ack["status"] == "ACCEPTED"
    assert sim.flight_mode == "EMERGENCY LAND"

    # 2. RTL
    ack = sim.send_command("RTL")
    assert ack["status"] == "ACCEPTED"
    assert sim.flight_mode == "RTL / LAND"

    # 3. Stage Waypoint
    ack = sim.send_command("STAGE_WAYPOINT", {"x": 5.5, "y": 9.2, "tag": "WP-TEST"})
    assert ack["status"] == "ACCEPTED"
    assert len(sim.staged_waypoints) == 1

    # 4. Commit Waypoints
    ack = sim.send_command("COMMIT_WAYPOINTS")
    assert ack["status"] == "ACCEPTED"
    assert len(sim.staged_waypoints) == 0
    assert (5.5, 9.2) in sim.accepted_waypoints

    # 5. Mark Survivor
    ack = sim.send_command("MARK_SURVIVOR", {"x": 8.0, "y": 8.0, "grid": "F6"})
    assert ack["status"] == "ACCEPTED"
    assert len(sim.user_marked_survivors) == 1
    assert sim.user_marked_survivors[0]["grid"] == "F6"


def test_json_file_plugin(tmp_path: Path):
    test_json = tmp_path / "mission.json"
    plugin = JsonFilePlugin(test_json)

    # When file does not exist
    res = plugin.poll()
    assert res.status == "WAITING"

    # Create valid file
    payload = {
        "mode": "AUTONOMOUS",
        "coverage": 78,
        "drone": {"x": 4.2, "y": 8.1, "altitude": 2.1},
        "telemetry": {"battery": 82, "voltage": 22.1},
    }
    test_json.write_text(json.dumps(payload), encoding="utf-8")

    res2 = plugin.poll()
    assert res2.status == "CONNECTED"
    assert res2.frame["coverage"] == 78
    assert res2.frame["drone"]["x"] == 4.2
