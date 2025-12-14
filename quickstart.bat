@echo off
REM Quick start script for API Bouncer on Windows

echo.
echo ========================================
echo   API Bouncer - Quick Start
echo ========================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

REM Start Redis
echo [1/4] Starting Redis...
docker-compose up -d
if errorlevel 1 (
    echo [ERROR] Failed to start Redis
    pause
    exit /b 1
)
echo       Redis started successfully!
echo.

REM Wait for Redis to be ready
echo [2/4] Waiting for Redis to be ready...
timeout /t 3 /nobreak >nul
echo       Redis is ready!
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo [3/4] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo       Virtual environment created!
    echo.
    
    echo [4/4] Installing dependencies...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo       Dependencies installed!
) else (
    echo [3/4] Virtual environment already exists
    echo [4/4] Activating virtual environment...
    call venv\Scripts\activate.bat
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Redis is running on localhost:6379
echo.
echo To start the API, run:
echo   uvicorn app.main:app --reload
echo.
echo Or simply:
echo   python -m app.main
echo.
echo To test the rate limiting:
echo   python test_rate_limit.py
echo.
echo To stop Redis:
echo   docker-compose down
echo.
pause
