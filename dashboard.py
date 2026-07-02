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
import visualization as viz
import insights
import formatting as fmt

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


def kpi(col, label, value, sub="", cls=""):
    col.markdown(
        f'<div class="kpi {cls}"><div class="lbl">{label}</div>'
        f'<div class="val">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True)


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
    data = data_cleaning.clean_all(raw)
    return data


def get_data():
    path = data_loader.find_excel()
    mtime = os.path.getmtime(path)
    return load_data(mtime), path, mtime


# ----------------------------------------------------------------- LOAD
try:
    data, xlpath, mtime = get_data()
except Exception as e:
    st.error(f"Gagal memuat data: {e}")
    st.stop()

df_all = data["all_resi"]

# ----------------------------------------------------------------- SIDEBAR
with st.sidebar:
    st.markdown(f"### 📦 {config.COMPANY}")
    st.caption(config.APP_TITLE)
    st.success(f"Data: {os.path.basename(xlpath)}")
    st.caption(f"Diperbarui: {pd.to_datetime(mtime, unit='s'):%d %b %Y %H:%M} • "
               f"{len(df_all):,} resi".replace(",", "."))
    if st.button("🔄 Muat ulang data", width='stretch'):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("#### 🔎 Filter Global")

    dmin = pd.to_datetime(df_all["tgl_kirim"].min())
    dmax = pd.to_datetime(df_all["tgl_kirim"].max())
    rng = st.date_input("Rentang Tanggal Kirim", (dmin, dmax),
                        min_value=dmin, max_value=dmax)

    prov_sel = st.multiselect("Provinsi", sorted(df_all["provinsi"].dropna().unique()))
    kota_opts = df_all[df_all["provinsi"].isin(prov_sel)] if prov_sel else df_all
    kota_sel = st.multiselect("Kota", sorted(kota_opts["kota"].dropna().unique()))
    status_sel = st.multiselect("Status Pengiriman",
                                sorted(df_all["status_ttd"].dropna().unique()))
    rekon_sel = st.multiselect("Status Settlement",
                               sorted(df_all["rekon"].dropna().unique()))
    hari_sel = st.multiselect("Hari Pengiriman",
                              ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"])

    dmaxv = int(df_all["durasi_kirim"].max() or 30)
    dur_sel = st.slider("Durasi Kirim (hari)", 0, dmaxv, (0, dmaxv))
    nmax = int(df_all["proyeksi_net"].max() or 0)
    net_sel = st.slider("Nilai Proyeksi Net (Rp)", 0, nmax, (0, nmax), step=10000)


# ----------------------------------------------------------------- APPLY FILTER
def apply_filters(df):
    m = pd.Series(True, index=df.index)
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        m &= df["tgl_kirim"].between(pd.Timestamp(rng[0]),
                                     pd.Timestamp(rng[1]) + pd.Timedelta(days=1))
    if prov_sel:
        m &= df["provinsi"].isin(prov_sel)
    if kota_sel:
        m &= df["kota"].isin(kota_sel)
    if status_sel:
        m &= df["status_ttd"].isin(status_sel)
    if rekon_sel:
        m &= df["rekon"].isin(rekon_sel)
    if hari_sel:
        m &= df["hari_kirim"].isin(hari_sel)
    m &= df["durasi_kirim"].between(*dur_sel) | df["durasi_kirim"].isna()
    m &= df["proyeksi_net"].between(*net_sel)
    return df[m]


dff = apply_filters(df_all)
if dff.empty:
    st.warning("Tidak ada data sesuai filter. Longgarkan filter di sidebar.")
    st.stop()

baseline = forecasting.compute_baseline(dff)
recv_dist = forecasting.receive_distribution(dff)

# ----------------------------------------------------------------- HEADER
st.markdown(f"## 📊 {config.APP_TITLE}")
st.caption(f"Periode data {dmin:%d %b %Y} – {dmax:%d %b %Y} • "
           f"{baseline['n_resi']:,} resi setelah filter".replace(",", "."))

tab1, tab2, tab3 = st.tabs(["💰 Modul 1 — Simulator Cashflow & Pencairan",
                            "🗺️ Modul 2 — Analisis Wilayah",
                            "📦 Modul 3 — Analisis Produk"])

# ---- seeder tabel produk (master, persisten lintas filter) ----
def seed_master():
    return prodeng.seed_product_table(
        df_all, top_n=25, total_budget_harian=config.DEFAULTS["budget_harian"],
        default_cpl=config.DEFAULTS["cpl"], hpp_ratio=config.DEFAULTS["hpp_ratio"])


if "produk_master" not in st.session_state:
    st.session_state["produk_master"] = seed_master()
if "editor_nonce" not in st.session_state:
    st.session_state["editor_nonce"] = 0

# =================================================================== MODUL 1
with tab1:
    st.markdown("#### ⚙️ Parameter Global")
    g1, g2, g3, g4 = st.columns(4)
    closing = g1.slider("Closing Order (%)", 0, 100,
                        int(config.DEFAULTS["closing_rate"] * 100)) / 100
    success = g1.slider("Success Delivery (%)", 0, 100,
                        int(round(baseline["success_rate"] * 100)) or 1) / 100
    opex_30 = rupiah_input(g1, "Biaya Operasional / 30 hari (Rp)", 0, "in_opex",
                           help="Biaya operasional teknis: packing, gaji, petty cash, dll. "
                                "Satu input untuk 30 hari; dibagi rata per hari.")
    ongkir = rupiah_input(g2, "Ongkir / Resi (Rp)", baseline["avg_total_biaya"], "in_ongkir")
    cashback_pct = g2.number_input("Cashback Ongkir (%)", 0.0, 100.0,
                                   value=round(baseline["cashback_pct"] * 100, 1), step=0.5,
                                   help="Cashback ongkir (Biaya Diskon) sbg omzet.")
    pct_cod = g3.slider("Order COD (%)", 0, 100, int(round(baseline["pct_cod"] * 100)))
    cod_fee_pct = g3.number_input("COD Fee (%)", 0.0, 10.0,
                                  value=round(baseline["cod_fee_rate"] * 100, 2), step=0.05)
    horizon = g4.selectbox("Proyeksi (hari)", config.HORIZON_OPTIONS, index=2)
    mode_label = g4.radio("Mode Pencairan", list(config.SETTLE_MODES.keys()))
    mode = config.SETTLE_MODES[mode_label]
    lag = config.SETTLE_DAILY_LAG_DEFAULT
    if mode == "mode1":
        lag = g4.number_input("Jeda cair (hari kerja)", 0, 10, lag)
    st.caption(f"➡️ Transfer otomatis **{100 - pct_cod}%**  •  Cashback per resi "
               f"≈ {rp(cashback_pct/100*ongkir)}  •  COD Fee per resi dihitung otomatis.")

    # ---------- TABEL PRODUK (input per produk) ----------
    st.markdown("#### 🧾 Tabel Produk — Budget Iklan/Hari, CPL, Nilai Produk, HPP")
    cap, btn = st.columns([5, 1])
    cap.caption("Default dari histori tiap produk. Edit nilai, **tambah baris** (ikon ＋ di "
                "bawah tabel), atau **hapus baris** (centang kotak di kiri baris lalu tekan "
                "tombol 🗑). Simulasi menyesuaikan otomatis.")
    if btn.button("🔄 Reset histori", width='stretch'):
        st.session_state["produk_master"] = seed_master()
        st.session_state["editor_nonce"] += 1
        st.rerun()

    _money = lambda label: st.column_config.NumberColumn(label, min_value=0, format="localized")
    edited = st.data_editor(
        st.session_state["produk_master"], num_rows="dynamic", width='stretch',
        height=290, key=f"editor_master_{st.session_state['editor_nonce']}",
        column_config={
            "Produk": st.column_config.TextColumn("Produk", width="large"),
            "Budget/Hari": _money("Budget/Hari (Rp)"),
            "CPL": _money("CPL (Rp)"),
            "Nilai Produk": _money("Nilai Produk (Rp)"),
            "HPP": _money("HPP (Rp)"),
        })
    st.session_state["produk_master"] = edited

    overrides = dict(closing_rate=closing, success_rate=success, ongkir_per_resi=ongkir,
                     cashback_pct=cashback_pct / 100, cod_fee_rate=cod_fee_pct / 100,
                     pct_cod=pct_cod / 100, opex_30=opex_30, horizon_days=horizon,
                     mode=mode, daily_lag=lag)
    sim = ce.simulate_multi(baseline, recv_dist, edited, overrides)
    s = sim["summary"]

    st.caption(
        f"🧮 **COD**: kas cair saat settlement = Produk + Cashback − Fee COD.  "
        f"**Non-COD**: kas masuk hari itu = Produk + Ongkir penuh.  "
        f"Paket retur: barang kembali (HPP tidak rugi), bayar ongkir retur "
        f"≈ {rp(s['return_ongkir_per_paket'])}/paket.  "
        f"Budget iklan total **{rp(s['budget_iklan'])}** ({rp(s['budget_harian'])}/hari × {horizon} hari)."
    )

    # ---------- KPI CARDS ----------
    st.markdown("#### 📌 Funnel & Omzet")
    r1 = st.columns(4)
    kpi(r1[0], "Budget Iklan", rp(s["budget_iklan"]), f"{rp(s['budget_harian'])}/hari")
    kpi(r1[1], "Estimasi Lead → Order", f"{num(s['n_lead'])} → {num(s['n_order'])}")
    kpi(r1[2], "Resi Dikirim", num(s["n_resi"]),
        f"{num(s['n_sukses'])} sampai ({fmt.persen(s['success_rate']*100,0)})")
    kpi(r1[3], "Omzet Kotor (horizon)", rp(s["total_revenue"]),
        f"COD {rp(s['nilai_cod'])} • Transfer {rp(s['nilai_transfer'])}", cls="green")

    st.markdown("##### 💵 Kebutuhan Modal & Break-even (audit working capital)")
    bal = (f"balik modal hari ke-{s['hari_balik_modal']}"
           if s.get("hari_balik_modal") is not None else "belum balik di horizon")
    sus = (f"self-sustaining hari ke-{s['hari_self_sustaining']}"
           if s.get("hari_self_sustaining") is not None else "belum self-sustaining")
    r3 = st.columns(4)
    kpi(r3[0], "⭐ Modal Awal Dibutuhkan", rp(s["modal_awal"]),
        "kas terdalam sblm berputar positif", cls="amber")
    kpi(r3[1], "Saldo Kas Minimum", rp(s["saldo_kas_min"]), sus, cls="amber")
    kpi(r3[2], "Total Beli Produk (HPP)", rp(s["total_beli_produk"]),
        "kas beli stok semua paket", cls="amber")
    kpi(r3[3], "Outstanding Omzet (puncak)", rp(s["outstanding_peak"]),
        "COD blm cair (nunggu settle)", cls="amber")
    st.markdown("##### 📈 Profitabilitas")
    r4 = st.columns(4)
    kpi(r4[0], "⭐ Laba Bersih (horizon)", rp(s["net_profit"]),
        "stlh HPP, iklan, retur, opex", cls="green" if s["net_profit"] >= 0 else "amber")
    kpi(r4[1], "⭐ ROI Modal", fmt.persen(s["roi_modal"], 0), bal,
        cls="green" if s["roi_modal"] >= 0 else "amber")
    kpi(r4[2], "ROI atas Iklan", fmt.persen(s["roi_iklan"], 0),
        cls="green" if s["roi_iklan"] >= 0 else "amber")
    kpi(r4[3], "Ongkir Retur + Opex", rp(s["total_return_cost"] + s["total_opex"]),
        f"retur {rp(s['total_return_cost'])} • opex {rp(s['total_opex'])}")

    # ---------- HASIL PER PRODUK ----------
    pp_df = sim["per_product"].copy()
    if not pp_df.empty:
        with st.expander("📦 Hasil Simulasi per Produk (lead, resi, omzet, laba, ROI)", expanded=True):
            show = pd.DataFrame({
                "Produk": pp_df["Produk"],
                "Budget/Hari": pp_df["budget_harian"].map(rp),
                "Lead": pp_df["lead"].map(num),
                "Resi": pp_df["resi"].map(num),
                "Gagal": pp_df["gagal"].map(num),
                "Omzet": pp_df["revenue"].map(rp),
                "Laba Bersih": pp_df["net_total"].map(rp),
                "Modal HPP": pp_df["modal_hpp"].map(rp),
                "ROI Iklan": (pp_df["roi"] * 100).round(0).map(lambda v: fmt.persen(v, 0)),
            })
            st.dataframe(show, width='stretch', height=280, hide_index=True)

    # ---------- INSIGHTS ----------
    st.markdown("#### 💡 Insight Otomatis")
    for line in insights.cashflow_insights(sim):
        st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

    # ---------- CHARTS ----------
    st.markdown("#### 📈 Akumulasi Biaya vs Net Omzet")
    st.plotly_chart(viz.fig_accumulation(sim["timeline"]), width='stretch')
    st.markdown("#### 💰 Saldo Kas Harian & Kebutuhan Modal")
    st.plotly_chart(viz.fig_saldo_kas(sim["timeline"]), width='stretch')
    st.markdown("#### 📈 Forecast Cashflow")
    st.plotly_chart(viz.fig_funnel(sim["funnel"]), width='stretch')
    g = st.columns(2)
    g[0].plotly_chart(viz.fig_cashflow(sim["timeline"], "Harian"), width='stretch')
    g[1].plotly_chart(viz.fig_outstanding_vs_cair(sim["timeline"]), width='stretch')
    g4 = st.columns(2)
    g4[0].plotly_chart(viz.fig_cod_vs_transfer(s), width='stretch')
    g4[1].plotly_chart(viz.fig_expense_breakdown(s), width='stretch')
    g5 = st.columns(2)
    g5[0].plotly_chart(viz.fig_settlement_schedule(sim["timeline"]), width='stretch')
    g5[1].plotly_chart(viz.fig_payout_calendar(sim["timeline"]), width='stretch')
    with st.expander("📅 Cashflow mingguan / bulanan & rincian"):
        gw = st.columns(2)
        gw[0].plotly_chart(viz.fig_cashflow(sim["weekly"], "Mingguan"), width='stretch')
        gw[1].plotly_chart(viz.fig_cashflow(sim["monthly"], "Bulanan"), width='stretch')
        st.plotly_chart(viz.fig_in_vs_out(sim["timeline"]), width='stretch')

    with st.expander("📋 Tabel Timeline Cashflow (harian)"):
        show = sim["timeline"].copy()
        show["tanggal"] = show["tanggal"].dt.strftime("%a %d %b %Y")
        st.dataframe(show.round(0), width='stretch', height=300)

# =================================================================== MODUL 2
with tab2:
    prov = geo.province_summary(dff)
    cities = geo.city_summary(dff)

    st.markdown("#### 🗺️ Sebaran Pengiriman Indonesia")
    mc = st.columns([3, 1])
    metric_label = mc[1].selectbox("Metrik Peta",
                                   ["Jumlah Resi", "Proyeksi Net", "Outstanding", "Rata² Durasi"])
    metric_map = {"Jumlah Resi": "resi", "Proyeksi Net": "proyeksi_net",
                  "Outstanding": "outstanding", "Rata² Durasi": "avg_durasi"}
    metric = metric_map[metric_label]
    gj = geo.load_geojson()
    if gj is not None:
        fig_map = viz.fig_choropleth(prov, gj, metric, metric_label)
    else:
        fig_map = viz.fig_bubble_map(prov, metric, metric_label)
    mc[0].plotly_chart(fig_map, width='stretch')

    # insights wilayah
    for line in insights.geography_insights(prov):
        st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

    st.markdown("#### 🔍 Drill-down Provinsi")
    psel = st.selectbox("Pilih Provinsi", prov["provinsi"].tolist())
    det = geo.province_detail(dff, psel)
    if det:
        d = st.columns(4)
        kpi(d[0], "Jumlah Resi", num(det["resi"]))
        kpi(d[1], "Total Proyeksi Net", rp(det["proyeksi_net"]), cls="green")
        kpi(d[2], "Rata² Durasi", f"{det['avg_durasi']} hari")
        kpi(d[3], "SLA Pengiriman", f"{det['sla']}%", cls="green")
        d2 = st.columns(4)
        kpi(d2[0], "Paket Sampai", num(det["sampai"]), cls="green")
        kpi(d2[1], "Belum Sampai", num(det["belum_sampai"]), cls="amber")
        kpi(d2[2], "Outstanding COD", rp(det["outstanding"]), cls="amber")
        kpi(d2[3], "Kota Terbanyak", det["top_kota"])

        st.markdown(f"##### Kota Tujuan di {psel}")
        cdet = geo.city_summary(dff, psel)
        st.plotly_chart(viz.fig_top_bar(cdet, "kota", 10, "resi",
                                        f"Top 10 Kota — {psel}"), width='stretch')

    st.markdown("#### 📊 Performa Wilayah")
    t = st.columns(2)
    t[0].plotly_chart(viz.fig_top_bar(prov, "provinsi", 10, "resi", "Top 10 Provinsi (Resi)"),
                      width='stretch')
    t[1].plotly_chart(viz.fig_top_bar(cities, "kota", 10, "resi", "Top 10 Kota (Resi)"),
                      width='stretch')
    t2 = st.columns(2)
    t2[0].plotly_chart(viz.fig_treemap(prov), width='stretch')
    t2[1].plotly_chart(viz.fig_region_perf(prov, "provinsi"), width='stretch')
    t3 = st.columns(2)
    t3[0].plotly_chart(viz.fig_duration_hist(dff), width='stretch')
    t3[1].plotly_chart(viz.fig_duration_box(dff, "provinsi"), width='stretch')

    with st.expander("📋 Tabel Performa Provinsi"):
        st.dataframe(prov.round(1), width='stretch', height=320)

# =================================================================== MODUL 3
with tab3:
    st.markdown("#### 📦 Analisis Produk — Data-Driven Decision")
    # HPP per produk diambil dari Tabel Produk (Modul 1) -> satu sumber data
    master = st.session_state.get("produk_master")
    hpp_map = (dict(zip(master["Produk"].astype(str),
                        pd.to_numeric(master["HPP"], errors="coerce").fillna(0)))
               if master is not None and not master.empty else {})
    default_hpp = round(baseline["avg_nilai_produk"] * config.DEFAULTS["hpp_ratio"])

    cc = st.columns([2, 1])
    cc[0].caption("💡 **HPP per produk** memakai nilai dari **Tabel Produk di Modul 1** "
                  "(satu sumber data). Produk tanpa HPP memakai default "
                  f"{rp(default_hpp)}. **Margin jual = Nilai Produk − HPP** (belum termasuk biaya iklan).")
    pareto_pct = cc[1].slider("Ambang Pareto (%)", 50, 95, 80, step=5)

    prod = prodeng.product_summary(dff, hpp=default_hpp, hpp_map=hpp_map, use_clean=True)
    if prod.empty:
        st.warning("Kolom produk (Nama Barang) tidak tersedia pada data.")
    else:
        prod_q = prodeng.quadrant(prod)
        pareto = prodeng.pareto_threshold(prod, pareto_pct)

        # ---- KPI produk ----
        st.markdown("##### 📌 Ringkasan")
        rp1 = st.columns(4)
        kpi(rp1[0], "Jumlah Produk", num(len(prod)))
        kpi(rp1[1], "Total Margin Jual", rp(prod["margin_jual"].sum()),
            "Nilai Produk − HPP (sblm iklan)", cls="green")
        kpi(rp1[2], "Total Net Real", rp(prod["net_real"].sum()),
            "stlh cashback & COD fee", cls="green")
        kpi(rp1[3], "Total Modal HPP", rp(prod["hpp_total"].sum()),
            "stok historis", cls="amber")
        rp2 = st.columns(4)
        win = prod.iloc[0]
        kpi(rp2[0], "Winning Product", win["produk"][:22],
            f"{fmt.persen(win['kontribusi_pct'])} net", cls="green")
        kpi(rp2[1], f"Produk Inti (Pareto {pareto_pct}%)", num(pareto["n_produk_inti"]),
            f"{pareto['share_produk']:.0f}% katalog", cls="amber")
        best_m = prod[prod["resi"] >= 10].sort_values("margin_jual_per_resi", ascending=False)
        if not best_m.empty:
            kpi(rp2[2], "Margin Jual/Resi Tertinggi", rp(best_m.iloc[0]["margin_jual_per_resi"]),
                best_m.iloc[0]["produk"][:18], cls="green")
        kpi(rp2[3], "Rata² Margin %", fmt.persen(prod["margin_pct"].mean()))

        # ---- insights ----
        st.markdown("##### 💡 Insight Otomatis")
        for line in insights.product_insights(prod, pareto):
            st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

        # ---- charts ----
        gp = st.columns(2)
        gp[0].plotly_chart(viz.fig_top_products(prod, 12, "net_real",
                           "🏆 Top 12 Produk (Kontribusi Net Real)"), width='stretch')
        gp[1].plotly_chart(viz.fig_top_products(prod, 12, "revenue",
                           "💰 Top 12 Produk (Revenue)"), width='stretch')
        st.plotly_chart(viz.fig_pareto(prod, 15), width='stretch')
        gp2 = st.columns([3, 2])
        gp2[0].plotly_chart(viz.fig_quadrant(prod_q), width='stretch')
        gp2[1].plotly_chart(viz.fig_product_treemap(prod, 25), width='stretch')
        st.plotly_chart(viz.fig_product_sla(prod, 12), width='stretch')

        # ---- drill-down produk ----
        st.markdown("##### 🔍 Detail Produk")
        psel2 = st.selectbox("Pilih Produk", prod["produk"].tolist())
        row = prod[prod["produk"] == psel2].iloc[0]
        dd = st.columns(4)
        kpi(dd[0], "Resi", num(row["resi"]), f"AOV {rp(row['aov'])}")
        kpi(dd[1], "HPP / Resi", rp(row["hpp_per_resi"]), cls="amber")
        kpi(dd[2], "Margin Jual / Resi", rp(row["margin_jual_per_resi"]),
            f"{fmt.persen(row['margin_pct'])} (sblm iklan)",
            cls="green" if row["margin_jual_per_resi"] >= 0 else "amber")
        kpi(dd[3], "Net Real / Resi", rp(row["margin_per_resi"]),
            "stlh cashback & COD fee",
            cls="green" if row["margin_per_resi"] >= 0 else "amber")
        dd2 = st.columns(4)
        kpi(dd2[0], "Total Margin Jual", rp(row["margin_jual"]), cls="green")
        kpi(dd2[1], "Kontribusi Net", fmt.persen(row["kontribusi_pct"]))
        kpi(dd2[2], "SLA", fmt.persen(row["sla"], 0),
            cls="green" if row["sla"] >= 60 else "amber")
        kpi(dd2[3], "% COD", fmt.persen(row["cod_pct"], 0))

        with st.expander("📋 Tabel Lengkap Produk (margin jual, net real, kontribusi)"):
            tbl = pd.DataFrame({
                "Produk": prod["produk"],
                "Resi": prod["resi"].map(num),
                "Nilai Produk": prod["aov"].map(rp),
                "HPP/Resi": prod["hpp_per_resi"].map(rp),
                "Margin Jual/Resi": prod["margin_jual_per_resi"].map(rp),
                "Margin %": prod["margin_pct"].map(lambda v: fmt.persen(v)),
                "Net Real/Resi": prod["margin_per_resi"].map(rp),
                "Net Total": prod["net_real"].map(rp),
                "Kontribusi": prod["kontribusi_pct"].map(lambda v: fmt.persen(v)),
                "SLA": prod["sla"].map(lambda v: fmt.persen(v, 0)),
            })
            st.dataframe(tbl, width='stretch', height=360, hide_index=True)

st.markdown("---")
st.caption(f"{config.APP_TITLE} • {config.COMPANY} • dibuat dengan Streamlit + Plotly • "
           "100% lokal/offline")
