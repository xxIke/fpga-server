from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from server.core.naming import safe_filename, slugify_submission
from server.runtime import get_state


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _current_student(request: Request):
    state = get_state()
    token = request.cookies.get(state.cfg.server.session_cookie_name)
    return state.store.student_from_session(token)


@router.get("/", response_class=RedirectResponse)
def root() -> RedirectResponse:
    return RedirectResponse(url="/student", status_code=302)


@router.get("/student", response_class=HTMLResponse)
def student_page(request: Request):
    state = get_state()
    student = _current_student(request)
    jobs = state.store.latest_jobs_for_student(int(student["id"])) if student else []
    return templates.TemplateResponse(
        request,
        "student.html",
        {
            "student": student,
            "jobs": jobs,
            "default_top": state.cfg.build.default_top_module,
        },
    )


@router.post("/student/register")
def student_register(request: Request, last_name: str = Form(...)):
    state = get_state()
    ident = state.store.register_student(last_name)
    token = state.store.create_session(
        ident.id,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    response = RedirectResponse(url="/student", status_code=303)
    response.set_cookie(
        key=state.cfg.server.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@router.post("/student/submit")
async def student_submit(
    request: Request,
    submission_name: str = Form(...),
    top_module: str = Form(default=""),
    files: list[UploadFile] | None = None,
):
    state = get_state()
    student = _current_student(request)
    if not student:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    if not files:
        return JSONResponse({"error": "No files uploaded"}, status_code=400)

    try:
        submission_slug = slugify_submission(submission_name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    student_slug = student["student_slug"]
    snapshot_dir = state.cfg.paths.students_dir / student_slug / "submissions" / submission_slug / "latest"
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        name = safe_filename(f.filename or "upload.txt")
        content = await f.read()
        (snapshot_dir / name).write_bytes(content)

    submission_id = state.store.upsert_submission(
        student_id=int(student["id"]),
        submission_name_raw=submission_name,
        submission_slug=submission_slug,
        snapshot_path=str(snapshot_dir),
    )
    job_hash = uuid.uuid4().hex[:12]
    job_id = state.store.enqueue_compile_job(
        student_id=int(student["id"]),
        submission_id=submission_id,
        top_module=top_module.strip() or state.cfg.build.default_top_module,
        job_hash=job_hash,
    )
    state.store.append_audit(
        {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "connection": request.client.host if request.client else "unknown",
            "student_name": student["display_name"],
            "submission_prefix_10": submission_name[:10],
            "status": "queued",
            "job_id": job_id,
        }
    )
    return JSONResponse({"job_id": job_id, "status": "pending"})


@router.get("/student/jobs/latest")
def student_jobs_latest(request: Request):
    state = get_state()
    student = _current_student(request)
    if not student:
        return JSONResponse([], status_code=200)
    jobs = state.store.latest_jobs_for_student(int(student["id"]))
    return JSONResponse(
        [
            {
                "id": j["id"],
                "status": j["status"],
                "submission_name": j["submission_name_raw"],
                "return_code": j["return_code"],
                "finished_at": j["finished_at"],
                "error_summary": j["error_summary"],
            }
            for j in jobs
        ]
    )


@router.get("/student/jobs/{job_id}/log")
def student_job_log(request: Request, job_id: int):
    state = get_state()
    student = _current_student(request)
    if not student:
        return PlainTextResponse("Not logged in", status_code=401)
    job = state.store.get_compile_job_for_student(job_id, int(student["id"]))
    if not job:
        return PlainTextResponse("Job not found", status_code=404)

    stdout = Path(job["stdout_path"]).read_text(encoding="utf-8") if job["stdout_path"] and Path(job["stdout_path"]).exists() else ""
    stderr = Path(job["stderr_path"]).read_text(encoding="utf-8") if job["stderr_path"] and Path(job["stderr_path"]).exists() else ""
    body = f"=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n"
    return PlainTextResponse(body)


@router.get("/instructor", response_class=HTMLResponse)
def instructor_page(request: Request):
    snap = get_state().store.instructor_snapshot()
    return templates.TemplateResponse(request, "instructor.html", {"snapshot": snap})


@router.get("/instructor/snapshot")
def instructor_snapshot():
    return JSONResponse(get_state().store.instructor_snapshot())


@router.post("/instructor/program")
def instructor_program(compile_job_id: int = Form(...), board_id: int = Form(...), mode: str = Form(default="load")):
    try:
        pj_id = get_state().engine.enqueue_program(compile_job_id=compile_job_id, board_id=board_id, mode=mode)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"program_job_id": pj_id, "status": "running"})


@router.post("/instructor/clear")
def instructor_clear(board_id: int = Form(...)):
    try:
        pj_id = get_state().engine.enqueue_program(compile_job_id=0, board_id=board_id, mode="clear")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"program_job_id": pj_id, "status": "running"})


@router.post("/instructor/requeue/{job_id}")
def instructor_requeue(job_id: int):
    ok = get_state().engine.requeue_compile_job(job_id)
    return JSONResponse({"ok": ok})


@router.get("/events/stream")
async def events_stream():
    async def generate():
        last_payload = ""
        while True:
            payload = get_state().engine.sse_payload()
            if payload != last_payload:
                yield f"event: snapshot\ndata: {payload}\n\n"
                last_payload = payload
            else:
                yield "event: heartbeat\ndata: {}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(generate(), media_type="text/event-stream")
