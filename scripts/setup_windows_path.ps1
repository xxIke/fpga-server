param(
  [switch]$SessionOnly,
  [switch]$VerboseChecks
)

$ErrorActionPreference = "Stop"

function Add-PathEntry {
  param(
    [Parameter(Mandatory=$true)][string]$Entry,
    [switch]$Persist
  )

  if (-not (Test-Path -LiteralPath $Entry)) {
    Write-Warning "Path not found, skipping: $Entry"
    return
  }

  $sessionParts = ($env:Path -split ';') | Where-Object { $_ -ne '' }
  if (-not ($sessionParts | Where-Object { $_ -eq $Entry })) {
    $env:Path = "$Entry;$env:Path"
    Write-Host "[OK] Added to current session PATH: $Entry"
  } else {
    Write-Host "[OK] Already in current session PATH: $Entry"
  }

  if ($Persist) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userParts = ($userPath -split ';') | Where-Object { $_ -ne '' }
    if (-not ($userParts | Where-Object { $_ -eq $Entry })) {
      $newPath = (($userPath.TrimEnd(';') + ';' + $Entry).Trim(';'))
      [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
      Write-Host "[OK] Added to persistent USER PATH: $Entry"
    } else {
      Write-Host "[OK] Already in persistent USER PATH: $Entry"
    }
  }
}

Write-Host "== FPGA Server PATH Setup =="
if ($SessionOnly) {
  Write-Host "Mode: current shell only (no persistent PATH changes)"
} else {
  Write-Host "Mode: current shell + persistent USER PATH"
}

# Default candidate tool directories.
# Keep these explicit so they map to our docs and common install locations.
$Candidates = @(
  "C:\tools\oss-cad-suite\bin",
  "C:\tools\openFPGALoader\bin",
  "C:\msys64\ucrt64\bin",
  "C:\msys64\mingw64\bin"
)

foreach ($p in $Candidates) {
  if ($SessionOnly) {
    Add-PathEntry -Entry $p
  } else {
    Add-PathEntry -Entry $p -Persist
  }
}

Write-Host ""
Write-Host "== Command Availability Check =="
$Commands = @("python", "git", "make", "yosys", "nextpnr-ice40", "icepack", "openFPGALoader")
foreach ($cmd in $Commands) {
  $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
  if ($resolved) {
    Write-Host "[OK] $cmd -> $($resolved.Source)"
    if ($VerboseChecks) {
      try {
        switch ($cmd) {
          "python" { & python --version }
          "git" { & git --version }
          "make" { & make --version | Select-Object -First 1 }
          "yosys" { & yosys -V }
          "nextpnr-ice40" { & nextpnr-ice40 --version }
          "icepack" { & icepack -h | Select-Object -First 1 }
          "openFPGALoader" { & openFPGALoader --version }
        }
      } catch {
        Write-Warning "Command check failed for $cmd: $($_.Exception.Message)"
      }
    }
  } else {
    Write-Warning "Missing command: $cmd"
  }
}

Write-Host ""
if ($SessionOnly) {
  Write-Host "Done. PATH updated for this shell only."
} else {
  Write-Host "Done. Persistent USER PATH updated. Open a NEW PowerShell and run:"
  Write-Host "  python -m server.cli preflight"
}
