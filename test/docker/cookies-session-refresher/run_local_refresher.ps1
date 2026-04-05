param(
  [string]$ProfileDir,
  [string]$RefreshTargets,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..\..')).Path
$ComposeFile = Join-Path $ScriptDir 'compose.cookies-refresh.local.yml'
$SourcesFile = Join-Path $ScriptDir 'refresh_sources.list'
$SmokeCheckScript = Join-Path $ScriptDir 'smoke_check_local_refresher.py'
$VenvPython = Join-Path $RepoRoot 'venv\Scripts\python.exe'
$WorkingProfileDir = if ($ProfileDir) {
  $ProfileDir
} else {
  Join-Path $ScriptDir 'FirefoxProfile'
}
$LogsDir = Join-Path $ScriptDir 'logs'
$RunId = Get-Date -Format 'yyyyMMdd_HHmmss'
$RunLogFile = Join-Path $LogsDir "session_refresher_$RunId.log"
$LatestLogFile = Join-Path $LogsDir 'session_refresher.latest.log'

function Get-Timestamp {
  Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
}

function Write-LocalLog {
  param([string]$Message)

  $line = '[{0}] [local] {1}' -f (Get-Timestamp), $Message
  Write-Host $line
  Add-Content -Path $RunLogFile -Value $line -Encoding utf8
}

function Write-ProcessOutput {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return
  }

  Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host $_
    Add-Content -Path $RunLogFile -Value $_ -Encoding utf8
  }
}

function Invoke-LoggedProcess {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$FailureMessage
  )

  $stdoutPath = Join-Path $LogsDir ('stdout_{0}_{1}.log' -f $RunId, [guid]::NewGuid().ToString('N'))
  $stderrPath = Join-Path $LogsDir ('stderr_{0}_{1}.log' -f $RunId, [guid]::NewGuid().ToString('N'))

  try {
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

    Write-ProcessOutput -Path $stdoutPath
    Write-ProcessOutput -Path $stderrPath

    if ($process.ExitCode -ne 0) {
      throw "$FailureMessage with exit code $($process.ExitCode)"
    }
  }
  finally {
    Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
  }
}

function Get-RefreshTargetsFromSourcesFile {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Sources file not found: $Path"
  }

  $targets = [System.Collections.Generic.List[string]]::new()
  Write-LocalLog "sources_parse_start file=$Path"

  foreach ($rawLine in Get-Content -Encoding utf8 $Path) {
    $line = $rawLine.Trim()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) {
      continue
    }

    $parts = $line.Split('|')
    if ($parts.Count -ne 3) {
      throw "Invalid sources line in ${Path}: $line"
    }

    $sourceKey = $parts[0].Trim()
    $sourceFolder = $parts[1].Trim()
    $sourceUrls = $parts[2].Trim()
    if ([string]::IsNullOrWhiteSpace($sourceKey) -or [string]::IsNullOrWhiteSpace($sourceFolder) -or [string]::IsNullOrWhiteSpace($sourceUrls)) {
      throw "Invalid sources line in ${Path}: $line"
    }

    $sourceCount = 0
    foreach ($rawUrl in $sourceUrls.Split(';')) {
      $url = $rawUrl.Trim()
      if ([string]::IsNullOrWhiteSpace($url)) {
        continue
      }
      if (-not ($url.StartsWith('http://') -or $url.StartsWith('https://'))) {
        throw "Invalid URL in ${Path}: $url"
      }
      $targets.Add($url)
      $sourceCount += 1
      Write-LocalLog "source=$sourceKey folder=$sourceFolder url=$url"
    }

    if ($sourceCount -eq 0) {
      throw "No URLs found for source '$sourceKey' in $Path"
    }

    Write-LocalLog "source=$sourceKey urls_count=$sourceCount"
  }

  if ($targets.Count -eq 0) {
    throw "No refresh targets found in $Path"
  }

  Write-LocalLog "sources_parse_done file=$Path total_targets=$($targets.Count)"
  return ($targets -join ',')
}

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
  throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $WorkingProfileDir -PathType Container)) {
  throw "Working Firefox profile directory not found: $WorkingProfileDir"
}

if (-not (Test-Path -LiteralPath $SourcesFile -PathType Leaf)) {
  throw "Sources file not found: $SourcesFile"
}

if (-not (Test-Path -LiteralPath $SmokeCheckScript -PathType Leaf)) {
  throw "Smoke-check script not found: $SmokeCheckScript"
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
  throw "venv python not found: $VenvPython"
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType File -Force -Path $RunLogFile | Out-Null
Copy-Item -LiteralPath $RunLogFile -Destination $LatestLogFile -Force

$profileItemsCount = (Get-ChildItem -LiteralPath $WorkingProfileDir -Force | Measure-Object).Count
Write-LocalLog "run_local_refresher_start compose_file=$ComposeFile"
Write-LocalLog "run_log_file=$RunLogFile"
Write-LocalLog "sources_file=$SourcesFile"
Write-LocalLog "smoke_check_script=$SmokeCheckScript"
Write-LocalLog "working_profile_dir=$WorkingProfileDir"
Write-LocalLog "working_profile_items_count=$profileItemsCount"
Write-LocalLog 'working_profile_mode=direct_mount'

$resolvedTargets = if ($RefreshTargets) {
  Write-LocalLog 'sources_parse_mode=argument'
  $RefreshTargets
} else {
  Get-RefreshTargetsFromSourcesFile -Path $SourcesFile
}

Write-LocalLog "resolved_targets=$resolvedTargets"

$env:HOST_UID = '1000'
$env:HOST_GID = '1000'
$env:REFRESH_TARGETS = $resolvedTargets

if (-not $SkipBuild) {
  Write-LocalLog 'compose_build_start image=djgurda-cookies-session-refresher:local-test'
  Invoke-LoggedProcess -FilePath 'docker' -Arguments @('compose', '-f', $ComposeFile, 'build', 'cookies-session-refresher-local') -FailureMessage 'docker compose build failed'
  Write-LocalLog 'compose_build_done image=djgurda-cookies-session-refresher:local-test'
}

Write-LocalLog 'compose_run_start container_name=DJgurda-cookies-local'
Invoke-LoggedProcess -FilePath 'docker' -Arguments @('compose', '-f', $ComposeFile, 'run', '--rm', 'cookies-session-refresher-local') -FailureMessage 'docker compose run failed'
Write-LocalLog 'compose_run_done container_name=DJgurda-cookies-local exit_code=0'

Write-LocalLog "smoke_check_start log_file=$RunLogFile"
Invoke-LoggedProcess -FilePath $VenvPython -Arguments @($SmokeCheckScript, $RunLogFile) -FailureMessage 'local smoke check failed'
Write-LocalLog 'smoke_check_done result=pass'

Copy-Item -LiteralPath $RunLogFile -Destination $LatestLogFile -Force
Write-LocalLog 'run_local_refresher_done'
