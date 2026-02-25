# FPGA Server (Windows Host MVP)

## Documents
- Requirements: `requirements.md`
- Design: `design.md`
- Legacy reference: `old_requirements.md`
- Setup: `docs/setup.md`
- Host prep + validation: `docs/host-preparation-validation.md`
- Runbook: `docs/runbook.md`
- Implementation plan: `docs/implementation-plan.md`

## Quickstart (WSL or Windows)
1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Initialize DB:
   - `python -m server.cli init-db`
3. Run preflight:
   - `python -m server.cli preflight`
4. Run server:
   - `python -m server.cli run --host 0.0.0.0 --port 8080`
5. Open:
   - Student UI: `http://localhost:8080/student`
   - Instructor UI: `http://localhost:8080/instructor`

## Implemented CLI Commands
- `python -m server.cli init-db`
- `python -m server.cli preflight`
- `python -m server.cli run --host 0.0.0.0 --port 8080`
- `python -m server.cli rehearse --students 5 --submissions 4`
