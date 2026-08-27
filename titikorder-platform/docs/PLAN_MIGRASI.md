# Fase S1 — Migrasi 3 Sistem Apps Script

Rencana rinci memindahkan operasional harian dari Apps Script + Google Sheets ke web app baru. Keputusan mengapa ini didahulukan: `adr/0002-migrasi-dulu-sebelum-demand.md`.

**Target akhir S1:** karyawan berhenti membuka Google Sheets untuk pekerjaan harian; semuanya lewat satu aplikasi dengan hak akses & audit yang benar.

**Yang BELUM berubah di S1:** order masih lahir di OrderOnline. Aplikasi ini berperan *impor → olah → ekspor*, sama seperti Apps Script. Lepas dari OrderOnline baru terjadi di S2.

---

## 1. Lingkup per sistem

### A. Admin Order (dari `Admin_Order_System`)

| Kemampuan | Modul | Catatan penting |
|---|---|---|
| Impor order OrderOnline (xlsx/csv) | `orders` | idempoten by `order_id`; format berkas **tidak boleh berubah** dari yang dipakai sekarang |
| Normalisasi wilayah & pemetaan produk→SKU | `catalog` | resolusi berlapis — lihat `HANDOVER.md` §3 poin 2 |
| Cek & alokasi stok (FIFO per wilayah) | `inventory` | tulis `stock_movements`, jangan UPDATE saldo |
| HPP moving average | `inventory` | port dari `Stok.gs` |
| Buat batch upload J&T | `shipping` | keluaran = berkas format J&T, lewat `CourierAdapter.exportOrders()` |
| Impor balik nomor resi | `shipping` | `CourierAdapter.importWaybills()` |
| Handover harian + dokumen pickup | `shipping` | cetak PDF |

### B. CS Undelivered (dari `CS_Undelivered_System`)

| Kemampuan | Modul | Catatan penting |
|---|---|---|
| Unggah data paket gagal antar | `shipping` | upsert by waybill; snapshot per bulan kirim |
| Distribusi otomatis ke CS per provinsi | `shipping` | tabel pemetaan provinsi→CS |
| Worklist CS + catat hasil followup | `shipping` | **CS hanya melihat provinsi miliknya** — ditegakkan di server |
| Unggah foto POD | `shipping` | simpan ke storage, bukan ke DB |
| Arsip otomatis baris yang hilang dari unggahan terbaru | `shipping` | jangan anggap penyusutan baris sebagai kehilangan data |
| Laporan performa CS | `analytics` | read-only untuk supervisor |

### C. J&T + Pencairan + Meta Ads (dari `JnT_GSheet_System` & `MetaAds.gs`)

| Kemampuan | Modul | Catatan penting |
|---|---|---|
| Unggah export **All Resi** | `shipping` | upsert by `No. Waybill`, abaikan spasi & `.0` di akhir |
| Unggah export **Settle Reconcile** | `finance` | dukung **dua format** (11 kolom lama & 7 kolom baru) |
| Status pengiriman & proyeksi pencairan | `finance` | port logika `Dashboard.gs` + `settlement_engine.py` |
| Rekonsiliasi: resi terkirim vs dana cair | `finance` | selisih wajib bisa dijelaskan per resi |
| Tarik Meta Ads harian | `ads` | `AdPlatformAdapter`; **satu purchase kanonik**, jangan jumlahkan alias |
| Pelabelan campaign → SKU (memory) | `ads` | port `Ref_Ads_Map`: sekali dikunci, diingat selamanya |
| Analisis iklan (Modul 5) | `analytics` | verdict berbasis **ROI**, bukan ROAS |

---

## 2. Urutan pengerjaan di dalam S1

Kerjakan per sistem sampai **benar-benar dipakai**, jangan paralel:

| Langkah | Isi | Selesai bila |
|---|---|---|
| **S1.1** | Impor All Resi + Settle Reconcile → dashboard pencairan | finance berhenti buka GSheet untuk cek pencairan |
| **S1.2** | Impor order + stok + HPP + export/impor J&T + handover | admin order berhenti buka GSheet |
| **S1.3** | Undelivered: unggah, distribusi, worklist CS, POD | CS & supervisor berhenti buka GSheet |
| **S1.4** | Meta Ads: tarik, pelabelan, analisis | advertiser berhenti buka GSheet/Streamlit |

S1.1 didahulukan karena **paling sedikit ketergantungannya** (cukup dua berkas export) sekaligus langsung menjawab pertanyaan bisnis paling mahal: uang saya di mana.

---

## 3. Menjalankan berdampingan dengan sistem lama

1. Selama migrasi, **Apps Script tetap hidup**. Web app dianggap pembanding.
2. Setiap hari, **rekonsiliasi**: jumlah baris, total nilai COD, jumlah resi, saldo stok. Selisih harus nol atau bisa dijelaskan.
3. Setelah **2–4 minggu** cocok terus, matikan modul lama — **per modul**, bukan sekaligus.
4. Tetapkan **satu sumber kebenaran per modul** sejak hari pertama migrasi modul itu, supaya tidak ada dua tempat yang sama-sama diedit.

---

## 4. Manajemen user, role & matriks permission

Wajib selesai di **S0**, karena S1 langsung melibatkan banyak peran.

### Peran

| Role | Siapa | Ruang lingkup |
|---|---|---|
| `owner` | pemilik | semua |
| `admin` | manajer operasional | semua kecuali kelola billing |
| `admin_order` | admin order | impor order, alokasi stok, batch J&T, handover |
| `gudang` | staf gudang | stok, cetak label, handover |
| `cs_undel` | CS | worklist undel **provinsi sendiri**, followup, POD |
| `spv_cs` | supervisor CS | unggah & distribusi undel, lihat semua CS, laporan |
| `finance` | keuangan | pencairan, rekonsiliasi, laporan keuangan |
| `advertiser` | tim iklan | tarik & labeli campaign, analisis iklan |
| `viewer` | manajemen | hanya melihat laporan |

### Matriks permission

`✔` = boleh · `—` = tidak · `◐` = terbatas pada data miliknya

| Permission | owner | admin | admin_order | gudang | cs_undel | spv_cs | finance | advertiser | viewer |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `iam.manage` | ✔ | ✔ | — | — | — | — | — | — | — |
| `catalog.read` | ✔ | ✔ | ✔ | ✔ | — | — | ✔ | ✔ | ✔ |
| `catalog.write` | ✔ | ✔ | ✔ | — | — | — | — | — | — |
| `orders.read` | ✔ | ✔ | ✔ | ✔ | ◐ | ✔ | ✔ | ✔ | ✔ |
| `orders.import` | ✔ | ✔ | ✔ | — | — | — | — | — | — |
| `orders.allocate` | ✔ | ✔ | ✔ | — | — | — | — | — | — |
| `shipping.export` | ✔ | ✔ | ✔ | ✔ | — | — | — | — | — |
| `shipping.import_waybill` | ✔ | ✔ | ✔ | — | — | — | — | — | — |
| `shipping.handover` | ✔ | ✔ | ✔ | ✔ | — | — | — | — | — |
| `undel.read` | ✔ | ✔ | ✔ | — | ◐ | ✔ | — | — | ✔ |
| `undel.assign` | ✔ | ✔ | — | — | — | ✔ | — | — | — |
| `undel.followup` | ✔ | ✔ | — | — | ◐ | ✔ | — | — | — |
| `undel.upload_pod` | ✔ | ✔ | — | — | ◐ | ✔ | — | — | — |
| `inventory.read` | ✔ | ✔ | ✔ | ✔ | — | — | ✔ | — | ✔ |
| `inventory.move` | ✔ | ✔ | ✔ | ✔ | — | — | — | — | — |
| `inventory.adjust` | ✔ | ✔ | — | — | — | — | — | — | — |
| `purchase.request` | ✔ | ✔ | ✔ | ✔ | — | — | — | — | — |
| `purchase.approve` | ✔ | ✔ | — | — | — | — | ✔ | — | — |
| `finance.read` | ✔ | ✔ | — | — | — | — | ✔ | — | ✔ |
| `finance.reconcile` | ✔ | ✔ | — | — | — | — | ✔ | — | — |
| `ads.read` | ✔ | ✔ | — | — | — | — | ✔ | ✔ | ✔ |
| `ads.manage` | ✔ | ✔ | — | — | — | — | — | ✔ | — |
| `analytics.read` | ✔ | ✔ | ✔ | — | — | ✔ | ✔ | ✔ | ✔ |
| `audit.read` | ✔ | ✔ | — | — | — | — | ✔ | — | — |

### Pembatasan data (bukan sekadar menu disembunyikan)

Tanda `◐` berarti pembatasan **baris**, bukan tombol:

- `cs_undel` hanya melihat paket undel pada **provinsi yang ditugaskan kepadanya** (tabel `cs_province_map`).
- `cs_undel` hanya melihat order yang berkaitan dengan paket tersebut.
- Ditegakkan di **query sisi server** + kebijakan RLS, bukan dengan menyembunyikan elemen UI.

Aturan wajib: **setiap endpoint memeriksa permission di server.** Menyembunyikan menu di frontend hanyalah kenyamanan, bukan keamanan.

### Halaman pengelolaan

| Halaman | Isi |
|---|---|
| Pengguna | undang, nonaktifkan, atur ulang kata sandi, tetapkan role |
| Role | daftar role + centang permission (matriks di atas, dapat disunting) |
| Pemetaan CS–Provinsi | siapa memegang provinsi mana |
| Log audit | siapa mengubah apa, kapan (read-only, immutable) |

---

## 5. Definisi selesai untuk S1

- [ ] Semua peran bisa login dan **hanya** melihat yang menjadi haknya
- [ ] Impor All Resi & Settle Reconcile jalan, dashboard pencairan cocok dengan GSheet
- [ ] Impor order → alokasi stok → export J&T → impor resi → handover berjalan penuh
- [ ] CS mengerjakan worklist undel di web app, POD tersimpan
- [ ] Meta Ads tertarik otomatis, verdict per produk tampil
- [ ] Rekonsiliasi harian cocok selama 2 minggu berturut-turut
- [ ] Log audit terisi untuk aksi sensitif
- [ ] Sistem Apps Script lama dimatikan modul per modul

---

## 6. Yang sengaja TIDAK dikerjakan di S1

Landing page builder · form intake publik · CRM followup closing · WhatsApp otomatis · fitur fulfillment/WMS · pembuatan resi langsung dari sistem (masih lewat export/import seperti sekarang).

Semua itu masuk S2 ke atas. Menahan diri di sini adalah yang membuat S1 selesai tepat waktu.
