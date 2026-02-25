import tempfile
import unittest
from pathlib import Path

from server.config import load_config
from server.db.store import Store


class StoreTests(unittest.TestCase):
    def test_submission_overwrite_and_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_path = root / "config.yaml"
            cfg_path.write_text(
                """
server: {host: 127.0.0.1, port: 8080, session_cookie_name: fpga_session}
paths:
  db_path: ./test.db
  template_dir: ./template
  students_dir: ./students
  temp_dir: ./temp
  artifacts_dir: ./artifacts
  logs_dir: ./logs
build: {num_processes: 1, timeout_seconds: 5, retention_per_student: 3, default_top_module: top}
programming: {workers: 2, timeout_seconds: 5, detect_interval_seconds: 30, blank_bitstream: blank_reset.bin}
security: {session_ttl_hours: 1}
""",
                encoding="utf-8",
            )
            for p in ("template", "students", "temp", "artifacts", "logs"):
                (root / p).mkdir(parents=True, exist_ok=True)

            cfg = load_config(cfg_path)
            store = Store(cfg)
            store.init_db()

            student = store.register_student("Smith")
            sid1 = store.upsert_submission(student.id, "demo", "demo", str(root / "a"))
            sid2 = store.upsert_submission(student.id, "demo", "demo", str(root / "b"))
            self.assertEqual(sid1, sid2)

            jid = store.enqueue_compile_job(student.id, sid1, "top", "abc123")
            self.assertTrue(jid > 0)


if __name__ == "__main__":
    unittest.main()
