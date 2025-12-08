@echo off
title Khadim Multi-Agent System Launcher

echo ================================================
echo       K H A A D I M   -  Multi Agent System
echo ================================================
echo.

REM -----------------------------------------------
REM CHECK VENV EXISTS
REM -----------------------------------------------
echo Checking for virtual environment...
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo ERROR: venv not found at: %cd%\venv
    echo Make sure you created venv using:
    echo python -m venv venv
    pause
    exit /b
)

echo Virtual environment found!
echo.

REM -----------------------------------------------
REM START CART AGENT
REM -----------------------------------------------
echo [1/5] Starting Cart Agent...
START "Cart Agent" cmd /k "call venv\Scripts\activate.bat && python cart_agent.py"

REM -----------------------------------------------
REM START ORDER AGENT
REM -----------------------------------------------
echo [2/5] Starting Order Agent...
START "Order Agent" cmd /k "call venv\Scripts\activate.bat && python order_agent.py"

REM -----------------------------------------------
REM START KITCHEN AGENT
REM -----------------------------------------------
echo [3/5] Starting Kitchen Agent...
START "Kitchen Agent" cmd /k "call venv\Scripts\activate.bat && python kitchen_agent.py"

REM -----------------------------------------------
REM START UPSELL AGENT (This was missing!)
REM -----------------------------------------------
echo [4/5] Starting Upsell Agent...
START "Upsell Agent" cmd /k "call venv\Scripts\activate.bat && python upsell_agent.py"

REM -----------------------------------------------
REM START Recommender Agent (This was missing!)
REM -----------------------------------------------
echo [5/6] Starting Recommender Agent...
START "Recommender Agent" cmd /k "call venv\Scripts\activate.bat && python recommender_agent.py"

REM -----------------------------------------------
REM START STREAMLIT ORCHESTRATOR
REM -----------------------------------------------
echo [6/6] Starting Orchestrator...
START "Orchestrator" cmd /k "call venv\Scripts\activate.bat && python -m streamlit run orchestrator.py"

echo.
echo All 6 agents launched in separate windows.
echo You can now open http://localhost:8501 to chat.
echo.
pause