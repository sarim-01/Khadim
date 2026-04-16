@echo off
echo ========================================
echo Installing Backend Dependencies
echo ========================================
echo.

cd /d "D:\Final YEar Project\backend"

echo Step 1: Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Step 2: Installing all requirements...
pip install -r requirements.txt

echo.
echo Step 3: Installing transformers (for voice)...
pip install transformers torch

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next: Run 'python main.py' to start server
pause
