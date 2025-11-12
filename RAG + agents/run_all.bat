@echo off
title Khadim Multi-Agent System Launcher

echo ===================================================
echo  Khadim Restaurant - Multi-Agent System Launcher
echo ===================================================
echo.
:: CHANGED: Updated path to look in the current folder
echo Checking for virtual environment at '.\venv\'...
echo.

:: CHANGED: Removed '..' from the path
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at '.\venv\Scripts\activate.bat'
    echo Please make sure your 'venv' folder is located in the *same* directory
    echo as this batch script.
    echo.
    echo Your current directory: %cd%
    echo Expected venv path: %cd%\venv
    echo.
    pause
    exit /b
)

echo Virtual environment found!
echo.
echo [1/3] Starting Cart Agent in a new window...
:: CHANGED: Removed '..' from the path
START "Cart Agent" cmd /k "call venv\Scripts\activate.bat && python cart_agent.py"

echo [2/3] Starting Order Agent in a new window...
:: CHANGED: Removed '..' from the path
START "Order Agent" cmd /k "call venv\Scripts\activate.bat && python order_agent.py"

echo [3/3] Starting Streamlit Orchestrator...
:: CHANGED: Removed '..' from the path
START "Streamlit Orchestrator" cmd /c "call venv\Scripts\activate.bat && streamlit run orchestrator.py"

echo.
echo All processes have been launched in separate windows.
echo