# Standar Desain UI/UX — TitikOrder

Aturan tampilan & pengalaman pengguna. Berlaku untuk **semua** layar di `seller-web` dan `ff-web`.

Dokumen ini setara `CLAUDE.md`: bukan saran, tapi **standar yang ditegakkan**.

---

## 1. Siapa yang memakai sistem ini

Desain harus tunduk pada kenyataan ini, bukan pada selera:

| Pengguna | Perangkat | Cara kerja | Implikasi desain |
|---|---|---|---|
| Admin order | desktop | impor berkas, olah batch, banyak data | tabel padat, filter kuat, keyboard |
| CS undel | **HP** | followup berulang, sambil menelepon | mobile-first, satu tangan, aksi cepat |
| Staf gudang | **HP / scanner** | berdiri, tangan kotor, terburu-buru | tombol besar, input barcode, minim ketik |
| Finance | desktop | rekonsiliasi, angka besar | tabel + ekspor, angka rapi |
| Advertiser | desktop | analisis, banding-membandingkan | grafik, rentang tanggal |
| Owner | HP & desktop | lihat ringkasan kapan saja | ringkasan dulu, detail belakangan |

**Mayoritas bukan orang teknis.** Mereka tidak akan membaca manual, tidak akan menebak, dan tidak akan melapor kalau bingung — mereka hanya akan kembali memakai Google Sheets. Itulah standar kegagalan yang sesungguhnya.

---

## 2. Prinsip

1. **Satu layar, satu tujuan.** Kalau sebuah halaman menjawab dua pertanyaan berbeda, pecah jadi dua.
2. **Aksi utama harus paling terlihat.** Satu tombol primer per layar. Sisanya sekunder atau tersembunyi di menu.
3. **Tunjukkan keadaan, jangan biarkan menebak.** Setiap layar punya empat status wajib (§6).
4. **Kecepatan input di atas keindahan.** Untuk CS & gudang, jumlah ketukan lebih penting daripada estetika.
5. **Jangan pernah kehilangan pekerjaan pengguna.** Form panjang harus tahan refresh dan koneksi putus.
6. **Bahasa Indonesia yang manusiawi.** Bukan istilah teknis, bukan terjemahan kaku.

---

## 3. Responsif: mobile terasa seperti aplikasi

Bukan sekadar "muat di layar kecil" — di HP harus **terasa seperti aplikasi**, bukan situs yang dikecilkan.

| Aspek | Mobile (<640px) | Desktop (≥1024px) |
|---|---|---|
| Navigasi | **bottom navigation** 3–5 ikon, jempol menjangkau | sidebar kiri, tetap terlihat |
| Detail data | **full-screen sheet** yang naik dari bawah | modal atau panel samping |
| Tabel | **kartu bertumpuk** (lihat §5) | tabel penuh |
| Filter | sheet "Filter" + jumlah filter aktif | inline di atas tabel |
| Aksi utama | tombol lebar penuh, menempel di bawah | tombol di kanan atas |
| Judul | header ringkas + tombol kembali | breadcrumb |

**Wajib diterapkan:**

- **PWA**: `manifest.json`, `display: standalone`, ikon, warna tema — sehingga bisa "Add to Home Screen" dan terbuka tanpa address bar.
- **Target sentuh minimal 44×44 px.** Jangan ada tombol kecil berdempetan.
- **Aman dari poni layar**: gunakan `env(safe-area-inset-*)` untuk bottom nav.
- **Tidak ada interaksi yang bergantung pada hover.** Hover tidak ada di HP.
- **Input yang tepat**: `inputmode="numeric"` untuk angka, `type="tel"` untuk telepon — agar papan ketik HP muncul benar.
- **Jangan pernah menyembunyikan aksi penting** di balik hover, klik kanan, atau gestur tersembunyi.

Breakpoint: `<640` mobile · `640–1023` tablet · `≥1024` desktop.

---

## 4. Navigasi

- Maksimal **2 tingkat** kedalaman menu. Kalau butuh tiga, struktur informasinya salah.
- Menu disusun **berdasar pekerjaan**, bukan berdasar tabel database. "Pencairan J&T", bukan "Settlements".
- **Menu yang tidak boleh diakses peran itu, disembunyikan** — tapi tetap dijaga server (lihat `PLAN_MIGRASI.md` §4).
- Selalu ada jalan kembali yang jelas. Pengguna harus tahu posisinya.

---

## 5. Menampilkan data (tabel adalah inti sistem ini)

**Desktop:** tabel dengan kolom yang bisa diurutkan, filter, pencarian, dan pilih-banyak.

**Mobile:** tabel **dilarang** digulir horizontal. Ubah jadi kartu:

```
┌─────────────────────────────┐
│ Sikat Punggung        🟢 OK │   ← identitas + status
│ JP1234567890                │   ← pengenal utama
│ Rp 69.500 · 2 pcs           │   ← 2–3 data terpenting saja
│                    [Detail] │   ← satu aksi
└─────────────────────────────┘
```

Aturan tabel:

- **Paginasi wajib** di atas 50 baris. Jangan pernah memuat 10.000 baris sekaligus.
- Kolom terpenting di kiri; kolom teknis (ID, timestamp) disembunyikan secara bawaan.
- **Angka rata kanan**, teks rata kiri. Rupiah selalu berformat `Rp 1.234.567`.
- Tanggal format Indonesia: `23 Agu 2026`, bukan `2026-08-23`.
- Status memakai **warna + teks**, tidak pernah warna saja (buta warna + cetak hitam-putih).
- Sediakan **ekspor** untuk layar yang dipakai finance.

---

## 6. Empat status wajib di setiap layar

Ini penyebab bug UI paling sering: developer hanya membuat status "berhasil dengan data".

| Status | Yang harus ditampilkan |
|---|---|
| **Memuat** | skeleton yang menyerupai bentuk kontennya — bukan spinner di tengah layar |
| **Kosong** | penjelasan singkat + **tombol aksi berikutnya** ("Belum ada order. Impor dari OrderOnline →") |
| **Error** | apa yang salah, dalam bahasa manusia + tombol **Coba lagi** |
| **Berisi** | data |

Tambahan: **status "tidak ada hasil filter"** berbeda dari "kosong" — sediakan tombol "Hapus filter".

Contoh error yang **salah**: `Error: 500 Internal Server Error`.
Contoh yang **benar**: "Gagal memuat data pencairan. Periksa koneksi Anda, lalu coba lagi." + tombol.

---

## 7. Form & input

- **Label selalu terlihat** di atas kolom. Jangan pakai placeholder sebagai label.
- **Validasi saat blur**, bukan saat mengetik huruf pertama. Pesan galat tepat di bawah kolom.
- Skema validasi memakai **Zod yang sama dengan backend** — tidak boleh ada dua sumber aturan.
- **Autofocus** pada kolom pertama; **Enter** mengirim; **Esc** menutup sheet.
- **Cegah kirim ganda**: tombol dinonaktifkan + status memuat selama proses.
- Form panjang: **simpan otomatis sebagai draf** supaya refresh tidak menghapus pekerjaan.
- Kolom telepon: normalisasi otomatis ke `62xxx` dan tampilkan hasilnya, agar pengguna sadar.
- Untuk gudang: dukung **input barcode scanner** (perangkat HID mengetik cepat lalu Enter).

---

## 8. Aksi berbahaya

- Hapus, batalkan order, koreksi stok, ubah harga → **wajib dialog konfirmasi** yang menyebutkan dampaknya secara spesifik: *"Hapus 3 order terpilih? Tindakan ini tidak bisa dibatalkan."*
- Untuk aksi sangat berisiko (koreksi stok massal), minta pengguna **mengetik ulang** nama/jumlahnya.
- Sediakan **Urungkan** lewat toast bila memungkinkan — lebih baik daripada konfirmasi berlapis.
- Tombol berbahaya **berwarna merah dan bukan tombol primer** pada layar itu.

---

## 9. Bahasa

Tulis untuk orang yang tidak pernah membaca dokumentasi:

| Jangan | Pakai |
|---|---|
| Waybill | No. Resi |
| Settlement | Pencairan |
| Undelivered | Paket Gagal Antar |
| Idempotency error | Data ini sudah pernah dikirim |
| Submit | Simpan / Kirim |
| Invalid input | Nomor HP belum benar |
| Sync failed | Gagal mengambil data dari J&T |

Aturan: **istilah yang sudah dipakai tim sehari-hari menang** atas istilah teknis yang "benar". `SKU` boleh, karena tim Anda memang memakainya.

---

## 10. Token desain

Gunakan token, jangan nilai acak. Semua lewat Tailwind + shadcn/ui.

- **Warna semantik**: `primary` (aksi), `success` (hijau), `warning` (kuning), `danger` (merah), `muted` (sekunder). Warna status wajib punya pasangan teks.
- **Jarak**: kelipatan 4px. Padding kartu 16px mobile, 24px desktop.
- **Radius**: konsisten satu nilai (8px) untuk kartu & tombol.
- **Tipografi**: maksimal 4 ukuran. Angka penting boleh lebih besar, sisanya seragam.
- **Bayangan**: seminimal mungkin. Gunakan garis batas tipis untuk memisahkan.
- **Mode gelap**: opsional, tapi kalau dibuat harus **semua warna lewat token** — jangan hardcode.

---

## 11. Aksesibilitas (juga mencegah bug)

- Semua input punya `<label>` yang tertaut.
- Navigasi **penuh dengan keyboard**: Tab, Enter, Esc. Cincin fokus terlihat.
- Kontras teks minimal **4.5:1**.
- Ikon tanpa teks wajib punya `aria-label`.
- Pakai **komponen shadcn/ui (Radix)** — aksesibilitas & fokus sudah benar dari sananya. Jangan membuat dropdown/dialog sendiri dari nol.

---

## 12. Aturan teknis anti-bug

1. **Server state pakai TanStack Query** — bukan `useEffect` + `fetch` manual. Loading, error, cache, refetch jadi konsisten.
2. **Form pakai react-hook-form + Zod**. Tidak ada validasi manual tersebar.
3. **Error boundary per rute** — satu komponen rusak tidak boleh membuat seluruh aplikasi blank.
4. **Toast untuk umpan balik**, bukan `alert()`.
5. **Jangan optimistic update** pada aksi yang menyentuh uang atau stok. Tunggu jawaban server.
6. **Semua daftar wajib `key` stabil** dari ID, bukan indeks array.
7. **Jangan format angka/tanggal manual** — pakai satu helper bersama (`Intl` dengan locale `id-ID`).
8. **Zona waktu**: simpan UTC, tampilkan WIB. Jangan pernah mengandalkan zona waktu browser untuk logika bisnis.
9. **Skeleton, bukan layout yang melompat.** Sediakan ruang dengan tinggi tetap agar konten tidak menggeser.

---

## 13. Checklist selesai (per layar)

Sebuah layar **belum selesai** sampai semua ini terpenuhi:

- [ ] Empat status ditangani: memuat, kosong, error, berisi
- [ ] Dicoba di lebar **360px** (HP kecil) tanpa gulir horizontal
- [ ] Dicoba di desktop 1440px tanpa ruang kosong berlebihan
- [ ] Bisa dioperasikan **hanya dengan keyboard**
- [ ] Aksi utama jelas; aksi berbahaya berkonfirmasi
- [ ] Tidak bisa dikirim dua kali (double submit)
- [ ] Teks berbahasa Indonesia, tanpa jargon teknis
- [ ] Angka & tanggal berformat Indonesia
- [ ] Daftar besar berpaginasi
- [ ] Peran tanpa izin **tidak bisa membuka lewat URL langsung**

---

## 14. Cara menguji sebelum menyatakan selesai

1. **Buka di HP asli**, bukan hanya emulator browser. Rasakan ukuran tombolnya.
2. **Aktifkan throttling jaringan "Slow 3G"** — apakah skeleton muncul? apakah tombol ganda tercegah?
3. **Kosongkan datanya** — apakah status kosong membantu, atau hanya layar putih?
4. **Isi 1.000 baris** — apakah masih responsif?
5. **Matikan API** — apakah muncul pesan yang bisa dimengerti, atau aplikasi blank?
6. **Login sebagai peran terbatas**, ketik URL halaman terlarang — harus ditolak.

Kalau salah satu gagal, layar itu belum selesai — sebagus apa pun tampilannya.
