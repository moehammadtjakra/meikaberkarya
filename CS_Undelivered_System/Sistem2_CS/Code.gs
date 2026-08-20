/**
 * ============================================================================
 *  SISTEM 2 — TIM CS: Followup Paket Undelivered (Meika Berkarya)   [v4]
 *
 *  TIGA komponen status yang dipisah tegas:
 *   1) Kategori Masalah      -> KLAIM dari ekspedisi/kurir (apa kata kurir)
 *   2) Status Followup       -> proses kerja CS (sejauh mana dihubungi)
 *   3) Hasil POD Pembanding  -> FAKTA dari konsumen (apa kata konsumen)
 *  Pertentangan antara (1) dan (3) = indikasi klaim kurir tidak valid.
 *
 *  Catatan: (3) disimpan di kolom sheet "Hasil Konfirmasi" (nama kolom lama
 *  dipertahankan agar cocok dengan Sistem 1); labelnya di UI = POD Pembanding.
 *
 *  PENTING: appsscript.json harus memuat scope "https://www.googleapis.com/auth/drive"
 *  agar upload foto tidak error. Jalankan cekAkses() untuk memastikan.
 * ============================================================================
 */

// Dinaikkan SETIAP kali deploy. Halaman yang sedang terbuka membandingkan versinya
// dengan versi di server; kalau beda -> banner "versi baru" muncul.
var APP_VERSION = 'v5.6 — link foto (jmsfile+Drive+POD pembanding) di export; anti-cache refresh';

var CFG2 = {
  spreadsheetId: '1P0VqcmpDPQtdf_8mpGQHBypKEemsIxBZuWKolLiKEKY',
  podFolderId:   '1PORxl9YwKwivD7EryPq7vPWLWDN-ywrx',

  masterSheet: 'MASTER_Undelivered',
  usersSheet:  'Users',
  mapSheet:    'Ref_Provinsi_CS',
  katSheet:    'Ref_Kategori_Masalah',
  tplSheet:    'Ref_Template_Pesan',
  logSheet:    'Log_Aktivitas',

  keyCol:      'No. Waybill',
  provinceCol: 'Provinsi Penerima',
  statusCol:   'Status Ekspedisi',
  shipDateCol: 'Tanggal Pengiriman',

  codCol:     'Nilai COD',
  ongkirCol:  'Total Biaya',
  codFlagCol: 'COD',

  showCols: ['Penerima', 'Telepon Penerima', 'Kota Penerima', 'Kecamatan Penerima',
             'Alamat Penerima', 'Nama Barang', 'Nilai COD', 'Total Biaya',
             'COD', 'Tanda TTD', 'Keterangan'],

  cPIC: 'PIC CS', cFU: 'Status Followup', cKat: 'Kategori Masalah',
  cHasil: 'Hasil Konfirmasi',              // = Hasil POD Pembanding (label UI)
  cPOD: 'Link POD Pembanding', cCatatan: 'Catatan CS',
  cTime: 'Timestamp Update', cBy: 'Diupdate Oleh',

  /**
   * SATU status saja. "Sedang Retur" lalu "Retur" sudah dilepas — CS hanya
   * mengerjakan paket yang masih dalam perjalanan dan masih bisa diselamatkan.
   * Catatan: kosakata Hasil Konfirmasi yang menyebut "retur/cancel" TETAP ada —
   * itu jawaban konsumen atas klaim kurir, bukan status paket dari J&T.
   */
  statusEkspedisi: ['Sedang Diantar'],

  // (2) Status Followup — proses kerja CS
  statusFollowup: ['Belum Followup', 'Dalam Proses', 'No Respon', 'Tidak Dapat Dihubungi', 'Selesai'],

  // (3) Hasil POD Pembanding — fakta dari konsumen
  hasilPOD: ['',
    'Penerima siap menerima paket',
    'Penerima minta jadwal tertentu',
    'Penerima belum dihubungi kurir',
    'Penerima membantah minta retur (klaim kurir tidak benar)',
    'Penerima konfirmasi minta retur/cancel',
    'Penerima sudah menerima paket',
    'Penerima belum siap bayar COD',
    'Alamat diperbaiki penerima',
    'Penerima tidak dapat dihubungi CS',
    'Perlu eskalasi ke ekspedisi'
  ],

  // hasil yang menandakan KLAIM KURIR TIDAK VALID (indikasi kecurangan)
  hasilKlaimTidakValid: [
    'Penerima membantah minta retur (klaim kurir tidak benar)',
    'Penerima belum dihubungi kurir'
  ],
  // hasil yang mengonfirmasi retur memang permintaan konsumen
  hasilReturValid: ['Penerima konfirmasi minta retur/cancel'],

  // hasil yang berarti paket BERPELUANG SELAMAT (nilai produk terselamatkan)
  hasilSelamat: [
    'Penerima siap menerima paket',
    'Penerima minta jadwal tertentu',
    'Penerima sudah menerima paket',
    'Penerima membantah minta retur (klaim kurir tidak benar)',
    'Alamat diperbaiki penerima'
  ],
  // hasil yang berarti paket KEMUNGKINAN HILANG (retur/cancel)
  hasilHilang: ['Penerima konfirmasi minta retur/cancel'],

  reportDays: 14,          // panjang grafik tren followup harian

  pageSizes: [25, 50, 100, 200],
  defaultPageSize: 25,
  maxPageSize: 200
};

// ---------------------------------------------------------------------------
// (1) KATEGORI MASALAH — klaim dari ekspedisi / kurir
//
// PENTING: daftar di bawah hanya BENIH untuk pemasangan awal.
// Begitu fitur "Tracking J&T" di Sistem 1 dijalankan, sheet Ref_Kategori_Masalah
// DISUSUN ULANG dari klaim asli yang tercatat di sistem J&T (field remark1) —
// mis. "Penerima menolak menerima paket", "Reschedule waktu pengiriman",
// "TLC Salah, sehingga paket salah sortir" — beserta kode resminya (7c, 31i,
// PT013, …) dan jumlah resi yang mengalaminya.
//
// Kenapa: daftar ini dulu disusun manual di awal proyek — tebakan. Sekarang kita
// punya klaim asli ekspedisi, jadi dropdown CS memakai kata-kata yang PERSIS SAMA
// dengan catatan J&T. Waktu CS mendebat klaim kurir, istilahnya cocok dan tidak
// bisa diperdebatkan.
//
// Jangan mengedit daftar ini untuk menambah kategori baru — biarkan datang dari
// lapangan lewat Sistem 1.
// ---------------------------------------------------------------------------
var KATEGORI_ROWS = [
  ['Belum ada klaim masalah dari ekspedisi', 'Paket berjalan normal — CS konfirmasi kesiapan terima'],
  ['Lainnya',                                'Kasus di luar daftar — jelaskan di Catatan CS']
];

// Template pesan — ringkas, tanpa perkenalan diri. Kategori = klaim ekspedisi.
var TEMPLATE_ROWS = [
  ['Paket sedang diantar (belum ada masalah)', 'Paket siap diantar (COD)',
   'Halo Kak {Penerima} 🙏 Paket {Nama Barang} (resi {No. Waybill}) sedang diantar ke alamat Kakak. Apakah Kakak ada di lokasi dan siap menerima? Mohon disiapkan pembayaran COD Rp {Nilai COD}. Terima kasih 🙏'],

  ['Paket sedang diantar (belum ada masalah)', 'Paket siap diantar (Non-COD)',
   'Halo Kak {Penerima} 🙏 Paket {Nama Barang} (resi {No. Waybill}) sedang diantar ke alamat Kakak. Apakah Kakak ada di lokasi dan siap menerima hari ini? Terima kasih 🙏'],

  ['Paket sedang diantar (belum ada masalah)', 'Minta jadwal pengantaran',
   'Halo Kak {Penerima} 🙏 Paket resi {No. Waybill} siap diantar. Kapan waktu Kakak ada di lokasi? Mohon infokan agar kurir bisa mengantar tepat waktu.'],

  ['Kurir klaim penerima minta cancel/retur', 'Verifikasi permintaan cancel/retur',
   'Halo Kak {Penerima} 🙏 Ada laporan bahwa paket {Nama Barang} (resi {No. Waybill}) diminta dibatalkan/retur. Apakah benar Kakak yang meminta? Jika tidak, akan kami antar ulang ya Kak.'],

  ['Kurir klaim penerima tidak di lokasi', 'Atur ulang jadwal antar',
   'Halo Kak {Penerima} 🙏 Kurir sudah mencoba mengantar paket resi {No. Waybill}, tapi Kakak belum ada di lokasi. Kapan waktu terbaik untuk diantar ulang?'],

  ['Kurir klaim penerima tidak merespons', 'Minta konfirmasi',
   'Halo Kak {Penerima} 🙏 Paket resi {No. Waybill} menunggu konfirmasi Kakak. Apakah sudah dihubungi kurir? Mohon dibalas agar paket tidak dikembalikan.'],

  ['Kurir klaim alamat tidak ditemukan', 'Minta alamat lengkap',
   'Halo Kak {Penerima} 🙏 Kurir kesulitan menemukan alamat untuk paket resi {No. Waybill}. Boleh dibantu alamat lengkap + patokan, atau share lokasi? Terima kasih 🙏'],

  ['Kurir klaim penerima menolak bayar COD', 'Konfirmasi kesiapan dana',
   'Halo Kak {Penerima} 🙏 Paket resi {No. Waybill} dengan COD Rp {Nilai COD} siap diantar. Apakah dananya sudah siap? Kalau butuh waktu, kami atur ulang jadwalnya.'],

  ['Kurir klaim paket sudah diterima', 'Verifikasi penerimaan paket',
   'Halo Kak {Penerima} 🙏 Paket resi {No. Waybill} tercatat sudah diterima. Apakah benar Kakak sudah menerimanya? Jika belum, mohon infokan agar kami telusuri.'],

  ['Ekspedisi mencatat paket ditahan/ditolak bea cukai', 'Info paket tertahan',
   'Halo Kak {Penerima} 🙏 Paket resi {No. Waybill} sedang tertahan pemeriksaan. Kami sedang mengurusnya dan akan kabari perkembangannya. Mohon ditunggu ya Kak.'],

  ['Ekspedisi mencatat barang rusak atau hilang', 'Info kendala paket',
   'Halo Kak {Penerima} 🙏 Mohon maaf, paket resi {No. Waybill} mengalami kendala dalam pengiriman. Kami sedang menelusuri dan akan segera kabari solusinya ya Kak.']
];

function getSS2() { return SpreadsheetApp.openById(CFG2.spreadsheetId); }

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('CS Undelivered — Followup (Meika Berkarya)')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Cek versi — SENGAJA seringan mungkin (tanpa buka spreadsheet / cek user),
    karena dipanggil berkala oleh halaman yang sedang terbuka. */
function getVersi() { return APP_VERSION; }

/** URL web app aktif — untuk memuat ulang halaman ke versi terbaru. */
function getWebAppUrl() {
  try { return ScriptApp.getService().getUrl(); } catch (e) { return ''; }
}

// ---------------------------------------------------------------------------
// DIAGNOSTIK
// ---------------------------------------------------------------------------
function cekAkses() {
  var out = [];
  var email = '';
  try { email = Session.getActiveUser().getEmail(); } catch (e) {}
  out.push('Login sebagai : ' + (email || '(tidak terbaca)'));
  try { out.push('Spreadsheet  : OK — ' + getSS2().getName()); }
  catch (e) { out.push('Spreadsheet  : GAGAL — ' + e.message); }
  try { out.push('Folder POD   : OK — ' + DriveApp.getFolderById(CFG2.podFolderId).getName()); }
  catch (e) {
    out.push('Folder POD   : GAGAL — ' + e.message);
    out.push('  → (a) podFolderId benar? (b) folder di-share ke akun ini sbg Editor?');
    out.push('  → (c) appsscript.json memuat scope "https://www.googleapis.com/auth/drive"?');
  }
  var msg = out.join('\n');
  Logger.log(msg);
  return msg;
}
function getPodFolder_() {
  try { return DriveApp.getFolderById(CFG2.podFolderId); }
  catch (e) {
    throw new Error('Folder POD tidak dapat diakses. Pastikan ID folder benar, folder di-share ke akun Anda ' +
      'sebagai Editor, dan script punya izin penuh Drive. Jalankan cekAkses() untuk detail.');
  }
}

// ---------------------------------------------------------------------------
// SETUP REFERENSI
// ---------------------------------------------------------------------------
function setup2() {
  var ss = getSS2();
  if (!ss.getSheetByName(CFG2.katSheet)) writeKategori_(ss);
  if (!ss.getSheetByName(CFG2.tplSheet)) writeTemplate_(ss);
  return 'Setup Sistem 2 selesai.';
}
function resetRefs2() {
  var ss = getSS2();
  writeKategori_(ss);
  writeTemplate_(ss);
  return 'Ref_Kategori_Masalah & Ref_Template_Pesan diperbarui.';
}
function writeKategori_(ss) {
  var sh = ss.getSheetByName(CFG2.katSheet) || ss.insertSheet(CFG2.katSheet);
  sh.clear();
  sh.getRange(1, 1, 1, 2).setValues([['Kategori', 'Keterangan']]);
  sh.getRange(2, 1, KATEGORI_ROWS.length, 2).setValues(KATEGORI_ROWS);
  sh.setFrozenRows(1); sh.setColumnWidth(1, 330); sh.setColumnWidth(2, 460);
}
function writeTemplate_(ss) {
  var sh = ss.getSheetByName(CFG2.tplSheet) || ss.insertSheet(CFG2.tplSheet);
  sh.clear();
  sh.getRange(1, 1, 1, 3).setValues([['Kategori', 'Judul', 'Isi Pesan']]);
  sh.getRange(2, 1, TEMPLATE_ROWS.length, 3).setValues(TEMPLATE_ROWS);
  sh.setFrozenRows(1); sh.setColumnWidth(1, 300); sh.setColumnWidth(3, 620);
}

// ---------------------------------------------------------------------------
// IDENTITAS & AKSES
// ---------------------------------------------------------------------------
function me_() {
  var email = '';
  try { email = (Session.getActiveUser().getEmail() || '').trim(); } catch (e) {}
  if (!email) {
    throw new Error('Tidak bisa mengenali akun Google Anda. Pastikan web app di-deploy dengan ' +
      '"Execute as: User accessing the web app" dan Anda sudah login akun Google.');
  }
  var u = loadUsers2(getSS2()).map[email.toLowerCase()];
  if (!u) throw new Error('Akun ' + email + ' belum terdaftar. Minta supervisor menambahkan Anda di panel "Kelola CS & Wilayah".');
  if (!u.aktif) throw new Error('Akun Anda berstatus nonaktif. Hubungi supervisor.');

  var isSuper = String(u.peran).toLowerCase() === 'superadmin';
  var provs = [];
  if (!isSuper) {
    provs = loadAssign2(getSS2()).list
      .filter(function (x) { return x.email.toLowerCase() === email.toLowerCase(); })
      .map(function (x) { return x.provinsi; });
  }
  return { email: email, nama: u.nama || email, peran: u.peran, isSuper: isSuper, provinces: provs };
}

function getMe() {
  var m = me_();
  var ss = getSS2();
  var csList = [];
  if (m.isSuper) {
    csList = loadUsers2(ss).list
      .filter(function (u) { return String(u.peran).toLowerCase() !== 'superadmin'; })
      .map(function (u) { return u.nama || u.email; });
  }
  return {
    email: m.email, nama: m.nama, peran: m.peran, isSuper: m.isSuper, provinces: m.provinces,
    versi: APP_VERSION,
    statusEkspedisi: CFG2.statusEkspedisi,
    statusFollowup:  CFG2.statusFollowup,
    hasilPOD:        CFG2.hasilPOD,
    hasilKlaimTidakValid: CFG2.hasilKlaimTidakValid,
    kategori:  loadKategori(ss),
    templates: loadTemplates(ss),
    csList: csList,
    pageSizes: CFG2.pageSizes,
    defaultPageSize: CFG2.defaultPageSize
  };
}

function assertOwn_(m, provinsi) {
  if (m.isSuper) return;
  var p = String(provinsi || '').trim().toLowerCase();
  var ok = m.provinces.some(function (x) { return String(x).trim().toLowerCase() === p; });
  if (!ok) throw new Error('Resi ini di luar wilayah tanggung jawab Anda.');
}

/** Normalisasi status followup lama ('' atau 'Belum') -> 'Belum Followup'. */
function normFu_(v) {
  var s = String(v || '').trim();
  if (s === '' || s === 'Belum') return 'Belum Followup';
  return s;
}

// ---------------------------------------------------------------------------
// WORKLIST (paginated)
// ---------------------------------------------------------------------------
function getWorklist(filter) {
  filter = filter || {};
  var m = me_();
  var sh = getSS2().getSheetByName(CFG2.masterSheet);

  var counts = { 'Semua': 0 };
  CFG2.statusEkspedisi.forEach(function (s) { counts[s] = 0; });

  var pageSize = parseInt(filter.pageSize, 10) || CFG2.defaultPageSize;
  if (pageSize < 1) pageSize = CFG2.defaultPageSize;
  if (pageSize > CFG2.maxPageSize) pageSize = CFG2.maxPageSize;
  var page = parseInt(filter.page, 10) || 1;
  if (page < 1) page = 1;

  if (!sh || sh.getLastRow() < 2) {
    return { rows: [], total: 0, page: 1, pageSize: pageSize, totalPages: 1, counts: counts, from: 0, to: 0 };
  }

  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();

  var iKey = header.indexOf(CFG2.keyCol), iProv = header.indexOf(CFG2.provinceCol);
  var iSt = header.indexOf(CFG2.statusCol), iFu = header.indexOf(CFG2.cFU);
  var iKat = header.indexOf(CFG2.cKat), iPic = header.indexOf(CFG2.cPIC);
  var iShip = header.indexOf(CFG2.shipDateCol);
  var iPen = header.indexOf('Penerima'), iTel = header.indexOf('Telepon Penerima');
  var iCod = header.indexOf(CFG2.codCol), iOng = header.indexOf(CFG2.ongkirCol);
  var iCodFlag = header.indexOf(CFG2.codFlagCol), iPod = header.indexOf(CFG2.cPOD);
  var iHasil = header.indexOf(CFG2.cHasil);
  // kolom hasil tracking J&T (diisi Sistem 1; bisa belum ada kalau belum pernah dijalankan)
  var iLab = header.indexOf('Label Tracking'), iAls = header.indexOf('Alasan Tertunda');
  var iWkt = header.indexOf('Waktu Tracking'), iKet = header.indexOf('Keterangan Tracking');
  var iPos = header.indexOf('Posisi Terakhir'), iKur = header.indexOf('Kurir Terakhir');
  var iFoto = header.indexOf('Foto Kurir');
  var iFotoDrive = header.indexOf('Foto Kurir Drive');

  var mine = {};
  m.provinces.forEach(function (p) { mine[String(p).trim().toLowerCase()] = 1; });

  var q    = String(filter.q || '').trim().toLowerCase();
  var fEks = String(filter.statusEks || '').trim();
  var fFu  = String(filter.statusFu || '').trim();
  var fKat = String(filter.kategori || '').trim();
  var fPic = String(filter.pic || '').trim();
  var fLab = String(filter.label || '').trim();      // filter label tracking J&T

  var TANPA_KAT = '(Belum ada kategori)';             // label untuk resi tanpa kategori
  var labelSet = {};

  // --- Pass 1: kumpulkan SCOPE = filter yang selalu aktif (wilayah + cari +
  //     label + PIC). Sub-tab status & sidebar kategori TIDAK diterapkan di sini,
  //     supaya angka tiap tab/kategori mencerminkan pilihan facet yang lain. ---
  var scope = [];   // {r, fu, kat, st}
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var prov = String(row[iProv] || '').trim();
    if (!m.isSuper && !mine[prov.toLowerCase()]) continue;

    var pic = iPic >= 0 ? String(row[iPic] || '').trim() : '';
    var lab = iLab >= 0 ? String(row[iLab] || '').trim() : '';
    if (lab) labelSet[lab] = 1;
    if (fPic && pic !== fPic) continue;
    if (fLab) { if (fLab === '__kosong' ? !!lab : lab !== fLab) continue; }
    if (q) {
      var hay = (String(row[iKey]) + ' ' + String(iPen >= 0 ? row[iPen] : '') + ' ' +
                 String(iTel >= 0 ? row[iTel] : '') + ' ' + prov).toLowerCase();
      if (hay.indexOf(q) < 0) continue;
    }
    scope.push({ r: r, fu: normFu_(row[iFu]),
                 kat: String(row[iKat] || '').trim(), st: String(row[iSt] || '').trim() });
  }

  // --- Angka tab utama (Semua + tiap status ekspedisi) atas SCOPE ---
  scope.forEach(function (s) {
    counts['Semua']++; if (counts.hasOwnProperty(s.st)) counts[s.st]++;
  });

  // --- Di dalam tab status ekspedisi terpilih (mis. "Sedang Diantar") ---
  var eks = scope.filter(function (s) { return !fEks || s.st === fEks; });
  var cocokKat = function (kat) {
    if (!fKat) return true;
    if (fKat === '__tanpa') return !kat;
    return kat === fKat;
  };

  // Sub-tab status followup: hitung per status, hormati filter kategori (bukan fFu).
  var countsFu = {}; CFG2.statusFollowup.forEach(function (s) { countsFu[s] = 0; });
  eks.forEach(function (s) { if (cocokKat(s.kat) && countsFu.hasOwnProperty(s.fu)) countsFu[s.fu]++; });

  // Sidebar kategori: hitung per kategori, hormati filter status followup (bukan fKat).
  var katCount = {};
  eks.forEach(function (s) {
    if (fFu && s.fu !== fFu) return;
    var k = s.kat || TANPA_KAT;
    katCount[k] = (katCount[k] || 0) + 1;
  });
  var kategoriOptions = Object.keys(katCount).sort(function (a, b) {
    if (a === TANPA_KAT) return 1; if (b === TANPA_KAT) return -1;   // "tanpa kategori" di bawah
    return katCount[b] - katCount[a];                                 // terbanyak di atas
  }).map(function (k) {
    return { kategori: k, value: (k === TANPA_KAT ? '__tanpa' : k), n: katCount[k] };
  });

  // --- Daftar akhir: terapkan status followup + kategori, lalu paginasi ---
  var matched = eks.filter(function (s) {
    return (!fFu || s.fu === fFu) && cocokKat(s.kat);
  }).map(function (s) { return s.r; });

  var total = matched.length;
  var totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (page > totalPages) page = totalPages;
  var start = (page - 1) * pageSize;
  var slice = matched.slice(start, start + pageSize);

  var out = slice.map(function (r) {
    var row = data[r];
    var cod = num_(iCod >= 0 ? row[iCod] : '');
    var ong = num_(iOng >= 0 ? row[iOng] : '');
    var hasil = iHasil >= 0 ? String(row[iHasil] || '').trim() : '';
    var o = {
      key: String(row[iKey]),
      provinsi: String(row[iProv] || '').trim(),
      status: String(row[iSt] || '').trim(),
      followup: normFu_(row[iFu]),
      hasil: hasil,
      flagTidakValid: CFG2.hasilKlaimTidakValid.indexOf(hasil) >= 0,
      tanggal: fmt_(row[iShip]),
      nilaiCOD: cod, totalBiaya: ong,
      nilaiProduk: (cod === '' || ong === '') ? '' : (cod - ong),
      isCod: isCod_(iCodFlag >= 0 ? row[iCodFlag] : '', cod),
      pods: splitPods_(iPod >= 0 ? row[iPod] : ''),
      // hasil tracking J&T terakhir — apa yang SEBENARNYA dicatat ekspedisi
      trkLabel:  iLab >= 0 ? String(row[iLab] || '').trim() : '',
      trkAlasan: iAls >= 0 ? String(row[iAls] || '').trim() : '',
      trkWaktu:  iWkt >= 0 ? String(row[iWkt] || '').trim() : '',
      trkKet:    iKet >= 0 ? String(row[iKet] || '').trim() : '',
      trkPosisi: iPos >= 0 ? String(row[iPos] || '').trim() : '',
      trkKurir:  iKur >= 0 ? String(row[iKur] || '').trim() : '',
      // Foto bukti dari kurir. Ini bahan sengketa paling kuat yang kita punya:
      // CS bisa melihat sendiri apa yang difoto kurir saat mengaku gagal antar.
      // Dua versi: Drive = permanen; jmsfile = asli J&T tapi kedaluwarsa ~24 jam.
      trkFoto:      iFoto >= 0 ? String(row[iFoto] || '').trim() : '',
      trkFotoDrive: iFotoDrive >= 0 ? String(row[iFotoDrive] || '').trim() : ''
    };
    CFG2.showCols.forEach(function (c) { var i = header.indexOf(c); o[c] = (i >= 0) ? fmt_(row[i]) : ''; });
    [CFG2.cKat, CFG2.cCatatan, CFG2.cPIC, CFG2.cTime, CFG2.cBy].forEach(function (c) {
      var i = header.indexOf(c); o[c] = (i >= 0) ? fmt_(row[i]) : '';
    });
    return o;
  });

  return { rows: out, total: total, page: page, pageSize: pageSize, totalPages: totalPages,
           counts: counts, from: total ? start + 1 : 0, to: start + out.length,
           labelOptions: Object.keys(labelSet).sort(),
           // sub-tab status followup + sidebar kategori (dengan jumlah masing-masing)
           statusFollowup: CFG2.statusFollowup,
           countsFu: countsFu,
           kategoriOptions: kategoriOptions };
}

function isCod_(flag, nilaiCod) {
  var f = String(flag || '').trim().toUpperCase();
  if (f) {
    if (f.indexOf('NON') >= 0) return false;
    if (f.indexOf('COD') >= 0) return true;
  }
  return (nilaiCod !== '' && Number(nilaiCod) > 0);
}

// ---------------------------------------------------------------------------
// SIMPAN FOLLOWUP
// ---------------------------------------------------------------------------
function saveFollowup(p) {
  var m = me_();
  var key = String(p.key || '').trim();
  if (!key) throw new Error('No. Waybill kosong.');

  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS2().getSheetByName(CFG2.masterSheet);
    var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var rowNum = findRow_(sh, header, key);
    if (rowNum < 0) throw new Error('Resi ' + key + ' tidak ditemukan.');
    assertOwn_(m, sh.getRange(rowNum, header.indexOf(CFG2.provinceCol) + 1).getValue());

    var up = {};
    up[CFG2.cKat]     = String(p.kategori || '');   // (1) klaim ekspedisi
    up[CFG2.cFU]      = normFu_(p.followup);        // (2) proses CS
    up[CFG2.cHasil]   = String(p.hasil || '');      // (3) hasil POD pembanding
    up[CFG2.cCatatan] = String(p.catatan || '');
    up[CFG2.cTime]    = new Date();
    up[CFG2.cBy]      = m.email;

    updateCells_(sh, rowNum, header, up);
    log2_('Followup', key + ' | klaim: ' + up[CFG2.cKat] + ' | status: ' + up[CFG2.cFU] +
                      ' | hasil: ' + up[CFG2.cHasil]);
    clearReportCache_(m.email);
    return { ok: true };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// FOTO POD PEMBANDING (MULTI)
// ---------------------------------------------------------------------------
function addPod(key, b64, filename, mimeType) {
  var m = me_();
  key = String(key || '').trim();
  if (!key) throw new Error('No. Waybill kosong.');
  if (!b64) throw new Error('File kosong.');

  var sh = getSS2().getSheetByName(CFG2.masterSheet);
  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var rowNum = findRow_(sh, header, key);
  if (rowNum < 0) throw new Error('Resi ' + key + ' tidak ditemukan.');
  var prov = String(sh.getRange(rowNum, header.indexOf(CFG2.provinceCol) + 1).getValue() || '').trim();
  assertOwn_(m, prov);

  var root = getPodFolder_();
  var f1 = childFolder_(root, prov || 'Tanpa Provinsi');
  var f2 = childFolder_(f1, Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM'));

  var stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd_HHmmss');
  var ext = (String(filename || '').match(/\.([a-zA-Z0-9]+)$/) || [, 'jpg'])[1];
  var blob = Utilities.newBlob(Utilities.base64Decode(b64), mimeType || 'image/jpeg',
                               key + '_' + stamp + '_' + Math.floor(Math.random() * 1000) + '.' + ext);
  var url = f2.createFile(blob).getUrl();

  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var iPod = header.indexOf(CFG2.cPOD);
    var cur = splitPods_(sh.getRange(rowNum, iPod + 1).getValue());
    cur.push(url);
    var up = {};
    up[CFG2.cPOD] = cur.join('\n'); up[CFG2.cTime] = new Date(); up[CFG2.cBy] = m.email;
    updateCells_(sh, rowNum, header, up);
    log2_('Tambah POD Pembanding', key);
    clearReportCache_(m.email);
    return { ok: true, url: url, pods: cur };
  } finally { lock.releaseLock(); }
}

function removePod(key, url) {
  var m = me_();
  key = String(key || '').trim(); url = String(url || '').trim();
  if (!key || !url) throw new Error('Data tidak lengkap.');

  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS2().getSheetByName(CFG2.masterSheet);
    var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var rowNum = findRow_(sh, header, key);
    if (rowNum < 0) throw new Error('Resi ' + key + ' tidak ditemukan.');
    assertOwn_(m, sh.getRange(rowNum, header.indexOf(CFG2.provinceCol) + 1).getValue());

    var iPod = header.indexOf(CFG2.cPOD);
    var keep = splitPods_(sh.getRange(rowNum, iPod + 1).getValue())
      .filter(function (u) { return u !== url; });

    var up = {};
    up[CFG2.cPOD] = keep.join('\n'); up[CFG2.cTime] = new Date(); up[CFG2.cBy] = m.email;
    updateCells_(sh, rowNum, header, up);
    try {
      var id = (url.match(/\/d\/([^\/\?]+)/) || [])[1];
      if (id) DriveApp.getFileById(id).setTrashed(true);
    } catch (e) {}
    log2_('Hapus POD Pembanding', key);
    clearReportCache_(m.email);
    return { ok: true, pods: keep };
  } finally { lock.releaseLock(); }
}

function splitPods_(v) {
  if (v === null || v === undefined || v === '') return [];
  return String(v).split(/[\n,;\s]+/).map(function (s) { return s.trim(); })
    .filter(function (s) { return s.indexOf('http') === 0; });
}

// ---------------------------------------------------------------------------
// REPORT
// ---------------------------------------------------------------------------
function getReport() {
  var m = me_();
  var cache = CacheService.getScriptCache();
  var ck = 'rep5_' + m.email;
  var hit = cache.get(ck); if (hit) return JSON.parse(hit);

  var tz = Session.getScriptTimeZone();
  var today = new Date();
  var todayStr = Utilities.formatDate(today, tz, 'yyyy-MM-dd');
  var users = loadUsers2(getSS2());

  var out = {
    isSuper: m.isSuper, nama: m.nama, tanggal: todayStr,
    total: 0, belum: 0, dalamProses: 0, selesai: 0, pctSelesai: 0,
    podCount: 0, pctPod: 0,
    klaimTidakValid: 0, returTerkonfirmasi: 0, terverifikasi: 0, pctTidakValid: 0,
    nilaiCOD: 0, nilaiProduk: 0, nilaiSelamat: 0, nilaiHilang: 0,
    codCount: 0, nonCodCount: 0,
    byStatus: {}, byFollowup: {}, byKategori: {}, byHasil: {}, byProvinsi: {},
    aging: { '0–1 hari': 0, '2–3 hari': 0, '4–7 hari': 0, '> 7 hari': 0 },
    daily: [], todayCount: 0, week7Count: 0, avgPerDay: 0,
    perCS: []
  };

  // ---------- 1) rekap dari MASTER ----------
  var sh = getSS2().getSheetByName(CFG2.masterSheet);
  var picStat = {};  // nama CS -> {total,belum,selesai,pod}
  if (sh && sh.getLastRow() > 1) {
    var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    var iProv = header.indexOf(CFG2.provinceCol), iSt = header.indexOf(CFG2.statusCol);
    var iFu = header.indexOf(CFG2.cFU), iKat = header.indexOf(CFG2.cKat);
    var iPod = header.indexOf(CFG2.cPOD), iHasil = header.indexOf(CFG2.cHasil);
    var iPic = header.indexOf(CFG2.cPIC), iCodFlag = header.indexOf(CFG2.codFlagCol);
    var iCod = header.indexOf(CFG2.codCol), iOng = header.indexOf(CFG2.ongkirCol);
    var iUpd = header.indexOf('Tanggal Update Status'), iShip = header.indexOf(CFG2.shipDateCol);

    var mine = {}; m.provinces.forEach(function (p) { mine[String(p).trim().toLowerCase()] = 1; });

    data.forEach(function (row) {
      var prov = String(row[iProv] || '').trim();
      if (!m.isSuper && !mine[prov.toLowerCase()]) return;
      out.total++;

      var fu = normFu_(row[iFu]);
      out.byFollowup[fu] = (out.byFollowup[fu] || 0) + 1;
      if (fu === 'Belum Followup') out.belum++;
      else if (fu === 'Selesai') out.selesai++;
      else out.dalamProses++;

      var st = String(row[iSt] || '').trim() || '(kosong)';
      out.byStatus[st] = (out.byStatus[st] || 0) + 1;

      var kat = String(row[iKat] || '').trim();
      if (kat) out.byKategori[kat] = (out.byKategori[kat] || 0) + 1;

      var cod = num_(iCod >= 0 ? row[iCod] : '');
      var ong = num_(iOng >= 0 ? row[iOng] : '');
      var produk = (cod === '' || ong === '') ? 0 : (cod - ong);
      out.nilaiCOD += (cod === '' ? 0 : cod);
      out.nilaiProduk += produk;

      var hs = iHasil >= 0 ? String(row[iHasil] || '').trim() : '';
      if (hs) {
        out.byHasil[hs] = (out.byHasil[hs] || 0) + 1;
        out.terverifikasi++;
        if (CFG2.hasilKlaimTidakValid.indexOf(hs) >= 0) out.klaimTidakValid++;
        if (CFG2.hasilReturValid.indexOf(hs) >= 0) out.returTerkonfirmasi++;
        if (CFG2.hasilSelamat.indexOf(hs) >= 0) out.nilaiSelamat += produk;
        if (CFG2.hasilHilang.indexOf(hs) >= 0) out.nilaiHilang += produk;
      }

      var hasPod = splitPods_(iPod >= 0 ? row[iPod] : '').length > 0;
      if (hasPod) out.podCount++;

      if (isCod_(iCodFlag >= 0 ? row[iCodFlag] : '', cod)) out.codCount++; else out.nonCodCount++;
      out.byProvinsi[prov || '(kosong)'] = (out.byProvinsi[prov || '(kosong)'] || 0) + 1;

      // aging: hanya resi yang BELUM difollowup
      if (fu === 'Belum Followup') {
        var base = toDate_(iUpd >= 0 ? row[iUpd] : '') || toDate_(iShip >= 0 ? row[iShip] : '');
        var d = base ? Math.floor((today - base) / 86400000) : 0;
        if (d <= 1) out.aging['0–1 hari']++;
        else if (d <= 3) out.aging['2–3 hari']++;
        else if (d <= 7) out.aging['4–7 hari']++;
        else out.aging['> 7 hari']++;
      }

      // per CS
      var pic = iPic >= 0 ? String(row[iPic] || '').trim() : '';
      if (pic) {
        if (!picStat[pic]) picStat[pic] = { nama: pic, total: 0, belum: 0, selesai: 0, pod: 0, today: 0, week7: 0 };
        picStat[pic].total++;
        if (fu === 'Belum Followup') picStat[pic].belum++;
        if (fu === 'Selesai') picStat[pic].selesai++;
        if (hasPod) picStat[pic].pod++;
      }
    });
  }

  out.pctSelesai     = out.total ? Math.round(out.selesai / out.total * 100) : 0;
  out.pctPod         = out.total ? Math.round(out.podCount / out.total * 100) : 0;
  out.pctTidakValid  = out.terverifikasi ? Math.round(out.klaimTidakValid / out.terverifikasi * 100) : 0;

  // ---------- 2) produktivitas harian (dari Log_Aktivitas) ----------
  var days = CFG2.reportDays;
  var since = new Date(today.getTime() - (days - 1) * 86400000);
  since.setHours(0, 0, 0, 0);

  var log = loadFollowupLog_(since, tz);                 // [{d, email, key}]
  var seen = {}, perDay = {}, perCSDay = {};
  log.forEach(function (e) {
    if (!m.isSuper && e.email !== m.email.toLowerCase()) return;   // CS: hanya miliknya
    var uk = e.d + '|' + e.email + '|' + e.key;
    if (seen[uk]) return;                                // 1 resi/CS/hari dihitung sekali
    seen[uk] = 1;
    perDay[e.d] = (perDay[e.d] || 0) + 1;
    var nama = (users.map[e.email] && users.map[e.email].nama) || e.email;
    if (!perCSDay[nama]) perCSDay[nama] = {};
    perCSDay[nama][e.d] = (perCSDay[nama][e.d] || 0) + 1;
  });

  // fallback: kalau log belum ada isinya, pakai Timestamp Update sebagai perkiraan
  if (!Object.keys(perDay).length) {
    var approx = approxDailyFromMaster_(m, since, tz);
    perDay = approx.perDay; perCSDay = approx.perCSDay;
    out.dailySumber = 'perkiraan (dari Timestamp Update)';
  } else {
    out.dailySumber = 'log aktivitas';
  }

  var total7 = 0;
  for (var i = days - 1; i >= 0; i--) {
    var dt = new Date(today.getTime() - i * 86400000);
    var ds = Utilities.formatDate(dt, tz, 'yyyy-MM-dd');
    var c = perDay[ds] || 0;
    out.daily.push({ d: ds, label: Utilities.formatDate(dt, tz, 'dd/MM'), n: c });
    if (i <= 6) total7 += c;
  }
  out.todayCount = perDay[todayStr] || 0;
  out.week7Count = total7;
  out.avgPerDay  = Math.round(total7 / 7 * 10) / 10;

  // gabungkan produktivitas ke tabel per CS
  Object.keys(perCSDay).forEach(function (nama) {
    if (!picStat[nama]) picStat[nama] = { nama: nama, total: 0, belum: 0, selesai: 0, pod: 0, today: 0, week7: 0 };
  });
  Object.keys(picStat).forEach(function (nama) {
    var dmap = perCSDay[nama] || {};
    picStat[nama].today = dmap[todayStr] || 0;
    var w = 0;
    for (var j = 0; j <= 6; j++) {
      var ds2 = Utilities.formatDate(new Date(today.getTime() - j * 86400000), tz, 'yyyy-MM-dd');
      w += (dmap[ds2] || 0);
    }
    picStat[nama].week7 = w;
    picStat[nama].pctSelesai = picStat[nama].total ? Math.round(picStat[nama].selesai / picStat[nama].total * 100) : 0;
  });
  out.perCS = Object.keys(picStat).map(function (k) { return picStat[k]; })
    .sort(function (a, b) { return b.total - a.total; });

  cache.put(ck, JSON.stringify(out), 120);
  return out;
}
function clearReportCache_(email) { try { CacheService.getScriptCache().remove('rep5_' + email); } catch (e) {} }

/** Ambil aksi "Followup" dari Log_Aktivitas sejak tanggal tertentu. */
function loadFollowupLog_(since, tz) {
  var sh = getSS2().getSheetByName(CFG2.logSheet);
  if (!sh || sh.getLastRow() < 2) return [];
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues();
  var out = [];
  data.forEach(function (r) {
    var t = r[0];
    if (!(t instanceof Date)) t = new Date(t);
    if (isNaN(t.getTime()) || t < since) return;
    if (String(r[2] || '').indexOf('Followup') < 0) return;
    var detail = String(r[3] || '');
    var key = (detail.split('|')[0] || '').trim();
    out.push({ d: Utilities.formatDate(t, tz, 'yyyy-MM-dd'),
               email: String(r[1] || '').trim().toLowerCase(), key: key });
  });
  return out;
}

/** Perkiraan produktivitas harian bila Log_Aktivitas masih kosong. */
function approxDailyFromMaster_(m, since, tz) {
  var perDay = {}, perCSDay = {};
  var sh = getSS2().getSheetByName(CFG2.masterSheet);
  if (!sh || sh.getLastRow() < 2) return { perDay: perDay, perCSDay: perCSDay };
  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var iProv = header.indexOf(CFG2.provinceCol), iTime = header.indexOf(CFG2.cTime), iPic = header.indexOf(CFG2.cPIC);
  var mine = {}; m.provinces.forEach(function (p) { mine[String(p).trim().toLowerCase()] = 1; });
  data.forEach(function (row) {
    var prov = String(row[iProv] || '').trim();
    if (!m.isSuper && !mine[prov.toLowerCase()]) return;
    var t = toDate_(iTime >= 0 ? row[iTime] : '');
    if (!t || t < since) return;
    var ds = Utilities.formatDate(t, tz, 'yyyy-MM-dd');
    perDay[ds] = (perDay[ds] || 0) + 1;
    var nama = iPic >= 0 ? String(row[iPic] || '').trim() : '';
    if (nama) {
      if (!perCSDay[nama]) perCSDay[nama] = {};
      perCSDay[nama][ds] = (perCSDay[nama][ds] || 0) + 1;
    }
  });
  return { perDay: perDay, perCSDay: perCSDay };
}

function toDate_(v) {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  var m2 = String(v).match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m2) return new Date(+m2[1], +m2[2] - 1, +m2[3]);
  var d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
}

// ---------------------------------------------------------------------------
// LOADERS & HELPERS
// ---------------------------------------------------------------------------
function loadUsers2(ss) {
  var sh = ss.getSheetByName(CFG2.usersSheet);
  var res = { list: [], map: {} };
  if (!sh || sh.getLastRow() < 2) return res;
  var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var ei = h.indexOf('Email'), ni = h.indexOf('Nama'), pi = h.indexOf('Peran'), ai = h.indexOf('Aktif');
  sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues().forEach(function (r) {
    var email = String(ei >= 0 ? r[ei] : '').trim(); if (!email) return;
    var a = ai >= 0 ? String(r[ai]).trim().toLowerCase() : '';
    var o = { email: email, nama: String(ni >= 0 ? r[ni] : '').trim(),
              peran: (String(pi >= 0 ? r[pi] : '').trim() || 'CS'),
              aktif: (a === '' || a === 'ya' || a === 'true' || a === 'aktif') };
    res.list.push(o); res.map[email.toLowerCase()] = o;
  });
  return res;
}
function loadAssign2(ss) {
  var sh = ss.getSheetByName(CFG2.mapSheet);
  var res = { list: [] };
  if (!sh || sh.getLastRow() < 2) return res;
  var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var pi = h.indexOf('Provinsi');
  var ei = h.indexOf('Email CS'); if (ei < 0) ei = h.indexOf('Email');
  sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues().forEach(function (r) {
    var prov = String(pi >= 0 ? r[pi] : '').trim();
    var email = String(ei >= 0 ? r[ei] : '').trim();
    if (prov && email) res.list.push({ provinsi: prov, email: email });
  });
  return res;
}
function loadKategori(ss) {
  var sh = ss.getSheetByName(CFG2.katSheet);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 1).getValues()
    .map(function (r) { return String(r[0] || '').trim(); })
    .filter(function (x) { return x !== ''; });
}
function loadTemplates(ss) {
  var sh = ss.getSheetByName(CFG2.tplSheet);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues()
    .filter(function (r) { return String(r[2] || '').trim() !== ''; })
    .map(function (r) {
      return { kategori: String(r[0] || '').trim(), judul: String(r[1] || '').trim(), isi: String(r[2] || '') };
    });
}
function findRow_(sh, header, key) {
  var kc = header.indexOf(CFG2.keyCol) + 1;
  if (kc < 1 || sh.getLastRow() < 2) return -1;
  var vals = sh.getRange(2, kc, sh.getLastRow() - 1, 1).getValues();
  var t = nk_(key);
  for (var i = 0; i < vals.length; i++) if (nk_(vals[i][0]) === t) return i + 2;
  return -1;
}
function updateCells_(sh, rowNum, header, updates) {
  var keys = Object.keys(updates).filter(function (k) { return header.indexOf(k) >= 0; });
  if (!keys.length) return;
  var idxs = keys.map(function (k) { return header.indexOf(k); });
  var minI = Math.min.apply(null, idxs), maxI = Math.max.apply(null, idxs);
  var rng = sh.getRange(rowNum, minI + 1, 1, maxI - minI + 1);
  var vals = rng.getValues()[0];
  keys.forEach(function (k) { vals[header.indexOf(k) - minI] = updates[k]; });
  rng.setValues([vals]);
}
function childFolder_(parent, name) {
  var it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : parent.createFolder(name);
}
function log2_(action, detail) {
  try {
    var sh = getSS2().getSheetByName(CFG2.logSheet);
    if (!sh) return;
    var email = '';
    try { email = Session.getActiveUser().getEmail() || ''; } catch (e) {}
    sh.appendRow([new Date(), email, action, detail]);
  } catch (e) {}
}
function nk_(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(/\s+/g, '').replace(/\.0$/, '');
}
function num_(v) {
  if (v === null || v === undefined || v === '') return '';
  var n = parseFloat(String(v).replace(/,/g, '').trim());
  return isNaN(n) ? '' : n;
}
function fmt_(v) {
  if (v === null || v === undefined) return '';
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return String(v);
}

// ===========================================================================
// EXPORT EXCEL (.xlsx)
//
// CS memilih filter (label tracking, status followup, kategori, provinsi) di
// modal -> file Excel langsung terunduh. HANYA resi di wilayah CS yang ikut;
// superadmin dapat semuanya. Batas wilayah ditegakkan di server, sama seperti
// worklist — filter provinsi di modal tidak bisa menembusnya.
// ===========================================================================
var EXPORT_COLS2 = [
  'No. Waybill', 'Tanggal Pengiriman', 'Penerima', 'Telepon Penerima',
  'Provinsi Penerima', 'Kota Penerima', 'Kecamatan Penerima', 'Alamat Penerima',
  'Nama Barang', 'COD/Non-COD', 'Nilai COD', 'Total Biaya', 'Nilai Produk',
  'Status Ekspedisi',
  'Label Tracking', 'Kode Tracking', 'Waktu Tracking', 'Keterangan Tracking',
  'Alasan Tertunda', 'Kode Alasan', 'Posisi Terakhir', 'Kurir Terakhir',
  'Foto Kurir (jmsfile)', 'Foto Kurir (Drive)', 'Cek Terakhir',
  'PIC CS', 'Kategori Masalah', 'Status Followup', 'Hasil POD Pembanding',
  'Jumlah Foto POD', 'Link POD Pembanding (Drive)', 'Catatan CS', 'Waktu Update', 'Diupdate Oleh'
];
var EXPORT_NUM_COLS2 = ['Nilai COD', 'Total Biaya', 'Nilai Produk', 'Jumlah Foto POD'];

/** Opsi dropdown modal export — hanya dari wilayah CS ini (superadmin: semua). */
function getExportOptions() {
  var m = me_();
  var sh = getSS2().getSheetByName(CFG2.masterSheet);
  var out = { label: [], followup: CFG2.statusFollowup, kategori: loadKategori(getSS2()),
              provinsi: [], isSuper: m.isSuper };
  if (!sh || sh.getLastRow() < 2) return out;

  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var iProv = header.indexOf(CFG2.provinceCol), iLab = header.indexOf('Label Tracking');
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();

  var mine = {}; m.provinces.forEach(function (p) { mine[String(p).trim().toLowerCase()] = 1; });
  var setL = {}, setP = {};
  data.forEach(function (row) {
    var prov = String(row[iProv] || '').trim();
    if (!m.isSuper && !mine[prov.toLowerCase()]) return;
    if (prov) setP[prov] = 1;
    var l = iLab >= 0 ? String(row[iLab] || '').trim() : '';
    if (l) setL[l] = 1;
  });
  out.label = Object.keys(setL).sort();
  out.provinsi = Object.keys(setP).sort();
  return out;
}

/** Export .xlsx semua resi (dalam wilayah) yang lolos filter. */
function exportExcel(filter) {
  filter = filter || {};
  var m = me_();
  var sh = getSS2().getSheetByName(CFG2.masterSheet);
  if (!sh || sh.getLastRow() < 2) throw new Error('Belum ada data untuk diexport.');

  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var ix = {}; header.forEach(function (h, i) { ix[h] = i; });
  var get = function (row, nm) { var i = ix[nm]; return i === undefined ? '' : row[i]; };

  var mine = {}; m.provinces.forEach(function (p) { mine[String(p).trim().toLowerCase()] = 1; });
  var fFu  = String(filter.followup || '').trim();
  var fKat = String(filter.kategori || '').trim();
  var fLab = String(filter.label || '').trim();
  var fProv = String(filter.provinsi || '').trim();

  var body = [];
  data.forEach(function (row) {
    var prov = String(get(row, CFG2.provinceCol) || '').trim();
    if (!m.isSuper && !mine[prov.toLowerCase()]) return;   // batas wilayah — tidak bisa ditembus
    if (fProv && prov !== fProv) return;

    var fu = normFu_(get(row, CFG2.cFU));
    if (fFu && fu !== fFu) return;
    if (fKat && String(get(row, CFG2.cKat) || '').trim() !== fKat) return;

    var lab = String(get(row, 'Label Tracking') || '').trim();
    if (fLab) { if (fLab === '__kosong' ? !!lab : lab !== fLab) return; }

    var cod = num_(get(row, CFG2.codCol)), ong = num_(get(row, CFG2.ongkirCol));
    var produk = (cod === '' || ong === '') ? '' : (cod - ong);
    var pods = splitPods_(get(row, CFG2.cPOD));
    body.push([
      String(get(row, CFG2.keyCol) || ''),
      fmt_(get(row, CFG2.shipDateCol)),
      String(get(row, 'Penerima') || ''),
      String(get(row, 'Telepon Penerima') || ''),
      prov,
      String(get(row, 'Kota Penerima') || ''),
      String(get(row, 'Kecamatan Penerima') || ''),
      String(get(row, 'Alamat Penerima') || ''),
      String(get(row, 'Nama Barang') || ''),
      isCod_(get(row, CFG2.codFlagCol), cod) ? 'COD' : 'Non-COD',
      cod === '' ? '' : cod,
      ong === '' ? '' : ong,
      produk,
      String(get(row, CFG2.statusCol) || ''),
      lab,
      String(get(row, 'Kode Tracking') || ''),
      String(get(row, 'Waktu Tracking') || ''),
      String(get(row, 'Keterangan Tracking') || ''),
      String(get(row, 'Alasan Tertunda') || ''),
      String(get(row, 'Kode Alasan') || ''),
      String(get(row, 'Posisi Terakhir') || ''),
      String(get(row, 'Kurir Terakhir') || ''),
      String(get(row, 'Foto Kurir') || ''),         // link jmsfile (~24 jam)
      String(get(row, 'Foto Kurir Drive') || ''),   // salinan permanen di Drive
      fmt_(get(row, 'Cek Terakhir')),
      String(get(row, CFG2.cPIC) || ''),
      String(get(row, CFG2.cKat) || ''),
      fu,
      String(get(row, CFG2.cHasil) || ''),
      pods.length,
      pods.join(' | '),
      String(get(row, CFG2.cCatatan) || ''),
      fmt_(get(row, CFG2.cTime)),
      String(get(row, CFG2.cBy) || '')
    ]);
  });

  var hasil = bikinXlsx_('Undelivered_' + (m.isSuper ? 'SemuaWilayah' : 'CS'), EXPORT_COLS2, body, EXPORT_NUM_COLS2);
  log2_('Export Excel', hasil.nama + ' | ' + body.length + ' baris');
  return hasil;
}

/**
 * Bangun file .xlsx: tulis ke spreadsheet SEMENTARA, minta Google export xlsx
 * lewat OAuth, ambil byte-nya, lalu spreadsheet sementara dibuang di 'finally'.
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
      .setFontWeight('bold').setBackground('#9E1B1B').setFontColor('#ffffff');
    sh.setFrozenRows(1);

    (numCols || []).forEach(function (nm) {
      var c = header.indexOf(nm);
      if (c >= 0 && rows.length) sh.getRange(2, c + 1, rows.length, 1).setNumberFormat('#,##0');
    });

    sh.setColumnWidths(1, header.length, 130);
    ['Alamat Penerima', 'Nama Barang', 'Keterangan Tracking', 'Alasan Tertunda',
     'Hasil POD Pembanding', 'Link POD Pembanding (Drive)', 'Catatan CS',
     'Foto Kurir (jmsfile)', 'Foto Kurir (Drive)'].forEach(function (nm) {
      var c = header.indexOf(nm);
      if (c >= 0) sh.setColumnWidth(c + 1, 260);
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
