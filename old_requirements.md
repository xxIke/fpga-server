# FPGA Development Environment Project

**Target Board:** Nandland Go Board (Lattice iCE40HX1K)
**Primary Environment Choice:** Option A — Centralized server with browser-based IDE

---

## 1. Objective

Create a **centralized, browser-accessible FPGA development environment** that allows students to:

* Write HDL (Verilog) for the Nandland Go Board
* Compile designs into a valid `.bin` bitstream using **open-source tooling**
* View build results and error messages
* Download the resulting bitstream
* Do all of the above **without installing any FPGA tools or managing licenses**

The environment must be:

* Fast to spin up
* Reliable for a classroom of ~25 students
* Simple enough to support during a single instructional day
* Reusable for future offerings with minimal rework

---

## 2. Non-Goals (Explicitly Out of Scope)

To keep scope controlled, the system will **not** initially attempt to:

* Provide local waveform viewing (GTKWave)
* Provide schematic or RTL visualization
* Support multiple FPGA boards or vendors
* Allow students to directly program hardware from their laptops
* Implement advanced job scheduling, authentication, or grading automation

These can be layered later once the core workflow is stable.

---

## 3. Core Design Principles

1. **Single Source of Truth**

   * One Ubuntu mini-PC hosts:

     * Toolchain
     * Constraints
     * Build scripts
     * Student workspaces
   * Eliminates environment drift.

2. **Zero Student OS-Level Access**

   * Students must **not** receive Linux user accounts or SSH access.
   * All interaction occurs through a **browser-based environment**.
   * Any notion of “accounts” applies only at the **application layer**, not the operating system.

3. **Browser-First Development**

   * Use **code-server (VS Code in the browser)** as the primary development interface.
   * Students only need:

     * WiFi
     * A modern browser

4. **Open Toolchain First**

   * Use `yosys`, `nextpnr-ice40`, `icestorm`.
   * Avoid ICEcube2, licensing, and vendor GUIs entirely.

5. **Instructor-Controlled Execution**

   * Students prepare HDL and review results.
   * The **instructor explicitly triggers each build** and programs hardware.
   * Prevents uncontrolled load and keeps hardware interaction intentional.

6. **Fail Fast, Fail Loud**

   * Compilation errors should surface clearly and immediately.
   * Logs are a first-class output.

---

## 4. High-Level Architecture

```
Students (Browser)
        |
        | HTTP / WebSocket
        v
----------------------------------
Ubuntu Mini-PC
----------------------------------
Web IDE / Frontend
  - Code editor
  - Build button
  - Log viewer
  - Download link

Backend Service
  - Per-student workspace
  - Build orchestration
  - Toolchain invocation

Open-Source FPGA Toolchain
  - yosys
  - nextpnr-ice40
  - icepack

(Manual step)
Instructor programs board via USB
```

---

## 5. Functional Requirements

### 5.1 Student-Facing Features

Each student must be able to:

* Access the environment via a web browser (code-server)
* Edit one or more HDL files
* View build status and logs
* Download the resulting `.bin` bitstream
* Iterate on designs of **limited complexity** (basic device interactions, LEDs, buttons, simple FSMs)

Students **do not**:

* Trigger builds directly
* Program hardware
* Receive OS-level credentials

### 5.2 Instructor-Facing Features

Instructor must be able to:

* Select a student workspace
* Trigger a build for that workspace
* Observe build success/failure and logs
* Program a Go Board with a selected `.bin` file
* Control build order and pacing during class

---

## 6. Implementation Plan (Actionable)

### Phase 1 — Toolchain & Reference Build (Foundation)

**Objective:** Prove that the board can be built end-to-end using open tools.

Actions:

* Install on mini-PC:

  * `yosys`
  * `nextpnr-ice40`
  * `icestorm`
* Create:

  * Known-good `constraints.pcf` for the Go Board
  * Minimal `top.v` (LED blink / counter)
* Write:

  * A standalone build script or Makefile
* Verify:

  * `.bin` successfully programs the Go Board via `iceprog`

Deliverable:

* A reproducible CLI build that works 100% of the time.

---

### Phase 2 — Workspace & Identity Model

**Objective:** Define how student work is isolated without OS-level accounts.

Decisions:

* No Linux user accounts for students
* All students share a **single OS user** running code-server
* Student identity exists only at the **application / workspace level**

Workspace layout example:

```
/srv/fpga/
  template/
    src/
    constraints.pcf
    Makefile
    README.md
  students/
    student01/
      src/
      build/
      logs/
    student02/
      ...
```

Actions:

* Create template workspace
* Write script to clone/reset template into `students/<id>/`
* Ensure code-server exposes only the `/srv/fpga/students` tree

Deliverable:

* Deterministic, resettable student workspaces without OS accounts.

---

### Phase 3 — code-server Integration (Primary UX)

**Objective:** Provide a stable, browser-based IDE for HDL development.

Actions:

* Install and configure **code-server** on the mini-PC
* Restrict workspace view to student directories
* Disable unnecessary extensions and features
* Pre-configure:

  * Verilog syntax highlighting
  * Read-only template files if desired

Deliverable:

* Students write and edit HDL entirely in-browser.

---

### Phase 4 — Build Queue & Instructor Control

**Objective:** Prevent uncontrolled builds and manage pacing.

Decisions:

* All builds go through a **global FIFO queue**
* Only the instructor triggers builds

Actions:

* Implement build queue (simple FIFO or lock-based worker)
* Each job:

  * Targets one student workspace
  * Runs build script
  * Captures logs
  * Produces `.bin`
* Enforce:

  * One active build at a time
  * Build timeout

Deliverable:

* Predictable, serialized builds under instructor control.

---

### Phase 5 — Classroom Hardening

**Objective:** Make the system reliable under teaching pressure.

Actions:

* Improve error surfacing (common yosys / nextpnr failures)
* Pre-test with multiple queued builds
* Add instructor utilities:

  * Reset a single student workspace
  * Reset all workspaces
  * Clear build queue

Deliverable:

* System is safe to use live with minimal troubleshooting.

---

## 7. Known Tradeoffs & Rationale

& Rationale

| Choice                   | Tradeoff                     | Why It’s Acceptable                  |
| ------------------------ | ---------------------------- | ------------------------------------ |
| Centralized server       | Single point of failure      | Simpler support; mini-PC is reliable |
| Browser IDE              | Less powerful than local IDE | Eliminates installs                  |
| Manual board programming | Slower demo throughput       | Only 2 boards anyway                 |
| Open-source tools        | Less vendor GUI polish       | No licenses, fully scriptable        |

---

## 8. Success Criteria

This project is successful if:

* A student with **zero prior FPGA experience** can:

  * Join WiFi
  * Open a browser
  * Modify HDL
  * Observe build results
* No student receives Linux credentials or installs FPGA tools
* All builds are controlled, queued, and observable by the instructor
* You spend class time teaching FPGA concepts, not debugging environments
