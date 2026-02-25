from __future__ import annotations

import re

RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


_student_re = re.compile(r"[^a-z0-9-]+")
_submission_re = re.compile(r"[^a-z0-9_-]+")


def _sanitize_common(value: str) -> str:
    out = value.strip().lower().replace(" ", "-")
    out = re.sub(r"-+", "-", out)
    out = out.strip("-._")
    return out


def slugify_student(value: str) -> str:
    out = _sanitize_common(value)
    out = _student_re.sub("", out)
    out = out[:32].strip("-._")
    if not out:
        raise ValueError("Student name is empty after normalization")
    if out in RESERVED:
        raise ValueError("Student name is reserved")
    return out


def slugify_submission(value: str) -> str:
    out = _sanitize_common(value)
    out = _submission_re.sub("", out)
    out = out[:48].strip("-._")
    if not out:
        raise ValueError("Submission name is empty after normalization")
    if out in RESERVED:
        raise ValueError("Submission name is reserved")
    return out


def safe_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)
    cleaned = cleaned.strip("._")
    if not cleaned:
        cleaned = "file.txt"
    return cleaned[:120]
