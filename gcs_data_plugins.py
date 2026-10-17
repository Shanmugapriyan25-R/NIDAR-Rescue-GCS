"""TEAM EDITH — NIDAR Rescue GCS Data Plugins & Autonomous Simulation Engine.

Autonomous Six-Person Rescue Mission Architecture:
- Default operating model is AUTONOMOUS. (Manual flight modes disabled).
- Strictly six designated mission target identities: S01, S02, S03, S04, S05, S06.
- Distinct target lifecycle: SEARCHING -> DETECTED -> TRACKING -> LOCALISED (with LOST/STALE handling).
- Autonomous mission state machine:
  IDLE -> PRE-FLIGHT CHECKS -> READY -> AUTONOMOUS SEARCH -> TARGET DETECTED -> TARGET TRACKING -> MISSION COMPLETE
  Exceptional states: PAUSED / SAFE HOLD, RETURNING HOME, ABORTING, ABORTED, CONNECTION LOST, SENSOR FAILURE, MISSION ERROR.
- Strict duplicate suppression and target association preventing creation of S07, S08, etc.
- Synchronized telemetry, sensor status, autonomous waypoints, and detection frames.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set


# Arena dimension: 15m x 15m metric indoor/outdoor disaster zone
ARENA_WIDTH_M = 15.0
ARENA_HEIGHT_M = 15.0

# 15x15 Metric Grid labels (A-O, 1-15)
GRID_COLS = [chr(ord('A') + i) for i in range(15)]
GRID_ROWS = [str(15 - i) for i in range(15)]

# Strictly six designated mission target person identities
DESIGNATED_TARGET_IDS = ["S01", "S02", "S03", "S04", "S05", "S06"]

# Canonical six simulated target identities with designated locations & timeline
SIM_TARGETS_MASTER: List[Dict[str, Any]] = [
    {
        "id": "S01",
        "number": "01",
        "grid": "A1",
        "x": 2.7,
        "y": 3.75,
        "lat": 10.8462,
        "lon": 76.2711,
        "confidence": 93,
        "movement": "STABLE",
        "bbox": [0.15, 0.20, 0.26, 0.36],
        "thumb": "assets/thumb_s1.png",
        "color_hex": "#10b981",
        "discover_sec": 8,
        "track_sec": 12,
        "localize_sec": 18,
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
        "movement": "MOVING",
        "bbox": [0.46, 0.32, 0.58, 0.49],
        "thumb": "assets/thumb_s2.png",
        "color_hex": "#2563eb",
        "discover_sec": 22,
        "lost_sec": 32,         # Temporary occlusion / loss event
        "reacquire_sec": 40,    # Reacquired by tracker
        "localize_sec": 48,
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
        "movement": "STABLE",
        "bbox": [0.18, 0.52, 0.29, 0.68],
        "thumb": "assets/thumb_s3.png",
        "color_hex": "#8b5cf6",
        "discover_sec": 56,
        "track_sec": 60,
        "localize_sec": 66,
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
        "movement": "INACTIVE",
        "bbox": [0.42, 0.70, 0.54, 0.86],
        "thumb": "assets/thumb_s4.png",
        "color_hex": "#ef4444",
        "discover_sec": 74,
        "track_sec": 78,
        "localize_sec": 84,
    },
    {
        "id": "S05",
        "number": "05",
        "grid": "F5",
        "x": 11.5,
        "y": 4.8,
        "lat": 10.8465,
        "lon": 76.2730,
        "confidence": 82,
        "movement": "STABLE",
        "bbox": [0.65, 0.35, 0.76, 0.50],
        "thumb": "assets/thumb_s1.png",
        "color_hex": "#f59e0b",
        "discover_sec": 92,
        "track_sec": 96,
        "localize_sec": 102,
    },
    {
        "id": "S06",
        "number": "06",
        "grid": "G8",
        "x": 12.2,
        "y": 9.5,
        "lat": 10.8451,
        "lon": 76.2735,
        "confidence": 91,
        "movement": "MOVING",
        "bbox": [0.70, 0.60, 0.82, 0.78],
        "thumb": "assets/thumb_s2.png",
        "color_hex": "#06b6d4",
        "discover_sec": 110,
        "track_sec": 114,
        "localize_sec": 120,    # 6/6 Confirmed! Triggers Mission Complete
    },
]

# Standard planned autonomous search route (metric coordinates in meters inside 15x15m arena)
AUTONOMOUS_SEARCH_WAYPOINTS: List[Tuple[float, float]] = [
    (1.5, 1.5),    # WP-1: Launch / Home Base
    (2.7, 3.8),    # WP-2: Sector A1 Corridor (S01 Zone)
    (5.5, 4.0),    # WP-3: Transit Alpha
    (7.8, 5.25),   # WP-4: Sector C4 Corridor (S02 Zone)
    (3.0, 8.25),   # WP-5: Sector B3 Corridor (S03 Zone)
    (7.0, 11.0),   # WP-6: Sector D2 Corridor (S04 Zone)
    (11.5, 4.8),   # WP-7: Sector F5 Corridor (S05 Zone)
    (12.2, 9.5),   # WP-8: Sector G8 Corridor (S06 Zone)
    (7.5, 7.5),    # WP-9: Central Verification Area
    (1.5, 1.5),    # WP-10: Home Base Landing Pad
]

HARDWARE_COMPONENTS = [
    {"id": "flight_stack", "name": "MicoAir h743v2 Stack", "role": "Autonomous Flight Controller / EKF", "group": "Flight control"},
    {"id": "lidar", "name": "RPLiDAR C1 - 360° DTOF Laser Scanner", "role": "2D range scan & SLAM obstacle map", "group": "Sensing"},
    {"id": "ai_compute", "name": "Jetson Orin Nano Super", "role": "Onboard AI inference host for human detection", "group": "AI compute"},
    {"id": "camera", "name": "Raspberry Pi Camera V2 / HD Gimbal", "role": "Visual reconnaissance camera feed", "group": "Sensing"},
    {"id": "bridge", "name": "ROS 2 Humble GCS Bridge", "role": "Telemetry & Command WebSocket interface", "group": "Network"},
]


# ==============================================================================
# MISSION STATE MACHINE
# ==============================================================================
class MissionState:
    IDLE = "IDLE"
    PRE_FLIGHT_CHECKS = "PRE-FLIGHT CHECKS"
    READY = "READY"
    AUTONOMOUS_SEARCH = "AUTONOMOUS SEARCH"
    TARGET_DETECTED = "TARGET DETECTED"
    TARGET_TRACKING = "TARGET TRACKING"
    MISSION_COMPLETE = "MISSION COMPLETE"

    # Exceptional states
    PAUSED_HOLD = "PAUSED / SAFE HOLD"
    RETURNING_HOME = "RETURNING HOME"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    CONNECTION_LOST = "CONNECTION LOST"
    SENSOR_FAILURE = "SENSOR FAILURE"
    MISSION_ERROR = "MISSION ERROR"

    ALL_STATES: Set[str] = {
        IDLE, PRE_FLIGHT_CHECKS, READY, AUTONOMOUS_SEARCH,
        TARGET_DETECTED, TARGET_TRACKING, MISSION_COMPLETE,
        PAUSED_HOLD, RETURNING_HOME, ABORTING, ABORTED,
        CONNECTION_LOST, SENSOR_FAILURE, MISSION_ERROR,
    }


class MissionStateMachine:
    """Rigorous state machine enforcing valid autonomous search mission transitions."""

    # Allowed transitions map: Current State -> Set of permitted next states
    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        MissionState.IDLE: {
            MissionState.PRE_FLIGHT_CHECKS,
            MissionState.READY,
            MissionState.SENSOR_FAILURE,
            MissionState.CONNECTION_LOST,
        },
        MissionState.PRE_FLIGHT_CHECKS: {
            MissionState.READY,
            MissionState.SENSOR_FAILURE,
            MissionState.CONNECTION_LOST,
            MissionState.IDLE,
            MissionState.MISSION_ERROR,
        },
        MissionState.READY: {
            MissionState.AUTONOMOUS_SEARCH,
            MissionState.PAUSED_HOLD,
            MissionState.RETURNING_HOME,
            MissionState.IDLE,
            MissionState.SENSOR_FAILURE,
            MissionState.CONNECTION_LOST,
            MissionState.ABORTING,
        },
        MissionState.AUTONOMOUS_SEARCH: {
            MissionState.TARGET_DETECTED,
            MissionState.TARGET_TRACKING,
            MissionState.MISSION_COMPLETE,
            MissionState.PAUSED_HOLD,
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.CONNECTION_LOST,
            MissionState.SENSOR_FAILURE,
            MissionState.MISSION_ERROR,
        },
        MissionState.TARGET_DETECTED: {
            MissionState.TARGET_TRACKING,
            MissionState.AUTONOMOUS_SEARCH,
            MissionState.MISSION_COMPLETE,
            MissionState.PAUSED_HOLD,
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.CONNECTION_LOST,
            MissionState.SENSOR_FAILURE,
        },
        MissionState.TARGET_TRACKING: {
            MissionState.AUTONOMOUS_SEARCH,
            MissionState.TARGET_DETECTED,
            MissionState.MISSION_COMPLETE,
            MissionState.PAUSED_HOLD,
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.CONNECTION_LOST,
            MissionState.SENSOR_FAILURE,
        },
        MissionState.MISSION_COMPLETE: {
            MissionState.RETURNING_HOME,
            MissionState.IDLE,
            MissionState.READY,
        },
        MissionState.PAUSED_HOLD: {
            MissionState.AUTONOMOUS_SEARCH,
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.CONNECTION_LOST,
            MissionState.SENSOR_FAILURE,
        },
        MissionState.RETURNING_HOME: {
            MissionState.IDLE,
            MissionState.READY,
            MissionState.MISSION_COMPLETE,
            MissionState.ABORTING,
            MissionState.ABORTED,
            MissionState.CONNECTION_LOST,
        },
        MissionState.ABORTING: {
            MissionState.ABORTED,
        },
        MissionState.ABORTED: {
            MissionState.IDLE,
            MissionState.READY,
        },
        MissionState.CONNECTION_LOST: {
            MissionState.AUTONOMOUS_SEARCH,
            MissionState.PAUSED_HOLD,
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.IDLE,
        },
        MissionState.SENSOR_FAILURE: {
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.IDLE,
        },
        MissionState.MISSION_ERROR: {
            MissionState.RETURNING_HOME,
            MissionState.ABORTING,
            MissionState.IDLE,
        },
    }

    def __init__(self, initial_state: str = MissionState.READY) -> None:
        self.current_state = initial_state
        self.state_enter_time = time.monotonic()
        self.last_transition_reason = "System Initialized"
        self.preflight_passed = True

    def get_state(self) -> str:
        return self.current_state

    def get_state_duration(self) -> float:
        return time.monotonic() - self.state_enter_time

    def can_transition(self, target_state: str) -> Tuple[bool, str]:
        if target_state not in MissionState.ALL_STATES:
            return False, f"Unknown target state: {target_state}"

        if target_state == self.current_state:
            return True, "Already in requested state"

        allowed = self.ALLOWED_TRANSITIONS.get(self.current_state, set())
        if target_state not in allowed:
            return False, f"Illegal state transition from {self.current_state} to {target_state}"

        return True, "OK"

    def transition(self, target_state: str, reason: str = "") -> Tuple[bool, str]:
        can_do, msg = self.can_transition(target_state)
        if not can_do:
            return False, msg

        self.current_state = target_state
        self.state_enter_time = time.monotonic()
        self.last_transition_reason = reason or f"Transition to {target_state}"
        return True, self.last_transition_reason


# ==============================================================================
# TARGET ASSOCIATION AND DUPLICATE SUPPRESSION
# ==============================================================================
def associate_and_suppress_detections(
    raw_detections: List[Dict[str, Any]],
    existing_roster: Optional[List[Dict[str, Any]]] = None,
    distance_threshold_m: float = 2.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Associate raw camera detections with the strictly six designated target slots.

    - Rejects any detections claiming to be S07, S08, etc.
    - Prevents duplicate detections from creating redundant person entries.
    - Updates confidence, bounding box, timestamps, and tracking status.
    - Returns (roster_targets, {"detected": detected_count, "localized": localized_count, "total": 6})
    """
    if existing_roster:
        roster_map = {t["id"]: dict(t) for t in existing_roster if t["id"] in DESIGNATED_TARGET_IDS}
    else:
        roster_map = {}

    master_dict = {t["id"]: t for t in SIM_TARGETS_MASTER}

    # Ensure all 6 designated target slots exist
    for target_id in DESIGNATED_TARGET_IDS:
        if target_id not in roster_map:
            master = master_dict.get(target_id, {})
            num = target_id.lstrip("S")
            roster_map[target_id] = {
                "id": target_id,
                "number": num,
                "grid": master.get("grid", "—"),
                "x": None,
                "y": None,
                "nominal_x": master.get("x"),
                "nominal_y": master.get("y"),
                "lat": master.get("lat"),
                "lon": master.get("lon"),
                "confidence": None,
                "status": "SEARCHING",
                "tracking_status": "NOT DETECTED",
                "loc_status": "UNAVAILABLE",
                "movement": "—",
                "bbox": None,
                "thumb": master.get("thumb", "assets/thumb_s1.png"),
                "color_hex": master.get("color_hex", "#64748b"),
                "first_seen_sec": None,
                "last_seen_sec": None,
                "is_stale": False,
            }

    for raw in raw_detections:
        claimed_id = str(raw.get("id", "")).upper()
        raw_x = raw.get("x")
        raw_y = raw.get("y")

        # 1. Match by explicit valid designated ID
        matched_id: Optional[str] = None
        if claimed_id in DESIGNATED_TARGET_IDS:
            matched_id = claimed_id
        elif raw_x is not None and raw_y is not None:
            # 2. Match by spatial proximity to existing known target position or nominal location
            min_dist = float("inf")
            for tid, tgt in roster_map.items():
                ref_x = tgt.get("x") if tgt.get("x") is not None else tgt.get("nominal_x")
                ref_y = tgt.get("y") if tgt.get("y") is not None else tgt.get("nominal_y")
                if ref_x is not None and ref_y is not None:
                    d = math.hypot(raw_x - ref_x, raw_y - ref_y)
                    if d < min_dist and d <= distance_threshold_m:
                        min_dist = d
                        matched_id = tid

        # Discard spurious or excess targets outside S01-S06
        if matched_id is None or matched_id not in roster_map:
            continue

        # Update matched designated target without creating duplicates
        target = roster_map[matched_id]
        cur_conf = target.get("confidence") or 0
        new_conf = raw.get("confidence", 80)
        target["confidence"] = max(cur_conf, new_conf) if cur_conf else new_conf
        target["status"] = raw.get("status", "LOCALISED" if (raw_x is not None and raw_y is not None) else "DETECTED")
        target["tracking_status"] = raw.get("tracking_status", "CONFIRMED")
        target["loc_status"] = raw.get("loc_status", "CONFIRMED" if (raw_x is not None and raw_y is not None) else "ESTIMATED")

        if raw_x is not None and raw_y is not None:
            target["x"] = round(float(raw_x), 2)
            target["y"] = round(float(raw_y), 2)
        if raw.get("grid"):
            target["grid"] = raw["grid"]
        if raw.get("bbox"):
            target["bbox"] = raw["bbox"]

        now_sec = raw.get("timestamp_sec", int(time.time()))
        if target.get("first_seen_sec") is None:
            target["first_seen_sec"] = now_sec
        target["last_seen_sec"] = now_sec
        target["is_stale"] = False

    roster = [roster_map[tid] for tid in DESIGNATED_TARGET_IDS]
    detected_count = sum(1 for t in roster if t["status"] in {"DETECTED", "TRACKING", "LOCALISED", "LOST", "STABLE", "MOVING"})
    localized_count = sum(1 for t in roster if t.get("loc_status") == "CONFIRMED")
    counts = {"detected": detected_count, "localized": localized_count, "total": 6}

    return roster, counts


def default_frame() -> Dict[str, Any]:
    """Produce a safe, initialized baseline telemetry frame with exactly six target slots."""
    baseline_targets: List[Dict[str, Any]] = []
    for tid in DESIGNATED_TARGET_IDS:
        num = tid.lstrip("S")
        baseline_targets.append({
            "id": tid,
            "number": num,
            "grid": "—",
            "x": None,
            "y": None,
            "lat": None,
            "lon": None,
            "confidence": None,
            "status": "SEARCHING",
            "tracking_status": "NOT DETECTED",
            "loc_status": "UNAVAILABLE",
            "movement": "—",
            "bbox": None,
            "thumb": "assets/thumb_s1.png",
            "color_hex": "#64748b",
            "first_seen_sec": None,
            "last_seen_sec": None,
            "is_stale": False,
        })

    return {
        "source_type": "SIMULATION",
        "source_label": "SIMULATION - READY",
        "mode": "AUTONOMOUS",
        "phase": MissionState.READY,
        "mission_seconds": 0,
        "coverage": 0,
        "target": "S01",
        "target_count": "0 / 6",
        "detected_count": 0,
        "localized_count": 0,
        "total_targets": 6,
        "drone": {
            "x": 1.5,
            "y": 1.5,
            "z": 0.0,
            "heading": 90.0,
            "yaw": 90.0,
            "altitude": 0.0,
            "speed": 0.0,
        },
        "telemetry": {
            "battery": 87,
            "voltage": 22.4,
            "current": 1.2,
            "link_ms": 35,
            "quality": 98,
            "mode": "AUTONOMOUS",
            "speed": 0.0,
            "heading": 90.0,
            "altitude": 0.0,
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
            "Jetson Orin": "OK (SIM)",
            "Jetson Gimbal / Mount": "OK (SIM)",
            "RPLIDAR C1": "OK (SIM)",
            "ROS 2 Bridge": "SIMULATED",
            "MAVLink": "OK (SIM)",
        },
        "survivors": baseline_targets,
        "active_waypoint_idx": 0,
        "completed_waypoints": [],
        "staged_waypoints": [],
        "accepted_waypoints": [list(pt) for pt in AUTONOMOUS_SEARCH_WAYPOINTS],
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


# ==============================================================================
# AUTONOMOUS SIMULATION ENGINE
# ==============================================================================
class SimulationPlugin(DataPlugin):
    """Deterministic, hardware-free autonomous six-target rescue simulation engine."""
    name = "Simulation"

    def __init__(self) -> None:
        self.sm = MissionStateMachine(initial_state=MissionState.READY)
        self.is_running = True
        self.is_paused = False
        self.start_time = time.monotonic()
        self.pause_time = 0.0
        self.total_paused_duration = 0.0
        self.base_battery = 87.0

        self.waypoints: List[Tuple[float, float]] = list(AUTONOMOUS_SEARCH_WAYPOINTS)
        self.staged_waypoints: List[Tuple[float, float, str]] = []
        self.current_wp_idx = 0
        self.completed_wp_indices: List[int] = []

        # Current kinematic state
        self.cur_x = 1.5
        self.cur_y = 1.5
        self.cur_alt = 2.40
        self.cur_yaw = 90.0
        self.cur_speed = 0.0

        # Injected test events (strictly clamped to S01-S06)
        self.test_overrides: Dict[str, Dict[str, Any]] = {}

    @property
    def flight_mode(self) -> str:
        cur = self.sm.get_state()
        if cur in {MissionState.ABORTING, MissionState.ABORTED}:
            return "ABORTED"
        if cur == MissionState.RETURNING_HOME:
            return "RETURNING HOME"
        if cur == MissionState.PAUSED_HOLD:
            return "PAUSED / SAFE HOLD"
        return "AUTONOMOUS"

    @flight_mode.setter
    def flight_mode(self, val: str) -> None:
        pass

    @property
    def accepted_waypoints(self) -> List[Tuple[float, float]]:
        return self.waypoints

    def start(self) -> None:
        self.is_running = True
        self.is_paused = False

    def pause(self) -> None:
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.pause_time = time.monotonic()
            self.sm.transition(MissionState.PAUSED_HOLD, "Operator commanded pause/hold")

    def resume(self) -> None:
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.total_paused_duration += time.monotonic() - self.pause_time
            self.sm.transition(MissionState.AUTONOMOUS_SEARCH, "Operator resumed mission")

    def reset(self) -> None:
        self.start_time = time.monotonic()
        self.pause_time = 0.0
        self.total_paused_duration = 0.0
        self.is_running = True
        self.is_paused = False
        self.current_wp_idx = 0
        self.completed_wp_indices.clear()
        self.cur_x, self.cur_y = 1.5, 1.5
        self.cur_alt = 2.40
        self.cur_yaw = 90.0
        self.cur_speed = 0.0
        self.staged_waypoints.clear()
        self.test_overrides.clear()
        self.sm = MissionStateMachine(initial_state=MissionState.READY)

    def get_elapsed_seconds(self) -> float:
        if not self.is_running:
            return 0.0
        if self.is_paused:
            return max(0.0, self.pause_time - self.start_time - self.total_paused_duration)
        return max(0.0, time.monotonic() - self.start_time - self.total_paused_duration)

    def poll(self) -> PluginResult:
        elapsed = self.get_elapsed_seconds()
        sim_sec = int(elapsed)
        current_state = self.sm.get_state()

        # ----------------------------------------------------------------------
        # 1. KINEMATICS & AUTONOMOUS ROUTE TRAVERSAL
        # ----------------------------------------------------------------------
        route = self.waypoints
        in_motion_states = {
            MissionState.AUTONOMOUS_SEARCH,
            MissionState.TARGET_DETECTED,
            MissionState.TARGET_TRACKING,
            MissionState.RETURNING_HOME,
        }

        if current_state in in_motion_states and len(route) >= 2:
            self.cur_speed = 1.2 if current_state != MissionState.RETURNING_HOME else 1.0
            seg_duration = 12.0  # seconds per autonomous waypoint leg
            total_duration = seg_duration * (len(route) - 1)
            t_route = (elapsed * 0.9) % total_duration
            seg_idx = int(t_route / seg_duration)
            next_idx = min(len(route) - 1, seg_idx + 1)
            frac = (t_route - (seg_idx * seg_duration)) / seg_duration

            self.current_wp_idx = next_idx
            self.completed_wp_indices = list(range(seg_idx))

            p1 = route[seg_idx]
            p2 = route[next_idx]
            self.cur_x = round(p1[0] + (p2[0] - p1[0]) * frac, 2)
            self.cur_y = round(p1[1] + (p2[1] - p1[1]) * frac, 2)

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            self.cur_yaw = round((math.degrees(math.atan2(dy, dx))) % 360, 1)
            self.cur_alt = 2.40
        elif current_state in {MissionState.PAUSED_HOLD, MissionState.READY, MissionState.IDLE}:
            self.cur_speed = 0.0
            self.cur_alt = 2.40 if current_state == MissionState.PAUSED_HOLD else 0.0
        elif current_state == MissionState.ABORTING:
            self.cur_speed = 0.0
            self.cur_alt = max(0.0, round(self.cur_alt - 0.2, 2))
            if self.cur_alt <= 0.05:
                self.sm.transition(MissionState.ABORTED, "Touchdown completed")
        elif current_state == MissionState.ABORTED:
            self.cur_speed = 0.0
            self.cur_alt = 0.0

        # Battery calculation
        battery_pct = max(5, int(self.base_battery - (elapsed * 0.015)))
        voltage = round(19.8 + (battery_pct / 100.0) * 3.0, 1)

        # ----------------------------------------------------------------------
        # 2. EXACTLY SIX DESIGNATED TARGETS STATUS
        # ----------------------------------------------------------------------
        roster_targets: List[Dict[str, Any]] = []
        detected_count = 0
        localized_count = 0

        for cand in SIM_TARGETS_MASTER:
            tid = cand["id"]
            num = cand["number"]
            grid = cand["grid"]
            x_val = cand["x"]
            y_val = cand["y"]
            col_hex = cand["color_hex"]
            thumb = cand["thumb"]

            # Check if this target is overridden by a test event
            if tid in self.test_overrides:
                override_data = self.test_overrides[tid]
                item = dict(override_data)
                if item.get("status") in {"DETECTED", "TRACKING", "LOCALISED"}:
                    detected_count += 1
                if item.get("loc_status") == "CONFIRMED":
                    localized_count += 1
                roster_targets.append(item)
                continue

            # Standard simulation timeline
            disc_sec = cand.get("discover_sec", 999)
            track_sec = cand.get("track_sec", disc_sec + 4)
            loc_sec = cand.get("localize_sec", track_sec + 6)
            lost_sec = cand.get("lost_sec", 999)
            reacquire_sec = cand.get("reacquire_sec", 999)

            if sim_sec < disc_sec:
                # Target not yet detected
                status = "SEARCHING"
                tracking_status = "NOT DETECTED"
                loc_status = "UNAVAILABLE"
                conf = None
                display_x, display_y = None, None
                first_seen = None
                last_seen = None
                is_stale = False
            elif lost_sec <= sim_sec < reacquire_sec:
                # Temporary occlusion / loss event
                status = "LOST"
                tracking_status = "LOST"
                loc_status = "ESTIMATED"
                conf = cand["confidence"] - 15
                display_x, display_y = x_val, y_val
                first_seen = disc_sec
                last_seen = lost_sec
                is_stale = True
                detected_count += 1
            elif sim_sec >= loc_sec:
                # Fully localised and confirmed
                status = "LOCALISED"
                tracking_status = "CONFIRMED"
                loc_status = "CONFIRMED"
                conf = cand["confidence"]
                display_x, display_y = x_val, y_val
                first_seen = disc_sec
                last_seen = sim_sec
                is_stale = False
                detected_count += 1
                localized_count += 1
            elif sim_sec >= track_sec:
                # Actively tracking
                status = "TRACKING"
                tracking_status = cand["movement"]
                loc_status = "ESTIMATED"
                conf = cand["confidence"]
                display_x, display_y = x_val, y_val
                first_seen = disc_sec
                last_seen = sim_sec
                is_stale = False
                detected_count += 1
            else:
                # Initial detection
                status = "DETECTED"
                tracking_status = "ACQUIRING"
                loc_status = "ESTIMATED"
                conf = cand["confidence"] - 5
                display_x, display_y = x_val, y_val
                first_seen = disc_sec
                last_seen = sim_sec
                is_stale = False
                detected_count += 1

            roster_targets.append({
                "id": tid,
                "number": num,
                "grid": grid if display_x is not None else "—",
                "x": display_x,
                "y": display_y,
                "lat": cand["lat"] if display_x is not None else None,
                "lon": cand["lon"] if display_x is not None else None,
                "confidence": conf,
                "status": status,
                "tracking_status": tracking_status,
                "loc_status": loc_status,
                "movement": cand["movement"] if display_x is not None else "—",
                "bbox": cand["bbox"] if status in {"DETECTED", "TRACKING", "LOCALISED"} else None,
                "thumb": thumb,
                "color_hex": col_hex,
                "first_seen_sec": first_seen,
                "last_seen_sec": last_seen,
                "is_stale": is_stale,
            })

        # ----------------------------------------------------------------------
        # 3. STATE MACHINE PROGRESSION BASED ON CRITERIA
        # ----------------------------------------------------------------------
        if current_state == MissionState.AUTONOMOUS_SEARCH and detected_count > 0:
            if localized_count == 6:
                self.sm.transition(MissionState.MISSION_COMPLETE, "All 6 designated targets confirmed and localized")
            elif any(t["status"] == "TRACKING" for t in roster_targets):
                self.sm.transition(MissionState.TARGET_TRACKING, "Tracker locked on active target")
            elif any(t["status"] == "DETECTED" for t in roster_targets):
                self.sm.transition(MissionState.TARGET_DETECTED, "New target signature detected")
        elif current_state == MissionState.TARGET_TRACKING and localized_count == 6:
            self.sm.transition(MissionState.MISSION_COMPLETE, "All 6 designated targets confirmed and localized")

        # ----------------------------------------------------------------------
        # 4. COVERAGE AND TIME FORMATTING
        # ----------------------------------------------------------------------
        mins = sim_sec // 60
        secs = sim_sec % 60
        flight_time_str = f"{mins:02d}:{secs:02d}"

        # Coverage proportional to mission progress and targets found
        coverage_pct = min(100, int((localized_count / 6.0) * 80 + min(20.0, elapsed * 0.2)))

        frame: Dict[str, Any] = {
            "source_type": "SIMULATION",
            "source_label": "SIMULATION - READY",
            "mode": "AUTONOMOUS",
            "phase": self.sm.get_state(),
            "mission_seconds": sim_sec,
            "coverage": coverage_pct,
            "target": roster_targets[min(detected_count, 5)]["id"] if detected_count > 0 else "—",
            "target_count": f"{detected_count} / 6",
            "detected_count": detected_count,
            "localized_count": localized_count,
            "total_targets": 6,
            "drone": {
                "x": self.cur_x,
                "y": self.cur_y,
                "z": self.cur_alt,
                "heading": self.cur_yaw,
                "yaw": self.cur_yaw,
                "altitude": self.cur_alt,
                "speed": self.cur_speed,
            },
            "telemetry": {
                "battery": battery_pct,
                "voltage": voltage,
                "current": 8.2 if self.cur_speed > 0 else 1.5,
                "link_ms": 35 + int((sim_sec % 4) * 2),
                "quality": 98,
                "mode": "AUTONOMOUS",
                "speed": self.cur_speed,
                "heading": self.cur_yaw,
                "altitude": self.cur_alt,
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
            "survivors": roster_targets,
            "active_waypoint_idx": self.current_wp_idx,
            "completed_waypoints": self.completed_wp_indices,
            "staged_waypoints": [list(w) for w in self.staged_waypoints],
            "accepted_waypoints": [list(w) for w in self.waypoints],
        }

        return PluginResult(frame=frame, status="SIMULATION", detail="Autonomous 6-Target Simulation Active")

    def send_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        cmd_upper = cmd.upper()

        if cmd_upper in {"START_MISSION", "START_AUTONOMOUS_MISSION"}:
            cur = self.sm.get_state()
            if cur in {MissionState.IDLE, MissionState.READY}:
                self.sm.transition(MissionState.AUTONOMOUS_SEARCH, "Autonomous search mission initiated")
                self.is_running = True
                self.is_paused = False
                return {"status": "ACCEPTED", "message": "Autonomous search mission started."}
            elif cur == MissionState.PAUSED_HOLD:
                self.sm.transition(MissionState.AUTONOMOUS_SEARCH, "Mission resumed from hold")
                self.is_paused = False
                return {"status": "ACCEPTED", "message": "Mission resumed from safe hold."}
            else:
                can_do, msg = self.sm.can_transition(MissionState.AUTONOMOUS_SEARCH)
                return {"status": "REJECTED", "message": f"Cannot start mission from {cur}: {msg}"}

        elif cmd_upper in {"PAUSE_MISSION", "SAFE_HOLD"}:
            cur = self.sm.get_state()
            can_do, msg = self.sm.can_transition(MissionState.PAUSED_HOLD)
            if can_do:
                self.pause()
                return {"status": "ACCEPTED", "message": "Mission paused. Drone hovering in safe hold."}
            return {"status": "REJECTED", "message": f"Cannot pause from {cur}: {msg}"}

        elif cmd_upper in {"RESUME_MISSION"}:
            cur = self.sm.get_state()
            if cur == MissionState.PAUSED_HOLD:
                self.resume()
                return {"status": "ACCEPTED", "message": "Autonomous search mission resumed."}
            return {"status": "REJECTED", "message": f"Cannot resume when state is {cur}"}

        elif cmd_upper in {"RTL", "RETURN_TO_HOME"}:
            can_do, msg = self.sm.transition(MissionState.RETURNING_HOME, "Return to launch commanded")
            if can_do:
                return {"status": "ACCEPTED", "message": "Return to launch sequence executed."}
            return {"status": "REJECTED", "message": f"RTL rejected: {msg}"}

        elif cmd_upper in {"ABORT", "EMERGENCY_ABORT", "ABORT_MISSION"}:
            self.sm.transition(MissionState.ABORTING, "Emergency abort commanded")
            return {"status": "ACCEPTED", "message": "Emergency abort executed. Immediate touchdown in progress."}

        elif cmd_upper in {"RESET_MISSION", "RESET"}:
            self.reset()
            return {"status": "ACCEPTED", "message": "Simulation reset to initial READY state."}

        elif cmd_upper == "SET_MODE":
            mode_req = params.get("mode", "").upper()
            if "MANUAL" in mode_req:
                return {
                    "status": "REJECTED",
                    "message": "Manual flight mode is disabled. Drone operates under autonomous mission control.",
                }
            return {"status": "ACCEPTED", "message": f"Autonomous mode set to {mode_req}."}

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
            self.waypoints.extend(new_pts)
            count = len(self.staged_waypoints)
            self.staged_waypoints.clear()
            return {"status": "ACCEPTED", "message": f"{count} staged waypoints committed to route."}

        elif cmd_upper == "CLEAR_WAYPOINTS":
            count = len(self.staged_waypoints)
            self.staged_waypoints.clear()
            return {"status": "ACCEPTED", "message": f"{count} staged waypoints cleared."}

        elif cmd_upper == "INJECT_TARGET_OVERRIDE":
            # For testing: inject state override for a specific target ID (S01-S06)
            tid = str(params.get("id", "S01")).upper()
            if tid not in DESIGNATED_TARGET_IDS:
                return {
                    "status": "REJECTED",
                    "message": f"Invalid target {tid}. Mission strictly constrained to S01-S06.",
                }
            self.test_overrides[tid] = params
            return {"status": "ACCEPTED", "message": f"Target {tid} override applied."}

        elif cmd_upper == "CLEAR_TARGET_OVERRIDES":
            self.test_overrides.clear()
            return {"status": "ACCEPTED", "message": "Target overrides cleared."}

        return {"status": "REJECTED", "message": f"Unknown command: {cmd}"}


# ==============================================================================
# JSON FILE & MANAGER
# ==============================================================================
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
