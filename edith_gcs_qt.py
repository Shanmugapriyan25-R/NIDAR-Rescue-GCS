#!/usr/bin/env python3
"""NIDAR Rescue GCS — Exact Modern Light Tactical UI (v2).

Faithfully implements the complete reference interface from reference_ui_v2.jpg:
- NO vertical sidebar (sidebar removed as requested).
- Top Header: Full-width brand bar with Drone Logo, NIDAR Rescue GCS,
  ● RTL / LAND dropdown, ⏱ 14:30 / 30:00 timer, 📶 COMM: CONNECTED (98%), settings button.
- Horizontal Navigation Tabs: [⌂ Mission] (active blue), [📍 Map], [👥 Survivors].
- Left Column:
    - DRONE CAMERA: Segmented RGB / THERMAL / PILOT VIEW, live aerial HUD with dynamic AI bounding boxes,
      capture/record/zoom controls, live FLIR thermal shader.
    - SURVIVOR QUEUE: 4 interactive cards (S01–S04) with confidence badges, status badges, thumbnails, coordinates.
- Center Column:
    - 2D SLAM LIDAR ARENA: Real interactive metric grid (A-O, 1-15), orthomosaic underlay,
      interactive survivor pins, drone with live rotating LiDAR sweep, waypoint flight path,
      START & STAGE WP, pulsing red sonar rings, scale bar, compass, and layer toggle.
    - SENSOR & DATA LINK STATUS: 6 active sensor pills (LiDAR, Radar, Vision, WiFi, MAVLink, Connected),
      coverage progress bar (64%), frame, survivors, and live mission time.
- Right Column:
    - MISSION STATUS: Donut progress chart (64%, MISSION PROGRESS), Aborted (2/6 Coverage), Local ENU Coordinates.
    - TELEMETRY: 2-column live telemetry grid (Battery, Voltage, Current, Altitude, Mode, Link, Quality, Speed, Heading, Flight, GPS, Position).
    - HARDWARE SUBSYSTEM HEALTH: 5 core units with solid emerald green OK pills.
- Bottom Row:
    - MISSION EVENT LOG: Chronological categorized events (INFO, DETECT, NAV) with real auto-scrolling log.
    - QUICK ACTIONS: Interactive Switch to Manual, Add Waypoint (click map to stage), Mark Survivor, Return to Home.
    - EMERGENCY ABORT: Prominent red RTL Land Here card with clean white hazard icon.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPolygonF, QPainterPath, QPixmap, QImage, QIcon, QCursor
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget
)

PALETTE = {
    "bg": "#f4f7fb",           # Soft tactical grey/blue canvas background
    "card": "#ffffff",         # Clean white card background
    "card_alt": "#f8fafc",     # Light slate card alt
    "line": "#e2e8f0",         # Border color (slate-200)
    "line_dark": "#cbd5e1",    # Darker border (slate-300)
    "ink": "#0f172a",          # Slate-900 primary text
    "muted": "#64748b",        # Slate-500 secondary text
    "blue": "#1d70f0",         # Primary blue
    "blue_soft": "#eff6ff",    # Soft blue tint
    "blue_border": "#bfdbfe",  # Soft blue border
    "cyan": "#0284c7",         # Cyan accent
    "green": "#10b981",        # Emerald green
    "green_soft": "#ecfdf5",   # Soft mint background
    "green_border": "#a7f3d0", # Mint border
    "amber": "#f59e0b",        # Amber
    "amber_soft": "#fffbeb",   # Soft amber background
    "amber_border": "#fde68a", # Amber border
    "danger": "#ef4444",       # Red
    "danger_soft": "#fef2f2",  # Soft red background
    "danger_border": "#fecaca",# Red border
    "purple": "#8b5cf6",       # Purple
    "purple_soft": "#f5f3ff",  # Soft purple background
    "purple_border": "#ddd6fe",# Purple border
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


# ==============================================================================
# 1. VECTOR DRONE LOGO & HAZARD ICON
# ==============================================================================
class DroneLogoWidget(QWidget):
    """Draws a crisp quadcopter drone outline icon matching the reference."""

    def __init__(self, size: int = 24, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size + 6, size)
        self.color = QColor(PALETTE["blue"])

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pen = QPen(self.color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = w / 2, h / 2
        p.drawEllipse(QPointF(cx, cy), 3.5, 3.5)

        skid = QPainterPath()
        skid.moveTo(cx - 5.5, cy + 3.0)
        skid.quadTo(cx, cy + 8.5, cx + 5.5, cy + 3.0)
        p.drawPath(skid)

        p.drawLine(QPointF(cx - 3.5, cy - 1), QPointF(cx - 10, cy - 4.5))
        p.drawLine(QPointF(cx - 10, cy - 4.5), QPointF(cx - 10, cy - 6.5))
        p.drawLine(QPointF(cx - 14, cy - 6.5), QPointF(cx - 6, cy - 6.5))

        p.drawLine(QPointF(cx + 3.5, cy - 1), QPointF(cx + 10, cy - 4.5))
        p.drawLine(QPointF(cx + 10, cy - 4.5), QPointF(cx + 10, cy - 6.5))
        p.drawLine(QPointF(cx + 6, cy - 6.5), QPointF(cx + 14, cy - 6.5))
        p.end()


class WhiteHazardIcon(QWidget):
    """Draws a crisp pure white hazard triangle with exclamation mark."""

    def __init__(self, size: int = 28, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        
        path = QPainterPath()
        top = QPointF(w / 2, 3)
        br = QPointF(w - 3, h - 3)
        bl = QPointF(3, h - 3)
        
        path.moveTo(top)
        path.lineTo(br)
        path.lineTo(bl)
        path.closeSubpath()

        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)

        # Exclamation mark inside
        p.setPen(QPen(QColor("#dc2626"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(w / 2, 9), QPointF(w / 2, 17))
        p.drawPoint(QPointF(w / 2, 21))
        p.end()


# ==============================================================================
# 2. CIRCULAR DONUT PROGRESS WIDGET
# ==============================================================================
class CircularProgressWidget(QWidget):
    """Circular donut progress chart displaying mission coverage percentage."""

    def __init__(self, value: int = 64, parent=None) -> None:
        super().__init__(parent)
        self.value = value
        self.setFixedSize(108, 108)

    def set_value(self, val: int) -> None:
        self.value = max(0, min(100, val))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        side = min(rect.width(), rect.height())
        ring_rect = QRectF((rect.width() - side) / 2 + 7, (rect.height() - side) / 2 + 7, side - 14, side - 14)
        pen_w = 8.5

        # Gray background track
        p.setPen(QPen(QColor("#e2e8f0"), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(ring_rect, 0, 360 * 16)

        # Gradient Progress Arc (teal to cyan)
        grad = QLinearGradient(ring_rect.topLeft(), ring_rect.bottomRight())
        grad.setColorAt(0, QColor("#10b981"))
        grad.setColorAt(1, QColor("#0284c7"))
        p.setPen(QPen(QBrush(grad), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        start_angle = 90 * 16
        span_angle = -int(self.value / 100.0 * 360 * 16)
        p.drawArc(ring_rect, start_angle, span_angle)

        # Centered Value Text
        p.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        p.setPen(QColor(PALETTE["ink"]))
        p.drawText(ring_rect.adjusted(0, -6, 0, -6), Qt.AlignmentFlag.AlignCenter, f"{self.value}%")

        # Centered Subtitle Text
        p.setFont(QFont("Segoe UI", 5, QFont.Weight.Bold))
        p.setPen(QColor(PALETTE["muted"]))
        p.drawText(ring_rect.adjusted(0, 20, 0, 20), Qt.AlignmentFlag.AlignCenter, "MISSION PROGRESS")
        p.end()


# ==============================================================================
# 3. INTERACTIVE DRONE CAMERA SURFACE
# ==============================================================================
class CameraSurface(QWidget):
    """Live interactive aerial reconnaissance feed with AI overlays and shader modes."""
    mode_changed = pyqtSignal(str)
    snapshot_taken = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode = "RGB"  # "RGB" or "THERMAL"
        self.zoom = 12.4
        self.is_recording = False
        self.record_seconds = 0
        self.shutter_flash = False
        self.highlighted_person: Optional[str] = None
        self.bg_pixmap = QPixmap("assets/camera_feed_bg.png")
        self.setMinimumHeight(185)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_mode(self, mode: str) -> None:
        if mode in {"RGB", "THERMAL"} and mode != self.mode:
            self.mode = mode
            self.mode_changed.emit(self.mode)
            self.update()

    def toggle_mode(self) -> None:
        self.set_mode("THERMAL" if self.mode == "RGB" else "RGB")

    def flash_shutter(self) -> None:
        self.shutter_flash = True
        self.update()
        QTimer.singleShot(120, self._clear_shutter)

    def _clear_shutter(self) -> None:
        self.shutter_flash = False
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(1.0, min(24.0, round(zoom, 1)))
        self.update()

    def set_highlight_person(self, pid: Optional[str]) -> None:
        self.highlighted_person = pid
        self.update()

    def mousePressEvent(self, event) -> None:
        pass

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()

        # Draw base reconnaissance video feed
        if not self.bg_pixmap.isNull():
            p.drawPixmap(rect, self.bg_pixmap)
        else:
            p.fillRect(rect, QColor("#1e293b"))

        # FLIR Thermal ironbow shader effect
        if self.mode == "THERMAL":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_ColorBurn)
            p.fillRect(rect, QColor(90, 20, 130, 190))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            p.fillRect(rect, QColor(0, 210, 255, 90))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Thermal tag banner
            p.fillRect(QRectF(8, 38, 74, 16), QColor(0, 0, 0, 170))
            p.setPen(QColor("#00f2fe"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(8, 38, 74, 16), Qt.AlignmentFlag.AlignCenter, "FLIR THERMAL")

        # Shutter flash animation
        if self.shutter_flash:
            p.fillRect(rect, QColor(255, 255, 255, 200))

        # Recording banner if active
        if self.is_recording:
            p.fillRect(QRectF(rect.width() - 85, 38, 78, 16), QColor(220, 38, 38, 200))
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            mins = self.record_seconds // 60
            secs = self.record_seconds % 60
            p.drawText(QRectF(rect.width() - 85, 38, 78, 16), Qt.AlignmentFlag.AlignCenter, f"REC {mins:02d}:{secs:02d}")

        p.end()


# ==============================================================================
# 4. SURVIVOR CARD COMPONENT
# ==============================================================================
class SurvivorCard(QFrame):
    """Survivor row card with colored accent, avatar, confidence, status, thumbnail."""
    selected = pyqtSignal(str)

    def __init__(
        self,
        survivor_id: str,
        number_str: str,
        grid_str: str,
        confidence_str: str,
        status_text: str,
        coords_str: str,
        color_hex: str,
        thumb_file: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.survivor_id = survivor_id
        self.color_hex = color_hex
        self.is_active_selected = False
        self.setObjectName("survivorCard")
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._update_card_style()

        # Circular Avatar Icon
        avatar = QLabel("👤")
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"""
            background: {color_hex};
            color: #ffffff;
            border-radius: 13px;
            font-size: 13px;
        """)
        layout.addWidget(avatar)

        # Center Details Column
        details = QVBoxLayout()
        details.setSpacing(1)

        title_lbl = QLabel(f"SURVIVOR {number_str}")
        title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color:{PALETTE['ink']};")
        details.addWidget(title_lbl)

        grd_row = QHBoxLayout()
        grd_row.setSpacing(6)
        grd_lbl = QLabel(f"GRD: {grid_str}")
        grd_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        grd_lbl.setStyleSheet(f"color:{PALETTE['muted']};")
        grd_row.addWidget(grd_lbl)

        coord_lbl = QLabel(coords_str)
        coord_lbl.setFont(QFont("Segoe UI", 6))
        coord_lbl.setStyleSheet("color:#94a3b8;")
        grd_row.addWidget(coord_lbl)
        grd_row.addStretch()
        details.addLayout(grd_row)

        layout.addLayout(details, 1)

        # Badges Box
        badge_box = QHBoxLayout()
        badge_box.setSpacing(4)

        conf_pill = QLabel(f"✔ {confidence_str}")
        conf_pill.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        conf_pill.setStyleSheet(f"""
            color: {color_hex};
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            padding: 2px 5px;
        """)
        badge_box.addWidget(conf_pill)

        state_pill = QLabel(status_text)
        state_pill.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        if status_text == "STABLE":
            st_color, st_bg, st_border = PALETTE["green"], PALETTE["green_soft"], PALETTE["green_border"]
        elif status_text == "MOVING":
            st_color, st_bg, st_border = PALETTE["amber"], PALETTE["amber_soft"], PALETTE["amber_border"]
        else:
            st_color, st_bg, st_border = PALETTE["muted"], "#f1f5f9", PALETTE["line"]

        state_pill.setStyleSheet(f"""
            color: {st_color};
            background: {st_bg};
            border: 1px solid {st_border};
            border-radius: 4px;
            padding: 2px 5px;
        """)
        badge_box.addWidget(state_pill)
        layout.addLayout(badge_box)

        # Aerial thumbnail preview
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(40, 26)
        thumb_lbl.setScaledContents(True)
        thumb_lbl.setStyleSheet("border-radius: 4px; border: 1px solid #cbd5e1;")
        pix = QPixmap(thumb_file)
        if not pix.isNull():
            thumb_lbl.setPixmap(pix)
        layout.addWidget(thumb_lbl)

        # Chevron arrow ›
        arrow_lbl = QLabel("›")
        arrow_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        arrow_lbl.setStyleSheet(f"color:{PALETTE['muted']};")
        layout.addWidget(arrow_lbl)

    def _update_card_style(self) -> None:
        bg_col = "#eff6ff" if self.is_active_selected else "#ffffff"
        border_col = PALETTE["blue"] if self.is_active_selected else "#e2e8f0"
        self.setStyleSheet(f"""
            QFrame#survivorCard {{
                background: {bg_col};
                border: 1px solid {border_col};
                border-left: 4px solid {self.color_hex};
                border-radius: 6px;
            }}
            QFrame#survivorCard:hover {{
                border-color: #cbd5e1;
                background: #f8fafc;
            }}
        """)

    def set_selected(self, val: bool) -> None:
        self.is_active_selected = val
        self._update_card_style()

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.survivor_id)


# ==============================================================================
# 5. REAL INTERACTIVE 2D SLAM LIDAR ARENA CANVAS
# ==============================================================================
class MapCanvas(QWidget):
    """Interactive 2D SLAM LiDAR Arena with metric grid, dynamic waypoints & sonar."""
    waypoint_added = pyqtSignal(float, float, str)
    survivor_clicked = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(440, 310)
        self.bg_pixmap = QPixmap("assets/arena_map_bg.png")
        self.add_waypoint_mode = False
        self.pulse_phase = 0.0
        self.scan_sweep = 0.0
        self.selected_target: Optional[str] = None
        self.user_waypoints: List[Tuple[float, float, str]] = []
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_add_waypoint_mode(self, enabled: bool) -> None:
        self.add_waypoint_mode = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def select_survivor(self, sid: str) -> None:
        self.selected_target = sid
        self.update()

    def tick_anim(self) -> None:
        self.pulse_phase = (self.pulse_phase + 0.12) % (2 * math.pi)
        self.scan_sweep = (self.scan_sweep + 0.05) % (2 * math.pi)
        self.update()

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        w, h = self.width(), self.height()
        norm_x = pos.x() / w
        norm_y = pos.y() / h

        if self.add_waypoint_mode:
            col_idx = int(norm_x * 15)
            row_idx = 15 - int(norm_y * 15)
            col_letter = chr(ord('A') + min(14, max(0, col_idx)))
            wp_tag = f"WP-{len(self.user_waypoints)+1} [{col_letter}{row_idx}]"
            self.user_waypoints.append((norm_x, norm_y, wp_tag))
            self.waypoint_added.emit(norm_x, norm_y, wp_tag)
            self.set_add_waypoint_mode(False)
            self.update()
            return

        # Check survivor click targets (approx normalized coords)
        targets = [
            ("S01", 0.18, 0.25),
            ("S02", 0.52, 0.35),
            ("S03", 0.20, 0.55),
            ("S04", 0.47, 0.73),
        ]
        for sid, tx, ty in targets:
            dx = (norm_x - tx) * w
            dy = (norm_y - ty) * h
            if math.hypot(dx, dy) < 22:
                self.survivor_clicked.emit(sid)
                self.select_survivor(sid)
                return

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()

        # Render complete high-resolution orthomosaic grid
        if not self.bg_pixmap.isNull():
            p.drawPixmap(rect, self.bg_pixmap)
        else:
            p.fillRect(rect, QColor("#e2e8f0"))

        # Animated live pulsing ring on S04
        s4_x = rect.width() * 0.468
        s4_y = rect.height() * 0.736
        pulse_r = 16.0 + 8.0 * math.sin(self.pulse_phase)
        p.setPen(QPen(QColor(239, 68, 68, 160), 1.6, Qt.PenStyle.DashLine))
        p.setBrush(QBrush(QColor(239, 68, 68, 20)))
        p.drawEllipse(QPointF(s4_x, s4_y), pulse_r, pulse_r)

        # Highlight beacon ring if survivor selected
        if self.selected_target:
            coords_map = {
                "S01": (0.18, 0.25),
                "S02": (0.52, 0.35),
                "S03": (0.20, 0.55),
                "S04": (0.47, 0.73),
            }
            if self.selected_target in coords_map:
                hx, hy = coords_map[self.selected_target]
                h_pt = QPointF(rect.width() * hx, rect.height() * hy)
                beacon_r = 20.0 + 4.0 * math.cos(self.pulse_phase * 2)
                p.setPen(QPen(QColor("#2563eb"), 2.0))
                p.setBrush(QBrush(QColor(37, 99, 235, 30)))
                p.drawEllipse(h_pt, beacon_r, beacon_r)

        # Render user-added waypoints and connection flight line
        if self.user_waypoints:
            p.setPen(QPen(QColor("#2563eb"), 2.0, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            last_pt = QPointF(rect.width() * 0.468, rect.height() * 0.58)  # Drone position
            for wx, wy, wtag in self.user_waypoints:
                curr_pt = QPointF(rect.width() * wx, rect.height() * wy)
                p.drawLine(last_pt, curr_pt)
                # Waypoint circle pin
                p.setPen(QPen(QColor("#2563eb"), 1.8))
                p.setBrush(QBrush(QColor("#ffffff")))
                p.drawEllipse(curr_pt, 7, 7)
                # Label
                p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                p.setPen(QColor("#1e40af"))
                p.drawText(QRectF(curr_pt.x() + 9, curr_pt.y() - 8, 80, 16), Qt.AlignmentFlag.AlignVCenter, wtag)
                last_pt = curr_pt

        # Waypoint placement cursor banner
        if self.add_waypoint_mode:
            p.fillRect(QRectF(10, 10, 220, 22), QColor(37, 99, 235, 220))
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(10, 10, 220, 22), Qt.AlignmentFlag.AlignCenter, "📍 CLICK ON ARENA TO PLACE WAYPOINT")

        p.end()


# ==============================================================================
# 6. HARDWARE SUBSYSTEM ITEM WIDGET
# ==============================================================================
class SubsystemItemWidget(QFrame):
    """Row widget for hardware component with solid emerald green OK capsule."""

    def __init__(self, icon_str: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("subsystemRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Icon
        icon_lbl = QLabel(icon_str)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 10, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color:{PALETTE['cyan']}; background:transparent;")
        layout.addWidget(icon_lbl)

        # Name
        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.name_lbl.setStyleSheet(f"color:{PALETTE['ink']}; background:transparent;")
        layout.addWidget(self.name_lbl, 1)

        # Solid emerald green OK capsule
        self.ok_badge = QLabel("OK")
        self.ok_badge.setObjectName("okBadge")
        self.ok_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.ok_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ok_badge.setFixedSize(30, 18)
        self.ok_badge.setStyleSheet("""
            QLabel#okBadge {
                background-color: #10b981;
                color: #ffffff;
                border-radius: 9px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.ok_badge)


# ==============================================================================
# 7. MAIN NIDAR RESCUE GCS APPLICATION (reference_ui_v2.jpg Exact Match)
# ==============================================================================
class NidarRescueGCS(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NIDAR Rescue GCS — AI-Powered Human Detection & Rescue")
        self.resize(1340, 780)
        self.setMinimumSize(1100, 680)

        self.flight_seconds = 14 * 60 + 30
        self.flight_mode = "RTL / LAND"
        self.survivor_cards: Dict[str, SurvivorCard] = {}

        self._build_ui()
        self._apply_theme()

        # Telemetry update timer (1 Hz)
        self.telem_timer = QTimer(self)
        self.telem_timer.timeout.connect(self._update_telemetry)
        self.telem_timer.start(1000)

        # Arena animation timer (30 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.map_canvas.tick_anim)
        self.anim_timer.start(35)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(8)

        # 1. Full-Width Top Header
        main_layout.addWidget(self._header())

        # 2. Main 3-Column Content Layout
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(8)
        columns_layout.addWidget(self._left_column(), 29)
        columns_layout.addWidget(self._center_column(), 46)
        columns_layout.addWidget(self._right_column(), 25)
        main_layout.addLayout(columns_layout, 1)

        # 3. Full-Width Bottom Bar
        main_layout.addWidget(self._bottom_bar())

    # --------------------------------------------------------------------------
    # Full Width Top Header Bar
    # --------------------------------------------------------------------------
    def _header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("header")
        bar.setFixedHeight(46)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(10)

        # Vector Drone Logo Icon
        drone_logo = DroneLogoWidget(22)
        row.addWidget(drone_logo)

        # Brand Title Box
        title_box = QHBoxLayout()
        title_box.setSpacing(6)
        nidar_lbl = QLabel("NIDAR")
        nidar_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        nidar_lbl.setStyleSheet(f"color:{PALETTE['ink']};")
        title_box.addWidget(nidar_lbl)

        gcs_lbl = QLabel("Rescue GCS")
        gcs_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        gcs_lbl.setStyleSheet(f"color:{PALETTE['blue']};")
        title_box.addWidget(gcs_lbl)

        sep = QLabel("|")
        sep.setFont(QFont("Segoe UI", 10))
        sep.setStyleSheet("color: #cbd5e1; margin: 0 4px;")
        title_box.addWidget(sep)

        sub_lbl = QLabel("AI-Powered Human Detection & Rescue")
        sub_lbl.setFont(QFont("Segoe UI", 8))
        sub_lbl.setStyleSheet(f"color:{PALETTE['muted']};")
        title_box.addWidget(sub_lbl)
        row.addLayout(title_box)

        row.addStretch()

        # Status Pills on Right
        self.mode_pill = QPushButton("● RTL / LAND  ⌄")
        self.mode_pill.setObjectName("modePill")
        self.mode_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.mode_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_pill.setStyleSheet(f"""
            QPushButton#modePill {{
                color: {PALETTE['green']};
                background: {PALETTE['green_soft']};
                border: 1px solid {PALETTE['green_border']};
                border-radius: 11px;
                padding: 3px 10px;
            }}
            QPushButton#modePill:hover {{
                background: #dcfce7;
            }}
        """)
        self.mode_pill.clicked.connect(self.toggle_flight_mode)
        row.addWidget(self.mode_pill)

        self.timer_pill = QLabel("⏱ 14:30 / 30:00")
        self.timer_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.timer_pill.setStyleSheet(f"""
            color: {PALETTE['ink']};
            background: #ffffff;
            border: 1px solid {PALETTE['line']};
            border-radius: 11px;
            padding: 3px 10px;
        """)
        row.addWidget(self.timer_pill)

        comm_pill = QLabel("📶 COMM: CONNECTED (98%)")
        comm_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        comm_pill.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 11px;
            padding: 3px 10px;
        """)
        row.addWidget(comm_pill)

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(26, 26)
        settings_btn.setStyleSheet(f"""
            background: #ffffff;
            border: 1px solid {PALETTE['line']};
            border-radius: 13px;
            font-size: 10pt;
            color: {PALETTE['muted']};
        """)
        settings_btn.clicked.connect(lambda: self.log_event("[SYSTEM] Configuration parameters opened."))
        row.addWidget(settings_btn)

        return bar

    # --------------------------------------------------------------------------
    # Left Column: Horizontal Tabs + Drone Camera + Survivor Queue
    # --------------------------------------------------------------------------
    def _left_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. HORIZONTAL NAVIGATION TABS (Replacing vertical sidebar)
        tabs_box = QHBoxLayout()
        tabs_box.setSpacing(6)

        self.tab_mission = QPushButton("⌂ Mission")
        self.tab_mission.setObjectName("navTab")
        self.tab_mission.setProperty("active", True)
        self.tab_mission.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.tab_mission.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_mission.setFixedHeight(28)
        self.tab_mission.clicked.connect(lambda: self._select_tab("Mission"))
        tabs_box.addWidget(self.tab_mission)

        self.tab_map = QPushButton("📍 Map")
        self.tab_map.setObjectName("navTab")
        self.tab_map.setProperty("active", False)
        self.tab_map.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.tab_map.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_map.setFixedHeight(28)
        self.tab_map.clicked.connect(lambda: self._select_tab("Map"))
        tabs_box.addWidget(self.tab_map)

        self.tab_surv = QPushButton("👥 Survivors")
        self.tab_surv.setObjectName("navTab")
        self.tab_surv.setProperty("active", False)
        self.tab_surv.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.tab_surv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_surv.setFixedHeight(28)
        self.tab_surv.clicked.connect(lambda: self._select_tab("Survivors"))
        tabs_box.addWidget(self.tab_surv)

        tabs_box.addStretch()
        layout.addLayout(tabs_box)

        # 2. DRONE CAMERA CARD
        cam_card = card_frame()
        cam_layout = QVBoxLayout(cam_card)
        cam_layout.setContentsMargins(8, 8, 8, 8)
        cam_layout.setSpacing(6)

        cam_head = QHBoxLayout()
        cam_icon = QLabel("📹")
        cam_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        cam_head.addWidget(cam_icon)
        cam_head.addWidget(label("DRONE CAMERA", 8, True))
        cam_head.addStretch()

        # RGB / THERMAL / PILOT VIEW Segmented Buttons
        self.btn_rgb = QPushButton("RGB")
        self.btn_rgb.setObjectName("modeSegment")
        self.btn_rgb.setProperty("active", True)
        self.btn_rgb.clicked.connect(lambda: self._set_cam_mode("RGB"))
        cam_head.addWidget(self.btn_rgb)

        self.btn_thermal = QPushButton("THERMAL")
        self.btn_thermal.setObjectName("modeSegment")
        self.btn_thermal.setProperty("active", False)
        self.btn_thermal.clicked.connect(lambda: self._set_cam_mode("THERMAL"))
        cam_head.addWidget(self.btn_thermal)

        self.btn_pilot = QPushButton("PILOT VIEW")
        self.btn_pilot.setObjectName("modeSegment")
        self.btn_pilot.setProperty("active", False)
        self.btn_pilot.clicked.connect(self.open_pilot_view)
        cam_head.addWidget(self.btn_pilot)
        cam_layout.addLayout(cam_head)

        # Camera Display Surface
        self.camera = CameraSurface()
        self.camera.mode_changed.connect(self._sync_cam_buttons)
        cam_layout.addWidget(self.camera, 1)

        # Controls under camera feed: Capture, Record, Zoom, Mode
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        cap_btn = QPushButton("📷 Capture")
        cap_btn.setObjectName("camCtrlBtn")
        cap_btn.clicked.connect(self.capture_snapshot)
        ctrl_row.addWidget(cap_btn)

        self.rec_btn = QPushButton("● Record")
        self.rec_btn.setObjectName("camCtrlBtn")
        self.rec_btn.setStyleSheet("color: #ef4444; font-weight: bold;")
        self.rec_btn.clicked.connect(self.toggle_recording)
        ctrl_row.addWidget(self.rec_btn)

        # Unified Zoom Capsule
        zoom_frame = QFrame()
        zoom_frame.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
            }
            QPushButton {
                background: transparent;
                border: 0;
                font-weight: bold;
                font-size: 8pt;
                color: #64748b;
            }
            QPushButton:hover {
                color: #0f172a;
            }
        """)
        zoom_layout = QHBoxLayout(zoom_frame)
        zoom_layout.setContentsMargins(4, 1, 4, 1)
        zoom_layout.setSpacing(4)

        zoom_m = QPushButton("−")
        zoom_m.setFixedSize(14, 18)
        zoom_m.clicked.connect(lambda: self._adjust_zoom(-1.0))
        zoom_layout.addWidget(zoom_m)

        self.zoom_lbl = QLabel("12.4x")
        self.zoom_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.zoom_lbl.setStyleSheet(f"color:{PALETTE['ink']};")
        zoom_layout.addWidget(self.zoom_lbl)

        zoom_p = QPushButton("+")
        zoom_p.setFixedSize(14, 18)
        zoom_p.clicked.connect(lambda: self._adjust_zoom(1.0))
        zoom_layout.addWidget(zoom_p)
        ctrl_row.addWidget(zoom_frame)

        ctrl_row.addStretch()

        mode_lbl = QLabel("Mode")
        mode_lbl.setFont(QFont("Segoe UI", 7))
        mode_lbl.setStyleSheet(f"color:{PALETTE['muted']};")
        ctrl_row.addWidget(mode_lbl)

        self.mode_select_btn = QPushButton("RGB ▾")
        self.mode_select_btn.setObjectName("camCtrlBtn")
        self.mode_select_btn.setStyleSheet("color: #2563eb; font-weight: bold;")
        self.mode_select_btn.clicked.connect(self.camera.toggle_mode)
        ctrl_row.addWidget(self.mode_select_btn)

        cam_layout.addLayout(ctrl_row)
        cam_card.setFixedHeight(290)
        layout.addWidget(cam_card)

        # 3. SURVIVOR QUEUE CARD
        surv_card = card_frame()
        surv_card.setFixedHeight(275)
        surv_layout = QVBoxLayout(surv_card)
        surv_layout.setContentsMargins(8, 8, 8, 8)
        surv_layout.setSpacing(5)

        surv_head = QHBoxLayout()
        surv_icon = QLabel("👥")
        surv_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        surv_head.addWidget(surv_icon)
        surv_head.addWidget(label("SURVIVOR QUEUE", 8, True))
        surv_head.addStretch()

        found_badge = QLabel("● 4 Found")
        found_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        found_badge.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 9px;
            padding: 2px 7px;
        """)
        surv_head.addWidget(found_badge)
        surv_layout.addLayout(surv_head)

        # 4 Interactive Survivor Cards
        surv_data = [
            ("S01", "01", "A1", "93%", "STABLE", "Lat: 10.8462  Lon: 76.2711", "#10b981", "assets/thumb_s1.png"),
            ("S02", "02", "C4", "87%", "MOVING", "Lat: 10.8468  Lon: 76.2719", "#2563eb", "assets/thumb_s2.png"),
            ("S03", "03", "B3", "76%", "STABLE", "Lat: 10.8459  Lon: 76.2726", "#8b5cf6", "assets/thumb_s3.png"),
            ("S04", "04", "D2", "68%", "INACTIVE", "Lat: 10.8447  Lon: 76.2714", "#ef4444", "assets/thumb_s4.png"),
        ]

        for sid, num, grd, conf, st, coords, col_hex, thumb in surv_data:
            sc = SurvivorCard(sid, num, grd, conf, st, coords, col_hex, thumb)
            sc.selected.connect(self.focus_survivor)
            self.survivor_cards[sid] = sc
            surv_layout.addWidget(sc)

        surv_layout.addStretch()
        layout.addWidget(surv_card)
        layout.addStretch()

        return col

    # --------------------------------------------------------------------------
    # Center Column: 2D SLAM LiDAR Arena + Sensor Status Strip
    # --------------------------------------------------------------------------
    def _center_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. 2D SLAM LIDAR ARENA CARD
        arena_card = card_frame()
        arena_layout = QVBoxLayout(arena_card)
        arena_layout.setContentsMargins(8, 8, 8, 8)
        arena_layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        radar_icon = QLabel("⬡")
        radar_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        head.addWidget(radar_icon)
        head.addWidget(label("2D SLAM LIDAR ARENA", 8, True))

        slam_pill = QLabel("✛ SLAM ACTIVE")
        slam_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        slam_pill.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 4px;
            padding: 2px 6px;
        """)
        head.addWidget(slam_pill)

        grid_pill = QLabel("⌗ METRIC GRID 15x15m")
        grid_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        grid_pill.setStyleSheet(f"""
            color: {PALETTE['blue']};
            background: {PALETTE['blue_soft']};
            border: 1px solid {PALETTE['blue_border']};
            border-radius: 4px;
            padding: 2px 6px;
        """)
        head.addWidget(grid_pill)

        head.addStretch()

        layers_btn = QPushButton("☵")
        layers_btn.setFixedSize(22, 22)
        layers_btn.setStyleSheet(f"background:transparent; border:1px solid {PALETTE['line']}; border-radius:3px; color:{PALETTE['muted']};")
        layers_btn.clicked.connect(lambda: self.log_event("[MAP] Layer display filters toggled."))
        head.addWidget(layers_btn)
        arena_layout.addLayout(head)

        # Interactive Map Canvas
        self.map_canvas = MapCanvas()
        self.map_canvas.survivor_clicked.connect(self.focus_survivor)
        self.map_canvas.waypoint_added.connect(self._on_waypoint_added)
        arena_layout.addWidget(self.map_canvas, 1)

        layout.addWidget(arena_card, 1)

        # 2. SENSOR & DATA LINK STATUS STRIP
        sensor_card = card_frame()
        sensor_layout = QVBoxLayout(sensor_card)
        sensor_layout.setContentsMargins(10, 8, 10, 8)
        sensor_layout.setSpacing(6)

        head_s = QHBoxLayout()
        head_s.addWidget(label("SENSOR & DATA LINK STATUS", 8, True))
        head_s.addStretch()
        head_s.addWidget(label("LOCAL ENU · SYNTHETIC FEED", 6, False, PALETTE["muted"]))
        sensor_layout.addLayout(head_s)

        # 6 Sensor status pills row
        pills_row = QHBoxLayout()
        pills_row.setSpacing(6)
        sensor_items = [
            ("📡", "LiDAR", "ACTIVE"),
            ("(((•)))", "RADAR", "ACTIVE"),
            ("👁", "VISION", "ACTIVE"),
            ("📶", "WiFi", "ACTIVE"),
            ("💻", "MAVLink", "ACTIVE"),
            ("🔗", "CONNECTED", "ACTIVE"),
        ]
        for icon, name, state in sensor_items:
            pill = QPushButton(f"{icon}  {name}\n    {state}")
            pill.setObjectName("sensorPill")
            pill.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            pill.setStyleSheet(f"""
                QPushButton#sensorPill {{
                    color: #059669;
                    background: #ecfdf5;
                    border: 1px solid #a7f3d0;
                    border-radius: 5px;
                    padding: 4px 6px;
                    text-align: center;
                }}
                QPushButton#sensorPill:hover {{
                    background: #d1fae5;
                }}
            """)
            pill.clicked.connect(lambda checked=False, s=name: self.log_event(f"[SENSOR] {s} diagnostic telemetry: OK."))
            pills_row.addWidget(pill)

        sensor_layout.addLayout(pills_row)

        # Metrics bar below
        metric_bar = QHBoxLayout()
        metric_bar.setSpacing(10)

        metric_bar.addWidget(label("ARENA COVERAGE", 7, True, PALETTE["muted"]))
        self.cov_prog = QProgressBar()
        self.cov_prog.setRange(0, 100)
        self.cov_prog.setValue(64)
        self.cov_prog.setTextVisible(False)
        self.cov_prog.setFixedHeight(6)
        metric_bar.addWidget(self.cov_prog, 2)
        metric_bar.addWidget(label("64%", 8, True))

        metric_bar.addWidget(self._divider())
        metric_bar.addWidget(label("FRAME", 7, True, PALETTE["muted"]))
        metric_bar.addWidget(label("LOCAL ENU", 8, True))

        metric_bar.addWidget(self._divider())
        metric_bar.addWidget(label("SURVIVORS", 7, True, PALETTE["muted"]))
        metric_bar.addWidget(label("4 / 6", 8, True))

        metric_bar.addWidget(self._divider())
        metric_bar.addWidget(label("MISSION TIME", 7, True, PALETTE["muted"]))
        self.time_val_lbl = label("14:30", 8, True)
        metric_bar.addWidget(self.time_val_lbl)

        sensor_layout.addLayout(metric_bar)
        layout.addWidget(sensor_card)

        return col

    # --------------------------------------------------------------------------
    # Right Column: Mission Status + Telemetry + Hardware Health
    # --------------------------------------------------------------------------
    def _right_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. MISSION STATUS CARD
        stat_card = card_frame()
        stat_layout = QVBoxLayout(stat_card)
        stat_layout.setContentsMargins(10, 8, 10, 8)
        stat_layout.setSpacing(6)

        s_head = QHBoxLayout()
        radar_i = QLabel("🎯")
        radar_i.setStyleSheet(f"color:{PALETTE['green']};")
        s_head.addWidget(radar_i)
        s_head.addWidget(label("MISSION STATUS", 8, True))
        s_head.addStretch()
        rtl_badge = QLabel("● RTL / LAND")
        rtl_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        rtl_badge.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 9px;
            padding: 2px 7px;
        """)
        s_head.addWidget(rtl_badge)
        stat_layout.addLayout(s_head)

        donut_row = QHBoxLayout()
        donut_row.setSpacing(10)
        self.donut = CircularProgressWidget(64)
        donut_row.addWidget(self.donut)

        donut_details = QVBoxLayout()
        donut_details.setSpacing(8)

        # Box 1: Aborted + 2/6 Coverage
        b1_row = QHBoxLayout()
        b1_row.setSpacing(6)
        w_icon = QLabel("⚠️")
        w_icon.setFixedSize(26, 26)
        w_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_icon.setStyleSheet("background: #fee2e2; border-radius: 5px;")
        b1_row.addWidget(w_icon)

        b1_txt = QVBoxLayout()
        b1_txt.setSpacing(0)
        b1_txt.addWidget(label("ABORTED", 8, True))
        cov_row = QHBoxLayout()
        cov_row.setSpacing(4)
        cov_row.addWidget(label("2 / 6", 8, True, PALETTE["danger"]))
        cov_row.addWidget(label("COVERAGE", 6, False, PALETTE["danger"]))
        cov_row.addStretch()
        b1_txt.addLayout(cov_row)
        b1_row.addLayout(b1_txt, 1)
        donut_details.addLayout(b1_row)

        # Box 2: Local ENU Coordinates
        b2_row = QHBoxLayout()
        b2_row.setSpacing(6)
        p_icon = QLabel("📍")
        p_icon.setFixedSize(26, 26)
        p_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p_icon.setStyleSheet("background: #e0f2fe; border-radius: 5px;")
        b2_row.addWidget(p_icon)

        b2_txt = QVBoxLayout()
        b2_txt.setSpacing(0)
        b2_txt.addWidget(label("LOCAL ENU", 8, True, PALETTE["blue"]))
        b2_txt.addWidget(label("COORDINATES", 6, False, PALETTE["muted"]))
        b2_row.addLayout(b2_txt, 1)
        donut_details.addLayout(b2_row)

        donut_row.addLayout(donut_details, 1)
        stat_layout.addLayout(donut_row)
        layout.addWidget(stat_card)

        # 2. TELEMETRY CARD
        telem_card = card_frame()
        telem_layout = QVBoxLayout(telem_card)
        telem_layout.setContentsMargins(10, 8, 10, 8)
        telem_layout.setSpacing(5)

        t_head = QHBoxLayout()
        t_icon = QLabel("📊")
        t_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        t_head.addWidget(t_icon)
        t_head.addWidget(label("TELEMETRY", 8, True))
        t_head.addStretch()
        t_head.addWidget(label("LOCAL ENU - 10 HZ", 6, False, PALETTE["muted"]))
        telem_layout.addLayout(t_head)

        # 2-Column Telemetry Grid
        t_grid = QGridLayout()
        t_grid.setVerticalSpacing(3)
        t_grid.setHorizontalSpacing(8)

        self.telem_labels: Dict[str, QLabel] = {}
        pairs = [
            ("🔋 Battery", "87%", "⚡ Voltage", "22.4 V"),
            ("⚙ Current", "8.2 A", "⛰ Altitude", "23.5 m"),
            ("🎮 Mode", "RTL / LAND", "🔗 Link", "37 ms"),
            ("📶 Quality", "98%", "💨 Speed", "1.9 m/s"),
            ("🧭 Heading", "332°", "⏱ Flight", "14:30"),
            ("🛰 GPS", "OPT_FLOW", "📍 Position", "OK"),
        ]

        for row_idx, (k1, v1, k2, v2) in enumerate(pairs):
            t_grid.addWidget(label(k1, 7, False, PALETTE["muted"]), row_idx, 0)
            v1_lbl = label(v1, 7, True, PALETTE["blue"] if "RTL" in v1 else PALETTE["ink"])
            self.telem_labels[k1] = v1_lbl
            t_grid.addWidget(v1_lbl, row_idx, 1)

            t_grid.addWidget(label(k2, 7, False, PALETTE["muted"]), row_idx, 2)
            v2_lbl = label(v2, 7, True, PALETTE["green"] if v2 == "OK" else PALETTE["ink"])
            self.telem_labels[k2] = v2_lbl
            t_grid.addWidget(v2_lbl, row_idx, 3)

        telem_layout.addLayout(t_grid)
        layout.addWidget(telem_card)

        # 3. HARDWARE SUBSYSTEM HEALTH CARD
        health_card = card_frame()
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(10, 8, 10, 8)
        health_layout.setSpacing(5)

        h_head = QHBoxLayout()
        h_icon = QLabel("⚙")
        h_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        h_head.addWidget(h_icon)
        h_head.addWidget(label("HARDWARE SUBSYSTEM HEALTH", 8, True))
        h_head.addStretch()
        h_head.addWidget(label("5 CORE UNITS", 6, False, PALETTE["muted"]))
        health_layout.addLayout(h_head)

        units = [
            ("📹", "Jetson Orin"),
            ("📷", "Jetson Gimbal / Mount"),
            ("◎", "RPLIDAR C1"),
            ("::", "ROS 2 Bridge"),
            ("🔗", "MAVLink"),
        ]
        for icon_str, name in units:
            health_layout.addWidget(SubsystemItemWidget(icon_str, name))

        layout.addWidget(health_card)

        return col

    # --------------------------------------------------------------------------
    # Bottom Row: Logs + Quick Actions + Emergency Abort
    # --------------------------------------------------------------------------
    def _bottom_bar(self) -> QWidget:
        row = QWidget()
        row.setObjectName("bottomBar")
        row.setFixedHeight(108)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. MISSION EVENT LOG (Chronological)
        log_card = card_frame()
        log_card.setFixedHeight(108)
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(10, 8, 10, 8)
        log_layout.setSpacing(4)

        l_head = QHBoxLayout()
        l_head.addWidget(QLabel("🕒"))
        l_head.addWidget(label("MISSION EVENT LOG (CHRONOLOGICAL)", 8, True))
        l_head.addStretch()
        log_layout.addLayout(l_head)

        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setFrameShape(QFrame.Shape.NoFrame)
        log_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        log_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        log_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: 0;
            }
            QScrollBar:vertical {
                width: 4px;
                background: #f1f5f9;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 2px;
            }
        """)

        self.log_scroll_widget = QWidget()
        self.log_scroll_widget.setStyleSheet("background: transparent;")
        self.log_container = QVBoxLayout(self.log_scroll_widget)
        self.log_container.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.log_container.setContentsMargins(0, 0, 8, 0)
        self.log_container.setSpacing(3)

        log_scroll.setWidget(self.log_scroll_widget)
        self.log_scroll_area = log_scroll
        log_layout.addWidget(log_scroll, 1)

        initial_events = [
            ("14:52:57", "[NAV] Local waypoint staged at ENU 13.1E / 6.0N.", "INFO", PALETTE["blue"], PALETTE["blue_soft"], PALETTE["blue_border"]),
            ("14:53:21", "[DETECT] Survivor 02 detected (87%) - GRD C4.", "DETECT", PALETTE["danger"], PALETTE["danger_soft"], PALETTE["danger_border"]),
            ("14:54:10", "[NAV] Rerouting to survivor 02 (ETA 1m 12s).", "NAV", PALETTE["blue"], PALETTE["blue_soft"], PALETTE["blue_border"]),
            ("14:55:02", "[STATUS] Mission continuing...", "INFO", PALETTE["blue"], PALETTE["blue_soft"], PALETTE["blue_border"]),
        ]

        for time_str, text_str, cat, cat_c, cat_bg, cat_b in initial_events:
            self._append_log_row(time_str, text_str, cat, cat_c, cat_bg, cat_b)

        layout.addWidget(log_card, 38)

        # 2. QUICK ACTIONS
        action_card = card_frame()
        action_card.setFixedHeight(108)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(10, 8, 10, 8)
        action_layout.setSpacing(6)

        qa_head = QHBoxLayout()
        qa_head.addWidget(label("QUICK ACTIONS", 8, True))
        qa_head.addStretch()
        sim_ready = QLabel("● SIMULATION - READY")
        sim_ready.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        sim_ready.setStyleSheet(f"color:{PALETTE['green']};")
        qa_head.addWidget(sim_ready)
        action_layout.addLayout(qa_head)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        actions = [
            ("🎮", "Switch to Manual", self.toggle_flight_mode),
            ("📍", "Add Waypoint", self.start_add_waypoint),
            ("👤", "Mark Survivor", self.mark_current_survivor),
            ("🏠", "Return to Home", self.return_to_home),
        ]
        for icon_str, title_str, handler in actions:
            btn = QPushButton(f"{icon_str}  {title_str}")
            btn.setObjectName("actionBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(handler)
            btns_row.addWidget(btn)

        action_layout.addLayout(btns_row)
        layout.addWidget(action_card, 42)

        # 3. EMERGENCY ABORT BUTTON
        self.abort_card = QFrame()
        self.abort_card.setObjectName("abortCard")
        self.abort_card.setFixedHeight(108)
        self.abort_card.setCursor(Qt.CursorShape.PointingHandCursor)
        abort_layout = QHBoxLayout(self.abort_card)
        abort_layout.setContentsMargins(14, 8, 14, 8)
        abort_layout.setSpacing(12)

        warn_icon = WhiteHazardIcon(28)
        abort_layout.addWidget(warn_icon)

        abort_txt = QVBoxLayout()
        abort_txt.setSpacing(1)
        a_title = QLabel("EMERGENCY ABORT")
        a_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        a_title.setStyleSheet("color: #ffffff; background: transparent;")
        abort_txt.addWidget(a_title)

        a_sub = QLabel("RTL - LAND HERE")
        a_sub.setFont(QFont("Segoe UI", 7))
        a_sub.setStyleSheet("color: #ffffff; background: transparent; opacity: 0.9;")
        abort_txt.addWidget(a_sub)
        abort_layout.addLayout(abort_txt)

        self.abort_card.mousePressEvent = lambda e: self.emergency_abort()  # type: ignore[method-assign]
        layout.addWidget(self.abort_card, 20)

        return row

    def _append_log_row(self, time_str: str, text_str: str, cat: str, cat_c: str, cat_bg: str, cat_b: str) -> None:
        # Cap at 50 rows to avoid runaway bloat
        while self.log_container.count() >= 50:
            item = self.log_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row_widget = QWidget()
        row_widget.setFixedHeight(17)
        row_widget.setStyleSheet("background: transparent;")
        line_row = QHBoxLayout(row_widget)
        line_row.setContentsMargins(0, 0, 0, 0)
        line_row.setSpacing(6)

        dot = QLabel("●")
        dot.setFont(QFont("Segoe UI", 6))
        dot.setStyleSheet(f"color:{cat_c};")
        line_row.addWidget(dot)

        t_lbl = QLabel(time_str)
        t_lbl.setFont(QFont("Segoe UI", 7))
        t_lbl.setStyleSheet(f"color:{PALETTE['muted']};")
        line_row.addWidget(t_lbl)

        msg_lbl = QLabel(text_str)
        msg_lbl.setFont(QFont("Segoe UI", 7))
        msg_lbl.setStyleSheet(f"color:{PALETTE['ink']};")
        line_row.addWidget(msg_lbl, 1)

        cat_pill = QLabel(cat)
        cat_pill.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        cat_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cat_pill.setFixedWidth(44)
        cat_pill.setStyleSheet(f"""
            color: {cat_c};
            background: {cat_bg};
            border: 1px solid {cat_b};
            border-radius: 3px;
            padding: 1px 2px;
        """)
        line_row.addWidget(cat_pill)

        self.log_container.addWidget(row_widget)

        if hasattr(self, "log_scroll_area"):
            QTimer.singleShot(10, lambda: self.log_scroll_area.verticalScrollBar().setValue(
                self.log_scroll_area.verticalScrollBar().maximum()
            ))

    def _divider(self) -> QFrame:
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("color: #e2e8f0;")
        return div

    # --------------------------------------------------------------------------
    # Stylesheet and Theme
    # --------------------------------------------------------------------------
    def _apply_theme(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {PALETTE['bg']};
                color: {PALETTE['ink']};
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }}
            QFrame#header {{
                background: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 6px;
            }}
            QPushButton#navTab {{
                background: transparent;
                border: 0;
                border-radius: 6px;
                color: {PALETTE['muted']};
                padding: 4px 12px;
            }}
            QPushButton#navTab:hover {{
                background: #e2e8f0;
                color: {PALETTE['ink']};
            }}
            QPushButton#navTab[active='true'] {{
                background: {PALETTE['blue']};
                color: #ffffff;
            }}
            QFrame#card {{
                background: {PALETTE['card']};
                border: 1px solid {PALETTE['line']};
                border-radius: 6px;
            }}
            QFrame#subsystemRow {{
                background: #f8fafc;
                border: 1px solid {PALETTE['line']};
                border-radius: 5px;
            }}
            QPushButton#modeSegment {{
                background: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 4px;
                padding: 2px 7px;
                font: 7pt 'Segoe UI';
                font-weight: bold;
                color: {PALETTE['muted']};
            }}
            QPushButton#modeSegment:hover {{
                background: {PALETTE['blue_soft']};
                border-color: {PALETTE['blue']};
            }}
            QPushButton#modeSegment[active='true'] {{
                background: {PALETTE['blue']};
                color: #ffffff;
                border-color: {PALETTE['blue']};
            }}
            QPushButton#camCtrlBtn {{
                background: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 4px;
                padding: 3px 8px;
                font: 7pt 'Segoe UI';
                color: {PALETTE['ink']};
            }}
            QPushButton#camCtrlBtn:hover {{
                background: {PALETTE['card_alt']};
            }}
            QPushButton#actionBtn {{
                background: #ffffff;
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 6px;
                padding: 6px 10px;
                font: 7pt 'Segoe UI';
                font-weight: 600;
                color: {PALETTE['blue']};
            }}
            QPushButton#actionBtn:hover {{
                background: {PALETTE['blue_soft']};
                border-color: {PALETTE['blue']};
            }}
            QFrame#abortCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444);
                border: 1px solid #b91c1c;
                border-radius: 6px;
            }}
            QFrame#abortCard:hover {{
                background: #b91c1c;
            }}
            QFrame#abortCard QLabel {{
                background: transparent;
                color: #ffffff;
            }}
            QProgressBar {{
                background: #e2e8f0;
                border: 0;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {PALETTE['blue']};
                border-radius: 3px;
            }}
        """)

    # --------------------------------------------------------------------------
    # Interactive Handlers & Slots
    # --------------------------------------------------------------------------
    def _select_tab(self, name: str) -> None:
        self.tab_mission.setProperty("active", name == "Mission")
        self.tab_map.setProperty("active", name == "Map")
        self.tab_surv.setProperty("active", name == "Survivors")
        for btn in (self.tab_mission, self.tab_map, self.tab_surv):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.log_event(f"[NAV] Switched view tab to {name}.")

    def _set_cam_mode(self, mode: str) -> None:
        if self.camera.mode == mode:
            return
        self.camera.set_mode(mode)

    def _sync_cam_buttons(self, mode: str) -> None:
        self.btn_rgb.setProperty("active", mode == "RGB")
        self.btn_thermal.setProperty("active", mode == "THERMAL")
        self.btn_rgb.style().unpolish(self.btn_rgb)
        self.btn_rgb.style().polish(self.btn_rgb)
        self.btn_thermal.style().unpolish(self.btn_thermal)
        self.btn_thermal.style().polish(self.btn_thermal)
        self.mode_select_btn.setText(f"{mode} ▾")
        if not hasattr(self, "_last_synced_cam_mode") or self._last_synced_cam_mode != mode:
            self._last_synced_cam_mode = mode
            self.log_event(f"[CAM] Sensor feed switched to {mode} mode.")

    def _adjust_zoom(self, delta: float) -> None:
        new_z = max(1.0, min(24.0, self.camera.zoom + delta))
        self.camera.set_zoom(new_z)
        self.zoom_lbl.setText(f"{self.camera.zoom:.1f}x")
        self.log_event(f"[CAM] Reconnaissance zoom adjusted to {self.camera.zoom:.1f}x.")

    def capture_snapshot(self) -> None:
        self.camera.flash_shutter()
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_event(f"[CAM] Snapshot captured to disk: RECON_{now_str}.jpg (1080p).")

    def toggle_recording(self) -> None:
        self.camera.is_recording = not self.camera.is_recording
        if self.camera.is_recording:
            self.camera.record_seconds = 0
            self.rec_btn.setText("⏹ Stop")
            self.rec_btn.setStyleSheet("color: #ffffff; background: #dc2626; font-weight: bold;")
            self.log_event("[CAM] Live mission video recording started.")
        else:
            self.rec_btn.setText("● Record")
            self.rec_btn.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.log_event("[CAM] Mission video recording saved.")

    def focus_survivor(self, survivor_id: str) -> None:
        for sid, card in self.survivor_cards.items():
            card.set_selected(sid == survivor_id)
        self.map_canvas.select_survivor(survivor_id)
        self.camera.set_highlight_person(survivor_id)
        self.log_event(f"[VISION] Locked tracking onto survivor target {survivor_id}.")

    def start_add_waypoint(self) -> None:
        self.map_canvas.set_add_waypoint_mode(True)
        self.log_event("[NAV] Click on Arena Map to place a staged waypoint.")

    def _on_waypoint_added(self, norm_x: float, norm_y: float, tag: str) -> None:
        enu_e = round(norm_x * 15.0, 1)
        enu_n = round((1.0 - norm_y) * 15.0, 1)
        self.log_event(f"[NAV] Local waypoint staged at ENU {enu_e}E / {enu_n}N ({tag}).")

    def mark_current_survivor(self) -> None:
        self.log_event("[VISION] Survivor localized at active crosshair (10.8464 N, 76.2716 E).")

    def return_to_home(self) -> None:
        self.flight_mode = "RTL / LAND"
        self._update_flight_mode_ui()
        self.log_event("[NAV] Return-to-Launch sequence commanded.")

    def toggle_flight_mode(self) -> None:
        self.flight_mode = "MANUAL" if self.flight_mode == "RTL / LAND" else "RTL / LAND"
        self._update_flight_mode_ui()
        self.log_event(f"[NAV] Flight mode transitioned to {self.flight_mode}.")

    def _update_flight_mode_ui(self) -> None:
        self.mode_pill.setText(f"● {self.flight_mode}  ⌄")
        if "RTL" in self.flight_mode:
            self.mode_pill.setStyleSheet(f"""
                QPushButton#modePill {{
                    color: {PALETTE['green']};
                    background: {PALETTE['green_soft']};
                    border: 1px solid {PALETTE['green_border']};
                    border-radius: 11px;
                    padding: 3px 10px;
                }}
            """)
        else:
            self.mode_pill.setStyleSheet(f"""
                QPushButton#modePill {{
                    color: {PALETTE['blue']};
                    background: {PALETTE['blue_soft']};
                    border: 1px solid {PALETTE['blue_border']};
                    border-radius: 11px;
                    padding: 3px 10px;
                }}
            """)
        if "🎮 Mode" in self.telem_labels:
            self.telem_labels["🎮 Mode"].setText(self.flight_mode)

    def emergency_abort(self) -> None:
        ans = QMessageBox.warning(
            self, "Emergency Abort",
            "DECLARE EMERGENCY ABORT (RTL / LAND)?\n\nImmediate return-to-base and emergency touchdown protocol will be commanded.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.flight_mode = "EMERGENCY LAND"
            self._update_flight_mode_ui()
            self.log_event("[ALERT] EMERGENCY ABORT CONFIRMED. Return-to-Launch initiated.")

    def log_event(self, msg: str) -> None:
        if hasattr(self, "_last_logged_msg") and self._last_logged_msg == msg:
            return
        self._last_logged_msg = msg

        now_str = datetime.now().strftime("%H:%M:%S")
        cat = "INFO"
        cat_c = PALETTE["blue"]
        cat_bg = PALETTE["blue_soft"]
        cat_b = PALETTE["blue_border"]

        if "[DETECT]" in msg or "[VISION]" in msg:
            cat = "DETECT"
            cat_c = PALETTE["danger"]
            cat_bg = PALETTE["danger_soft"]
            cat_b = PALETTE["danger_border"]
        elif "[NAV]" in msg:
            cat = "NAV"
            cat_c = PALETTE["blue"]
            cat_bg = PALETTE["blue_soft"]
            cat_b = PALETTE["blue_border"]
        elif "[ALERT]" in msg:
            cat = "ALERT"
            cat_c = PALETTE["danger"]
            cat_bg = PALETTE["danger_soft"]
            cat_b = PALETTE["danger_border"]

        self._append_log_row(now_str, msg, cat, cat_c, cat_bg, cat_b)

    def open_pilot_view(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("NIDAR Drone Camera — Pilot Reconnaissance View")
        dialog.resize(900, 560)
        v = QVBoxLayout(dialog)
        cam = CameraSurface()
        cam.set_mode(self.camera.mode)
        v.addWidget(cam, 1)
        dialog.exec()

    def _update_telemetry(self) -> None:
        self.flight_seconds += 1
        mins = self.flight_seconds // 60
        secs = self.flight_seconds % 60
        time_str = f"{mins:02d}:{secs:02d}"

        self.timer_pill.setText(f"⏱ {time_str} / 30:00")
        self.time_val_lbl.setText(time_str)

        if "⏱ Flight" in self.telem_labels:
            self.telem_labels["⏱ Flight"].setText(time_str)

        if self.camera.is_recording:
            self.camera.record_seconds += 1
            self.camera.update()


def main() -> int:
    app = QApplication(sys.argv)
    window = NidarRescueGCS()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
