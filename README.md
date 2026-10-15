# 🛸 TEAM EDITH | NIDAR Rescue Ground Control Station (GCS)
**Autonomous GPS-Denied Indoor Search, Mapping & Survivor Localization Challenge**  
*NIDAR AirMouse Challenge — Track 1 (PS2)*  
*Branch:* `shan` (Developed by **Shanmugapriyan / Shan**)

---

## 📌 Overview
The **TEAM EDITH NIDAR Rescue Ground Control Station (GCS)** is a high-performance, modular tactical monitoring and operator command console engineered for autonomous UAVs operating in GPS-denied indoor disaster corridors and search-and-rescue operations.

This branch features the **Native PyQt6 Operator Console** with a pluggable data engine, ROS 2 WebSocket bridging, real-time SLAM visualization, and survivor tracking.

---

## 🌟 Key Features

- **Tactical 2D SLAM & Arena Grid:**
  - Real-time robotic SLAM visualization with high-contrast point cloud / obstacle mapping.
  - 1-meter metric coordinate arena grid (A–O & 1–15) with dynamic drone trajectory ribbons.
  - Rotating LiDAR scan cone with obstacle clearance diagnostics.

- **Survivor Localization & Tracking:**
  - Multi-target tracking engine (T1–T6) mapping discrete arena grid coordinates (e.g., `Grid [C-4]`, `X 2.4E / Y 3.8N`).
  - Real-time confidence score scoring, detection timestamps, and movement classification.

- **Modular Data Plugin Engine (`gcs_data_plugins.py`):**
  - **Simulation Mode:** Deterministic preview data for mission rehearsals and offline testing.
  - **File Feed (`data/mission.json`):** Hot-reloading normalized JSON state for atomic writes from external planners or bridges.
  - **HTTP JSON Stream:** Polled REST endpoint integration for live network telemetry.

- **ROS 2 Robotics Bridge (`ros2_gcs_bridge.py`):**
  - High-speed WebSocket bridge (`ws://0.0.0.0:9090`) subscribing to standard ROS 2 topics (`/odom`, `/scan`, `/map`, `/drone/battery`, `/survivors/detections`, `/diagnostics`).

- **Dual Engine Implementations:**
  - `edith_gcs_qt.py`: Modern, responsive PyQt6 operator console.
  - `edith_gcs.py`: Lightweight Tkinter desktop implementation.

- **Safety & Operator Controls:**
  - One-click Autonomous Mission Dispatch, Return-to-Launch (RTL), and Emergency Abort triggers.

---

## 📁 Repository Structure

```
├── edith_gcs_qt.py         # Primary PyQt6 tactical GCS operator console
├── edith_gcs.py            # Lightweight desktop GCS implementation
├── gcs_data_plugins.py     # Pluggable telemetry & mission data engine
├── ros2_gcs_bridge.py      # ROS 2 Humble WebSocket telemetry bridge
├── data/
│   └── mission.json        # Normalized mission telemetry & target feed
├── output/playwright/
│   ├── nidar-gcs-ui-design.html # GCS UI Design specification & layout
│   ├── nidar-gcs-ui-design.png  # High-resolution design mockup
│   └── render_ui_mockup.py      # Design renderer
├── DATA_PLUGINS.md         # Data plugin configuration & ROS 2 documentation
├── requirements.txt        # Python dependency specifications
├── run_gcs.bat             # Windows one-click launcher
└── run_gcs.sh              # Linux Ubuntu launcher
```

---

## 🚀 Quick Start

### 🪟 Windows Setup & Launch
1. Ensure Python 3.10+ is installed:
   ```cmd
   pip install -r requirements.txt
   ```
2. Double-click `run_gcs.bat` or run:
   ```cmd
   python edith_gcs_qt.py
   ```

### 🐧 Linux (Ubuntu 22.04 LTS / Jammy)
1. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3-pyqt6
   # Or via pip:
   pip install -r requirements.txt
   ```
2. Launch the GCS:
   ```bash
   chmod +x run_gcs.sh
   ./run_gcs.sh
   ```

---

## 👥 Authors & Team
- **Shan (Shanmugapriyan)** — GCS Frontend Architecture, PyQt6 UI & Data Plugins (`shan` branch)
- **Sheldon** — GCS Architecture & Mission Systems (`sheldon` branch)
- **Mukil** — Lead & System Integration
- **TEAM EDITH**
