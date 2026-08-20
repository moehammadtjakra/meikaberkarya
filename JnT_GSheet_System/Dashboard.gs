/**
 * ============================================================================
 *  J&T DATA LOADER — DASHBOARD & PROYEKSI PENCAIRAN   (Meika Berkarya)
 *
 *  DEFINISI STATUS RESI (dari sheet "All Resi"):
 *    SAMPAI      : Tanda TTD menyatakan sudah sampai
 *    BERMASALAH  : Tanda TTD BELUM sampai, TAPI kolom Waktu Terima sudah terisi
 *                  (paket berhenti/retur/selesai tanpa TTD normal)
 *    PROSES      : Tanda TTD BELUM sampai DAN Waktu Terima masih kosong
 *
 *  NET OMZET  =  Nilai COD  −  COD Fee  −  Total Biaya Setelah Diskon
 *  Dihitung hanya untuk resi COD (Nilai COD > 0). Non-COD tidak menghasilkan
 *  pencairan dari J&T, jadi tidak ikut dijumlahkan.
 *
 *  JADWAL PENCAIRAN J&T (berdasarkan HARI PAKET SAMPAI):
 *    sampai Rabu / Kamis            -> cair SENIN berikutnya
 *    sampai Jumat / Sabtu / Minggu  -> cair SELASA berikutnya
 *    sampai Senin / Selasa          -> cair KAMIS minggu yang sama
 *
 *  REALISASI vs PROYEKSI:
 *    - Resi yang SUDAH ada di "Settle Reconcile" -> pencairan dihitung dari
 *      "Waktu TTD" pada file reconcile  (angka yang sudah dikonfirmasi J&T)
 *    - Resi SAMPAI di "All Resi" tapi BELUM ada di reconcile -> PROYEKSI,
 *      dihitung dari "Waktu Terima"
 * ============================================================================
 */

var DASH = {
  // kolom All Resi
  aKey: 'No. Waybill', aKirim: 'Tanggal Pengiriman', aProv: 'Provinsi Penerima',
  aTerima: 'Waktu Terima', aTTD: 'Tanda TTD', aBarang: 'Nama Barang', aFlagCOD: 'COD',
  aCOD: 'Nilai COD', aFee: 'COD Fee', aBiaya: 'Total Biaya Setelah Diskon',

  // kolom Settle Reconcile
  rKey: 'No. Waybill', rTTD: 'Waktu TTD', rStatus: 'Status Retur',

  /**
   * Nilai "Tanda TTD" yang berarti paket SAMPAI.
   * Kosongkan array ini untuk memakai aturan otomatis:
   *   dianggap SAMPAI bila Tanda TTD terisi dan TIDAK mengandung kata
   *   "belum" / "tidak" / "retur" / "gagal" / "batal".
   * Kalau nama status di data Anda berbeda, cukup daftarkan di sini —
   * nilai unik yang ditemukan sistem selalu ditampilkan di panel Kalibrasi.
   */
  ttdSampai: [],

  ttdBukanSampai: ['belum', 'tidak', 'retur', 'gagal', 'batal', 'cancel', 'void']
};

// ---------------------------------------------------------------------------
// (Report per Barang dihapus — pencocokan nama antar-produk O(n²) dengan Levenshtein
//  membuat dashboard lambat. Fungsi normalisasi nama barang ikut dihapus.)

// ---------------------------------------------------------------------------
// PARSE 1 BARIS All Resi -> objek terklasifikasi (satu sumber kebenaran)
// ---------------------------------------------------------------------------
function parseResi_(r) {
  var ttd = String(r[DASH.aTTD] == null ? '' : r[DASH.aTTD]).trim();
  var sampai = isSampai_(ttd);
  var tTerima = tgl_(r[DASH.aTerima]);
  var tKirim  = tgl_(r[DASH.aKirim]);
  var cod = ang_(r[DASH.aCOD]), fee = ang_(r[DASH.aFee]), biaya = ang_(r[DASH.aBiaya]);
  var isCod = cod > 0;
  var kelas = sampai ? 'sampai' : (tTerima ? 'bermasalah' : 'proses');
  var durasi = null;
  if (kelas === 'sampai' && tKirim && tTerima) {
    var d = Math.round((tTerima - tKirim) / 86400000);
    if (d >= 0 && d < 120) durasi = d;
  }
  return { ttd: ttd, sampai: sampai, kelas: kelas, isCod: isCod,
           net: isCod ? (cod - fee - biaya) : 0,
           tTerima: tTerima, tKirim: tKirim, durasi: durasi,
           key: normKey(r[DASH.aKey]),
           prov: String(r[DASH.aProv] == null ? '' : r[DASH.aProv]).trim() || '(kosong)' };
}

// ===========================================================================
// ENDPOINT 1 — INTI (hanya baca "All Resi"): KPI, per bulan, provinsi, kalibrasi
//   Cepat & tidak bergantung pada Settle Reconcile, jadi bisa tampil lebih dulu.
// ===========================================================================
function getDashInti() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('dashInti');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var A = bacaSheet_(CONFIG.allResi.sheetName);
  var out = {
    adaData: A.rows.length > 0,
    ringkas: { dikirim: 0, sampai: 0, netSampai: 0, bermasalah: 0, netBermasalah: 0,
               proses: 0, netProses: 0, nonCod: 0, cod: 0, pctCod: 0,
               pctSampai: 0, pctBermasalah: 0, pctProses: 0, rerataDurasi: 0 },
    provinsi: [], bulanan: [], kalibrasi: []
  };
  if (!A.rows.length) return out;

  var tz = Session.getScriptTimeZone();
  var Rg = out.ringkas;
  var prov = {}, bulan = {}, ttdUnik = {}, durTotal = 0, durN = 0;

  A.rows.forEach(function (r) {
    var e = parseResi_(r);
    Rg.dikirim++;
    if (e.isCod) Rg.cod++; else Rg.nonCod++;

    if (!ttdUnik[e.ttd]) ttdUnik[e.ttd] = { nilai: e.ttd || '(kosong)', n: 0, sampai: e.sampai };
    ttdUnik[e.ttd].n++;

    if (e.kelas === 'sampai')          { Rg.sampai++;     Rg.netSampai += e.net; }
    else if (e.kelas === 'bermasalah') { Rg.bermasalah++; Rg.netBermasalah += e.net; }
    else                               { Rg.proses++;     Rg.netProses += e.net; }
    if (e.durasi !== null) { durTotal += e.durasi; durN++; }

    var P = prov[e.prov] || (prov[e.prov] = { provinsi: e.prov, total: 0, sampai: 0,
                              bermasalah: 0, proses: 0, net: 0, durTotal: 0, durN: 0 });
    P.total++; P[e.kelas]++;
    if (e.kelas === 'sampai') P.net += e.net;
    if (e.durasi !== null) { P.durTotal += e.durasi; P.durN++; }

    var bk = e.tKirim ? Utilities.formatDate(e.tKirim, tz, 'yyyy-MM') : '(tanpa tanggal)';
    var B = bulan[bk] || (bulan[bk] = { bulan: bk,
              label: bk === '(tanpa tanggal)' ? bk : namaBulan_(e.tKirim),
              dikirim: 0, sampai: 0, bermasalah: 0, proses: 0, net: 0, durTotal: 0, durN: 0 });
    B.dikirim++; B[e.kelas]++;
    if (e.kelas === 'sampai') B.net += e.net;
    if (e.durasi !== null) { B.durTotal += e.durasi; B.durN++; }
  });

  Rg.pctCod        = pctBulat_(Rg.cod, Rg.dikirim);
  Rg.pctSampai     = pctBulat_(Rg.sampai, Rg.dikirim);
  Rg.pctBermasalah = pctBulat_(Rg.bermasalah, Rg.dikirim);
  Rg.pctProses     = pctBulat_(Rg.proses, Rg.dikirim);
  Rg.rerataDurasi  = durN ? Math.round(durTotal / durN * 10) / 10 : 0;

  out.provinsi = Object.keys(prov).map(function (k) {
    var P = prov[k];
    return { provinsi: P.provinsi, total: P.total,
             sampai: P.sampai, pctSampai: pct_(P.sampai, P.total),
             bermasalah: P.bermasalah, pctBermasalah: pct_(P.bermasalah, P.total),
             proses: P.proses, pctProses: pct_(P.proses, P.total),
             durasi: P.durN ? Math.round(P.durTotal / P.durN * 10) / 10 : '', net: P.net };
  }).sort(function (a, b) { return b.total - a.total; });

  out.bulanan = Object.keys(bulan).sort().reverse().map(function (k) {
    var B = bulan[k];
    return { bulan: B.bulan, label: B.label, dikirim: B.dikirim,
             sampai: B.sampai, pctSampai: pct_(B.sampai, B.dikirim),
             bermasalah: B.bermasalah, pctBermasalah: pct_(B.bermasalah, B.dikirim),
             proses: B.proses, pctProses: pct_(B.proses, B.dikirim),
             durasi: B.durN ? Math.round(B.durTotal / B.durN * 10) / 10 : '', net: B.net };
  });

  out.kalibrasi = Object.keys(ttdUnik).map(function (k) { return ttdUnik[k]; })
    .sort(function (a, b) { return b.n - a.n; });

  try { cache.put('dashInti', JSON.stringify(out), 30); } catch (e) {}   // simpan 30 dtk
  return out;
}

// ===========================================================================
// ENDPOINT 2 — SETTLE (silang "All Resi" x "Settle Reconcile"): KPI settle + pencairan
// ===========================================================================
function getDashSettle() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('dashSettle');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var A = bacaSheet_(CONFIG.allResi.sheetName);
  var R = bacaSheet_(CONFIG.reconcile.sheetName);
  var out = { sudahSettle: 0, netSudahSettle: 0, belumSettle: 0, netBelumSettle: 0,
              pencairan: [], berikutnya: null, reconcileRows: R.rows.length };
  if (!A.rows.length) return out;

  var settle = {};
  R.rows.forEach(function (r) {
    var k = normKey(r[DASH.rKey]);
    if (k) settle[k] = tgl_(r[DASH.rTTD]);
  });

  var tz = Session.getScriptTimeZone();
  var cair = {};
  A.rows.forEach(function (r) {
    var e = parseResi_(r);
    if (e.kelas !== 'sampai' || !e.isCod) return;              // hanya COD yang sudah sampai
    var sudah = settle.hasOwnProperty(e.key) && settle[e.key];
    var acuan = sudah ? settle[e.key] : e.tTerima;            // reconcile lebih otoritatif
    if (!acuan) return;
    var tc = tglCair_(acuan);
    var ds = Utilities.formatDate(tc, tz, 'yyyy-MM-dd');
    var c = cair[ds] || (cair[ds] = { tanggal: ds, hari: namaHari_(tc),
              label: Utilities.formatDate(tc, tz, 'dd/MM/yyyy'),
              resiSettle: 0, netSettle: 0, resiProyeksi: 0, netProyeksi: 0 });
    if (sudah) { c.resiSettle++;   c.netSettle += e.net;   out.sudahSettle++; out.netSudahSettle += e.net; }
    else       { c.resiProyeksi++; c.netProyeksi += e.net; out.belumSettle++; out.netBelumSettle += e.net; }
  });

  var hariIni = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  out.pencairan = Object.keys(cair).sort().map(function (k) {
    var c = cair[k];
    c.total = c.netSettle + c.netProyeksi;
    c.resi = c.resiSettle + c.resiProyeksi;
    c.lewat = (c.tanggal < hariIni);
    return c;
  });
  var depan = out.pencairan.filter(function (c) { return !c.lewat; });
  out.berikutnya = depan.length ? depan[0] : null;

  try { cache.put('dashSettle', JSON.stringify(out), 30); } catch (e) {}
  return out;
}

/** Kosongkan cache dashboard — dipanggil setiap selesai upload agar angka selalu akurat. */
function dashCacheClear_() {
  try { CacheService.getScriptCache().removeAll(['dashInti', 'dashSettle']); } catch (e) {}
}

/** Endpoint gabungan (kompatibilitas) — menyatukan inti + settle. */
function getDashboard() {
  var inti = getDashInti();
  if (!inti.adaData) return inti;
  var s = getDashSettle();
  ['sudahSettle', 'netSudahSettle', 'belumSettle', 'netBelumSettle'].forEach(function (k) {
    inti.ringkas[k] = s[k];
  });
  inti.pencairan = s.pencairan;
  inti.berikutnya = s.berikutnya;
  inti.reconcileRows = s.reconcileRows;
  return inti;
}

function pctBulat_(a, b) { return b ? Math.round(a / b * 100) : 0; }

// ---------------------------------------------------------------------------
// ATURAN
// ---------------------------------------------------------------------------
/** Tanda TTD -> apakah paket SAMPAI? */
function isSampai_(ttd) {
  var s = String(ttd || '').trim().toLowerCase();
  if (!s) return false;                                   // kosong = belum sampai
  if (DASH.ttdSampai.length) {                            // daftar eksplisit (kalau diisi)
    return DASH.ttdSampai.some(function (x) { return String(x).toLowerCase() === s; });
  }
  var buruk = DASH.ttdBukanSampai.some(function (w) { return s.indexOf(w) >= 0; });
  return !buruk;
}

/**
 * Tanggal pencairan J&T dari tanggal paket SAMPAI.
 *   Sen(1)->Kam(+3)  Sel(2)->Kam(+2)  Rab(3)->Sen(+5)  Kam(4)->Sen(+4)
 *   Jum(5)->Sel(+4)  Sab(6)->Sel(+3)  Min(0)->Sel(+2)
 */
function tglCair_(d) {
  var tambah = { 0: 2, 1: 3, 2: 2, 3: 5, 4: 4, 5: 4, 6: 3 };
  var r = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  r.setDate(r.getDate() + tambah[r.getDay()]);
  return r;
}

function namaHari_(d) {
  return ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'][d.getDay()];
}

function namaBulan_(d) {
  var b = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
           'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
  return b[d.getMonth()] + ' ' + d.getFullYear();
}

// ===========================================================================
// PREVIEW & EXPORT — "Sampai tapi BELUM di reconcile"
//
// Daftar resi yang PERSIS dihitung widget: sudah SAMPAI + COD + belum muncul di
// Settle Reconcile. Non-COD sengaja tidak masuk (net-nya 0, tidak menghasilkan
// pencairan), jadi jumlah baris = angka pada widget.
// ===========================================================================
var BELUM_COLS = [
  'No. Waybill', 'Tanggal Pengiriman', 'Penerima', 'Provinsi Penerima',
  'Nilai Barang', 'Biaya Kirim Setelah Diskon', 'Nilai COD', 'COD Fee',
  'Diterima Oleh', 'Waktu Terima', 'Keterangan', 'Tanda TTD',
  'COD / Non-COD', 'Net Diterima'
];

function dataBelumReconcile_() {
  var A = bacaSheet_(CONFIG.allResi.sheetName);
  var R = bacaSheet_(CONFIG.reconcile.sheetName);
  var settle = {};
  R.rows.forEach(function (r) { var k = normKey(r[DASH.rKey]); if (k) settle[k] = 1; });

  var s = function (v) { return String(v == null ? '' : v).trim(); };
  var out = [];
  A.rows.forEach(function (r) {
    var e = parseResi_(r);
    if (e.kelas !== 'sampai' || !e.isCod) return;      // hanya COD yang sudah sampai
    if (settle.hasOwnProperty(e.key)) return;          // sudah reconcile -> lewati
    out.push({
      waybill:      s(r[DASH.aKey]),
      tglKirim:     fmtTgl_(r[DASH.aKirim]),
      penerima:     s(r['Penerima']),
      provinsi:     s(r[DASH.aProv]),
      nilaiBarang:  ang_(r['Nilai Barang']),
      biaya:        ang_(r[DASH.aBiaya]),               // Total Biaya Setelah Diskon
      cod:          ang_(r[DASH.aCOD]),
      fee:          ang_(r[DASH.aFee]),
      diterimaOleh: s(r['Diterima Oleh']),
      waktuTerima:  fmtTgl_(r[DASH.aTerima]),
      keterangan:   s(r['Keterangan']),
      ttd:          s(r[DASH.aTTD]),
      isCod:        true,
      net:          e.net                               // Nilai COD − COD Fee − Total Biaya Setelah Diskon
    });
  });
  // urut dari net terbesar supaya yang paling "berharga" di atas
  out.sort(function (a, b) { return b.net - a.net; });
  return out;
}

/** Dipanggil dari modal preview. */
function getBelumReconcile() {
  var d = dataBelumReconcile_();
  return { rows: d, total: d.length,
           netTotal: d.reduce(function (a, x) { return a + x.net; }, 0) };
}

/** Bangun file .xlsx dari daftar yang sama, lalu kirim ke klien untuk diunduh. */
function exportBelumReconcile() {
  var d = dataBelumReconcile_();
  var body = d.map(function (x) {
    return [x.waybill, x.tglKirim, x.penerima, x.provinsi, x.nilaiBarang, x.biaya,
            x.cod, x.fee, x.diterimaOleh, x.waktuTerima, x.keterangan, x.ttd,
            x.isCod ? 'COD' : 'Non-COD', x.net];
  });
  return bikinXlsx_('Sampai_BelumReconcile', BELUM_COLS, body,
                    ['Nilai Barang', 'Biaya Kirim Setelah Diskon', 'Nilai COD', 'COD Fee', 'Net Diterima']);
}

/** Format tanggal untuk tampilan (dd/MM/yyyy), aman untuk sel kosong. */
function fmtTgl_(v) {
  var d = tgl_(v);
  return d ? Utilities.formatDate(d, Session.getScriptTimeZone() || 'Asia/Jakarta', 'dd/MM/yyyy') : '';
}

/**
 * Bangun file .xlsx: tulis ke spreadsheet SEMENTARA, minta Google export xlsx
 * lewat OAuth, ambil byte-nya, lalu spreadsheet sementara dibuang di 'finally'.
 * (Perlu izin UrlFetch — saat deploy pertama setelah ini, Apps Script minta
 * otorisasi ulang. Itu normal.)
 */
function bikinXlsx_(namaDasar, header, rows, numCols) {
  var tz = Session.getScriptTimeZone() || 'Asia/Jakarta';
  var stamp = Utilities.formatDate(new Date(), tz, 'yyyyMMdd_HHmm');
  var namaFile = namaDasar + '_' + stamp + '.xlsx';

  var tmp = SpreadsheetApp.create('__tmp_export_' + stamp + '_' + Math.floor(Math.random() * 1e6));
  var tmpId = tmp.getId();
  try {
    var sh = tmp.getSheets()[0];
    sh.setName('Export');
    var all = [header].concat(rows.length ? rows : [header.map(function () { return ''; })]);
    sh.getRange(1, 1, all.length, header.length).setValues(all);
    sh.getRange(1, 1, 1, header.length)
      .setFontWeight('bold').setBackground('#C8102E').setFontColor('#ffffff');
    sh.setFrozenRows(1);
    (numCols || []).forEach(function (nm) {
      var c = header.indexOf(nm);
      if (c >= 0 && rows.length) sh.getRange(2, c + 1, rows.length, 1).setNumberFormat('#,##0');
    });
    sh.setColumnWidths(1, header.length, 120);
    ['Penerima', 'Keterangan', 'Diterima Oleh'].forEach(function (nm) {
      var c = header.indexOf(nm); if (c >= 0) sh.setColumnWidth(c + 1, 200);
    });
    SpreadsheetApp.flush();

    var url = 'https://docs.google.com/spreadsheets/d/' + tmpId + '/export?format=xlsx';
    var resp = UrlFetchApp.fetch(url, {
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200)
      throw new Error('Gagal membangun Excel (HTTP ' + resp.getResponseCode() + '). Coba lagi.');

    return {
      nama: namaFile, jumlah: rows.length,
      mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      b64: Utilities.base64Encode(resp.getBlob().getBytes())
    };
  } finally {
    try { DriveApp.getFileById(tmpId).setTrashed(true); } catch (e) {}
  }
}

// ---------------------------------------------------------------------------
// HELPER
// ---------------------------------------------------------------------------
/** Baca sheet jadi array objek per NAMA kolom (aman terhadap urutan kolom). */
function bacaSheet_(nama) {
  var sh = getSpreadsheet().getSheetByName(nama);
  if (!sh || sh.getLastRow() < 2) return { header: [], rows: [] };
  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var rows = data.map(function (r) {
    var o = {};
    header.forEach(function (h, i) { if (h) o[h] = r[i]; });
    return o;
  });
  return { header: header, rows: rows };
}

function ang_(v) {
  if (v === null || v === undefined || v === '') return 0;
  var n = parseFloat(String(v).replace(/[^\d.-]/g, ''));
  return isNaN(n) ? 0 : n;
}
function tgl_(v) {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null
    : new Date(v.getFullYear(), v.getMonth(), v.getDate());
  var m = String(v).match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  var d = new Date(v);
  return isNaN(d.getTime()) ? null : new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
function pct_(a, b) { return b ? Math.round(a / b * 1000) / 10 : 0; }
