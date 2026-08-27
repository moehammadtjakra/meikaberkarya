# Panduan Memulai — dari folder kosong sampai Claude Code membangun

Panduan langkah demi langkah untuk memulai proyek TitikOrder, dengan cara yang memastikan **Claude Code memahami seluruh konteks** yang sudah kita putuskan tanpa Anda harus menjelaskan ulang.

---

## Langkah 0 — Keputusan repo (baca dulu)

**Satu repo `titikorder`** memuat **kedua domain** (Seller dan Fulfillment) beserta semua service-nya.

**Repo bukan batas keandalan.** Keandalan datang dari service & database yang terpisah saat berjalan — dan itu tetap terpenuhi. Satu repo tetap men-deploy 7 service yang gagal, di-scale, dan di-rollback sendiri-sendiri. Rinciannya di `docs/adr/0001-satu-repo-seller-fulfillment.md`.

| | Satu repo (dipilih) | Repo terpisah |
|---|---|---|
| Keandalan runtime | **sama** | **sama** |
| Ubah kontrak Seller↔Fulfillment | satu PR, atomik | wajib versioning + rilis 2 tahap |
| Konteks Claude Code | utuh, satu sesi | terpotong, saling buta |
| `packages/contracts` bersama | impor langsung | perlu registry paket privat |
| Cocok saat | solo / tim kecil | ada tim & akses terpisah |

**Syarat mutlak:** `apps/seller-*` dilarang mengimpor dari `apps/ff-*` dan sebaliknya — satu-satunya jembatan adalah `packages/contracts`, ditegakkan lint di CI. Dengan batas ini terjaga, memisah repo nanti cukup `git subtree split` atau `git filter-repo` dan histori tetap terbawa.

Repo terpisah tetap dipakai untuk **produk yang benar-benar beda** — dashboard J&T Anda tetap di repo sendiri.

Struktur di komputer:

```
D:\Projects\                     ← folder utama (bukan repo)
├── titikorder\                  ← repo #1  (monorepo platform)
└── meika-dashboard\             ← repo #2  (dashboard J&T, sudah ada)
```

**Jalankan Claude Code di dalam `titikorder\`**, bukan di folder utama. Kalau sewaktu-waktu perlu melihat repo dashboard (mis. mem-port Modul 5), pakai `/add-dir` di sesi yang sedang berjalan.

---

## Langkah 1 — Siapkan repo

```bash
mkdir -p /d/Projects/titikorder && cd /d/Projects/titikorder
git init -b main
```

Salin seluruh isi folder `titikorder-platform/` (hasil kerja kita) ke sini, sehingga menjadi:

```
titikorder/
├── CLAUDE.md
├── README.md
├── docs/    BLUEPRINT · STRUCTURE · PLAN_SELLER · SPLIT_PLAN · INFRA_GCP · COST_AND_APPS · SETUP_GUIDE
├── db/      schema.sql · test_schema.py
└── packages/core/  order.ts · order.test.ts
```

Buat `.gitignore` minimal:

```
node_modules/
.next/
dist/
.env*
!.env.example
*.log
.turbo/
coverage/
```

Commit pertama:

```bash
git add .
git commit -m "docs: arsitektur, skema DB, dan domain logic awal"
```

---

## Langkah 2 — GitHub

```bash
gh repo create titikorder --private --source=. --remote=origin --push
```

Atau buat repo manual di GitHub lalu:

```bash
git remote add origin https://github.com/<akun>/titikorder.git
git push -u origin main
```

Setelah itu, di GitHub → Settings → Branches, aktifkan **branch protection** pada `main`: wajib PR, wajib CI hijau. Ini murah dan mencegah dorongan langsung yang merusak.

---

## Langkah 2b — Kunci izin Claude Code (git & deploy di tangan Anda)

Instruksi di `CLAUDE.md` saja tidak cukup — kuncinya di level izin. Buat berkas **`.claude/settings.json`** di root repo:

```json
{
  "permissions": {
    "deny": [
      "Bash(git commit:*)",
      "Bash(git push:*)",
      "Bash(git reset:*)",
      "Bash(git rebase:*)",
      "Bash(git checkout:*)",
      "Bash(git merge:*)",
      "Bash(gh pr create:*)",
      "Bash(gcloud run deploy:*)",
      "Bash(gcloud sql:*)",
      "Bash(terraform apply:*)",
      "Bash(prisma migrate deploy:*)"
    ],
    "allow": [
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(pnpm install:*)",
      "Bash(pnpm build:*)",
      "Bash(pnpm test:*)",
      "Bash(pnpm lint:*)",
      "Bash(npx tsx:*)"
    ]
  }
}
```

Commit berkas ini ke repo supaya aturannya ikut ke mana pun. Verifikasi di sesi Claude Code dengan `/permissions`.

**Alur kerja yang berlaku:** Claude Code menjalankan siklus *explore → rencana → ubah → evaluasi → lapor*, lalu **berhenti**. Anda yang membaca `git diff`, memutuskan, lalu commit dan push sendiri. Untuk tugas besar, mulai dengan mode rencana (tekan `Shift+Tab`) agar ia menyusun rencana tanpa menyentuh berkas.

---

## Langkah 3 — Buka Claude Code & pastikan konteksnya masuk

Di VS Code, buka folder `titikorder`, lalu jalankan Claude Code di terminal terintegrasi:

```bash
claude
```

**Prompt verifikasi konteks** (tempel apa adanya):

```
Baca CLAUDE.md dan seluruh file di docs/. Lalu ringkas dalam maksimal 10 poin:
arsitektur yang dipilih, aturan yang tidak boleh dilanggar, urutan fase S0-S5,
dan apa yang sudah ada di repo ini. Jangan menulis kode dulu.
```

Kalau ringkasannya cocok dengan yang kita putuskan (dua service, dua DB, RLS + `app_user`, ledger append-only, resi milik seller, routing gudang sebelum resi, adapter courier/ads, Cloud Run), berarti konteksnya sudah utuh. **Jangan lanjut sebelum bagian ini benar** — semua pekerjaan berikutnya bergantung padanya.

---

## Langkah 4 — Prompt kickoff Fase S0

Prasyarat: PostgreSQL lokal sudah jalan (lihat `LOCAL_SETUP.md`) dan `app_user` sudah punya password.

Tempel prompt ini:

```
Kerjakan Fase S0 sesuai docs/PLAN_SELLER.md, docs/PLAN_MIGRASI.md, dan docs/STRUCTURE.md.

KERANGKA MONOREPO
1. pnpm workspaces + turborepo (package.json, pnpm-workspace.yaml, turbo.json)
2. packages/config  — tsconfig & eslint bersama (termasuk aturan larangan impor
   silang antara apps/seller-* dan apps/ff-*)
3. apps/seller-api    — NestJS 11 + Fastify + Prisma + Zod
   apps/seller-web    — Next.js 15 App Router + Tailwind + shadcn/ui
   apps/seller-worker — NestJS standalone (kerangka saja)
   (lp-renderer belum dibuat di S0 — landing page baru di S2)
4. packages/core       — pindahkan order.ts + order.test.ts yang sudah ada ke sini
   packages/db         — Prisma schema hasil terjemahan db/schema.sql
   packages/contracts  — skema Zod + tipe event
   packages/integrations/courier/core + ads/core — interface adapter saja

FONDASI WAJIB
5. apps/seller-api/src/lib/db.ts — helper tx() yang SELALU menjalankan
   SET LOCAL app.current_org sebelum query, dan konek sebagai role app_user
6. Modul iam: organisasi, user, membership, role, permission, audit log
7. RBAC penuh sesuai matriks di docs/PLAN_MIGRASI.md §4:
   - guard permission di server untuk SETIAP endpoint
   - pembatasan baris (row-level) untuk peran cs_undel — bukan sekadar
     menyembunyikan menu
   - halaman kelola pengguna, kelola role + centang permission, log audit
8. Auth.js (credentials provider) untuk login lokal; simpan user di DB kita
9. Modul catalog: produk, SKU, offer/bundle — CRUD dasar
10. Port FulfillmentProvider + SelfManualProvider (stub)
11. Dockerfile per app (multi-stage, non-root) siap untuk Cloud Run
12. .env.example per app; DATABASE_URL menunjuk ke Postgres lokal sebagai app_user

BATASAN
- JANGAN membangun fitur S1 ke atas (importer J&T, undel, Meta Ads, LP, CRM).
- Patuhi semua aturan di CLAUDE.md: RLS, ledger append-only, harga dari DB,
  efek samping di luar transaksi.
- Jangan menaruh logika bisnis di frontend.

SETELAH SELESAI
- jalankan `npx tsx packages/core/order.test.ts` (harus 19 lulus)
- jalankan `pnpm build` — tidak boleh ada error TypeScript
- buat seed: 1 organisasi, role bawaan, 1 user owner, beberapa SKU contoh
- laporkan file apa saja yang dibuat, apa yang belum, dan cara menjalankannya
```

**Definisi selesai S0:** Anda bisa `pnpm dev`, membuka http://localhost:3000, login sebagai owner, membuat produk/SKU, membuat user baru dengan role berbeda, lalu **membuktikan** bahwa user dengan role terbatas tidak bisa mengakses hal di luar haknya — walau URL-nya diketik langsung.

## Langkah 5 — Verifikasi

```bash
npx tsx packages/core/order.test.ts     # 19 tes domain
python db/test_schema.py                 # 7 tes perilaku skema (butuh pgserver, psycopg)
pnpm build
```

Commit:

```bash
git checkout -b feat/s0-scaffold
git add . && git commit -m "feat: kerangka monorepo fase S0"
git push -u origin feat/s0-scaffold
```

---

## Langkah 6 — CI/CD

**Rekomendasi: Cloud Build atau GitHub Actions, bukan Jenkins.**

Jenkins mengharuskan Anda menjalankan dan merawat server sendiri: patch keamanan, pembaruan plugin, backup konfigurasi — ±$25–50/bulan plus waktu Anda, untuk hasil yang setara. Cloud Build berjalan tanpa server dan terintegrasi langsung dengan Artifact Registry serta Cloud Run; GitHub Actions punya kuota gratis yang memadai dan konfigurasinya ada di repo.

Pakai Jenkins hanya bila ada keharusan organisasi atau Anda sudah punya instans yang berjalan.

**Alur CI/CD (siapa pun runner-nya):**

```
PR → lint + typecheck + test (domain & skema)
merge ke main → build image per app yang berubah → Artifact Registry
             → jalankan migrasi DB sebagai job terpisah
             → deploy Cloud Run, traffic 10% → 100%
```

Dua aturan penting:

1. **Migrasi DB dijalankan sebagai job tersendiri**, bukan saat service start — kalau tidak, beberapa instance akan bermigrasi bersamaan.
2. **Path-based trigger** untuk monorepo: hanya bangun app yang berubah. Contoh filter Cloud Build: `apps/seller-api/**`, `packages/**`.

Bila tetap memakai Jenkins: jalankan di VM kecil GCE, dan gunakan **Workload Identity Federation** agar tidak perlu menyimpan kunci service account jangka panjang (kunci statis adalah risiko keamanan terbesar di CI).

Prompt untuk Claude Code:

```
Buat pipeline CI/CD dengan Cloud Build: cloudbuild.yaml per app + path-based trigger,
build image multi-stage, migrasi Prisma sebagai step terpisah, deploy ke Cloud Run
dengan traffic split bertahap. Sertakan juga workflow GitHub Actions untuk PR check
(lint, typecheck, test). Jangan simpan kredensial apa pun di repo.
```

---

## Langkah 7 — Setup Google Cloud (mengikuti anggaran)

Ikuti **tahap A** di `docs/COST_AND_APPS.md` — jangan nyalakan semuanya.

1. Buat 3 project: `titikorder-dev`, `titikorder-staging`, `titikorder-prod`.
2. Aktifkan API: Cloud Run, Cloud SQL, Artifact Registry, Secret Manager, Cloud Build, Cloud Scheduler, Pub/Sub.
3. Cloud SQL PostgreSQL **zonal** (belum HA), **private IP**, aktifkan PITR.
4. Jalankan `db/schema.sql`, lalu buat role `app_user` (sudah ada di skema) dan simpan kredensialnya di Secret Manager.
5. Deploy satu service dulu (`seller-api`) untuk memastikan jalur build→deploy hidup.
6. Cloudflare: arahkan `titikorder.com`, aktifkan proxy, lalu **Authenticated Origin Pulls** agar `*.run.app` tidak bisa diakses langsung.

Baru setelah semua hijau, lanjut ke fase S1.

---

## Langkah 8 — Urutan prompt fase berikutnya

Satu fase = satu rangkaian prompt. Selalu rujuk dokumennya agar Claude Code tidak berimprovisasi:

| Fase | Prompt pembuka |
|---|---|
| S1 | `Kerjakan Fase S1 sesuai docs/PLAN_SELLER.md: landing page + form intake idempoten + order + CRM closing. Pakai packages/core/order.ts yang sudah ada, jangan tulis ulang logikanya.` |
| S2 | `Kerjakan Fase S2: routing gudang, penerbitan resi, adapter J&T (export, impor resi, tracking, pencairan) sesuai pola di docs/STRUCTURE.md §3.` |
| S3 | `Kerjakan Fase S3: stok gudang seller (ledger append-only), procurement, pencairan COD, rekonsiliasi.` |
| S4 | `Kerjakan Fase S4: adapter Meta Ads + modul analytics. Port logika dari repo dashboard (pakai /add-dir).` |
| S5 | `Kerjakan Fase S5: Sistem Fulfillment sebagai service terpisah dengan DB sendiri, event Pub/Sub, dan adapter TitikFulfillmentProvider.` |

**Aturan disiplin:** jangan mulai fase berikutnya sebelum fase sekarang benar-benar dipakai di operasional nyata minimal 1–2 minggu. Ini yang membedakan sistem yang selesai dari sistem yang selamanya 80%.

---

## Ringkas

1. Satu repo `titikorder`, Claude Code dijalankan di dalamnya.
2. Salin `CLAUDE.md` + `docs/` + `db/` + `packages/core/` — inilah "ingatan" proyek.
3. Verifikasi pemahaman Claude Code sebelum menyuruhnya menulis kode.
4. Kickoff S0 → verifikasi tes → commit lewat PR.
5. CI/CD pakai Cloud Build/GitHub Actions; Jenkins hanya bila wajib.
6. GCP mengikuti tahap A dulu.
7. Naik fase hanya setelah fase sebelumnya terpakai nyata.
