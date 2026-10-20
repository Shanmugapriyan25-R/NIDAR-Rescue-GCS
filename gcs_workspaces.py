#!/usr/bin/env python3
"""NIDAR Rescue GCS — Dedicated Map & Survivors Workspaces.

Provides dedicated full-size workspaces for:
1. Map Tab (MapWorkspaceWidget):
   - Enlarged 2D SLAM LiDAR Arena canvas
   - Real-time drone pose & heading banner
   - Planned route and waypoint markers with active/pending/accepted/completed states
   - Target markers with valid coordinates (or LOCATION UNAVAILABLE)
   - Coordinate grid (15x15m), scale bar, compass, and layer visibility controls
   - Localisation source & data freshness indicators
   - Interactive waypoint staging and marker selection

2. Survivors Tab (SurvivorsWorkspaceWidget):
   - Exactly six designated target identities (S01 - S06)
   - Real-time detection counters derived from valid detection events (0/6 to 6/6)
   - Detailed target cards with confidence, timestamps, tracking state, localisation state
   - Coordinates rendered only when valid (no fabricated coordinates)
   - Filter and search controls
   - Selected target visual evidence & tactical inspector
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget, QProgressBar
)

PALETTE = {
    "bg": "#f6f9fc",
    "card": "#ffffff",
    "card_alt": "#f8fafc",
    "ink": "#0f172a",
    "navy": "#1e293b",
    "muted": "#64748b",
    "line": "#e2e8f0",
    "blue": "#2563eb",
    "blue_soft": "#eff6ff",
    "blue_border": "#bfdbfe",
    "cyan": "#0284c7",
    "cyan_soft": "#f0f9ff",
    "cyan_border": "#bae6fd",
    "green": "#10b981",
    "green_soft": "#ecfdf5",
    "green_border": "#a7f3d0",
    "amber": "#f59e0b",
    "amber_soft": "#fffbeb",
    "amber_border": "#fde68a",
    "danger": "#ef4444",
    "danger_soft": "#fef2f2",
    "danger_border": "#fecaca",
    "purple": "#8b5cf6",
    "purple_soft": "#f5f3ff",
    "purple_border": "#ddd6fe",
}

DESIGNATED_TARGETS = ["S01", "S02", "S03", "S04", "S05", "S06"]


# ==============================================================================
# 1. DEDICATED MAP WORKSPACE WIDGET
# ==============================================================================
class MapWorkspaceWidget(QWidget):
    """Full dedicated workspace for 2D SLAM LiDAR Arena, Waypoints, and Tactical Map."""

    def __init__(self, main_window: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self.selected_target_id: Optional[str] = None
        self.selected_waypoint_info: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Top HUD Banner
        layout.addWidget(self._build_top_hud())

        # 2. Main Horizontal Workspace Split (Map on Left, Controls on Right)
        body = QHBoxLayout()
        body.setSpacing(8)

        # Left: Map Canvas Card
        map_card = QFrame()
        map_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 8px;
            }}
        """)
        m_layout = QVBoxLayout(map_card)
        m_layout.setContentsMargins(8, 8, 8, 8)
        m_layout.setSpacing(6)

        # Import MapCanvas from edith_gcs_qt
        from edith_gcs_qt import MapCanvas
        self.map_canvas = MapCanvas(self)
        self.map_canvas.survivor_clicked.connect(self._on_map_survivor_clicked)
        self.map_canvas.waypoint_added.connect(self._on_map_waypoint_added)
        self.map_canvas.waypoint_selected.connect(self._on_map_waypoint_selected)
        m_layout.addWidget(self.map_canvas, 1)

        # Map Toolbar Row
        tb_row = QHBoxLayout()
        tb_row.setSpacing(6)

        self.btn_stage_wp = QPushButton("📍  Stage Waypoint (Click Map)")
        self.btn_stage_wp.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_stage_wp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stage_wp.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['blue_soft']};
                color: {PALETTE['blue']};
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 5px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: #dbeafe;
            }}
        """)
        self.btn_stage_wp.clicked.connect(self._toggle_stage_mode)
        tb_row.addWidget(self.btn_stage_wp)

        btn_commit_wp = QPushButton("✓  Commit Route")
        btn_commit_wp.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        btn_commit_wp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_commit_wp.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['green_soft']};
                color: {PALETTE['green']};
                border: 1px solid {PALETTE['green_border']};
                border-radius: 5px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: #d1fae5;
            }}
        """)
        btn_commit_wp.clicked.connect(self._commit_waypoints)
        tb_row.addWidget(btn_commit_wp)

        btn_clear_wp = QPushButton("✕  Clear Staged")
        btn_clear_wp.setFont(QFont("Segoe UI", 8))
        btn_clear_wp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_wp.setStyleSheet(f"""
            QPushButton {{
                background-color: #ffffff;
                color: {PALETTE['muted']};
                border: 1px solid {PALETTE['line']};
                border-radius: 5px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: #f1f5f9;
                color: {PALETTE['ink']};
            }}
        """)
        btn_clear_wp.clicked.connect(self._clear_staged_waypoints)
        tb_row.addWidget(btn_clear_wp)

        tb_row.addStretch()

        self.sim_watermark = QLabel("SIMULATION ARENA · LOCAL ENU COORDINATES")
        self.sim_watermark.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.sim_watermark.setStyleSheet(f"color: {PALETTE['cyan']}; background: {PALETTE['cyan_soft']}; border: 1px solid {PALETTE['cyan_border']}; border-radius: 4px; padding: 2px 6px;")
        tb_row.addWidget(self.sim_watermark)

        m_layout.addLayout(tb_row)
        body.addWidget(map_card, 72)

        # Right: Side Control & Registry Panel
        body.addWidget(self._build_side_panel(), 28)
        layout.addLayout(body, 1)

    def _build_top_hud(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 6px;
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(10)

        title = QLabel("🗺️  2D SLAM ARENA & TACTICAL MAP")
        title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {PALETTE['ink']};")
        row.addWidget(title)

        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color: {PALETTE['line']};")
        row.addWidget(sep1)

        self.drone_pose_lbl = QLabel("DRONE POSE: X: 1.50m · Y: 1.50m · Z: 2.40m · HDG: 90.0° · SPD: 1.2 m/s")
        self.drone_pose_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.drone_pose_lbl.setStyleSheet(f"color: {PALETTE['blue']};")
        row.addWidget(self.drone_pose_lbl)

        row.addStretch()

        self.source_pill = QLabel("LOCAL ENU · 2D SLAM")
        self.source_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.source_pill.setStyleSheet(f"""
            color: {PALETTE['cyan']};
            background: {PALETTE['cyan_soft']};
            border: 1px solid {PALETTE['cyan_border']};
            border-radius: 9px;
            padding: 2px 8px;
        """)
        row.addWidget(self.source_pill)

        self.freshness_pill = QLabel("● FRESH (10 Hz)")
        self.freshness_pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.freshness_pill.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 9px;
            padding: 2px 8px;
        """)
        row.addWidget(self.freshness_pill)

        return bar

    def _build_side_panel(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Layer Visibility Controls Card
        layers_card = QFrame()
        layers_card.setStyleSheet(f"background-color:#ffffff; border:1px solid {PALETTE['line']}; border-radius:6px;")
        l_layout = QVBoxLayout(layers_card)
        l_layout.setContentsMargins(10, 8, 10, 8)
        l_layout.setSpacing(4)

        l_head = QLabel("MAP LAYER CONTROLS")
        l_head.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        l_head.setStyleSheet(f"color:{PALETTE['blue']};")
        l_layout.addWidget(l_head)

        grid_row = QGridLayout()
        grid_row.setSpacing(4)

        self.chk_grid = QCheckBox("15x15m Metric Grid")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self._on_layer_toggled)
        grid_row.addWidget(self.chk_grid, 0, 0)

        self.chk_drone = QCheckBox("Drone & LiDAR Sweep")
        self.chk_drone.setChecked(True)
        self.chk_drone.toggled.connect(self._on_layer_toggled)
        grid_row.addWidget(self.chk_drone, 0, 1)

        self.chk_path = QCheckBox("Planned Route")
        self.chk_path.setChecked(True)
        self.chk_path.toggled.connect(self._on_layer_toggled)
        grid_row.addWidget(self.chk_path, 1, 0)

        self.chk_staged = QCheckBox("Staged Waypoints")
        self.chk_staged.setChecked(True)
        self.chk_staged.toggled.connect(self._on_layer_toggled)
        grid_row.addWidget(self.chk_staged, 1, 1)

        self.chk_targets = QCheckBox("Survivor Markers")
        self.chk_targets.setChecked(True)
        self.chk_targets.toggled.connect(self._on_layer_toggled)
        grid_row.addWidget(self.chk_targets, 2, 0)

        self.chk_sonar = QCheckBox("Sonar Rings")
        self.chk_sonar.setChecked(True)
        self.chk_sonar.toggled.connect(self._on_layer_toggled)
        grid_row.addWidget(self.chk_sonar, 2, 1)

        l_layout.addLayout(grid_row)
        layout.addWidget(layers_card)

        # 2. Target Coordinate Registry Card
        target_card = QFrame()
        target_card.setStyleSheet(f"background-color:#ffffff; border:1px solid {PALETTE['line']}; border-radius:6px;")
        t_layout = QVBoxLayout(target_card)
        t_layout.setContentsMargins(10, 8, 10, 8)
        t_layout.setSpacing(4)

        t_head = QHBoxLayout()
        t_title = QLabel("DESIGNATED TARGET COORDINATES")
        t_title.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        t_title.setStyleSheet(f"color:{PALETTE['navy']};")
        t_head.addWidget(t_title)
        t_head.addStretch()
        self.target_badge = QLabel("0 / 6 LOCALIZED")
        self.target_badge.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        self.target_badge.setStyleSheet(f"color:{PALETTE['green']}; background:{PALETTE['green_soft']}; border-radius:6px; padding:1px 5px;")
        t_head.addWidget(self.target_badge)
        t_layout.addLayout(t_head)

        self.target_scroll = QScrollArea()
        self.target_scroll.setWidgetResizable(True)
        self.target_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.target_scroll.setFixedHeight(140)
        self.target_scroll.setStyleSheet("background:transparent; border:0;")

        self.target_rows_widget = QWidget()
        self.target_rows_widget.setStyleSheet("background:transparent;")
        self.target_rows_layout = QVBoxLayout(self.target_rows_widget)
        self.target_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.target_rows_layout.setSpacing(3)
        self.target_scroll.setWidget(self.target_rows_widget)
        t_layout.addWidget(self.target_scroll)

        layout.addWidget(target_card)

        # 3. Waypoint Route Registry Card
        wp_card = QFrame()
        wp_card.setStyleSheet(f"background-color:#ffffff; border:1px solid {PALETTE['line']}; border-radius:6px;")
        w_layout = QVBoxLayout(wp_card)
        w_layout.setContentsMargins(10, 8, 10, 8)
        w_layout.setSpacing(4)

        w_head = QLabel("AUTONOMOUS ROUTE & WAYPOINTS")
        w_head.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        w_head.setStyleSheet(f"color:{PALETTE['navy']};")
        w_layout.addWidget(w_head)

        self.wp_scroll = QScrollArea()
        self.wp_scroll.setWidgetResizable(True)
        self.wp_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.wp_scroll.setStyleSheet("background:transparent; border:0;")

        self.wp_rows_widget = QWidget()
        self.wp_rows_widget.setStyleSheet("background:transparent;")
        self.wp_rows_layout = QVBoxLayout(self.wp_rows_widget)
        self.wp_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.wp_rows_layout.setSpacing(2)
        self.wp_scroll.setWidget(self.wp_rows_widget)
        w_layout.addWidget(self.wp_scroll, 1)

        layout.addWidget(wp_card, 1)

        # 4. Map Legend Card
        legend_card = QFrame()
        legend_card.setFixedHeight(50)
        legend_card.setStyleSheet(f"background-color:#ffffff; border:1px solid {PALETTE['line']}; border-radius:6px;")
        lg_layout = QHBoxLayout(legend_card)
        lg_layout.setContentsMargins(8, 4, 8, 4)
        lg_layout.setSpacing(8)

        legend_items = [
            ("▲", "Drone", PALETTE["cyan"]),
            ("●", "Active WP", PALETTE["blue"]),
            ("✓", "Completed", PALETTE["green"]),
            ("◌", "Staged", PALETTE["amber"]),
            ("👥", "Localized", PALETTE["green"]),
            ("?", "Searching", PALETTE["muted"]),
        ]
        for icon, txt, c_color in legend_items:
            item = QLabel(f"<span style='color:{c_color}; font-weight:bold;'>{icon}</span> {txt}")
            item.setFont(QFont("Segoe UI", 6))
            item.setStyleSheet("background:transparent;")
            lg_layout.addWidget(item)
        lg_layout.addStretch()

        layout.addWidget(legend_card)
        return col

    def _on_layer_toggled(self) -> None:
        self.map_canvas.layer_grid = self.chk_grid.isChecked()
        self.map_canvas.layer_drone = self.chk_drone.isChecked()
        self.map_canvas.layer_path = self.chk_path.isChecked()
        self.map_canvas.layer_staged = self.chk_staged.isChecked()
        self.map_canvas.layer_survivors = self.chk_targets.isChecked()
        self.map_canvas.layer_sonar = self.chk_sonar.isChecked()
        self.map_canvas.update()

    def _toggle_stage_mode(self) -> None:
        mode = not self.map_canvas.add_waypoint_mode
        self.map_canvas.set_add_waypoint_mode(mode)
        if mode:
            self.btn_stage_wp.setText("✕ Cancel Staging")
            self.btn_stage_wp.setStyleSheet(f"background:#fee2e2; color:{PALETTE['danger']}; border:1px solid {PALETTE['danger_border']}; border-radius:5px; padding:4px 10px; font-weight:bold;")
            self.main_window.log_event("[NAV] Click anywhere on map to stage a new waypoint.")
        else:
            self.btn_stage_wp.setText("📍 Stage Waypoint (Click Map)")
            self.btn_stage_wp.setStyleSheet(f"background:{PALETTE['blue_soft']}; color:{PALETTE['blue']}; border:1px solid {PALETTE['blue_border']}; border-radius:5px; padding:4px 10px; font-weight:bold;")

    def _commit_waypoints(self) -> None:
        self.main_window.commit_staged_waypoints()
        self.map_canvas.set_add_waypoint_mode(False)
        self.btn_stage_wp.setText("📍 Stage Waypoint (Click Map)")
        self.btn_stage_wp.setStyleSheet(f"background:{PALETTE['blue_soft']}; color:{PALETTE['blue']}; border:1px solid {PALETTE['blue_border']}; border-radius:5px; padding:4px 10px; font-weight:bold;")

    def _clear_staged_waypoints(self) -> None:
        self.main_window.clear_staged_waypoints()
        self.map_canvas.staged_waypoints.clear()
        self.map_canvas.update()

    def _on_map_survivor_clicked(self, sid: str) -> None:
        self.selected_target_id = sid
        self.main_window.focus_survivor(sid)

    def _on_map_waypoint_added(self, x: float, y: float, tag: str) -> None:
        self.main_window._on_waypoint_added(x, y, tag)

    def _on_map_waypoint_selected(self, w_type: str, idx: int, x: float, y: float, tag: str) -> None:
        self.main_window._on_waypoint_selected(w_type, idx, x, y, tag)

    def sync_frame_data(self, frame: Dict[str, Any]) -> None:
        """Central data binding for map workspace."""
        drone = frame.get("drone", {})
        x = float(drone.get("x", 1.5))
        y = float(drone.get("y", 1.5))
        yaw = float(drone.get("yaw", drone.get("heading", 90.0)))
        alt = float(drone.get("altitude", drone.get("z", 2.4)))
        spd = float(drone.get("speed", 0.0))

        # Update HUD
        self.drone_pose_lbl.setText(
            f"DRONE POSE: X: {x:.2f}m · Y: {y:.2f}m · Z: {alt:.2f}m · HDG: {yaw:.1f}° · SPD: {spd:.2f} m/s"
        )

        # Source & Freshness
        src_label = str(frame.get("source_label", "LOCAL ENU")).upper()
        if "SIMULATION" in src_label:
            self.source_pill.setText("LOCAL ENU · 2D SLAM [SIMULATION]")
        else:
            self.source_pill.setText(src_label)

        # Update Map Canvas
        self.map_canvas.update_drone_state(x, y, yaw)
        survivors = frame.get("survivors", [])
        self.cached_survivors = survivors
        self.map_canvas.update_survivors(survivors)

        # Update Target Registry List
        self._refresh_target_registry(survivors)

        # Update Waypoint list
        active_wp_idx = frame.get("active_waypoint_idx", self.map_canvas.active_waypoint_idx)
        self._refresh_waypoint_list(active_wp_idx)

    def select_target(self, sid: str) -> None:
        self.selected_target_id = sid
        self.map_canvas.select_survivor(sid)
        self.refresh_target_rows()

    def refresh_target_rows(self) -> None:
        if hasattr(self, "cached_survivors") and self.cached_survivors:
            self._refresh_target_registry(self.cached_survivors)

    def _refresh_target_registry(self, survivors: List[Dict[str, Any]]) -> None:
        while self.target_rows_layout.count():
            item = self.target_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        localized_count = 0
        for s in survivors:
            tid = str(s.get("id", "S01"))
            grid = str(s.get("grid", "—"))
            st = str(s.get("status", "SEARCHING")).upper()
            x = s.get("x")
            y = s.get("y")

            row_frame = QFrame()
            row_frame.setCursor(Qt.CursorShape.PointingHandCursor)
            is_selected = (tid == self.selected_target_id)
            bg = "#eff6ff" if is_selected else "#ffffff"
            border = PALETTE["blue"] if is_selected else PALETTE["line"]
            row_frame.setStyleSheet(f"background:{bg}; border:1px solid {border}; border-radius:4px;")
            r_layout = QHBoxLayout(row_frame)
            r_layout.setContentsMargins(6, 2, 6, 2)
            r_layout.setSpacing(6)

            id_lbl = QLabel(f"<b>{tid}</b> [{grid}]")
            id_lbl.setFont(QFont("Segoe UI", 7))
            id_lbl.setStyleSheet(f"color:{PALETTE['navy']}; border:0;")
            r_layout.addWidget(id_lbl)

            if x is not None and y is not None and st in {"LOCALISED", "TRACKING", "DETECTED"}:
                localized_count += 1
                coord_lbl = QLabel(f"X:{float(x):.1f}m Y:{float(y):.1f}m")
                coord_lbl.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                coord_lbl.setStyleSheet(f"color:{PALETTE['green']}; border:0;")
                r_layout.addWidget(coord_lbl)

                st_badge = QLabel(st[:8])
                st_badge.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                st_badge.setStyleSheet(f"color:#ffffff; background:{PALETTE['green']}; border-radius:4px; padding:1px 4px; border:0;")
                r_layout.addWidget(st_badge)
            else:
                coord_lbl = QLabel("LOCATION UNAVAILABLE")
                coord_lbl.setFont(QFont("Segoe UI", 6))
                coord_lbl.setStyleSheet(f"color:{PALETTE['muted']}; border:0;")
                r_layout.addWidget(coord_lbl)

                st_badge = QLabel("SEARCHING")
                st_badge.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                st_badge.setStyleSheet(f"color:#ffffff; background:#94a3b8; border-radius:4px; padding:1px 4px; border:0;")
                r_layout.addWidget(st_badge)

            # Make row clickable
            row_frame.mousePressEvent = lambda ev, s_id=tid: self._on_target_row_clicked(s_id)
            self.target_rows_layout.addWidget(row_frame)

        self.target_badge.setText(f"{localized_count} / 6 LOCALIZED")

    def _on_target_row_clicked(self, sid: str) -> None:
        self.selected_target_id = sid
        self.main_window.focus_survivor(sid)
        self.map_canvas.select_survivor(sid)

    def _refresh_waypoint_list(self, active_idx: int) -> None:
        while self.wp_rows_layout.count():
            item = self.wp_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, (wx, wy) in enumerate(self.map_canvas.accepted_waypoints):
            is_active = (idx == active_idx)
            is_done = (idx in self.map_canvas.completed_waypoints)

            row_frame = QFrame()
            bg = "#f0fdf4" if is_done else ("#eff6ff" if is_active else "#ffffff")
            b_col = PALETTE["green_border"] if is_done else (PALETTE["blue_border"] if is_active else PALETTE["line"])
            row_frame.setStyleSheet(f"background:{bg}; border:1px solid {b_col}; border-radius:4px;")
            r_layout = QHBoxLayout(row_frame)
            r_layout.setContentsMargins(6, 2, 6, 2)
            r_layout.setSpacing(6)

            tag = "START" if idx == 0 else f"WP-{idx+1}"
            tag_lbl = QLabel(f"<b>{tag}</b>")
            tag_lbl.setFont(QFont("Segoe UI", 7))
            tag_lbl.setStyleSheet(f"color:{PALETTE['navy']}; border:0;")
            r_layout.addWidget(tag_lbl)

            c_lbl = QLabel(f"({wx:.1f}m, {wy:.1f}m)")
            c_lbl.setFont(QFont("Segoe UI", 6))
            c_lbl.setStyleSheet(f"color:{PALETTE['muted']}; border:0;")
            r_layout.addWidget(c_lbl)

            r_layout.addStretch()

            if is_done:
                st_lbl = QLabel("COMPLETED")
                st_lbl.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                st_lbl.setStyleSheet(f"color:{PALETTE['green']}; border:0;")
            elif is_active:
                st_lbl = QLabel("ACTIVE")
                st_lbl.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
                st_lbl.setStyleSheet(f"color:{PALETTE['blue']}; font-weight:bold; border:0;")
            else:
                st_lbl = QLabel("PENDING")
                st_lbl.setFont(QFont("Segoe UI", 6))
                st_lbl.setStyleSheet(f"color:{PALETTE['muted']}; border:0;")
            r_layout.addWidget(st_lbl)

            self.wp_rows_layout.addWidget(row_frame)


# ==============================================================================
# 2. DEDICATED SURVIVORS WORKSPACE WIDGET
# ==============================================================================
class SurvivorsWorkspaceWidget(QWidget):
    """Full dedicated workspace for monitoring the exactly six designated target identities."""

    def __init__(self, main_window: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self.selected_target_id: str = "S01"
        self.active_filter: str = "ALL"
        self.search_query: str = ""
        self.cached_survivors: List[Dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Top HUD Banner
        layout.addWidget(self._build_top_hud())

        # 2. Main Horizontal Workspace Split (6-Card Grid on Left, Dossier on Right)
        body = QHBoxLayout()
        body.setSpacing(8)

        # Left: 6-Target Cards Roster
        cards_card = QFrame()
        cards_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 8px;
            }}
        """)
        c_layout = QVBoxLayout(cards_card)
        c_layout.setContentsMargins(8, 8, 8, 8)
        c_layout.setSpacing(6)

        # Filter and Search Bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)

        filter_lbl = QLabel("Filter:")
        filter_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        filter_lbl.setStyleSheet(f"color:{PALETTE['muted']};")
        filter_bar.addWidget(filter_lbl)

        self.btn_f_all = QPushButton("All (6)")
        self.btn_f_all.setProperty("active", True)
        self.btn_f_all.clicked.connect(lambda: self._set_filter("ALL"))
        filter_bar.addWidget(self.btn_f_all)

        self.btn_f_detected = QPushButton("Detected / Tracking")
        self.btn_f_detected.setProperty("active", False)
        self.btn_f_detected.clicked.connect(lambda: self._set_filter("DETECTED"))
        filter_bar.addWidget(self.btn_f_detected)

        self.btn_f_localised = QPushButton("Localised")
        self.btn_f_localised.setProperty("active", False)
        self.btn_f_localised.clicked.connect(lambda: self._set_filter("LOCALISED"))
        filter_bar.addWidget(self.btn_f_localised)

        self.btn_f_searching = QPushButton("Searching")
        self.btn_f_searching.setProperty("active", False)
        self.btn_f_searching.clicked.connect(lambda: self._set_filter("SEARCHING"))
        filter_bar.addWidget(self.btn_f_searching)

        filter_bar.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Filter S01-S06 or Grid...")
        self.search_edit.setFont(QFont("Segoe UI", 7))
        self.search_edit.setFixedWidth(180)
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 4px;
                padding: 2px 6px;
                color: {PALETTE['ink']};
            }}
        """)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        filter_bar.addWidget(self.search_edit)

        c_layout.addLayout(filter_bar)

        # Scroll Area for the 6 Cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent; border:0;")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background:transparent;")
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(6)
        scroll.setWidget(self.cards_container)
        c_layout.addWidget(scroll, 1)

        body.addWidget(cards_card, 62)

        # Right: Detailed Dossier & Visual Inspector
        body.addWidget(self._build_dossier_panel(), 38)
        layout.addLayout(body, 1)

        self._style_filter_buttons()

    def _build_top_hud(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 6px;
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(10)

        title = QLabel("👥  SIX-TARGET SURVIVOR MONITORING & LOCALISATION WORKSPACE")
        title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {PALETTE['ink']};")
        row.addWidget(title)

        row.addStretch()

        self.hud_detected = QLabel("● 0 / 6 DETECTED")
        self.hud_detected.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.hud_detected.setStyleSheet(f"""
            color: {PALETTE['green']};
            background: {PALETTE['green_soft']};
            border: 1px solid {PALETTE['green_border']};
            border-radius: 9px;
            padding: 2px 8px;
        """)
        row.addWidget(self.hud_detected)

        self.hud_localized = QLabel("● 0 / 6 LOCALISED")
        self.hud_localized.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.hud_localized.setStyleSheet(f"""
            color: {PALETTE['blue']};
            background: {PALETTE['blue_soft']};
            border: 1px solid {PALETTE['blue_border']};
            border-radius: 9px;
            padding: 2px 8px;
        """)
        row.addWidget(self.hud_localized)

        self.hud_searching = QLabel("● 6 SEARCHING")
        self.hud_searching.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.hud_searching.setStyleSheet(f"""
            color: {PALETTE['muted']};
            background: #f1f5f9;
            border: 1px solid {PALETTE['line']};
            border-radius: 9px;
            padding: 2px 8px;
        """)
        row.addWidget(self.hud_searching)

        return bar

    def _build_dossier_panel(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Inspector Card
        dossier_card = QFrame()
        dossier_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 8px;
            }}
        """)
        d_layout = QVBoxLayout(dossier_card)
        d_layout.setContentsMargins(12, 10, 12, 10)
        d_layout.setSpacing(8)

        head = QHBoxLayout()
        self.d_title = QLabel("TARGET DOSSIER: S01")
        self.d_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.d_title.setStyleSheet(f"color:{PALETTE['ink']};")
        head.addWidget(self.d_title)
        head.addStretch()

        self.d_status_badge = QLabel("SEARCHING")
        self.d_status_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.d_status_badge.setStyleSheet(f"color:#ffffff; background:#94a3b8; border-radius:9px; padding:2px 8px;")
        head.addWidget(self.d_status_badge)
        d_layout.addLayout(head)

        # Image / Thumbnail Preview
        self.d_thumb_frame = QFrame()
        self.d_thumb_frame.setFixedHeight(120)
        self.d_thumb_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #0f172a;
                border: 1px solid {PALETTE['line']};
                border-radius: 6px;
            }}
        """)
        thumb_layout = QVBoxLayout(self.d_thumb_frame)
        thumb_layout.setContentsMargins(4, 4, 4, 4)
        self.d_thumb_lbl = QLabel()
        self.d_thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.d_thumb_lbl.setText("NO DETECTION SIGNATURE")
        self.d_thumb_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.d_thumb_lbl.setStyleSheet("color:#64748b; background:transparent;")
        thumb_layout.addWidget(self.d_thumb_lbl)
        d_layout.addWidget(self.d_thumb_frame)

        # Key-Value Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        self.d_fields: Dict[str, QLabel] = {}
        fields = [
            ("Target Identity", "S01"),
            ("Sector Grid", "A1"),
            ("Confidence", "—"),
            ("Localisation State", "UNAVAILABLE"),
            ("Metric ENU Coords", "COORDINATES UNAVAILABLE"),
            ("GPS Coordinates", "UNAVAILABLE"),
            ("Tracking State", "NOT DETECTED"),
            ("First Sighting", "—"),
            ("Last Sighting", "—"),
            ("Distance to Drone", "—"),
        ]

        for idx, (label_txt, default_val) in enumerate(fields):
            lbl = QLabel(label_txt)
            lbl.setFont(QFont("Segoe UI", 7))
            lbl.setStyleSheet(f"color:{PALETTE['muted']};")
            grid.addWidget(lbl, idx, 0)

            val_lbl = QLabel(default_val)
            val_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            val_lbl.setStyleSheet(f"color:{PALETTE['ink']};")
            self.d_fields[label_txt] = val_lbl
            grid.addWidget(val_lbl, idx, 1)

        d_layout.addLayout(grid)
        d_layout.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_view_on_map = QPushButton("📍 View on Map")
        self.btn_view_on_map.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_view_on_map.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_on_map.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['blue']};
                color: #ffffff;
                border-radius: 4px;
                padding: 4px 10px;
                border: 0;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
        """)
        self.btn_view_on_map.clicked.connect(self._view_selected_on_map)
        btn_row.addWidget(self.btn_view_on_map)

        btn_log = QPushButton("📋 Log Target")
        btn_log.setFont(QFont("Segoe UI", 8))
        btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_log.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: {PALETTE['ink']};
                border: 1px solid {PALETTE['line']};
                border-radius: 4px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        btn_log.clicked.connect(self._log_target_dossier)
        btn_row.addWidget(btn_log)

        d_layout.addLayout(btn_row)
        layout.addWidget(dossier_card)

        return col

    def _style_filter_buttons(self) -> None:
        btns = [
            (self.btn_f_all, "ALL"),
            (self.btn_f_detected, "DETECTED"),
            (self.btn_f_localised, "LOCALISED"),
            (self.btn_f_searching, "SEARCHING"),
        ]
        for btn, name in btns:
            is_active = (self.active_filter == name)
            bg = PALETTE["blue"] if is_active else "#ffffff"
            fg = "#ffffff" if is_active else PALETTE["ink"]
            b_col = PALETTE["blue"] if is_active else PALETTE["line"]
            btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold if is_active else QFont.Weight.Normal))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {fg};
                    border: 1px solid {b_col};
                    border-radius: 4px;
                    padding: 2px 8px;
                }}
            """)

    def _set_filter(self, f_type: str) -> None:
        self.active_filter = f_type
        self._style_filter_buttons()
        self.refresh_cards()

    def _on_search_text_changed(self, text: str) -> None:
        self.search_query = text.strip().upper()
        self.refresh_cards()

    def select_target(self, sid: str) -> None:
        self.selected_target_id = sid
        self.refresh_cards()
        self.refresh_dossier()

    def _view_selected_on_map(self) -> None:
        self.main_window._select_tab("Map")
        self.main_window.map_workspace.selected_target_id = self.selected_target_id
        self.main_window.map_workspace.map_canvas.select_survivor(self.selected_target_id)

    def _log_target_dossier(self) -> None:
        s = next((t for t in self.cached_survivors if t.get("id") == self.selected_target_id), None)
        if s:
            st = s.get("status", "SEARCHING")
            conf = s.get("confidence", "—")
            grid = s.get("grid", "—")
            x = s.get("x")
            y = s.get("y")
            loc_str = f"({x:.1f}m, {y:.1f}m)" if x is not None and y is not None else "UNAVAILABLE"
            self.main_window.log_event(f"[VISION] Target Report {self.selected_target_id}: Status={st}, Conf={conf}%, Grid={grid}, Pos={loc_str}")

    def sync_frame_data(self, frame: Dict[str, Any]) -> None:
        """Central data binding for survivor monitoring workspace."""
        raw_survivors = frame.get("survivors", [])
        valid_survivors = [s for s in raw_survivors if str(s.get("id")) in DESIGNATED_TARGETS]
        self.cached_survivors = valid_survivors

        detected_cnt = sum(1 for s in valid_survivors if str(s.get("status", "")).upper() in {"DETECTED", "TRACKING", "LOCALISED", "LOST", "FOUND"})
        localized_cnt = sum(1 for s in valid_survivors if str(s.get("status", "")).upper() in {"LOCALISED", "CONFIRMED"})
        searching_cnt = max(0, 6 - detected_cnt)

        self.hud_detected.setText(f"● {detected_cnt} / 6 DETECTED")
        self.hud_localized.setText(f"● {localized_cnt} / 6 LOCALISED")
        self.hud_searching.setText(f"● {searching_cnt} SEARCHING")

        self.refresh_cards()
        self.refresh_dossier()

    def refresh_cards(self) -> None:
        # Clear cards
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Filter strictly the 6 designated targets
        filtered: List[Dict[str, Any]] = []
        for s in self.cached_survivors:
            tid = str(s.get("id", "")).upper()
            if tid not in DESIGNATED_TARGETS:
                continue

            st = str(s.get("status", "SEARCHING")).upper()
            grid = str(s.get("grid", "")).upper()

            # Filter check
            if self.active_filter == "DETECTED" and st not in {"DETECTED", "TRACKING", "LOCALISED", "LOST"}:
                continue
            if self.active_filter == "LOCALISED" and st not in {"LOCALISED", "CONFIRMED"}:
                continue
            if self.active_filter == "SEARCHING" and st != "SEARCHING":
                continue

            # Search check
            if self.search_query:
                if self.search_query not in tid and self.search_query not in grid and self.search_query not in st:
                    continue

            filtered.append(s)

        # Render 2 columns of cards
        for idx, s in enumerate(filtered):
            card = self._create_survivor_card_widget(s)
            r = idx // 2
            c = idx % 2
            self.cards_grid.addWidget(card, r, c)

    def _create_survivor_card_widget(self, s: Dict[str, Any]) -> QFrame:
        tid = str(s.get("id", "S01"))
        grid = str(s.get("grid", "—"))
        st = str(s.get("status", "SEARCHING")).upper()
        conf = s.get("confidence")
        x = s.get("x")
        y = s.get("y")
        tracking_st = str(s.get("tracking_status", "NOT DETECTED"))
        loc_st = str(s.get("loc_status", "UNAVAILABLE"))
        is_selected = (tid == self.selected_target_id)

        card = QFrame()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        bg = "#eff6ff" if is_selected else "#ffffff"
        border = PALETTE["blue"] if is_selected else PALETTE["line"]
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1.5px solid {border};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Top row: ID + Grid + Status Badge
        top = QHBoxLayout()
        t_lbl = QLabel(f"<b>{tid}</b> · Sector {grid}")
        t_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color:{PALETTE['navy']}; border:0;")
        top.addWidget(t_lbl)
        top.addStretch()

        if st == "LOCALISED":
            badge_col = PALETTE["green"]
        elif st == "TRACKING":
            badge_col = PALETTE["cyan"]
        elif st == "DETECTED":
            badge_col = PALETTE["amber"]
        elif st == "LOST":
            badge_col = PALETTE["danger"]
        else:
            badge_col = "#94a3b8"

        badge = QLabel(st)
        badge.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
        badge.setStyleSheet(f"color:#ffffff; background:{badge_col}; border-radius:4px; padding:1px 5px; border:0;")
        top.addWidget(badge)
        layout.addLayout(top)

        # Confidence Bar
        conf_row = QHBoxLayout()
        conf_lbl = QLabel(f"Confidence: {conf}%" if conf is not None else "Confidence: —")
        conf_lbl.setFont(QFont("Segoe UI", 7))
        conf_lbl.setStyleSheet(f"color:{PALETTE['muted']}; border:0;")
        conf_row.addWidget(conf_lbl)
        conf_row.addStretch()

        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setValue(int(conf) if conf is not None else 0)
        pbar.setTextVisible(False)
        pbar.setFixedHeight(5)
        pbar.setFixedWidth(60)
        pbar.setStyleSheet(f"""
            QProgressBar {{
                background: #f1f5f9;
                border-radius: 2px;
                border: 0;
            }}
            QProgressBar::chunk {{
                background: {badge_col};
                border-radius: 2px;
            }}
        """)
        conf_row.addWidget(pbar)
        layout.addLayout(conf_row)

        # Coordinates
        if x is not None and y is not None and st in {"LOCALISED", "TRACKING", "DETECTED"}:
            c_text = f"ENU: X:{float(x):.2f}m  Y:{float(y):.2f}m"
            c_col = PALETTE["ink"]
        else:
            c_text = "Coordinates: UNAVAILABLE"
            c_col = PALETTE["muted"]

        coord_lbl = QLabel(c_text)
        coord_lbl.setFont(QFont("Segoe UI", 7))
        coord_lbl.setStyleSheet(f"color:{c_col}; border:0;")
        layout.addWidget(coord_lbl)

        # Tracking state
        track_lbl = QLabel(f"Track: {tracking_st} | Loc: {loc_st}")
        track_lbl.setFont(QFont("Segoe UI", 6))
        track_lbl.setStyleSheet(f"color:{PALETTE['muted']}; border:0;")
        layout.addWidget(track_lbl)

        card.mousePressEvent = lambda ev, s_id=tid: self._on_card_clicked(s_id)
        return card

    def _on_card_clicked(self, sid: str) -> None:
        self.selected_target_id = sid
        self.main_window.focus_survivor(sid)
        self.refresh_cards()
        self.refresh_dossier()

    def refresh_dossier(self) -> None:
        """Update right-side dossier inspector with selected target data."""
        s = next((t for t in self.cached_survivors if t.get("id") == self.selected_target_id), None)
        if not s:
            return

        tid = str(s.get("id", "S01"))
        grid = str(s.get("grid", "—"))
        st = str(s.get("status", "SEARCHING")).upper()
        conf = s.get("confidence")
        x = s.get("x")
        y = s.get("y")
        lat = s.get("lat")
        lon = s.get("lon")
        tracking_st = str(s.get("tracking_status", "NOT DETECTED"))
        loc_st = str(s.get("loc_status", "UNAVAILABLE"))
        first_seen = s.get("first_seen_sec")
        last_seen = s.get("last_seen_sec")
        thumb_path = s.get("thumb")

        self.d_title.setText(f"TARGET DOSSIER: {tid}")
        self.d_status_badge.setText(st)

        if st == "LOCALISED":
            badge_col = PALETTE["green"]
        elif st == "TRACKING":
            badge_col = PALETTE["cyan"]
        elif st == "DETECTED":
            badge_col = PALETTE["amber"]
        elif st == "LOST":
            badge_col = PALETTE["danger"]
        else:
            badge_col = "#94a3b8"

        self.d_status_badge.setStyleSheet(f"color:#ffffff; background:{badge_col}; border-radius:9px; padding:2px 8px;")

        # Thumbnail
        if thumb_path and st in {"DETECTED", "TRACKING", "LOCALISED", "LOST"}:
            pix = QPixmap(str(thumb_path))
            if not pix.isNull():
                self.d_thumb_lbl.setPixmap(pix.scaled(180, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.d_thumb_lbl.setText(f"● {st} SIGNATURE (GRID {grid})")
                self.d_thumb_lbl.setStyleSheet(f"color:{PALETTE['cyan']}; font-weight:bold; background:transparent;")
        else:
            self.d_thumb_lbl.setText("NO DETECTION SIGNATURE")
            self.d_thumb_lbl.setStyleSheet("color:#64748b; background:transparent;")

        # Fields
        self.d_fields["Target Identity"].setText(f"{tid} (Victim Slot #{tid.lstrip('S')})")
        self.d_fields["Sector Grid"].setText(f"Sector {grid}")
        self.d_fields["Confidence"].setText(f"{conf}% Human Heat & Vision Signature" if conf is not None else "—")
        self.d_fields["Localisation State"].setText(loc_st)

        if x is not None and y is not None and st in {"LOCALISED", "TRACKING", "DETECTED"}:
            self.d_fields["Metric ENU Coords"].setText(f"X: {float(x):.2f}m · Y: {float(y):.2f}m · Z: 0.0m")
            self.d_fields["Metric ENU Coords"].setStyleSheet(f"color:{PALETTE['green']}; font-weight:bold;")
            if lat is not None and lon is not None:
                self.d_fields["GPS Coordinates"].setText(f"{float(lat):.6f}° N, {float(lon):.6f}° E")
            else:
                self.d_fields["GPS Coordinates"].setText("Ref: 12.9716° N, 77.5946° E (Local ENU)")

            # Distance to drone
            drone = self.main_window.plugin_manager.poll().frame or {}
            dx = float(drone.get("drone", {}).get("x", 1.5)) - float(x)
            dy = float(drone.get("drone", {}).get("y", 1.5)) - float(y)
            dist = math.hypot(dx, dy)
            self.d_fields["Distance to Drone"].setText(f"{dist:.2f} meters")
        else:
            self.d_fields["Metric ENU Coords"].setText("COORDINATES UNAVAILABLE")
            self.d_fields["Metric ENU Coords"].setStyleSheet(f"color:{PALETTE['muted']};")
            self.d_fields["GPS Coordinates"].setText("UNAVAILABLE")
            self.d_fields["Distance to Drone"].setText("—")

        self.d_fields["Tracking State"].setText(tracking_st)
        self.d_fields["First Sighting"].setText(f"T+{first_seen}s" if first_seen is not None else "Not Detected")
        self.d_fields["Last Sighting"].setText(f"T+{last_seen}s" if last_seen is not None else "Not Detected")
