#!/usr/bin/env python3
"""NIDAR Rescue GCS — Exact Modern Light Tactical UI (v2) Phase 2 Fully Functional.

Faithfully implements the complete reference interface from reference_ui_v2.jpg:
- NO vertical sidebar (sidebar removed as requested).
- Top Header: Full-width brand bar with Drone Logo, NIDAR Rescue GCS,
  ● RTL / LAND dropdown, ⏱ 14:30 / 30:00 timer, 📶 COMM: CONNECTED (98%), settings button.
- Horizontal Navigation Tabs: [⌂ Mission] (active blue), [📍 Map], [👥 Survivors].
- Left Column:
    - DRONE CAMERA: Segmented RGB / THERMAL / PILOT VIEW, live aerial HUD with dynamic AI bounding boxes,
      capture/record/zoom controls, live FLIR thermal shader, real snapshot and video frame saving.
    - SURVIVOR QUEUE: Dynamic interactive cards (S01–S04) with confidence badges, status badges, thumbnails, coordinates.
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
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPolygonF, QPainterPath, QPixmap, QImage, QIcon, QCursor, QAction
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QMessageBox, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSplitter, QVBoxLayout, QWidget, QButtonGroup, QLineEdit, QStackedWidget
)

from gcs_client import GCSClientWorker
from gcs_data_plugins import (
    DataPluginManager, ARENA_WIDTH_M, ARENA_HEIGHT_M,
    DESIGNATED_TARGET_IDS, MissionState
)
from health_model import HealthState, HealthSystemManager
from subsystem_diagnostics import SubsystemItemWidget, SubsystemDiagnosticsDialog
from gcs_workspaces import MapWorkspaceWidget, SurvivorsWorkspaceWidget

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
        self.value = max(0, min(100, int(val)))
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
    """Live interactive aerial reconnaissance feed with dynamic AI overlays, shaders, snapshots."""
    mode_changed = pyqtSignal(str)
    snapshot_taken = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode = "RGB"  # "RGB" or "THERMAL"
        self.zoom = 12.4
        self.is_recording = False
        self.record_seconds = 0
        self.record_dir: Optional[Path] = None
        self.record_frame_count = 0
        self.shutter_flash = False
        self.highlighted_person: Optional[str] = None
        self.bg_pixmap = QPixmap("assets/camera_feed_bg.png")
        self.active_detections: List[Dict[str, Any]] = []
        self.telem_hud: Dict[str, Any] = {
            "altitude": 2.4,
            "speed": 1.2,
            "heading": 228,
            "battery": 86,
        }
        self.is_simulated_stream = True
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

    def set_detections(self, detections: List[Dict[str, Any]]) -> None:
        self.active_detections = detections
        self.update()

    def set_telemetry(self, telem: Dict[str, Any]) -> None:
        """Receive unified telemetry matching the main dashboard exactly."""
        self.telem_hud.update(telem)
        self.update()

    def save_snapshot_to_disk(self) -> str:
        """Render the current frame and overlays to an image on disk."""
        self.flash_shutter()
        out_dir = Path("output/snapshots")
        out_dir.mkdir(parents=True, exist_ok=True)
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = out_dir / f"RECON_{now_str}.jpg"

        pix = self.grab()
        pix.save(str(filepath), "JPEG", 95)
        self.snapshot_taken.emit(str(filepath))
        return str(filepath)

    def start_recording(self) -> str:
        self.is_recording = True
        self.record_seconds = 0
        self.record_frame_count = 0
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.record_dir = Path(f"output/recordings/REC_{now_str}")
        self.record_dir.mkdir(parents=True, exist_ok=True)
        return str(self.record_dir)

    def stop_recording(self) -> Tuple[int, str]:
        self.is_recording = False
        count = self.record_frame_count
        rec_path = str(self.record_dir) if self.record_dir else "output/recordings"
        return count, rec_path

    def capture_video_frame(self) -> None:
        if self.is_recording and self.record_dir:
            self.record_frame_count += 1
            if self.record_frame_count % 3 == 0:  # Sample at ~10 FPS from 30 FPS tick
                frame_file = self.record_dir / f"frame_{self.record_frame_count:05d}.jpg"
                pix = self.grab()
                pix.save(str(frame_file), "JPEG", 85)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        w, h = rect.width(), rect.height()

        # 1. Base feed
        if not self.bg_pixmap.isNull():
            p.drawPixmap(rect, self.bg_pixmap)
        else:
            p.fillRect(rect, QColor("#1e293b"))

        # 2. FLIR Thermal ironbow shader effect
        if self.mode == "THERMAL":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_ColorBurn)
            p.fillRect(rect, QColor(90, 20, 130, 190))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            p.fillRect(rect, QColor(0, 210, 255, 90))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Thermal tag banner (truthfully labelled)
            p.fillRect(QRectF(8, 38, 140, 16), QColor(0, 0, 0, 180))
            p.setPen(QColor("#00f2fe"))
            p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            p.drawText(QRectF(8, 38, 140, 16), Qt.AlignmentFlag.AlignCenter, "SIMULATED THERMAL (POST-FILTER)")

        # 3. Dynamic Telemetry Aerial HUD (consistent with telemetry panel & reference UI)
        alt = self.telem_hud.get("altitude", 2.4)
        spd = self.telem_hud.get("speed", 1.2)
        bat = self.telem_hud.get("battery", 86)

        # Top-Left: Stream badge [● SIMULATED] + [1080p]
        p.fillRect(QRectF(10, 10, 72, 18), QColor(220, 38, 38, 220))
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        stream_tag = "● LIVE" if not self.is_simulated_stream else "● SIMULATED"
        p.drawText(QRectF(10, 10, 72, 18), Qt.AlignmentFlag.AlignCenter, stream_tag)

        p.fillRect(QRectF(86, 10, 42, 18), QColor(15, 23, 42, 190))
        p.drawText(QRectF(86, 10, 42, 18), Qt.AlignmentFlag.AlignCenter, "1080p")

        # Top-Right: Altitude, Speed, Zoom pill
        tr_rect = QRectF(w - 170, 10, 160, 18)
        p.fillRect(tr_rect, QColor(15, 23, 42, 190))
        p.setPen(QColor("#ffffff"))
        p.drawText(tr_rect, Qt.AlignmentFlag.AlignCenter, f"ALT {alt}m   SPD {spd}m/s   {self.zoom:.1f}x")

        # 4. Center Tactical Crosshairs
        cx, cy = w / 2, h / 2
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.0))
        p.drawLine(QPointF(cx - 15, cy), QPointF(cx - 4, cy))
        p.drawLine(QPointF(cx + 4, cy), QPointF(cx + 15, cy))
        p.drawLine(QPointF(cx, cy - 15), QPointF(cx, cy - 4))
        p.drawLine(QPointF(cx, cy + 4), QPointF(cx, cy + 15))

        # 5. Dynamic AI Bounding Boxes from incoming detection events
        for det in self.active_detections:
            status = str(det.get("status", "SEARCHING")).upper()
            bbox = det.get("bbox")
            if status in {"SEARCHING", "NOT DETECTED", "—"} or bbox is None:
                continue

            sid = str(det.get("id", "S01"))
            conf = det.get("confidence") or 0

            bx1 = bbox[0] * w
            by1 = bbox[1] * h
            bw = (bbox[2] - bbox[0]) * w
            bh = (bbox[3] - bbox[1]) * h
            box_rect = QRectF(bx1, by1, bw, bh)

            is_focused = (sid == self.highlighted_person)

            # Box outline
            box_color = QColor(PALETTE["cyan"]) if not is_focused else QColor(PALETTE["blue"])
            if status == "MOVING":
                box_color = QColor(PALETTE["amber"])
            elif status == "INACTIVE":
                box_color = QColor(PALETTE["danger"])

            p.setPen(QPen(box_color, 2.0 if is_focused else 1.4, Qt.PenStyle.SolidLine))
            p.setBrush(QBrush(QColor(box_color.red(), box_color.green(), box_color.blue(), 25 if not is_focused else 50)))
            p.drawRect(box_rect)

            # Detection Tag
            tag_text = f"TARGET {sid}: {conf}%" if not is_focused else f"TARGET {sid} [LOCKED]"
            tag_w = max(bw + 12, 78.0)
            tag_rect = QRectF(bx1, max(0.0, by1 - 16), tag_w, 15)
            p.fillRect(tag_rect, QColor(0, 0, 0, 190))
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag_text)

        # 6. Stream status watermark
        watermark_text = "SIMULATED VIDEO (NO PHYSICAL AIR UNIT)" if self.is_simulated_stream else "LIVE CAMERA (AIR UNIT CONNECTED)"
        p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(8, h - 20, 260, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, watermark_text)

        # 7. Shutter flash animation
        if self.shutter_flash:
            p.fillRect(rect, QColor(255, 255, 255, 220))

        # 8. Recording banner if active
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
        is_stale: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.survivor_id = survivor_id
        self.color_hex = color_hex
        self.is_active_selected = False
        self.is_stale = is_stale
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
        self.setToolTip(f"Designated Target {survivor_id} — Slot {number_str}")
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

        is_searching = status_text in {"SEARCHING", "NOT DETECTED", "—"}
        conf_display = "—%" if is_searching or not confidence_str or confidence_str == "0%" else f"✔ {confidence_str}"
        conf_pill = QLabel(conf_display)
        conf_pill.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        conf_pill.setStyleSheet(f"""
            color: {color_hex if not is_searching else '#94a3b8'};
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            padding: 2px 5px;
        """)
        badge_box.addWidget(conf_pill)

        if is_stale or status_text in {"LOST", "STALE"}:
            st_color, st_bg, st_border = PALETTE["amber"], PALETTE["amber_soft"], PALETTE["amber_border"]
            badge_text = "LOST (STALE)" if is_stale else "LOST"
        elif status_text in {"LOCALISED", "CONFIRMED", "FOUND"}:
            st_color, st_bg, st_border = PALETTE["green"], PALETTE["green_soft"], PALETTE["green_border"]
            badge_text = "LOCALISED"
        elif status_text in {"TRACKING", "MOVING"}:
            st_color, st_bg, st_border = PALETTE["blue"], PALETTE["blue_soft"], PALETTE["blue_border"]
            badge_text = "TRACKING"
        elif status_text == "DETECTED":
            st_color, st_bg, st_border = PALETTE["cyan"], PALETTE["blue_soft"], PALETTE["blue_border"]
            badge_text = "DETECTED"
        else:
            st_color, st_bg, st_border = PALETTE["muted"], "#f1f5f9", PALETTE["line"]
            badge_text = "SEARCHING"

        state_pill = QLabel(badge_text)
        state_pill.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
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
    waypoint_selected = pyqtSignal(str, int, float, float, str)  # (type, idx, x, y, tag)
    survivor_clicked = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(440, 310)
        self.bg_pixmap = QPixmap("assets/arena_map_bg.png")
        self.add_waypoint_mode = False
        self.pulse_phase = 0.0
        self.scan_sweep = 0.0
        self.selected_target: Optional[str] = None
        self.selected_waypoint: Optional[Tuple[str, int, float, float, str]] = None
        self.drone_pos = (1.5, 1.5)
        self.drone_yaw = 90.0
        self.active_survivors: List[Dict[str, Any]] = []
        self.staged_waypoints: List[Tuple[float, float, str]] = []
        self.accepted_waypoints: List[Tuple[float, float]] = []
        self.active_waypoint_idx: int = 0
        self.completed_waypoints: List[int] = []

        # Layer visibility flags
        self.layer_grid = True
        self.layer_drone = True
        self.layer_lidar = True
        self.layer_path = True
        self.layer_staged = True
        self.layer_survivors = True
        self.layer_sonar = True

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_add_waypoint_mode(self, enabled: bool) -> None:
        self.add_waypoint_mode = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def select_survivor(self, sid: str) -> None:
        self.selected_target = sid
        self.update()

    def select_waypoint(self, w_type: str, idx: int, x: float, y: float, tag: str) -> None:
        self.selected_waypoint = (w_type, idx, x, y, tag)
        self.update()

    def update_drone_state(self, x: float, y: float, yaw: float) -> None:
        self.drone_pos = (x, y)
        self.drone_yaw = yaw
        self.update()

    def update_survivors(self, survivors: List[Dict[str, Any]]) -> None:
        self.active_survivors = survivors
        self.update()

    def update_waypoints(
        self,
        staged: List[Tuple[float, float, str]],
        accepted: List[Tuple[float, float]],
        active_idx: int = 0,
        completed: Optional[List[int]] = None,
    ) -> None:
        self.staged_waypoints = staged
        self.accepted_waypoints = accepted
        self.active_waypoint_idx = active_idx
        self.completed_waypoints = completed or []
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
            metric_x = round(norm_x * ARENA_WIDTH_M, 2)
            metric_y = round((1.0 - norm_y) * ARENA_HEIGHT_M, 2)
            col_idx = int(norm_x * 15)
            row_idx = 15 - int(norm_y * 15)
            col_letter = chr(ord('A') + min(14, max(0, col_idx)))
            wp_tag = f"WP-{len(self.staged_waypoints)+1} [{col_letter}{row_idx}]"
            self.staged_waypoints.append((metric_x, metric_y, wp_tag))
            self.waypoint_added.emit(metric_x, metric_y, wp_tag)
            self.set_add_waypoint_mode(False)
            self.update()
            return

        # Check clicks on staged waypoints
        for idx, (wx, wy, wtag) in enumerate(self.staged_waypoints):
            pt_x = wx / ARENA_WIDTH_M * w
            pt_y = (1.0 - wy / ARENA_HEIGHT_M) * h
            if math.hypot(pos.x() - pt_x, pos.y() - pt_y) < 18:
                self.selected_waypoint = ("staged", idx, wx, wy, wtag)
                self.waypoint_selected.emit("staged", idx, wx, wy, wtag)
                self.update()
                return

        # Check clicks on accepted waypoints
        for idx, (ax, ay) in enumerate(self.accepted_waypoints):
            pt_x = ax / ARENA_WIDTH_M * w
            pt_y = (1.0 - ay / ARENA_HEIGHT_M) * h
            if math.hypot(pos.x() - pt_x, pos.y() - pt_y) < 18:
                self.selected_waypoint = ("accepted", idx, ax, ay, f"WP-{idx+1}")
                self.waypoint_selected.emit("accepted", idx, ax, ay, f"WP-{idx+1}")
                self.update()
                return

        # Check clicks on survivors (only localized targets)
        for s in self.active_survivors:
            if s.get("x") is None or s.get("y") is None or s.get("status") in {"SEARCHING", "NOT DETECTED", "—"}:
                continue
            sx = float(s["x"]) / ARENA_WIDTH_M * w
            sy = (1.0 - float(s["y"]) / ARENA_HEIGHT_M) * h
            dx = pos.x() - sx
            dy = pos.y() - sy
            if math.hypot(dx, dy) < 22:
                sid = str(s.get("id", "S01"))
                self.survivor_clicked.emit(sid)
                self.select_survivor(sid)
                return

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        w, h = rect.width(), rect.height()

        # 1. Base map background
        if not self.bg_pixmap.isNull():
            p.drawPixmap(rect, self.bg_pixmap)
        else:
            p.fillRect(rect, QColor("#e2e8f0"))

        # 2. Accepted Autonomous Waypoint Route Path
        if self.layer_path and self.accepted_waypoints:
            last_pt: Optional[QPointF] = None
            for idx, (ax, ay) in enumerate(self.accepted_waypoints):
                cur_pt = QPointF(ax / ARENA_WIDTH_M * w, (1.0 - ay / ARENA_HEIGHT_M) * h)
                if last_pt:
                    if idx <= self.active_waypoint_idx:
                        p.setPen(QPen(QColor(PALETTE["cyan"]), 2.2, Qt.PenStyle.SolidLine))
                    else:
                        p.setPen(QPen(QColor("#2563eb"), 1.8, Qt.PenStyle.SolidLine))
                    p.drawLine(last_pt, cur_pt)

                # Differentiate completed, active, and pending waypoints
                if idx in self.completed_waypoints:
                    p.setPen(QPen(QColor(PALETTE["green"]), 1.8))
                    p.setBrush(QBrush(QColor(PALETTE["green_soft"])))
                    p.drawEllipse(cur_pt, 4.0, 4.0)
                elif idx == self.active_waypoint_idx:
                    pulse_r = 7.0 + 3.0 * math.sin(self.pulse_phase * 2)
                    p.setPen(QPen(QColor(PALETTE["cyan"]), 2.0))
                    p.setBrush(QBrush(QColor(2, 132, 199, 40)))
                    p.drawEllipse(cur_pt, pulse_r, pulse_r)
                    p.setPen(QPen(QColor(PALETTE["cyan"]), 2.0))
                    p.setBrush(QBrush(QColor("#ffffff")))
                    p.drawEllipse(cur_pt, 4.5, 4.5)
                else:
                    p.setPen(QPen(QColor("#2563eb"), 1.6))
                    p.setBrush(QBrush(QColor("#ffffff")))
                    p.drawEllipse(cur_pt, 4.0, 4.0)

                p.setFont(QFont("Segoe UI", 5, QFont.Weight.Bold))
                p.setPen(QColor(PALETTE["muted"]))
                wp_lbl = "START" if idx == 0 else f"WP-{idx+1}"
                p.drawText(QRectF(cur_pt.x() + 5, cur_pt.y() - 5, 38, 10), Qt.AlignmentFlag.AlignVCenter, wp_lbl)
                last_pt = cur_pt

        # 3. Staged Waypoint Flight Lines
        if self.layer_staged and self.staged_waypoints:
            p.setPen(QPen(QColor(PALETTE["amber"]), 2.0, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            drone_pt = QPointF(self.drone_pos[0] / ARENA_WIDTH_M * w, (1.0 - self.drone_pos[1] / ARENA_HEIGHT_M) * h)
            last_pt = drone_pt
            for wx, wy, wtag in self.staged_waypoints:
                curr_pt = QPointF(wx / ARENA_WIDTH_M * w, (1.0 - wy / ARENA_HEIGHT_M) * h)
                p.drawLine(last_pt, curr_pt)
                p.setPen(QPen(QColor(PALETTE["amber"]), 1.8))
                p.setBrush(QBrush(QColor("#ffffff")))
                p.drawEllipse(curr_pt, 6, 6)
                p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                p.setPen(QColor(PALETTE["ink"]))
                p.drawText(QRectF(curr_pt.x() + 8, curr_pt.y() - 8, 80, 16), Qt.AlignmentFlag.AlignVCenter, f"{wtag} [STAGED]")
                last_pt = curr_pt

        # 4. Highlight Selected Waypoint
        if self.selected_waypoint:
            w_type, w_idx, wx, wy, wtag = self.selected_waypoint
            sel_pt = QPointF(wx / ARENA_WIDTH_M * w, (1.0 - wy / ARENA_HEIGHT_M) * h)
            p.setPen(QPen(QColor("#2563eb"), 2.0, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(37, 99, 235, 30)))
            p.drawEllipse(sel_pt, 12, 12)

        # 5. Survivors & Sonar Beacons (Only localized/detected targets)
        if self.layer_survivors:
            for s in self.active_survivors:
                if s.get("x") is None or s.get("y") is None:
                    continue
                if s.get("status") in {"SEARCHING", "NOT DETECTED", "—"}:
                    continue
                sid = str(s.get("id", "S01"))
                sx = float(s["x"]) / ARENA_WIDTH_M * w
                sy = (1.0 - float(s["y"]) / ARENA_HEIGHT_M) * h
                col_hex = s.get("color_hex", "#10b981")
                status = str(s.get("status", "STABLE")).upper()

                # Sonar pulse for active targets
                if self.layer_sonar and (status in {"MOVING", "LOST"} or sid == "S04"):
                    pulse_r = 14.0 + 8.0 * math.sin(self.pulse_phase)
                    pulse_col = QColor(PALETTE["amber"]) if status == "LOST" else QColor(239, 68, 68, 160)
                    p.setPen(QPen(pulse_col, 1.5, Qt.PenStyle.DashLine))
                    p.setBrush(QBrush(QColor(pulse_col.red(), pulse_col.green(), pulse_col.blue(), 20)))
                    p.drawEllipse(QPointF(sx, sy), pulse_r, pulse_r)

                # Survivor pin
                p.setPen(QPen(QColor(col_hex), 2.0))
                p.setBrush(QBrush(QColor("#ffffff")))
                p.drawEllipse(QPointF(sx, sy), 7, 7)

                p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                p.setPen(QColor(col_hex))
                p.drawText(QRectF(sx - 10, sy - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, sid)

                # Selected beacon ring
                if sid == self.selected_target:
                    beacon_r = 20.0 + 4.0 * math.cos(self.pulse_phase * 2)
                    p.setPen(QPen(QColor("#2563eb"), 2.0))
                    p.setBrush(QBrush(QColor(37, 99, 235, 30)))
                    p.drawEllipse(QPointF(sx, sy), beacon_r, beacon_r)

        # 6. Dynamic Drone Marker & LiDAR Sweep
        if self.layer_drone:
            dx = self.drone_pos[0] / ARENA_WIDTH_M * w
            dy = (1.0 - self.drone_pos[1] / ARENA_HEIGHT_M) * h
            drone_pt = QPointF(dx, dy)

            # Rotating LiDAR Sweep Fan
            if self.layer_lidar:
                p.setPen(Qt.PenStyle.NoPen)
                sweep_grad = QRadialGradient(drone_pt, 50)
                sweep_grad.setColorAt(0, QColor(2, 132, 199, 70))
                sweep_grad.setColorAt(1, QColor(2, 132, 199, 0))
                p.setBrush(QBrush(sweep_grad))
                p.drawPie(QRectF(dx - 50, dy - 50, 100, 100), int(math.degrees(self.scan_sweep) * 16), 45 * 16)

            # Drone Quadcopter Icon
            p.save()
            p.translate(drone_pt)
            p.rotate(self.drone_yaw)

            p.setPen(QPen(QColor(PALETTE["blue"]), 2.2))
            p.setBrush(QBrush(QColor("#ffffff")))
            p.drawEllipse(QPointF(0, 0), 6, 6)

            p.drawLine(QPointF(-7, -7), QPointF(7, 7))
            p.drawLine(QPointF(-7, 7), QPointF(7, -7))

            p.setPen(QPen(QColor(PALETTE["cyan"]), 1.2))
            for rx, ry in [(-7, -7), (7, -7), (-7, 7), (7, 7)]:
                p.drawEllipse(QPointF(rx, ry), 3, 3)

            p.setPen(QPen(QColor(PALETTE["danger"]), 2.2))
            p.drawLine(QPointF(0, -6), QPointF(0, -12))
            p.restore()

        # 7. Metric Scale Bar (Bottom Left)
        scale_w = (3.0 / ARENA_WIDTH_M) * w
        scale_y = h - 16
        p.setPen(QPen(QColor(PALETTE["ink"]), 1.5))
        p.drawLine(QPointF(14, scale_y), QPointF(14 + scale_w, scale_y))
        p.drawLine(QPointF(14, scale_y - 3), QPointF(14, scale_y + 3))
        p.drawLine(QPointF(14 + scale_w, scale_y - 3), QPointF(14 + scale_w, scale_y + 3))
        p.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        p.drawText(QRectF(14, scale_y - 14, scale_w, 12), Qt.AlignmentFlag.AlignCenter, "3 METERS")

        # 8. Waypoint placement cursor banner
        if self.add_waypoint_mode:
            p.fillRect(QRectF(10, 10, 240, 22), QColor(37, 99, 235, 230))
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(10, 10, 240, 22), Qt.AlignmentFlag.AlignCenter, "📍 CLICK ON ARENA TO PLACE STAGED WAYPOINT")

        p.end()


# ==============================================================================
# 6. HARDWARE SUBSYSTEM ITEM WIDGET
# ==============================================================================
class SubsystemItemWidget(QFrame):
    """Row widget for hardware component with dynamic OK/SIM/WAITING capsule."""
    clicked = pyqtSignal(str)

    def __init__(self, icon_str: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("subsystemRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon_str)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 10, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color:{PALETTE['cyan']}; background:transparent;")
        layout.addWidget(icon_lbl)

        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.name_lbl.setStyleSheet(f"color:{PALETTE['ink']}; background:transparent;")
        layout.addWidget(self.name_lbl, 1)

        self.ok_badge = QLabel("OK")
        self.ok_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.ok_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ok_badge.setFixedHeight(18)
        self.ok_badge.setMinimumWidth(38)
        self.set_status("OK")
        layout.addWidget(self.ok_badge)

    def set_status(self, status: str) -> None:
        status_upper = status.upper()
        display_text = "OK (SIM)" if status_upper in {"SIM", "SIMULATED"} else status_upper
        self.ok_badge.setText(display_text)
        if "OK" in status_upper or "SIM" in status_upper:
            bg_col = "#10b981"
        elif "WAIT" in status_upper or "WARN" in status_upper:
            bg_col = "#f59e0b"
        else:
            bg_col = "#ef4444"

        self.ok_badge.setStyleSheet(f"""
            background-color: {bg_col};
            color: #ffffff;
            border-radius: 9px;
            padding: 1px 6px;
            font-weight: bold;
        """)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.name_lbl.text())


# ==============================================================================
# 7. REAL SETTINGS & CONFIGURATION DIALOG
# ==============================================================================
class SettingsDialog(QDialog):
    """Configuration dialog for switching data source and simulation controls."""

    def __init__(self, current_source: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NIDAR GCS — System Configuration & Data Source")
        self.resize(460, 320)
        self.current_source = current_source
        self.selected_source = current_source

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Telemetry & Bridge Data Source")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Select active telemetry source for the GCS interface:")
        desc.setFont(QFont("Segoe UI", 8))
        desc.setStyleSheet(f"color:{PALETTE['muted']};")
        layout.addWidget(desc)

        # Radio button options
        self.btn_group = QButtonGroup(self)

        self.rad_sim = QRadioButton("Simulation (Hardware-Free Local Deterministic Feed)")
        self.rad_ws = QRadioButton("WebSocket Bridge (ws://127.0.0.1:9090 — ROS 2 / Mock)")
        self.rad_file = QRadioButton("JSON File Watcher (data/mission.json)")

        for rad in (self.rad_sim, self.rad_ws, self.rad_file):
            rad.setFont(QFont("Segoe UI", 8))
            self.btn_group.addButton(rad)
            layout.addWidget(rad)

        if current_source == "Simulation":
            self.rad_sim.setChecked(True)
        elif current_source == "WebSocket":
            self.rad_ws.setChecked(True)
        else:
            self.rad_file.setChecked(True)

        layout.addSpacing(10)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply Configuration")
        apply_btn.setStyleSheet(f"background:{PALETTE['blue']}; color:#ffffff; font-weight:bold; padding:6px 14px; border-radius:4px;")
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        layout.addLayout(btn_row)

    def _on_apply(self) -> None:
        if self.rad_sim.isChecked():
            self.selected_source = "Simulation"
        elif self.rad_ws.isChecked():
            self.selected_source = "WebSocket"
        else:
            self.selected_source = "JSON file"
        self.accept()


# ==============================================================================
# 8. MAIN NIDAR RESCUE GCS APPLICATION
# ==============================================================================
class NidarRescueGCS(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NIDAR Rescue GCS — AI-Powered Human Detection & Rescue")
        self.resize(1340, 780)
        self.setMinimumSize(1100, 680)

        self.flight_seconds = 0
        self.flight_mode = "AUTONOMOUS"
        self.active_source = "Simulation"
        self.survivor_cards: Dict[str, SurvivorCard] = {}
        self.last_survivor_signature: str = ""
        self.selected_target_id: str = "S01"
        self.diagnostics_dialog: Optional[SubsystemDiagnosticsDialog] = None

        # 1. Initialize Data Plugins and WebSocket Client
        self.plugin_manager = DataPluginManager(Path("data"))
        self.ws_client = GCSClientWorker(url="ws://127.0.0.1:9090")
        self.health_manager = HealthSystemManager(is_simulation=(self.active_source == "Simulation"))
        self._setup_ws_connections()

        # 2. Build UI and apply styles
        self._build_ui()
        self._apply_theme()

        # 3. High-Frequency UI Data Loop (10 Hz)
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self._poll_data)
        self.data_timer.start(250)
        self._poll_data()

        # 4. Arena animation timer (30 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.map_canvas.tick_anim)
        self.anim_timer.timeout.connect(self.map_workspace.map_canvas.tick_anim)
        self.anim_timer.timeout.connect(self.camera.capture_video_frame)
        self.anim_timer.start(35)

        self.log_event("[SYSTEM] NIDAR Ground Control Station initialized in SIMULATION mode.")

    def _setup_ws_connections(self) -> None:
        self.ws_client.connected_signal.connect(self._on_ws_connected)
        self.ws_client.disconnected_signal.connect(self._on_ws_disconnected)
        self.ws_client.status_changed_signal.connect(self._on_ws_status_changed)
        self.ws_client.frame_received_signal.connect(self._on_ws_frame)
        self.ws_client.command_ack_signal.connect(self._on_command_ack)
        self.ws_client.error_signal.connect(lambda err: self.log_event(f"[COMM] Error: {err}"))

    def closeEvent(self, event) -> None:
        """Graceful shutdown of background workers and timers."""
        self.data_timer.stop()
        self.anim_timer.stop()
        if self.ws_client.isRunning():
            self.ws_client.stop()
        event.accept()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # 1. Full-Width Top Header
        main_layout.addWidget(self._header())

        # 2. Central Workspace Stack (Mission / Map / Survivors)
        self.view_stack = QStackedWidget()

        # Page 0: Complete Mission Dashboard (3-Column Layout + Bottom Bar)
        self.page_mission = QWidget()
        pm_layout = QVBoxLayout(self.page_mission)
        pm_layout.setContentsMargins(0, 0, 0, 0)
        pm_layout.setSpacing(6)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(8)
        columns_layout.addWidget(self._left_column(), 29)
        columns_layout.addWidget(self._center_column(), 46)
        columns_layout.addWidget(self._right_column(), 25)
        pm_layout.addLayout(columns_layout, 1)

        pm_layout.addWidget(self._bottom_bar())
        self.view_stack.addWidget(self.page_mission)

        # Page 1: Dedicated Map Workspace
        self.map_workspace = MapWorkspaceWidget(self)
        self.view_stack.addWidget(self.map_workspace)

        # Page 2: Dedicated Survivors Workspace
        self.survivors_workspace = SurvivorsWorkspaceWidget(self)
        self.view_stack.addWidget(self.survivors_workspace)

        main_layout.addWidget(self.view_stack, 1)

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

        row.addSpacing(14)

        # Horizontal Navigation Tabs: Mission, Map, Survivors
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

        row.addLayout(tabs_box)
        row.addStretch()

        # Flight Mode Dropdown Button
        self.mode_pill = QPushButton("● AUTONOMOUS  ⌄")
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
        self.mode_pill.clicked.connect(self.show_flight_mode_menu)
        row.addWidget(self.mode_pill)

        # Timer Pill
        self.timer_pill = QLabel("⏱ 00:00 / 30:00")
        self.timer_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.timer_pill.setStyleSheet(f"""
            color: {PALETTE['ink']};
            background: #ffffff;
            border: 1px solid {PALETTE['line']};
            border-radius: 11px;
            padding: 3px 10px;
        """)
        row.addWidget(self.timer_pill)

        # Dynamic Communication Status Pill
        self.comm_pill = QLabel("● SIMULATION (ACTIVE)")
        self.comm_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.comm_pill.setStyleSheet(f"""
            color: {PALETTE['cyan']};
            background: {PALETTE['blue_soft']};
            border: 1px solid {PALETTE['blue_border']};
            border-radius: 11px;
            padding: 3px 10px;
        """)
        row.addWidget(self.comm_pill)

        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(26, 26)
        settings_btn.setStyleSheet(f"""
            background: #ffffff;
            border: 1px solid {PALETTE['line']};
            border-radius: 13px;
            font-size: 10pt;
            color: {PALETTE['muted']};
        """)
        settings_btn.clicked.connect(self.open_settings)
        row.addWidget(settings_btn)

        return bar

    # --------------------------------------------------------------------------
    # Left Column: Drone Camera + Survivor Queue
    # --------------------------------------------------------------------------
    def _left_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Drone Camera Card
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

        self.camera = CameraSurface()
        self.camera.mode_changed.connect(self._sync_cam_buttons)
        cam_layout.addWidget(self.camera, 1)

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

        # 3. Dynamic Survivor Queue Card
        surv_card = card_frame()
        surv_card.setFixedHeight(275)
        self.surv_card_layout = QVBoxLayout(surv_card)
        self.surv_card_layout.setContentsMargins(8, 8, 8, 8)
        self.surv_card_layout.setSpacing(5)

        surv_head = QHBoxLayout()
        surv_icon = QLabel("👥")
        surv_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        surv_head.addWidget(surv_icon)
        surv_head.addWidget(label("SURVIVOR QUEUE", 8, True))
        surv_head.addStretch()

        self.found_badge = QLabel("● 0 / 6 DETECTED")
        self.found_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.found_badge.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 9px;
            padding: 2px 7px;
        """)
        surv_head.addWidget(self.found_badge)
        self.surv_card_layout.addLayout(surv_head)

        # Scroll Area for dynamic survivor cards
        self.surv_scroll = QScrollArea()
        self.surv_scroll.setObjectName("survScroll")
        self.surv_scroll.setWidgetResizable(True)
        self.surv_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.surv_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.surv_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.surv_scroll.setStyleSheet("""
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

        self.surv_container_widget = QWidget()
        self.surv_container_widget.setStyleSheet("background:transparent;")
        self.survivor_layout = QVBoxLayout(self.surv_container_widget)
        self.survivor_layout.setContentsMargins(0, 0, 0, 0)
        self.survivor_layout.setSpacing(4)
        self.survivor_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.surv_scroll.setWidget(self.surv_container_widget)
        self.surv_card_layout.addWidget(self.surv_scroll, 1)

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

        # 1. Arena Card
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
        layers_btn.clicked.connect(self.toggle_map_layers)
        head.addWidget(layers_btn)
        arena_layout.addLayout(head)

        self.map_canvas = MapCanvas()
        self.map_canvas.survivor_clicked.connect(self.focus_survivor)
        self.map_canvas.waypoint_added.connect(self._on_waypoint_added)
        self.map_canvas.waypoint_selected.connect(self._on_waypoint_selected)
        arena_layout.addWidget(self.map_canvas, 1)

        layout.addWidget(arena_card, 1)

        # 2. Sensor Status Strip
        sensor_card = card_frame()
        sensor_layout = QVBoxLayout(sensor_card)
        sensor_layout.setContentsMargins(10, 8, 10, 8)
        sensor_layout.setSpacing(6)

        head_s = QHBoxLayout()
        head_s.addWidget(label("SENSOR & DATA LINK STATUS", 8, True))
        head_s.addStretch()
        self.feed_type_lbl = label("LOCAL ENU · SYNTHETIC FEED", 6, False, PALETTE["muted"])
        head_s.addWidget(self.feed_type_lbl)
        sensor_layout.addLayout(head_s)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(6)
        self.sensor_pills: Dict[str, QPushButton] = {}
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
            """)
            pill.clicked.connect(lambda checked=False, s=name: self._on_sensor_pill_clicked(s))
            pills_row.addWidget(pill)
            self.sensor_pills[name] = pill

        sensor_layout.addLayout(pills_row)

        metric_bar = QHBoxLayout()
        metric_bar.setSpacing(10)

        metric_bar.addWidget(label("ARENA COVERAGE", 7, True, PALETTE["muted"]))
        self.cov_prog = QProgressBar()
        self.cov_prog.setRange(0, 100)
        self.cov_prog.setValue(0)
        self.cov_prog.setTextVisible(False)
        self.cov_prog.setFixedHeight(6)
        metric_bar.addWidget(self.cov_prog, 2)
        self.cov_lbl = label("0%", 8, True)
        metric_bar.addWidget(self.cov_lbl)

        metric_bar.addWidget(self._divider())
        metric_bar.addWidget(label("FRAME", 7, True, PALETTE["muted"]))
        metric_bar.addWidget(label("LOCAL ENU", 8, True))

        metric_bar.addWidget(self._divider())
        metric_bar.addWidget(label("SURVIVORS", 7, True, PALETTE["muted"]))
        self.surv_stat_lbl = label("0 / 6", 8, True)
        metric_bar.addWidget(self.surv_stat_lbl)

        metric_bar.addWidget(self._divider())
        metric_bar.addWidget(label("MISSION TIME", 7, True, PALETTE["muted"]))
        self.time_val_lbl = label("00:00", 8, True)
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

        # 1. Mission Status Card
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
        self.rtl_status_badge = QLabel("● AUTONOMOUS")
        self.rtl_status_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.rtl_status_badge.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 9px;
            padding: 2px 7px;
        """)
        s_head.addWidget(self.rtl_status_badge)
        stat_layout.addLayout(s_head)

        donut_row = QHBoxLayout()
        donut_row.setSpacing(10)
        self.donut = CircularProgressWidget(0)
        donut_row.addWidget(self.donut)

        donut_details = QVBoxLayout()
        donut_details.setSpacing(8)

        # Box 1: Mission Phase & Coverage Summary
        b1_row = QHBoxLayout()
        b1_row.setSpacing(6)
        w_icon = QLabel("⚠️")
        w_icon.setFixedSize(26, 26)
        w_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_icon.setStyleSheet("background: #fee2e2; border-radius: 5px;")
        b1_row.addWidget(w_icon)

        b1_txt = QVBoxLayout()
        b1_txt.setSpacing(0)
        self.phase_lbl = label("READY", 8, True)
        b1_txt.addWidget(self.phase_lbl)
        cov_row = QHBoxLayout()
        cov_row.setSpacing(4)
        self.cov_summary_lbl = label("0 / 6", 8, True, PALETTE["danger"])
        cov_row.addWidget(self.cov_summary_lbl)
        cov_row.addWidget(label("SURVIVORS", 6, False, PALETTE["danger"]))
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
        self.enu_coord_lbl = label("LOCAL ENU", 8, True, PALETTE["blue"])
        b2_txt.addWidget(self.enu_coord_lbl)
        self.enu_sub_lbl = label("X: 7.0m  Y: 6.0m", 6, False, PALETTE["muted"])
        b2_txt.addWidget(self.enu_sub_lbl)
        b2_row.addLayout(b2_txt, 1)
        donut_details.addLayout(b2_row)

        donut_row.addLayout(donut_details, 1)
        stat_layout.addLayout(donut_row)
        layout.addWidget(stat_card)

        # 2. Telemetry Card
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

        t_grid = QGridLayout()
        t_grid.setVerticalSpacing(3)
        t_grid.setHorizontalSpacing(8)

        self.telem_labels: Dict[str, QLabel] = {}
        pairs = [
            ("🔋 Battery", "—", "⚡ Voltage", "—"),
            ("⚙ Current", "—", "⛰ Altitude", "—"),
            ("🎮 Mode", "RTL / LAND", "🔗 Link", "—"),
            ("📶 Quality", "—", "💨 Speed", "—"),
            ("🧭 Heading", "—", "⏱ Flight", "00:00"),
            ("🛰 GPS", "OPT_FLOW", "📍 Position", "OK"),
        ]

        for row_idx, (k1, v1, k2, v2) in enumerate(pairs):
            t_grid.addWidget(label(k1, 7, False, PALETTE["muted"]), row_idx, 0)
            v1_lbl = label(v1, 7, True, PALETTE["ink"])
            self.telem_labels[k1] = v1_lbl
            t_grid.addWidget(v1_lbl, row_idx, 1)

            t_grid.addWidget(label(k2, 7, False, PALETTE["muted"]), row_idx, 2)
            v2_lbl = label(v2, 7, True, PALETTE["ink"])
            self.telem_labels[k2] = v2_lbl
            t_grid.addWidget(v2_lbl, row_idx, 3)

        telem_layout.addLayout(t_grid)
        layout.addWidget(telem_card)

        # 3. Hardware Subsystem Health Card
        health_card = card_frame()
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(10, 8, 10, 8)
        health_layout.setSpacing(4)

        h_head = QHBoxLayout()
        h_icon = QLabel("⚙")
        h_icon.setStyleSheet(f"color:{PALETTE['blue']};")
        h_head.addWidget(h_icon)
        h_head.addWidget(label("HARDWARE SUBSYSTEM HEALTH", 8, True))
        h_head.addStretch()
        h_head.addWidget(label("10 UNITS · INTERACTIVE", 6, False, PALETTE["muted"]))
        health_layout.addLayout(h_head)

        health_scroll = QScrollArea()
        health_scroll.setWidgetResizable(True)
        health_scroll.setFrameShape(QFrame.Shape.NoFrame)
        health_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        health_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        health_scroll.setStyleSheet("""
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

        health_container = QWidget()
        health_container.setStyleSheet("background:transparent;")
        health_list_layout = QVBoxLayout(health_container)
        health_list_layout.setContentsMargins(0, 0, 0, 0)
        health_list_layout.setSpacing(3)

        self.health_widgets: Dict[str, SubsystemItemWidget] = {}
        units = [
            ("💻", "Jetson Orin"),
            ("🎮", "RadioLink CrossFlight"),
            ("🔋", "Power & Battery"),
            ("◎", "RPLIDAR C1"),
            ("🧭", "IMU / GPS Localisation"),
            ("📷", "Camera & Gimbal"),
            ("::", "ROS 2 Bridge"),
            ("🔗", "MAVLink"),
            ("👁", "AI Detection Pipeline"),
            ("🗺️", "SLAM & Mapping"),
            ("(((•)))", "Obstacle Radar"),
        ]
        for icon_str, name in units:
            w = SubsystemItemWidget(icon_str, name)
            w.clicked.connect(self._on_subsystem_clicked)
            self.health_widgets[name] = w
            health_list_layout.addWidget(w)

        # Legacy alias for backward compatibility
        self.health_widgets["Jetson Gimbal / Mount"] = self.health_widgets["Camera & Gimbal"]

        health_scroll.setWidget(health_container)
        health_layout.addWidget(health_scroll, 1)

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

        # 1. Mission Event Log
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

        layout.addWidget(log_card, 38)

        # 2. Quick Actions
        action_card = card_frame()
        action_card.setFixedHeight(108)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(10, 8, 10, 8)
        action_layout.setSpacing(6)

        qa_head = QHBoxLayout()
        qa_head.addWidget(label("QUICK ACTIONS", 8, True))
        qa_head.addStretch()
        self.qa_status_lbl = QLabel("● SIMULATION - READY")
        self.qa_status_lbl.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['green']};")
        qa_head.addWidget(self.qa_status_lbl)
        action_layout.addLayout(qa_head)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        self.btn_qa_start = QPushButton("🚀  Start Mission")
        self.btn_qa_start.setObjectName("actionBtn")
        self.btn_qa_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qa_start.clicked.connect(self.start_autonomous_mission)
        btns_row.addWidget(self.btn_qa_start)

        self.btn_qa_pause = QPushButton("⏸  Pause Hold")
        self.btn_qa_pause.setObjectName("actionBtn")
        self.btn_qa_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qa_pause.clicked.connect(self.pause_mission)
        btns_row.addWidget(self.btn_qa_pause)

        self.btn_qa_resume = QPushButton("▶  Resume")
        self.btn_qa_resume.setObjectName("actionBtn")
        self.btn_qa_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qa_resume.clicked.connect(self.resume_mission)
        btns_row.addWidget(self.btn_qa_resume)

        self.btn_qa_rtl = QPushButton("🏠  Return Home")
        self.btn_qa_rtl.setObjectName("actionBtn")
        self.btn_qa_rtl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qa_rtl.clicked.connect(self.return_to_home)
        btns_row.addWidget(self.btn_qa_rtl)

        self.btn_qa_reset = QPushButton("🔄  Reset Sim")
        self.btn_qa_reset.setObjectName("actionBtn")
        self.btn_qa_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qa_reset.clicked.connect(self.reset_mission)
        btns_row.addWidget(self.btn_qa_reset)

        action_layout.addLayout(btns_row)
        layout.addWidget(action_card, 42)

        # 3. Emergency Abort Card
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
        abort_txt.setSpacing(2)
        a_title = QLabel("EMERGENCY ABORT")
        a_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        a_title.setStyleSheet("color: #ffffff; background: transparent;")
        abort_txt.addWidget(a_title)

        a_sub = QLabel("RTL - LAND HERE")
        a_sub.setFont(QFont("Segoe UI", 7))
        a_sub.setStyleSheet("color: #ffffff; background: transparent; opacity: 0.9;")
        abort_txt.addWidget(a_sub)

        a_sim_badge = QLabel("[SIMULATION ONLY]")
        a_sim_badge.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        a_sim_badge.setStyleSheet("color: #fecaca; background: transparent;")
        abort_txt.addWidget(a_sim_badge)

        abort_layout.addLayout(abort_txt)

        abort_arrow = QLabel("›")
        abort_arrow.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        abort_arrow.setStyleSheet("color: #ffffff; background: transparent;")
        abort_layout.addWidget(abort_arrow)

        self.abort_card.mousePressEvent = lambda e: self.emergency_abort()  # type: ignore[method-assign]
        layout.addWidget(self.abort_card, 20)

        return row

    def _append_log_row(self, time_str: str, text_str: str, cat: str, cat_c: str, cat_bg: str, cat_b: str) -> None:
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
                background: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #475569;
                padding: 4px 14px;
                font-weight: bold;
            }}
            QPushButton#navTab:hover {{
                background: #f1f5f9;
                color: #0f172a;
                border-color: #94a3b8;
            }}
            QPushButton#navTab:focus {{
                outline: 2px solid #bfdbfe;
            }}
            QPushButton#navTab[active='true'] {{
                background: {PALETTE['blue']};
                color: #ffffff;
                border-color: #1d4ed8;
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
            QFrame#subsystemRow:hover {{
                background: #f1f5f9;
                border-color: #cbd5e1;
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
            QPushButton#actionBtn:disabled {{
                background: #f8fafc;
                border-color: #e2e8f0;
                color: #94a3b8;
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
    # Central Data Polling & Processing
    # --------------------------------------------------------------------------
    def _poll_data(self) -> None:
        """Called every 100ms. Reads telemetry from the active source and updates the GUI."""
        if self.active_source == "WebSocket":
            if self.ws_client.is_stale():
                self._update_comm_status("STALE")
            return

        # Poll plugin manager (Simulation or JSON file)
        res = self.plugin_manager.poll()
        if res.frame:
            self._apply_frame(res.frame)

    def _apply_frame(self, frame: Dict[str, Any]) -> None:
        """Central data-binding pipeline updating all widgets truthfully."""
        # 1. Flight mode & Phase
        mode = frame.get("mode") or frame.get("telemetry", {}).get("mode", self.flight_mode)
        self.flight_mode = mode
        self._update_flight_mode_ui()

        phase = frame.get("phase", "EXPLORING")
        self.phase_lbl.setText(phase.upper())

        # 2. Mission Time
        mission_sec = frame.get("mission_seconds", self.flight_seconds)
        self.flight_seconds = mission_sec
        mins = mission_sec // 60
        secs = mission_sec % 60
        time_str = f"{mins:02d}:{secs:02d}"
        self.timer_pill.setText(f"⏱ {time_str} / 30:00")
        self.time_val_lbl.setText(time_str)
        if "⏱ Flight" in self.telem_labels:
            self.telem_labels["⏱ Flight"].setText(time_str)

        # 3. Telemetry Grid
        telem = frame.get("telemetry", {})
        drone = frame.get("drone", {})

        bat_val = telem.get("battery", "—")
        if "🔋 Battery" in self.telem_labels:
            self.telem_labels["🔋 Battery"].setText(f"{bat_val}%" if bat_val != "—" else "—")

        volt_val = telem.get("voltage", "—")
        if "⚡ Voltage" in self.telem_labels:
            self.telem_labels["⚡ Voltage"].setText(f"{volt_val} V" if volt_val != "—" else "—")

        curr_val = telem.get("current", "—")
        if "⚙ Current" in self.telem_labels:
            self.telem_labels["⚙ Current"].setText(f"{curr_val} A" if curr_val != "—" else "—")

        alt_val = drone.get("altitude") or telem.get("altitude", "—")
        if "⛰ Altitude" in self.telem_labels:
            self.telem_labels["⛰ Altitude"].setText(f"{alt_val} m" if alt_val != "—" else "—")

        link_val = telem.get("link_ms", "—")
        if "🔗 Link" in self.telem_labels:
            self.telem_labels["🔗 Link"].setText(f"{link_val} ms" if link_val != "—" else "—")

        qual_val = telem.get("quality", "—")
        if "📶 Quality" in self.telem_labels:
            self.telem_labels["📶 Quality"].setText(f"{qual_val}%" if qual_val != "—" else "—")

        spd_val = drone.get("speed") or telem.get("speed", "—")
        if "💨 Speed" in self.telem_labels:
            self.telem_labels["💨 Speed"].setText(f"{spd_val} m/s" if spd_val != "—" else "—")

        hdg_val = drone.get("heading") or drone.get("yaw") or telem.get("heading", "—")
        if "🧭 Heading" in self.telem_labels:
            self.telem_labels["🧭 Heading"].setText(f"{hdg_val}°" if hdg_val != "—" else "—")

        # ENU coordinates box
        dx = drone.get("x", 7.0)
        dy = drone.get("y", 6.0)
        dz = drone.get("z", alt_val)
        self.enu_sub_lbl.setText(f"X: {dx:.1f}m  Y: {dy:.1f}m  Z: {dz:.1f}m" if isinstance(dx, (int, float)) else "X: —  Y: —")

        # 4. Coverage & Donut
        coverage = frame.get("coverage", 0)
        self.donut.set_value(coverage)
        self.cov_prog.setValue(coverage)
        self.cov_lbl.setText(f"{coverage}%")

        # 5. Survivors / Detections (Strictly 6 Designated Target Slots)
        survivors = frame.get("survivors") or frame.get("targets") or []
        self._sync_survivor_cards(survivors)

        detected_count = frame.get("detected_count")
        if detected_count is None:
            detected_count = sum(1 for s in survivors if str(s.get("status", "")).upper() in {"DETECTED", "TRACKING", "LOCALISED", "LOST", "FOUND", "STABLE", "MOVING"})
        total_targets = frame.get("total_targets", 6)

        self.found_badge.setText(f"● {detected_count} / {total_targets} DETECTED")
        self.surv_stat_lbl.setText(f"{detected_count} / {total_targets}")
        self.cov_summary_lbl.setText(f"{detected_count} / {total_targets}")

        # Summary color indicator
        if detected_count == 0:
            self.cov_summary_lbl.setStyleSheet(f"color: {PALETTE['danger']};")
        elif detected_count == total_targets:
            self.cov_summary_lbl.setStyleSheet(f"color: {PALETTE['green']};")
        else:
            self.cov_summary_lbl.setStyleSheet(f"color: {PALETTE['blue']};")

        # 6. Map Canvas Updates
        if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
            self.map_canvas.update_drone_state(dx, dy, float(hdg_val) if isinstance(hdg_val, (int, float)) else 0.0)
        self.map_canvas.update_survivors(survivors)

        staged_wp = frame.get("staged_waypoints", [])
        accepted_wp = frame.get("accepted_waypoints", [])
        active_wp_idx = frame.get("active_waypoint_idx", 0)
        completed_wp = frame.get("completed_waypoints", [])
        self.map_canvas.update_waypoints(staged_wp, accepted_wp, active_wp_idx, completed_wp)

        # 7. Camera Detections & Consistent Telemetry Overlay
        self.camera.set_detections(survivors)
        self.camera.set_telemetry({
            "altitude": alt_val,
            "speed": spd_val,
            "heading": hdg_val,
            "battery": bat_val,
        })
        self.camera.is_simulated_stream = (self.active_source == "Simulation")

        # 8. Subsystem Health & Diagnostics System
        if hasattr(self, "health_manager"):
            self.health_manager.update_from_telemetry_frame(frame)
            self.health_manager.evaluate_all_freshness()
            for name, widget in self.health_widgets.items():
                real_name = "Camera & Gimbal" if name == "Jetson Gimbal / Mount" else name
                sub = self.health_manager.get_subsystem(real_name)
                if sub:
                    widget.set_status(sub.current_state.value)

            if hasattr(self, "diagnostics_dialog") and self.diagnostics_dialog and self.diagnostics_dialog.isVisible():
                self.diagnostics_dialog.refresh()

        # 9. Workspace Synchronizations
        if hasattr(self, "map_workspace"):
            self.map_workspace.sync_frame_data(frame)

        if hasattr(self, "survivors_workspace"):
            self.survivors_workspace.sync_frame_data(frame)

        # 10. Feed label
        src_label = frame.get("source_label", "SYNTHETIC FEED")
        self.feed_type_lbl.setText(f"LOCAL ENU · {src_label.upper()}")

    def _sync_survivor_cards(self, survivors: List[Dict[str, Any]]) -> None:
        """Dynamically add, remove, or update survivor cards based on live events."""
        sig = repr([(s.get("id"), s.get("status"), s.get("is_stale"), s.get("confidence")) for s in survivors])
        if sig == self.last_survivor_signature:
            return
        self.last_survivor_signature = sig

        # Clear existing layout
        while self.survivor_layout.count():
            item = self.survivor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.survivor_cards.clear()

        if not survivors:
            empty_lbl = QLabel("No active detections.\nSimulation scanner active...")
            empty_lbl.setFont(QFont("Segoe UI", 7))
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"color:{PALETTE['muted']}; padding:20px;")
            self.survivor_layout.addWidget(empty_lbl)
            return

        for s in survivors:
            sid = str(s.get("id", "S01"))
            num = str(s.get("number", sid.lstrip("S") or "01"))
            grid = str(s.get("grid", "—"))
            conf_val = s.get("confidence")
            conf = f"{conf_val}%" if conf_val is not None else ""
            status = str(s.get("status", "SEARCHING")).upper()
            is_stale = bool(s.get("is_stale", False))

            lat = s.get("lat")
            lon = s.get("lon")
            x = s.get("x")
            y = s.get("y")
            loc_tag = s.get("loc_status", "CONFIRMED" if (x is not None and y is not None) else "UNAVAILABLE")
            if lat is not None and lon is not None:
                coords_str = f"Lat: {lat:.4f}  Lon: {lon:.4f}"
            elif x is not None and y is not None:
                coords_str = f"ENU: {x:.1f}m, {y:.1f}m"
            else:
                coords_str = "Coordinates Unavailable"

            col_hex = s.get("color_hex", "#10b981") if status not in {"SEARCHING", "NOT DETECTED", "—"} else "#94a3b8"
            thumb = s.get("thumb", "assets/thumb_s1.png")

            card = SurvivorCard(sid, num, grid, conf, status, coords_str, col_hex, thumb, is_stale=is_stale)
            card.selected.connect(self.focus_survivor)
            self.survivor_cards[sid] = card
            self.survivor_layout.addWidget(card)

    # --------------------------------------------------------------------------
    # WebSocket Event Handlers
    # --------------------------------------------------------------------------
    def _on_ws_connected(self) -> None:
        self._update_comm_status("CONNECTED")
        self.log_event("[COMM] Connected to ROS 2 GCS WebSocket Bridge (10 Hz).")

    def _on_ws_disconnected(self) -> None:
        self._update_comm_status("DISCONNECTED")
        self.log_event("[COMM] Disconnected from ROS 2 GCS WebSocket Bridge.")

    def _on_ws_status_changed(self, status: str) -> None:
        self._update_comm_status(status)

    def _on_ws_frame(self, frame: Dict[str, Any]) -> None:
        if self.active_source == "WebSocket":
            frame["source_type"] = "WEBSOCKET"
            frame["source_label"] = "LIVE WEBSOCKET BRIDGE"
            self._apply_frame(frame)

    def _on_command_ack(self, ack: Dict[str, Any]) -> None:
        cmd = ack.get("command", "")
        status = ack.get("status", "")
        msg = ack.get("message", "")
        self.log_event(f"[COMMAND ACK] {cmd} -> {status}: {msg}")

    def _update_comm_status(self, status: str) -> None:
        if self.active_source == "Simulation":
            self.comm_pill.setText("● SIMULATION (ACTIVE)")
            self.comm_pill.setStyleSheet(f"""
                color: {PALETTE['cyan']};
                background: {PALETTE['blue_soft']};
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 11px;
                padding: 3px 10px;
            """)
            self.qa_status_lbl.setText("● SIMULATION - READY")
            self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['green']};")
        elif status == "CONNECTED":
            self.comm_pill.setText("📶 COMM: CONNECTED (98%)")
            self.comm_pill.setStyleSheet(f"""
                color: {PALETTE['green']};
                background: {PALETTE['green_soft']};
                border: 1px solid {PALETTE['green_border']};
                border-radius: 11px;
                padding: 3px 10px;
            """)
            self.qa_status_lbl.setText("● BRIDGE CONNECTED")
            self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['green']};")
        elif status == "CONNECTING":
            self.comm_pill.setText("⏳ COMM: CONNECTING...")
            self.comm_pill.setStyleSheet(f"""
                color: {PALETTE['amber']};
                background: {PALETTE['amber_soft']};
                border: 1px solid {PALETTE['amber_border']};
                border-radius: 11px;
                padding: 3px 10px;
            """)
            self.qa_status_lbl.setText("⏳ CONNECTING...")
            self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['amber']};")
        elif status == "STALE":
            self.comm_pill.setText("⚠️ COMM: STALE (>3s)")
            self.comm_pill.setStyleSheet(f"""
                color: {PALETTE['amber']};
                background: {PALETTE['amber_soft']};
                border: 1px solid {PALETTE['amber_border']};
                border-radius: 11px;
                padding: 3px 10px;
            """)
            self.qa_status_lbl.setText("⚠️ DATA STALE")
            self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['amber']};")
        else:
            self.comm_pill.setText("⚠️ COMM: DISCONNECTED")
            self.comm_pill.setStyleSheet(f"""
                color: {PALETTE['danger']};
                background: {PALETTE['danger_soft']};
                border: 1px solid {PALETTE['danger_border']};
                border-radius: 11px;
                padding: 3px 10px;
            """)
            self.qa_status_lbl.setText("● DISCONNECTED")
            self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['danger']};")

    # --------------------------------------------------------------------------
    # Interactive Handlers & Slots
    # --------------------------------------------------------------------------
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.active_source, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_source = dlg.selected_source
            if new_source != self.active_source:
                self.active_source = new_source
                self.log_event(f"[SYSTEM] Switched telemetry source to {new_source}.")
                if new_source == "WebSocket":
                    if not self.ws_client.isRunning():
                        self.ws_client.start()
                else:
                    self.plugin_manager.select(new_source)
                self._update_comm_status("CONNECTED" if new_source == "Simulation" else "CONNECTING")

    def show_flight_mode_menu(self) -> None:
        menu = QMenu(self)
        modes = [
            ("🚀 AUTONOMOUS (Start / Resume Search)", "START_MISSION"),
            ("⏸ PAUSE / SAFE HOLD (Hover in Place)", "PAUSE_MISSION"),
            ("🏠 RETURN TO HOME (RTL to Launch Pad)", "RTL"),
            ("🛑 EMERGENCY ABORT (Immediate Touchdown)", "ABORT"),
        ]
        for title, cmd_key in modes:
            act = QAction(title, menu)
            act.triggered.connect(lambda checked, c=cmd_key: self._on_mode_menu_action(c))
            menu.addAction(act)
        menu.exec(QCursor.pos())

    def _on_mode_menu_action(self, cmd_key: str) -> None:
        if cmd_key == "START_MISSION":
            self.start_autonomous_mission()
        elif cmd_key == "PAUSE_MISSION":
            self.pause_mission()
        elif cmd_key == "RTL":
            self.return_to_home()
        elif cmd_key == "ABORT":
            self.emergency_abort()

    def _set_flight_mode(self, new_mode: str) -> None:
        if "MANUAL" in new_mode.upper():
            self.log_event("[MISSION] Manual flight mode rejected: Drone operates strictly under autonomous mission control.")
            return
        self.dispatch_command("SET_MODE", {"mode": new_mode})
        self.flight_mode = new_mode
        self._update_flight_mode_ui()
        self.log_event(f"[NAV] Flight mode transitioned to {new_mode}.")

    def toggle_map_layers(self) -> None:
        menu = QMenu(self)
        layers = [
            ("Metric Grid (15x15m)", "layer_grid"),
            ("Drone & LiDAR Scan", "layer_drone"),
            ("Accepted Flight Path", "layer_path"),
            ("Staged Waypoints", "layer_staged"),
            ("Survivor Markers", "layer_survivors"),
            ("Sonar Pulse Rings", "layer_sonar"),
        ]
        for title, attr in layers:
            act = QAction(title, menu)
            act.setCheckable(True)
            act.setChecked(getattr(self.map_canvas, attr))
            act.triggered.connect(lambda checked, a=attr: setattr(self.map_canvas, a, checked))
            menu.addAction(act)

        menu.addSeparator()
        commit_act = QAction("✔ Commit Staged Waypoints to Active Plan", menu)
        commit_act.triggered.connect(lambda: self.dispatch_command("COMMIT_WAYPOINTS"))
        menu.addAction(commit_act)

        clear_act = QAction("✖ Clear Staged Waypoints", menu)
        clear_act.triggered.connect(lambda: self.dispatch_command("CLEAR_WAYPOINTS"))
        menu.addAction(clear_act)

        menu.exec(QCursor.pos())

    def commit_staged_waypoints(self) -> None:
        self.dispatch_command("COMMIT_WAYPOINTS")
        self.log_event("[NAV] Staged waypoints committed to active exploration route.")

    def clear_staged_waypoints(self) -> None:
        self.dispatch_command("CLEAR_WAYPOINTS")
        self.map_canvas.staged_waypoints.clear()
        self.map_canvas.update()
        if hasattr(self, "map_workspace"):
            self.map_workspace.map_canvas.staged_waypoints.clear()
            self.map_workspace.map_canvas.update()
        self.log_event("[NAV] All staged waypoints cleared.")

    def _select_tab(self, name: str) -> None:
        self.tab_mission.setProperty("active", name == "Mission")
        self.tab_map.setProperty("active", name == "Map")
        self.tab_surv.setProperty("active", name == "Survivors")
        for btn in (self.tab_mission, self.tab_map, self.tab_surv):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if hasattr(self, "view_stack"):
            if name == "Map":
                self.view_stack.setCurrentIndex(1)
                if hasattr(self, "map_workspace"):
                    self.map_workspace.selected_target_id = self.selected_target_id
                    if self.selected_target_id:
                        self.map_workspace.map_canvas.select_survivor(self.selected_target_id)
            elif name == "Survivors":
                self.view_stack.setCurrentIndex(2)
                if hasattr(self, "survivors_workspace"):
                    if self.selected_target_id:
                        self.survivors_workspace.select_target(self.selected_target_id)
            else:
                self.view_stack.setCurrentIndex(0)

        if name == "Map":
            self.log_event("[NAV] Switched view tab to Map. 2D SLAM Arena view prioritized.")
        elif name == "Survivors":
            self.log_event("[VISION] Switched view tab to Survivors. Focus locked on detection queue.")
            if self.survivor_cards and not self.selected_target_id:
                first_sid = list(self.survivor_cards.keys())[0]
                self.focus_survivor(first_sid)
        else:
            self.log_event("[NAV] Switched view tab to Mission Dashboard overview.")

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
        filepath = self.camera.save_snapshot_to_disk()
        self.log_event(f"[CAM] Snapshot captured and saved: {filepath}")

    def toggle_recording(self) -> None:
        if not self.camera.is_recording:
            rec_path = self.camera.start_recording()
            self.rec_btn.setText("⏹ Stop")
            self.rec_btn.setStyleSheet("color: #ffffff; background: #dc2626; font-weight: bold;")
            self.log_event(f"[CAM] Video recording started: {rec_path}")
        else:
            frames, rec_path = self.camera.stop_recording()
            self.rec_btn.setText("● Record")
            self.rec_btn.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.log_event(f"[CAM] Video recording saved ({frames} frames): {rec_path}")

    def focus_survivor(self, survivor_id: str) -> None:
        self.selected_target_id = survivor_id
        for sid, card in self.survivor_cards.items():
            card.set_selected(sid == survivor_id)
        self.map_canvas.select_survivor(survivor_id)
        self.camera.set_highlight_person(survivor_id)
        if hasattr(self, "map_workspace"):
            self.map_workspace.selected_target_id = survivor_id
            self.map_workspace.map_canvas.select_survivor(survivor_id)
            self.map_workspace.refresh_target_rows()
        if hasattr(self, "survivors_workspace"):
            self.survivors_workspace.select_target(survivor_id)
        self.log_event(f"[VISION] Locked tracking onto survivor target {survivor_id}.")

    def start_add_waypoint(self) -> None:
        self.map_canvas.set_add_waypoint_mode(True)
        self.log_event("[NAV] Staging mode active: click on Arena Map to place a staged waypoint.")

    def _on_waypoint_added(self, metric_x: float, metric_y: float, tag: str) -> None:
        self.dispatch_command("STAGE_WAYPOINT", {"x": metric_x, "y": metric_y, "tag": tag})
        self.log_event(f"[NAV] Local waypoint staged at metric ({metric_x}m, {metric_y}m) [{tag}].")

    def _on_waypoint_selected(self, w_type: str, idx: int, x: float, y: float, tag: str) -> None:
        self.map_canvas.select_waypoint(w_type, idx, x, y, tag)
        self.log_event(f"[NAV] Waypoint selected: {tag} ({x:.1f}m, {y:.1f}m) [{w_type.upper()}].")

    def _on_sensor_pill_clicked(self, name: str) -> None:
        diagnostics = {
            "LiDAR": "RPLiDAR C1 360° 12m scanner: ACTIVE. 10 Hz scan rate. No obstacle breach.",
            "RADAR": "Optical-flow ground radar aid: NOMINAL. Ground clearance 2.40m.",
            "VISION": "Jetson Orin AI vision inference: STANDBY (Simulation stream active; no onboard model).",
            "WiFi": "2.4GHz / 5.8GHz telemetry link: NOMINAL. RSSI -48 dBm.",
            "MAVLink": "MAVLink v2 protocol: HEARTBEAT ACTIVE (1 Hz). MAV_STATE_ACTIVE.",
            "CONNECTED": "GCS primary telemetry link: NOMINAL. Packet loss 0.0%.",
        }
        info = diagnostics.get(name, "Status: OK.")
        self.log_event(f"[SENSOR] {name}: {info}")

    def _on_subsystem_clicked(self, name: str) -> None:
        details = {
            "Jetson Orin": "Edge AI Inference Host · Model: Standby (Simulated Feed) · GPU: 38% · Temp: 44°C",
            "Jetson Gimbal / Mount": "2-Axis Brushless Gimbal · Pitch: -45° · Roll: 0° · Stabilization: ACTIVE",
            "RadioLink CrossFlight": "ArduPilot Autopilot · Chibios · Heartbeat: 1.0 Hz · Flight Mode: GUIDED",
            "Power & Battery System": "4S LiPo Power Module · 15.6V · 14.2A · 86% Capacity · Cell Delta: 12mV",
            "RPLIDAR C1": "DTOF 360° Laser Scanner · Range: 12m · Freq: 10 Hz · Obstacles: None",
            "IMU / GPS / Localisation": "9-DOF EKF3 Localisation · RTK Fix · Sats: 14 · ENU Frame",
            "Camera & Gimbal": "1080p Sony Sensor · 30 FPS · 2-Axis Gimbal · Pitch: -45° · Roll: 0°",
            "ROS 2 Bridge": "Micro-ROS / rclpy WebSocket Bridge · Port: 9090 · Topic Latency: 22ms",
            "MAVLink": "MAVLink v2 Protocol · Baud: 115200 · Heartbeat: 1 Hz · State: ACTIVE",
            "AI Detection Pipeline": "YOLOv8-Rescue TensorRT · Infer: 28ms · Target Tracker: SORT ACTIVE",
            "SLAM & Mapping Pipeline": "Cartographer 2D LIDAR SLAM · Map Res: 5cm · Loop Closure: ACTIVE",
            "Obstacle Radar": "Subsystem NOT CONFIGURED on current airframe payload",
        }
        info = details.get(name, "Status: OK.")
        self.log_event(f"[SUBSYSTEM] {name}: {info}")
        self.show_subsystem_diagnostics(name)

    def show_subsystem_diagnostics(self, name: str) -> None:
        rec = self.health_manager.get_record(name)
        if not rec:
            return
        if self.diagnostics_dialog is None:
            self.diagnostics_dialog = SubsystemDiagnosticsDialog(
                subsystem_name=name,
                health_manager=self.health_manager,
                is_simulation=(self.active_source == "Simulation"),
                parent=self,
            )
            self.diagnostics_dialog.state_injected.connect(self._on_subsystem_state_injected)
        else:
            self.diagnostics_dialog.set_subsystem(name)
        self.diagnostics_dialog.show()
        self.diagnostics_dialog.raise_()
        self.diagnostics_dialog.activateWindow()

    def _on_subsystem_state_injected(self, name: str, state_str: str) -> None:
        state_enum = HealthState.from_str(state_str)
        self.health_manager.inject_state(name, state_enum)
        self.dispatch_command("SET_SUBSYSTEM_STATE", {"subsystem": name, "state": state_str})
        w = self.health_widgets.get(name)
        if w:
            rec = self.health_manager.get_record(name)
            if rec:
                w.update_record(rec)
        self.log_event(f"[DIAG] Subsystem diagnostic state injected: {name} -> {state_str}")

    def start_autonomous_mission(self) -> None:
        self.dispatch_command("START_MISSION")
        self.flight_mode = "AUTONOMOUS"
        if hasattr(self, "phase_lbl"):
            self.phase_lbl.setText("AUTONOMOUS SEARCH")
        self._update_flight_mode_ui()
        self.log_event("[MISSION] Autonomous search mission initiated. Target roster: S01-S06.")

    def pause_mission(self) -> None:
        self.dispatch_command("PAUSE_MISSION")
        self.flight_mode = "PAUSED / SAFE HOLD"
        self._update_flight_mode_ui()
        self.log_event("[MISSION] Mission paused. Drone entering safe hold hover.")

    def resume_mission(self) -> None:
        self.dispatch_command("RESUME_MISSION")
        self.flight_mode = "AUTONOMOUS"
        self._update_flight_mode_ui()
        self.log_event("[MISSION] Autonomous search mission resumed.")

    def return_to_home(self) -> None:
        ans = QMessageBox.question(
            self, "Return to Launch (RTL)",
            "Command Return-to-Launch (RTL)?\nThe drone will pause exploration and return to home base (1.5m, 1.5m).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.dispatch_command("RTL")
            self.flight_mode = "RETURNING HOME"
            self._update_flight_mode_ui()
            self.log_event("[MISSION] Return-to-Launch sequence commanded.")

    def reset_mission(self) -> None:
        ans = QMessageBox.question(
            self, "Reset Mission",
            "Reset Autonomous Search Mission Simulation?\nTelemetry and target detection roster will be reset to initial READY state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.dispatch_command("RESET_MISSION")
            self.flight_mode = "AUTONOMOUS"
            self._update_flight_mode_ui()
            self.log_event("[MISSION] Mission simulation reset to initial READY state.")

    def _update_flight_mode_ui(self) -> None:
        self.mode_pill.setText(f"● {self.flight_mode}  ⌄")
        if "RTL" in self.flight_mode or "RETURN" in self.flight_mode:
            self.mode_pill.setStyleSheet(f"""
                QPushButton#modePill {{
                    color: {PALETTE['amber']};
                    background: {PALETTE['amber_soft']};
                    border: 1px solid {PALETTE['amber_border']};
                    border-radius: 11px;
                    padding: 3px 10px;
                }}
            """)
        elif "EMERGENCY" in self.flight_mode or "ABORT" in self.flight_mode:
            self.mode_pill.setStyleSheet(f"""
                QPushButton#modePill {{
                    color: {PALETTE['danger']};
                    background: {PALETTE['danger_soft']};
                    border: 1px solid {PALETTE['danger_border']};
                    border-radius: 11px;
                    padding: 3px 10px;
                }}
            """)
        elif "PAUSE" in self.flight_mode or "HOLD" in self.flight_mode:
            self.mode_pill.setStyleSheet(f"""
                QPushButton#modePill {{
                    color: {PALETTE['amber']};
                    background: {PALETTE['amber_soft']};
                    border: 1px solid {PALETTE['amber_border']};
                    border-radius: 11px;
                    padding: 3px 10px;
                }}
            """)
        else:
            self.mode_pill.setStyleSheet(f"""
                QPushButton#modePill {{
                    color: {PALETTE['green']};
                    background: {PALETTE['green_soft']};
                    border: 1px solid {PALETTE['green_border']};
                    border-radius: 11px;
                    padding: 3px 10px;
                }}
            """)

        self.rtl_status_badge.setText(f"● {self.flight_mode}")
        if "🎮 Mode" in self.telem_labels:
            self.telem_labels["🎮 Mode"].setText(self.flight_mode)

        mode_upper = self.flight_mode.upper()
        if hasattr(self, "btn_qa_start"):
            if "ABORT" in mode_upper:
                self.btn_qa_start.setEnabled(False)
                self.btn_qa_pause.setEnabled(False)
                self.btn_qa_resume.setEnabled(False)
                self.btn_qa_rtl.setEnabled(False)
                self.btn_qa_reset.setEnabled(True)
                self.qa_status_lbl.setText("● SIMULATION - ABORTED")
                self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['danger']};")
            elif "PAUSE" in mode_upper or "HOLD" in mode_upper:
                self.btn_qa_start.setEnabled(False)
                self.btn_qa_pause.setEnabled(False)
                self.btn_qa_resume.setEnabled(True)
                self.btn_qa_rtl.setEnabled(True)
                self.btn_qa_reset.setEnabled(True)
                self.qa_status_lbl.setText("● SIMULATION - PAUSED")
                self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['amber']};")
            elif "RETURN" in mode_upper or "RTL" in mode_upper:
                self.btn_qa_start.setEnabled(False)
                self.btn_qa_pause.setEnabled(True)
                self.btn_qa_resume.setEnabled(False)
                self.btn_qa_rtl.setEnabled(False)
                self.btn_qa_reset.setEnabled(True)
                self.qa_status_lbl.setText("● SIMULATION - RETURNING HOME")
                self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['amber']};")
            elif "COMPLETE" in mode_upper:
                self.btn_qa_start.setEnabled(False)
                self.btn_qa_pause.setEnabled(False)
                self.btn_qa_resume.setEnabled(False)
                self.btn_qa_rtl.setEnabled(True)
                self.btn_qa_reset.setEnabled(True)
                self.qa_status_lbl.setText("● SIMULATION - COMPLETED")
                self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['green']};")
            elif "READY" in mode_upper or (hasattr(self, "phase_lbl") and self.phase_lbl.text().upper() in {"READY", "IDLE", "PRE-FLIGHT CHECKS"}):
                self.btn_qa_start.setEnabled(True)
                self.btn_qa_pause.setEnabled(False)
                self.btn_qa_resume.setEnabled(False)
                self.btn_qa_rtl.setEnabled(True)
                self.btn_qa_reset.setEnabled(True)
                self.qa_status_lbl.setText("● SIMULATION - READY")
                self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['green']};")
            else:
                self.btn_qa_start.setEnabled(False)
                self.btn_qa_pause.setEnabled(True)
                self.btn_qa_resume.setEnabled(False)
                self.btn_qa_rtl.setEnabled(True)
                self.btn_qa_reset.setEnabled(True)
                self.qa_status_lbl.setText("● SIMULATION - AUTONOMOUS ACTIVE")
                self.qa_status_lbl.setStyleSheet(f"color:{PALETTE['green']};")

    def emergency_abort(self) -> None:
        ans = QMessageBox.warning(
            self, "Emergency Abort",
            "DECLARE EMERGENCY ABORT (SIMULATED RTL / TOUCHDOWN)?\n\nImmediate simulated touchdown and motor kill will be executed.\n(Physical drone commands remain disabled).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.dispatch_command("ABORT")
            self.flight_mode = "ABORTED"
            self._update_flight_mode_ui()
            self.log_event("[ALERT] SIMULATED EMERGENCY ABORT CONFIRMED. Immediate touchdown in progress. Physical flight commands remain disabled.")

    def dispatch_command(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Route command to active source (WebSocket or Simulation plugin)."""
        if self.active_source == "WebSocket":
            self.ws_client.send_command(cmd, params)
        else:
            ack = self.plugin_manager.send_command(cmd, params)
            if ack.get("message"):
                self.log_event(f"[SIM COMMAND] {ack.get('message')}")

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
        elif "[COMM]" in msg:
            cat = "COMM"
            cat_c = PALETTE["purple"]
            cat_bg = PALETTE["purple_soft"]
            cat_b = PALETTE["purple_border"]
        elif "[SENSOR]" in msg or "[SUBSYSTEM]" in msg:
            cat = "INFO"
            cat_c = PALETTE["cyan"]
            cat_bg = PALETTE["blue_soft"]
            cat_b = PALETTE["blue_border"]

        self._append_log_row(now_str, msg, cat, cat_c, cat_bg, cat_b)

    def open_pilot_view(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("NIDAR Drone Camera — Pilot Reconnaissance View")
        dialog.resize(900, 560)
        v = QVBoxLayout(dialog)
        cam = CameraSurface()
        cam.set_mode(self.camera.mode)
        cam.set_detections(self.camera.active_detections)
        cam.set_telemetry(self.camera.telem_hud)
        cam.is_simulated_stream = self.camera.is_simulated_stream
        v.addWidget(cam, 1)
        dialog.exec()


def main() -> int:
    app = QApplication(sys.argv)
    window = NidarRescueGCS()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
