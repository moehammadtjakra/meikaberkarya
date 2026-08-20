# -*- coding: utf-8 -*-
"""
gsheet_login.py — LOGIN SEKALI ke Google (OAuth) untuk dashboard.

Jalankan sekali dari terminal di folder ini:
    python gsheet_login.py

Alurnya:
  1. Browser terbuka -> pilih akun Google yang punya akses ke spreadsheet.
  2. Setujui izin (Google Sheets read-only).
  3. Token disimpan di credentials/authorized_user.json (dipakai dashboard, senyap).

Prasyarat:
  - File OAuth Client ID (tipe "Desktop app") disimpan sebagai:
        credentials/oauth_client.json
  - GSHEET_ID sudah diisi di secrets_local.py
"""
import os
import config

os.makedirs(os.path.dirname(config.GSHEET_OAUTH_CRED), exist_ok=True)

if not os.path.exists(config.GSHEET_OAUTH_CRED):
    raise SystemExit(
        "[!] Belum ada file OAuth Client di: %s\n"
        "    Buat di Google Cloud Console -> APIs & Services -> Credentials ->\n"
        "    Create OAuth client ID -> Application type: Desktop app -> unduh JSON,\n"
        "    lalu simpan sebagai file di atas." % config.GSHEET_OAUTH_CRED)

if "REPLACE_ME" in open(config.GSHEET_OAUTH_CRED, encoding="utf-8").read():
    raise SystemExit(
        "[!] credentials/oauth_client.json masih berisi template 'REPLACE_ME'.\n"
        "    Ganti isinya dengan JSON asli dari Google Cloud Console\n"
        "    (OAuth client ID -> Desktop app -> Download JSON). Lihat credentials/CARA_ISI.md")

if not getattr(config, "GSHEET_ID", ""):
    raise SystemExit("[!] GSHEET_ID belum diisi di secrets_local.py "
                     "(ambil dari URL: .../spreadsheets/d/<ID>/edit).")

import gspread

gc = gspread.oauth(
    credentials_filename=config.GSHEET_OAUTH_CRED,
    authorized_user_filename=config.GSHEET_OAUTH_TOKEN,
)
sh = gc.open_by_key(config.GSHEET_ID)
print("[OK] Login berhasil. Spreadsheet:", sh.title)
print("     Tabs:", [w.title for w in sh.worksheets()])
print("     Token tersimpan di:", config.GSHEET_OAUTH_TOKEN)
print("     Sekarang jalankan start.bat seperti biasa.")
