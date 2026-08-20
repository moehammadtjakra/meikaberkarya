# Sistem Admin Order — OrderOnline ⇄ J&T (Panduan Pasang)

Menggantikan kerja manual Excel: import order OrderOnline → cek stok → hasilkan file siap upload J&T → tarik resi & URL tracking → kirim balik ke OrderOnline.

File:
- `Code.gs` — konfigurasi, import order, normalisasi wilayah, mapping produk & bump.
- `Stok.gs` — ledger stok multi-gudang, HPP rata-rata bergerak, registry SKU, harga jual.
- `Batch.gs` — perencanaan stok (FIFO/wilayah), buat batch, export file upload J&T.
- `Tracking.gs` — import Url-Tracking, CSV `paid`, CSV retur `unpaid`.
- `Handover.gs` — handover resi harian + PDF serah-terima pickup J&T.
- `Index.html` — antarmuka 6 tab.
- `appsscript.json` — manifest (scope & advanced service).

---

## ⚠️ Rekomendasi arsitektur: **pakai spreadsheet TERPISAH**

Jangan digabung dengan spreadsheet Sistem CS Undelivered. Alasannya nyata, bukan sekadar kerapian:

**1. Keamanan / hak akses berbeda.** Tim admin order tidak perlu (dan sebaiknya tidak bisa) melihat data followup CS, begitu pula sebaliknya. Satu spreadsheet = satu izin akses; tidak bisa dipisah per-sheet secara aman.

**2. Pola tulis bertabrakan.** Sistem Admin Order **menulis ulang seluruh sheet ORDERS** saat membuat batch. Sistem CS menulis **per baris** dan dipakai 6–15 CS bersamaan. Kalau satu spreadsheet, keduanya berebut kunci (`LockService`) — admin menunggu CS, CS menunggu admin. Terpisah = tidak pernah saling tunggu.

**3. Isolasi kegagalan & kuota.** Kalau satu sistem bermasalah (file rusak, kuota habis, script error), yang lain tetap jalan.

**Integrasinya tetap ada:** modul Retur bisa **membaca** spreadsheet Sistem CS lewat ID (cukup akses *Viewer*) untuk menarik resi berstatus Retur. Sambungannya searah dan read-only — aman.

---

## Langkah pasang

### 1. Buat spreadsheet baru
Buat Google Sheet baru, mis. **`MB — Admin Order`**, di **akun Workspace superadmin** (bukan Gmail pribadi — kuota Apps Script lebih tinggi dan kepemilikan terpusat).

### 2. Pasang script
Di spreadsheet itu: **Extensions → Apps Script**.
- Tempel isi **`Code.gs`** ke file kode utama.
- **+** → **Script** → beri nama `Stok` → tempel **`Stok.gs`**.
- **+** → **Script** → beri nama `Batch` → tempel **`Batch.gs`**.
- **+** → **Script** → beri nama `Tracking` → tempel **`Tracking.gs`**.
- **+** → **Script** → beri nama `Handover` → tempel **`Handover.gs`**.
- **+** → **HTML** → beri nama `Index` → tempel **`Index.html`**.
- ⚙ **Project Settings** → centang **"Show appsscript.json manifest file in editor"** → buka `appsscript.json` → tempel isi file manifest.

Manifest sudah otomatis mengaktifkan **Drive API** (untuk baca file .xlsx dan membuat file hasil) dan scope yang dibutuhkan.

### 3. Jalankan `setup`
Pilih fungsi **`setup`** → **Run** → **Authorize** (Advanced → Go to project → Allow).
Ini membuat semua sheet: `ORDERS`, `REF_PRODUK`, `STOK`, `STOK_MASUK`, `REF_WILAYAH`, `REF_ALIAS_PROVINSI`, `AREA_JNT`, `KATEGORI_JNT`, `BATCH`, `PENGIRIM`, `LOG` — beserta data pengirim & alias provinsi bawaan.

### 4. Deploy Web App
**Deploy → New deployment → Web app**:
- **Execute as: User accessing the web app**
- **Who has access: Anyone with a Google account** (atau *Anyone within domain* bila semua admin ada di Workspace)

Lalu **share spreadsheet ini ke semua admin sebagai Editor** (dan folder Drive hasil, bila `driveFolderId` diisi).

> **Kenapa begini:** Anda ingin **setiap aktivitas & batch tercatat atas nama siapa**. Itu hanya mungkin kalau script berjalan atas nama admin yang login. Konsekuensinya admin punya akses ke spreadsheet — tapi Anda sudah menyatakan tidak masalah karena mereka memang berbagi data yang sama.
>
> Keamanannya tetap berlapis: **hanya email yang terdaftar di sheet `USERS`** yang bisa memakai aplikasi. Email lain — walau punya link — akan ditolak.

### 4b. Daftarkan admin & akun OrderOnline
Tab **Master Data → Admin & Akun OrderOnline** (khusus superadmin):
- **Admin**: daftarkan email Google tiap admin + peran (`admin` / `superadmin`).
- **Akun OrderOnline**: sistem sudah menyiapkan `A1`, `A2`, `A3` — ganti kode & namanya sesuai 3 akun Anda.

Semua aksi tercatat di sheet **`LOG`** (waktu, email, nama, aksi, detail), dan tiap batch menyimpan **siapa yang membuatnya**.

### 5. Import master (sekali saja) — tab **Master Data**
- Upload **`Informasi Area.xls`** → tombol *Import Area* (7.323 wilayah J&T).
- Upload **`exptemplete-List Kategori Barang.xls`** → tombol *Import Kategori* (443 kategori).

### 6. Petakan produk (sekali, ~7 baris)
Import satu file order dulu, lalu di tab **Master Data** akan muncul daftar **Produk Belum Dipetakan**. Isi untuk tiap kombinasi:

**Semua kolom sudah terisi otomatis** — tugas Anda hanya memeriksa dan mengoreksi yang kurang pas, lalu simpan sekali.

| Kolom | Diisi otomatis dari |
|---|---|
| SKU Stok | **terkunci** — ditentukan sistem, dijamin unik dan tidak terpecah |
| Nama Barang J&T | nama produk yang **sudah dirapikan**: tanda kurung, kode awalan (`SF -`), kata promo, dan nomor urut dibuang → `(SF - Semprotan Noozle)` menjadi `Semprotan Noozle` |
| Rincian Isi | `3 pcs Semprotan Noozle (Beli 2 Gratis 1)` — masuk ke kolom Keterangan resi, acuan tim gudang |
| Kategori | **ditebak dari nama barang**; dikosongkan bila sistem tidak yakin |
| Pcs per order | dibaca dari teks promo pada Variation |

> Promo dibaca benar: *"Beli 1 Gratis 1"* → **2 pcs**, *"Beli 2 Gratis 1"* → **3 pcs**, *"Beli 1"* → **1 pcs**.

**Cara sistem menebak kategori** (tiga lapis, berhenti di yang pertama cocok):

1. **Belajar** — produk yang sudah pernah Anda petakan dan namanya mirip (≥85%) → pakai kategori yang sama. Makin sering dipakai, makin pintar.
2. **Harfiah** — seluruh kata nama kategori muncul di nama produk (mis. `Sikat Gigi Elektrik` → kategori `Sikat Gigi`).
3. **Kamus kata kunci** — menjembatani celah makna: `Gelang` → `Perhiasan`, `Vacum/Charger/Lampu` → `Elektronik`, `Sikat/Semprotan/Lap` → `Peralatan Rumah Tangga`. Kamusnya ada di `Stok.gs` (`KAMUS_KATEGORI`) dan bebas Anda tambah.

Kalau ketiganya gagal, kategori **dibiarkan kosong** — lebih baik kosong daripada salah.

#### Satu barang, banyak nama — aturannya: **1 barang = 1 SKU**

OrderOnline sering menulis barang yang sama dengan format berbeda: `Semprotan Noozle 04` dan `(SF - Semprotan Noozle)`. Barangnya identik, jadi stoknya **harus satu SKU**. Yang berbeda hanya *varian pembelian* (beli 1 / beli 2 gratis 1) — itu diwakili kolom **Pcs**, bukan SKU baru.

Sistem menormalkan nama dulu, lalu **menetapkan sendiri** SKU-nya (kolomnya terkunci). Urutan pengecekannya:

1. nama atau alias persis sudah terdaftar → SKU lama
2. nama beda format tapi bentuk kanoniknya sama → SKU lama
3. mirip ≥93% dengan SKU terdaftar → SKU lama
4. mirip ≥93% dengan **baris lain di daftar yang sama** (dua-duanya sama-sama baru) → SKU yang sama
5. selain itu → SKU baru yang dijamin unik

Titik 4 penting: kalau `Semprotan Noozle 04` dan `(SF - Semprotan Noozle)` sama-sama produk baru dan muncul berbarengan di daftar, keduanya tetap dapat **satu SKU**, bukan dua.

Ikon di sebelah kode SKU menjelaskan keputusannya: **✓** disatukan ke SKU yang sudah ada atau ke baris lain; **+** produk baru; **!** kode produk OrderOnline bentrok dengan SKU milik produk lain (sistem membuat kode baru agar stok tidak tercampur).

Sekali disimpan, nama versi itu dicatat sebagai **alias** di sheet `REF_SKU_ALIAS`. Import berikutnya dengan nama yang sama langsung dikenali.

> Ambangnya 93% karena `Lampu LED 3W` dan `Lampu LED 5W` mirip 90% padahal barangnya berbeda. Saat ragu sistem memilih **memisahkan** — kalau ternyata keliru, satukan lewat **Gabung SKU**. Itu jauh lebih aman daripada stok dua produk berbeda terlanjur tercampur.

#### Kalau terlanjur terpecah: **Gabung SKU**
Card *Gabung SKU* di tab Master Data menyatukan dua SKU yang ternyata barang yang sama. Pilih SKU asal dan tujuan → **Pratinjau** (lihat hasil stok & HPP) → **Gabungkan**. Yang terjadi: stok dijumlahkan per gudang dengan **HPP rata-rata tertimbang**, seluruh pemetaan produk dan order dialihkan ke SKU tujuan, mutasi tercatat di `STOK_MUTASI` (ref `GABUNG`), dan nama lama disimpan sebagai alias supaya tidak terpecah lagi. **Tidak bisa dibatalkan.**

### 6b. Petakan bump / bundling tambahan

OrderOnline punya fitur **bump** (bundling tambahan saat checkout). Di file export, bump muncul di kolom `bump` — tapi **hanya sebagai nama**, tanpa `product_code`. Kalau tidak ada bump, isinya `-` (bukan sel kosong).

Karena itu tiap nama bump perlu ditunjuk ke **SKU stok** lewat card **Bump / Bundling Belum Dipetakan** di Master Data. SKU ditentukan sistem (dikunci) dengan aturan yang sama seperti pemetaan produk — kalau bump-nya barang yang sudah ada di gudang, otomatis nyambung ke SKU itu; kalau produk baru, SKU dibuat otomatis dan masuk ke Stok dengan **saldo 0** (isi lewat *↓ Stok Masuk*). Satu tombol untuk seluruh tabel.

> Order yang bump-nya belum dipetakan **ditahan** di status *Perlu Mapping*. Ini disengaja: tanpa SKU, stok bump mustahil dipotong dengan benar dan paket berisiko terkirim tanpa isi yang sudah dibayar konsumen.

**Yang terjadi setelah bump dipetakan:**

| Hal | Perilaku |
|---|---|
| **Keterangan resi J&T** | bump ikut disebut → `2 pcs Sikat Punggung + 1 pcs Kunci Gembok Motor - Hubungi penerima` |
| **Stok** | dipotong **dua-duanya** — barang utama *dan* bump |
| **Siap kirim** | hanya kalau **kedua** SKU mencukupi. Kalau stok bump habis, order **tetap Pending Stok** walau barang utamanya ada |
| **Nilai Barang** | `product_price + bump_price` (mis. 65.000 + 44.500 = **109.500**) |
| **COD** | tidak berubah — `gross_revenue` dari OO sudah termasuk harga bump |
| **Pcs bump** | diasumsikan **1 pcs**/order (OO tidak mengirim qty bump); bisa diubah di tabel pemetaan |

> **Catatan teknis:** kolom `product_price` di sheet ORDERS sengaja **tidak** ditambahi `bump_price`. Penjumlahan hanya dilakukan saat membuat resi. Kalau digabung di ORDERS, perhitungan **harga jual per pcs** (tab Stok) akan tercemar harga bump dan nilai jual stok jadi salah.
>
> **Produk tambahan lewat kolom `notes`** (teks bebas + `other_cost`) **tidak** diproses sistem — isinya terlalu dinamis dan berisiko salah memotong stok. Kalau ada order semacam itu, sesuaikan keterangan resi & stoknya secara manual.

### 7. Isi stok awal
Tab **Master Data → Stok Gudang**. Tersedia **CRUD penuh**:

- **Tambah SKU** — form di atas tabel (SKU, nama produk, stok awal).
- **Ubah** — nama & jumlah stok bisa diedit langsung di tabel, klik *Simpan*. Nilai stok di sini bersifat **mutlak** (mengganti, bukan menambah) — pakai ini untuk koreksi/stok opname.
- **Hapus** — SKU yang masih dipakai order aktif akan **ditolak**, dengan opsi hapus paksa setelah konfirmasi. Kolom *Dipakai order* menunjukkan berapa order aktif memakai SKU itu.
- **Stok Masuk** (form bawah) — untuk barang datang; menambah jumlah **dan tercatat di riwayat** `STOK_MASUK`. Gunakan ini untuk penerimaan barang rutin.

### Nilai jual stok (tab 5 · Stok)

Selain **nilai persediaan** (modal, dari HPP), tab Stok menampilkan **nilai jual stok terkini** — berapa rupiah stok yang ada sekarang kalau habis terjual — beserta **potensi margin** (nilai jual − modal). Angkanya juga dirinci per barang di kolom *Jual/pcs* dan *Nilai jual*.

**Dari mana harga jualnya?** Dari `product_price` OrderOnline. Tapi harga itu adalah harga **satu order**, dan satu order bisa berisi 1, 2, atau 4 pcs tergantung varian promo — jadi tidak bisa dipakai mentah-mentah sebagai harga satuan. Sistem membaginya dengan jumlah pcs order tersebut lebih dulu, lalu merata-ratakan **secara tertimbang**: `total rupiah ÷ total pcs`.

Contoh: 10 order @1 pcs Rp100.000 + 1 order @4 pcs Rp300.000 → `(1.000.000 + 300.000) ÷ (10 + 4)` = **Rp92.857/pcs**.

> Kenapa tertimbang, bukan rata-rata biasa? Rata-rata biasa dari harga satuan tiap order menghasilkan Rp97.727 — terlalu optimistis, karena order bundel 4 pcs yang murah per pcs hanya dihitung sebagai *satu* sampel padahal menyumbang 4 pcs. Tertimbang mencerminkan harga jual yang benar-benar terjadi.

**Kalau produk belum pernah terjual** (belum ada order dengan `product_price`), harga otomatisnya belum ada — ditandai **belum ada**. Tinggal **ketik harganya langsung di kolom Jual/pcs**, lalu klik **Update Harga Jual** — **satu tombol untuk seluruh tabel**, bukan per baris. Tombolnya menampilkan berapa baris yang berubah dan baru aktif kalau memang ada perubahan.

Nilai jual, margin, total di kaki tabel, dan KPI **langsung ikut berhitung saat Anda mengetik** (sebelum disimpan), jadi efeknya terlihat dulu sebelum diputuskan. Yang belum disimpan ditandai di KPI: *"N belum disimpan"*.

| Tanda | Arti |
|---|---|
| **otomatis** | harga dihitung dari order OrderOnline (arahkan kursor untuk lihat dari berapa order) |
| **manual** | harga diisi admin — **mengalahkan** hitungan otomatis (tooltip menampilkan berapa harga otomatisnya, sebagai pembanding) |
| **belum ada** | belum pernah terjual & belum diisi — tidak ikut dijumlahkan ke total |

Harga manual disimpan di sheet **`REF_HARGA_JUAL`** (per SKU, bukan per gudang, lengkap dengan siapa & kapan mengisinya). **Kosongkan** isian lalu Update untuk menghapus harga manual — harganya kembali dihitung otomatis dari OrderOnline.

> Jalankan `setup()` sekali setelah update ini agar sheet `REF_HARGA_JUAL` terbentuk.

---

## Alur kerja harian

**① Import Order** — upload export *processing* OrderOnline. Order yang sudah pernah masuk otomatis dilewati (anti-duplikat). Order dengan kurir kosong muncul di daftar *Perlu Cek Kurir* untuk Anda setujui satu per satu.

**② Stok & Kirim** — lihat kebutuhan pcs per SKU vs stok gudang. Order diurutkan **FIFO** dan yang stoknya cukup **otomatis tercentang**; sisanya jadi *Pending Stok*. Klik **Buat Batch** → sistem memotong stok, mengunci order, dan menghasilkan **file .xlsx siap upload ke J&T** (kolomnya persis template Anda).

**③ Tracking** — alur tiga langkah, tidak ada yang tersimpan sebelum Anda menyetujuinya:

1. Upload export **Url-Tracking** dari J&T → klik **Proses**. Sistem hanya *membaca* file, belum menulis apa pun.
2. Muncul **tabel hasil transform**: AWB, URL tracking, akun, `order_id`, nama produk, penerima. Baris yang **tidak cocok ditandai merah** dan bisa Anda perbaiki langsung di tabel (isi/ubah akun & `order_id`), atau hapus dari daftar.
3. Klik **Simpan & Export CSV** → sistem menulis AWB + URL ke order, mengubah statusnya jadi *Tracking Terkirim ke OO*, lalu mengunduh **satu CSV per akun OrderOnline** berisi `order_id, receipt_number (URL), payment_status=paid`.

Pencocokan memakai `AKUN-order_id` yang disisipkan di **Nama Barang** saat batch dibuat (dipisah spasi — J&T mengubah karakter `#` menjadi `,`, jadi pemisah khusus tidak dipakai lagi).

**Riwayat Export** ada di tabel paling bawah tab ini: setiap CSV yang pernah dibuat (paid maupun unpaid/retur) bisa **diunduh ulang** kapan saja.

**④ Retur** — upload file retur J&T, atau tarik langsung dari Sistem CS Undelivered → unduh CSV yang sama dengan `payment_status=unpaid`. Ini pun tercatat di Riwayat Export.

---

## Handover Resi Harian (pickup J&T)

Ada di tab **2 · Kirim**, di bawah Riwayat Batch. Dokumen serah-terima paket ke kurir J&T.

Resi dikelompokkan per **tanggal batch** (kapan paket disiapkan) dan hanya memuat order yang **sudah punya nomor resi** — jadi handover baru muncul setelah nomor resi masuk lewat tab Tracking. Tiap baris menampilkan tanggal (*Jumat, 17 Jul 2026*), total resi, total nilai barang, dan sebaran akun OO.

| Ikon | Fungsi |
|---|---|
| **👁** | rincian resi hari itu — nomor resi, nilai barang, akun, order_id, penerima, kota, batch, status |
| **🖨** | cetak PDF handover — **pilih tanggal pickup dulu**, baru Proses |

**Kenapa tanggal pickup dipisah dari tanggal batch?** Karena sering berbeda: paket dibatch sore, dijemput kurir keesokan harinya. Bawaannya sama dengan tanggal batch, tinggal diubah bila perlu — yang tercetak di PDF adalah tanggal pickup pilihan Anda.

**Isi PDF:** judul **HANDOVER**, subjudul *BACK-UP DATA PEMERIKSAAN & PERHITUNGAN*, tanggal pick up, ekspedisi JNT, lalu tabel resi bergaya dokumen Anda — **4 kelompok kolom × 20 baris = 80 resi per halaman**. Untuk >80 resi, PDF berhalaman otomatis; nomor urut lanjut menyambung antar-halaman, tiap halaman diberi *"Halaman n dari N"*, dan **blok tanda tangan ada di setiap halaman**: *Disetujui Oleh* (GUDANG MEIKA JAYA ABADI — **Wasrip**, Kepala Administrasi Gudang), *Diketahui Oleh* (Supervisi Ekspedisi), *Diperiksa Oleh* (Kurir). **Total Resi & Total Nilai Barang hanya di halaman terakhir**; halaman sebelumnya menampilkan subtotal per halaman supaya tidak rancu.

**Nilai Barang** = `product_price + bump_price` — sama persis dengan yang dikirim ke J&T, jadi angkanya cocok saat dicek silang dengan data ekspedisi.

> Order yang belakangan **retur tetap ikut** di handover. Ini disengaja: paketnya memang benar-benar diserahkan hari itu, dan dokumen handover adalah catatan historis — isinya tidak boleh berubah gara-gara status paket berubah kemudian.

Pengaturan tata letak & nama penanda tangan ada di `HO` pada `Handover.gs` (`barisPerKolom`, `kolomPerHalaman`, `ttdNama`, `ttdJabatan`, `gudang`).

---

## Pengaman yang sudah tertanam

- **Anti-duplikat order** — `order_id` yang sudah ada tidak diimport ulang.
- **Anti kirim dua kali** — order yang sudah punya Batch ID ditolak keras saat pembuatan batch.
- **Validasi ulang di server** — sistem tidak percaya centang di layar; stok, wilayah, dan produk dicek ulang sebelum batch dibuat.
- **Stok dipotong di dalam `LockService`** — mustahil minus karena dua admin klik bersamaan.
- **Order tidak bisa dikirim** kalau wilayah belum valid atau produk belum dipetakan — mencegah upload J&T ditolak.
- **Sheet `LOG`** — jejak audit semua aksi.

---

## Hasil uji dengan data asli Anda (142 order)

| Yang diuji | Hasil |
|---|---|
| Normalisasi wilayah | **89% valid otomatis** (dari 49% mentah) |
| Saran wilayah untuk sisanya | **16 dari 16 berkeyakinan tinggi (≥85%)**, tanpa regresi pada 125 wilayah yang sudah valid |
| Pcs dari promo | Benar semua, termasuk kasus *"Beli 2 Gratis 1" = 3 pcs* |
| Nilai COD | `gross_revenue`; 3 order non-COD → 0 |
| Alokasi stok FIFO | Tidak pernah melebihi stok; order terlama diprioritaskan |
| Pencocokan AWB → order_id | **100% akurat** |

---

## Konfigurasi yang mungkin perlu disesuaikan

Di `Code.gs` bagian `CFG`:

```javascript
csSpreadsheetId: '',   // ID spreadsheet Sistem CS Undelivered (untuk fitur Retur otomatis)
driveFolderId:   '',   // folder Drive tempat menyimpan file hasil; '' = My Drive
jumlahKoli:      1,    // kolom "Jumlah" di template J&T
```

**Tentang `jumlahKoli`:** template Anda selama ini selalu diisi **1**, jadi saya ikuti. Kalau ternyata J&T menghitung ongkir per pcs (bukan per paket), ubah nilainya agar mengambil `Pcs`.

**Tentang `#Akun-order_id` di Nama Barang:** kode ini (mis. `#A1-276121736`) **tercetak di label paket** dan merupakan **satu-satunya kunci** pencocokan resi ke order. Kode akun ikut disisipkan supaya order_id dari **akun OrderOnline berbeda tidak tertukar**. Jangan diubah/dihapus manual sebelum upload ke J&T — kalau hilang, sistem terpaksa memakai pencocokan cadangan (nama + kecamatan + barang) yang bisa ambigu.

**Migrasi:** kalau sheet `ORDERS` sudah terlanjur dibuat dengan versi lama, jalankan `setup` sekali lagi — kolom baru (`Akun OO`, `Diimport Oleh`) ditambahkan otomatis tanpa merusak data lama.

---

## Update kode tanpa mengganti URL (penting)

Ini sering salah dan bikin bingung — merasa sudah deploy tapi aplikasi masih versi lama.

1. **Save** kode di editor Apps Script.
2. Naikkan `APP_VERSION` di `Code.gs` (mis. `'v6 — perbaikan X'`). Ini bukan sekadar kosmetik: versinya **tampil di pojok kanan atas aplikasi**, jadi Anda bisa langsung memastikan deployment sudah memakai kode terbaru.
3. **Deploy → Manage deployments**.
4. Pilih deployment yang **Deployment ID-nya sama dengan link yang Anda bagikan**. (Lihat URL: `.../macros/s/AKfycb…/exec` — bagian `AKfycb…` itu ID-nya. Kalau ada beberapa deployment, jangan sampai salah pilih.)
5. Klik ikon **pensil (Edit)**.
6. **Buka dropdown "Version" → pilih "New version".** ⚠️ **Ini langkah yang paling sering terlewat.** Dropdown ini defaultnya masih menunjuk versi lama; kalau tidak diubah, Deploy tetap berhasil tapi **kode lama yang jalan**. Inilah sebabnya membuat *New deployment* terasa "berhasil" sementara *Edit* tidak.
7. Isi description → **Deploy**.

URL tidak berubah, kode langsung yang terbaru.

### Yang terjadi otomatis setelah deploy baru

**Halaman yang sedang dibuka user.** Halaman tidak tahu kodenya sudah diganti — maka aplikasi **membandingkan versinya sendiri dengan versi di server** setiap 1,5 menit dan setiap kali user kembali ke tab. Kalau berbeda, muncul banner hitam di atas: *"Versi baru tersedia"* + tombol **Muat ulang sekarang**. Tombol ✕ menundanya 10 menit. Karena itu **wajib menaikkan `APP_VERSION` setiap deploy** — kalau versinya tidak diubah, banner tidak akan muncul dan user tetap memakai kode lama sampai me-refresh sendiri.

**Cache server (`CacheService`).** Kunci cache diikat ke `APP_VERSION`, jadi begitu versi naik, seluruh cache lama otomatis tidak terpakai (kuncinya beda). Tidak perlu dibersihkan manual, dan mustahil kode baru membaca data berformat lama.

**Cache browser.** Halaman sudah memakai meta `no-cache`, dan tombol muat ulang menambahkan `?v=<timestamp>` pada URL agar benar-benar mengambil versi baru.

### Soal cookie

Cookie **tidak dihapus, dan memang sebaiknya tidak**. Aplikasi ini tidak menyimpan apa pun di cookie — satu-satunya cookie di domain itu milik **sesi login Google Anda**. Menghapusnya berarti membuat user logout dan harus login ulang, tanpa manfaat apa pun. Masalah "versi lama" bukan berasal dari cookie, melainkan dari tiga hal di atas (deployment version, cache server, cache browser) yang semuanya sudah ditangani.

**Kalau masih terlihat versi lama:** buka dengan **Ctrl+Shift+R** (hard refresh), atau tambahkan `?v=2` di akhir URL sekali saja untuk memaksa lewat cache. Halaman ini sudah memuat meta anti-cache, tapi CDN Google kadang menahan beberapa menit. Cek badge versi di pojok kanan atas untuk memastikan.
