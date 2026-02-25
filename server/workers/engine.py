from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.config import AppConfig
from server.core.filesystem import copy_tree, ensure_runtime_dirs, overlay_tree
from server.db.store import Store
from server.workers.boards import build_program_command, detect_boards


class Engine:
    def __init__(self, cfg: AppConfig, store: Store):
        self.cfg = cfg
        self.store = store
        self.stop_event = threading.Event()
        self.rr_lock = threading.Lock()
        self.rr_students: deque[int] = deque()
        self.compile_threads: list[threading.Thread] = []
        self.board_thread: threading.Thread | None = None
        self.program_pool = ThreadPoolExecutor(max_workers=max(2, cfg.programming.workers))
        self.board_locks: dict[int, threading.Lock] = {}
        self.board_locks_lock = threading.Lock()

    def start(self) -> None:
        ensure_runtime_dirs(self.cfg)
        self.store.mark_interrupted_running_jobs()
        self.store.ensure_settings_defaults()
        self.board_thread = threading.Thread(target=self._board_scan_loop, daemon=True)
        self.board_thread.start()
        for idx in range(max(1, self.cfg.build.num_processes)):
            t = threading.Thread(target=self._compile_loop, name=f"compile-worker-{idx}", daemon=True)
            t.start()
            self.compile_threads.append(t)

    def stop(self) -> None:
        self.stop_event.set()
        for t in self.compile_threads:
            t.join(timeout=1.5)
        if self.board_thread:
            self.board_thread.join(timeout=1.5)
        self.program_pool.shutdown(wait=False, cancel_futures=False)

    def _next_student(self) -> int | None:
        with self.rr_lock:
            current = set(self.store.pending_students())
            self.rr_students = deque([s for s in self.rr_students if s in current])
            for sid in sorted(current):
                if sid not in self.rr_students:
                    self.rr_students.append(sid)
            if not self.rr_students:
                return None
            sid = self.rr_students.popleft()
            self.rr_students.append(sid)
            return sid

    def _compile_loop(self) -> None:
        while not self.stop_event.is_set():
            sid = self._next_student()
            if sid is None:
                time.sleep(0.5)
                continue
            job = self.store.claim_next_pending_for_student(sid)
            if not job:
                time.sleep(0.1)
                continue
            self._run_compile_job(int(job["id"]))

    def _run_compile_job(self, job_id: int) -> None:
        job = self.store.compile_job_by_id(job_id)
        if not job:
            return

        student_slug = job["student_slug"]
        job_hash = job["job_hash"]
        top_module = job["top_module"]
        snapshot = Path(job["source_snapshot_path"])

        temp_dir = self.cfg.paths.temp_dir / f"{student_slug}_{job_hash}"
        history_dir = self.cfg.paths.students_dir / student_slug / "history" / f"job-{job_id}-{job_hash[:8]}"
        log_dir = self.cfg.paths.students_dir / student_slug / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        history_dir.mkdir(parents=True, exist_ok=True)

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        copy_tree(self.cfg.paths.template_dir, temp_dir)
        overlay_tree(snapshot, temp_dir)

        cmd = ["make", "-C", str(temp_dir), f"TOP={top_module}", f"BUILD={temp_dir / 'build'}", "all"]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.cfg.build.timeout_seconds,
            )
            rc = int(proc.returncode)
            out = proc.stdout or ""
            err = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            rc = 124
            out = exc.stdout or ""
            err = (exc.stderr or "") + f"\n[ERROR] Build timed out after {self.cfg.build.timeout_seconds}s"

        stdout_path = history_dir / "stdout.log"
        stderr_path = history_dir / "stderr.log"
        stdout_path.write_text(out, encoding="utf-8")
        stderr_path.write_text(err, encoding="utf-8")

        artifact_path: Path | None = None
        if rc == 0:
            bins = sorted((temp_dir / "build").glob("*.bin"), key=lambda p: p.stat().st_mtime)
            if bins:
                artifact_path = history_dir / bins[-1].name
                shutil.copy2(bins[-1], artifact_path)

        error_summary = None
        if rc != 0:
            combined = (err.strip() or out.strip() or "build failed").splitlines()
            error_summary = combined[-1][:250] if combined else "build failed"

        self.store.complete_compile_job(
            job_id=job_id,
            return_code=rc,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            artifact_bin_path=str(artifact_path) if artifact_path else None,
            history_path=str(history_dir),
            error_summary=error_summary,
        )

        sub = self.store.submission_for_job(job_id)
        if sub:
            self.store.append_audit(
                {
                    "timestamp": self.store.now(),
                    "connection": "session",
                    "student_name": sub["display_name"],
                    "submission_prefix_10": (sub["submission_name_raw"] or "")[:10],
                    "status": "completed" if rc == 0 else "failed",
                    "job_id": job_id,
                }
            )

        removed = self.store.trim_student_history(int(job["sid"]), self.cfg.build.retention_per_student)
        for row in removed:
            for key in ("history_path",):
                p = row.get(key)
                if p:
                    rp = Path(str(p))
                    if rp.exists() and rp.is_dir():
                        shutil.rmtree(rp, ignore_errors=True)

    def _board_scan_loop(self) -> None:
        while not self.stop_event.is_set():
            detected = detect_boards(timeout_seconds=10)
            self.store.upsert_boards(detected)
            self.stop_event.wait(self.cfg.programming.detect_interval_seconds)

    def _board_lock(self, board_id: int) -> threading.Lock:
        with self.board_locks_lock:
            lock = self.board_locks.get(board_id)
            if lock is None:
                lock = threading.Lock()
                self.board_locks[board_id] = lock
            return lock

    def enqueue_program(self, compile_job_id: int, board_id: int, mode: str) -> int:
        board = self.store.get_board(board_id)
        if not board:
            raise ValueError("Board not found")
        cj = None
        if mode != "clear":
            cj = self.store.get_compile_job(compile_job_id)
            if not cj:
                raise ValueError("Compile job not found")
            if cj["status"] != "completed":
                raise ValueError("Compile job is not completed")
            if not cj["artifact_bin_path"]:
                raise ValueError("Compile artifact missing")

        pj_id = self.store.create_program_job(compile_job_id if mode != "clear" else None, board_id, mode)
        self.program_pool.submit(self._run_program_job, pj_id, compile_job_id, board_id, mode)
        return pj_id

    def _run_program_job(self, program_job_id: int, compile_job_id: int, board_id: int, mode: str) -> None:
        board = self.store.get_board(board_id)
        compile_job = self.store.get_compile_job(compile_job_id) if mode != "clear" else None
        if not board:
            return

        output_path = self.cfg.paths.logs_dir / f"program-{program_job_id}.log"
        serial = board["programmer_serial"]
        if mode == "clear":
            bitstream = self.cfg.paths.artifacts_dir / self.cfg.programming.blank_bitstream
        else:
            if not compile_job:
                self.store.complete_program_job(program_job_id, 1, str(output_path))
                self.store.update_board_error(board_id, "Missing compile job")
                return
            bitstream = Path(str(compile_job["artifact_bin_path"]))

        lock = self._board_lock(board_id)
        with lock:
            cmd = build_program_command(str(bitstream), "volatile" if mode == "volatile" else "load", serial)
            rc = 1
            text = ""
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.cfg.programming.timeout_seconds)
                rc = int(proc.returncode)
                text = (proc.stdout or "") + "\n" + (proc.stderr or "")
            except Exception as exc:
                text = f"[ERROR] {exc}"

            output_path.write_text(text, encoding="utf-8")
            self.store.complete_program_job(program_job_id, rc, str(output_path))
            self.store.update_board_error(board_id, None if rc == 0 else text[-250:])

    def sse_payload(self) -> str:
        snap = self.store.instructor_snapshot()
        return json.dumps(snap, sort_keys=True)

    def requeue_compile_job(self, job_id: int) -> bool:
        return self.store.requeue_compile_job(job_id)
