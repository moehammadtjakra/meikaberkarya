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
// DASHBOARD ORDERONLINE — leads, closing (paid), closing rate, produk terbaik
// ===========================================================================
var ORDER_MIN_LEADS = 10;    // ambang minimal leads agar closing rate produk bermakna

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

  var akun = {}, prod = {}, bulan = {};
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

    var p = String(r['product'] || '').trim() || '(tanpa nama produk)';
    if (!prod[p]) prod[p] = { product: p, leads: 0, closing: 0 };
    prod[p].leads++; if (paid) prod[p].closing++;

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
