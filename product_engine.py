# -*- coding: utf-8 -*-
"""
product_engine.py
=================
Modul 3 — Analisis Produk.

Mengolah kolom 'Nama Barang' (produk) menjadi metrik keputusan:
winning product, kontribusi margin, AOV, SLA per produk, analisis Pareto,
dan kuadran volume vs margin (bintang / sapi perah / pertanyaan).

HPP per produk diterima sebagai parameter (rata-rata) sehingga margin & net
menjadi "real": Net Real = Proyeksi Net - HPP, Margin Produk = Nilai Produk - HPP.
"""

from __future__ import annotations
import re
import numpy as np
import pandas as pd

# pola pembersih nama produk agar varian "Beli 1 / Gratis 1 / 1 Pcs / (BLACK)"
# tergabung ke produk inti.
_CLEAN_PATTERNS = [
    r"\bbeli\s*\d+\b", r"\bgratis\s*\d+\b", r"\bdapat\s*\d+\b",
    r"\b\d+\s*(pcs|set|paket|pack|buah|lusin)\b", r"\bbonus\b.*",
    r"\(.*?\)", r"\b1\s*set\b", r"\bfree\b", r"\bpromo\b",
]


def clean_product_name(name: str) -> str:
    if not isinstance(name, str):
        return "(Tidak Diketahui)"
    s = name.lower()
    for pat in _CLEAN_PATTERNS:
        s = re.sub(pat, " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.title() if s else name.strip().title()


def product_summary(df: pd.DataFrame, hpp: float = 0.0,
                    hpp_map: dict | None = None,
                    use_clean: bool = True) -> pd.DataFrame:
    """
    Ringkasan per produk dari data historis.

    hpp     : HPP default (dipakai jika produk tidak ada di hpp_map).
    hpp_map : dict {nama_produk: hpp} untuk HPP berbeda tiap produk.

    Kolom kunci:
      margin_jual      = Nilai Produk - HPP  (margin kotor jual, BELUM termasuk iklan)
      net_real         = Proyeksi Net - HPP  (setelah cashback & COD fee, belum iklan)
    """
    if "nama_barang" not in df.columns and "Nama Barang" in df.columns:
        df = df.rename(columns={"Nama Barang": "nama_barang"})
    if "nama_barang" not in df.columns:
        return pd.DataFrame()

    d = df.copy()
    d["produk"] = (d["nama_barang"].map(clean_product_name)
                   if use_clean else d["nama_barang"])
    hpp_map = hpp_map or {}
    d["hpp_row"] = d["produk"].map(hpp_map).fillna(hpp).astype(float)
    d["net_real_row"] = d["proyeksi_net"].fillna(0) - d["hpp_row"]
    d["margin_jual_row"] = d["nilai_produk"].fillna(0) - d["hpp_row"]

    g = (d.groupby("produk")
           .agg(resi=("waybill", "count"),
                revenue=("nilai_produk", "sum"),
                hpp_total=("hpp_row", "sum"),
                net_real=("net_real_row", "sum"),
                margin_jual=("margin_jual_row", "sum"),
                sampai=("is_sampai", "sum"),
                retur=(("is_retur", "sum") if "is_retur" in d else ("is_sampai", "size")),
                cod=("is_cod", "sum"),
                avg_durasi=("durasi_kirim", "mean"))
           .reset_index())
    if "is_retur" not in d:
        g["retur"] = 0

    g["aov"] = (g["revenue"] / g["resi"]).round(0)
    g["hpp_per_resi"] = (g["hpp_total"] / g["resi"]).round(0)
    g["margin_jual_per_resi"] = (g["margin_jual"] / g["resi"]).round(0)
    g["margin_per_resi"] = (g["net_real"] / g["resi"]).round(0)
    g["margin_pct"] = (g["margin_jual"] / g["revenue"] * 100).round(1)
    g["sla"] = (g["sampai"] / g["resi"] * 100).round(1)
    g["retur_pct"] = (g["retur"] / g["resi"] * 100).round(1)
    g["cod_pct"] = (g["cod"] / g["resi"] * 100).round(1)
    g["avg_durasi"] = g["avg_durasi"].round(1)

    total_net = g["net_real"].sum()
    g["kontribusi_pct"] = (g["net_real"] / total_net * 100).round(2) if total_net else 0
    g = g.sort_values("net_real", ascending=False).reset_index(drop=True)
    g["kontribusi_kumulatif"] = g["kontribusi_pct"].cumsum().round(1)
    return g


def seed_product_table(df: pd.DataFrame, top_n: int = 25,
                       total_budget_harian: float = 3_000_000,
                       default_cpl: int = 8000,
                       hpp_ratio: float = 0.40,
                       use_clean: bool = True) -> pd.DataFrame:
    """
    Bangun tabel perencanaan per produk (default dari histori), siap diedit:
      Produk | Budget/Hari | CPL | Nilai Produk | HPP
    Budget/Hari dialokasikan proporsional terhadap jumlah resi historis.
    """
    base = product_summary(df, hpp=0, use_clean=use_clean)
    if base.empty:
        return pd.DataFrame(columns=["Produk", "Budget/Hari",
                                     "CPL", "Nilai Produk", "HPP"])
    base = base.nlargest(top_n, "resi").reset_index(drop=True)
    share = base["resi"] / base["resi"].sum()
    nilai_produk = (base["aov"]).round(0)
    out = pd.DataFrame({
        "Produk": base["produk"],
        "Budget/Hari": (share * total_budget_harian).round(-3).astype(int),
        "CPL": int(default_cpl),
        "Nilai Produk": nilai_produk.astype(int),
        "HPP": (nilai_produk * hpp_ratio).round(-2).astype(int),
    })
    return out


def pareto_threshold(prod: pd.DataFrame, pct: float = 80.0) -> dict:
    """Jumlah produk yang menyumbang `pct`% net (prinsip Pareto)."""
    if prod.empty:
        return {}
    n_at = int((prod["kontribusi_kumulatif"] <= pct).sum()) + 1
    n_at = min(n_at, len(prod))
    return {
        "n_produk_total": len(prod),
        "n_produk_inti": n_at,
        "pct": pct,
        "share_produk": round(n_at / len(prod) * 100, 1),
    }


def quadrant(prod: pd.DataFrame) -> pd.DataFrame:
    """Klasifikasi kuadran berdasarkan volume (resi) & margin/resi (median split)."""
    if prod.empty:
        return prod
    d = prod.copy()
    vol_med = d["resi"].median()
    mar_med = d["margin_per_resi"].median()

    def _lab(r):
        hv, hm = r["resi"] >= vol_med, r["margin_per_resi"] >= mar_med
        if hv and hm:
            return "⭐ Winning (Volume & Margin Tinggi)"
        if hv and not hm:
            return "🐄 Volume Tinggi, Margin Tipis"
        if not hv and hm:
            return "💎 Margin Tinggi, Volume Rendah"
        return "❓ Volume & Margin Rendah"

    d["kuadran"] = d.apply(_lab, axis=1)
    return d
