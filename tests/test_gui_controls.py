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


def test_waypoint_staging(qapp):
    win = NidarRescueGCS()
    win._on_waypoint_added(3.2, 7.8, "WP-TEST [D8]")
    win._poll_data()
    qapp.processEvents()

    assert len(win.map_canvas.staged_waypoints) >= 1
    wp = win.map_canvas.staged_waypoints[-1]
    assert wp[0] == 3.2
    assert wp[1] == 7.8
    assert wp[2] == "WP-TEST [D8]"
    win.close()


def test_flight_mode_toggle(qapp):
    win = NidarRescueGCS()
    initial_mode = win.flight_mode
    win.toggle_flight_mode()
    assert win.flight_mode != initial_mode
    assert win.telem_labels["🎮 Mode"].text() == win.flight_mode
    win.close()
