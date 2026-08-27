# Menjalankan di Komputer Sendiri (Lokal)

Panduan menyiapkan lingkungan lokal supaya bisa **mencoba aplikasi web secara manual** sebelum menyentuh Google Cloud.

Prinsipnya: lokal harus **semirip mungkin** dengan produksi (Postgres versi sama, RLS aktif, role `app_user`), tapi **tanpa satu pun layanan berbayar**.

---

## 1. Yang perlu dipasang

| Alat | Versi | Kegunaan | Cara pasang (Windows) |
|---|---|---|---|
| **Node.js** | 20 LTS atau 22 | menjalankan semua service | `winget install OpenJS.NodeJS.LTS` |
| **pnpm** | 9+ | manajer paket monorepo | `npm install -g pnpm` |
| **Docker Desktop** | terbaru | menjalankan PostgreSQL | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Git** | — | sudah ada | — |
| **DBeaver** (opsional) | — | melihat isi database | `winget install dbeaver.dbeaver` |

**Kenapa Docker untuk Postgres, bukan installer?** Versinya bisa dikunci sama persis dengan Cloud SQL, mudah dihapus/ulang bila rusak, dan tidak meninggalkan service Windows yang berjalan diam-diam.

Kalau tidak ingin memakai Docker, PostgreSQL 16 versi installer juga bisa — bagian berikutnya tinggal disesuaikan.

---

## 2. Jalankan PostgreSQL

Buat `docker-compose.yml` di root repo:

```yaml
services:
  db:
    image: postgres:16
    container_name: titikorder-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: titikorder
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data:
```

Nyalakan:

```bash
docker compose up -d
docker compose ps          # pastikan status "running"
```

---

## 3. Terapkan skema & buat role aplikasi

```bash
# terapkan skema yang sudah tervalidasi
docker exec -i titikorder-db psql -U postgres -d titikorder < db/schema.sql

# beri password untuk role app_user (dibuat oleh schema.sql, awalnya NOLOGIN)
docker exec -i titikorder-db psql -U postgres -d titikorder -c "ALTER ROLE app_user LOGIN PASSWORD 'devpassword';"
```

> ⚠️ **Jebakan paling sering:** aplikasi **harus** konek sebagai `app_user`, bukan `postgres`.
> Superuser mem-*bypass* RLS, sehingga isolasi antar-tenant mati tanpa pesan error apa pun — dan Anda baru sadar setelah data seller bocor di produksi. Kalau lokal memakai `postgres`, bug isolasi tidak akan pernah terlihat saat pengujian.

Verifikasi cepat bahwa RLS benar-benar aktif:

```bash
python db/test_schema.py     # 7 pemeriksaan harus lulus
```

---

## 4. Berkas environment

Tiap app punya `.env.local` sendiri (jangan pernah di-commit — sudah masuk `.gitignore`):

```bash
# apps/seller-api/.env.local
DATABASE_URL="postgresql://app_user:devpassword@localhost:5432/titikorder"
NODE_ENV=development
PORT=3001
AUTH_SECRET="ganti-dengan-string-acak-panjang"
```

```bash
# apps/seller-web/.env.local
NEXT_PUBLIC_API_URL="http://localhost:3001"
AUTH_SECRET="samakan-dengan-seller-api"
```

Buat `AUTH_SECRET` acak:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

---

## 5. Autentikasi saat lokal

Identity Platform butuh project GCP — itu menghambat pengujian lokal. Untuk tahap ini pakai **Auth.js dengan credentials provider** (email + kata sandi) yang datanya ada di database sendiri:

- Jalan penuh offline, tanpa biaya, tanpa setup cloud.
- Peran & permission tetap dari tabel `roles` / `role_permissions` kita.
- Bila kelak butuh SSO/MFA untuk seller eksternal, Auth.js tinggal ditambah provider — bukan ditulis ulang.

Konsekuensinya: `INFRA_GCP.md` menyebut Identity Platform; itu tetap berlaku sebagai **opsi masa depan**, bukan keharusan sekarang.

---

## 6. Seed data awal

Minimal yang harus ada agar bisa login dan mencoba:

1. Satu organisasi (`Meika Berkarya`, type `both`)
2. Role bawaan + permission (sudah di-seed oleh `schema.sql`)
3. Satu user `owner` dengan kata sandi yang Anda tentukan
4. Beberapa SKU contoh

```bash
pnpm db:seed
```

Untuk pengujian yang benar-benar berguna, impor **berkas nyata** yang selama ini dipakai di Apps Script (export J&T, export OrderOnline) lewat menu impor di aplikasi — bukan data karangan. Hanya dengan data asli Anda akan menemukan kasus tepi seperti `product_code` ganda atau alias purchase Meta.

---

## 7. Jalankan aplikasi

```bash
pnpm install
pnpm dev
```

| Aplikasi | Alamat lokal |
|---|---|
| Back-office seller | http://localhost:3000 |
| API seller | http://localhost:3001 |
| Landing page (nanti) | http://localhost:3002 |

Masuk dengan user `owner` hasil seed.

---

## 8. Perintah harian

```bash
docker compose up -d          # nyalakan database
docker compose stop           # matikan (data tetap aman)
docker compose down -v        # HAPUS database beserta datanya — hati-hati

pnpm dev                      # jalankan semua app
pnpm --filter seller-api dev  # satu app saja
pnpm db:migrate               # terapkan migrasi baru
pnpm db:studio                # lihat isi DB lewat Prisma Studio

npx tsx packages/core/order.test.ts   # tes domain (cepat)
python db/test_schema.py               # tes perilaku skema
```

---

## 9. Kalau bermasalah

| Gejala | Kemungkinan sebab | Tindakan |
|---|---|---|
| Query mengembalikan kosong padahal data ada | `SET LOCAL app.current_org` belum dijalankan | cek helper `tx()`; ini perilaku **fail-closed** yang disengaja |
| Semua tenant terlihat | konek sebagai `postgres`, bukan `app_user` | perbaiki `DATABASE_URL` |
| `password authentication failed` | `app_user` belum diberi password | ulangi langkah 3 |
| Port 5432 bentrok | ada Postgres lain berjalan | ubah ke `"5433:5432"` lalu sesuaikan `DATABASE_URL` |
| Perubahan skema tidak muncul | migrasi belum dijalankan | `pnpm db:migrate` |

---

## 10. Beda lokal vs produksi

| | Lokal | Produksi |
|---|---|---|
| Database | Docker Postgres 16 | Cloud SQL PostgreSQL |
| Auth | Auth.js credentials | Auth.js (opsional + Identity Platform) |
| Berkas | folder lokal | Cloud Storage |
| Job terjadwal | dijalankan manual | Cloud Scheduler |
| Rahasia | `.env.local` | Secret Manager |

Yang **sama persis**: versi Postgres, skema, RLS, role `app_user`, dan seluruh aturan integritas. Inilah yang membuat pengujian lokal bermakna.
