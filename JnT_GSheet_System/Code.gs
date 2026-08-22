/**
 * ============================================================================
 *  J&T DATA LOADER — Meika Berkarya
 *  Pengganti Power Query (Excel) untuk All Resi & Settle Reconcile.
 *
 *  Alur: User upload file (.xlsx / .xls) lewat web app  ->  file dikonversi
 *  Google Sheets sementara (Drive)  ->  di-transform sesuai kode M Power Query
 *  ->  di-UPSERT (update-or-insert) ke sheet tujuan berdasarkan "No. Waybill".
 *
 *  Dua dataset dijaga sebagai SHEET TERPISAH (persis dua query PQ Anda).
 * ============================================================================
 */

// Dinaikkan SETIAP kali deploy versi baru. Halaman yang sedang terbuka
// membandingkan versinya dengan versi di server; kalau beda -> banner "versi
// baru" muncul dan user cukup klik "Muat ulang" (tanpa hapus cache manual).
var APP_VERSION = 'v2.9 — report produk: tambah CPC, CPM, daily budget, link click, LPV';

// ---------------------------------------------------------------------------
// KONFIGURASI
// ---------------------------------------------------------------------------

// Kosongkan ('') kalau script ini TERIKAT pada spreadsheet (Extensions >
// Apps Script dari dalam Sheet). Isi dengan ID spreadsheet kalau script
// berdiri sendiri (standalone). ID = bagian URL antara /d/ dan /edit.
var SPREADSHEET_ID = '';

function getSpreadsheet() {
  return SPREADSHEET_ID ? SpreadsheetApp.openById(SPREADSHEET_ID)
                        : SpreadsheetApp.getActiveSpreadsheet();
}

// Set false kalau sheet sudah berupa Table (tipe kolom dikunci oleh Table,
// sehingga setNumberFormat akan ditolak). Table mengatur formatnya sendiri.
var APPLY_NUMBER_FORMATS = false;

/**
 * Definisi kolom setiap dataset.
 * type: 'text' | 'int' | 'num' | 'date' | 'any'
 * from: nama kolom di file sumber (kalau beda dengan nama output)
 * calc: 'codfee' | 'nilaiproduk' (kolom hitung)
 * forceText: paksa format sel = teks (untuk No. Waybill & telepon)
 */
var CONFIG = {
  allResi: {
    sheetName: 'All Resi',
    keyCol:  'No. Waybill',
    sortCol: 'Tanggal Pengiriman',
    rangeCol: 'Tanggal Pengiriman',  // kolom acuan rentang tanggal di Riwayat Upload
    // kolom sumber yang WAJIB ada untuk validasi slot upload
    requireCols: ['No. Waybill', 'Tanggal Pengiriman', 'Biaya Kirim'],
    columns: [
      { name: 'No. Waybill',                type: 'text', forceText: true },
      { name: 'Tanggal Pengiriman',         type: 'date' },
      { name: 'Klien Pengirim',             type: 'text' },
      { name: 'Nama Pengirim',              type: 'text' },
      { name: 'Telepon Pengirim',           type: 'text', forceText: true },
      { name: 'Kota Pengirim',              type: 'text' },
      { name: 'Kecamatan Pengirim',         type: 'text' },
      { name: 'Alamat Pengirim',            type: 'text' },
      { name: 'Penerima',                   type: 'text' },
      { name: 'Telepon Penerima',           type: 'text', forceText: true },
      { name: 'Provinsi Penerima',          type: 'text' },
      { name: 'Kota Penerima',              type: 'text' },
      { name: 'Kecamatan Penerima',         type: 'text' },
      { name: 'Alamat Penerima',            type: 'text' },
      { name: 'Jumlah Barang',              type: 'int' },
      { name: 'Tipe Barang',                type: 'text' },
      { name: 'Berat',                      type: 'int' },
      { name: 'Nilai Barang',               type: 'int' },
      { name: 'Layanan',                    type: 'text' },
      { name: 'Metode Pembayaran',          type: 'text' },
      { name: 'Nama Barang',                type: 'text' },
      { name: 'Kategori Barang',            type: 'text' },
      { name: 'Biaya Kirim',                type: 'num' },
      { name: 'Biaya Asuransi',             type: 'int' },
      { name: 'Biaya Lainnya',              type: 'int' },
      { name: 'Total Biaya',                type: 'num' },
      { name: 'Nilai Voucher',              type: 'any' },
      { name: 'Tanda Diskon',               type: 'text' },
      { name: 'Biaya Diskon',               type: 'num' },
      { name: 'Total Biaya Setelah Diskon', type: 'num' },
      { name: 'Nilai COD',                  type: 'num',  from: '代收货款金额' }, // 代收货款金额
      { name: 'COD Fee',                    type: 'num',  calc: 'codfee' },
      { name: 'Diterima Oleh',              type: 'text' },
      { name: 'Hubungan',                   type: 'text' },
      { name: 'Waktu Terima',               type: 'date' },
      { name: 'Keterangan',                 type: 'text' },
      { name: 'Tanda TTD',                  type: 'text' },
      { name: 'Alasan Void',                type: 'any' },
      { name: 'Sumber Order',               type: 'text' },
      { name: 'Catatan Pengirim untuk kurir', type: 'any' },
      { name: 'Catatan Penerima untuk Kurir', type: 'any' },
      { name: 'Apakah Paket Abnormal?',     type: 'text' },
      { name: 'COD',                        type: 'text' },
      { name: 'Nilai Produk',               type: 'num',  calc: 'nilaiproduk' }
    ]
  },

  reconcile: {
    sheetName: 'Settle Reconcile',
    keyCol:  'No. Waybill',
    sortCol: 'Waktu TTD',
    rangeCol: 'Waktu TTD',          // kolom acuan rentang tanggal di Riwayat Upload

    /**
     * J&T mengganti format file Settle Reconcile. DUA format didukung sekaligus,
     * dengan hasil di sheet & fungsi hilir (dashboard pencairan) TETAP SAMA:
     *
     *   Format lama "COD Reconciliation Details" (11 kolom):
     *     No. Waybill | Waktu TTD | TTD | Status Retur | Penerima | DP TTD |
     *     COD | Jenis Layanan | Jenis Barang | Lokasi (Asal) | Tujuan
     *   Format baru "COD佣金对账明细票数" (7 kolom):
     *     No. Waybill | No. Order | Jenis Layanan | Bulan | Waktu Terima |
     *     Nominal COD | Komisi COD
     *
     * Yang berubah cuma NAMA kolomnya -> ditangani lewat alias 'from' (array):
     *   Waktu TTD  <- 'Waktu TTD'  (lama)  ATAU 'Waktu Terima' (baru)
     *   COD        <- 'COD'        (lama)  ATAU 'Nominal COD'   (baru)
     *
     * Kolom skema tetap 11 (tidak diubah) supaya sheet & dashboard tidak
     * terpengaruh. Kolom yang tak ada di suatu format dibiarkan kosong.
     * Downstream hanya butuh No. Waybill + Waktu TTD, jadi keduanya terisi
     * apa pun formatnya.
     */
    requireCols: ['No. Waybill'],
    requireAny:  [['Waktu TTD', 'Waktu Terima']],   // minimal satu dari grup ini ada
    columns: [
      { name: 'No. Waybill',   type: 'text', forceText: true },
      { name: 'Waktu TTD',     type: 'date', from: ['Waktu TTD', 'Waktu Terima'] },
      { name: 'TTD',           type: 'text' },
      { name: 'Status Retur',  type: 'text' },
      { name: 'Penerima',      type: 'text' },
      { name: 'DP TTD',        type: 'text' },
      { name: 'COD',           type: 'int',  from: ['COD', 'Nominal COD'] },
      { name: 'Jenis Layanan', type: 'text' },
      { name: 'Jenis Barang',  type: 'text' },
      { name: 'Lokasi (Asal)', type: 'text' },
      { name: 'Tujuan',        type: 'text' }
    ]
  }
};

// ---------------------------------------------------------------------------
// WEB APP ENTRY
// ---------------------------------------------------------------------------

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('J&T Data Loader — Meika Berkarya')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Cek versi — SENGAJA seringan mungkin, dipanggil berkala oleh halaman terbuka. */
function getVersi() { return APP_VERSION; }

/** URL web app aktif — untuk memuat ulang halaman ke versi terbaru (bust cache). */
function getWebAppUrl() {
  try { return ScriptApp.getService().getUrl(); } catch (e) { return ''; }
}

/**
 * Dipanggil dari front-end. Mengembalikan ringkasan proses.
 * @param {string} b64       isi file (base64, tanpa prefix data:)
 * @param {string} filename  nama file asli
 * @param {string} datasetKey 'allResi' | 'reconcile'
 */
function processUpload(b64, filename, datasetKey) {
  return processUploadFiles([{ b64: b64, name: filename }], datasetKey);
}

/**
 * MULTI-FILE: proses beberapa file sekaligus dalam SATU submit.
 * Semua file dibaca dulu, lalu ditulis ke sheet SEKALI jalan (bukan per file),
 * jadi jauh lebih cepat daripada mengupload satu per satu.
 *
 * @param {Array<{b64:string,name:string}>} files
 * @param {string} datasetKey 'allResi' | 'reconcile'
 */
function processUploadFiles(files, datasetKey) {
  var cfg = CONFIG[datasetKey];
  if (!cfg) throw new Error('Dataset tidak dikenal: ' + datasetKey);
  if (!files || !files.length) throw new Error('Belum ada file yang dipilih.');

  var batches = [], gagal = [], diproses = 0;

  files.forEach(function (f) {
    try {
      var rows = readUploadedSheet(f.b64, f.name);
      if (!rows.length) throw new Error('file kosong / tidak ada baris data');

      // Validasi slot: pastikan file memang untuk dataset ini.
      // - requireCols : semua kolom ini WAJIB ada.
      // - requireAny  : tiap grup butuh MINIMAL SATU kolom (untuk alias antar-format,
      //                 mis. "Waktu TTD" ATAU "Waktu Terima").
      var headerKeys = Object.keys(rows[0]);
      var missing = (cfg.requireCols || []).filter(function (c) { return headerKeys.indexOf(c) < 0; });
      var missingAny = (cfg.requireAny || []).filter(function (grp) {
        return !grp.some(function (c) { return headerKeys.indexOf(c) >= 0; });
      }).map(function (grp) { return grp.join(' / '); });
      if (missing.length || missingAny.length) {
        throw new Error('bukan file "' + cfg.sheetName + '" — kolom wajib tidak ada: ' +
                        missing.concat(missingAny).join(', '));
      }

      var out = rows.map(function (r) { return buildRow(r, cfg); });
      batches.push({ name: f.name, rows: out, jumlah: rows.length,
                     rentang: rentangTanggal_(out, cfg) });
      diproses += rows.length;
    } catch (e) {
      gagal.push({ name: f.name, pesan: (e && e.message) ? e.message : String(e) });
    }
  });

  if (!batches.length) {
    throw new Error('Tidak ada file yang bisa diproses. ' +
      gagal.map(function (g) { return g.name + ': ' + g.pesan; }).join(' | '));
  }

  var res = upsertBatches(cfg, batches);           // satu kali tulis untuk semua file
  catatRiwayat_(datasetKey, cfg, res.perFile);     // catat tiap file ke Riwayat_Upload
  try { dashCacheClear_(); } catch (e) {}          // data berubah -> cache dashboard direset

  return {
    sheetName: cfg.sheetName,
    jumlahFile: batches.length,
    processed: diproses,
    added: res.added, updated: res.updated, total: res.total,
    perFile: res.perFile,
    dilewati: res.dilewati,                        // baris file tanpa No. Waybill
    dupLamaDibersihkan: res.dupLamaDibersihkan,    // duplikat lama di sheet yang dibuang
    kosongLamaDibuang: res.kosongLamaDibuang,
    gagal: gagal
  };
}

/** Rentang tanggal (min–maks) pada kolom acuan dataset — untuk tabel riwayat. */
function rentangTanggal_(rows, cfg) {
  var idx = cfg.columns.map(function (c) { return c.name; }).indexOf(cfg.rangeCol || cfg.sortCol);
  if (idx < 0) return { awal: '', akhir: '' };
  var min = null, max = null;
  rows.forEach(function (r) {
    var v = r[idx];
    if (!(v instanceof Date)) return;
    if (!min || v < min) min = v;
    if (!max || v > max) max = v;
  });
  return { awal: min ? fmtDate(min) : '', akhir: max ? fmtDate(max) : '' };
}

/** Ringkasan jumlah baris tiap sheet (untuk ditampilkan saat halaman dibuka). */
function getStatus() {
  var ss = getSpreadsheet();
  function count(name) {
    var sh = ss.getSheetByName(name);
    return sh ? Math.max(0, sh.getLastRow() - 1) : 0;
  }
  return {
    spreadsheetName: ss.getName(),
    allResi:     count(CONFIG.allResi.sheetName),
    reconcile:   count(CONFIG.reconcile.sheetName),
    orderOnline: count(ORDER_CFG.sheetName)          // sheet OrderOnline (Order.gs)
  };
}

// ---------------------------------------------------------------------------
// BACA FILE UPLOAD  (xlsx/xls -> Google Sheet sementara via Drive)
// ---------------------------------------------------------------------------
/**
 * Catatan: file "Settle Reconcile" dari J&T berekstensi .xls tapi isinya
 * sebenarnya format OOXML (xlsx). Konversi Drive mendeteksi dari isi file,
 * jadi kedua jenis file tetap terbaca dengan benar.
 * Butuh "Advanced Drive Service" aktif (Services > Drive API).
 */
function readUploadedSheet(b64, filename) {
  var bytes = Utilities.base64Decode(b64);
  var blob = Utilities.newBlob(
    bytes,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    filename || 'upload.xlsx'
  );

  var tmp = driveConvertToSheet(blob);

  try {
    var sh = SpreadsheetApp.openById(tmp.id).getSheets()[0];
    var values = sh.getDataRange().getValues();
    if (values.length < 2) return [];

    var header = values[0].map(function (h) { return String(h).trim(); });
    var out = [];
    for (var i = 1; i < values.length; i++) {
      var row = values[i], obj = {}, blank = true;
      for (var j = 0; j < header.length; j++) {
        var v = row[j];
        obj[header[j]] = v;
        if (v !== '' && v !== null && v !== undefined) blank = false;
      }
      if (!blank) out.push(obj);
    }
    return out;
  } finally {
    // selalu bersihkan file sementara
    DriveApp.getFileById(tmp.id).setTrashed(true);
  }
}

/**
 * Konversi blob (xlsx/xls) menjadi Google Sheet sementara.
 * Mendukung Advanced Drive Service v3 (Files.create) maupun v2 (Files.insert).
 */
function driveConvertToSheet(blob) {
  var name = '__tmp_jnt_' + Date.now();
  if (typeof Drive.Files.create === 'function') {
    // Drive API v3
    return Drive.Files.create(
      { name: name, mimeType: MimeType.GOOGLE_SHEETS },
      blob,
      { supportsAllDrives: true }
    );
  }
  // Drive API v2
  return Drive.Files.insert(
    { title: name, mimeType: MimeType.GOOGLE_SHEETS },
    blob,
    { convert: true }
  );
}

// ---------------------------------------------------------------------------
// TRANSFORM 1 BARIS
// ---------------------------------------------------------------------------
/**
 * Pilih nilai sumber untuk sebuah kolom output.
 * `cand` boleh berupa string (satu nama) atau array nama (alias/format berbeda).
 * Untuk array: dipilih kolom PERTAMA yang benar-benar ada di file ini —
 * inilah yang membuat satu skema mendukung beberapa format J&T sekaligus.
 */
function pilihSumber_(raw, cand) {
  if (Object.prototype.toString.call(cand) === '[object Array]') {
    for (var i = 0; i < cand.length; i++) {
      if (Object.prototype.hasOwnProperty.call(raw, cand[i])) return raw[cand[i]];
    }
    return '';
  }
  return raw[cand];
}

function buildRow(raw, cfg) {
  var nilaiCOD   = asNum(raw['代收货款金额']); // 代收货款金额 -> Nilai COD
  var biayaKirim = asNum(raw['Biaya Kirim']);

  return cfg.columns.map(function (c) {
    if (c.calc === 'codfee') {
      return nilaiCOD === '' ? '' : nilaiCOD * 0.015;
    }
    if (c.calc === 'nilaiproduk') {
      return (nilaiCOD === '' || biayaKirim === '') ? '' : (nilaiCOD - biayaKirim);
    }
    var src = pilihSumber_(raw, c.from || c.name);
    switch (c.type) {
      case 'text': return asText(src);
      case 'int':  return asInt(src);
      case 'num':  return asNum(src);
      case 'date': return asDate(src);
      default:     return (src === null || src === undefined) ? '' : src; // 'any'
    }
  });
}

// ---------------------------------------------------------------------------
// UPSERT ke sheet tujuan (kunci: No. Waybill)
// ---------------------------------------------------------------------------
/** Versi satu file — tetap ada demi kompatibilitas; jalur sebenarnya = upsertBatches. */
function upsert(cfg, newRows) {
  return upsertBatches(cfg, [{ name: '(single)', rows: newRows, jumlah: newRows.length,
                               rentang: { awal: '', akhir: '' } }]);
}

/**
 * UPSERT banyak file sekaligus (satu kali baca + satu kali tulis).
 *
 * JAMINAN ANTI-DUPLIKAT (tiga lapis, No. Waybill = kunci tunggal):
 *   1. Sheet lama dibersihkan dulu. Kalau di sheet TERLANJUR ada waybill kembar
 *      (mis. sisa data lama / tempelan manual), yang tersisa satu — baris paling
 *      bawah (terbaru) yang dipertahankan.
 *   2. Waybill kembar DI DALAM satu file: kemunculan berikutnya menimpa, bukan menambah.
 *   3. Waybill kembar ANTAR file dalam satu submit: file berikutnya dihitung update.
 *      (Peta kunci dibagi bersama untuk semua file.)
 *   Baris tanpa No. Waybill tidak pernah ditulis — dilaporkan sebagai "dilewati".
 */
function upsertBatches(cfg, batches) {
  var lock = LockService.getScriptLock();
  lock.waitLock(60000);
  try {
    var ss = getSpreadsheet();
    var sh = ss.getSheetByName(cfg.sheetName) || ss.insertSheet(cfg.sheetName);
    var headers = cfg.columns.map(function (c) { return c.name; });
    var nCol = headers.length;

    if (sh.getLastRow() < 1 || String(sh.getRange(1, 1).getValue()).trim() === '') {
      sh.getRange(1, 1, 1, nCol).setValues([headers]);
      sh.setFrozenRows(1);
    }

    var lastRow = sh.getLastRow();
    var mentah = lastRow > 1 ? sh.getRange(2, 1, lastRow - 1, nCol).getValues() : [];
    var keyIdx = headers.indexOf(cfg.keyCol);

    // --- LAPIS 1: bersihkan duplikat & baris tanpa waybill yang SUDAH ada di sheet ---
    var existing = [], map = {};
    var dupLama = 0, kosongLama = 0;
    mentah.forEach(function (row) {
      var k = normKey(row[keyIdx]);
      if (k === '') { kosongLama++; return; }               // baris tanpa waybill -> buang
      if (map.hasOwnProperty(k)) {                          // kembar -> pertahankan yang terbaru
        existing[map[k]] = row; dupLama++;
      } else {
        existing.push(row); map[k] = existing.length - 1;
      }
    });

    // --- LAPIS 2 & 3: upsert isi file (peta kunci dipakai bersama lintas file) ---
    var totAdd = 0, totUpd = 0, totLewat = 0, perFile = [];
    batches.forEach(function (b) {
      var add = 0, upd = 0, lewat = 0, dupDalamFile = 0;
      var kunciFile = {};                                   // kunci yang sudah muncul di FILE INI
      b.rows.forEach(function (row) {
        var k = normKey(row[keyIdx]);
        if (k === '') { lewat++; return; }                  // tanpa waybill -> tidak pernah ditulis
        if (kunciFile[k]) dupDalamFile++;                   // kembar di dalam file yang sama
        kunciFile[k] = 1;

        if (map.hasOwnProperty(k)) { existing[map[k]] = row; upd++; }   // timpa, bukan tambah
        else { existing.push(row); map[k] = existing.length - 1; add++; }
      });
      totAdd += add; totUpd += upd; totLewat += lewat;
      perFile.push({ name: b.name, jumlah: b.jumlah, added: add, updated: upd,
                     dilewati: lewat, dupDalamFile: dupDalamFile,
                     awal: b.rentang.awal, akhir: b.rentang.akhir });
    });

    var sortIdx = headers.indexOf(cfg.sortCol);
    existing.sort(function (a, b) { return cmpVal(a[sortIdx], b[sortIdx]); });

    // tulis balik: kosongkan SELURUH baris lama dulu (jumlah baris bisa berkurang
    // setelah duplikat dibersihkan — kalau tidak dikosongkan, sisa baris akan tertinggal)
    if (lastRow > 1) sh.getRange(2, 1, lastRow - 1, nCol).clearContent();
    if (existing.length) sh.getRange(2, 1, existing.length, nCol).setValues(existing);

    applyFormats(sh, cfg, existing.length);

    return { added: totAdd, updated: totUpd, total: existing.length, perFile: perFile,
             dilewati: totLewat, dupLamaDibersihkan: dupLama, kosongLamaDibuang: kosongLama };
  } finally {
    lock.releaseLock();
  }
}

// ---------------------------------------------------------------------------
// DIAGNOSTIK DUPLIKAT — cek/bersihkan tanpa perlu upload
// ---------------------------------------------------------------------------
/** Laporan: adakah waybill kembar di kedua sheet? (tidak mengubah apa pun) */
function cekDuplikat() {
  var hasil = {};
  ['allResi', 'reconcile'].forEach(function (key) {
    var cfg = CONFIG[key];
    var sh = getSpreadsheet().getSheetByName(cfg.sheetName);
    var o = { sheet: cfg.sheetName, total: 0, unik: 0, duplikat: 0, tanpaWaybill: 0, contoh: [] };
    if (sh && sh.getLastRow() > 1) {
      var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
        .map(function (x) { return String(x).trim(); });
      var keyIdx = headers.indexOf(cfg.keyCol);
      var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
      var seen = {};
      data.forEach(function (r) {
        o.total++;
        var k = normKey(r[keyIdx]);
        if (k === '') { o.tanpaWaybill++; return; }
        if (seen[k]) { o.duplikat++; if (o.contoh.length < 10) o.contoh.push(k); }
        else { seen[k] = 1; o.unik++; }
      });
    }
    hasil[key] = o;
  });
  return hasil;
}

/** Bersihkan duplikat yang sudah terlanjur ada (jalankan dari editor bila perlu). */
function bersihkanDuplikat() {
  var out = [];
  ['allResi', 'reconcile'].forEach(function (key) {
    var r = upsertBatches(CONFIG[key], []);   // tanpa file -> hanya membersihkan sheet
    out.push(CONFIG[key].sheetName + ': ' + r.dupLamaDibersihkan + ' duplikat dibuang, ' +
             r.kosongLamaDibuang + ' baris tanpa waybill dibuang, sisa ' + r.total + ' baris.');
  });
  return out.join('\n');
}

// ---------------------------------------------------------------------------
// RIWAYAT UPLOAD — tiap file dicatat: rentang tanggal, jumlah resi, kapan diupload
// ---------------------------------------------------------------------------
var RIWAYAT_SHEET = 'Riwayat_Upload';
var RIWAYAT_HEADER = ['Waktu Upload', 'Dataset', 'Nama File', 'Rentang Awal', 'Rentang Akhir',
                      'Jumlah Resi', 'Baru', 'Diupdate', 'Diupload Oleh'];

function riwayatSheet_() {
  var ss = getSpreadsheet();
  var sh = ss.getSheetByName(RIWAYAT_SHEET);
  if (!sh) {
    sh = ss.insertSheet(RIWAYAT_SHEET);
    sh.getRange(1, 1, 1, RIWAYAT_HEADER.length).setValues([RIWAYAT_HEADER]);
    sh.setFrozenRows(1);
  }
  return sh;
}

function catatRiwayat_(datasetKey, cfg, perFile) {
  if (!perFile || !perFile.length) return;
  var sh = riwayatSheet_();
  var now = new Date();
  var email = '';
  try { email = Session.getActiveUser().getEmail() || ''; } catch (e) {}

  var rows = perFile.map(function (f) {
    return [now, cfg.sheetName, f.name, f.awal, f.akhir, f.jumlah, f.added, f.updated, email];
  });
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, RIWAYAT_HEADER.length).setValues(rows);
}

/** Riwayat upload untuk satu dataset (terbaru dulu). */
function getRiwayat(datasetKey) {
  var cfg = CONFIG[datasetKey];
  if (!cfg) return [];
  var sh = getSpreadsheet().getSheetByName(RIWAYAT_SHEET);
  if (!sh || sh.getLastRow() < 2) return [];

  var data = sh.getRange(2, 1, sh.getLastRow() - 1, RIWAYAT_HEADER.length).getValues();
  var out = [];
  data.forEach(function (r) {
    if (String(r[1]).trim() !== cfg.sheetName) return;
    out.push({
      waktu:  (r[0] instanceof Date)
                ? Utilities.formatDate(r[0], Session.getScriptTimeZone(), 'dd/MM/yyyy HH:mm')
                : String(r[0]),
      file:   String(r[2]),
      awal:   (r[3] instanceof Date) ? fmtDate(r[3]) : String(r[3] || ''),
      akhir:  (r[4] instanceof Date) ? fmtDate(r[4]) : String(r[4] || ''),
      jumlah: Number(r[5]) || 0,
      added:  Number(r[6]) || 0,
      updated:Number(r[7]) || 0,
      oleh:   String(r[8] || '')
    });
  });
  return out.reverse();
}

function applyFormats(sh, cfg, nRows) {
  if (!APPLY_NUMBER_FORMATS) return;   // dilewati saat pakai Table
  if (nRows < 1) return;
  cfg.columns.forEach(function (c, idx) {
    var fmt = c.forceText ? '@'
            : c.type === 'date' ? 'yyyy-mm-dd'
            : c.type === 'num'  ? '#,##0.00'
            : c.type === 'int'  ? '#,##0'
            : null;
    if (!fmt) return;
    // Kalau sheet berupa Table, tipe kolom dikunci -> setNumberFormat ditolak.
    // Abaikan error tersebut; Table sudah mengatur format sendiri.
    try {
      sh.getRange(2, idx + 1, nRows, 1).setNumberFormat(fmt);
    } catch (e) { /* typed column (Table) — lewati */ }
  });
}

// ---------------------------------------------------------------------------
// HELPER KONVERSI TIPE
// ---------------------------------------------------------------------------
function asText(v) {
  if (v === null || v === undefined) return '';
  if (v instanceof Date) return fmtDate(v);
  return String(v).trim();
}

function asInt(v) {
  if (v === null || v === undefined || v === '') return '';
  var n = parseFloat(String(v).replace(/,/g, '').trim());
  return isNaN(n) ? '' : Math.round(n);
}

function asNum(v) {
  if (v === null || v === undefined || v === '') return '';
  var n = parseFloat(String(v).replace(/,/g, '').trim());
  return isNaN(n) ? '' : n;
}

function asDate(v) {
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) return new Date(v.getFullYear(), v.getMonth(), v.getDate());
  var s = String(v).trim();
  if (!s) return '';
  var m = s.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);      // 2026-07-03 [ 16:57:40 ]
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  var d = new Date(s);
  return isNaN(d.getTime()) ? s : new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function fmtDate(d) {
  return Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

/** kunci pencocokan: buang spasi, samakan sebagai teks digit murni. */
function normKey(v) {
  if (v === null || v === undefined) return '';
  var s = (v instanceof Date) ? fmtDate(v) : String(v);
  return s.replace(/\s+/g, '').replace(/\.0$/, '');
}

/** comparator sort: Date & angka naik; kosong ditaruh paling bawah. */
function cmpVal(a, b) {
  var ea = (a === '' || a === null || a === undefined);
  var eb = (b === '' || b === null || b === undefined);
  if (ea && eb) return 0;
  if (ea) return 1;
  if (eb) return -1;
  if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime();
  return a < b ? -1 : (a > b ? 1 : 0);
}
