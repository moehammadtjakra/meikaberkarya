# CLAUDE.md — TitikOrder

Instruksi proyek untuk Claude Code. Baca ini lebih dulu sebelum mengubah apa pun.

---

## Apa ini

Platform social commerce hulu-hilir, revamp dari titikorder.com. **Tahap sekarang: sisi SELLER saja.**

Alur bisnis inti: iklan → landing page → lead → CS closing → kirim (resi ekspedisi) → tracking → diterima/retur → pencairan COD → laba.

**Sesi baru? Baca `docs/HANDOVER.md` lebih dulu** — di sana ada konteks bisnis, seluruh keputusan beserta alasannya, dan pelajaran teknis dari data nyata yang tidak terbaca dari kode.

Dokumen acuan (baca bila menyentuh arsitektur):
- `docs/HANDOVER.md` — **konteks & keputusan (mulai dari sini)**
- `docs/DESIGN_SYSTEM.md` — **standar UI/UX wajib** (baca sebelum membuat layar apa pun)
- `docs/BRAND.md` — **identitas visual**: tipografi, palet, gerak, dan daftar larangan "tampilan AI"
- `docs/PLAN_MIGRASI.md` — **lingkup Fase S1 + matriks RBAC**
- `docs/LOCAL_SETUP.md` — menjalankan di komputer sendiri (Docker Postgres, `app_user`, seed)
- `docs/DEPLOY_GUIDE.md` — deploy ke GCP + rencana domain dev/prod
- `docs/BLUEPRINT.md` — arsitektur & stack
- `docs/STRUCTURE.md` — struktur folder + pola adapter courier/ads
- `docs/PLAN_SELLER.md` — rencana Sistem Seller, fase S0–S5
- `docs/SPLIT_PLAN.md` — pembagian Seller DB vs Fulfillment DB
- `docs/INFRA_GCP.md` — service GCP, domain, keamanan
- `docs/COST_AND_APPS.md` — batas anggaran & aplikasi end-user
- `docs/SETUP_GUIDE.md` — langkah memulai & urutan prompt per fase
- `db/schema.sql` — skema tervalidasi (7 tes perilaku lulus)

**Anggaran adalah batasan desain.** Target biaya infrastruktur: ±Rp 1–3 juta/bulan saat membangun, ±Rp 3–5 juta/bulan saat produksi. Jangan menyarankan komponen berbiaya besar (GKE, HA multi-zona, BigQuery/Datastream, Memorystore) sebelum ada kebutuhan nyata — lihat tabel "Kapan menaikkan kelas" di `COST_AND_APPS.md`.

---

## Aturan yang TIDAK BOLEH dilanggar

1. **Aplikasi konek ke Postgres sebagai role `app_user`, bukan `postgres`.**
   Superuser mem-*bypass* RLS. Salah role = isolasi antar-tenant mati total tanpa error apa pun.

2. **Setiap transaksi wajib `SET LOCAL app.current_org = '<uuid>'`.**
   Tanpa ini query mengembalikan kosong (fail-closed). Jangan pernah menyiasatinya dengan menonaktifkan RLS.

3. **Jangan pernah `UPDATE` saldo stok atau uang.**
   Tulis baris baru di `stock_movements` / `ledger_entries`. Saldo dibaca dari view `stock_balances`.
   Tabel `stock_movements`, `ledger_entries`, `audit_logs` bersifat **append-only** (dijaga trigger).

4. **Harga selalu diambil dari database, tidak pernah dari client.**
   Payload form hanya boleh membawa `offerId` + `qty`.

5. **Efek samping di luar transaksi.**
   WhatsApp, webhook, sinkronisasi ekspedisi → masuk queue. Kegagalannya tidak boleh membatalkan order.

6. **Routing gudang mendahului penerbitan resi.**
   Urutan wajib: `confirmed → pilih gudang → reservasi stok → terbitkan resi → permintaan fulfillment`.
   Alamat asal pada resi bergantung gudang pemenuh, jadi urutan ini tidak boleh dibalik.

7. **Logika ekspedisi & ads TIDAK boleh masuk modul inti.**
   Semua lewat adapter di `packages/integrations/`. Menambah SPX/TikTok = folder baru, bukan membedah `shipping`/`ads`.

8. **`packages/core` harus bebas I/O.**
   Tanpa import DB, tanpa fetch, tanpa framework. Supaya bisa diuji dalam milidetik.

9. **JANGAN menjalankan git yang mengubah riwayat atau remote.**
   Dilarang: `git commit`, `git push`, `git reset`, `git rebase`, `git checkout`, `git merge`, `gh pr create`.
   Boleh: `git status`, `git diff`, `git log`, `git show`.
   **Commit dan push adalah keputusan manusia.** Tugas Anda berhenti di: ubah berkas → jalankan tes → laporkan ringkasan perubahan. Biarkan pemilik repo yang meninjau diff lalu memutuskan.

10. **JANGAN men-deploy atau menyentuh infrastruktur/produksi.**
    Dilarang: `gcloud run deploy`, `gcloud sql …`, `terraform apply`, `prisma migrate deploy`.
    Boleh menulis berkas konfigurasi/migrasi, tapi eksekusinya dilakukan manusia atau pipeline CI.

11. **Batas antar domain tidak boleh ditembus.**
    `apps/seller-*` dilarang mengimpor dari `apps/ff-*` dan sebaliknya. Satu-satunya jembatan adalah `packages/contracts`. Lihat `docs/adr/0001-satu-repo-seller-fulfillment.md`.

12. **Setiap layar wajib mengikuti `docs/DESIGN_SYSTEM.md`.**
    Empat status (memuat/kosong/error/berisi), mobile terasa seperti aplikasi (bottom nav, sheet, tabel→kartu), bahasa Indonesia tanpa jargon, target sentuh ≥44px, dan checklist §13 terpenuhi. Layar yang hanya menangani "berhasil dengan data" dianggap **belum selesai**.

---

## Arsitektur singkat

- **Dua service, dua database**: Sistem Seller (SS, repo ini) dan Sistem Fulfillment (FS, menyusul di S5).
- Di dalam SS: **modular monolith** dengan batas modul tegas. Jangan pecah jadi microservices.
- SS memiliki: SKU master, order, CRM, **resi & tracking**, keuangan, iklan.
- FS memiliki: stok fisik di gudangnya, bin, picking, packing, tagihan jasa.
- SS bicara ke gudang lewat port `FulfillmentProvider` — implementasi `SelfManualProvider` sekarang, `TitikFulfillmentProvider` nanti.

**Multi-tenant-ready:** semua tabel bisnis punya `org_id` + RLS sejak awal. Sekarang dipakai internal; membuka seller lain cukup membuat akun.

---

## Stack

TypeScript end-to-end.

- **Frontend**: Next.js 15 (App Router) + Tailwind + shadcn/ui — `lp-renderer`, `seller-web`, `ff-web`
- **Backend**: NestJS 11 (Fastify) + Prisma + Zod — `seller-api`, `ff-api`
- **Worker**: NestJS standalone, konsumsi Pub/Sub push
- **Data**: Cloud SQL for PostgreSQL (private IP, RLS)
- **Deploy**: Google Cloud Run (bukan GKE) — rincian di `docs/INFRA_GCP.md`

**Logika bisnis hanya di `*-api`.** Frontend boleh punya BFF tipis untuk kebutuhan layar, tapi jangan menaruh aturan bisnis di sana.

---

## Struktur

```
apps/lp        landing page publik (trafik iklan, edge/ISR)
apps/web       back-office seller  → src/modules/<domain>/
apps/worker    job latar (tarik Meta, polling tracking, parse settlement)
packages/core          domain logic murni (tanpa I/O)
packages/db            Prisma schema + migrasi
packages/contracts     skema Zod + tipe event
packages/ui            komponen bersama
packages/integrations/courier/{jnt,spx,everpro}
packages/integrations/ads/{meta,tiktok}
```

Modul di `apps/web/src/modules/`: `iam` `catalog` `storefront` `orders` `crm` `inventory` `procurement` `shipping` `finance` `ads` `analytics`.

**Organisasi berdasarkan DOMAIN, bukan lapisan teknis.** Jangan buat folder `controllers/`, `services/`, `models/` di level atas.

---

## Fitur general vs internal

Bedakan dengan **entitlement**, bukan basis kode terpisah:

- `general` — dipakai semua seller (storefront builder, CRM, katalog, stok)
- `internal` — baru untuk internal (export J&T, analisis pencairan, Meta Ads analytics)

Cek lewat `packages/core/features.ts`. Saat seller lain masuk, cukup nyalakan flag.

---

## Disiplin fase (jangan lompat)

| Fase | Isi | Selesai bila |
|---|---|---|
| **S0** | IAM, org+RLS, **RBAC + matriks permission**, katalog/SKU, audit, port fulfillment | bisa login & kelola produk; hak akses per peran berlaku |
| **S1** | **Migrasi 3 sistem Apps Script**: admin order, CS undelivered, J&T (resi + pencairan), Meta Ads | karyawan berhenti memakai Google Sheets untuk kerja harian |
| **S2** | LP + form + intake + CRM closing | order nyata masuk & di-closing di sistem sendiri (lepas dari OrderOnline) |
| **S3** | stok lanjutan, procurement, keuangan menyeluruh | stok & kas cocok kenyataan |
| **S4** | port Modul 1/3/4/5 + funnel penuh | keputusan scale/kill dari sistem |
| **S5** | adapter FS + event bus | order bisa dipenuhi gudang FS |

Urutan ini ditetapkan `docs/adr/0002-migrasi-dulu-sebelum-demand.md`. Rincian S1 (lingkup per sistem + matriks RBAC): `docs/PLAN_MIGRASI.md`.

**Satu fase tidak dimulai sebelum fase sebelumnya dipakai nyata.** Jangan menambah fitur yang belum ada penggunanya.

---

## Konvensi kode

- Bahasa UI, komentar, dan pesan commit: **Bahasa Indonesia**. Nama variabel/fungsi: Inggris.
- Validasi input dengan **Zod** di batas sistem (route handler, job).
- Uang: `numeric(14,2)` di DB, jangan `float` di JS untuk perhitungan akhir.
- Telepon dinormalisasi ke `62xxx` lewat `normalizePhone()` — ini kunci dedup pelanggan.
- Setiap intake/webhook wajib `idempotency_keys`.
- Migrasi DB selalu lewat Prisma migrate; jangan ubah tabel manual di produksi.

---

## Repo, git & CI/CD

**Monorepo.** Semua service ada di repo ini. Jangan menyarankan memecah jadi banyak repo — `packages/core` dan `packages/contracts` dipakai bersama, dan perubahan lintas service harus bisa atomik dalam satu commit.

**Git:**
- Branch: `feat/…`, `fix/…`, `chore/…`, `docs/…`. Jangan commit langsung ke `main`.
- Pesan commit: **Bahasa Indonesia**, format Conventional Commits (`feat: …`, `fix: …`).
- Satu PR = satu tujuan. PR yang menyentuh 5 modul sekaligus sulit ditinjau.

**CI/CD** (Cloud Build / GitHub Actions):
- PR → lint + typecheck + tes domain + tes skema.
- Merge ke `main` → build image **hanya app yang berubah** (path-based trigger) → Artifact Registry → deploy Cloud Run dengan traffic split bertahap.
- **Migrasi DB dijalankan sebagai job terpisah**, bukan saat service start — beberapa instance akan bermigrasi bersamaan kalau ditaruh di startup.
- Rollback = arahkan trafik ke revisi Cloud Run sebelumnya.

**Lingkungan:** `dev` → `staging` → `prod`, masing-masing project GCP terpisah. Jangan pernah menguji migrasi langsung di `prod`.

**Rahasia:** hanya dari Secret Manager. Tidak ada `.env` di image, tidak ada kunci service account statis di CI (pakai Workload Identity Federation).

## Perintah

```bash
pnpm dev                      # jalankan semua app
pnpm --filter seller-web dev  # satu app saja
pnpm test                     # unit test
pnpm db:migrate               # migrasi Prisma
npx tsx packages/core/order.test.ts      # tes domain (cepat, tanpa DB)
python db/test_schema.py                 # tes perilaku skema di Postgres sementara
```

---

## Cara kerja yang diharapkan (loop)

Setiap tugas dikerjakan dalam siklus ini — **berhenti sebelum git**:

```
1. EXPLORE   baca kode & dokumen terkait dulu; jangan menebak isi berkas
2. RENCANA   sampaikan rencana singkat + berkas mana yang akan disentuh
3. UBAH      lakukan perubahan sekecil mungkin yang menyelesaikan tugas
4. EVALUASI  jalankan tes/build; kalau gagal, perbaiki dan ulangi
5. LAPOR     ringkas: apa yang berubah, kenapa, apa yang belum, risiko apa
   ┗━ BERHENTI. Manusia yang meninjau diff, commit, dan push.
```

Untuk tugas besar atau berisiko, gunakan mode rencana lebih dulu dan tunggu persetujuan sebelum mengubah berkas.

## Sebelum menyatakan selesai

- Jalankan tes domain & tes skema bila menyentuh `core` atau `db`.
- Untuk perubahan lintas modul, periksa dampaknya ke RLS dan idempotency.
- Jangan pernah menulis `.env`, kredensial, atau token ke dalam repo.
- Laporkan perubahan — **jangan** commit atau push.
