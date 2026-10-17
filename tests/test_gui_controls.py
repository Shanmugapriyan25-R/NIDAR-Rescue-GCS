"""Tests for GUI controls, user interactions, snapshots, survivor selection, and clean shutdown."""

import sys
import glob
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

from edith_gcs_qt import NidarRescueGCS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_tab_selection(qapp):
    win = NidarRescueGCS()
    win._select_tab("Map")
    assert win.tab_map.property("active") is True
    assert win.tab_mission.property("active") is False

    win._select_tab("Survivors")
    assert win.tab_surv.property("active") is True
    win.close()


def test_camera_mode_and_zoom(qapp):
    win = NidarRescueGCS()

    # Mode switch
    win._set_cam_mode("THERMAL")
    assert win.camera.mode == "THERMAL"
    assert win.btn_thermal.property("active") is True

    win._set_cam_mode("RGB")
    assert win.camera.mode == "RGB"
    assert win.btn_rgb.property("active") is True

    # Zoom bounds
    win._adjust_zoom(5.0)
    assert 1.0 <= win.camera.zoom <= 24.0

    win._adjust_zoom(-30.0)
    assert win.camera.zoom == 1.0
    win.close()


def test_snapshot_saving_to_disk(qapp):
    win = NidarRescueGCS()
    win.show()
    qapp.processEvents()

    # Capture snapshot
    win.capture_snapshot()
    qapp.processEvents()

    snaps = glob.glob("output/snapshots/*.jpg")
    assert len(snaps) >= 1
    latest_snap = Path(snaps[-1])
    assert latest_snap.exists()
    assert latest_snap.stat().st_size > 500  # Non-empty image
    win.close()


def test_video_recording_lifecycle(qapp):
    win = NidarRescueGCS()
    assert win.camera.is_recording is False

    win.toggle_recording()
    assert win.camera.is_recording is True
    assert win.rec_btn.text() == "⏹ Stop"

    win.camera.capture_video_frame()

    win.toggle_recording()
    assert win.camera.is_recording is False
    assert win.rec_btn.text() == "● Record"
    win.close()


def test_survivor_focus_interaction(qapp):
    win = NidarRescueGCS()
    win._poll_data()
    qapp.processEvents()

    # Verify at least one survivor card was built
    assert len(win.survivor_cards) >= 1
    first_sid = list(win.survivor_cards.keys())[0]

    win.focus_survivor(first_sid)
    assert win.map_canvas.selected_target == first_sid
    assert win.camera.highlighted_person == first_sid
    assert win.survivor_cards[first_sid].is_active_selected is True
    win.close()


def test_waypoint_staging_and_selection(qapp):
    win = NidarRescueGCS()
    win._on_waypoint_added(3.2, 7.8, "WP-TEST [D8]")
    win._poll_data()
    qapp.processEvents()

    assert len(win.map_canvas.staged_waypoints) >= 1
    wp = win.map_canvas.staged_waypoints[-1]
    assert wp[0] == 3.2
    assert wp[1] == 7.8
    assert wp[2] == "WP-TEST [D8]"

    # Test waypoint selection
    win._on_waypoint_selected("staged", 0, 3.2, 7.8, "WP-TEST [D8]")
    assert win.map_canvas.selected_waypoint is not None
    assert win.map_canvas.selected_waypoint[0] == "staged"
    win.close()


def test_flight_mode_menu_selection(qapp):
    win = NidarRescueGCS()
    win._set_flight_mode("MANUAL")
    assert win.flight_mode == "MANUAL"
    assert win.telem_labels["🎮 Mode"].text() == "MANUAL"
    assert "MANUAL" in win.mode_pill.text()

    win._set_flight_mode("AUTONOMOUS")
    assert win.flight_mode == "AUTONOMOUS"
    assert win.telem_labels["🎮 Mode"].text() == "AUTONOMOUS"

    win._set_flight_mode("RTL / LAND")
    assert win.flight_mode == "RTL / LAND"
    win.close()


def test_telemetry_consistency_across_widgets(qapp):
    """Verify that camera overlay, telemetry panel, and map canvas share the exact same values."""
    win = NidarRescueGCS()
    win._poll_data()
    qapp.processEvents()

    # Get values from shared poll
    cam_telem = win.camera.telem_hud
    telem_alt = win.telem_labels["⛰ Altitude"].text()
    telem_bat = win.telem_labels["🔋 Battery"].text()
    telem_spd = win.telem_labels["💨 Speed"].text()
    telem_hdg = win.telem_labels["🧭 Heading"].text()

    assert f"{cam_telem['altitude']} m" == telem_alt
    assert f"{cam_telem['battery']}%" == telem_bat
    assert f"{cam_telem['speed']} m/s" == telem_spd
    assert f"{cam_telem['heading']}°" == telem_hdg

    # Map drone position matches ENU coordinates label
    dx, dy = win.map_canvas.drone_pos
    assert f"X: {dx:.1f}m  Y: {dy:.1f}m" in win.enu_sub_lbl.text()
    win.close()


def test_clickable_subsystems_and_sensors(qapp):
    """Verify clicking subsystem rows and sensor pills logs diagnostic telemetry."""
    win = NidarRescueGCS()
    initial_log_count = win.log_container.count()

    # Click a subsystem row
    win._on_subsystem_clicked("Jetson Orin")
    assert win.log_container.count() == initial_log_count + 1

    # Click a sensor pill
    win._on_sensor_pill_clicked("LiDAR")
    assert win.log_container.count() == initial_log_count + 2
    win.close()


def test_stale_detection_handling(qapp):
    """Verify that a survivor with is_stale=True renders a STALE badge."""
    win = NidarRescueGCS()
    sample_survivors = [
        {
            "id": "S99",
            "number": "99",
            "grid": "A1",
            "x": 2.0,
            "y": 2.0,
            "confidence": 60,
            "status": "SEARCHING",
            "is_stale": True,
            "thumb": "assets/thumb_s1.png",
            "color_hex": "#ef4444",
        }
    ]
    win._sync_survivor_cards(sample_survivors)
    qapp.processEvents()

    card = win.survivor_cards.get("S99")
    assert card is not None
    assert card.is_stale is True
    win.close()
