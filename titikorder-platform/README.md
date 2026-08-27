# TitikOrder — Platform Social Commerce (revamp)

Monorepo untuk platform hulu-hilir: **seller** (landing page → iklan → closing → kirim → uang cair) dan **fulfillment** (inbound → inventory → pick/pack → outbound → tagihan).

> ## 🧭 Mulai dari sini
>
> **[docs/HANDOVER.md](docs/HANDOVER.md)** — konteks bisnis, semua keputusan + alasannya, pelajaran dari data nyata, dan **prompt sesi pertama**. Wajib dibaca sebelum menulis kode.
>
> Lalu: **[docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)** (langkah membuat repo & kickoff S0) → **[CLAUDE.md](CLAUDE.md)** (aturan wajib) → **[docs/BLUEPRINT.md](docs/BLUEPRINT.md)** (arsitektur) → **[docs/STRUCTURE.md](docs/STRUCTURE.md)** (struktur & adapter) → **[docs/PLAN_SELLER.md](docs/PLAN_SELLER.md)** (fase S0–S5) → **[docs/INFRA_GCP.md](docs/INFRA_GCP.md)** (GCP) → **[docs/CICD_ENVIRONMENTS.md](docs/CICD_ENVIRONMENTS.md)** (branch & environment) → **[docs/FAILURE_ISOLATION.md](docs/FAILURE_ISOLATION.md)** (dampak kegagalan) → **[docs/COST_AND_APPS.md](docs/COST_AND_APPS.md)** (biaya & aplikasi).

---

## Isi saat ini

```
titikorder-platform/
├── CLAUDE.md                 # instruksi proyek untuk Claude Code
├── docs/
│   ├── BLUEPRINT.md          # arsitektur, stack, roadmap
│   ├── STRUCTURE.md          # struktur folder + pola adapter courier/ads
│   ├── PLAN_SELLER.md        # rencana Sistem Seller (fase S0–S5)
│   └── SPLIT_PLAN.md         # pembagian Seller DB vs Fulfillment DB
├── db/
│   ├── schema.sql            # DDL Fase 0-2 (tervalidasi di Postgres)
│   └── test_schema.py        # uji perilaku: RLS, state machine, ledger
├── packages/core/
│   ├── order.ts              # domain logic murni (tanpa I/O)
│   └── order.test.ts         # 19 tes, jalan tanpa DB
└── apps/lp/app/api/intake/route.ts   # endpoint order intake (idempoten)
```

---

## Menjalankan verifikasi

**Skema database** (butuh `pip install pgserver "psycopg[binary]"` — menyalakan Postgres sementara, tanpa instalasi server):

```bash
cd db && python test_schema.py
```
Menguji: isolasi RLS antar-tenant, WITH CHECK, state machine order, ledger stok, immutability append-only, constraint, idempotency.

**Domain logic:**

```bash
npx tsx packages/core/order.test.ts
```

---

## Aturan yang tidak boleh dilanggar

1. **Aplikasi konek sebagai `app_user`, bukan `postgres`.** Superuser mem-*bypass* RLS — kalau salah role, isolasi antar-tenant mati total meski policy sudah ada.
2. **Setiap transaksi wajib `SET LOCAL app.current_org = '<uuid>'`.** Tanpa ini, query tidak melihat baris apa pun (fail-closed, aman).
3. **Jangan pernah `UPDATE` saldo stok/uang.** Tulis baris baru di `stock_movements` / `ledger_entries`. Saldo dibaca dari view `stock_balances`.
4. **Harga selalu diambil dari DB**, tidak pernah dipercaya dari client.
5. **Efek samping (WhatsApp, webhook, sinkron ekspedisi) di luar transaksi** dan lewat queue — kegagalannya tidak boleh membatalkan order.

---

## Langkah berikutnya (Fase 1)

- [x] Skema DB Fase 0–2 + verifikasi perilaku
- [x] Domain logic order (state machine, dedup telepon, offer/bundle, idempotency)
- [x] API order intake
- [ ] Scaffold Next.js: `npx create-next-app@latest` untuk `apps/web-lp` & `apps/web-app`
- [ ] `lib/db.ts` (pool Postgres + helper `tx()` yang otomatis set `app.current_org`)
- [ ] `lib/queue.ts` (Cloud Tasks / Pub/Sub)
- [ ] Halaman landing page + form (render dari `landing_pages.content`)
- [ ] Back-office: daftar order, papan CS closing, catat followup
- [ ] Export batch ke ekspedisi + impor balik nomor resi
- [ ] Polling tracking → `tracking_events` → status shipment/undel

## Migrasi dashboard yang sudah ada

Dashboard Streamlit (Modul 1–5) tidak dibuang. Setelah Postgres hidup, ganti sumber di `data_loader.py` dari Google Sheet → Postgres; seluruh engine (`cashflow_engine`, `meta_engine`, `product_admin`, …) tetap berjalan. Port ke web menyusul di Fase 3.
