# -*- coding: utf-8 -*-
"""
product_admin.py
================
Membangun KATALOG PRODUK dari sheet admin (Import-Order + Import-Stock) dan
melakukan AUTO-PLOTTING budget iklan & CPL optimal per produk.

Sumber:
  - Import-Order : tiap baris = 1 order. Kolom kunci: SKU, Pcs (pcs produk utama),
                   gross_revenue (nilai jual riil), HPP (COGS per order), Status Order.
  - Import-Stock : SKU, Nama Produk (unik & bersih), Stok (sisa pcs), HPP per Pcs.

Output katalog (per SKU): nama, nilai_jual, hpp_order, pcs_order, stok_pcs,
hpp_pcs, n_orders. optimize_table() menambah CPL & Budget/Hari optimal +
kolom siap dipakai tabel produk dashboard.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

import config


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def build_catalog(order_df: pd.DataFrame | None,
                  stock_df: pd.DataFrame | None,
                  all_resi: pd.DataFrame | None = None) -> pd.DataFrame:
    """Katalog per SKU dari order (nilai jual & HPP riil) + stok gudang + retur.
    Retur per produk dihitung dgn join order↔all_resi lewat No. Waybill."""
    if order_df is None or len(order_df) == 0:
        return pd.DataFrame()

    o = order_df.copy()
    o.columns = [str(c).strip() for c in o.columns]
    if "SKU" not in o.columns:
        return pd.DataFrame()

    # hanya order yang benar-benar terkirim (bila kolom status ada)
    if "Status Order" in o.columns:
        mask = o["Status Order"].astype(str).str.contains("Terkirim", case=False, na=False)
        if mask.any():
            o = o[mask]

    o["SKU"] = o["SKU"].astype(str).str.strip()
    o = o[o["SKU"].ne("") & o["SKU"].str.lower().ne("nan")]
    for c in ["Pcs", "gross_revenue", "product_price", "HPP", "cogs"]:
        if c in o.columns:
            o[c] = _num(o[c])

    # Nilai jual = product_price (TOTAL nilai produk dalam 1 resi, sudah termasuk
    # jumlah pcs). Fallback gross_revenue bila product_price tak ada.
    sell_col = "product_price" if "product_price" in o.columns else "gross_revenue"
    hpp_col = "HPP" if "HPP" in o.columns else "cogs"
    agg = (o.groupby("SKU")
             .agg(n_orders=("SKU", "size"),
                  nilai_jual=(sell_col, "mean"),
                  hpp_order_ord=(hpp_col, "mean"),
                  pcs_order=("Pcs", "mean") if "Pcs" in o.columns else ("SKU", "size"))
             .reset_index())
    if "Pcs" not in o.columns:
        agg["pcs_order"] = 1.0
    agg["pcs_order"] = agg["pcs_order"].round().clip(lower=1).astype(int)

    # gabung stok
    if stock_df is not None and len(stock_df):
        s = stock_df.copy()
        s.columns = [str(c).strip() for c in s.columns]
        if "SKU" in s.columns:
            s["SKU"] = s["SKU"].astype(str).str.strip()
            nama_c = "Nama Produk" if "Nama Produk" in s.columns else None
            stok_c = "Stok" if "Stok" in s.columns else None
            hppp_c = "HPP per Pcs" if "HPP per Pcs" in s.columns else None
            keep = ["SKU"] + [c for c in [nama_c, stok_c, hppp_c] if c]
            s = s[keep].drop_duplicates("SKU")
            agg = agg.merge(s, on="SKU", how="left")
            agg = agg.rename(columns={nama_c: "nama", stok_c: "stok_pcs",
                                      hppp_c: "hpp_pcs"})
    for c, d in [("nama", None), ("stok_pcs", 0), ("hpp_pcs", np.nan)]:
        if c not in agg.columns:
            agg[c] = d
    # fallback nama dari kolom Produk order bila stok tak punya
    if agg["nama"].isna().any() and "Produk" in o.columns:
        nm = (o.groupby("SKU")["Produk"].first()
                .str.replace(r"[()]", "", regex=True).str.strip())
        agg["nama"] = agg["nama"].fillna(agg["SKU"].map(nm))
    agg["nama"] = agg["nama"].fillna(agg["SKU"])
    agg["stok_pcs"] = _num(agg["stok_pcs"]).fillna(0).clip(lower=0).astype(int)
    agg["hpp_pcs"] = _num(agg["hpp_pcs"])
    # HPP per order = Pcs/Order x HPP per Pcs (dari Import-Stock). Bila hpp_pcs kosong,
    # pakai rata-rata HPP dari sheet order sebagai cadangan.
    agg["hpp_order"] = (agg["pcs_order"] * agg["hpp_pcs"])
    agg["hpp_order"] = agg["hpp_order"].fillna(agg["hpp_order_ord"])
    agg["nilai_jual"] = _num(agg["nilai_jual"]).round()
    agg["hpp_order"] = _num(agg["hpp_order"]).round()
    agg["aov"] = agg["nilai_jual"]                         # Average Order Value

    # --- Retur per SKU: join order (No. Waybill) ↔ all_resi (waybill) ---
    agg["retur_pct"] = np.nan
    if (all_resi is not None and len(all_resi) and "No. Waybill" in o.columns
            and "waybill" in all_resi.columns):
        def _wb(s):
            return s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        wb = pd.DataFrame({"SKU": o["SKU"].values, "wb": _wb(o["No. Waybill"])})
        ar = pd.DataFrame({"wb": _wb(all_resi["waybill"])})
        ar["is_retur"] = (all_resi["is_retur"].values if "is_retur" in all_resi else False)
        ar["is_sampai"] = (all_resi["is_sampai"].values if "is_sampai" in all_resi else False)
        j = wb.merge(ar, on="wb", how="left")
        gg = (j.groupby("SKU")
                .agg(sampai=("is_sampai", "sum"), retur=("is_retur", "sum")).reset_index())
        gg["den"] = gg["sampai"] + gg["retur"]
        # bagi lewat denominator yang 0-nya diganti NaN → tak ada ZeroDivisionError
        _den = _num(gg["den"]).replace(0, np.nan)
        gg["retur_pct"] = _num(gg["retur"]) / _den * 100
        agg = agg.drop(columns=["retur_pct"]).merge(
            gg[["SKU", "retur_pct"]], on="SKU", how="left")
    agg["retur_pct"] = _num(agg["retur_pct"]).round(1)
    return agg.sort_values("n_orders", ascending=False).reset_index(drop=True)


def optimize_table(catalog: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Auto-plot CPL & Budget/Hari optimal per produk.
      CPL     = clamp(breakeven_CPL x CPL_TARGET_FRAC, CPL_MIN, CPL_MAX)
      Budget  = untuk menghabiskan stok gudang selama horizon (cash beli produk = 0);
                produk stok 0 / tak profitabel → budget 0.
    Mengembalikan DataFrame kolom tabel produk dashboard (+ Stok & Pcs/Order).
    """
    if catalog is None or catalog.empty:
        return pd.DataFrame(columns=["Produk", "Budget/Hari", "CPL", "Nilai Produk",
                                     "HPP", "Stok (pcs)", "Pcs/Order"])
    closing = float(params.get("closing", 0.3)) or 0.3
    success = float(params.get("success", 0.6)) or 0.6
    ongkir = float(params.get("ongkir", 0) or 0)
    cb_pct = float(params.get("cashback_pct", 0) or 0)
    fee = float(params.get("cod_fee_rate", 0.015) or 0)
    ovar = float(params.get("opex_var_resi", 0) or 0)
    horizon = max(int(params.get("horizon", 30) or 30), 1)
    cmin, cmax = config.CPL_MIN, config.CPL_MAX
    frac = config.CPL_TARGET_FRAC

    b_min = config.BUDGET_MIN_PRODUK
    b_max = config.BUDGET_MAX_PRODUK

    rows = []
    for _, r in catalog.iterrows():
        jual = float(r["nilai_jual"] or 0)
        hpp = float(r["hpp_order"] or 0)
        pcs = int(r["pcs_order"] or 1)
        stok = int(r["stok_pcs"] or 0)
        # Retur per produk (bila ada) → success efektif produk itu
        rp_ = r.get("retur_pct")
        retur_pct = float(rp_) if pd.notna(rp_) else np.nan
        success_p = (1 - retur_pct / 100) if pd.notna(retur_pct) else success
        success_p = min(max(success_p, 0.05), 1.0)
        # Contribution Margin per order sukses (setelah COD fee, +cashback, −opex var)
        cm = jual - hpp - fee * (jual + ongkir) + cb_pct * ongkir - ovar
        cm_pct = (cm / jual * 100) if jual else 0.0
        # nilai ekspektasi margin per LEAD (pakai success per-produk) → breakeven CPL
        be_cpl = closing * success_p * cm
        cpl = int(min(cmax, max(cmin, round(be_cpl * frac / 100.0) * 100)))
        profitable = be_cpl > cmin and cm > 0
        score = cm * success_p                              # bobot alokasi budget
        stock_orders = (stok // pcs) if pcs > 0 else 0
        # LABA/ORDER (stlh iklan): biaya iklan per order = CPL ÷ closing (leads utk 1 order);
        # laba/order dikirim = success×CM − biaya retur − biaya iklan/order.
        cac = (cpl / closing) if closing else 0.0
        ret_per = max((1 - success_p) - config.RETUR_FREE_THRESHOLD, 0.0) * ongkir
        net_order = success_p * cm - (1 - success_p) * ret_per - cac
        rows.append({
            "Produk": str(r["nama"]), "CPL": cpl,
            "Nilai Produk": int(jual), "HPP": int(hpp),
            "Stok (pcs)": stok, "Pcs/Order": pcs,
            "AoV": int(jual), "CM": int(round(cm)), "CM%": round(cm_pct, 1),
            "Retur %": (round(retur_pct, 1) if pd.notna(retur_pct) else np.nan),
            "Laba/Order": int(round(net_order)),
            "_score": score, "_be_cpl": be_cpl, "_profitable": profitable,
            "_stock_orders": stock_orders, "_n": int(r.get("n_orders", 0)),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # --- Budget di-scale berdasarkan skor (CM × success): skor tertinggi →
    #     BUDGET_MAX (3jt), profitabel terlemah → BUDGET_MIN; tak profitabel → 0.
    #     Produk retur tinggi otomatis dapat budget lebih kecil. ---
    prof = df["_profitable"] & (df["CM"] > 0)
    df["Budget/Hari"] = 0
    if prof.any():
        cmv = df.loc[prof, "_score"].astype(float)
        lo, hi = cmv.min(), cmv.max()
        if hi > lo:
            norm = (cmv - lo) / (hi - lo)
        else:
            norm = pd.Series(1.0, index=cmv.index)
        bud = b_min + norm * (b_max - b_min)
        df.loc[prof, "Budget/Hari"] = (bud / 10000).round() * 10000
    df["Budget/Hari"] = df["Budget/Hari"].astype(int)

    cols = ["Produk", "Budget/Hari", "CPL", "Nilai Produk", "HPP",
            "Stok (pcs)", "Pcs/Order", "AoV", "CM", "CM%", "Retur %", "Laba/Order"]
    extra = ["_score", "_be_cpl", "_profitable", "_stock_orders", "_n"]
    df = df[cols + extra].sort_values(["_score", "Budget/Hari"], ascending=False).reset_index(drop=True)
    return df
