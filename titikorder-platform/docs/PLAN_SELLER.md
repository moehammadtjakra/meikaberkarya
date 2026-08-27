# Rencana — Sistem Seller (SS)

Dokumen **perencanaan**, belum kode. Fokus: sistem untuk menjalankan bisnis sebagai **seller** (hulu: iklan & landing page → closing → kirim → uang cair), yang berdiri sebagai **service terpisah** dari Sistem Fulfillment (FS).

Keputusan yang sudah disepakati:

| Pertanyaan | Keputusan |
|---|---|
| Tenancy | **Internal dulu**, arsitektur siap multi-tenant (`org_id` + RLS sejak awal). Membuka seller lain = cukup membuat akun, bukan refactor. |
| Penerbit resi | **Selalu Seller.** FS tidak pernah menerbitkan resi. |
| Titik serah ke ekspedisi | **Tergantung gudang asal**: gudang milik seller *atau* gudang fulfillment. |
| Komunikasi antar service | **REST sinkron** untuk perintah + **event async** (outbox) untuk perubahan status. |

---

## 1. Prinsip

1. **Dua service, dua database.** Tidak ada JOIN lintas service, tidak ada transaksi lintas service.
2. **Berhenti di dua service.** Di dalam SS tetap *modular monolith* dengan batas modul tegas.
3. **Satu data, satu pemilik.** Seberang hanya memegang replika/read-model.
4. **Port sebelum adapter.** SS bicara ke `FulfillmentProvider` (interface), bukan langsung ke FS.
5. **Multi-tenant-ready, bukan multi-tenant-penuh.** `org_id` + RLS ada sejak awal; billing langganan ditunda.

---

## 2. Batas kepemilikan data (REVISI)

| Data | Pemilik | Seberang mendapat |
|---|---|---|
| Produk, **SKU master**, barcode | **SS** | FS replika via event `sku.upserted` |
| Landing page, offer, harga, promo | SS | — |
| Customer, order, CRM, followup | SS | FS hanya dapat ringkasan order untuk dikemas |
| **Shipment, waybill, tracking, undel** | **SS** | FS menerima nomor resi untuk dicetak & diserahkan |
| Iklan, funnel, analitik, P&L seller | SS | — |
| Pencairan COD ekspedisi | SS | — |
| Stok di **gudang milik seller** | **SS** (modul sederhana) | — |
| Stok di **gudang fulfillment**, bin, putaway, picking | **FS** | SS dapat read-model "tersedia untuk dijual" |
| Tagihan jasa fulfillment | FS | masuk sebagai biaya di SS |

**Aturan tegas:** SS tidak pernah menulis stok fisik yang berada di gudang FS. Ia hanya membaca proyeksinya.

**Catatan sadar (trade-off):** logika stok ada di dua tempat. Mitigasinya: stok di sisi SS dibuat **sengaja sederhana** — ledger mutasi tanpa bin/putaway/picking. Semua kecanggihan gudang (rak, wave picking, kondisi barang) hanya ada di FS.

---

## 3. Urutan kritis: routing gudang mendahului resi

Karena alamat asal pada resi berbeda per gudang, urutannya **tidak boleh dibalik**:

```
order confirmed
   └─> 1. ROUTING: pilih gudang pemenuh
          (cek stok tersedia per lokasi + aturan prioritas)
   └─> 2. RESERVASI stok di gudang terpilih
   └─> 3. TERBITKAN RESI  (alamat asal = gudang terpilih)   ← SS
   └─> 4. KIRIM PERMINTAAN FULFILLMENT + nomor resi         ← ke SS-internal atau FS
   └─> 5. gudang: pick → pack → tempel label resi → handover
   └─> 6. TRACKING (SS polling ekspedisi) → delivered / undel / retur
```

Aturan routing (dapat dikonfigurasi, urutan default):
1. Gudang yang stoknya cukup untuk **seluruh** item order (hindari split shipment di awal).
2. Prioritas gudang terdekat dengan tujuan (kelak, saat data ongkir per origin sudah ada).
3. Prioritas manual per produk (mis. produk A selalu dari gudang FS).
4. Bila tak ada yang cukup → order masuk antrean `menunggu stok`, **resi belum diterbitkan**.

---

## 4. Modul di dalam Sistem Seller

| Modul | Tanggung jawab | Catatan |
|---|---|---|
| `iam` | org, user, role, audit log | fondasi multi-tenant |
| `catalog` | produk, SKU, barcode, offer/bundle/bump, pricing | **sumber kebenaran SKU** |
| `storefront` | landing page builder, CMS konten, form | disajikan aplikasi LP terpisah |
| `orders` | intake, dedup, state machine, routing gudang | jantung sistem |
| `crm` | assignment CS, followup, script, WhatsApp | antrean kerja CS |
| `inventory` | ledger stok gudang seller + read-model stok FS | sederhana, tanpa bin |
| `procurement` | permintaan pembelian, penerimaan barang | restock |
| `shipping` | terbitkan resi, export/impor ekspedisi, tracking, undel, retur | **milik SS** |
| `finance` | pencairan COD, rekonsiliasi, kas, P&L | |
| `ads` | tarik Meta Ads, pelabelan campaign→SKU, atribusi | dari MetaAds.gs |
| `analytics` | Modul 1 (planning), 3 (wilayah), 4 (produk), 5 (iklan), funnel | port dari Streamlit |
| `fulfillment-port` | interface + adapter ke gudang sendiri / FS | kunci anti-rework |

---

## 5. Alur utama yang harus dirancang tuntas

**A. Lead masuk**
`submit form LP` → validasi + normalisasi telepon → **idempotency** (anti dobel) → dedup customer → order `new` → auto-assign CS (round-robin/beban) → masuk antrean followup.

**B. Closing**
`new → contacted → closing → confirmed`. Setiap sentuhan tercatat di `crm_activities` dengan `next_action_at`. Order tanpa aktivitas > X jam masuk **daftar terlantar**. Metrik: kecepatan respons, closing rate per CS & per produk.

**C. Pemenuhan & kirim**
`confirmed` → routing gudang → reservasi → terbitkan resi → permintaan fulfillment → `packed` → `shipped`.

**D. Purna-kirim**
Polling tracking → `delivered` | `undelivered` (masuk monitoring undel, ada SLA followup) → `returned` → **stok kembali** (mutasi `inbound_return` di gudang penerima retur).

**E. Uang**
`delivered` + COD → piutang → pencairan ekspedisi (jadwal & rekonsiliasi) → kas. Selisih pencairan wajib bisa dijelaskan per resi.

**F. Iklan**
Tarik Meta harian → labeli campaign→SKU → atribusi ke lead/closing per rentang → ROI per produk → verdict scale/kill (Modul 5 yang sudah jalan).

---

## 6. Kontrak antar service (draft)

**REST (SS → FS), perintah:**

```
POST /v1/fulfillment-orders        # minta dikemas & diserahkan
     { orderRef, waybill, courier, shipTo, lines[{skuCode, qty}], priority }
GET  /v1/stock?skuCode=&ownerOrg=  # stok tersedia di gudang FS
POST /v1/inbound-notices           # pemberitahuan barang masuk (restock/retur)
```

**Event (FS → SS), perubahan status** — via outbox, konsumen idempoten:

```
fulfillment.accepted     { orderRef, warehouseId, at }
fulfillment.packed       { orderRef, at, packedBy }
fulfillment.handed_over  { orderRef, waybill, at }      → SS set shipment 'picked_up'
fulfillment.exception    { orderRef, reason }           → mis. stok fisik kurang
stock.changed            { ownerOrg, skuCode, qtyAvailable, at }
inbound.received         { skuCode, qty, condition, at }
```

**Event (SS → FS):**

```
sku.upserted             { skuCode, name, barcode, weight, dimensions }
order.cancelled          { orderRef }   → batalkan pekerjaan bila belum dikemas
```

Ketentuan: setiap event punya `event_id` + `occurred_at`; konsumen menyimpan `event_id` yang sudah diproses (dedup); pengiriman **at-least-once**, jadi konsumen **wajib idempoten**.

---

## 7. Peran & hak akses

| Role | Ruang lingkup |
|---|---|
| `owner` / `admin` | semua |
| `advertiser` | iklan, landing page, analitik iklan, lihat order |
| `cs_closing` | order (baca/ubah status closing), followup, WhatsApp |
| `monitoring` | tracking, undel, retur |
| `gudang` (gudang seller) | stok, pick/pack sederhana, cetak label |
| `finance` | pencairan, rekonsiliasi, laporan |

CS hanya melihat order yang **ditugaskan kepadanya** (kecuali supervisor) — ditegakkan di server, bukan disembunyikan di UI.

---

## 8. Fase pengerjaan

| Fase | Isi | Definisi selesai |
|---|---|---|
| **S0 — Fondasi** | IAM, org+RLS, **RBAC + matriks permission**, katalog/SKU/offer, audit, port `FulfillmentProvider` | bisa login & kelola produk; hak akses per peran sudah berlaku |
| **S1 — Migrasi operasional** | pindahkan 3 sistem Apps Script: admin order, CS undelivered, J&T (resi + pencairan), Meta Ads | **karyawan berhenti memakai Google Sheets** untuk pekerjaan harian |
| **S2 — Demand** | LP + form + intake idempoten + CRM closing | order nyata masuk & di-closing di sistem sendiri (**lepas dari OrderOnline**) |
| **S3 — Barang & uang lanjutan** | stok lanjutan, procurement, keuangan menyeluruh | stok & kas cocok dengan kenyataan |
| **S4 — Kecerdasan** | port Modul 1/3/4/5 + analisis funnel penuh | keputusan scale/kill dari sistem, bukan Excel |
| **S5 — Pisah tuntas** | adapter `TitikFulfillmentProvider`, event bus, read-model stok FS | order bisa dipenuhi gudang FS tanpa ubah kode inti |

> Urutan ini diubah oleh `adr/0002-migrasi-dulu-sebelum-demand.md`: migrasi sistem yang sudah berjalan didahulukan sebelum membangun demand. Rincian S1 ada di `PLAN_MIGRASI.md`.

Aturan: **satu fase tidak dimulai sebelum fase sebelumnya dipakai nyata** minimal 1–2 minggu.

---

## 9. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Migrasi dari OrderOnline setengah jalan | data terpecah dua tempat | jalankan **paralel** 2–4 minggu, rekonsiliasi harian, baru matikan yang lama |
| Stok sistem ≠ stok fisik | overselling, order batal | ledger append-only + opname berkala + job rekonsiliasi |
| Event hilang / dobel | status ngawur | outbox + at-least-once + konsumen idempoten + dead-letter queue |
| Resi terbit sebelum stok pasti | biaya resi hangus, order batal | reservasi stok **sebelum** terbitkan resi |
| API ekspedisi/Meta berubah | penarikan data mati | adapter terisolasi + retry backoff + alert |
| Ambisi melebihi kapasitas solo | tak ada yang selesai | disiplin fase; tolak fitur tanpa pengguna |

---

## 10. Yang masih terbuka (diputuskan sebelum S2–S3)

1. **Split shipment**: bila stok tersebar di dua gudang, boleh pecah jadi 2 resi atau tunggu? (usul: tahap awal **tidak** boleh pecah)
2. **Multi-kurir**: hanya J&T dulu, atau siapkan abstraksi kurir sejak awal? (usul: abstraksi tipis, implementasi J&T saja)
3. **WhatsApp**: manual (klik-to-chat) dulu atau langsung Cloud API? (usul: manual dulu, hemat & tanpa approval)
4. **Retur masuk ke gudang mana** bila asal kirim dari FS tapi seller punya gudang sendiri?
5. **Harga & promo**: apakah butuh versi/jadwal (harga berlaku mulai tanggal)?

---

## 11. Rencana berikutnya

Setelah rencana ini disepakati:
1. Rancang **Sistem Fulfillment (FS)** dengan cara yang sama.
2. Tetapkan kontrak event final (skema versioned) di `packages/contracts`.
3. Pecah `db/schema.sql` menjadi `db/seller/` dan `db/fulfillment/`.
4. Mulai **S0**.
