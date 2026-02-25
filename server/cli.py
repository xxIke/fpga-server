from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from server.runtime import initialize


def cmd_init_db(args: argparse.Namespace) -> int:
    _ = args
    state = initialize()
    state.store.init_db()
    state.store.ensure_settings_defaults()
    print(f"Initialized DB at {state.cfg.paths.db_path}")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    _ = args
    state = initialize()
    cfg = state.cfg
    ok = True

    print("== Binary checks ==")
    for cmd in ("python", "yosys", "nextpnr-ice40", "icepack", "openFPGALoader", "make"):
        path = shutil.which(cmd)
        if path:
            print(f"[OK] {cmd}: {path}")
        else:
            print(f"[ERROR] missing command: {cmd}")
            ok = False

    print("\n== Filesystem checks ==")
    for p in (cfg.paths.students_dir, cfg.paths.temp_dir, cfg.paths.logs_dir, cfg.paths.artifacts_dir, cfg.paths.template_dir):
        p.mkdir(parents=True, exist_ok=True)
        test_file = p / ".preflight_write_test"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            print(f"[OK] writable: {p}")
        except Exception as exc:
            print(f"[ERROR] not writable: {p} ({exc})")
            ok = False

    print("\n== Database checks ==")
    try:
        state.store.init_db()
        print(f"[OK] DB initialized: {cfg.paths.db_path}")
    except Exception as exc:
        ok = False
        print(f"[ERROR] DB init failed: {exc}")

    blank = cfg.paths.artifacts_dir / cfg.programming.blank_bitstream
    if blank.exists():
        print(f"[OK] blank/reset artifact exists: {blank}")
    else:
        print(f"[ERROR] missing blank/reset artifact: {blank}")
        ok = False

    print("\n== Board detect check ==")
    if shutil.which("openFPGALoader"):
        try:
            proc = subprocess.run(["openFPGALoader", "--detect"], capture_output=True, text=True, timeout=15)
            text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            if text:
                print("[OK] openFPGALoader --detect returned output")
            else:
                print("[WARN] detect returned no output")
        except Exception as exc:
            print(f"[WARN] detect command failed: {exc}")
    else:
        print("[WARN] skipping detect check; openFPGALoader missing")

    print("\n== Result ==")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_rehearse(args: argparse.Namespace) -> int:
    state = initialize()
    students = args.students
    submissions = args.submissions
    print(f"Rehearsal: students={students} submissions_each={submissions}")

    for i in range(1, students + 1):
        ident = state.store.register_student(f"Student{i}")
        for j in range(1, submissions + 1):
            sub_name = f"submission-{j}"
            sub_slug = f"submission-{j}"
            snap_dir = state.cfg.paths.students_dir / ident.student_slug / "submissions" / sub_slug / "latest"
            snap_dir.mkdir(parents=True, exist_ok=True)
            (snap_dir / "top.v").write_text(
                f"module top(output LED); assign LED = 1'b{j % 2}; endmodule\n",
                encoding="utf-8",
            )
            sid = state.store.upsert_submission(ident.id, sub_name, sub_slug, str(snap_dir))
            jid = state.store.enqueue_compile_job(ident.id, sid, state.cfg.build.default_top_module, uuid.uuid4().hex[:12])
            print(f"Queued student={ident.student_slug} job={jid}")
            time.sleep(0.2)

    deadline = time.time() + args.wait_seconds
    while time.time() < deadline:
        snap = state.store.instructor_snapshot()
        pending = len(snap["pending"])
        running = len(snap["running"])
        if pending == 0 and running == 0:
            break
        time.sleep(1)

    snap = state.store.instructor_snapshot()
    print(json.dumps({"pending": len(snap["pending"]), "running": len(snap["running"]), "candidates": len(snap["program_candidates"])}, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    import uvicorn

    state = initialize()
    host = args.host or state.cfg.server.host
    port = args.port or state.cfg.server.port
    uvicorn.run("server.app:app", host=host, port=port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FPGA server CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Initialize sqlite DB")
    p_init.set_defaults(func=cmd_init_db)

    p_pre = sub.add_parser("preflight", help="Run environment preflight checks")
    p_pre.set_defaults(func=cmd_preflight)

    p_run = sub.add_parser("run", help="Run web server")
    p_run.add_argument("--host", default=None)
    p_run.add_argument("--port", type=int, default=None)
    p_run.set_defaults(func=cmd_run)

    p_reh = sub.add_parser("rehearse", help="Run rehearsal queue simulation")
    p_reh.add_argument("--students", type=int, default=5)
    p_reh.add_argument("--submissions", type=int, default=4)
    p_reh.add_argument("--wait-seconds", type=int, default=60)
    p_reh.set_defaults(func=cmd_rehearse)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
