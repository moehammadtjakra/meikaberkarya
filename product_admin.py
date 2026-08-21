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


def global_closing_rate(oo_df: pd.DataFrame | None) -> float | None:
    """Closing rate GLOBAL dari OrderOnline = (paid & status completed/processing) ÷ total leads."""
    if oo_df is None or len(oo_df) == 0:
        return None
    d = oo_df.copy()
    d.columns = [str(c).strip() for c in d.columns]
    if "payment_status" not in d.columns or "status" not in d.columns:
        return None
    paid = d["payment_status"].astype(str).str.lower().eq("paid")
    stat = d["status"].astype(str).str.lower().isin(["completed", "processing"])
    n = len(d)
    return float((paid & stat).sum() / n) if n else None


def _closing_per_sku(oo_df, ref_df, order_df):
    """Closing rate (%) per SKU dari OrderOnline. Acuan SKU (tanpa variation):
      1) order_id → Import-Order.SKU (resolusi final sistem admin, paling reliable), lalu
      2) fallback product_code → SKU dari RefProduk HANYA untuk product_code yang unik.
    Product_code ganda (>1 SKU di RefProduk) tidak dipetakan lewat fallback — rapikan
    product_code agar unik di RefProduk untuk closing rate yang akurat."""
    if oo_df is None or len(oo_df) == 0:
        return None
    oo = oo_df.copy()
    oo.columns = [str(c).strip() for c in oo.columns]
    if "product_code" not in oo.columns:
        return None
    oo["_oid"] = oo.get("order_id", pd.Series("", index=oo.index)).astype(str).str.strip()
    oo["_pc"] = oo["product_code"].astype(str).str.strip()

    # (1) order_id → SKU dari Import-Order
    oid2sku = {}
    if order_df is not None and len(order_df):
        io = order_df.copy(); io.columns = [str(c).strip() for c in io.columns]
        if {"order_id", "SKU"}.issubset(io.columns):
            io["_oid"] = io["order_id"].astype(str).str.strip()
            io["_sku"] = io["SKU"].astype(str).str.strip()
            io = io[io["_sku"].ne("") & io["_sku"].str.lower().ne("nan")]
            oid2sku = io.groupby("_oid")["_sku"].first().to_dict()

    # (2) fallback product_code → SKU (unik saja) dari RefProduk
    pc2sku = {}
    if ref_df is not None and len(ref_df):
        rf = ref_df.copy(); rf.columns = [str(c).strip() for c in rf.columns]
        if {"product_code", "SKU"}.issubset(rf.columns):
            rf["_pc"] = rf["product_code"].astype(str).str.strip()
            rf["_sku"] = rf["SKU"].astype(str).str.strip()
            uni = rf.groupby("_pc")["_sku"].nunique()
            pc2sku = {pc: rf.loc[rf["_pc"] == pc, "_sku"].iloc[0] for pc in uni[uni == 1].index}

    oo["_sku"] = oo["_oid"].map(oid2sku)
    oo["_sku"] = oo["_sku"].fillna(oo["_pc"].map(pc2sku))

    paid = oo.get("payment_status", pd.Series("", index=oo.index)).astype(str).str.lower().eq("paid")
    stat = oo.get("status", pd.Series("", index=oo.index)).astype(str).str.lower().isin(
        ["completed", "processing"])
    oo["_clo"] = (paid & stat).astype(int)
    gg = (oo.dropna(subset=["_sku"]).groupby("_sku")
            .agg(leads=("_sku", "size"), clo=("_clo", "sum")).reset_index())
    _den = gg["leads"].replace(0, np.nan)
    gg["closing_rate"] = (gg["clo"] / _den * 100).round(1)
    return gg.rename(columns={"_sku": "SKU"})[["SKU", "closing_rate"]]


def build_catalog(order_df: pd.DataFrame | None,
                  stock_df: pd.DataFrame | None,
                  all_resi: pd.DataFrame | None = None,
                  oo_df: pd.DataFrame | None = None,
                  ref_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Katalog per SKU dari order (nilai jual & HPP riil) + stok gudang + retur + closing.
    Retur via join order↔all_resi (No. Waybill); closing via OrderOnline↔RefProduk (product_code)."""
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
                  pcs_order=("Pcs", "mean") if "Pcs" in o.columns else ("SKU", "size"),
                  pcs_total=("Pcs", "sum") if "Pcs" in o.columns else ("SKU", "size"))
             .reset_index())
    if "Pcs" not in o.columns:
        agg["pcs_order"] = 1.0
        agg["pcs_total"] = agg["n_orders"]
    agg["pcs_order"] = agg["pcs_order"].round().clip(lower=1).astype(int)
    agg["pcs_total"] = _num(agg["pcs_total"]).fillna(0).round().astype(int)

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
    try:
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
            _den = _num(gg["sampai"] + gg["retur"]).replace(0, np.nan)
            gg["retur_pct"] = _num(gg["retur"]) / _den * 100
            agg = agg.drop(columns=["retur_pct"]).merge(
                gg[["SKU", "retur_pct"]], on="SKU", how="left")
    except Exception:
        agg["retur_pct"] = np.nan
    agg["retur_pct"] = _num(agg["retur_pct"]).round(1)

    # --- Closing rate per SKU dari OrderOnline ---
    agg["closing_rate"] = np.nan
    try:
        _clo = _closing_per_sku(oo_df, ref_df, order_df)
        if _clo is not None and len(_clo):
            agg = agg.drop(columns=["closing_rate"]).merge(_clo, on="SKU", how="left")
    except Exception:
        agg["closing_rate"] = np.nan
    agg["closing_rate"] = _num(agg.get("closing_rate")).round(1)
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
        # margin kotor produk (sebelum iklan) — dipakai internal utk set CPL & budget
        cm_gross = jual - hpp - fee * (jual + ongkir) + cb_pct * ongkir - ovar
        be_cpl = closing * success_p * cm_gross               # breakeven CPL
        cpl = int(min(cmax, max(cmin, round(be_cpl * frac / 100.0) * 100)))
        profitable = be_cpl > cmin and cm_gross > 0
        score = cm_gross * success_p                          # bobot alokasi budget
        stock_orders = (stok // pcs) if pcs > 0 else 0
        # CM yang DITAMPILKAN = margin per order setelah biaya akuisisi iklan (CPL ÷ closing)
        cac = (cpl / closing) if closing else 0.0
        cm = cm_gross - cac
        cm_pct = (cm / jual * 100) if jual else 0.0
        rows.append({
            "Produk": str(r["nama"]), "CPL": cpl,
            "Nilai Produk": int(jual), "HPP": int(hpp),
            "Stok (pcs)": stok, "Pcs/Order": pcs,
            "Total Resi": int(r.get("n_orders", 0)),
            "Closing Rate": (round(float(r.get("closing_rate")), 1)
                             if pd.notna(r.get("closing_rate")) else np.nan),
            "Pcs Terjual": int(r.get("pcs_total", 0) or 0),
            "AoV": int(jual), "CM": int(round(cm)), "CM%": round(cm_pct, 1),
            "Retur %": (round(retur_pct, 1) if pd.notna(retur_pct) else np.nan),
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
            "Stok (pcs)", "Pcs/Order", "Total Resi", "Closing Rate", "Pcs Terjual",
            "AoV", "CM", "CM%", "Retur %"]
    extra = ["_score", "_be_cpl", "_profitable", "_stock_orders", "_n"]
    df = df[cols + extra].sort_values(["_score", "Budget/Hari"], ascending=False).reset_index(drop=True)
    return df
