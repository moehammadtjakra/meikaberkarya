# Identitas Visual TitikOrder

Dokumen ini menjawab satu masalah spesifik: **kenapa tampilan buatan AI terasa hambar dan seragam** — lalu memberi keputusan estetis yang membuat produk ini terasa punya tangan manusia.

Berpasangan dengan `DESIGN_SYSTEM.md` (aturan perilaku UI). Dokumen itu mengatur **cara kerja**; dokumen ini mengatur **rasa**.

---

## 1. Akar masalahnya

Tampilan terasa "buatan AI" bukan karena AI tidak mampu, tapi karena AI **mengambil nilai bawaan** setiap kali tidak diberi arahan:

- font `Inter` (atau Roboto/Arial)
- palet `slate`/`zinc` bawaan Tailwind — abu-abu kebiruan yang dingin
- gradien ungu-biru
- semua sudut membulat seragam, bayangan tebal di mana-mana
- ikon emoji, ilustrasi *undraw*, hero section yang tidak perlu

Kombinasi itu muncul di jutaan proyek, jadi otak kita mengenalinya sebagai "template". **Obatnya bukan menambah hiasan, tapi mengambil keputusan yang disengaja** dan menaatinya secara konsisten. Jiwa seni lahir dari konsistensi pilihan, bukan dari dekorasi.

---

## 2. Kepribadian

TitikOrder dipakai **8 jam sehari** oleh CS, gudang, dan finance. Ini bukan situs pemasaran yang dilihat 30 detik.

Tiga kata yang memandu setiap keputusan:

| Kata | Artinya di layar |
|---|---|
| **Tenang** | tidak berisik, tidak banyak warna bersaing, mata tidak lelah setelah berjam-jam |
| **Kokoh** | terasa dapat dipercaya untuk mengurus uang & stok; padat, rapi, presisi |
| **Cekatan** | cepat direspons, sedikit langkah, tidak ada animasi yang membuat menunggu |

**Bukan**: playful, glossy, futuristik, atau "startup banget". Sistem yang mengelola uang COD tidak boleh terasa main-main.

---

## 3. Tipografi

**Antarmuka: Plus Jakarta Sans.**
Dipilih bukan sekadar karena bagus — huruf ini memang dirancang untuk identitas kota Jakarta. Ada ceritanya, cocok untuk produk Indonesia, dan **bukan Inter**. Bentuk hurufnya lebih hangat dan sedikit lebih berkarakter tanpa mengorbankan keterbacaan.

**Angka & kode: JetBrains Mono** (atau Geist Mono).
Wajib untuk kolom uang, nomor resi, dan SKU. Alasannya teknis: **angka rata lebar (tabular)** membuat kolom rupiah sejajar sempurna, sehingga selisih angka langsung terlihat mata. Ini bukan gaya — ini fungsi.

Aturan:

- Maksimal **4 ukuran** di seluruh aplikasi. Hierarki dibuat dengan ukuran + bobot, bukan dengan warna.
- Hanya dua bobot: **400** dan **600**. Jangan 300 (tipis, buruk di layar murah) dan jangan 800.
- Angka penting boleh besar (kartu ringkasan), tapi **hanya satu angka besar per layar**.
- Judul memakai *sentence case*, bukan Title Case, bukan HURUF BESAR SEMUA.

---

## 4. Warna

Menjauh dari `slate` bawaan. Netral memakai **`stone`** — abu-abu hangat, jauh lebih nyaman untuk pemakaian panjang.

| Peran | Pilihan | Kenapa |
|---|---|---|
| Primer | **teal tua / petrol** (bukan biru generik) | tenang, dapat dipercaya, berbeda dari biru SaaS |
| Netral | **stone** (hangat) | ramah mata setelah berjam-jam |
| Sukses | hijau tua | pasti, bukan neon |
| Peringatan | amber | terbaca di layar HP murah di bawah lampu gudang |
| Bahaya | merah bata | serius, bukan merah menyala |

Aturan:

- **Warna hanya untuk makna**, tidak pernah untuk dekorasi. Kalau sebuah elemen berwarna, warnanya harus punya arti.
- **Satu warna aksen per layar.** Kalau ada tiga hal berwarna bersaing, tidak ada yang menonjol.
- **Dilarang gradien** kecuali sangat halus pada satu elemen tanda tangan (§7).
- Status wajib **warna + teks + bentuk** — jangan warna saja (buta warna, cetak hitam-putih, layar redup di gudang).

---

## 5. Ruang & ritme

Ini yang paling sering membuat tampilan terasa "belum jadi": jarak yang seragam di mana-mana.

- Skala jarak: `4 · 8 · 12 · 16 · 24 · 32 · 48`. Jangan angka acak.
- **Kepadatan berbeda per jenis layar** — inilah variasi yang dimaksud:
  - **Layar kerja** (daftar order, worklist CS): padat, banyak baris terlihat, jarak kecil
  - **Layar ringkasan** (dashboard, laporan): lapang, ada ruang bernapas
  - **Layar aksi** (form, konfirmasi): fokus, satu kolom, ruang lebar
- Garis batas tipis (`1px`) lebih dipilih daripada bayangan untuk memisahkan area.
- Bayangan hanya untuk elemen yang benar-benar melayang (sheet, dropdown, dialog). Bukan untuk kartu biasa.
- Radius: **8px** untuk kartu & tombol, **12px** untuk sheet/dialog. Dua nilai saja.

---

## 6. Gerak

Gerak berfungsi memberi tahu **apa yang terjadi**, bukan memamerkan.

- Durasi **150–200ms**, easing `ease-out`. Cukup terasa, tidak membuat menunggu.
- Sheet naik dari bawah, dialog memudar. Konsisten arah datangnya.
- **Tidak ada** animasi memantul (spring), parallax, atau elemen yang muncul saat digulir. Itu bahasa situs pemasaran.
- Perubahan status (berhasil/gagal) **wajib** ada umpan balik gerak halus — supaya perubahan tidak terlewat.
- Hormati `prefers-reduced-motion`.

---

## 7. Satu elemen tanda tangan

Agar produk punya wajah yang diingat, pilih **satu** ciri khas dan pakai konsisten di seluruh aplikasi:

> **Aksen "titik"** — sebuah titik kecil berwarna sebagai penanda status dan penegas, sejalan dengan nama TitikOrder. Muncul di indikator status, penanda item aktif di navigasi, dan sebagai bullet pada ringkasan.

Satu ciri yang diulang konsisten jauh lebih kuat daripada lima ide yang dipakai sekali-sekali. **Jangan tambah ciri kedua.**

---

## 8. Ikon & gambar

- **Satu keluarga ikon** saja (Lucide). Jangan campur.
- **Dilarang emoji sebagai ikon UI.** Emoji berbeda bentuk di tiap perangkat dan terlihat tidak profesional pada sistem keuangan.
- Ikon selalu berpasangan dengan teks pada aksi penting. Ikon sendirian hanya untuk aksi yang sangat lazim (tutup, cari).
- **Tidak ada ilustrasi stok** (undraw dan sejenisnya). Untuk status kosong, cukup ikon garis sederhana + kalimat jelas + tombol aksi.
- Foto hanya foto produk asli.

---

## 9. Daftar larangan — penanda "tampilan AI"

Kalau salah satu muncul, tampilan langsung terasa template:

- ❌ Font `Inter`, `Roboto`, `Arial`, atau font bawaan sistem
- ❌ Palet `slate`/`zinc` bawaan tanpa penyesuaian
- ❌ Gradien ungu→biru
- ❌ Glassmorphism / blur latar berlebihan
- ❌ Bayangan tebal di setiap kartu
- ❌ Emoji sebagai ikon
- ❌ Hero section atau *marketing copy* di aplikasi internal
- ❌ Teks contoh "Lorem ipsum" atau kalimat generik ("Manage your data efficiently")
- ❌ Semua tombol berukuran sama tanpa hierarki
- ❌ Kartu statistik seragam berjejer empat tanpa alasan

---

## 10. Variasi tanpa kekacauan

Permintaan "dinamis, tidak monoton" mudah berubah jadi berantakan. Batasnya:

**Boleh bervariasi:** kepadatan tata letak per jenis layar · susunan kolom · cara data disajikan (tabel, kartu, garis waktu, grafik) · penekanan angka utama.

**Tidak boleh bervariasi:** font · palet · radius · skala jarak · gaya ikon · pola navigasi · lokasi tombol utama.

Prinsipnya: **variasi ada di komposisi, bukan di komponen.** Sama seperti musik — nada dasarnya tetap, aransemennya yang berbeda tiap lagu.

---

## 11. Cara menilai hasil

Sebelum menyatakan sebuah layar bagus, jawab jujur:

1. Kalau logo dilepas, apakah masih bisa dibedakan dari template Tailwind mana pun? Kalau tidak — belum selesai.
2. Apakah mata tahu **ke mana harus melihat pertama**? Kalau semuanya menonjol, tidak ada yang menonjol.
3. Apakah nyaman dilihat setelah **dua jam**? Bukan sekadar menarik dalam 5 detik pertama.
4. Apakah setiap warna di layar itu **punya arti**?
5. Apakah ada **satu** hal yang paling ditonjolkan, bukan tiga?
