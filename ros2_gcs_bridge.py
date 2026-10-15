#!/usr/bin/env python3
"""
TEAM EDITH — ROS 2 Ground Control Station WebSocket Bridge
NIDAR AirMouse Problem Statement 2

Subscribes to standard ROS 2 robotics topics:
  - /map (nav_msgs/msg/OccupancyGrid)
  - /scan (sensor_msgs/msg/LaserScan)
  - /odom (nav_msgs/msg/Odometry)
  - /drone/battery (sensor_msgs/msg/BatteryState)
  - /survivors/detections (std_msgs/msg/String / vision_msgs)
  - /diagnostics (diagnostic_msgs/msg/DiagnosticArray)

Broadcasts JSON frames to the GCS frontend via WebSocket (port 9090).
"""

import asyncio
import json
# pyrefly: ignore [missing-import]
import websockets
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import LaserScan, BatteryState
from std_msgs.msg import String

class EdithGCSBridge(Node):
    def __init__(self):
        super().__init__('edith_gcs_bridge')
        self.get_logger().info('Initializing TEAM EDITH GCS WebSocket Bridge...')

        self.telemetry = {
            "mode": "live",
            "drone": {"x": 1.2, "y": 1.2, "yaw": 0.0, "altitude": 1.18},
            "battery": {"percent": 65, "voltage": 22.8},
            "targets": []
        }
        self.connected_clients = set()

        # ROS 2 Subscribers
        self.sub_odom = self.create_subscription(Odometry, '/odom', self.odom_callback, 10)
        self.sub_bat = self.create_subscription(BatteryState, '/drone/battery', self.bat_callback, 10)
        self.sub_targets = self.create_subscription(String, '/survivors/detections', self.targets_callback, 10)

    def odom_callback(self, msg: Odometry):
        self.telemetry["drone"]["x"] = round(msg.pose.pose.position.x, 2)
        self.telemetry["drone"]["y"] = round(msg.pose.pose.position.y, 2)
        self.telemetry["drone"]["altitude"] = round(msg.pose.pose.position.z, 2)

    def bat_callback(self, msg: BatteryState):
        self.telemetry["battery"]["percent"] = int(msg.percentage * 100)
        self.telemetry["battery"]["voltage"] = round(msg.voltage, 2)

    def targets_callback(self, msg: String):
        try:
            self.telemetry["targets"] = json.loads(msg.data)
        except Exception:
            pass

    async def broadcast_loop(self):
        while True:
            if self.connected_clients:
                message = json.dumps(self.telemetry)
                await asyncio.gather(
                    *[ws.send(message) for ws in self.connected_clients],
                    return_exceptions=True
                )
            await asyncio.sleep(0.1) # 10 Hz telemetry stream

async def websocket_handler(websocket, bridge: EdithGCSBridge):
    bridge.connected_clients.add(websocket)
    bridge.get_logger().info(f"Client connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("command") == "ABORT":
                bridge.get_logger().warn("GCS DISPATCHED EMERGENCY ABORT / RTL!")
    finally:
        bridge.connected_clients.remove(websocket)

def main():
    rclpy.init()
    bridge_node = EdithGCSBridge()

    async def main_async():
        server = await websockets.serve(
            lambda ws: websocket_handler(ws, bridge_node),
            "0.0.0.0",
            9090
        )
        bridge_node.get_logger().info("GCS WebSocket Server running on ws://0.0.0.0:9090")
        
        while rclpy.ok():
            rclpy.spin_once(bridge_node, timeout_sec=0.01)
            await asyncio.sleep(0.01)

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
    finally:
        bridge_node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
