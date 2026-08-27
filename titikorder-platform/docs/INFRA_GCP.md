# Infrastruktur Google Cloud — TitikOrder

Arsitektur produksi skala perusahaan: **tahan banting, aman, andal, dan mudah dikembangkan**. Dokumen ini menggantikan bagian infrastruktur di `BLUEPRINT.md`.

> **Catatan jujur di depan.** Arsitektur ini lebih kuat daripada Vercel+Supabase, tapi memindahkan beban ke operasional: VPC, IAM, CI/CD, monitoring, dan biaya bulanan yang nyata. Karena dikerjakan solo, ikuti **§10 Tahapan adopsi** — jangan menyalakan semuanya di hari pertama.

---

## 1. Prinsip

1. **Cloud Run, bukan GKE.** Kubernetes menambah beban operasional besar tanpa manfaat pada skala ini. Cloud Run memberi container, autoscaling, scale-to-zero, dan traffic splitting tanpa mengelola node.
2. **Dua domain bisnis, database terpisah.** Seller dan Fulfillment tidak pernah saling `JOIN`.
3. **Sinkron untuk perintah, asinkron untuk status.** REST antar service; Pub/Sub untuk event.
4. **Tanpa rahasia di kode.** Semua kredensial di Secret Manager.
5. **Database tidak pernah publik.** Private IP + VPC egress.
6. **Setiap service punya service account sendiri** dengan hak seminimal mungkin.

---

## 2. Peta service

### Domain Seller

| Service | Isi | Sifat |
|---|---|---|
| `lp-renderer` | landing page publik + endpoint intake form | trafik iklan spiky, publik, di-CDN |
| `seller-web` | back-office (order, CRM, katalog, keuangan, analitik) | internal, ber-auth |
| `seller-api` | API domain seller (sumber kebenaran bisnis) | internal + publik terbatas |
| `seller-worker` | job: tarik Meta Ads, polling tracking, parse pencairan, publikasi outbox | tanpa HTTP publik |

### Domain Fulfillment (mulai S5)

| Service | Isi | Sifat |
|---|---|---|
| `ff-web` | UI gudang (inbound, putaway, picking, packing, outbound) — PWA untuk scanner | internal gudang |
| `ff-api` | API domain fulfillment | internal |
| `ff-worker` | job: konsumsi event, rekonsiliasi stok, tagihan | tanpa HTTP publik |

### Platform bersama

| Komponen | Keterangan |
|---|---|
| `notification` (opsional, nanti) | WhatsApp, email, webhook keluar — dipakai kedua domain |
| Identity Platform | autentikasi terkelola (bukan service yang Anda bangun) |
| Cloudflare | pintu masuk tunggal: TLS, CDN, WAF, anti-DDoS, custom domain seller |

**Kenapa FE dan BE dipisah di sini** (berbeda dari saran awal): dengan dua domain bisnis, beberapa frontend, dan kemungkinan aplikasi scanner/mobile, API domain perlu berdiri sendiri agar bisa dipakai banyak klien. `seller-web` dan `ff-web` tetap boleh punya BFF tipis (server action Next.js) untuk kebutuhan layar, tapi **logika bisnis hanya ada di `*-api`**.

---

## 3. Framework per service

| Service | Framework | Alasan |
|---|---|---|
| `lp-renderer` | **Next.js 15** (App Router, ISR) | render cepat, cocok di-CDN, SEO |
| `seller-web`, `ff-web` | **Next.js 15** + Tailwind + shadcn/ui + TanStack Query | konsisten, komponen dimiliki sendiri |
| `seller-api`, `ff-api` | **NestJS 11** (adapter Fastify) + **Prisma** + Zod | modular, DI, terstruktur untuk jangka panjang, OpenAPI otomatis |
| `seller-worker`, `ff-worker` | NestJS standalone, konsumsi **Pub/Sub push** | satu basis kode dengan API, tanpa server HTTP publik |
| `ff-web` (scanner) | Next.js **PWA** | jalan di perangkat scanner Android, dukung input HID barcode |

Bahasa seragam **TypeScript** di semua service. Kontrak antar service: **OpenAPI** (dari NestJS) + paket tipe bersama + skema event ber-versi.

---

## 4. Domain & subdomain

| Domain | Tujuan | Di depan |
|---|---|---|
| `titikorder.com` | situs marketing | Cloudflare CDN |
| `app.titikorder.com` | back-office seller | Cloudflare → `seller-web` |
| `api.titikorder.com` | API seller | Cloudflare → `seller-api` |
| `wms.titikorder.com` | back-office gudang | Cloudflare → `ff-web` |
| `ff-api.titikorder.com` | API fulfillment | internal saja (ingress internal) |
| `id.titikorder.com` | autentikasi | Identity Platform |
| `cdn.titikorder.com` | aset statis, gambar produk | Cloudflare + GCS |
| `status.titikorder.com` | halaman status | eksternal |
| `lp.titikorder.com/{seller}/{slug}` | **landing page produk — berbasis path** | Cloudflare → `lp-renderer` |
| domain milik seller | LP dengan domain sendiri | **Cloudflare for SaaS** (100 gratis, lalu ±$0,10/hostname) |

**Landing page memakai path, bukan subdomain per LP.** Jumlah LP akan sangat banyak (per SKU, per seller, per uji kreatif); dengan path, menambah LP hanya berarti menambah satu baris database — tanpa DNS, sertifikat, atau aksi infrastruktur. Batas 8 event per domain di Meta AEM yang dulu jadi alasan memisah domain sudah dihapus Meta sejak Juni 2025.

**Domain milik seller sendiri** tetap didukung (per seller, bukan per LP) demi kredibilitas iklan, lewat Cloudflare for SaaS. Simpan pemetaan domain→org di database.

Lingkungan dipisah **per project GCP**: `titikorder-dev` dan `titikorder-prod` (staging ditunda demi anggaran).

**Penting — pola subdomain environment memakai tanda hubung, bukan tingkat kedua**: `app-dev.titikorder.com`, bukan `app.dev.titikorder.com`. Universal SSL gratis Cloudflare hanya mencakup domain utama + subdomain **satu tingkat**; pola dua tingkat menyebabkan peringatan sertifikat dan menuntut Advanced Certificate Manager (±$10/bulan). Rincian di `DEPLOY_GUIDE.md` §1.

---

## 5. Layanan GCP yang dipakai

### Inti

| Kebutuhan | Layanan | Catatan |
|---|---|---|
| Menjalankan service | **Cloud Run** | autoscale, scale-to-zero (kecuali API: `min-instances=1`) |
| Database transaksi | **Cloud SQL for PostgreSQL** | HA multi-zona, PITR, **private IP** |
| Berkas | **Cloud Storage** | PDF resi, label, foto POD, ekspor |
| Event antar service | **Pub/Sub** | topik per domain event + **dead-letter topic** |
| Job terjadwal | **Cloud Scheduler** | tarik Meta harian, polling tracking |
| Job terarah + retry | **Cloud Tasks** | panggilan keluar (webhook, ekspedisi) |
| Rahasia | **Secret Manager** | token Meta, kredensial J&T |
| Image container | **Artifact Registry** | |
| CI/CD | **Cloud Build** atau GitHub Actions | deploy ke Cloud Run |
| Pintu masuk, CDN, WAF | **Cloudflare** (Free/Pro) | menggantikan LB + Armor + CDN; hemat ±$50–95/bln. Wajib Authenticated Origin Pulls agar `*.run.app` tak bisa diakses langsung |
| _(opsional nanti)_ | Global External LB + Cloud Armor + Cloud CDN | bila butuh VPC-SC/IAP atau fitur GCP-native |
| Autentikasi | **Identity Platform** | MFA, SSO, custom claims (org + role) |
| Sertifikat & DNS | **Cloudflare DNS + SSL** | termasuk domain kustom seller (Cloudflare for SaaS) |
| Observability | **Cloud Logging, Monitoring, Trace, Error Reporting** | SLO + alert |

### Pendukung

| Kebutuhan | Layanan |
|---|---|
| Cache & lock terdistribusi | **Memorystore for Redis** (baru saat perlu) |
| Gudang data analitik | **BigQuery** |
| Replikasi OLTP → OLAP | **Datastream** (CDC dari Cloud SQL) |
| Anti-bot pada form LP | **reCAPTCHA Enterprise** |
| Jaringan privat | **VPC** + **Direct VPC egress** Cloud Run |
| Kontrol perimeter (lanjutan) | VPC Service Controls |

---

## 6. Jaringan & keamanan

**Alur trafik:**

```
Pengguna → Cloudflare (TLS, CDN, WAF, DDoS) → Cloud Run
                     │ Authenticated Origin Pulls (mTLS)
                     ↓ Direct VPC egress
           Cloud SQL (private IP)
```

**Aturan keamanan wajib:**

1. **Cloud SQL tanpa IP publik.** Akses hanya lewat VPC dari Cloud Run.
2. **Service account per service**, hak minimal. `seller-api` boleh baca Secret X; `lp-renderer` tidak.
3. **Service internal tidak boleh diakses publik.** `ff-api` dan semua `*-worker` memakai **Cloud Run ingress: internal** + autentikasi ID token antar service (IAM `run.invoker`).
4. **Proteksi endpoint publik**: rate limit per IP pada `/api/intake` + aturan WAF di Cloudflare. Form LP adalah target spam lead — pasangkan **Turnstile** (Cloudflare) atau reCAPTCHA Enterprise.
   Karena origin tidak bisa dibatasi per-IP tanpa LB, **wajib** aktifkan *Authenticated Origin Pulls* (mTLS) atau verifikasi header rahasia di Cloud Run.
5. **Rahasia hanya dari Secret Manager**, di-mount saat runtime. Tidak ada `.env` di image.
6. **RLS Postgres tetap berlaku** — aplikasi konek sebagai `app_user` (non-superuser) dan wajib `SET LOCAL app.current_org`. Ini lapis keamanan terakhir bila ada bug di kode.
7. **Audit ganda**: Cloud Audit Logs (infrastruktur) + tabel `audit_logs` (bisnis).
8. **Cadangan teruji**: PITR aktif + restore diuji terjadwal. Cadangan yang tak pernah diuji dianggap tidak ada.

---

## 7. Data & analitik

- **Cloud SQL** = sumber kebenaran transaksi (OLTP). Dua instance/database: `seller` dan `fulfillment`.
- **BigQuery** = analitik berat (funnel iklan→closing→kirim→cair, Modul 1/3/4/5). Data mengalir lewat **Datastream** (CDC) dari Cloud SQL, **tanpa membebani database produksi**.
- Dashboard bisa memakai modul `analytics` sendiri atau Looker Studio di atas BigQuery.

Pemisahan ini penting: laporan berat tidak boleh memperlambat pencatatan order saat iklan sedang jalan.

---

## 8. CI/CD & lingkungan

```
push ke main → Cloud Build / GitHub Actions
  → lint + test (domain test, schema test)
  → build image → Artifact Registry
  → migrasi DB (job terpisah, bukan saat start service)
  → deploy Cloud Run dengan traffic split 10% → 100%
```

Aturan:
- **Migrasi DB dijalankan sebagai job tersendiri**, tidak di dalam proses start service (mencegah balapan antar instance).
- **Rollback** = arahkan trafik ke revisi Cloud Run sebelumnya (instan).
- Setiap PR dites di `dev`; rilis lewat `staging` sebelum `prod`.

---

## 9. Keandalan

| Aspek | Praktik |
|---|---|
| Ketersediaan | Cloud SQL HA multi-zona; Cloud Run multi-zona otomatis |
| Latensi | `min-instances=1` pada `*-api` dan `lp-renderer` (hindari cold start) |
| Kegagalan sementara | retry + exponential backoff; **dead-letter topic** Pub/Sub |
| Duplikasi pesan | konsumen **idempoten** (Pub/Sub at-least-once) |
| Konsistensi lintas service | **outbox pattern** — tulis event dalam transaksi yang sama |
| Deteksi dini | SLO (ketersediaan, latensi p95, error rate) + alert ke email/WA |
| Beban puncak iklan | LP di-CDN, intake ringan, kerja berat didorong ke queue |

---

## 10. Tahapan adopsi (jangan nyalakan semua sekaligus)

| Tahap | Yang diaktifkan | Kira-kira biaya |
|---|---|---|
| **A. Fase S0–S2** | 1 project, Cloud Run (`lp-renderer`, `seller-web`, `seller-api`, `seller-worker`), Cloud SQL **single-zone**, GCS, Secret Manager, Cloud Scheduler, Logging | rendah |
| **B. Fase S3–S4** | Cloudflare Pro (CDN/WAF), domain kustom seller, Identity Platform, Pub/Sub, monitoring/SLO. **HA Cloud SQL ditunda** demi anggaran | menengah |
| **C. Fase S5** | Database + service Fulfillment, Pub/Sub antar domain, BigQuery + Datastream | menengah–tinggi |
| **D. Skala** | Memorystore, VPC-SC, multi-region, CMEK | sesuai kebutuhan |

Biaya terbesar biasanya **Cloud SQL HA** dan **Load Balancer** — keduanya ditunda ke tahap B. Cloud Run sendiri murah karena scale-to-zero.

---

## 11. Ringkasan integrasi eksternal

| Integrasi | Cara masuk | Layanan GCP terkait |
|---|---|---|
| **J&T** (export, resi, tracking, pencairan) | `CourierAdapter` di `seller-api`/`worker` | Cloud Tasks (panggilan keluar), GCS (berkas), Scheduler |
| **SPX / Everpro / Lincah** | adapter baru, tanpa ubah inti | sama |
| **Meta Ads** | `AdPlatformAdapter`, tarik harian | Scheduler + Secret Manager |
| **TikTok / Google Ads** | adapter baru | sama |
| **WhatsApp** (BSP resmi) | service `notification` | Cloud Tasks, Secret Manager |
| **Payment gateway** (Xendit/Midtrans) | webhook masuk | Cloud Run + WAF Cloudflare + idempotency |
| **Sistem Fulfillment** | REST (perintah) + Pub/Sub (status) | Pub/Sub, IAM ID token |

Semua integrasi tetap lewat **port adapter** — menambah ekspedisi atau platform iklan baru tidak menyentuh modul inti.
