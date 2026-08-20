/**
 * ============================================================================
 *  TRACKING & RETUR — Sistem Admin Order (Meika Berkarya) [v2]
 *  Pencocokan lewat "#<KodeAkun>-<order_id>" di Nama Barang.
 *  CSV hasil dipisah PER AKUN OrderOnline (karena diupload ke akun masing2).
 * ============================================================================
 */

/**
 * Ambil kunci "<AKUN>-<order_id>" dari Nama Barang hasil export J&T.
 *
 * PENTING: J&T MENGUBAH karakter pemisah. Contoh nyata —
 *   dikirim : "Sikat Punggung #A1-276273726"
 *   kembali : "Sikat Punggung ,A1-276273726"     ('#' menjadi ',')
 * Karena itu parser ini TIDAK bergantung pada karakter pemisah apa pun.
 * Ia hanya mencari pola <KODE>-<ANGKA> di ujung teks, lalu memverifikasi
 * bahwa <KODE> memang salah satu kode akun yang terdaftar.
 */
function ekstrakKunci_(namaBarang, akunSet) {
  var s = t_(namaBarang);
  if (!s) return null;

  // pola utama: ... <AKUN>-<order_id>  (pemisah sebelum AKUN boleh apa saja)
  var m = s.match(/([A-Za-z0-9]{1,12})\s*[-‐-―]\s*(\d{4,})\s*$/);
  if (m) {
    var akun = m[1].toUpperCase();
    if (akunSet[akun]) return { akun: akun, order: m[2], via: 'akun+order' };
    // kode di depan bukan kode akun -> tetap coba pakai order_id-nya saja
    return { akun: '', order: m[2], via: 'order' };
  }
  // cadangan: hanya angka panjang di ujung
  var m2 = s.match(/(\d{6,})\s*$/);
  if (m2) return { akun: '', order: m2[1], via: 'order' };
  return null;
}

/**
 * TAHAP 1 — PROSES (pratinjau saja, TIDAK menulis apa pun).
 * Membaca file Url-Tracking, mencocokkan ke order, lalu mengembalikan
 * gambaran hasil transform agar admin bisa memeriksa/mengoreksi dulu.
 */
function prosesTracking(b64, filename) {
  me_();
  var rows = readSheet_(b64, filename, 0);
  if (!rows.length) throw new Error('File kosong.');

  var kAwb  = pick_(rows[0], ['No. Waybill', 'No Waybill', 'Waybill']);
  var kUrl  = pick_(rows[0], ['Ekspor URL Tracking', 'URL Tracking', 'Url Tracking']);
  var kNama = pick_(rows[0], ['Nama Barang']);
  var kPen  = pick_(rows[0], ['Penerima']);
  var kKec  = pick_(rows[0], ['Kecamatan Penerima', 'Kecamatan']);
  if (!kAwb || !kUrl) throw new Error('Kolom "No. Waybill" atau "Ekspor URL Tracking" tidak ditemukan.');

  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var akunSet = {};
  Object.keys(akunMap_()).forEach(function (k) { akunSet[k.toUpperCase()] = 1; });

  var byKey = {}, byOrder = {}, orderDup = {}, byComp = {}, compDup = {};
  t.rows.forEach(function (r, i) {
    var akun = t_(r['Akun OO']), oid = t_(r['order_id']);
    byKey[akun + '|' + oid] = i;
    if (byOrder.hasOwnProperty(oid)) orderDup[oid] = 1; else byOrder[oid] = i;
    var s = t_(r['Status Order']);
    if (s === CFG.ST.diBatch || s === CFG.ST.dapatAWB) {
      var c = compKey_(r['Nama Penerima'], r['Kecamatan JNT'], r['Nama Barang JNT']);
      if (byComp.hasOwnProperty(c)) compDup[c] = 1; else byComp[c] = i;
    }
  });

  var out = [], cocok = 0;
  rows.forEach(function (r) {
    var awb = t_(r[kAwb]), url = t_(r[kUrl]);
    if (!awb && !url) return;
    var namaBarang = kNama ? t_(r[kNama]) : '';
    var idx = -1, via = '';

    var k = ekstrakKunci_(namaBarang, akunSet);
    if (k) {
      if (k.akun && byKey.hasOwnProperty(k.akun + '|' + k.order)) { idx = byKey[k.akun + '|' + k.order]; via = 'kode di nama barang'; }
      if (idx < 0 && byOrder.hasOwnProperty(k.order) && !orderDup[k.order]) { idx = byOrder[k.order]; via = 'order_id'; }
    }
    if (idx < 0 && kPen && kKec) {
      var bersih = namaBarang.replace(/[^A-Za-z0-9]*[A-Za-z0-9]{1,12}\s*[-‐-―]\s*\d{4,}\s*$/, '').trim();
      var c = compKey_(r[kPen], r[kKec], bersih);
      if (byComp.hasOwnProperty(c) && !compDup[c]) { idx = byComp[c]; via = 'nama+kecamatan (cadangan)'; }
    }

    var o = { awb: awb, url: url, namaBarang: namaBarang,
              penerima: kPen ? t_(r[kPen]) : '', akun: '', order_id: '', nama: '',
              cocok: false, via: via, catatan: '' };
    if (idx >= 0) {
      var row = t.rows[idx];
      o.akun = t_(row['Akun OO']);
      o.order_id = t_(row['order_id']);
      o.nama = t_(row['Nama Penerima']);
      o.cocok = true;
      cocok++;
      var st = t_(row['Status Order']);
      if (st === CFG.ST.trackingOK) o.catatan = 'sudah pernah dikirim ke OrderOnline';
    } else {
      o.catatan = 'tidak cocok — isi order_id manual bila perlu';
      if (k) o.order_id = k.order;      // tetap tawarkan hasil parsing
    }
    out.push(o);
  });

  return { ok: true, dibaca: out.length, cocok: cocok, gagal: out.length - cocok, rows: out };
}

/**
 * TAHAP 2 — SIMPAN & EXPORT.
 * Menulis AWB + URL ke ORDERS, lalu membuat CSV per akun untuk OrderOnline
 * dan mencatatnya di riwayat export.
 */
function simpanTrackingExport(rows) {
  var me = me_();
  if (!rows || !rows.length) throw new Error('Tidak ada baris untuk disimpan.');

  var lock = LockService.getScriptLock(); lock.waitLock(120000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.orders);
    var t = readTable_(sh);
    var byKey = {}, byOrder = {};
    t.rows.forEach(function (r, i) {
      byKey[t_(r['Akun OO']) + '|' + t_(r['order_id'])] = i;
      byOrder[t_(r['order_id'])] = i;
    });

    var grup = {}, simpan = 0, lewat = 0;
    rows.forEach(function (r) {
      var oid = t_(r.order_id), url = t_(r.url), awb = t_(r.awb), akun = t_(r.akun);
      if (!oid || !url) { lewat++; return; }
      var idx = byKey.hasOwnProperty(akun + '|' + oid) ? byKey[akun + '|' + oid]
              : (byOrder.hasOwnProperty(oid) ? byOrder[oid] : -1);
      if (idx < 0) { lewat++; return; }

      var row = t.rows[idx];
      if (awb) row['No. Waybill'] = awb;
      row['URL Tracking'] = url;
      row['Waktu AWB'] = new Date();
      row['Status Order'] = CFG.ST.trackingOK;

      var ak = t_(row['Akun OO']) || akun || 'NA';
      if (!grup[ak]) grup[ak] = [];
      grup[ak].push([oid, url, 'paid']);
      simpan++;
    });
    if (!simpan) throw new Error('Tidak ada baris valid (butuh order_id & URL tracking).');

    writeTable_(sh, t);

    var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd_HHmm');
    var files = Object.keys(grup).map(function (akun) {
      var f = makeCsv_(['order_id', 'receipt_number', 'payment_status'], grup[akun],
        'OO_' + akun + '_paid_' + stamp + '.csv');
      f.akun = akun; f.jumlah = grup[akun].length;
      return f;
    });
    catatExport_('paid', files, me.nama);

    log_('Export Tracking', simpan + ' order, ' + files.length + ' file');
    return { ok: true, jumlah: simpan, dilewati: lewat, files: files };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// RIWAYAT EXPORT
// ---------------------------------------------------------------------------
function catatExport_(jenis, files, oleh) {
  try {
    var sh = getSS().getSheetByName(CFG.sh.ekspor);
    if (!sh) return;
    var now = new Date();
    var rows = files.map(function (f) {
      return [now, jenis, f.akun || '', f.jumlah || 0, f.name, f.id, oleh || ''];
    });
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, 7).setValues(rows);
  } catch (e) {}
}

function getExportHistory() {
  me_();
  var sh = getSS().getSheetByName(CFG.sh.ekspor);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 7).getValues().map(function (r) {
    return { waktu: fmtDT_(r[0]), jenis: t_(r[1]), akun: t_(r[2]),
             jumlah: num_(r[3]) || 0, nama: t_(r[4]), fileId: t_(r[5]), oleh: t_(r[6]) };
  }).reverse();
}

function compKey_(nama, kec, namaBarang) {
  return lc_(nama).replace(/\s+/g, ' ') + '|' + lc_(kec).replace(/\s+/g, ' ') + '|' +
         lc_(namaBarang).replace(/\s+/g, ' ');
}
function pick_(obj, names) {
  for (var i = 0; i < names.length; i++) if (obj.hasOwnProperty(names[i])) return names[i];
  return null;
}

// ---------------------------------------------------------------------------
// CSV -> OrderOnline (paid). Dipisah per akun.
// ---------------------------------------------------------------------------
function exportCsvPaid() {
  me_();
  var sh = getSS().getSheetByName(CFG.sh.orders);
  var t = readTable_(sh);
  var grup = {}, idx = [];
  t.rows.forEach(function (r, i) {
    if (t_(r['Status Order']) !== CFG.ST.dapatAWB) return;
    if (!t_(r['URL Tracking'])) return;
    var akun = t_(r['Akun OO']) || 'NA';
    if (!grup[akun]) grup[akun] = [];
    grup[akun].push([t_(r['order_id']), t_(r['URL Tracking']), 'paid']);
    idx.push(i);
  });
  if (!idx.length) throw new Error('Tidak ada order berstatus "Dapat AWB" yang siap dikirim ke OrderOnline.');

  var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd_HHmm');
  var files = Object.keys(grup).map(function (akun) {
    var f = makeCsv_(['order_id', 'receipt_number', 'payment_status'], grup[akun],
      'OO_' + akun + '_paid_' + stamp + '.csv');
    f.akun = akun; f.jumlah = grup[akun].length;
    return f;
  });

  idx.forEach(function (i) { t.rows[i]['Status Order'] = CFG.ST.trackingOK; });
  writeTable_(sh, t);
  log_('Export CSV paid', idx.length + ' order, ' + files.length + ' file');
  return { ok: true, jumlah: idx.length, files: files };
}

// ---------------------------------------------------------------------------
// RETUR -> CSV unpaid (dipisah per akun)
// ---------------------------------------------------------------------------
function returDariFile(b64, filename) {
  me_();
  var rows = readSheet_(b64, filename, 0);
  var k = pick_(rows[0] || {}, ['No. Waybill', 'No Waybill', 'Waybill']);
  if (!k) throw new Error('Kolom "No. Waybill" tidak ditemukan di file.');
  var awbs = rows.map(function (r) { return t_(r[k]); }).filter(function (x) { return x; });
  return prosesRetur_(awbs, 'file: ' + filename);
}

function returDariSistemCS() {
  me_();
  if (!CFG.csSpreadsheetId) throw new Error('CFG.csSpreadsheetId belum diisi (ID spreadsheet Sistem CS).');
  var sh = SpreadsheetApp.openById(CFG.csSpreadsheetId).getSheetByName(CFG.csMasterSheet);
  if (!sh || sh.getLastRow() < 2) throw new Error('Sheet ' + CFG.csMasterSheet + ' kosong / tidak ditemukan.');
  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return t_(x); });
  var iW = header.indexOf('No. Waybill'), iS = header.indexOf('Status Ekspedisi');
  if (iW < 0 || iS < 0) throw new Error('Kolom "No. Waybill"/"Status Ekspedisi" tidak ditemukan di Sistem CS.');
  var awbs = [];
  sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues().forEach(function (r) {
    if (t_(r[iS]) === 'Retur') awbs.push(t_(r[iW]));
  });
  return prosesRetur_(awbs, 'Sistem CS Undelivered');
}

function prosesRetur_(awbs, sumber) {
  var lock = LockService.getScriptLock(); lock.waitLock(120000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.orders);
    var t = readTable_(sh);
    var byAwb = {};
    t.rows.forEach(function (r, i) { if (t_(r['No. Waybill'])) byAwb[t_(r['No. Waybill'])] = i; });

    var grup = {}, total = 0, tidakKetemu = 0, seen = {};
    awbs.forEach(function (a) {
      if (seen[a]) return; seen[a] = 1;
      if (!byAwb.hasOwnProperty(a)) { tidakKetemu++; return; }
      var r = t.rows[byAwb[a]];
      var akun = t_(r['Akun OO']) || 'NA';
      if (!grup[akun]) grup[akun] = [];
      grup[akun].push([t_(r['order_id']), t_(r['URL Tracking']), 'unpaid']);
      r['Status Order'] = CFG.ST.retur;
      total++;
    });
    if (!total) throw new Error('Tidak ada resi retur yang cocok dengan data order (' + tidakKetemu + ' tidak dikenali).');

    writeTable_(sh, t);
    var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd_HHmm');
    var files = Object.keys(grup).map(function (akun) {
      var f = makeCsv_(['order_id', 'receipt_number', 'payment_status'], grup[akun],
        'OO_' + akun + '_unpaid_' + stamp + '.csv');
      f.akun = akun; f.jumlah = grup[akun].length;
      return f;
    });
    var nm = ''; try { nm = me_().nama; } catch (e) {}
    catatExport_('unpaid (retur)', files, nm);
    log_('Export CSV retur', total + ' order | sumber: ' + sumber);
    return { ok: true, jumlah: total, tidakKetemu: tidakKetemu, files: files };
  } finally { lock.releaseLock(); }
}

function getTrackingStatus() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var o = { menungguAwb: 0, dapatAwb: 0, terkirimOO: 0, retur: 0 };
  t.rows.forEach(function (r) {
    var s = t_(r['Status Order']);
    if (s === CFG.ST.diBatch) o.menungguAwb++;
    else if (s === CFG.ST.dapatAWB) o.dapatAwb++;
    else if (s === CFG.ST.trackingOK) o.terkirimOO++;
    else if (s === CFG.ST.retur) o.retur++;
  });
  return o;
}
