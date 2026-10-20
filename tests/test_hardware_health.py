"""Tests for common health status model, subsystem manager, and interactive diagnostics dialog."""

import sys
import time
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

from health_model import HealthState, HealthSystemManager, SubsystemRecord, STATUS_STYLE
from subsystem_diagnostics import SubsystemDiagnosticsDialog, SubsystemItemWidget
from edith_gcs_qt import NidarRescueGCS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_seven_health_states_and_style_tokens():
    """Verify that all 7 required health states exist, parse cleanly, and have valid visual style tokens."""
    expected_states = [
        "OK",
        "WARNING",
        "ERROR",
        "DISCONNECTED",
        "STALE",
        "SIMULATED",
        "NOT CONFIGURED",
    ]
    for st in expected_states:
        enum_val = HealthState.from_str(st)
        assert enum_val.value == st
        assert st in STATUS_STYLE
        style = STATUS_STYLE[st]
        assert "bg" in style
        assert "badge_text" in style
        assert "icon" in style
        assert len(style["icon"]) >= 1


def test_health_manager_all_eleven_subsystems():
    """Verify that all 11 Genuine Subsystems are registered with appropriate metadata and categories."""
    mgr = HealthSystemManager(is_simulation=True)
    expected_subsystems = [
        ("Jetson Orin", "COMPUTE"),
        ("RadioLink CrossFlight", "AUTOPILOT"),
        ("Power & Battery System", "POWER"),
        ("RPLIDAR C1", "PERCEPTION"),
        ("IMU / GPS / Localisation", "NAVIGATION & ODOMETRY"),
        ("Camera & Gimbal", "PAYLOAD"),
        ("ROS 2 Bridge", "NETWORK"),
        ("MAVLink", "FLIGHT PROTOCOL"),
        ("AI Detection Pipeline", "VISION & DEEP LEARNING"),
        ("SLAM & Mapping Pipeline", "SPATIAL MAPPING"),
        ("Obstacle Radar", "OPTIONAL"),
    ]

    for name, cat in expected_subsystems:
        sub = mgr.get_subsystem(name)
        assert sub is not None, f"Subsystem {name} must exist in HealthSystemManager."
        assert cat in sub.category, f"Subsystem {name} category mismatch: expected {cat} in {sub.category}."
        assert isinstance(sub.metrics, dict)
        assert sub.description
        assert sub.troubleshooting


def test_unconfigured_hardware_stays_not_configured():
    """Verify that optional unconfigured hardware is explicitly labelled NOT CONFIGURED and never falsely reported healthy."""
    mgr = HealthSystemManager(is_simulation=True)
    radar = mgr.get_subsystem("Obstacle Radar")
    assert radar is not None
    assert radar.current_state == HealthState.NOT_CONFIGURED

    # Freshness evaluation must NOT promote unconfigured hardware
    mgr.evaluate_all_freshness()
    assert radar.current_state == HealthState.NOT_CONFIGURED


def test_stale_transition_and_recovery():
    """Verify that a subsystem transitions to STALE after exceeding freshness timeout and recovers on fresh update."""
    mgr = HealthSystemManager(is_simulation=True)
    lidar = mgr.get_subsystem("RPLIDAR C1")
    assert lidar is not None
    lidar.freshness_timeout_sec = 0.05  # 50 ms for fast test

    # Fresh update
    lidar.update_metrics(
        {"Scan Frequency": "10.0 Hz", "Valid Points": "360"},
        state=HealthState.OK,
        source_label="TEST DRIVER",
    )
    assert lidar.current_state == HealthState.OK

    # Wait past freshness timeout
    time.sleep(0.08)
    lidar.evaluate_freshness()
    assert lidar.current_state == HealthState.STALE
    assert any("STALE" in str(trans) for trans in lidar.status_history)

    # Valid data returns
    lidar.update_metrics(
        {"Scan Frequency": "10.0 Hz", "Valid Points": "360"},
        state=HealthState.OK,
        source_label="TEST DRIVER",
    )
    assert lidar.current_state == HealthState.OK


def test_diagnostics_dialog_inspection_and_injection(qapp):
    """Verify that SubsystemDiagnosticsDialog displays accurate metrics and allows operator state injection."""
    mgr = HealthSystemManager(is_simulation=True)
    dialog = SubsystemDiagnosticsDialog(
        subsystem_name="Jetson Orin",
        health_manager=mgr,
        is_simulation=True,
    )
    try:
        dialog.show()
        qapp.processEvents()

        assert "Jetson Orin" in dialog.name_label.text()
        assert "COMPUTE" in dialog.category_label.text()

        injected_records = []
        dialog.state_injected.connect(lambda name, state: injected_records.append((name, state)))

        # Test state injection: WARNING
        idx_warn = dialog.state_combo.findText("WARNING")
        if idx_warn >= 0:
            dialog.state_combo.setCurrentIndex(idx_warn)
            dialog._apply_test_state()
            qapp.processEvents()

            assert len(injected_records) == 1
            assert injected_records[0] == ("Jetson Orin", "WARNING")
            assert mgr.get_subsystem("Jetson Orin").current_state == HealthState.WARNING
            assert "WARNING" in dialog.status_pill.text()

        # Test state injection: ERROR
        idx_err = dialog.state_combo.findText("ERROR")
        if idx_err >= 0:
            dialog.state_combo.setCurrentIndex(idx_err)
            dialog._apply_test_state()
            qapp.processEvents()

            assert len(injected_records) == 2
            assert injected_records[1] == ("Jetson Orin", "ERROR")
            assert mgr.get_subsystem("Jetson Orin").current_state == HealthState.ERROR
            assert "ERROR" in dialog.status_pill.text()
    finally:
        dialog.close()


def test_main_gui_health_panel_interaction(qapp):
    """Verify that clicking subsystem rows in the main dashboard opens the diagnostics dialog with correct subsystem."""
    win = NidarRescueGCS()
    try:
        # Check all 11 subsystem rows in GUI right column
        assert len(win.health_widgets) >= 11

        # Check Jetson Orin click
        win._on_subsystem_clicked("Jetson Orin")
        qapp.processEvents()
        assert win.diagnostics_dialog is not None
        assert win.diagnostics_dialog.isVisible()
        assert win.diagnostics_dialog.subsystem_name == "Jetson Orin"

        # Check RPLIDAR C1 click switches subsystem in open dialog
        win._on_subsystem_clicked("RPLIDAR C1")
        qapp.processEvents()
        assert win.diagnostics_dialog.subsystem_name == "RPLIDAR C1"

        # Check legacy alias Jetson Gimbal / Mount maps to Camera & Gimbal
        assert "Jetson Gimbal / Mount" in win.health_widgets
        assert "Camera & Gimbal" in win.health_widgets
    finally:
        if win.diagnostics_dialog:
            win.diagnostics_dialog.close()
        win.close()
