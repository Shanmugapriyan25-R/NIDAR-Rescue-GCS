#!/usr/bin/env python3
"""
TEAM EDITH — Ground Control Station (GCS)
NIDAR AirMouse — Problem Statement 2 (PS2)
Native Desktop Application
Light Aerospace Command Center Visual System
Zero-Scroll Viewport | 2D SLAM | Camera OSD | Telemetry | Audio
"""

import sys
import math
import time
import winsound
from datetime import datetime
import tkinter as tk
from tkinter import ttk

# ==============================================================================
# COLOR PALETTE (LIGHT THEME SPECIFICATION)
# ==============================================================================
HEX_BG_PRIMARY    = "#F6F9FC"
HEX_BG_CARD       = "#FFFFFF"
HEX_BG_SUBTLE     = "#F8FAFC"
HEX_BLUE_SOFT     = "#EAF4FF"
HEX_BLUE_PRIMARY  = "#2563EB"
HEX_BLUE_HOVER    = "#1D4ED8"
HEX_CYAN_ACCENT   = "#06B6D4"
HEX_CYAN_SOFT     = "#E8FAFC"
HEX_SUCCESS       = "#16A34A"
HEX_SUCCESS_SOFT  = "#ECFDF3"
HEX_WARNING       = "#F59E0B"
HEX_WARNING_SOFT  = "#FFF7E6"
HEX_DANGER        = "#DC2626"
HEX_DANGER_SOFT   = "#FEF2F2"
HEX_TEXT_PRIMARY  = "#0F172A"
HEX_TEXT_SEC      = "#475569"
HEX_TEXT_MUTED    = "#64748B"
HEX_BORDER        = "#E2E8F0"
HEX_GRID_LINE     = "#E5E7EB"
HEX_MAP_WALLS     = "#64748B"
HEX_MAP_EXPLORED  = "#E2E8F0"
HEX_MAP_UNEXPLORED= "#F8FAFC"
HEX_TARGET_ORANGE = "#F97316"

FONT_HEADING = ("Rajdhani", 12, "bold")
FONT_TITLE   = ("Rajdhani", 16, "bold")
FONT_MONO    = ("JetBrains Mono", 10)
FONT_MONO_SM = ("JetBrains Mono", 9)
FONT_MONO_BD = ("JetBrains Mono", 10, "bold")
FONT_BODY    = ("Segoe UI", 10)

class EdithGCSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TEAM EDITH — Ground Control Station | NIDAR AirMouse PS2")
        self.geometry("1600x920")
        self.minsize(1280, 720)
        self.configure(bg=HEX_BG_PRIMARY)

        # Mission States
        self.mode = "simulation" # 'simulation' or 'live'
        self.mission_state = "EXPLORING"
        self.mission_time_sec = 146
        self.battery_pct = 65.0
        self.battery_v = 22.80

        # Corridor Navigation Waypoints (15m x 15m modular maze)
        self.waypoints = [
            (1.2, 1.2), (1.2, 4.2), (3.5, 4.2), (3.5, 2.2),
            (7.2, 2.2), (7.2, 4.0), (11.2, 4.0), (11.2, 8.5),
            (5.2, 8.5), (5.2, 11.5), (12.2, 11.5), (12.2, 13.5),
            (4.2, 13.5)
        ]
        self.wp_idx = 8
        self.target_wp_idx = 9
        self.wp_t = 0.4

        self.drone_x = 4.5
        self.drone_y = 6.8
        self.drone_yaw = 198.0
        self.trajectory = []
        self.lidar_angle = 0.0

        self.targets = [
            {"id": "T1", "grid": "C4", "x": 3.2, "y": 4.1, "found": True, "conf": 94.2},
            {"id": "T2", "grid": "G2", "x": 7.5, "y": 2.3, "found": True, "conf": 91.7},
            {"id": "T3", "grid": "K3", "x": 11.4, "y": 3.8, "found": True, "conf": 88.5},
            {"id": "T4", "grid": "E8", "x": 5.1, "y": 8.6, "found": True, "conf": 92.1},
            {"id": "T5", "grid": "L11", "x": 12.2, "y": 11.5, "found": False, "conf": 0.0},
            {"id": "T6", "grid": "D13", "x": 4.0, "y": 13.2, "found": False, "conf": 0.0},
        ]

        self.map_layers = {"grid": True, "path": True, "lidar": True, "targets": True}
        self.map_zoom = 1.0

        self.init_styles()
        self.create_header()
        self.create_dashboard()
        self.start_loops()

        # Scheduled Detections
        self.after(14000, self.discover_next_target)
        self.after(28000, self.discover_next_target)

    def init_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TProgressbar", thickness=6, troughcolor=HEX_BLUE_SOFT, background=HEX_TARGET_ORANGE)

    # --------------------------------------------------------------------------
    # TOP HEADER
    # --------------------------------------------------------------------------
    def create_header(self):
        header = tk.Frame(self, bg=HEX_BG_CARD, height=48, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        header.pack(side="top", fill="x", padx=10, pady=(8, 6))

        # Brand
        left_f = tk.Frame(header, bg=HEX_BG_CARD)
        left_f.pack(side="left", padx=12, pady=6)
        lbl_brand = tk.Label(left_f, text="TEAM EDITH", font=("Rajdhani", 16, "bold"), fg=HEX_BLUE_PRIMARY, bg=HEX_BG_CARD)
        lbl_brand.pack(side="left")
        lbl_sub = tk.Label(left_f, text="NIDAR AIRMOUSE GCS", font=FONT_MONO_SM, fg=HEX_TEXT_MUTED, bg=HEX_BG_SUBTLE, bd=1, relief="solid")
        lbl_sub.pack(side="left", padx=(10, 0), ipadx=6, ipady=2)

        # Center Controls
        center_f = tk.Frame(header, bg=HEX_BG_CARD)
        center_f.pack(side="left", expand=True)

        self.btn_sim = tk.Button(center_f, text="✓ SIMULATION", font=("Rajdhani", 11, "bold"), bg=HEX_BLUE_PRIMARY, fg="#FFFFFF",
                                 bd=0, padx=12, pady=3, command=lambda: self.set_mode("simulation"))
        self.btn_sim.pack(side="left", padx=2)

        self.btn_live = tk.Button(center_f, text="LIVE HARDWARE", font=("Rajdhani", 11, "bold"), bg=HEX_BG_SUBTLE, fg=HEX_TEXT_SEC,
                                  bd=1, relief="solid", padx=12, pady=3, command=lambda: self.set_mode("live"))
        self.btn_live.pack(side="left", padx=2)

        self.lbl_ros = tk.Label(center_f, text="● ROS 2 ONLINE", font=FONT_MONO_BD, fg=HEX_SUCCESS, bg=HEX_SUCCESS_SOFT,
                                bd=1, relief="solid", padx=8, pady=2)
        self.lbl_ros.pack(side="left", padx=14)

        lbl_net = tk.Label(center_f, text="📶 Wi-Fi 6 | 99% -42 dBm | 3 ms", font=FONT_MONO_SM, fg=HEX_TEXT_SEC, bg=HEX_BG_SUBTLE,
                           bd=1, relief="solid", padx=8, pady=2)
        lbl_net.pack(side="left", padx=6)

        # Right Indicators
        right_f = tk.Frame(header, bg=HEX_BG_CARD)
        right_f.pack(side="right", padx=12, pady=6)

        self.lbl_timer = tk.Label(right_f, text="MISSION  00:02:26", font=FONT_MONO_BD, fg=HEX_BLUE_PRIMARY, bg=HEX_BLUE_SOFT,
                                  bd=1, relief="solid", padx=8, pady=3)
        self.lbl_timer.pack(side="left", padx=(0, 10))

        self.lbl_bat = tk.Label(right_f, text="🔋 65% | 22.8V 6S", font=FONT_MONO_BD, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_SUBTLE,
                                bd=1, relief="solid", padx=8, pady=3)
        self.lbl_bat.pack(side="left")

    # --------------------------------------------------------------------------
    # ZERO-SCROLL DASHBOARD VIEWPORT
    # --------------------------------------------------------------------------
    def create_dashboard(self):
        container = tk.Frame(self, bg=HEX_BG_PRIMARY)
        container.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

        container.columnconfigure(0, weight=16) # SLAM & Survivors
        container.columnconfigure(1, weight=14) # Camera & Thermals
        container.columnconfigure(2, weight=10) # Mission, Compass & Controls
        container.rowconfigure(0, weight=1)

        # ----------------------------------------------------------------------
        # COLUMN 1: SLAM MAP (Top) & SURVIVOR TABLE (Bottom)
        # ----------------------------------------------------------------------
        col1 = tk.Frame(container, bg=HEX_BG_PRIMARY)
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        col1.rowconfigure(0, weight=16) # SLAM Map Card
        col1.rowconfigure(1, weight=10) # Survivor Table Card
        col1.columnconfigure(0, weight=1)

        # Card: SLAM Map
        card_slam = tk.Frame(col1, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_slam.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        head_slam = tk.Frame(card_slam, bg=HEX_BG_CARD)
        head_slam.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_slam, text="2D SLAM OCCUPANCY GRID", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")
        tk.Label(head_slam, text="15m × 15m | 1m GRID", font=FONT_MONO_SM, fg=HEX_TEXT_MUTED, bg=HEX_BG_SUBTLE, bd=1, relief="solid").pack(side="right", padx=2, ipadx=4)

        slam_body = tk.Frame(card_slam, bg=HEX_MAP_UNEXPLORED)
        slam_body.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))

        self.canvas_slam = tk.Canvas(slam_body, bg=HEX_MAP_UNEXPLORED, highlightthickness=0)
        self.canvas_slam.pack(side="left", fill="both", expand=True)

        # Map Toolbar
        toolbar = tk.Frame(slam_body, bg=HEX_BG_CARD)
        toolbar.pack(side="right", fill="y", padx=(4, 0))

        def make_btn(txt, cmd):
            b = tk.Button(toolbar, text=txt, font=FONT_MONO_BD, bg=HEX_BG_CARD, fg=HEX_TEXT_PRIMARY,
                          bd=1, relief="solid", width=3, pady=2, command=cmd)
            b.pack(pady=2)
            return b

        make_btn("+", lambda: self.zoom_map(1.15))
        make_btn("−", lambda: self.zoom_map(0.85))
        make_btn("⌂", self.reset_map)
        self.b_grid = make_btn("#", lambda: self.toggle_layer("grid"))
        self.b_path = make_btn("~", lambda: self.toggle_layer("path"))
        self.b_lidar = make_btn("◎", lambda: self.toggle_layer("lidar"))
        self.b_tgt = make_btn("⚑", lambda: self.toggle_layer("targets"))

        # Card: Survivor Localization
        card_surv = tk.Frame(col1, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_surv.grid(row=1, column=0, sticky="nsew")

        head_surv = tk.Frame(card_surv, bg=HEX_BG_CARD)
        head_surv.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_surv, text="SURVIVOR LOCALIZATION", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")
        self.lbl_tgt_badge = tk.Label(head_surv, text="4 / 6 LOCATED", font=FONT_MONO_SM, fg=HEX_TEXT_MUTED, bg=HEX_BG_SUBTLE, bd=1, relief="solid")
        self.lbl_tgt_badge.pack(side="right", padx=2, ipadx=4)

        prog_f = tk.Frame(card_surv, bg=HEX_BLUE_SOFT)
        prog_f.pack(side="top", fill="x", padx=8, pady=(0, 4))
        self.lbl_prog_txt = tk.Label(prog_f, text="TARGETS LOCATED: 4 OF 6", font=FONT_MONO_SM, bg=HEX_BLUE_SOFT, fg=HEX_TEXT_PRIMARY)
        self.lbl_prog_txt.pack(side="left", padx=8, pady=3)
        self.prog_bar = ttk.Progressbar(prog_f, style="TProgressbar", maximum=6, value=4, length=120)
        self.prog_bar.pack(side="right", padx=8, pady=3)

        # Table
        tbl_frame = tk.Frame(card_surv, bg=HEX_BG_CARD)
        tbl_frame.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 6))

        headers = ["ID", "STATUS", "METRIC GRID", "YOLO CONF"]
        for c, h in enumerate(headers):
            tk.Label(tbl_frame, text=h, font=FONT_HEADING, bg=HEX_BG_SUBTLE, fg=HEX_TEXT_MUTED, bd=1, relief="solid").grid(row=0, column=c, sticky="nsew", ipady=2)
            tbl_frame.columnconfigure(c, weight=1)

        self.tbl_rows = []
        for r, tgt in enumerate(self.targets):
            lbl_id = tk.Label(tbl_frame, text=tgt["id"], font=FONT_MONO_BD, bg=HEX_BG_CARD, fg=HEX_TEXT_PRIMARY)
            lbl_id.grid(row=r+1, column=0, sticky="nsew", pady=1)

            lbl_st = tk.Label(tbl_frame, text="FOUND" if tgt["found"] else "SEARCHING", font=FONT_MONO_BD,
                              bg=HEX_SUCCESS_SOFT if tgt["found"] else HEX_WARNING_SOFT,
                              fg=HEX_SUCCESS if tgt["found"] else HEX_WARNING, bd=1, relief="solid")
            lbl_st.grid(row=r+1, column=1, sticky="nsew", pady=1, padx=4)

            lbl_gr = tk.Label(tbl_frame, text=f"Grid [{tgt['grid']}]", font=FONT_MONO_SM, bg=HEX_BG_CARD, fg=HEX_TEXT_PRIMARY)
            lbl_gr.grid(row=r+1, column=2, sticky="nsew", pady=1)

            conf_str = f"{tgt['conf']:.1f}%" if tgt["conf"] > 0 else "--"
            lbl_cf = tk.Label(tbl_frame, text=conf_str, font=FONT_MONO_SM, bg=HEX_BG_CARD, fg=HEX_BLUE_PRIMARY if tgt["conf"] > 0 else HEX_TEXT_MUTED)
            lbl_cf.grid(row=r+1, column=3, sticky="nsew", pady=1)

            self.tbl_rows.append((lbl_st, lbl_cf))

        # ----------------------------------------------------------------------
        # COLUMN 2: CAMERA FEED & SYSTEM HEALTH
        # ----------------------------------------------------------------------
        col2 = tk.Frame(container, bg=HEX_BG_PRIMARY)
        col2.grid(row=0, column=1, sticky="nsew", padx=5)
        col2.rowconfigure(0, weight=14) # Camera Card
        col2.rowconfigure(1, weight=9)  # Health Card
        col2.columnconfigure(0, weight=1)

        # Card: Camera
        card_cam = tk.Frame(col2, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_cam.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        head_cam = tk.Frame(card_cam, bg=HEX_BG_CARD)
        head_cam.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_cam, text="ONBOARD CAM V2 (CSI)", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")
        tk.Label(head_cam, text="YOLOv8 ACTIVE", font=FONT_MONO_SM, fg=HEX_TEXT_MUTED, bg=HEX_BG_SUBTLE, bd=1, relief="solid").pack(side="right", padx=2, ipadx=4)

        self.canvas_cam = tk.Canvas(card_cam, bg="#0F172A", highlightthickness=0)
        self.canvas_cam.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))

        # Card: System Health
        card_health = tk.Frame(col2, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_health.grid(row=1, column=0, sticky="nsew")

        head_h = tk.Frame(card_health, bg=HEX_BG_CARD)
        head_h.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_h, text="SYSTEM HEALTH & THERMALS", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")
        tk.Label(head_h, text="4 BOARDS NOMINAL", font=FONT_MONO_SM, fg=HEX_TEXT_MUTED, bg=HEX_BG_SUBTLE, bd=1, relief="solid").pack(side="right", padx=2, ipadx=4)

        h_grid = tk.Frame(card_health, bg=HEX_BG_CARD)
        h_grid.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))
        h_grid.columnconfigure(0, weight=1)
        h_grid.columnconfigure(1, weight=1)
        h_grid.rowconfigure(0, weight=1)
        h_grid.rowconfigure(1, weight=1)

        def make_health_box(parent, title, temp, status, r, c):
            box = tk.Frame(parent, bg=HEX_BG_SUBTLE, bd=1, relief="solid")
            box.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)
            tk.Label(box, text=title, font=("Rajdhani", 10, "bold"), fg=HEX_TEXT_SEC, bg=HEX_BG_SUBTLE).pack(anchor="w", padx=6, pady=(3, 0))
            lbl_val = tk.Label(box, text=f"{temp}  |  {status}", font=FONT_MONO_BD, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_SUBTLE)
            lbl_val.pack(anchor="w", padx=6, pady=(0, 3))
            return lbl_val

        self.h_fc = make_health_box(h_grid, "MICOAIR H743v2", "38°C", "MAVLink OK", 0, 0)
        self.h_jet = make_health_box(h_grid, "JETSON ORIN NANO", "51°C", "YOLO+SLAM", 0, 1)
        self.h_esc = make_health_box(h_grid, "HOLYBRO 4IN1 ESC", "44°C", "DShot SYNC", 1, 0)
        self.h_pi = make_health_box(h_grid, "RASPBERRY PI 4", "46°C", "BRIDGE OK", 1, 1)

        # ----------------------------------------------------------------------
        # COLUMN 3: MISSION STATUS, COMPASS, BATTERY & CONTROLS
        # ----------------------------------------------------------------------
        col3 = tk.Frame(container, bg=HEX_BG_PRIMARY)
        col3.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        col3.rowconfigure(0, weight=8)  # Mission Card
        col3.rowconfigure(1, weight=11) # Compass & Battery Card
        col3.rowconfigure(2, weight=8)  # Flight Controls Card
        col3.columnconfigure(0, weight=1)

        # Card: Mission Status
        card_mis = tk.Frame(col3, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_mis.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        head_m = tk.Frame(card_mis, bg=HEX_BG_CARD)
        head_m.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_m, text="MISSION EXECUTIVE", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")
        self.lbl_mode_bd = tk.Label(head_m, text="SIMULATION", font=FONT_MONO_SM, fg=HEX_TEXT_MUTED, bg=HEX_BG_SUBTLE, bd=1, relief="solid")
        self.lbl_mode_bd.pack(side="right", padx=2, ipadx=4)

        m_body = tk.Frame(card_mis, bg=HEX_BG_CARD)
        m_body.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 6))

        self.lbl_mis_state = tk.Label(m_body, text="● EXPLORING", font=("Rajdhani", 14, "bold"), fg=HEX_BLUE_PRIMARY, bg=HEX_BLUE_SOFT,
                                      bd=1, relief="solid", padx=8, pady=3)
        self.lbl_mis_state.pack(anchor="w", fill="x", pady=2)

        self.lbl_mis_goal = tk.Label(m_body, text="ACTIVE: AUTONOMOUS SEARCH", font=FONT_MONO_SM, fg=HEX_TEXT_SEC, bg=HEX_BG_CARD)
        self.lbl_mis_goal.pack(anchor="w", pady=2)

        self.lbl_alt = tk.Label(m_body, text="ALT (MTF-01): 1.18 m AGL", font=FONT_MONO_BD, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD)
        self.lbl_alt.pack(anchor="w", pady=2)

        # Card: Compass & Battery
        card_comp = tk.Frame(col3, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_comp.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        head_c = tk.Frame(card_comp, bg=HEX_BG_CARD)
        head_c.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_c, text="HEADING & 6S CELLS", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")

        split_f = tk.Frame(card_comp, bg=HEX_BG_CARD)
        split_f.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))

        self.canvas_comp = tk.Canvas(split_f, bg=HEX_BG_CARD, width=120, height=120, highlightthickness=0)
        self.canvas_comp.pack(side="left", padx=4)

        cell_f = tk.Frame(split_f, bg=HEX_BG_CARD)
        cell_f.pack(side="right", fill="both", expand=True, padx=4)
        self.cell_lbls = []
        for i in range(6):
            cl = tk.Label(cell_f, text=f"C{i+1}: 3.80V", font=("JetBrains Mono", 8), bg=HEX_BG_SUBTLE, fg=HEX_TEXT_SEC, bd=1, relief="solid")
            cl.pack(fill="x", pady=1, ipady=1)
            self.cell_lbls.append(cl)

        # Card: Flight Controls
        card_ctrl = tk.Frame(col3, bg=HEX_BG_CARD, bd=1, relief="solid", highlightbackground=HEX_BORDER, highlightthickness=1)
        card_ctrl.grid(row=2, column=0, sticky="nsew")

        head_ctrl = tk.Frame(card_ctrl, bg=HEX_BG_CARD)
        head_ctrl.pack(side="top", fill="x", padx=10, pady=6)
        tk.Label(head_ctrl, text="FLIGHT CONTROLS", font=FONT_HEADING, fg=HEX_TEXT_PRIMARY, bg=HEX_BG_CARD).pack(side="left")

        ctrl_body = tk.Frame(card_ctrl, bg=HEX_BG_CARD)
        ctrl_body.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 8))

        btn_start = tk.Button(ctrl_body, text="▶ START MISSION", font=("Rajdhani", 12, "bold"), bg=HEX_BLUE_PRIMARY, fg="#FFFFFF",
                              bd=0, pady=6, command=self.cmd_start)
        btn_start.pack(fill="x", pady=2)

        btn_rtl = tk.Button(ctrl_body, text="⤺ RETURN TO HOME (LZ)", font=("Rajdhani", 12, "bold"), bg=HEX_BLUE_SOFT, fg=HEX_BLUE_PRIMARY,
                            bd=1, relief="solid", pady=6, command=self.cmd_rtl)
        btn_rtl.pack(fill="x", pady=2)

        btn_abort = tk.Button(ctrl_body, text="⚠ EMERGENCY ABORT", font=("Rajdhani", 12, "bold"), bg=HEX_DANGER, fg="#FFFFFF",
                             bd=0, pady=6, command=self.cmd_abort)
        btn_abort.pack(fill="x", pady=2)

    # --------------------------------------------------------------------------
    # MAP & DRAWING ENGINES
    # --------------------------------------------------------------------------
    def zoom_map(self, f):
        self.map_zoom = max(0.6, min(2.5, self.map_zoom * f))

    def reset_map(self):
        self.map_zoom = 1.0

    def toggle_layer(self, layer):
        self.map_layers[layer] = not self.map_layers[layer]

    def draw_slam(self):
        c = self.canvas_slam
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10: return

        arena_m = 15.0
        min_dim = min(w, h) * 0.88 * self.map_zoom
        m_to_px = min_dim / arena_m
        ox = (w - min_dim) / 2.0
        oy = (h - min_dim) / 2.0

        # Explored Corridors
        for i in range(len(self.waypoints) - 1):
            p1 = self.waypoints[i]
            p2 = self.waypoints[i + 1]
            c.create_line(ox + p1[0] * m_to_px, oy + p1[1] * m_to_px,
                          ox + p2[0] * m_to_px, oy + p2[1] * m_to_px,
                          width=1.2 * m_to_px, fill=HEX_MAP_EXPLORED, capstyle="round")

        # 1m Grid
        if self.map_layers["grid"]:
            for i in range(int(arena_m) + 1):
                gx = ox + i * m_to_px
                gy = oy + i * m_to_px
                c.create_line(gx, oy, gx, oy + min_dim, fill=HEX_GRID_LINE)
                c.create_line(ox, gy, ox + min_dim, gy, fill=HEX_GRID_LINE)
                if i < int(arena_m):
                    c.create_text(gx + 0.35 * m_to_px, oy - 6, text=chr(65 + i), font=("JetBrains Mono", 7), fill=HEX_TEXT_MUTED)
                    c.create_text(ox - 8, gy + 0.5 * m_to_px, text=str(i + 1), font=("JetBrains Mono", 7), fill=HEX_TEXT_MUTED)

        # Outer Walls & Partitions
        c.create_rectangle(ox, oy, ox + min_dim, oy + min_dim, outline=HEX_MAP_WALLS, width=3)
        walls = [
            ((2.5, 0), (2.5, 3)), ((0, 5.5), (4.5, 5.5)),
            ((5.5, 0), (5.5, 6.5)), ((5.5, 8), (5.5, 15)),
            ((7.5, 3.5), (10, 3.5)), ((9.5, 5.5), (15, 5.5)),
            ((7.5, 10), (13.5, 10)), ((2.5, 9.5), (2.5, 15)),
            ((2.5, 12), (8, 12))
        ]
        for w1, w2 in walls:
            c.create_line(ox + w1[0] * m_to_px, oy + w1[1] * m_to_px,
                          ox + w2[0] * m_to_px, oy + w2[1] * m_to_px,
                          fill=HEX_MAP_WALLS, width=3)

        # Entry LZ (A1)
        lz_x = ox + 1.2 * m_to_px
        lz_y = oy + 1.2 * m_to_px
        c.create_oval(lz_x - 0.6 * m_to_px, lz_y - 0.6 * m_to_px,
                      lz_x + 0.6 * m_to_px, lz_y + 0.6 * m_to_px,
                      fill=HEX_SUCCESS_SOFT, outline=HEX_SUCCESS, width=1.5)
        c.create_text(lz_x, lz_y, text="LZ", font=("Rajdhani", 8, "bold"), fill=HEX_SUCCESS)

        # Trajectory
        if self.map_layers["path"] and len(self.trajectory) > 1:
            coords = []
            for pt in self.trajectory:
                coords.extend([ox + pt[0] * m_to_px, oy + pt[1] * m_to_px])
            c.create_line(*coords, fill=HEX_BLUE_PRIMARY, width=2, dash=(4, 4))

        # Drone coords
        dx_px = ox + self.drone_x * m_to_px
        dy_px = oy + self.drone_y * m_to_px

        # RPLiDAR C1 Scan Points
        if self.map_layers["lidar"]:
            self.lidar_angle += 0.08
            num_rays = 32
            for i in range(num_rays):
                ang = self.lidar_angle + (i * 2.0 * math.pi) / num_rays
                dist = (1.5 + math.sin(ang * 3 + self.drone_x) * 0.8) * m_to_px
                lx = dx_px + math.cos(ang) * dist
                ly = dy_px + math.sin(ang) * dist
                c.create_line(dx_px, dy_px, lx, ly, fill="#C7F3FA", width=1)
                c.create_oval(lx - 1.5, ly - 1.5, lx + 1.5, ly + 1.5, fill=HEX_CYAN_ACCENT, outline="")

        # Targets
        if self.map_layers["targets"]:
            for tgt in self.targets:
                if not tgt["found"]: continue
                tx = ox + tgt["x"] * m_to_px
                ty = oy + tgt["y"] * m_to_px
                c.create_oval(tx - 9, ty - 9, tx + 9, ty + 9, fill="#FFEDD5", outline="")
                c.create_oval(tx - 5, ty - 5, tx + 5, ty + 5, fill=HEX_TARGET_ORANGE, outline="")
                c.create_text(tx + 8, ty - 4, anchor="w", text=f"{tgt['id']} [{tgt['grid']}]",
                              font=("Rajdhani", 9, "bold"), fill=HEX_TEXT_PRIMARY)

        # Directional Quadcopter Drone Marker
        rad = math.radians(self.drone_yaw)
        # Quad arms
        c.create_line(dx_px - 8, dy_px - 8, dx_px + 8, dy_px + 8, fill=HEX_BLUE_PRIMARY, width=2.5)
        c.create_line(dx_px - 8, dy_px + 8, dx_px + 8, dy_px - 8, fill=HEX_BLUE_PRIMARY, width=2.5)
        for mx, my in [(-8, -8), (8, -8), (-8, 8), (8, 8)]:
            c.create_oval(dx_px + mx - 3, dy_px + my - 3, dx_px + mx + 3, dy_px + my + 3, fill=HEX_CYAN_ACCENT, outline="")

        # Heading triangle
        hx = dx_px - math.sin(rad) * 14
        hy = dy_px + math.cos(rad) * 14
        c.create_polygon(hx, hy, dx_px - math.cos(rad) * 5, dy_px - math.sin(rad) * 5,
                         dx_px + math.cos(rad) * 5, dy_px + math.sin(rad) * 5, fill=HEX_BLUE_PRIMARY)

    def draw_camera(self):
        c = self.canvas_cam
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10: return

        # Room corridor geometry
        c.create_polygon(0, h, w * 0.35, h * 0.55, w * 0.65, h * 0.55, w, h, fill="#1E293B")
        c.create_line(0, 0, w * 0.35, h * 0.55, fill="#475569", width=1.5)
        c.create_line(w, 0, w * 0.65, h * 0.55, fill="#475569", width=1.5)

        # Reticle
        cx, cy = w / 2, h / 2
        c.create_rectangle(cx - 15, cy - 15, cx + 15, cy + 15, outline=HEX_CYAN_ACCENT, width=1)
        c.create_line(cx - 22, cy, cx + 22, cy, fill=HEX_CYAN_ACCENT)
        c.create_line(cx, cy - 22, cx, cy + 22, fill=HEX_CYAN_ACCENT)

        # YOLOv8 Target Bounding Box
        t = time.time()
        bx = w * 0.42 + math.sin(t * 1.5) * 6
        by = h * 0.36 + math.cos(t * 1.2) * 3
        bw = w * 0.18
        bh = h * 0.34

        c.create_rectangle(bx, by, bx + bw, by + bh, outline=HEX_CYAN_ACCENT, width=2)
        c.create_rectangle(bx, by - 16, bx + bw, by, fill=HEX_CYAN_ACCENT, outline="")
        c.create_text(bx + 4, by - 8, anchor="w", text="HUMAN 94.2%", font=("JetBrains Mono", 8, "bold"), fill="#FFFFFF")

        # OSD Header
        if int(time.time() * 2) % 2 == 0:
            c.create_oval(14, 14, 22, 22, fill=HEX_DANGER, outline="")
        c.create_text(28, 18, anchor="w", text="REC", font=("JetBrains Mono", 9, "bold"), fill=HEX_DANGER)
        c.create_text(70, 18, anchor="w", text="30 FPS | 1280x720", font=("JetBrains Mono", 9), fill="#FFFFFF")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:22]
        c.create_text(w - 180, 18, anchor="w", text=now_str, font=("JetBrains Mono", 9), fill="#FFFFFF")

    def draw_compass(self):
        c = self.canvas_comp
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10: return

        cx, cy = w / 2, h / 2 - 8
        radius = min(w, h) * 0.38

        c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=HEX_BORDER, width=2, fill="#FFFFFF")
        c.create_text(cx, cy - radius + 10, text="N", font=("Rajdhani", 8, "bold"), fill=HEX_DANGER)
        c.create_text(cx, cy + radius - 10, text="S", font=("Rajdhani", 8, "bold"), fill=HEX_TEXT_MUTED)
        c.create_text(cx + radius - 10, cy, text="E", font=("Rajdhani", 8, "bold"), fill=HEX_TEXT_MUTED)
        c.create_text(cx - radius + 10, cy, text="W", font=("Rajdhani", 8, "bold"), fill=HEX_TEXT_MUTED)

        # Needle
        rad = math.radians(self.drone_yaw)
        nx = cx + math.sin(rad) * (radius - 8)
        ny = cy - math.cos(rad) * (radius - 8)
        sx = cx - math.sin(rad) * (radius - 8)
        sy = cy + math.cos(rad) * (radius - 8)

        c.create_line(cx, cy, nx, ny, fill=HEX_DANGER, width=3)
        c.create_line(cx, cy, sx, sy, fill=HEX_TEXT_MUTED, width=3)
        c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=HEX_TEXT_PRIMARY)

        cardinal = "N" if (self.drone_yaw > 315 or self.drone_yaw <= 45) else \
                   "E" if self.drone_yaw <= 135 else \
                   "S" if self.drone_yaw <= 225 else "W"
        c.create_text(cx, h - 8, text=f"{int(self.drone_yaw)}° {cardinal}", font=("JetBrains Mono", 10, "bold"), fill=HEX_TEXT_PRIMARY)

    # --------------------------------------------------------------------------
    # SIMULATION & TELEMETRY LOOPS
    # --------------------------------------------------------------------------
    def start_loops(self):
        def fast_tick():
            if self.mode == "simulation":
                cur_wp = self.waypoints[self.wp_idx]
                nxt_wp = self.waypoints[self.target_wp_idx]

                self.wp_t += 0.012
                if self.wp_t >= 1.0:
                    self.wp_t = 0.0
                    self.wp_idx = self.target_wp_idx
                    if self.mission_state == "RAPID_RTL":
                        self.target_wp_idx = max(0, self.wp_idx - 1)
                        if self.wp_idx == 0:
                            self.mission_state = "LANDED"
                            self.lbl_mis_state.config(text="● LANDED (SAFE)", bg=HEX_SUCCESS_SOFT, fg=HEX_SUCCESS)
                    else:
                        self.target_wp_idx = (self.wp_idx + 1) % len(self.waypoints)

                self.drone_x = cur_wp[0] + (nxt_wp[0] - cur_wp[0]) * self.wp_t
                self.drone_y = cur_wp[1] + (nxt_wp[1] - cur_wp[1]) * self.wp_t

                dx = nxt_wp[0] - cur_wp[0]
                dy = nxt_wp[1] - cur_wp[1]
                deg = math.degrees(math.atan2(dy, dx)) + 90.0
                self.drone_yaw = (deg + 360.0) % 360.0

                if not self.trajectory or math.hypot(self.drone_x - self.trajectory[-1][0], self.drone_y - self.trajectory[-1][1]) > 0.3:
                    self.trajectory.append((self.drone_x, self.drone_y))
                    if len(self.trajectory) > 80: self.trajectory.pop(0)

                self.lbl_alt.config(text=f"ALT (MTF-01): {(1.18 + math.sin(time.time()*2)*0.02):.2f} m AGL")

            self.draw_slam()
            self.draw_camera()
            self.draw_compass()
            self.after(50, fast_tick)

        def slow_tick():
            self.mission_time_sec += 1
            m = self.mission_time_sec // 60
            s = self.mission_time_sec % 60
            self.lbl_timer.config(text=f"MISSION  00:{m:02d}:{s:02d}")

            if self.battery_pct > 10:
                self.battery_pct -= 0.02
                self.battery_v = (self.battery_pct / 100.0) * (25.2 - 19.8) + 19.8
                self.lbl_bat.config(text=f"🔋 {int(self.battery_pct)}% | {self.battery_v:.1f}V 6S")
                cell_v = f"{self.battery_v / 6.0:.2f}V"
                for i, cl in enumerate(self.cell_lbls):
                    cl.config(text=f"C{i+1}: {cell_v}")

            self.after(1000, slow_tick)

        self.after(100, fast_tick)
        self.after(1000, slow_tick)

    # --------------------------------------------------------------------------
    # TARGET DISCOVERY & AUDIO ALERTS
    # --------------------------------------------------------------------------
    def play_tactical_chirp(self):
        try:
            winsound.Beep(920, 90)
            winsound.Beep(1280, 80)
        except Exception:
            pass

    def play_victory_alarm(self):
        try:
            winsound.Beep(659, 140)
            winsound.Beep(880, 140)
            winsound.Beep(1175, 280)
        except Exception:
            pass

    def discover_next_target(self):
        next_t = next((t for t in self.targets if not t["found"]), None)
        if next_t:
            next_t["found"] = True
            next_t["conf"] = 92.4
            idx = self.targets.index(next_t)
            lbl_st, lbl_cf = self.tbl_rows[idx]
            lbl_st.config(text="FOUND", bg=HEX_SUCCESS_SOFT, fg=HEX_SUCCESS)
            lbl_cf.config(text="92.4%", fg=HEX_BLUE_PRIMARY)

            found_cnt = sum(1 for t in self.targets if t["found"])
            self.lbl_tgt_badge.config(text=f"{found_cnt} / 6 LOCATED")
            self.lbl_prog_txt.config(text=f"TARGETS LOCATED: {found_cnt} OF 6")
            self.prog_bar["value"] = found_cnt

            if found_cnt < 6:
                self.play_tactical_chirp()
            else:
                self.play_victory_alarm()
                self.mission_state = "RAPID_RTL"
                self.lbl_mis_state.config(text="● RAPID RTL", bg=HEX_SUCCESS_SOFT, fg=HEX_SUCCESS)
                self.lbl_mis_goal.config(text="ALL 6 FOUND -> RETURN TO LZ")

    # --------------------------------------------------------------------------
    # OPERATIONAL CONTROLS
    # --------------------------------------------------------------------------
    def set_mode(self, new_mode):
        self.mode = new_mode
        if new_mode == "simulation":
            self.btn_sim.config(bg=HEX_BLUE_PRIMARY, fg="#FFFFFF")
            self.btn_live.config(bg=HEX_BG_SUBTLE, fg=HEX_TEXT_SEC)
            self.lbl_ros.config(text="● ROS 2 ONLINE", bg=HEX_SUCCESS_SOFT, fg=HEX_SUCCESS)
            self.lbl_mode_bd.config(text="SIMULATION")
        else:
            self.btn_sim.config(bg=HEX_BG_SUBTLE, fg=HEX_TEXT_SEC)
            self.btn_live.config(bg=HEX_WARNING, fg="#FFFFFF")
            self.lbl_ros.config(text="● ROS 2 OFFLINE", bg=HEX_DANGER_SOFT, fg=HEX_DANGER)
            self.lbl_mode_bd.config(text="LIVE HARDWARE")

    def cmd_start(self):
        self.mission_state = "EXPLORING"
        self.lbl_mis_state.config(text="● EXPLORING", bg=HEX_BLUE_SOFT, fg=HEX_BLUE_PRIMARY)
        self.lbl_mis_goal.config(text="ACTIVE: AUTONOMOUS SEARCH")
        self.play_tactical_chirp()

    def cmd_rtl(self):
        self.mission_state = "RAPID_RTL"
        self.lbl_mis_state.config(text="● RAPID RTL", bg=HEX_BLUE_SOFT, fg=HEX_BLUE_PRIMARY)
        self.lbl_mis_goal.config(text="RETURNING TO ENTRY LZ")
        self.play_tactical_chirp()

    def cmd_abort(self):
        self.mission_state = "ABORTED"
        self.lbl_mis_state.config(text="⚠ ABORTED (RTL)", bg=HEX_DANGER_SOFT, fg=HEX_DANGER)
        self.lbl_mis_goal.config(text="EMERGENCY RTL DISPATCHED")
        self.play_tactical_chirp()

if __name__ == "__main__":
    app = EdithGCSApp()
    app.mainloop()
