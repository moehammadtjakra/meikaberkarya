# -*- coding: utf-8 -*-
"""
daily_engine.py
===============
Simulasi cashflow harian dengan parameter yang BISA DIUBAH PER HARI
(budget iklan, CPL, biaya operasional). Perubahan di satu hari otomatis
menggeser hasil hari-hari berikutnya — baik pengeluaran maupun potensi kas
masuk dari pencairan COD order-order sebelumnya.

Model ekonomi memakai rata-rata tertimbang (blended) dari produk terpilih,
konsisten dengan cashflow_engine:
  cod_disb = Harga + Cashback − FeeCOD×(Harga+Ongkir)   (kas COD bersih)
  tr_in    = Harga + Ongkir penuh                        (kas transfer, hari kirim)
  return_per = max(retur% − 20%, 0) × Ongkir             (per paket gagal)
COD dari hari-d dikirim → diterima (d + durasi) → cair mengikuti jadwal J&T.
Bila pencairan jatuh di luar range, masuk OUTSTANDING (tetap akan cair nanti).
"""

from __future__ import annotations
from collections import defaultdict
import pandas as pd

import settlement_engine as se
import config


def _lag_dist(recv_dist, durasi):
    """Distribusi lama-kirim (historis) digeser agar rata-ratanya = durasi."""
    if recv_dist is None or len(recv_dist) == 0:
        return {max(int(round(durasi or 1)), 1): 1.0}
    items = [(int(k), float(v)) for k, v in recv_dist.items()]
    tot = sum(v for _, v in items) or 1.0
    cur = sum(k * v for k, v in items) / tot
    shift = int(round(durasi - cur)) if durasi and durasi > 0 else 0
    out = defaultdict(float)
    for k, v in items:
        out[max(k + shift, 1)] += v
    return dict(out)


def _f(x):
    try:
        v = float(x)
        return v if v == v else 0.0
    except (TypeError, ValueError):
        return 0.0


def simulate_editable(day_rows, g: dict, recv_dist) -> dict:
    """
    day_rows : list of dict / iterable baris harian, tiap baris punya
               'budget', 'cpl', 'opex'.
    g        : parameter global (closing, success, pct_cod, ongkir, cashback,
               cod_fee_rate, hpp, nilai_produk, mode, daily_lag, durasi_override,
               start_date).
    """
    rows = list(day_rows)
    H = len(rows)
    start = pd.Timestamp(g["start_date"]).normalize()
    opex_var_resi = float(g.get("opex_var_resi", 0) or 0)          # per resi (otomatis)
    stock_free = float(g.get("stock_orders_free", 0) or 0)         # order tercukupi stok
    cum_resi = 0.0                                                  # kumulatif order (stok)
    ongkir = g["ongkir"]; cb = g["cashback"]; cfr = g["cod_fee_rate"]
    closing = g["closing"]; success = g["success"]; pcod = g["pct_cod"]
    hpp = g["hpp"]; nilai = g["nilai_produk"]
    cod_disb = nilai + cb - cfr * (nilai + ongkir)
    tr_in = nilai + ongkir
    excess = max((1 - success) - config.RETUR_FREE_THRESHOLD, 0.0)
    return_per = excess * ongkir
    lagd = _lag_dist(recv_dist, g.get("durasi_override"))
    mode = g.get("mode", "mode2"); dlag = g.get("daily_lag", 1)

    cod_cair = defaultdict(float)   # index hari -> kas COD cair
    ret_out = defaultdict(float)    # index hari -> biaya ongkir retur
    daycol = []
    cod_ship_total = 0.0
    cod_cair_inrange = 0.0
    ret_total = 0.0

    for i, row in enumerate(rows):
        budget = _f(row.get("budget")); cpl = _f(row.get("cpl"))
        opex_manual = _f(row.get("opex"))               # petty cash kondisional (input)
        gaji = _f(row.get("gaji"))                       # gaji lump (kolom editable)
        leads = budget / cpl if cpl > 0 else 0.0
        orders = leads * closing
        resi = orders
        sukses = resi * success
        gagal = resi - sukses
        transfer = sukses * (1 - pcod) * tr_in
        # HPP cash STOK-AWARE: order awal dipenuhi stok, beli hanya yang melebihi stok
        _over_after = max(cum_resi + resi - stock_free, 0.0)
        _over_before = max(cum_resi - stock_free, 0.0)
        hpp_out = (_over_after - _over_before) * hpp
        cum_resi += resi
        d = start + pd.Timedelta(days=i)
        # opex total = petty cash (input) + variabel/resi (otomatis) + gaji (kolom editable)
        opex = opex_manual + resi * opex_var_resi + gaji
        for lag, prob in lagd.items():
            recv = d + pd.Timedelta(days=int(lag))
            chunk = sukses * pcod * cod_disb * prob
            cod_ship_total += chunk
            ret_total += gagal * return_per * prob
            payout = (se.payout_date_mode1(recv, dlag) if mode == "mode1"
                      else se.payout_date_mode2(recv))
            if pd.notna(payout):
                pidx = (payout - start).days
                if 0 <= pidx < H:
                    cod_cair[pidx] += chunk
                    cod_cair_inrange += chunk
            ridx = (recv - start).days
            if 0 <= ridx < H:
                ret_out[ridx] += gagal * return_per * prob
        daycol.append(dict(i=i, tanggal=d, budget=budget, cpl=cpl, opex=opex,
                           leads=leads, resi=resi, sukses=sukses,
                           transfer=transfer, hpp_out=hpp_out))

    out_rows = []
    modal_awal = float(g.get("modal_awal", 0) or 0)
    saldo = modal_awal                 # saldo kas dimulai dari modal awal
    for dc in daycol:
        i = dc["i"]
        cin = dc["transfer"] + cod_cair.get(i, 0.0)
        cout = dc["budget"] + dc["hpp_out"] + dc["opex"] + ret_out.get(i, 0.0)
        net = cin - cout
        sawal = saldo
        saldo += net
        out_rows.append({
            "tanggal": dc["tanggal"], "budget": dc["budget"], "cpl": dc["cpl"],
            "opex": dc["opex"], "leads": dc["leads"], "resi": dc["resi"],
            "sukses": dc["sukses"], "hpp": dc["hpp_out"],
            "transfer_in": dc["transfer"], "cod_cair": cod_cair.get(i, 0.0),
            "cash_in": cin, "cash_out": cout, "net": net,
            "saldo_awal": sawal, "saldo_akhir": saldo,
        })
    df = pd.DataFrame(out_rows)
    outstanding = cod_ship_total - cod_cair_inrange
    kas_terendah = float(df["saldo_akhir"].min()) if not df.empty else modal_awal
    return {
        "table": df,
        "outstanding": outstanding,
        "cod_ship_total": cod_ship_total,
        "cair_inrange": cod_cair_inrange,
        "modal_awal": modal_awal,
        "kas_terendah": kas_terendah,                 # posisi kas paling rendah
        "kas_habis": bool(kas_terendah < -1e-6),      # True = modal tak cukup
        "saldo_akhir": float(df["saldo_akhir"].iloc[-1]) if not df.empty else modal_awal,
    }
