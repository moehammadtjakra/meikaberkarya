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
    ret_rate = s.get("return_rate", 0) * 100
    if s.get("retur_excess", 0) <= 0:
        ret_txt = (f"Retur {ret_rate:.0f}% (≤ 20%) → **ongkir retur GRATIS** sesuai aturan J&T. "
                   f"Barang kembali & bisa dijual ulang (HPP tidak hilang).")
    else:
        ret_txt = (f"Retur {ret_rate:.0f}% (> 20%) → kena ongkir retur atas kelebihan "
                   f"{s.get('retur_excess',0)*100:.0f}% × ongkir penuh = ±{_rp(s.get('total_return_cost',0))}. "
                   f"Barang tetap kembali (HPP tidak hilang).")
    out.append(
        f"Sekitar {_num(s['n_sukses'])} paket berhasil dikirim "
        f"(success rate {s['success_rate']*100:.1f}%). {_num(s['n_gagal'])} paket retur. " + ret_txt
    )
    out.append(
        f"Komposisi bayar {p['pct_cod']*100:.0f}% COD, {(1-p['pct_cod'])*100:.0f}% transfer. "
        f"Non-COD ({_rp(s['nilai_transfer'])}) masuk **hari itu juga** (likuid langsung); "
        f"COD ({_rp(s['nilai_cod'])}) baru cair setelah paket diterima + settlement."
    )
    bep = s.get("hari_bep_kas")
    km = s.get("hari_kembali_modal")
    bep_txt = (f"Kas kumulatif mulai positif di hari ke-{bep}"
               if bep is not None else "Kas belum sempat positif dalam horizon ini")
    km_txt = (f", tapi **modal aman ditarik penuh baru di hari ke-{km}** (setelah itu "
              f"saldo kas tak pernah minus lagi)." if km is not None
              else ", dan modal belum aman ditarik penuh dalam periode ini.")
    out.append(
        f"💰 **Modal awal realistis ±{_rp(s.get('modal_awal', 0))}** — kas terdalam yang "
        f"harus ditalangi (iklan + beli produk HPP ±{_rp(s.get('total_beli_produk', 0))} + "
        f"opex) sebelum omzet COD cair. Saldo kas terendah {_rp(s.get('saldo_kas_min', 0))}. "
        f"{bep_txt}{km_txt}"
    )
    out.append(
        f"📈 **Laba bersih ±{_rp(s.get('net_profit', 0))}** (omzet − HPP terjual − iklan − "
        f"ongkir retur − opex ±{_rp(s.get('total_opex', 0))}) → **ROI modal "
        f"{s.get('roi_modal', 0):.0f}%**, ROI atas iklan {s.get('roi_iklan', 0):.0f}%."
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
        f"Outstanding omzet (sudah didapat tapi belum cair, menunggu paket diterima & "
        f"settlement) memuncak di {_rp(s['outstanding_peak'])} — ini sumber utama kebutuhan modal awal."
    )
    out.append(
        f"Dana cair minggu ini ±{_rp(s['cair_minggu_ini'])}, "
        f"bulan ini ±{_rp(s['cair_bulan_ini'])}."
    )
    return out


def geography_insights(prov: pd.DataFrame) -> list[str]:
    if prov is None or prov.empty:
        return []
    out = []
    top = prov.iloc[0]
    retur_all = (prov["retur"].sum() / prov["resi"].sum() * 100) if prov["resi"].sum() else 0
    out.append(
        f"🏆 Pasar terbesar: **{top['provinsi']}** — {_num(top['resi'])} resi, "
        f"net {_rp(top['proyeksi_net'])}, sampai {top['sla']:.0f}%, retur {top['retur_pct']:.0f}%."
    )
    sig = prov[prov["resi"] >= 15]
    if not sig.empty:
        w = sig.sort_values("retur_pct", ascending=False).iloc[0]
        out.append(
            f"🔴 Retur tertinggi: **{w['provinsi']}** — {w['retur_pct']:.0f}% "
            f"({_num(int(w['retur']))} dari {_num(int(w['resi']))} resi). "
            f"Pertimbangkan **kurangi/hentikan iklan** ke wilayah ini, atau perketat "
            f"verifikasi order (rata² retur nasional {retur_all:.0f}%)."
        )
        # wilayah volume besar TAPI retur tinggi = prioritas perbaikan
        big_bad = sig[(sig["resi"] >= sig["resi"].median()) &
                      (sig["retur_pct"] > retur_all)].sort_values("resi", ascending=False)
        if not big_bad.empty:
            b = big_bad.iloc[0]
            out.append(
                f"⚠️ Prioritas perbaikan: **{b['provinsi']}** bervolume besar "
                f"({_num(int(b['resi']))} resi) sekaligus retur tinggi ({b['retur_pct']:.0f}%) — "
                f"dampaknya paling besar ke biaya & modal tertahan."
            )
        safe = sig.sort_values(["retur_pct", "sla"], ascending=[True, False]).iloc[0]
        out.append(
            f"✅ Paling aman: **{safe['provinsi']}** — retur hanya {safe['retur_pct']:.0f}%, "
            f"sampai {safe['sla']:.0f}%. Wilayah seperti ini layak **digenjot**."
        )
    return out


def product_insights(prod: pd.DataFrame, pareto: dict) -> list[str]:
    if prod is None or prod.empty:
        return []
    out = []
    win = prod.iloc[0]
    out.append(
        f"🏆 **Winning: {win['produk']}** — kontribusi net terbesar {win['kontribusi_pct']:.1f}% "
        f"({_rp(win['net_real'])}), margin {_rp(win['margin_jual_per_resi'])}/resi, "
        f"sampai {win['sla']:.0f}%, retur {win['retur_pct']:.0f}%. Prioritas utama untuk di-scale."
    )
    sig = prod[prod["resi"] >= 10]
    if not sig.empty:
        # produk teraman: retur terendah + SLA tinggi
        safe = sig.sort_values(["retur_pct", "sla"], ascending=[True, False]).iloc[0]
        out.append(
            f"✅ **Teraman: {safe['produk']}** — retur cuma {safe['retur_pct']:.0f}%, "
            f"sampai {safe['sla']:.0f}% ({_num(safe['resi'])} resi). Paling minim risiko modal "
            f"tertahan, aman digenjot terutama untuk pasar baru."
        )
        # bintang: margin tinggi & aman sekaligus
        star = sig[(sig["margin_jual_per_resi"] > sig["margin_jual_per_resi"].median()) &
                   (sig["retur_pct"] < sig["retur_pct"].median())].sort_values(
            "net_real", ascending=False)
        if not star.empty:
            stp = star.iloc[0]
            out.append(
                f"⭐ **{stp['produk']}** margin tinggi ({_rp(stp['margin_jual_per_resi'])}/resi) "
                f"DAN aman (retur {stp['retur_pct']:.0f}%) — kombinasi terbaik."
            )
        # bahaya: volume tinggi tapi retur tinggi
        risk = sig[sig["retur_pct"] > 30].sort_values("resi", ascending=False)
        if not risk.empty:
            r = risk.iloc[0]
            out.append(
                f"⚠️ **{r['produk']}** retur tinggi ({r['retur_pct']:.0f}%, {_num(r['resi'])} resi) "
                f"— banyak modal & ongkir terbuang; perketat target audiens/verifikasi order."
            )
        thin = sig.sort_values("margin_jual_per_resi").iloc[0]
        if thin["margin_jual_per_resi"] < 0:
            out.append(
                f"🔻 **{thin['produk']}** rugi setelah HPP "
                f"({_rp(thin['margin_jual_per_resi'])}/resi) — naikkan harga atau tekan HPP."
            )
    if pareto:
        out.append(
            f"📊 Pareto: cukup **{pareto['n_produk_inti']} produk** "
            f"({pareto['share_produk']:.0f}% katalog) sudah menyumbang ~{pareto['pct']:.0f}% net "
            f"— fokuskan stok, modal & iklan di sini."
        )
    return out
