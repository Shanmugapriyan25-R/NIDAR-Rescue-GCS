"""TEAM EDITH — NIDAR Rescue GCS Data Plugins & Simulation Engine.

Provides unified data adapters and a deterministic, hardware-free simulation engine.
Operators can select between:
- "Simulation": Full hardware-free deterministic simulation of drone kinematics,
  telemetry, sensor health, and sequential survivor detection events.
- "JSON file": Watches a mission file (e.g. data/mission.json).
- "WebSocket": Connects to the ROS 2 or simulation bridge via WebSocket.

All sources produce normalized, schema-validated frames so the UI remains stable
regardless of connection state or data loss.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Arena dimension: 15m x 15m metric indoor/outdoor disaster zone
ARENA_WIDTH_M = 15.0
ARENA_HEIGHT_M = 15.0

# 15x15 Metric Grid labels (A-O, 1-15)
GRID_COLS = [chr(ord('A') + i) for i in range(15)]
GRID_ROWS = [str(15 - i) for i in range(15)]

# Canonical simulation survivor candidates with discovery timeline
SIM_SURVIVORS_MASTER = [
    {
        "id": "S01",
        "number": "01",
        "grid": "A1",
        "x": 2.7,
        "y": 3.75,
        "lat": 10.8462,
        "lon": 76.2711,
        "confidence": 93,
        "status": "STABLE",
        "movement": "STABLE",
        "bbox": [0.15, 0.20, 0.26, 0.36],
        "thumb": "assets/thumb_s1.png",
        "color_hex": "#10b981",
        "discover_sec": 0,
        "last_seen_sec": 0,
    },
    {
        "id": "S02",
        "number": "02",
        "grid": "C4",
        "x": 7.8,
        "y": 5.25,
        "lat": 10.8468,
        "lon": 76.2719,
        "confidence": 87,
        "status": "MOVING",
        "movement": "MOVING",
        "bbox": [0.46, 0.32, 0.58, 0.49],
        "thumb": "assets/thumb_s2.png",
        "color_hex": "#2563eb",
        "discover_sec": 12,
        "last_seen_sec": 12,
    },
    {
        "id": "S03",
        "number": "03",
        "grid": "B3",
        "x": 3.0,
        "y": 8.25,
        "lat": 10.8459,
        "lon": 76.2726,
        "confidence": 76,
        "status": "STABLE",
        "movement": "STABLE",
        "bbox": [0.18, 0.52, 0.29, 0.68],
        "thumb": "assets/thumb_s3.png",
        "color_hex": "#8b5cf6",
        "discover_sec": 24,
        "last_seen_sec": 24,
    },
    {
        "id": "S04",
        "number": "04",
        "grid": "D2",
        "x": 7.0,
        "y": 11.0,
        "lat": 10.8447,
        "lon": 76.2714,
        "confidence": 68,
        "status": "INACTIVE",
        "movement": "INACTIVE",
        "bbox": [0.42, 0.70, 0.54, 0.86],
        "thumb": "assets/thumb_s4.png",
        "color_hex": "#ef4444",
        "discover_sec": 38,
        "last_seen_sec": 38,
    },
]

# Standard waypoint patrol route (metric coordinates in meters inside 15x15m arena)
PATROL_WAYPOINTS = [
    (1.5, 1.5), (1.5, 4.5), (3.5, 4.5), (3.5, 2.0),
    (7.0, 2.0), (7.0, 5.0), (11.0, 5.0), (11.0, 9.0),
    (7.0, 9.0), (7.0, 12.0), (3.5, 12.0), (1.5, 13.5),
    (7.0, 7.5), (13.5, 7.5), (13.5, 2.0)
]

HARDWARE_COMPONENTS = [
    {"id": "flight_stack", "name": "MicoAir h743v2 Stack", "role": "Flight controller / EKF state", "group": "Flight control"},
    {"id": "lidar", "name": "RPLiDAR C1 - 360° DTOF Laser Scanner", "role": "2D range scan & SLAM obstacle map", "group": "Sensing"},
    {"id": "ai_compute", "name": "Jetson Orin Nano Super", "role": "Onboard AI inference host for human detection", "group": "AI compute"},
    {"id": "camera", "name": "Raspberry Pi Camera V2 / HD Gimbal", "role": "Visual reconnaissance camera feed", "group": "Sensing"},
    {"id": "bridge", "name": "ROS 2 Humble GCS Bridge", "role": "Telemetry & Command WebSocket interface", "group": "Network"},
]


def default_frame() -> Dict[str, Any]:
    """Produce a safe, initialized baseline telemetry frame."""
    return {
        "source_type": "SIMULATION",
        "source_label": "SIMULATION - READY",
        "mode": "RTL / LAND",
        "phase": "STANDBY",
        "mission_seconds": 0,
        "coverage": 0,
        "target": "S01",
        "drone": {
            "x": 7.0,
            "y": 6.0,
            "z": 1.20,
            "heading": 228.0,
            "yaw": 228.0,
            "altitude": 1.20,
            "speed": 0.0,
        },
        "telemetry": {
            "battery": 87,
            "voltage": 22.4,
            "current": 8.2,
            "link_ms": 37,
            "quality": 98,
            "mode": "RTL / LAND",
            "speed": 0.0,
            "heading": 228.0,
            "altitude": 1.20,
            "gps": "OPT_FLOW",
            "position": "OK",
            "flight_time": "00:00",
        },
        "sensors": {
            "lidar": "ACTIVE",
            "radar": "ACTIVE",
            "vision": "ACTIVE",
            "wifi": "ACTIVE",
            "mavlink": "ACTIVE",
            "connected": "ACTIVE",
        },
        "health": {
            "Jetson Orin": "OK",
            "Jetson Gimbal / Mount": "OK",
            "RPLIDAR C1": "OK",
            "ROS 2 Bridge": "SIMULATED",
            "MAVLink": "OK",
        },
        "survivors": [],
        "staged_waypoints": [],
        "accepted_waypoints": [list(pt) for pt in PATROL_WAYPOINTS[:5]],
        "events": [],
    }


@dataclass
class PluginResult:
    frame: Optional[Dict[str, Any]] = None
    status: str = "READY"
    detail: str = ""


class DataPlugin:
    name: str = "Base Data Source"

    def poll(self) -> PluginResult:
        return PluginResult()

    def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"status": "REJECTED", "message": "Command not supported by this plugin"}


class SimulationPlugin(DataPlugin):
    """Deterministic, hardware-free simulation engine."""
    name = "Simulation"

    def __init__(self) -> None:
        self.is_running = True
        self.is_paused = False
        self.start_time = time.monotonic()
        self.pause_time = 0.0
        self.total_paused_duration = 0.0
        self.flight_mode = "RTL / LAND"
        self.phase = "EXPLORING"
        self.base_battery = 87.0
        self.staged_waypoints: List[Tuple[float, float, str]] = []
        self.accepted_waypoints: List[Tuple[float, float]] = list(PATROL_WAYPOINTS[:6])
        self.user_marked_survivors: List[Dict[str, Any]] = []
        self.active_survivors_cache: List[Dict[str, Any]] = []

    def start(self) -> None:
        if not self.is_running:
            self.reset()
        self.is_running = True
        self.is_paused = False

    def pause(self) -> None:
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.pause_time = time.monotonic()

    def resume(self) -> None:
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.total_paused_duration += time.monotonic() - self.pause_time

    def reset(self) -> None:
        self.start_time = time.monotonic()
        self.pause_time = 0.0
        self.total_paused_duration = 0.0
        self.is_running = True
        self.is_paused = False
        self.flight_mode = "RTL / LAND"
        self.phase = "EXPLORING"
        self.staged_waypoints.clear()
        self.user_marked_survivors.clear()
        self.active_survivors_cache.clear()

    def get_elapsed_seconds(self) -> float:
        if not self.is_running:
            return 0.0
        if self.is_paused:
            return max(0.0, self.pause_time - self.start_time - self.total_paused_duration)
        return max(0.0, time.monotonic() - self.start_time - self.total_paused_duration)

    def poll(self) -> PluginResult:
        elapsed = self.get_elapsed_seconds()
        sim_sec = int(elapsed)

        # 1. Kinematics along patrol route
        speed = 1.2 if self.flight_mode not in {"EMERGENCY LAND", "RTL / LAND"} else (0.8 if self.flight_mode == "RTL / LAND" else 0.0)
        route = self.accepted_waypoints if self.accepted_waypoints else PATROL_WAYPOINTS
        if len(route) >= 2 and self.flight_mode != "EMERGENCY LAND":
            seg_duration = 6.0  # seconds per waypoint segment
            total_duration = seg_duration * (len(route) - 1)
            t_route = (elapsed * 0.8) % total_duration
            seg_idx = int(t_route / seg_duration)
            next_idx = min(len(route) - 1, seg_idx + 1)
            frac = (t_route - (seg_idx * seg_duration)) / seg_duration

            p1 = route[seg_idx]
            p2 = route[next_idx]
            cur_x = p1[0] + (p2[0] - p1[0]) * frac
            cur_y = p1[1] + (p2[1] - p1[1]) * frac

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            yaw = (math.degrees(math.atan2(dy, dx))) % 360
        else:
            cur_x, cur_y, yaw = 7.0, 6.0, 228.0

        # Altitude & Battery
        alt = 2.4 if self.flight_mode != "EMERGENCY LAND" else max(0.0, round(2.4 - (elapsed % 10) * 0.4, 1))
        battery_pct = max(5, int(self.base_battery - (elapsed * 0.015)))
        voltage = round(19.8 + (battery_pct / 100.0) * 3.0, 1)

        # 2. Dynamic Sequential Survivor Discovery & Stale Detection
        active_survivors: List[Dict[str, Any]] = []
        for cand in SIM_SURVIVORS_MASTER:
            if sim_sec >= cand["discover_sec"]:
                item = dict(cand)
                # Stale warning: if discovered > 30s ago and inactive
                time_since_seen = sim_sec - cand.get("last_seen_sec", 0)
                item["is_stale"] = (time_since_seen > 30 and item["status"] == "INACTIVE")
                active_survivors.append(item)

        # Include any manually marked survivors
        for s in self.user_marked_survivors:
            s_item = dict(s)
            active_survivors.append(s_item)

        self.active_survivors_cache = active_survivors

        # 3. Dynamic Coverage Calculation
        # Incremental coverage starting at 42% climbing to 92%
        coverage = min(92, int(42 + min(50.0, elapsed * 0.8)))

        # Format flight time MM:SS
        mins = sim_sec // 60
        secs = sim_sec % 60
        flight_time_str = f"{mins:02d}:{secs:02d}"

        frame: Dict[str, Any] = {
            "source_type": "SIMULATION",
            "source_label": "SIMULATION - READY",
            "mode": self.flight_mode,
            "phase": self.phase,
            "mission_seconds": sim_sec,
            "coverage": coverage,
            "target": active_survivors[0]["id"] if active_survivors else "—",
            "drone": {
                "x": round(cur_x, 2),
                "y": round(cur_y, 2),
                "z": round(alt, 2),
                "heading": round(yaw),
                "yaw": round(yaw),
                "altitude": round(alt, 1),
                "speed": round(speed, 1),
            },
            "telemetry": {
                "battery": battery_pct,
                "voltage": voltage,
                "current": 8.2 if speed > 0 else 1.5,
                "link_ms": 35 + int((sim_sec % 5) * 2),
                "quality": 98,
                "mode": self.flight_mode,
                "speed": round(speed, 1),
                "heading": round(yaw),
                "altitude": round(alt, 1),
                "gps": "OPT_FLOW",
                "position": "OK",
                "flight_time": flight_time_str,
            },
            "sensors": {
                "lidar": "ACTIVE",
                "radar": "ACTIVE",
                "vision": "ACTIVE",
                "wifi": "ACTIVE",
                "mavlink": "ACTIVE",
                "connected": "ACTIVE",
            },
            "health": {
                "Jetson Orin": "OK (SIM)",
                "Jetson Gimbal / Mount": "OK (SIM)",
                "RPLIDAR C1": "OK (SIM)",
                "ROS 2 Bridge": "SIMULATED",
                "MAVLink": "OK (SIM)",
            },
            "survivors": active_survivors,
            "staged_waypoints": [list(w) for w in self.staged_waypoints],
            "accepted_waypoints": [list(w) for w in self.accepted_waypoints],
        }

        return PluginResult(frame=frame, status="SIMULATION", detail="Deterministic Local Simulation Active")

    def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        cmd_upper = cmd.upper()

        if cmd_upper in {"ABORT", "EMERGENCY_ABORT"}:
            self.flight_mode = "EMERGENCY LAND"
            self.phase = "ABORTED"
            return {"status": "ACCEPTED", "message": "Simulation emergency touchdown executed. Motors disarmed."}
        elif cmd_upper == "RTL":
            self.flight_mode = "RTL / LAND"
            self.phase = "RTL"
            return {"status": "ACCEPTED", "message": "Simulation RTL commanded. Returning to start waypoint (1.5, 1.5)."}
        elif cmd_upper == "SET_MODE":
            mode_name = params.get("mode", "MANUAL")
            self.flight_mode = mode_name
            return {"status": "ACCEPTED", "message": f"Simulation flight mode set to {mode_name}."}
        elif cmd_upper == "STAGE_WAYPOINT":
            x = float(params.get("x", 0.0))
            y = float(params.get("y", 0.0))
            tag = str(params.get("tag", f"WP-{len(self.staged_waypoints)+1}"))
            self.staged_waypoints.append((x, y, tag))
            return {"status": "ACCEPTED", "message": f"Waypoint {tag} staged at ({x}m, {y}m)."}
        elif cmd_upper == "COMMIT_WAYPOINTS":
            if not self.staged_waypoints:
                return {"status": "REJECTED", "message": "No staged waypoints to commit."}
            new_pts = [(w[0], w[1]) for w in self.staged_waypoints]
            self.accepted_waypoints.extend(new_pts)
            count = len(self.staged_waypoints)
            self.staged_waypoints.clear()
            return {"status": "ACCEPTED", "message": f"{count} staged waypoints committed to active flight plan."}
        elif cmd_upper == "CLEAR_WAYPOINTS":
            count = len(self.staged_waypoints)
            self.staged_waypoints.clear()
            return {"status": "ACCEPTED", "message": f"{count} staged waypoints cleared."}
        elif cmd_upper == "MARK_SURVIVOR":
            surv_id = f"S{len(self.user_marked_survivors) + 5:02d}"
            new_s = {
                "id": surv_id,
                "number": f"{len(self.user_marked_survivors) + 5:02d}",
                "grid": params.get("grid", "M9"),
                "x": float(params.get("x", 7.5)),
                "y": float(params.get("y", 7.5)),
                "lat": float(params.get("lat", 10.8464)),
                "lon": float(params.get("lon", 76.2716)),
                "confidence": 88,
                "status": "STABLE",
                "movement": "MANUALLY MARKED",
                "bbox": [0.45, 0.45, 0.55, 0.55],
                "thumb": "assets/thumb_s1.png",
                "color_hex": "#06b6d4",
                "discover_sec": 0,
                "last_seen_sec": int(self.get_elapsed_seconds()),
            }
            self.user_marked_survivors.append(new_s)
            return {"status": "ACCEPTED", "message": f"Survivor {surv_id} marked manually at ({new_s['x']}m, {new_s['y']}m)."}
        elif cmd_upper == "ADD_DETECTION":
            det_id = str(params.get("id", f"S{len(self.user_marked_survivors)+10:02d}"))
            new_det = {
                "id": det_id,
                "number": det_id.lstrip("S") or "10",
                "grid": params.get("grid", "B2"),
                "x": float(params.get("x", 4.0)),
                "y": float(params.get("y", 4.0)),
                "lat": float(params.get("lat", 10.8465)),
                "lon": float(params.get("lon", 76.2715)),
                "confidence": int(params.get("confidence", 85)),
                "status": params.get("status", "FOUND"),
                "movement": params.get("movement", "STABLE"),
                "bbox": params.get("bbox", [0.3, 0.3, 0.45, 0.45]),
                "thumb": "assets/thumb_s1.png",
                "color_hex": "#10b981",
                "discover_sec": 0,
                "last_seen_sec": int(self.get_elapsed_seconds()),
            }
            self.user_marked_survivors.append(new_det)
            return {"status": "ACCEPTED", "message": f"Sample detection {det_id} injected."}
        elif cmd_upper == "REMOVE_DETECTION":
            target_id = params.get("id", "")
            before_len = len(self.user_marked_survivors)
            self.user_marked_survivors = [s for s in self.user_marked_survivors if s["id"] != target_id]
            if len(self.user_marked_survivors) < before_len:
                return {"status": "ACCEPTED", "message": f"Detection {target_id} removed."}
            return {"status": "REJECTED", "message": f"Detection {target_id} not found."}
        elif cmd_upper == "CLEAR_DETECTIONS":
            self.user_marked_survivors.clear()
            return {"status": "ACCEPTED", "message": "Manual detections cleared."}

        return {"status": "REJECTED", "message": f"Unknown command: {cmd}"}


class JsonFilePlugin(DataPlugin):
    """Watches a local JSON file (e.g. data/mission.json)."""
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
                content = self.path.read_text(encoding="utf-8")
                payload = json.loads(content)
                if not isinstance(payload, dict):
                    raise ValueError("JSON payload must be a dictionary")
                # Merge into default frame schema
                merged = default_frame()
                merged.update(payload)
                merged["source_type"] = "FILE"
                merged["source_label"] = f"FILE: {self.path.name}"
                self._last_frame = merged
                self._last_modified = modified
            return PluginResult(frame=self._last_frame, status="CONNECTED", detail=f"Watching {self.path.name}")
        except Exception as exc:
            return PluginResult(status="ERROR", detail=f"File error: {exc}")


class DataPluginManager:
    """Manages active data sources and routes commands."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.source = "Simulation"
        self.plugins: Dict[str, DataPlugin] = {
            "Simulation": SimulationPlugin(),
            "JSON file": JsonFilePlugin(self.data_dir / "mission.json"),
        }

    def select(self, source: str) -> None:
        if source not in self.plugins:
            raise ValueError(f"Unknown data source: {source}")
        self.source = source

    def poll(self) -> PluginResult:
        return self.plugins[self.source].poll()

    def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.plugins[self.source].send_command(cmd, params)
