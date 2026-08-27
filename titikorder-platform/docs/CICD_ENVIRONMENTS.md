# Repo, Service, Environment & CI/CD — penjelasan menyeluruh

Dokumen ini menjawab kebingungan yang paling sering muncul: **apa bedanya repo, service, environment, dan domain** — lalu bagaimana alur push → test → produksi bekerja di atasnya.

---

## 1. Empat sumbu yang sering tertukar

Ini bukan hal yang sama, dan jumlahnya berbeda-beda:

| Sumbu | Jumlah | Artinya | Contoh |
|---|---|---|---|
| **Repo** | **1** | tempat kode disimpan | `titikorder` di GitHub |
| **Service** | **7** | unit yang berjalan & di-deploy sendiri | `seller-api`, `lp-renderer`, … |
| **Environment** | **2–3** | salinan lengkap sistem | `dev`, (`staging`), `prod` |
| **Domain** | banyak | alamat menuju service di environment tertentu | `app.titikorder.com` |

Cara membacanya:

> **Satu repo** berisi kode **tujuh service**. Setiap service di-*deploy* ke **tiap environment**. Setiap environment punya **domain sendiri**.

Jadi di produksi ada 7 service berjalan; di dev ada 7 service berjalan lagi (terpisah total, database sendiri). Kode mereka berasal dari repo yang sama, hanya beda **branch** dan **konfigurasi**.

---

## 2. Service utama & isinya

### Domain Seller (dibangun sekarang, fase S0–S4)

| Service | Peran | Jenis |
|---|---|---|
| `lp-renderer` | landing page publik + form intake | Next.js |
| `seller-web` | back-office: order, CRM, katalog, keuangan, analitik | Next.js |
| `seller-api` | **logika bisnis** — sumber kebenaran | NestJS |
| `seller-worker` | job latar: tarik Meta, polling tracking, parse pencairan | NestJS |

Modul **di dalam** `seller-api` (bukan service terpisah): `iam`, `catalog`, `storefront`, `orders`, `crm`, `inventory`, `procurement`, `shipping`, `finance`, `ads`, `analytics`.

### Domain Fulfillment (fase S5)

| Service | Peran | Jenis |
|---|---|---|
| `ff-web` | UI gudang, PWA scanner | Next.js |
| `ff-api` | logika gudang | NestJS |
| `ff-worker` | konsumsi event, rekonsiliasi, tagihan | NestJS |

**Kedua domain ada di repo yang sama**, tapi berjalan sebagai service terpisah dengan database terpisah. Alasannya di `adr/0001-satu-repo-seller-fulfillment.md`.

---

## 3. Environment

Satu environment = **satu project GCP + satu set Cloud Run + satu Cloud SQL**. Semuanya terisolasi.

| Environment | Project GCP | Untuk apa | Biaya |
|---|---|---|---|
| **dev** | `titikorder-dev` | uji fitur baru, data palsu | murah — Cloud SQL kecil, semua Cloud Run scale-to-zero |
| **staging** | `titikorder-staging` | UAT mirip produksi | **tunda** sampai ada seller berbayar |
| **prod** | `titikorder-prod` | operasional nyata | sesuai `COST_AND_APPS.md` |

**Mulai dengan dua environment saja (dev + prod).** Setiap environment menambah satu Cloud SQL (±$25–30/bulan untuk dev). Staging baru masuk akal ketika downtime produksi sudah mahal.

### Domain per environment

| Environment | Domain |
|---|---|
| prod | `app.titikorder.com` · `api.titikorder.com` · `lp.titikorder.com` · `wms.titikorder.com` |
| dev | `app-dev.titikorder.com` · `api-dev.titikorder.com` · `lp-dev.titikorder.com` |

> **Pola tanda hubung, bukan tingkat kedua.** Pakai `app-dev.titikorder.com`, bukan `app.dev.titikorder.com` — Universal SSL gratis Cloudflare hanya mencakup subdomain **satu tingkat**, sehingga pola dua tingkat memicu peringatan sertifikat. Lihat `DEPLOY_GUIDE.md` §1.

Domain hanyalah penunjuk. `app.titikorder.com` → service `seller-web` di project `titikorder-prod`; `app-dev.titikorder.com` → service `seller-web` di project `titikorder-dev`. **Kode sama, environment beda.**

---

## 4. Alur branch → deploy

```
feat/nama-fitur
   │ push
   ├─→ CI: lint · typecheck · tes domain · tes skema
   │   TIDAK di-deploy ke mana pun
   │
   │ PR + review
   ▼
develop
   │
   ├─→ CI build image (hanya service yang berubah)
   ├─→ migrasi DB dev
   └─→ deploy ke environment DEV, trafik 100%
       ▼  uji fitur di app-dev.titikorder.com
   │
   │ PR develop → main + review
   ▼
main
   │
   ├─→ CI build image
   ├─→ migrasi DB prod  (job terpisah, sebelum deploy)
   ├─→ deploy revisi baru dengan trafik 0%
   ├─→ smoke test lewat URL revisi (belum kena pengguna)
   ├─→ geser 10% → pantau error rate & latensi
   └─→ geser 100%
```

**Aturan branch:**

| Branch | Boleh di-push langsung? | Deploy ke |
|---|---|---|
| `feat/*`, `fix/*` | ya | tidak ada |
| `develop` | tidak — hanya lewat PR | dev |
| `main` | tidak — hanya lewat PR | prod |

Aktifkan **branch protection** di GitHub untuk `develop` dan `main`: wajib PR, wajib CI hijau.

---

## 5. "Test di production" yang aman

Anda menyebut ingin menguji lagi di produksi. Caranya **bukan** deploy langsung ke semua pengguna, tapi **canary**:

1. Deploy revisi baru dengan **0% trafik** — ia hidup tapi belum menerima pengguna.
2. Cloud Run memberi **URL khusus revisi**; lakukan smoke test di situ dengan data produksi asli.
3. Geser **10%** trafik. Pantau error rate, latensi p95, dan log 10–30 menit.
4. Kalau sehat → **100%**. Kalau bermasalah → **kembalikan ke revisi lama**, selesai dalam hitungan detik.

Inilah kenapa Cloud Run dipilih: rollback bukan proses build ulang, melainkan memindahkan penunjuk trafik.

---

## 6. Migrasi database — bagian paling berisiko

Saat canary, **revisi lama dan baru berjalan bersamaan** di atas database yang sama. Karena itu migrasi wajib **kompatibel mundur** (pola expand → migrate → contract):

| Tahap | Aksi | Aman karena |
|---|---|---|
| **Expand** | tambah kolom/tabel baru (nullable), jangan hapus apa pun | kode lama tidak terganggu |
| **Migrate** | deploy kode baru yang menulis ke keduanya | dua versi hidup berdampingan |
| **Contract** | setelah 100% & stabil, baru hapus kolom lama | tidak ada lagi yang memakainya |

**Jangan pernah** menghapus atau mengganti nama kolom dalam rilis yang sama dengan kode yang memakainya. Ini penyebab downtime paling umum di sistem yang sudah jalan.

Migrasi dijalankan sebagai **job CI terpisah**, bukan saat service start — kalau di startup, beberapa instance akan bermigrasi bersamaan dan saling bertabrakan.

---

## 7. Build hanya yang berubah (monorepo)

Satu repo bukan berarti semua di-build tiap commit. Pakai **path-based trigger**:

| Berubah | Yang di-build |
|---|---|
| `apps/seller-api/**` | `seller-api` saja |
| `apps/lp-renderer/**` | `lp-renderer` saja |
| `packages/core/**` atau `packages/contracts/**` | semua service yang memakainya |
| `docs/**` | tidak ada (hanya CI dokumen) |

---

## 8. Rahasia & konfigurasi per environment

Tidak ada `.env` di repo. Tiap environment punya **Secret Manager sendiri** di project GCP-nya:

```
titikorder-dev   → DATABASE_URL(dev), META_TOKEN(akun uji)
titikorder-prod  → DATABASE_URL(prod), META_TOKEN(akun asli), kredensial J&T
```

Cloud Run membaca secret saat runtime lewat service account masing-masing. CI **tidak** menyimpan kunci service account statis — pakai **Workload Identity Federation**.

---

## 9. Ringkasan satu layar

```
REPO (1)            titikorder
   └── SERVICE (7)  lp-renderer · seller-web · seller-api · seller-worker
                    ff-web · ff-api · ff-worker
        └── ENVIRONMENT (2)   dev  ·  prod        ← masing-masing project GCP + DB sendiri
             └── DOMAIN       app-dev.titikorder.com  ·  app.titikorder.com

BRANCH            feat/*  →  develop  →  main
DEPLOY KE         (tidak)     dev         prod (canary 10% → 100%)
```

Yang perlu diingat: **repo mengatur di mana kode disimpan; service mengatur apa yang berjalan; environment mengatur untuk siapa ia berjalan; domain hanya alamatnya.** Keempatnya bebas berubah tanpa mengganggu yang lain.
