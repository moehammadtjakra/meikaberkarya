# -*- coding: utf-8 -*-
"""
cashflow_engine.py
==================
Inti aplikasi: Simulator Proyeksi Pencairan Dana & Cashflow.

Mengambil parameter marketing/pengiriman/pembayaran + baseline histori,
lalu mensimulasikan funnel (Lead -> Order -> Resi -> Sampai -> Dana Cair)
dan menghasilkan timeline cashflow harian/mingguan/bulanan, outstanding COD,
jadwal pencairan, serta estimasi kebutuhan modal kerja.

CATATAN ASUMSI (transparan, dapat diubah lewat parameter):
- `proyeksi_net` adalah margin BERSIH per resi sukses (sudah dikurangi ongkir
  & COD fee). Ongkir & cashback ditampilkan sebagai komponen biaya informatif
  agar tidak dihitung ganda terhadap kas.
- COD: dana bersih cair pada TANGGAL PENCAIRAN (delay = distribusi waktu terima
  histori + aturan settlement mode terpilih).
- Transfer (non-COD): dianggap prabayar, kas masuk pada hari kirim.
"""

from __future__ import annotations
from collections import defaultdict
import numpy as np
import pandas as pd

import config
import settlement_engine as se


def build_params(baseline: dict, overrides: dict | None = None) -> dict:
    """Gabungkan default + baseline histori + override pengguna."""
    p = {
        "modal_awal": config.DEFAULTS.get("modal_awal", 0),
        "budget_harian": config.DEFAULTS["budget_harian"],
        "cpl": config.DEFAULTS["cpl"],
        "closing_rate": config.DEFAULTS["closing_rate"],
        "success_rate": baseline.get("success_rate", config.DEFAULTS["success_rate"]),
        "ongkir_per_resi": baseline.get("avg_total_biaya",
                                        baseline.get("avg_ongkir", config.DEFAULTS["ongkir_per_resi"])),
        "nilai_produk": baseline.get("avg_nilai_produk", config.DEFAULTS["nilai_produk"]),
        "hpp": baseline.get("avg_nilai_produk", config.DEFAULTS["nilai_produk"]) * config.DEFAULTS["hpp_ratio"],
        "cashback_pct": baseline.get("cashback_pct", config.DEFAULTS["cashback_pct"]),
        "cod_fee_rate": baseline.get("cod_fee_rate", config.DEFAULTS["cod_fee_rate"]),
        "pct_cod": baseline.get("pct_cod", config.DEFAULTS["pct_cod"]),
        "horizon_days": config.DEFAULTS["horizon_days"],
        "opex_fix_bulan": config.DEFAULTS.get("opex_fix_bulan", 0),
        "opex_var_resi": config.DEFAULTS.get("opex_var_resi", 0),
        "payday": config.DEFAULTS.get("payday", 25),
        "mode": "mode2",
        "daily_lag": config.SETTLE_DAILY_LAG_DEFAULT,
        "start_date": pd.Timestamp.today().normalize(),
    }
    if overrides:
        p.update({k: v for k, v in overrides.items() if v is not None})

    # Budget iklan total = budget harian x horizon
    p["budget_iklan"] = p["budget_harian"] * int(p["horizon_days"])

    # --- Turunan ekonomi per resi (formula tervalidasi dari histori) ---
    #   Nilai COD    = Nilai Produk + Ongkir (Total Biaya)
    #   Cashback     = cashback_pct x Ongkir   (Biaya Diskon, jadi OMZET/income)
    #   COD Fee      = cod_fee_rate x Nilai COD
    #   Margin Produk= Nilai Produk - HPP  (laba kotor produk)
    #   Net REAL     = (Nilai Produk - HPP) + Cashback - COD Fee
    p["cashback_ongkir"] = p["cashback_pct"] * p["ongkir_per_resi"]
    p["avg_nilai_cod"] = p["nilai_produk"] + p["ongkir_per_resi"]
    p["cod_fee"] = p["cod_fee_rate"] * p["avg_nilai_cod"]
    p["margin_produk"] = p["nilai_produk"] - p["hpp"]
    p["avg_proyeksi_net"] = p["margin_produk"] + p["cashback_ongkir"] - p["cod_fee"]
    return p


def _receive_lag_dist(recv_dist, avg_durasi: float) -> dict:
    """Kembalikan dict {lag_hari: probabilitas}. Fallback ke titik tunggal."""
    if recv_dist is not None and len(recv_dist) > 0:
        return {int(k): float(v) for k, v in recv_dist.items()}
    lag = max(int(round(avg_durasi or config.DEFAULTS["avg_durasi"])), 1)
    return {lag: 1.0}


def _shift_lag_dist(recv_dist, target_mean) -> dict:
    """
    Geser distribusi lama-kirim historis agar rata-ratanya = target_mean (hari),
    sambil mempertahankan bentuk sebaran (variasi hari-dalam-minggu tetap realistis).
    Dipakai bila pengguna mengubah input rata-rata durasi kirim.
    """
    if recv_dist is None or len(recv_dist) == 0:
        return {max(int(round(target_mean or 1)), 1): 1.0}
    items = [(int(k), float(v)) for k, v in recv_dist.items()]
    tot = sum(v for _, v in items) or 1.0
    cur_mean = sum(k * v for k, v in items) / tot
    if not target_mean or target_mean <= 0:
        return {k: v for k, v in items}
    shift = int(round(target_mean - cur_mean))
    out = defaultdict(float)
    for k, v in items:
        out[max(k + shift, 1)] += v
    return dict(out)


def payday_schedule(start, horizon, payday_dom, amount) -> dict:
    """
    Jadwal pembayaran opex TETAP (gaji): {tanggal_gajian: nominal} untuk tiap bulan
    kalender dalam periode operasi [start, start+horizon-1]. Bila tanggal gajian
    melebihi jumlah hari bulan, dipakai hari terakhir bulan itu.
    """
    out = {}
    amount = float(amount or 0)
    if amount <= 0 or horizon <= 0:
        return out
    start = pd.Timestamp(start).normalize()
    end = start + pd.Timedelta(days=int(horizon) - 1)
    cur = pd.Timestamp(start.year, start.month, 1)
    while cur <= end:
        dom = min(int(payday_dom or 25), cur.days_in_month)
        pay = pd.Timestamp(cur.year, cur.month, dom)
        if start <= pay <= end:
            out[pay] = out.get(pay, 0.0) + amount
        cur = cur + pd.offsets.MonthBegin(1)
    return out


def _build_timeline(start, horizon, recv_dist, avg_durasi, resi_per_day,
                    ad_per_day, success_rate, pct_cod, cod_disb, tr_in,
                    hpp_per_resi, return_ongkir, opex_var_per_resi, opex_fix_sched,
                    mode, daily_lag, stock_orders_free=0.0) -> pd.DataFrame:
    """
    Timeline cashflow harian (model kas realistis, COD vs Non-COD dipisah).

    Masuk:
      - Non-COD (transfer): kas masuk HARI KIRIM = Harga Produk + Ongkir penuh
        (prabayar, likuid langsung; tanpa fee COD/cashback).
      - COD: kas masuk di TANGGAL PENCAIRAN = Harga Produk + Cashback − Fee COD
        (setelah paket diterima + skema settlement).
    Keluar:
      - Biaya iklan & pembelian produk (HPP semua paket dikirim) di hari kirim.
      - Biaya operasional (opex) per hari.
      - Ongkir retur (per paket gagal, sesuai aturan J&T) saat paket diterima/retur.

    Selain KAS, dihitung juga LABA AKRUAL harian (pengakuan omzet & HPP saat paket
    diterima/terjual; HPP paket retur TIDAK jadi beban karena barang kembali).
    """
    lag_dist = _receive_lag_dist(recv_dist, avg_durasi)
    cod_cair = defaultdict(float)        # kas COD cair (tgl pencairan)
    transfer_in = defaultdict(float)     # kas transfer (hari kirim)
    cod_shipped = defaultdict(float)     # omzet COD earned (tgl diterima)
    return_out = defaultdict(float)      # biaya ongkir retur (tgl retur ≈ diterima)
    rev_accr = defaultdict(float)        # omzet diakui (akrual)
    cogs_accr = defaultdict(float)       # HPP barang terjual (akrual)

    ship_days = [start + pd.Timedelta(days=i) for i in range(horizon)]
    for d in ship_days:
        s_cod = resi_per_day * success_rate * pct_cod
        s_tr = resi_per_day * success_rate * (1 - pct_cod)
        s_gagal = resi_per_day * (1 - success_rate)
        transfer_in[d] += s_tr * tr_in
        # akrual transfer diakui di hari kirim (prabayar & langsung dikirim)
        rev_accr[d] += s_tr * tr_in
        cogs_accr[d] += s_tr * hpp_per_resi
        for lag, prob in lag_dist.items():
            recv = d + pd.Timedelta(days=int(lag))
            chunk = s_cod * prob * cod_disb
            cod_shipped[recv] += chunk
            return_out[recv] += s_gagal * prob * return_ongkir
            # akrual COD diakui saat paket DITERIMA
            rev_accr[recv] += chunk
            cogs_accr[recv] += s_cod * prob * hpp_per_resi
            payout = (se.payout_date_mode1(recv, daily_lag)
                      if mode == "mode1" else se.payout_date_mode2(recv))
            if pd.notna(payout):
                cod_cair[payout] += chunk

    all_dates = (set(ship_days) | set(cod_cair) | set(cod_shipped)
                 | set(transfer_in) | set(return_out))
    if not all_dates:
        all_dates = {start}
    full_range = pd.date_range(min(all_dates), max(all_dates))

    rows = []
    for d in full_range:
        in_ship = start <= d < start + pd.Timedelta(days=horizon)
        ad = ad_per_day if in_ship else 0.0
        # HPP cash-out STOK-AWARE: order awal dipenuhi stok gudang (tak beli),
        # pembelian baru hanya untuk order melebihi total stok (depletion back-loaded).
        if in_ship:
            _si = (d - start).days
            _N = resi_per_day * horizon
            _cs = resi_per_day * _si
            _ce = resi_per_day * (_si + 1)
            buy_orders = max(min(_ce, _N) - max(_cs, stock_orders_free), 0.0)
            hpp_spend = buy_orders * hpp_per_resi
        else:
            hpp_spend = 0.0
        # Opex = variabel per resi (skala volume, hari kirim) + tetap/gaji (lump saat gajian)
        opex_var = (resi_per_day * opex_var_per_resi) if in_ship else 0.0
        opex = opex_var + opex_fix_sched.get(d, 0.0)
        ti = transfer_in.get(d, 0.0)
        cc = cod_cair.get(d, 0.0)
        cs = cod_shipped.get(d, 0.0)
        ro = return_out.get(d, 0.0)
        rev_a = rev_accr.get(d, 0.0)
        cogs_a = cogs_accr.get(d, 0.0)
        laba = rev_a - cogs_a - ad - opex - ro
        rows.append({
            "tanggal": d, "ad_spend": ad, "hpp_spend": hpp_spend, "opex": opex,
            "return_ongkir": ro,
            "transfer_in": ti, "cod_cair": cc, "cod_shipped": cs,
            "cash_in": ti + cc, "cash_out": ad + hpp_spend + opex + ro,
            "omzet_realized": ti + cc, "omzet_earned": ti + cs,
            "net_cashflow": ti + cc - ad - hpp_spend - opex - ro,
            "rev_accrual": rev_a, "cogs_accrual": cogs_a, "laba_harian": laba,
        })
    tl = pd.DataFrame(rows)
    tl["cum_net"] = tl["net_cashflow"].cumsum()
    tl["cum_ad"] = tl["ad_spend"].cumsum()
    tl["cum_hpp"] = tl["hpp_spend"].cumsum()
    tl["cum_opex"] = tl["opex"].cumsum()
    tl["cum_cash_in"] = tl["cash_in"].cumsum()
    tl["cum_cash_out"] = tl["cash_out"].cumsum()
    tl["cum_omzet_realized"] = tl["omzet_realized"].cumsum()
    tl["cum_omzet_earned"] = tl["omzet_earned"].cumsum()
    tl["cum_cod_shipped"] = tl["cod_shipped"].cumsum()
    tl["cum_cod_cair"] = tl["cod_cair"].cumsum()
    tl["cod_outstanding"] = tl["cum_cod_shipped"] - tl["cum_cod_cair"]
    tl["omzet_outstanding"] = tl["cum_omzet_earned"] - tl["cum_omzet_realized"]
    # SALDO KAS kumulatif (posisi kas = kas masuk − kas keluar)
    tl["saldo_kas"] = tl["net_cashflow"].cumsum()
    tl["cum_cash"] = tl["saldo_kas"]
    tl["modal_kerja_kumulatif"] = tl["saldo_kas"]
    # LABA AKRUAL kumulatif
    tl["laba_kumulatif"] = tl["laba_harian"].cumsum()
    return tl


def simulate(baseline: dict, recv_dist: pd.Series, overrides: dict) -> dict:
    p = build_params(baseline, overrides)
    horizon = int(p["horizon_days"])
    start = pd.Timestamp(p["start_date"]).normalize()

    # ---------------- FUNNEL (total) ----------------
    n_lead = p["budget_iklan"] / p["cpl"] if p["cpl"] else 0
    n_order = n_lead * p["closing_rate"]
    n_resi = n_order                      # asumsi 1 order = 1 resi
    n_sukses = n_resi * p["success_rate"]
    n_gagal = n_resi - n_sukses

    total_ongkir = n_resi * p["ongkir_per_resi"]
    # komponen omzet/net berbasis paket sukses (selaras dengan total_net)
    total_cashback = n_sukses * p["cashback_ongkir"]      # omzet/income
    total_nilai_produk = n_sukses * p["nilai_produk"]
    total_hpp = n_sukses * p["hpp"]
    total_margin_produk = n_sukses * p["margin_produk"]
    total_cod_fee = n_sukses * p["cod_fee"]
    total_net = n_sukses * p["avg_proyeksi_net"]

    sukses_cod = n_sukses * p["pct_cod"]
    sukses_transfer = n_sukses * (1 - p["pct_cod"])
    nilai_cod = sukses_cod * p["avg_nilai_cod"]
    nilai_transfer = sukses_transfer * p["avg_nilai_cod"]
    net_cod = sukses_cod * p["avg_proyeksi_net"]
    net_transfer = sukses_transfer * p["avg_proyeksi_net"]

    # ---------------- TIMELINE HARIAN ----------------
    resi_per_day = n_resi / horizon if horizon else 0
    ad_per_day = p["budget_iklan"] / horizon if horizon else 0
    cod_disb = p["nilai_produk"] + p["cashback_ongkir"] - p["cod_fee"]
    tr_in = p["nilai_produk"] + p["ongkir_per_resi"]
    return_ongkir = max(p["ongkir_per_resi"] - p["cashback_ongkir"], 0)
    tl = _build_timeline(
        start, horizon, recv_dist, baseline.get("avg_durasi"),
        resi_per_day, ad_per_day, p["success_rate"], p["pct_cod"],
        cod_disb, tr_in, p["hpp"], return_ongkir, 0.0, {},
        p["mode"], p["daily_lag"])

    # ---------------- AGREGASI MINGGUAN / BULANAN ----------------
    weekly = _resample(tl, "W-MON")
    monthly = _resample(tl, "MS")

    # ---------------- KPI RINGKAS ----------------
    today = pd.Timestamp.today().normalize()
    week_end = today + pd.Timedelta(days=7)
    month_end = today + pd.Timedelta(days=30)
    cair_minggu = tl.loc[(tl["tanggal"] >= today) & (tl["tanggal"] < week_end), "cod_cair"].sum() \
        + tl.loc[(tl["tanggal"] >= today) & (tl["tanggal"] < week_end), "transfer_in"].sum()
    cair_bulan = tl.loc[(tl["tanggal"] >= today) & (tl["tanggal"] < month_end), "cod_cair"].sum() \
        + tl.loc[(tl["tanggal"] >= today) & (tl["tanggal"] < month_end), "transfer_in"].sum()

    modal_kerja = float(-tl["modal_kerja_kumulatif"].min())
    modal_kerja = max(modal_kerja, 0.0)
    outstanding_peak = float(tl["cod_outstanding"].max())

    summary = {
        "budget_iklan": p["budget_iklan"],
        "budget_harian": p["budget_harian"],
        "n_lead": n_lead, "n_order": n_order, "n_resi": n_resi,
        "n_sukses": n_sukses, "n_gagal": n_gagal,
        "success_rate": p["success_rate"],
        "total_ongkir": total_ongkir, "total_cashback": total_cashback,
        "total_nilai_produk": total_nilai_produk, "total_cod_fee": total_cod_fee,
        "total_hpp": total_hpp, "total_margin_produk": total_margin_produk,
        "modal_hpp": n_resi * p["hpp"],
        "total_net": total_net,
        "nilai_cod": nilai_cod, "nilai_transfer": nilai_transfer,
        "net_cod": net_cod, "net_transfer": net_transfer,
        "pct_cod": p["pct_cod"], "pct_transfer": 1 - p["pct_cod"],
        "avg_net_per_resi": p["avg_proyeksi_net"],
        "avg_durasi": baseline.get("avg_durasi"),
        "cair_minggu_ini": cair_minggu, "cair_bulan_ini": cair_bulan,
        "outstanding_peak": outstanding_peak,
        "outstanding_akhir": float(tl["cod_outstanding"].iloc[-1]),
        "net_cashflow_total": float(tl["net_cashflow"].sum()),
        "modal_kerja": modal_kerja,
        "horizon_days": horizon,
        "params": p,
    }

    funnel = {
        "Lead": n_lead, "Order": n_order, "Resi": n_resi,
        "Paket Sampai": n_sukses,
    }

    return {"summary": summary, "timeline": tl, "weekly": weekly,
            "monthly": monthly, "funnel": funnel}


def _resample(tl: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = (tl.set_index("tanggal")
           [["ad_spend", "hpp_spend", "opex", "return_ongkir",
             "transfer_in", "cod_cair", "net_cashflow"]]
           .resample(rule).sum().reset_index())
    g["cum_net"] = g["net_cashflow"].cumsum()
    return g


_BULAN_ID = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
             7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"}


def monthly_pnl(tl: pd.DataFrame, modal_awal: float = 0.0) -> pd.DataFrame:
    """
    Laba-Rugi (akrual) + Arus Kas per BULAN KALENDER, plus saldo kas akhir tiap bulan.
    Kolom akrual: omzet, HPP terjual, iklan, opex, retur -> laba bersih (akrual).
    Kolom kas   : kas masuk, kas keluar, arus kas bersih, saldo kas akhir (= modal +
                  akumulasi arus kas s/d akhir bulan itu).
    """
    if tl is None or tl.empty:
        return pd.DataFrame()
    d = tl.copy()
    d["bulan"] = d["tanggal"].dt.to_period("M")
    agg = (d.groupby("bulan").agg(
        omzet=("rev_accrual", "sum"),
        hpp_terjual=("cogs_accrual", "sum"),
        iklan=("ad_spend", "sum"),
        opex=("opex", "sum"),
        retur=("return_ongkir", "sum"),
        laba_bersih=("laba_harian", "sum"),
        kas_masuk=("cash_in", "sum"),
        kas_keluar=("cash_out", "sum"),
        arus_kas=("net_cashflow", "sum"),
    ).reset_index())
    agg["laba_kumulatif"] = agg["laba_bersih"].cumsum()
    agg["saldo_kas_akhir"] = modal_awal + agg["arus_kas"].cumsum()
    agg["label"] = agg["bulan"].apply(lambda p: f"{_BULAN_ID[p.month]} {p.year}")
    return agg


def simulate_multi(baseline: dict, recv_dist: pd.Series,
                   product_rows: pd.DataFrame, overrides: dict) -> dict:
    """
    Simulasi multi-produk: tiap produk punya Budget/Hari, CPL, Nilai Produk, HPP
    sendiri. Funnel & ekonomi dihitung per produk lalu diagregasi; timeline
    cashflow memakai nilai efektif (rata-rata tertimbang).
    """
    p = build_params(baseline, overrides)              # ambil rate global
    horizon = int(p["horizon_days"])
    start = pd.Timestamp(p["start_date"]).normalize()
    ongkir = p["ongkir_per_resi"]
    cashback = p["cashback_ongkir"]                      # = cashback_pct x ongkir
    cod_fee_rate = p["cod_fee_rate"]
    closing = p["closing_rate"]
    success = p["success_rate"]
    pct_cod = p["pct_cod"]

    # Ongkir retur (aturan J&T): gratis bila retur ≤ ambang (20%); jika melebihi,
    # biaya = (retur% − ambang) × ongkir PENUH untuk tiap paket retur.
    return_rate = 1 - success
    retur_excess = max(return_rate - config.RETUR_FREE_THRESHOLD, 0.0)
    return_ongkir = retur_excess * ongkir            # per paket gagal

    rows = []
    def _f(x):
        v = pd.to_numeric(x, errors="coerce")
        return float(v) if pd.notna(v) else 0.0

    for _, r in product_rows.iterrows():
        bh = _f(r.get("Budget/Hari"))
        cpl = _f(r.get("CPL"))
        nilai_produk = _f(r.get("Nilai Produk"))
        hpp = _f(r.get("HPP"))
        stok_pcs = _f(r.get("Stok (pcs)"))
        pcs_order = _f(r.get("Pcs/Order")) or 1.0
        nama = str(r.get("Produk", "-"))
        if not nama or nama in ("-", "nan", "None"):
            continue  # lewati baris kosong
        budget_total = bh * horizon
        lead = budget_total / cpl if cpl > 0 else 0
        order = lead * closing
        resi = order
        sukses = resi * success
        gagal = resi - sukses
        # STOK: berapa order yang bisa dipenuhi dari stok gudang (tanpa beli baru)
        stock_orders = (stok_pcs / pcs_order) if pcs_order > 0 else 0.0
        orders_from_stock = min(resi, stock_orders)
        orders_buy = max(resi - stock_orders, 0.0)
        # kas masuk per resi sukses, dibedakan metode bayar
        cod_disb = nilai_produk + cashback - cod_fee_rate * (nilai_produk + ongkir)
        tr_in = nilai_produk + ongkir                # transfer: produk + ongkir penuh
        sukses_cod = sukses * pct_cod
        sukses_tr = sukses * (1 - pct_cod)
        revenue = sukses_cod * cod_disb + sukses_tr * tr_in   # total kas masuk kotor
        cogs = hpp * sukses                          # HPP hanya barang terjual (retur balik)
        return_cost = return_ongkir * gagal          # ongkir retur paket gagal
        modal_hpp = hpp * resi                        # HPP semua paket (bila beli semua)
        beli_hpp = hpp * orders_buy                    # kas beli baru (di atas stok)
        hemat_hpp = hpp * orders_from_stock            # hemat dari stok gudang
        net_total = revenue - cogs - return_cost - budget_total   # laba produk (sblm opex)
        margin_jual = nilai_produk - hpp
        opex_var_r = float(p.get("opex_var_resi", 0) or 0)
        # Contribution Margin per order sukses (setelah fee, +cashback, −opex var)
        cm = nilai_produk - hpp - cod_fee_rate * (nilai_produk + ongkir) + cashback - opex_var_r
        cm_pct = (cm / nilai_produk * 100) if nilai_produk else 0.0
        roi = (net_total / budget_total) if budget_total > 0 else 0
        rows.append({
            "Produk": nama, "budget_harian": bh, "budget_total": budget_total,
            "cpl": cpl, "nilai_produk": nilai_produk, "hpp": hpp,
            "aov": nilai_produk, "cm": cm, "cm_pct": cm_pct,
            "stok_pcs": stok_pcs, "pcs_order": pcs_order, "stock_orders": stock_orders,
            "orders_from_stock": orders_from_stock, "orders_buy": orders_buy,
            "lead": lead, "order": order, "resi": resi, "sukses": sukses, "gagal": gagal,
            "cod_disb": cod_disb, "tr_in": tr_in,
            "margin_jual_per_resi": margin_jual,
            "net_per_resi": (net_total / resi) if resi else 0,
            "modal_hpp": modal_hpp, "beli_hpp": beli_hpp, "hemat_hpp": hemat_hpp,
            "revenue": revenue, "cogs": cogs,
            "return_cost": return_cost, "net_total": net_total, "roi": roi,
        })
    cols = ["Produk", "budget_harian", "budget_total", "cpl", "nilai_produk", "hpp",
            "aov", "cm", "cm_pct",
            "stok_pcs", "pcs_order", "stock_orders", "orders_from_stock", "orders_buy",
            "lead", "order", "resi", "sukses", "gagal", "cod_disb", "tr_in",
            "margin_jual_per_resi", "net_per_resi", "modal_hpp", "beli_hpp", "hemat_hpp",
            "revenue", "cogs", "return_cost", "net_total", "roi"]
    pdf = pd.DataFrame(rows, columns=cols)

    # ---- agregasi ----
    n_lead = pdf["lead"].sum(); n_order = pdf["order"].sum()
    n_resi = pdf["resi"].sum(); n_sukses = pdf["sukses"].sum(); n_gagal = pdf["gagal"].sum()
    budget_harian_tot = pdf["budget_harian"].sum()
    budget_total = pdf["budget_total"].sum()
    total_modal_hpp = pdf["modal_hpp"].sum()                 # HPP semua paket (full)
    total_stock_orders = pdf["orders_from_stock"].sum()      # order tercukupi stok
    total_revenue = pdf["revenue"].sum()
    total_cogs = pdf["cogs"].sum()
    total_return_cost = pdf["return_cost"].sum()
    total_hpp = total_cogs                                   # COGS = HPP terjual
    total_nilai_produk = (pdf["sukses"] * pdf["nilai_produk"]).sum()
    sukses_cod = n_sukses * pct_cod
    sukses_transfer = n_sukses * (1 - pct_cod)
    total_cashback = sukses_cod * cashback                  # cashback COD saja
    total_cod_fee = (pdf["sukses"] * pct_cod * cod_fee_rate
                     * (pdf["nilai_produk"] + ongkir)).sum()
    total_ongkir = n_resi * ongkir
    # kas masuk COD vs transfer (untuk KPI)
    nilai_cod = (pdf["sukses"] * pct_cod * pdf["cod_disb"]).sum()
    nilai_transfer = (pdf["sukses"] * (1 - pct_cod) * pdf["tr_in"]).sum()

    # bobot efektif untuk timeline
    eff_cod_disb = (nilai_cod / sukses_cod) if sukses_cod else 0
    eff_tr_in = (nilai_transfer / sukses_transfer) if sukses_transfer else 0
    eff_hpp_resi = total_modal_hpp / n_resi if n_resi else 0
    eff_net = (pdf["net_total"].sum() / n_sukses) if n_sukses else 0

    # OPEX: tetap/bulan (gaji, sewa) keluar LUMP di tanggal gajian; variabel per resi.
    opex_fix_bulan = float(p.get("opex_fix_bulan", 0) or 0)
    opex_var_resi = float(p.get("opex_var_resi", 0) or 0)
    payday = int(p.get("payday", 25) or 25)
    opex_fix_sched = payday_schedule(start, horizon, payday, opex_fix_bulan)

    resi_per_day = n_resi / horizon if horizon else 0
    ad_per_day = budget_harian_tot
    # Rata-rata durasi kirim bisa dioverride pengguna → geser distribusi terima,
    # sehingga tanggal paket sampai (dan pencairan Sen/Sel/Kam) ikut menyesuaikan.
    durasi_ovr = p.get("durasi_override")
    eff_recv = (_shift_lag_dist(recv_dist, durasi_ovr) if durasi_ovr else recv_dist)
    avg_dur_eff = durasi_ovr or baseline.get("avg_durasi")
    tl = _build_timeline(start, horizon, eff_recv, avg_dur_eff,
                         resi_per_day, ad_per_day, success, pct_cod,
                         eff_cod_disb, eff_tr_in, eff_hpp_resi, return_ongkir,
                         opex_var_resi, opex_fix_sched, p["mode"], p["daily_lag"],
                         stock_orders_free=total_stock_orders)
    total_opex = float(tl["opex"].sum())                 # opex aktual (tetap + variabel)
    total_beli_produk = float(tl["hpp_spend"].sum())     # kas beli produk (stok-aware)
    stok_hemat = max(total_modal_hpp - total_beli_produk, 0.0)  # penghematan dari stok

    weekly = _resample(tl, "W-MON")
    monthly = _resample(tl, "MS")

    today = pd.Timestamp.today().normalize()
    week_end = today + pd.Timedelta(days=7)
    month_end = today + pd.Timedelta(days=30)
    mask_w = (tl["tanggal"] >= today) & (tl["tanggal"] < week_end)
    mask_m = (tl["tanggal"] >= today) & (tl["tanggal"] < month_end)
    cair_minggu = tl.loc[mask_w, "cod_cair"].sum() + tl.loc[mask_w, "transfer_in"].sum()
    cair_bulan = tl.loc[mask_m, "cod_cair"].sum() + tl.loc[mask_m, "transfer_in"].sum()

    # ---- LIKUIDITAS DALAM HORIZON (dana yang benar-benar cair ≤ T) ----
    horizon_end = start + pd.Timedelta(days=horizon)
    in_hz = tl["tanggal"] < horizon_end
    total_cod_earned = float(tl["cod_shipped"].sum())          # total disbursement COD (semua waktu)
    cod_cleared_hz = float(tl.loc[in_hz, "cod_cair"].sum())    # COD cair dalam horizon
    lam_cod = (cod_cleared_hz / total_cod_earned) if total_cod_earned else 1.0
    total_ret_amt = float(tl["return_ongkir"].sum())
    ret_hz = float(tl.loc[in_hz, "return_ongkir"].sum())
    lam_ret = (ret_hz / total_ret_amt) if total_ret_amt else 1.0
    cash_in_likuid = float(tl.loc[in_hz, "cash_in"].sum())     # kas benar-benar masuk ≤ T
    cash_out_horizon = float(tl.loc[in_hz, "cash_out"].sum())  # kas keluar ≤ T
    laba_likuid = cash_in_likuid - cash_out_horizon            # laba bersih LIKUID dalam horizon
    outstanding_dana = total_cod_earned - cod_cleared_hz       # COD blm cair di akhir horizon

    # ---- METRIK MODAL KERJA (audit) ----
    # LABA BERSIH (akrual): HPP barang retur TIDAK rugi (barang kembali & dijual ulang)
    net_profit = (total_revenue - total_cogs - total_return_cost
                  - budget_total - total_opex)
    # SALDO KAS: modal awal = defisit kas terdalam; HPP retur ikut membebani kas
    saldo_min = float(tl["saldo_kas"].min())
    modal_awal = max(-saldo_min, 0.0)
    cash_net_total = float(tl["net_cashflow"].sum())        # arus kas bersih horizon
    roi_modal = (net_profit / modal_awal * 100) if modal_awal > 0 else 0.0
    roi_iklan = (net_profit / budget_total * 100) if budget_total > 0 else 0.0
    def _hari(mask):
        s = tl.loc[mask, "tanggal"]
        return int((s.iloc[0] - start).days) if not s.empty else None

    # BEP KAS: hari pertama saldo kas kumulatif kembali >= 0 (kas mulai positif).
    # CATATAN: ini BUKAN titik aman menarik modal — kas masih bisa turun lagi.
    trough_idx = int(tl["saldo_kas"].idxmin())
    after = tl.iloc[trough_idx:]
    bk = after.loc[after["saldo_kas"] >= 0, "tanggal"]
    hari_bep_kas = (int((bk.iloc[0] - start).days)
                    if not bk.empty and net_profit > 0 else None)
    hari_balik_modal = hari_bep_kas   # alias kompatibilitas
    # HARI AMAN KEMBALIKAN MODAL: hari pertama saldo kas TIDAK PERNAH negatif lagi
    # sesudahnya → menarik modal awal di hari ini tak membuat cashflow minus lagi.
    neg = tl["saldo_kas"] < -1e-6
    if not neg.any():
        hari_kembali_modal = 0
    elif bool(neg.iloc[-1]):
        hari_kembali_modal = None      # masih defisit di akhir simulasi
    else:
        last_neg_date = tl.loc[neg, "tanggal"].max()
        hari_kembali_modal = int((last_neg_date - start).days) + 1
    saldo_di_hari_kembali = (float(tl.loc[tl["tanggal"] ==
                             start + pd.Timedelta(days=hari_kembali_modal), "saldo_kas"].iloc[0])
                             if hari_kembali_modal is not None
                             and (tl["tanggal"] == start + pd.Timedelta(days=hari_kembali_modal)).any()
                             else None)
    # hari pertama LABA (akrual) kumulatif >= 0
    hari_laba_positif = _hari(tl["laba_kumulatif"] >= 0) if net_profit > 0 else None
    # hari pertama ARUS KAS HARIAN >= 0
    hari_cashflow_positif = _hari(tl["net_cashflow"] >= 0)
    # self-sustaining: arus kas harian >= 0 dan tetap positif s/d akhir
    hari_self_sustaining = None
    nc = tl["net_cashflow"].values
    for i in range(len(nc)):
        if nc[i] >= -1e-6 and all(v >= -1e-6 for v in nc[i:]):
            hari_self_sustaining = int((tl["tanggal"].iloc[i] - start).days)
            break
    laba_akhir_positif = bool(tl["laba_kumulatif"].iloc[-1] >= 0)

    # ---- MODAL AWAL (input) → POSISI KAS RIIL & RUNWAY ----
    modal_awal_input = float(p.get("modal_awal", 0) or 0)
    tl["kas_riil"] = modal_awal_input + tl["net_cashflow"].cumsum()
    neg_riil = tl["kas_riil"] < -1e-6
    hari_kas_habis = (int((tl.loc[neg_riil, "tanggal"].iloc[0] - start).days)
                      if neg_riil.any() else None)     # None = kas tak pernah habis
    kas_riil_terendah = float(tl["kas_riil"].min())
    modal_cukup = bool(kas_riil_terendah >= -1e-6)      # modal menutup defisit terdalam
    kekurangan_modal = max(-kas_riil_terendah, 0.0)     # tambahan modal bila kurang

    last_day = int((tl["tanggal"].iloc[-1] - start).days)

    def _kas_at(day):
        dt = start + pd.Timedelta(days=day)
        r = tl.loc[tl["tanggal"] == dt, "kas_riil"]
        return float(r.iloc[0]) if not r.empty else None

    def _laba_akrual_at(day):
        dt = start + pd.Timedelta(days=day)
        r = tl.loc[tl["tanggal"] <= dt, "laba_harian"]
        return float(r.sum()) if len(r) else None

    posisi = {}                                          # {hari: {kas, laba_akrual}}
    for day in (30, 60, 90, horizon):
        if day <= last_day:
            posisi[day] = {"kas": _kas_at(day), "laba_akrual": _laba_akrual_at(day)}
    kas_riil_akhir = float(tl["kas_riil"].iloc[-1])      # setelah semua COD cair

    monthly_tab = monthly_pnl(tl, modal_awal_input)

    p["budget_harian"] = budget_harian_tot
    p["budget_iklan"] = budget_total
    summary = {
        "budget_iklan": budget_total, "budget_harian": budget_harian_tot,
        "n_lead": n_lead, "n_order": n_order, "n_resi": n_resi,
        "n_sukses": n_sukses, "n_gagal": n_gagal, "success_rate": success,
        "total_ongkir": total_ongkir, "total_cashback": total_cashback,
        "total_nilai_produk": total_nilai_produk, "total_cod_fee": total_cod_fee,
        "total_hpp": total_hpp, "total_revenue": total_revenue,
        "total_cogs": total_cogs, "total_return_cost": total_return_cost,
        "return_ongkir_per_paket": return_ongkir,
        "modal_hpp": total_modal_hpp, "total_net": net_profit,
        "nilai_cod": nilai_cod, "nilai_transfer": nilai_transfer,
        "net_cod": sukses_cod * eff_net, "net_transfer": sukses_transfer * eff_net,
        "pct_cod": pct_cod, "pct_transfer": 1 - pct_cod,
        "avg_net_per_resi": eff_net, "avg_durasi": baseline.get("avg_durasi"),
        "cair_minggu_ini": cair_minggu, "cair_bulan_ini": cair_bulan,
        "outstanding_peak": float(tl["omzet_outstanding"].max()),
        "outstanding_akhir": float(tl["omzet_outstanding"].iloc[-1]),
        "net_cashflow_total": cash_net_total,
        "total_beli_produk": total_beli_produk,        # kas beli produk (stok-aware)
        "total_hpp_full": total_modal_hpp,             # bila beli semua (tanpa stok)
        "stok_hemat": stok_hemat,                      # penghematan dari stok gudang
        "stock_orders_total": total_stock_orders,      # order tercukupi stok
        "total_opex": total_opex, "opex_fix_bulan": opex_fix_bulan,
        "opex_var_resi": opex_var_resi, "payday": payday,
        "modal_dibutuhkan": modal_awal, "saldo_kas_min": saldo_min,
        "saldo_kas_akhir": float(tl["saldo_kas"].iloc[-1]),
        "modal_kerja": modal_awal, "modal_total": modal_awal,
        # --- Modal awal (INPUT) & posisi kas riil ---
        "modal_awal": modal_awal_input,
        "modal_cukup": modal_cukup, "kekurangan_modal": kekurangan_modal,
        "hari_kas_habis": hari_kas_habis,
        "kas_riil_terendah": kas_riil_terendah, "kas_riil_akhir": kas_riil_akhir,
        "posisi_hari": posisi,
        "net_profit": net_profit, "roi_modal": roi_modal, "roi_iklan": roi_iklan,
        "roi_modal_awal": ((net_profit / modal_awal_input * 100)
                           if modal_awal_input > 0 else 0.0),
        "laba_likuid": laba_likuid, "cash_in_likuid": cash_in_likuid,
        "cash_out_horizon": cash_out_horizon, "outstanding_dana": outstanding_dana,
        "lam_cod": lam_cod, "lam_ret": lam_ret,
        "return_rate": return_rate, "retur_excess": retur_excess,
        "hari_balik_modal": hari_balik_modal, "hari_bep_kas": hari_bep_kas,
        "hari_kembali_modal": hari_kembali_modal,
        "saldo_di_hari_kembali": saldo_di_hari_kembali,
        "hari_laba_positif": hari_laba_positif,
        "hari_cashflow_positif": hari_cashflow_positif,
        "hari_self_sustaining": hari_self_sustaining,
        "laba_akhir_positif": laba_akhir_positif,
        "horizon_days": horizon, "params": p,
    }
    funnel = {"Lead": n_lead, "Order": n_order, "Resi": n_resi,
              "Paket Sampai": n_sukses}
    return {"summary": summary, "timeline": tl, "weekly": weekly,
            "monthly": monthly, "monthly_pnl": monthly_tab,
            "funnel": funnel, "per_product": pdf}
