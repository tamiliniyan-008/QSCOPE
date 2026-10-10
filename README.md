# ATOM-QSA

**Atom Interferometer — Q-SCOPE Risk Certificate System & Statevector Quantum Health Monitor**

This project provides a comprehensive platform to analyze atom-interferometer measurements, reconstruct residual phase uncertainty, certify nonlinear measurement-model discrepancy ($d_{\text{mean}}$ bounds), select estimator policies (`STAY_EKF` / `ESCALATE_NONLINEAR` / `ABSTAIN`), and monitor sensor health using a 4-qubit Statevector Quantum Monitor with adaptive CUSUM drift detection.

---

## Architecture Overview

1. **Mission Telemetry Engine**: Multi-channel sensor ingestion supporting population $p(t)$, phase $\phi(t)$, tri-axial accelerations ($a_x, a_y, a_z$), and fringe contrast $C(t)$.
2. **Q-SCOPE Risk Certificate**: Evaluates $d_{\text{mean}}$ nonlinear discrepancy bounds against safety threshold $\tau = 0.067349$.
3. **Three-State Decision Policy**: Automatically routes tracking between linear EKF, nonlinear phase-grid estimation, and mission abstention.
4. **4-Qubit Statevector Quantum Monitor**: Maps extracted vibration features $[mean, std, slope, abs\_diff\_mean]$ to rotation angles $[\theta_0, \theta_1, \theta_2, \theta_3] \in [0, \pi]$, evaluates quantum state overlap fidelity $F_t = |\langle\psi_{\text{ref}}|\psi_t\rangle|^2$, and accumulates fidelity loss $L_t = 1 - F_t$ in an adaptive leave-one-out CUSUM accumulator.
5. **Modern Mission Control UI**: Built with React 18, Vite, Tailwind CSS, and Clean Laboratory Light Mode styling.

---

## Quickstart Guide

### 1. Run Automated Tests
```cmd
.\.venv\Scripts\python.exe -m pytest tests
```
*(All 14 tests covering live quantum endpoints, statevector simulation, and EKF pipeline pass).*

### 2. Generate Synthetic Mission Telemetry
```cmd
.\.venv\Scripts\python.exe generate_data.py
```
*(Writes `data\sample_mission.csv`).*

### 3. Start Backend API Server
```cmd
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Docs: **http://localhost:8000/docs**
- Health Check: **http://localhost:8000/health**

### 4. Start Frontend Mission Control UI
In a separate terminal:
```cmd
cd frontend
npm.cmd run dev
```
- Open Mission Control: 👉 **http://localhost:3000**

---

## Frontend Dashboard Views

- **⚡ Product Live Pipeline (Default View)**:
  - **Stage 1 (Left - Analogue Wave Stream)**: 60 FPS live oscilloscope canvas simulating continuous interference fringes $p(t)$ and phase $\phi(t)$ from the cold-atom vacuum sensor, with machine connect/disconnect toggle and vibration drift injection.
  - **Stage 2 (Center - Quantum Processor Artifact)**: Glowing animated 4-qubit quantum core showing data re-uploading ($RY(\theta_i)$), laser entanglement gates (CNOT), real-time state overlap fidelity $F_t = |\langle\psi_{\text{ref}}|\psi_t\rangle|^2$, and loss $L_t$.
  - **Stage 3 (Right - Live Text Decision Output)**: Authoritative natural-language diagnostic intelligence feed, real-time status badges (`STAY_EKF` vs `ESCALATE_NONLINEAR`), risk certification summaries, and instant report copying.
- **Tab 1: Mission Telemetry Stream**: Multi-channel time-series charts, mission CSV uploader, and step-by-step window stepper.
- **Tab 2: Q-SCOPE Risk Certificate**: $d_{\text{mean}}$ discrepancy bounds gauge, Three-State Decision Policy banner, and interactive threshold slider.
- **Tab 3: 4-Qubit Quantum Engine**: Detailed circuit schematic, parameter shift gradients, and leave-one-out CUSUM accumulator.
- **Tab 4: Audit & History Log**: Filterable log of analyzed sensor windows, SQLite audit trail, and one-click JSON/CSV data export.

---

## Standalone Quantum CLI Tools

```cmd
# Run quantum engine self-test (80+ mathematical checks)
.\.venv\Scripts\python.exe -m modules.quantum_simulation.quantum_monitor --selftest

# Run standalone dataset analysis & prediction CLI
.\.venv\Scripts\python.exe -m modules.quantum_simulation.quantum_monitor --analyze data\sample_mission.csv --column population --baseline first:8
```
