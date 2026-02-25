# Class-Day Runbook

## 1. Startup
1. Connect boards to fixed hub ports.
2. Run preflight:
   - `python -m server.cli preflight`
3. Start server:
   - `python -m server.cli run --host 0.0.0.0 --port 8080`
4. Open instructor dashboard:
   - `http://<host>:8080/instructor`

## 2. Student Workflow
1. Student opens `/student`.
2. Student registers with last name.
3. Student uploads files with `submission_name`.
4. Student views latest 3 job statuses and raw logs.

## 3. Instructor Workflow
1. Monitor compile queue/running jobs.
2. Select completed compile candidate and target board.
3. Trigger `Load` or `Volatile` program action.
4. Trigger `Clear/Reset` per board when needed.

## 4. Rehearsal
Run queue load simulation:
```bash
python -m server.cli rehearse --students 5 --submissions 4
```

## 5. Recovery
- If process crashes, restart server command; running jobs are marked interrupted and queue processing resumes.
- If a board is missing, reseat cable on same hub port and refresh dashboard.
- If compile failures spike, inspect raw logs via student job log links.
