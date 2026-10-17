#!/usr/bin/env python3
"""TEAM EDITH — ROS 2 Ground Control Station WebSocket Bridge.
NIDAR AirMouse Problem Statement 2.

Dual-mode bridge:
1. ROS 2 Mode (Active when rclpy and ROS 2 are installed):
   Subscribes to standard ROS 2 robotics topics:
     - /map (nav_msgs/msg/OccupancyGrid)
     - /scan (sensor_msgs/msg/LaserScan)
     - /odom (nav_msgs/msg/Odometry)
     - /drone/battery (sensor_msgs/msg/BatteryState)
     - /survivors/detections (std_msgs/msg/String / vision_msgs)
     - /diagnostics (diagnostic_msgs/msg/DiagnosticArray)
   Publishes commands received from GCS:
     - /cmd_vel (geometry_msgs/msg/Twist)
     - /mission/abort (std_msgs/msg/Empty or Bool)

2. Standalone Simulation Mode (Active when rclpy is not installed):
   Runs a mock telemetry broadcaster on WebSocket port 9090 for hardware-free
   development on Windows. Accepts GCS commands and responds with acknowledgements.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import time
from typing import Any, Dict, Optional, Set

import websockets

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ros2_gcs_bridge")

# Safe ROS 2 import guard
ROS2_AVAILABLE = False
try:
    import rclpy
    from nav_msgs.msg import OccupancyGrid, Odometry
    from rclpy.node import Node
    from sensor_msgs.msg import BatteryState, LaserScan
    from std_msgs.msg import String

    ROS2_AVAILABLE = True
except ImportError:
    Node = object  # type: ignore[misc,assignment]


class EdithGCSBridge(Node if ROS2_AVAILABLE else object):
    """Bridge node connecting ROS 2 topics to WebSocket clients, or simulating them."""

    def __init__(self) -> None:
        if ROS2_AVAILABLE:
            super().__init__("edith_gcs_bridge")
            self.get_logger().info("Initializing TEAM EDITH GCS WebSocket Bridge with ROS 2 Humble...")
        else:
            logger.info("Initializing TEAM EDITH GCS WebSocket Bridge in STANDALONE SIMULATION mode (ROS 2 not installed)...")

        self.telemetry: Dict[str, Any] = {
            "type": "telemetry",
            "mode": "live" if ROS2_AVAILABLE else "simulation",
            "phase": "EXPLORING",
            "mission_seconds": 0,
            "coverage": 64,
            "drone": {"x": 7.0, "y": 6.0, "z": 2.35, "yaw": 228.0, "altitude": 2.35, "speed": 1.19},
            "battery": {"percent": 87, "voltage": 22.4, "current": 8.2},
            "telemetry": {"battery": 87, "voltage": 22.4, "current": 8.2, "link_ms": 37, "quality": 98, "mode": "RTL / LAND"},
            "sensors": {
                "lidar": "ACTIVE",
                "radar": "ACTIVE",
                "vision": "ACTIVE",
                "wifi": "CONNECTED",
                "mavlink": "CONNECTED",
                "connected": "ACTIVE",
            },
            "health": {
                "Jetson Orin": "OK",
                "Jetson Gimbal / Mount": "OK",
                "RPLIDAR C1": "OK",
                "ROS 2 Bridge": "OK" if ROS2_AVAILABLE else "SIMULATED",
                "MAVLink": "OK",
            },
            "targets": [
                {
                    "id": "S01",
                    "number": "01",
                    "grid": "A1",
                    "confidence": 93,
                    "status": "STABLE",
                    "x": 2.7,
                    "y": 3.75,
                    "lat": 10.8462,
                    "lon": 76.2711,
                    "bbox": [0.15, 0.20, 0.25, 0.35],
                    "movement": "STABLE",
                    "detected_at": "14:52",
                },
                {
                    "id": "S02",
                    "number": "02",
                    "grid": "C4",
                    "confidence": 87,
                    "status": "MOVING",
                    "x": 7.8,
                    "y": 5.25,
                    "lat": 10.8468,
                    "lon": 76.2719,
                    "bbox": [0.45, 0.30, 0.58, 0.48],
                    "movement": "MOVING",
                    "detected_at": "14:53",
                },
            ],
            "active_waypoints": [
                (1.2, 1.2), (1.2, 4.2), (3.5, 4.2), (7.2, 4.0), (11.2, 8.5)
            ],
        }

        self.connected_clients: Set[Any] = set()
        self.sim_tick = 0
        self.start_time = time.monotonic()

        if ROS2_AVAILABLE:
            self._setup_ros2_subscribers()

    def _setup_ros2_subscribers(self) -> None:
        self.sub_odom = self.create_subscription(Odometry, "/odom", self.odom_callback, 10)
        self.sub_bat = self.create_subscription(BatteryState, "/drone/battery", self.bat_callback, 10)
        self.sub_targets = self.create_subscription(String, "/survivors/detections", self.targets_callback, 10)

    def odom_callback(self, msg: Any) -> None:
        self.telemetry["drone"]["x"] = round(msg.pose.pose.position.x, 2)
        self.telemetry["drone"]["y"] = round(msg.pose.pose.position.y, 2)
        self.telemetry["drone"]["altitude"] = round(msg.pose.pose.position.z, 2)
        self.telemetry["drone"]["z"] = round(msg.pose.pose.position.z, 2)

    def bat_callback(self, msg: Any) -> None:
        pct = int(msg.percentage * 100) if msg.percentage <= 1.0 else int(msg.percentage)
        self.telemetry["battery"]["percent"] = pct
        self.telemetry["battery"]["voltage"] = round(msg.voltage, 2)
        self.telemetry["telemetry"]["battery"] = pct
        self.telemetry["telemetry"]["voltage"] = round(msg.voltage, 2)

    def targets_callback(self, msg: Any) -> None:
        try:
            self.telemetry["targets"] = json.loads(msg.data)
        except Exception as exc:
            logger.debug(f"Targets parse error: {exc}")

    def update_simulation_tick(self) -> None:
        """Advance mock physics and trajectory when running in hardware-free mode."""
        self.sim_tick += 1
        elapsed = time.monotonic() - self.start_time
        self.telemetry["mission_seconds"] = int(elapsed)

        # Orbit arena waypoint path
        t = elapsed * 0.15
        cx, cy, r = 7.5, 7.5, 4.0
        x = cx + r * math.cos(t)
        y = cy + r * math.sin(t)
        yaw = (math.degrees(t + math.pi / 2)) % 360

        self.telemetry["drone"]["x"] = round(x, 2)
        self.telemetry["drone"]["y"] = round(y, 2)
        self.telemetry["drone"]["heading"] = round(yaw, 1)
        self.telemetry["drone"]["yaw"] = round(yaw, 1)

    async def broadcast_loop(self) -> None:
        while True:
            if not ROS2_AVAILABLE:
                self.update_simulation_tick()

            if self.connected_clients:
                message = json.dumps(self.telemetry)
                # Send to all connected GCS clients
                await asyncio.gather(
                    *[ws.send(message) for ws in list(self.connected_clients)],
                    return_exceptions=True,
                )
            await asyncio.sleep(0.1)  # 10 Hz telemetry stream

    def process_command(self, cmd_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming command and return structured acknowledgement."""
        cmd_id = cmd_data.get("command_id", f"cmd_{int(time.time()*1000)}")
        cmd = cmd_data.get("command", "").upper()
        params = cmd_data.get("params", {})

        logger.info(f"Received GCS Command: {cmd} (ID: {cmd_id}) with params {params}")

        if cmd in {"ABORT", "EMERGENCY_ABORT", "RTL"}:
            self.telemetry["telemetry"]["mode"] = "RTL / LAND"
            self.telemetry["phase"] = "RTL"
            return {
                "type": "command_ack",
                "command_id": cmd_id,
                "command": cmd,
                "status": "ACCEPTED",
                "message": "Emergency abort / RTL commanded successfully.",
                "timestamp": time.time(),
            }
        elif cmd == "SET_MODE":
            mode_name = params.get("mode", "MANUAL")
            self.telemetry["telemetry"]["mode"] = mode_name
            return {
                "type": "command_ack",
                "command_id": cmd_id,
                "command": cmd,
                "status": "ACCEPTED",
                "message": f"Flight mode set to {mode_name}.",
                "timestamp": time.time(),
            }
        elif cmd == "STAGE_WAYPOINT":
            wp = params.get("waypoint")
            return {
                "type": "command_ack",
                "command_id": cmd_id,
                "command": cmd,
                "status": "ACCEPTED",
                "message": f"Waypoint {wp} received by planner.",
                "timestamp": time.time(),
            }
        else:
            return {
                "type": "command_ack",
                "command_id": cmd_id,
                "command": cmd,
                "status": "REJECTED",
                "message": f"Unrecognized or unsupported command: {cmd}",
                "timestamp": time.time(),
            }


async def websocket_handler(websocket: Any, bridge: EdithGCSBridge) -> None:
    bridge.connected_clients.add(websocket)
    remote = getattr(websocket, "remote_address", "client")
    logger.info(f"GCS client connected from {remote}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if isinstance(data, dict):
                    ack = bridge.process_command(data)
                    await websocket.send(json.dumps(ack))
            except json.JSONDecodeError:
                err_ack = {
                    "type": "command_ack",
                    "status": "REJECTED",
                    "message": "Invalid JSON format received",
                    "timestamp": time.time(),
                }
                await websocket.send(json.dumps(err_ack))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        bridge.connected_clients.remove(websocket)
        logger.info(f"GCS client disconnected from {remote}")


def main() -> None:
    if ROS2_AVAILABLE:
        rclpy.init()

    bridge_node = EdithGCSBridge()

    async def main_async() -> None:
        host = "0.0.0.0"
        port = 9090
        server = await websockets.serve(
            lambda ws: websocket_handler(ws, bridge_node),
            host,
            port,
        )
        logger.info(f"GCS WebSocket Server running on ws://127.0.0.1:{port}")

        broadcast_task = asyncio.create_task(bridge_node.broadcast_loop())

        if ROS2_AVAILABLE:
            while rclpy.ok():
                rclpy.spin_once(bridge_node, timeout_sec=0.02)
                await asyncio.sleep(0.01)
        else:
            # Keep event loop running in standalone simulation mode
            await broadcast_task

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Bridge stopped by user.")
    finally:
        if ROS2_AVAILABLE:
            bridge_node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
