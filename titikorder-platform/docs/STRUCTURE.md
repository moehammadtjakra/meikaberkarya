# Struktur Kode & Pola Ekstensi

Panduan struktur folder Sistem Seller, dan **cara menambah ekspedisi / platform iklan baru tanpa membedah kode inti**.

---

## 1. Kenapa dibagi begini

Pemisahan app **bukan** frontend vs backend (Next.js App Router sudah full-stack — memisahkannya berarti menulis API untuk setiap hal sepele). Pemisahan dilakukan berdasarkan **profil trafik & siklus hidup**:

| App | Profil | Alasan terpisah |
|---|---|---|
| `apps/lp` | publik, trafik iklan spiky | lonjakan iklan tidak boleh menjatuhkan operasional; di-deploy ke edge/CDN dengan ISR |
| `apps/web` | internal, trafik stabil, ber-auth | back-office CS/gudang/finance |
| `apps/worker` | tanpa HTTP | job lama (tarik Meta, polling tracking, parse settlement) tidak boleh menahan request |

Semua berbagi `packages/*`. Karena `packages/core` dan `packages/db` bebas dari framework, kelak bisa diangkat jadi API service tersendiri **tanpa refactor** bila benar-benar dibutuhkan.

---

## 2. Pohon folder

```
titikorder/
├── CLAUDE.md
├── package.json · pnpm-workspace.yaml · turbo.json
│
├── docs/
│   ├── BLUEPRINT.md          arsitektur & stack
│   ├── PLAN_SELLER.md        rencana fase S0–S5
│   ├── SPLIT_PLAN.md         Seller DB vs Fulfillment DB
│   ├── STRUCTURE.md          dokumen ini
│   └── adr/                  catatan keputusan (kenapa X, bukan Y)
│
├── apps/
│   ├── lp/                   Next.js publik
│   │   ├── app/[org]/[slug]/page.tsx      render landing page dari DB
│   │   └── app/api/intake/route.ts        submit form (idempoten)
│   │
│   ├── web/                  Next.js back-office
│   │   ├── CLAUDE.md         konvensi modul & UI
│   │   └── src/
│   │       ├── app/          routing & halaman (tipis)
│   │       ├── lib/          db.ts, auth.ts, queue.ts
│   │       └── modules/      ← DOMAIN
│   │           ├── iam/          org, user, role, audit
│   │           ├── catalog/      produk, SKU, barcode, offer, bundle, pricing
│   │           ├── storefront/   CMS, LP builder, konfigurasi pixel
│   │           ├── orders/       intake, state machine, routing gudang
│   │           ├── crm/          assignment, followup, WhatsApp
│   │           ├── inventory/    stok gudang seller + read-model stok FS
│   │           ├── procurement/  permintaan pembelian
│   │           ├── shipping/     resi, export, tracking, undel, retur
│   │           ├── finance/      pencairan COD, rekonsiliasi, P&L
│   │           ├── ads/          tarik & labeli campaign → SKU
│   │           └── analytics/    Modul 1/3/4/5 + funnel
│   │
│   └── worker/               job latar (Pub/Sub push + Scheduler)
│       └── jobs/{pullAds,pollTracking,parseSettlement,reconcile}.ts
│
├── packages/
│   ├── core/                 domain logic MURNI — tanpa I/O
│   │   ├── order.ts          state machine, telepon, total, offer  (19 tes lulus)
│   │   ├── routing.ts        pilih gudang pemenuh
│   │   ├── pricing.ts        bundle/bump/promo
│   │   └── features.ts       entitlement general vs internal
│   ├── db/                   Prisma schema, migrasi, seed
│   ├── contracts/            skema Zod + tipe event (versioned)
│   ├── ui/                   komponen bersama (shadcn)
│   └── integrations/
│       ├── CLAUDE.md         cara menambah adapter
│       ├── courier/
│       │   ├── core/         interface CourierAdapter + tipe ternormalisasi
│       │   ├── jnt/          aktif
│       │   ├── spx/          menyusul
│       │   └── everpro/      agregator, menyusul
│       └── ads/
│           ├── core/         interface AdPlatformAdapter
│           ├── meta/         aktif (port dari MetaAds.gs)
│           └── tiktok/       menyusul
│
└── db/                       schema.sql + test_schema.py
```

**Aturan penamaan modul:** organisasi berdasarkan **domain**, bukan lapisan teknis. Tidak ada folder `controllers/`, `services/`, `models/` di level atas.

Isi tiap modul:
```
modules/orders/
├── ui/              komponen & halaman khusus modul
├── server/          logic sisi server (query, mutation)
├── schema.ts        Zod
└── index.ts         API publik modul (satu-satunya pintu masuk)
```
Modul lain **hanya boleh** mengimpor dari `index.ts` modul tetangga — bukan menembus ke `server/` internalnya. Ini yang menjaga batas tetap tegas.

---

## 3. Pola adapter — jantung "fitur khusus"

Masalah nyata: **format tiap ekspedisi berbeda**, dan daftarnya bertambah (J&T → SPX → Everpro/Lincah). Kalau logika J&T menyebar di modul `shipping`, menambah SPX berarti membedah kode inti.

### CourierAdapter

```ts
// packages/integrations/courier/core/types.ts
export interface CourierAdapter {
  code: string
  label: string

  /** Order internal → berkas upload sesuai format ekspedisi ini */
  exportOrders(orders: ExportableOrder[]): Promise<ExportFile>

  /** Berkas/API balasan ekspedisi → nomor resi per order */
  importWaybills(input: FileInput): Promise<WaybillAssignment[]>

  /** Data tracking mentah → event ternormalisasi */
  importTracking(input: FileInput | ApiParams): Promise<NormalizedTrackingEvent[]>

  /** Laporan pencairan → baris settlement ternormalisasi */
  importSettlement(input: FileInput): Promise<NormalizedSettlement[]>

  /** Opsional: baca PDF resi (format berbeda tiap client) */
  parseWaybillPdf?(pdf: Buffer): Promise<WaybillInfo>
}
```

Modul `shipping` hanya mengenal interface ini dan sebuah registry:

```ts
const couriers: Record<string, CourierAdapter> = { jnt, spx, everpro }
```

**Menambah SPX = membuat satu folder baru + mendaftarkannya.** Nol perubahan di modul inti.

Semua adapter **wajib** mengubah data ke bentuk ternormalisasi yang sama, agar analitik (`finance`, `analytics`) tidak perlu tahu asal ekspedisinya.

### AdPlatformAdapter

```ts
export interface AdPlatformAdapter {
  code: 'meta' | 'tiktok' | 'google'
  fetchDailyStats(range: DateRange, account: string): Promise<NormalizedAdStat[]>
  // purchase/konversi dikembalikan sebagai satu nilai kanonik —
  // jangan menjumlahkan alias (pelajaran dari Meta: 1 purchase muncul di banyak label)
}
```

Modul `ads` dan `analytics` bekerja di atas `NormalizedAdStat`, sehingga menambah TikTok tidak menyentuh Modul 5.

---

## 4. General vs internal — pakai entitlement

Fitur yang baru berlaku internal **tidak** dipisah basis kodenya. Cukup ditandai:

```ts
// packages/core/features.ts
export const FEATURES = {
  'storefront.builder':   'general',   // semua seller
  'crm.followup':         'general',
  'catalog.sku':          'general',
  'inventory.basic':      'general',

  'shipping.export.jnt':  'internal',  // baru untuk internal
  'finance.settlement':   'internal',
  'ads.meta.analytics':   'internal',
} as const
```

Disimpan per org di tabel entitlement; dicek di server (bukan sekadar disembunyikan di UI). Saat seller lain bergabung, cukup **menyalakan flag** — tanpa rilis versi berbeda.

---

## 5. Satu sesi Claude Code untuk semuanya

Monorepo membuat satu sesi Claude Code melihat seluruh konteks. Yang membantu:

- `CLAUDE.md` di root — aturan lintas proyek (dibaca otomatis)
- `CLAUDE.md` bersarang di `apps/web/` dan `packages/integrations/` — konvensi lokal, dibaca saat bekerja di sana
- `docs/` — keputusan arsitektur; rujuk file-nya saat memberi tugas, mis. *"ikuti docs/PLAN_SELLER.md fase S1"*
- `docs/adr/` — catat keputusan penting beserta alasannya, supaya tidak diperdebatkan ulang

**Buat repo git tersendiri.** Jangan digabung dengan repo dashboard J&T — repo itu punya `CLAUDE.md` sendiri dengan konteks berbeda, dan mencampurnya membuat aturan saling bertabrakan.

---

## 6. Urutan memulai (S0)

1. `git init` di repo baru, salin `CLAUDE.md`, `docs/`, `db/`, `packages/core/order.ts`.
2. Inisiasi workspace: pnpm + turbo, lalu `create-next-app` untuk `apps/web` dan `apps/lp`.
3. `packages/db`: Prisma, generate dari `db/schema.sql` (Seller DB saja — lihat `SPLIT_PLAN.md`).
4. `lib/db.ts`: pool Postgres + helper `tx()` yang **otomatis** `SET LOCAL app.current_org`.
5. Auth (Identity Platform) + modul `iam` + `catalog`.
6. Definisikan port `FulfillmentProvider` + `SelfManualProvider` (walau isinya masih sederhana).

Selesai S0 = bisa login, kelola produk/SKU/offer, dengan RLS aktif dan port sudah terpasang.
