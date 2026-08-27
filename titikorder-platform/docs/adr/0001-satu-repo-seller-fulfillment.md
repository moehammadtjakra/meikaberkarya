# ADR 0001 — Satu repo untuk Seller dan Fulfillment

**Status:** Diterima · 2026-08-23

---

## Konteks

TitikOrder punya dua domain bisnis yang sengaja dipisah di runtime: **Seller** (landing page, order, CRM, resi, keuangan, iklan) dan **Fulfillment** (gudang, inbound, picking, packing, tagihan). Keduanya sudah diputuskan berjalan sebagai **service terpisah dengan database terpisah**.

Muncul pertanyaan: apakah keduanya juga perlu **repositori GitHub terpisah**, dengan alasan keandalan sistem?

## Klarifikasi penting

**Repositori bukan batas keandalan.** Keandalan runtime ditentukan oleh:

- service yang di-deploy terpisah (Cloud Run, revisi & rollback sendiri-sendiri),
- database yang terpisah (kegagalan satu tidak menyeret yang lain),
- komunikasi lewat kontrak (REST + Pub/Sub), bukan `JOIN` lintas domain.

Ketiganya **sudah tercapai** tanpa memandang jumlah repo. Satu repo bisa men-deploy tujuh service yang gagal, di-scale, dan di-rollback secara independen. Repo hanyalah organisasi source code.

Jadi keputusan repo murni soal **organisasi manusia**, bukan perilaku sistem.

## Keputusan

**Gunakan SATU repositori `titikorder`** yang memuat kedua domain, dengan batas internal yang ditegakkan alat.

```
apps/seller-*      domain Seller
apps/ff-*          domain Fulfillment
packages/contracts kontrak bersama (REST + skema event)  ← satu-satunya jembatan
```

**Aturan batas:** kode `apps/seller-*` **dilarang** mengimpor dari `apps/ff-*` dan sebaliknya. Satu-satunya jalur adalah `packages/contracts`. Ditegakkan lewat lint (mis. `eslint no-restricted-imports` atau `dependency-cruiser`) yang jalan di CI — bukan sekadar kesepakatan lisan.

## Alasan

1. **Kontrak berubah atomik.** Saat skema event `fulfillment.handed_over` berubah, produsen dan konsumen diperbarui dalam **satu PR**. Dengan dua repo, Anda wajib melakukan versioning kontrak + rilis dua tahap yang kompatibel mundur — beban nyata untuk pengembang tunggal.
2. **Satu sesi Claude Code melihat semuanya.** Dua repo berarti dua sesi yang saling buta terhadap kontrak yang mereka bagi.
3. **Tidak ada paket npm internal.** `packages/core`, `contracts`, dan `ui` diimpor langsung tanpa perlu registry privat.
4. **Tidak ada kerugian keandalan** — lihat klarifikasi di atas.

## Kapan ditinjau ulang (pemicu pemisahan)

Pisahkan menjadi dua repo bila **salah satu** terjadi:

| Pemicu | Alasan |
|---|---|
| Ada tim/vendor terpisah untuk gudang | akses source code perlu dibatasi |
| Fulfillment dijual/dipisah sebagai badan usaha sendiri | kepemilikan kode ikut terpisah |
| Audit/kepatuhan menuntut ruang lingkup terpisah | jejak audit lebih bersih |
| CI mulai lambat & mengganggu (> ±15 menit walau sudah path-based) | waktu tunggu jadi mahal |

Selama tidak ada satu pun yang terjadi, satu repo lebih menguntungkan.

## Cara memisahkan nanti (kalau pemicunya muncul)

Keputusan ini **reversibel dengan murah**, asalkan aturan batas ditaati:

```bash
git subtree split -P apps/ff-api -b ff-api-only
# atau, dengan histori lebih bersih:
git filter-repo --path apps/ff-api --path packages/contracts
```

Histori commit ikut terbawa. Yang membuat pemisahan mahal bukan ukuran repo, melainkan **impor silang yang terlanjur menyebar** — itulah sebabnya lint pembatas dipasang sejak hari pertama.

## Konsekuensi

**Positif:** perubahan kontrak atomik; konteks AI utuh; tanpa registry paket internal; pemisahan tetap terbuka.

**Negatif yang diterima:** semua orang yang punya akses repo melihat kedua domain; CI perlu path-based trigger sejak awal agar tidak membangun semuanya setiap commit.

**Risiko utama:** batas antar domain luntur diam-diam lewat impor silang. **Mitigasi:** aturan lint di CI, ditambah pengingat eksplisit di `CLAUDE.md`.
