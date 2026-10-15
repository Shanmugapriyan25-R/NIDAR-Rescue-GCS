"""Small, dependency-free mission data adapters for NIDAR Rescue GCS.

The desktop client always has a deterministic Simulation source.  Operators can
switch to a JSON file (ideal for ROS/PX4 bridge output) or an HTTP JSON endpoint
without changing the UI.  Every external payload is merged into the safe local
schema, so an unavailable source never crashes the GCS.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_SURVIVORS = [
    {"id": "S01", "status": "found", "grid": "B2", "x": 5.2, "y": 4.2, "confidence": 92, "movement": "MOVEMENT DETECTED", "detected_at": "08:14"},
    {"id": "S02", "status": "found", "grid": "C4", "x": 8.2, "y": 6.3, "confidence": 85, "movement": "STATIONARY (THERMAL)", "detected_at": "08:29"},
    {"id": "S03", "status": "searching", "grid": "A3", "x": 0.0, "y": 0.0, "confidence": 0, "movement": "SEARCH PENDING", "detected_at": "--:--"},
    {"id": "S04", "status": "searching", "grid": "D2", "x": 0.0, "y": 0.0, "confidence": 0, "movement": "SEARCH PENDING", "detected_at": "--:--"},
    {"id": "S05", "status": "searching", "grid": "D4", "x": 0.0, "y": 0.0, "confidence": 0, "movement": "SEARCH PENDING", "detected_at": "--:--"},
    {"id": "S06", "status": "searching", "grid": "E1", "x": 0.0, "y": 0.0, "confidence": 0, "movement": "SEARCH PENDING", "detected_at": "--:--"},
]


# Local ENU route used only by the deterministic desktop simulation.  It is not
# a flight path or a command sent to an aircraft.
SIMULATION_ROUTE = [
    (10.8, 8.1), (10.3, 7.2), (9.4, 6.4), (8.1, 5.6), (7.3, 4.9),
    (7.1, 3.6), (7.2, 2.3), (8.5, 1.6), (10.1, 1.5), (10.8, 2.1),
]


# User-supplied planning inventory. These are intentionally marked PLANNED:
# the desktop UI cannot prove a cable, ROS topic, or physical device exists.
HARDWARE_COMPONENTS = [
    {"id": "flight_stack", "name": "MicoAir h743v2 Stack", "role": "Flight-control stack; firmware/interface not specified", "group": "Flight control"},
    {"id": "lidar", "name": "RPLiDAR C1 - DTOF LiDAR 360° Laser Range Scanner (12m, IP54)", "role": "2D range scan input for localization and SLAM", "group": "Sensing"},
    {"id": "ai_compute", "name": "Jetson nano orin super", "role": "AI compute host for survivor detection/inference", "group": "AI compute"},
    {"id": "ros_host", "name": "Raspberry Pi 4 Model 8GB RAM Development Board", "role": "Companion computer candidate for ROS 2 and SLAM", "group": "ROS / SLAM"},
    {"id": "camera", "name": "Raspberry Pi Camera V2", "role": "Visual camera input for reconnaissance", "group": "Sensing"},
    {"id": "elrs_rx_primary", "name": "Radiomaster RP1 ELRS 2.4G Receiver", "role": "Primary manual-control radio receiver", "group": "Control link"},
    {"id": "elrs_rx_secondary", "name": "HGLRC ELRS 2.4G Receiver", "role": "Secondary/alternate ELRS receiver", "group": "Control link"},
    {"id": "elrs_tx", "name": "Radiomaster Pocket ELRS Tx", "role": "Operator-side ELRS transmitter", "group": "Control link"},
    {"id": "optical_flow", "name": "Micoair MTF-01 Opticalflow", "role": "Optical-flow velocity/height aid for GPS-denied flight", "group": "Sensing"},
    {"id": "dji_o4", "name": "DJI O4 unit pro", "role": "Digital video link / air-unit candidate", "group": "Video link"},
    {"id": "airframe", "name": "Holybro X500 V2 Barebones Frame Kit (inc. Motor & ESC & Prop)", "role": "Airframe, propulsion, ESC, and propeller assembly", "group": "Airframe"},
    {"id": "charger", "name": "HOTA T6 DC 300W PD 90W 15A 1-6S LiPo Battery Charger", "role": "Battery charging equipment; not a flight telemetry source", "group": "Power"},
    {"id": "battery", "name": "Molicel 21700 P45B", "role": "Battery cell / pack component", "group": "Power"},
    {"id": "router", "name": "TP-Link Archer AX55 AX3000 Wi-Fi 6 Router", "role": "Local development and telemetry network", "group": "Network"},
]

TARGET_PLATFORM = {
    "os": "Ubuntu 22.04 LTS - Jammy Jellyfish",
    "ros": "ROS 2 Humble (target; Ubuntu 22.04 compatible)",
    "slam": "ROS 2 SLAM stack (LiDAR driver + localization; package selection pending)",
    "ai": "Jetson nano orin super - AI inference host",
    "note": "Planning target only; hardware and ROS topics are not detected by this desktop UI.",
}


def default_frame() -> Dict[str, Any]:
    return {
        "mode": "AUTONOMOUS",
        "phase": "EXPLORING",
        "mission_seconds": 741,
        "coverage": 64,
        "target": "S01",
        "drone": {"x": 7.0, "y": 6.0, "heading": 228, "altitude": 2.35, "speed": 1.19},
        "telemetry": {"battery": 87, "voltage": 22.4, "current": 8.2, "link_ms": 37, "quality": 98},
        "sensors": {"lidar": "ACTIVE", "slam": "ACTIVE", "vision": "ACTIVE", "wifi": "CONNECTED", "mavlink": "CONNECTED"},
        "health": {name: "READY" for name in (
            "Flight Controller", "Camera Sensor", "3D Localization EKF", "Mapping Engine",
            "Survivor AI", "Local Communication", "Emergency System",
        )},
        "components": {},
        "component_status": {item["id"]: "PLANNED" for item in HARDWARE_COMPONENTS},
        "hardware_components": [dict(item) for item in HARDWARE_COMPONENTS],
        "target_platform": dict(TARGET_PLATFORM),
        "survivors": [dict(item) for item in DEFAULT_SURVIVORS],
        "events": [
            "[08:42:15]  [INFO]  Waypoint WP-09 reached. Scanning Corridor Beta.",
            "[08:41:25]  [INFO]  Survivor S02 localized at Grid C4 (Localization Conf: 85%).",
        ],
        "source_label": "SYNTHETIC FEED",
    }


def deep_merge(base: Dict[str, Any], incoming: Dict[str, Any], _nested: bool = False) -> Dict[str, Any]:
    """Merge a normalized partial payload while retaining safe defaults.

    Unknown top-level fields are ignored, while nested extension maps such as
    ``components`` can add a new named status without requiring a UI release.
    """
    result = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value, _nested=True)
        elif key in result or _nested:
            result[key] = value
    return result


@dataclass
class PluginResult:
    frame: Optional[Dict[str, Any]] = None
    status: str = "READY"
    detail: str = ""


class DataPlugin:
    name = "Data source"

    def poll(self) -> PluginResult:
        return PluginResult()


class SimulationPlugin(DataPlugin):
    name = "Simulation"

    def __init__(self) -> None:
        self.started_at = time.monotonic()

    def poll(self) -> PluginResult:
        elapsed = time.monotonic() - self.started_at
        segment = elapsed * 0.28
        index = int(segment) % len(SIMULATION_ROUTE)
        next_index = (index + 1) % len(SIMULATION_ROUTE)
        fraction = segment - int(segment)
        start = SIMULATION_ROUTE[index]
        end = SIMULATION_ROUTE[next_index]
        x = start[0] + (end[0] - start[0]) * fraction
        y = start[1] + (end[1] - start[1]) * fraction
        heading = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])) % 360
        return PluginResult(
            frame={
                "mission_seconds": 741 + int(elapsed),
                "source_label": "SYNTHETIC FEED",
                "drone": {"x": round(x, 2), "y": round(y, 2), "heading": round(heading), "altitude": 2.35, "speed": 1.19},
            },
            detail="Local deterministic route preview; no vehicle command sent",
        )


class JsonFilePlugin(DataPlugin):
    name = "JSON file"

    def __init__(self, path: Path) -> None:
        self.path = path
        self._last_modified: Optional[float] = None
        self._last_frame: Optional[Dict[str, Any]] = None

    def poll(self) -> PluginResult:
        if not self.path.exists():
            return PluginResult(status="WAITING", detail=f"Waiting for {self.path.name}")
        try:
            modified = self.path.stat().st_mtime
            if self._last_frame is None or modified != self._last_modified:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("payload must be a JSON object")
                self._last_frame = payload
                self._last_modified = modified
            return PluginResult(frame=self._last_frame, detail=f"Watching {self.path.name}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return PluginResult(status="ERROR", detail=f"JSON input: {exc}")


class HttpJsonPlugin(DataPlugin):
    name = "HTTP JSON"

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.strip()
        self._last_poll = 0.0
        self._last_frame: Optional[Dict[str, Any]] = None

    def poll(self) -> PluginResult:
        if not self.endpoint:
            return PluginResult(status="WAITING", detail="Set NIDAR_HTTP_FEED environment variable or use JSON file")
        now = time.monotonic()
        if now - self._last_poll < 2.0:
            return PluginResult(frame=self._last_frame, status="CONNECTED" if self._last_frame else "WAITING", detail=self.endpoint)
        self._last_poll = now
        try:
            with urllib.request.urlopen(self.endpoint, timeout=0.8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            self._last_frame = payload
            return PluginResult(frame=payload, status="CONNECTED", detail=self.endpoint)
        except Exception as exc:  # network errors are intentionally contained in the adapter
            return PluginResult(frame=self._last_frame, status="WAITING", detail=f"HTTP feed unavailable: {exc}")


@dataclass
class DataPluginManager:
    data_dir: Path
    source: str = "Simulation"
    http_endpoint: str = field(default_factory=lambda: os.environ.get("NIDAR_HTTP_FEED", ""))

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.plugins: Dict[str, DataPlugin] = {
            "Simulation": SimulationPlugin(),
            "JSON file": JsonFilePlugin(self.data_dir / "mission.json"),
            "HTTP JSON": HttpJsonPlugin(self.http_endpoint),
        }

    def select(self, source: str, endpoint: str = "") -> None:
        if source not in self.plugins:
            raise ValueError(f"Unknown data source: {source}")
        self.source = source
        if source == "HTTP JSON":
            self.http_endpoint = endpoint.strip()
            self.plugins[source] = HttpJsonPlugin(self.http_endpoint)

    def poll(self) -> PluginResult:
        return self.plugins[self.source].poll()

    @property
    def source_hint(self) -> str:
        if self.source == "JSON file":
            return str(self.data_dir / "mission.json")
        if self.source == "HTTP JSON":
            return self.http_endpoint or "NIDAR_HTTP_FEED"
        return "Built-in synthetic mission"
