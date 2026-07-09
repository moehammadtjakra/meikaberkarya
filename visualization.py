# -*- coding: utf-8 -*-
"""
visualization.py
================
Seluruh fungsi pembuat grafik Plotly (tema dark, dominan biru-hijau).
Setiap fungsi menerima DataFrame/sumber data dan mengembalikan go.Figure.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

import config
import formatting as fmt

T = config.THEME


def _base_layout(fig: go.Figure, title: str = "", height: int = 300) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color=T["text"]), x=0.01, xanchor="left"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=T["text"], family="Segoe UI, Inter, sans-serif", size=11),
        margin=dict(l=8, r=8, t=40, b=8),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h",
                    yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(size=10)),
        hoverlabel=dict(bgcolor=T["card"], font_size=12),
        separators=",.",   # format Indonesia: desimal koma, ribuan titik
    )
    fig.update_xaxes(gridcolor=T["grid"], zeroline=False, color=T["muted"])
    fig.update_yaxes(gridcolor=T["grid"], zeroline=False, color=T["muted"])
    return fig


def _rp(v):
    return fmt.rupiah(v)


# ------------------------------------------------------------------ MODUL 1
def fig_funnel(funnel: dict) -> go.Figure:
    labels = list(funnel.keys())
    vals = list(funnel.values())
    fig = go.Figure(go.Funnel(
        y=labels, x=vals,
        textinfo="value+percent initial",
        marker=dict(color=[T["blue"], T["blue_soft"], T["teal"],
                           T["green_soft"], T["green"]]),
        connector=dict(line=dict(color=T["grid"])),
    ))
    return _base_layout(fig, "Funnel: Lead → Order → Resi → Sampai → Dana Cair", 380)


def fig_cashflow(df: pd.DataFrame, gran: str = "Harian") -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=df["tanggal"], y=df["transfer_in"], name="Transfer Masuk",
                marker_color=T["green"])
    fig.add_bar(x=df["tanggal"], y=df["cod_cair"], name="COD Cair",
                marker_color=T["blue_soft"])
    fig.add_bar(x=df["tanggal"], y=-df["ad_spend"], name="Iklan", marker_color=T["red"])
    fig.add_bar(x=df["tanggal"], y=-df["hpp_spend"], name="Beli Produk (HPP)",
                marker_color=T["amber"])
    out2 = -(df["opex"] + df["return_ongkir"])
    fig.add_bar(x=df["tanggal"], y=out2, name="Opex + Ongkir Retur",
                marker_color=T["purple"])
    fig.add_trace(go.Scatter(x=df["tanggal"], y=df["net_cashflow"],
                             name="Net Cashflow", mode="lines",
                             line=dict(color=T["text"], width=2)))
    fig.update_layout(barmode="relative")
    return _base_layout(fig, f"Forecast Cashflow {gran}", 360)


def fig_cum_cashflow(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["tanggal"], y=df["cum_net"],
                             name="Akumulasi Net", mode="lines",
                             fill="tozeroy", line=dict(color=T["green"], width=2)))
    return _base_layout(fig, "Akumulasi Net Cashflow", 300)


def fig_accumulation(tl: pd.DataFrame) -> go.Figure:
    """
    Multi-line akumulasi: Biaya Iklan, Beli Produk (HPP), dan Net Omzet.
    Net Omzet: garis penuh = sudah cair; garis putus-putus = termasuk outstanding
    (omzet sudah didapat tapi menunggu paket diterima & settlement ekspedisi).
    Tooltip menampilkan nilai kumulatif & nilai harian per line.
    """
    x = tl["tanggal"]
    ht = ("<b>%{fullData.name}</b><br>Kumulatif: %{y:,.0f}"
          "<br>Hari ini: %{customdata:,.0f}<extra></extra>")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=tl["cum_ad"], name="Akumulasi Biaya Iklan", mode="lines",
        line=dict(color=T["red"], width=2), customdata=tl["ad_spend"], hovertemplate=ht))
    fig.add_trace(go.Scatter(
        x=x, y=tl["cum_hpp"], name="Akumulasi Beli Produk (HPP)", mode="lines",
        line=dict(color=T["amber"], width=2), customdata=tl["hpp_spend"], hovertemplate=ht))
    if "cum_opex" in tl and tl["cum_opex"].iloc[-1] > 0:
        fig.add_trace(go.Scatter(
            x=x, y=tl["cum_opex"], name="Akumulasi Operasional", mode="lines",
            line=dict(color=T["purple"], width=1.5, dash="dot"),
            customdata=tl["opex"], hovertemplate=ht))
    # net omzet cair (realized) — garis penuh
    fig.add_trace(go.Scatter(
        x=x, y=tl["cum_omzet_realized"], name="Net Omzet (Cair)", mode="lines",
        line=dict(color=T["green"], width=2.5),
        customdata=tl["omzet_realized"], hovertemplate=ht))
    # net omzet termasuk outstanding (earned) — garis putus-putus
    fig.add_trace(go.Scatter(
        x=x, y=tl["cum_omzet_earned"], name="Net Omzet + Outstanding (blm cair)",
        mode="lines", line=dict(color=T["green_soft"], width=2, dash="dash"),
        customdata=tl["omzet_earned"], hovertemplate=ht))
    fig.update_layout(hovermode="x unified")
    return _base_layout(fig, "Akumulasi Biaya Iklan vs Beli Produk vs Net Omzet", 420)


def fig_outstanding_vs_cair(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["tanggal"], y=df["cod_outstanding"],
                             name="Outstanding COD", mode="lines",
                             fill="tozeroy", line=dict(color=T["amber"], width=2)))
    fig.add_trace(go.Scatter(x=df["tanggal"], y=df["cod_cair"],
                             name="Dana Cair Harian", mode="lines",
                             line=dict(color=T["green"], width=2)))
    return _base_layout(fig, "Outstanding COD vs Dana Cair", 340)


def fig_cash_journey(tl: pd.DataFrame, summary: dict) -> go.Figure:
    """
    Perjalanan kas kumulatif: Kas Keluar vs Kas Masuk (cair) vs Kas Masuk+Outstanding.
    Jarak (Kas Keluar − Kas Masuk) di titik terlebar = MODAL yang harus ditalangi.
    Titik dua garis berpotongan = BALIK MODAL. Tooltip: kumulatif + nilai harian.
    """
    x = tl["tanggal"]
    ht = ("<b>%{fullData.name}</b><br>Kumulatif: %{y:,.0f}"
          "<br>Hari ini: %{customdata:,.0f}<extra></extra>")
    fig = go.Figure()
    # area gap (modal terpakai) = kas keluar di atas kas masuk
    fig.add_trace(go.Scatter(x=x, y=tl["cum_cash_out"], name="Kas Keluar Kumulatif",
                             mode="lines", line=dict(color=T["red"], width=2.5),
                             customdata=tl["cash_out"], hovertemplate=ht))
    fig.add_trace(go.Scatter(x=x, y=tl["cum_cash_in"], name="Kas Masuk (sudah cair)",
                             mode="lines", line=dict(color=T["green"], width=2.5),
                             fill="tonexty", fillcolor="rgba(255,92,92,0.12)",
                             customdata=tl["cash_in"], hovertemplate=ht))
    fig.add_trace(go.Scatter(x=x, y=tl["cum_omzet_earned"],
                             name="Kas Masuk + Outstanding (blm cair)", mode="lines",
                             line=dict(color=T["green_soft"], width=1.8, dash="dash"),
                             customdata=tl["omzet_earned"], hovertemplate=ht))
    # Laba/Saldo kas kumulatif = Kas Masuk − Kas Keluar kumulatif (rekonsiliasi dgn
    # 2 garis kas di atas). Harian = net cashflow (surplus/defisit hari itu).
    if "saldo_kas" in tl:
        fig.add_trace(go.Scatter(x=x, y=tl["saldo_kas"],
                                 name="Laba Bersih Kumulatif (Kas = Masuk − Keluar)",
                                 mode="lines", line=dict(color=T["blue"], width=2.4),
                                 customdata=tl["net_cashflow"], hovertemplate=ht))
        fig.add_hline(y=0, line=dict(color=T["muted"], dash="dot", width=1))
    # anotasi modal (gap terlebar)
    gap = (tl["cum_cash_out"] - tl["cum_cash_in"])
    gi = int(gap.idxmax())
    if gap.iloc[gi] > 0:
        fig.add_annotation(x=tl["tanggal"].iloc[gi], y=tl["cum_cash_out"].iloc[gi],
                           ax=0, ay=-30, text=f"Modal {_rp(gap.iloc[gi])}",
                           font=dict(color=T["amber"]), arrowcolor=T["amber"])
    # anotasi BEP kas (kas kumulatif mulai positif) — BUKAN titik aman tarik modal
    bm = summary.get("hari_bep_kas")
    if bm is not None:
        bt = tl["tanggal"].iloc[0] + pd.Timedelta(days=int(bm))
        fig.add_vline(x=bt, line=dict(color=T["blue"], dash="dot"),
                      annotation_text=f"Kas mulai positif H+{bm}",
                      annotation_position="top left",
                      annotation_font=dict(color=T["blue"], size=10))
    # anotasi HARI AMAN KEMBALIKAN MODAL (saldo tak pernah minus lagi sesudahnya)
    km = summary.get("hari_kembali_modal")
    if km is not None and km != bm:
        kt = tl["tanggal"].iloc[0] + pd.Timedelta(days=int(km))
        fig.add_vline(x=kt, line=dict(color=T["green"], dash="dash", width=2),
                      annotation_text=f"✓ Aman kembalikan modal H+{km}",
                      annotation_position="top right",
                      annotation_font=dict(color=T["green"], size=10))
    fig.update_layout(hovermode="x unified")
    return _base_layout(fig, "Perjalanan Kas: Keluar vs Masuk (area merah = modal ditalangi)", 440)


def fig_daily_omzet(tl: pd.DataFrame) -> go.Figure:
    """Proyeksi omzet/kas masuk harian, dipisah sumber: COD (cair) vs Transfer."""
    fig = go.Figure()
    fig.add_bar(x=tl["tanggal"], y=tl["transfer_in"], name="Transfer (prabayar, hari kirim)",
                marker_color=T["green"],
                hovertemplate="%{x|%a %d %b}<br>Transfer: %{y:,.0f}<extra></extra>")
    fig.add_bar(x=tl["tanggal"], y=tl["cod_cair"], name="COD (cair saat settlement)",
                marker_color=T["blue"],
                hovertemplate="%{x|%a %d %b}<br>COD cair: %{y:,.0f}<extra></extra>")
    fig.update_layout(barmode="stack", hovermode="x unified")
    return _base_layout(fig, "Proyeksi Omzet/Kas Masuk Harian — COD vs Transfer", 340)


def fig_saldo_kas(df: pd.DataFrame) -> go.Figure:
    """Saldo kas kumulatif harian — titik terdalam = modal awal dibutuhkan."""
    fig = go.Figure()
    color = [T["green"] if v >= 0 else T["red"] for v in df["saldo_kas"]]
    fig.add_trace(go.Scatter(
        x=df["tanggal"], y=df["saldo_kas"], name="Saldo Kas", mode="lines",
        fill="tozeroy", line=dict(color=T["blue"], width=2),
        hovertemplate="%{x|%d %b}<br>Saldo: %{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=T["muted"], dash="dot"))
    tmin = df.loc[df["saldo_kas"].idxmin()]
    fig.add_annotation(x=tmin["tanggal"], y=tmin["saldo_kas"],
                       text=f"Modal awal {_rp(-tmin['saldo_kas'])}",
                       showarrow=True, arrowcolor=T["amber"], font=dict(color=T["amber"]))
    return _base_layout(fig, "Saldo Kas Harian (titik terdalam = kebutuhan modal)", 340)


def fig_in_vs_out(df: pd.DataFrame) -> go.Figure:
    inflow = df["transfer_in"] + df["cod_cair"]
    outflow = df["ad_spend"] + df["hpp_spend"] + df["opex"] + df["return_ongkir"]
    fig = go.Figure()
    fig.add_bar(x=df["tanggal"], y=inflow, name="Kas Masuk", marker_color=T["green"])
    fig.add_bar(x=df["tanggal"], y=outflow, name="Kas Keluar (iklan+HPP+opex+retur)",
                marker_color=T["red"])
    fig.update_layout(barmode="group")
    return _base_layout(fig, "Kas Masuk vs Kas Keluar", 340)


def fig_expense_breakdown(summary: dict) -> go.Figure:
    """Waterfall Laba-Rugi: Omzet − HPP − Iklan − Ongkir Retur − Opex = Laba Bersih."""
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "relative", "relative", "relative", "total"],
        x=["Omzet Kotor", "HPP (terjual)", "Biaya Iklan", "Ongkir Retur",
           "Operasional", "Laba Bersih"],
        y=[summary["total_revenue"], -summary["total_cogs"], -summary["budget_iklan"],
           -summary["total_return_cost"], -summary["total_opex"], None],
        text=[_rp(summary["total_revenue"]), "-" + _rp(summary["total_cogs"]),
              "-" + _rp(summary["budget_iklan"]), "-" + _rp(summary["total_return_cost"]),
              "-" + _rp(summary["total_opex"]), _rp(summary["net_profit"])],
        textposition="outside",
        connector=dict(line=dict(color=T["grid"])),
        increasing=dict(marker=dict(color=T["green"])),
        decreasing=dict(marker=dict(color=T["red"])),
        totals=dict(marker=dict(color=T["blue"])),
    ))
    return _base_layout(fig, "Laba-Rugi: dari Omzet ke Laba Bersih", 340)


def fig_cod_vs_transfer(summary: dict) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=["COD", "Transfer"],
        values=[summary["nilai_cod"], summary["nilai_transfer"]],
        hole=0.55, marker=dict(colors=[T["blue"], T["green"]]),
        textinfo="label+percent"))
    return _base_layout(fig, "Distribusi COD vs Transfer", 300)


def fig_settlement_schedule(df: pd.DataFrame) -> go.Figure:
    d = df[df["cod_cair"] > 0]
    fig = go.Figure(go.Bar(x=d["tanggal"], y=d["cod_cair"],
                           marker_color=T["teal"],
                           hovertemplate="%{x|%a %d %b}<br>%{y:,.0f}<extra></extra>"))
    return _base_layout(fig, "Estimasi Jadwal Settlement (COD Cair)", 320)


def fig_payout_calendar(df: pd.DataFrame) -> go.Figure:
    """Kalender pencairan: heatmap minggu x hari."""
    d = df.copy()
    d["dow"] = d["tanggal"].dt.weekday
    d["week"] = d["tanggal"].dt.isocalendar().week.astype(int)
    pivot = d.pivot_table(index="week", columns="dow", values="cod_cair",
                          aggfunc="sum", fill_value=0)
    hari = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
    z = pivot.reindex(columns=range(7), fill_value=0).values
    fig = go.Figure(go.Heatmap(
        z=z, x=hari, y=[f"Mg {w}" for w in pivot.index],
        colorscale=config.COLORSCALE, showscale=True,
        hovertemplate="%{y} %{x}<br>Rp%{z:,.0f}<extra></extra>"))
    return _base_layout(fig, "Kalender Pencairan COD", 320)


# ------------------------------------------------------------------ MODUL 2
def fig_bubble_map(prov: pd.DataFrame, metric: str = "resi",
                   label: str = "Jumlah Resi") -> go.Figure:
    d = prov.dropna(subset=["lat", "lon"]).copy()
    # provinsi tanpa nilai (mis. durasi NaN krn paket masih transit) -> 0
    d[metric] = pd.to_numeric(d[metric], errors="coerce").fillna(0)
    fig = go.Figure(go.Scattergeo(
        lon=d["lon"], lat=d["lat"], text=d["provinsi"],
        marker=dict(
            size=d[metric], sizemode="area",
            sizeref=2.0 * d[metric].max() / (45 ** 2) if d[metric].max() else 1,
            sizemin=4, color=d[metric], colorscale=config.COLORSCALE,
            showscale=True, line=dict(width=0.5, color="rgba(255,255,255,0.4)"),
            colorbar=dict(title=label)),
        hovertemplate="<b>%{text}</b><br>" + label + ": %{marker.color:,.0f}<extra></extra>",
    ))
    fig.update_geos(scope="asia", center=dict(lat=-2.5, lon=118),
                    projection_scale=4.2, showcountries=True,
                    countrycolor=T["grid"], showland=True, landcolor=T["panel"],
                    showocean=True, oceancolor=T["bg"], lataxis_range=[-11, 7],
                    lonaxis_range=[94, 142], bgcolor="rgba(0,0,0,0)")
    return _base_layout(fig, f"Peta Sebaran ({label})", 460)


def fig_choropleth(prov: pd.DataFrame, geojson: dict, metric: str = "resi",
                   label: str = "Jumlah Resi") -> go.Figure:
    prov = prov.copy()
    prov[metric] = pd.to_numeric(prov[metric], errors="coerce").fillna(0)
    fig = px.choropleth(
        prov, geojson=geojson, locations="provinsi",
        featureidkey="properties.Propinsi", color=metric,
        color_continuous_scale=config.COLORSCALE)
    fig.update_geos(scope="asia", center=dict(lat=-2.5, lon=118),
                    lataxis_range=[-11, 7], lonaxis_range=[94, 142],
                    bgcolor="rgba(0,0,0,0)", visible=False)
    return _base_layout(fig, f"Choropleth ({label})", 460)


def fig_top_bar(df: pd.DataFrame, col: str, n: int = 10,
                value: str = "resi", title: str = "") -> go.Figure:
    d = df.nlargest(n, value).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d[value], y=d[col], orientation="h",
        marker=dict(color=d[value], colorscale=config.COLORSCALE),
        text=d[value], textposition="auto"))
    return _base_layout(fig, title, 380)


def fig_treemap(prov: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Treemap(
        labels=prov["provinsi"], parents=[""] * len(prov),
        values=prov["resi"],
        marker=dict(colors=prov["proyeksi_net"], colorscale=config.COLORSCALE),
        textinfo="label+value+percent root",
        hovertemplate="<b>%{label}</b><br>Resi: %{value}<extra></extra>"))
    return _base_layout(fig, "Treemap Wilayah (ukuran=resi, warna=net)", 420)


def fig_duration_hist(df: pd.DataFrame) -> go.Figure:
    d = df["durasi_kirim"].dropna()
    fig = go.Figure(go.Histogram(x=d, nbinsx=30, marker_color=T["blue"]))
    fig.add_vline(x=d.mean(), line=dict(color=T["amber"], dash="dash"),
                  annotation_text=f"rata² {d.mean():.1f} hari")
    return _base_layout(fig, "Histogram Durasi Pengiriman", 320)


def fig_duration_box(df: pd.DataFrame, by: str = "provinsi", n: int = 10) -> go.Figure:
    top = df[by].value_counts().head(n).index
    d = df[df[by].isin(top)]
    fig = go.Figure()
    for i, g in enumerate(top):
        fig.add_trace(go.Box(y=d[d[by] == g]["durasi_kirim"], name=str(g),
                             marker_color=config.CATEGORICAL_COLORS[i % 8]))
    fig.update_layout(showlegend=False)
    return _base_layout(fig, f"Boxplot Durasi per {by.title()}", 360)


def fig_region_perf(df: pd.DataFrame, col: str = "provinsi", n: int = 12) -> go.Figure:
    d = df.nlargest(n, "resi")
    fig = go.Figure()
    fig.add_bar(x=d[col], y=d["resi"], name="Resi", marker_color=T["blue"])
    fig.add_trace(go.Scatter(x=d[col], y=d["sla"], name="SLA %", yaxis="y2",
                             mode="lines+markers", line=dict(color=T["green"])))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 100],
                                  color=T["muted"], showgrid=False))
    return _base_layout(fig, f"Performa {col.title()} (Resi vs SLA)", 360)


# ------------------------------------------------------------------ MODUL 3
def fig_top_products(prod: pd.DataFrame, n: int = 12,
                     value: str = "net_real", title: str = "") -> go.Figure:
    d = prod.nlargest(n, value).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d[value], y=d["produk"], orientation="h",
        marker=dict(color=d[value], colorscale=config.COLORSCALE),
        text=[_rp(v) for v in d[value]], textposition="auto"))
    return _base_layout(fig, title or "Top Produk (Kontribusi Net Real)", 420)


def fig_pareto(prod: pd.DataFrame, n: int = 15) -> go.Figure:
    d = prod.head(n)
    fig = go.Figure()
    fig.add_bar(x=d["produk"], y=d["net_real"], name="Net Real",
                marker_color=T["blue"])
    fig.add_trace(go.Scatter(x=d["produk"], y=d["kontribusi_kumulatif"],
                             name="Kumulatif %", yaxis="y2", mode="lines+markers",
                             line=dict(color=T["amber"], width=2)))
    fig.add_hline(y=80, line=dict(color=T["green"], dash="dash"), yref="y2")
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 105],
                                  color=T["muted"], showgrid=False, ticksuffix="%"))
    return _base_layout(fig, "Analisis Pareto Produk (80/20)", 400)


def fig_quadrant(prod: pd.DataFrame) -> go.Figure:
    color_map = {
        "⭐ Winning (Volume & Margin Tinggi)": T["green"],
        "🐄 Volume Tinggi, Margin Tipis": T["blue"],
        "💎 Margin Tinggi, Volume Rendah": T["purple"],
        "❓ Volume & Margin Rendah": T["muted"],
    }
    fig = go.Figure()
    for k, c in color_map.items():
        d = prod[prod["kuadran"] == k]
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["resi"], y=d["margin_per_resi"], mode="markers", name=k,
            marker=dict(size=(d["net_real"].clip(lower=1) ** 0.5) / 30 + 6, color=c,
                        line=dict(width=0.5, color="rgba(255,255,255,0.4)")),
            text=d["produk"],
            hovertemplate="<b>%{text}</b><br>Resi: %{x}<br>Margin/resi: %{y:,.0f}<extra></extra>"))
    fig.add_vline(x=prod["resi"].median(), line=dict(color=T["grid"], dash="dot"))
    fig.add_hline(y=prod["margin_per_resi"].median(), line=dict(color=T["grid"], dash="dot"))
    fig.update_xaxes(title="Volume (Resi)")
    fig.update_yaxes(title="Margin per Resi (Rp)")
    return _base_layout(fig, "Kuadran Produk: Volume vs Margin", 440)


def fig_product_treemap(prod: pd.DataFrame, n: int = 25) -> go.Figure:
    d = prod.head(n)
    fig = go.Figure(go.Treemap(
        labels=d["produk"], parents=[""] * len(d), values=d["net_real"].clip(lower=0),
        marker=dict(colors=d["margin_per_resi"], colorscale=config.COLORSCALE),
        textinfo="label+value+percent root",
        hovertemplate="<b>%{label}</b><br>Net Real: %{value:,.0f}<extra></extra>"))
    return _base_layout(fig, "Treemap Kontribusi Net Real per Produk", 420)


def fig_product_sla(prod: pd.DataFrame, n: int = 12) -> go.Figure:
    d = prod.nlargest(n, "resi")
    fig = go.Figure()
    fig.add_bar(x=d["produk"], y=d["resi"], name="Resi", marker_color=T["blue"])
    fig.add_trace(go.Scatter(x=d["produk"], y=d["sla"], name="SLA %", yaxis="y2",
                             mode="lines+markers", line=dict(color=T["green"])))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 100],
                                  color=T["muted"], showgrid=False))
    return _base_layout(fig, "Volume vs SLA per Produk (Top Volume)", 380)
