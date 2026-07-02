@echo off
REM ============================================================
REM  J&T BI Dashboard - Peluncur (double click file ini)
REM  Otomatis: cek dependency -> jalankan dashboard di browser
REM ============================================================
cd /d "%~dp0"
title J&T BI Dashboard - Meika Berkarya

echo.
echo  =====================================================
echo   J^&T Business Intelligence Dashboard
echo   Meika Berkarya
echo  =====================================================
echo.

REM cek python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python tidak ditemukan.
    echo     Install Python 3.10+ dari https://www.python.org/downloads/
    echo     dan centang "Add Python to PATH" saat instalasi.
    pause
    exit /b
)

REM pasang dependency hanya jika streamlit belum ada
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo [i] Memasang dependency pertama kali, mohon tunggu...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
)

REM bersihkan cache bytecode lama (cegah modul usang setelah update)
if exist "__pycache__" rmdir /s /q "__pycache__"

echo [i] Menjalankan dashboard... browser akan terbuka otomatis.
echo     Untuk berhenti: tutup jendela ini atau tekan Ctrl+C.
echo.
python -B -m streamlit run dashboard.py --theme.base=dark --browser.gatherUsageStats=false

pause
