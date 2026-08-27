# Rencana Pemisahan Skema — Seller DB vs Fulfillment DB

`db/schema.sql` yang sudah tervalidasi dirancang saat masih satu sistem. Dengan keputusan **dua service, dua database**, berikut pembagiannya. Dokumen ini adalah acuan sebelum memecah file.

Legenda: **SS** = Seller System · **FS** = Fulfillment System · **replika** = salinan read-only yang disinkronkan lewat event.

---

## Tetap di Seller DB (36 → 30 tabel)

| Tabel | Catatan |
|---|---|
| `organizations`, `users`, `roles`, `permissions`, `role_permissions`, `memberships` | **Diduplikasi di kedua DB.** Identitas dibagi lewat provider auth yang sama (Identity Platform), tapi tiap service punya tabel org/role sendiri. |
| `audit_logs`, `idempotency_keys` | tiap service punya sendiri |
| `products`, `skus`, `offers`, `offer_items` | **SS pemilik SKU master** |
| `landing_pages` | |
| `customers`, `orders`, `order_items`, `order_status_history` | |
| `crm_activities` | |
| `couriers`, `shipments`, `tracking_events` | **resi milik SS** (sesuai keputusan) |
| `export_batches`, `export_batch_items` | export ke ekspedisi dilakukan SS |
| `purchase_requests`, `purchase_request_items` | pengadaan milik seller |
| `settlements`, `ledger_accounts`, `ledger_entries` | keuangan seller |
| `ad_daily_stats`, `ad_campaign_map` | iklan |
| `warehouses`, `locations` | **hanya gudang milik seller** (tanpa bin detail) |
| `stock_movements`, `stock_balances`, `stock_reservations` | **hanya stok di gudang seller** |

## Pindah / diduplikasi ke Fulfillment DB

| Tabel | Di FS menjadi |
|---|---|
| `warehouses`, `locations` | gudang & **bin lengkap** milik fulfiller |
| `stock_movements`, `stock_balances`, `stock_reservations` | ledger stok fisik di gudang FS (lengkap: putaway, pick, pack) |
| `fulfillment_agreements` | **pindah ke FS** — FS yang mengelola relasi dengan client seller |
| `skus` | **replika** dari SS (`sku_code`, nama, barcode, berat, dimensi) |

## Tabel baru yang hanya ada di FS (dirancang di rencana FS)

`inbound_notices`, `inbound_receipts` (klasifikasi SKU/qty/kondisi), `putaway_tasks`, `pick_tasks`, `pack_tasks`, `outbound_handovers`, `fulfillment_orders`, `billing_invoices`, `pdf_templates`.

## Tabel baru yang perlu ditambahkan di SS

| Tabel | Guna |
|---|---|
| `outbox_events` | pola outbox: tulis event dalam transaksi yang sama, dikirim worker |
| `inbox_events` | dedup event masuk (`event_id` sudah diproses) |
| `fulfillment_locations` | daftar gudang pemenuh (milik sendiri **atau** milik FS) + prioritas routing |
| `stock_snapshot_external` | read-model stok di gudang FS (hasil event `stock.changed`) |
| `fulfillment_orders` | jejak permintaan fulfillment yang dikirim ke gudang/FS + statusnya |

---

## Perubahan penting pada tabel yang ada

1. **`shipments`** — tambah `origin_warehouse_ref` (gudang asal, menentukan alamat pengirim di resi) dan `fulfilled_by` (`self` | `fulfiller`). Ini konsekuensi langsung dari "titik serah tergantung gudang asal".

2. **`orders`** — tambah `fulfillment_location_ref` (hasil routing) dan `fulfillment_status` (terpisah dari `status` order, karena pekerjaan gudang punya siklus sendiri).

3. **`stock_movements` di SS** — `location_id` cukup merujuk gudang seller. Stok di FS **tidak** ditulis ke sini; ia hidup di `stock_snapshot_external`.

4. **`fulfillment_agreements`** — hapus dari Seller DB, pindah ke FS.

---

## Yang TIDAK berubah

Seluruh mekanisme integritas yang sudah lulus uji tetap berlaku **di kedua database**:

- RLS `org_id` + role `app_user` (non-superuser)
- `stock_movements` / `ledger_entries` / `audit_logs` append-only
- state machine order (SS) — FS akan punya state machine sendiri untuk pekerjaan gudang
- `idempotency_keys`

---

## Urutan eksekusi saat memecah

1. Salin `schema.sql` → `db/seller/schema.sql`, buang tabel milik FS, tambah tabel baru SS.
2. Buat `db/fulfillment/schema.sql` (setelah rencana FS disepakati).
3. Jalankan `test_schema.py` untuk **masing-masing** DB.
4. Tambah uji baru: outbox/inbox idempoten, dan routing gudang.

> Catatan: selama **S0–S4**, SS berjalan sendiri memakai gudang seller. Pemecahan DB fulfillment baru benar-benar dibutuhkan di **S5**. Namun tabel `outbox_events` dan port `FulfillmentProvider` **sudah dipasang sejak S0** supaya tidak ada pembongkaran besar nanti.
