# Windows Lab Server Requirements (Draft)

## 1. Purpose
Build a reliable, headless classroom FPGA lab server that runs on a **Windows host only** (no dependency on WSL USB passthrough), where students edit code and the instructor controls build/program operations for Nandland Go Board labs.

## 2. Goals
- Provide repeatable student builds from centralized workspaces.
- Keep instructor in control of board programming.
- Avoid WSL USB instability for repeated class use.
- Support class-day operations with fast recovery and minimal manual troubleshooting.
- Operate fully offline on a local network.

## 3. Stakeholders and Roles
- Instructor: manages workspaces, queue, builds, and programming.
- Student: edits only assigned workspace.
- Admin (optional): installs dependencies and maintains host.

## 4. Scope
### In scope
- Windows-native build queue service.
- Student registration and workspace lifecycle management.
- Deterministic artifact generation (`.json`, `.asc`, `.bin`) and logs.
- Instructor-triggered programming of selected artifacts.
- Multi-board management for connected target boards.
- Instructor and student web GUI surfaces.
- Operational scripts and documentation for class-day usage.
- Instructor-assisted/proxy student submission workflow for offline/local-only environments.

### Out of scope (for initial release)
- Per-student OS accounts.
- Strong multi-tenant security model beyond classroom trust assumptions.
- Cloud-hosted infrastructure.

## 5. Constraints and Assumptions
- Host OS is Windows 11.
- Target host hardware baseline is AMD Ryzen AI 9 365 with Radeon 880M and 32 GB RAM.
- Toolchain must be headless and scriptable.
- USB programming must run natively on Windows (not through WSL USB attach).
- Verilog support is required; VHDL is optional and may require separate tooling path.
- Existing classroom workflow (template + student folders + queue) should be preserved when possible.
- Operations must succeed without internet access.
- A powered 7-port USB hub is used for board connectivity.

## 6. Functional Requirements
### FR-1 Workspace management
- System shall allow student registration by last name, creating/reusing that student's artifact/workspace directory.
- System shall handle last-name collisions deterministically (for example via instructor-approved suffixing/alias) while keeping stable student directory identity for the session.
- System shall initialize a student workspace from a template on first registration.
- System shall support resetting a workspace to template state.
- System shall persist login session where possible (session token/cookie with optional connection metadata assist); student may relogin by last name if session is lost.
- System shall preserve build and submission logs per student.

### FR-2 Build submission and queueing
- System shall accept build submissions by `student_id`, user-chosen `submission_name`, and optional top module.
- System shall validate `submission_name` to a safe naming policy.
- Safe naming policy shall be explicitly documented and enforceable (allowed charset, max length, reserved names, and normalization behavior).
- Duplicate `submission_name` for the same student shall overwrite prior artifacts/results with that name.
- System shall retain only the most recent 3 build records/artifact sets per student (after overwrite rules).
- System shall enqueue compile jobs with fairness policy: FIFO order with per-student round-robin fairness to prevent queue monopolization.
- System shall reject invalid/malformed submissions with clear errors.
- System shall prevent accidental duplicate submissions within a configurable cooldown window.

### FR-3 Queue worker execution
- System shall support configurable parallel build workers.
- System shall enforce configurable build timeout per job.
- System shall write per-job status (`pending`, `running`, `completed`, `failed`) and logs.
- System shall recover from crashes by:
  - handling stale lock state safely,
  - re-queueing orphaned running jobs,
  - preserving prior logs,
  - reassociating recovered jobs to existing student directories.
- System shall preserve deterministic queue ordering semantics when multiple workers are enabled.
- System shall build in temporary job directories named `student_name_job_hash`.
- On completion/failure, system shall copy build outputs/logs back into server-managed student artifact directories.
- Job state transitions shall be persisted atomically so crash recovery never leaves ambiguous ownership/status.

### FR-4 Build toolchain integration
- System shall invoke a Windows-native FPGA toolchain in non-interactive mode.
- System shall support build target selection (default `top`).
- System shall produce deterministic artifacts in `students/<id>/build/`.

### FR-5 Programming workflow
- System shall discover and track multiple connected programming targets (boards/programmers).
- System shall assign stable board identifiers based on host USB port path/location for instructor recognition.
- System shall program a selected `.bin` artifact to a selected target board via Windows-native USB path.
- System shall support volatile and non-volatile programming modes (if supported by selected programmer).
- System shall fail safely with actionable messages when programmer/board is not detected.
- System shall allow board interactions (`load`, `clear/reset`) only via instructor GUI; no automatic board programming actions.
- System shall enqueue completed compile artifacts into an instructor programming queue in FIFO order labeled `student_name-submission_name`.
- System shall only add artifacts to programming queue after successful compile for the selected target.
- System shall verify selected board readiness before attempting upload.
- System shall provide a board clear/reset action that erases currently loaded behavior (implemented via supported erase operation or known blank bitstream).
- System shall support programming at least 2 boards concurrently.
- Programming queue selection order shall default to FIFO while final execution remains an explicit instructor action.

### FR-6 Status and observability
- System shall provide a queue status command for instructor use.
- System shall expose last successful build artifact per student.
- System shall provide a preflight check command to validate:
  - required binaries,
  - queue health,
  - USB/programmer visibility,
  - workspace accessibility.
- System shall maintain append-only submission audit log entries containing timestamp, connection info, student name, first 10 chars of submission name, and compile status.

### FR-7 Operations
- System shall provide one-command class startup and one-command class shutdown/recovery routines.
- System shall support manual start/stop/restart of worker and UI processes via documented commands.

### FR-8 Instructor GUI
- System shall provide a live instructor panel showing queue state (pending/running/completed/failed) with near-real-time updates.
- System shall allow instructor to select a completed job artifact and interactively choose a target board for programming.
- System shall allow instructor to trigger board clear/reset interactively per selected board.
- System shall display board inventory/status (connected, busy, last programmed, last error).
- System shall allow instructor to manually start/stop/restart server components.

### FR-9 Student visibility
- System shall allow each student to view their most recent submission status and build errors.
- System shall expose raw compiler stdout/stderr output for debugging/troubleshooting.

## 7. Non-Functional Requirements
### NFR-1 Reliability
- Worker crash shall not require manual queue surgery in normal recovery cases.
- Class-day recover-to-service target: <= 5 minutes using documented steps.
- System state shall survive process restart without requiring internet services or external dependencies.

### NFR-2 Performance
- Queue submit-to-start latency target: <= 3 seconds when idle.
- Build logs must stream or be available immediately after completion/failure.
- System shall support at least 4 concurrent builds on target hardware baseline (configurable by host capacity).
- System shall support at least 1 active compile while at least 2 board programming operations are in progress.

### NFR-3 Usability
- All operator tasks must be executable from documented CLI commands.
- Error messages must include direct next-step hints.
- Instructor GUI actions (program/select/reset) should complete in <= 3 clicks from queue view.

### NFR-4 Maintainability
- Scripts should be readable and modular.
- Configurable values (timeouts, paths, cooldown) shall be centralized.
- Build worker count (`num_processes`) shall be a configurable setting.

### NFR-5 Portability (within Windows)
- Must work on clean Windows machine after documented setup.
- Must not require WSL for core functionality.

## 8. Security and Safety Requirements
- Student workspaces shall be isolated by folder and naming convention.
- Programming command shall only target artifacts under managed workspace roots.
- Scripts shall avoid destructive operations outside managed directories.
- Student UI isolation is desirable, but strict access control is not a classroom release blocker for initial use.
- Instructor board actions shall include target confirmation to reduce accidental programming/reset.
- Submission names and student-provided identifiers shall be sanitized before use in paths, commands, and logs.

## 9. Documentation Requirements
- Setup guide for Windows host from clean install.
- Host preparation and environment validation guide with explicit dependency install and verification steps.
- Class-day runbook (start, monitor, recover, shutdown).
- Troubleshooting guide for toolchain, queue, and USB/programmer issues.
- Instructor quick-reference cheat sheet (single-page commands).
- Offline/local-network operations guide including instructor proxy submission flow.

## 10. Acceptance Criteria (Release Gate)
- AC-1: Preflight passes on target classroom host.
- AC-2: At least 10 sequential build jobs complete without manual intervention.
- AC-2b: At least 20 mixed jobs with parallel workers complete with no lost/duplicated jobs.
- AC-3: Worker restart during processing recovers cleanly with no lost job metadata.
- AC-4: Instructor programs selected board from selected successful artifact using documented GUI flow.
- AC-4b: Instructor can execute documented board reset/clear action from GUI.
- AC-5: A new instructor can follow docs and run a full start-to-build-to-program cycle in <= 30 minutes.
- AC-6: Student can view most recent submission errors from student UI in <= 15 seconds after build completion.
- AC-7: Rehearsal script simulates 5 students registering and each submitting 4 named submissions periodically, with expected queue/log outcomes.
- AC-8: Submission log records connection info, student name, first 10 chars of submission name, and compilation status.
- AC-9: Offline operation validated (no internet) for register, submit, build, queue view, and program workflows.

## 11. Open Decisions to Confirm Before Design
- Toolchain choice:
  - Option A: Apio-based flow.
  - Option B: OSS CAD Suite + explicit `yosys/nextpnr/icepack` commands.
- Programmer choice:
  - Option A: `apio upload`.
  - Option B: `openFPGALoader`/equivalent direct programmer command.
- Multi-board strategy:
  - Option A: one programmer process at a time with per-board reservation.
  - Option B: concurrent programming with board-level locks.
- Service host style:
  - Option A: Python worker + PowerShell wrappers.
  - Option B: Pure PowerShell implementation.
- Student editor delivery:
  - Option A: code-server on Windows.
  - Option B: VS Code Server/remote alternative.
- Session tracking approach:
  - Option A: cookie/session token only.
  - Option B: cookie/session token plus soft binding to connection metadata (IP and related connection attributes).

## 12. Proposed Milestones
- M1: Finalize requirements and technology choices.
- M2: Design document (architecture + failure modes + operational model).
- M3: Implement scripts and queue worker.
- M4: Validate with rehearsal run and finalize docs.
