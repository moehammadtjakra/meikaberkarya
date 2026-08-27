# Estimasi Biaya & Peta Aplikasi

Dua hal yang perlu diketahui pemilik bisnis sebelum membangun: **berapa biaya bulanannya**, dan **aplikasi apa saja yang akan dipakai orang**.

> Angka di bawah adalah **estimasi**, bukan penawaran. Harga Google Cloud berubah, berbeda per region, dan sangat bergantung volume. Verifikasi dengan [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator) sebelum menganggarkan. Kurs yang dipakai ±Rp 16.000/USD.

---

## BAGIAN 1 — Biaya

### Asumsi

- Region **asia-southeast2 (Jakarta)**. Singapura (asia-southeast1) biasanya 10–20% lebih murah.
- Tahap A: internal saja (bisnis Anda), ±3.000 order/bulan.
- Tahap B: trafik iklan penuh + operasional harian.
- Tahap C: gudang fulfillment jalan + melayani beberapa seller.

### Keputusan penekan biaya: Cloudflare di depan, bukan GCP Load Balancer

Ini pengungkit terbesar. GCP Load Balancer + Cloud Armor + Cloud CDN berbiaya **$50–115/bulan** hanya untuk pintu masuk. **Cloudflare** memberi fungsi setara untuk kebutuhan ini — CDN, WAF, anti-DDoS, dan custom domain — pada **$0 (Free) atau $20 (Pro)**.

Cloud Run tetap jadi origin di belakangnya. Konsekuensi teknis yang harus ditangani: tanpa LB, origin tidak bisa dibatasi per-IP, jadi **wajib** memasang *Authenticated Origin Pulls* (mTLS) atau pemeriksaan header rahasia di Cloud Run agar `*.run.app` tidak bisa diakses langsung melewati Cloudflare.

Pindah ke GCP LB nanti bila benar-benar butuh fitur GCP-native (VPC Service Controls, IAP, Cloud Armor lanjutan).

### Tahap A — Membangun & internal (target ≤ Rp 3 juta)

| Komponen | Konfigurasi | Perkiraan/bulan |
|---|---|---|
| Cloud SQL PostgreSQL | 1 vCPU / 3,75 GB, 20 GB SSD, **zonal** + PITR | $25 – 60 |
| Cloud Run (4 service) | **scale-to-zero**, trafik rendah | $5 – 15 |
| Cloud Storage + Artifact Registry | berkas, image (dengan cleanup policy) | $3 – 8 |
| Secret Manager, Scheduler, Tasks | | $2 – 5 |
| Logging & Monitoring | **dengan exclusion filter** | $3 – 10 |
| Cloudflare | Free | $0 |
| Identity Platform | gratis s/d 50.000 pengguna aktif | $0 |
| **Total** | | **±$38 – 98** → **Rp 0,6 – 1,6 juta** |

Nyaman di dalam anggaran Rp 1–3 juta, dengan ruang untuk beberapa seller pertama.

### Tahap B — Produksi sisi seller (target Rp 3–5 juta)

| Komponen | Konfigurasi | Perkiraan/bulan |
|---|---|---|
| Cloud SQL | 2 vCPU / 8 GB, **zonal** + PITR + backup | $110 – 160 |
| Cloud Run | `min-instances=1` di `seller-api` & `lp-renderer`; sisanya scale-to-zero | $35 – 60 |
| Cloudflare Pro | CDN, WAF, DDoS | $20 |
| Custom hostname seller | 100 pertama gratis, lalu $0,10/hostname | $0 – 10 |
| Cloud Storage + egress | gambar produk, berkas | $10 – 25 |
| Pub/Sub, Tasks, Scheduler | | $5 – 15 |
| Logging, Monitoring, Trace | | $10 – 25 |
| **Total** | | **±$190 – 315** → **Rp 3 – 5 juta** |

**Kompromi yang disadari: belum HA (single-zone).** Bila zona Google mengalami gangguan, layanan mati sampai dipulihkan dari PITR (perkiraan 1–4 jam). Ini keputusan bisnis, bukan kelalaian teknis — dan wajib diimbangi backup otomatis + **runbook pemulihan yang pernah diuji**.

Naikkan ke HA (+±Rp 2–3 juta/bulan) saat kerugian 1 jam downtime sudah melampaui biaya itu.

### Tahap C — + Fulfillment & analitik

| Komponen | Perkiraan/bulan |
|---|---|
| Cloud SQL kedua (fulfillment), zonal | $60 – 120 |
| 3 Cloud Run tambahan (`ff-*`), scale-to-zero saat gudang tutup | $20 – 45 |
| Pub/Sub (volume event naik) | $5 – 20 |
| BigQuery + Datastream | **tunda** sampai Postgres kewalahan | $0 (awal) |
| **Total keseluruhan** | **±$275 – 500** → **Rp 4,4 – 8 juta** |

BigQuery dan Datastream sengaja ditunda: Postgres sanggup melayani analitik sampai puluhan juta baris. Menyalakannya terlalu dini menambah ±$50–160/bulan tanpa manfaat yang terasa.

### Biaya di luar infrastruktur

| Pos | Perkiraan | Catatan |
|---|---|---|
| Domain `titikorder.com` | ±Rp 200 rb/tahun | |
| **WhatsApp Cloud API** | **Rp 2 – 6 juta/bulan** | per percakapan; **sering jadi biaya variabel terbesar** |
| Payment gateway | per transaksi (±Rp 5 rb COD / 2,9% kartu) | dibebankan ke transaksi |
| reCAPTCHA Enterprise | gratis s/d 10 rb penilaian/bulan | |
| Belanja iklan Meta | biaya bisnis, bukan infrastruktur | |

WhatsApp bisa melampaui biaya server. Mitigasi awal: pakai klik-to-chat manual dulu (gratis), baru naik ke Cloud API saat volume CS menuntut otomatisasi.

### Pengungkit penghematan (urut dari yang paling berdampak)

1. **Cloudflare menggantikan LB + Armor + CDN** — hemat ±$50–95/bulan.
2. **Zonal dulu, HA menyusul** — hemat ±Rp 2–3 juta/bulan.
3. **Tunda BigQuery/Datastream** — hemat ±$50–160/bulan.
4. **Scale-to-zero** untuk `worker` dan `ff-*` (gudang tidak 24 jam).
5. **Exclusion filter di Cloud Logging** — log yang tidak disaring diam-diam bisa jadi pos besar.
6. **Committed Use Discount** 1–3 tahun untuk Cloud SQL: hemat 25–52%. Ambil setelah beban stabil.
7. **Region Singapura** (asia-southeast1) 10–20% lebih murah dari Jakarta, bila tambahan latensi ±20 ms dapat diterima.
8. **Kredit gratis $300** untuk akun GCP baru.

### Ringkas (versi hemat)

| Tahap | Kondisi bisnis | Biaya bulanan |
|---|---|---|
| A | membangun, internal + beberapa seller | **Rp 0,6 – 1,6 juta** |
| B | produksi penuh sisi seller | **Rp 3 – 5 juta** |
| C | + fulfillment (analitik ditunda) | **Rp 4,4 – 8 juta** |

Semuanya **pay-as-you-go** — tidak ada komitmen di muka. Biaya naik mengikuti trafik, bukan mengikuti rencana.

### Kapan menaikkan kelas

| Naikkan | Saat |
|---|---|
| Cloud SQL HA | kerugian 1 jam downtime > ±Rp 3 juta/bulan |
| Ukuran instance DB | CPU rutin > 70% atau query melambat |
| GCP LB + Cloud Armor | butuh VPC-SC/IAP, atau serangan melewati Cloudflare |
| BigQuery + Datastream | query analitik > 5 detik, atau data > puluhan juta baris |
| Memorystore Redis | butuh cache/lock lintas instance |

Sebagai pembanding: satu langganan OrderOnline untuk beberapa akun biasanya jauh lebih murah di awal, tapi biayanya tetap sementara kemampuannya terbatas. Nilai platform sendiri baru terasa saat (a) Anda berhenti membayar per-seat, (b) data hulu-hilir menyatu, dan (c) Anda bisa **menjual akses ke seller lain**.

---

## BAGIAN 2 — Aplikasi dari sisi pengguna

Meski di belakang layar ada 7 service, **pengguna hanya mengenal 4 permukaan**: dua publik (tanpa login) dan dua aplikasi (dengan login).

### 1. Situs marketing — `titikorder.com`

- **Siapa**: calon seller, publik.
- **Isi**: penjelasan produk, harga langganan, daftar/hubungi.
- **Akses**: browser, tanpa login.

### 2. Landing page produk — publik

- **Siapa**: konsumen akhir yang mengeklik iklan Meta/TikTok.
- **Alamat** — **berbasis path, bukan subdomain**:
  - `lp.titikorder.com/{seller}/{slug-produk}` (bawaan), atau
  - **domain milik seller sendiri** (mis. `promosikat.com`) — per seller, bukan per LP.
- **Akses**: browser HP, tanpa login. Hanya isi form → order masuk.
- Dilayani `lp-renderer` di belakang CDN, terpisah dari sistem internal, sehingga lonjakan iklan tidak mengganggu operasional.

**Kenapa path, bukan subdomain per LP?** Jumlah LP akan sangat banyak (per SKU, per seller, per uji kreatif). Dengan path, menambah LP hanya berarti **menambah satu baris database** — tanpa DNS, tanpa sertifikat, tanpa aksi infrastruktur. Mau 10 atau 10.000 LP, biaya dan operasionalnya identik.

Dulu ada alasan kuat memisah domain: batas **8 event per domain** pada Meta Aggregated Event Measurement. Sejak **Juni 2025** Meta menghapus batas itu beserta konfigurasi AEM manual, sehingga berbagi satu domain tidak lagi merugikan pelacakan iklan.

**Domain milik seller sendiri** tetap didukung untuk kredibilitas iklan, lewat **Cloudflare for SaaS**: 100 hostname pertama gratis, selanjutnya ±$0,10/hostname/bulan.

### 3. Aplikasi Seller — `app.titikorder.com`

Satu aplikasi, tampilan menyesuaikan peran. Login lewat `id.titikorder.com`.

| Peran | Yang dilihat | Perangkat |
|---|---|---|
| Owner / admin | semua modul, dashboard, keuangan | desktop |
| Advertiser | landing page, kampanye, ROI per produk | desktop |
| CS closing | antrean lead, followup, ubah status closing | desktop / tablet |
| Monitoring | tracking paket, undel, retur | desktop |
| Finance | pencairan COD, rekonsiliasi, laba rugi | desktop |
| Gudang seller | stok, cetak label, serah ke ekspedisi | HP / desktop |

CS hanya melihat order yang **ditugaskan kepadanya** — dibatasi di server, bukan sekadar disembunyikan.

### 4. Aplikasi Gudang (WMS) — `wms.titikorder.com`

- **Siapa**: staf gudang fulfillment (mulai Fase S5).
- **Isi**: barang masuk, penempatan rak, pengambilan (picking), pengemasan, serah ke ekspedisi.
- **Akses**: **PWA** — dibuka lewat browser HP/perangkat scanner Android, bisa "install" ke layar utama. Mendukung pemindai barcode.
- Dipisah dari aplikasi seller karena penggunanya, perangkatnya, dan ritme kerjanya berbeda.

### Seller lain yang hanya menitip barang

Mereka **tidak** mendapat aplikasi baru. Mereka masuk ke `app.titikorder.com` dengan akun sendiri dan hak terbatas — melihat stok mereka di gudang Anda, status pengiriman, dan tagihan. Ini memakai mekanisme *entitlement* yang sama, jadi tidak ada basis kode tambahan.

### Peta alamat

| Alamat | Untuk siapa | Login |
|---|---|---|
| `titikorder.com` | publik, calon seller | tidak |
| `lp.titikorder.com/{seller}/{slug}` / domain seller | konsumen dari iklan | tidak |
| `app.titikorder.com` | tim seller & client fulfillment | ya |
| `wms.titikorder.com` | staf gudang | ya |
| `id.titikorder.com` | halaman masuk | — |
| `api.titikorder.com` | integrasi & aplikasi internal | token |
| `cdn.titikorder.com` | gambar & aset | tidak |
| `status.titikorder.com` | halaman status layanan | tidak |

---

## Kesimpulan untuk pengambilan keputusan

- **Biaya awal ringan** (±Rp 1,5 juta/bulan) selama membangun; naik ke ±Rp 5–8 juta saat produksi penuh, dan Rp 8–15 juta saat fulfillment jalan.
- **Pos terbesar**: Cloud SQL HA dan WhatsApp API. Keduanya bisa ditunda.
- **Pengguna hanya melihat 4 permukaan**, sehingga pelatihan tim tetap sederhana meski sistem di belakangnya besar.
- Struktur ini sudah siap dijual ke seller lain tanpa membangun ulang — cukup membuat akun dan menyalakan fitur.
