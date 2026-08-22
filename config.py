# -*- coding: utf-8 -*-
"""
config.py
=========
Pusat konfigurasi untuk J&T Business Intelligence Dashboard.

Semua konstanta (path file, nama sheet, pemetaan kolom, aturan settlement,
tema warna, dan asumsi default) dikumpulkan di sini agar mudah dipelihara dan
diperluas untuk ekspedisi lain di masa depan.
"""

from __future__ import annotations
import os

# ---------------------------------------------------------------------------
# PATH & FILE
# ---------------------------------------------------------------------------
# Direktori root project = lokasi file config.py ini
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folder data sumber. Bisa diperluas: tambahkan ekspedisi lain di EXPEDITIONS.
DATA_DIR = os.path.join(BASE_DIR, "JnT")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Nama file Excel yang dibaca otomatis (tanpa upload manual).
EXCEL_FILENAME = "jnt_recap.xlsx"

# Pola pencarian fallback bila nama persis tidak ditemukan.
EXCEL_GLOB_PATTERNS = ["jnt_recap*.xlsx", "*recap*.xlsx", "*.xlsx"]

# Nama sheet di dalam workbook.
SHEET_ALL_RESI = "all_resi"
SHEET_SETTLE = "settle_reconcile"      # ejaan asli pada file
SHEET_SETTLE_ALT = "settle_reconsile"  # ejaan alternatif sesuai brief
SHEET_PROBLEM = "problem"

# ---------------------------------------------------------------------------
# SUMBER DATA  ("excel" = file lokal | "gsheet" = Google Sheet)
# ---------------------------------------------------------------------------
DATA_SOURCE = "gsheet"         # SUMBER UTAMA: Google Sheet live

# Mode koneksi GSheet:
#   "oauth"  = baca sheet LANGSUNG sebagai akun Google Anda (login sekali via
#              browser). Dipakai karena org memblokir web app publik & SA key.
#   "webapp" = via Apps Script Web App (butuh deployment 'Anyone' — DIBLOKIR org).
GSHEET_MODE = "oauth"

# --- Mode OAUTH (baca langsung) ---
GSHEET_ID = ""                                     # ID spreadsheet (URL /d/<ID>/edit)
GSHEET_TAB_ALL_RESI = "All Resi"                   # nama TAB di GSheet
GSHEET_TAB_SETTLE = "Settle Reconcile"
GSHEET_TAB_PROBLEM = "Laporan Paket Tertunda"
# Sheet admin (importrange): order & stok. Coba beberapa kemungkinan nama tab.
GSHEET_TAB_ORDER = ["Import-Order", "ORDERS", "Orders", "Order", "Import Order"]
GSHEET_TAB_STOCK = ["Import-Stock", "STOK", "Stok", "Stock", "Import Stock"]
GSHEET_TAB_OO = ["OrderOnline", "Order Online", "ORDERONLINE", "OO"]
GSHEET_TAB_REF = ["Impor-RefProduk", "Import-RefProduk", "RefProduk", "Ref Produk"]
GSHEET_TAB_META = ["Meta-Ads", "Meta Ads", "MetaAds"]        # data iklan Meta (Modul 5)
GSHEET_OAUTH_CRED = os.path.join(BASE_DIR, "credentials", "oauth_client.json")
GSHEET_OAUTH_TOKEN = os.path.join(BASE_DIR, "credentials", "authorized_user.json")
# Untuk DEPLOY headless (Streamlit Cloud): isi via st.secrets (bukan file).
# dict isi oauth_client.json & authorized_user.json. Bila keduanya terisi,
# loader pakai gspread.oauth_from_dict (tanpa browser).
GSHEET_OAUTH_CLIENT_INFO = None
GSHEET_OAUTH_AUTHORIZED_INFO = None

# --- Mode WEBAPP (tidak dipakai; kosong — isi via secrets_local.py bila perlu) ---
GSHEET_WEBAPP_URL = ""
GSHEET_TOKEN = ""

# Override rahasia dari file lokal (secrets_local.py) yang TIDAK ikut ke git.
try:
    from secrets_local import *  # noqa: F401,F403
except Exception:
    pass

# Boleh juga lewat environment variable (mis. server / Streamlit Cloud).
DATA_SOURCE = os.environ.get("DATA_SOURCE", DATA_SOURCE)
GSHEET_MODE = os.environ.get("GSHEET_MODE", GSHEET_MODE)
GSHEET_ID = os.environ.get("GSHEET_ID", GSHEET_ID)
GSHEET_WEBAPP_URL = os.environ.get("GSHEET_WEBAPP_URL", GSHEET_WEBAPP_URL)
GSHEET_TOKEN = os.environ.get("GSHEET_TOKEN", GSHEET_TOKEN)

# ---------------------------------------------------------------------------
# PEMETAAN KOLOM (nama asli di Excel -> nama kanonik internal)
# ---------------------------------------------------------------------------
# Dengan memetakan ke nama kanonik, modul lain tidak bergantung pada ejaan
# kolom Excel. Bila ekspedisi lain memakai nama berbeda, cukup ubah di sini.
COLMAP_ALL_RESI = {
    "No. Waybill": "waybill",
    "Tanggal Pengiriman": "tgl_kirim",
    "Provinsi Penerima": "provinsi",
    "Kota Penerima": "kota",
    "Kecamatan Penerima": "kecamatan",
    "Nama Barang": "nama_barang",
    "Kategori Barang": "kategori_barang",
    "Layanan": "layanan",
    "Metode Pembayaran": "metode_bayar",
    "Berat": "berat",
    "Biaya Kirim": "ongkir",
    "Total Biaya": "total_biaya",
    "Biaya Diskon": "biaya_diskon",
    "Nilai Voucher": "voucher",
    "Nilai COD": "nilai_cod",
    "COD Fee": "cod_fee",
    "COD": "tipe_cod",                 # 'COD' / 'NONCOD'
    "Nilai Produk": "nilai_produk",
    "Rekon": "rekon",                  # 'Recon' / '-'
    "Proyeksi_Net": "proyeksi_net",
    "Durasi Kirim": "durasi_kirim",
    "Waktu Terima": "waktu_terima",
    "Tanda TTD": "status_ttd",         # 'Sampai Tujuan' / 'Belum Diterima'
    "Apakah Paket Abnormal?": "abnormal",
    "Keterangan": "keterangan",
}

COLMAP_SETTLE = {
    "No. Waybill": "waybill",
    "Waktu TTD": "waktu_ttd",
    "TTD": "ttd",
    "Status Retur": "status_retur",
    "COD": "nilai_cod",
    "Jenis Layanan": "layanan",
    "Lokasi (Asal)": "asal",
    "Tujuan": "tujuan",
}

# Nilai kategori yang dianggap "paket sampai / berhasil".
STATUS_SAMPAI = "Sampai Tujuan"
STATUS_BELUM = "Belum Diterima"
REKON_DONE = "Recon"          # sudah direkonsiliasi -> dasar pencairan
TIPE_COD = "COD"
TIPE_NONCOD = "NONCOD"

# ---------------------------------------------------------------------------
# ASUMSI DEFAULT SIMULATOR (dipakai bila histori tidak tersedia)
# Nilai sebenarnya akan dihitung ulang dari data oleh forecasting.py
# ---------------------------------------------------------------------------
DEFAULTS = {
    "modal_awal": 200_000_000,    # modal awal / kas awal yang disiapkan (Rp)
    "budget_iklan": 100_000_000,  # total (otomatis = budget_harian x horizon)
    "budget_harian": 3_000_000,   # budget iklan per hari (Rp)
    "n_cs": 3,                    # jumlah customer service default
    "hpp_ratio": 0.40,            # default HPP = 40% dari Nilai Produk
    "cpl": 8_000,                 # Cost per lead (Rp)
    "closing_rate": 0.30,         # % lead -> order
    "success_rate": 0.85,         # % resi terkirim
    "ongkir_per_resi": 65_000,
    "nilai_produk": 80_000,       # rata-rata nilai produk (Rp)
    "cashback_ongkir": 0,         # rata-rata cashback ongkir nominal (Rp)
    "cashback_pct": 0.41,         # cashback ongkir = % dari Total Biaya (omzet)
    "cod_fee_rate": 0.015,        # 1.5% dari nilai COD (pola J&T)
    "pct_cod": 0.65,              # 65% order COD
    "horizon_days": 30,
    "avg_durasi": 7,
    "opex_fix_bulan": 0,          # opex TETAP/bulan (gaji, sewa) — lump saat gajian
    "opex_var_resi": 0,           # opex VARIABEL per resi (packing, petty cash)
    "payday": 25,                 # tanggal gajian (hari dalam bulan) utk opex tetap
}

# Auto-plotting budget iklan & CPL per produk (dari data order/stok)
CPL_MIN = 9_000               # CPL realistis minimum (Rp/lead)
CPL_MAX = 25_000              # CPL realistis maksimum (Rp/lead)
CPL_TARGET_FRAC = 0.5         # CPL disetel = breakeven CPL x fraksi ini (ROAS ~2x)
BUDGET_MIN_PRODUK = 100_000   # budget iklan minimum per produk profitabel (Rp/hari)
BUDGET_MIN_MAXFLOOR = 300_000 # batas atas rentang "minimum default" (Rp/hari)
BUDGET_MAX_PRODUK = 3_000_000 # budget iklan maksimum per produk (CM terbaik) (Rp/hari)

HORIZON_OPTIONS = [7, 14, 30, 60, 90]

# ---------------------------------------------------------------------------
# ATURAN SETTLEMENT / PENCAIRAN
# ---------------------------------------------------------------------------
# Skema Baru: cair H+1 hari kerja setelah paket DITERIMA (mis. diterima Kamis
# -> cair Jumat; diterima Jumat -> cair Senin; diterima Senin -> cair Selasa).
SETTLE_DAILY_LAG_DEFAULT = 1  # hari kerja setelah paket diterima (H+1)

# Mode 2 (default): cair Senin / Selasa / Kamis.
# Mapping: hari paket DITERIMA (weekday Python: Mon=0..Sun=6) -> hari CAIR.
# - Cair Senin  : paket diterima Rabu, Kamis (minggu sebelumnya)
# - Cair Selasa : paket diterima Jumat, Sabtu, Minggu
# - Cair Kamis  : paket diterima Senin, Selasa
SETTLE_MODE2_RECEIVE_TO_PAYOUT = {
    2: "Senin",    # Rabu
    3: "Senin",    # Kamis
    4: "Selasa",   # Jumat
    5: "Selasa",   # Sabtu
    6: "Selasa",   # Minggu
    0: "Kamis",    # Senin
    1: "Kamis",    # Selasa
}
PAYOUT_WEEKDAY = {"Senin": 0, "Selasa": 1, "Rabu": 2, "Kamis": 3,
                  "Jumat": 4, "Sabtu": 5, "Minggu": 6}

SETTLE_MODES = {
    "Skema Lama — Cair Senin/Selasa/Kamis": "mode2",
    "Skema Baru — Cair H+1 Hari Kerja": "mode1",
}

# Aturan ongkir retur J&T: gratis bila persentase retur <= ambang; jika melebihi,
# biaya = (retur% − ambang) × total ongkir PENUH (tanpa diskon) dari paket retur.
RETUR_FREE_THRESHOLD = 0.20  # 20%

# Rekomendasi standar performa wilayah (default; bisa disesuaikan di dashboard).
# Retur maks 20% selaras dengan ambang GRATIS ongkir retur J&T — di atasnya mulai
# kena biaya. Sampai min 60% = batas sehat agar mayoritas order menghasilkan kas.
TARGET_SAMPAI_MIN = 60   # % paket sampai minimal (rekomendasi)
TARGET_RETUR_MAX = 20    # % retur maksimal (rekomendasi)

# ---------------------------------------------------------------------------
# TEMA VISUAL (Dark, dominan biru-hijau, ala Power BI / Tableau)
# ---------------------------------------------------------------------------
THEME = {
    "bg": "#0E1117",
    "panel": "#161B26",
    "card": "#1C2333",
    "grid": "#2A3142",
    "text": "#E6EDF3",
    "muted": "#8B98A9",
    "blue": "#2E8BFF",
    "blue_soft": "#5AA9FF",
    "green": "#19C37D",
    "green_soft": "#4FD89E",
    "teal": "#16C2C2",
    "amber": "#F5A623",
    "red": "#FF5C5C",
    "purple": "#9B7BFF",
}

# Skala warna kontinu (rendah -> tinggi): MERAH -> KUNING -> HIJAU.
# Untuk metrik "makin tinggi makin baik" (resi, net): hijau = tinggi.
# Untuk metrik "makin tinggi makin buruk" (retur, durasi): pakai reversescale.
COLORSCALE = [
    [0.0, "#FF5C5C"],   # merah  (rendah / buruk)
    [0.5, "#F5C542"],   # kuning (menengah)
    [1.0, "#19C37D"],   # hijau  (tinggi / baik)
]

CATEGORICAL_COLORS = ["#2E8BFF", "#19C37D", "#16C2C2", "#9B7BFF",
                      "#F5A623", "#FF5C5C", "#5AA9FF", "#4FD89E"]

APP_TITLE = "J&T Business Intelligence Dashboard"
COMPANY = "Meika Berkarya"
