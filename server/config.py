from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    session_cookie_name: str


@dataclass(frozen=True)
class PathsConfig:
    db_path: Path
    template_dir: Path
    students_dir: Path
    temp_dir: Path
    artifacts_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class BuildConfig:
    num_processes: int
    timeout_seconds: int
    retention_per_student: int
    default_top_module: str


@dataclass(frozen=True)
class ProgrammingConfig:
    workers: int
    timeout_seconds: int
    detect_interval_seconds: int
    blank_bitstream: str


@dataclass(frozen=True)
class SecurityConfig:
    session_ttl_hours: int


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    paths: PathsConfig
    build: BuildConfig
    programming: ProgrammingConfig
    security: SecurityConfig


def _get(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping for '{key}'")
    return value


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path).resolve()
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("config.yaml must contain a top-level mapping")

    srv = _get(raw, "server")
    paths = _get(raw, "paths")
    build = _get(raw, "build")
    prog = _get(raw, "programming")
    sec = _get(raw, "security")

    cfg = AppConfig(
        server=ServerConfig(
            host=str(srv.get("host", "0.0.0.0")),
            port=int(srv.get("port", 8080)),
            session_cookie_name=str(srv.get("session_cookie_name", "fpga_session")),
        ),
        paths=PathsConfig(
            db_path=(path.parent / str(paths.get("db_path", "./fpga_server.db"))).resolve(),
            template_dir=(path.parent / str(paths.get("template_dir", "./template"))).resolve(),
            students_dir=(path.parent / str(paths.get("students_dir", "./students"))).resolve(),
            temp_dir=(path.parent / str(paths.get("temp_dir", "./temp"))).resolve(),
            artifacts_dir=(path.parent / str(paths.get("artifacts_dir", "./artifacts"))).resolve(),
            logs_dir=(path.parent / str(paths.get("logs_dir", "./logs"))).resolve(),
        ),
        build=BuildConfig(
            num_processes=int(build.get("num_processes", 4)),
            timeout_seconds=int(build.get("timeout_seconds", 180)),
            retention_per_student=int(build.get("retention_per_student", 3)),
            default_top_module=str(build.get("default_top_module", "top")),
        ),
        programming=ProgrammingConfig(
            workers=int(prog.get("workers", 2)),
            timeout_seconds=int(prog.get("timeout_seconds", 45)),
            detect_interval_seconds=int(prog.get("detect_interval_seconds", 8)),
            blank_bitstream=str(prog.get("blank_bitstream", "blank_reset.bin")),
        ),
        security=SecurityConfig(
            session_ttl_hours=int(sec.get("session_ttl_hours", 12)),
        ),
    )

    return cfg
