# TitikOrder — Blueprint Arsitektur

Platform social commerce hulu-ke-hilir: **sisi seller** (landing page, iklan, CRM closing, stok, keuangan) dan **sisi fulfillment** (inbound, inventory, picking, packing, outbound, tagihan client).

Dokumen ini adalah acuan tunggal untuk membangun. Konteks: **dikerjakan solo + AI**, target menggantikan ketergantungan pada OrderOnline lalu tumbuh jadi agregator.

---

## 1. Prinsip arsitektur (jangan dilanggar)

1. **Beberapa service berbatas domain — bukan microservices.** Dua domain bisnis (Seller, Fulfillment), masing-masing dipecah jadi `web` + `api` + `worker`. **Di dalam tiap service tetap modular monolith** dengan modul berbatas tegas. Jangan memecah lebih jauh: setiap service tambahan mengalikan beban operasional.
2. **Multi-tenant sejak baris pertama.** Semua tabel bisnis punya `org_id` + Row-Level Security di Postgres.
3. **Ledger, bukan angka yang di-UPDATE.** Stok & uang disimpan sebagai mutasi append-only. Saldo = agregat.
4. **Landing page terpisah dari back-office.** Trafik iklan tidak boleh menjatuhkan operasional gudang.
5. **Idempotent by default.** Semua impor, webhook, dan submit form pakai idempotency key.
6. **State machine eksplisit.** Order & shipment punya transisi sah yang ditegakkan, bukan kolom status bebas.

---

## 2. Stack final (dioptimalkan untuk solo + AI)

Kriteria: bagian bergerak sesedikit mungkin, dukungan AI codegen maksimal, dan Anda sudah menulis JavaScript (Apps Script) sehingga TypeScript adalah lanjutan alami.

> **Diperbarui:** target deploy adalah **Google Cloud** dengan service terpisah. Rincian infrastruktur ada di **[INFRA_GCP.md](INFRA_GCP.md)** — dokumen itu yang berlaku bila ada perbedaan.

| Lapis | Pilihan | Catatan |
|---|---|---|
| Bahasa | **TypeScript** end-to-end | satu bahasa untuk LP, web, API, worker |
| Frontend | **Next.js 15 (App Router)** + shadcn/ui + Tailwind | `lp-renderer`, `seller-web`, `ff-web` |
| Backend | **NestJS 11** (Fastify) + Prisma + Zod | `seller-api`, `ff-api` — logika bisnis hanya di sini |
| Worker | NestJS standalone, konsumsi **Pub/Sub push** | satu basis kode dengan API |
| Kontrak | **OpenAPI** (dari NestJS) + skema event ber-versi | antar service |
| Database | **Cloud SQL for PostgreSQL** | RLS, ledger, private IP |
| Runtime | **Cloud Run** | bukan GKE — beban operasional jauh lebih ringan |
| Event | **Pub/Sub** (+ dead-letter) | status antar domain |
| Job terjadwal | **Cloud Scheduler** + **Cloud Tasks** | tarik Meta, polling tracking |
| Auth | **Identity Platform** | custom claims org + role |
| Analitik | **BigQuery** ← Datastream (CDC) | laporan berat tidak membebani OLTP |
| Observability | Cloud Logging/Monitoring/Trace + Error Reporting | SLO + alert |

**Kenapa bukan Laravel + Filament?** Filament unggul untuk panel admin cepat, tapi Anda butuh landing page berperforma iklan (native di Next.js), dan AI codegen paling kuat di TS/Next. Satu bahasa juga menurunkan beban kognitif solo.

**Kenapa bukan microservices/Kubernetes?** Tidak ada masalah yang mereka pecahkan di tahap ini, dan keduanya menambah biaya operasional besar untuk satu orang.

---

## 3. Model multi-tenant (fondasi)

```
Organization (tenant)
  type: seller | fulfiller | both
  └─ Membership → User + Role (scoped per org)

FulfillmentAgreement
  seller_org_id  ──┐
  fulfiller_org_id ─┴─→ syarat biaya, SLA, status
```

- Anda = org pertama dengan `type = both`.
- Seller lain masuk sebagai org terpisah, terhubung ke org fulfillment Anda lewat *agreement*.
- **Isolasi data ditegakkan di database** (RLS pakai `app.current_org`), bukan hanya di kode aplikasi. Bug di query tidak bisa membocorkan data seller lain.
- Data gudang (lokasi, bin) milik org fulfiller; **stok milik seller** tapi *berada di* lokasi fulfiller → `stock_movements` menyimpan `owner_org_id` dan `location_id` sekaligus.

### RBAC

Role berbasis **permission**, bukan hard-code nama role:

| Role | Ruang lingkup utama |
|---|---|
| `owner` / `admin` | semua dalam org |
| `advertiser` | kampanye, analitik iklan, landing page |
| `cs_closing` | order, followup, ubah status closing |
| `monitoring` | tracking, undel, retur (read + update status) |
| `gudang` | inbound, putaway, picking, packing, outbound |
| `finance` | pencairan, tagihan, laporan keuangan |
| `client_seller` | (di sisi fulfiller) hanya melihat data org-nya sendiri |

Permission disimpan di DB (`role_permissions`), dicek di server pada setiap aksi.

---

## 4. Peta modul

```
apps/
  lp-renderer/   Landing page publik + endpoint submit form        (Next.js)
  seller-web/    Back-office seller                                 (Next.js)
  seller-api/    API domain seller — logika bisnis                  (NestJS)
  seller-worker/ Job: tarik Meta, polling tracking, parse pencairan (NestJS)
  ff-web/        UI gudang (PWA scanner)          — mulai S5        (Next.js)
  ff-api/        API domain fulfillment           — mulai S5        (NestJS)
  ff-worker/     Job gudang & rekonsiliasi        — mulai S5        (NestJS)

packages/
  db/            Prisma schema + migrasi + seed
  core/          Domain logic murni (state machine, ledger, pricing) — tanpa I/O
  contracts/     Skema Zod + tipe event ber-versi
  integrations/  Adapter courier & ads
  ui/            Komponen bersama
```

Struktur folder rinci: lihat `STRUCTURE.md`. Peta service & GCP: lihat `INFRA_GCP.md`.

Modul domain di dalam `seller-api`:

| Modul | Isi |
|---|---|
| `catalog` | produk, SKU, varian, bundling/bump, pricing |
| `landing` | builder halaman, form, CMS konten |
| `orders` | intake, state machine, dedup, alamat |
| `crm` | followup, script closing, aktivitas, WhatsApp |
| `shipping` | export ekspedisi, resi, tracking, undel/retur |
| `inventory` | ledger stok, req pembelian, opname |
| `finance` | pencairan ekspedisi, COD settlement, rekonsiliasi |
| `ads` | Meta Ads pull, atribusi, analitik funnel |
| `analytics` | planning/targeting (Modul 1), wilayah (3), produk (4), iklan (5) |
| `iam` | org, user, role, audit log |

---

## 5. Data integrity — mekanisme konkret

**a. Stock ledger (append-only).** Tidak ada kolom `stok` yang di-UPDATE.

```
stock_movements(id, org_id, owner_org_id, sku_id, location_id,
                qty_delta, type, ref_type, ref_id, created_by, created_at)
```
Saldo = `SUM(qty_delta)`, dipercepat oleh snapshot harian / materialized view. Setiap unit bisa ditelusuri asalnya (inbound baru vs retur).

**b. Uang juga ledger.** `ledger_entries` bergaya double-entry untuk COD, pencairan ekspedisi, biaya fulfillment, dan tagihan client — sehingga selisih selalu bisa dijelaskan.

**c. Idempotency.** Tabel `idempotency_keys`; setiap submit form/webhook/import membawa kunci. Retry tidak pernah menggandakan order atau mutasi stok.

**d. State machine.** Transisi order & shipment divalidasi di `packages/core` dan dijaga constraint DB. Contoh order: `new → contacted → closing → confirmed → packed → shipped → delivered | returned | cancelled`.

**e. Concurrency gudang.** Reservasi stok saat picking + optimistic locking (kolom `version`), supaya dua picker tidak mengambil unit yang sama.

**f. Audit log immutable** untuk aksi sensitif (ubah harga, adjust stok, ubah status pembayaran).

**g. Job rekonsiliasi harian:** stok fisik vs ledger, resi terkirim vs settlement ekspedisi, purchase Meta vs lead masuk.

---

## 6. Availability & reliability

- **Pisahkan LP dari app.** LP di edge/CDN dengan ISR; submit order menulis ke endpoint ringan + antre. Gudang tetap jalan saat trafik iklan melonjak.
- **App stateless** → mudah discale horizontal; semua state di Postgres/Storage.
- **Backup**: PITR aktif + **restore test terjadwal**. Backup yang tidak pernah diuji = tidak ada backup.
- **Staging environment** wajib, dengan migrasi otomatis.
- **Observability**: Cloud Error Reporting + Cloud Logging (log terstruktur) + Cloud Trace, SLO & alert di Cloud Monitoring.
- **Graceful degradation**: jika API ekspedisi/Meta mati, job masuk antrean retry dengan backoff — bukan menggagalkan transaksi user.

---

## 7. Buy vs build (jangan bangun sendiri)

| Kebutuhan | Pakai |
|---|---|
| Payment gateway / tagihan | **Xendit** atau **Midtrans** |
| WhatsApp | **Meta WhatsApp Cloud API** via BSP resmi (hindari unofficial) |
| Auth | **Identity Platform** (GCP) |
| Penyimpanan berkas | **Cloud Storage** |
| Multi-kurir (opsional) | Biteship / Shipper; atau API resmi J&T bila sudah ada |
| Error tracking | Sentry |
| Email transaksional | Resend |

**PDF resi multi-format client:** jangan mulai dari ML. Buat **template registry**:
`pdf_templates(client_org_id, matcher_regex, field_rules jsonb)` → parse rule-based → hitung **confidence** → yang gagal masuk **antrean review manusia**. ML hanya jika volume sudah besar.

---

## 8. Roadmap bertahap

Membangun semuanya sekaligus adalah cara tercepat untuk gagal. Setiap fase harus **dipakai nyata** sebelum lanjut.

> **Sumber kebenaran fase: `PLAN_SELLER.md` §8.** Tabel di bawah adalah salinannya. Bila suatu saat berbeda, `PLAN_SELLER.md` yang berlaku.

### Sistem Seller (S0–S5)

| Fase | Isi | Definisi selesai |
|---|---|---|
| **S0 — Fondasi** | IAM, org+RLS, **RBAC + matriks permission**, katalog/SKU/offer, audit, port `FulfillmentProvider` | bisa login & kelola produk; hak akses per peran sudah berlaku |
| **S1 — Migrasi operasional** | pindahkan 3 sistem Apps Script: admin order, CS undelivered, J&T (resi + pencairan), Meta Ads | **karyawan berhenti memakai Google Sheets** untuk pekerjaan harian |
| **S2 — Demand** | LP + form + intake idempoten + CRM closing | order nyata masuk & di-closing di sistem sendiri (**lepas dari OrderOnline**) |
| **S3 — Barang & uang lanjutan** | stok lanjutan, procurement, keuangan menyeluruh | stok & kas cocok dengan kenyataan |
| **S4 — Kecerdasan** | port Modul 1/3/4/5 + analisis funnel penuh | keputusan scale/kill dari sistem, bukan Excel |
| **S5 — Pisah tuntas** | adapter `TitikFulfillmentProvider`, event bus, read-model stok FS | order bisa dipenuhi gudang FS tanpa ubah kode inti |

> Urutan ini diubah oleh `adr/0002-migrasi-dulu-sebelum-demand.md`: migrasi sistem yang sudah berjalan didahulukan sebelum membangun demand. Rincian S1 ada di `PLAN_MIGRASI.md`.

### Sistem Fulfillment (F0–Fn) — direncanakan terpisah

WMS penuh (inbound, putaway, picking, packing, outbound, barcode) dan fulfillment-as-a-service (manajemen client, tagihan + payment gateway, parsing PDF resi) adalah **lingkup Sistem Fulfillment**, bukan fase Sistem Seller. Rencananya disusun tersendiri setelah S1–S2 berjalan nyata, dengan cara yang sama seperti `PLAN_SELLER.md`.

**Jembatan penting:** dashboard Streamlit Anda (Modul 1–5) **tidak perlu dibuang**. Begitu Postgres hidup, ganti `data_loader` dari GSheet → Postgres; seluruh engine (`cashflow_engine`, `meta_engine`, `product_admin`, …) tetap jalan. Port ke web menyusul di **S4**. Ini menyelamatkan berbulan-bulan kerja yang sudah ada.

---

## 9. Catatan realistis soal skala

Scope penuh dokumen ini setara pekerjaan tim 8–15 engineer selama 1,5–2 tahun. Sebagai solo + AI, itu bukan alasan menurunkan ambisi, tapi alasan untuk:

- **Menyelesaikan Fase 1 sampai benar-benar dipakai** sebelum menyentuh WMS.
- Menolak fitur yang belum ada penggunanya (YAGNI).
- Memakai layanan jadi untuk apa pun yang bukan keunggulan kompetitif Anda.
- Menjaga `packages/core` bebas I/O supaya logika bisnis bisa diuji cepat tanpa DB.

Keunggulan kompetitif Anda bukan pada auth/payment/kurir — tapi pada **integrasi hulu-hilir berbasis data**: dari iklan → lead → closing → kirim → retur → uang cair, dalam satu sistem. Fokuskan energi di sana.
