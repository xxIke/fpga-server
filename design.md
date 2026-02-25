# FPGA Server Design (Windows Host)

## 1. Design Intent
Implement an offline-capable Windows-hosted FPGA classroom server for Nandland Go Board labs with:
- student registration + named submissions,
- fair concurrent compilation,
- instructor-controlled multi-board programming,
- instructor/student GUIs,
- resilient restart behavior.

This document turns `requirements.md` into an implementation baseline.

## 2. Technology Baseline (Selected)
- Host OS: Windows 11 (single instructor-managed machine).
- Backend runtime: Python 3.11+.
- Web app: FastAPI + Jinja templates + Server-Sent Events (SSE) for live updates.
- Local data store: SQLite (WAL mode) for durable state and crash recovery.
- Compile toolchain: OSS CAD Suite binaries (`yosys`, `nextpnr-ice40`, `icepack`) on Windows.
- Programming tool: `openFPGALoader` (Windows-native USB access).
- Process orchestration: Python worker threads/processes managed by backend process.

Rationale: minimal moving parts, strong offline behavior, scriptable headless toolchain, straightforward operator workflow.

## 3. High-Level Architecture

```text
Student Browser(s)                 Instructor Browser
       |                                   |
       +-------------- HTTP/SSE -----------+
                         |
                    FastAPI Server
     +-------------------+-------------------+
     |                   |                   |
 Registration/Auth   Compile Scheduler   Program Scheduler
     |                   |                   |
  Workspace FS      Worker Pool (N)      Board Workers (M)
     |                   |                   |
   students/         temp builds/         openFPGALoader
                         |
                 OSS CAD toolchain

Durable state: SQLite + append-only audit log
```

## 4. Core Components

### 4.1 Web/API Layer
- Student pages:
  - register/login by last name,
  - submit named build,
  - view most recent 3 submissions and raw logs.
- Instructor pages:
  - live compile queue + statuses,
  - live program queue + board status,
  - program selected artifact to selected board,
  - clear/reset selected board.
- SSE channel emits queue/board/job state changes.

### 4.2 Scheduler Layer
- Compile Scheduler:
  - fairness: per-student round-robin over submission FIFO,
  - assigns jobs to `num_processes` compile workers,
  - enforces timeout and deterministic state transitions.
- Program Scheduler:
  - maintains FIFO display order,
  - executes only on instructor action,
  - applies per-board lock to prevent simultaneous conflicting actions.

### 4.3 Persistence Layer
- SQLite database for:
  - students, sessions, submissions, compile jobs, program jobs, boards, settings.
- Append-only text/JSONL audit log for instructor diagnostics and post-class review.
- All state transitions done in DB transactions.

### 4.4 Filesystem Layout

```text
fpga-server/
  template/
  students/
    <student_id>/
      source/
      submissions/
        <submission_name>/
          latest/                 # current canonical copy for this name
      history/                    # capped to most recent 3 builds
      logs/
  temp/
    <student_name>_<job_hash>/    # isolated compile workspace
  artifacts/
    blank_reset.bin               # known-clear image used for reset/clear
  logs/
    submissions_audit.jsonl
```

## 5. Data Model (Initial)

## 5.1 students
- `id` (pk)
- `last_name_raw`
- `student_slug` (path-safe stable ID)
- `display_name`
- `created_at`, `last_seen_at`

## 5.2 sessions
- `id` (pk)
- `student_id`
- `session_token`
- `ip_addr`, `user_agent`
- `created_at`, `expires_at`, `last_seen_at`

## 5.3 submissions
- `id` (pk)
- `student_id`
- `submission_name_raw`
- `submission_slug`
- `source_snapshot_path`
- `created_at`
- unique `(student_id, submission_slug)` with overwrite semantics

## 5.4 compile_jobs
- `id` (pk)
- `student_id`, `submission_id`
- `status` (`pending|running|completed|failed|canceled`)
- `queue_seq`
- `job_hash`
- `top_module`
- `started_at`, `finished_at`
- `return_code`
- `stdout_path`, `stderr_path`
- `artifact_bin_path`

## 5.5 program_jobs
- `id` (pk)
- `compile_job_id`
- `board_id`
- `status` (`ready|running|completed|failed|canceled`)
- `queue_seq`
- `mode` (`load|clear`)
- `started_at`, `finished_at`
- `return_code`
- `output_path`

## 5.6 boards
- `id` (pk)
- `board_alias` (e.g. `board-a`)
- `usb_location_id` (stable port-path identity)
- `programmer_serial` (if available)
- `state` (`connected|busy|error|missing`)
- `last_seen_at`

## 5.7 settings
- `key`, `value`
- includes `num_processes`, timeouts, retention count, naming regex.

## 6. Key Workflows

### 6.1 Registration/Login
1. Student enters last name.
2. Server normalizes to slug, resolves collision policy, returns session cookie.
3. Existing student reuses same student directory.

### 6.2 Compile Submission
1. Student submits source + `submission_name`.
2. Server validates/sanitizes name.
3. If same `(student, submission_name)` exists, overwrite canonical submission.
4. Create compile job (`pending`) and audit record.
5. Scheduler dispatches using fair round-robin by student.
6. Worker copies snapshot into `temp/<student>_<hash>/`, runs toolchain, captures raw stdout/stderr.
7. On success: move artifacts/logs to student-managed paths, enqueue program candidate (FIFO label `student-submission`).
8. Trim student history to most recent 3 builds.

### 6.3 Instructor Programming
1. Instructor selects queued successful compile job and target board in GUI.
2. Backend checks board lock + readiness.
3. Program worker runs `openFPGALoader` command.
4. Status/logs update live in instructor panel.

### 6.4 Instructor Clear/Reset
1. Instructor chooses board + `clear/reset`.
2. Backend programs `artifacts/blank_reset.bin` (or supported erase command).
3. Board status updates; no automatic trigger.

### 6.5 Crash Recovery
On restart:
- recover stale running compile/program jobs to consistent terminal states,
- requeue eligible pending jobs,
- rebuild board inventory from current USB scan,
- preserve all prior logs and audit rows.

## 7. Concurrency and Fairness
- Compile parallelism: configurable `num_processes`.
- Programming parallelism: minimum 2 board workers.
- Fairness algorithm:
  - maintain per-student pending queues,
  - dispatch in round-robin across students,
  - preserve per-student local FIFO.
- Board locking:
  - one active action per board,
  - compile jobs independent from board actions.

## 8. Naming and Validation Policy (Proposed)
- `student_slug`: lowercase `[a-z0-9-]`, max 32.
- `submission_slug`: lowercase `[a-z0-9_-]`, max 48.
- Collapse spaces to `-`, strip unsafe chars.
- Reserved names denied: `con`, `prn`, `aux`, `nul`, `com1..9`, `lpt1..9`.
- Display original raw input in UI, use slug only for FS/commands.

## 9. Observability and Logs
- Raw compiler stdout/stderr stored per build and visible to students.
- Instructor dashboard shows:
  - compile queue, running jobs, failures,
  - program queue, board states, recent board errors.
- Submission audit log row format:
  - timestamp, connection info, student name, first 10 chars of submission name, compile status.

## 10. Offline/Network Model
- Single host serves all pages/assets locally.
- No external auth, cloud queues, or internet dependency at runtime.
- Optional instructor proxy submit endpoint for manual “submit on behalf of student”.

## 11. Failure Modes and Handling
- Toolchain binary missing: preflight blocks start with explicit fix command.
- USB board missing: board marked `missing`, actions blocked with diagnostic message.
- Build timeout: job failed with timeout marker in raw logs.
- Worker crash: status reconciler marks interrupted jobs and requeues safe states.
- Duplicate student names: deterministic aliasing prompts shown to instructor/student.

## 12. Initial Milestones
- D1: skeleton app (FastAPI + SQLite + templates + preflight).
- D2: registration/session + submission persistence + raw log display.
- D3: fair compile scheduler with `num_processes` and retention policy.
- D4: multi-board detection + instructor program/reset GUI.
- D5: rehearsal automation (5 students x 4 submissions) and class runbook validation.
