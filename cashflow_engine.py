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
                    ad_per_day, success_rate, pct_cod, cod_disb, tr_in,
                    hpp_per_resi, return_ongkir, opex_per_day,
                    mode, daily_lag) -> pd.DataFrame:
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
        hpp_spend = (resi_per_day * hpp_per_resi) if in_ship else 0.0
        opex = opex_per_day if in_ship else 0.0
        ti = transfer_in.get(d, 0.0)
        cc = cod_cair.get(d, 0.0)
        cs = cod_shipped.get(d, 0.0)
        ro = return_out.get(d, 0.0)
        laba = rev_accr.get(d, 0.0) - cogs_accr.get(d, 0.0) - ad - opex - ro
        rows.append({
            "tanggal": d, "ad_spend": ad, "hpp_spend": hpp_spend, "opex": opex,
            "return_ongkir": ro,
            "transfer_in": ti, "cod_cair": cc, "cod_shipped": cs,
            "cash_in": ti + cc, "cash_out": ad + hpp_spend + opex + ro,
            "omzet_realized": ti + cc, "omzet_earned": ti + cs,
            "net_cashflow": ti + cc - ad - hpp_spend - opex - ro,
            "laba_harian": laba,
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
        cod_disb, tr_in, p["hpp"], return_ongkir, 0.0,
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
        nama = str(r.get("Produk", "-"))
        if not nama or nama in ("-", "nan", "None"):
            continue  # lewati baris kosong
        budget_total = bh * horizon
        lead = budget_total / cpl if cpl > 0 else 0
        order = lead * closing
        resi = order
        sukses = resi * success
        gagal = resi - sukses
        # kas masuk per resi sukses, dibedakan metode bayar
        cod_disb = nilai_produk + cashback - cod_fee_rate * (nilai_produk + ongkir)
        tr_in = nilai_produk + ongkir                # transfer: produk + ongkir penuh
        sukses_cod = sukses * pct_cod
        sukses_tr = sukses * (1 - pct_cod)
        revenue = sukses_cod * cod_disb + sukses_tr * tr_in   # total kas masuk kotor
        cogs = hpp * sukses                          # HPP hanya barang terjual (retur balik)
        return_cost = return_ongkir * gagal          # ongkir retur paket gagal
        modal_hpp = hpp * resi                        # kas beli stok semua paket dikirim
        net_total = revenue - cogs - return_cost - budget_total   # laba produk (sblm opex)
        margin_jual = nilai_produk - hpp
        roi = (net_total / budget_total) if budget_total > 0 else 0
        rows.append({
            "Produk": nama, "budget_harian": bh, "budget_total": budget_total,
            "cpl": cpl, "nilai_produk": nilai_produk, "hpp": hpp,
            "lead": lead, "order": order, "resi": resi, "sukses": sukses, "gagal": gagal,
            "cod_disb": cod_disb, "tr_in": tr_in,
            "margin_jual_per_resi": margin_jual,
            "net_per_resi": (net_total / resi) if resi else 0,
            "modal_hpp": modal_hpp, "revenue": revenue, "cogs": cogs,
            "return_cost": return_cost, "net_total": net_total, "roi": roi,
        })
    cols = ["Produk", "budget_harian", "budget_total", "cpl", "nilai_produk", "hpp",
            "lead", "order", "resi", "sukses", "gagal", "cod_disb", "tr_in",
            "margin_jual_per_resi", "net_per_resi", "modal_hpp", "revenue", "cogs",
            "return_cost", "net_total", "roi"]
    pdf = pd.DataFrame(rows, columns=cols)

    # ---- agregasi ----
    n_lead = pdf["lead"].sum(); n_order = pdf["order"].sum()
    n_resi = pdf["resi"].sum(); n_sukses = pdf["sukses"].sum(); n_gagal = pdf["gagal"].sum()
    budget_harian_tot = pdf["budget_harian"].sum()
    budget_total = pdf["budget_total"].sum()
    total_modal_hpp = pdf["modal_hpp"].sum()
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

    # opex teknis (packing, gaji, petty cash) — 1 input per 30 hari
    opex_30 = float(p.get("opex_30", 0) or 0)
    opex_per_day = opex_30 / 30.0
    total_opex = opex_per_day * horizon

    resi_per_day = n_resi / horizon if horizon else 0
    ad_per_day = budget_harian_tot
    tl = _build_timeline(start, horizon, recv_dist, baseline.get("avg_durasi"),
                         resi_per_day, ad_per_day, success, pct_cod,
                         eff_cod_disb, eff_tr_in, eff_hpp_resi, return_ongkir,
                         opex_per_day, p["mode"], p["daily_lag"])

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

    # BEP kas (balik modal): saldo kas kembali >= 0 setelah melewati titik terdalam
    trough_idx = int(tl["saldo_kas"].idxmin())
    after = tl.iloc[trough_idx:]
    bk = after.loc[after["saldo_kas"] >= 0, "tanggal"]
    hari_balik_modal = (int((bk.iloc[0] - start).days)
                        if not bk.empty and net_profit > 0 else None)
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
        "total_beli_produk": total_modal_hpp,
        "total_opex": total_opex, "opex_30": opex_30,
        "modal_awal": modal_awal, "saldo_kas_min": saldo_min,
        "saldo_kas_akhir": float(tl["saldo_kas"].iloc[-1]),
        "modal_kerja": modal_awal, "modal_total": modal_awal,
        "net_profit": net_profit, "roi_modal": roi_modal, "roi_iklan": roi_iklan,
        "laba_likuid": laba_likuid, "cash_in_likuid": cash_in_likuid,
        "cash_out_horizon": cash_out_horizon, "outstanding_dana": outstanding_dana,
        "lam_cod": lam_cod, "lam_ret": lam_ret,
        "return_rate": return_rate, "retur_excess": retur_excess,
        "hari_balik_modal": hari_balik_modal,
        "hari_laba_positif": hari_laba_positif,
        "hari_cashflow_positif": hari_cashflow_positif,
        "hari_self_sustaining": hari_self_sustaining,
        "laba_akhir_positif": laba_akhir_positif,
        "horizon_days": horizon, "params": p,
    }
    funnel = {"Lead": n_lead, "Order": n_order, "Resi": n_resi,
              "Paket Sampai": n_sukses}
    return {"summary": summary, "timeline": tl, "weekly": weekly,
            "monthly": monthly, "funnel": funnel, "per_product": pdf}
