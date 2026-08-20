# J&T Data Loader — Panduan Pasang (Google Sheets + Apps Script)

Sistem ini menggantikan Power Query Excel. Anda cukup **upload file lewat halaman web**, dan sistem otomatis merapikan data lalu memperbarui dua sheet: **All Resi** dan **Settle Reconcile**.

File yang dibuat:
- `Code.gs` — backend (transform + upsert + riwayat upload).
- `Dashboard.gs` — backend dashboard & proyeksi pencairan J&T.
- `Index.html` — halaman web (Upload Data · Dashboard · Pencairan J&T).

---

## Ringkasan cara kerja

1. Anda upload file resi J&T (`.xlsx`/`.xls`) lewat halaman web.
2. Script mengonversi file ke Google Sheet sementara (via Drive), lalu **membuang & merapikannya persis seperti Power Query** (tipe data, rename kolom, kolom hitung `COD Fee` & `Nilai Produk`, urutan kolom, sortir).
3. Data masuk ke sheet tujuan dengan **UPSERT berdasarkan `No. Waybill`**:
   - Waybill baru → **ditambahkan**.
   - Waybill yang sudah ada (mis. Anda upload ulang bulan lama karena ada perubahan dari J&T) → **baris lama ditimpa**, tidak menduplikasi.

> Catatan: file "Settle Reconcile" berekstensi `.xls` tapi isinya sebenarnya format xlsx — sistem tetap membacanya dengan benar.

> **Dua format Settle Reconcile didukung sekaligus.** J&T mengganti format file ini. Sistem menerima **keduanya** tanpa Anda perlu memilih apa pun:
> - Format lama *"COD Reconciliation Details"* (11 kolom: `Waktu TTD`, `TTD`, `Penerima`, `COD`, …).
> - Format baru *"COD佣金对账明细票数"* (7 kolom: `No. Order`, `Bulan`, `Waktu Terima`, `Nominal COD`, `Komisi COD`, …).
>
> Yang berubah hanya nama kolomnya: `Waktu Terima` diperlakukan sama seperti `Waktu TTD`, dan `Nominal COD` sama seperti `COD`. Hasil di sheet dan angka pencairan di dashboard **tetap sama persis**. Kolom yang tidak ada di salah satu format (mis. `TTD`, `Penerima` pada format baru) dibiarkan kosong — tidak dipakai perhitungan.

### Jaminan anti-duplikat (No. Waybill = kunci tunggal)

| Sumber duplikasi | Penanganan |
|---|---|
| Waybill kembar **di dalam satu file** | Kemunculan berikutnya **menimpa**, bukan menambah baris |
| Waybill kembar **antar file** dalam satu submit | Peta kunci dipakai bersama; file berikutnya dihitung sebagai *update* |
| Upload **ulang** file yang sama / bulan lama | Baris lama ditimpa (upsert), bukan diduplikasi |
| Waybill kembar yang **sudah terlanjur ada** di sheet | Dibersihkan otomatis tiap upload — yang dipertahankan baris paling bawah (paling baru) |
| Baris **tanpa No. Waybill** | Tidak pernah ditulis; dilaporkan sebagai "dilewati" |

Perbandingan kunci mengabaikan spasi dan akhiran `.0` (antisipasi waybill yang terbaca sebagai angka), jadi `1360655939` dan `1360655939.0` dianggap **resi yang sama**.

Dua alat bantu: tombol **"Periksa sekarang"** di Dashboard → *Integritas data* (menghitung total baris vs waybill unik per sheet, tanpa mengubah apa pun), dan fungsi **`bersihkanDuplikat()`** yang bisa dijalankan langsung dari editor Apps Script bila ingin merapikan sheet tanpa upload.

---

## Langkah pemasangan (sekali saja)

### 1. Buka / buat spreadsheet
Buka Google Sheet tujuan Anda (atau buat baru di sheets.google.com). Sistem akan membuat sheet **All Resi** dan **Settle Reconcile** otomatis kalau belum ada.

### 2. Buka editor Apps Script
Di spreadsheet: menu **Extensions → Apps Script**.

### 3. Tempel kode
- Di file `Code.gs` yang terbuka: hapus isinya, **tempel seluruh isi `Code.gs`** dari sini.
- Klik ikon **+** → **Script** → beri nama **`Dashboard`** → **tempel seluruh isi `Dashboard.gs`**.
- Klik ikon **+** → **HTML** → beri nama **`Index`** (huruf besar I, tanpa `.html`) → **tempel seluruh isi `Index.html`**.
- Simpan (Ctrl+S).

### 4. (Opsional) Set ID spreadsheet
Karena Anda membuka Apps Script dari dalam spreadsheet, **biarkan** baris ini apa adanya:
```javascript
var SPREADSHEET_ID = '';
```
(Isi hanya jika nanti script dibuat standalone/terpisah dari spreadsheet.)

### 5. Aktifkan Advanced Drive Service — WAJIB
Konversi file butuh layanan ini:
- Di editor Apps Script, panel kiri, di samping **Services** klik ikon **+**.
- Cari **Drive API**, pilih, klik **Add**. (Identifier harus tetap: `Drive`.)

### 6. Deploy sebagai Web App
- Klik **Deploy → New deployment**.
- Ikon gerigi → pilih **Web app**.
- Isi:
  - **Description**: `JnT Data Loader`
  - **Execute as**: **Me** (akun Anda)
  - **Who has access**: **Only myself** (paling aman) — atau *Anyone with Google account* kalau mau dipakai staf lain.
- Klik **Deploy**.
- Klik **Authorize access** → pilih akun → di layar "Google hasn't verified" klik **Advanced → Go to (project) (unsafe)** → **Allow**. (Ini normal untuk script pribadi.)
- Salin **Web app URL** yang muncul. Itulah link yang Anda buka untuk upload. **Bookmark** link tersebut.

Selesai. Buka URL-nya, upload file, sheet langsung terupdate.

---

## Pemakaian harian

### Tab 1 · Upload Data
Tiap slot menerima **beberapa file sekaligus** — pilih/tarik banyak file, semuanya diproses dalam satu submit dan ditulis ke sheet sekali jalan (jauh lebih cepat daripada satu per satu). File yang gagal (mis. tertukar slot) dilewati dan dilaporkan, file lain tetap masuk.

Di bawah tiap slot ada **Riwayat Upload**: nama file, **rentang tanggal** isinya (Settle Reconcile → rentang *Waktu TTD*; All Resi → rentang *Tanggal Pengiriman*), jumlah resi, berapa baru vs update, dan kapan diupload. Tersimpan permanen di sheet **`Riwayat_Upload`**.

### Tab 2 · Dashboard

Definisi status yang dipakai:

| Status | Aturan |
|---|---|
| **Sampai tujuan** | `Tanda TTD` menyatakan sudah sampai |
| **Bermasalah / retur** | `Tanda TTD` **belum** sampai **tapi** `Waktu Terima` sudah terisi |
| **Masih dalam pengiriman** | `Tanda TTD` **belum** sampai **dan** `Waktu Terima` masih kosong |

**Net omzet = `Nilai COD` − `COD Fee` − `Total Biaya Setelah Diskon`**, dihitung hanya untuk resi COD (`Nilai COD` > 0). Resi non-COD tidak menghasilkan pencairan dari J&T, jadi tidak ikut dijumlahkan (jumlahnya tetap ditampilkan sebagai catatan).

Isinya: KPI ringkas (dikirim, sampai + net omzet, bermasalah, proses kirim + net omzet, rata-rata durasi kirim, status reconcile, pencairan berikutnya) dan **tabel per provinsi** yang bisa **diurutkan dengan klik judul kolom** — total, sampai/%, retur/%, proses/%, rata-rata durasi kirim, dan net omzet.

> **Panel Kalibrasi** di bawah tabel menampilkan semua nilai unik kolom `Tanda TTD` yang ditemukan di data Anda beserta cara sistem membacanya. Cek sekali di awal. Kalau ada nilai yang salah dibaca, daftarkan nilai-nilai "sampai" di `DASH.ttdSampai` pada `Dashboard.gs`.

### Tab 3 · Pencairan J&T

Aturan yang dipakai (berdasarkan **hari paket sampai**):

| Paket sampai | Cair |
|---|---|
| Rabu, Kamis | **Senin** berikutnya |
| Jumat, Sabtu, Minggu | **Selasa** berikutnya |
| Senin, Selasa | **Kamis** minggu itu |

Tiap tanggal pencairan dipecah dua:
- **Terkonfirmasi** — resi yang **sudah muncul** di Settle Reconcile (acuan tanggal: `Waktu TTD` dari file reconcile).
- **Proyeksi** — resi yang di All Resi **sudah sampai** tapi **belum ada** di Settle Reconcile (acuan: `Waktu Terima`). Inilah perkiraan uang yang masih akan cair.

Sistem mencocokkan `No. Waybill` antara kedua sheet, jadi KPI *"Sampai tapi belum di reconcile"* langsung memberi tahu berapa resi dan berapa rupiah yang belum direkonsiliasi J&T.

**Preview & Export.** Di widget **"Sampai tapi BELUM di reconcile"** ada tombol **👁 Preview & Export**. Klik → muncul tabel rinci resi yang sudah sampai (COD) tapi belum masuk reconcile: No. Waybill, Tgl Kirim, Penerima, Provinsi, Nilai Barang, Biaya (setelah diskon), Nilai COD, COD Fee, Diterima Oleh, Waktu Terima, Keterangan, Tanda TTD, COD/Non-COD, dan **Net yang seharusnya diterima** — diurut dari Net terbesar. Jumlah barisnya persis sama dengan angka di widget (COD-only). Tombol **⤓ Download Excel** di modal itu mengunduh data yang sama sebagai `.xlsx`.

---

## Kalau ada perubahan kode nanti
Setelah mengedit `Code.gs`/`Index.html`, **Deploy → Manage deployments → (pilih) → Edit (pensil) → Version: New version → Deploy**. URL tetap sama.

---

## Troubleshooting

| Gejala | Sebab & solusi |
|---|---|
| `Drive is not defined` | Advanced Drive Service belum diaktifkan (langkah 5). |
| `File ini sepertinya bukan file "…"` | File tertukar slot — pastikan file All Resi di slot 1, Reconcile di slot 2. |
| Sheet aktif tampil "(cek izin)" | Selesaikan proses **Authorize** (langkah 6). |
| Waybill tampil sebagai angka/ilmiah | Sudah diantisipasi (kolom dipaksa format teks). Kalau masih terjadi, pastikan pakai `Code.gs` versi ini. |
| Proses lambat untuk file besar (ribuan baris) | Normal beberapa detik; batas eksekusi 6 menit — aman. |

---

## Setelah update kode (banner "versi baru")

Halaman yang dibiarkan terbuka tidak otomatis tahu kalau kodenya sudah diganti. Karena itu:

1. **Naikkan `APP_VERSION`** di `Code.gs` (mis. `'v1.2 — perbaikan X'`) — **wajib**, ini pemicunya.
2. Save → **Deploy → Manage deployments → Edit (pensil) → Version: New version → Deploy**. URL tetap sama.

Aplikasi membandingkan versinya sendiri dengan versi di server tiap 1,5 menit dan tiap kali Anda kembali ke tab. Kalau beda → muncul **banner hitam** di atas: *"Versi baru tersedia"* + tombol **Muat ulang sekarang**. Tombol **✕** menundanya 10 menit. Versi yang sedang dipakai juga tampil kecil di sebelah judul.

Kenapa harus diklik, bukan otomatis? Halaman Apps Script berjalan di dalam **iframe**; yang harus dipindah adalah jendela atasnya, dan browser hanya mengizinkannya bila dipicu **klik user**. Tombolnya menambah `?v=<timestamp>` agar benar-benar melewati cache browser — jadi **tidak perlu hapus cache manual**, cukup klik.

> Kalau `APP_VERSION` tidak dinaikkan, banner **tidak muncul** dan user tetap memakai kode lama sampai me-refresh sendiri.

---

## Kesetaraan dengan Power Query (audit)

**All Resi** — 44 kolom akhir, identik dengan query Anda:
`No. Waybill` (teks), `Tanggal Pengiriman` (tanggal), … `Biaya Kirim`/`Total Biaya`/`Biaya Diskon`/`Total Biaya Setelah Diskon`/`Nilai COD` (angka), `Jumlah Barang`/`Berat`/`Nilai Barang`/`Biaya Asuransi`/`Biaya Lainnya` (bulat), `COD Fee` = `Nilai COD` × 0,015, `Nilai Produk` = `Nilai COD` − `Biaya Kirim`, `代收货款金额` → **Nilai COD**, `Waktu Terima` tanggal saja. Sortir menaik `Tanggal Pengiriman`.

**Settle Reconcile** — 11 kolom: `No. Waybill` (teks), `Waktu TTD` (tanggal saja), `COD` (bulat), sisanya teks. Sortir menaik `Waktu TTD`.

Beda dari Power Query: model **folder** (baca semua file) diganti **upload manual + upsert per waybill** — sesuai permintaan Anda supaya bisa update resi lama tanpa duplikasi dan tetap ringan.
