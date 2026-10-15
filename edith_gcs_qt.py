#!/usr/bin/env python3
"""NIDAR Rescue GCS — native desktop operator console.

This UI mirrors the approved web-console reference while remaining a local
PyQt6 application. It labels simulation data and can consume a normalized
JSON file or HTTP JSON feed through ``gcs_data_plugins``.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient, QPolygonF
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSlider, QSplitter, QVBoxLayout, QWidget,
)

from gcs_data_plugins import DataPluginManager, SIMULATION_ROUTE, deep_merge, default_frame


PALETTE = {
    "ink": "#10223f", "muted": "#60718e", "line": "#d8e1ed", "canvas": "#f4f7fb",
    "card": "#ffffff", "blue": "#1d4ed8", "cyan": "#009f8c", "green": "#00a67a",
    "green_soft": "#e7fbf5", "navy": "#1e2b41", "danger": "#df2c2c",
}


def label(text: str, size: int = 8, bold: bool = False, color: str = PALETTE["ink"]) -> QLabel:
    widget = QLabel(text)
    widget.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    widget.setStyleSheet(f"color:{color}; background:transparent;")
    return widget


def card_frame() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def coordinate_label(survivor: Dict[str, Any]) -> str:
    """Render coordinates defensively; external feeds may omit or stringify them."""
    if survivor.get("status") != "found":
        return "—"
    try:
        x = float(survivor.get("x", 0))
        y = float(survivor.get("y", 0))
    except (TypeError, ValueError):
        return "—"
    return f"X {x:.1f}E / Y {y:.1f}N"


class CameraSurface(QWidget):
    """Interactive synthetic feed; click it to swap IR and optical presentation."""

    mode_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.mode = "OPTICAL"
        self.zoom = 96
        self.setMinimumHeight(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_mode(self, mode: str) -> None:
        if mode not in {"OPTICAL", "THERMAL"}:
            return
        self.mode = mode
        self.update()

    def toggle_mode(self) -> None:
        self.mode = "THERMAL" if self.mode == "OPTICAL" else "OPTICAL"
        self.mode_changed.emit(self.mode)
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.toggle_mode()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        gradient = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomRight()))
        gradient.setColorAt(0, QColor("#040b18"))
        gradient.setColorAt(1, QColor("#10213b" if self.mode == "OPTICAL" else "#17111d"))
        p.fillRect(rect, gradient)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        for x in range(-rect.height(), rect.width(), 24):
            p.drawLine(x, 0, x + rect.height(), rect.height())
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        p.drawText(QRectF(rect), Qt.AlignmentFlag.AlignCenter, "CAMERA FEED")
        p.setFont(QFont("Segoe UI", 6))
        p.setPen(QColor("#91a4c5"))
        p.drawText(10, rect.height() - 10, self.mode)
        p.drawText(rect.width() - 65, rect.height() - 10, f"{self.zoom}%")
        p.end()


class PilotViewDialog(QDialog):
    """A larger local preview of the synthetic pilot feed."""

    mode_changed = pyqtSignal(str)
    zoom_changed = pyqtSignal(int)

    def __init__(self, mode: str, zoom: int, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("NIDAR Pilot View — Simulation")
        self.resize(920, 590)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(label("PILOT VIEW", 11, True))
        header.addWidget(label("SIMULATION · NO VEHICLE CONTROL", 7, True, PALETTE["muted"]))
        header.addStretch()
        layout.addLayout(header)
        self.camera = CameraSurface()
        self.camera.setMinimumSize(860, 470)
        self.camera.set_mode(mode)
        self.camera.zoom = zoom
        self.camera.mode_changed.connect(self.mode_changed.emit)
        layout.addWidget(self.camera, 1)
        controls = QHBoxLayout()
        toggle = QPushButton("TOGGLE OPTICAL / THERMAL")
        toggle.clicked.connect(self.camera.toggle_mode)
        controls.addWidget(toggle)
        controls.addWidget(label("ZOOM", 7, True, PALETTE["muted"]))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(70, 130)
        self.zoom.setValue(zoom)
        self.zoom.valueChanged.connect(self._set_zoom)
        controls.addWidget(self.zoom, 1)
        self.zoom_value = label(f"{zoom}%", 7, True)
        controls.addWidget(self.zoom_value)
        close = QPushButton("CLOSE")
        close.clicked.connect(self.close)
        controls.addWidget(close)
        layout.addLayout(controls)

    def _set_zoom(self, value: int) -> None:
        self.camera.zoom = value
        self.camera.update()
        self.zoom_value.setText(f"{value}%")
        self.zoom_changed.emit(value)

    def sync_mode(self, mode: str) -> None:
        self.camera.set_mode(mode)

    def sync_zoom(self, value: int) -> None:
        if self.zoom.value() != value:
            self.zoom.setValue(value)


class MapCanvas(QWidget):
    """Neutral local-coordinate renderer with a selectable waypoint."""

    waypoint_selected = pyqtSignal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(420, 285)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.frame: Dict[str, Any] = default_frame()
        self.night = False
        self.extra_waypoint: tuple[float, float] | None = None
        self.route = list(SIMULATION_ROUTE)

    def set_frame(self, frame: Dict[str, Any]) -> None:
        self.frame = frame
        self.update()

    def _area(self) -> QRectF:
        available = self.rect().adjusted(12, 10, -12, -10)
        ratio = 1.42
        width = min(available.width(), available.height() * ratio)
        height = width / ratio
        return QRectF(available.center().x() - width / 2, available.center().y() - height / 2, width, height)

    def _point(self, x: float, y: float, area: QRectF) -> QPointF:
        return QPointF(area.left() + x / 14 * area.width(), area.bottom() - y / 10 * area.height())

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#17253a" if self.night else "#1d2b3e"))
        area = self._area()
        p.fillRect(area, QColor("#3c514e" if self.night else "#677976"))
        p.setPen(QPen(QColor(255, 255, 255, 26) if self.night else QColor(210, 224, 220, 42), 1))
        for i in range(15):
            x = area.left() + i / 14 * area.width()
            p.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        for i in range(11):
            y = area.top() + i / 10 * area.height()
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))

        def occupancy_polygon(points: list[tuple[float, float]]) -> QPolygonF:
            return QPolygonF([QPointF(area.left() + x * area.width(), area.top() + y * area.height()) for x, y in points])

        # Reference-style synthetic occupancy grid. It communicates the visual
        # language of a 2D SLAM map without claiming a real floorplan or scan.
        free_space = occupancy_polygon([
            (0.05, 0.04), (0.46, 0.04), (0.48, 0.22), (0.92, 0.22), (0.94, 0.84),
            (0.86, 0.84), (0.85, 0.77), (0.72, 0.77), (0.71, 0.89), (0.60, 0.89),
            (0.58, 0.80), (0.43, 0.80), (0.42, 0.91), (0.26, 0.92), (0.23, 0.85),
            (0.08, 0.86), (0.08, 0.70), (0.03, 0.69), (0.04, 0.50), (0.09, 0.49),
            (0.09, 0.35), (0.05, 0.34),
        ])
        p.setBrush(QBrush(QColor("#c9cbca" if not self.night else "#9da5a2")))
        p.setPen(QPen(QColor("#0a1112"), 3))
        p.drawPolygon(free_space)

        obstacles = [
            [(0.16, 0.27), (0.35, 0.27), (0.36, 0.38), (0.26, 0.39), (0.25, 0.34), (0.16, 0.34)],
            [(0.16, 0.58), (0.36, 0.58), (0.36, 0.65), (0.27, 0.65), (0.26, 0.71), (0.16, 0.70)],
            [(0.49, 0.23), (0.52, 0.23), (0.52, 0.40), (0.49, 0.40)],
            [(0.57, 0.61), (0.78, 0.61), (0.78, 0.70), (0.65, 0.70), (0.64, 0.66), (0.57, 0.66)],
        ]
        p.setBrush(QBrush(QColor("#5e6d6a" if not self.night else "#465855")))
        p.setPen(QPen(QColor("#15201f"), 2))
        for obstacle in obstacles:
            p.drawPolygon(occupancy_polygon(obstacle))
        p.setPen(QPen(QColor("#0e1717"), 1.2))
        for x, y, width, height in ((.13, .17, .018, .06), (.39, .10, .025, .035), (.76, .32, .02, .02), (.82, .51, .012, .02), (.47, .78, .02, .02), (.33, .79, .014, .025), (.88, .45, .015, .015)):
            p.fillRect(QRectF(area.left() + x * area.width(), area.top() + y * area.height(), width * area.width(), height * area.height()), QColor("#121c1c"))

        p.setPen(QColor("#e8f0ed" if self.night else "#dce7e2"))
        p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        p.drawText(QPointF(area.left() + 10, area.bottom() - 10), "SIMULATED OCCUPANCY MAP")
        for index, grid_label in enumerate("ABCDEFGH"):
            p.drawText(QPointF(area.left() + 18 + index * (area.width() - 36) / 7, area.top() + 14), grid_label)

        path = [self._point(x, y, area) for x, y in self.route]
        p.setPen(QPen(QColor("#ffffff"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for first, second in zip(path, path[1:]):
            p.drawLine(first, second)
        p.setPen(QPen(QColor("#1964f2"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for first, second in zip(path, path[1:]):
            p.drawLine(first, second)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(QPen(QColor("#1964f2"), 2))
        p.drawEllipse(path[0], 4.5, 4.5)
        p.setFont(QFont("Segoe UI", 6))
        p.drawText(path[0] + QPointF(5, -3), "TRACK START")

        for survivor in self.frame.get("survivors", []):
            if survivor.get("status") != "found":
                continue
            pt = self._point(float(survivor.get("x", 0)), float(survivor.get("y", 0)), area)
            p.setBrush(QBrush(QColor("#00b894")))
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawEllipse(pt, 6, 6)
            p.setBrush(QBrush(QColor("#ffffff")))
            p.setPen(QPen(QColor("#1e2b41"), 1))
            bubble = QRectF(pt.x() + 9, pt.y() - 11, 42, 16)
            p.drawRoundedRect(bubble, 3, 3)
            p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            p.drawText(bubble, Qt.AlignmentFlag.AlignCenter, survivor.get("id", "S"))

        drone = self.frame.get("drone", {})
        dp = self._point(float(drone.get("x", 7)), float(drone.get("y", 6)), area)
        heading = math.radians(float(drone.get("heading", 0)))
        triangle = [
            dp + QPointF(math.cos(heading) * 12, -math.sin(heading) * 12),
            dp + QPointF(math.cos(heading + 2.45) * 9, -math.sin(heading + 2.45) * 9),
            dp + QPointF(math.cos(heading - 2.45) * 9, -math.sin(heading - 2.45) * 9),
        ]
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.setBrush(QBrush(QColor("#4865a8")))
        p.drawPolygon(triangle)
        tip = QRectF(dp.x() + 12, dp.y() - 23, 86, 23)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(QPen(QColor("#1f56d7"), 1))
        p.drawRoundedRect(tip, 3, 3)
        p.setPen(QColor("#10223f"))
        p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        p.drawText(tip.adjusted(4, 2, -2, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f"DRONE · HDG {int(drone.get('heading', 0))}°")
        p.setFont(QFont("Segoe UI", 5))
        p.drawText(tip.adjusted(4, 11, -2, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f"{drone.get('speed', 0):.2f}m/s · {drone.get('altitude', 0):.1f}m")

        if self.extra_waypoint:
            wp = self._point(*self.extra_waypoint, area)
            p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            p.setPen(QPen(QColor("#f59e0b"), 2, Qt.PenStyle.DashLine))
            p.drawEllipse(wp, 8, 8)
        legend = QRectF(area.right() - 112, area.bottom() - 31, 105, 24)
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.drawRoundedRect(legend, 3, 3)
        p.setPen(QPen(QColor("#1964f2"), 2))
        p.drawLine(QPointF(legend.left() + 8, legend.top() + 9), QPointF(legend.left() + 32, legend.top() + 9))
        p.setPen(QColor("#10223f"))
        p.setFont(QFont("Segoe UI", 5))
        p.drawText(QPointF(legend.left() + 38, legend.top() + 11), "TRAVELLED TRACK")
        p.drawText(QPointF(legend.left() + 38, legend.top() + 19), "1 m SCALE")
        p.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        area = self._area()
        if not area.contains(event.position()):
            return
        x = max(0.0, min(14.0, (event.position().x() - area.left()) / area.width() * 14))
        y = max(0.0, min(10.0, (area.bottom() - event.position().y()) / area.height() * 10))
        self.extra_waypoint = (x, y)
        self.waypoint_selected.emit(x, y)
        self.update()


class PreFlightDialog(QDialog):
    def __init__(self, manager: DataPluginManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("NIDAR Pre-Flight & Data Source")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(label("PRE-FLIGHT CHECK", 12, True))
        layout.addWidget(label("Select the source feeding this desktop console. Missing data remains visibly waiting.", 8, False, PALETTE["muted"]))
        self.source = QComboBox()
        self.source.addItems(["Simulation", "JSON file", "HTTP JSON"])
        self.source.setCurrentText(manager.source)
        layout.addWidget(self.source)
        self.endpoint = QLineEdit(manager.http_endpoint)
        self.endpoint.setPlaceholderText("http://127.0.0.1:8080/mission   (HTTP JSON only)")
        layout.addWidget(self.endpoint)
        self.source_hint = label("", 8, False, PALETTE["muted"])
        layout.addWidget(self.source_hint)
        for text in ("Mission controls checked", "Emergency return-to-launch path available", "Data source state visible to operator"):
            check = QCheckBox(text)
            check.setChecked(True)
            check.setEnabled(False)
            layout.addWidget(check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_source)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.source.currentTextChanged.connect(self.update_hint)
        self.update_hint()

    def update_hint(self) -> None:
        name = self.source.currentText()
        if name == "JSON file":
            hint = f"Watching {self.manager.data_dir / 'mission.json'}"
        elif name == "HTTP JSON":
            hint = "Endpoint is polled every two seconds with a short timeout."
        else:
            hint = "Built-in synthetic feed; no vehicle or external system is controlled."
        self.source_hint.setText(hint)
        self.endpoint.setEnabled(name == "HTTP JSON")

    def apply_source(self) -> None:
        self.manager.select(self.source.currentText(), self.endpoint.text())
        self.accept()


class ComponentDetailsDialog(QDialog):
    """Detailed planning inventory and runtime status view."""

    def __init__(self, frame: Dict[str, Any], plugin_status: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NIDAR Component Status & Target Platform")
        self.resize(760, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(label("COMPONENT STATUS / TARGET PLATFORM", 12, True))
        layout.addWidget(label("PLANNED means this is an estimated bill of materials. READY or CONNECTED must come from a real JSON/HTTP/ROS adapter.", 8, False, PALETTE["muted"]))

        platform = frame.get("target_platform", {})
        platform_card = card_frame()
        platform_layout = QGridLayout(platform_card)
        platform_layout.setContentsMargins(9, 7, 9, 7)
        platform_layout.addWidget(label("OS", 7, True, PALETTE["muted"]), 0, 0)
        platform_layout.addWidget(label(str(platform.get("os", "Ubuntu 22.04 LTS - Jammy Jellyfish")), 8, True), 0, 1)
        platform_layout.addWidget(label("ROS 2", 7, True, PALETTE["muted"]), 1, 0)
        platform_layout.addWidget(label(str(platform.get("ros", "ROS 2 Humble")), 8, True), 1, 1)
        platform_layout.addWidget(label("SLAM", 7, True, PALETTE["muted"]), 2, 0)
        platform_layout.addWidget(label(str(platform.get("slam", "LiDAR localization / SLAM")), 8, False), 2, 1)
        platform_layout.addWidget(label("AI HOST", 7, True, PALETTE["muted"]), 3, 0)
        platform_layout.addWidget(label(str(platform.get("ai", "Jetson nano orin super")), 8, True), 3, 1)
        layout.addWidget(platform_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        items_layout = QVBoxLayout(host)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.setSpacing(5)
        statuses = frame.get("component_status", {})
        for index, item in enumerate(frame.get("hardware_components", []), 1):
            row = card_frame()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(9, 6, 9, 6)
            top = QHBoxLayout()
            top.addWidget(label(f"{index:02d}  {item.get('name', 'Unnamed component')}", 9, True))
            top.addStretch()
            status_value = str(statuses.get(item.get("id", ""), "PLANNED")).upper()
            status = label(status_value, 7, True, PALETTE["green"] if status_value in {"READY", "ACTIVE", "CONNECTED"} else "#b77900")
            status.setObjectName("readyPill")
            top.addWidget(status)
            row_layout.addLayout(top)
            row_layout.addWidget(label(f"ROLE: {item.get('role', 'Role pending')}   ·   GROUP: {item.get('group', 'Unassigned')}   ·   PLUGIN STATUS: {plugin_status}", 7, False, PALETTE["muted"]))
            items_layout.addWidget(row)
        items_layout.addStretch()
        scroll.setWidget(host)
        layout.addWidget(scroll, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


class NidarRescueGCS(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NIDAR RESCUE GCS — AIRMOUSE SKELETAL V1")
        self.resize(1450, 900)
        self.setMinimumSize(1050, 650)
        self.night = False
        self.pilot_window: PilotViewDialog | None = None
        self.frame = default_frame()
        self.manager = DataPluginManager(Path(__file__).resolve().parent / "data")
        self.last_source_status = "READY"
        self.last_survivor_signature = ""
        self._build_ui()
        self._apply_theme()
        self._render_frame()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_data)
        self.timer.start(1000)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(7)
        outer.addWidget(self._header())
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._left_column())
        self.splitter.addWidget(self._center_column())
        self.splitter.addWidget(self._right_column())
        self.splitter.setStretchFactor(0, 22)
        self.splitter.setStretchFactor(1, 58)
        self.splitter.setStretchFactor(2, 20)
        self.splitter.setSizes([285, 830, 255])
        outer.addWidget(self.splitter, 1)
        outer.addWidget(self._event_bar())

    def _header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("header")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(9)
        row.addWidget(label("NIDAR RESCUE GCS", 12, True))
        row.addWidget(label("|  AIRMOUSE SKELETAL V1", 7, False, "#7c8eaf"))
        self.tabs: Dict[str, QPushButton] = {}
        for name in ("Mission", "Map", "Survivors"):
            button = QPushButton(name)
            button.setObjectName("navTab")
            button.clicked.connect(lambda checked=False, n=name: self.select_tab(n))
            self.tabs[name] = button
            row.addWidget(button)
        row.addStretch(1)
        self.mode_pill = label("● AUTONOMOUS", 8, True)
        self.mode_pill.setObjectName("modePill")
        row.addWidget(self.mode_pill)
        self.timer_label = label("TIMER: 00:00 / 30:00", 8, True)
        row.addWidget(self.timer_label)
        self.comm_label = label("COMM: CONNECTED · 98%", 8, True)
        self.comm_label.setObjectName("commPill")
        row.addWidget(self.comm_label)
        preflight = QPushButton("Pre-Flight")
        preflight.clicked.connect(self.open_preflight)
        row.addWidget(preflight)
        self.night_button = QPushButton("NIGHT")
        self.night_button.clicked.connect(self.toggle_night)
        row.addWidget(self.night_button)
        return bar

    def _left_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        cam = card_frame()
        cam_layout = QVBoxLayout(cam)
        cam_layout.setContentsMargins(9, 8, 9, 8)
        head = QHBoxLayout()
        head.addWidget(label("●  LIVE CAMERA", 9, True, PALETTE["ink"]))
        head.addStretch()
        self.camera_live = label("LIVE · OPTICAL", 7, True, PALETTE["green"])
        head.addWidget(self.camera_live)
        self.camera_mode = QPushButton("PILOT VIEW ↗")
        self.camera_mode.setObjectName("miniButton")
        self.camera_mode.clicked.connect(self.open_pilot_view)
        head.addWidget(self.camera_mode)
        cam_layout.addLayout(head)
        self.camera = CameraSurface()
        self.camera.mode_changed.connect(self.on_camera_mode_changed)
        cam_layout.addWidget(self.camera)
        slider_row = QHBoxLayout()
        slider_row.addWidget(label("VIEW SIZE", 7, True, PALETTE["muted"]))
        self.camera_slider = QSlider(Qt.Orientation.Horizontal)
        self.camera_slider.setRange(70, 130)
        self.camera_slider.setValue(96)
        self.camera_slider.valueChanged.connect(self.change_camera_zoom)
        slider_row.addWidget(self.camera_slider, 1)
        self.zoom_label = label("96%", 7, True)
        slider_row.addWidget(self.zoom_label)
        cam_layout.addLayout(slider_row)
        people = QHBoxLayout()
        people.addWidget(label("People detected", 8))
        people.addStretch()
        self.people_label = label("02", 8, True)
        self.people_label.setObjectName("numberBadge")
        people.addWidget(self.people_label)
        cam_layout.addLayout(people)
        layout.addWidget(cam, 3)

        queue = card_frame()
        queue_layout = QVBoxLayout(queue)
        queue_layout.setContentsMargins(9, 8, 9, 8)
        queue_layout.addWidget(label("DETECTIONS", 9, True))
        self.survivor_host = QWidget()
        self.survivor_host.setObjectName("survivorList")
        self.survivor_layout = QVBoxLayout(self.survivor_host)
        self.survivor_layout.setContentsMargins(0, 1, 0, 1)
        self.survivor_layout.setSpacing(5)
        queue_layout.addWidget(self.survivor_host, 1)
        focus = QFrame()
        focus.setObjectName("focusLine")
        focus_layout = QHBoxLayout(focus)
        focus_layout.setContentsMargins(7, 4, 7, 4)
        self.focus_label = label("FOCUSED: SURVIVOR 1", 7, True)
        self.focus_grid_label = label("COORD B2", 7, True, PALETTE["muted"])
        focus_layout.addWidget(self.focus_label)
        focus_layout.addStretch()
        focus_layout.addWidget(self.focus_grid_label)
        queue_layout.addWidget(focus)
        layout.addWidget(queue, 7)
        return column

    def _center_column(self) -> QWidget:
        frame = card_frame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(7)
        header = QHBoxLayout()
        header.addWidget(label("LIVE 2D MAP", 10, True))
        active = label("TRACKING ACTIVE", 7, True, PALETTE["green"])
        active.setObjectName("trackingPill")
        header.addWidget(active)
        header.addStretch()
        self.target_label = label("TARGET: SURVIVOR S01 (FOCUSED)", 7, True, "#53688d")
        header.addWidget(self.target_label)
        layout.addLayout(header)
        details = QHBoxLayout()
        self.map_state_label = label("● SLAM PREVIEW ACTIVE    SIMULATED OCCUPANCY GRID · LOCAL ENU    DRONE TRACK", 6, True, PALETTE["green"])
        details.addWidget(self.map_state_label)
        details.addStretch()
        self.cell_label = label("MAPPED CELLS 115 / 180", 6, False, PALETTE["muted"])
        details.addWidget(self.cell_label)
        layout.addLayout(details)
        self.map_canvas = MapCanvas()
        self.map_canvas.waypoint_selected.connect(self.set_waypoint)
        layout.addWidget(self.map_canvas, 1)

        sensor = card_frame()
        sensor.setObjectName("sensorStrip")
        sensor_row = QVBoxLayout(sensor)
        sensor_row.setContentsMargins(8, 5, 8, 5)
        top = QHBoxLayout()
        top.addWidget(label("MAP / SENSOR STATUS", 8, True))
        top.addStretch()
        self.source_label = label("LOCAL ENU · SYNTHETIC FEED", 6, False, PALETTE["muted"])
        top.addWidget(self.source_label)
        sensor_row.addLayout(top)
        self.sensor_label = label("LIDAR · ACTIVE    SLAM · ACTIVE    VISION · ACTIVE    WIFI · CONNECTED    MAVLINK · CONNECTED", 7, True, PALETTE["green"])
        sensor_row.addWidget(self.sensor_label)
        layout.addWidget(sensor)

        coverage = card_frame()
        coverage.setObjectName("coverageStrip")
        row = QHBoxLayout(coverage)
        row.setContentsMargins(9, 6, 9, 6)
        left = QVBoxLayout()
        left.addWidget(label("MAP COVERAGE", 8, True, PALETTE["muted"]))
        self.coverage_progress = QProgressBar()
        self.coverage_progress.setRange(0, 100)
        self.coverage_progress.setTextVisible(False)
        self.coverage_progress.setFixedHeight(8)
        left.addWidget(self.coverage_progress)
        row.addLayout(left, 2)
        self.coverage_pct = label("64%", 9, True)
        row.addWidget(self.coverage_pct)
        row.addWidget(self._metric_divider())
        self.frame_metric = label("COORDINATE FRAME: LOCAL ENU", 9)
        row.addWidget(self.frame_metric, 2)
        row.addWidget(self._metric_divider())
        self.survivor_metric = label("SURVIVORS FOUND: 2 / 06", 9)
        row.addWidget(self.survivor_metric, 2)
        row.addWidget(self._metric_divider())
        self.mission_metric = label("MISSION TIME: 12:21", 9)
        row.addWidget(self.mission_metric, 2)
        layout.addWidget(coverage)
        return frame

    def _metric_divider(self) -> QFrame:
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setObjectName("divider")
        return divider

    def _right_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        status = card_frame()
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(9, 8, 9, 8)
        head = QHBoxLayout()
        head.addWidget(label("MISSION STATUS", 9, True))
        head.addStretch()
        self.auto_small = label("AUTONOMOUS", 6, True, PALETTE["green"])
        head.addWidget(self.auto_small)
        status_layout.addLayout(head)
        grid = QGridLayout()
        for col, text in enumerate(("PHASE", "SURVIVORS", "MAP COVERAGE", "COORDINATES")):
            grid.addWidget(label(text, 7, False, PALETTE["muted"]), col // 2 * 2, col % 2)
        self.phase_value = label("EXPLORING", 8, True)
        self.survivor_value = label("2 / 6", 8, True)
        self.coverage_value = label("64%", 8, True)
        self.coordinate_value = label("LOCAL ENU", 8, True)
        for col, value in enumerate((self.phase_value, self.survivor_value, self.coverage_value, self.coordinate_value)):
            grid.addWidget(value, col // 2 * 2 + 1, col % 2)
        status_layout.addLayout(grid)
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 100)
        self.status_progress.setTextVisible(False)
        self.status_progress.setFixedHeight(7)
        status_layout.addWidget(self.status_progress)
        layout.addWidget(status, 2)

        telem = card_frame()
        telem_layout = QVBoxLayout(telem)
        telem_layout.setContentsMargins(9, 8, 9, 8)
        head = QHBoxLayout()
        head.addWidget(label("TELEMETRY", 9, True))
        head.addStretch()
        head.addWidget(label("LOCAL ENU · 10 HZ SIM", 6, False, PALETTE["muted"]))
        telem_layout.addLayout(head)
        self.telemetry_grid = QGridLayout()
        self.telemetry_grid.setVerticalSpacing(4)
        self.telemetry_values: Dict[str, QLabel] = {}
        pairs = [("Battery", "battery"), ("Voltage", "voltage"), ("Current", "current"), ("Altitude", "altitude"), ("Mode", "mode"), ("Link", "link"), ("Quality", "quality"), ("Speed", "speed"), ("Heading", "heading"), ("Flight", "flight"), ("GPS", "gps"), ("Position", "position")]
        for i, (name, key) in enumerate(pairs):
            row, block = i // 2, i % 2
            self.telemetry_grid.addWidget(label(name, 7, False, PALETTE["muted"]), row, block * 2)
            value = label("--", 7, True)
            self.telemetry_values[key] = value
            self.telemetry_grid.addWidget(value, row, block * 2 + 1)
        telem_layout.addLayout(self.telemetry_grid)
        layout.addWidget(telem, 3)

        health = card_frame()
        health_layout = QVBoxLayout(health)
        health_layout.setContentsMargins(9, 8, 9, 8)
        head = QHBoxLayout()
        head.addWidget(label("COMPONENT STATUS", 9, True))
        head.addStretch()
        details = QPushButton("DETAILS")
        details.setObjectName("miniButton")
        details.clicked.connect(self.open_component_details)
        head.addWidget(details)
        head.addWidget(label("10 COMPONENTS", 6, False, PALETTE["muted"]))
        health_layout.addLayout(head)
        self.health_rows: Dict[str, QLabel] = {}
        self.component_names = (
            "Flight Controller", "Camera", "LiDAR", "SLAM / Localization", "Mapping Engine",
            "Vision AI", "Wi-Fi", "MAVLink", "Emergency System", "Data Plugin",
        )
        for name in self.component_names:
            row = QHBoxLayout()
            row.addWidget(label(name, 8))
            row.addStretch()
            value = label("READY", 6, True, PALETTE["green"])
            value.setObjectName("readyPill")
            self.health_rows[name] = value
            row.addWidget(value)
            health_layout.addLayout(row)
        layout.addWidget(health, 4)
        return column

    def _event_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("eventBar")
        frame.setFixedHeight(68)
        row = QHBoxLayout(frame)
        row.setContentsMargins(9, 7, 9, 7)
        events = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(label("EVENT LOG (CHRONOLOGICAL)", 8, True))
        top.addStretch()
        self.plugin_state = label("REAL-TIME MISSION STREAM", 6, False, PALETTE["muted"])
        top.addWidget(self.plugin_state)
        events.addLayout(top)
        self.event_one = label("", 7, False)
        self.event_two = label("", 7, False)
        events.addWidget(self.event_one)
        events.addWidget(self.event_two)
        row.addLayout(events, 1)
        abort = QPushButton("●  EMERGENCY ABORT\nRTL · LAND HERE")
        abort.setObjectName("abortButton")
        abort.setFixedSize(140, 54)
        abort.clicked.connect(self.emergency_abort)
        row.addWidget(abort)
        return frame

    def _apply_theme(self) -> None:
        if self.night:
            background, card, ink, line = "#101827", "#172337", "#eff6ff", "#2d405a"
        else:
            background, card, ink, line = PALETTE["canvas"], PALETTE["card"], PALETTE["ink"], PALETTE["line"]
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{background}; color:{ink}; font-family:'Segoe UI'; }}
            QFrame#header, QFrame#card, QFrame#eventBar {{ background:{card}; border:1px solid {line}; border-radius:4px; }}
            QFrame#sensorStrip, QFrame#coverageStrip {{ background:{card}; border:1px solid {line}; border-radius:3px; }}
            QPushButton {{ background:{card}; color:{ink}; border:1px solid {line}; border-radius:4px; padding:4px 10px; font: 8pt 'Segoe UI'; }}
            QPushButton:hover {{ border-color:#6f8fbd; background:#eef5ff; }}
            QPushButton#navTab {{ padding:3px 11px; }}
            QPushButton#navTab[active='true'] {{ background:#f4f8ff; border-color:#a8bdd9; font-weight:700; }}
            QPushButton#miniButton {{ padding:2px 5px; font: 7pt 'Segoe UI'; }}
            QLabel#modePill, QLabel#commPill {{ background:#e7fbf5; border:1px solid #9de7d4; border-radius:9px; padding:3px 8px; color:#087c67; }}
            QLabel#trackingPill {{ background:#e8fcf3; border:1px solid #8fe1bf; border-radius:3px; padding:2px 6px; }}
            QLabel#numberBadge {{ background:#f5f8fc; border:1px solid {line}; border-radius:3px; padding:2px 6px; }}
            QLabel#notice, QLabel#focusLine, QFrame#focusLine {{ background:#f7f9fc; border:1px solid {line}; border-radius:3px; padding:5px; }}
            QLabel#readyPill {{ background:#e6fbf2; border:1px solid #91e4c0; border-radius:3px; padding:2px 4px; }}
            QProgressBar {{ background:#e7edf5; border:0; border-radius:3px; }}
            QProgressBar::chunk {{ background:#1f304e; border-radius:3px; }}
            QPushButton#abortButton {{ background:#df2c2c; color:white; border:1px solid #b91919; font-weight:700; }}
            QPushButton#abortButton:hover {{ background:#bb1f29; }}
            QScrollArea {{ border:0; background:transparent; }}
            QSplitter::handle {{ background:{line}; width:5px; }}
            QFrame#divider {{ color:{line}; }}
        """)
        for name, button in self.tabs.items():
            button.setProperty("active", name == "Mission")
            button.style().unpolish(button)
            button.style().polish(button)
        self.map_canvas.night = self.night
        self.map_canvas.update()

    def toggle_night(self) -> None:
        self.night = not self.night
        self.night_button.setText("DAY" if self.night else "NIGHT")
        self._apply_theme()
        self.log_event(f"[UI] {'Night' if self.night else 'Day'} operator theme enabled.")

    def select_tab(self, name: str) -> None:
        for tab, button in self.tabs.items():
            button.setProperty("active", tab == name)
            button.style().unpolish(button)
            button.style().polish(button)
        if name == "Map":
            self.map_canvas.setFocus()
            self.log_event("[NAV] Map view selected. Click map to place a safe local waypoint.")
        elif name == "Survivors":
            self.survivor_host.setFocus()
            self.log_event("[NAV] Survivor queue selected. Choose a row to focus the map target.")
        else:
            self.log_event("[NAV] Mission overview selected.")

    def focus_camera(self) -> None:
        self.camera.setFocus()
        self.log_event("[CAM] Pilot camera highlighted. Click feed to switch optical / thermal mode.")

    def open_pilot_view(self) -> None:
        if self.pilot_window and self.pilot_window.isVisible():
            self.pilot_window.raise_()
            self.pilot_window.activateWindow()
            return
        self.pilot_window = PilotViewDialog(self.camera.mode, self.camera.zoom, self)
        self.pilot_window.mode_changed.connect(self.on_camera_mode_changed)
        self.pilot_window.zoom_changed.connect(self.change_camera_zoom)
        self.pilot_window.destroyed.connect(lambda: setattr(self, "pilot_window", None))
        self.pilot_window.show()
        self.log_event("[CAM] Pilot View opened in simulation mode.")

    def on_camera_mode_changed(self, mode: str) -> None:
        self.camera.set_mode(mode)
        if self.pilot_window and self.pilot_window.isVisible():
            self.pilot_window.sync_mode(mode)
        self.camera_live.setText(f"LIVE · {mode}")
        self.log_event(f"[CAM] Sensor mode switched to {mode}.")

    def change_camera_zoom(self, value: int) -> None:
        self.camera.zoom = value
        self.camera.update()
        self.zoom_label.setText(f"{value}%")
        if self.pilot_window and self.pilot_window.isVisible():
            self.pilot_window.sync_zoom(value)
        self.camera.update()

    def open_preflight(self) -> None:
        dialog = PreFlightDialog(self.manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.frame = default_frame()
            self.log_event(f"[DATA] Source selected: {self.manager.source} ({self.manager.source_hint}).")
            self._poll_data()

    def open_component_details(self) -> None:
        dialog = ComponentDetailsDialog(self.frame, self.last_source_status, self)
        dialog.exec()

    def add_sim_detection(self) -> None:
        survivors = self.frame.get("survivors", [])
        for item in survivors:
            if item.get("status") == "searching":
                n = int(str(item.get("id", "S03"))[1:])
                item.update({"status": "found", "x": 3.0 + n * 0.85, "y": 2.0 + n * 0.62, "confidence": 82 + n})
                self.frame["target"] = item["id"]
                self.log_event(f"[VISION] {item['id']} localized at Grid {item['grid']} (simulation).")
                self._render_frame(force_survivors=True)
                return
        self.log_event("[VISION] All six survivor slots are already localized.")

    def focus_survivor(self, survivor_id: str) -> None:
        self.frame["target"] = survivor_id
        self.log_event(f"[NAV] Target focus updated to survivor {survivor_id}.")
        self._render_frame()

    def set_waypoint(self, x: float, y: float) -> None:
        self.log_event(f"[NAV] Local waypoint staged at ENU {x:.1f}E / {y:.1f}N. No vehicle command sent.")

    def emergency_abort(self) -> None:
        answer = QMessageBox.question(self, "Emergency abort", "Declare an emergency abort in this GCS session?\n\nThe local simulation will change to RTL / LAND. No external vehicle command is sent by this desktop preview.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.frame["mode"] = "RTL / LAND"
            self.frame["phase"] = "ABORTED"
            self.log_event("[ALERT] EMERGENCY ABORT acknowledged. Local session is in RTL / LAND.")
            self._render_frame()

    def _poll_data(self) -> None:
        result = self.manager.poll()
        self.last_source_status = result.status
        if result.frame:
            self.frame = deep_merge(self.frame, result.frame)
        self.plugin_state.setText(f"{self.manager.source.upper()} · {result.status} · {result.detail}".upper()[:105])
        self._render_frame()

    def _render_frame(self, force_survivors: bool = False) -> None:
        frame = self.frame
        seconds = int(frame.get("mission_seconds", 0))
        minutes, remainder = divmod(seconds, 60)
        mode = str(frame.get("mode", "AUTONOMOUS"))
        self.mode_pill.setText(f"● {mode}")
        self.auto_small.setText(mode)
        self.timer_label.setText(f"TIMER: {minutes:02}:{remainder:02} / 30:00")
        telemetry = frame.get("telemetry", {})
        quality = telemetry.get("quality", 0)
        self.comm_label.setText(f"COMM: {'CONNECTED' if self.last_source_status != 'ERROR' else 'WAITING'} · {quality}%")
        self.phase_value.setText(str(frame.get("phase", "EXPLORING")))
        survivors = frame.get("survivors", [])
        found = sum(1 for item in survivors if item.get("status") == "found")
        coverage = int(frame.get("coverage", 0))
        self.survivor_value.setText(f"{found} / {len(survivors)}")
        self.coverage_value.setText(f"{coverage}%")
        self.coordinate_value.setText("LOCAL ENU")
        self.status_progress.setValue(coverage)
        self.target_label.setText(f"TARGET: SURVIVOR {frame.get('target', 'S01')} (FOCUSED)")
        self.cell_label.setText(f"MAPPED CELLS {round(coverage * 1.8):03d} / 180")
        self.source_label.setText(f"LOCAL ENU · {frame.get('source_label', 'SYNTHETIC FEED')}")
        sensors = frame.get("sensors", {})
        self.sensor_label.setText("    ".join(f"{name.upper()} · {state}" for name, state in sensors.items()))
        self.coverage_progress.setValue(coverage)
        self.coverage_pct.setText(f"{coverage}%")
        self.frame_metric.setText("COORDINATE FRAME: LOCAL ENU")
        self.survivor_metric.setText(f"SURVIVORS FOUND: {found} / {len(survivors):02d}")
        self.mission_metric.setText(f"MISSION TIME: {minutes:02}:{remainder:02}")
        self.people_label.setText(f"{found:02d}")
        focused = next((item for item in survivors if str(item.get("id")) == str(frame.get("target", "S01"))), None)
        if focused:
            focus_number = str(focused.get("id", "S01")).lstrip("S").lstrip("0") or "0"
            self.focus_label.setText(f"FOCUSED: SURVIVOR {focus_number}")
            self.focus_grid_label.setText(f"COORD {focused.get('grid', '—')}")
        drone = frame.get("drone", {})
        values = {
            "battery": f"{telemetry.get('battery', '--')}%", "voltage": f"{telemetry.get('voltage', '--')} V",
            "current": f"{telemetry.get('current', '--')} A", "altitude": f"{drone.get('altitude', '--')} m",
            "mode": mode, "link": f"{telemetry.get('link_ms', '--')} ms", "quality": f"{quality}%",
            "speed": f"{drone.get('speed', '--')} m/s", "heading": f"{drone.get('heading', '--')}°",
            "flight": f"{minutes:02}:{remainder:02}", "gps": "OPT_FLOW", "position": "OK",
        }
        for key, value in values.items():
            self.telemetry_values[key].setText(value)
        health = frame.get("health", {})
        sensors = frame.get("sensors", {})
        explicit_components = frame.get("components", {})
        simulation_only = self.manager.source == "Simulation" and not explicit_components
        fallback_status = "SIMULATED" if simulation_only else "WAITING"
        component_values = {
            "Flight Controller": explicit_components.get("Flight Controller", fallback_status if simulation_only else health.get("Flight Controller", "WAITING")),
            "Camera": explicit_components.get("Camera", fallback_status if simulation_only else health.get("Camera Sensor", "WAITING")),
            "LiDAR": explicit_components.get("LiDAR", fallback_status if simulation_only else sensors.get("lidar", "WAITING")),
            "SLAM / Localization": explicit_components.get("SLAM / Localization", fallback_status if simulation_only else health.get("3D Localization EKF", sensors.get("slam", "WAITING"))),
            "Mapping Engine": explicit_components.get("Mapping Engine", fallback_status if simulation_only else health.get("Mapping Engine", "WAITING")),
            "Vision AI": explicit_components.get("Vision AI", fallback_status if simulation_only else health.get("Survivor AI", sensors.get("vision", "WAITING"))),
            "Wi-Fi": explicit_components.get("Wi-Fi", fallback_status if simulation_only else sensors.get("wifi", "WAITING")),
            "MAVLink": explicit_components.get("MAVLink", fallback_status if simulation_only else sensors.get("mavlink", "WAITING")),
            "Emergency System": explicit_components.get("Emergency System", fallback_status if simulation_only else health.get("Emergency System", "WAITING")),
            "Data Plugin": explicit_components.get("Data Plugin", self.last_source_status),
        }
        for name, widget in self.health_rows.items():
            value = str(component_values.get(name, "WAITING")).upper()
            widget.setText(value)
            if value in {"READY", "ACTIVE", "CONNECTED", "NOMINAL"}:
                color, background, border = PALETTE["green"], "#e6fbf2", "#91e4c0"
            elif value in {"ERROR", "OFFLINE", "DISCONNECTED", "FAULT"}:
                color, background, border = "#c32929", "#fff0f0", "#efb1b1"
            else:
                color, background, border = "#b77900", "#fff8e6", "#f0d18a"
            widget.setStyleSheet(f"color:{color}; background:{background}; border:1px solid {border}; border-radius:3px; padding:2px 4px;")
        events = frame.get("events", [])
        if events:
            self.event_one.setText(events[-1])
            self.event_two.setText(events[-2] if len(events) > 1 else "")
        signature = repr(survivors) + str(frame.get("target"))
        if force_survivors or signature != self.last_survivor_signature:
            self.last_survivor_signature = signature
            self._build_survivors(survivors)
        self.map_canvas.set_frame(frame)

    def _build_survivors(self, survivors: Iterable[Dict[str, Any]]) -> None:
        while self.survivor_layout.count():
            item = self.survivor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        focused_id = str(self.frame.get("target", "S01"))
        for survivor in survivors:
            found = survivor.get("status") == "found"
            survivor_id = str(survivor.get("id", "—"))
            survivor_number = survivor_id.lstrip("S") or "—"
            focused = survivor_id == focused_id
            card = QFrame()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet(
                f"background:{'#ffffff' if found else '#f7f9fc'}; "
                f"border:{2 if focused else 1}px solid {'#14b8c4' if focused else PALETTE['line']}; "
                f"border-left:3px solid {'#00a67a' if found else '#ccd6e3'}; border-radius:3px;"
            )
            card.mousePressEvent = lambda event, sid=survivor.get("id", "S01"): self.focus_survivor(str(sid))  # type: ignore[method-assign]
            row = QVBoxLayout(card)
            row.setContentsMargins(7, 5, 7, 4)
            row.setSpacing(3)
            top = QHBoxLayout()
            top.setSpacing(4)
            top.addWidget(label(f"SURVIVOR {survivor_number}", 8, True, PALETTE["ink"] if found else PALETTE["muted"]))
            top.addStretch()
            status = label("FOUND" if found else "SEARCHING", 6, True, PALETTE["green"] if found else PALETTE["muted"])
            status.setStyleSheet(
                f"color:{PALETTE['green'] if found else PALETTE['muted']}; "
                f"background:{'#e6fbf2' if found else '#f7f9fc'}; "
                f"border:1px solid {'#91e4c0' if found else '#c8d3e1'}; border-radius:3px; padding:2px 5px;"
            )
            top.addWidget(status)
            row.addLayout(top)
            bottom = QHBoxLayout()
            bottom.addWidget(label(f"COORD: {survivor.get('grid', '—')}", 7, False, PALETTE["ink"] if found else PALETTE["muted"]))
            bottom.addStretch()
            confidence = f"{survivor.get('confidence', 0)}% CONFIDENCE" if found else "— CONFIDENCE"
            bottom.addWidget(label(confidence, 6, False, PALETTE["muted"]))
            row.addLayout(bottom)
            self.survivor_layout.addWidget(card)
        self.survivor_layout.addStretch()

    def log_event(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        events = self.frame.setdefault("events", [])
        events.append(f"[{timestamp}]  {message}")
        self._render_frame()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NIDAR Rescue GCS")
    window = NidarRescueGCS()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
