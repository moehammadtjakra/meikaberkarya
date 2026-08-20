# Sistem 2 — Tim CS: Followup Paket Undelivered (Panduan Pasang)

Web app untuk tim CS. Tiap CS login dengan akun Google dan **hanya melihat resi pada provinsi tanggung jawabnya**. Menulis ke sheet `MASTER_Undelivered` yang sama dengan Sistem 1.

File:
- `Code.gs` — backend.
- `Index.html` — front-end (Worklist + Report).

---

## Yang bisa dilakukan CS

- **Worklist** resi wilayahnya, difilter per Status Ekspedisi & Status Followup, plus pencarian (resi/nama/telepon).
- Klik resi → **detail lengkap** (penerima, telepon, alamat, barang, nilai COD, keterangan).
- Tombol **Chat WhatsApp** langsung ke nomor penerima.
- **Template pesan** siap pakai — otomatis terisi data resi (nama, no. resi, barang, kota) → tombol **Salin**.
- Update **Kategori Masalah**, **Status Followup**, **Hasil Konfirmasi** (Terima/Cancel/dll), dan **Catatan CS**.
- **Upload foto POD Pembanding** (bisa langsung dari kamera HP) → tersimpan ke Drive, link masuk ke sheet.
- Tab **Report Saya**: total resi wilayah, belum difollowup, selesai, POD terkumpul, grafik status followup, kategori masalah, dan sebaran provinsi.

### Akses per peran

| Peran | Yang dilihat |
|---|---|
| **CS** | hanya resi di provinsi yang ditugaskan padanya (lewat panel Sistem 1) |
| **superadmin** | **seluruh wilayah** — worklist, report, followup, upload POD, semuanya penuh. Tidak perlu (dan tidak boleh) dipetakan ke provinsi mana pun; di panel Sistem 1, kartu superadmin memang sengaja tidak punya pemilih provinsi. Superadmin juga dapat filter tambahan **"Semua CS"** untuk menyaring per CS. |

> Status **"Sedang Retur" sudah dihapus** dari sistem (tidak dipakai lagi). Tab dan filter kini hanya *Semua · Sedang Diantar · Retur · Report*.

### Label Tracking J&T

Kalau supervisor sudah menjalankan **Tracking J&T** di Sistem 1, tiap resi membawa **catatan terakhir dari sistem J&T**:

- **Filter "Label Tracking J&T"** di baris filter — isinya diambil dari **data nyata di wilayah Anda**, bukan daftar tetap. Kalau J&T menambah label baru, otomatis muncul tanpa ubah kode. Ada juga opsi *"— belum pernah dicek —"*.
- **Badge ungu** di kartu resi (mis. 🚚 *Sedang Tertunda*) + keterangan, waktu, dan posisi terakhir paket.
- Di **modal followup**, ada kotak ungu *"Catatan terakhir sistem J&T"* berisi label, keterangan, posisi, nama & HP kurir, dan yang terpenting: **klaim ekspedisinya** — mis. *"Penerima menolak menerima paket"*.

**Cara pakainya:** baca klaim itu **sebelum** menelepon konsumen. Tanyakan langsung apakah benar. Kalau konsumen membantah, catat di **Hasil POD Pembanding** — itulah bukti sengketa Anda, dan otomatis masuk ke laporan *Integritas Klaim Kurir* milik supervisor.

**Kategori Masalah kini terisi otomatis** dari klaim resmi J&T, bukan diketik CS. Dropdown-nya pun disusun ulang dari alasan yang benar-benar muncul di lapangan (lihat panduan Sistem 1 §5d), jadi kata-katanya persis sama dengan catatan ekspedisi.

### Lembar kerja: sub-tab status + sidebar kategori

Di dalam tab **Sedang Diantar**, worklist kini terbagi otomatis:

- **Sub-tab di atas** per **Status Followup** (Belum Followup · Dalam Proses · No Respon · Tidak Dapat Dihubungi · Selesai), tiap tab menampilkan **jumlah resi**. Klik untuk fokus ke satu status.
- **Sidebar kiri** per **Kategori Masalah** (dari hasil tracking J&T), juga dengan jumlahnya. Klik untuk menyaring. Di HP, sidebar jadi barisan chip yang bisa digeser.

Angkanya **saling menyesuaikan**: pilih satu kategori di sidebar, jumlah di tiap sub-tab status ikut menyesuaikan — begitu pula sebaliknya. Jadi CS langsung tahu, misalnya, "berapa resi *Menolak COD* yang *Belum Followup*". Filter pencarian & label tracking di atas tetap berlaku untuk keduanya.

### Foto bukti kurir: dua versi link

Di modal followup, foto kurir kini punya dua tautan: **Foto kurir (Drive)** — salinan permanen, dan **Versi jmsfile** — asli dari J&T tapi berlaku ±24 jam. Pakai versi Drive untuk arsip; versi jmsfile kalau ingin yang paling asli. (Supervisor perlu menjalankan Tracking J&T di Sistem 1 agar keduanya terisi.)

### Upload POD pembanding: tempel (paste) atau pilih file

Dua cara, boleh dicampur:

1. **Tempel gambar** — screenshot/snipping hasil chat WhatsApp, klik kotak *"Tempel gambar di sini"*, tekan **Ctrl+V**. Gambar langsung masuk antrean.
2. **Pilih file** — dari galeri/kamera seperti biasa.

Semua yang di antrean tampil sebagai pratinjau (bisa dibuang satu-satu), lalu klik **Simpan foto ke Drive** — sekali klik menyimpan semuanya ke folder POD_Pembanding.

### Export Excel

Tombol **⤓ Export Excel** di atas worklist membuka modal filter: **label tracking**, **status followup**, **kategori masalah**, dan **provinsi** (provinsi hanya muncul kalau Anda menangani lebih dari satu, atau superadmin). Kosongkan filter untuk mengekspor semua. Klik **Proses & Download** → file `.xlsx` langsung terunduh.

Isinya lengkap: data konsumen (penerima, telepon, alamat, barang, nilai COD), tracking J&T (label, alasan, kurir, waktu), sampai progres followup (PIC CS, kategori, status, hasil POD, jumlah & link foto, catatan). Angka COD sudah terformat ribuan, header dibekukan.

> Batas wilayah tetap berlaku: CS hanya bisa mengekspor resi di provinsinya. Filter provinsi di modal **tidak bisa menembus** itu — ditegakkan di server, sama seperti worklist.

---

## Langkah pasang

### 1. Siapkan folder Drive untuk foto POD
Di Google Drive akun superadmin, buat folder (mis. di dalam `CS_Undelivered`) bernama **`POD_Pembanding`**. Buka folder itu, salin **ID folder** dari URL (bagian setelah `/folders/`).

### 2. Buat project Apps Script baru (terpisah dari Sistem 1)
Buka **script.google.com** → **New project**.
- Tempel isi `Code.gs`.
- Klik **+** → **HTML** → beri nama **`Index`** → tempel isi `Index.html`.

### 3. Isi 2 ID di `CFG2` — WAJIB
```javascript
spreadsheetId: 'ISI_ID_SPREADSHEET',   // ID spreadsheet yang sama dengan Sistem 1
podFolderId:   'ISI_ID_FOLDER_POD',    // ID folder POD_Pembanding dari langkah 1
```
(ID spreadsheet = bagian URL antara `/d/` dan `/edit`.)

### 4. Jalankan `setup2` sekali
Pilih fungsi **`setup2`** → **Run** → **Authorize**. Ini membuat sheet `Ref_Kategori_Masalah` dan `Ref_Template_Pesan` beserta isi contoh.

### 5. Deploy sebagai Web App
**Deploy → New deployment → Web app**. Pilih salah satu pola di bawah.

---

## Pilih pola akses (penting)

### Pola A — CS pakai akun Gmail pribadi (kondisi Anda sekarang)
- **Execute as:** **User accessing the web app**
- **Who has access:** **Anyone with a Google account**
- **Share spreadsheet** ke semua email CS sebagai **Editor**.
- **Share folder `POD_Pembanding`** ke semua email CS sebagai **Editor**.

Ini diperlukan karena script berjalan *atas nama CS*, sehingga CS butuh izin menulis ke spreadsheet & Drive. Konsekuensinya: **CS bisa membuka spreadsheet secara langsung**. Sistem tetap membatasi lewat aplikasi (CS tidak bisa menyimpan resi di luar wilayahnya), tapi akses mentah ke sheet tidak bisa dicegah pada pola ini.

### Pola B — CS dipindah ke akun Google Workspace Anda (disarankan jangka panjang)
- **Execute as:** **Me** (superadmin)
- **Who has access:** **Anyone within [domain Anda]**
- **Tidak perlu** share spreadsheet maupun folder ke CS.

Ini jauh lebih aman: CS hanya bisa mengakses data lewat aplikasi, tidak bisa membuka spreadsheet mentah. Kode yang sama sudah mendukung pola ini — tidak perlu diubah.

> Rekomendasi: mulai dengan **Pola A** agar cepat jalan, lalu pindah ke **Pola B** saat akun CS sudah dibuatkan di Workspace.

---

### 6. Bagikan URL ke tim CS
Salin **Web app URL** hasil deploy, kirim ke tim CS. Pastikan tiap CS sudah:
- Terdaftar di panel **"Kelola CS & Wilayah"** (Sistem 1), dengan **email Google yang benar** dan status **Aktif**.
- Punya minimal satu **provinsi** yang ditetapkan.

Kalau belum, CS akan melihat pesan "Akun belum terdaftar" atau "Belum ada wilayah".

---

## Mengubah kategori & template pesan

Supervisor bisa mengeditnya langsung di spreadsheet:

- **`Ref_Kategori_Masalah`** — kolom `Kategori` | `Keterangan`. Tambah/hapus baris sesuai kebutuhan.
- **`Ref_Template_Pesan`** — kolom `Kategori` | `Judul` | `Isi Pesan`.

Placeholder yang tersedia di Isi Pesan (otomatis diganti data resi):
`{Penerima}` · `{No. Waybill}` · `{Nama Barang}` · `{Kota Penerima}` · `{Provinsi Penerima}` · `{Nilai COD}` · `{Status Ekspedisi}`

---

## Catatan teknis

- **Update per baris.** Saat CS menyimpan, sistem hanya menulis kolom kerja CS di baris resi itu — bukan menulis ulang sheet. Ini yang membuat 6–15 CS bisa bekerja bersamaan tanpa saling menunggu, dan **upload supervisor tidak menimpa hasil kerja CS**.
- **Batas tampilan.** Worklist menampilkan maksimal 300 resi sekali muat (ubah `CFG2.maxRows` bila perlu). Gunakan filter/pencarian untuk mempersempit.
- **Foto POD** disimpan di `POD_Pembanding/[Provinsi]/[YYYY-MM]/` dengan nama `{No.Waybill}_{timestamp}`. Sheet hanya menyimpan link-nya, sehingga tetap ringan.
- **Keamanan wilayah** ditegakkan di server: CS yang mencoba menyimpan resi di luar provinsinya akan ditolak.

## Setelah update kode

1. **Naikkan `APP_VERSION`** di `Code.gs` (mis. `'v5.1 — perbaikan X'`). **Wajib** — lihat penjelasan di bawah.
2. Save → **Deploy → Manage deployments → Edit (pensil) → Version: New version → Deploy**. URL tetap sama.

### Banner "versi baru" otomatis

CS sering membiarkan tab-nya terbuka seharian, jadi halaman mereka tidak tahu kalau kodenya sudah diganti. Aplikasi kini **membandingkan versinya sendiri dengan versi di server** setiap 1,5 menit dan setiap kali CS kembali ke tab. Kalau berbeda → muncul banner hitam di atas: *"Versi baru tersedia (v5.0 → v5.1)"* + tombol **Muat ulang sekarang**. Tombol **✕** menundanya 10 menit (berguna kalau CS sedang di tengah followup). Versi yang sedang dipakai juga tampil di pojok identitas.

Kenapa harus diklik, bukan otomatis? Halaman Apps Script berjalan di dalam **iframe**, dan yang harus dipindahkan adalah jendela atasnya — browser hanya mengizinkan itu bila dipicu **klik user**. Auto-redirect tanpa gestur akan diblokir diam-diam. Tombolnya menambahkan `?v=<timestamp>` agar benar-benar melewati cache browser.

> Kalau `APP_VERSION` tidak dinaikkan, banner **tidak akan muncul** dan CS tetap memakai kode lama sampai me-refresh sendiri.

### Loader progress per section

Tiap bagian yang sedang menunggu data menampilkan **persentase yang naik** (melambat mendekati 92%, lalu digantikan isi aslinya begitu data tiba). Diterapkan di **daftar resi (worklist)** dan **tab Report** (ringkasan, KPI, tabel produktivitas CS). Khusus Report, loader-nya kini per-bagian — tidak lagi menutup seluruh layar dengan overlay, jadi bagian yang sudah siap tetap bisa dilihat. Kalau salah satu gagal, hanya bagian itu yang menampilkan pesan error.
