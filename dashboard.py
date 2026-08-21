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
.block-container {{ padding-top:1.2rem; padding-bottom:2rem; max-width:1500px; }}
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
            padding:10px 16px; margin:6px 0 10px 0; }}
.section-banner .st {{ color:{T['text']}; font-size:1.05rem; font-weight:700; }}
.section-banner .sd {{ color:{T['muted']}; font-size:.78rem; margin-top:2px; }}
.section-banner.amber {{ background:linear-gradient(90deg,{T['amber']}22,{T['card']});
            border-left-color:{T['amber']}; }}
.section-banner.green {{ background:linear-gradient(90deg,{T['green']}22,{T['card']});
            border-left-color:{T['green']}; }}
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
    a = (f'<div id="{anchor}" style="position:relative;top:-70px;visibility:hidden;"></div>'
         if anchor else "")
    st.markdown(
        f'{a}<div class="section-banner {cls}"><div class="st">{title}</div>'
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
@st.cache_data(show_spinner="Membaca & memproses data Excel terbaru...")
def load_data(_mtime: float):
    raw = data_loader.load_workbook()
    return data_cleaning.clean_all(raw)


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


@st.cache_data(show_spinner="Menarik data live dari Google Sheet...")
def load_data_gsheet(_nonce: int):
    raw = data_loader.load_workbook()          # otomatis ke gsheet via config
    return data_cleaning.clean_all(raw)


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
_hc[1].caption(f"Sumber: **{_src}** • {len(df_all):,} resi • data "
               f"{dmin:%d %b %Y}–{dmax:%d %b %Y}".replace(",", "."))
if _hc[2].button("🔄 Muat ulang", width='stretch'):
    st.session_state["gsheet_nonce"] = st.session_state.get("gsheet_nonce", 0) + 1
    st.cache_data.clear()
    st.rerun()

tab1, tab4, tab2, tab3 = st.tabs(["💰 Modul 1 — Simulator Cashflow & Pencairan",
                                  "🎯 Modul 2 — Target Profit Simulator",
                                  "🗺️ Modul 3 — Analisis Wilayah",
                                  "📦 Modul 4 — Analisis Produk"])

# ---- katalog produk dari sheet admin (Import-Order + Import-Stock + retur) ----
_catalog = padmin.build_catalog(data.get("order"), data.get("stock"), df_all)
# Kolom input (editable) + kolom turunan (disabled)
_INCOLS = ["Produk", "Budget/Hari", "CPL", "Nilai Produk", "HPP", "Stok (pcs)", "Pcs/Order"]
_DERIVED = ["CM", "CM%", "Retur %"]
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
            closing=config.DEFAULTS["closing_rate"],
            success=baseline.get("success_rate", config.DEFAULTS["success_rate"]),
            ongkir=baseline.get("avg_total_biaya", config.DEFAULTS["ongkir_per_resi"]),
            cashback_pct=baseline.get("cashback_pct", config.DEFAULTS["cashback_pct"]),
            cod_fee_rate=baseline.get("cod_fee_rate", config.DEFAULTS["cod_fee_rate"]),
            opex_var_resi=0, horizon=config.DEFAULTS["horizon_days"])
        return padmin.optimize_table(_catalog, pr)[_PCOLS].copy()
    t = prodeng.seed_product_table(
        df_all, top_n=25, total_budget_harian=config.DEFAULTS["budget_harian"],
        default_cpl=config.DEFAULTS["cpl"], hpp_ratio=config.DEFAULTS["hpp_ratio"])
    t["Stok (pcs)"] = 0
    t["Pcs/Order"] = 1
    _nj = pd.to_numeric(t["Nilai Produk"], errors="coerce").fillna(0)
    _hp = pd.to_numeric(t["HPP"], errors="coerce").fillna(0)
    t["CM"] = (_nj - _hp).round().astype(int)
    t["CM%"] = ((_nj - _hp) / _nj.replace(0, np.nan) * 100).round(1)
    t["Retur %"] = np.nan
    return t[_PCOLS]


def _recompute_derived(dfp, ongkir_, cb_pct_, fee_pct_, ovar_):
    """Hitung ulang CM & CM% dari kolom input (live); Retur % tetap dari data."""
    d = dfp.copy()
    nj = pd.to_numeric(d.get("Nilai Produk"), errors="coerce").fillna(0)
    hp = pd.to_numeric(d.get("HPP"), errors="coerce").fillna(0)
    cm = nj - hp - (fee_pct_ / 100) * (nj + ongkir_) + (cb_pct_ / 100) * ongkir_ - ovar_
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
            st.session_state["produk_master"] = pd.DataFrame(_d["produk_master"])
        st.session_state.pop("editor_master", None)
        for _kk in [k for k in st.session_state if str(k).startswith(("cf_edit_", "cfed_"))]:
            st.session_state.pop(_kk, None)

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
        closing = g1.slider("Closing Order (%)", 0, 100,
                            int(config.DEFAULTS["closing_rate"] * 100), key="p_closing") / 100
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
            "Rata² Durasi Kirim (hari)", 1.0, 60.0, key="p_durasi",
            value=round(float(baseline.get("avg_durasi") or 7), 1), step=0.5,
            help="Rata-rata lama paket dari pickup s/d sampai di alamat tujuan. Menentukan tanggal "
                 "paket diterima → memicu jadwal pencairan COD. Makin lama durasi, makin lambat cair.")
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
        cap.caption(f"Sumber: **{_src}**. Nilai Jual (=AoV, dari product_price), HPP (=Pcs×HPP/pcs), "
                    "Stok, & Retur dari data. **CPL & Budget di-auto-plot optimal** berdasarkan CM & "
                    "retur. Kolom **CM, CM%, Retur %** otomatis (tidak bisa diedit). Geser ke kanan "
                    "untuk melihat semua kolom. Sel input tetap bisa Anda ubah manual.")
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
        _cm_help = ("Contribution Margin per order = Nilai Jual − HPP − Fee COD×(Nilai Jual+Ongkir) "
                    "+ Cashback×Ongkir − Opex variabel. Otomatis dari input.")
        edited = st.data_editor(
            st.session_state["produk_master"], num_rows="dynamic", width='stretch',
            height=320, key="editor_master",
            column_config={
                "Produk": st.column_config.TextColumn("Produk", width="medium"),
                "Budget/Hari": _money("Budget/Hari (Rp)"),
                "CPL": _money("CPL (Rp)"),
                "Nilai Produk": st.column_config.NumberColumn(
                    "Nilai Jual / AoV (Rp)", min_value=0, format="localized",
                    help="Average Order Value = nilai jual total produk per order (product_price), "
                         "sudah termasuk jumlah pcs dalam 1 resi."),
                "HPP": st.column_config.NumberColumn(
                    "HPP (Rp)", min_value=0, format="localized",
                    help="Harga pokok per order = Pcs/Order × HPP per Pcs (dari Import-Stock)."),
                "Stok (pcs)": _int("Stok (pcs)", "Sisa stok gudang. Order tercukupi stok tidak "
                                                 "menimbulkan biaya beli produk."),
                "Pcs/Order": _int("Pcs/Order", "Rata-rata pcs produk utama per order (untuk "
                                               "menghitung berapa order yang bisa dipenuhi stok)."),
                "CM": st.column_config.NumberColumn("CM (Rp/order)", disabled=True,
                                                    format="localized", help=_cm_help),
                "CM%": st.column_config.NumberColumn("CM %", disabled=True, format="%.1f%%",
                    help="CM ÷ Nilai Jual × 100. Makin tinggi makin layak di-scale budget-nya."),
                "Retur %": st.column_config.NumberColumn("Retur %", disabled=True, format="%.1f%%",
                    help="% retur produk ini dari histori (order yang gagal diterima ÷ sampai+retur, "
                         "via join No. Waybill). Retur tinggi → budget iklan di-scale lebih kecil."),
            })
        # Kolom CM/CM% (disabled) menyegar saat tekan "Re-plot optimal". Edit manual pada
        # Nilai/HPP tetap dipakai simulasi (via `edited`), CM tampil ter-update usai re-plot.
        st.session_state["produk_current"] = edited     # snapshot utk fitur Planning (aman, key beda)

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
        st.caption(
            f"🧮 **COD**: kas cair saat settlement = Produk + Cashback − Fee COD.  "
            f"**Non-COD**: kas masuk hari itu = Produk + Ongkir penuh.  "
            f"Ongkir retur J&T: {_ret} (gratis bila retur bulanan ≤ 20%).  "
            f"Budget iklan total **{rp(s['budget_iklan'])}** ({rp(s['budget_harian'])}/hari × {horizon} hari)."
        )

    # ============================ SECTION 1: SKEMA GLOBAL ============================
    st.markdown("---")
    with st.container(border=True):
        section("📊 SECTION 1 — HASIL SKEMA GLOBAL",
                "Proyeksi berdasarkan parameter global di atas (belanja iklan & opex rata sesuai "
                "setelan). Inilah baseline sebelum Anda menyesuaikan pengeluaran per tanggal.",
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
        st.caption("Estimasi memakai ekstrapolasi linear efisiensi saat ini (kontribusi/rupiah "
                   "iklan konstan). Realitanya CPL bisa naik saat skala besar & stok perlu ditambah — "
                   "gunakan sebagai arah, lalu uji lewat tabel produk & Skema Harian.")

        # ---------- CHART UTAMA: POSISI KAS ----------
        st.markdown("#### 📈 Posisi Kas Sepanjang Waktu")
        st.plotly_chart(viz.fig_cash_position(sim["timeline"], s), width='stretch')
        st.caption("Garis biru = **posisi kas riil** = Modal Awal + akumulasi arus kas harian. "
                   "Garis putus abu = level Modal Awal; garis merah putus = batas 0. Titik hijau = "
                   "saldo di H+30/60/90. Bila kurva menembus 0, modal **kurang** untuk skala belanja "
                   "ini (tanda ⚠️ menunjukkan harinya) — kurangi budget/HPP atau tambah modal.")

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
            st.caption("**Laba Bersih** = laba *akrual* (omzet COD diakui saat paket diterima). "
                       "**Saldo Kas Akhir** = posisi *kas* di akhir bulan (Modal Awal + akumulasi arus "
                       "kas) — bisa beda dari laba karena COD baru cair belakangan. Bulan pertama/terakhir "
                       "dapat mencakup sebagian hari.")
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
        st.caption("Saldo Awal hari-1 = **Modal Awal**. Saldo Akhir = Saldo Awal + (Kas Masuk − Kas "
                   "Keluar). Saldo negatif = modal tak cukup di hari itu. Timeline mencakup hari kirim "
                   "+ ekor pencairan COD setelah horizon.")

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
        st.caption("Nilai awal = sama dengan Skema Global (Gaji sudah terisi otomatis di tanggal "
                   "gajian). Ubah sel mana pun untuk skenario what-if. Opex variabel/resi tetap "
                   "otomatis mengikuti volume.")

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

    # ==================== PLANNING: simpan / muat / hapus ====================
    st.markdown("---")
    with st.container(border=True):
        section("💾 PLANNING — Simpan / Muat Skenario", anchor="sec-plan",
                desc="Simpan konfigurasi + tabel produk sebagai skenario bernama, buka lagi, "
                     "perbarui, atau hapus. Tersimpan sebagai file di folder plans/.")
        pc = st.columns([2, 1, 2])
        plan_name = pc[0].text_input("Nama planning", key="plan_name_input",
                                     placeholder="mis. Skenario Agresif 5x")
        if pc[1].button("💾 Simpan / Update", width='stretch'):
            if plan_name.strip():
                payload = {k: st.session_state.get(k) for k in _PLAN_KEYS}
                _pm = st.session_state.get("produk_current", st.session_state["produk_master"])
                payload["produk_master"] = _pm[_INCOLS].to_dict("records")
                planning.save_plan(plan_name, payload)
                st.success(f"Planning '{plan_name}' tersimpan.")
            else:
                st.warning("Isi nama planning terlebih dahulu.")
        _plans = planning.list_plans()
        sel = pc[2].selectbox("Planning tersimpan", ["—"] + _plans, key="plan_select")
        lc = st.columns([1, 1, 3])
        if lc[0].button("📂 Muat", width='stretch', disabled=(sel == "—")):
            pl = planning.load_plan(sel)
            if pl:
                st.session_state["_pending_load"] = pl["data"]
                st.success(f"Memuat '{sel}'…")
                st.rerun()
        if lc[1].button("🗑 Hapus", width='stretch', disabled=(sel == "—")):
            planning.delete_plan(sel)
            st.session_state.pop("plan_select", None)
            st.rerun()
        lc[2].caption("Muat = terapkan skenario ke semua input & tabel produk. Simpan pakai nama "
                      "sama untuk meng-update. File di folder plans/ (server ephemeral bisa reset).")

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

    st.markdown("#### 🗺️ Analisis Wilayah — Ringkasan Keputusan")
    k = st.columns(4)
    kpi(k[0], "Total Resi", num(tot_resi), f"{prov['provinsi'].nunique()} provinsi")
    kpi(k[1], "% Sampai Rata²", fmt.persen(sla_all, 0), "paket sukses sampai konsumen",
        cls="green" if sla_all >= config.TARGET_SAMPAI_MIN else "amber",
        help="Persentase paket yang statusnya 'Sampai Tujuan' dari total dikirim. "
             "(dulu diberi label SLA)")
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
    mc[1].caption("🟢 Hijau = baik, 🔴 Merah = buruk. Untuk Retur/Durasi/Outstanding, "
                  "makin hijau makin rendah (makin baik).")

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
    st.markdown("#### 📦 Analisis Produk — Keputusan Cepat")
    master = st.session_state.get("produk_master")
    hpp_map = (dict(zip(master["Produk"].astype(str),
                        pd.to_numeric(master["HPP"], errors="coerce").fillna(0)))
               if master is not None and not master.empty else {})
    default_hpp = round(baseline["avg_nilai_produk"] * config.DEFAULTS["hpp_ratio"])
    topc = st.columns([3, 1])
    topc[0].caption("**Winning** = kontribusi margin terbesar. **Aman** = paling banyak "
                    "sampai & paling sedikit retur. HPP dari Tabel Produk (Modul 1).")
    pareto_pct = topc[1].slider("Ambang Pareto (%)", 50, 95, 80, step=5)

    prod = prodeng.product_summary(dff, hpp=default_hpp, hpp_map=hpp_map, use_clean=True)
    if prod.empty:
        st.warning("Kolom produk (Nama Barang) tidak tersedia pada data.")
    else:
        pareto = prodeng.pareto_threshold(prod, pareto_pct)
        sigp = prod[prod["resi"] >= 10]
        win = prod.iloc[0]
        safe = (sigp.sort_values(["retur_pct", "sla"], ascending=[True, False]).iloc[0]
                if not sigp.empty else win)

        # ---- KPI keputusan ----
        r = st.columns(4)
        kpi(r[0], "🏆 Winning (Margin Terbaik)", win["produk"][:20],
            f"{fmt.persen(win['kontribusi_pct'])} net • {rp(win['margin_jual_per_resi'])}/resi",
            cls="green", help="Produk dengan kontribusi net real (margin) terbesar.")
        kpi(r[1], "✅ Produk Teraman", safe["produk"][:20],
            f"retur {safe['retur_pct']:.0f}% • sampai {safe['sla']:.0f}%", cls="green",
            help="Paling banyak sampai & paling sedikit retur (min 10 resi).")
        kpi(r[2], "Total Net Real", rp(prod["net_real"].sum()), f"{num(len(prod))} produk",
            cls="green")
        kpi(r[3], f"Produk Inti (Pareto {pareto_pct}%)", num(pareto["n_produk_inti"]),
            f"{pareto['share_produk']:.0f}% produk = {pareto_pct}% net", cls="amber")

        # ---- BRIEF PARETO (kacamata bisnis) ----
        st.info(f"📊 **Arti Pareto:** hanya **{pareto['n_produk_inti']} dari "
                f"{pareto['n_produk_total']} produk** ({pareto['share_produk']:.0f}% katalog) "
                f"sudah menyumbang **{pareto_pct}% dari total keuntungan**. Artinya bisnis Anda "
                f"**bertumpu pada segelintir produk inti** — di sinilah stok, modal, dan budget "
                f"iklan sebaiknya diprioritaskan. Sisanya (produk 'ekor panjang') kontribusinya "
                f"kecil: evaluasi mana yang dipertahankan, mana yang dihentikan agar modal & "
                f"perhatian tidak terpecah. Geser ambang Pareto untuk melihat konsentrasi ini "
                f"lebih ketat/longgar.")

        st.markdown("##### 💡 Insight Otomatis")
        for line in insights.product_insights(prod, pareto):
            st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

        # ---- Winning vs Aman (dua tabel berdampingan) ----
        st.markdown("##### 🏆 Winning Products  vs  ✅ Produk Teraman")
        cols = st.columns(2)
        wl = prod.head(10)
        cols[0].caption("Kontribusi margin terbaik (genjot iklannya)")
        cols[0].dataframe(pd.DataFrame({
            "Produk": wl["produk"], "Resi": wl["resi"].map(num),
            "Net Real": wl["net_real"].map(rp),
            "Margin/Resi": wl["margin_jual_per_resi"].map(rp),
            "Kontribusi": wl["kontribusi_pct"].map(lambda v: fmt.persen(v)),
            "% Sampai": wl["sla"].map(lambda v: fmt.persen(v, 0)),
        }), width='stretch', height=380, hide_index=True)
        sl = (sigp.sort_values(["retur_pct", "sla"], ascending=[True, False]).head(10)
              if not sigp.empty else prod.head(10))
        cols[1].caption("Paling aman (sampai tinggi, retur rendah)")
        cols[1].dataframe(pd.DataFrame({
            "Produk": sl["produk"], "Resi": sl["resi"].map(num),
            "% Sampai": sl["sla"].map(lambda v: fmt.persen(v, 0)),
            "% Retur": sl["retur_pct"].map(lambda v: fmt.persen(v, 0)),
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
        kpi(dd[0], "Resi", num(row["resi"]), f"AOV {rp(row['aov'])}")
        kpi(dd[1], "Margin Jual / Resi", rp(row["margin_jual_per_resi"]),
            f"{fmt.persen(row['margin_pct'])} (sblm iklan)",
            cls="green" if row["margin_jual_per_resi"] >= 0 else "amber")
        kpi(dd[2], "% Sampai / % Retur", f"{row['sla']:.0f}% / {row['retur_pct']:.0f}%",
            cls="green" if row["sla"] >= config.TARGET_SAMPAI_MIN else "amber")
        kpi(dd[3], "Kontribusi Net", fmt.persen(row["kontribusi_pct"]),
            f"net {rp(row['net_real'])}", cls="green")

        with st.expander("📋 Tabel lengkap semua produk"):
            tbl = pd.DataFrame({
                "Produk": prod["produk"], "Resi": prod["resi"].map(num),
                "Nilai Produk": prod["aov"].map(rp),
                "Margin Jual/Resi": prod["margin_jual_per_resi"].map(rp),
                "Margin %": prod["margin_pct"].map(lambda v: fmt.persen(v)),
                "Net Total": prod["net_real"].map(rp),
                "Kontribusi": prod["kontribusi_pct"].map(lambda v: fmt.persen(v)),
                "% Sampai": prod["sla"].map(lambda v: fmt.persen(v, 0)),
                "% Retur": prod["retur_pct"].map(lambda v: fmt.persen(v, 0)),
            })
            st.dataframe(tbl, width='stretch', height=360, hide_index=True)

# =================================================================== MODUL TARGET
with tab4:
    st.markdown("#### 🎯 Target Profit Simulator")
    st.caption("Tetapkan target laba & waktu, sistem menghitung MUNDUR skenario yang "
               "dibutuhkan (closing, CPL, budget) + batas aman biaya. Parameter dasar "
               "diambil dari Tabel Produk & Parameter Global di Modul 1.")

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
    st.caption("Empat jalur berbeda menuju target laba likuid yang sama. Angka sudah "
               "memperhitungkan bahwa sebagian COD belum cair dalam horizon.")
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
        st.markdown("##### 🛡️ Batas Aman — Harus Terpenuhi Bersamaan (AND)")
        st.warning("Seluruh parameter batas aman di bawah ini harus berada dalam rentang "
                   "rekomendasi **secara bersamaan**. Apabila **salah satu** parameter berada "
                   "di luar batas, target laba bersih **berpotensi tidak tercapai** meskipun "
                   "parameter lainnya masih memenuhi.")
        st.caption(f"Dihitung pada rencana yang mencapai target (budget ≈ "
                   f"{rp(L.get('budget_ref',0)/target_days)}/hari). Batas = titik impas per parameter.")
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


st.markdown("---")
st.caption(f"{config.APP_TITLE} • {config.COMPANY} • dibuat dengan Streamlit + Plotly • "
           "100% lokal/offline")
