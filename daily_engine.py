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
        budget = _f(row.get("budget")); cpl = _f(row.get("cpl")); opex = _f(row.get("opex"))
        leads = budget / cpl if cpl > 0 else 0.0
        orders = leads * closing
        resi = orders
        sukses = resi * success
        gagal = resi - sukses
        transfer = sukses * (1 - pcod) * tr_in
        hpp_out = resi * hpp
        d = start + pd.Timedelta(days=i)
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
    saldo = 0.0
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
    return {
        "table": df,
        "outstanding": outstanding,
        "cod_ship_total": cod_ship_total,
        "cair_inrange": cod_cair_inrange,
        "modal_awal": float(-df["saldo_akhir"].min()) if not df.empty else 0.0,
        "saldo_akhir": float(df["saldo_akhir"].iloc[-1]) if not df.empty else 0.0,
    }
