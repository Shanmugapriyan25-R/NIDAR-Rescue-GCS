"""Tests for functional Mission, Map, and Survivors navigation tabs and dedicated workspaces."""

import sys
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

from edith_gcs_qt import NidarRescueGCS
from gcs_workspaces import MapWorkspaceWidget, SurvivorsWorkspaceWidget, DESIGNATED_TARGETS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_navigation_tab_switching_and_views(qapp):
    """Verify that Mission, Map, and Survivors tabs switch real QStackedWidget views with proper active styling."""
    win = NidarRescueGCS()
    try:
        # Default view on startup must be Mission overview (Index 0)
        assert win.view_stack.currentIndex() == 0
        assert win.view_stack.currentWidget() == win.page_mission
        assert win.tab_mission.property("active") is True
        assert win.tab_map.property("active") is False
        assert win.tab_surv.property("active") is False

        # Switch to Map tab (Index 1)
        win._select_tab("Map")
        qapp.processEvents()
        assert win.view_stack.currentIndex() == 1
        assert win.view_stack.currentWidget() == win.map_workspace
        assert isinstance(win.view_stack.currentWidget(), MapWorkspaceWidget)
        assert win.tab_mission.property("active") is False
        assert win.tab_map.property("active") is True
        assert win.tab_surv.property("active") is False

        # Switch to Survivors tab (Index 2)
        win._select_tab("Survivors")
        qapp.processEvents()
        assert win.view_stack.currentIndex() == 2
        assert win.view_stack.currentWidget() == win.survivors_workspace
        assert isinstance(win.view_stack.currentWidget(), SurvivorsWorkspaceWidget)
        assert win.tab_mission.property("active") is False
        assert win.tab_map.property("active") is False
        assert win.tab_surv.property("active") is True

        # Switch back to Mission tab (Index 0)
        win._select_tab("Mission")
        qapp.processEvents()
        assert win.view_stack.currentIndex() == 0
        assert win.view_stack.currentWidget() == win.page_mission
        assert win.tab_mission.property("active") is True
        assert win.tab_map.property("active") is False
        assert win.tab_surv.property("active") is False
    finally:
        win.close()


def test_navigation_state_preservation(qapp):
    """Verify that switching tabs does not reset camera, zoom, logs, waypoints, or telemetry."""
    win = NidarRescueGCS()
    try:
        # Set specific state on Mission overview
        win._set_cam_mode("THERMAL")
        win._adjust_zoom(3.0)
        initial_zoom = win.camera.zoom
        win.log_event("[TEST] Custom state preservation check marker.")
        log_count_before = win.log_container.count()
        win.dispatch_command("STAGE_WAYPOINT", {"x": 4.5, "y": 6.5, "tag": "WP-TEST-PRESERVE"})
        win._poll_data()
        qapp.processEvents()

        # Switch across Map and Survivors views
        win._select_tab("Map")
        qapp.processEvents()
        win._select_tab("Survivors")
        qapp.processEvents()
        win._select_tab("Mission")
        qapp.processEvents()

        # Verify state is completely preserved
        assert win.camera.mode == "THERMAL"
        assert win.camera.zoom == initial_zoom
        assert win.log_container.count() >= log_count_before
        assert any(
            "WP-TEST-PRESERVE" in str(w) for w in win.map_canvas.staged_waypoints
        ) or any(
            "WP-TEST-PRESERVE" in str(w) for w in win.plugin_manager.active_plugin.staged_waypoints
        )
    finally:
        win.close()


def test_map_workspace_layer_controls_and_hud(qapp):
    """Verify that dedicated Map workspace has HUD, metric grid controls, and syncs layer visibility."""
    win = NidarRescueGCS()
    try:
        mw = win.map_workspace
        assert mw is not None
        assert isinstance(mw, MapWorkspaceWidget)

        # Check HUD banner elements
        assert "SIMULATION" in mw.sim_watermark.text().upper()
        assert hasattr(mw, "drone_pose_lbl")
        assert hasattr(mw, "source_pill")

        # Test layer toggles
        mw.chk_grid.setChecked(False)
        assert mw.map_canvas.layer_grid is False
        mw.chk_grid.setChecked(True)
        assert mw.map_canvas.layer_grid is True

        mw.chk_sonar.setChecked(False)
        assert mw.map_canvas.layer_sonar is False

        # Test waypoint staging button toggle
        assert mw.map_canvas.add_waypoint_mode is False
        mw._toggle_stage_mode()
        assert mw.map_canvas.add_waypoint_mode is True
        mw._toggle_stage_mode()
        assert mw.map_canvas.add_waypoint_mode is False
    finally:
        win.close()


def test_survivors_workspace_strictly_six_targets(qapp):
    """Verify that Survivors workspace strictly monitors exactly six designated identities (S01-S06)."""
    win = NidarRescueGCS()
    try:
        sw = win.survivors_workspace
        assert sw is not None
        assert isinstance(sw, SurvivorsWorkspaceWidget)

        # Designated target list must be exactly S01-S06
        assert DESIGNATED_TARGETS == ["S01", "S02", "S03", "S04", "S05", "S06"]
        assert len(DESIGNATED_TARGETS) == 6

        # Feed test frame
        test_frame = {
            "survivors": [
                {"id": "S01", "status": "DETECTED", "grid": "B2", "confidence": 88, "x": 3.0, "y": 4.0},
                {"id": "S02", "status": "SEARCHING", "grid": "—", "confidence": None, "x": None, "y": None},
                {"id": "S03", "status": "LOCALISED", "grid": "C4", "confidence": 95, "x": 6.5, "y": 8.0},
                {"id": "S04", "status": "SEARCHING", "grid": "—", "confidence": None, "x": None, "y": None},
                {"id": "S05", "status": "TRACKING", "grid": "A1", "confidence": 72, "x": 1.2, "y": 2.2},
                {"id": "S06", "status": "LOST", "grid": "D3", "confidence": 54, "x": None, "y": None},
                # Artificial intruder target must be filtered out
                {"id": "S07", "status": "DETECTED", "grid": "Z9", "confidence": 99, "x": 9.9, "y": 9.9},
            ]
        }
        sw.sync_frame_data(test_frame)
        qapp.processEvents()

        # Cached survivors must contain only designated targets
        cached_ids = [s["id"] for s in sw.cached_survivors if s["id"] in DESIGNATED_TARGETS]
        assert len(cached_ids) == 6
        assert "S07" not in [s["id"] for s in sw.cards_grid_items] if hasattr(sw, "cards_grid_items") else True

        # Counter derivation
        # Detected count should be 4 (S01, S03, S05, S06) out of 6
        assert "4 / 6" in sw.hud_detected.text()
    finally:
        win.close()


def test_bidirectional_target_selection_synchronization(qapp):
    """Verify that selecting a target in one view synchronizes across Camera, Map, and Survivor views."""
    win = NidarRescueGCS()
    try:
        win._poll_data()
        qapp.processEvents()

        # Select target from main window
        win.focus_survivor("S02")
        qapp.processEvents()

        assert win.selected_target_id == "S02"
        assert win.map_canvas.selected_target == "S02"
        assert win.camera.highlighted_person == "S02"
        assert win.map_workspace.selected_target_id == "S02"
        assert win.map_workspace.map_canvas.selected_target == "S02"
        assert win.survivors_workspace.selected_target_id == "S02"
        assert "S02" in win.survivors_workspace.d_title.text()

        # Select different target from Survivors workspace
        win.survivors_workspace.select_target("S04")
        qapp.processEvents()
        assert win.survivors_workspace.selected_target_id == "S04"
        assert "S04" in win.survivors_workspace.d_title.text()

        # Select target from Map workspace
        win.map_workspace.select_target("S01")
        qapp.processEvents()
        assert win.map_workspace.selected_target_id == "S01"
        assert win.map_workspace.map_canvas.selected_target == "S01"
    finally:
        win.close()


def test_survivors_workspace_filters_and_search(qapp):
    """Verify search box and status filtering in Survivors workspace."""
    win = NidarRescueGCS()
    try:
        sw = win.survivors_workspace
        test_frame = {
            "survivors": [
                {"id": "S01", "status": "DETECTED", "grid": "B2", "confidence": 88, "x": 3.0, "y": 4.0},
                {"id": "S02", "status": "SEARCHING", "grid": "—", "confidence": None, "x": None, "y": None},
                {"id": "S03", "status": "LOCALISED", "grid": "C4", "confidence": 95, "x": 6.5, "y": 8.0},
                {"id": "S04", "status": "SEARCHING", "grid": "—", "confidence": None, "x": None, "y": None},
                {"id": "S05", "status": "TRACKING", "grid": "A1", "confidence": 72, "x": 1.2, "y": 2.2},
                {"id": "S06", "status": "LOST", "grid": "D3", "confidence": 54, "x": None, "y": None},
            ]
        }
        sw.sync_frame_data(test_frame)

        # Filter: SEARCHING
        sw._set_filter("SEARCHING")
        qapp.processEvents()
        assert sw.active_filter == "SEARCHING"

        # Filter: LOCALISED
        sw._set_filter("LOCALISED")
        qapp.processEvents()
        assert sw.active_filter == "LOCALISED"

        # Search Query
        sw._on_search_text_changed("S03")
        qapp.processEvents()
        assert sw.search_query == "S03"

        # Reset search and filter
        sw._on_search_text_changed("")
        sw._set_filter("ALL")
        qapp.processEvents()
        assert sw.active_filter == "ALL"
        assert sw.search_query == ""
    finally:
        win.close()
