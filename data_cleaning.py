# -*- coding: utf-8 -*-
"""
data_cleaning.py
================
Membersihkan & menstandarkan data mentah:
 - rename kolom Excel -> nama kanonik (lihat config.COLMAP_*)
 - parsing tanggal
 - konversi numerik (buang pemisah ribuan, simbol)
 - normalisasi teks (provinsi, kota, status)
 - kolom turunan (flag sampai, flag rekon, hari kirim/terima, lead time)
"""

from __future__ import annotations
import numpy as np
import pandas as pd

import config

HARI_ID = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
           4: "Jumat", 5: "Sabtu", 6: "Minggu"}


def _to_numeric(s: pd.Series) -> pd.Series:
    if s.dtype.kind in "if":
        return s.astype(float)
    cleaned = (
        s.astype(str)
        .str.replace(r"[^\d,.\-]", "", regex=True)
        .str.replace(".", "", regex=False)   # pemisah ribuan ID
        .str.replace(",", ".", regex=False)  # desimal ID
        .replace({"": np.nan, "-": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _norm_text(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .replace({"nan": np.nan, "None": np.nan, "": np.nan})
    )


def clean_all_resi(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.rename(columns=config.COLMAP_ALL_RESI).copy()

    # ---- tanggal ----
    for c in ["tgl_kirim", "waktu_terima"]:
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # ---- numerik ----
    for c in ["ongkir", "total_biaya", "biaya_diskon", "voucher", "nilai_cod",
              "cod_fee", "nilai_produk", "proyeksi_net", "durasi_kirim", "berat"]:
        if c in df:
            df[c] = _to_numeric(df[c])

    # ---- teks/kategori ----
    for c in ["provinsi", "kota", "kecamatan", "layanan", "metode_bayar",
              "tipe_cod", "rekon", "status_ttd", "abnormal"]:
        if c in df:
            df[c] = _norm_text(df[c])

    # standarkan ejaan provinsi agar cocok dengan tabel centroid
    if "provinsi" in df:
        df["provinsi"] = df["provinsi"].map(_std_provinsi).fillna(df["provinsi"])

    # ---- flag turunan ----
    df["is_sampai"] = df.get("status_ttd").eq(config.STATUS_SAMPAI) if "status_ttd" in df else False
    df["is_cod"] = df.get("tipe_cod").eq(config.TIPE_COD) if "tipe_cod" in df else True
    df["is_recon"] = df.get("rekon").eq(config.REKON_DONE) if "rekon" in df else False

    # durasi: bila kosong tapi ada kedua tanggal, hitung selisih
    if "durasi_kirim" in df and {"tgl_kirim", "waktu_terima"}.issubset(df.columns):
        calc = (df["waktu_terima"] - df["tgl_kirim"]).dt.days
        df["durasi_kirim"] = df["durasi_kirim"].fillna(calc)
    df.loc[df["durasi_kirim"] < 0, "durasi_kirim"] = np.nan

    # hari (nama) kirim & terima
    if "tgl_kirim" in df:
        df["hari_kirim"] = df["tgl_kirim"].dt.weekday.map(HARI_ID)
    if "waktu_terima" in df:
        df["hari_terima"] = df["waktu_terima"].dt.weekday.map(HARI_ID)

    # proyeksi net fallback
    if "proyeksi_net" not in df or df["proyeksi_net"].isna().all():
        df["proyeksi_net"] = df.get("nilai_produk", 0)

    return df


def clean_settle(df_raw: pd.DataFrame | None) -> pd.DataFrame | None:
    if df_raw is None:
        return None
    df = df_raw.rename(columns=config.COLMAP_SETTLE).copy()
    if "waktu_ttd" in df:
        df["waktu_ttd"] = pd.to_datetime(df["waktu_ttd"], errors="coerce")
    if "nilai_cod" in df:
        df["nilai_cod"] = _to_numeric(df["nilai_cod"])
    for c in ["status_retur", "ttd", "asal", "tujuan", "layanan"]:
        if c in df:
            df[c] = _norm_text(df[c])
    return df


# --- normalisasi nama provinsi ke bentuk baku ---
_PROV_ALIAS = {
    "di yogyakarta": "Daerah Istimewa Yogyakarta",
    "diy": "Daerah Istimewa Yogyakarta",
    "yogyakarta": "Daerah Istimewa Yogyakarta",
    "dki": "DKI Jakarta",
    "jakarta": "DKI Jakarta",
    "kep. bangka belitung": "Kepulauan Bangka Belitung",
    "bangka belitung": "Kepulauan Bangka Belitung",
    "kep. riau": "Kepulauan Riau",
}


def _std_provinsi(v):
    if not isinstance(v, str):
        return v
    key = v.strip().lower()
    return _PROV_ALIAS.get(key, v.strip())


def clean_all(raw: dict) -> dict:
    """Bersihkan seluruh workbook sekaligus."""
    return {
        "all_resi": clean_all_resi(raw["all_resi"]),
        "settle": clean_settle(raw.get("settle")),
        "problem": raw.get("problem"),
        "path": raw.get("path"),
        "mtime": raw.get("mtime"),
    }
