# -*- coding: utf-8 -*-
"""
geography_engine.py
===================
Agregasi performa wilayah (provinsi & kota) + penyediaan koordinat untuk peta.

Peta default: bubble/scatter map OFFLINE memakai centroid provinsi
(assets/province_centroids.py). Bila tersedia file
'assets/indonesia-provinces.geojson', dapat dipakai untuk choropleth.
"""

from __future__ import annotations
import os
import json
import pandas as pd

import config

try:
    from assets.province_centroids import PROVINCE_CENTROIDS
except Exception:  # pragma: no cover
    import importlib.util
    _p = os.path.join(config.ASSETS_DIR, "province_centroids.py")
    _spec = importlib.util.spec_from_file_location("province_centroids", _p)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    PROVINCE_CENTROIDS = _mod.PROVINCE_CENTROIDS


def province_summary(df: pd.DataFrame) -> pd.DataFrame:
    if "provinsi" not in df:
        return pd.DataFrame()
    _ret = ("is_retur", "sum") if "is_retur" in df else ("is_sampai", "size")
    _ong = ("ongkir", "mean") if "ongkir" in df else ("proyeksi_net", "mean")
    _cbk = ("biaya_diskon", "mean") if "biaya_diskon" in df else ("proyeksi_net", "mean")
    g = (df.groupby("provinsi")
           .agg(resi=("waybill", "count"),
                proyeksi_net=("proyeksi_net", "sum"),
                avg_durasi=("durasi_kirim", "mean"),
                sampai=("is_sampai", "sum"),
                retur=_ret,
                avg_ongkir=_ong,
                avg_cashback=_cbk,
                nilai_cod=("nilai_cod", "sum"))
           .reset_index())
    if "is_retur" not in df:
        g["retur"] = 0
    g["belum_sampai"] = g["resi"] - g["sampai"]
    g["sla"] = (g["sampai"] / g["resi"] * 100).round(1)
    g["retur_pct"] = (g["retur"] / g["resi"] * 100).round(1)
    g["avg_durasi"] = g["avg_durasi"].round(1)
    g["avg_ongkir"] = g["avg_ongkir"].round(0)
    g["avg_cashback"] = g["avg_cashback"].round(0)
    # outstanding = nilai COD paket belum sampai (perkiraan)
    out = (df[~df["is_sampai"]].groupby("provinsi")["nilai_cod"].sum()
           if "is_cod" in df else pd.Series(dtype=float))
    g["outstanding"] = g["provinsi"].map(out).fillna(0)
    g["lat"] = g["provinsi"].map(lambda p: PROVINCE_CENTROIDS.get(p, (None, None))[0])
    g["lon"] = g["provinsi"].map(lambda p: PROVINCE_CENTROIDS.get(p, (None, None))[1])
    return g.sort_values("resi", ascending=False).reset_index(drop=True)


def city_summary(df: pd.DataFrame, provinsi: str | None = None) -> pd.DataFrame:
    if "kota" not in df:
        return pd.DataFrame()
    d = df if not provinsi else df[df["provinsi"] == provinsi]
    _ret = ("is_retur", "sum") if "is_retur" in df else ("is_sampai", "size")
    g = (d.groupby(["provinsi", "kota"])
           .agg(resi=("waybill", "count"),
                proyeksi_net=("proyeksi_net", "sum"),
                avg_durasi=("durasi_kirim", "mean"),
                sampai=("is_sampai", "sum"),
                retur=_ret,
                nilai_cod=("nilai_cod", "sum"))
           .reset_index())
    if "is_retur" not in df:
        g["retur"] = 0
    g["belum_sampai"] = g["resi"] - g["sampai"]
    g["sla"] = (g["sampai"] / g["resi"] * 100).round(1)
    g["retur_pct"] = (g["retur"] / g["resi"] * 100).round(1)
    g["avg_durasi"] = g["avg_durasi"].round(1)
    return g.sort_values("resi", ascending=False).reset_index(drop=True)


def province_detail(df: pd.DataFrame, provinsi: str) -> dict:
    d = df[df["provinsi"] == provinsi]
    if d.empty:
        return {}
    top_city = (d["kota"].value_counts().head(1).index[0]
                if "kota" in d and not d["kota"].dropna().empty else "-")
    return {
        "provinsi": provinsi,
        "resi": len(d),
        "proyeksi_net": float(d["proyeksi_net"].sum()),
        "avg_durasi": round(float(d["durasi_kirim"].mean()), 1) if d["durasi_kirim"].notna().any() else None,
        "sampai": int(d["is_sampai"].sum()),
        "belum_sampai": int((~d["is_sampai"]).sum()),
        "retur": int(d["is_retur"].sum()) if "is_retur" in d else 0,
        "retur_pct": round(d["is_retur"].mean() * 100, 1) if "is_retur" in d else 0.0,
        "avg_ongkir": round(float(d["ongkir"].mean()), 0) if "ongkir" in d else 0.0,
        "avg_cashback": round(float(d["biaya_diskon"].mean()), 0) if "biaya_diskon" in d else 0.0,
        "outstanding": float(d.loc[~d["is_sampai"], "nilai_cod"].sum()),
        "top_kota": top_city,
        "sla": round(d["is_sampai"].mean() * 100, 1),
    }


def load_geojson() -> dict | None:
    """Muat geojson provinsi bila tersedia (untuk choropleth opsional)."""
    path = os.path.join(config.ASSETS_DIR, "indonesia-provinces.geojson")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
