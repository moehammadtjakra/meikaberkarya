# -*- coding: utf-8 -*-
"""
run_dashboard.py
================
Peluncur dashboard. Cukup double-click file ini (atau start.bat).
Akan menjalankan Streamlit dan membuka dashboard di browser default.

Mendukung dua mode:
  1) Sebagai skrip Python biasa  -> memanggil `streamlit run dashboard.py`
  2) Sebagai .exe hasil PyInstaller -> memakai streamlit.web.cli internal
"""

from __future__ import annotations
import os
import sys
import subprocess


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _clear_pycache(here):
    """Hapus cache bytecode lama agar modul yang diupdate tidak tertimpa versi usang."""
    import shutil
    pc = os.path.join(here, "__pycache__")
    if os.path.isdir(pc):
        shutil.rmtree(pc, ignore_errors=True)


def main():
    here = _app_dir()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # jangan tulis .pyc baru
    _clear_pycache(here)
    dashboard = os.path.join(here, "dashboard.py")
    args = [
        "run", dashboard,
        "--server.headless=false",
        "--server.port=8501",
        "--browser.gatherUsageStats=false",
        "--theme.base=dark",
    ]

    if getattr(sys, "frozen", False):
        # Mode .exe: jalankan via API internal Streamlit
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit"] + args
        sys.exit(stcli.main())
    else:
        # Mode skrip: panggil streamlit lewat interpreter aktif
        try:
            subprocess.run([sys.executable, "-m", "streamlit"] + args, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("\n[!] Streamlit belum terpasang. Jalankan dulu:")
            print("    pip install -r requirements.txt\n")
            input("Tekan Enter untuk keluar...")


if __name__ == "__main__":
    main()
