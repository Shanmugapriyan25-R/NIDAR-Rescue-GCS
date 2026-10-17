"""Test application imports, startup, and clean window instantiation."""

import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_core_module_imports():
    """Verify that all core modules import cleanly on Windows without rclpy."""
    import gcs_client
    import gcs_data_plugins
    import ros2_gcs_bridge
    import edith_gcs_qt

    assert hasattr(gcs_client, "GCSClientWorker")
    assert hasattr(gcs_data_plugins, "DataPluginManager")
    assert hasattr(gcs_data_plugins, "SimulationPlugin")
    assert hasattr(ros2_gcs_bridge, "EdithGCSBridge")
    assert hasattr(edith_gcs_qt, "NidarRescueGCS")
    assert ros2_gcs_bridge.ROS2_AVAILABLE is False  # On Windows without ROS 2


def test_window_startup_and_geometry():
    """Verify that NidarRescueGCS window starts up and initializes central state."""
    from PyQt6.QtWidgets import QApplication
    from edith_gcs_qt import NidarRescueGCS

    app = QApplication.instance() or QApplication(sys.argv)
    window = NidarRescueGCS()
    window.resize(1340, 800)

    assert window.windowTitle().startswith("NIDAR Rescue GCS")
    assert window.active_source == "Simulation"
    assert window.flight_mode == "AUTONOMOUS"
    assert window.map_canvas is not None
    assert window.camera is not None
    assert window.donut is not None
    assert len(window.telem_labels) == 12

    # Process events and verify no crash
    app.processEvents()
    window.close()
