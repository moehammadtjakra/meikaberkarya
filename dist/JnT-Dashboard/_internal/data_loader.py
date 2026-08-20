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


def load_from_gsheet_webapp() -> dict:
    """
    Baca data langsung dari Google Sheet lewat endpoint Web App Apps Script
    (mode=data&token=...). Endpoint mengembalikan JSON:
        {"all_resi": [[header],[row],...], "settle_reconcile": [...], "problem": [...]}
    Tiap tabel diubah menjadi DataFrame (header di baris pertama).
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

    def _df(rows):
        if not rows:
            return None
        d = pd.DataFrame(rows[1:], columns=rows[0])
        # Angka dari getValues() datang sebagai number asli (JSON), tapi sel kosong
        # jadi "" -> kolom bertipe object. Ubah kolom yang mayoritas numerik ke
        # numeric agar pembersihan hilir tidak salah parse (hindari isu lokal desimal).
        d = d.replace("", pd.NA)
        for c in d.columns:
            conv = pd.to_numeric(d[c], errors="coerce")
            nonnull = d[c].notna().sum()
            if nonnull and conv.notna().sum() >= 0.8 * nonnull:
                d[c] = conv
        return d

    all_resi = _df(data.get("all_resi"))
    if all_resi is None or all_resi.empty:
        raise ValueError("Tab 'All Resi' kosong / tidak ditemukan di Google Sheet.")

    return {
        "all_resi": all_resi,
        "settle": _df(data.get("settle_reconcile")),
        "problem": _df(data.get("problem")),
        "path": "Google Sheet (live)",
        "mtime": time.time(),
        "sheets": list(data.keys()),
    }


def load_workbook(path: str | None = None) -> dict:
    """
    Baca seluruh sheet relevan. Sumber ditentukan config.DATA_SOURCE:
      - "gsheet" (dan URL terisi) -> tarik live dari Google Sheet (Apps Script).
      - selain itu -> baca file Excel lokal (perilaku lama, tetap sebagai fallback).
    Mengembalikan dict: {'all_resi', 'settle'|None, 'problem'|None, 'path', 'mtime', 'sheets'}
    """
    if (getattr(config, "DATA_SOURCE", "excel") == "gsheet"
            and getattr(config, "GSHEET_WEBAPP_URL", "")):
        return load_from_gsheet_webapp()

    path = path or find_excel()
    xl = pd.ExcelFile(path, engine="openpyxl")

    all_resi = _read_sheet(xl, config.SHEET_ALL_RESI)
    if all_resi is None:
        raise ValueError(
            f"Sheet '{config.SHEET_ALL_RESI}' tidak ditemukan. "
            f"Sheet tersedia: {xl.sheet_names}"
        )

    settle = _read_sheet(xl, config.SHEET_SETTLE, config.SHEET_SETTLE_ALT)
    problem = _read_sheet(xl, config.SHEET_PROBLEM)

    return {
        "all_resi": all_resi,
        "settle": settle,
        "problem": problem,
        "path": path,
        "mtime": os.path.getmtime(path),
        "sheets": xl.sheet_names,
    }
