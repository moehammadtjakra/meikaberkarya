# -*- coding: utf-8 -*-
# =====================================================================
#  TEMPLATE KREDENSIAL LOKAL — JANGAN taruh token asli di file ini.
#
#  CARA PAKAI:
#   1. SALIN file ini menjadi:  secrets_local.py   (di folder yang sama)
#   2. Isi 3 nilai di bawah dengan URL & token Apps Script Anda.
#   3. Jalankan dashboard seperti biasa (start.bat). config.py otomatis
#      membaca file secrets_local.py dan menimpa nilai default.
#
#  secrets_local.py sudah masuk .gitignore → TIDAK ikut ke GitHub, aman.
# =====================================================================

DATA_SOURCE = "gsheet"   # "gsheet" untuk baca dari Google Sheet, "excel" untuk file lokal

# URL Web App Apps Script (Deploy -> Web app), yang berakhiran /exec
GSHEET_WEBAPP_URL = "https://script.google.com/macros/s/AKfy........../exec"

# Token rahasia — HARUS SAMA PERSIS dengan var DATA_TOKEN di Code.gs Apps Script
GSHEET_TOKEN = "GANTI_TOKEN_RAHASIA_PANJANG"
