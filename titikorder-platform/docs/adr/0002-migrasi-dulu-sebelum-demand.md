# ADR 0002 — Migrasi 3 sistem Apps Script dulu, sebelum membangun demand

**Status:** Diterima · 2026-08-23 · menggantikan urutan fase di ADR sebelumnya dan `PLAN_SELLER.md` §8 versi awal

---

## Konteks

Rencana awal menempatkan **S1 = Demand** (landing page + form intake + CRM closing) sebagai fase pertama setelah fondasi, dengan tujuan melepas ketergantungan pada OrderOnline.

Namun kenyataan operasional hari ini: karyawan menjalankan pekerjaan harian di **tiga sistem Apps Script + Google Sheets**:

1. **Admin Order System** — impor order OrderOnline, cek & alokasi stok, HPP, buat batch upload J&T, tarik nomor resi, handover harian.
2. **CS Undelivered System** — unggah data paket gagal antar, distribusi ke CS per provinsi, followup, unggah foto POD.
3. **JnT GSheet System** — unggah export J&T (All Resi + Settle Reconcile), pantau status kirim & **pencairan dana**, plus penarikan **Meta Ads** untuk analisis iklan.

Sistem-sistem itu berjalan, dipakai tiap hari, dan sudah terbukti secara bisnis — tetapi tersebar di beberapa spreadsheet, tanpa hak akses yang rapi, tanpa audit, dan rawan salah karena bergantung pada disiplin manual.

## Keputusan

**Tukar urutan fase.** Setelah fondasi (S0), kerjakan **migrasi tiga sistem tersebut** lebih dulu. Demand (landing page, intake, CRM) digeser ke fase berikutnya.

Urutan baru:

| Fase | Isi |
|---|---|
| **S0** | Fondasi: IAM, org+RLS, **RBAC + matriks permission**, katalog/SKU, audit log |
| **S1** | **Migrasi operasional**: admin order, CS undelivered, J&T (resi + pencairan), Meta Ads |
| **S2** | Demand: landing page + form intake + CRM closing |
| **S3** | Stok lanjutan, procurement, keuangan menyeluruh |
| **S4** | Analitik penuh (Modul 1/3/4/5 + funnel) |
| **S5** | Pisah tuntas ke Sistem Fulfillment |

## Alasan

1. **Risiko lebih rendah.** Ini *migrasi*, bukan penemuan. Model data, aturan bisnis, dan format berkasnya sudah diketahui dan sudah tervalidasi lewat data nyata.
2. **Nilai langsung terasa.** Begitu S1 selesai, karyawan berpindah ke satu aplikasi dengan hak akses & audit yang benar — tanpa menunggu CRM/landing page jadi.
3. **Bisa berjalan paralel.** Di fase ini order **masih lahir di OrderOnline**; aplikasi baru berperan *impor → olah → ekspor*, sama seperti Apps Script sekarang. Sistem lama boleh tetap hidup sampai yang baru terbukti.
4. **Adopsi lebih mudah.** Pengguna sudah mengenal alur kerjanya; yang berubah hanya antarmukanya, bukan prosesnya.
5. **Fondasi data untuk fase berikutnya.** Order, resi, stok, pencairan, dan iklan sudah masuk Postgres — sehingga CRM dan landing page nanti tinggal menyambung, bukan memulai dari kosong.

## Konsekuensi

**Positif:** operasional pindah lebih cepat; data terpusat lebih awal; sistem lama bisa dipensiunkan bertahap per modul.

**Negatif yang diterima:** ketergantungan pada OrderOnline **belum** lepas di akhir S1 — itu baru terjadi di S2. Perlu disampaikan ke tim agar ekspektasinya benar.

**Risiko:** menjalankan dua sistem berdampingan (Apps Script & web app) berpotensi menimbulkan data ganda atau tak sinkron.
**Mitigasi:** tetapkan satu sumber kebenaran per modul saat migrasi, jalankan paralel maksimal 2–4 minggu dengan rekonsiliasi harian, lalu matikan yang lama.

## Catatan pelaksanaan

- Importer di web app **wajib menerima format berkas yang sama** dengan yang dipakai Apps Script hari ini (export J&T, export OrderOnline). Jangan menuntut tim mengubah cara mengambil data.
- Logika yang sudah terbukti di Apps Script & dashboard Streamlit **di-port**, bukan ditulis ulang dari nol — lihat `HANDOVER.md` §2 dan §3.
- RBAC harus selesai di S0, karena migrasi ini langsung melibatkan banyak peran (admin order, CS, supervisor, finance, advertiser).
