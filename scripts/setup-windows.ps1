<#
.SYNOPSIS
  TemplateOS one-shot setup for Windows 10/11.

.DESCRIPTION
  Installs missing tools with winget (Git, Python 3.12, Node.js LTS, Docker
  Desktop), pulls the main branch, creates .env, starts the Docker services
  (Gotenberg, optional local PostgreSQL / ONLYOFFICE), installs backend and
  frontend dependencies, runs the database migrations and opens the backend
  (http://localhost:8000) and frontend (http://localhost:5173) in two new
  PowerShell windows.

  Run from the repository root:
    powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1

.PARAMETER Branch      Branch to pull (default: main).
.PARAMETER SkipPull    Do not fetch/checkout/pull.
.PARAMETER SkipDocker  Do not install or start Docker services (no PDF output).
.PARAMETER Database    local = PostgreSQL in Docker, neon = paste a connection
                       string. Asked when .env still has the placeholder.
.PARAMETER WithEditor  Also start ONLYOFFICE Docs (Word editor, ~4 GB image).
.PARAMETER SeedDemo    Seed the demo users from the SIT_* values in .env.
.PARAMETER NoRun       Set everything up but do not start the servers.
.PARAMETER RunOnly     Skip setup, only start the servers (needs a previous setup).
.PARAMETER Trace       Print every script line as it runs (the log may then contain secrets).
.PARAMETER Yes         Answer yes to every prompt.

  Log file: <repo>\logs\templateos-setup-windows-<time>.log (or $env:PBL_LOG_DIR).
  On failure it prints the step, the error and the script call stack.
#>
[CmdletBinding()]
param(
  [string]$Branch = 'main',
  [switch]$SkipPull,
  [switch]$SkipDocker,
  [ValidateSet('', 'local', 'neon')][string]$Database = '',
  [switch]$WithEditor,
  [switch]$SeedDemo,
  [switch]$NoRun,
  [switch]$RunOnly,
  [switch]$Trace,
  [switch]$Yes
)

# Works in Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/Harsh2227kumar/TemplateOS.git'
$LocalDbUrl = 'postgresql+psycopg://templateos:templateos@localhost:5433/templateos'

# ---------- logging ----------
$LogDir = if ($env:PBL_LOG_DIR) { $env:PBL_LOG_DIR } else { Join-Path $PSScriptRoot '..\logs' }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogDir = (Resolve-Path $LogDir).Path
$LogFile = Join-Path $LogDir ("templateos-setup-windows-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
try { Start-Transcript -Path $LogFile -Append | Out-Null } catch { Write-Host "[!] Could not start the log file: $_" -ForegroundColor Yellow }
$script:StepNo = 0; $script:CurrentStep = '0. start'

# ---------- helpers ----------
function Step($msg) { $script:StepNo++; $script:CurrentStep = "$($script:StepNo). $msg"; Write-Host ''; Write-Host "==> [$($script:StepNo)] $msg" -ForegroundColor Cyan }
function Info($msg) { Write-Host "    $msg" }
function Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Fail($msg) { throw $msg }
function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# Without a person at the keyboard (stdin redirected) and without -Yes, the
# answer is "no": nothing gets installed unattended by accident.
function Confirm-Step($question) {
  if ($Yes) { return $true }
  if ([Console]::IsInputRedirected) { return $false }
  $reply = Read-Host "    $question [Y/n]"
  return -not ($reply -match '^[nN]')
}

# Runs a native command; throws when it exits non-zero. stderr output (git,
# npm and pip print progress there) is not treated as an error.
function Run {
  param([Parameter(Mandatory)][string]$Exe, [string[]]$Arguments = @())
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  # piping through Out-Host puts native output into the transcript (log file) too
  try { & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } | Out-Host; $code = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
  if ($code -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed with exit code $code" }
}

# Runs a native command quietly; returns $true when it exits 0.
function Test-Run {
  param([Parameter(Mandatory)][string]$Exe, [string[]]$Arguments = @())
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { & $Exe @Arguments *> $null; return ($LASTEXITCODE -eq 0) }
  catch { return $false }
  finally { $ErrorActionPreference = $old }
}

# Native command output as one trimmed string ('' on failure).
function Get-Output {
  param([Parameter(Mandatory)][string]$Exe, [string[]]$Arguments = @())
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { $out = & $Exe @Arguments 2> $null; if ($LASTEXITCODE -ne 0) { return '' }; return (($out | Out-String).Trim()) }
  catch { return '' }
  finally { $ErrorActionPreference = $old }
}

function Update-PathFromRegistry {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$machine;$user"
}

function Install-WithWinget($id, $label) {
  if (-not (Have winget)) {
    Fail "winget is not available. Install $label manually (see README.md), then re-run."
  }
  Info "Installing $label with winget ($id)..."
  Run winget @('install', '-e', '--id', $id, '--accept-source-agreements', '--accept-package-agreements')
  Update-PathFromRegistry
}

function New-Secret {
  $bytes = New-Object byte[] 48
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return ([Convert]::ToBase64String($bytes)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

# Opens the backend and the frontend in two new PowerShell windows.
function Start-Servers($Root, $VPy) {
  $Backend = Join-Path $Root 'backend'
  $BindHost = if ($WithEditor) { '0.0.0.0' } else { '127.0.0.1' }
  foreach ($port in 8000, 5173) {
    $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
      $proc = Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue
      Fail "Port $port is already in use by $($proc.ProcessName) (PID $($busy[0].OwningProcess)). Close it and re-run with -RunOnly."
    }
  }
  $shell = if (Have pwsh) { 'pwsh' } else { 'powershell' }
  $q = { param($s) "'" + ($s -replace "'", "''") + "'" }
  $backendCmd = "Set-Location $(& $q $Backend); `$Host.UI.RawUI.WindowTitle = 'TemplateOS backend'; & $(& $q $VPy) -m uvicorn app.main:app --reload --host $BindHost --port 8000"
  $frontendCmd = "Set-Location $(& $q $Root); `$Host.UI.RawUI.WindowTitle = 'TemplateOS frontend'; npm run dev:frontend"

  Step 'Starting backend (http://localhost:8000) and frontend (http://localhost:5173)'
  Start-Process $shell -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $backendCmd) | Out-Null
  Start-Process $shell -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $frontendCmd) | Out-Null
  Info 'Two new windows are running the servers; close them (or press Ctrl+C in each) to stop.'
  $waited = 0
  while ($waited -lt 60 -and -not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 3; $waited += 3 }
  if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
    Warn "The backend is not listening on 8000 yet: check the 'TemplateOS backend' window for the error."
  }
  if ($env:PBL_NO_BROWSER -ne '1') { Start-Process 'http://localhost:5173' | Out-Null; Info 'Opened http://localhost:5173 in your browser.' }
}

$script:ExitCode = 0
try {
  if ($Trace) { Set-PSDebug -Trace 1 }
  Info "TemplateOS setup (windows) | branch=$Branch | log: $LogFile"
  if ($RunOnly) {
    $Root = Get-Output git @('-C', $PSScriptRoot, 'rev-parse', '--show-toplevel')
    if (-not $Root) { Fail 'Run -RunOnly from inside the TemplateOS repository.' }
    $Root = [IO.Path]::GetFullPath($Root); Set-Location $Root
    $VPy = Join-Path $Root 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $VPy)) { Fail 'backend\.venv is missing: run the full setup first.' }
    if (-not (Test-Path (Join-Path $Root '.env'))) { Fail '.env is missing: run the full setup first.' }
    $envText = Get-Content (Join-Path $Root '.env') -Raw
    if (-not $SkipDocker -and (Test-Run docker @('info'))) {
      try { Run docker @('compose', 'up', '-d', 'gotenberg') } catch { Warn "Could not start Gotenberg (PDF output will fail): $($_.Exception.Message)" }
      if ($envText -match '(?m)^DATABASE_URL=.*@(localhost|127\.0\.0\.1):5433/') { Run docker @('compose', '--profile', 'db', 'up', '-d', '--wait', 'postgres') }
    } elseif (-not $SkipDocker) { Warn 'Docker Desktop is not running: PDF output (Gotenberg) will fail until it is.' }
    if ($envText -match '(?m)^ONLYOFFICE_ENABLED=true') { $WithEditor = $true }
    Start-Servers $Root $VPy
    return
  }

  # ---------- 1. tools ----------
  Step 'Checking required software'
  Info ("Windows {0}, PowerShell {1}" -f [Environment]::OSVersion.Version, $PSVersionTable.PSVersion)

  if (-not (Have git)) {
    if (-not (Confirm-Step 'Git not found. Install it with winget?')) { Fail 'Git is required.' }
    Install-WithWinget 'Git.Git' 'Git'
    if (-not (Have git)) { Fail 'Git installed; open a new PowerShell window and re-run this script.' }
  }

  # Python 3.12+: try the py launcher first (avoids the Microsoft Store alias).
  function Find-Python {
    $candidates = @(@('py', '-3.13'), @('py', '-3.12'), @('python'), @('python3'))
    foreach ($c in $candidates) {
      $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
      if (-not (Have $exe)) { continue }
      if (Test-Run $exe ($pre + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'))) {
        $path = Get-Output $exe ($pre + @('-c', 'import sys; print(sys.executable)'))
        if ($path) { return $path }
      }
    }
    return $null
  }
  $Py = Find-Python
  if (-not $Py) {
    if (-not (Confirm-Step 'Python 3.12+ not found. Install Python 3.12 with winget?')) { Fail 'Python 3.12+ is required.' }
    Install-WithWinget 'Python.Python.3.12' 'Python 3.12'
    $Py = Find-Python
    if (-not $Py) { Fail 'Python installed; open a new PowerShell window and re-run this script.' }
  }
  Info "Python: $Py ($(Get-Output $Py @('--version')))"

  function Test-Node {
    if (-not (Have node)) { return $false }
    return (Test-Run node @('-e', 'const v=process.versions.node.split(''.'').map(Number);process.exit(v[0]>22||(v[0]===22&&v[1]>=18)?0:1)'))
  }
  if (-not (Test-Node)) {
    if (-not (Confirm-Step 'Node.js 22.18+ not found. Install Node.js LTS with winget?')) { Fail 'Node.js 22.18+ is required.' }
    Install-WithWinget 'OpenJS.NodeJS.LTS' 'Node.js LTS'
    if (-not (Test-Node)) { Fail 'Node.js installed; open a new PowerShell window and re-run this script.' }
  }
  Info "Node.js: $(Get-Output node @('--version')), npm $(Get-Output npm @('--version'))"

  if (-not $SkipDocker) {
    $dockerExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Have docker) -and -not (Test-Path $dockerExe)) {
      if (-not (Confirm-Step 'Docker Desktop not found. Install it with winget? (needs WSL 2; may ask for a restart)')) {
        Fail 'Docker is required (or re-run with -SkipDocker).'
      }
      Install-WithWinget 'Docker.DockerDesktop' 'Docker Desktop'
      Warn 'If Docker Desktop asks you to restart Windows or to install WSL 2 (wsl --install), do that, then re-run this script.'
    }
    if (-not (Have docker)) { $env:Path = (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin') + ";$env:Path" }
    if (-not (Test-Run docker @('info'))) {
      if (Test-Path $dockerExe) {
        Info 'Starting Docker Desktop (accept its terms window on first launch)...'
        Start-Process $dockerExe | Out-Null
      }
      $waited = 0
      while (-not (Test-Run docker @('info'))) {
        if ($waited -ge 240) { Fail "Docker Desktop is not running. Start it, wait for 'Engine running', and re-run." }
        Start-Sleep -Seconds 5; $waited += 5
      }
    }
    if (-not (Test-Run docker @('compose', 'version'))) { Fail "'docker compose' is missing; update Docker Desktop." }
    Info "Docker: $(Get-Output docker @('--version'))"
  }

  # ---------- 2. repository ----------
  Step "Getting the code (branch: $Branch)"
  $Root = Get-Output git @('-C', $PSScriptRoot, 'rev-parse', '--show-toplevel')
  if ($Root) {
    $Root = [IO.Path]::GetFullPath($Root)
    Info "Repository: $Root"
  } else {
    $Root = Join-Path (Get-Location) 'TemplateOS'
    if (Test-Path (Join-Path $Root '.git')) { Info "Using existing clone: $Root" }
    else { Run git @('clone', '--branch', $Branch, $RepoUrl, $Root) }
  }
  Set-Location $Root
  $exclude = Join-Path $Root '.git\info\exclude'
  if ((Test-Path (Split-Path $exclude)) -and -not (Select-String -Path $exclude -Pattern '^logs/$' -Quiet -ErrorAction SilentlyContinue)) { Add-Content $exclude 'logs/' }

  if (-not $SkipPull) {
    $dirty = Get-Output git @('status', '--porcelain', '--untracked-files=no')
    if ($dirty) {
      $dirty -split "`n" | ForEach-Object { Info "  $_" }
      Fail 'Uncommitted changes (listed above). Commit or stash them, or re-run with -SkipPull.'
    }
    Run git @('fetch', 'origin', $Branch)
    if ((Get-Output git @('rev-parse', '--abbrev-ref', 'HEAD')) -ne $Branch) {
      if (Test-Run git @('show-ref', '--verify', '--quiet', "refs/heads/$Branch")) { Run git @('checkout', $Branch) }
      else { Run git @('checkout', '-b', $Branch, '--track', "origin/$Branch") }
    }
    Run git @('pull', '--ff-only', 'origin', $Branch)
  } else {
    Info 'Skipping git pull (-SkipPull).'
  }

  # ---------- 3. .env ----------
  Step 'Configuring .env'
  $EnvPath = Join-Path $Root '.env'
  if (-not (Test-Path $EnvPath)) { Copy-Item (Join-Path $Root '.env.example') $EnvPath; Info 'Created .env from .env.example' }

  function Get-EnvValue($key) {
    foreach ($line in [IO.File]::ReadAllLines($EnvPath)) {
      if ($line -match ('^\s*' + [regex]::Escape($key) + '\s*=(.*)$')) { return $Matches[1].Trim() }
    }
    return ''
  }
  function Set-EnvValue($key, $value) {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.AddRange([IO.File]::ReadAllLines($EnvPath))
    $pattern = '^\s*#?\s*' + [regex]::Escape($key) + '\s*='
    $done = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
      if ($lines[$i] -match $pattern) { $lines[$i] = "$key=$value"; $done = $true; break }
    }
    if (-not $done) { $lines.Add("$key=$value") }
    [IO.File]::WriteAllLines($EnvPath, $lines, (New-Object Text.UTF8Encoding $false))
  }

  $jwt = Get-EnvValue 'JWT_SECRET_KEY'
  if (-not $jwt -or $jwt -eq 'generate-a-long-random-secret-here' -or $jwt.Length -lt 32) {
    Set-EnvValue 'JWT_SECRET_KEY' (New-Secret); Info 'Generated JWT_SECRET_KEY'
  }

  $dbUrl = Get-EnvValue 'DATABASE_URL'
  if (-not $Database) {
    if (-not $dbUrl -or $dbUrl -like '*USER:PASSWORD@HOST*') {
      if (-not $SkipDocker -and (Confirm-Step 'Use a local PostgreSQL in Docker? (No = paste a Neon URL)')) { $Database = 'local' }
      else { $Database = 'neon' }
    } else {
      Info 'Keeping DATABASE_URL from .env'
    }
  }
  if ($Database -eq 'local') {
    if ($SkipDocker) { Fail '-Database local needs Docker; drop -SkipDocker.' }
    Set-EnvValue 'DATABASE_URL' $LocalDbUrl; $dbUrl = $LocalDbUrl
    Info 'DATABASE_URL -> local Docker PostgreSQL (port 5433)'
  } elseif ($Database -eq 'neon') {
    $url = Read-Host '    Paste your PostgreSQL/Neon connection string'
    if (-not $url) { Fail 'No DATABASE_URL given.' }
    Set-EnvValue 'DATABASE_URL' $url.Trim(); $dbUrl = $url.Trim()
  }
  $UseLocalDb = ($dbUrl -like '*@localhost:5433/*') -or ($dbUrl -like '*@127.0.0.1:5433/*')

  if ($WithEditor) {
    $oo = Get-EnvValue 'ONLYOFFICE_JWT_SECRET'
    if (-not $oo -or $oo.Length -lt 32 -or $oo -eq 'generate-a-long-random-secret-for-onlyoffice') {
      Set-EnvValue 'ONLYOFFICE_JWT_SECRET' (New-Secret)
    }
    Set-EnvValue 'ONLYOFFICE_ENABLED' 'true'
    Set-EnvValue 'ONLYOFFICE_PUBLIC_URL' 'http://localhost:8082'
    Set-EnvValue 'BACKEND_URL_FOR_ONLYOFFICE' 'http://host.docker.internal:8000'
    Info 'Word editor (ONLYOFFICE) enabled in .env'
  }
  if ($SkipDocker) { Warn 'Docker skipped: PDF output needs Gotenberg or a local LibreOffice (see README).' }

  # ---------- 4. Docker services ----------
  if (-not $SkipDocker) {
    Step 'Starting Docker services'
    Run docker @('compose', 'up', '-d', 'gotenberg')
    if ($UseLocalDb) { Run docker @('compose', '--profile', 'db', 'up', '-d', '--wait', 'postgres') }
    if ($WithEditor) {
      Info 'Starting ONLYOFFICE (first pull is large and the first start takes a few minutes)'
      $env:ONLYOFFICE_JWT_SECRET = Get-EnvValue 'ONLYOFFICE_JWT_SECRET'
      Run docker @('compose', '--profile', 'editor', 'up', '-d', 'onlyoffice')
    }
    Run docker @('compose', 'ps')
  }

  # ---------- 5. backend ----------
  Step 'Installing backend dependencies (backend\.venv)'
  $Backend = Join-Path $Root 'backend'
  $VPy = Join-Path $Backend '.venv\Scripts\python.exe'
  if (-not (Test-Path $VPy)) { Run $Py @('-m', 'venv', (Join-Path $Backend '.venv')) }
  Run $VPy @('-m', 'pip', 'install', '--upgrade', 'pip')
  Run $VPy @('-m', 'pip', 'install', '-r', (Join-Path $Backend 'requirements.txt'))

  Step 'Running database migrations'
  Push-Location $Backend
  try { Run $VPy @('-m', 'alembic', 'upgrade', 'head') }
  catch { Fail 'Migrations failed. Check DATABASE_URL in .env (and that the database is reachable).' }
  finally { Pop-Location }

  if (-not $SeedDemo -and -not $Yes -and -not [Console]::IsInputRedirected) {
    $r = Read-Host '    Seed the demo users (SIT_* in .env)? [y/N]'
    if ($r -match '^[yY]') { $SeedDemo = $true }
  }
  if ($SeedDemo) {
    Push-Location $Backend
    try { Run $VPy @('scripts\seed_demo_users.py') } finally { Pop-Location }
  }

  # ---------- 6. frontend ----------
  Step 'Installing frontend dependencies (npm workspaces)'
  Run npm @('install')

  # ---------- 7. run ----------
  if ($NoRun) {
    Step 'Setup complete'
    Info 'Start both servers: powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -RunOnly'
    Info 'or: cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload   |   npm run dev:frontend'
    return
  }
  Start-Servers $Root $VPy
}
catch {
  $inv = $_.InvocationInfo
  Write-Host ''
  Write-Host "[x] TemplateOS failed in step '$($script:CurrentStep)'" -ForegroundColor Red
  Write-Host "    error: $($_.Exception.Message)" -ForegroundColor Red
  if ($inv -and $inv.ScriptLineNumber -and $inv.Line -notmatch 'function Fail') { Write-Host "    at line $($inv.ScriptLineNumber): $($inv.Line.Trim())" }
  if ($_.ScriptStackTrace) { Write-Host '    call stack (innermost first):'; ($_.ScriptStackTrace -split "`r?`n") | Where-Object { $_ -notmatch 'at Fail,' } | ForEach-Object { Write-Host "      $_" } }
  Write-Host "    full log: $LogFile"
  Write-Host '    next: re-run with -Trace to print every line.'
  $script:ExitCode = 1
}
finally {
  Set-PSDebug -Off
  try { Stop-Transcript | Out-Null } catch { }
}
exit $script:ExitCode

