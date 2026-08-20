/**
 * ============================================================================
 *  SISTEM 1 — SUPERVISOR: Upload & Distribusi (CS Undelivered, Meika Berkarya)
 *
 *  Supervisor upload file export ekspedisi menu "Sedang Diantar".
 *  Sistem menandai Status Ekspedisi, menormalkan,
 *  meng-UPSERT ke sheet MASTER berdasarkan No. Waybill (kolom kerja CS
 *  DIPERTAHANKAN), mendistribusikan otomatis ke CS via provinsi, dan
 *  meng-ARSIP-kan resi yang hilang dari snapshot (per bulan pengiriman).
 * ============================================================================
 */

// Dinaikkan SETIAP kali deploy. Halaman yang sedang terbuka membandingkan versinya
// dengan versi di server; kalau beda -> banner "versi baru" muncul.
var APP_VERSION = 'v3.2 — link foto (jmsfile + Drive) masuk export Excel';

// ---------------------------------------------------------------------------
// KONFIGURASI
// ---------------------------------------------------------------------------
var CFG = {
  spreadsheetId: '',                 // '' = pakai spreadsheet aktif
  masterSheet:  'MASTER_Undelivered',
  arsipSheet:   'Arsip_Undelivered', // resi yg keluar dari status aktif (hilang dari snapshot)
  mapSheet:     'Ref_Provinsi_CS',   // kolom: Provinsi | Nama CS | Email CS
  usersSheet:   'Users',             // kolom: Email | Nama | Peran | Provinsi
  logSheet:     'Log_Aktivitas',

  keyCol:       'No. Waybill',        // nama kolom nomor resi (dikonfirmasi dari file export)
  provinceCol:  'Provinsi Penerima',  // nama kolom provinsi (dikonfirmasi dari file export)
  shipDateCol:  'Tanggal Pengiriman', // kolom tanggal pengiriman (dasar cakupan per-bulan)

  arsipExtra: ['Tanggal Diarsip', 'Status Saat Diarsip'],

  // Rename kolom dari file export -> nama kolom di MASTER.
  // Berlaku untuk file yang diupload MAUPUN header lama yang sudah ada di sheet.
  renameCols: {
    '代收货款金额': 'Nilai COD'
  },

  /**
   * SATU status saja. "Sedang Retur" lalu "Retur" sudah dilepas — sistem ini
   * fokus penuh pada paket yang MASIH BISA DISELAMATKAN, yaitu "Sedang Diantar".
   * Paket yang sudah retur berarti sudah kalah; tidak ada lagi yang bisa
   * difollowup CS, jadi menampilkannya hanya menambah kebisingan.
   */
  statusLabel: {
    diantar: 'Sedang Diantar'
  },

  sysCols: ['Status Ekspedisi', 'Tanggal Update Status'],
  csCols:  ['PIC CS', 'Status Followup', 'Kategori Masalah', 'Hasil Konfirmasi',
            'Link POD Pembanding', 'Catatan CS', 'Timestamp Update', 'Diupdate Oleh'],

  driveRoot: 'CS_Undelivered'
};

function getSS() {
  return CFG.spreadsheetId ? SpreadsheetApp.openById(CFG.spreadsheetId)
                           : SpreadsheetApp.getActiveSpreadsheet();
}

// ---------------------------------------------------------------------------
// WEB APP ENTRY
// ---------------------------------------------------------------------------
function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Sistem 1 — Upload & Distribusi (Meika Berkarya)')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Cek versi — SENGAJA seringan mungkin, dipanggil berkala oleh halaman terbuka. */
function getVersi() { return APP_VERSION; }

/** URL web app aktif — untuk memuat ulang halaman ke versi terbaru. */
function getWebAppUrl() {
  try { return ScriptApp.getService().getUrl(); } catch (e) { return ''; }
}

// ---------------------------------------------------------------------------
// SETUP: buat sheet & header bila belum ada
// ---------------------------------------------------------------------------
function setup() {
  var ss = getSS();
  ensureSheet(ss, CFG.mapSheet,   ['Provinsi', 'Email CS']);
  ensureSheet(ss, CFG.usersSheet, ['Email', 'Nama', 'Peran', 'Aktif']);
  ensureSheet(ss, CFG.logSheet,   ['Waktu', 'Email', 'Aksi', 'Detail']);
  return 'Setup selesai. Kelola CS & wilayah lewat panel "Kelola CS & Wilayah" di web app.';
}
function ensureSheet(ss, name, header) {
  var sh = ss.getSheetByName(name);
  if (!sh) { sh = ss.insertSheet(name); }
  if (sh.getLastRow() < 1 || String(sh.getRange(1, 1).getValue()).trim() === '') {
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.setFrozenRows(1);
  }
  return sh;
}

// ---------------------------------------------------------------------------
// PROSES UPLOAD (dipanggil front-end)
//   slotKey: 'diantar' — satu-satunya slot yang tersisa
// ---------------------------------------------------------------------------
function processUpload(b64, filename, slotKey) {
  var statusLabel = CFG.statusLabel[slotKey];
  if (!statusLabel) throw new Error('Slot tidak dikenal: ' + slotKey);

  var rows = readUploadedSheet(b64, filename);
  if (!rows.length) throw new Error('File kosong / tidak ada baris data.');

  var uploadHeader = Object.keys(rows[0]);
  if (uploadHeader.indexOf(CFG.keyCol) < 0) {
    throw new Error('Kolom kunci "' + CFG.keyCol + '" tidak ditemukan di file. ' +
      'Sesuaikan CFG.keyCol dengan nama kolom nomor resi di file export Anda.');
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var ss = getSS();
    var sh = ss.getSheetByName(CFG.masterSheet) || ss.insertSheet(CFG.masterSheet);

    // --- susun header MASTER: kolom export + kolom sistem + kolom CS ---
    var existingHeader = (sh.getLastRow() >= 1)
      ? sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(function (x) { return String(x).trim(); })
      : [];
    // rename header lama juga, supaya data yg terlanjur masuk dgn nama kolom asli
    // (mis. 代收货款金额) ikut dipetakan ke "Nilai COD" — tidak jadi kolom ganda.
    existingHeader = renameHead_(existingHeader).filter(function (x) { return x !== ''; });

    var header = mergeHeader(existingHeader, uploadHeader);
    var idx = {}; header.forEach(function (h, i) { idx[h] = i; });

    // --- muat data MASTER yg ada (array baris selaras header baru) ---
    var existRows = [];
    if (sh.getLastRow() > 1 && existingHeader.length) {
      var raw = sh.getRange(2, 1, sh.getLastRow() - 1, existingHeader.length).getValues();
      raw.forEach(function (r) {
        var obj = new Array(header.length).fill('');
        existingHeader.forEach(function (h, i) { if (idx.hasOwnProperty(h)) obj[idx[h]] = r[i]; });
        existRows.push(obj);
      });
    }
    var keyIdx = idx[CFG.keyCol];
    var map = {};
    existRows.forEach(function (r, i) { map[normKey(r[keyIdx])] = i; });

    // --- muat arsip (objek per kolom) untuk kemungkinan restore ---
    var ar = loadArsip(ss);            // { map: key->obj, list: [obj] }
    var restoredKeys = {};

    // --- peta provinsi -> CS untuk distribusi otomatis ---
    var provMap = loadProvinceMap(ss);
    var today = new Date();
    var picIdx = idx['PIC CS'];
    var provIdx = idx[CFG.provinceCol];
    var stIdx = idx['Status Ekspedisi'];
    var tglIdx = idx['Tanggal Update Status'];
    var shipIdx = idx[CFG.shipDateCol];

    // --- himpunan kunci diupload & bulan pengiriman yg tercakup file ---
    var uploadedKeys = {}, monthsInUpload = {};
    rows.forEach(function (src) {
      var k = normKey(src[CFG.keyCol]); if (k === '') return;
      uploadedKeys[k] = 1;
      var mk = monthKey(src[CFG.shipDateCol]); if (mk) monthsInUpload[mk] = 1;
    });

    var added = 0, updated = 0, restored = 0;
    rows.forEach(function (src) {
      var k = normKey(src[CFG.keyCol]);
      if (k === '') return;

      var row;
      if (map.hasOwnProperty(k)) {                 // UPDATE (pertahankan kolom CS)
        row = existRows[map[k]];
        uploadHeader.forEach(function (h) { if (idx.hasOwnProperty(h)) row[idx[h]] = src[h]; });
        updated++;
      } else {                                     // INSERT (mungkin kembali dari arsip)
        row = new Array(header.length).fill('');
        uploadHeader.forEach(function (h) { if (idx.hasOwnProperty(h)) row[idx[h]] = src[h]; });
        if (ar.map.hasOwnProperty(k)) {            // restore hasil kerja CS dari arsip
          var ao = ar.map[k];
          CFG.csCols.forEach(function (c) {
            if (idx.hasOwnProperty(c) && ao[c] != null && ao[c] !== '') row[idx[c]] = ao[c];
          });
          restoredKeys[k] = 1; restored++;
        }
        existRows.push(row);
        map[k] = existRows.length - 1;
        added++;
      }
      if (stIdx  != null) row[stIdx]  = statusLabel;
      if (tglIdx != null) row[tglIdx] = today;
      if (picIdx != null && provIdx != null && String(row[picIdx]).trim() === '') {
        var cs = provMap[normProv(row[provIdx])];
        if (cs) row[picIdx] = cs;
      }
    });

    // --- RECONCILE: resi berstatus sama, di bulan tercakup, tapi hilang dari file -> arsipkan ---
    var keep = [], archivedNow = [];
    existRows.forEach(function (row) {
      var st = String(row[stIdx]).trim();
      var k = normKey(row[keyIdx]);
      var mk = (shipIdx != null) ? monthKey(row[shipIdx]) : '';
      var disappeared = (st === statusLabel) && mk && monthsInUpload[mk] && !uploadedKeys[k];
      if (disappeared) {
        var o = {}; header.forEach(function (h, i) { o[h] = row[i]; });
        o[CFG.arsipExtra[0]] = today;        // Tanggal Diarsip
        o[CFG.arsipExtra[1]] = statusLabel;  // Status Saat Diarsip
        archivedNow.push(o);
      } else {
        keep.push(row);
      }
    });
    existRows = keep;

    // --- urut: Status Ekspedisi, lalu Provinsi, lalu key ---
    existRows.sort(function (a, b) {
      return cmp(a[stIdx], b[stIdx]) || cmp(a[provIdx], b[provIdx]) || cmp(a[keyIdx], b[keyIdx]);
    });

    // --- tulis balik MASTER (batch) ---
    sh.clear();
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.setFrozenRows(1);
    if (existRows.length) sh.getRange(2, 1, existRows.length, header.length).setValues(existRows);

    // --- tulis balik ARSIP: arsip lama minus yg direstore + yg baru diarsipkan ---
    var arsipHeader = header.concat(CFG.arsipExtra);
    var arsipObjs = ar.list.filter(function (o) { return !restoredKeys[normKey(o[CFG.keyCol])]; }).concat(archivedNow);
    writeArsip(ss, arsipHeader, arsipObjs);

    // --- arsip file mentah + log ---
    try { archiveUpload(b64, filename); } catch (e) {}
    logAct('Upload ' + statusLabel, filename + ' | +' + added + ' /~' + updated +
           ' | restore ' + restored + ' | arsip +' + archivedNow.length);

    var undistributed = 0;
    if (picIdx != null) existRows.forEach(function (r) { if (String(r[picIdx]).trim() === '') undistributed++; });

    return { statusLabel: statusLabel, filename: filename, processed: rows.length,
             added: added, updated: updated, restored: restored, archived: archivedNow.length,
             total: existRows.length, undistributed: undistributed };
  } finally {
    lock.releaseLock();
  }
}

function mergeHeader(existingHeader, uploadHeader) {
  var sysset = {}; CFG.sysCols.forEach(function (c) { sysset[c] = 1; });
  var csset  = {}; CFG.csCols.forEach(function (c) { csset[c] = 1; });
  var isMeta = function (h) { return sysset[h] || csset[h]; };

  var exportCols = [];
  var push = function (h) { if (h && !isMeta(h) && exportCols.indexOf(h) < 0) exportCols.push(h); };
  uploadHeader.forEach(push);
  existingHeader.forEach(push);

  return exportCols.concat(CFG.sysCols).concat(CFG.csCols);
}

// ---------------------------------------------------------------------------
// DASHBOARD DATA (dengan cache singkat)
// ---------------------------------------------------------------------------
function getDashboard() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('dash1');
  if (hit) return JSON.parse(hit);

  var ss = getSS();
  var sh = ss.getSheetByName(CFG.masterSheet);
  var out = { total: 0, byStatus: {}, byCS: {}, undistributed: 0, arsipTotal: 0,
              statuses: [CFG.statusLabel.diantar],
              hasData: false };
  if (sh && sh.getLastRow() > 1) {
    var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    var si = header.indexOf('Status Ekspedisi'), pi = header.indexOf('PIC CS');
    out.total = data.length; out.hasData = true;
    data.forEach(function (r) {
      var st = si >= 0 ? (String(r[si]).trim() || '(kosong)') : '(kosong)';
      out.byStatus[st] = (out.byStatus[st] || 0) + 1;
      var cs = pi >= 0 ? String(r[pi]).trim() : '';
      if (cs === '') out.undistributed++;
      else out.byCS[cs] = (out.byCS[cs] || 0) + 1;
    });
  }
  var ash = ss.getSheetByName(CFG.arsipSheet);
  if (ash && ash.getLastRow() > 1) out.arsipTotal = ash.getLastRow() - 1;

  cache.put('dash1', JSON.stringify(out), 90);
  return out;
}

// ---------------------------------------------------------------------------
// BACA FILE UPLOAD (xlsx/xls -> Google Sheet sementara via Drive)
// ---------------------------------------------------------------------------
function readUploadedSheet(b64, filename) {
  var blob = Utilities.newBlob(Utilities.base64Decode(b64),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename || 'upload.xlsx');
  var tmp = driveConvertToSheet(blob);
  try {
    var sh = SpreadsheetApp.openById(tmp.id).getSheets()[0];
    var values = sh.getDataRange().getValues();
    if (values.length < 2) return [];
    var header = renameHead_(values[0].map(function (h) { return String(h).trim(); }));
    var out = [];
    for (var i = 1; i < values.length; i++) {
      var obj = {}, blank = true;
      for (var j = 0; j < header.length; j++) {
        var v = values[i][j]; obj[header[j]] = v;
        if (v !== '' && v !== null && v !== undefined) blank = false;
      }
      if (!blank) out.push(obj);
    }
    return out;
  } finally {
    DriveApp.getFileById(tmp.id).setTrashed(true);
  }
}

/** Konversi blob -> Google Sheet sementara. Dukung Drive API v3 (create) & v2 (insert). */
function driveConvertToSheet(blob) {
  var name = '__tmp_cs1_' + Date.now();
  if (typeof Drive.Files.create === 'function') {
    return Drive.Files.create({ name: name, mimeType: MimeType.GOOGLE_SHEETS }, blob, { supportsAllDrives: true });
  }
  return Drive.Files.insert({ title: name, mimeType: MimeType.GOOGLE_SHEETS }, blob, { convert: true });
}

// ---------------------------------------------------------------------------
// ARSIP HELPERS
// ---------------------------------------------------------------------------
function loadArsip(ss) {
  var sh = ss.getSheetByName(CFG.arsipSheet);
  var res = { map: {}, list: [] };
  if (!sh || sh.getLastRow() < 2) return res;
  var hdr = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); }));
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var kcol = hdr.indexOf(CFG.keyCol);
  data.forEach(function (r) {
    var o = {}; hdr.forEach(function (h, i) { o[h] = r[i]; });
    res.list.push(o);
    if (kcol >= 0) res.map[normKey(r[kcol])] = o;
  });
  return res;
}

/** Terapkan CFG.renameCols pada daftar nama kolom. */
function renameHead_(header) {
  return header.map(function (h) {
    var name = String(h).trim();
    return CFG.renameCols.hasOwnProperty(name) ? CFG.renameCols[name] : name;
  });
}
function writeArsip(ss, arsipHeader, objs) {
  var sh = ss.getSheetByName(CFG.arsipSheet) || ss.insertSheet(CFG.arsipSheet);
  sh.clear();
  sh.getRange(1, 1, 1, arsipHeader.length).setValues([arsipHeader]);
  sh.setFrozenRows(1);
  if (objs.length) {
    var rows = objs.map(function (o) { return arsipHeader.map(function (h) { return (o[h] == null) ? '' : o[h]; }); });
    sh.getRange(2, 1, rows.length, arsipHeader.length).setValues(rows);
  }
}
function monthKey(v) {
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM');
  var m = String(v).match(/(\d{4})-(\d{1,2})/);
  return m ? (m[1] + '-' + ('0' + m[2]).slice(-2)) : '';
}

// ---------------------------------------------------------------------------
// DISTRIBUSI, ARSIP FILE, LOG, UTIL
// ---------------------------------------------------------------------------
// Peta provinsi(lower) -> label PIC (Nama CS dari Users, fallback email).
// loadUsers & loadAssignments didefinisikan di Admin.gs (satu project yg sama).
function loadProvinceMap(ss) {
  var u = loadUsers(ss);
  var a = loadAssignments(ss);
  var m = {};
  a.list.forEach(function (x) {
    var us = u.map[x.email.toLowerCase()];
    m[x.provLower] = (us && us.nama) ? us.nama : x.email;
  });
  return m;
}

function archiveUpload(b64, filename) {
  var folder = getFolderPath([CFG.driveRoot, 'Arsip_Upload', ym()]);
  var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd_HHmmss');
  folder.createFile(Utilities.newBlob(Utilities.base64Decode(b64), 'application/octet-stream', stamp + '_' + filename));
}
function getFolderPath(parts) {
  var cur = DriveApp.getRootFolder();
  parts.forEach(function (name) {
    var it = cur.getFoldersByName(name);
    cur = it.hasNext() ? it.next() : cur.createFolder(name);
  });
  return cur;
}
function ym() { return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM'); }

function logAct(action, detail) {
  try {
    var ss = getSS();
    var sh = ss.getSheetByName(CFG.logSheet) || ensureSheet(ss, CFG.logSheet, ['Waktu', 'Email', 'Aksi', 'Detail']);
    sh.appendRow([new Date(), (Session.getActiveUser().getEmail() || ''), action, detail]);
  } catch (e) {}
}

function normKey(v) {
  if (v === null || v === undefined) return '';
  var s = (v instanceof Date) ? String(v.getTime()) : String(v);
  return s.replace(/\s+/g, '').replace(/\.0$/, '');
}
function normProv(v) { return String(v == null ? '' : v).trim().toLowerCase(); }
function cmp(a, b) {
  var ea = (a === '' || a == null), eb = (b === '' || b == null);
  if (ea && eb) return 0; if (ea) return 1; if (eb) return -1;
  if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime();
  return a < b ? -1 : (a > b ? 1 : 0);
}
