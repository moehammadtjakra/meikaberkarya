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

    # Jaminan kolom: sumber GSheet mungkin tak punya sebagian kolom turunan Excel
    # (mis. 'rekon'). Pastikan ada agar tidak KeyError di hilir; isi NaN = default aman.
    for c in ["provinsi", "kota", "kecamatan", "layanan", "metode_bayar", "tipe_cod",
              "rekon", "status_ttd", "abnormal", "nama_barang", "kategori_barang"]:
        if c not in df.columns:
            df[c] = np.nan
    for c in ["ongkir", "total_biaya", "biaya_diskon", "voucher", "nilai_cod",
              "cod_fee", "nilai_produk", "berat"]:
        if c not in df.columns:
            df[c] = np.nan

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
    # RETUR / bermasalah: status "Belum Diterima" TAPI sudah ada tanggal Waktu Terima
    # (ada upaya antar tapi tidak diterima → dikembalikan). Berbeda dari "masih transit".
    if {"status_ttd", "waktu_terima"}.issubset(df.columns):
        df["is_retur"] = df["status_ttd"].eq(config.STATUS_BELUM) & df["waktu_terima"].notna()
        df["in_transit"] = df["status_ttd"].eq(config.STATUS_BELUM) & df["waktu_terima"].isna()
    else:
        df["is_retur"] = False
        df["in_transit"] = False

    # durasi kirim: bila kolom tidak ada / kosong, hitung dari (waktu_terima − tgl_kirim).
    # Penting untuk sumber GSheet yang tidak menyimpan kolom turunan "Durasi Kirim".
    if {"tgl_kirim", "waktu_terima"}.issubset(df.columns):
        calc = (df["waktu_terima"] - df["tgl_kirim"]).dt.days
        df["durasi_kirim"] = (df["durasi_kirim"].fillna(calc)
                              if "durasi_kirim" in df else calc)
    if "durasi_kirim" not in df.columns:
        df["durasi_kirim"] = np.nan
    df.loc[df["durasi_kirim"] < 0, "durasi_kirim"] = np.nan

    # hari (nama) kirim & terima
    if "tgl_kirim" in df:
        df["hari_kirim"] = df["tgl_kirim"].dt.weekday.map(HARI_ID)
    if "waktu_terima" in df:
        df["hari_terima"] = df["waktu_terima"].dt.weekday.map(HARI_ID)

    # Proyeksi Net: bila kolom belum ada (data GSheet tanpa kolom turunan),
    # hitung dgn rumus tervalidasi = Nilai Produk + Biaya Diskon (cashback) − COD Fee.
    if "proyeksi_net" not in df.columns or df["proyeksi_net"].isna().all():
        _np = pd.to_numeric(df["nilai_produk"], errors="coerce").fillna(0) if "nilai_produk" in df else 0
        _bd = pd.to_numeric(df["biaya_diskon"], errors="coerce").fillna(0) if "biaya_diskon" in df else 0
        _cf = pd.to_numeric(df["cod_fee"], errors="coerce").fillna(0) if "cod_fee" in df else 0
        df["proyeksi_net"] = _np + _bd - _cf

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
        "order": raw.get("order"),      # sheet Import-Order (admin) — mentah
        "stock": raw.get("stock"),      # sheet Import-Stock (admin) — mentah
        "oo": raw.get("oo"),            # sheet OrderOnline (leads) — mentah
        "ref": raw.get("ref"),          # sheet Impor-RefProduk (mapping) — mentah
        "path": raw.get("path"),
        "mtime": raw.get("mtime"),
    }
