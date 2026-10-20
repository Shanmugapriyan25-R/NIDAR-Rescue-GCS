# 🛡️ Security Policy — NIDAR Rescue GCS

The **TEAM EDITH NIDAR Rescue Ground Control Station (GCS)** is an autonomous UAV monitoring, SLAM mapping, and survivor localization console engineered for mission-critical search-and-rescue operations. 

Given the physical safety considerations associated with multirotor flight control and tactical robotics, security and failsafe reliability are treated as tier-1 core engineering requirements.

---

## 📌 Supported Versions

We actively provide security patches, safety updates, and vulnerability fixes for the following releases:

| Version / Branch | Supported | Notes |
| :--- | :--- | :--- |
| `main` (Latest) | ✅ Yes | Active development, latest PyQt6 architecture & security updates |
| `shan` | ✅ Yes | Tactical navigation workspaces, health model, and 2D SLAM integration |
| `< 2.0.0` (Tkinter) | ❌ No | Legacy desktop baseline; upgrade to PyQt6 console recommended |

---

## 🔒 Tactical Flight Safety Architecture

The GCS implements strict defense-in-depth safety boundaries to protect ground personnel and airframes:

### 1. Command Verification & Bounded Telemetry
- All incoming operator commands (`START_MISSION`, `ABORT_MISSION`, `RETURN_HOME`, `HOLD`, `SET_SUBSYSTEM_STATE`, `STAGE_WAYPOINT`) are validated and clamped against flight envelope constraints before dispatch.
- Waypoint coordinates are bound strictly within arena metric boundaries ($0 \le X \le 15\,\text{m}$, $0 \le Y \le 15\,\text{m}$, $0 \le Z \le 5\,\text{m}$).
- Out-of-bounds or malformed commands are rejected with explicit operator telemetry warnings.

### 2. Autonomous Fail-Safe Lifecycle
- **Heartbeat & Link Loss Detection:** If telemetry connection or WebSocket heartbeat drops for more than $2.0\,\text{seconds}$, the system automatically enters `STALE / LINK WARNING` state and commands the UAV into a safe hover/hold or autonomous Return-to-Launch (RTL).
- **Emergency Abort:** Physical/UI one-click Abort immediately terminates autonomous trajectory execution, commands zero horizontal velocity, and engages emergency landing protocols.
- **Low Battery RTL:** The flight state machine constantly evaluates remaining LiPo battery voltage and trigger automatic return-home sequencing when capacity falls below emergency thresholds.

### 3. Simulation & Real Hardware Isolation
- Simulation mode operates deterministically and is clearly labeled in the operator HUD.
- Simulated states, mock target injections, and synthetic diagnostic overrides can never inadvertently broadcast to active physical hardware interfaces.

---

## 🌐 Network & Bridge Security

The GCS interfaces with onboard autonomy stacks via ROS 2 WebSocket bridges and MAVLink v2:

1. **Localhost / Controlled Interface Binding:**
   - The WebSocket telemetry bridge (`ros2_gcs_bridge.py`) binds by default to controlled network interfaces.
   - For field deployments across tactical ad-hoc Wi-Fi / mesh networks, run the bridge over a private WireGuard VPN or secure VLAN.
2. **MAVLink v2 Packet Integrity:**
   - Packet framing utilizes MAVLink v2 CRC-16 checks to protect against frame corruption and spoofing.
3. **No Unauthenticated Remote Execution:**
   - The GCS does not expose unauthenticated shell or remote code execution entry points.

---

## 🔑 Credential & Asset Protection

- **Zero Hardcoded Secrets:** No API keys, cloud tokens, private cryptographic keys, or credentials are stored in this repository.
- **Sanitized Reconnaissance Data:** Mission snapshots and video recordings are stored locally under `output/snapshots/` and `output/recordings/` and are strictly excluded from version control via `.gitignore` to prevent leakage of operational reconnaissance data or survivor imagery.

---

## 🚨 Reporting a Vulnerability

If you identify a security vulnerability, safety flaw, or potential remote command exploit in this codebase:

1. **Do NOT open a public GitHub issue.**
2. Send an email to the security and development maintainers:
   - **Lead Architect:** `shanmugapriyan.r@outlook.com`
   - **Repository:** [Shanmugapriyan25-R/NIDAR-Rescue-GCS](https://github.com/Shanmugapriyan25-R/NIDAR-Rescue-GCS)
3. Include detailed steps to reproduce the vulnerability, including:
   - Operating system and Python version
   - Component affected (`edith_gcs_qt.py`, `ros2_gcs_bridge.py`, `gcs_data_plugins.py`)
   - Proof of concept payload or command sequence
   - Expected vs actual behavior

### Response Timeline
- **Initial Acknowledgement:** Within **24–48 hours**.
- **Assessment & Triage:** Within **3 business days**.
- **Fix & Public Advisory:** Dependent on severity, typically within **7 business days**.
