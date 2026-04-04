param(
  [string]$ArchivePath,
  [string]$RefreshTargets,
  [switch]$SkipBuild,
  [switch]$SkipProfilePrepare
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalDir = Join-Path $ScriptDir "local"
$ComposeFile = Join-Path $ScriptDir "compose.cookies-refresh.local.yml"
$ProfileDir = Join-Path $LocalDir "firefox_selenium_profile"
$ProfileArchive = if ($ArchivePath) {
  $ArchivePath
} else {
  Join-Path $LocalDir "firefox_profile.tar.gz"
}
$LogsDir = Join-Path $LocalDir "logs"
$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLogFile = Join-Path $LogsDir "session_refresher_$RunId.log"
$LatestLogFile = Join-Path $LogsDir "session_refresher.latest.log"

$ProfileFiles = @(
  "cookies.sqlite",
  "permissions.sqlite",
  "content-prefs.sqlite",
  "key4.db",
  "cert9.db",
  "pkcs11.txt",
  "logins.json",
  "formhistory.sqlite",
  "storage.sqlite",
  "webappsstore.sqlite",
  "handlers.json",
  "places.sqlite"
)

$ProfileDirs = @(
  "storage"
)

function Get-Timestamp {
  Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

function Write-LocalLog {
  param([string]$Message)

  $line = "[{0}] [local] {1}" -f (Get-Timestamp), $Message
  Write-Host $line
  Add-Content -Path $RunLogFile -Value $line -Encoding utf8
}

function Resolve-ProfileSourceDir {
  param([string]$ExtractDir)

  $firefoxProfileDir = Join-Path $ExtractDir "firefox_profile"
  if (Test-Path -LiteralPath $firefoxProfileDir -PathType Container) {
    return $firefoxProfileDir
  }

  $defaultProfileDir = Join-Path $ExtractDir "rwui9dvc.default"
  if (Test-Path -LiteralPath $defaultProfileDir -PathType Container) {
    return $defaultProfileDir
  }

  $childDirs = Get-ChildItem -LiteralPath $ExtractDir -Directory -Force
  if ($childDirs.Count -eq 1) {
    return $childDirs[0].FullName
  }

  return $ExtractDir
}

function Copy-ProfileItem {
  param(
    [string]$SourceDir,
    [string]$TargetDir,
    [string]$ItemName
  )

  $sourcePath = Join-Path $SourceDir $ItemName
  $targetPath = Join-Path $TargetDir $ItemName

  if (-not (Test-Path -LiteralPath $sourcePath)) {
    Write-LocalLog "prepare_profile_skip_missing item=$ItemName"
    return
  }

  $targetParent = Split-Path -Parent $targetPath
  New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
  Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Recurse -Force
  Write-LocalLog "prepare_profile_item_copied item=$ItemName"
}

function Prepare-LocalProfile {
  if (-not (Test-Path -LiteralPath $ProfileArchive -PathType Leaf)) {
    throw "Profile archive not found: $ProfileArchive"
  }

  New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
  New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

  $archiveSizeBytes = (Get-Item -LiteralPath $ProfileArchive).Length
  Write-LocalLog "prepare_profile_start archive_path=$ProfileArchive profile_dir=$ProfileDir"
  Write-LocalLog "prepare_profile_archive_found file=$ProfileArchive size_bytes=$archiveSizeBytes"

  $extractDir = Join-Path $LocalDir (".tmp_profile_extract_{0}" -f ([guid]::NewGuid().ToString("N")))
  New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

  try {
    Write-LocalLog "prepare_profile_extract_start archive_path=$ProfileArchive tmp_dir=$extractDir"
    tar -xzf $ProfileArchive -C $extractDir
    Write-LocalLog "prepare_profile_extract_done tmp_dir=$extractDir"

    $sourceDir = Resolve-ProfileSourceDir -ExtractDir $extractDir
    Write-LocalLog "prepare_profile_source_resolved source_dir=$sourceDir profile_dir=$ProfileDir"

    Write-LocalLog "prepare_profile_replace_start profile_dir=$ProfileDir"
    Get-ChildItem -LiteralPath $ProfileDir -Force |
      Remove-Item -Recurse -Force

    foreach ($itemName in $ProfileFiles) {
      Copy-ProfileItem -SourceDir $sourceDir -TargetDir $ProfileDir -ItemName $itemName
    }

    foreach ($itemName in $ProfileDirs) {
      Copy-ProfileItem -SourceDir $sourceDir -TargetDir $ProfileDir -ItemName $itemName
    }
    Write-LocalLog "prepare_profile_replace_done profile_dir=$ProfileDir"

    Write-LocalLog "prepare_profile_cleanup_start profile_dir=$ProfileDir"
    @(
      ".parentlock",
      ".startup-incomplete",
      "lock",
      "sessionstore.jsonlz4",
      "sessionstore-backups\\recovery.jsonlz4",
      "sessionstore-backups\\recovery.baklz4",
      "sessionstore-backups\\previous.jsonlz4"
    ) | ForEach-Object {
      Remove-Item -LiteralPath (Join-Path $ProfileDir $_) -Force -ErrorAction SilentlyContinue
    }

    Get-ChildItem -LiteralPath (Join-Path $ProfileDir "sessionstore-backups") -Force -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like "upgrade.jsonlz4*" } |
      Remove-Item -Force -ErrorAction SilentlyContinue

    @("cache2", "startupCache", "crashes", "minidumps") | ForEach-Object {
      Remove-Item -LiteralPath (Join-Path $ProfileDir $_) -Recurse -Force -ErrorAction SilentlyContinue
    }

    Get-ChildItem -LiteralPath $ProfileDir -Recurse -Force -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint -or
        $_.Name -like "*.sqlite-shm" -or
        $_.Name -like "*.sqlite-wal"
      } |
      Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $profileItemsCount = (Get-ChildItem -LiteralPath $ProfileDir -Force | Measure-Object).Count
    Write-LocalLog "prepare_profile_cleanup_done profile_dir=$ProfileDir sessionstore_removed=true cache_removed=true sqlite_sidecars_removed=true symlinks_removed=true"
    Write-LocalLog "prepare_profile_done profile_dir=$ProfileDir profile_items_count=$profileItemsCount"
  } finally {
    Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
  throw "Compose file not found: $ComposeFile"
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType File -Force -Path $RunLogFile | Out-Null
Copy-Item -LiteralPath $RunLogFile -Destination $LatestLogFile -Force

Write-LocalLog "run_local_refresher_start compose_file=$ComposeFile"
Write-LocalLog "run_log_file=$RunLogFile"
Write-LocalLog "profile_archive=$ProfileArchive"
Write-LocalLog "profile_dir=$ProfileDir"

if (-not $SkipProfilePrepare) {
  Prepare-LocalProfile
} else {
  if (-not (Test-Path -LiteralPath $ProfileDir -PathType Container)) {
    throw "Profile directory does not exist: $ProfileDir"
  }
  Write-LocalLog "prepare_profile_skipped profile_dir=$ProfileDir"
}

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