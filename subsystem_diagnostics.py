#!/usr/bin/env python3
"""NIDAR Rescue GCS — Subsystem Diagnostics Dialog & Item Widgets.

Provides interactive diagnostics views for hardware subsystems with consistent visual styling:
- White cards
- Pale-blue borders
- Dark-navy text
- Blue icons
- Clear status badges (OK, WARNING, ERROR, DISCONNECTED, STALE, SIMULATED, NOT CONFIGURED)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget, QComboBox, QMessageBox
)

from health_model import HealthState, HealthSystemManager, STATUS_STYLE, SubsystemRecord

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
    "green": "#10b981",
    "amber": "#f59e0b",
    "danger": "#ef4444",
}


class SubsystemItemWidget(QFrame):
    """Compact row widget for hardware subsystem summary panel in the main dashboard."""
    clicked = pyqtSignal(str)

    def __init__(self, icon_str: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("subsystemRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name = name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        # Icon
        self.icon_lbl = QLabel(icon_str)
        self.icon_lbl.setFont(QFont("Segoe UI Emoji", 10, QFont.Weight.Bold))
        self.icon_lbl.setStyleSheet(f"color:{PALETTE['cyan']}; background:transparent;")
        layout.addWidget(self.icon_lbl)

        # Name
        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.name_lbl.setStyleSheet(f"color:{PALETTE['ink']}; background:transparent;")
        layout.addWidget(self.name_lbl, 1)

        # Status badge
        self.ok_badge = QLabel("OK")
        self.ok_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.ok_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ok_badge.setFixedHeight(18)
        self.ok_badge.setMinimumWidth(44)
        self.set_status("OK")
        layout.addWidget(self.ok_badge)

        self._apply_style(hover=False)

    def _apply_style(self, hover: bool = False) -> None:
        border = PALETTE["blue_border"] if hover else PALETTE["line"]
        bg = "#f0f9ff" if hover else "#ffffff"
        self.setStyleSheet(f"""
            QFrame#subsystemRow {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)

    def enterEvent(self, event) -> None:
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def set_status(self, status: str) -> None:
        status_upper = status.upper().strip()

        if "SIM" in status_upper:
            display_text = "OK (SIM)"
            bg_col = STATUS_STYLE[HealthState.SIMULATED.value]["bg"]
        elif status_upper in {"OK", "NOMINAL", "ACTIVE"}:
            display_text = "OK"
            bg_col = STATUS_STYLE[HealthState.OK.value]["bg"]
        elif "WARN" in status_upper or "WAIT" in status_upper:
            display_text = "WARN"
            bg_col = STATUS_STYLE[HealthState.WARNING.value]["bg"]
        elif "ERR" in status_upper or "FAIL" in status_upper:
            display_text = "ERROR"
            bg_col = STATUS_STYLE[HealthState.ERROR.value]["bg"]
        elif "DISC" in status_upper:
            display_text = "DISC"
            bg_col = STATUS_STYLE[HealthState.DISCONNECTED.value]["bg"]
        elif "STALE" in status_upper:
            display_text = "STALE"
            bg_col = STATUS_STYLE[HealthState.STALE.value]["bg"]
        elif "NOT" in status_upper or "N/A" in status_upper or "CONFIG" in status_upper:
            display_text = "N/A"
            bg_col = STATUS_STYLE[HealthState.NOT_CONFIGURED.value]["bg"]
        else:
            display_text = status_upper[:7]
            bg_col = "#64748b"

        self.ok_badge.setText(display_text)
        self.ok_badge.setStyleSheet(f"""
            background-color: {bg_col};
            color: #ffffff;
            border-radius: 9px;
            padding: 1px 7px;
            font-weight: bold;
            font-size: 7pt;
        """)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.name)


class SubsystemDiagnosticsDialog(QDialog):
    """Detailed, interactive diagnostics system for a hardware subsystem."""
    state_injected = pyqtSignal(str, str)  # (subsystem_name, new_state_str)

    def __init__(
        self,
        subsystem_name: str,
        health_manager: HealthSystemManager,
        is_simulation: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.subsystem_name = subsystem_name
        self.health_manager = health_manager
        self.is_simulation = is_simulation

        self.setWindowTitle(f"NIDAR Rescue GCS — Subsystem Diagnostics: {subsystem_name}")
        self.resize(560, 580)
        self.setMinimumSize(480, 480)
        self.setStyleSheet(f"background-color: {PALETTE['bg']};")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(10)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        # 1. Top Header Card
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 8px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(14, 10, 14, 10)
        h_layout.setSpacing(12)

        self.icon_badge = QLabel("⚙")
        self.icon_badge.setFont(QFont("Segoe UI Emoji", 20, QFont.Weight.Bold))
        self.icon_badge.setFixedSize(44, 44)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setStyleSheet(f"background: {PALETTE['blue_soft']}; border-radius: 22px; color: {PALETTE['blue']};")
        h_layout.addWidget(self.icon_badge)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.name_label = QLabel(self.subsystem_name)
        self.name_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.name_label.setStyleSheet(f"color: {PALETTE['ink']};")
        title_col.addWidget(self.name_label)

        self.category_label = QLabel("CATEGORY: GENERAL SUBSYSTEM")
        self.category_label.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.category_label.setStyleSheet(f"color: {PALETTE['muted']};")
        title_col.addWidget(self.category_label)
        h_layout.addLayout(title_col, 1)

        self.status_pill = QLabel("● OK")
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFixedHeight(26)
        self.status_pill.setMinimumWidth(80)
        h_layout.addWidget(self.status_pill)

        self.layout.addWidget(header_card)

        # 2. Source & Freshness Metadata Banner
        meta_card = QFrame()
        meta_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 6px;
            }}
        """)
        m_layout = QHBoxLayout(meta_card)
        m_layout.setContentsMargins(12, 6, 12, 6)
        m_layout.setSpacing(10)

        self.source_label = QLabel("SOURCE: UNKNOWN")
        self.source_label.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.source_label.setStyleSheet(f"color: {PALETTE['navy']};")
        m_layout.addWidget(self.source_label)

        m_layout.addStretch()

        self.freshness_label = QLabel("FRESHNESS: LIVE")
        self.freshness_label.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.freshness_label.setStyleSheet(f"color: {PALETTE['cyan']};")
        m_layout.addWidget(self.freshness_label)

        self.layout.addWidget(meta_card)

        # 3. Description Note
        self.desc_label = QLabel()
        self.desc_label.setFont(QFont("Segoe UI", 8))
        self.desc_label.setStyleSheet(f"color: {PALETTE['muted']}; padding: 0 4px;")
        self.desc_label.setWordWrap(True)
        self.layout.addWidget(self.desc_label)

        # 4. Scrollable Diagnostics & Metrics Section
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: 0;")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)

        # Metrics Card
        metrics_card = QFrame()
        metrics_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 8px;
            }}
        """)
        self.metrics_layout = QVBoxLayout(metrics_card)
        self.metrics_layout.setContentsMargins(12, 10, 12, 10)
        self.metrics_layout.setSpacing(6)

        m_head = QLabel("TELEMETRY METRICS & PARAMETERS")
        m_head.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        m_head.setStyleSheet(f"color: {PALETTE['blue']};")
        self.metrics_layout.addWidget(m_head)

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setHorizontalSpacing(12)
        self.metrics_grid.setVerticalSpacing(4)
        self.metrics_layout.addLayout(self.metrics_grid)

        self.scroll_layout.addWidget(metrics_card)

        # Error / Alert Banner
        self.alert_card = QFrame()
        self.alert_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 8px;
            }}
        """)
        a_layout = QVBoxLayout(self.alert_card)
        a_layout.setContentsMargins(12, 8, 12, 8)
        a_layout.setSpacing(4)

        a_title = QLabel("LATEST WARNING / ERROR DIAGNOSTIC")
        a_title.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        a_title.setStyleSheet(f"color: {PALETTE['muted']};")
        a_layout.addWidget(a_title)

        self.alert_msg = QLabel("None · Subsystem is operating within nominal thresholds.")
        self.alert_msg.setFont(QFont("Segoe UI", 8))
        self.alert_msg.setStyleSheet(f"color: {PALETTE['green']}; font-weight: bold;")
        self.alert_msg.setWordWrap(True)
        a_layout.addWidget(self.alert_msg)

        self.scroll_layout.addWidget(self.alert_card)

        # Troubleshooting Card
        trouble_card = QFrame()
        trouble_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 8px;
            }}
        """)
        t_layout = QVBoxLayout(trouble_card)
        t_layout.setContentsMargins(12, 8, 12, 8)
        t_layout.setSpacing(4)

        t_title = QLabel("REMEDIAL & TROUBLESHOOTING ACTIONS")
        t_title.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        t_title.setStyleSheet(f"color: {PALETTE['muted']};")
        t_layout.addWidget(t_title)

        self.trouble_msg = QLabel()
        self.trouble_msg.setFont(QFont("Segoe UI", 8))
        self.trouble_msg.setStyleSheet(f"color: {PALETTE['ink']};")
        self.trouble_msg.setWordWrap(True)
        t_layout.addWidget(self.trouble_msg)

        self.scroll_layout.addWidget(trouble_card)

        # Status History Card
        hist_card = QFrame()
        hist_card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['line']};
                border-radius: 8px;
            }}
        """)
        h_layout2 = QVBoxLayout(hist_card)
        h_layout2.setContentsMargins(12, 8, 12, 8)
        h_layout2.setSpacing(4)

        h_title = QLabel("RECENT STATUS TRANSITION HISTORY")
        h_title.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        h_title.setStyleSheet(f"color: {PALETTE['muted']};")
        h_layout2.addWidget(h_title)

        self.hist_container = QVBoxLayout()
        self.hist_container.setSpacing(2)
        h_layout2.addLayout(self.hist_container)

        self.scroll_layout.addWidget(hist_card)

        scroll.setWidget(scroll_widget)
        self.layout.addWidget(scroll, 1)

        # 5. Simulation Testing & State Injection Controls
        sim_box = QFrame()
        sim_box.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {PALETTE['blue_border']};
                border-radius: 8px;
            }}
        """)
        s_layout = QHBoxLayout(sim_box)
        s_layout.setContentsMargins(12, 6, 12, 6)
        s_layout.setSpacing(8)

        sim_lbl = QLabel("🧪 Test State:")
        sim_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        sim_lbl.setStyleSheet(f"color: {PALETTE['blue']};")
        s_layout.addWidget(sim_lbl)

        self.state_combo = QComboBox()
        self.state_combo.setFont(QFont("Segoe UI", 8))
        for st in HealthState:
            self.state_combo.addItem(st.value)
        self.state_combo.setCurrentText(HealthState.SIMULATED.value)
        s_layout.addWidget(self.state_combo, 1)

        apply_btn = QPushButton("Apply State")
        apply_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['blue']};
                color: #ffffff;
                border-radius: 4px;
                padding: 4px 12px;
                border: 0;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
        """)
        apply_btn.clicked.connect(self._apply_test_state)
        s_layout.addWidget(apply_btn)

        close_btn = QPushButton("Close")
        close_btn.setFont(QFont("Segoe UI", 8))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: {PALETTE['ink']};
                border: 1px solid {PALETTE['line']};
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        close_btn.clicked.connect(self.close)
        s_layout.addWidget(close_btn)

        self.layout.addWidget(sim_box)

    def set_subsystem(self, subsystem_name: str) -> None:
        self.subsystem_name = subsystem_name
        if hasattr(self, "name_label"):
            self.name_label.setText(subsystem_name)
        self.setWindowTitle(f"NIDAR Rescue GCS — Subsystem Diagnostics: {subsystem_name}")
        self.refresh()

    def refresh(self) -> None:
        """Fetch latest metrics and transitions from HealthSystemManager."""
        rec = self.health_manager.get_subsystem(self.subsystem_name)
        if not rec:
            return

        self.icon_badge.setText(rec.icon)
        self.category_label.setText(f"CATEGORY: {rec.category.upper()}")
        self.desc_label.setText(rec.description)
        self.trouble_msg.setText(rec.troubleshooting)

        # Status badge styling
        st_val = rec.current_state.value
        style_info = STATUS_STYLE.get(st_val, STATUS_STYLE[HealthState.NOT_CONFIGURED.value])
        self.status_pill.setText(f"{style_info['icon']}  {st_val}")
        self.status_pill.setStyleSheet(f"""
            background-color: {style_info['bg']};
            color: {style_info['badge_text']};
            border-radius: 13px;
            padding: 3px 12px;
            font-weight: bold;
        """)

        # Source & Freshness
        self.source_label.setText(f"DATA SOURCE: {rec.source_label}")
        age = rec.get_age_seconds()
        if st_val == HealthState.NOT_CONFIGURED.value:
            self.freshness_label.setText("FRESHNESS: NOT CONFIGURED")
            self.freshness_label.setStyleSheet(f"color: {PALETTE['muted']};")
        elif age > rec.freshness_timeout_sec or st_val == HealthState.STALE.value:
            self.freshness_label.setText(f"FRESHNESS: STALE ({age:.1f}s ago)")
            self.freshness_label.setStyleSheet(f"color: {PALETTE['danger']}; font-weight: bold;")
        else:
            self.freshness_label.setText(f"FRESHNESS: FRESH (age: {int(age*1000)}ms)")
            self.freshness_label.setStyleSheet(f"color: {PALETTE['green']}; font-weight: bold;")

        # Metrics grid
        # Clear old rows
        while self.metrics_grid.count():
            item = self.metrics_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, (k, v) in enumerate(rec.metrics.items()):
            row = idx
            k_lbl = QLabel(k)
            k_lbl.setFont(QFont("Segoe UI", 8))
            k_lbl.setStyleSheet(f"color: {PALETTE['muted']};")
            self.metrics_grid.addWidget(k_lbl, row, 0)

            v_lbl = QLabel(str(v))
            v_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {PALETTE['ink']};")
            self.metrics_grid.addWidget(v_lbl, row, 1)

        # Error / Alert
        if rec.last_error_message:
            self.alert_msg.setText(rec.last_error_message)
            self.alert_msg.setStyleSheet(f"color: {PALETTE['danger']}; font-weight: bold;")
        elif st_val == HealthState.ERROR.value:
            self.alert_msg.setText("ERROR: Critical subsystem failure reported by driver.")
            self.alert_msg.setStyleSheet(f"color: {PALETTE['danger']}; font-weight: bold;")
        elif st_val == HealthState.WARNING.value:
            self.alert_msg.setText("WARNING: Operating near performance boundaries or high latency.")
            self.alert_msg.setStyleSheet(f"color: {PALETTE['amber']}; font-weight: bold;")
        elif st_val == HealthState.STALE.value:
            self.alert_msg.setText(f"STALE: No fresh packet arrived in >{rec.freshness_timeout_sec}s.")
            self.alert_msg.setStyleSheet(f"color: {PALETTE['danger']}; font-weight: bold;")
        elif st_val == HealthState.DISCONNECTED.value:
            self.alert_msg.setText("DISCONNECTED: Hardware link or network stream unavailable.")
            self.alert_msg.setStyleSheet(f"color: {PALETTE['muted']}; font-weight: bold;")
        elif st_val == HealthState.NOT_CONFIGURED.value:
            self.alert_msg.setText("NOT CONFIGURED: Hardware not present on this vehicle variant.")
            self.alert_msg.setStyleSheet(f"color: {PALETTE['muted']};")
        else:
            self.alert_msg.setText("None · Subsystem is operating within nominal thresholds.")
            self.alert_msg.setStyleSheet(f"color: {PALETTE['green']}; font-weight: bold;")

        # Transition History
        while self.hist_container.count():
            item = self.hist_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for t_str, st_txt, reason in rec.status_history[:6]:
            row_w = QLabel(f"[{t_str}]  ● {st_txt} — {reason}")
            row_w.setFont(QFont("Segoe UI", 7))
            row_w.setStyleSheet(f"color: {PALETTE['navy']};")
            self.hist_container.addWidget(row_w)

    def _apply_test_state(self) -> None:
        target_state_str = self.state_combo.currentText()
        target_state = HealthState(target_state_str)
        err = f"Manually simulated {target_state_str} event" if target_state in {HealthState.ERROR, HealthState.WARNING} else None
        self.health_manager.set_subsystem_state(
            self.subsystem_name, target_state, reason="Operator state injection test", error_msg=err
        )
        self.state_injected.emit(self.subsystem_name, target_state_str)
        self.refresh()
