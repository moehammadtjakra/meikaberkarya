# Panduan Deploy — dari Lokal ke Google Cloud

Langkah menaikkan aplikasi dari komputer sendiri ke cloud: **environment dev dulu untuk pengujian**, produksi menyusul setelah terbukti.

Prasyarat: Fase S0 selesai, aplikasi jalan di lokal, Dockerfile per app sudah ada.

---

## 1. Rencana domain — baca ini sebelum membeli apa pun

### Jebakan yang harus dihindari

Cloudflare **Universal SSL (paket gratis) hanya mencakup domain utama dan subdomain satu tingkat.** Artinya:

| Alamat | Tercakup SSL gratis? |
|---|---|
| `titikorder.com` | ✅ ya |
| `app.titikorder.com` | ✅ ya |
| `app.dev.titikorder.com` | ❌ **tidak** — dua tingkat |

Kalau Anda memakai pola `app.dev.titikorder.com`, browser akan menampilkan **peringatan sertifikat**, dan untuk memperbaikinya perlu Advanced Certificate Manager (±$10/bulan).

### Pola yang dipakai — gratis dan aman

Pakai **tanda hubung**, bukan tingkat kedua:

| Environment | Alamat | Menuju |
|---|---|---|
| **dev** | `app-dev.titikorder.com` | `seller-web` (dev) |
| | `api-dev.titikorder.com` | `seller-api` (dev) |
| **prod** | `app.titikorder.com` | `seller-web` (prod) |
| | `api.titikorder.com` | `seller-api` (prod) |
| | `wms.titikorder.com` | `ff-web` (nanti) |
| | `lp.titikorder.com` | `lp-renderer` (nanti) |

Semua satu tingkat → tercakup Universal SSL gratis. Menghemat ±Rp 160rb/bulan dan menghindari kebingungan sertifikat.

### Yang perlu dibeli sekarang

Hanya **satu domain**: `titikorder.com` (±Rp 200rb/tahun). Beli di registrar mana pun, lalu **pindahkan nameserver-nya ke Cloudflare** (gratis). Semua subdomain di atas dibuat di Cloudflare tanpa biaya tambahan.

---

## 2. Dua environment, dua project GCP

| Project GCP | Untuk | Ukuran |
|---|---|---|
| `titikorder-dev` | pengujian, data palsu | sekecil mungkin, scale-to-zero |
| `titikorder-prod` | operasional nyata | sesuai `COST_AND_APPS.md` |

Project terpisah = tagihan terpisah, izin terpisah, dan **mustahil salah menghapus data produksi** saat bereksperimen.

---

## 3. Langkah deploy ke dev

### A. Siapkan project & API

```bash
gcloud projects create titikorder-dev
gcloud config set project titikorder-dev
# aktifkan billing lewat Console (wajib, walau pemakaian masih di tier gratis)

gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com
```

Region yang dipakai: **`asia-southeast2`** (Jakarta). Konsisten untuk semua layanan.

### B. Database

```bash
gcloud sql instances create titikorder-dev-db \
  --database-version=POSTGRES_16 \
  --tier=db-g1-small \
  --region=asia-southeast2 \
  --storage-size=10GB
```

Lalu:
1. Buat database `titikorder`.
2. Jalankan `db/schema.sql` (atau `prisma migrate deploy`).
3. Buat role `app_user` + beri password kuat.

> **Untuk dev**, instance terkecil sudah cukup. Jangan aktifkan HA — itu untuk produksi.

### C. Simpan rahasia

```bash
echo -n "postgresql://app_user:PASSWORD@HOST:5432/titikorder" | \
  gcloud secrets create DATABASE_URL --data-file=-

echo -n "STRING_ACAK_PANJANG" | gcloud secrets create AUTH_SECRET --data-file=-
```

**Jangan pernah** menaruh nilai ini di `.env` yang ikut ke image.

### D. Registry & image pertama

```bash
gcloud artifacts repositories create titikorder \
  --repository-format=docker --location=asia-southeast2

gcloud builds submit --tag \
  asia-southeast2-docker.pkg.dev/titikorder-dev/titikorder/seller-api:v1 \
  --file apps/seller-api/Dockerfile .
```

### E. Deploy ke Cloud Run

```bash
gcloud run deploy seller-api \
  --image asia-southeast2-docker.pkg.dev/titikorder-dev/titikorder/seller-api:v1 \
  --region asia-southeast2 \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,AUTH_SECRET=AUTH_SECRET:latest \
  --min-instances 0 --max-instances 3 \
  --allow-unauthenticated
```

Ulangi untuk `seller-web`. Cloud Run memberi URL sementara `https://seller-api-xxxx.a.run.app` — **uji dulu lewat URL itu** sebelum menyentuh domain.

Kalau sudah bisa dibuka, separuh pekerjaan selesai.

### F. Sambungkan domain lewat Cloudflare

1. Di Cloud Run → **Manage Custom Domains** → tambahkan `api-dev.titikorder.com`. Google memberi catatan DNS.
2. Di Cloudflare → tambahkan catatan DNS itu, **proxy aktif (awan oranye)**.
3. Ulangi untuk `app-dev.titikorder.com`.
4. Di Cloudflare SSL/TLS, mode **Full (strict)**.

> Kalau *domain mapping* Cloud Run belum tersedia di region Anda, alternatifnya memakai Global External Load Balancer (±$18–25/bulan). Periksa dulu ketersediaannya sebelum menganggarkan.

### G. Lindungi origin — jangan dilewati

Tanpa Load Balancer, URL `*.run.app` tetap bisa diakses langsung, **melewati seluruh proteksi Cloudflare**. Wajib ditutup:

1. Di Cloudflare → **Transform Rules** → tambahkan header, mis. `X-Origin-Secret: <nilai-acak-panjang>`.
2. Di aplikasi, tolak request yang tidak membawa header itu (kecuali health check).
3. Simpan nilainya di Secret Manager.

Tanpa langkah ini, WAF dan rate limit Anda hanyalah hiasan.

---

## 4. Verifikasi sebelum menyatakan berhasil

- [ ] `https://api-dev.titikorder.com/health` menjawab
- [ ] `https://app-dev.titikorder.com` bisa login dengan user seed
- [ ] Sertifikat SSL **hijau tanpa peringatan**
- [ ] URL `*.run.app` langsung **ditolak** (uji dengan `curl`)
- [ ] Cloud SQL **tidak** punya IP publik terbuka
- [ ] Log tampil di Cloud Logging
- [ ] Peran terbatas tidak bisa membuka halaman terlarang lewat URL langsung

---

## 5. Otomatiskan (setelah manual berhasil)

Deploy manual sekali dulu supaya Anda paham alurnya. Setelah itu baru CI/CD:

```
merge ke develop → build image → migrasi DB (job terpisah) → deploy dev
merge ke main    → build image → migrasi DB → deploy prod (canary 10% → 100%)
```

Prompt untuk Claude Code:

```
Buat pipeline Cloud Build: cloudbuild.yaml per app dengan path-based trigger,
build multi-stage, migrasi Prisma sebagai step terpisah (bukan saat service start),
deploy ke Cloud Run dengan traffic split bertahap. Tambahkan workflow GitHub
Actions untuk PR check (lint, typecheck, test). Jangan simpan kredensial di repo;
pakai Workload Identity Federation.
```

---

## 6. Naik ke produksi

Ulangi seluruh langkah di project `titikorder-prod`, dengan perbedaan:

| Aspek | dev | prod |
|---|---|---|
| Cloud SQL | terkecil, tanpa HA | lebih besar, **PITR aktif** |
| `min-instances` | 0 | **1** pada API & web (hindari cold start) |
| Data | palsu | nyata — **backup wajib teruji** |
| Domain | `*-dev.titikorder.com` | `app.` / `api.titikorder.com` |
| Akses | Anda saja | tim, sesuai peran |

**Sebelum pengguna nyata masuk:**

- [ ] Backup otomatis + PITR aktif, dan **restore sudah pernah diuji**
- [ ] Alert: error rate, latensi p95, budget mendekati batas
- [ ] Runbook pemulihan tertulis dan pernah dilatih
- [ ] Rollback pernah dicoba di dev (geser trafik ke revisi lama)
- [ ] Semua rahasia di Secret Manager, tidak ada di repo
- [ ] Proteksi origin aktif

---

## 7. Urutan yang disarankan

1. **Deploy `seller-api` + `seller-web` ke dev**, uji lewat URL `run.app`.
2. Sambungkan domain dev, pastikan SSL bersih.
3. Pakai dev selama beberapa hari sambil menyelesaikan Fase S1.
4. Baru siapkan produksi ketika S1.1 (pencairan J&T) siap dipakai finance.

Jangan menyiapkan produksi sebelum ada yang benar-benar akan memakainya — biayanya berjalan sejak hari pertama, sementara manfaatnya belum ada.
