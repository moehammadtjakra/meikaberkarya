/**
 * ============================================================================
 *  J&T DATA LOADER — MODUL ORDERONLINE   (Meika Berkarya)
 *
 *  Upload export order dari platform OrderOnline -> disimpan ke SHEET TERPISAH
 *  "OrderOnline", dipisah per AKUN (A1/A2/A3, dipilih saat upload).
 *
 *  DEFINISI (dikonfirmasi user):
 *    LEADS   = tiap baris (1 submission form = 1 lead)
 *    CLOSING = baris dengan payment_status == "paid"
 *    CLOSING RATE = closing / leads
 *
 *  UPSERT: kunci = Akun + order_id (order_id bisa saja sama antar akun, jadi
 *  akun ikut jadi bagian kunci). Upload ulang rentang yang sama -> baris lama
 *  ditimpa, tidak menduplikasi.
 * ============================================================================
 */

// Akun OrderOnline. Ganti nama di sini kalau perlu (mis. 'A1 — Indra').
var AKUN_ORDERONLINE = ['A1', 'A2', 'A3'];

var ORDER_CFG = {
  sheetName: 'OrderOnline',
  keyCols: ['Akun', 'order_id'],           // kunci gabungan
  // kolom yang WAJIB ada di file export supaya validasi slot lolos
  requireCols: ['order_id', 'status', 'product'],
  // kolom yang disimpan (subset berguna dari 53 kolom export). 'Akun' diinjeksi.
  columns: [
    'Akun', 'order_id', 'created_at', 'name', 'phone', 'province', 'city',
    'product', 'product_code', 'variation', 'quantity', 'status',
    'payment_status', 'payment_method', 'product_price', 'net_revenue',
    'handled_by', 'courier', 'receipt_number', 'utm_source', 'utm_campaign'
  ],
  numCols: ['quantity', 'product_price', 'net_revenue']
};

function getAkunOrderOnline() { return AKUN_ORDERONLINE.slice(); }

/** Satu file. */
function processOrderUpload(b64, filename, akun) {
  return processOrderUploadFiles([{ b64: b64, name: filename }], akun);
}

/**
 * MULTI-FILE: proses beberapa file OrderOnline dalam satu submit, untuk satu akun.
 * Semua dibaca dulu lalu ditulis SEKALI (upsert), jadi cepat & tanpa duplikat.
 */
function processOrderUploadFiles(files, akun) {
  akun = String(akun || '').trim();
  if (AKUN_ORDERONLINE.indexOf(akun) < 0)
    throw new Error('Akun tidak dikenal: "' + akun + '". Pilih salah satu: ' + AKUN_ORDERONLINE.join(', '));
  if (!files || !files.length) throw new Error('Belum ada file yang dipilih.');

  var batches = [], gagal = [], diproses = 0;
  files.forEach(function (f) {
    try {
      var rows = readUploadedSheet(f.b64, f.name);      // reuse pembaca file Data Loader
      if (!rows.length) throw new Error('file kosong / tidak ada baris data');

      var headerKeys = Object.keys(rows[0]);
      var missing = ORDER_CFG.requireCols.filter(function (c) { return headerKeys.indexOf(c) < 0; });
      if (missing.length)
        throw new Error('sepertinya bukan export OrderOnline — kolom wajib tidak ada: ' + missing.join(', '));

      var out = rows.map(function (src) { return bangunBarisOrder_(src, akun); })
                    .filter(function (r) { return r; });    // baris tanpa order_id dibuang
      batches.push({ name: f.name, rows: out, jumlah: rows.length });
      diproses += rows.length;
    } catch (e) {
      gagal.push({ name: f.name, pesan: (e && e.message) ? e.message : String(e) });
    }
  });

  if (!batches.length)
    throw new Error('Tidak ada file yang bisa diproses. ' +
      gagal.map(function (g) { return g.name + ': ' + g.pesan; }).join(' | '));

  var res = upsertOrder_(batches);
  try { dashCacheClear_(); } catch (e) {}
  try { CacheService.getScriptCache().remove('dashOrder'); } catch (e) {}

  return {
    sheetName: ORDER_CFG.sheetName, akun: akun,
    jumlahFile: batches.length, processed: diproses,
    added: res.added, updated: res.updated, total: res.total,
    perFile: res.perFile, dilewati: res.dilewati, gagal: gagal
  };
}

/** Satu baris export -> array selaras ORDER_CFG.columns (atau null bila tanpa order_id). */
function bangunBarisOrder_(src, akun) {
  var oid = String(src['order_id'] == null ? '' : src['order_id']).trim();
  if (!oid) return null;
  return ORDER_CFG.columns.map(function (c) {
    if (c === 'Akun') return akun;
    var v = src[c];
    if (ORDER_CFG.numCols.indexOf(c) >= 0) return ang_(v);
    if (v === null || v === undefined) return '';
    return (v instanceof Date) ? v : String(v).trim();
  });
}

function kunciOrder_(akun, oid) {
  return normKey(akun) + '||' + normKey(oid);
}

/** UPSERT ke sheet OrderOnline (kunci gabungan Akun+order_id). */
function upsertOrder_(batches) {
  var lock = LockService.getScriptLock();
  lock.waitLock(60000);
  try {
    var ss = getSpreadsheet();
    var sh = ss.getSheetByName(ORDER_CFG.sheetName) || ss.insertSheet(ORDER_CFG.sheetName);
    var headers = ORDER_CFG.columns;
    var nCol = headers.length;

    if (sh.getLastRow() < 1 || String(sh.getRange(1, 1).getValue()).trim() === '') {
      sh.getRange(1, 1, 1, nCol).setValues([headers]);
      sh.setFrozenRows(1);
    }

    var iAkun = headers.indexOf('Akun'), iOid = headers.indexOf('order_id');
    var lastRow = sh.getLastRow();
    var mentah = lastRow > 1 ? sh.getRange(2, 1, lastRow - 1, nCol).getValues() : [];

    var existing = [], map = {};
    mentah.forEach(function (row) {
      var k = kunciOrder_(row[iAkun], row[iOid]);
      if (k === '||') return;
      if (map.hasOwnProperty(k)) { existing[map[k]] = row; }        // kembar lama -> pertahankan terbaru
      else { existing.push(row); map[k] = existing.length - 1; }
    });

    var totAdd = 0, totUpd = 0, totLewat = 0, perFile = [];
    batches.forEach(function (b) {
      var add = 0, upd = 0, lewat = 0;
      b.rows.forEach(function (row) {
        var k = kunciOrder_(row[iAkun], row[iOid]);
        if (k === '||') { lewat++; return; }
        if (map.hasOwnProperty(k)) { existing[map[k]] = row; upd++; }
        else { existing.push(row); map[k] = existing.length - 1; add++; }
      });
      totAdd += add; totUpd += upd; totLewat += lewat;
      perFile.push({ name: b.name, jumlah: b.jumlah, added: add, updated: upd, dilewati: lewat });
    });

    // urut terbaru dulu berdasarkan created_at (string dd-mm-yyyy - HH:MM)
    var iCreated = headers.indexOf('created_at');
    existing.sort(function (a, b) {
      var ta = tglOrder_(a[iCreated]), tb = tglOrder_(b[iCreated]);
      return (tb ? tb.getTime() : 0) - (ta ? ta.getTime() : 0);
    });

    if (lastRow > 1) sh.getRange(2, 1, lastRow - 1, nCol).clearContent();
    if (existing.length) sh.getRange(2, 1, existing.length, nCol).setValues(existing);

    return { added: totAdd, updated: totUpd, total: existing.length, perFile: perFile, dilewati: totLewat };
  } finally {
    lock.releaseLock();
  }
}

// ===========================================================================
// AUTO-TARIK dari API OrderOnline (token sesi ditempel per akun)
//
// Login penuh TIDAK bisa diotomatiskan (butuh reCAPTCHA). Tapi endpoint export
// cukup pakai Bearer JWT -> user tempel token per akun (berlaku ~7 hari),
// pilih rentang tanggal, klik Tarik -> data langsung masuk sheet OrderOnline.
// ===========================================================================
var ORDER_API = {
  exportUrl: 'https://reconcile.orderonline.id/submission/export',
  origin:  'https://app.orderonline.id',
  referer: 'https://app.orderonline.id/',
  ua: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
};
var ORDER_TOKEN_PROP = 'oo_token_';   // + akun (mis. oo_token_A1)

function potongOO_(s, n) {
  s = String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  return s.length > n ? s.slice(0, n) + '…' : (s || '(kosong)');
}

/** Ambil klaim exp (epoch detik) dari JWT, atau null. */
function jwtExp_(token) {
  try {
    var p = String(token).split('.')[1];
    p = p.replace(/-/g, '+').replace(/_/g, '/');
    while (p.length % 4) p += '=';
    var obj = JSON.parse(Utilities.newBlob(Utilities.base64Decode(p)).getDataAsString());
    return obj.exp || null;
  } catch (e) { return null; }
}

function bersihToken_(s) {
  return String(s || '').trim().replace(/^authorization\s*:\s*/i, '').replace(/^bearer\s+/i, '').replace(/^['"]|['"]$/g, '').trim();
}

/** Panel token: simpan token satu akun. */
function simpanTokenOrder(akun, token) {
  akun = String(akun || '').trim();
  if (AKUN_ORDERONLINE.indexOf(akun) < 0) throw new Error('Akun tidak dikenal: ' + akun);
  token = bersihToken_(token);
  if (!token) throw new Error('Token kosong.');
  if (token.split('.').length !== 3) throw new Error('Token bukan JWT (harus ada 2 titik). Salin nilai setelah "Bearer ".');
  PropertiesService.getScriptProperties().setProperty(ORDER_TOKEN_PROP + akun, JSON.stringify({
    token: token, disimpan: new Date().toISOString(), oleh: (Session.getActiveUser().getEmail() || '')
  }));
  return statusTokenOrder();
}
function hapusTokenOrder(akun) {
  PropertiesService.getScriptProperties().deleteProperty(ORDER_TOKEN_PROP + String(akun || '').trim());
  return statusTokenOrder();
}
function bacaTokenOrder_(akun) {
  var s = PropertiesService.getScriptProperties().getProperty(ORDER_TOKEN_PROP + akun);
  if (!s) return null;
  try { return JSON.parse(s); } catch (e) { return null; }
}

/** Status semua akun (untuk UI) — token disamarkan, plus info kedaluwarsa. */
function statusTokenOrder() {
  var tz = Session.getScriptTimeZone() || 'Asia/Jakarta';
  return AKUN_ORDERONLINE.map(function (a) {
    var o = bacaTokenOrder_(a);
    if (!o || !o.token) return { akun: a, ada: false };
    var exp = jwtExp_(o.token);
    var kedaluwarsa = exp ? (exp * 1000 < Date.now()) : false;
    return {
      akun: a, ada: true, ekor: '…' + o.token.slice(-8),
      exp: exp ? Utilities.formatDate(new Date(exp * 1000), tz, 'dd/MM/yyyy HH:mm') : '',
      kedaluwarsa: kedaluwarsa,
      sisaJam: exp ? Math.round((exp * 1000 - Date.now()) / 36e5) : null,
      oleh: o.oleh || ''
    };
  });
}

/**
 * Panggil endpoint export untuk satu akun & rentang tanggal.
 * @return {Object} { rows:[...objek...], via:'xlsx'|'json' }  atau  { _error, ... }
 */
function ambilExportOrder_(token, since, until) {
  var url = ORDER_API.exportUrl +
    '?limit=1000000&sort_by=created_at&sort=desc&page=1' +
    '&since=' + encodeURIComponent(since) + '&until=' + encodeURIComponent(until) +
    '&timestamp=' + Date.now() + '&use_cache_header=false&file_type=excel';

  var resp = UrlFetchApp.fetch(url, {
    method: 'get', muteHttpExceptions: true, followRedirects: true,
    headers: {
      'authorization': 'Bearer ' + token,
      'accept': 'application/json, text/plain, */*',
      'origin': ORDER_API.origin, 'referer': ORDER_API.referer,
      'user-agent': ORDER_API.ua
    }
  });

  var code = resp.getResponseCode();
  if (code === 401 || code === 403)
    return { _error: 'HTTP ' + code + ' — token ditolak/kedaluwarsa. Tempel ulang token akun ini.' };
  if (code !== 200) return { _error: 'HTTP ' + code + ' — ' + potongOO_(resp.getContentText(), 220) };

  var bytes = resp.getContent();
  var headers = resp.getAllHeaders();
  var ct = String(headers['Content-Type'] || headers['content-type'] || '');

  // xlsx = arsip ZIP, diawali "PK" (0x50 0x4B)
  var isZip = bytes.length > 1 && (bytes[0] & 0xff) === 0x50 && (bytes[1] & 0xff) === 0x4B;
  if (isZip || /spreadsheet|excel|officedocument|octet-stream/i.test(ct)) {
    var rows = readUploadedSheet(Utilities.base64Encode(bytes), 'oo_export.xlsx');
    return { rows: rows, via: 'xlsx' };
  }

  // Bukan xlsx -> JSON. Endpoint OrderOnline mengembalikan:
  //   { "data": "https://…s3…/exports/….xlsx", "message":"", "error_code":0, ... }
  // yaitu URL file di S3 yang harus DIUNDUH lagi.
  var teks = resp.getContentText().replace(/^﻿/, '').trim();   // buang BOM (bikin JSON.parse gagal)
  var j;
  try { j = JSON.parse(teks); }
  catch (e) { return { _error: 'Balasan bukan xlsx maupun JSON (Content-Type: ' + ct + '): ' + potongOO_(teks, 300) }; }

  if (j && j.error_code && Number(j.error_code) !== 0)
    return { _error: 'OrderOnline menolak: ' + (j.message || ('error_code ' + j.error_code)) };

  // data berupa array order langsung?
  var arr = Array.isArray(j) ? j
    : (j && Array.isArray(j.data) ? j.data
    : (j && j.data && Array.isArray(j.data.data) ? j.data.data
    : (j && Array.isArray(j.rows) ? j.rows : null)));
  if (arr) return { rows: arr, via: 'json' };

  // data berupa URL file (kasus nyata OrderOnline)
  var link = '';
  if (j) {
    if (typeof j.data === 'string' && /^https?:\/\//i.test(j.data)) link = j.data;
    else link = j.url || (j.data && (j.data.url || j.data.link)) || '';
  }
  if (link) {
    var r2 = UrlFetchApp.fetch(link, { method: 'get', muteHttpExceptions: true, followRedirects: true });
    if (r2.getResponseCode() !== 200)
      return { _error: 'Gagal mengunduh file export dari S3 (HTTP ' + r2.getResponseCode() + ').' };
    return { rows: readUploadedSheet(Utilities.base64Encode(r2.getContent()), 'oo_export.xlsx'), via: 'xlsx-url' };
  }
  return { _error: 'Balasan JSON tak dikenal strukturnya: ' + potongOO_(teks, 300) };
}

/** Tarik & simpan ke sheet OrderOnline untuk satu akun. */
function tarikOrderOnline(akun, since, until) {
  akun = String(akun || '').trim();
  if (AKUN_ORDERONLINE.indexOf(akun) < 0) throw new Error('Akun tidak dikenal: ' + akun);
  since = String(since || '').trim(); until = String(until || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(since) || !/^\d{4}-\d{2}-\d{2}$/.test(until))
    throw new Error('Rentang tanggal wajib diisi (format yyyy-mm-dd).');

  var o = bacaTokenOrder_(akun);
  if (!o || !o.token) throw new Error('Token akun ' + akun + ' belum ada. Tempel token dulu.');
  var exp = jwtExp_(o.token);
  if (exp && exp * 1000 < Date.now()) throw new Error('Token akun ' + akun + ' sudah kedaluwarsa. Tempel token baru.');

  var res = ambilExportOrder_(o.token, since, until);
  if (res._error) throw new Error(res._error);

  var out = res.rows.map(function (src) { return bangunBarisOrder_(src, akun); })
                    .filter(function (r) { return r; });
  if (!out.length) throw new Error('Tidak ada order pada rentang ' + since + ' → ' + until +
    ' untuk akun ' + akun + '. (Balasan terbaca via ' + res.via + ', ' + res.rows.length + ' baris mentah.)');

  var r = upsertOrder_([{ name: 'API ' + since + '..' + until, rows: out, jumlah: res.rows.length }]);
  try { dashCacheClear_(); } catch (e) {}
  try { CacheService.getScriptCache().remove('dashOrder'); } catch (e) {}

  return { akun: akun, since: since, until: until, via: res.via,
           ditarik: res.rows.length, disimpan: out.length,
           added: r.added, updated: r.updated, total: r.total };
}

/**
 * DIAGNOSTIK — lihat balasan MENTAH endpoint export (tanpa menyimpan apa pun).
 * Jalankan ini dulu kalau tarik gagal, lalu kirim hasilnya supaya parsing
 * bisa disesuaikan. Bisa dipanggil dari editor atau dari tombol di UI.
 */
function tesTarikOrderMentah(akun, since, until) {
  akun = String(akun || AKUN_ORDERONLINE[0]).trim();
  var o = bacaTokenOrder_(akun);
  if (!o || !o.token) return 'Token akun ' + akun + ' belum ada.';
  since = since || Utilities.formatDate(new Date(Date.now() - 7 * 864e5), Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd');
  until = until || Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd');

  var url = ORDER_API.exportUrl + '?limit=1000000&sort_by=created_at&sort=desc&page=1' +
    '&since=' + encodeURIComponent(since) + '&until=' + encodeURIComponent(until) +
    '&timestamp=' + Date.now() + '&use_cache_header=false&file_type=excel';
  var resp = UrlFetchApp.fetch(url, {
    method: 'get', muteHttpExceptions: true, followRedirects: true,
    headers: { 'authorization': 'Bearer ' + o.token, 'accept': 'application/json, text/plain, */*',
               'origin': ORDER_API.origin, 'referer': ORDER_API.referer, 'user-agent': ORDER_API.ua }
  });
  var bytes = resp.getContent();
  var headers = resp.getAllHeaders();
  var ct = String(headers['Content-Type'] || headers['content-type'] || '');
  var isZip = bytes.length > 1 && (bytes[0] & 0xff) === 0x50 && (bytes[1] & 0xff) === 0x4B;
  var out = 'Akun         : ' + akun + '\n' +
            'Rentang      : ' + since + ' → ' + until + '\n' +
            'HTTP         : ' + resp.getResponseCode() + '\n' +
            'Content-Type : ' + ct + '\n' +
            'Ukuran       : ' + bytes.length + ' byte\n' +
            'Terdeteksi   : ' + (isZip ? 'FILE XLSX (ZIP) ✔' : 'bukan xlsx') + '\n';
  if (isZip) {
    try {
      var rows = readUploadedSheet(Utilities.base64Encode(bytes), 'oo_export.xlsx');
      out += 'Baris terbaca: ' + rows.length + '\n' +
             'Kolom        : ' + (rows.length ? Object.keys(rows[0]).slice(0, 12).join(', ') + '…' : '(kosong)');
    } catch (e) { out += 'Gagal baca xlsx: ' + e.message; }
  } else {
    out += '--- CUPLIKAN BALASAN ---\n' + potongOO_(resp.getContentText(), 1200);
  }
  Logger.log(out);
  return out;
}

// ===========================================================================
// DASHBOARD ORDERONLINE — leads, closing (paid), closing rate, produk terbaik
// ===========================================================================
var ORDER_MIN_LEADS = 10;    // ambang minimal leads agar closing rate produk bermakna

// Sheet acuan penamaan produk (di spreadsheet yang sama). Nama sheet dicoba
// berurutan — pakai yang pertama ditemukan (typo "Impor" vs "Import" ditoleransi).
var ORDER_REF = {
  ref:   ['Impor-RefProduk', 'Import-RefProduk', 'Ref Produk', 'RefProduk', 'Ref_Produk'],
  stok:  ['Import-Stock', 'Impor-Stock', 'Stok', 'Stock']
};

/**
 * Peta product_code (huruf besar) -> NAMA PRODUK KANONIK.
 * Sumber utama: Impor-RefProduk (product_code -> "Nama Barang JNT").
 * Cadangan   : Import-Stock (SKU -> "Nama Produk").
 * Dipakai supaya "produk terbaik" tampil bersih & seragam, bukan teks promo
 * OrderOnline yang beragam ("((Gelang Retro…))", "…Beli 1 Gratis 1").
 */
function petaProdukKanonik_() {
  var ss = getSpreadsheet();
  var map = {};
  var pilih = function (names) {
    for (var i = 0; i < names.length; i++) { var sh = ss.getSheetByName(names[i]); if (sh) return sh; }
    return null;
  };
  var serap = function (sh, kolKode, kolNamaKandidat) {
    if (!sh || sh.getLastRow() < 2) return;
    var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var ik = h.indexOf(kolKode);
    var inx = -1;
    kolNamaKandidat.forEach(function (nm) { if (inx < 0) inx = h.indexOf(nm); });
    if (ik < 0 || inx < 0) return;
    sh.getRange(2, 1, sh.getLastRow() - 1, h.length).getValues().forEach(function (r) {
      var c = String(r[ik] == null ? '' : r[ik]).trim().toUpperCase();
      var n = String(r[inx] == null ? '' : r[inx]).trim();
      if (c && n && !map[c]) map[c] = n;      // sumber pertama menang
    });
  };
  serap(pilih(ORDER_REF.ref),  'product_code', ['Nama Barang JNT', 'Nama Produk']);
  serap(pilih(ORDER_REF.stok), 'SKU',          ['Nama Produk', 'Nama Barang JNT']);
  return map;
}

/** Bersihkan teks produk OrderOnline (buang kurung & spasi berlebih) — cadangan bila kode tak ada di ref. */
function bersihProduk_(s) {
  var x = String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  x = x.replace(/^[\(\[\{\s]+/, '').replace(/[\)\]\}\s]+$/, '').trim();
  return x;
}

/**
 * @param {Object} f  { since:'yyyy-mm-dd', until:'yyyy-mm-dd', akun:'A1'|'' }  (opsional)
 */
function getDashOrder(f) {
  f = f || {};
  var t = bacaSheet_(ORDER_CFG.sheetName);
  var out = {
    ada: t.rows.length > 0,
    leads: 0, closing: 0, rate: 0,
    perAkun: [], produkTerbaik: [], produkSemua: [], perBulan: [],
    akunList: AKUN_ORDERONLINE.slice(), minLeads: ORDER_MIN_LEADS,
    periode: { since: String(f.since || ''), until: String(f.until || '') }
  };
  if (!out.ada) return out;

  var fAkun = String(f.akun || '').trim();
  var since = f.since ? tglOrder_(f.since + ' ') : null;
  var until = f.until ? tglOrder_(f.until + ' ') : null;
  if (until) until = new Date(until.getFullYear(), until.getMonth(), until.getDate(), 23, 59, 59);

  var peta = petaProdukKanonik_();          // product_code -> nama kanonik
  var akun = {}, prod = {}, bulan = {}, tanpaRef = {};
  AKUN_ORDERONLINE.forEach(function (a) { akun[a] = { akun: a, leads: 0, closing: 0 }; });

  t.rows.forEach(function (r) {
    var a = String(r['Akun'] || '').trim();
    if (fAkun && a !== fAkun) return;
    var tgl = tglOrder_(r['created_at']);
    if (since && (!tgl || tgl < since)) return;
    if (until && (!tgl || tgl > until)) return;

    var paid = String(r['payment_status'] || '').trim().toLowerCase() === 'paid';
    out.leads++; if (paid) out.closing++;

    if (akun[a]) { akun[a].leads++; if (paid) akun[a].closing++; }

    // NAMA PRODUK KANONIK dari product_code; kalau kode tak ada di ref, pakai
    // teks produk yang dibersihkan; grouping tetap per-kode supaya varian promo
    // dari produk sama menyatu.
    var code = String(r['product_code'] == null ? '' : r['product_code']).trim().toUpperCase();
    var kanonik = (code && peta[code]) ? peta[code]
                : (bersihProduk_(r['product']) || code || '(tanpa nama produk)');
    var gk = code ? ('C:' + code) : ('N:' + kanonik.toLowerCase());
    if (code && !peta[code]) tanpaRef[code] = kanonik;       // kode belum ada di Ref Produk
    if (!prod[gk]) prod[gk] = { product: kanonik, kode: code, leads: 0, closing: 0 };
    prod[gk].leads++; if (paid) prod[gk].closing++;

    if (tgl) {
      var bk = tgl.getFullYear() + '-' + ('0' + (tgl.getMonth() + 1)).slice(-2);
      if (!bulan[bk]) bulan[bk] = { bulan: bk, leads: 0, closing: 0 };
      bulan[bk].leads++; if (paid) bulan[bk].closing++;
    }
  });

  out.rate = pct_(out.closing, out.leads);
  out.perAkun = AKUN_ORDERONLINE.map(function (a) {
    var o = akun[a]; o.rate = pct_(o.closing, o.leads); return o;
  });

  var semua = Object.keys(prod).map(function (k) {
    var o = prod[k]; o.rate = pct_(o.closing, o.leads); return o;
  });
  // produk terbaik: hanya yang leads >= ambang (biar 1 lead 1 closing = 100% tidak menipu),
  // diurut closing rate tertinggi, lalu leads terbanyak.
  out.produkTerbaik = semua.filter(function (o) { return o.leads >= ORDER_MIN_LEADS; })
    .sort(function (a, b) { return (b.rate - a.rate) || (b.leads - a.leads); });
  out.produkSemua = semua.sort(function (a, b) { return b.leads - a.leads; });

  out.perBulan = Object.keys(bulan).sort().map(function (k) {
    var o = bulan[k]; o.rate = pct_(o.closing, o.leads); return o;
  });

  // kode produk yang belum ada padanannya di Ref Produk (biar bisa ditambahkan)
  out.kodeTanpaRef = Object.keys(tanpaRef).map(function (c) { return c + ' — ' + tanpaRef[c]; });
  out.refAda = Object.keys(peta).length;
  return out;
}

/**
 * Parse created_at OrderOnline: "21-08-2026 - 13:52" (dd-mm-yyyy - HH:MM).
 * Juga menerima yyyy-mm-dd bila suatu saat formatnya berubah.
 */
function tglOrder_(v) {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  var s = String(v).trim();
  var m = s.match(/(\d{1,2})-(\d{1,2})-(\d{4})(?:\s*-\s*(\d{1,2}):(\d{2}))?/);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0));
  var m2 = s.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m2) return new Date(+m2[1], +m2[2] - 1, +m2[3]);
  var d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}
