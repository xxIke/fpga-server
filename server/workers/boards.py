from __future__ import annotations

import hashlib
import re
import subprocess
from typing import Any


_SERIAL_RE = re.compile(r"serial\s*[:=]\s*([A-Za-z0-9_-]+)", re.IGNORECASE)


def detect_boards(timeout_seconds: int = 15) -> list[dict[str, str]]:
    cmd = ["openFPGALoader", "--detect"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except Exception:
        return []

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    boards: list[dict[str, str]] = []
    seen: set[str] = set()

    for line in lines:
        # Ignore generic headers/log levels if present.
        if line.lower().startswith(("openfpgaloader", "supported", "usage")):
            continue
        usb_location_id = line
        digest = hashlib.sha1(usb_location_id.encode("utf-8")).hexdigest()[:12]
        usb_location_id = f"loc-{digest}"
        if usb_location_id in seen:
            continue
        seen.add(usb_location_id)
        serial_match = _SERIAL_RE.search(line)
        serial = serial_match.group(1) if serial_match else ""
        boards.append(
            {
                "usb_location_id": usb_location_id,
                "programmer_serial": serial,
                "raw_line": line,
            }
        )

    return boards


def build_program_command(bitstream_path: str, mode: str, serial: str | None) -> list[str]:
    cmd: list[str] = ["openFPGALoader"]
    if serial:
        cmd.extend(["--ftdi-serial", serial])
    if mode == "volatile":
        cmd.append("--volatile")
    cmd.append(bitstream_path)
    return cmd
