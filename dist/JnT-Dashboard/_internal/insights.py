# -*- coding: utf-8 -*-
"""
insights.py
===========
Menghasilkan insight otomatis berbahasa Indonesia yang mudah dipahami
manajemen, berdasarkan hasil simulasi cashflow & analisis wilayah.
"""

from __future__ import annotations
import pandas as pd
import formatting as fmt


def _rp(v):
    return fmt.rupiah(v)


def _num(v):
    return fmt.jumlah(v)


def cashflow_insights(sim: dict) -> list[str]:
    s = sim["summary"]
    tl = sim["timeline"]
    p = s["params"]
    out = []

    eff_cpl = s["budget_iklan"] / s["n_lead"] if s.get("n_lead") else 0
    out.append(
        f"Dengan budget iklan {_rp(s['budget_iklan'])} (CPL efektif {_rp(eff_cpl)}), "
        f"diperkirakan memperoleh ±{_num(s['n_lead'])} lead."
    )
    out.append(
        f"Dari lead tersebut diperkirakan menghasilkan ±{_num(s['n_order'])} order "
        f"(closing {p['closing_rate']*100:.0f}%) yang setara {_num(s['n_resi'])} resi."
    )
    out.append(
        f"Modal yang perlu disiapkan: HPP produk ±{_rp(s.get('modal_hpp', 0))} "
        f"(beli stok) + modal kerja ±{_rp(s.get('modal_kerja', 0))} (talangan) "
        f"= total ±{_rp(s.get('modal_total', 0))}."
    )
    out.append(
        f"Sekitar {_num(s['n_sukses'])} paket berhasil dikirim "
        f"(success rate {s['success_rate']*100:.1f}%), {_num(s['n_gagal'])} berpotensi gagal/retur."
    )
    out.append(
        f"Komposisi pembayaran {p['pct_cod']*100:.0f}% COD dan "
        f"{(1-p['pct_cod'])*100:.0f}% transfer. Dana transfer ({_rp(s['nilai_transfer'])}) "
        f"masuk lebih cepat karena bersifat prabayar."
    )

    # kapan COD mulai cair & puncak pencairan
    cair = tl[tl["cod_cair"] > 0]
    if not cair.empty:
        first = cair["tanggal"].iloc[0]
        peak_row = cair.loc[cair["cod_cair"].idxmax()]
        out.append(
            f"Dana COD mulai cair pada {first:%a, %d %b %Y} mengikuti pola settlement "
            f"({'harian' if p['mode']=='mode1' else 'Senin/Selasa/Kamis'}). "
            f"Puncak pencairan diperkirakan {peak_row['tanggal']:%d %b %Y} "
            f"sebesar {_rp(peak_row['cod_cair'])}."
        )

    out.append(
        f"Outstanding COD (dana tertahan) diperkirakan memuncak di "
        f"{_rp(s['outstanding_peak'])}."
    )
    out.append(
        f"Estimasi kebutuhan MODAL KERJA ±{_rp(s['modal_kerja'])} — yaitu dana talangan "
        f"untuk menutup jeda antara biaya iklan/ongkir di awal dengan pencairan COD "
        f"yang baru masuk {p.get('mode')=='mode2' and 'tiap Senin/Selasa/Kamis' or 'beberapa hari kerja'} kemudian."
    )
    out.append(
        f"Proyeksi net cashflow selama {s['horizon_days']} hari: "
        f"{_rp(s['net_cashflow_total'])}. Dana cair minggu ini ±{_rp(s['cair_minggu_ini'])}, "
        f"bulan ini ±{_rp(s['cair_bulan_ini'])}."
    )
    return out


def geography_insights(prov: pd.DataFrame) -> list[str]:
    if prov is None or prov.empty:
        return []
    out = []
    top = prov.iloc[0]
    out.append(
        f"Provinsi tujuan terbanyak: {top['provinsi']} dengan {_num(top['resi'])} resi "
        f"(net {_rp(top['proyeksi_net'])}, SLA {top['sla']:.0f}%)."
    )
    # SLA terendah (min 20 resi)
    sig = prov[prov["resi"] >= 20]
    if not sig.empty:
        worst = sig.sort_values("sla").iloc[0]
        out.append(
            f"SLA terendah di {worst['provinsi']} ({worst['sla']:.0f}% sampai, "
            f"durasi rata² {worst['avg_durasi']} hari) — perlu perhatian operasional."
        )
        slow = sig.sort_values("avg_durasi", ascending=False).iloc[0]
        out.append(
            f"Pengiriman terlama menuju {slow['provinsi']} "
            f"(rata² {slow['avg_durasi']} hari)."
        )
    out.append(
        f"Total outstanding COD dari paket belum sampai: "
        f"{_rp(prov['outstanding'].sum())} tersebar di {len(prov)} provinsi."
    )
    return out


def product_insights(prod: pd.DataFrame, pareto: dict) -> list[str]:
    if prod is None or prod.empty:
        return []
    out = []
    win = prod.iloc[0]
    out.append(
        f"🏆 Winning product: **{win['produk']}** menyumbang {win['kontribusi_pct']:.1f}% "
        f"net real ({_rp(win['net_real'])}) dari {_num(win['resi'])} resi."
    )
    # margin jual per resi tertinggi (volume cukup, min 10 resi)
    sig = prod[prod["resi"] >= 10]
    if not sig.empty:
        hi = sig.sort_values("margin_jual_per_resi", ascending=False).iloc[0]
        out.append(
            f"💎 Margin jual per resi tertinggi: **{hi['produk']}** "
            f"({_rp(hi['margin_jual_per_resi'])}/resi, margin {hi['margin_pct']:.0f}%, "
            f"{_num(hi['resi'])} resi) — paling layak digenjot iklannya."
        )
        # volume tinggi tapi SLA rendah -> risiko
        risk = sig[sig["sla"] < 60].sort_values("resi", ascending=False)
        if not risk.empty:
            r = risk.iloc[0]
            out.append(
                f"⚠️ **{r['produk']}** bervolume tinggi ({_num(r['resi'])} resi) "
                f"namun SLA hanya {r['sla']:.0f}% — banyak paket belum sampai, "
                f"berisiko menahan pencairan COD."
            )
        # margin tipis / rugi setelah HPP
        thin = sig.sort_values("margin_jual_per_resi").iloc[0]
        if thin["margin_jual_per_resi"] < 0:
            out.append(
                f"🔻 **{thin['produk']}** merugi setelah HPP "
                f"({_rp(thin['margin_jual_per_resi'])}/resi) — evaluasi harga jual/HPP."
            )
    if pareto:
        out.append(
            f"📊 Prinsip Pareto: {pareto['n_produk_inti']} produk "
            f"({pareto['share_produk']:.0f}% dari {pareto['n_produk_total']} produk) "
            f"menyumbang ~{pareto['pct']:.0f}% net — fokuskan stok & iklan di sini."
        )
    out.append(
        f"AOV (rata² nilai order) tertinggi: "
        f"**{prod.sort_values('aov', ascending=False).iloc[0]['produk']}** "
        f"({_rp(prod['aov'].max())})."
    )
    return out
