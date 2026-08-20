# Sistem 1 — Supervisor: Upload & Distribusi (Panduan Pasang)

Web app untuk supervisor: upload file export ekspedisi dari 2 menu (**Sedang Diantar**, **Retur**), otomatis dirapikan, di-**upsert** per `No. Waybill`, dan **didistribusikan ke CS berdasarkan provinsi**. Dilengkapi mini-dashboard.

> Status **"Sedang Retur" sudah dihapus** dari sistem (tidak dipakai lagi). Yang tersisa hanya *Sedang Diantar* dan *Retur*.

File:
- `Code.gs` — backend upload & distribusi.
- `Admin.gs` — backend kelola CS & pemetaan provinsi.
- `Report.gs` — backend **Performa Followup CS** (read-only).
- `JntTrack.gs` — backend **Tracking J&T otomatis** (solusi sementara sampai API resmi turun).
- `Index.html` — front-end (upload + dashboard + Tracking J&T + Performa Followup CS + panel Kelola CS & Wilayah).

---

## Cara kerja singkat

- Tiap slot upload menandai kolom **Status Ekspedisi** sesuai menunya.
- **Upsert by No. Waybill**: resi baru ditambah; resi lama di-update statusnya (menangani perpindahan status tanpa duplikat). **Kolom kerja CS tidak pernah ditimpa.**
- **Distribusi otomatis**: kolom `PIC CS` diisi dari pemetaan `Ref_Provinsi_CS` (provinsi → CS). Resi yang provinsinya belum dipetakan → `PIC CS` kosong = **Belum Terdistribusi**.
- **Snapshot-reconcile + arsip**: setiap file adalah snapshot lengkap suatu status untuk rentang bulan pengirimannya. Resi yang **sebelumnya** berstatus itu (di bulan yang sama) tapi **hilang** dari file terbaru = sudah keluar dari tahap tsb → otomatis **dipindah ke sheet `Arsip_Undelivered`** (lengkap dengan hasil kerja CS-nya).
- **Auto-restore**: kalau resi yang sudah diarsipkan **muncul lagi** di file status lain (mis. Retur), ia otomatis **kembali ke MASTER** dengan status baru dan hasil kerja CS-nya dipulihkan.
- Pengecekan "hilang" dibatasi **per bulan pengiriman** yang ada di file — aman untuk upload terpisah bulan ini & bulan lalu.
- File mentah diarsipkan ke Drive (`CS_Undelivered/Arsip_Upload/YYYY-MM`) dan aktivitas dicatat di `Log_Aktivitas`.

---

## Langkah pasang (sekali)

### 1. Spreadsheet & Apps Script
Buka Google Sheet tujuan (disarankan **milik akun Workspace superadmin**) → **Extensions → Apps Script**.
- Tempel isi `Code.gs` ke file kode.
- Klik **+** → **Script** → beri nama **`Admin`** → tempel isi `Admin.gs`.
- Klik **+** → **Script** → beri nama **`Report`** → tempel isi `Report.gs`.
- Klik **+** → **Script** → beri nama **`JntTrack`** → tempel isi `JntTrack.gs`.
- Klik **+** → **HTML** → beri nama **`Index`** → tempel isi `Index.html`.
- Simpan semua.

### 2. Aktifkan Advanced Drive Service — WAJIB
Panel kiri → di samping **Services** klik **+** → pilih **Drive API** → **Add** (identifier tetap `Drive`).

### 3. Nama kolom (sudah dikonfirmasi dari file Anda)
Sudah diset sesuai file export "Sedang Diantar" (sheet "Resi Saya", 42 kolom):
```javascript
keyCol:      'No. Waybill',
provinceCol: 'Provinsi Penerima',
shipDateCol: 'Tanggal Pengiriman',
```
> Tidak perlu diubah selama struktur file kedua menu sama. Kalau file "Retur" ternyata beda kolom, beri tahu saya.

### 4. Jalankan `setup` sekali
Di editor Apps Script, pilih fungsi **`setup`** pada dropdown → **Run** → selesaikan **Authorize** (Advanced → Go to project → Allow). Ini membuat sheet `Ref_Provinsi_CS`, `Users`, `Log_Aktivitas`.

### 5. Kelola CS & wilayah (lewat panel, bukan edit sheet)
Setelah web app dideploy, buka tab **"Kelola CS & Wilayah"**:

- **Tambah CS**: isi email Google, nama, peran → Simpan.
- **Tetapkan wilayah**: pada kartu CS, pilih provinsi → "+ Tambah wilayah". Satu provinsi = satu CS.
- Provinsi yang muncul di data tapi belum dipetakan tampil di **"Provinsi Belum Terdistribusi"** — tetapkan ke CS dari situ.
- Setiap kartu CS menampilkan **beban per wilayah dan per status** (Sedang Diantar / Retur) beserta totalnya.
- **Kartu ber-role `superadmin` tidak punya tabel & pemilih provinsi** — aksesnya sudah seluruh wilayah, jadi menampilkannya justru menyesatkan (seolah aksesnya terbatas pada provinsi yang dipilih). Superadmin juga tidak muncul di dropdown *"tetapkan ke CS"* pada daftar provinsi belum terdistribusi.
- Tombol **"Re-distribusi ulang"** menerapkan pemetaan terbaru ke seluruh data (mis. setelah memindah wilayah ke CS lain).

> Provinsi baru bisa dipetakan setelah muncul di data (upload minimal satu file dulu).

### 5b. Tab "Performa Followup CS" (read-only)

Supervisor melihat hasil kerja tim CS tanpa bisa mengubahnya. Semua angka mengikuti filter di bagian atas (rentang tanggal — bawaannya **bulan berjalan** —, CS, status ekspedisi, status followup, kategori masalah, hasil POD pembanding, ada/tidaknya foto, dan pencarian bebas).

**Produktivitas harian per CS.** Matriks CS × tanggal: berapa **resi** yang difollowup tiap CS per hari, lengkap dengan total, jumlah hari aktif, dan rerata per hari. Satu resi yang disentuh berkali-kali di hari yang sama dihitung **satu** — yang diukur cakupan kerja, bukan jumlah klik. Sumber angkanya `Log_Aktivitas` (aksi *Followup* yang ditulis Sistem 2); kalau log masih kosong, sistem memakai `Timestamp Update` sebagai perkiraan dan menandainya di layar.

**Kualitas kerja per CS.** Resi ditangani, belum/proses/selesai, % selesai, berapa yang punya foto POD, berapa yang sudah diverifikasi ke konsumen, berapa klaim kurir yang dibantah, dan nilai COD yang dipegang CS itu.

**Integritas klaim kurir.** Menyilangkan **kata kurir** (Kategori Masalah) dengan **kata konsumen** (Hasil POD Pembanding). Untuk tiap kategori klaim: berapa yang **dibantah** konsumen, berapa yang **dikonfirmasi**, berapa hasil lain, berapa yang belum diverifikasi, dan **% dibantah**. Persentase tinggi = klaim kurir patut dipersoalkan ke ekspedisi.

**Detail per resi.** Tabel sampai ke kategori masalah, status followup, hasil POD pembanding, **link foto POD**, catatan CS, waktu update, dan siapa yang mengupdate. Ada paginasi.

**Export Excel (.xlsx).** Tombol **⤓ Export Excel** membuka modal filter tersendiri: **label tracking**, **status followup**, **kategori masalah**, **provinsi**. Kosongkan filter untuk mengekspor semua. Klik **Proses & Download** → file `.xlsx` langsung terunduh — data konsumen, tracking J&T, sampai progres followup dalam satu file, angka COD terformat, header dibekukan. (Tombol **CSV** yang lama tetap ada untuk ekspor cepat teks polos.) File Excel dibangun di server lewat spreadsheet sementara yang langsung dibuang, jadi tidak ada file sampah di Drive Anda.

> Supervisor **tidak bisa** mengubah data followup dari sini. Ini disengaja: angka performa CS tidak boleh bisa "dirapikan" oleh yang menilainya.

### 5c. Tab "Tracking J&T" — ⚠️ SOLUSI SEMENTARA

Mengambil **label tracking terakhir** tiap resi *Sedang Diantar* langsung dari **endpoint platform VIP J&T**, karena export portal tidak memuatnya dan admin terpaksa mengecek satu per satu. Endpoint VIP ini juga memberi **foto bukti kurir** yang sudah bertanda tangan.

> **Ini bukan API resmi.** Endpoint yang dipakai (`jmsvipgw.jntexpress.id`) adalah milik platform VIP internal J&T; strukturnya bisa berubah kapan saja tanpa pemberitahuan. Pakai **hanya sampai API resmi J&T disetujui**. Begitu API resmi turun, cukup ganti isi fungsi `lacak_()` di `JntTrack.gs` — sheet, kolom, dashboard, dan Sistem 2 **tidak perlu diubah sama sekali**.

#### Wajib dulu: isi panel "Sesi Manual" (authToken + device-no)

Endpoint VIP diautorisasi lewat dua header dari **sesi login VIP** Anda: `authToken` (JWT) dan `device-no`. Keduanya **ditempel manual** — Apps Script tidak bisa login VIP sendiri.

Cara mengambilnya (±1 menit):

1. Login di **login-newvip.jet.co.id** → buka menu **Tracking** → lacak **1 resi** sampai hasilnya muncul.
2. **F12** → tab **Network** → klik permintaan **`trace/list`**.
3. Di **Request Headers**, salin nilai **`authToken`** dan **`device-no`**.
4. Tempel keduanya di panel **Sesi Manual** pada tab Tracking J&T → **Simpan Sesi**.

> Ambil dari **sesi VIP yang sedang aktif**. `authToken` tidak memuat tanggal kedaluwarsa — umurnya diputuskan server VIP, jadi hanya lapangan yang tahu berapa lama bertahan. Kalau tracking mulai gagal *unauthorized*, sesinya habis: tempel ulang. Kalau Anda logout dari VIP, token bisa ikut mati.

Sesi disimpan di **Script Properties**, bukan di dalam kode — jadi menempel ulang **tidak perlu deploy ulang**, dan tidak ada token yang tertinggal di file kode. Satu sesi dipakai untuk semua resi.

**Lalu jalankan 3 fungsi ini dari editor Apps Script:**

| Fungsi | Gunanya |
|---|---|
| `cekSesi()` | menampilkan sesi VIP yang sedang dipakai (authToken/device-no, cek bentuk JWT) |
| `tesSatuResi()` | menarik 1 resi sungguhan + menampilkan balasan mentah VIP — **bukti sesinya diterima** |
| `tesMultiResi()` | menguji banyak resi dalam 1 permintaan (`codes` berupa array). Kalau lolos, naikkan `TRK.resiPerRequest` jadi `10`: request turun 700 → 70 |

**Foto bukti kurir.** Endpoint VIP mengembalikan URL foto yang **sudah bertanda tangan** (`traceItems[].imgUrl`) — tanda tangan itu dibuat server J&T, tidak bisa kita buat sendiri. URL-nya **berlaku ±24 jam**.

Karena itu, tiap tracking berjalan, foto paket bermasalah **otomatis disalin ke Google Drive** (folder `CS_Undelivered/POD_Kurir_JNT/[bulan]`) sebagai salinan **permanen**. Ada dedup: foto yang sudah pernah disimpan tidak diunduh ulang. Di Sistem CS, tiap resi menampilkan **dua link**: versi Drive (permanen) dan versi jmsfile (asli J&T, ±24 jam). Kalau penyimpanan Drive gagal (kuota/izin), tracking tetap jalan — kolom Drive dibiarkan kosong, link jmsfile tetap ada. Tetap **jalankan tracking berkala** agar link jmsfile & salinan Drive selalu segar.

**Cara pakai:** buka tab **Tracking J&T** → **▶ Mulai Perbarui**. Proses berjalan di **latar belakang** (trigger server) — halaman boleh ditutup, dan Anda tetap bisa upload file atau kelola CS. Progresnya dibaca ulang dari sheet, jadi tetap akurat walau halaman di-refresh atau dibuka supervisor lain.

#### Kalau macet — buka "Log proses"

Di bawah tombol ada panel **Log proses**: langkah demi langkah, sama persis dengan yang tercatat di **Apps Script → Executions** (`console.log`). Isinya: sesi mana yang dipakai, berapa resi diproses, 3 contoh hasil parsing pertama, tiap kegagalan beserta alasannya, dan `CRASH` lengkap bila ada. Panel ini terbuka sendiri saat proses gagal atau macet — supervisor tidak perlu membuka Apps Script.

Sistem juga **mendeteksi macet sendiri**: kalau job tertulis "jalan" tapi triggernya hilang dan tidak ada denyut >3 menit, layar langsung melapor *"Proses berhenti tanpa kabar"* dan tombol **Mulai Perbarui** bisa ditekan lagi.

**Pengaman yang tertanam:**

- Jeda **1,2 detik** antar permintaan (sopan, menghindari rate-limit).
- **Berhenti sendiri** setelah **5 permintaan gagal beruntun** — supaya tidak menghantam server yang sedang menolak kita. Alasannya ditulis apa adanya di layar, tidak didiamkan.
- Balasan **401/403** otomatis dikenali sebagai **sesi VIP kedaluwarsa** (tempel ulang), bukan "tidak ada data".
- Batas waktu eksekusi dijaga (25 menit); kalau belum habis, trigger berikutnya **melanjutkan sendiri**. Tidak ada antrean yang disimpan — daftar sisa dihitung ulang dari sheet tiap putaran, jadi kalau eksekusi mati di tengah jalan tidak ada resi yang terlewat maupun dobel.
- Label terbaru **diurutkan sendiri** dari `scanTime`, tidak menggantungkan diri pada urutan kiriman J&T.

**Kapasitas** (Workspace berbayar: 30 menit/eksekusi, 6 jam/hari trigger, 100.000 fetch/hari):

| Mode | 700 resi |
|---|---|
| 1 resi/request | 700 request · ±14 menit · 1 putaran |
| 10 resi/request | 70 request · ±1,4 menit · 1 putaran |

**Kolom baru di `MASTER_Undelivered`** (dibuat otomatis): `Label Tracking`, `Kode Tracking`, `Waktu Tracking`, `Keterangan Tracking`, `Alasan Tertunda`, `Kode Alasan`, `Posisi Terakhir`, `Kurir Terakhir`, `Foto Kurir`, `Cek Terakhir`.

**Yang ditampilkan:** KPI (total, belum dicek, jumlah label, paket diam >3 hari), grafik sebaran label, daftar alasan tertunda, tabel label per CS, dan **daftar paket paling berisiko** — yang label terakhirnya sudah lama tidak berubah.

### 5d. Kategori Masalah kini datang dari lapangan

Selesai menarik tracking, sistem **menyusun ulang** sheet `Ref_Kategori_Masalah` dari klaim asli J&T (field `remark1`) — mis. *"Penerima menolak menerima paket"*, *"Reschedule waktu pengiriman"*, *"TLC Salah, sehingga paket salah sortir"* — lengkap dengan kode resminya (`7c`, `31i`, `PT013`, …) dan jumlah resi yang mengalaminya, diurut dari yang paling sering.

Dropdown Kategori Masalah di **Sistem 2 otomatis ikut berubah**, dan kolom `Kategori Masalah` tiap resi **terisi sendiri** dari alasan resmi J&T.

> Kenapa diubah: daftar kategori yang lama disusun manual di awal proyek — tebakan. Sekarang kita punya klaim asli ekspedisi, jadi dropdown CS memakai kata-kata yang **persis sama** dengan catatan J&T. Waktu CS mendebat klaim kurir, istilahnya cocok dan tidak bisa diperdebatkan. **Jangan menambah kategori manual di sheet** — biarkan datang dari lapangan.

### 6. Deploy Web App
**Deploy → New deployment → Web app**:
- Execute as: **Me**
- Who has access: **Only myself** (atau *Anyone with Google account* bila supervisor lain memakai)
- **Deploy** → salin **Web app URL** → bookmark.

Selesai. Buka URL, upload file, sheet `MASTER_Undelivered` terisi & terdistribusi otomatis.

---

## Catatan penting

- **Jangan** ubah sheet `MASTER_Undelivered` dan `Arsip_Undelivered` menjadi **Table** (fitur tabel Google Sheets). Proses upload menulis ulang seluruh sheet; kalau berupa Table, tipe kolom terkunci dan bisa error. Biarkan sebagai sheet biasa. (Dashboard & analisis tetap bisa dibuat di sheet terpisah dengan `QUERY`.)
- Sheet `MASTER_Undelivered` dan `Arsip_Undelivered` dibuat **otomatis** saat upload pertama — tidak perlu dibuat manual.
- Struktur kolom MASTER = **kolom dari file export** + `Status Ekspedisi`, `Tanggal Update Status` + kolom kerja CS (`PIC CS`, `Status Followup`, dst.). Kolom kerja CS akan diisi oleh **Sistem 2** nanti.
- Kalau `PIC CS` sudah terisi (mis. supervisor pindahkan manual), upload berikutnya **tidak** menimpanya.
- `Arsip_Undelivered` = resi yang sudah keluar dari status aktif (kemungkinan terkirim). Tetap disimpan agar CS bisa **verifikasi POD** bila perlu (antisipasi kurir mengaku terkirim). Kalau resi muncul lagi di file status lain, otomatis kembali ke MASTER.

---

## Setelah update kode

1. **Naikkan `APP_VERSION`** di `Code.gs` (mis. `'v2.1 — perbaikan X'`). **Wajib** — lihat penjelasan di bawah.
2. Save → **Deploy → Manage deployments → Edit (pensil) → Version: New version → Deploy**. URL tetap.

(Untuk uji cepat pakai URL `/dev` di **Test deployments**.)

### Banner "versi baru" otomatis

Halaman yang sedang dibuka user tidak tahu kalau kodenya sudah diganti. Karena itu aplikasi **membandingkan versinya sendiri dengan versi di server** setiap 1,5 menit dan setiap kali user kembali ke tab. Kalau berbeda → muncul banner hitam di atas: *"Versi baru tersedia (v2.0 → v2.1)"* + tombol **Muat ulang sekarang**. Tombol **✕** menundanya 10 menit.

Kenapa harus diklik, bukan otomatis? Halaman Apps Script berjalan di dalam **iframe**, dan yang harus dipindahkan adalah jendela atasnya — browser hanya mengizinkan itu bila dipicu **klik user**. Auto-redirect tanpa gestur akan diblokir diam-diam. Tombolnya menambahkan `?v=<timestamp>` agar benar-benar melewati cache browser.

> Kalau `APP_VERSION` tidak dinaikkan, banner **tidak akan muncul** dan user tetap memakai kode lama sampai me-refresh sendiri.

### Loader progress per section

Tiap bagian yang sedang menunggu data menampilkan **persentase yang naik** (melambat mendekati 92%, lalu digantikan isi aslinya begitu data tiba) — bukan lagi layar diam tanpa keterangan. Diterapkan di: Ringkasan Distribusi (KPI), tab Performa Followup CS (matriks harian, kualitas per CS, integritas klaim, grafik, tabel detail), dan panel Kelola CS & Wilayah. Kalau salah satu gagal, hanya bagian itu yang menampilkan pesan error — bagian lain yang sudah masuk tetap tampil.

---

## Langkah berikutnya

Konfigurasi kolom sudah dikunci dari file "Sedang Diantar". Untuk memastikan file **Retur** juga sama strukturnya, kirim satu contoh bila ada.
