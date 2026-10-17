"""Comprehensive automated verification tests for the NIDAR Rescue GCS Autonomous Six-Person Rescue Mission.

Covers all core requirements:
- Strictly six designated target identities (S01-S06)
- Detection counter boundaries strictly 0/6 through 6/6
- Duplicate detection suppression and extraneous identity filtering
- Target loss and reacquisition lifecycle (S02 temporary loss)
- Cross-widget telemetry data consistency (Camera, Map, Telemetry grid)
- Mission state machine transitions and strict rejection of MANUAL flight mode
- Quick action controls lifecycle (Start, Pause, Resume, RTL, Reset)
- Responsive layout verification at target 16:9 resolutions (1920x1080, 1600x900, 1366x768)
"""

import sys
import time
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gcs_data_plugins import (
    DataPluginManager, SimulationPlugin, MissionState, MissionStateMachine,
    DESIGNATED_TARGET_IDS, SIM_TARGETS_MASTER, associate_and_suppress_detections
)
from edith_gcs_qt import NidarRescueGCS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_designated_target_identities_and_roster():
    """Verify strictly six designated target identities (S01 to S06) across plugin and master."""
    assert DESIGNATED_TARGET_IDS == ["S01", "S02", "S03", "S04", "S05", "S06"]
    assert len(SIM_TARGETS_MASTER) == 6
    master_ids = [t["id"] for t in SIM_TARGETS_MASTER]
    assert master_ids == DESIGNATED_TARGET_IDS

    sim = SimulationPlugin()
    res = sim.poll()
    frame = res.frame
    assert frame is not None

    targets = frame.get("survivors") or frame.get("targets")
    assert len(targets) == 6
    for idx, target in enumerate(targets):
        expected_id = f"S0{idx+1}"
        assert target["id"] == expected_id
        assert target["id"] in DESIGNATED_TARGET_IDS


def test_gui_renders_exact_six_survivor_cards(qapp):
    """Verify that NidarRescueGCS builds and maintains exactly 6 cards for S01-S06."""
    win = NidarRescueGCS()
    win.show()
    qapp.processEvents()

    assert len(win.survivor_cards) == 6
    for target_id in DESIGNATED_TARGET_IDS:
        assert target_id in win.survivor_cards
        card = win.survivor_cards[target_id]
        assert card.survivor_id == target_id

    win.close()


def test_detection_counter_boundaries_0_to_6(qapp):
    """Verify counter boundaries strictly range from 0/6 up to 6/6 without fabricated counts."""
    win = NidarRescueGCS()
    win.show()
    qapp.processEvents()

    # 1. Boundary 0/6: All targets SEARCHING
    sim = win.plugin_manager.plugins.get("Simulation")
    assert sim is not None

    sim.test_overrides = {
        tid: {
            "id": tid, "number": tid.lstrip("S"), "grid": "—",
            "x": None, "y": None, "lat": None, "lon": None,
            "confidence": None, "status": "SEARCHING", "tracking_status": "NOT DETECTED",
            "loc_status": "UNAVAILABLE", "movement": "—", "bbox": None,
            "thumb": "assets/thumb_s1.png", "color_hex": "#94a3b8", "is_stale": False,
        }
        for tid in DESIGNATED_TARGET_IDS
    }
    win._poll_data()
    qapp.processEvents()

    assert win.found_badge.text() == "● 0 / 6 DETECTED"
    assert win.surv_stat_lbl.text() == "0 / 6"
    assert win.cov_summary_lbl.text() == "0 / 6"

    # 2. Boundary 1/6: Only S01 detected
    sim.test_overrides["S01"]["status"] = "LOCALISED"
    sim.test_overrides["S01"]["loc_status"] = "CONFIRMED"
    sim.test_overrides["S01"]["confidence"] = 93
    sim.test_overrides["S01"]["x"] = 2.7
    sim.test_overrides["S01"]["y"] = 3.8
    sim.test_overrides["S01"]["lat"] = 10.8462
    sim.test_overrides["S01"]["lon"] = 76.2711

    win._poll_data()
    qapp.processEvents()

    assert win.found_badge.text() == "● 1 / 6 DETECTED"
    assert win.surv_stat_lbl.text() == "1 / 6"

    # 3. Boundary 6/6: All six targets confirmed
    for tid in DESIGNATED_TARGET_IDS:
        sim.test_overrides[tid]["status"] = "LOCALISED"
        sim.test_overrides[tid]["loc_status"] = "CONFIRMED"
        sim.test_overrides[tid]["confidence"] = 85
        sim.test_overrides[tid]["x"] = 5.0
        sim.test_overrides[tid]["y"] = 5.0

    win._poll_data()
    qapp.processEvents()

    assert win.found_badge.text() == "● 6 / 6 DETECTED"
    assert win.surv_stat_lbl.text() == "6 / 6"
    assert win.cov_summary_lbl.text() == "6 / 6"

    win.close()


def test_duplicate_detection_suppression():
    """Verify duplicate camera observations near the same target are suppressed into single identities."""
    raw_detections = [
        # Two bounding boxes/readings for S01 in Sector A1 (2.7, 3.8)
        {"id": "RAW_DET_1", "x": 2.72, "y": 3.79, "confidence": 92, "bbox": [0.10, 0.20, 0.25, 0.40]},
        {"id": "RAW_DET_2", "x": 2.68, "y": 3.82, "confidence": 95, "bbox": [0.11, 0.21, 0.24, 0.41]},
        # One reading for S02 in Sector C4 (7.8, 5.25)
        {"id": "RAW_DET_3", "x": 7.81, "y": 5.24, "confidence": 88, "bbox": [0.40, 0.30, 0.55, 0.50]},
        # Extraneous reading outside arena that does not match any designated target
        {"id": "RAW_DET_EXTRANEOUS", "x": 99.0, "y": 99.0, "confidence": 50, "bbox": [0.8, 0.8, 0.9, 0.9]},
    ]

    associated, counts = associate_and_suppress_detections(raw_detections)

    # Exactly 6 slots returned
    assert len(associated) == 6
    target_map = {t["id"]: t for t in associated}

    # S01: Highest confidence (95) selected, duplicate suppressed
    assert target_map["S01"]["status"] == "LOCALISED"
    assert target_map["S01"]["confidence"] == 95
    assert target_map["S01"]["loc_status"] == "CONFIRMED"

    # S02: Single detection associated
    assert target_map["S02"]["status"] == "LOCALISED"
    assert target_map["S02"]["confidence"] == 88

    # S03-S06: Remain SEARCHING
    for tid in ["S03", "S04", "S05", "S06"]:
        assert target_map[tid]["status"] == "SEARCHING"
        assert target_map[tid]["loc_status"] == "UNAVAILABLE"

    # Detection count is strictly 2 / 6
    assert counts["detected"] == 2
    assert counts["total"] == 6


def test_target_loss_and_reacquisition_lifecycle():
    """Verify S02 temporary loss (sec=42) and reacquisition (sec=48) timeline behavior."""
    sim = SimulationPlugin()

    # Before discovery (t = 10s) -> S02 SEARCHING
    sim.start_time = time.monotonic() - 10.0
    f1 = sim.poll().frame
    s02_t1 = next(t for t in f1["survivors"] if t["id"] == "S02")
    assert s02_t1["status"] == "SEARCHING"
    assert s02_t1["loc_status"] == "UNAVAILABLE"

    # Detected & Tracking (t = 25s) -> S02 DETECTED or TRACKING
    sim.start_time = time.monotonic() - 25.0
    f2 = sim.poll().frame
    s02_t2 = next(t for t in f2["survivors"] if t["id"] == "S02")
    assert s02_t2["status"] in {"DETECTED", "TRACKING"}
    assert s02_t2["is_stale"] is False

    # Occluded / Lost (t = 36s, within lost_sec=32..reacquire_sec=40) -> S02 LOST
    sim.start_time = time.monotonic() - 36.0
    f3 = sim.poll().frame
    s02_t3 = next(t for t in f3["survivors"] if t["id"] == "S02")
    assert s02_t3["status"] == "LOST"
    assert s02_t3["is_stale"] is True
    assert s02_t3["loc_status"] == "ESTIMATED"

    # Reacquired & Localised (t = 52s, after localize_sec=48) -> S02 LOCALISED and active
    sim.start_time = time.monotonic() - 52.0
    f4 = sim.poll().frame
    s02_t4 = next(t for t in f4["survivors"] if t["id"] == "S02")
    assert s02_t4["status"] == "LOCALISED"
    assert s02_t4["is_stale"] is False


def test_telemetry_consistency_camera_map_telemetry(qapp):
    """Verify altitude, speed, heading, and battery match perfectly across all widgets."""
    win = NidarRescueGCS()
    win.show()

    sim = win.plugin_manager.plugins.get("Simulation")
    sim.start_time = time.monotonic() - 25.0
    win._poll_data()
    qapp.processEvents()

    # 1. Telemetry values from frame
    frame = sim.poll().frame
    telem = frame["telemetry"]
    drone = frame["drone"]

    exp_alt = drone.get("altitude") or telem.get("altitude")
    exp_spd = drone.get("speed") or telem.get("speed")
    exp_hdg = drone.get("heading") or telem.get("heading")
    exp_bat = telem.get("battery")

    # 2. Check main telemetry panel labels
    assert win.telem_labels["⛰ Altitude"].text() == f"{exp_alt} m"
    assert win.telem_labels["💨 Speed"].text() == f"{exp_spd} m/s"
    assert win.telem_labels["🧭 Heading"].text() == f"{exp_hdg}°"
    assert win.telem_labels["🔋 Battery"].text() == f"{exp_bat}%"

    # 3. Check Camera HUD state
    assert win.camera.telem_hud["altitude"] == exp_alt
    assert win.camera.telem_hud["speed"] == exp_spd
    assert win.camera.telem_hud["heading"] == exp_hdg
    assert win.camera.telem_hud["battery"] == exp_bat

    # 4. Check Map canvas drone state
    assert win.map_canvas.drone_pos == (drone["x"], drone["y"])
    assert win.map_canvas.drone_yaw == exp_hdg

    win.close()


def test_mission_state_machine_and_manual_rejection():
    """Verify valid autonomous state machine transitions and strict rejection of MANUAL flight mode."""
    sm = MissionStateMachine(initial_state=MissionState.IDLE)
    assert sm.get_state() == MissionState.IDLE

    # Valid sequence: IDLE -> READY -> AUTONOMOUS_SEARCH
    sm.transition(MissionState.READY, "Pre-flight checks passed")
    assert sm.get_state() == MissionState.READY

    sm.transition(MissionState.AUTONOMOUS_SEARCH, "Mission start command")
    assert sm.get_state() == MissionState.AUTONOMOUS_SEARCH

    # Pause Hold & Resume
    sm.transition(MissionState.PAUSED_HOLD, "Operator hold command")
    assert sm.get_state() == MissionState.PAUSED_HOLD

    sm.transition(MissionState.AUTONOMOUS_SEARCH, "Operator resume command")
    assert sm.get_state() == MissionState.AUTONOMOUS_SEARCH

    # Invalid jump rejection: AUTONOMOUS_SEARCH cannot jump straight to IDLE
    success, msg = sm.transition(MissionState.IDLE, "Illegal jump")
    assert success is False
    assert "Illegal state transition" in msg

    # Simulation engine rejects MANUAL mode command
    sim = SimulationPlugin()
    res = sim.send_command("SET_MODE", {"mode": "MANUAL"})
    assert res["status"] == "REJECTED"
    assert "autonomous" in res["message"].lower() or "rejected" in res["message"].lower()


def test_quick_actions_state_and_enabling(qapp):
    """Verify Quick Action buttons dynamically enable and disable according to mission state."""
    win = NidarRescueGCS()
    win.show()
    qapp.processEvents()

    # Initial READY state
    assert win.btn_qa_start.isEnabled() is True
    assert win.btn_qa_pause.isEnabled() is False
    assert win.btn_qa_resume.isEnabled() is False
    assert win.btn_qa_rtl.isEnabled() is True
    assert win.btn_qa_reset.isEnabled() is True

    # Start Mission
    win.start_autonomous_mission()
    qapp.processEvents()
    assert win.flight_mode == "AUTONOMOUS"
    assert win.btn_qa_start.isEnabled() is False
    assert win.btn_qa_pause.isEnabled() is True
    assert win.btn_qa_resume.isEnabled() is False

    # Pause Mission
    win.pause_mission()
    qapp.processEvents()
    assert win.flight_mode == "PAUSED / SAFE HOLD"
    assert win.btn_qa_start.isEnabled() is False
    assert win.btn_qa_pause.isEnabled() is False
    assert win.btn_qa_resume.isEnabled() is True

    # Resume Mission
    win.resume_mission()
    qapp.processEvents()
    assert win.flight_mode == "AUTONOMOUS"
    assert win.btn_qa_pause.isEnabled() is True
    assert win.btn_qa_resume.isEnabled() is False

    win.close()


def test_simulation_reset_and_repeated_execution(qapp):
    """Verify simulation reset restores initial 0/6 detection roster and enables repeatable runs."""
    win = NidarRescueGCS()
    win.show()
    sim = win.plugin_manager.plugins.get("Simulation")

    # Advance to 60s
    sim.start_time = time.monotonic() - 60.0
    win._poll_data()
    qapp.processEvents()

    detected_first_run = win.found_badge.text()
    assert "0 / 6" not in detected_first_run

    # Reset
    sim.send_command("RESET_MISSION")
    win.flight_mode = "AUTONOMOUS"
    win._poll_data()
    qapp.processEvents()

    # Must be reset back to 0/6 detected
    assert win.found_badge.text() == "● 0 / 6 DETECTED"
    assert win.surv_stat_lbl.text() == "0 / 6"

    win.close()


@pytest.mark.parametrize("width,height", [
    (1920, 1080),  # Full HD 16:9
    (1600, 900),   # HD+ 16:9
    (1366, 768),   # Standard Laptop 16:9
])
def test_responsive_window_resolutions(qapp, width, height):
    """Verify application layout renders cleanly at all target 16:9 desktop resolutions."""
    win = NidarRescueGCS()
    win.resize(width, height)
    win.show()
    qapp.processEvents()

    assert win.width() >= 1100
    assert win.height() >= 640
    assert win.map_canvas.width() > 300
    assert win.camera.width() > 200
    assert win.donut.width() > 80
    assert len(win.survivor_cards) == 6

    # Verify no clipping on core labels
    assert win.found_badge.isVisible()
    assert win.timer_pill.isVisible()
    assert win.mode_pill.isVisible()

    win.close()
