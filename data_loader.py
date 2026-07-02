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


def load_workbook(path: str | None = None) -> dict:
    """
    Baca seluruh sheet relevan dari workbook.
    Mengembalikan dict: {'all_resi': df, 'settle': df|None, 'problem': df|None, 'path', 'mtime'}
    """
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
