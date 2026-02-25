# Setup Guide

Use this with `docs/host-preparation-validation.md` for full host provisioning and pre-class checks.

## 1. Install Python Dependencies
```bash
python -m pip install -r requirements.txt
```

## 2. Required Folder Layout
The server expects these directories (auto-created if missing):
- `template/`
- `students/`
- `temp/`
- `artifacts/`
- `logs/`

## 3. Initialize Database
```bash
python -m server.cli init-db
```

## 4. Run Preflight
```bash
python -m server.cli preflight
```

## 5. Start Server
```bash
python -m server.cli run --host 0.0.0.0 --port 8080
```

## 6. Main Endpoints
- Student: `/student`
- Instructor: `/instructor`
- SSE stream: `/events/stream`

## 7. Notes
- Runtime configuration is read from `config.yaml`.
- Default compile workers: `4` (`build.num_processes`).
- Upload submissions require files via web form; no browser code editor is included in MVP.
