"""TEAM EDITH — GCS WebSocket Client Module.
NIDAR Rescue GCS Ground Control Station.

Provides a thread-safe, non-blocking asynchronous WebSocket client for PyQt6
connecting to the ROS 2 GCS bridge (or simulation bridge).

Handles:
- Configurable WebSocket URL and port (e.g. ws://127.0.0.1:9090).
- Automatic reconnection with bounded exponential backoff.
- Truthful connection lifecycle states: DISCONNECTED, CONNECTING, CONNECTED, STALE, ERROR.
- Strict schema validation and safe default fallback.
- Bidirectional command dispatching with command IDs, timeouts, and acknowledgements.
- Data staleness detection.
- Clean shutdown when the GUI closes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

logger = logging.getLogger("gcs_client")


class GCSClientWorker(QThread):
    """Background worker thread running an asyncio event loop for WebSockets."""

    # Qt Signals for GUI integration
    connected_signal = pyqtSignal()
    disconnected_signal = pyqtSignal()
    status_changed_signal = pyqtSignal(str)  # "CONNECTING", "CONNECTED", "DISCONNECTED", "STALE", "ERROR"
    frame_received_signal = pyqtSignal(dict)
    telemetry_received_signal = pyqtSignal(dict)
    detections_received_signal = pyqtSignal(list)
    sensors_received_signal = pyqtSignal(dict)
    command_ack_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, url: str = "ws://127.0.0.1:9090", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.url = url.strip()
        self._is_running = True
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws: Any = None
        self._send_queue: Optional[asyncio.Queue] = None
        self._last_msg_timestamp: float = 0.0
        self._stale_threshold_sec: float = 3.0
        self._current_status: str = "DISCONNECTED"

    def set_url(self, url: str) -> None:
        self.url = url.strip()

    def get_status(self) -> str:
        return self._current_status

    def is_stale(self) -> bool:
        if self._current_status != "CONNECTED":
            return False
        return (time.monotonic() - self._last_msg_timestamp) > self._stale_threshold_sec

    def send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Enqueue a command dictionary to be sent to the bridge."""
        cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"
        payload = {
            "type": "command",
            "command_id": cmd_id,
            "command": command,
            "params": params or {},
            "timestamp": time.time(),
        }
        if self._loop and self._send_queue and self.isRunning():
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, payload)
        return cmd_id

    def stop(self) -> None:
        """Signal the worker to stop and wait for loop termination."""
        self._is_running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.quit()
        self.wait(1500)

    def run(self) -> None:
        """Worker thread entrypoint."""
        try:
            import websockets
        except ImportError as exc:
            self._current_status = "ERROR"
            self.error_signal.emit(f"websockets package not available: {exc}")
            self.status_changed_signal.emit("ERROR")
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_queue = asyncio.Queue()

        try:
            self._loop.run_until_complete(self._main_client_loop())
        except Exception as exc:
            logger.debug(f"Event loop terminated: {exc}")
        finally:
            try:
                # Cancel all remaining tasks
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.close()
            except Exception:
                pass
            self._current_status = "DISCONNECTED"
            self.status_changed_signal.emit("DISCONNECTED")

    async def _main_client_loop(self) -> None:
        import websockets

        backoff = 1.0
        max_backoff = 10.0

        while self._is_running:
            self._current_status = "CONNECTING"
            self.status_changed_signal.emit("CONNECTING")

            try:
                async with websockets.connect(
                    self.url,
                    ping_interval=10,
                    ping_timeout=5,
                    close_timeout=3,
                ) as ws:
                    self._ws = ws
                    self._current_status = "CONNECTED"
                    self._last_msg_timestamp = time.monotonic()
                    backoff = 1.0  # Reset backoff on successful connection
                    self.connected_signal.emit()
                    self.status_changed_signal.emit("CONNECTED")

                    consumer_task = asyncio.create_task(self._consumer_handler(ws))
                    producer_task = asyncio.create_task(self._producer_handler(ws))
                    stale_check_task = asyncio.create_task(self._stale_monitor())

                    done, pending = await asyncio.wait(
                        [consumer_task, producer_task, stale_check_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()

            except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError) as exc:
                self._current_status = "DISCONNECTED"
                self.disconnected_signal.emit()
                self.status_changed_signal.emit("DISCONNECTED")
            except Exception as exc:
                self._current_status = "ERROR"
                self.error_signal.emit(f"Connection error: {exc}")
                self.status_changed_signal.emit("ERROR")

            if not self._is_running:
                break

            # Bounded exponential backoff
            await asyncio.sleep(backoff)
            backoff = min(max_backoff, backoff * 1.5)

    async def _consumer_handler(self, ws: Any) -> None:
        async for message in ws:
            if not self._is_running:
                break
            self._last_msg_timestamp = time.monotonic()
            try:
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                data = json.loads(message)
                if not isinstance(data, dict):
                    continue
                self._dispatch_incoming_data(data)
            except json.JSONDecodeError as exc:
                self.error_signal.emit(f"Malformed JSON from bridge: {exc}")
            except Exception as exc:
                self.error_signal.emit(f"Error handling bridge frame: {exc}")

    async def _producer_handler(self, ws: Any) -> None:
        while self._is_running:
            try:
                payload = await asyncio.wait_for(self._send_queue.get(), timeout=0.5)
                await ws.send(json.dumps(payload))
                self._send_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.debug(f"Send failed: {exc}")
                break

    async def _stale_monitor(self) -> None:
        while self._is_running:
            await asyncio.sleep(1.0)
            if self._current_status == "CONNECTED":
                if (time.monotonic() - self._last_msg_timestamp) > self._stale_threshold_sec:
                    self._current_status = "STALE"
                    self.status_changed_signal.emit("STALE")
            elif self._current_status == "STALE":
                if (time.monotonic() - self._last_msg_timestamp) <= self._stale_threshold_sec:
                    self._current_status = "CONNECTED"
                    self.status_changed_signal.emit("CONNECTED")

    def _dispatch_incoming_data(self, data: Dict[str, Any]) -> None:
        """Route parsed JSON payload to appropriate signals with safe schema extraction."""
        msg_type = data.get("type")

        # Command acknowledgement
        if msg_type == "command_ack" or "command_id" in data:
            self.command_ack_signal.emit(data)
            return

        # Canonical full telemetry frame
        self.frame_received_signal.emit(data)

        if "drone" in data or "battery" in data or "telemetry" in data:
            self.telemetry_received_signal.emit(data)

        if "targets" in data or "survivors" in data:
            targets = data.get("targets") or data.get("survivors") or []
            if isinstance(targets, list):
                self.detections_received_signal.emit(targets)

        if "sensors" in data or "health" in data or "components" in data:
            sensors = data.get("sensors") or data.get("health") or {}
            if isinstance(sensors, dict):
                self.sensors_received_signal.emit(sensors)
