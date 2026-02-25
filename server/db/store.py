from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from server.config import AppConfig
from server.core.naming import slugify_student


@dataclass
class StudentIdentity:
    id: int
    display_name: str
    student_slug: str


class Store:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.db_path = cfg.paths.db_path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def tx(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    last_name_raw TEXT NOT NULL,
                    student_slug TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    session_token TEXT NOT NULL UNIQUE,
                    ip_addr TEXT,
                    user_agent TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    submission_name_raw TEXT NOT NULL,
                    submission_slug TEXT NOT NULL,
                    source_snapshot_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(student_id, submission_slug)
                );

                CREATE TABLE IF NOT EXISTS compile_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    queue_seq INTEGER NOT NULL,
                    job_hash TEXT NOT NULL,
                    top_module TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    return_code INTEGER,
                    stdout_path TEXT,
                    stderr_path TEXT,
                    artifact_bin_path TEXT,
                    history_path TEXT,
                    error_summary TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS program_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compile_job_id INTEGER REFERENCES compile_jobs(id) ON DELETE CASCADE,
                    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    queue_seq INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    return_code INTEGER,
                    output_path TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS boards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_alias TEXT NOT NULL UNIQUE,
                    usb_location_id TEXT NOT NULL UNIQUE,
                    programmer_serial TEXT,
                    state TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # Lightweight migration: allow NULL compile_job_id for clear/reset program jobs.
            info = conn.execute("PRAGMA table_info(program_jobs)").fetchall()
            compile_col = next((r for r in info if r["name"] == "compile_job_id"), None)
            if compile_col and int(compile_col["notnull"]) == 1:
                conn.executescript(
                    """
                    ALTER TABLE program_jobs RENAME TO program_jobs_old;
                    CREATE TABLE program_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        compile_job_id INTEGER REFERENCES compile_jobs(id) ON DELETE CASCADE,
                        board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                        status TEXT NOT NULL,
                        queue_seq INTEGER NOT NULL,
                        mode TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        return_code INTEGER,
                        output_path TEXT,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO program_jobs(id, compile_job_id, board_id, status, queue_seq, mode, started_at, finished_at, return_code, output_path, created_at)
                    SELECT id, compile_job_id, board_id, status, queue_seq, mode, started_at, finished_at, return_code, output_path, created_at
                    FROM program_jobs_old;
                    DROP TABLE program_jobs_old;
                    """
                )
        finally:
            conn.close()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def ensure_settings_defaults(self) -> None:
        defaults = {
            "num_processes": str(self.cfg.build.num_processes),
            "retention_per_student": str(self.cfg.build.retention_per_student),
        }
        with self.tx() as conn:
            for key, value in defaults.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                    (key, value),
                )

    def _next_queue_seq(self, conn: sqlite3.Connection, table: str) -> int:
        row = conn.execute(f"SELECT COALESCE(MAX(queue_seq), 0) + 1 AS n FROM {table}").fetchone()
        return int(row["n"])

    def register_student(self, last_name: str) -> StudentIdentity:
        base = slugify_student(last_name)
        with self.tx() as conn:
            exact = conn.execute(
                "SELECT id, display_name, student_slug FROM students WHERE lower(last_name_raw)=lower(?) ORDER BY id LIMIT 1",
                (last_name.strip(),),
            ).fetchone()
            if exact:
                conn.execute("UPDATE students SET last_seen_at=? WHERE id=?", (self.now(), exact["id"]))
                return StudentIdentity(id=exact["id"], display_name=exact["display_name"], student_slug=exact["student_slug"])

            slug = base
            i = 2
            while conn.execute("SELECT 1 FROM students WHERE student_slug=?", (slug,)).fetchone():
                slug = f"{base}-{i}"
                i += 1
            now = self.now()
            cur = conn.execute(
                "INSERT INTO students(last_name_raw, student_slug, display_name, created_at, last_seen_at) VALUES(?, ?, ?, ?, ?)",
                (last_name.strip(), slug, last_name.strip(), now, now),
            )
            student_id = int(cur.lastrowid)
            return StudentIdentity(id=student_id, display_name=last_name.strip(), student_slug=slug)

    def create_session(self, student_id: int, ip_addr: str | None, user_agent: str | None) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.cfg.security.session_ttl_hours)
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO sessions(student_id, session_token, ip_addr, user_agent, created_at, expires_at, last_seen_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    student_id,
                    token,
                    ip_addr,
                    user_agent,
                    now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
        return token

    def student_from_session(self, token: str | None) -> sqlite3.Row | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.id, s.display_name, s.student_slug
                FROM sessions sess
                JOIN students s ON s.id = sess.student_id
                WHERE sess.session_token=? AND sess.expires_at > ?
                """,
                (token, self.now()),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE session_token=?",
                    (self.now(), token),
                )
                conn.execute(
                    "UPDATE students SET last_seen_at=? WHERE id=?",
                    (self.now(), row["id"]),
                )
            return row

    def upsert_submission(self, student_id: int, submission_name_raw: str, submission_slug: str, snapshot_path: str) -> int:
        now = self.now()
        with self.tx() as conn:
            existing = conn.execute(
                "SELECT id FROM submissions WHERE student_id=? AND submission_slug=?",
                (student_id, submission_slug),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE submissions SET submission_name_raw=?, source_snapshot_path=?, updated_at=? WHERE id=?",
                    (submission_name_raw, snapshot_path, now, existing["id"]),
                )
                return int(existing["id"])
            cur = conn.execute(
                "INSERT INTO submissions(student_id, submission_name_raw, submission_slug, source_snapshot_path, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
                (student_id, submission_name_raw, submission_slug, snapshot_path, now, now),
            )
            return int(cur.lastrowid)

    def enqueue_compile_job(self, student_id: int, submission_id: int, top_module: str, job_hash: str) -> int:
        with self.tx() as conn:
            queue_seq = self._next_queue_seq(conn, "compile_jobs")
            cur = conn.execute(
                """
                INSERT INTO compile_jobs(
                    student_id, submission_id, status, queue_seq, job_hash, top_module, created_at
                ) VALUES(?, ?, 'pending', ?, ?, ?, ?)
                """,
                (student_id, submission_id, queue_seq, job_hash, top_module, self.now()),
            )
            return int(cur.lastrowid)

    def pending_students(self) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT student_id FROM compile_jobs WHERE status='pending' ORDER BY student_id"
            ).fetchall()
        return [int(r["student_id"]) for r in rows]

    def claim_next_pending_for_student(self, student_id: int) -> sqlite3.Row | None:
        with self.tx() as conn:
            row = conn.execute(
                """
                SELECT * FROM compile_jobs
                WHERE status='pending' AND student_id=?
                ORDER BY queue_seq ASC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE compile_jobs SET status='running', started_at=? WHERE id=?",
                (self.now(), row["id"]),
            )
            return conn.execute("SELECT * FROM compile_jobs WHERE id=?", (row["id"],)).fetchone()

    def complete_compile_job(
        self,
        job_id: int,
        return_code: int,
        stdout_path: str,
        stderr_path: str,
        artifact_bin_path: str | None,
        history_path: str,
        error_summary: str | None,
    ) -> None:
        status = "completed" if return_code == 0 else "failed"
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE compile_jobs
                SET status=?, finished_at=?, return_code=?, stdout_path=?, stderr_path=?, artifact_bin_path=?, history_path=?, error_summary=?
                WHERE id=?
                """,
                (
                    status,
                    self.now(),
                    return_code,
                    stdout_path,
                    stderr_path,
                    artifact_bin_path,
                    history_path,
                    error_summary,
                    job_id,
                ),
            )

    def mark_interrupted_running_jobs(self) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE compile_jobs
                SET status='failed', finished_at=?, return_code=-2, error_summary='Interrupted by server restart'
                WHERE status='running'
                """,
                (self.now(),),
            )
            conn.execute(
                """
                UPDATE program_jobs
                SET status='failed', finished_at=?, return_code=-2
                WHERE status='running'
                """,
                (self.now(),),
            )

    def latest_jobs_for_student(self, student_id: int, limit: int = 3) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT j.*, sub.submission_name_raw, sub.submission_slug
                FROM compile_jobs j
                JOIN submissions sub ON sub.id=j.submission_id
                WHERE j.student_id=?
                ORDER BY COALESCE(j.finished_at, j.created_at) DESC, j.id DESC
                LIMIT ?
                """,
                (student_id, limit),
            ).fetchall()

    def get_compile_job_for_student(self, job_id: int, student_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT j.*, sub.submission_name_raw
                FROM compile_jobs j
                JOIN submissions sub ON sub.id=j.submission_id
                WHERE j.id=? AND j.student_id=?
                """,
                (job_id, student_id),
            ).fetchone()

    def get_compile_job(self, job_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT j.*, sub.submission_name_raw, sub.submission_slug, s.student_slug, s.display_name
                FROM compile_jobs j
                JOIN submissions sub ON sub.id=j.submission_id
                JOIN students s ON s.id=j.student_id
                WHERE j.id=?
                """,
                (job_id,),
            ).fetchone()

    def trim_student_history(self, student_id: int, retention: int) -> list[dict[str, Any]]:
        with self.tx() as conn:
            rows = conn.execute(
                """
                SELECT id, stdout_path, stderr_path, artifact_bin_path, history_path
                FROM compile_jobs
                WHERE student_id=?
                ORDER BY COALESCE(finished_at, created_at) DESC, id DESC
                """,
                (student_id,),
            ).fetchall()
            to_remove = rows[retention:]
            if not to_remove:
                return []
            ids = [int(r["id"]) for r in to_remove]
            conn.execute(
                f"DELETE FROM program_jobs WHERE compile_job_id IN ({','.join('?' for _ in ids)})",
                ids,
            )
            conn.execute(
                f"DELETE FROM compile_jobs WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            )
            return [dict(r) for r in to_remove]

    def instructor_snapshot(self) -> dict[str, Any]:
        with self._connect() as conn:
            pending = conn.execute(
                """
                SELECT j.id, j.queue_seq, s.student_slug, sub.submission_name_raw, j.status, j.top_module, j.created_at
                FROM compile_jobs j
                JOIN students s ON s.id=j.student_id
                JOIN submissions sub ON sub.id=j.submission_id
                WHERE j.status='pending'
                ORDER BY j.queue_seq ASC
                """
            ).fetchall()
            running = conn.execute(
                """
                SELECT j.id, s.student_slug, sub.submission_name_raw, j.status, j.started_at
                FROM compile_jobs j
                JOIN students s ON s.id=j.student_id
                JOIN submissions sub ON sub.id=j.submission_id
                WHERE j.status='running'
                ORDER BY j.started_at ASC
                """
            ).fetchall()
            completed_ready = conn.execute(
                """
                SELECT j.id AS compile_job_id, s.student_slug, sub.submission_name_raw, j.finished_at, j.artifact_bin_path
                FROM compile_jobs j
                JOIN students s ON s.id=j.student_id
                JOIN submissions sub ON sub.id=j.submission_id
                WHERE j.status='completed' AND j.artifact_bin_path IS NOT NULL
                ORDER BY j.finished_at ASC
                """
            ).fetchall()
            boards = conn.execute(
                "SELECT * FROM boards ORDER BY board_alias ASC"
            ).fetchall()
            recent_program = conn.execute(
                """
                SELECT pj.id, pj.compile_job_id, pj.board_id, pj.status, pj.mode, pj.started_at, pj.finished_at, pj.return_code
                FROM program_jobs pj
                ORDER BY pj.id DESC LIMIT 20
                """
            ).fetchall()
            return {
                "pending": [dict(r) for r in pending],
                "running": [dict(r) for r in running],
                "program_candidates": [dict(r) for r in completed_ready],
                "boards": [dict(r) for r in boards],
                "program_jobs": [dict(r) for r in recent_program],
            }

    def upsert_boards(self, detected: list[dict[str, str]]) -> None:
        now = self.now()
        with self.tx() as conn:
            seen = set()
            for idx, item in enumerate(detected, start=1):
                usb_id = item["usb_location_id"]
                serial = item.get("programmer_serial")
                seen.add(usb_id)
                row = conn.execute("SELECT id FROM boards WHERE usb_location_id=?", (usb_id,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE boards SET state='connected', last_seen_at=?, programmer_serial=?, last_error=NULL WHERE id=?",
                        (now, serial, row["id"]),
                    )
                else:
                    alias = f"board-{chr(96 + idx)}"
                    suffix = 2
                    while conn.execute("SELECT 1 FROM boards WHERE board_alias=?", (alias,)).fetchone():
                        alias = f"board-{chr(96 + idx)}-{suffix}"
                        suffix += 1
                    conn.execute(
                        "INSERT INTO boards(board_alias, usb_location_id, programmer_serial, state, last_seen_at, last_error) VALUES(?, ?, ?, 'connected', ?, NULL)",
                        (alias, usb_id, serial, now),
                    )
            rows = conn.execute("SELECT id, usb_location_id FROM boards").fetchall()
            for r in rows:
                if r["usb_location_id"] not in seen:
                    conn.execute(
                        "UPDATE boards SET state='missing', last_seen_at=? WHERE id=?",
                        (now, r["id"]),
                    )

    def get_board(self, board_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM boards WHERE id=?", (board_id,)).fetchone()

    def create_program_job(self, compile_job_id: int | None, board_id: int, mode: str) -> int:
        with self.tx() as conn:
            queue_seq = self._next_queue_seq(conn, "program_jobs")
            cur = conn.execute(
                """
                INSERT INTO program_jobs(compile_job_id, board_id, status, queue_seq, mode, created_at)
                VALUES(?, ?, 'running', ?, ?, ?)
                """,
                (compile_job_id, board_id, queue_seq, mode, self.now()),
            )
            return int(cur.lastrowid)

    def complete_program_job(self, job_id: int, return_code: int, output_path: str) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE program_jobs
                SET status=?, finished_at=?, return_code=?, output_path=?
                WHERE id=?
                """,
                (
                    "completed" if return_code == 0 else "failed",
                    self.now(),
                    return_code,
                    output_path,
                    job_id,
                ),
            )

    def update_board_error(self, board_id: int, error: str | None) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE boards SET last_error=?, state=? WHERE id=?",
                (error, "error" if error else "connected", board_id),
            )

    def requeue_compile_job(self, job_id: int) -> bool:
        with self.tx() as conn:
            row = conn.execute("SELECT id FROM compile_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return False
            queue_seq = self._next_queue_seq(conn, "compile_jobs")
            conn.execute(
                "UPDATE compile_jobs SET status='pending', queue_seq=?, started_at=NULL, finished_at=NULL, return_code=NULL WHERE id=?",
                (queue_seq, job_id),
            )
            return True

    def compile_job_by_id(self, job_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT j.*, sub.submission_name_raw, sub.source_snapshot_path, s.student_slug, s.id AS sid
                FROM compile_jobs j
                JOIN submissions sub ON sub.id=j.submission_id
                JOIN students s ON s.id=j.student_id
                WHERE j.id=?
                """,
                (job_id,),
            ).fetchone()

    def submission_for_job(self, job_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT sub.submission_name_raw, s.display_name, j.status
                FROM compile_jobs j
                JOIN submissions sub ON sub.id=j.submission_id
                JOIN students s ON s.id=j.student_id
                WHERE j.id=?
                """,
                (job_id,),
            ).fetchone()

    def append_audit(self, payload: dict[str, Any]) -> None:
        path = self.cfg.paths.logs_dir / "submissions_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, sort_keys=True) + "\n")
