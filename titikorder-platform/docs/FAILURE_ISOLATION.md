# Kalau Terjadi Error — Apa yang Ikut Mati, Apa yang Tetap Jalan

Dokumen ini menjawab: **kalau satu bagian rusak, apakah bagian lain ikut kena?**

Jawaban singkatnya: **sebagian besar tidak menular** — itulah gunanya memisah service dan database. Tapi ada beberapa titik yang **memang menular**, dan Anda harus tahu persis yang mana supaya bisa memutuskan mana yang perlu dibayar mahal untuk diamankan.

---

## 1. Yang TIDAK menular (terisolasi)

| Yang rusak | Yang ikut mati | Yang tetap jalan |
|---|---|---|
| Bug kode di `ff-api` | fitur gudang | **seluruh sisi seller normal** |
| `ff-api` crash / kehabisan memori | instance itu (Cloud Run otomatis mengganti) | semua service lain |
| **Database fulfillment** mati | operasi gudang | seller tetap terima order, closing, terbitkan resi |
| Deploy buruk di `seller-web` | back-office (10% pengguna saat canary) | `lp-renderer` tetap terima order dari iklan |
| Lonjakan trafik iklan di `lp-renderer` | — (autoscale sendiri) | back-office tidak melambat |
| `seller-worker` mati | job latar tertunda | web & API tetap melayani; job menyusul saat hidup lagi |
| Token Meta kedaluwarsa | tarik data iklan | seluruh operasional lain |
| API J&T mati | export/tracking tertunda | order & closing tetap jalan |

**Kenapa terisolasi:** tiap service adalah proses terpisah di Cloud Run dengan instance, memori, dan penskalaan sendiri. Kehabisan memori di satu service tidak mengambil jatah service lain. Database terpisah berarti kegagalan data di satu domain tidak menyentuh domain lain.

---

## 2. Bahaya utama: kegagalan berantai dari panggilan sinkron

Ini risiko paling nyata dan paling sering menjatuhkan sistem terdistribusi.

**Skenario:** `seller-api` memanggil `ff-api` untuk minta barang dikemas. `ff-api` mati atau lambat.

- **Tanpa pengaman:** permintaan menggantung menunggu jawaban. Koneksi menumpuk. Kapasitas `seller-api` habis dipakai menunggu. **Akhirnya sisi seller ikut mati** — padahal yang rusak cuma gudang.
- **Dengan pengaman:** panggilan dibatasi waktu, gagal cepat, order tetap tersimpan dengan status `menunggu fulfillment`, lalu dicoba lagi otomatis.

**Mitigasi wajib** (jangan dianggap opsional):

1. **Timeout pendek** (mis. 3 detik) pada setiap panggilan antar service.
2. **Circuit breaker** — setelah beberapa kegagalan beruntun, berhenti memanggil sementara, jangan terus menghantam service yang sedang sekarat.
3. **Fallback yang bermakna** — order **tetap tersimpan**; permintaan fulfillment masuk antrean.
4. **Jangan panggil service lain di dalam transaksi database.** Transaksi harus selesai dulu, panggilan menyusul.

**Aturan emas:** perintah lewat REST **dengan timeout**, status lewat **event Pub/Sub**. Kalau `ff-worker` mati, event menumpuk di antrean dan diproses saat ia hidup lagi — tidak ada yang hilang, tidak ada yang menular.

---

## 3. Yang MEMANG menular (titik gagal bersama)

Jujur soal ini penting, karena inilah yang menentukan keputusan anggaran Anda.

| Yang rusak | Dampak | Status sekarang | Mitigasi |
|---|---|---|---|
| **Cloud SQL seller** | seluruh sisi seller mati (LP, web, API, worker) | **zonal (belum HA)** demi anggaran | PITR + runbook pemulihan; naikkan ke HA saat mampu |
| **Migrasi DB yang salah** | bisa menjatuhkan semua service seller sekaligus | risiko tertinggi dalam praktik | migrasi expand→contract, dites di dev, dijalankan sebagai job terpisah |
| **Bug di `packages/core` / `contracts`** | menyebar ke semua service yang memakainya | kode memang dibagi | 19 tes domain wajib hijau; perubahan core memicu CI semua service |
| **Cloudflare** | semua domain tak bisa diakses | jarang, tapi pernah terjadi | terima risikonya; alternatifnya (LB GCP) menambah biaya |
| **Region GCP mati** | seluruh sistem mati | multi-region terlalu mahal sekarang | terima risikonya di tahap ini |
| **Identity Platform** | login gagal di semua aplikasi | terkelola Google | LP publik **tetap jalan** (tanpa login) — order tetap masuk |
| **Billing/kuota GCP habis** | semua mati | kelalaian administratif | pasang **budget alert** + kartu cadangan |

**Yang paling perlu Anda sadari:** karena Cloud SQL masih zonal (pilihan sadar demi menekan biaya ke Rp 3–5 juta), kegagalan zona berarti sisi seller mati sampai dipulihkan — perkiraan 1–4 jam. Ini bukan kelemahan desain, melainkan **keputusan bisnis** yang bisa dibalik kapan saja dengan menyalakan HA.

---

## 4. Mode terdegradasi — yang penting tetap hidup

Sistem dirancang supaya **kehilangan sebagian fungsi, bukan mati total**:

| Yang mati | Yang MASIH bisa dilakukan |
|---|---|
| Gudang / fulfillment | terima lead, followup, closing, terbitkan resi, kirim dari gudang sendiri |
| Integrasi J&T | terima & closing order; export menyusul saat pulih |
| Meta Ads | seluruh operasional; hanya laporan iklan tertunda |
| Back-office (`seller-web`) | **landing page tetap menerima order** — iklan tidak terbuang |
| WhatsApp API | closing manual lewat telepon/WA biasa |

Prioritas tertinggi: **jangan sampai order dari iklan hilang.** Karena itu `lp-renderer` sengaja dibuat paling sederhana dan paling terpisah — ia hanya perlu menulis satu baris order, tidak bergantung pada gudang, iklan, atau back-office.

---

## 5. Pertahanan berlapis yang sudah terpasang

| Lapis | Melindungi dari |
|---|---|
| **Idempotency key** | order dobel saat retry/jaringan putus |
| **Ledger append-only** | stok/uang rusak karena update salah |
| **RLS di database** | kebocoran data antar seller walau ada bug di kode |
| **State machine** | status order melompat tidak masuk akal |
| **Canary 10%** | deploy buruk hanya mengenai sebagian kecil pengguna |
| **Dead-letter queue** | event gagal hilang diam-diam |
| **PITR** | kehilangan data karena kesalahan manusia |

---

## 6. Yang harus disiapkan sebelum produksi

1. **Runbook pemulihan** — langkah restore Cloud SQL dari PITR, **pernah diuji**, bukan sekadar ditulis.
2. **Alert** untuk: error rate naik, latensi p95 naik, antrean dead-letter bertambah, budget mendekati batas.
3. **Halaman status** (`status.titikorder.com`) supaya tim tahu tanpa menebak.
4. **Latihan rollback** — coba kembalikan trafik ke revisi lama sekali di dev, supaya saat panik Anda sudah hafal.

---

## Ringkas

- Bug atau matinya **satu service** hampir tidak pernah menjatuhkan yang lain — itu hasil dari pemisahan service + database.
- Yang benar-benar bisa menular ada tiga: **panggilan sinkron tanpa timeout**, **database bersama per domain**, dan **migrasi yang salah**. Ketiganya bisa dikendalikan dengan disiplin, bukan dengan uang.
- Sisanya (region, Cloudflare, HA) adalah **keputusan anggaran** — sadar diambil, dan bisa dinaikkan kapan pun bisnis menuntut.
