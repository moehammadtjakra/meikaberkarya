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

tab1, tab4, tab2, tab3 = st.tabs(["💰 Modul 1 — Simulator Cashflow & Pencairan",
                                  "🎯 Modul — Target Profit Simulator",
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
    n_cs = int(g1.number_input("Jumlah Customer Service (orang)", 1, 200,
                               int(config.DEFAULTS.get("n_cs", 3)), step=1,
                               help="Untuk membagi beban leads per CS."))
    ongkir = rupiah_input(g2, "Ongkir / Resi (Rp)", baseline["avg_total_biaya"], "in_ongkir")
    cashback_pct = g2.number_input("Cashback Ongkir (%)", 0.0, 100.0,
                                   value=round(baseline["cashback_pct"] * 100, 1), step=0.5,
                                   help="Cashback ongkir (Biaya Diskon) sbg omzet.")
    durasi_kirim = g2.number_input(
        "Rata² Durasi Kirim (hari)", 1.0, 60.0,
        value=round(float(baseline.get("avg_durasi") or 7), 1), step=0.5,
        help="Rata-rata lama paket dari pickup s/d sampai di alamat tujuan. Default dari "
             "histori. Menentukan tanggal paket diterima → memicu jadwal pencairan COD "
             "(Sen/Sel/Kam atau H+1). Makin lama durasi, makin lambat COD cair.")
    pct_cod = g3.slider("Order COD (%)", 0, 100, int(round(baseline["pct_cod"] * 100)))
    cod_fee_pct = g3.number_input("COD Fee (%)", 0.0, 10.0,
                                  value=round(baseline["cod_fee_rate"] * 100, 2), step=0.05)
    horizon = int(g4.number_input("Proyeksi (hari)", min_value=1, max_value=3650,
                                  value=int(config.DEFAULTS["horizon_days"]), step=1,
                                  help="Bebas isi berapa pun (> 0 hari)."))
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
        st.session_state.pop("editor_master", None)   # bersihkan state editor
        st.rerun()

    _money = lambda label: st.column_config.NumberColumn(label, min_value=0, format="localized")
    # Key STABIL + base dataframe tetap → edit langsung tersimpan tanpa perlu 2x Enter.
    # Gunakan nilai kembalian `edited` langsung (jangan ditulis balik ke base).
    edited = st.data_editor(
        st.session_state["produk_master"], num_rows="dynamic", width='stretch',
        height=290, key="editor_master",
        column_config={
            "Produk": st.column_config.TextColumn("Produk", width="large"),
            "Budget/Hari": _money("Budget/Hari (Rp)"),
            "CPL": _money("CPL (Rp)"),
            "Nilai Produk": _money("Nilai Produk (Rp)"),
            "HPP": _money("HPP (Rp)"),
        })

    overrides = dict(closing_rate=closing, success_rate=success, ongkir_per_resi=ongkir,
                     cashback_pct=cashback_pct / 100, cod_fee_rate=cod_fee_pct / 100,
                     pct_cod=pct_cod / 100, opex_30=opex_30, horizon_days=horizon,
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

    # ---------- KPI CARDS ----------
    st.markdown("#### 📌 Funnel & Omzet")
    r1 = st.columns(4)
    kpi(r1[0], "Budget Iklan", rp(s["budget_iklan"]), f"{rp(s['budget_harian'])}/hari")
    kpi(r1[1], "Estimasi Lead → Order", f"{num(s['n_lead'])} → {num(s['n_order'])}",
        help="Lead = Budget ÷ CPL. Order = Lead × Closing Rate.")
    kpi(r1[2], "Resi Dikirim", num(s["n_resi"]),
        f"{num(s['n_sukses'])} sampai ({fmt.persen(s['success_rate']*100,0)})",
        help="Resi = jumlah order dikirim. Sampai = Resi × Success Rate; sisanya retur.")
    kpi(r1[3], "Estimasi Omzet (Kas Masuk)", rp(s["total_revenue"]),
        f"COD {rp(s['nilai_cod'])} • Transfer {rp(s['nilai_transfer'])}", cls="green",
        help="Total DANA yang diterima perusahaan dari paket terkirim selama horizon "
             "(kas masuk kotor, sebelum dikurangi HPP/iklan/opex). "
             "COD = Σ (Harga+Cashback−FeeCOD) untuk paket COD sampai; "
             "Transfer = Σ (Harga+Ongkir) untuk paket transfer. Bukan laba.")

    leads_per_hari = s["n_lead"] / horizon if horizon else 0
    leads_per_cs = leads_per_hari / n_cs if n_cs else 0
    rcs = st.columns(4)
    kpi(rcs[0], "Total Leads / Hari", num(leads_per_hari),
        f"≈ {num(s['n_lead'])} lead / {horizon} hari",
        help="Rata-rata leads masuk per hari = total lead ÷ horizon.")
    kpi(rcs[1], f"Leads / Hari per CS ({n_cs} orang)", num(leads_per_cs),
        "beban follow-up tiap CS/hari", cls="amber",
        help="Total leads harian dibagi jumlah Customer Service. Acuan beban kerja & "
             "kebutuhan penambahan CS.")
    kpi(rcs[2], "Resi / Hari", num((s["n_resi"] / horizon) if horizon else 0),
        f"dikirim (closing {fmt.persen(closing*100,0)})",
        help="Jumlah resi/paket yang dikirim per hari = order per hari (1 order = 1 resi).")
    kpi(rcs[3], "Resi Completed / Hari", num((s["n_sukses"] / horizon) if horizon else 0),
        f"sukses sampai ({fmt.persen(s['success_rate']*100,0)})", cls="green",
        help="Paket yang sukses terkirim & diterima konsumen tanpa masalah per hari "
             "= resi/hari × success rate. Sisanya retur/gagal.")

    st.markdown("##### 💵 Kebutuhan Modal & Break-even")
    r3 = st.columns(4)
    kpi(r3[0], "⭐ Modal Awal Dibutuhkan", rp(s["modal_awal"]),
        "dana ditalangi di titik terdalam", cls="amber",
        help="Jumlah kas maksimum yang harus Anda talangi sendiri sebelum arus kas "
             "berputar positif. = titik terdalam saldo kas (kas masuk − kas keluar kumulatif).")
    kpi(r3[1], "Saldo Kas Minimum", rp(s["saldo_kas_min"]),
        "posisi kas terendah", cls="amber",
        help="Saldo kas paling rendah selama simulasi (negatif = kekurangan yang ditalangi modal).")
    kpi(r3[2], "Total Beli Produk (HPP)", rp(s["total_beli_produk"]),
        "kas beli stok semua paket", cls="amber",
        help="Total uang untuk beli stok semua paket dikirim (HPP × resi). Barang retur "
             "kembali jadi stok (tidak hilang), tapi kasnya sudah keluar.")
    kpi(r3[3], "Outstanding Omzet (puncak)", rp(s["outstanding_peak"]),
        "COD blm cair (nunggu settle)", cls="amber",
        help="Omzet COD yang sudah didapat tapi belum cair (menunggu paket diterima + "
             "settlement J&T). Ini penyebab utama kebutuhan modal.")

    st.markdown("##### 📈 Profitabilitas & Kapan Mulai Untung")
    r4 = st.columns(4)
    kpi(r4[0], "⭐ Laba Bersih (horizon)", rp(s["net_profit"]),
        "stlh HPP, iklan, retur, opex", cls="green" if s["net_profit"] >= 0 else "amber",
        help="Omzet − HPP barang terjual − biaya iklan − ongkir retur − operasional. "
             "HPP barang retur TIDAK dihitung rugi karena barang kembali & bisa dijual lagi.")
    kpi(r4[1], "⭐ ROI Modal", fmt.persen(s["roi_modal"], 0),
        "laba ÷ modal awal", cls="green" if s["roi_modal"] >= 0 else "amber",
        help="Laba bersih dibagi modal awal yang dibutuhkan. Ukuran seberapa produktif "
             "modal yang Anda tanam.")
    lp = s.get("hari_laba_positif")
    lp_txt = (f"H+{lp}" if lp is not None else "> horizon")
    kpi(r4[2], "Laba Bersih Positif", lp_txt,
        f"target laba tercapai hari ke-{lp}" if lp is not None
        else f"baru positif setelah {horizon} hari",
        cls="green" if lp is not None else "amber",
        help="Hari pertama laba (akrual) kumulatif ≥ 0 sejak mulai. Jika '> horizon', "
             "laba baru positif setelah periode simulasi selesai.")
    bep = s.get("hari_bep_kas")
    km = s.get("hari_kembali_modal")
    kpi(r4[3], "Kas Mulai Positif (BEP Kas)",
        f"H+{bep}" if bep is not None else "> horizon",
        (f"⚠️ blm aman tarik modal — aman di H+{km}" if km is not None
         else "kas masih bisa turun lagi"),
        cls="amber",
        help="Hari saldo kas kumulatif pertama kali ≥ 0. PENTING: ini BUKAN titik aman "
             "menarik modal — kas masih bisa turun negatif lagi setelahnya. Lihat kartu "
             "'Aman Kembalikan Modal'.")

    st.markdown("##### 🤝 Pengembalian Modal Investor")
    rk = st.columns(4)
    kpi(rk[0], "Modal Awal Dibutuhkan", rp(s["modal_awal"]),
        "dana ditalangi investor/owner", cls="amber")
    if km is not None:
        kpi(rk[1], "✓ Aman Kembalikan Modal", f"Hari ke-{km}",
            "saldo kas tak minus lagi sesudahnya", cls="green",
            help="Rekomendasi hari untuk menarik/mengembalikan modal awal penuh TANPA "
                 "membuat cashflow harian minus lagi. = hari pertama saldo kas tidak "
                 "pernah negatif lagi hingga akhir periode. Lebih akurat dari BEP kas.")
    else:
        kpi(rk[1], "✓ Aman Kembalikan Modal", "> horizon",
            "belum aman dalam periode ini", cls="amber",
            help="Dalam horizon ini saldo kas masih bisa negatif — modal belum bisa "
                 "ditarik penuh tanpa risiko defisit. Perpanjang horizon atau kurangi belanja.")
    kpi(rk[2], "Kas Mulai Positif (BEP)", f"H+{bep}" if bep is not None else "> horizon",
        "≠ titik aman tarik modal")
    kpi(rk[3], "Sumber Pengembalian", "Margin operasi",
        "laba bersih penjualan yang cair", cls="green",
        help="Modal kembali dari akumulasi surplus kas (margin jual − HPP − iklan − "
             "fee − retur − opex), bukan dari utang/investasi baru.")

    # ---------- CHARTS ----------
    st.markdown("#### 📈 Perjalanan Kas & Kebutuhan Modal")
    st.plotly_chart(viz.fig_cash_journey(sim["timeline"], s), width='stretch')
    st.caption("Garis merah = total kas keluar (iklan+HPP+opex+retur) kumulatif. Garis hijau "
               "= kas masuk yang sudah cair kumulatif. **Garis biru tebal = Laba Bersih "
               "Kumulatif (kas) = kas masuk − kas keluar** — jadi persis selisih garis hijau "
               "dan merah (surplus/defisit harian yang dijumlahkan). Saat biru di bawah 0, "
               "itulah modal yang sedang ditalangi (area merah). Garis vertikal biru = **kas "
               "mulai positif** (BEP kas, tapi bisa turun lagi); garis vertikal hijau = **hari "
               "aman mengembalikan seluruh modal** — saat saldo kas sudah cukup menutup modal "
               "awal DAN cashflow sesudahnya dijamin tak minus lagi. Kursor menampilkan nilai "
               "kumulatif & harian tiap garis.")
    st.markdown("#### 💵 Proyeksi Omzet Harian — COD vs Transfer")
    st.plotly_chart(viz.fig_daily_omzet(sim["timeline"]), width='stretch')
    st.caption(f"Transfer ({fmt.persen((1-pct_cod/100)*100,0)} order) masuk di hari kirim. "
               f"COD ({pct_cod}% order) baru masuk saat cair — setelah paket sampai "
               f"(±{durasi_kirim:g} hari) mengikuti jadwal pencairan J&T. Ubah durasi kirim "
               f"atau %COD untuk melihat dampaknya pada timing kas.")

    # ---------- TABEL CASHFLOW HARIAN ----------
    st.markdown("#### 🧾 Tabel Cashflow Harian")
    _HARI = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
    _BLN = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
            7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}

    def _tgl(t):
        return f"{_HARI[t.weekday()]}, {t.day} {_BLN[t.month]} {t.year}"

    tlx = sim["timeline"].copy()
    tlx["saldo_akhir"] = tlx["saldo_kas"]
    tlx["saldo_awal"] = tlx["saldo_kas"] - tlx["net_cashflow"]
    tabel_cf = pd.DataFrame({
        "Tanggal": [_tgl(t) for t in tlx["tanggal"]],
        "Kas Masuk": tlx["cash_in"].map(rp),
        "Kas Keluar": tlx["cash_out"].map(rp),
        "Laba/Rugi": tlx["net_cashflow"].map(rp),
        "Saldo Awal": tlx["saldo_awal"].map(rp),
        "Saldo Akhir": tlx["saldo_akhir"].map(rp),
    })
    st.dataframe(tabel_cf, width='stretch', height=380, hide_index=True)
    st.caption("Saldo Awal tiap hari = Saldo Akhir hari sebelumnya (mulai Rp0). Saldo negatif "
               "= kas yang sedang ditalangi modal. Timeline mencakup hari kirim + ekor "
               "pencairan COD setelah horizon.")
    g4 = st.columns(2)
    g4[0].plotly_chart(viz.fig_funnel(sim["funnel"]), width='stretch')
    g4[1].plotly_chart(viz.fig_expense_breakdown(s), width='stretch')
    g5 = st.columns(2)
    g5[0].plotly_chart(viz.fig_settlement_schedule(sim["timeline"]), width='stretch')
    g5[1].plotly_chart(viz.fig_payout_calendar(sim["timeline"]), width='stretch')
    with st.expander("🔍 Rincian akumulasi biaya per komponen & cashflow mingguan"):
        st.plotly_chart(viz.fig_accumulation(sim["timeline"]), width='stretch')
        gw = st.columns(2)
        gw[0].plotly_chart(viz.fig_cashflow(sim["weekly"], "Mingguan"), width='stretch')
        gw[1].plotly_chart(viz.fig_cashflow(sim["monthly"], "Bulanan"), width='stretch')

    with st.expander("📋 Tabel Timeline Cashflow (harian)"):
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
            "Budget/Hari": pp_df["budget_harian"].map(rp),
            "Lead": pp_df["lead"].map(num),
            "Resi": pp_df["resi"].map(num),
            "Gagal": pp_df["gagal"].map(num),
            "Omzet": pp_df["revenue"].map(rp),
            "Laba Bersih": pp_df["net_total"].map(rp),
            "Modal HPP": pp_df["modal_hpp"].map(rp),
            "ROI Iklan": (pp_df["roi"] * 100).round(0).map(lambda v: fmt.persen(v, 0)),
        })
        st.dataframe(show, width='stretch', height=300, hide_index=True)

    # ========== SIMULASI CASHFLOW HARIAN (EDITABLE PER HARI) ==========
    st.markdown("---")
    st.markdown("#### 🧮 Simulasi Cashflow Harian (ubah budget/CPL/opex per hari)")
    st.caption("Ubah **Budget Iklan, CPL, atau Opex di hari tertentu** — kolom lain "
               "dihitung ulang otomatis, termasuk pencairan COD dari order hari itu yang "
               "baru cair beberapa hari kemudian. Budget dibagi proporsional ke produk terpilih.")

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
    g_daily = dict(closing=closing, success=success, pct_cod=pct_cod / 100, ongkir=ongkir,
                   cashback=cashback_pct / 100 * ongkir, cod_fee_rate=cod_fee_pct / 100,
                   hpp=hpp_bl, nilai_produk=nilai_bl, mode=mode, daily_lag=lag,
                   durasi_override=durasi_kirim, start_date=pd.Timestamp.today().normalize())

    start_cf = g_daily["start_date"]
    _tgl_list = [start_cf + pd.Timedelta(days=i) for i in range(horizon)]

    def _tgl_id(t):
        _H = {0: "Sen", 1: "Sel", 2: "Rab", 3: "Kam", 4: "Jum", 5: "Sab", 6: "Min"}
        _B = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
              7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}
        return f"{_H[t.weekday()]}, {t.day} {_B[t.month]} {t.year}"

    def _seed_cf():
        return pd.DataFrame({
            "Tanggal": [_tgl_id(t) for t in _tgl_list],
            "Budget Iklan": [int(round(tot_budget_day))] * horizon,
            "CPL": [int(round(eff_cpl))] * horizon,
            "Opex": [int(round(opex_30 / 30))] * horizon,
        })

    _key = f"cf_edit_{horizon}"
    if _key not in st.session_state:
        st.session_state[_key] = _seed_cf()
    cbtn = st.columns([5, 1])
    cbtn[0].caption(f"Range {horizon} hari sejak {_tgl_id(start_cf)}. Default budget "
                    f"{rp(tot_budget_day)}/hari, CPL {rp(eff_cpl)}, opex {rp(opex_30/30)}/hari.")
    if cbtn[1].button("🔄 Reset harian", width='stretch'):
        st.session_state[_key] = _seed_cf()
        st.session_state.pop(f"cfed_{horizon}", None)
        st.rerun()

    _mny = lambda lb: st.column_config.NumberColumn(lb, min_value=0, format="localized")
    ed_days = st.data_editor(
        st.session_state[_key], width='stretch', height=260, key=f"cfed_{horizon}",
        column_config={
            "Tanggal": st.column_config.TextColumn("Tanggal", disabled=True),
            "Budget Iklan": _mny("Budget Iklan (Rp)"),
            "CPL": _mny("CPL (Rp)"),
            "Opex": _mny("Opex (Rp)"),
        })

    day_rows = [{"budget": r["Budget Iklan"], "cpl": r["CPL"], "opex": r["Opex"]}
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
    mcf = st.columns(4)
    kpi(mcf[0], "Total Kas Masuk (range)", rp(tcf["cash_in"].sum()), cls="green")
    kpi(mcf[1], "Total Kas Keluar (range)", rp(tcf["cash_out"].sum()), cls="amber")
    kpi(mcf[2], "Saldo Akhir Range", rp(res_cf["saldo_akhir"]),
        cls="green" if res_cf["saldo_akhir"] >= 0 else "amber")
    kpi(mcf[3], "⏳ Outstanding Omzet (cair setelah range)", rp(res_cf["outstanding"]),
        "COD order dalam range yg blm cair", cls="amber",
        help="Dana COD dari order selama range ini yang pencairannya jatuh SETELAH hari "
             "terakhir range — tetap akan cair meski belanja iklan hanya di range ini.")

    st.markdown("#### 💡 Insight Otomatis")
    for line in insights.cashflow_insights(sim):
        st.markdown(f'<div class="insight">• {line}</div>', unsafe_allow_html=True)

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
        cpl=eff_cpl, budget_harian=tot_bud, opex_30=opex_30,
    )
    # faktor likuiditas (fraksi COD yang cair ≤ T) — ambil dari 1x simulasi acuan
    syn0 = pd.DataFrame([{"Produk": "acuan", "Budget/Hari": max(base["budget_harian"], 1_000_000),
                          "CPL": base["cpl"] or config.DEFAULTS["cpl"],
                          "Nilai Produk": base["nilai_produk"], "HPP": base["hpp"]}])
    ov0 = dict(closing_rate=base["closing"], success_rate=base["success"], ongkir_per_resi=ongkir,
               cashback_pct=base["cashback_pct"], cod_fee_rate=base["cod_fee_rate"],
               pct_cod=base["pct_cod"], opex_30=base["opex_30"], horizon_days=target_days,
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
        kpi(gl[2], "Opex Maksimal / 30 hari", "≤ " + rp(L.get("opex_30_max", 0)),
            f"skrg {rp(base['opex_30'])}", cls="green",
            help="Batas biaya operasional teknis sebelum target gagal.")
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
                pct_cod=sc["pct_cod"], opex_30=opex_30, horizon_days=target_days,
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
    kpi(d2[2], "⭐ Modal Awal Dibutuhkan", rp(st_["modal_awal"]),
        "dana diputar di awal", cls="amber")
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
