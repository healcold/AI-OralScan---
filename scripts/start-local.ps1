param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo 'backend'
$frontend = Join-Path $repo 'frontend'
$child = $null
$oldTarget = $env:ORALSCAN_API_TARGET
try {
    if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 with the Windows Python launcher first.' }
    if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 or newer first.' }
    if (-not (Get-Command pnpm.cmd -ErrorAction SilentlyContinue)) { throw 'Install pnpm first: npm.cmd install -g pnpm@10' }
    $nodeVersion = & node.exe --version
    if ($LASTEXITCODE -ne 0 -or [int]($nodeVersion.TrimStart('v').Split('.')[0]) -lt 22) { throw 'Node.js 22 or newer is required.' }
    & py.exe -3.12 -c 'import sys; print(sys.version)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required by this launcher.' }
    if (-not $PrepareOnly) {
        foreach ($port in @(8000,5173)) {
            if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
                throw "Port $port is already in use. Close the previous local server and try again."
            }
        }
    }
    # Keep long ONNX wheel paths away from deeply nested repository folders.
    # Give each checkout its own environment; leave existing .venv and data intact.
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try { $key = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($repo.ToLowerInvariant())))).Replace('-','').Substring(0,12) }
    finally { $hash.Dispose() }
    $runtime = Join-Path $env:LOCALAPPDATA "OralScan\$key"
    $venv = Join-Path $runtime 'venv'
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    $python = Join-Path $venv 'Scripts\python.exe'
    Write-Host "Python environment: $venv"
    if (-not (Test-Path -LiteralPath $python)) {
        & py.exe -3.12 -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    & $python -m pip install -r (Join-Path $backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed. See the error above; servers were not started.' }
    & pnpm.cmd -C $frontend install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed. See the error above.' }
    if ($PrepareOnly) { Write-Host 'Dependencies ready.'; exit 0 }
    $stdout = Join-Path $runtime 'backend.log'
    $stderr = Join-Path $runtime 'backend-error.log'
    $child = Start-Process -FilePath $python -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $ready = $false
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        if ($child.HasExited) { throw "Backend stopped. Read $stderr" }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw "Backend did not become ready. Read $stderr" }
    $env:ORALSCAN_API_TARGET = 'http://127.0.0.1:8000'
    Write-Host 'Backend ready. Open http://127.0.0.1:5173 when Vite is ready below.'
    Write-Host 'Keep this window open. Press Ctrl+C to stop the local website.'
    & pnpm.cmd -C $frontend exec vite --host 127.0.0.1 --port 5173 --strictPort
    if ($LASTEXITCODE -ne 0) { throw 'Frontend stopped with an error.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if ($child -and -not $child.HasExited) { Stop-Process -Id $child.Id -ErrorAction SilentlyContinue }
    $env:ORALSCAN_API_TARGET = $oldTarget
}
