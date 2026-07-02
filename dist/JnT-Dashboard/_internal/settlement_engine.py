# -*- coding: utf-8 -*-
"""
settlement_engine.py
====================
Menerjemahkan tanggal paket DITERIMA menjadi tanggal PENCAIRAN (settlement)
berdasarkan mode yang dipilih.

Mode 1 : cair setiap hari kerja (jeda rata-rata setelah diterima).
Mode 2 : cair Senin / Selasa / Kamis (default), mengikuti aturan brief:
         - Cair Senin  <= paket diterima Rabu/Kamis (minggu sebelumnya)
         - Cair Selasa <= paket diterima Jumat/Sabtu/Minggu
         - Cair Kamis  <= paket diterima Senin/Selasa
"""

from __future__ import annotations
import pandas as pd

import config


def _next_weekday(d: pd.Timestamp, target_weekday: int) -> pd.Timestamp:
    """Tanggal >= d berikutnya yang jatuh pada target_weekday (Mon=0)."""
    delta = (target_weekday - d.weekday()) % 7
    return d + pd.Timedelta(days=delta)


def _add_business_days(d: pd.Timestamp, n: int) -> pd.Timestamp:
    """Tambah n hari kerja (Sen-Jum)."""
    cur = d
    added = 0
    while added < n:
        cur += pd.Timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def payout_date_mode2(received: pd.Timestamp) -> pd.Timestamp:
    """Tanggal pencairan untuk satu paket pada Mode 2."""
    if pd.isna(received):
        return pd.NaT
    payout_name = config.SETTLE_MODE2_RECEIVE_TO_PAYOUT.get(received.weekday())
    if payout_name is None:
        # fallback: cair pada Kamis terdekat
        payout_name = "Kamis"
    target = config.PAYOUT_WEEKDAY[payout_name]
    # cair pada hari target SETELAH paket diterima (>= hari berikutnya)
    return _next_weekday(received + pd.Timedelta(days=1), target)


def payout_date_mode1(received: pd.Timestamp,
                      lag: int = config.SETTLE_DAILY_LAG_DEFAULT) -> pd.Timestamp:
    """Mode 1: cair `lag` hari kerja setelah diterima."""
    if pd.isna(received):
        return pd.NaT
    return _add_business_days(received, lag)


def assign_payout_dates(received: pd.Series, mode: str = "mode2",
                        lag: int = config.SETTLE_DAILY_LAG_DEFAULT) -> pd.Series:
    """Vektor: petakan seri tanggal-diterima -> tanggal pencairan."""
    fn = (lambda d: payout_date_mode1(d, lag)) if mode == "mode1" else payout_date_mode2
    return received.apply(fn)


def settle_label(received_weekday: int, mode: str = "mode2") -> str:
    if mode == "mode2":
        return config.SETTLE_MODE2_RECEIVE_TO_PAYOUT.get(received_weekday, "Kamis")
    return "Hari Kerja"
