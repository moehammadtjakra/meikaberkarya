# Serah-Terima Konteks — baca ini pertama

Dokumen ini memindahkan **seluruh konteks perencanaan** ke sesi kerja baru (Claude Code atau orang baru). Isinya adalah hal-hal yang **tidak terbaca dari kode**: latar bisnis, keputusan beserta alasannya, dan pelajaran dari sistem yang sudah berjalan.

Kalau Anda AI yang baru membaca repo ini: **baca dokumen ini sampai habis sebelum menulis kode apa pun.**

---

## 1. Konteks bisnis

**Meika Berkarya** adalah bisnis social commerce di Indonesia: menjual produk lewat iklan Meta → landing page → lead masuk → CS closing lewat WhatsApp → dikirim COD lewat J&T.

Kondisi saat ini:

- Volume: ribuan order per bulan. Data nyata terakhir: **20.943 lead** OrderOnline, **6.468 closing** (closing rate ±31% keseluruhan, ±46% pada definisi paid & completed), belanja iklan Meta puluhan juta rupiah per bulan.
- **Ketergantungan pada OrderOnline** (platform pihak ketiga) untuk landing page + order + CRM. Inilah yang akan digantikan.
- Ekspedisi: **J&T** (kerja sama langsung). Rencana berikutnya SPX, mungkin agregator (Everpro/Lincah).
- Iklan: **Meta Ads**. Rencana berikutnya TikTok/Google.
- Pemilik juga akan menjalankan **jasa fulfillment** dan ingin menggaet seller lain — karena itu sistem dirancang multi-tenant sejak awal.

**Tujuan besar:** menjadi agregator social commerce yang menyatukan hulu (iklan, landing page, closing) sampai hilir (gudang, kirim, retur, uang cair) dalam satu sistem berbasis data.

**Dikerjakan solo + AI.** Ini batasan desain yang nyata: setiap komponen tambahan harus dibayar dengan waktu satu orang.

---

## 2. Aset yang sudah ada (di luar repo ini)

Jangan membangun ulang yang sudah jalan. Semua ini ada di repo terpisah (`meika-dashboard` / folder Meika Berkarya):

| Aset | Isi | Relevansi |
|---|---|---|
| **Dashboard Streamlit** | Modul 1 (simulator cashflow), 2 (target profit), 3 (wilayah), 4 (produk), 5 (iklan Meta) | logikanya akan di-port ke modul `analytics` pada Fase S4 |
| `meta_engine.py` | agregasi iklan per produk, verdict Scale/Optimize/Kill berbasis ROI | jadi acuan `integrations/ads/meta` |
| `product_admin.py` | resolusi OrderOnline→SKU berlapis, katalog produk | acuan logika pemetaan produk |
| **MetaAds.gs** (Apps Script) | penarik Meta Ads harian + pelabelan campaign→SKU | jadi acuan `AdPlatformAdapter` |
| **JnT_GSheet_System** | upsert data J&T by waybill, dashboard pencairan | acuan `CourierAdapter` (J&T) |
| **Admin_Order_System** | export order → J&T, tarik resi, stok, HPP moving average | acuan modul `shipping` & `inventory` |
| **CS_Undelivered_System** | distribusi paket undel ke CS per provinsi | acuan modul monitoring undel |

**Cara memakainya:** saat mengerjakan fase yang relevan, tambahkan repo dashboard ke sesi (`/add-dir`) lalu **port logikanya**, jangan menulis ulang dari nol.

---

## 3. Pelajaran teknis dari data nyata (mahal didapat, jangan diulangi)

Ini kesalahan yang sudah ditemukan dan diperbaiki di sistem lama. Jangan mengulanginya:

1. **Meta melaporkan satu purchase dalam banyak label.** `purchase`, `omni_purchase`, `onsite_web_purchase`, `offsite_conversion.fb_pixel_purchase`, dst semuanya berisi **angka yang sama**. Ambil **satu kanonik** (`purchase`); menjumlahkannya membuat angka 8× lipat.

2. **`product_code` OrderOnline tidak unik.** Kode `TPT` dipakai 6 produk berbeda (Sikat Punggung, Pembesar Layar Hp, dll). Resolusi ke SKU harus **berlapis**: `order_id` → Import-Order, lalu `product_code` + nama produk (cocokkan ke nama kanonik), baru `product_code` saja.

3. **Purchase Meta ≠ lead nyata.** Di data terakhir, Meta melaporkan 3.370 purchase sementara OrderOnline hanya menerima 1.842 lead — **selisih 45%**. Jangan pernah memakai angka Meta sebagai dasar keuangan; pakai data internal.

4. **Cost/purchase Meta jauh lebih murah dari CPA nyata.** Rp 17.920 (Meta) vs Rp 67.551 (spend ÷ closing nyata). Keputusan scale/kill harus memakai CPA nyata.

5. **ROI ≠ ROAS.** ROAS pakai omzet, ROI pakai laba. Di data nyata: ROAS 1,15× tapi ROI −6,9% — terlihat untung padahal rugi setelah HPP. Verdict harus berbasis ROI.

6. **Closing COD = sudah terkirim & terbayar.** Jangan mengalikan margin dengan success rate lagi untuk order yang sudah `paid & completed` — itu diskon ganda yang membuat semua produk terlihat rugi.

7. **Retur dihitung terhadap TOTAL resi**, bukan (sampai + retur). Begitu juga success rate. Ini acuan yang dipakai bisnis terhadap ekspedisi.

8. **Rata-rata durasi kirim hanya dari paket yang sampai** — memasukkan retur membuat proyeksi pencairan meleset.

---

## 4. Keputusan yang sudah final (jangan diperdebatkan ulang)

| # | Keputusan | Alasan singkat |
|---|---|---|
| 1 | **Dua domain (Seller, Fulfillment), database terpisah** | batas bisnis nyata; fulfillment kelak melayani seller lain |
| 2 | **Satu repo untuk keduanya** | kontrak berubah atomik; konteks AI utuh. Lihat `adr/0001` |
| 3 | **Cloud Run, bukan GKE** | beban operasional K8s tidak terbayar pada skala ini |
| 4 | **Cloudflare, bukan GCP Load Balancer** | fungsi setara, hemat ±$50–95/bulan |
| 5 | **Cloud SQL zonal dulu, HA menyusul** | menekan biaya ke Rp 3–5 juta; risiko downtime 1–4 jam diterima sadar |
| 6 | **Resi selalu diterbitkan Seller** | integrasi J&T sudah dikuasai; FS hanya pelaksana fisik |
| 7 | **Routing gudang SEBELUM terbitkan resi** | alamat asal di resi bergantung gudang pemenuh |
| 8 | **Landing page berbasis path, bukan subdomain** | jumlah LP sangat banyak; menambah LP = satu baris DB |
| 9 | **Ledger append-only untuk stok & uang** | keterlacakan; tidak ada saldo yang di-UPDATE |
| 10 | **RLS Postgres + role `app_user`** | isolasi tenant ditegakkan DB, bukan hanya kode |
| 11 | **Adapter untuk ekspedisi & platform iklan** | menambah SPX/TikTok = folder baru, nol perubahan inti |
| 12 | **General vs internal pakai entitlement**, bukan basis kode terpisah | membuka seller lain cukup menyalakan flag |
| 13 | **Frontend/backend dipisah** (`*-web` vs `*-api`) | banyak klien (web, scanner, mobile kelak); logika bisnis hanya di `*-api` |
| 14 | **TypeScript + Next.js + NestJS + Prisma** | satu bahasa; dukungan AI codegen terbaik |
| 15 | **Claude Code tidak boleh commit/push/deploy** | keputusan rilis tetap di tangan manusia |

---

## 5. Status saat ini

**Sudah ada & tervalidasi:**

| Berkas | Status |
|---|---|
| `db/schema.sql` | Fase 0–2, dijalankan di PostgreSQL sungguhan → **0 error** |
| `db/test_schema.py` | **7 tes perilaku lulus**: isolasi RLS, WITH CHECK, state machine, ledger, append-only, constraint, idempotency |
| `packages/core/order.ts` | state machine, normalisasi telepon, total order, ekspansi bundle, idempotency key |
| `packages/core/order.test.ts` | **19 tes lulus**, tanpa DB |
| `apps/lp/app/api/intake/route.ts` | contoh endpoint intake idempoten (belum terpasang di app nyata) |
| `docs/*` | arsitektur, struktur, rencana fase, GCP, biaya, CI/CD, isolasi kegagalan |

**Belum ada:** seluruh kerangka aplikasi (Fase S0). Itulah pekerjaan pertama.

---

## 6. Yang belum diputuskan (jangan asal pilih — tanyakan)

1. **Split shipment** bila stok tersebar di dua gudang: pecah 2 resi atau tunggu? (usulan: jangan pecah dulu)
2. **Multi-kurir**: abstraksi sejak awal atau J&T dulu? (usulan: abstraksi tipis, implementasi J&T saja)
3. **WhatsApp**: klik-to-chat manual dulu atau langsung Cloud API? (usulan: manual — Cloud API bisa Rp 2–6 juta/bulan)
4. **Gudang penerima retur** bila kirim dari gudang FS tapi seller punya gudang sendiri
5. **Versi harga** — apakah promo perlu jadwal berlaku?

---

## 7. Prompt sesi pertama (tempel apa adanya)

```
Kamu akan bekerja di proyek TitikOrder. Sebelum menulis kode apa pun:

1. Baca docs/HANDOVER.md sampai habis, lalu CLAUDE.md, lalu seluruh file di docs/.
2. Baca db/schema.sql dan packages/core/order.ts (keduanya sudah tervalidasi — jangan ditulis ulang).

Setelah itu, ringkas dalam maksimal 12 poin:
- konteks bisnis dan apa yang sedang digantikan
- arsitektur yang dipilih beserta alasannya
- aturan yang tidak boleh dilanggar
- apa yang sudah ada di repo dan sudah tervalidasi
- urutan fase S0-S5 dan apa target Fase S0
- hal yang belum diputuskan

Jangan menulis atau mengubah kode apa pun di langkah ini.
Setelah ringkasanmu saya setujui, baru kita mulai Fase S0.
```

Kalau ringkasannya meleset dari isi dokumen, **perbaiki dokumennya**, bukan lanjut bekerja. Dokumen adalah ingatan proyek ini — kalau ia salah, semua pekerjaan berikutnya ikut salah.

Prompt untuk Fase S0 dan fase-fase berikutnya ada di `SETUP_GUIDE.md` §4 dan §8.

---

## 8. Cara merawat konteks ini

Konteks akan usang kalau tidak dirawat. Aturannya:

- **Keputusan arsitektur baru** → tulis ADR di `docs/adr/`, jangan hanya diputuskan di percakapan.
- **Asumsi bisnis berubah** (harga, ekspedisi, closing rate) → perbarui dokumen terkait di commit yang sama.
- **Pelajaran mahal baru** (bug yang makan waktu berhari-hari) → tambahkan ke §3 dokumen ini.
- **Fase selesai** → perbarui §5 Status.

Satu kalimat yang layak diingat: *dokumen yang tidak diperbarui lebih berbahaya daripada tidak ada dokumen*, karena orang (dan AI) akan mempercayainya.
