param(
  [string]$ProfileDir,
  [string]$RefreshTargets,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = Join-Path $ScriptDir "compose.cookies-refresh.local.yml"
$WorkingProfileDir = if ($ProfileDir) {
  $ProfileDir
} else {
  Join-Path $ScriptDir "FirefoxProfile"
}
$LogsDir = Join-Path $ScriptDir "logs"
$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLogFile = Join-Path $LogsDir "session_refresher_$RunId.log"
$LatestLogFile = Join-Path $LogsDir "session_refresher.latest.log"

function Get-Timestamp {
  Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

function Write-LocalLog {
  param([string]$Message)

  $line = "[{0}] [local] {1}" -f (Get-Timestamp), $Message
  Write-Host $line
  Add-Content -Path $RunLogFile -Value $line -Encoding utf8
}

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
  throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $WorkingProfileDir -PathType Container)) {
  throw "Working Firefox profile directory not found: $WorkingProfileDir"
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType File -Force -Path $RunLogFile | Out-Null
Copy-Item -LiteralPath $RunLogFile -Destination $LatestLogFile -Force

$profileItemsCount = (Get-ChildItem -LiteralPath $WorkingProfileDir -Force | Measure-Object).Count
Write-LocalLog "run_local_refresher_start compose_file=$ComposeFile"
Write-LocalLog "run_log_file=$RunLogFile"
Write-LocalLog "working_profile_dir=$WorkingProfileDir"
Write-LocalLog "working_profile_items_count=$profileItemsCount"
Write-LocalLog "working_profile_mode=direct_mount"

$env:HOST_UID = "1000"
$env:HOST_GID = "1000"
if ($RefreshTargets) {
  $env:REFRESH_TARGETS = $RefreshTargets
}

if (-not $SkipBuild) {
  Write-LocalLog "compose_build_start image=djgurda-cookies-session-refresher:local-test"
  docker compose -f $ComposeFile build cookies-session-refresher-local 2>&1 |
    ForEach-Object {
      Write-Host $_
      Add-Content -Path $RunLogFile -Value $_ -Encoding utf8
    }
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose build failed with exit code $LASTEXITCODE"
  }
  Write-LocalLog "compose_build_done image=djgurda-cookies-session-refresher:local-test"
}

Write-LocalLog "compose_run_start container_name=DJgurda-cookies-local"
docker compose -f $ComposeFile run --rm cookies-session-refresher-local 2>&1 |
  ForEach-Object {
    Write-Host $_
    Add-Content -Path $RunLogFile -Value $_ -Encoding utf8
  }
if ($LASTEXITCODE -ne 0) {
  throw "docker compose run failed with exit code $LASTEXITCODE"
}

Copy-Item -LiteralPath $RunLogFile -Destination $LatestLogFile -Force
Write-LocalLog "compose_run_done container_name=DJgurda-cookies-local exit_code=0"
Write-LocalLog "run_local_refresher_done"
