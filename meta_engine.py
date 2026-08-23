# -*- coding: utf-8 -*-
"""
meta_engine.py
==============
Modul 5 — Analisis Iklan Meta.

Menggabungkan data iklan Meta (sheet `Meta-Ads`, per campaign per hari) dengan
KATALOG produk (product_admin.build_catalog) untuk menghasilkan keputusan
**scale / optimize / kill** per produk.

Dua lapis:
  - Lapis Meta (dari API): spend, purchases (pixel), CPM, CPC, add-to-cart, budget.
  - Lapis nyata (katalog per SKU): margin kotor/order, success (sampai%), retur%,
    AoV, closing — dipakai menghitung margin efektif per purchase, CM setelah iklan,
    ROAS, dan titik impas biaya per purchase.

Catatan model: Meta "purchase" = order ditempatkan di web. Sebagian retur/tidak
sampai, jadi margin efektif per purchase = margin_kotor_per_order × success_rate.
Verdict membandingkan cost/purchase aktual vs titik impas (= margin efektif itu).
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _margin_gross_per_order(cat: pd.DataFrame, p: dict) -> pd.Series:
    """Margin kotor per order (sebelum iklan), konsisten dgn product_engine."""
    ongkir = float(p.get("ongkir", 0) or 0)
    cb = float(p.get("cashback_pct", 0) or 0)       # fraksi
    fee = float(p.get("cod_fee_rate", 0) or 0)      # fraksi
    ovar = float(p.get("opex_var_resi", 0) or 0)
    nj = _num(cat.get("nilai_jual")).fillna(0)
    hp = _num(cat.get("hpp_order")).fillna(0)
    return (nj - hp - fee * (nj + ongkir) + cb * ongkir - ovar)


def _verdict(ratio, purchases, spend, has_margin):
    """ratio = cost_per_purchase / breakeven. -> (label, css)."""
    if not has_margin:
        return "⚪ Review", "muted"
    if spend > 0 and purchases <= 0:
        return "🔴 Kill", "red"
    if ratio is None or not np.isfinite(ratio):
        return "⚪ Review", "muted"
    if ratio <= 0.70:
        return "🟢 Scale", "green"
    if ratio <= 1.0:
        return "🟡 Optimize", "amber"
    return "🔴 Kill", "red"


def filter_period(meta: pd.DataFrame, since=None, until=None) -> pd.DataFrame:
    """Saring baris Meta-Ads berdasarkan rentang tanggal (inklusif)."""
    if meta is None or len(meta) == 0:
        return meta
    d = meta.copy()
    if "date" in d:
        dt = pd.to_datetime(d["date"], errors="coerce")
        if since is not None:
            d = d[dt >= pd.to_datetime(since)]
            dt = pd.to_datetime(d["date"], errors="coerce")
        if until is not None:
            d = d[dt <= pd.to_datetime(until)]
    return d


def product_ad_summary(meta: pd.DataFrame, catalog: pd.DataFrame,
                       params: dict | None = None,
                       since=None, until=None) -> dict:
    """
    Ringkas iklan per produk + verdict. Mengembalikan dict:
      { 'ada': bool, 'produk': DataFrame, 'total': dict, 'review': DataFrame,
        'unmatched_spend': float }
    """
    p = params or {}
    out = {"ada": False, "produk": pd.DataFrame(), "total": {},
           "review": pd.DataFrame(), "unmatched_spend": 0.0}
    if meta is None or len(meta) == 0:
        return out
    d = filter_period(meta, since, until)
    if d is None or len(d) == 0:
        return out
    out["ada"] = True

    d = d.copy()
    d["sku"] = d.get("sku", "").astype(str).str.strip()
    d["produk"] = d.get("produk", "").astype(str).str.strip()
    for c in ["spend", "purchases", "impressions", "clicks", "add_to_cart",
              "link_click", "cost_per_purchase", "daily_budget"]:
        if c in d:
            d[c] = _num(d[c]).fillna(0)

    # kunci agregasi: SKU bila ada, else nama produk (campaign belum terlabeli)
    d["_key"] = np.where(d["sku"].ne("") & d["sku"].str.lower().ne("nan"),
                         d["sku"], d["produk"])

    g = (d.groupby("_key")
           .agg(produk=("produk", "first"),
                sku=("sku", "first"),
                spend=("spend", "sum"),
                purchases=("purchases", "sum"),
                impressions=("impressions", "sum"),
                clicks=("clicks", "sum"),
                add_to_cart=("add_to_cart", "sum"),
                n_campaign=("campaign_id", "nunique") if "campaign_id" in d else ("produk", "size"),
                daily_budget=("daily_budget", "sum"))
           .reset_index(drop=True))

    # --- gabung katalog per SKU (margin, success, retur, AoV, closing) ---
    cat = catalog.copy() if catalog is not None and not catalog.empty else pd.DataFrame()
    if not cat.empty and "SKU" in cat.columns:
        cat["SKU"] = cat["SKU"].astype(str).str.strip()
        cat["_mg"] = _margin_gross_per_order(cat, p).round()
        keep = cat[["SKU", "_mg", "sampai_pct", "retur_pct", "closing_rate",
                    "aov", "nilai_jual", "n_orders"]].copy()
        g = g.merge(keep, left_on="sku", right_on="SKU", how="left")
    else:
        for c in ["_mg", "sampai_pct", "retur_pct", "closing_rate", "aov",
                  "nilai_jual", "n_orders"]:
            g[c] = np.nan

    succ_def = float(p.get("success_default", 0.6) or 0.6)
    g["success"] = (_num(g["sampai_pct"]) / 100).fillna(succ_def).clip(0, 1)
    g["aov"] = _num(g["aov"]).fillna(_num(g["nilai_jual"]))
    g["margin_order"] = _num(g["_mg"])            # margin kotor/order (bisa NaN bila tak match)

    # --- metrik keputusan ---
    pur = g["purchases"].replace(0, np.nan)
    g["cost_per_purchase"] = (g["spend"] / pur).round()            # per order web
    g["cost_per_sampai"] = (g["spend"] / (pur * g["success"])).round()   # per paket sampai
    g["eff_margin"] = (g["margin_order"] * g["success"]).round()   # margin efektif/purchase
    g["cm_after_ad"] = (g["eff_margin"] - g["cost_per_purchase"]).round()   # per purchase
    g["profit"] = (g["purchases"] * g["eff_margin"] - g["spend"]).round()   # total range
    g["revenue"] = (g["purchases"] * g["aov"]).round()
    g["roas"] = (g["revenue"] / g["spend"].replace(0, np.nan)).round(2)
    g["ctr"] = (g["clicks"] / g["impressions"].replace(0, np.nan) * 100).round(2)
    g["breakeven_cpp"] = g["eff_margin"]
    g["ratio"] = (g["cost_per_purchase"] / g["breakeven_cpp"].replace(0, np.nan))

    verd = g.apply(lambda r: _verdict(
        r["ratio"], r["purchases"], r["spend"], pd.notna(r["margin_order"])), axis=1)
    g["verdict"] = [v[0] for v in verd]
    g["verdict_css"] = [v[1] for v in verd]

    g = g.sort_values("spend", ascending=False).reset_index(drop=True)

    # totals
    tot = {
        "spend": float(g["spend"].sum()),
        "purchases": float(g["purchases"].sum()),
        "revenue": float(g["revenue"].sum(skipna=True)),
        "profit": float(g["profit"].sum(skipna=True)),
        "impressions": float(g["impressions"].sum()),
        "clicks": float(g["clicks"].sum()),
        "n_produk": int(len(g)),
    }
    tot["cost_per_purchase"] = (tot["spend"] / tot["purchases"]) if tot["purchases"] else np.nan
    tot["roas"] = (tot["revenue"] / tot["spend"]) if tot["spend"] else np.nan
    out["total"] = tot

    # review: campaign belum terlabeli (sku kosong) ATAU match_status PERLU REVIEW
    unmatched = g[g["sku"].eq("") | g["sku"].str.lower().eq("nan") | g["margin_order"].isna()]
    out["unmatched_spend"] = float(unmatched["spend"].sum())
    rv = d[d.get("match_status", "").astype(str).str.upper().str.contains("REVIEW", na=False)]
    if len(rv):
        out["review"] = (rv.groupby("campaign_name")
                           .agg(spend=("spend", "sum"),
                                purchases=("purchases", "sum"),
                                produk=("produk", "first"))
                           .reset_index()
                           .sort_values("spend", ascending=False))
    out["produk"] = g
    return out


def campaign_detail(meta: pd.DataFrame, key: str, params: dict | None = None,
                    since=None, until=None) -> pd.DataFrame:
    """Rincian per campaign untuk satu produk (SKU atau nama)."""
    if meta is None or len(meta) == 0:
        return pd.DataFrame()
    d = filter_period(meta, since, until).copy()
    d["sku"] = d.get("sku", "").astype(str).str.strip()
    d["produk"] = d.get("produk", "").astype(str).str.strip()
    m = d[(d["sku"] == key) | (d["produk"] == key)].copy()
    if m.empty:
        return pd.DataFrame()
    for c in ["spend", "purchases", "impressions", "clicks", "daily_budget"]:
        if c in m:
            m[c] = _num(m[c]).fillna(0)
    g = (m.groupby("campaign_name")
           .agg(spend=("spend", "sum"), purchases=("purchases", "sum"),
                impressions=("impressions", "sum"), clicks=("clicks", "sum"),
                daily_budget=("daily_budget", "max"),
                status=("status", "last") if "status" in m else ("campaign_name", "size"))
           .reset_index())
    pur = g["purchases"].replace(0, np.nan)
    g["cost_per_purchase"] = (g["spend"] / pur).round()
    g["ctr"] = (g["clicks"] / g["impressions"].replace(0, np.nan) * 100).round(2)
    return g.sort_values("spend", ascending=False).reset_index(drop=True)


def date_bounds(meta: pd.DataFrame):
    """(min_date, max_date) dari sheet Meta-Ads, atau (None, None)."""
    if meta is None or len(meta) == 0 or "date" not in meta:
        return None, None
    dt = pd.to_datetime(meta["date"], errors="coerce").dropna()
    if dt.empty:
        return None, None
    return dt.min().date(), dt.max().date()


# excluded status (campaign yang sengaja dikecualikan user di Ref_Ads_Map)
_EXCLUDE_STATUS = ("DIKECUALIKAN", "EXCLUDED", "EXCLUDE")


def cost_per_purchase_by_sku(meta: pd.DataFrame, since=None, until=None) -> dict:
    """cost/purchase blended per SKU dari Meta-Ads (spend ÷ purchases), utk default CPL Modul 1.
    Mengabaikan campaign yang DIKECUALIKAN. Hanya SKU dengan purchase > 0."""
    if meta is None or len(meta) == 0 or "sku" not in meta:
        return {}
    d = filter_period(meta, since, until).copy()
    if "match_status" in d:
        d = d[~d["match_status"].astype(str).str.upper().isin(_EXCLUDE_STATUS)]
    d["sku"] = d["sku"].astype(str).str.strip()
    d = d[d["sku"].ne("") & d["sku"].str.lower().ne("nan")]
    for c in ["spend", "purchases"]:
        d[c] = _num(d.get(c)).fillna(0)
    g = d.groupby("sku").agg(spend=("spend", "sum"), purchases=("purchases", "sum"))
    g = g[g["purchases"] > 0]
    return (g["spend"] / g["purchases"]).round().to_dict()


def campaign_perf(meta: pd.DataFrame, oo_resolved: pd.DataFrame,
                  catalog: pd.DataFrame, params: dict | None = None,
                  since=None, until=None) -> dict:
    """
    SECTION 1 Modul 5 — performa iklan per produk (unik per SKU) dalam rentang tanggal.
    Meta-Ads difilter kolom `date`; OrderOnline difilter kolom `created` (created_at).

    Mengembalikan dict: { 'ada', 'produk' (DataFrame), 'total' (dict),
      'excluded_spend', 'unmatched_spend' }.
    """
    p = params or {}
    out = {"ada": False, "produk": pd.DataFrame(), "total": {},
           "excluded_spend": 0.0, "unmatched_spend": 0.0}
    if meta is None or len(meta) == 0:
        return out
    d = filter_period(meta, since, until).copy()
    if d is None or len(d) == 0:
        return out
    out["ada"] = True

    d["match_status"] = d.get("match_status", "").astype(str).str.upper()
    d["sku"] = d.get("sku", "").astype(str).str.strip()
    for c in ["spend", "impressions", "clicks", "link_click", "landing_page_view",
              "purchases", "add_to_cart", "daily_budget"]:
        d[c] = _num(d.get(c)).fillna(0)

    excl = d[d["match_status"].isin(_EXCLUDE_STATUS)]
    out["excluded_spend"] = float(excl["spend"].sum())
    d = d[~d["match_status"].isin(_EXCLUDE_STATUS)]

    has_sku = d["sku"].ne("") & d["sku"].str.lower().ne("nan")
    out["unmatched_spend"] = float(d.loc[~has_sku, "spend"].sum())
    dm = d[has_sku].copy()
    if dm.empty:
        return out

    # daily_budget = jumlah budget per campaign (ambil satu nilai per campaign_id)
    if "campaign_id" in dm:
        _cb = dm.groupby(["sku", "campaign_id"])["daily_budget"].max().groupby("sku").sum()
    else:
        _cb = dm.groupby("sku")["daily_budget"].max()

    g = (dm.groupby("sku")
           .agg(produk=("produk", lambda s: s.dropna().astype(str).mode().iloc[0]
                        if not s.dropna().empty else ""),
                spend=("spend", "sum"), impressions=("impressions", "sum"),
                clicks=("clicks", "sum"), link_click=("link_click", "sum"),
                landing_page_view=("landing_page_view", "sum"),
                purchases=("purchases", "sum"), add_to_cart=("add_to_cart", "sum"),
                n_campaign=("campaign_id", "nunique") if "campaign_id" in dm else ("spend", "size"))
           .reset_index())
    g["daily_budget"] = g["sku"].map(_cb).fillna(0)

    # metrik iklan (dihitung ulang dari agregat)
    _imp = g["impressions"].replace(0, np.nan)
    _clk = g["clicks"].replace(0, np.nan)
    _pur = g["purchases"].replace(0, np.nan)
    g["cpm"] = (g["spend"] / _imp * 1000).round()
    g["ctr"] = (g["clicks"] / _imp * 100).round(2)
    g["cpc"] = (g["spend"] / _clk).round()
    g["cost_per_purchase"] = (g["spend"] / _pur).round()

    # --- OrderOnline dalam rentang created_at (leads, closing, omzet) ---
    if oo_resolved is not None and len(oo_resolved) and "created" in oo_resolved:
        oo = oo_resolved.copy()
        oo["sku"] = oo["sku"].astype(str).str.strip()
        cr = pd.to_datetime(oo["created"], errors="coerce")
        if since is not None:
            oo = oo[cr >= pd.to_datetime(since)]; cr = pd.to_datetime(oo["created"], errors="coerce")
        if until is not None:
            # inklusif s/d akhir hari `until`
            oo = oo[cr <= (pd.to_datetime(until) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]
        oo["price"] = _num(oo.get("price")).fillna(0)
        oo["is_closing"] = oo.get("is_closing", False).astype(bool)
        oo["_omz"] = np.where(oo["is_closing"], oo["price"], 0.0)
        og = (oo.dropna(subset=["sku"]).groupby("sku")
                .agg(leads=("sku", "size"), closing=("is_closing", "sum"),
                     omzet=("_omz", "sum")).reset_index())
        g = g.merge(og, on="sku", how="left")
    for c in ["leads", "closing", "omzet"]:
        if c not in g:
            g[c] = 0
        g[c] = _num(g[c]).fillna(0)

    # --- ekonomi produk dari katalog (margin, success, AoV) ---
    cat = catalog.copy() if catalog is not None and not catalog.empty else pd.DataFrame()
    if not cat.empty and "SKU" in cat.columns:
        cat["SKU"] = cat["SKU"].astype(str).str.strip()
        nj = _num(cat.get("nilai_jual")).fillna(0)
        hp = _num(cat.get("hpp_order")).fillna(0)
        ongkir = float(p.get("ongkir", 0) or 0); cb = float(p.get("cashback_pct", 0) or 0)
        fee = float(p.get("cod_fee_rate", 0) or 0); ovar = float(p.get("opex_var_resi", 0) or 0)
        cat["_mg"] = (nj - hp - fee * (nj + ongkir) + cb * ongkir - ovar).round()
        keep = cat[["SKU", "_mg", "sampai_pct", "nilai_jual"]].copy()
        g = g.merge(keep, left_on="sku", right_on="SKU", how="left")
        g = g.drop(columns=[c for c in ["SKU"] if c in g])
    else:
        g["_mg"] = np.nan; g["sampai_pct"] = np.nan; g["nilai_jual"] = np.nan

    succ_def = float(p.get("success_default", 0.6) or 0.6)
    g["success"] = (_num(g["sampai_pct"]) / 100).fillna(succ_def).clip(0, 1)
    g["margin_order"] = _num(g["_mg"])
    g["produk"] = g.apply(lambda r: (r["produk"] or r["sku"]), axis=1)

    # --- metrik keputusan (berbasis closing REAL OrderOnline) ---
    _ld = g["leads"].replace(0, np.nan)
    _cl = g["closing"].replace(0, np.nan)
    target_roi = float(p.get("target_roi", 40) or 0)      # % ROI minimal utk Scale
    g["cost_per_lead"] = (g["spend"] / _ld).round()
    g["cost_per_closing"] = (g["spend"] / _cl).round()
    g["roas"] = (g["omzet"] / g["spend"].replace(0, np.nan)).round(2)
    # closing OrderOnline (paid & completed) = order COD yang SUDAH terkirim & terbayar,
    # jadi margin kotor/order langsung terealisasi (tanpa diskon success lagi).
    g["breakeven_cpa"] = g["margin_order"]                              # impas = margin/closing
    g["profit"] = (g["closing"] * g["margin_order"] - g["spend"]).round()
    # ROI iklan = laba ÷ spend (%). ROI 0% = balik modal; beda dari ROAS (omzet÷spend).
    g["roi"] = (g["profit"] / g["spend"].replace(0, np.nan) * 100).round(1)

    def _decide(r):
        has_m = pd.notna(r["margin_order"])
        if r["spend"] > 0 and r["closing"] <= 0:
            return ("🔴 Kill", "red",
                    f"Spend {_rp(r['spend'])} tanpa closing di rentang ini — matikan / cek tracking.")
        if has_m and pd.notna(r["roi"]):
            roi = r["roi"]
            if roi >= target_roi:
                return ("🟢 Scale", "green",
                        f"ROI {roi:.0f}% ≥ target {target_roi:.0f}% (laba {_rp(r['profit'])}, "
                        f"CPA {_rp(r['cost_per_closing'])} vs impas {_rp(r['breakeven_cpa'])}). Naikkan budget.")
            if roi >= 0:
                return ("🟡 Optimize", "amber",
                        f"ROI {roi:.0f}% (laba {_rp(r['profit'])}) masih di bawah target {target_roi:.0f}%. "
                        "Optimalkan closing/kreatif sebelum scale.")
            return ("🔴 Kill", "red",
                    f"ROI {roi:.0f}% — rugi {_rp(abs(r['profit']))} (CPA {_rp(r['cost_per_closing'])} > "
                    f"impas {_rp(r['breakeven_cpa'])}). Turunkan CPA atau matikan.")
        # tanpa margin katalog: pakai ROAS omzet/spend
        ro = r["roas"]
        if pd.notna(ro):
            if ro >= 3:
                return ("🟢 Scale", "green", f"ROAS {ro:.1f}× (omzet {_rp(r['omzet'])}, margin tak diketahui). Layak scale.")
            if ro >= 1.5:
                return ("🟡 Optimize", "amber", f"ROAS {ro:.1f}× — cukup, optimalkan closing.")
            return ("🔴 Kill", "red", f"ROAS {ro:.1f}× rendah (omzet {_rp(r['omzet'])} < biaya). Evaluasi.")
        return ("⚪ Data kurang", "muted", "Belum ada margin/closing — labeli produk & tunggu data.")

    dec = g.apply(_decide, axis=1)
    g["verdict"] = [x[0] for x in dec]
    g["verdict_css"] = [x[1] for x in dec]
    g["aksi"] = [x[2] for x in dec]

    g = g.sort_values("spend", ascending=False).reset_index(drop=True)

    tot = {
        "spend": float(g["spend"].sum()), "leads": float(g["leads"].sum()),
        "closing": float(g["closing"].sum()), "omzet": float(g["omzet"].sum()),
        "purchases": float(g["purchases"].sum()), "profit": float(g["profit"].sum(skipna=True)),
        "n_produk": int(len(g)),
    }
    tot["roas"] = (tot["omzet"] / tot["spend"]) if tot["spend"] else np.nan
    tot["roi"] = (tot["profit"] / tot["spend"] * 100) if tot["spend"] else np.nan
    # rata-rata biaya akuisisi
    tot["avg_cpp_meta"] = (tot["spend"] / tot["purchases"]) if tot["purchases"] else np.nan  # per purchase Meta
    tot["cpa_real"] = (tot["spend"] / tot["closing"]) if tot["closing"] else np.nan          # per closing OO
    tot["cost_per_closing"] = tot["cpa_real"]
    # selisih jumlah purchase Meta vs leads OrderOnline (kebocoran/atribusi)
    tot["gap_purchase_leads"] = tot["purchases"] - tot["leads"]
    tot["loss_pct"] = ((tot["purchases"] - tot["leads"]) / tot["purchases"] * 100
                       if tot["purchases"] else np.nan)
    out["total"] = tot
    out["produk"] = g
    return out


def _rp(v):
    """Format Rupiah ringkas untuk teks insight (mandiri, tanpa import UI)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(v):
        return "-"
    n = abs(v)
    if n >= 1e9:
        return f"Rp{v/1e9:.1f}M"
    if n >= 1e6:
        return f"Rp{v/1e6:.1f}jt"
    if n >= 1e3:
        return f"Rp{v/1e3:.0f}rb"
    return f"Rp{v:.0f}"
