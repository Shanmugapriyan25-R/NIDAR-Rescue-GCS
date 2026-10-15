# NIDAR data plugins

The GCS ships with three safe, dependency-free sources selected from **Pre-Flight**:

- **Simulation**: deterministic preview data; it is never presented as real hardware data.
- **JSON file**: edits to `data/mission.json` are detected while the GCS is open. A ROS 2/PX4 bridge can atomically write this normalized object.
- **HTTP JSON**: set `NIDAR_HTTP_FEED` before launch or supply an endpoint in Pre-Flight. The source is polled every two seconds with a short timeout.

The accepted keys are the ones shown in `data/mission.json`; all keys are optional. Nested `telemetry`, `drone`, `sensors`, `health`, `components`, and `component_status` objects are merged with safe defaults. `components` controls the ten runtime rows in the main panel (for example `{"LiDAR": "CONNECTED", "Vision AI": "READY"}`). `component_status` is keyed by the 14 inventory IDs in the **DETAILS** dialog (for example `{"lidar": "CONNECTED", "ai_compute": "READY"}`). The UI exposes live status for Flight Controller, Camera, LiDAR, SLAM/Localization, Mapping Engine, Vision AI, Wi-Fi, MAVLink, Emergency System, and the active Data Plugin. Use `survivors` as an array of objects with `id`, `status`, `grid`, `x`, `y`, `confidence`, and optional `movement` / `detected_at` fields for the operator detection rows.

The bundled inventory and target platform are planning metadata: Ubuntu 22.04 LTS (Jammy Jellyfish), ROS 2 Humble, a LiDAR/localization SLAM stack, and Jetson nano orin super as the AI host. `PLANNED`, `SIMULATED`, and `WAITING` are intentionally distinct from `READY`/`CONNECTED`; the desktop UI does not probe USB, GPIO, ROS topics, flight-controller firmware, or physical power.

## Ubuntu 22.04 launch

From the project directory on Ubuntu Jammy:

```bash
sudo apt update
sudo apt install -y python3-pyqt6
chmod +x run_gcs.sh
./run_gcs.sh
```

If the OS uses a virtual environment or does not provide the apt package, use `python3 -m pip install -r requirements.txt` instead.

The GUI itself is dependency-light and can run in Simulation mode before ROS 2 is installed. The ROS 2 bridge remains optional until the actual topics, drivers, and Jetson/Raspberry Pi network are configured.

The bundled `ros2_gcs_bridge.py` remains a separate ROS 2/WebSocket bridge. It is not automatically treated as connected; map that bridge into this JSON schema or an HTTP endpoint after the actual ROS topics and hardware are available.
