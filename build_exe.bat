@echo off
REM ============================================================
REM  Build .EXE dengan PyInstaller (jalankan di WINDOWS)
REM  Hasil: dist\JnT-Dashboard\JnT-Dashboard.exe
REM ============================================================
cd /d "%~dp0"
title Build J&T Dashboard EXE

echo [i] Memasang PyInstaller + dependency...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

echo [i] Membersihkan build lama...
rmdir /s /q build dist 2>nul
del /q JnT-Dashboard.spec 2>nul

echo [i] Mengompilasi... (proses ini bisa beberapa menit)
python -m PyInstaller run_dashboard.py ^
  --name "JnT-Dashboard" ^
  --onedir --noconfirm --clean ^
  --collect-all streamlit ^
  --collect-all plotly ^
  --collect-all sklearn ^
  --collect-data openpyxl ^
  --add-data "dashboard.py;." ^
  --add-data "config.py;." ^
  --add-data "data_loader.py;." ^
  --add-data "data_cleaning.py;." ^
  --add-data "forecasting.py;." ^
  --add-data "settlement_engine.py;." ^
  --add-data "cashflow_engine.py;." ^
  --add-data "geography_engine.py;." ^
  --add-data "visualization.py;." ^
  --add-data "insights.py;." ^
  --add-data "assets;assets" ^
  --add-data "JnT;JnT"

echo.
echo [OK] Selesai. Buka: dist\JnT-Dashboard\JnT-Dashboard.exe
echo      (Folder JnT ikut dibundel; untuk data terbaru, ganti file
echo       jnt_recap.xlsx di dalam folder dist tsb, atau rebuild.)
pause
