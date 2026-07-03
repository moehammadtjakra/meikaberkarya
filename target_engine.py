# -*- coding: utf-8 -*-
"""
target_engine.py
================
Target Profit Simulator — perhitungan MUNDUR (reverse), berbasis LIKUIDITAS.

Target laba = LABA BERSIH LIKUID dalam horizon = kas yang benar-benar sudah CAIR
masuk rekening dalam T hari, dikurangi seluruh kas keluar dalam periode tsb.
Bukan sekadar omzet/order.

Kunci: sebagian pencairan COD JATUH DI LUAR horizon (delay terima + settlement),
sehingga hanya fraksi λ_cod dari disbursement COD yang cair ≤ T. Transfer cair 100%
(prabayar). λ_cod & λ_ret dihitung sekali dari mesin cashflow (tergantung horizon,
skema pencairan, & distribusi lama kirim), lalu dipakai closed-form di sini.

Model:
  disb_cod   = Harga + Cashback − FeeCOD×(Harga+Ongkir)      (kas COD bersih)
  disb_tr    = Harga + Ongkir penuh                          (kas transfer)
  return_per = max(retur% − 20%, 0) × Ongkir                 (per paket gagal)
  m_liq (kontribusi likuid per order) =
        success×(1−%COD)×disb_tr                 (transfer, cair penuh)
      + λ_cod×success×%COD×disb_cod              (COD, hanya yang cair ≤ T)
      − HPP                                       (beli stok tiap order)
      − λ_ret×(1−success)×return_per              (ongkir retur ≤ T)
  Laba likuid = Budget×(K_liq − 1) − Opex,   K_liq = Closing×m_liq / CPL
"""

from __future__ import annotations
import config


def _rp(v):
    try:
        return f"Rp{float(v):,.0f}".replace(",", ".")
    except Exception:
        return "-"


def unit_economics(b: dict, lam_cod: float = 1.0, lam_ret: float = 1.0) -> dict:
    """Besaran per-order berbasis kas LIKUID (memakai faktor likuiditas λ)."""
    price, ongkir, hpp = b["nilai_produk"], b["ongkir"], b["hpp"]
    cashback = b["cashback_pct"] * ongkir
    fee = b["cod_fee_rate"]
    pcod, success = b["pct_cod"], b["success"]

    disb_cod = price + cashback - fee * (price + ongkir)
    disb_tr = price + ongkir
    excess = max((1 - success) - config.RETUR_FREE_THRESHOLD, 0.0)
    return_per = excess * ongkir

    v_tr = success * (1 - pcod) * disb_tr                 # transfer cair penuh
    v_cod = lam_cod * success * pcod * disb_cod           # COD yang cair ≤ T
    v_ret = lam_ret * (1 - success) * return_per          # ongkir retur ≤ T
    m_liq = v_tr + v_cod - hpp - v_ret
    K = (b["closing"] * m_liq / b["cpl"]) if b["cpl"] else 0
    return {"disb_cod": disb_cod, "disb_tr": disb_tr, "cashback": cashback,
            "return_per": return_per, "return_rate": 1 - success,
            "v_tr": v_tr, "v_cod": v_cod, "v_ret": v_ret,
            "m_liq": m_liq, "K": K}


def laba_likuid(budget_total, cpl, closing, m_liq, opex_total):
    if cpl <= 0:
        return -opex_total
    return (budget_total / cpl) * closing * m_liq - budget_total - opex_total


def _funnel(budget_total, cpl, closing, b):
    leads = budget_total / cpl if cpl else 0
    orders = leads * closing
    resi = orders
    sukses = resi * b["success"]
    ue = unit_economics({**b, "closing": closing, "cpl": cpl})
    omzet = sukses * (b["pct_cod"] * ue["disb_cod"] + (1 - b["pct_cod"]) * ue["disb_tr"])
    return {"leads": leads, "orders": orders, "resi": resi, "sukses": sukses,
            "omzet": omzet, "budget_total": budget_total, "cpl": cpl, "closing": closing}


def solve(target_profit: float, days: int, b: dict,
          lam_cod: float = 1.0, lam_ret: float = 1.0) -> dict:
    T = max(int(days), 1)
    opex_total = b["opex_30"] * T / 30.0
    budget0 = b["budget_harian"] * T
    P = target_profit

    ue = unit_economics(b, lam_cod, lam_ret)
    m_liq = ue["m_liq"]
    K0 = ue["K"]
    laba_now = laba_likuid(budget0, b["cpl"], b["closing"], m_liq, opex_total)
    K_req = ((P + opex_total) / budget0 + 1) if budget0 > 0 else None

    options = []

    # Opsi 1 — naikkan Closing
    if m_liq > 0 and budget0 > 0:
        closing_req = K_req * b["cpl"] / m_liq
        feasible = closing_req <= 1.0
        options.append({
            "nama": "Opsi 1 — Fokus Naikkan Closing Rate",
            "ubah": f"Closing {b['closing']*100:.0f}% → {min(closing_req,1)*100:.1f}%",
            "feasible": feasible,
            "catatan": ("Cukup naikkan closing rate (kualitas follow-up CS)."
                        if feasible else
                        f"Butuh closing {closing_req*100:.0f}% (>100%) — tak realistis "
                        "hanya dari closing."),
            "scenario": {**b, "closing": min(closing_req, 1.0)},
            "funnel": _funnel(budget0, b["cpl"], min(closing_req, 1.0), b),
        })

    # Opsi 2 — turunkan CPL
    if m_liq > 0 and budget0 > 0 and K_req and K_req > 0:
        cpl_req = b["closing"] * m_liq / K_req
        feasible = 0 < cpl_req <= b["cpl"]
        options.append({
            "nama": "Opsi 2 — Fokus Turunkan CPL",
            "ubah": f"CPL {_rp(b['cpl'])} → {_rp(cpl_req)}",
            "feasible": feasible,
            "catatan": ("Turunkan biaya per lead (kreatif & targeting iklan lebih efisien)."
                        if feasible else
                        f"Butuh CPL {_rp(cpl_req)} — {'lebih tinggi dari sekarang' if cpl_req>b['cpl'] else 'sangat agresif'}."),
            "scenario": {**b, "cpl": max(cpl_req, 1)},
            "funnel": _funnel(budget0, max(cpl_req, 1), b["closing"], b),
        })

    # Opsi 3 — kombinasi (faktor f: closing↑, CPL↓)
    def _net_f(f):
        cl = min(b["closing"] * (1 + f), 1.0)
        cp = b["cpl"] * (1 - f)
        ue2 = unit_economics({**b, "closing": cl, "cpl": cp}, lam_cod, lam_ret)
        return laba_likuid(budget0, cp, cl, ue2["m_liq"], opex_total)
    f_sol, feas3 = None, False
    if _net_f(0) >= P:
        f_sol, feas3 = 0.0, True
    elif _net_f(0.9) >= P:
        lo, hi = 0.0, 0.9
        for _ in range(40):
            mid = (lo + hi) / 2
            (lo, hi) = (mid, hi) if _net_f(mid) < P else (lo, mid)
        f_sol, feas3 = hi, True
    if f_sol is not None:
        cl = min(b["closing"] * (1 + f_sol), 1.0)
        cp = b["cpl"] * (1 - f_sol)
        options.append({
            "nama": "Opsi 3 — Kombinasi Closing↑ & CPL↓",
            "ubah": f"Closing → {cl*100:.1f}%, CPL → {_rp(cp)}",
            "feasible": feas3, "catatan": f"Perbaikan seimbang ±{f_sol*100:.0f}%.",
            "scenario": {**b, "closing": cl, "cpl": cp},
            "funnel": _funnel(budget0, cp, cl, b)})
    else:
        options.append({"nama": "Opsi 3 — Kombinasi Closing↑ & CPL↓", "feasible": False,
                        "ubah": "-", "catatan": "Target tak tercapai walau closing & CPL diperbaiki agresif.",
                        "scenario": b, "funnel": _funnel(budget0, b["cpl"], b["closing"], b)})

    # Opsi 4 — tambah budget
    if K0 > 1:
        budget_req = (P + opex_total) / (K0 - 1)
        options.append({
            "nama": "Opsi 4 — Tambah Budget Iklan",
            "ubah": f"Budget → {_rp(budget_req)} ({_rp(budget_req/T)}/hari)",
            "feasible": True, "catatan": "Metrik tetap, skalakan belanja iklan.",
            "scenario": {**b, "budget_harian": budget_req / T},
            "funnel": _funnel(budget_req, b["cpl"], b["closing"], b)})
    else:
        options.append({"nama": "Opsi 4 — Tambah Budget Iklan", "feasible": False, "ubah": "-",
                        "catatan": "Per rupiah iklan belum untung (K≤1) — perbaiki unit-ekonomi dulu.",
                        "scenario": b, "funnel": _funnel(budget0, b["cpl"], b["closing"], b)})

    # ---- BATAS AMAN (guardrail sebelum RUGI) pada rencana yang mencapai target ----
    B = (P + opex_total) / (K0 - 1) if K0 > 1 else budget0
    orders_ref = (B / b["cpl"]) * b["closing"] if b["cpl"] else 0
    s = b["success"]
    limits = {"budget_ref": B, "orders_ref": orders_ref}
    if orders_ref > 0:
        m_be = (B + opex_total) / orders_ref            # kontribusi likuid minimal (net=0)
        # HPP maksimal
        limits["hpp_max"] = (ue["v_tr"] + ue["v_cod"] - ue["v_ret"]) - m_be
        # Harga jual minimal (linear thd harga)
        A = s * (1 - b["pct_cod"]) + lam_cod * s * b["pct_cod"] * (1 - b["cod_fee_rate"])
        Bc = (s * (1 - b["pct_cod"]) * b["ongkir"]
              + lam_cod * s * b["pct_cod"] * (ue["cashback"] - b["cod_fee_rate"] * b["ongkir"]))
        if A > 0:
            limits["price_min"] = (m_be + b["hpp"] + ue["v_ret"] - Bc) / A
        # Opex maksimal aman /30 hari
        limits["opex_30_max"] = max(orders_ref * m_liq - B, 0) * 30 / T
        # Retur maksimal (min success) sebelum rugi — numerik
        def _net_succ(su):
            ue2 = unit_economics({**b, "success": su}, lam_cod, lam_ret)
            return laba_likuid(B, b["cpl"], b["closing"], ue2["m_liq"], opex_total)
        succ_min = None
        lo, hi = 0.05, 0.999
        if _net_succ(lo) >= 0:
            succ_min = lo
        elif _net_succ(hi) >= 0:
            for _ in range(40):
                mid = (lo + hi) / 2
                (lo, hi) = (mid, hi) if _net_succ(mid) < 0 else (lo, mid)
            succ_min = hi
        if succ_min is not None:
            limits["return_max"] = 1 - succ_min

    return {"target": P, "days": T, "opex_total": opex_total, "budget0": budget0,
            "laba_now": laba_now, "m_liq": m_liq, "K": K0, "K_req": K_req,
            "lam_cod": lam_cod, "lam_ret": lam_ret,
            "options": options, "limits": limits, "profitable_per_lead": K0 > 1}
