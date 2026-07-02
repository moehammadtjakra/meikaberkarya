# -*- coding: utf-8 -*-
"""
forecasting.py
==============
Mempelajari histori sheet all_resi untuk:
 1. Menghasilkan BASELINE metrik (default simulator).
 2. Forecast volume resi harian ke depan (tren via regresi linear sklearn,
    dengan musiman hari-dalam-minggu). Fallback ke rata-rata bila data minim.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

import config

try:
    from sklearn.linear_model import LinearRegression
    _HAS_SK = True
except Exception:                       # pragma: no cover
    _HAS_SK = False


def compute_baseline(df: pd.DataFrame) -> dict:
    """Hitung metrik baseline dari histori untuk mengisi default simulator."""
    n = len(df)
    days = df["tgl_kirim"].dt.normalize().nunique() if "tgl_kirim" in df else 1
    days = max(days, 1)

    sampai = df["is_sampai"].sum() if "is_sampai" in df else 0
    cod_mask = df["is_cod"] if "is_cod" in df else pd.Series(True, index=df.index)

    def _mean(col, mask=None, default=0.0):
        if col not in df:
            return default
        s = df.loc[mask, col] if mask is not None else df[col]
        v = s.mean()
        return float(v) if pd.notna(v) else default

    base = {
        "n_resi": int(n),
        "n_hari_data": int(days),
        "resi_per_hari": round(n / days, 1),
        "avg_ongkir": _mean("ongkir", default=config.DEFAULTS["ongkir_per_resi"]),
        "avg_total_biaya": _mean("total_biaya", default=config.DEFAULTS["ongkir_per_resi"]),
        "avg_nilai_produk": _mean("nilai_produk", default=config.DEFAULTS["nilai_produk"]),
        "avg_proyeksi_net": _mean("proyeksi_net", default=100_000),
        "avg_nilai_cod": _mean("nilai_cod", cod_mask, default=145_000),
        "avg_cod_fee": _mean("cod_fee", cod_mask, default=0),
        "avg_durasi": _mean("durasi_kirim", default=config.DEFAULTS["avg_durasi"]),
        "success_rate": round(sampai / n, 4) if n else config.DEFAULTS["success_rate"],
        "pct_cod": round(float(cod_mask.mean()), 4) if n else config.DEFAULTS["pct_cod"],
    }
    # Cashback ongkir (Biaya Diskon) sbg % dari Total Biaya/ongkir -> bobot total
    sum_disk = df["biaya_diskon"].sum() if "biaya_diskon" in df else 0
    sum_biaya = df["total_biaya"].sum() if "total_biaya" in df else 0
    base["avg_cashback"] = _mean("biaya_diskon", default=config.DEFAULTS["cashback_ongkir"])
    base["cashback_pct"] = round(sum_disk / sum_biaya, 4) if sum_biaya else config.DEFAULTS["cashback_pct"]
    # cod fee rate efektif (terhadap Nilai COD)
    base["cod_fee_rate"] = round(base["avg_cod_fee"] / base["avg_nilai_cod"], 4) \
        if base["avg_nilai_cod"] else config.DEFAULTS["cod_fee_rate"]
    return base


def durasi_by_region(df: pd.DataFrame, level: str = "provinsi") -> pd.DataFrame:
    """Rata-rata durasi & SLA per provinsi/kota."""
    if level not in df:
        return pd.DataFrame()
    g = (df.groupby(level)
           .agg(avg_durasi=("durasi_kirim", "mean"),
                resi=("waybill", "count"),
                sampai=("is_sampai", "sum"))
           .reset_index())
    g["sla"] = (g["sampai"] / g["resi"] * 100).round(1)
    g["avg_durasi"] = g["avg_durasi"].round(1)
    return g.sort_values("resi", ascending=False)


def receive_distribution(df: pd.DataFrame) -> pd.Series:
    """Distribusi probabilitas jeda (hari) antara kirim dan diterima."""
    if "durasi_kirim" not in df:
        return pd.Series(dtype=float)
    d = df["durasi_kirim"].dropna()
    d = d[(d >= 0) & (d <= 60)].round().astype(int)
    if d.empty:
        return pd.Series(dtype=float)
    return (d.value_counts(normalize=True).sort_index())


def forecast_daily_volume(df: pd.DataFrame, horizon: int = 30) -> pd.DataFrame:
    """
    Forecast jumlah resi harian untuk `horizon` hari ke depan.
    Memakai regresi linear (tren) + faktor musiman hari-dalam-minggu.
    """
    if "tgl_kirim" not in df or df["tgl_kirim"].notna().sum() == 0:
        return pd.DataFrame(columns=["tanggal", "resi_forecast"])

    daily = (df.dropna(subset=["tgl_kirim"])
               .groupby(df["tgl_kirim"].dt.normalize())
               .size().rename("resi").reset_index())
    daily.columns = ["tanggal", "resi"]
    daily = daily.sort_values("tanggal").reset_index(drop=True)

    if len(daily) < 3:
        avg = daily["resi"].mean() if len(daily) else config.DEFAULTS["budget_iklan"]
        future = pd.date_range(daily["tanggal"].max() + pd.Timedelta(days=1),
                               periods=horizon) if len(daily) else \
            pd.date_range(pd.Timestamp.today().normalize(), periods=horizon)
        return pd.DataFrame({"tanggal": future, "resi_forecast": round(avg or 0)})

    daily["t"] = (daily["tanggal"] - daily["tanggal"].min()).dt.days
    daily["dow"] = daily["tanggal"].dt.weekday

    # faktor musiman per hari
    seas = daily.groupby("dow")["resi"].mean()
    seas = (seas / seas.mean()).to_dict()

    if _HAS_SK:
        model = LinearRegression().fit(daily[["t"]], daily["resi"])
        slope, intercept = float(model.coef_[0]), float(model.intercept_)
    else:
        slope, intercept = np.polyfit(daily["t"], daily["resi"], 1)

    last_t = daily["t"].max()
    last_date = daily["tanggal"].max()
    rows = []
    for i in range(1, horizon + 1):
        t = last_t + i
        date = last_date + pd.Timedelta(days=i)
        trend = max(slope * t + intercept, 0)
        val = trend * seas.get(date.weekday(), 1.0)
        rows.append((date, max(round(val), 0)))
    return pd.DataFrame(rows, columns=["tanggal", "resi_forecast"])
