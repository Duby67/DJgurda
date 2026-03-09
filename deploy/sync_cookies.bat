@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SOURCE_DIR=%SCRIPT_DIR%cookies"
set "CONFIG_FILE=%SCRIPT_DIR%sync_cookies.env"

if not exist "%CONFIG_FILE%" (
    echo [ERROR] Local sync config not found: "%CONFIG_FILE%"
    echo [INFO] Create it from "%SCRIPT_DIR%sync_cookies.env.example"
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do (
    if not "%%~A"=="" (
        set "%%~A=%%~B"
    )
)

if not defined REMOTE_USER (
    echo [ERROR] REMOTE_USER is not defined in "%CONFIG_FILE%"
    exit /b 1
)

if not defined REMOTE_HOST (
    echo [ERROR] REMOTE_HOST is not defined in "%CONFIG_FILE%"
    exit /b 1
)

if not defined REMOTE_PORT (
    echo [ERROR] REMOTE_PORT is not defined in "%CONFIG_FILE%"
    exit /b 1
)

if not exist "%SOURCE_DIR%" (
    echo [ERROR] Deploy cookies directory not found: "%SOURCE_DIR%"
    exit /b 1
)

echo Select target environment for cookies upload:
echo   dev
echo   prod
set /p TARGET_ENV=Type dev or prod and press Enter:
set "TARGET_ENV=%TARGET_ENV: =%"

if /I not "%TARGET_ENV%"=="dev" if /I not "%TARGET_ENV%"=="prod" (
    echo [ERROR] Invalid environment: "%TARGET_ENV%". Expected dev or prod.
    exit /b 1
)

set "REMOTE_DIR=/home/%REMOTE_USER%/bot_%TARGET_ENV%/data/cookies"

where ssh >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ssh is not found in PATH.
    exit /b 1
)

where scp >nul 2>&1
if errorlevel 1 (
    echo [ERROR] scp is not found in PATH.
    exit /b 1
)

echo [INFO] Ensuring remote directory exists: %REMOTE_DIR%
ssh -p %REMOTE_PORT% %REMOTE_USER%@%REMOTE_HOST% "mkdir -p %REMOTE_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to prepare remote directory.
    exit /b 1
)

set /a FILES_COPIED=0
for %%F in ("%SOURCE_DIR%\*_cookies.txt") do (
    if exist "%%~fF" (
        echo [INFO] Uploading %%~nxF
        scp -P %REMOTE_PORT% "%%~fF" %REMOTE_USER%@%REMOTE_HOST%:%REMOTE_DIR%/
        if errorlevel 1 (
            echo [ERROR] Upload failed: %%~nxF
            exit /b 1
        )
        set /a FILES_COPIED+=1
    )
)

if !FILES_COPIED! EQU 0 (
    echo [WARN] No cookie files found to upload in "%SOURCE_DIR%".
) else (
    echo [OK] Uploaded !FILES_COPIED! file(s) to %REMOTE_USER%@%REMOTE_HOST%:%REMOTE_DIR%
)

endlocal
exit /b 0
