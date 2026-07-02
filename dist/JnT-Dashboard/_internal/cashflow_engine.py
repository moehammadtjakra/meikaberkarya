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


def _receive_lag_dist(recv_dist: pd.Series, avg_durasi: float) -> dict:
    """Kembalikan dict {lag_hari: probabilitas}. Fallback ke titik tunggal."""
    if recv_dist is not None and len(recv_dist) > 0:
        return {int(k): float(v) for k, v in recv_dist.items()}
    lag = max(int(round(avg_durasi or config.DEFAULTS["avg_durasi"])), 1)
    return {lag: 1.0}


def _build_timeline(start, horizon, recv_dist, avg_durasi, resi_per_day,
                    ad_per_day, success_rate, pct_cod, eff_net, eff_ongkir,
                    eff_cashback, mode, daily_lag) -> pd.DataFrame:
    """Bangun timeline cashflow harian dari kuantitas agregat per hari."""
    lag_dist = _receive_lag_dist(recv_dist, avg_durasi)
    cod_cair = defaultdict(float)
    transfer_in = defaultdict(float)
    cod_shipped = defaultdict(float)

    ship_days = [start + pd.Timedelta(days=i) for i in range(horizon)]
    for d in ship_days:
        s_cod = resi_per_day * success_rate * pct_cod
        s_tr = resi_per_day * success_rate * (1 - pct_cod)
        transfer_in[d] += s_tr * eff_net
        for lag, prob in lag_dist.items():
            recv = d + pd.Timedelta(days=int(lag))
            net_chunk = s_cod * prob * eff_net
            cod_shipped[recv] += net_chunk
            payout = (se.payout_date_mode1(recv, daily_lag)
                      if mode == "mode1" else se.payout_date_mode2(recv))
            if pd.notna(payout):
                cod_cair[payout] += net_chunk

    all_dates = set(ship_days) | set(cod_cair) | set(cod_shipped) | set(transfer_in)
    if not all_dates:
        all_dates = {start}
    full_range = pd.date_range(min(all_dates), max(all_dates))

    rows = []
    for d in full_range:
        in_ship = start <= d < start + pd.Timedelta(days=horizon)
        ad = ad_per_day if in_ship else 0.0
        ong = (resi_per_day * eff_ongkir) if in_ship else 0.0
        cb = (resi_per_day * eff_cashback) if in_ship else 0.0
        ti = transfer_in.get(d, 0.0)
        cc = cod_cair.get(d, 0.0)
        rows.append({
            "tanggal": d, "ad_spend": ad, "ongkir": ong, "cashback": cb,
            "transfer_in": ti, "cod_cair": cc,
            "cod_shipped": cod_shipped.get(d, 0.0),
            "net_cashflow": ti + cc - ad,
        })
    tl = pd.DataFrame(rows)
    tl["cum_net"] = tl["net_cashflow"].cumsum()
    tl["cum_cod_shipped"] = tl["cod_shipped"].cumsum()
    tl["cum_cod_cair"] = tl["cod_cair"].cumsum()
    tl["cod_outstanding"] = tl["cum_cod_shipped"] - tl["cum_cod_cair"]
    tl["cum_outflow"] = tl["ad_spend"].cumsum()
    tl["cum_inflow"] = (tl["transfer_in"] + tl["cod_cair"]).cumsum()
    tl["modal_kerja_kumulatif"] = tl["cum_inflow"] - tl["cum_outflow"]
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
    tl = _build_timeline(
        start, horizon, recv_dist, baseline.get("avg_durasi"),
        resi_per_day, ad_per_day, p["success_rate"], p["pct_cod"],
        p["avg_proyeksi_net"], p["ongkir_per_resi"], p["cashback_ongkir"],
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
        "Paket Sampai": n_sukses, "Dana Cair (net)": total_net,
    }

    return {"summary": summary, "timeline": tl, "weekly": weekly,
            "monthly": monthly, "funnel": funnel}


def _resample(tl: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = (tl.set_index("tanggal")
           [["ad_spend", "ongkir", "cashback", "transfer_in", "cod_cair", "net_cashflow"]]
           .resample(rule).sum().reset_index())
    g["cum_net"] = g["net_cashflow"].cumsum()
    return g


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

    rows = []
    def _f(x):
        v = pd.to_numeric(x, errors="coerce")
        return float(v) if pd.notna(v) else 0.0

    for _, r in product_rows.iterrows():
        bh = _f(r.get("Budget/Hari"))
        cpl = _f(r.get("CPL"))
        nilai_produk = _f(r.get("Nilai Produk"))
        hpp = _f(r.get("HPP"))
        nama = str(r.get("Produk", "-"))
        if not nama or nama in ("-", "nan", "None"):
            continue  # lewati baris kosong
        budget_total = bh * horizon
        lead = budget_total / cpl if cpl > 0 else 0
        order = lead * closing
        resi = order
        sukses = resi * success
        nilai_cod = nilai_produk + ongkir
        cod_fee = cod_fee_rate * nilai_cod
        margin_jual = nilai_produk - hpp
        net = margin_jual + cashback - cod_fee
        modal_hpp = hpp * resi
        revenue = sukses * nilai_produk
        net_total = sukses * net
        margin_total = sukses * margin_jual
        roi = (net_total - budget_total) / budget_total if budget_total > 0 else 0
        rows.append({
            "Produk": nama, "budget_harian": bh, "budget_total": budget_total,
            "cpl": cpl, "nilai_produk": nilai_produk, "hpp": hpp,
            "lead": lead, "order": order, "resi": resi, "sukses": sukses,
            "margin_jual_per_resi": margin_jual, "net_per_resi": net,
            "modal_hpp": modal_hpp, "revenue": revenue, "net_total": net_total,
            "margin_total": margin_total, "nilai_cod_per_resi": nilai_cod,
            "roi": roi,
        })
    cols = ["Produk", "budget_harian", "budget_total", "cpl", "nilai_produk", "hpp",
            "lead", "order", "resi", "sukses", "margin_jual_per_resi", "net_per_resi",
            "modal_hpp", "revenue", "net_total", "margin_total", "nilai_cod_per_resi", "roi"]
    pdf = pd.DataFrame(rows, columns=cols)

    # ---- agregasi ----
    n_lead = pdf["lead"].sum(); n_order = pdf["order"].sum()
    n_resi = pdf["resi"].sum(); n_sukses = pdf["sukses"].sum()
    n_gagal = n_resi - n_sukses
    budget_harian_tot = pdf["budget_harian"].sum()
    budget_total = pdf["budget_total"].sum()
    total_modal_hpp = pdf["modal_hpp"].sum()
    total_net = pdf["net_total"].sum()
    total_margin_produk = pdf["margin_total"].sum()
    total_nilai_produk = pdf["revenue"].sum()
    total_hpp = (pdf["sukses"] * pdf["hpp"]).sum()
    total_cod_fee = (pdf["sukses"] * cod_fee_rate * pdf["nilai_cod_per_resi"]).sum()
    total_cashback = n_sukses * cashback
    total_ongkir = n_resi * ongkir

    eff_net = total_net / n_sukses if n_sukses else 0
    eff_nilai_cod = ((pdf["sukses"] * pdf["nilai_cod_per_resi"]).sum() / n_sukses
                     if n_sukses else 0)
    sukses_cod = n_sukses * pct_cod
    sukses_transfer = n_sukses * (1 - pct_cod)
    nilai_cod = sukses_cod * eff_nilai_cod
    nilai_transfer = sukses_transfer * eff_nilai_cod

    resi_per_day = n_resi / horizon if horizon else 0
    ad_per_day = budget_harian_tot
    tl = _build_timeline(start, horizon, recv_dist, baseline.get("avg_durasi"),
                         resi_per_day, ad_per_day, success, pct_cod,
                         eff_net, ongkir, cashback, p["mode"], p["daily_lag"])

    weekly = _resample(tl, "W-MON")
    monthly = _resample(tl, "MS")

    today = pd.Timestamp.today().normalize()
    week_end = today + pd.Timedelta(days=7)
    month_end = today + pd.Timedelta(days=30)
    mask_w = (tl["tanggal"] >= today) & (tl["tanggal"] < week_end)
    mask_m = (tl["tanggal"] >= today) & (tl["tanggal"] < month_end)
    cair_minggu = tl.loc[mask_w, "cod_cair"].sum() + tl.loc[mask_w, "transfer_in"].sum()
    cair_bulan = tl.loc[mask_m, "cod_cair"].sum() + tl.loc[mask_m, "transfer_in"].sum()
    modal_kerja = max(float(-tl["modal_kerja_kumulatif"].min()), 0.0)

    p["budget_harian"] = budget_harian_tot
    p["budget_iklan"] = budget_total
    summary = {
        "budget_iklan": budget_total, "budget_harian": budget_harian_tot,
        "n_lead": n_lead, "n_order": n_order, "n_resi": n_resi,
        "n_sukses": n_sukses, "n_gagal": n_gagal, "success_rate": success,
        "total_ongkir": total_ongkir, "total_cashback": total_cashback,
        "total_nilai_produk": total_nilai_produk, "total_cod_fee": total_cod_fee,
        "total_hpp": total_hpp, "total_margin_produk": total_margin_produk,
        "modal_hpp": total_modal_hpp, "total_net": total_net,
        "nilai_cod": nilai_cod, "nilai_transfer": nilai_transfer,
        "net_cod": sukses_cod * eff_net, "net_transfer": sukses_transfer * eff_net,
        "pct_cod": pct_cod, "pct_transfer": 1 - pct_cod,
        "avg_net_per_resi": eff_net, "avg_durasi": baseline.get("avg_durasi"),
        "cair_minggu_ini": cair_minggu, "cair_bulan_ini": cair_bulan,
        "outstanding_peak": float(tl["cod_outstanding"].max()),
        "outstanding_akhir": float(tl["cod_outstanding"].iloc[-1]),
        "net_cashflow_total": float(tl["net_cashflow"].sum()),
        "modal_kerja": modal_kerja,
        "modal_total": modal_kerja + total_modal_hpp,
        "horizon_days": horizon, "params": p,
    }
    funnel = {"Lead": n_lead, "Order": n_order, "Resi": n_resi,
              "Paket Sampai": n_sukses, "Dana Cair (net)": total_net}
    return {"summary": summary, "timeline": tl, "weekly": weekly,
            "monthly": monthly, "funnel": funnel, "per_product": pdf}
