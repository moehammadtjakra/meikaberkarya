# -*- coding: utf-8 -*-
"""
dashboard.py
============
Antarmuka utama (Streamlit) J&T Business Intelligence Dashboard.

Dijalankan oleh run_dashboard.py / start.bat. Saat dibuka, otomatis:
membaca Excel terbaru -> membersihkan -> menghitung baseline & forecast ->
menampilkan KPI, Simulator Cashflow (Modul 1), dan Analisis Wilayah (Modul 2).
"""

from __future__ import annotations
import os
import sys
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import data_loader
import data_cleaning
import forecasting
import cashflow_engine as ce
import geography_engine as geo
import product_engine as prodeng
import product_admin as padmin
import meta_engine as meng
import planning
import target_engine as te
import daily_engine as de
import visualization as viz
import insights
import formatting as fmt
import numpy as np

T = config.THEME

# ----------------------------------------------------------------- PAGE/THEME
st.set_page_config(page_title=config.APP_TITLE, page_icon="📦",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown(f"""
<style>
:root {{ --blue:{T['blue']}; --green:{T['green']}; }}
.stApp {{ background:{T['bg']}; color:{T['text']}; }}
section[data-testid="stSidebar"] {{ background:{T['panel']}; }}
.block-container {{ padding-top:4.2rem; padding-bottom:2rem; max-width:1500px; }}
h1,h2,h3,h4 {{ color:{T['text']}; }}
.kpi {{ background:linear-gradient(145deg,{T['card']},{T['panel']});
        border:1px solid {T['grid']}; border-left:4px solid var(--blue);
        border-radius:14px; padding:14px 16px; height:100%; }}
.kpi.green {{ border-left-color:var(--green); }}
.kpi.amber {{ border-left-color:{T['amber']}; }}
.kpi .lbl {{ color:{T['muted']}; font-size:.72rem; text-transform:uppercase;
             letter-spacing:.4px; }}
.kpi .val {{ color:{T['text']}; font-size:1.45rem; font-weight:700; margin-top:2px; }}
.kpi .sub {{ color:{T['muted']}; font-size:.7rem; margin-top:2px; }}
.insight {{ background:{T['card']}; border:1px solid {T['grid']};
            border-radius:10px; padding:10px 14px; margin-bottom:8px;
            font-size:.9rem; }}
.section-banner {{ background:linear-gradient(90deg,{T['blue']}22,{T['card']});
            border-left:5px solid {T['blue']}; border-radius:10px;
            padding:10px 16px; margin:6px 0 10px 0; scroll-margin-top:5rem; }}
/* offset agar anchor navbar tidak tertutup toolbar Streamlit yang fixed */
[data-testid="stVerticalBlockBorderWrapper"] {{ scroll-margin-top:5rem; }}
html {{ scroll-behavior:smooth; }}
.section-banner .st {{ color:{T['text']}; font-size:1.05rem; font-weight:700; }}
.section-banner .sd {{ color:{T['muted']}; font-size:.78rem; margin-top:2px; }}
.section-banner.amber {{ background:linear-gradient(90deg,{T['amber']}22,{T['card']});
            border-left-color:{T['amber']}; }}
.section-banner.green {{ background:linear-gradient(90deg,{T['green']}22,{T['card']});
            border-left-color:{T['green']}; }}
.section-banner.purple {{ background:linear-gradient(90deg,{T['purple']}22,{T['card']});
            border-left-color:{T['purple']}; }}
.section-banner.teal {{ background:linear-gradient(90deg,{T['teal']}22,{T['card']});
            border-left-color:{T['teal']}; }}
.kpi.red {{ border-left-color:{T['red']}; }}
.navbar {{ display:flex; gap:8px; flex-wrap:wrap; margin:2px 0 10px 0; }}
.navbar a {{ background:{T['card']}; border:1px solid {T['grid']}; color:{T['text']};
            padding:6px 14px; border-radius:20px; font-size:.82rem; font-weight:600;
            text-decoration:none; }}
.navbar a:hover {{ background:{T['blue']}; color:white; border-color:{T['blue']}; }}
.stTabs [data-baseweb="tab-list"] {{ gap:6px; }}
.stTabs [data-baseweb="tab"] {{ background:{T['card']}; border-radius:8px 8px 0 0;
            padding:8px 18px; }}
.stTabs [aria-selected="true"] {{ background:{T['blue']}; color:white; }}
[data-testid="stMetricValue"] {{ color:{T['text']}; }}
</style>
""", unsafe_allow_html=True)


def rp(v):
    return fmt.rupiah(v)


def rp_full(v):
    return fmt.ribuan(v) if v is None or not isinstance(v, str) else v


def num(v):
    return fmt.jumlah(v)


def kpi(col, label, value, sub="", cls="", help=""):
    tip = f' title="{help}"' if help else ""
    info = ' <span style="opacity:.5">ⓘ</span>' if help else ""
    col.markdown(
        f'<div class="kpi {cls}"{tip}><div class="lbl">{label}{info}</div>'
        f'<div class="val">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True)


def section(title, desc="", cls="", anchor=None):
    """Banner section besar untuk mengelompokkan area Modul 1."""
    aid = f' id="{anchor}"' if anchor else ""
    st.markdown(
        f'<div{aid} class="section-banner {cls}"><div class="st">{title}</div>'
        f'<div class="sd">{desc}</div></div>', unsafe_allow_html=True)


def _fmt_ribuan(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except Exception:
        return "0"


def rupiah_input(container, label, default_value, key, help=None):
    """Input nominal dengan pemisah ribuan otomatis (mis. 100000 -> 100.000)."""
    if key not in st.session_state:
        st.session_state[key] = _fmt_ribuan(default_value)

    def _reformat():
        digits = "".join(c for c in st.session_state[key] if c.isdigit())
        st.session_state[key] = _fmt_ribuan(digits) if digits else "0"

    container.text_input(label, key=key, on_change=_reformat, help=help)
    digits = "".join(c for c in st.session_state[key] if c.isdigit())
    return int(digits) if digits else 0


# ----------------------------------------------------------------- DATA (cache)
# TTL wajib: tanpa ini cache bertahan selamanya, sehingga dashboard bisa
# menampilkan angka lama setelah data di GSheet diperbarui — sumber
# kebingungan "angka beda dengan Apps Script" yang sulit dilacak.
CACHE_TTL = 900          # 15 menit


@st.cache_data(show_spinner="Membaca & memproses data Excel terbaru...", ttl=CACHE_TTL)
def load_data(_mtime: float):
    raw = data_loader.load_workbook()
    d = data_cleaning.clean_all(raw)
    d["_loaded_at"] = pd.Timestamp.now()
    return d


# --- Jembatan Streamlit Secrets (untuk DEPLOY headless di Streamlit Cloud) ---
# Bila app di-deploy, isi kredensial lewat st.secrets [gsheet] (bukan file lokal).
try:
    if "gsheet" in st.secrets:
        _sec = st.secrets["gsheet"]
        config.DATA_SOURCE = "gsheet"
        config.GSHEET_MODE = "oauth"
        if _sec.get("id"):
            config.GSHEET_ID = _sec["id"]
        if "oauth_client" in _sec:
            config.GSHEET_OAUTH_CLIENT_INFO = dict(_sec["oauth_client"])
        if "authorized_user" in _sec:
            config.GSHEET_OAUTH_AUTHORIZED_INFO = dict(_sec["authorized_user"])
except Exception:
    pass


@st.cache_data(show_spinner="Menarik data live dari Google Sheet...", ttl=CACHE_TTL)
def load_data_gsheet(_nonce: int):
    raw = data_loader.load_workbook()          # otomatis ke gsheet via config
    d = data_cleaning.clean_all(raw)
    d["_loaded_at"] = pd.Timestamp.now()
    return d


def _use_gsheet():
    return getattr(config, "DATA_SOURCE", "excel") == "gsheet"


def get_data():
    if _use_gsheet():
        nonce = st.session_state.get("gsheet_nonce", 0)
        return load_data_gsheet(nonce), "Google Sheet (live)", None
    path = data_loader.find_excel()
    mtime = os.path.getmtime(path)
    return load_data(mtime), path, mtime


# ----------------------------------------------------------------- LOAD
try:
    data, xlpath, mtime = get_data()
except Exception as e:
    st.error(f"Gagal memuat data: {e}")
    st.info("Mode Google Sheet (OAuth): pastikan sudah menjalankan `python gsheet_login.py` "
            "sekali, GSHEET_ID terisi di secrets_local.py, dan file credentials/oauth_client.json ada.")
    st.stop()

df_all = data["all_resi"]

# ----------------------------------------------------------------- HEADER (tanpa sidebar)
dmin = pd.to_datetime(df_all["tgl_kirim"].min())
dmax = pd.to_datetime(df_all["tgl_kirim"].max())
dff = df_all                       # sidebar & filter global dihapus (pakai seluruh data)
baseline = forecasting.compute_baseline(dff)
recv_dist = forecasting.receive_distribution(dff)

_hc = st.columns([6, 3, 1.6])
_hc[0].markdown(f"## 📊 {config.APP_TITLE}")
_src = "🌐 Google Sheet (live)" if _use_gsheet() else f"📄 {os.path.basename(str(xlpath))}"
_loaded_at = data.get("_loaded_at")
_umur = ""
if _loaded_at is not None:
    _mnt = int((pd.Timestamp.now() - _loaded_at).total_seconds() // 60)
    _umur = " • dimuat **baru saja**" if _mnt < 1 else f" • dimuat **{_mnt} mnt lalu**"
_hc[1].caption(f"Sumber: **{_src}** • {len(df_all):,} resi • data "
               f"{dmin:%d %b %Y}–{dmax:%d %b %Y}{_umur}".replace(",", "."))
if _hc[2].button("🔄 Muat ulang", width='stretch'):
    st.session_state["gsheet_nonce"] = st.session_state.get("gsheet_nonce", 0) + 1
    st.cache_data.clear()
    st.rerun()

tab1, tab4, tab2, tab3, tab5 = st.tabs(["💰 Modul 1 — Simulator Cashflow & Pencairan",
                                        "🎯 Modul 2 — Target Profit Simulator",
                                        "🗺️ Modul 3 — Analisis Wilayah",
                                        "📦 Modul 4 — Analisis Produk",
                                        "📣 Modul 5 — Analisis Iklan Meta"])

# ---- katalog produk dari sheet admin (Order + Stock + retur + OrderOnline closing) ----
try:
    _catalog = padmin.build_catalog(data.get("order"), data.get("stock"), df_all,
                                    data.get("oo"), data.get("ref"))
except Exception as _ce:
    try:
        _catalog = padmin.build_catalog(data.get("order"), data.get("stock"), df_all)
    except Exception:
        _catalog = pd.DataFrame()
    st.warning(f"Katalog produk dari sheet admin gagal sebagian ({type(_ce).__name__}); "
               "memakai data seadanya. Cek tab Import-Order/Stock/OrderOnline/RefProduk.")
# Closing rate GLOBAL dari OrderOnline (paid & completed/processing ÷ total leads) — default slider
try:
    _OO_CLOSING = padmin.global_closing_rate(data.get("oo"))
except Exception:
    _OO_CLOSING = None
_META = data.get("meta")     # sheet Meta-Ads (Modul 5); None bila belum ada
try:                          # OrderOnline ter-resolusi ke SKU + created_at + closing
    _OO_RESOLVED = padmin.resolve_oo_products(data.get("oo"), data.get("ref"), data.get("order"))
except Exception:
    _OO_RESOLVED = pd.DataFrame()
try:                          # cost/purchase per SKU dari Meta (default CPL Modul 1)
    _META_CPP = meng.cost_per_purchase_by_sku(_META) if _META is not None else {}
except Exception:
    _META_CPP = {}
# Kolom input (editable) + kolom turunan (disabled)
_INCOLS = ["Produk", "Budget/Hari", "CPL", "Nilai Produk", "HPP", "Stok (pcs)", "Pcs/Order"]
_DERIVED = ["Total Resi", "Closing Rate", "Pcs Terjual", "CM", "CM%", "Retur %"]
_PCOLS = _INCOLS + _DERIVED
# kunci widget input yang disimpan/dimuat oleh fitur Planning
_PLAN_KEYS = ["in_modal", "sim_start", "sim_end", "p_closing", "p_success", "p_ncs",
              "in_ongkir", "p_cashback", "p_durasi", "p_pctcod", "p_codfee",
              "in_opexvar", "in_opexfix", "p_payday", "p_mode", "p_target"]


# ---- seeder tabel produk (master, persisten lintas filter) ----
def seed_master(params: dict | None = None):
    """Seed dari data admin (nama/nilai jual/HPP/stok/retur + auto CPL & budget optimal).
    Fallback ke histori all_resi bila sheet admin tidak tersedia."""
    if _catalog is not None and not _catalog.empty:
        pr = params or dict(
            closing=(_OO_CLOSING or config.DEFAULTS["closing_rate"]),
            success=baseline.get("success_rate", config.DEFAULTS["success_rate"]),
            ongkir=baseline.get("avg_total_biaya", config.DEFAULTS["ongkir_per_resi"]),
            cashback_pct=baseline.get("cashback_pct", config.DEFAULTS["cashback_pct"]),
            cod_fee_rate=baseline.get("cod_fee_rate", config.DEFAULTS["cod_fee_rate"]),
            opex_var_resi=0, horizon=config.DEFAULTS["horizon_days"],
            cpl_override=_META_CPP)     # default CPL = cost/purchase real Meta-Ads per SKU
        return padmin.optimize_table(_catalog, pr)[_PCOLS].copy()
    t = prodeng.seed_product_table(
        df_all, top_n=25, total_budget_harian=config.DEFAULTS["budget_harian"],
        default_cpl=config.DEFAULTS["cpl"], hpp_ratio=config.DEFAULTS["hpp_ratio"])
    t["Stok (pcs)"] = 0
    t["Pcs/Order"] = 1
    _nj = pd.to_numeric(t["Nilai Produk"], errors="coerce").fillna(0)
    _hp = pd.to_numeric(t["HPP"], errors="coerce").fillna(0)
    t["Total Resi"] = 0
    t["Closing Rate"] = np.nan
    t["Pcs Terjual"] = 0
    t["CM"] = (_nj - _hp).round().astype(int)
    t["CM%"] = ((_nj - _hp) / _nj.replace(0, np.nan) * 100).round(1)
    t["Retur %"] = np.nan
    return t[_PCOLS]


def _recompute_derived(dfp, ongkir_, cb_pct_, fee_pct_, ovar_, closing_, success_=None):
    """Hitung ulang CM & CM% LIVE dari input (Nilai Jual, HPP, CPL, Closing + rate global).
    CM = margin per order SETELAH biaya akuisisi iklan:
        CM = Nilai Jual − HPP − FeeCOD×(Nilai+Ongkir) + Cashback×Ongkir − OpexVar − (CPL÷Closing)
    Retur % tetap dari data (tidak dihitung ulang)."""
    d = dfp.copy()
    nj = pd.to_numeric(d.get("Nilai Produk"), errors="coerce").fillna(0)
    hp = pd.to_numeric(d.get("HPP"), errors="coerce").fillna(0)
    cpl = pd.to_numeric(d.get("CPL"), errors="coerce").fillna(0)
    cac = (cpl / closing_) if closing_ else 0.0            # biaya iklan per order
    cm = (nj - hp - (fee_pct_ / 100) * (nj + ongkir_) + (cb_pct_ / 100) * ongkir_
          - ovar_ - cac)
    d["CM"] = cm.round()
    d["CM%"] = (cm / nj.replace(0, np.nan) * 100).round(1)
    if "Retur %" not in d.columns:
        d["Retur %"] = np.nan
    return d


if "produk_master" not in st.session_state:
    st.session_state["produk_master"] = seed_master()
if "editor_nonce" not in st.session_state:
    st.session_state["editor_nonce"] = 0

# =================================================================== MODUL 1
with tab1:
    # --- Terapkan planning yang dimuat SEBELUM widget input dibuat (aman) ---
    if "_pending_load" in st.session_state:
        _d = st.session_state.pop("_pending_load")
        for _k in _PLAN_KEYS:
            if _k in _d and _d[_k] is not None:
                _v = _d[_k]
                if _k in ("sim_start", "sim_end"):
                    try:
                        _v = pd.to_datetime(_v).date()
                    except Exception:
                        pass
                st.session_state[_k] = _v
        if _d.get("produk_master"):
            _pm = pd.DataFrame(_d["produk_master"])
            # Pasang kembali kolom DATA (Total Resi, Closing Rate, Pcs Terjual, Retur %)
            # dari katalog terkini via nama Produk — plan hanya menyimpan kolom input.
            _datacols = ["Total Resi", "Closing Rate", "Pcs Terjual", "Retur %"]
            try:
                _lut = seed_master().drop_duplicates("Produk").set_index("Produk")
                for _c in _datacols:
                    _pm[_c] = (_pm["Produk"].map(_lut[_c]) if _c in _lut.columns else np.nan)
            except Exception:
                for _c in _datacols:
                    if _c not in _pm.columns:
                        _pm[_c] = np.nan
            for _c in ("CM", "CM%"):
                if _c not in _pm.columns:
                    _pm[_c] = np.nan
            st.session_state["produk_master"] = _pm.reindex(
                columns=[c for c in _PCOLS if c in _pm.columns])
        st.session_state.pop("editor_master", None)
        st.session_state.pop("_prod_insig", None)         # paksa recompute CM/CM% stlh muat
        for _kk in [k for k in st.session_state if str(k).startswith(("cf_edit_", "cfed_"))]:
            st.session_state.pop(_kk, None)
        # simpan penyesuaian harian yang dimuat utk dipasang saat tabel harian dibangun
        st.session_state["_pending_daily"] = _d.get("daily")

    st.markdown(
        '<div class="navbar">'
        '<a href="#sec-set">⚙️ Pengaturan</a>'
        '<a href="#sec-global">📊 Skema Global</a>'
        '<a href="#sec-harian">🧮 Skema Harian</a>'
        '<a href="#sec-banding">⚖️ Perbandingan</a>'
        '<a href="#sec-plan">💾 Planning</a></div>', unsafe_allow_html=True)
    with st.container(border=True):
        section("⚙️ PENGATURAN — Parameter Global",
                "Semua angka di bawah ini (modal, periode, parameter, tabel produk) menjadi "
                "dasar SKEMA GLOBAL. Ubah di sini untuk mengatur seluruh simulasi.",
                anchor="sec-set")
        st.markdown("#### 💰 Modal Awal")
        mm = st.columns([2, 3])
        modal_awal = rupiah_input(mm[0], "Modal Awal Disiapkan (Rp)",
                                  config.DEFAULTS["modal_awal"], "in_modal",
                                  help="Kas awal yang Anda siapkan — dipakai untuk budget iklan, "
                                       "beli barang (HPP), dan biaya operasional. Simulasi memakai "
                                       "ini sebagai saldo kas awal, lalu menghitung posisi kas tiap "
                                       "hari, kapan (jika) kas habis, dan saldo di hari ke-30/60.")
        mm[1].caption("Saldo kas dimulai dari nilai ini. Bila arus kas menekan saldo di bawah 0, "
                      "artinya modal **kurang** untuk skala belanja yang dipilih. Atur budget/HPP di "
                      "tabel produk agar modal cukup.")

        st.markdown("#### 🗓️ Periode Simulasi")
        _today = pd.Timestamp.today().normalize()
        dcol = st.columns([1, 1, 2])
        start_date = dcol[0].date_input("Tanggal Mulai", value=_today.date(), key="sim_start")
        end_date = dcol[1].date_input("Tanggal Selesai",
                                      value=(_today + pd.Timedelta(days=29)).date(), key="sim_end")
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        if end_ts < start_ts:
            dcol[2].error("⚠️ Tanggal Selesai harus ≥ Tanggal Mulai.")
            st.stop()
        horizon = int((end_ts - start_ts).days) + 1
        dcol[2].caption(f"Durasi simulasi **{horizon} hari** ({start_ts:%d %b %Y} – "
                        f"{end_ts:%d %b %Y}). Semua proyeksi & belanja iklan mengikuti rentang ini.")

        st.markdown("#### ⚙️ Parameter Global")
        g1, g2, g3, g4 = st.columns(4)
        _cl_def = int(round((_OO_CLOSING if _OO_CLOSING else config.DEFAULTS["closing_rate"]) * 100))
        closing = g1.slider("Closing Order (%)", 0, 100, _cl_def, key="p_closing",
                            help=("Default dari OrderOnline: (paid & completed/processing) ÷ total "
                                  "leads." if _OO_CLOSING else "Default dari asumsi.")) / 100
        success = g1.slider("Success Delivery (%)", 0, 100,
                            int(round(baseline["success_rate"] * 100)) or 1, key="p_success") / 100
        n_cs = int(g1.number_input("Jumlah Customer Service (orang)", 1, 200,
                                   int(config.DEFAULTS.get("n_cs", 3)), step=1, key="p_ncs",
                                   help="Untuk membagi beban leads per CS."))
        ongkir = rupiah_input(g2, "Ongkir / Resi (Rp)", baseline["avg_total_biaya"], "in_ongkir")
        cashback_pct = g2.number_input("Cashback Ongkir (%)", 0.0, 100.0, key="p_cashback",
                                       value=round(baseline["cashback_pct"] * 100, 1), step=0.5,
                                       help="Cashback ongkir (Biaya Diskon) sbg omzet.")
        durasi_kirim = g2.number_input(
            "Rata² Durasi Kirim Berhasil (hari)", 1.0, 60.0, key="p_durasi",
            value=round(float(baseline.get("avg_durasi") or 7), 1), step=0.5,
            help="Rata-rata lama paket dari pickup s/d SAMPAI di konsumen — HANYA paket sukses "
                 "sampai (retur & yang masih transit tidak dihitung). Default dari histori. "
                 "Menentukan tanggal paket diterima → memicu jadwal pencairan COD.")
        pct_cod = g3.slider("Order COD (%)", 0, 100, int(round(baseline["pct_cod"] * 100)), key="p_pctcod")
        cod_fee_pct = g3.number_input("COD Fee (%)", 0.0, 10.0, key="p_codfee",
                                      value=round(baseline["cod_fee_rate"] * 100, 2), step=0.05)
        opex_var_resi = rupiah_input(g3, "Opex Variabel / Resi (Rp)",
                                     int(config.DEFAULTS.get("opex_var_resi", 0)), "in_opexvar",
                                     help="Biaya per paket: packing, ongkos ke drop point, bonus "
                                          "per closing, dll. Otomatis dikali jumlah resi (skala volume).")
        opex_fix_bulan = rupiah_input(g4, "Opex Tetap / Bulan (Rp)",
                                      int(config.DEFAULTS.get("opex_fix_bulan", 0)), "in_opexfix",
                                      help="Biaya tetap bulanan: gaji, sewa, langganan. Keluar "
                                           "SEKALIGUS di tanggal gajian tiap bulan (bukan disebar).")
        payday = int(g4.number_input("Tanggal Gajian", 1, 28,
                                     int(config.DEFAULTS.get("payday", 25)), step=1, key="p_payday",
                                     help="Hari dalam bulan saat opex tetap (gaji) dibayarkan."))
        mode_label = g4.radio("Mode Pencairan", list(config.SETTLE_MODES.keys()), key="p_mode")
        mode = config.SETTLE_MODES[mode_label]
        lag = config.SETTLE_DAILY_LAG_DEFAULT
        if mode == "mode1":
            lag = g4.number_input("Jeda cair (hari kerja)", 0, 10, lag)
        st.caption(f"➡️ Transfer otomatis **{100 - pct_cod}%** • Cashback per resi "
                   f"≈ {rp(cashback_pct/100*ongkir)} • Opex tetap {rp(opex_fix_bulan)}/bln "
                   f"(gajian tgl {payday}) + variabel {rp(opex_var_resi)}/resi.")

        # ---------- TABEL PRODUK (input per produk + kolom turunan disabled) ----------
        st.markdown("#### 🧾 Tabel Produk — Nilai Jual, HPP, Stok, AoV, CM & Retur dari Data Admin")
        _src = ("Order + Stock (admin)" if (_catalog is not None and not _catalog.empty)
                else "histori All Resi (sheet admin tidak tersedia)")
        cap, btn = st.columns([5, 1])
        cap.caption(f"Sumber: **{_src}**. **✏️ = bisa diedit** (Budget, CPL, Nilai Jual, HPP, Stok, "
                    "Pcs/Order) • **🔒 = otomatis, tidak bisa diedit** (Total Resi, Closing Rate, Pcs "
                    "Terjual, CM, CM%, Retur %). CM & CM% **live-update** saat Anda ubah CPL/Closing/"
                    "Nilai Jual/HPP. Geser ke kanan untuk melihat semua kolom.")
        if btn.button("🎯 Re-plot optimal", width='stretch',
                      help="Hitung ulang CPL & Budget optimal per produk memakai parameter global "
                           "saat ini (closing, success, ongkir, dll)."):
            _pr = dict(closing=closing, success=success, ongkir=ongkir,
                       cashback_pct=cashback_pct / 100, cod_fee_rate=cod_fee_pct / 100,
                       opex_var_resi=opex_var_resi, horizon=horizon)
            st.session_state["produk_master"] = seed_master(_pr)
            st.session_state.pop("editor_master", None)
            st.rerun()

        _money = lambda label: st.column_config.NumberColumn(label, min_value=0, format="localized")
        _int = lambda label, h: st.column_config.NumberColumn(label, min_value=0, step=1, help=h)
        _cm_help = ("CM = margin per order SETELAH biaya akuisisi iklan.  Rumus: "
                    "Nilai Jual − HPP − FeeCOD×(Nilai Jual+Ongkir) + Cashback×Ongkir − Opex Variabel "
                    "− (CPL ÷ Closing).  Bagian (CPL÷Closing) = biaya iklan untuk mendapatkan 1 order "
                    "(butuh 1/Closing leads @ CPL).  Ter-update otomatis saat CPL, Closing, Nilai "
                    "Jual, atau HPP diubah.  Catatan: Budget iklan menentukan VOLUME, bukan margin "
                    "per order, jadi tidak mengubah CM.")
        _colcfg = {
            "Produk": st.column_config.TextColumn("✏️ Produk", width="medium"),
            "Budget/Hari": _money("✏️ Budget/Hari (Rp)"),
            "CPL": _money("✏️ CPL (Rp)"),
            "Nilai Produk": st.column_config.NumberColumn(
                "✏️ Nilai Jual / AoV per Resi (Rp)", min_value=0, format="localized",
                help="AoV (Average Order Value) = nilai jual total produk PER RESI/ORDER "
                     "(product_price), sudah mencakup berapa pun jumlah pcs dalam 1 resi — "
                     "jadi ini nilai per resi, BUKAN per pcs."),
            "HPP": st.column_config.NumberColumn(
                "✏️ HPP (Rp)", min_value=0, format="localized",
                help="Harga pokok per order = Pcs/Order × HPP per Pcs (dari Import-Stock)."),
            "Stok (pcs)": _int("✏️ Stok (pcs)", "Sisa stok gudang. Order tercukupi stok tidak "
                                                "menimbulkan biaya beli produk."),
            "Pcs/Order": _int("✏️ Pcs/Order", "Rata-rata pcs produk utama per order (untuk "
                                              "menghitung berapa order yang bisa dipenuhi stok)."),
            "Total Resi": st.column_config.NumberColumn("🔒 Total Resi", disabled=True,
                format="localized",
                help="Jumlah transaksi/resi produk ini sejauh ini (dari Import-Order). "
                     "Otomatis dari data — tidak bisa diedit."),
            "Closing Rate": st.column_config.NumberColumn("🔒 Closing Rate", disabled=True,
                format="%.1f%%",
                help="Closing rate historis produk ini dari OrderOnline = order (paid & "
                     "completed/processing) ÷ total leads produk itu. Otomatis dari data — "
                     "tidak bisa diedit."),
            "Pcs Terjual": st.column_config.NumberColumn("🔒 Pcs Terjual", disabled=True,
                format="localized",
                help="Total pcs produk ini yang terjual sejauh ini (Σ Pcs semua order). "
                     "Otomatis dari data — tidak bisa diedit."),
            "CM": st.column_config.NumberColumn("🔒 CM (Rp/order)", disabled=True,
                                                format="localized", help=_cm_help),
            "CM%": st.column_config.NumberColumn("🔒 CM %", disabled=True, format="%.1f%%",
                help="CM ÷ Nilai Jual × 100 (memakai CM setelah biaya akuisisi). Otomatis, "
                     "ter-update saat input diubah."),
            "Retur %": st.column_config.NumberColumn("🔒 Retur %", disabled=True, format="%.1f%%",
                help="% retur produk ini = resi gagal diterima (Tanda TTD 'Belum Diterima' & "
                     "Waktu Terima terisi) ÷ TOTAL seluruh resi produk itu (via join No. Waybill "
                     "ke All Resi). Otomatis dari data — tidak bisa diedit."),
        }
        # --- Urutkan lalu TETAP bisa edit: tombol Urutkan menata ulang baris (edit ikut terbawa) ---
        _sc = st.columns([2, 2, 1.3, 4])
        _sortby = _sc[0].selectbox("Urutkan kolom", ["(bawaan)"] + _PCOLS, key="prod_sort_col")
        _sortdir = _sc[1].radio("Arah", ["Turun", "Naik"], horizontal=True, key="prod_sort_dir")
        if _sc[2].button("↕️ Urutkan", width='stretch',
                         help="Tata ulang baris sesuai kolom & arah; edit yang sudah ada ikut terbawa."):
            _cur = st.session_state.get("produk_current", st.session_state["produk_master"]).copy()
            if _sortby != "(bawaan)" and _sortby in _cur.columns:
                _cur = _cur.sort_values(_sortby, ascending=(_sortdir == "Naik"),
                                        na_position="last", kind="stable").reset_index(drop=True)
            st.session_state["produk_master"] = _cur
            st.session_state.pop("editor_master", None)
            st.rerun()
        _sc[3].caption("Pilih kolom & arah lalu klik **Urutkan** — tabel tersusun dan **tetap bisa "
                       "diedit** dalam urutan itu; edit yang sudah ada ikut terbawa.")

        edited = st.data_editor(
            st.session_state["produk_master"], num_rows="dynamic", width='stretch',
            height=320, key="editor_master", column_config=_colcfg)
        # LIVE-UPDATE kolom turunan (CM, CM%) dari input terbaru — termasuk CPL.
        # Rerun HANYA saat INPUT berubah (pakai signature), sehingga tidak loop.
        _ed = _recompute_derived(edited, ongkir, cashback_pct, cod_fee_pct,
                                 opex_var_resi, closing).reset_index(drop=True)
        # Signature INPUT ternormalisasi (numerik dibulatkan) — kebal drift format,
        # jadi rerun berhenti begitu input stabil (tidak loop).
        _sig = edited[_INCOLS].copy()
        for _c in ["Budget/Hari", "CPL", "Nilai Produk", "HPP", "Stok (pcs)", "Pcs/Order"]:
            if _c in _sig:
                _sig[_c] = pd.to_numeric(_sig[_c], errors="coerce").round(2)
        _insig = f"{ongkir}|{cashback_pct}|{cod_fee_pct}|{closing}|" + _sig.to_json()
        if st.session_state.get("_prod_insig") != _insig:
            st.session_state["_prod_insig"] = _insig
            st.session_state["produk_master"] = _ed
            st.rerun()                              # sekali, lalu signature cocok → berhenti
        st.session_state["produk_current"] = _ed        # snapshot utk Planning
        edited = _ed

        overrides = dict(modal_awal=modal_awal, start_date=start_ts,
                         closing_rate=closing, success_rate=success, ongkir_per_resi=ongkir,
                         cashback_pct=cashback_pct / 100, cod_fee_rate=cod_fee_pct / 100,
                         pct_cod=pct_cod / 100, horizon_days=horizon,
                         opex_fix_bulan=opex_fix_bulan, opex_var_resi=opex_var_resi, payday=payday,
                         durasi_override=durasi_kirim, mode=mode, daily_lag=lag)
        sim = ce.simulate_multi(baseline, recv_dist, edited, overrides)
        s = sim["summary"]

        _ret = ("GRATIS (retur ≤ 20%)" if s.get("retur_excess", 0) <= 0
                else f"{s.get('retur_excess',0)*100:.0f}% × ongkir penuh")
        st.caption(f"Budget iklan total **{rp(s['budget_iklan'])}** "
                   f"({rp(s['budget_harian'])}/hari × {horizon} hari) • Ongkir retur J&T: {_ret}.")

    # ============================ SECTION 1: SKEMA GLOBAL ============================
    st.markdown("---")
    with st.container(border=True):
        section("📊 SECTION 1 — HASIL SKEMA GLOBAL",
                "Proyeksi dari parameter global (baseline sebelum penyesuaian harian).",
                anchor="sec-global")

        # info transparansi jadwal gaji (opex tetap)
        _sched = ce.payday_schedule(start_ts, horizon, payday, opex_fix_bulan)
        if opex_fix_bulan > 0:
            if _sched:
                _tgls = ", ".join(f"{d:%d %b}" for d in sorted(_sched))
                st.caption(f"💼 Opex tetap (gaji) {rp(opex_fix_bulan)}/bln dibebankan pada: **{_tgls}** "
                           f"(tanggal gajian {payday}, yang jatuh dalam periode).")
            else:
                st.warning(f"⚠️ Opex tetap {rp(opex_fix_bulan)}/bln **belum terhitung**: tidak ada "
                           f"tanggal gajian (tgl {payday}) yang jatuh dalam periode "
                           f"{start_ts:%d %b}–{end_ts:%d %b}. Perpanjang periode atau ubah tanggal gajian.")

        # ---------- KPI: POSISI KEUANGAN (cash-first) ----------
        pos = s.get("posisi_hari", {})
        _pk = lambda day: pos.get(day, {}).get("kas")
        _pl = lambda day: pos.get(day, {}).get("laba_akrual")
        kas_h = _pk(horizon)
        modal0 = s["modal_awal"]

        st.markdown("#### 💵 Posisi Keuangan")
        r1 = st.columns(4)
        kpi(r1[0], "Modal Awal", rp(modal0), "kas awal disiapkan",
            help="Kas awal yang Anda siapkan sebagai titik mulai saldo.")
        kpi(r1[1], f"Saldo Kas @ H+{horizon}", rp(kas_h) if kas_h is not None else "—",
            "posisi kas di akhir horizon", cls="green" if (kas_h or 0) >= 0 else "amber",
            help="Posisi kas riil di hari terakhir horizon = Modal Awal + akumulasi arus kas "
                 "sampai hari itu (COD yang belum cair belum termasuk).")
        if s["modal_cukup"]:
            kpi(r1[2], "Status Modal", "✓ CUKUP",
                f"kas terendah {rp(s['kas_riil_terendah'])}", cls="green",
                help="Saldo kas tidak pernah menyentuh negatif — modal awal cukup menopang "
                     "seluruh belanja pada skala ini.")
        else:
            khb = s.get("hari_kas_habis")
            kpi(r1[2], "Status Modal", "⚠️ KURANG",
                (f"kas habis H+{khb} • tambah {rp(s['kekurangan_modal'])}"
                 if khb is not None else f"tambah {rp(s['kekurangan_modal'])}"), cls="amber",
                help="Saldo kas sempat minus — modal awal TIDAK cukup untuk skala belanja ini. "
                     "Kurangi budget/HPP atau tambah modal sebesar kekurangan ini.")
        kpi(r1[3], "Kas Setelah Semua COD Cair", rp(s["kas_riil_akhir"]),
            "termasuk outstanding yang akhirnya cair", cls="green" if s["kas_riil_akhir"] >= modal0 else "amber",
            help="Posisi kas bila menunggu SEMUA COD outstanding cair (ekor setelah horizon). "
                 "Ini kas final bila belanja dihentikan di akhir horizon.")

        # ---------- POSISI DI HARI KE-30 & 60 ----------
        st.markdown("##### 📆 Posisi di Hari ke-30 & 60")
        r2 = st.columns(4)
        k30, k60, l30, l60 = _pk(30), _pk(60), _pl(30), _pl(60)
        kpi(r2[0], "Saldo Kas H+30", rp(k30) if k30 is not None else "> horizon",
            "posisi kas hari ke-30", cls="green" if (k30 or 0) >= 0 else "amber")
        kpi(r2[1], "Laba Akrual s/d H+30", rp(l30) if l30 is not None else "> horizon",
            "laba (akrual) kumulatif 30 hari", cls="green" if (l30 or 0) >= 0 else "amber")
        kpi(r2[2], "Saldo Kas H+60", rp(k60) if k60 is not None else "> horizon",
            "posisi kas hari ke-60", cls="green" if (k60 or 0) >= 0 else "amber")
        kpi(r2[3], "Laba Akrual s/d H+60", rp(l60) if l60 is not None else "> horizon",
            "laba (akrual) kumulatif 60 hari", cls="green" if (l60 or 0) >= 0 else "amber")

        # ---------- LABA & EFISIENSI ----------
        leads_per_hari = s["n_lead"] / horizon if horizon else 0
        leads_per_cs = leads_per_hari / n_cs if n_cs else 0
        st.markdown("##### 📈 Laba & Efisiensi (horizon)")
        r3 = st.columns(4)
        kpi(r3[0], "Laba Bersih Akrual", rp(s["net_profit"]),
            "stlh HPP, iklan, retur, opex", cls="green" if s["net_profit"] >= 0 else "amber",
            help="Laba income-statement (akrual): Omzet − HPP barang terjual − iklan − ongkir "
                 "retur − operasional. HPP barang retur TIDAK dihitung rugi (barang kembali). "
                 "Beda dari kas: laba akrual mengakui omzet COD saat paket diterima, bukan saat cair.")
        kpi(r3[1], "ROI Modal Awal", fmt.persen(s.get("roi_modal_awal", 0), 0),
            "laba akrual ÷ modal awal", cls="green" if s.get("roi_modal_awal", 0) >= 0 else "amber",
            help="Laba bersih (akrual) horizon dibagi Modal Awal yang Anda siapkan.")
        kpi(r3[2], "Estimasi Omzet (Kas Masuk)", rp(s["total_revenue"]),
            f"COD {rp(s['nilai_cod'])} • Transfer {rp(s['nilai_transfer'])}", cls="green",
            help="Total dana masuk kotor dari paket terkirim selama horizon (sebelum HPP/iklan/opex).")
        kpi(r3[3], "Outstanding COD (blm cair)", rp(s["outstanding_akhir"]),
            "menunggu settle di akhir horizon", cls="amber",
            help="Omzet COD yang sudah didapat tapi belum cair di akhir horizon (menunggu paket "
                 "diterima + settlement J&T). Penyebab utama kebutuhan modal kerja.")

        # ---------- FUNNEL OPERASIONAL (ringkas) ----------
        st.markdown("##### 🧭 Funnel Operasional")
        r4 = st.columns(4)
        kpi(r4[0], "Lead → Order", f"{num(s['n_lead'])} → {num(s['n_order'])}",
            f"budget {rp(s['budget_iklan'])} • CPL closing {fmt.persen(closing*100,0)}",
            help="Lead = Budget ÷ CPL. Order = Lead × Closing Rate (1 order = 1 resi).")
        kpi(r4[1], "Resi Dikirim", num(s["n_resi"]),
            f"{num(s['n_sukses'])} sampai ({fmt.persen(s['success_rate']*100,0)})",
            help="Resi dikirim; Sampai = Resi × Success Rate, sisanya retur.")
        kpi(r4[2], "Resi Completed / Hari", num((s["n_sukses"] / horizon) if horizon else 0),
            f"sukses sampai ({fmt.persen(s['success_rate']*100,0)})", cls="green",
            help="Paket sukses per hari = resi/hari × success rate.")
        kpi(r4[3], f"Leads / Hari per CS ({n_cs})", num(leads_per_cs),
            "beban follow-up tiap CS/hari", cls="amber",
            help="Total leads harian ÷ jumlah CS. Acuan beban kerja & kebutuhan tambah CS.")

        # ---------- STOK & MODAL PRODUK (stok-aware) ----------
        st.markdown("##### 📦 Stok Gudang & Modal Produk")
        r5 = st.columns(4)
        kpi(r5[0], "Beli Produk (kas keluar)", rp(s["total_beli_produk"]),
            "hanya order melebihi stok", cls="amber",
            help="Kas untuk beli stok baru — HANYA untuk order yang melebihi stok gudang. "
                 "Order yang tercukupi stok tidak menimbulkan biaya beli.")
        kpi(r5[1], "💚 Hemat dari Stok", rp(s.get("stok_hemat", 0)),
            f"{num(s.get('stock_orders_total',0))} order dari stok", cls="green",
            help="Penghematan kas karena sebagian order dipenuhi dari stok gudang yang sudah ada "
                 "(HPP-nya sudah dibayar sebelumnya). = HPP semua paket − kas beli baru.")
        kpi(r5[2], "HPP bila Beli Semua", rp(s.get("total_hpp_full", 0)),
            "tanpa memanfaatkan stok", cls="amber",
            help="Total HPP bila semua paket harus dibeli baru (skenario tanpa stok gudang).")
        kpi(r5[3], "Order Tercukupi Stok", num(s.get("stock_orders_total", 0)),
            f"dari {num(s['n_resi'])} resi", cls="green",
            help="Jumlah order yang bisa dipenuhi dari stok gudang tanpa pembelian baru.")

        # ---------- TARGET PROFIT vs MODAL (kelipatan modal/bulan) ----------
        st.markdown("##### 🎯 Target Profit vs Modal — bisakah profit 3–10× modal / bulan?")
        _mf = 30.0 / horizon if horizon else 1.0                 # normalisasi ke 30 hari
        prof_month = s["net_profit"] * _mf                        # laba bersih akrual /bulan
        ratio_now = (prof_month / modal0) if modal0 else 0.0
        GC = s["total_revenue"] - s["total_cogs"] - s["total_return_cost"]   # kontribusi kotor
        cr = (GC / s["budget_iklan"]) if s["budget_iklan"] > 0 else 0.0      # kontribusi/rupiah iklan
        opex_month = s["total_opex"] * _mf
        tt = st.columns([1, 3])
        target_mult = tt[0].slider("Target laba / bulan (× modal)", 1, 10, 3, key="p_target",
                                   help="Berapa kali lipat Modal Awal ingin Anda hasilkan sebagai "
                                        "laba bersih dalam sebulan.")
        tgt_profit = target_mult * modal0
        tr = st.columns(4)
        kpi(tr[0], "Laba/Bulan Sekarang", rp(prof_month),
            f"≈ {ratio_now:.2f}× modal", cls="green" if prof_month >= 0 else "amber",
            help="Laba bersih akrual dinormalkan ke 30 hari, dibagi Modal Awal.")
        kpi(tr[1], f"Target ({target_mult}× modal)", rp(tgt_profit),
            "laba bersih/bulan diinginkan")
        # budget yang dibutuhkan (ekstrapolasi linear: laba = budget×(cr−1) − opex)
        if cr > 1:
            bud_month_need = (tgt_profit + opex_month) / (cr - 1)
            bud_day_need = bud_month_need / 30.0
            scale = (bud_day_need / s["budget_harian"]) if s["budget_harian"] > 0 else float("inf")
            modal_need = s.get("modal_dibutuhkan", 0) * scale     # kasar: defisit ∝ belanja
            kpi(tr[2], "Butuh Budget Iklan", rp(bud_day_need) + "/hari",
                f"≈ {scale:.1f}× budget skarang", cls="amber",
                help="Estimasi budget iklan/hari agar target tercapai (ekstrapolasi dari efisiensi "
                     "kontribusi per rupiah iklan saat ini).")
            _cukup = modal_need <= modal0 * 1.05
            kpi(tr[3], "Perkiraan Modal Perlu", rp(modal_need),
                ("✓ modal cukup" if _cukup else f"⚠️ > modal ({rp(modal0)})"),
                cls="green" if _cukup else "amber",
                help="Perkiraan modal kerja pada skala target (defisit kas ~sebanding belanja).")
        else:
            kpi(tr[2], "Butuh Budget Iklan", "—", "belum bisa di-scale", cls="amber")
            kpi(tr[3], "Perkiraan Modal Perlu", "—", "perbaiki CM/CPL dulu", cls="amber")

        # verdict + lever
        if cr <= 1:
            st.markdown(
                f'<div class="insight">⚠️ <b>Belum layak di-scale.</b> Kontribusi kotor per rupiah '
                f'iklan baru <b>{cr:.2f}×</b> (≤ 1) — menambah budget justru menambah rugi. '
                f'Naikkan dulu: <b>CM</b> (turunkan HPP / naikkan harga), turunkan <b>CPL</b>, atau '
                f'naikkan <b>success delivery</b> sebelum mengejar target {target_mult}× modal.</div>',
                unsafe_allow_html=True)
        elif ratio_now >= target_mult:
            st.markdown(
                f'<div class="insight">✅ <b>Target tercapai.</b> Skenario saat ini sudah '
                f'≈ <b>{ratio_now:.2f}× modal/bulan</b> (≥ target {target_mult}×). Pertahankan '
                f'CM & CPL, dan pastikan stok + modal menopang volume ini.</div>',
                unsafe_allow_html=True)
        else:
            _ok = (cr > 1) and (modal_need <= modal0 * 1.05)
            _msg = ("✅ <b>Bisa dikejar dengan scaling.</b>" if _ok
                    else "⚠️ <b>Perlu modal/kombinasi lever.</b>")
            st.markdown(
                f'<div class="insight">{_msg} Untuk {target_mult}× modal (≈ {rp(tgt_profit)}/bulan), '
                f'naikkan budget ke <b>{rp(bud_day_need)}/hari</b> (≈ {scale:.1f}× sekarang) pada '
                f'produk <b>CM tertinggi</b>. Perkiraan modal kerja <b>{rp(modal_need)}</b>'
                f'{" — MASIH di bawah modal Anda ✓." if _ok else f" — di atas modal {rp(modal0)}. Opsi: tambah modal, pakai pencairan <b>H+1</b> (mode 1) agar COD cepat cair, turunkan HPP/CPL, atau tingkatkan success rate."}'
                f'</div>', unsafe_allow_html=True)
        st.caption("Estimasi ekstrapolasi linear — pakai sebagai arah, uji lewat tabel produk.")

        # ---------- CHART UTAMA: POSISI KAS ----------
        st.markdown("#### 📈 Posisi Kas Sepanjang Waktu")
        st.plotly_chart(viz.fig_cash_position(sim["timeline"], s), width='stretch')
        st.caption("Garis biru = posisi kas (Modal Awal + arus kas). Menembus 0 = modal kurang.")

        # ---------- P&L BULANAN ----------
        st.markdown("#### 🧾 Laba-Rugi (P&L) per Bulan")
        mdf = sim.get("monthly_pnl")
        if mdf is not None and not mdf.empty:
            pnl_tab = pd.DataFrame({
                "Bulan": mdf["label"],
                "Omzet": mdf["omzet"].map(rp),
                "HPP Terjual": mdf["hpp_terjual"].map(rp),
                "Iklan": mdf["iklan"].map(rp),
                "Opex": mdf["opex"].map(rp),
                "Retur": mdf["retur"].map(rp),
                "Laba Bersih": mdf["laba_bersih"].map(rp),
                "Laba Kumulatif": mdf["laba_kumulatif"].map(rp),
                "Arus Kas": mdf["arus_kas"].map(rp),
                "Saldo Kas Akhir": mdf["saldo_kas_akhir"].map(rp),
            })
            st.dataframe(pnl_tab, width='stretch', hide_index=True)
            st.caption("Laba Bersih = akrual; Saldo Kas Akhir = posisi kas akhir bulan (bisa beda "
                       "karena COD cair belakangan).")
            st.plotly_chart(viz.fig_monthly_pnl(mdf), width='stretch')

        # ---------- TABEL CASHFLOW HARIAN ----------
        st.markdown("#### 🧾 Tabel Cashflow Harian")
        _HARI = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
        _BLN = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
                7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}

        def _tgl(t):
            return f"{_HARI[t.weekday()]}, {t.day} {_BLN[t.month]} {t.year}"

        tlx = sim["timeline"].copy()
        tlx["saldo_akhir"] = tlx["kas_riil"]
        tlx["saldo_awal"] = tlx["kas_riil"] - tlx["net_cashflow"]
        tabel_cf = pd.DataFrame({
            "Tanggal": [_tgl(t) for t in tlx["tanggal"]],
            "Kas Masuk": tlx["cash_in"].map(rp),
            "Kas Keluar": tlx["cash_out"].map(rp),
            "Arus Kas": tlx["net_cashflow"].map(rp),
            "Saldo Awal": tlx["saldo_awal"].map(rp),
            "Saldo Akhir": tlx["saldo_akhir"].map(rp),
        })
        st.dataframe(tabel_cf, width='stretch', height=380, hide_index=True)
        st.caption("Saldo Awal hari-1 = Modal Awal. Saldo negatif = modal tak cukup hari itu.")

        with st.expander("🔍 Chart & detail tambahan (omzet harian, funnel, waterfall, settlement, akumulasi)"):
            st.plotly_chart(viz.fig_daily_omzet(sim["timeline"]), width='stretch')
            st.caption(f"Transfer ({fmt.persen((1-pct_cod/100)*100,0)} order) masuk hari kirim; "
                       f"COD ({pct_cod}% order) masuk saat cair (±{durasi_kirim:g} hari + jadwal J&T).")
            gg = st.columns(2)
            gg[0].plotly_chart(viz.fig_funnel(sim["funnel"]), width='stretch')
            gg[1].plotly_chart(viz.fig_expense_breakdown(s), width='stretch')
            g5 = st.columns(2)
            g5[0].plotly_chart(viz.fig_settlement_schedule(sim["timeline"]), width='stretch')
            g5[1].plotly_chart(viz.fig_payout_calendar(sim["timeline"]), width='stretch')
            st.plotly_chart(viz.fig_accumulation(sim["timeline"]), width='stretch')
            show = sim["timeline"].copy()
            show["tanggal"] = show["tanggal"].dt.strftime("%a %d %b %Y")
            st.dataframe(show.round(0), width='stretch', height=300)

        # ---------- (BAWAH) HASIL PER PRODUK & INSIGHT ----------
        st.markdown("---")
        st.markdown("#### 📦 Hasil Simulasi per Produk")
        pp_df = sim["per_product"].copy()
        if not pp_df.empty:
            show = pd.DataFrame({
                "Produk": pp_df["Produk"],
                "AoV": pp_df.get("aov", pp_df["nilai_produk"]).map(rp),
                "CM/order": pp_df.get("cm", pp_df["margin_jual_per_resi"]).map(rp),
                "CM%": pp_df.get("cm_pct", 0).round(0).map(lambda v: f"{v:.0f}%"),
                "Budget/Hari": pp_df["budget_harian"].map(rp),
                "Resi": pp_df["resi"].map(num),
                "Stok→Order": pp_df.get("orders_from_stock", 0).map(num),
                "Beli (kas)": pp_df.get("beli_hpp", pp_df["modal_hpp"]).map(rp),
                "Laba Bersih": pp_df["net_total"].map(rp),
                "ROI Iklan": (pp_df["roi"] * 100).round(0).map(lambda v: fmt.persen(v, 0)),
            })
            st.dataframe(show, width='stretch', height=300, hide_index=True)
            st.caption("**AoV** nilai jual/order • **CM** contribution margin/order • **Stok→Order** "
                       "dipenuhi stok (tanpa beli) • **Beli (kas)** beli produk di atas stok.")

    # ==================== SECTION 2: SKEMA PENYESUAIAN HARIAN ====================
    st.markdown("---")
    with st.container(border=True):
        section("🧮 SECTION 2 — SKEMA PENYESUAIAN HARIAN", cls="amber", anchor="sec-harian",
                desc="Atur ulang Budget Iklan, CPL, Petty Cash, bahkan Gaji di tanggal tertentu. "
                     "Semua dihitung ulang otomatis (termasuk pencairan COD yang cair belakangan). "
                     "Bandingkan hasilnya dengan Skema Global di Section 3.")
        st.caption("Nilai awal = Skema Global. Ubah sel mana pun untuk what-if; opex variabel/resi otomatis.")

        # --- parameter blended (tertimbang jumlah order) dari tabel produk ---
        _e = edited.copy()
        _bud = pd.to_numeric(_e["Budget/Hari"], errors="coerce").fillna(0)
        _cpl = pd.to_numeric(_e["CPL"], errors="coerce").fillna(0)
        _prc = pd.to_numeric(_e["Nilai Produk"], errors="coerce").fillna(0)
        _hpp = pd.to_numeric(_e["HPP"], errors="coerce").fillna(0)
        _leads_p = (_bud / _cpl.replace(0, np.nan)).fillna(0)
        _TL = float(_leads_p.sum())
        tot_budget_day = float(_bud.sum())
        eff_cpl = tot_budget_day / _TL if _TL else config.DEFAULTS["cpl"]
        _wl = (_leads_p / _TL) if _TL else pd.Series([1 / max(len(_prc), 1)] * len(_prc))
        nilai_bl = float((_prc * _wl).sum()) or baseline["avg_nilai_produk"]
        hpp_bl = float((_hpp * _wl).sum())
        g_daily = dict(modal_awal=modal_awal,
                       closing=closing, success=success, pct_cod=pct_cod / 100, ongkir=ongkir,
                       cashback=cashback_pct / 100 * ongkir, cod_fee_rate=cod_fee_pct / 100,
                       hpp=hpp_bl, nilai_produk=nilai_bl, mode=mode, daily_lag=lag,
                       opex_var_resi=opex_var_resi, opex_fix_bulan=opex_fix_bulan, payday=payday,
                       stock_orders_free=s.get("stock_orders_total", 0),
                       durasi_override=durasi_kirim, start_date=start_ts)

        start_cf = g_daily["start_date"]
        _tgl_list = [start_cf + pd.Timedelta(days=i) for i in range(horizon)]

        def _tgl_id(t):
            _H = {0: "Sen", 1: "Sel", 2: "Rab", 3: "Kam", 4: "Jum", 5: "Sab", 6: "Min"}
            _B = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
                  7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}
            return f"{_H[t.weekday()]}, {t.day} {_B[t.month]} {t.year}"

        _sched_cf = ce.payday_schedule(start_cf, horizon, payday, opex_fix_bulan)

        def _seed_cf():
            gaji_col = [int(round(_sched_cf.get(t.normalize(), 0))) for t in _tgl_list]
            return pd.DataFrame({
                "Tanggal": [_tgl_id(t) for t in _tgl_list],
                "Budget Iklan": [int(round(tot_budget_day))] * horizon,
                "CPL": [int(round(eff_cpl))] * horizon,
                "Petty Cash": [0] * horizon,
                "Gaji": gaji_col,
            })

        # Signature parameter global → bila berubah, baseline harian di-seed ulang agar
        # selalu mengikuti Skema Global (edit manual reset saat parameter global diubah).
        _sig = (f"{horizon}_{int(round(tot_budget_day))}_{int(round(eff_cpl))}_"
                f"{int(opex_fix_bulan)}_{payday}_{int(round(s.get('stock_orders_total',0)))}")
        _key = f"cf_edit_{_sig}"
        _edkey = f"cfed_{_sig}"
        if _key not in st.session_state:
            _pend = st.session_state.pop("_pending_daily", None)
            if _pend:            # penyesuaian harian dari planning yang dimuat
                try:
                    _pdf = pd.DataFrame(_pend)
                    st.session_state[_key] = _pdf if len(_pdf) == horizon else _seed_cf()
                except Exception:
                    st.session_state[_key] = _seed_cf()
            else:
                st.session_state[_key] = _seed_cf()
        cbtn = st.columns([5, 1])
        cbtn[0].caption(f"Range {horizon} hari sejak {_tgl_id(start_cf)}. Default: budget "
                        f"{rp(tot_budget_day)}/hari, CPL {rp(eff_cpl)}, gaji {rp(opex_fix_bulan)} di "
                        f"tgl gajian. Opex variabel {rp(opex_var_resi)}/resi tetap otomatis.")
        if cbtn[1].button("🔄 Reset harian", width='stretch'):
            st.session_state[_key] = _seed_cf()
            st.session_state.pop(_edkey, None)
            st.rerun()

        _mny = lambda lb: st.column_config.NumberColumn(lb, min_value=0, format="localized")
        ed_days = st.data_editor(
            st.session_state[_key], width='stretch', height=260, key=_edkey,
            column_config={
                "Tanggal": st.column_config.TextColumn("Tanggal", disabled=True),
                "Budget Iklan": _mny("Budget Iklan (Rp)"),
                "CPL": _mny("CPL (Rp)"),
                "Petty Cash": _mny("Petty Cash (Rp)"),
                "Gaji": _mny("Gaji (Rp)"),
            })

        day_rows = [{"budget": r["Budget Iklan"], "cpl": r["CPL"],
                     "opex": r["Petty Cash"], "gaji": r["Gaji"]}
                    for _, r in ed_days.iterrows()]
        res_cf = de.simulate_editable(day_rows, g_daily, recv_dist)
        tcf = res_cf["table"]

        hasil = pd.DataFrame({
            "Tanggal": [_tgl_id(t) for t in tcf["tanggal"]],
            "Budget Iklan": tcf["budget"].map(rp),
            "CPL": tcf["cpl"].map(rp),
            "Opex": tcf["opex"].map(rp),
            "Leads": tcf["leads"].map(num),
            "Resi Terkirim": tcf["resi"].map(num),
            "HPP": tcf["hpp"].map(rp),
            "Kas Masuk": tcf["cash_in"].map(rp),
            "Kas Keluar": tcf["cash_out"].map(rp),
            "Laba/Rugi": tcf["net"].map(rp),
            "Saldo Awal": tcf["saldo_awal"].map(rp),
            "Saldo Akhir": tcf["saldo_akhir"].map(rp),
        })
        st.dataframe(hasil, width='stretch', height=380, hide_index=True)
        st.caption(f"Saldo dimulai dari Modal Awal {rp(modal_awal)}. Ubah pengeluaran di tanggal "
                   "tertentu untuk melihat dampaknya ke saldo & pencairan hari-hari berikutnya.")
        mcf = st.columns(4)
        kpi(mcf[0], "Saldo Akhir Range", rp(res_cf["saldo_akhir"]),
            f"dari modal {rp(modal_awal)}", cls="green" if res_cf["saldo_akhir"] >= 0 else "amber")
        if res_cf.get("kas_habis"):
            kpi(mcf[1], "Kas Terendah", rp(res_cf["kas_terendah"]),
                "⚠️ modal kurang (sempat minus)", cls="amber")
        else:
            kpi(mcf[1], "Kas Terendah", rp(res_cf["kas_terendah"]),
                "✓ tak pernah minus", cls="green")
        kpi(mcf[2], "Total Kas Keluar (range)", rp(tcf["cash_out"].sum()), cls="amber")
        kpi(mcf[3], "⏳ Outstanding (cair setelah range)", rp(res_cf["outstanding"]),
            "COD order dalam range yg blm cair", cls="amber",
            help="Dana COD dari order selama range ini yang pencairannya jatuh SETELAH hari "
                 "terakhir range — tetap akan cair meski belanja iklan hanya di range ini.")

    # ==================== SECTION 3: PERBANDINGAN GLOBAL vs HARIAN ====================
    st.markdown("---")
    with st.container(border=True):
        section("⚖️ SECTION 3 — PERBANDINGAN: Global vs Penyesuaian Harian", cls="green",
                anchor="sec-banding",
                desc="Selisih posisi keuangan antara skema Global (baseline) dan skema Harian "
                     "(setelah Anda menyesuaikan pengeluaran per tanggal), dalam periode simulasi.")

        tl_h = sim["timeline"][sim["timeline"]["tanggal"] <= end_ts].copy()
        g_end = float(tl_h["kas_riil"].iloc[-1]); g_low = float(tl_h["kas_riil"].min())
        g_in = float(tl_h["cash_in"].sum()); g_out = float(tl_h["cash_out"].sum())
        d_end = float(res_cf["saldo_akhir"]); d_low = float(res_cf["kas_terendah"])
        d_in = float(tcf["cash_in"].sum()); d_out = float(tcf["cash_out"].sum())

        def _sel(v):
            if abs(v) < 1:
                return "— sama"
            return ("▲ " + rp(v)) if v > 0 else ("▼ " + rp(abs(v)))

        cmp_tab = pd.DataFrame({
            "Metrik": ["Saldo Kas Akhir", "Kas Terendah", "Total Kas Masuk",
                       "Total Kas Keluar", "Arus Kas Bersih (range)"],
            "Skema Global": [rp(g_end), rp(g_low), rp(g_in), rp(g_out), rp(g_in - g_out)],
            "Skema Harian": [rp(d_end), rp(d_low), rp(d_in), rp(d_out), rp(d_in - d_out)],
            "Selisih (Harian − Global)": [_sel(d_end - g_end), _sel(d_low - g_low),
                                          _sel(d_in - g_in), _sel(d_out - g_out),
                                          _sel((d_in - d_out) - (g_in - g_out))],
        })
        st.dataframe(cmp_tab, width='stretch', hide_index=True)

        _diff_end = d_end - g_end
        if abs(_diff_end) < 1:
            st.caption("Skema Harian saat ini identik dengan Skema Global (belum ada penyesuaian). "
                       "Ubah sel di tabel Section 2 untuk melihat dampaknya di sini.")
        else:
            _arah = "lebih tinggi" if _diff_end > 0 else "lebih rendah"
            st.caption(f"Dengan penyesuaian harian, saldo kas akhir **{_arah} {rp(abs(_diff_end))}** "
                       f"dibanding skema global. Grafik di bawah membandingkan lintasan kas keduanya.")

        g_saldo = tl_h.set_index("tanggal")["kas_riil"].reindex(tcf["tanggal"]).values
        st.plotly_chart(viz.fig_compare_saldo(tcf["tanggal"], g_saldo,
                                              tcf["saldo_akhir"].values, modal_awal), width='stretch')

    # ==================== PLANNING: simpan / muat / hapus (compact) ====================
    st.markdown("---")
    with st.container(border=True):
        st.markdown('<div id="sec-plan"></div>💾 **Planning** — simpan skenario '
                    '(parameter + tabel produk + penyesuaian harian), buka lagi kapan saja.',
                    unsafe_allow_html=True)
        _plans = planning.list_plans()
        pc = st.columns([3, 1, 3, 1, 0.7])
        plan_name = pc[0].text_input("Nama skenario", key="plan_name_input",
                                     placeholder="Nama skenario…", label_visibility="collapsed")
        if pc[1].button("💾 Simpan", width='stretch',
                        help="Simpan/perbarui skenario dgn nama di kiri."):
            if plan_name.strip():
                payload = {k: st.session_state.get(k) for k in _PLAN_KEYS}
                _pm = st.session_state.get("produk_current", st.session_state["produk_master"])
                payload["produk_master"] = _pm[_INCOLS].to_dict("records")
                payload["daily"] = ed_days.to_dict("records")   # penyesuaian harian ikut disimpan
                planning.save_plan(plan_name, payload)
                st.toast(f"Skenario '{plan_name}' tersimpan.")
            else:
                st.toast("Isi nama skenario dulu.", icon="⚠️")
        sel = pc[2].selectbox("Skenario", ["—"] + _plans, key="plan_select",
                              label_visibility="collapsed")
        if pc[3].button("📂 Muat", width='stretch', disabled=(sel == "—"),
                        help="Terapkan skenario ini ke semua input, tabel produk, & penyesuaian harian."):
            pl = planning.load_plan(sel)
            if pl:
                st.session_state["_pending_load"] = pl["data"]
                st.rerun()
        if pc[4].button("🗑", width='stretch', disabled=(sel == "—"), help="Hapus skenario terpilih."):
            planning.delete_plan(sel)
            st.session_state.pop("plan_select", None)
            st.rerun()

    st.markdown("#### 💡 Insight Otomatis")
    for line in insights.cashflow_insights(sim):
        st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

# =================================================================== MODUL 3
with tab2:
    prov = geo.province_summary(dff)
    tot_resi = int(prov["resi"].sum())
    tot_sampai = int(prov["sampai"].sum())
    tot_retur = int(prov["retur"].sum())
    sla_all = tot_sampai / tot_resi * 100 if tot_resi else 0
    retur_all = tot_retur / tot_resi * 100 if tot_resi else 0
    sig = prov[prov["resi"] >= 15]
    worst = sig.sort_values("retur_pct", ascending=False).iloc[0] if not sig.empty else None
    best = sig.sort_values("retur_pct").iloc[0] if not sig.empty else None

    avg_ongkir_all = float(dff["ongkir"].mean()) if "ongkir" in dff else 0.0
    avg_cashback_all = float(dff["biaya_diskon"].mean()) if "biaya_diskon" in dff else 0.0

    section("🗺️ Analisis Wilayah — Ringkasan Keputusan",
            "Sebaran resi, % sampai & retur per provinsi (pembagi = total resi). "
            "Fokuskan iklan di wilayah sehat, kurangi di wilayah retur tinggi.",
            cls="green")
    k = st.columns(4)
    kpi(k[0], "Total Resi", num(tot_resi), f"{prov['provinsi'].nunique()} provinsi")
    kpi(k[1], "% Sampai Rata²", fmt.persen(sla_all, 0), "sukses sampai konsumen",
        cls="green" if sla_all >= config.TARGET_SAMPAI_MIN else "amber",
        help="Paket 'Sampai Tujuan' ÷ total resi dikirim.")
    kpi(k[2], "% Retur Rata²", fmt.persen(retur_all, 0), f"{num(tot_retur)} paket retur",
        cls="green" if retur_all <= config.TARGET_RETUR_MAX else "amber",
        help="Paket 'Belum Diterima' tapi sudah ada Waktu Terima = diupayakan antar lalu "
             "dikembalikan. Sisanya (100−sampai−retur) masih transit.")
    if worst is not None:
        kpi(k[3], "⚠️ Perlu Perhatian", worst["provinsi"][:16],
            f"retur {worst['retur_pct']:.0f}% ({num(int(worst['retur']))} paket)", cls="amber")

    # ---- STANDAR REKOMENDASI + ONGKIR/CASHBACK ----
    st.markdown("##### 🎯 Standar Rekomendasi & Ongkir/Cashback")
    sc = st.columns(4)
    target_sampai = sc[0].number_input("Standar min % Sampai", 0, 100,
                                       int(config.TARGET_SAMPAI_MIN), step=5,
                                       help="Rekomendasi: minimal 60% paket sampai agar sehat.")
    target_retur = sc[1].number_input("Standar maks % Retur", 0, 100,
                                      int(config.TARGET_RETUR_MAX), step=5,
                                      help="Rekomendasi: maksimal 20% — selaras ambang GRATIS "
                                           "ongkir retur J&T. Di atasnya mulai kena biaya retur.")
    kpi(sc[2], "Rata² Ongkir Penuh", rp(avg_ongkir_all),
        "biaya kirim penuh per resi", cls="amber",
        help="Rata-rata ongkir penuh (Biaya Kirim) — ini uang titipan konsumen ke J&T, "
             "bukan pendapatan. Jadi acuan biaya & ongkir retur.")
    kpi(sc[3], "Rata² Cashback Diterima", rp(avg_cashback_all),
        "diskon ongkir dari J&T (omzet)", cls="green",
        help="Rata-rata cashback/diskon ongkir (Biaya Diskon) yang perusahaan terima "
             "dari J&T per resi — ini menjadi bagian omzet.")
    n_kritis = int(((sig["retur_pct"] > target_retur) | (sig["sla"] < target_sampai)).sum())
    st.caption(f"📌 **{n_kritis} dari {len(sig)} provinsi** (min 15 resi) melanggar standar "
               f"(retur > {target_retur}% atau sampai < {target_sampai}%). "
               f"Fokuskan perbaikan/pengurangan iklan di wilayah ini.")

    # ---- PETA ----
    st.markdown("##### Peta Sebaran")
    mc = st.columns([3, 1])
    metric_label = mc[1].selectbox("Warnai peta berdasarkan",
                                   ["Jumlah Resi", "Proyeksi Net", "% Retur",
                                    "Rata² Durasi", "Outstanding"])
    mm = {"Jumlah Resi": ("resi", False), "Proyeksi Net": ("proyeksi_net", False),
          "% Retur": ("retur_pct", True), "Rata² Durasi": ("avg_durasi", True),
          "Outstanding": ("outstanding", True)}
    metric, rev = mm[metric_label]
    gj = geo.load_geojson()
    fig_map = (viz.fig_choropleth(prov, gj, metric, metric_label, reverse=rev)
               if gj is not None else viz.fig_bubble_map(prov, metric, metric_label, reverse=rev))
    mc[0].plotly_chart(fig_map, width='stretch')
    mc[1].caption("🟢 baik · 🔴 buruk (Retur/Durasi/Outstanding: makin hijau makin rendah).")

    for line in insights.geography_insights(prov):
        st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

    # ---- WILAYAH BERMASALAH (retur) ----
    st.markdown("##### 🔴 Wilayah Bermasalah — Retur Tertinggi → Terendah")
    cc = st.columns([3, 2])
    cc[0].plotly_chart(viz.fig_retur_ranking(prov, 12), width='stretch')
    tblw = sig.sort_values("retur_pct", ascending=False)

    def _status(row):
        bad_r = row["retur_pct"] > target_retur
        bad_s = row["sla"] < target_sampai
        if bad_r and bad_s:
            return "🔴 Kritis"
        if bad_r:
            return "🟠 Retur tinggi"
        if bad_s:
            return "🟡 Sampai rendah"
        return "🟢 OK"

    show_w = pd.DataFrame({
        "Provinsi": tblw["provinsi"], "Resi": tblw["resi"].map(num),
        "Retur": tblw["retur"].map(num),
        "% Retur": tblw["retur_pct"].map(lambda v: fmt.persen(v, 0)),
        "% Sampai": tblw["sla"].map(lambda v: fmt.persen(v, 0)),
        "Status": tblw.apply(_status, axis=1),
    })
    cc[1].dataframe(show_w, width='stretch', height=380, hide_index=True)

    # ---- WILAYAH TERBAIK ----
    st.markdown("##### 🏆 Wilayah Terbaik (Volume & Margin)")
    t = st.columns(2)
    t[0].plotly_chart(viz.fig_top_bar(prov, "provinsi", 10, "resi", "Top 10 Provinsi (Resi)"),
                      width='stretch')
    t[1].plotly_chart(viz.fig_region_perf(prov, "provinsi"), width='stretch')

    # ---- DRILL DOWN ----
    st.markdown("##### 🔍 Detail Provinsi")
    psel = st.selectbox("Pilih Provinsi", prov["provinsi"].tolist())
    det = geo.province_detail(dff, psel)
    if det:
        d = st.columns(4)
        kpi(d[0], "Resi", num(det["resi"]), f"kota terbanyak: {det['top_kota']}")
        kpi(d[1], "% Sampai", fmt.persen(det["sla"], 0),
            cls="green" if det["sla"] >= config.TARGET_SAMPAI_MIN else "amber")
        kpi(d[2], "% Retur", fmt.persen(det["retur_pct"], 0), f"{num(det['retur'])} paket",
            cls="green" if det["retur_pct"] <= config.TARGET_RETUR_MAX else "amber")
        kpi(d[3], "Proyeksi Net", rp(det["proyeksi_net"]), cls="green")
        d2 = st.columns(4)
        kpi(d2[0], "Rata² Ongkir Penuh", rp(det.get("avg_ongkir", 0)), "per resi")
        kpi(d2[1], "Rata² Cashback", rp(det.get("avg_cashback", 0)), "diterima (omzet)",
            cls="green")
        kpi(d2[2], "Paket Sampai", num(det["sampai"]), cls="green")
        kpi(d2[3], "Rata² Durasi", f"{det['avg_durasi']} hari" if det.get("avg_durasi") else "-")
        cdet = geo.city_summary(dff, psel)
        st.plotly_chart(viz.fig_top_bar(cdet, "kota", 10, "resi", f"Top Kota — {psel}"),
                        width='stretch')

    with st.expander("📋 Tabel lengkap provinsi & distribusi durasi kirim"):
        st.dataframe(prov.round(1), width='stretch', height=300)
        e = st.columns(2)
        e[0].plotly_chart(viz.fig_duration_hist(dff), width='stretch')
        e[1].plotly_chart(viz.fig_duration_box(dff, "provinsi"), width='stretch')

# =================================================================== MODUL 3
with tab3:
    section("📦 Analisis Produk — Keputusan Cepat",
            "Winning & produk teraman dari katalog admin (nama SKU unik, closing/retur riil). "
            "Prioritaskan stok, modal & iklan pada produk inti (Pareto).",
            cls="purple")
    topc = st.columns([3, 1])
    _use_cat = _catalog is not None and not _catalog.empty
    if _use_cat:
        _pp = dict(ongkir=ongkir, cashback_pct=cashback_pct / 100,
                   cod_fee_rate=cod_fee_pct / 100, opex_var_resi=opex_var_resi)
        prod = prodeng.product_summary_catalog(_catalog, _pp)
        topc[0].caption("Sumber: **katalog admin** (nama SKU unik, closing & retur riil). "
                        "🏆 Winning = kontribusi margin terbesar • ✅ Aman = sampai tinggi, retur rendah.",
                        help="Margin/resi = margin kotor SEBELUM iklan (Nilai − HPP − Fee COD + "
                             "Cashback). Retur % & Sampai % memakai pembagi TOTAL resi per produk.")
    else:
        master = st.session_state.get("produk_master")
        hpp_map = (dict(zip(master["Produk"].astype(str),
                            pd.to_numeric(master["HPP"], errors="coerce").fillna(0)))
                   if master is not None and not master.empty else {})
        default_hpp = round(baseline["avg_nilai_produk"] * config.DEFAULTS["hpp_ratio"])
        prod = prodeng.product_summary(dff, hpp=default_hpp, hpp_map=hpp_map, use_clean=True)
        topc[0].caption("Sumber: histori all_resi (Nama Barang). 🏆 Winning = margin terbesar • "
                        "✅ Aman = sampai tinggi, retur rendah.")
    pareto_pct = topc[1].slider("Ambang Pareto (%)", 50, 95, 80, step=5)

    if prod.empty:
        st.warning("Data produk tidak tersedia (cek sheet Import-Order/Stock atau kolom Nama Barang).")
    else:
        if "closing_rate" not in prod.columns:
            prod["closing_rate"] = np.nan
        _p0 = lambda v: "–" if pd.isna(v) else fmt.persen(v, 0)
        pareto = prodeng.pareto_threshold(prod, pareto_pct)
        sigp = prod[(prod["resi"] >= 10) & prod["retur_pct"].notna()]
        win = prod.iloc[0]
        safe = (sigp.sort_values(["retur_pct", "sla"], ascending=[True, False]).iloc[0]
                if not sigp.empty else win)

        # ---- KPI keputusan ----
        r = st.columns(4)
        kpi(r[0], "🏆 Winning (Margin Terbaik)", win["produk"][:20],
            f"{fmt.persen(win['kontribusi_pct'])} net • {rp(win['margin_jual_per_resi'])}/resi",
            cls="green", help="Kontribusi net (margin kotor × volume) terbesar.")
        kpi(r[1], "✅ Produk Teraman", safe["produk"][:20],
            f"retur {_p0(safe['retur_pct'])} • sampai {_p0(safe['sla'])}", cls="green",
            help="Retur terendah & sampai tertinggi (min 10 resi, data pengiriman tersedia).")
        kpi(r[2], "Total Net Real", rp(prod["net_real"].sum()), f"{num(len(prod))} produk",
            cls="green", help="Total margin kotor seluruh produk (sebelum iklan).")
        kpi(r[3], f"Produk Inti (Pareto {pareto_pct}%)", num(pareto["n_produk_inti"]),
            f"{pareto['share_produk']:.0f}% produk = {pareto_pct}% net", cls="amber",
            help=f"{pareto['n_produk_inti']} dari {pareto['n_produk_total']} produk "
                 f"menyumbang {pareto_pct}% keuntungan — prioritaskan stok, modal & iklan di sini.")

        st.markdown("##### 💡 Insight Otomatis")
        for line in insights.product_insights(prod, pareto):
            st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

        # ---- Winning vs Aman (dua tabel berdampingan) ----
        st.markdown("##### 🏆 Winning Products  vs  ✅ Produk Teraman")
        cols = st.columns(2)
        wl = prod.head(10)
        cols[0].caption("🏆 Kontribusi margin terbesar — genjot iklannya")
        cols[0].dataframe(pd.DataFrame({
            "Produk": wl["produk"], "Resi": wl["resi"].map(num),
            "Net Real": wl["net_real"].map(rp),
            "Margin/Resi": wl["margin_jual_per_resi"].map(rp),
            "Closing": wl["closing_rate"].map(_p0),
            "Kontribusi": wl["kontribusi_pct"].map(lambda v: fmt.persen(v)),
            "Sampai": wl["sla"].map(_p0),
        }), width='stretch', height=380, hide_index=True)
        sl = (sigp.sort_values(["retur_pct", "sla"], ascending=[True, False]).head(10)
              if not sigp.empty else prod.head(10))
        cols[1].caption("✅ Sampai tinggi, retur rendah — paling minim risiko modal")
        cols[1].dataframe(pd.DataFrame({
            "Produk": sl["produk"], "Resi": sl["resi"].map(num),
            "Sampai": sl["sla"].map(_p0),
            "Retur": sl["retur_pct"].map(_p0),
            "Closing": sl["closing_rate"].map(_p0),
            "Margin/Resi": sl["margin_jual_per_resi"].map(rp),
        }), width='stretch', height=380, hide_index=True)

        st.plotly_chart(viz.fig_top_products(prod, 12, "net_real",
                        "🏆 Top 12 Produk — Kontribusi Net Real (Margin)"), width='stretch')

        with st.expander("📊 Kuadran (volume vs margin) & Pareto"):
            gp = st.columns([3, 2])
            gp[0].plotly_chart(viz.fig_quadrant(prodeng.quadrant(prod)), width='stretch')
            gp[1].plotly_chart(viz.fig_pareto(prod, 15), width='stretch')

        # ---- drill-down produk ----
        st.markdown("##### 🔍 Detail Produk")
        psel2 = st.selectbox("Pilih Produk", prod["produk"].tolist())
        row = prod[prod["produk"] == psel2].iloc[0]
        dd = st.columns(4)
        kpi(dd[0], "Resi", num(row["resi"]), f"AoV {rp(row['aov'])}",
            help="Total resi terkirim • AoV = nilai jual rata-rata per resi.")
        kpi(dd[1], "Margin/Resi (sblm iklan)", rp(row["margin_jual_per_resi"]),
            f"{fmt.persen(row['margin_pct'])} margin",
            cls="green" if row["margin_jual_per_resi"] >= 0 else "amber")
        kpi(dd[2], "Sampai / Retur", f"{_p0(row['sla'])} / {_p0(row['retur_pct'])}",
            f"closing {_p0(row['closing_rate'])}",
            cls="green" if (pd.notna(row["sla"]) and row["sla"] >= config.TARGET_SAMPAI_MIN)
            else "amber", help="Sampai% & Retur% memakai pembagi total resi produk.")
        kpi(dd[3], "Kontribusi Net", fmt.persen(row["kontribusi_pct"]),
            f"net {rp(row['net_real'])}", cls="green")

        with st.expander("📋 Tabel lengkap semua produk"):
            tbl = pd.DataFrame({
                "Produk": prod["produk"], "Resi": prod["resi"].map(num),
                "AoV": prod["aov"].map(rp),
                "Margin/Resi": prod["margin_jual_per_resi"].map(rp),
                "Margin %": prod["margin_pct"].map(lambda v: fmt.persen(v)),
                "Net Total": prod["net_real"].map(rp),
                "Kontribusi": prod["kontribusi_pct"].map(lambda v: fmt.persen(v)),
                "Closing": prod["closing_rate"].map(_p0),
                "Sampai": prod["sla"].map(_p0),
                "Retur": prod["retur_pct"].map(_p0),
            })
            st.dataframe(tbl, width='stretch', height=360, hide_index=True)

# =================================================================== MODUL TARGET
with tab4:
    section("🎯 Target Profit Simulator",
            "Tetapkan target laba & waktu → sistem hitung MUNDUR skenario (closing, CPL, budget) "
            "+ batas aman. Parameter dasar dari Tabel Produk & Parameter Global (Modul 1).",
            cls="amber")

    tc = st.columns([1, 1, 2])
    target_profit = rupiah_input(tc[0], "Target Laba Bersih (Rp)", 600_000_000, "in_target")
    target_days = int(tc[1].number_input("Target Waktu (hari)", min_value=1, max_value=3650,
                                         value=30, step=1, help="Bebas isi > 0 hari."))

    # --- rakit parameter dasar dari tabel produk + global (Modul 1) ---
    et = edited.copy()
    bud = pd.to_numeric(et["Budget/Hari"], errors="coerce").fillna(0)
    cplc = pd.to_numeric(et["CPL"], errors="coerce").fillna(0)
    prc = pd.to_numeric(et["Nilai Produk"], errors="coerce").fillna(0)
    hpc = pd.to_numeric(et["HPP"], errors="coerce").fillna(0)
    tot_bud = float(bud.sum())
    leads_day = float((bud / cplc.replace(0, np.nan)).sum())
    eff_cpl = tot_bud / leads_day if leads_day else config.DEFAULTS["cpl"]
    _nr = max(len(prc), 1)
    wgt = (bud / tot_bud) if tot_bud else pd.Series([1 / _nr] * len(prc))
    base = dict(
        nilai_produk=(float((prc * wgt).sum()) if len(prc) else 0) or baseline["avg_nilai_produk"],
        ongkir=ongkir, hpp=(float((hpc * wgt).sum()) if len(prc) else 0) or baseline["avg_nilai_produk"] * config.DEFAULTS["hpp_ratio"],
        cashback_pct=cashback_pct / 100, cod_fee_rate=cod_fee_pct / 100,
        pct_cod=pct_cod / 100, success=success, closing=closing,
        cpl=eff_cpl, budget_harian=tot_bud, opex_30=opex_fix_bulan,
    )
    # faktor likuiditas (fraksi COD yang cair ≤ T) — ambil dari 1x simulasi acuan
    syn0 = pd.DataFrame([{"Produk": "acuan", "Budget/Hari": max(base["budget_harian"], 1_000_000),
                          "CPL": base["cpl"] or config.DEFAULTS["cpl"],
                          "Nilai Produk": base["nilai_produk"], "HPP": base["hpp"]}])
    ov0 = dict(closing_rate=base["closing"], success_rate=base["success"], ongkir_per_resi=ongkir,
               cashback_pct=base["cashback_pct"], cod_fee_rate=base["cod_fee_rate"],
               pct_cod=base["pct_cod"], opex_fix_bulan=opex_fix_bulan,
               opex_var_resi=opex_var_resi, payday=payday, horizon_days=target_days,
               durasi_override=durasi_kirim, mode=mode, daily_lag=lag)
    s0 = ce.simulate_multi(baseline, recv_dist, syn0, ov0)["summary"]
    lam_cod, lam_ret = s0["lam_cod"], s0["lam_ret"]
    res = te.solve(target_profit, target_days, base, lam_cod, lam_ret)

    tc[2].markdown(
        f"<div class='insight'>🎯 <b>Target = laba bersih LIKUID</b>: kas yang benar-benar "
        f"sudah cair masuk rekening dalam {target_days} hari (bukan omzet/order). "
        f"Hanya <b>{fmt.persen(lam_cod*100,0)}</b> pencairan COD yang cair ≤ {target_days} hari "
        f"(sisanya outstanding). Proyeksi laba likuid skenario <b>saat ini</b> "
        f"≈ <b>{rp(res['laba_now'])}</b> vs target <b>{rp(target_profit)}</b>.</div>",
        unsafe_allow_html=True)

    if not res["profitable_per_lead"]:
        st.error("⚠️ Dengan unit-ekonomi saat ini, setiap rupiah iklan **belum** "
                 "menghasilkan laba likuid (K ≤ 1). Menambah budget justru memperbesar rugi — "
                 "perbaiki dulu closing/CPL/HPP/harga sebelum scaling.")

    st.markdown("##### 🧭 Strategi Mencapai Target (laba likuid)")
    st.caption("Empat jalur menuju target laba likuid yang sama (sudah memperhitungkan COD outstanding).")
    for opt in res["options"]:
        f = opt["funnel"]
        badge = "✅ Realistis" if opt["feasible"] else "⚠️ Sulit / perlu lever lain"
        cc = st.columns([2, 3])
        cc[0].markdown(f"**{opt['nama']}**  \n{badge}  \n**{opt['ubah']}**")
        cc[1].markdown(
            f"<div style='font-size:.85rem'>{opt['catatan']}<br>"
            f"Leads <b>{num(f['leads'])}</b> → Order <b>{num(f['orders'])}</b> → "
            f"Resi <b>{num(f['resi'])}</b> • Estimasi omzet <b>{rp(f['omzet'])}</b> • "
            f"Budget <b>{rp(f['budget_total'])}</b></div>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:4px 0;border-color:#2A3142'>", unsafe_allow_html=True)

    # --- Batas aman (guardrail AND) ---
    L = res["limits"]
    if L:
        st.markdown("##### 🛡️ Batas Aman — Harus Terpenuhi **Bersamaan** (AND)")
        st.caption("Semua batas berikut harus terpenuhi sekaligus; salah satu meleset → target "
                   f"berpotensi gagal. Titik impas per parameter (budget ≈ {rp(L.get('budget_ref',0)/target_days)}/hari).")
        gl = st.columns(4)
        kpi(gl[0], "HPP Maksimal / produk", "≤ " + rp(L.get("hpp_max", 0)),
            f"skrg {rp(base['hpp'])}", cls="green",
            help="HPP tertinggi yang masih membuat rencana impas. Di atasnya target gagal.")
        kpi(gl[1], "Harga Jual Minimal", "≥ " + rp(L.get("price_min", 0)),
            f"skrg {rp(base['nilai_produk'])}", cls="green",
            help="Harga jual terendah sebelum rencana rugi.")
        kpi(gl[2], "Opex Tetap Maks / bulan", "≤ " + rp(L.get("opex_30_max", 0)),
            f"skrg {rp(base['opex_30'])}", cls="green",
            help="Batas opex tetap bulanan (gaji dll) sebelum target gagal.")
        kpi(gl[3], "Retur Maksimal", "≤ " + fmt.persen(L.get("return_max", 0) * 100, 0),
            f"skrg {fmt.persen((1-base['success'])*100,0)}", cls="green",
            help="Persentase retur tertinggi yang masih impas.")

    # --- Detail eksekusi salah satu opsi (pakai engine nyata) ---
    st.markdown("##### 🔎 Detail Eksekusi & Kebutuhan (dana yang benar-benar cair)")
    feas = [o for o in res["options"] if o["feasible"]] or res["options"]
    pick = st.selectbox("Pilih strategi untuk dihitung detail (modal, pencairan, cashflow)",
                        [o["nama"] for o in feas])
    chosen = next(o for o in feas if o["nama"] == pick)
    sc = chosen["scenario"]
    syn = pd.DataFrame([{
        "Produk": "Skenario Target", "Budget/Hari": sc["budget_harian"],
        "CPL": sc["cpl"], "Nilai Produk": sc["nilai_produk"], "HPP": sc["hpp"]}])
    ov_t = dict(closing_rate=sc["closing"], success_rate=sc["success"], ongkir_per_resi=ongkir,
                cashback_pct=sc["cashback_pct"], cod_fee_rate=sc["cod_fee_rate"],
                pct_cod=sc["pct_cod"], opex_fix_bulan=opex_fix_bulan,
                opex_var_resi=opex_var_resi, payday=payday, horizon_days=target_days,
                durasi_override=durasi_kirim, mode=mode, daily_lag=lag)
    st_ = ce.simulate_multi(baseline, recv_dist, syn, ov_t)
    simt, st_ = st_, st_["summary"]
    d1 = st.columns(4)
    kpi(d1[0], "Total Omzet (dikirim)", rp(st_["total_revenue"]),
        "seluruh paket terkirim", cls="green",
        help="Total nilai penjualan paket terkirim (belum tentu semua cair dalam horizon).")
    kpi(d1[1], "Total Kas Keluar", rp(st_["cash_out_horizon"]),
        "iklan+HPP+opex+retur", cls="amber",
        help="Seluruh uang yang keluar selama horizon: iklan, beli produk, operasional, ongkir retur.")
    kpi(d1[2], "Kas Masuk LIKUID", rp(st_["cash_in_likuid"]),
        f"cair ≤ {target_days} hari", cls="green",
        help="Uang yang benar-benar sudah cair masuk rekening dalam horizon (transfer + COD yang settle ≤ T).")
    kpi(d1[3], "Outstanding (belum cair)", rp(st_["outstanding_dana"]),
        "COD nunggu terima+settle", cls="amber",
        help="Dana COD yang sudah jadi penjualan tapi belum cair di akhir horizon.")
    d2 = st.columns(4)
    kpi(d2[0], "⭐ Laba Bersih LIKUID", rp(st_["laba_likuid"]),
        "vs target " + rp(target_profit),
        cls="green" if st_["laba_likuid"] >= target_profit * 0.98 else "amber",
        help="Kas masuk likuid − kas keluar. Inilah 'laba yang benar-benar sudah cair' "
             "sesuai target Anda.")
    kpi(d2[1], "Laba Akrual (semua sales)", rp(st_["net_profit"]),
        "termasuk yg blm cair",
        help="Laba bila SEMUA penjualan (termasuk outstanding) dihitung — selalu ≥ laba likuid.")
    kpi(d2[2], "⭐ Modal Kerja Dibutuhkan", rp(st_["modal_dibutuhkan"]),
        "defisit kas terdalam (talangan)", cls="amber")
    bm2 = st_.get("hari_balik_modal")
    kpi(d2[3], "Balik Modal", f"H+{bm2}" if bm2 is not None else "> horizon",
        cls="green" if bm2 is not None else "amber")
    d3 = st.columns(4)
    kpi(d3[0], "Leads", num(st_["n_lead"]))
    kpi(d3[1], "Order", num(st_["n_order"]))
    kpi(d3[2], "Resi Sampai", num(st_["n_sukses"]),
        f"dari {num(st_['n_resi'])} dikirim")
    kpi(d3[3], "Budget Iklan", rp(st_["budget_iklan"]), f"{rp(st_['budget_harian'])}/hari")
    st.plotly_chart(viz.fig_cash_journey(simt["timeline"], st_), width='stretch')

# =================================================================== MODUL 5
with tab5:
    section("📣 Analisis Iklan Meta — Performa Campaign per Produk",
            "Real per rentang tanggal: biaya iklan (Meta-Ads) vs leads, closing & omzet "
            "(OrderOnline). Sistem menandai produk mana untuk di-scale atau dimatikan.",
            cls="teal")

    if _META is None or len(_META) == 0:
        st.info("Belum ada data iklan. Pasang **MetaAds.gs** di Apps Script (lihat "
                "`JnT_GSheet_System/PANDUAN_META_ADS.md`), tarik data, lalu muat ulang. "
                "Sheet `Meta-Ads` akan otomatis terbaca di sini.")
    else:
        import datetime as _dt
        _dmin, _dmax = meng.date_bounds(_META)
        _dmax = _dmax or _dt.date.today()
        _dmin = _dmin or (_dmax - _dt.timedelta(days=30))
        fc = st.columns([1, 1, 1, 3])
        m_since = fc[0].date_input("Dari (tgl iklan / order)", value=max(_dmin, _dmax - _dt.timedelta(days=30)),
                                   min_value=_dmin, max_value=_dmax, key="m_since")
        m_until = fc[1].date_input("Sampai", value=_dmax, min_value=_dmin, max_value=_dmax, key="m_until")
        target_roi = fc[2].number_input("Target ROI (%)", 0, 2000, 40, step=10, key="m_roi",
                                        help="ROI = laba ÷ spend. Verdict 🟢 Scale bila ROI ≥ target ini, "
                                             "🟡 Optimize bila 0–target, 🔴 Kill bila ROI < 0. "
                                             "Beda dari ROAS (yang pakai omzet, bukan laba).")
        _mp = dict(ongkir=ongkir, cashback_pct=cashback_pct / 100,
                   cod_fee_rate=cod_fee_pct / 100, opex_var_resi=opex_var_resi,
                   success_default=success, target_roi=target_roi)
        R = meng.campaign_perf(_META, _OO_RESOLVED, _catalog, _mp, m_since, m_until)

        # --- Diagnostik: bandingkan dengan dashboard Apps Script bila angkanya beda
        with st.expander("🔎 Diagnostik data Meta-Ads (buka bila angka beda dengan Apps Script)"):
            _m = _META
            _gid = str(getattr(config, "GSHEET_ID", "") or "—")
            _gid_show = (_gid[:6] + "…" + _gid[-4:]) if len(_gid) > 12 else _gid
            _d = _m["date"] if "date" in _m else None
            _nat = int(_d.isna().sum()) if _d is not None else -1
            st.markdown(
                f"**Sumber:** `{'Google Sheet (live)' if _use_gsheet() else 'Excel'}` • "
                f"**GSHEET_ID:** `{_gid_show}` • **baris Meta-Ads:** `{len(_m):,}` • "
                f"**tanggal gagal parse (NaT):** `{_nat}`".replace(",", "."))
            _tu = (data.get("tabs_used") or {}).get("meta")
            if _tu:
                st.markdown(f"**Tab yang terbaca:** `{_tu}`")
            _sh = data.get("sheets")
            if _sh:
                _cand = [s for s in _sh if "meta" in str(s).lower()]
                if len(_cand) > 1:
                    st.warning(f"Ada **lebih dari satu** tab mirip Meta-Ads: `{_cand}`. "
                               "Sistem memakai yang pertama cocok — pastikan itu yang benar.")
            if _d is not None and _d.notna().any():
                st.markdown(f"**Cakupan tanggal:** `{_d.min():%d %b %Y}` – `{_d.max():%d %b %Y}`")
            if _nat > 0:
                st.error(f"{_nat} baris punya tanggal tak terbaca sehingga **hilang dari filter**. "
                         "Contoh nilai mentahnya:")
                st.write(list(_m.loc[_d.isna(), "date"].astype(str).head(5)))
            # Rekap per match_status pada rentang terpilih — ini yang dibandingkan
            try:
                _sel = _m[(_d >= pd.Timestamp(m_since)) & (_d <= pd.Timestamp(m_until))]
                _rk = (_sel.assign(_s=_sel.get("match_status", "—"))
                       .groupby("_s")
                       .agg(baris=("_s", "size"), spend=("spend", "sum"),
                            purchase=("purchases", "sum")).reset_index()
                       .rename(columns={"_s": "match_status"}))
                st.caption("Rekap rentang terpilih per status. Baris **TERKUNCI** inilah yang "
                           "muncul di dashboard Apps Script — cocokkan angkanya.")
                st.dataframe(_rk, hide_index=True, width='stretch')
            except Exception as _e:
                st.caption(f"Rekap gagal dihitung: {_e}")

        if not R["ada"] or R["produk"].empty:
            st.warning("Tidak ada iklan produk yang terpetakan pada rentang ini.")
        else:
            g = R["produk"]; tot = R["total"]
            fc[3].markdown(
                f"<div class='insight'>Rentang <b>{m_since:%d %b}</b>–<b>{m_until:%d %b %Y}</b>: "
                f"spend <b>{rp(tot['spend'])}</b> → <b>{num(tot['leads'])}</b> leads, "
                f"<b>{num(tot['closing'])}</b> closing, omzet <b>{rp(tot['omzet'])}</b> • "
                f"ROAS <b>{tot['roas']:.2f}×</b> • ROI <b>{tot['roi']:.0f}%</b>. "
                f"Est. laba <b>{rp(tot['profit'])}</b>.</div>",
                unsafe_allow_html=True)

            n_scale = int(g["verdict"].str.contains("Scale").sum())
            n_opt = int(g["verdict"].str.contains("Optimize").sum())
            n_kill = int(g["verdict"].str.contains("Kill").sum())
            k = st.columns(5)
            kpi(k[0], "Total Spend", rp(tot["spend"]), f"{tot['n_produk']} produk", cls="amber",
                help="Belanja iklan produk terpetakan pada rentang ini.")
            kpi(k[1], "Leads → Closing", f"{num(tot['leads'])} → {num(tot['closing'])}",
                f"closing rate {fmt.persen(tot['closing']/tot['leads']*100,0) if tot['leads'] else '–'}",
                help="Leads & closing OrderOnline (paid & completed/processing) di rentang created_at.")
            kpi(k[2], "Omzet & ROAS", rp(tot["omzet"]),
                f"ROAS {tot['roas']:.2f}×" if pd.notna(tot["roas"]) else "ROAS –",
                cls="green" if (tot.get("roas") or 0) >= 1 else "amber",
                help="Omzet = Σ product_price order closing. ROAS = omzet ÷ spend.")
            kpi(k[3], "Est. Laba", rp(tot["profit"]),
                "closing × margin − spend", cls="green" if tot["profit"] >= 0 else "red",
                help="Laba estimasi: closing × margin kotor/order (dari katalog) − spend iklan.")
            kpi(k[4], "🟢/🟡/🔴", f"{n_scale} / {n_opt} / {n_kill}", "Scale / Opt / Kill",
                cls="green" if n_scale >= n_kill else "amber")

            k2 = st.columns(4)
            kpi(k2[0], "Rata² Cost/Purchase Meta", rp(tot["avg_cpp_meta"]) if pd.notna(tot["avg_cpp_meta"]) else "–",
                f"{num(tot['purchases'])} purchase (pixel)", cls="amber",
                help="Total spend ÷ total purchase yang dilaporkan Pixel Meta. Biaya per 'order web' "
                     "versi Meta — belum tentu = order nyata yang masuk sistem.")
            kpi(k2[1], "CPA Real (closing OO)", rp(tot["cpa_real"]) if pd.notna(tot["cpa_real"]) else "–",
                f"{num(tot['closing'])} closing", cls="green" if pd.notna(tot["cpa_real"]) else "",
                help="Total spend ÷ total closing OrderOnline (paid & completed). Biaya akuisisi NYATA "
                     "per order yang benar-benar terbayar — acuan utama profitabilitas.")
            kpi(k2[2], "ROI Iklan Total", f"{tot['roi']:.0f}%" if pd.notna(tot["roi"]) else "–",
                "laba ÷ spend", cls="green" if (tot.get("roi") or 0) >= 0 else "red",
                help="ROI = est. laba ÷ spend × 100%. 0% = balik modal. Berbeda dari ROAS "
                     "(ROAS pakai omzet/pendapatan, ROI pakai laba setelah HPP).")
            kpi(k2[3], "Selisih Purchase Meta vs Leads OO",
                f"{tot['loss_pct']:.0f}%" if pd.notna(tot["loss_pct"]) else "–",
                f"{num(tot['purchases'])} purchase vs {num(tot['leads'])} leads",
                cls="amber" if (tot.get("loss_pct") or 0) > 0 else "",
                help="(purchase Meta − leads OrderOnline) ÷ purchase Meta × 100%. Positif = Meta "
                     "melaporkan lebih banyak purchase daripada lead yang benar-benar masuk OrderOnline "
                     "(indikasi over-count Pixel / lead bocor / beda atribusi). Idealnya mendekati 0%.")

            _w = []
            if R["unmatched_spend"] > 0:
                _w.append(f"**{rp(R['unmatched_spend'])}** spend pada campaign **belum terpetakan** "
                          "ke produk (mis. campaign TOF/prospek/event). Labeli di `Ref_Ads_Map` "
                          "(`locked=TRUE`) bila ingin dihitung per produk.")
            if R["excluded_spend"] > 0:
                _w.append(f"**{rp(R['excluded_spend'])}** spend pada campaign **DIKECUALIKAN** (sengaja).")
            if _w:
                st.caption("⚠️ " + "  •  ".join(_w))

            # ---- tabel performa per produk ----
            st.markdown("##### 🧭 Performa & Keputusan per Produk")
            st.caption("Penanda sumber data: **MA** = Meta Ads · **OO** = OrderOnline · **JNT** = J&T. "
                       "Verdict dari **skor gabungan CM% + Closing Rate + Retur** (bobot 50/30/20): "
                       "🟢 Scale ≥70 • 🟡 Optimize 40–69 • 🔴 Kill <40. "
                       "Aturan keras: CM/Order ≤ 0 atau tanpa closing → langsung Kill. "
                       "Arahkan kursor ke judul kolom untuk cara hitungnya.")
            _rp = lambda v: rp(v) if pd.notna(v) else "–"
            _pc = lambda v: f"{v:.1f}%" if pd.notna(v) else "–"
            show = pd.DataFrame({
                "Produk": g["produk"], "Verdict": g["verdict"],
                "Skor": g["skor"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "–"),
                # ---- Meta Ads ----
                "Spend - MA": g["spend"].map(rp),
                "Budget/Hari - MA": g["daily_budget"].map(rp),
                "CPM - MA": g["cpm"].map(_rp),
                "CTR - MA": g["ctr"].map(lambda v: f"{v:.2f}%" if pd.notna(v) else "–"),
                "CPC - MA": g["cpc"].map(_rp),
                "Klik - MA": g["clicks"].map(num),
                "Link Klik - MA": g["link_click"].map(num),
                "LPV - MA": g["landing_page_view"].map(num),
                "Purchase - MA": g["purchases"].map(num),
                "Cost/Purchase - MA": g["cost_per_purchase"].map(_rp),
                # ---- OrderOnline ----
                "Leads - OO": g["leads"].map(num),
                "Closing - OO": g["closing"].map(num),
                "Closing Rate - OO": g["closing_rate"].map(_pc),
                "Omzet - OO": g["omzet"].map(rp),
                # ---- J&T ----
                "Retur % - JNT": g["retur_pct"].map(_pc),
                # ---- turunan ----
                "Pcs Terjual": g["pcs_terjual"].map(num),
                "Cost/Closing": g["cost_per_closing"].map(_rp),
                "Impas/Closing": g["breakeven_cpa"].map(_rp),
                "CM/Order": g["cm_per_order"].map(_rp),
                "CM %": g["cm_pct"].map(_pc),
                "ROAS": g["roas"].map(lambda v: f"{v:.2f}×" if pd.notna(v) else "–"),
                "ROI": g["roi"].map(lambda v: f"{v:.0f}%" if pd.notna(v) else "–"),
                "Laba": g["profit"].map(_rp),
                "Aksi": g["aksi"],
            })
            _tc = st.column_config.TextColumn
            _tips = {
                "Produk": "Nama barang unik (SKU). Iklan digabung dari semua campaign produk ini.",
                "Verdict": "Rekomendasi otomatis dari skor. Aturan keras: rugi per order atau tanpa closing → Kill.",
                "Skor": "0–100. Gabungan CM% (bobot 50%), Closing Rate (30%), dan Retur (20%). "
                        "Bila salah satu datanya tidak ada, bobot dihitung ulang dari yang tersedia.",
                "Spend - MA": "Meta Ads. Total belanja iklan produk ini pada rentang tanggal.",
                "Budget/Hari - MA": "Meta Ads. Jumlah daily_budget semua campaign aktif produk ini (snapshot).",
                "CPM - MA": "Meta Ads. Biaya per 1.000 impresi = spend ÷ impresi × 1.000.",
                "CTR - MA": "Meta Ads. Klik ÷ impresi × 100%.",
                "CPC - MA": "Meta Ads. Spend ÷ klik.",
                "Klik - MA": "Meta Ads. Total semua klik iklan.",
                "Link Klik - MA": "Meta Ads. Klik menuju link/landing (bagian dari total klik).",
                "LPV - MA": "Meta Ads. Landing page view — halaman benar-benar termuat.",
                "Purchase - MA": "Meta Ads. Purchase versi Pixel (satu nilai kanonik, bukan penjumlahan alias). "
                                 "Sering LEBIH BESAR dari lead nyata — jangan dipakai untuk keuangan.",
                "Cost/Purchase - MA": "Meta Ads. Spend ÷ purchase Pixel. Biasanya terlihat lebih murah dari CPA nyata.",
                "Leads - OO": "OrderOnline. Order/lead masuk pada rentang created_at yang sama, dipetakan ke SKU ini.",
                "Closing - OO": "OrderOnline. Lead yang paid & status completed/processing = order COD terbayar.",
                "Closing Rate - OO": "OrderOnline. Closing ÷ Leads × 100%. Efisiensi CS mengubah lead jadi order.",
                "Omzet - OO": "OrderOnline. Σ product_price dari order closing (pendapatan nyata).",
                "Retur % - JNT": "J&T. Paket retur ÷ TOTAL resi produk ini (bukan hanya sampai+retur). "
                                 "Tidak dikalikan lagi ke margin — dipakai sebagai penalti skor karena retur "
                                 "membakar ongkir, stok, dan waktu CS.",
                "Pcs Terjual": "Qty order closing × pcs per order (dari katalog admin). Berguna untuk rencana stok.",
                "Cost/Closing": "CPA nyata = spend ÷ closing OO. Acuan utama, bukan Cost/Purchase Meta.",
                "Impas/Closing": "Margin kotor per order dari katalog (Nilai − HPP − fee COD + cashback). "
                                 "Batas CPA sebelum rugi.",
                "CM/Order": "Laba bersih per order setelah biaya iklan = Impas − Cost/Closing. "
                            "Kalau ≤ 0, menambah budget memperbesar kerugian.",
                "CM %": "CM/Order ÷ nilai jual × 100%. Ketebalan margin — penggerak skor terbesar.",
                "ROAS": "Omzet ÷ spend. Berbasis pendapatan, BUKAN laba — bisa terlihat bagus padahal rugi.",
                "ROI": "Laba ÷ spend × 100%. Laba = closing × margin − spend. 0% = balik modal.",
                "Laba": "Estimasi laba rentang ini = closing × margin kotor/order − spend.",
                "Aksi": "Tindakan yang disarankan, menyebut penyebab terlemah dari ketiga penggerak skor.",
            }
            _cfg = {k: _tc(help=v, width=("large" if k == "Aksi" else
                                          "medium" if k == "Produk" else None))
                    for k, v in _tips.items()}
            st.dataframe(show, width='stretch', height=460, hide_index=True, column_config=_cfg)

            # ---- insight ringkas ----
            tips = []
            _sc = g[g["verdict"].str.contains("Scale")].sort_values("profit", ascending=False)
            if not _sc.empty:
                w = _sc.iloc[0]
                tips.append(f"🟢 **Scale: {w['produk']}** — {w['aksi']}")
            _kl = g[g["verdict"].str.contains("Kill") & g["profit"].notna()].sort_values("profit")
            if not _kl.empty:
                l = _kl.iloc[0]
                tips.append(f"🔴 **Kill: {l['produk']}** — {l['aksi']}")
            _spend_kill = g[g["verdict"].str.contains("Kill")]["spend"].sum()
            if _spend_kill > 0:
                tips.append(f"💸 Total **{rp(_spend_kill)}** spend berada di produk berstatus Kill — "
                            "realokasi ke produk Scale/Optimize.")
            for t in tips:
                st.markdown(f'<div class="insight">• {t}</div>', unsafe_allow_html=True)

            # ---- drilldown per campaign ----
            st.markdown("##### 🔍 Rincian per Campaign")
            psel5 = st.selectbox("Pilih produk", g["produk"].tolist(), key="m_prod")
            _row = g[g["produk"] == psel5].iloc[0]
            _key = _row["sku"] if str(_row["sku"]).strip() not in ("", "nan") else _row["produk"]
            cd = meng.campaign_detail(_META, _key, _mp, m_since, m_until)
            if cd.empty:
                st.caption("Tidak ada campaign untuk produk ini pada rentang tanggal.")
            else:
                st.dataframe(pd.DataFrame({
                    "Campaign": cd["campaign_name"], "Spend": cd["spend"].map(rp),
                    "Purchase": cd["purchases"].map(num),
                    "Cost/Purchase": cd["cost_per_purchase"].map(_rp),
                    "CTR": cd["ctr"].map(lambda v: f"{v:.2f}%" if pd.notna(v) else "–"),
                    "Budget/Hari": cd["daily_budget"].map(rp),
                    "Status": cd.get("status", ""),
                }), width='stretch', height=280, hide_index=True)


st.markdown("---")
st.caption(f"{config.APP_TITLE} • {config.COMPANY} • dibuat dengan Streamlit + Plotly • "
           "100% lokal/offline")
