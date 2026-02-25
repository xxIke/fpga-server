# Host Preparation and Environment Validation (Windows, Step by Step)

This guide assumes you are comfortable in Linux but not Windows.
Every step includes exact commands and what result to expect.

## 0. What "PATH" means (plain language)
`PATH` is just Windows' list of folders it searches when you type a command.
Example: if `yosys.exe` is in `C:\tools\oss-cad-suite\bin`, Windows can only run `yosys` if that folder is in PATH.

You will do two things:
1. install tools,
2. add their tool folders to PATH.

## 1. Open PowerShell as Administrator
1. Press `Windows` key.
2. Type `powershell`.
3. Right-click `Windows PowerShell`.
4. Click `Run as administrator`.

Keep this window open for install steps.

## 2. Install required software
Run each command one at a time.

### 2.1 Python 3.11+
```powershell
winget install --id Python.Python.3.11 -e
```

### 2.2 Git
```powershell
winget install --id Git.Git -e
```

### 2.3 GNU Make
```powershell
winget install --id ezwinports.make -e
```

### 2.4 OSS CAD Suite (manual download)
1. Open browser and download OSS CAD Suite Windows zip release.
2. Create folder `C:\tools` (if missing).
3. Extract zip so you end up with a folder like:
   - `C:\tools\oss-cad-suite\bin`

Note: you can use another location, but this guide assumes `C:\tools\oss-cad-suite`.

### 2.5 openFPGALoader (manual download)
1. Download Windows release archive/binary for openFPGALoader.
2. Extract to:
   - `C:\tools\openFPGALoader\bin`
3. Confirm file exists:
   - `C:\tools\openFPGALoader\bin\openFPGALoader.exe`

## 3. Pull project repo
Still in admin PowerShell, run:

```powershell
git clone <your-repo-url> C:\fpga-server
cd C:\fpga-server
```

## 4. Add tool folders to PATH (persistent)
Still in admin PowerShell, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\fpga-server
.\scripts\setup_windows_path.ps1
```

Now close this PowerShell window.

What this script does:
- adds these common tool folders if they exist:
  - `C:\tools\oss-cad-suite\bin`
  - `C:\tools\openFPGALoader\bin`
  - `C:\msys64\ucrt64\bin`
  - `C:\msys64\mingw64\bin`
- updates current shell PATH and persistent user PATH
- prints command availability checks

## 5. Open a NEW normal PowerShell window
Do not run as admin for normal usage.

## 6. Verify tool commands work
Run these commands exactly:

```powershell
python --version
git --version
make --version
yosys -V
nextpnr-ice40 --version
icepack -h
openFPGALoader --version
```

Expected:
- each command prints version/help text,
- no "command not found" style errors.

If a command fails, go back to Step 3 and check install folders exist.

## 7. Install Python packages
```powershell
cd C:\fpga-server
python -m pip install -r requirements.txt
```

## 8. Initialize database
```powershell
python -m server.cli init-db
```

Expected:
- output includes: `Initialized DB at ...`

## 9. Run preflight validation
```powershell
python -m server.cli preflight
```

Expected:
- final line is `PASS`.
- if you see `[ERROR]`, fix that item before continuing.

## 10. Verify USB boards are visible
Connect boards to powered hub, then run:

```powershell
openFPGALoader --detect
```

Expected:
- output shows connected boards/programmers.
- if output is empty, check hub power, cable, and board connection.

## 11. Start server
```powershell
python -m server.cli run --host 0.0.0.0 --port 8080
```

Open in browser:
- Student UI: `http://localhost:8080/student`
- Instructor UI: `http://localhost:8080/instructor`

From another machine on same LAN:
- `http://<windows-host-ip>:8080/student`

## 12. Offline test (required)
1. Disconnect internet (or use isolated LAN).
2. Re-run:
   - `python -m server.cli preflight`
3. Start server and confirm student/instructor pages still work.

## 13. Pre-class checklist
Run in order:
1. `python -m server.cli preflight`
2. `python -m server.cli rehearse --students 5 --submissions 4`
3. Open instructor dashboard and confirm:
   - boards listed,
   - queue updates,
   - no obvious errors.

## 14. Quick troubleshooting
- Error: command not recognized
  - verify executable exists on disk,
  - re-run Step 3,
  - close/open PowerShell and test again.
- Boards not detected
  - check powered hub, cable, USB port,
  - re-run `openFPGALoader --detect`.
- Build failures
  - open student job log and read raw stdout/stderr.
- Program failures
  - check instructor dashboard program job output and board error state.
