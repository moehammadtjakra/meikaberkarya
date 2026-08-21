# -*- coding: utf-8 -*-
"""
data_loader.py
==============
Mendeteksi & membaca file Excel terbaru secara OTOMATIS (tanpa upload manual).

Fungsi utama:
    find_excel()   -> mengembalikan path file Excel terbaru
    load_workbook()-> membaca semua sheet menjadi dict of DataFrame (mentah)
"""

from __future__ import annotations
import os
import glob
import pandas as pd

import config


def find_excel() -> str:
    """Cari file Excel di folder data. Prioritas: nama persis -> pola -> terbaru."""
    exact = os.path.join(config.DATA_DIR, config.EXCEL_FILENAME)
    if os.path.exists(exact):
        return exact

    candidates: list[str] = []
    for pat in config.EXCEL_GLOB_PATTERNS:
        candidates += glob.glob(os.path.join(config.DATA_DIR, pat))
    # buang file lock Excel sementara (~$...)
    candidates = [c for c in candidates if not os.path.basename(c).startswith("~$")]
    if not candidates:
        raise FileNotFoundError(
            f"File Excel tidak ditemukan di folder: {config.DATA_DIR}\n"
            f"Pastikan '{config.EXCEL_FILENAME}' tersedia."
        )
    # ambil yang paling baru dimodifikasi
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _read_sheet(xl: pd.ExcelFile, *names: str) -> pd.DataFrame | None:
    """Baca sheet pertama yang tersedia dari daftar nama alternatif."""
    for n in names:
        if n in xl.sheet_names:
            return xl.parse(n)
    return None


def _rows_to_df(rows):
    """Ubah list-of-list (baris0=header) -> DataFrame; kolom mayoritas-numerik
    dikonversi ke numeric agar pembersihan hilir tidak salah parse (isu desimal lokal)."""
    if not rows:
        return None
    header = rows[0]
    body = [r + [None] * (len(header) - len(r)) for r in rows[1:]]  # pad baris pendek
    d = pd.DataFrame(body, columns=header)
    d = d.replace("", pd.NA)
    for c in d.columns:
        conv = pd.to_numeric(d[c], errors="coerce")
        nonnull = d[c].notna().sum()
        if nonnull and conv.notna().sum() >= 0.8 * nonnull:
            d[c] = conv
    return d


def load_from_gsheet_oauth() -> dict:
    """
    Baca sheet LANGSUNG sebagai akun Google Anda via OAuth (gspread).
    Login sekali via browser (token disimpan di credentials/authorized_user.json),
    berikutnya berjalan senyap. Dipakai karena organisasi memblokir web app publik
    & service-account key.

    Angka diminta sebagai UNFORMATTED_VALUE (number asli) dan tanggal sebagai
    FORMATTED_STRING (yyyy-MM-dd sesuai format sel) agar konsisten dgn Excel.
    """
    import time
    try:
        import gspread
    except ImportError:
        raise ImportError("Paket 'gspread' belum terpasang. Jalankan: "
                          "pip install -r requirements.txt")

    gid = getattr(config, "GSHEET_ID", "")
    if not gid:
        raise ValueError("GSHEET_ID belum diisi (secrets_local.py) — ambil dari URL "
                         "spreadsheet: .../spreadsheets/d/<ID>/edit")

    # (A) DEPLOY headless (Streamlit Cloud): pakai kredensial dari dict/secrets,
    #     tanpa browser. Butuh oauth_client + authorized_user (hasil login lokal sekali).
    client_info = getattr(config, "GSHEET_OAUTH_CLIENT_INFO", None)
    auth_info = getattr(config, "GSHEET_OAUTH_AUTHORIZED_INFO", None)
    if client_info and auth_info:
        gc, _ = gspread.oauth_from_dict(dict(client_info), dict(auth_info))
    else:
        # (B) LOKAL: pakai file + login browser sekali (via gsheet_login.py).
        cred = getattr(config, "GSHEET_OAUTH_CRED", None)
        authf = getattr(config, "GSHEET_OAUTH_TOKEN", None)
        if not cred or not os.path.exists(cred):
            raise FileNotFoundError(
                "File OAuth Client belum ada di: %s\n"
                "Buat OAuth Client ID (tipe 'Desktop app') di Google Cloud Console, "
                "unduh JSON-nya, simpan sebagai file itu, lalu jalankan: python gsheet_login.py"
                % cred)
        gc = gspread.oauth(credentials_filename=cred, authorized_user_filename=authf)
    sh = gc.open_by_key(gid)

    def _grab(titles):
        for t in ([titles] if isinstance(titles, str) else (titles or [])):
            try:
                r = sh.values_get(t, params={
                    "valueRenderOption": "UNFORMATTED_VALUE",
                    "dateTimeRenderOption": "FORMATTED_STRING",
                })
            except Exception:
                continue
            df = _rows_to_df(r.get("values"))
            if df is not None and not df.empty:
                return df
        return None

    all_resi = _grab(getattr(config, "GSHEET_TAB_ALL_RESI", "All Resi"))
    if all_resi is None or all_resi.empty:
        raise ValueError("Tab '%s' kosong / tidak ditemukan di Google Sheet."
                         % getattr(config, "GSHEET_TAB_ALL_RESI", "All Resi"))

    return {
        "all_resi": all_resi,
        "settle": _grab(getattr(config, "GSHEET_TAB_SETTLE", "Settle Reconcile")),
        "problem": _grab(getattr(config, "GSHEET_TAB_PROBLEM", "Laporan Paket Tertunda")),
        "order": _grab(getattr(config, "GSHEET_TAB_ORDER", [])),
        "stock": _grab(getattr(config, "GSHEET_TAB_STOCK", [])),
        "oo": _grab(getattr(config, "GSHEET_TAB_OO", [])),
        "ref": _grab(getattr(config, "GSHEET_TAB_REF", [])),
        "path": "Google Sheet (live, OAuth)",
        "mtime": time.time(),
        "sheets": [w.title for w in sh.worksheets()],
    }


def load_from_gsheet_webapp() -> dict:
    """
    (TIDAK dipakai — org memblokir deployment 'Anyone'.) Baca via endpoint Web App
    Apps Script (mode=data&token=...). Disimpan sebagai alternatif bila kebijakan berubah.
    """
    import time
    import requests

    url = getattr(config, "GSHEET_WEBAPP_URL", "")
    token = getattr(config, "GSHEET_TOKEN", "")
    if not url:
        raise ValueError("GSHEET_WEBAPP_URL belum diisi (config.py / secrets_local.py).")

    r = requests.get(url, params={"mode": "data", "token": token},
                     timeout=120, allow_redirects=True)
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        raise ValueError("Respons GSheet bukan JSON — cek URL /exec, token, & akses "
                         "deployment (harus 'Anyone').")
    if isinstance(data, dict) and data.get("error"):
        raise PermissionError("Akses GSheet ditolak — token salah / deployment bukan "
                              "'Anyone'.")

    all_resi = _rows_to_df(data.get("all_resi"))
    if all_resi is None or all_resi.empty:
        raise ValueError("Tab 'All Resi' kosong / tidak ditemukan di Google Sheet.")

    return {
        "all_resi": all_resi,
        "settle": _rows_to_df(data.get("settle_reconcile")),
        "problem": _rows_to_df(data.get("problem")),
        "order": _rows_to_df(data.get("order")),
        "stock": _rows_to_df(data.get("stock")),
        "path": "Google Sheet (live)",
        "mtime": time.time(),
        "sheets": list(data.keys()),
    }


def load_workbook(path: str | None = None) -> dict:
    """
    Baca seluruh sheet relevan. Sumber ditentukan config.DATA_SOURCE:
      - "gsheet" + GSHEET_MODE="oauth"  -> baca sheet langsung via OAuth (default).
      - "gsheet" + GSHEET_MODE="webapp" -> via Apps Script Web App (diblokir org).
      - selain itu -> baca file Excel lokal (fallback).
    """
    if getattr(config, "DATA_SOURCE", "excel") == "gsheet":
        mode = getattr(config, "GSHEET_MODE", "oauth")
        if mode == "webapp":
            return load_from_gsheet_webapp()
        return load_from_gsheet_oauth()

    path = path or find_excel()
    xl = pd.ExcelFile(path, engine="openpyxl")

    all_resi = _read_sheet(xl, config.SHEET_ALL_RESI, "All Resi", "all_resi")
    if all_resi is None:
        raise ValueError(
            f"Sheet '{config.SHEET_ALL_RESI}' tidak ditemukan. "
            f"Sheet tersedia: {xl.sheet_names}"
        )

    settle = _read_sheet(xl, config.SHEET_SETTLE, config.SHEET_SETTLE_ALT,
                         "Settle Reconcile", "settle_reconcile")
    problem = _read_sheet(xl, config.SHEET_PROBLEM, "Laporan Paket Tertunda")
    order = _read_sheet(xl, "Import-Order", "ORDERS", "Order")
    stock = _read_sheet(xl, "Import-Stock", "STOK", "Stok", "Stock")
    oo = _read_sheet(xl, "OrderOnline", "Order Online", "OO")
    ref = _read_sheet(xl, "Impor-RefProduk", "Import-RefProduk", "RefProduk")

    return {
        "all_resi": all_resi,
        "settle": settle,
        "problem": problem,
        "order": order,
        "stock": stock,
        "oo": oo,
        "ref": ref,
        "path": path,
        "mtime": os.path.getmtime(path),
        "sheets": xl.sheet_names,
    }
