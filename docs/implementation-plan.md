# Implementation Plan (Initial)

## Phase 1: Project Skeleton
- Create `server/` app skeleton (FastAPI, template rendering, SQLite init).
- Add config loader and preflight command.
- Add directory bootstrap for `students/`, `temp/`, `logs/`, `artifacts/`.
- Implement automated host preparation/environment validation checks from `docs/host-preparation-validation.md`.

## Phase 2: Student Flows
- Implement registration/login by last name with stable slug + collision handling.
- Implement submission endpoint with safe-name validation.
- Implement overwrite-by-name and keep-most-recent-3 retention.
- Implement student page to display latest statuses and raw compiler output.

## Phase 3: Compile Engine
- Implement durable compile queue tables.
- Implement fair round-robin scheduler and `num_processes` worker pool.
- Implement temp build directory strategy and copyback to student artifacts.
- Implement timeout/error handling and crash recovery reconciliation.

## Phase 4: Board and Programming
- Implement board discovery with stable ID by USB location path.
- Implement instructor programming queue and per-board locks.
- Implement program action and clear/reset action (blank bitstream).
- Implement live instructor board/queue panel (SSE updates).

## Phase 5: Logging, Rehearsal, and Docs
- Implement append-only submission audit log entries.
- Build rehearsal script: 5 students, 4 named submissions each, periodic submit timing.
- Validate offline operation and update setup/runbook.
- Produce quick command cheatsheet.
