/**
 * ============================================================================
 *  TRACKING J&T OTOMATIS — Sistem 1 (Supervisor, Meika Berkarya)
 *
 *  Mengambil label tracking TERBARU tiap resi berstatus "Sedang Diantar"
 *  langsung dari endpoint yang dipakai halaman jet.co.id/track.
 *
 *  ── SIFAT SEMENTARA ────────────────────────────────────────────────────────
 *  Ini SOLUSI SEMENTARA sampai API resmi J&T disetujui. Endpoint ini milik
 *  halaman publik mereka, ada Web Application Firewall (Huawei) di depannya,
 *  dan strukturnya bisa berubah sewaktu-waktu tanpa pemberitahuan. Karena itu:
 *    - jeda antar-permintaan dibuat sopan (TRK.jedaMs)
 *    - setiap kegagalan dicatat, tidak didiamkan
 *    - kalau 5 permintaan beruntun gagal, proses BERHENTI SENDIRI — supaya
 *      kita tidak menghantam server yang sedang menolak kita
 *  Begitu API resmi turun, cukup ganti isi lacak_() — sheet, kolom, dashboard,
 *  dan seluruh sistem lain tidak perlu diubah sama sekali.
 *
 *  ── CARA KERJA LATAR BELAKANG ─────────────────────────────────────────────
 *  Supervisor klik "Mulai" -> job ditandai jalan -> trigger berantai
 *  (lanjutRefreshTracking) mengerjakan sisanya di server Google. Halaman boleh
 *  ditutup; user tetap bisa upload/kelola CS seperti biasa. Progres dibaca
 *  ulang dari sheet, jadi tetap akurat walau halaman di-refresh.
 * ============================================================================
 */

var TRK = {
  /**
   * ENDPOINT VIP (jmsvipgw). Migrasi dari endpoint publik jet.co.id.
   * Alasan pindah:
   *   - responsnya memuat "traceItems[].imgUrl" = FOTO bukti kurir yang SUDAH
   *     bertanda tangan (endpoint publik hanya memberi path mentah -> AccessDenied),
   *   - auth-nya JWT (authToken) + device-no, lebih bersih daripada scrape pId/pst,
   *   - "codes" berupa array -> batch banyak resi sekali panggil.
   * Body:  {"type":1,"codes":["<billcode>", ...]}
   * Header wajib: authToken, device-no, language, routeName, content-type json.
   */
  apiUrl:  'https://jmsvipgw.jntexpress.id/jts-idn-gateway/yl-indonesia-vip-read/vipread/trace/list',
  origin:  'https://login-newvip.jet.co.id',
  language: 'in_ID',
  routeName: 'expressTracking',

  /**
   * Berapa resi per permintaan. "codes" jelas berupa array, jadi batch didukung.
   * Tetap mulai dari 1 dan JANGAN naikkan sebelum tesMultiResi() lolos — kalau
   * ternyata dibatasi, seluruh batch bisa gagal diam-diam.
   */
  resiPerRequest: 1,

  jedaMs:   1200,             // jeda antar permintaan (sopan, hindari rate-limit)
  budgetMs: 25 * 60 * 1000,   // Workspace: batas 30 menit/eksekusi -> sisakan margin

  /**
   * Cicil ke sheet tiap N resi. Kalau eksekusi mati mendadak, paling banyak
   * N-1 resi yang perlu diambil ulang — bukan seluruh pekerjaan.
   */
  flushTiap: 5,
  gagalBeruntunMaks: 5,

  /**
   * Cadangan terakhir kalau panel "Sesi Manual" di layar tidak dipakai.
   * Lebih baik pakai panelnya: tidak perlu ubah kode & tidak perlu deploy ulang.
   */
  authTokenManual: '',
  deviceNoManual: '',

  /**
   * Foto bukti kurir. Endpoint VIP mengembalikan URL yang SUDAH bertanda tangan
   * di "traceItems[].imgUrl" (AccessKeyId/Expires/Signature dibuat server J&T —
   * kita tidak punya secret-nya, jadi tidak bisa menandatangani sendiri).
   * URL itu KEDALUWARSA ~24 jam, jadi disegarkan tiap kali tracking dijalankan.
   * Kalau CS membuka foto yang sudah lewat 24 jam sejak run terakhir, link-nya
   * akan menolak — sinyal bahwa tracking perlu dijalankan ulang.
   */
  statusTarget: 'Sedang Diantar',
  ua: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
};

/**
 * Label J&T kadang lolos dalam bahasa Mandarin — istilah internal operasional
 * mereka yang tidak sempat diterjemahkan. Contoh nyata dari lapangan:
 * "留仓件", "派件中", bahkan gabungan "留仓件,派件中".
 *
 * Kalau dibiarkan, CS melihat aksara yang tidak bisa dibaca, dan yang lebih
 * buruk: sebaran label jadi pecah — "派件中" dihitung terpisah dari
 * "Sedang Diantar" padahal artinya sama. Statistik supervisor jadi bohong.
 *
 * BATAS PENGETAHUAN SAYA: hanya istilah di bawah ini yang saya yakini. Label
 * Mandarin lain SENGAJA tidak saya terka — teksnya dibiarkan apa adanya lalu
 * dilaporkan lewat log & labelBelumDikenal(), supaya diterjemahkan berdasarkan
 * kenyataan di portal J&T, bukan tebakan saya.
 */
var LABEL_CN = {
  // --- field "status" endpoint VIP (state paket) — dikonfirmasi dari respons nyata ---
  '停留中':   'Sedang Tertunda',          // code 110 (问题件) -> paket tertahan/bermasalah
  '派送中':   'Sedang Diantar Kurir',     // code 94  -> "Paket akan segera diantarkan…"
  '运输中':   'Dalam Perjalanan',         // code 50/92 -> transit antar gerai
  '已揽件':   'Sudah Diambil Kurir',      // code 10  -> "Paket telah diproses di … Drop Point"
  // --- field "scanTypeName" (jenis scan) — dikonfirmasi lebih awal dari endpoint publik ---
  '问题件':   'Sedang Tertunda',
  '派件':     'Sedang Diantar Kurir',     '派件中': 'Sedang Diantar Kurir',
  '到件':     'Tiba di Gerai',            // code 92
  '发件':     'Berangkat dari Gerai',     // code 50
  '取件扫描': 'Sudah Diambil Kurir',      // code 10
  '揽收':     'Sudah Diambil Kurir',      '快件揽收': 'Sudah Diambil Kurir',
  '留仓件':   'Tertahan di Gudang',
  '签收':     'Paket Diterima',           '已签收': 'Paket Diterima',
  '退件':     'Dalam Pengiriman Retur',   '退仓': 'Dalam Pengiriman Retur'
};

function adaCjk_(s) { return /[㐀-䶿一-鿿]/.test(String(s == null ? '' : s)); }

/**
 * Normalkan label tracking.
 * - rapikan spasi
 * - terjemahkan istilah Mandarin yang dikenal
 * - "留仓件,派件中" dipecah, dipetakan satu-satu, lalu digabung lagi tanpa kembar
 * - yang tidak dikenal DIBIARKAN UTUH (bukan dibuang, bukan ditebak)
 */
function normLabel_(s) {
  var x = String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  if (!x) return '';
  if (LABEL_CN[x]) return LABEL_CN[x];

  var bagian = x.split(/[,，、;；\/|]+/)
                .map(function (p) { return p.trim(); })
                .filter(function (p) { return p; });
  var hasil = [];
  bagian.forEach(function (p) {
    var v = LABEL_CN[p] || p;
    if (hasil.indexOf(v) < 0) hasil.push(v);       // "留仓件,派件中" bisa memetakan ke label sama
  });
  return hasil.join(' · ');
}

/** Lapor sekali di akhir ronde — jangan menulis log tiap resi (mahal). */
function laporLabelAsing_(cjk) {
  var k = Object.keys(cjk || {});
  if (!k.length) return;
  trkLog_('Label J&T belum diterjemahkan (' + k.length + ' jenis): ' +
          k.map(function (x) { return '"' + x + '" x' + cjk[x]; }).join(', ') +
          ' -> tambahkan ke LABEL_CN di JntTrack.gs', 'WARN');
}

/**
 * Diagnostik: daftar label Mandarin yang masih tersisa di sheet, beserta
 * jumlahnya. Jalankan dari editor kalau ada aksara asing di kolom label.
 */
function labelBelumDikenal() {
  var sh = getSS().getSheetByName(CFG.masterSheet);
  if (!sh || sh.getLastRow() < 2) return 'Belum ada data.';
  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var iLab = header.indexOf('Label Tracking');
  if (iLab < 0) return 'Kolom "Label Tracking" belum ada — jalankan tracking dulu.';

  var data = sh.getRange(2, iLab + 1, sh.getLastRow() - 1, 1).getValues();
  var asing = {}, semua = {};
  data.forEach(function (r) {
    var v = String(r[0] || '').trim(); if (!v) return;
    semua[v] = (semua[v] || 0) + 1;
    if (adaCjk_(v)) asing[v] = (asing[v] || 0) + 1;
  });
  var out = 'SEMUA LABEL DI SHEET:\n' +
    Object.keys(semua).sort(function (a, b) { return semua[b] - semua[a]; })
      .map(function (k) { return '  ' + semua[k] + '\t' + k; }).join('\n') +
    '\n\nMASIH BERAKSARA MANDARIN: ' +
    (Object.keys(asing).length
      ? '\n' + Object.keys(asing).map(function (k) { return '  ' + asing[k] + '\t' + k; }).join('\n') +
        '\n\nKirim daftar ini supaya bisa ditambahkan ke LABEL_CN.'
      : '(tidak ada ✔)');
  Logger.log(out);
  return out;
}

/** Kolom hasil tracking — SENGAJA berurutan supaya bisa ditulis sekali jalan. */
var TRACK_COLS = ['Label Tracking', 'Kode Tracking', 'Waktu Tracking', 'Keterangan Tracking',
                  'Alasan Tertunda', 'Kode Alasan', 'Posisi Terakhir', 'Kurir Terakhir',
                  'Foto Kurir', 'Foto Kurir Drive', 'Cek Terakhir'];
// 'Foto Kurir'       = URL jmsfile bertanda tangan (berlaku ~24 jam, disegarkan tiap run)
// 'Foto Kurir Drive' = salinan permanen di Google Drive (folder POD_Kurir_JNT)

// Folder Drive tempat menyimpan salinan foto kurir. Dibuat otomatis di bawah
// folder root sistem. Dibuat per bulan supaya tidak menumpuk di satu folder.
var FOTO_KURIR_FOLDER = 'POD_Kurir_JNT';

var TRK_PROP = 'jnt_track_job';
var TRK_SESI_PROP = 'jnt_track_sesi';   // sesi manual hasil tempel dari DevTools
var TRK_LOG_PROP  = 'jnt_track_log';    // catatan langkah terakhir (cincin, maks 60 baris)

// ---------------------------------------------------------------------------
// LOG — tampil di Apps Script (Executions) DAN di layar supervisor
// ---------------------------------------------------------------------------
/**
 * Kenapa dua-duanya: console.log masuk ke Executions (buat saya/teknis),
 * tapi supervisor tidak akan membuka Apps Script. Jadi log yang sama juga
 * disimpan supaya bisa dibaca langsung di tab Tracking J&T.
 */
function trkLog_(pesan, level) {
  level = level || 'INFO';
  var baris = Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Jakarta',
                'HH:mm:ss') + ' [' + level + '] ' + pesan;
  if (level === 'ERROR') console.error(baris); else console.log(baris);
  try {
    var p = PropertiesService.getScriptProperties();
    var arr = [];
    try { arr = JSON.parse(p.getProperty(TRK_LOG_PROP) || '[]') || []; } catch (e) { arr = []; }
    arr.push(baris);
    if (arr.length > 60) arr = arr.slice(-60);
    // Properti punya batas ~9 KB per nilai. Sejak balasan mentah J&T ikut
    // dicatat, 60 baris bisa menembusnya — dan kalau lewat, setProperty
    // melempar error dan SELURUH log hilang. Buang yang paling tua dulu.
    while (arr.length > 1 && JSON.stringify(arr).length > 8000) arr = arr.slice(1);
    p.setProperty(TRK_LOG_PROP, JSON.stringify(arr));
  } catch (e) { /* log tidak boleh menjatuhkan proses utama */ }
}
/** Dibaca UI. */
function getLogTracking() {
  try {
    return JSON.parse(PropertiesService.getScriptProperties().getProperty(TRK_LOG_PROP) || '[]') || [];
  } catch (e) { return []; }
}
function hapusLogTracking() {
  PropertiesService.getScriptProperties().deleteProperty(TRK_LOG_PROP);
  return [];
}

/**
 * Pastikan kolom-kolom ini ada di sheet; yang belum ada ditambahkan di kanan.
 * Mengembalikan header terbaru.
 *
 * Ini fungsi yang HILANG pada v2.1–v2.2: dipanggil tapi tidak pernah ditulis,
 * sehingga trigger mati oleh ReferenceError sebelum sempat menulis progres apa pun.
 */
function ensureColumns_(sh, cols) {
  var lastCol = Math.max(1, sh.getLastColumn());
  var header = sh.getRange(1, 1, 1, lastCol).getValues()[0]
                 .map(function (x) { return String(x).trim(); });
  var kurang = cols.filter(function (c) { return header.indexOf(c) < 0; });
  if (kurang.length) {
    sh.getRange(1, lastCol + 1, 1, kurang.length).setValues([kurang]);
    header = header.concat(kurang);
    trkLog_('Kolom ditambahkan: ' + kurang.join(', '));
    SpreadsheetApp.flush();
  }
  return header;
}

// ---------------------------------------------------------------------------
// SESI: authToken (JWT) + device-no  — dari login platform VIP
// ---------------------------------------------------------------------------
/**
 * Endpoint VIP diautorisasi lewat header:
 *   authToken : JWT dari sesi login VIP (tanpa klaim exp -> umurnya diputuskan
 *               server; hanya bisa diketahui dari lapangan — kalau tracking mulai
 *               gagal "unauthorized", berarti sesinya habis: tempel ulang).
 *   device-no : penanda perangkat, ikut dari header permintaan VIP.
 * Keduanya ditempel manual dari DevTools (panel "Sesi Manual"), lalu disimpan di
 * Script Properties — jadi tempel ulang TIDAK perlu deploy ulang.
 */
function ambilSesi_() {
  var m = bacaSesiManual_();
  return {
    authToken: m.authToken, deviceNo: m.deviceNo,
    ada: !!(m.authToken && m.deviceNo), manual: true
  };
}

/** Bersihkan tempelan token: buang prefiks "authToken:"/kutip/spasi. */
function bersihToken_(s, namaHeader) {
  s = String(s || '').trim();
  if (namaHeader) s = s.replace(new RegExp('^\\s*' + namaHeader + '\\s*:\\s*', 'i'), '');
  return s.replace(/^['"]|['"]$/g, '').trim();
}

/** Panel "Sesi Manual" -> simpan. Dipanggil dari layar, bukan dari editor. */
function simpanSesiManual(authToken, deviceNo) {
  authToken = bersihToken_(authToken, 'authToken');
  deviceNo  = bersihToken_(deviceNo, 'device-no');

  if (!authToken) throw new Error('authToken wajib diisi.');
  if (!deviceNo)  throw new Error('device-no wajib diisi.');
  // JWT selalu berbentuk 3 bagian dipisah titik. Cek ringan supaya salah-tempel ketahuan.
  if (authToken.split('.').length !== 3)
    throw new Error('authToken tidak berbentuk JWT (harus ada 2 titik). Salin utuh dari header authToken.');

  PropertiesService.getScriptProperties().setProperty(TRK_SESI_PROP, JSON.stringify({
    authToken: authToken, deviceNo: deviceNo, disimpan: new Date().toISOString(),
    oleh: (Session.getActiveUser().getEmail() || '')
  }));
  return statusSesiManual();
}

function bacaSesiManual_() {
  var s = PropertiesService.getScriptProperties().getProperty(TRK_SESI_PROP);
  var o = {};
  if (s) { try { o = JSON.parse(s) || {}; } catch (e) { o = {}; } }
  return {
    authToken: o.authToken || TRK.authTokenManual || '',
    deviceNo:  o.deviceNo  || TRK.deviceNoManual  || '',
    disimpan: o.disimpan || '', oleh: o.oleh || ''
  };
}

function hapusSesiManual() {
  PropertiesService.getScriptProperties().deleteProperty(TRK_SESI_PROP);
  return statusSesiManual();
}

/** Untuk UI — token disamarkan, hanya ekor yang ditampilkan. */
function statusSesiManual() {
  var m = bacaSesiManual_();
  var umurJam = m.disimpan ? Math.round((Date.now() - new Date(m.disimpan).getTime()) / 36e5) : null;
  return {
    ada: !!(m.authToken && m.deviceNo),
    tokenEkor: m.authToken ? '…' + m.authToken.slice(-8) : '',
    deviceEkor: m.deviceNo ? '…' + m.deviceNo.slice(-6) : '',
    jwtValid: m.authToken ? (m.authToken.split('.').length === 3) : false,
    disimpan: m.disimpan, oleh: m.oleh, umurJam: umurJam
  };
}

/**
 * Diagnostik cepat — jalankan dari editor untuk membuat/memeriksa 10 kolom
 * tracking TANPA harus menjalankan seluruh job.
 *
 * Berguna karena kolom ini dibuat di dalam proses tracking, bukan saat setup:
 * kalau prosesnya gagal di awal, kolomnya tidak akan pernah muncul dan
 * sheet terlihat seolah tidak terjadi apa-apa.
 */
function siapkanKolomTracking() {
  var sh = getSS().getSheetByName(CFG.masterSheet);
  if (!sh) throw new Error('Sheet "' + CFG.masterSheet + '" tidak ada.');

  var sebelum = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0]
                  .map(function (x) { return String(x).trim(); });
  var kurangSebelum = TRACK_COLS.filter(function (c) { return sebelum.indexOf(c) < 0; });
  var header = ensureColumns_(sh, TRACK_COLS);

  var idx = TRACK_COLS.map(function (c) { return header.indexOf(c); });
  var berdampingan = (Math.max.apply(null, idx) - Math.min.apply(null, idx) + 1) === TRACK_COLS.length;

  var pesan =
    'Sheet          : ' + CFG.masterSheet + '\n' +
    'Jumlah kolom   : ' + sebelum.length + ' -> ' + header.length + '\n' +
    'Baru dibuat    : ' + (kurangSebelum.length ? kurangSebelum.join(', ') : '(tidak ada — semua sudah lengkap)') + '\n' +
    'Posisi kolom   : ' + (Math.min.apply(null, idx) + 1) + '–' + (Math.max.apply(null, idx) + 1) +
                          (berdampingan ? ' (berdampingan ✔)' : ' (TERCERAI — sistem pakai jalur tulis aman)') + '\n' +
    'Resi target    : ' + hitungKandidat_().total + ' berstatus "' + TRK.statusTarget + '"\n\n' +
    'Kolom siap. Isinya baru terisi setelah tracking dijalankan.';
  Logger.log(pesan);
  return pesan;
}

/** Diagnostik — jalankan dari editor kalau tracking bermasalah. */
function cekSesi() {
  var s = ambilSesi_();
  var pesan =
    'authToken : ' + (s.authToken ? '…' + s.authToken.slice(-10) + ' (' +
                      (s.authToken.split('.').length === 3 ? 'bentuk JWT ✔' : 'BUKAN JWT!') + ')' : '(KOSONG)') + '\n' +
    'device-no : ' + (s.deviceNo ? '…' + s.deviceNo.slice(-8) : '(KOSONG)') + '\n\n' +
    (s.ada
      ? 'Sesi VIP siap. Uji beneran dengan tesSatuResi().'
      : 'Sesi VIP belum lengkap. Ambil dari platform VIP:\n' +
        '  1. Login di login-newvip.jet.co.id, buka menu Tracking, lacak 1 resi.\n' +
        '  2. DevTools (F12) -> Network -> klik permintaan "trace/list".\n' +
        '  3. Di Request Headers, salin nilai: authToken dan device-no.\n' +
        '  4. Tempel keduanya di panel "Sesi Manual" pada tab Tracking J&T.');
  Logger.log(pesan);
  return pesan;
}

// ---------------------------------------------------------------------------
// PANGGIL API
// ---------------------------------------------------------------------------
function potong_(s, n) {
  s = String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  return s.length > n ? s.slice(0, n) + '…' : (s || '(kosong)');
}

/**
 * J&T membungkus JSON-nya DI DALAM string JSON lagi (ganda).
 * Badan balasannya benar-benar berbentuk:  "{\"code\":20000,...}"
 * Jadi JSON.parse sekali hanya mengupas kulitnya dan menghasilkan STRING,
 * bukan objek — lalu semua pembacaan field diam-diam undefined.
 *
 * Ini yang membuat 5 resi pertama dilaporkan "API menolak: ?", padahal J&T
 * menjawab code=20000 (查询成功 = query berhasil) dengan data lengkap.
 * Kupas berulang sampai jadi objek; jangan pernah asumsikan sekali cukup.
 */
function uraikanJson_(teks) {
  var v = JSON.parse(teks);
  for (var i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  return v;
}

/**
 * Sukses menurut J&T + data berupa array.
 * Endpoint VIP memakai code=1 & succ=true ("Permintaan berhasil"); endpoint
 * publik lama memakai code=20000. Terima keduanya supaya tidak menolak balasan
 * yang sebenarnya benar (pelajaran mahal dulu: menuntut bentuk yang dibayangkan).
 */
function suksesJnt_(j) {
  if (!j || typeof j !== 'object') return false;
  if (!j.data || Object.prototype.toString.call(j.data) !== '[object Array]') return false;
  if (j.succ === true) return true;
  return j.code === undefined || Number(j.code) === 1 || Number(j.code) === 20000;
}

/**
 * Terangkan penolakan APA ADANYA.
 *
 * Versi lama cuma membaca j.desc, dan waktu field itu tidak ada hasilnya
 * "API menolak: ?" — kita jadi buta persis di titik yang paling perlu dilihat.
 * J&T tidak menjanjikan nama field tertentu, jadi jangan menebak: coba nama
 * yang lazim, lalu SELALU lampirkan balasan mentahnya.
 */
function jelaskanTolak_(j, teks) {
  var kandidat = ['desc', 'msg', 'message', 'errorMsg', 'error_msg', 'errMsg', 'reason', 'info'];
  var pesan = '';
  for (var i = 0; i < kandidat.length && !pesan; i++) {
    if (j && j[kandidat[i]]) pesan = String(j[kandidat[i]]);
  }
  var bagian = [];
  if (j && j.code !== undefined) bagian.push('code=' + j.code);
  if (pesan) bagian.push('"' + pesan + '"');
  bagian.push('mentah: ' + potong_(teks, 220));
  return bagian.join(' · ');
}

/** @return {Object} peta billcode -> data terbaru, atau {_error:'...'} */
function lacak_(billcodes, sesi) {
  if (!sesi || !sesi.authToken || !sesi.deviceNo)
    return { _error: 'Sesi VIP belum ada (authToken/device-no).' };

  var res = UrlFetchApp.fetch(TRK.apiUrl, {
    method: 'post',
    contentType: 'application/json;charset=UTF-8',
    payload: JSON.stringify({ type: 1, codes: billcodes }),
    muteHttpExceptions: true, followRedirects: false,
    headers: {
      'accept': 'application/json, text/plain, */*',
      'authToken': sesi.authToken,
      'device-no': sesi.deviceNo,
      'language': TRK.language,
      'routeName': TRK.routeName,
      'origin': TRK.origin,
      'user-agent': TRK.ua
    }
  });

  var kode = res.getResponseCode();
  var teks = res.getContentText();
  if (kode === 401 || kode === 403)
    return { _error: 'HTTP ' + kode + ' — sesi VIP ditolak/kedaluwarsa. Tempel ulang authToken & device-no.' };
  if (kode !== 200) return { _error: 'HTTP ' + kode + ' — ' + potong_(teks, 160) };

  var j;
  try { j = uraikanJson_(teks); }
  catch (e) {
    return { _error: 'Balasan bukan JSON: ' + potong_(teks, 160) };
  }
  if (!suksesJnt_(j)) return { _error: 'API menolak: ' + jelaskanTolak_(j, teks) };

  var out = {};
  j.data.forEach(function (d) {
    var key = String(d.keyword || '').trim();
    if (key) out[key] = ambilTerbaru_(d.details, d.traceItems);
  });
  return out;
}

/**
 * Ambil catatan TERBARU. Sengaja diurutkan sendiri berdasarkan scanTime —
 * tidak menggantungkan diri pada urutan yang dikirim J&T.
 *
 * traceItems = daftar foto yang SUDAH bertanda tangan (imgUrl) dari endpoint VIP;
 * dipetakan ke detail lewat nama file yang sama pada path fotonya.
 */
function ambilTerbaru_(details, traceItems) {
  if (!details || !details.length) return null;
  var s = details.slice().sort(function (a, b) {
    return String(b.scanTime || '').localeCompare(String(a.scanTime || ''));
  });
  var x = s[0];
  var masalah = Number(x.code) === 110;         // 110 = 问题件/停留中 (paket bermasalah)
  var pathFoto = st_(x.abnormalPicUrl || x.returnSignPicUrl || x.returnRegisterPicUrl);
  return {
    label:      normLabel_(x.status),
    kode:       (x.code === 0 || x.code) ? String(x.code) : '',
    waktu:      st_(x.scanTime),
    keterangan: st_(x.customerTracking),
    alasan:     masalah ? normAlasan_(x.remark1) : '',
    kodeAlasan: masalah ? st_(x.remark4) : '',
    posisi:     st_(x.scanNetworkCity),
    // staffName TIDAK selalu ada pada catatan bermasalah -> cadangan scanByName,
    // supaya "Kurir Terakhir" tidak kosong persis di baris yang paling dibutuhkan.
    kurir:      [st_(x.staffName) || st_(x.scanByName), st_(x.staffContact)]
                  .filter(function (v) { return v; }).join(' · '),
    foto:       fotoBertandaTangan_(pathFoto, traceItems)
  };
}
function st_(v) { return String(v == null ? '' : v).trim(); }

/** Nama file terakhir dari sebuah path/URL (buang query & folder). */
function namaFile_(u) {
  var s = String(u || '').split('?')[0];
  var i = s.lastIndexOf('/');
  return i >= 0 ? s.slice(i + 1) : s;
}

/**
 * Cocokkan path foto (relatif, dari "abnormalPicUrl") dengan URL bertanda tangan
 * di traceItems (imgUrl) lewat NAMA FILE yang sama. Kembalikan URL bertanda
 * tangan yang siap diklik.
 *
 * Kenapa lewat nama file, bukan urutan: satu resi bisa punya beberapa foto
 * (mis. problem + receipt). Nama file unik memastikan CS melihat foto yang
 * benar-benar milik catatan terbaru, bukan foto lain.
 *
 * Tanda tangan ini KEDALUWARSA ~24 jam — memang begitu adanya. Karena tracking
 * dijalankan berkala, URL tersegarkan tiap run. Kalau sudah lewat, link menolak
 * -> sinyal jalankan tracking lagi.
 */
function fotoBertandaTangan_(pathFoto, traceItems) {
  if (!pathFoto) return '';
  if (traceItems && traceItems.length) {
    var target = namaFile_(pathFoto);
    for (var i = 0; i < traceItems.length; i++) {
      var u = st_(traceItems[i] && traceItems[i].imgUrl);
      if (u && namaFile_(u) === target) return u;          // sudah bertanda tangan
    }
  }
  // Tidak ada di traceItems -> simpan path apa adanya (belum bisa diklik, tapi
  // tidak hilang; jadi jejak kalau suatu saat perlu ditandatangani ulang).
  return pathFoto;
}

/**
 * Normalisasi alasan dari lapangan (remark1).
 * Data asli tidak konsisten kapitalisasinya, mis.
 *   "Menunggu konfirmasi Untuk Delivery"
 *   "Penerima menolak menerima paket"
 * Yang dibereskan hanya spasi & huruf pertama — ISI TEKSNYA TIDAK DIUBAH,
 * karena ini klaim resmi ekspedisi dan dipakai sebagai bukti saat sengketa.
 */
function normAlasan_(s) {
  var x = String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  if (!x) return '';
  return x.charAt(0).toUpperCase() + x.slice(1);
}
function kunciAlasan_(s) { return normAlasan_(s).toLowerCase().replace(/[^a-z0-9]/g, ''); }

// ---------------------------------------------------------------------------
// SALINAN FOTO KURIR KE DRIVE (permanen)
// ---------------------------------------------------------------------------
/**
 * Simpan foto bukti kurir ke Google Drive supaya bisa dibuka kapan saja —
 * link jmsfile aslinya kedaluwarsa ~24 jam, salinan Drive ini tidak.
 *
 * Efisien & tahan-ulang:
 *  - DEDUP by nama file: kalau foto ini sudah pernah disimpan (tracking jalan
 *    berkali-kali), tidak diunduh ulang — cukup pakai link Drive yang lama.
 *  - Kegagalan (kuota/izin/expired) TIDAK menjatuhkan tracking: dicatat di log,
 *    kolom Drive dibiarkan kosong, link jmsfile tetap tersimpan.
 *
 * @return {string} URL Drive, atau '' bila gagal / bukan URL bertanda tangan.
 */
function simpanFotoKeDrive_(signedUrl) {
  var u = String(signedUrl || '').trim();
  if (!u || !/^https?:\/\//i.test(u)) return '';        // path mentah (tak bertanda tangan) -> lewati

  try {
    var nama = namaFile_(u);
    if (!nama) return '';
    var folder = folderFotoKurir_();

    var ada = folder.getFilesByName(nama);               // DEDUP
    if (ada.hasNext()) return ada.next().getUrl();

    var res = UrlFetchApp.fetch(u, { muteHttpExceptions: true });
    if (res.getResponseCode() !== 200) {
      trkLog_('Foto->Drive gagal (HTTP ' + res.getResponseCode() + ') ' + nama, 'WARN');
      return '';
    }
    var blob = res.getBlob().setName(nama);
    return folder.createFile(blob).getUrl();
  } catch (e) {
    trkLog_('Foto->Drive error: ' + (e && e.message), 'WARN');
    return '';
  }
}

/** Folder POD_Kurir_JNT/[YYYY-MM] di bawah root sistem (dibuat bila belum ada). */
function folderFotoKurir_() {
  var ym = Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM');
  return getFolderPath([CFG.driveRoot, FOTO_KURIR_FOLDER, ym]);   // getFolderPath ada di Code.gs
}

// ---------------------------------------------------------------------------
// JOB LATAR BELAKANG
// ---------------------------------------------------------------------------
function bacaJob_() {
  try { var v = PropertiesService.getScriptProperties().getProperty(TRK_PROP);
        return v ? JSON.parse(v) : null; } catch (e) { return null; }
}
function simpanJob_(j) {
  PropertiesService.getScriptProperties().setProperty(TRK_PROP, JSON.stringify(j));
  return j;
}
function hapusTriggerTracking_() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'lanjutRefreshTracking') ScriptApp.deleteTrigger(t);
  });
}

/** Dipanggil dari UI. Menandai job & melempar pekerjaan ke trigger. */
function mulaiRefreshTracking() {
  var j = bacaJob_();
  if (j && j.status === 'jalan' && !getProgresTracking().macet)
    throw new Error('Proses tracking sedang berjalan. Tunggu selesai atau klik Hentikan.');

  var n = hitungKandidat_().total;
  if (!n) throw new Error('Tidak ada resi berstatus "' + TRK.statusTarget + '" yang punya No. Waybill.');

  hapusLogTracking();
  simpanJob_({ status: 'jalan', mulai: new Date().getTime(), denyut: new Date().getTime(),
               total: n, ok: 0, gagal: 0, putaran: 0, crash: 0,
               pesan: 'Menyiapkan…', errTerakhir: '' });
  hapusTriggerTracking_();
  ScriptApp.newTrigger('lanjutRefreshTracking').timeBased().after(1000).create();
  trkLog_('Job dimulai — ' + n + ' resi berstatus "' + TRK.statusTarget + '".');
  logAct('Tracking J&T', 'Mulai — ' + n + ' resi');
  return { ok: true, total: n };
}

function hentikanRefreshTracking() {
  var j = bacaJob_() || {};
  j.status = 'dihentikan';
  j.pesan = 'Dihentikan oleh supervisor.';
  simpanJob_(j);
  hapusTriggerTracking_();
  logAct('Tracking J&T', 'Dihentikan manual');
  return { ok: true };
}

/** Kandidat = Sedang Diantar + punya waybill. Belum dicek = Cek Terakhir < job.mulai */
function hitungKandidat_(sejak) {
  var sh = getSS().getSheetByName(CFG.masterSheet);
  var out = { total: 0, belum: 0, sudah: 0 };
  if (!sh || sh.getLastRow() < 2) return out;
  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var iSt = header.indexOf('Status Ekspedisi'), iKey = header.indexOf(CFG.keyCol);
  var iCek = header.indexOf('Cek Terakhir');
  if (iSt < 0 || iKey < 0) return out;
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  data.forEach(function (r) {
    if (String(r[iSt]).trim() !== TRK.statusTarget) return;
    if (!String(r[iKey]).trim()) return;
    out.total++;
    var c = (iCek >= 0) ? r[iCek] : '';
    var ts = (c instanceof Date) ? c.getTime() : 0;
    if (sejak && ts >= sejak) out.sudah++; else out.belum++;
  });
  return out;
}

/**
 * Inti proses. Dipanggil trigger, boleh berjalan berkali-kali sampai habis.
 * Tidak menyimpan antrean di mana pun — daftar sisa dihitung ulang dari sheet
 * tiap putaran. Efeknya: kalau eksekusi mati di tengah jalan, putaran
 * berikutnya otomatis melanjutkan tanpa ada yang terlewat atau dobel.
 */
function lanjutRefreshTracking() {
  // Jaring pengaman terluar. Sebelumnya tidak ada, dan akibatnya fatal:
  // satu ReferenceError (ensureColumns_ yang tidak pernah ditulis) membuat
  // trigger mati tanpa suara — job tetap tertulis "jalan" & "Menyiapkan…"
  // selamanya, tanpa satu pun petunjuk di layar. Sekarang setiap kegagalan
  // wajib meninggalkan jejak: di Executions dan di layar supervisor.
  try {
    jalankanPutaranTracking_();
  } catch (e) {
    var j = bacaJob_() || {};
    trkLog_('CRASH: ' + (e && e.message) + ' | ' + (e && e.stack ? String(e.stack).split('\n')[1] : ''), 'ERROR');
    j.crash = (j.crash || 0) + 1;
    j.errTerakhir = String(e && e.message || e);
    if (j.crash >= 3) {
      gagalJob_(j, 'Berhenti setelah 3 kali error beruntun. Terakhir: ' + j.errTerakhir);
    } else {
      j.pesan = 'Error — mencoba lagi (' + j.crash + '/3): ' + j.errTerakhir;
      j.denyut = new Date().getTime();
      simpanJob_(j);
      jadwalkanLagi_();
    }
  }
}

function jalankanPutaranTracking_() {
  var job = bacaJob_();
  if (!job || job.status !== 'jalan') { hapusTriggerTracking_(); trkLog_('Job tidak aktif — trigger dibersihkan.'); return; }
  hapusTriggerTracking_();

  var mulaiRun = new Date().getTime();
  job.putaran = (job.putaran || 0) + 1;
  job.denyut = mulaiRun;
  job.pesan = 'Putaran ' + job.putaran + ' — menyiapkan…';
  simpanJob_(job);
  trkLog_('=== Putaran ' + job.putaran + ' mulai (ok=' + job.ok + ', gagal=' + job.gagal + ') ===');

  var sesi;
  try { sesi = ambilSesi_(); } catch (e) { return gagalJob_(job, 'Gagal membaca sesi VIP: ' + e.message); }
  if (!sesi.ada)
    return gagalJob_(job, 'Sesi VIP belum ada. Isi panel "Sesi Manual" (authToken + device-no) di tab Tracking J&T.');
  trkLog_('Sesi VIP dipakai · authToken …' + sesi.authToken.slice(-8) + ' · device …' + sesi.deviceNo.slice(-6));

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) { trkLog_('Sheet sedang dikunci proses lain — dijadwalkan ulang.', 'WARN'); jadwalkanLagi_(); return; }

  try {
    var sh = getSS().getSheetByName(CFG.masterSheet);
    if (!sh) return gagalJob_(job, 'Sheet "' + CFG.masterSheet + '" tidak ditemukan.');
    ensureColumns_(sh, TRACK_COLS);                       // kolom hasil dibuat bila belum ada

    var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
      .map(function (x) { return String(x).trim(); }));
    var nRow = sh.getLastRow() - 1;
    if (nRow < 1) return selesaiJob_(job, 'Tidak ada data.');

    var iSt = header.indexOf('Status Ekspedisi'), iKey = header.indexOf(CFG.keyCol);
    var iKat = header.indexOf('Kategori Masalah');
    var kol = {}; TRACK_COLS.forEach(function (c) { kol[c] = header.indexOf(c); });

    var data = sh.getRange(2, 1, nRow, header.length).getValues();

    // baris yang perlu dicek putaran ini
    var perlu = [];
    data.forEach(function (r, i) {
      if (String(r[iSt]).trim() !== TRK.statusTarget) return;
      var awb = String(r[iKey]).trim(); if (!awb) return;
      var c = r[kol['Cek Terakhir']];
      var ts = (c instanceof Date) ? c.getTime() : 0;
      if (ts >= job.mulai) return;                        // sudah dicek di job ini
      perlu.push({ i: i, awb: awb });
    });

    if (!perlu.length) return selesaiJob_(job, 'Semua resi sudah diperbarui.');
    trkLog_(perlu.length + ' resi perlu dicek putaran ini · ' + TRK.resiPerRequest + ' resi/permintaan');

    var gagalBeruntun = 0, katUbah = {}, tunda = [], cjk = {};
    // tunda = baris yang sudah diperbarui tapi BELUM sampai ke sheet.
    var n = TRK.resiPerRequest > 1 ? TRK.resiPerRequest : 1;

    for (var p = 0; p < perlu.length; p += n) {
      if (new Date().getTime() - mulaiRun > TRK.budgetMs) {
        trkLog_('Batas waktu eksekusi tercapai — sisanya dilanjutkan putaran berikutnya.');
        break;
      }

      var grup = perlu.slice(p, p + n);
      var hasil = lacak_(grup.map(function (g) { return g.awb; }), sesi);

      if (hasil._error) {
        gagalBeruntun++;
        job.gagal += grup.length;
        job.errTerakhir = hasil._error;
        trkLog_('GAGAL ' + grup.map(function (g) { return g.awb; }).join(',') +
                ' -> ' + hasil._error + ' (beruntun ' + gagalBeruntun + '/' + TRK.gagalBeruntunMaks + ')', 'WARN');
        // Berhenti kalau server konsisten menolak — jangan dihantam terus.
        if (gagalBeruntun >= TRK.gagalBeruntunMaks) {
          // Selamatkan dulu yang sudah didapat — jangan ikut hangus bersama kegagalan.
          tulisBaris_(sh, data, kol, iKat, tunda, katUbah);
          return gagalJob_(job, 'Berhenti otomatis setelah ' + gagalBeruntun +
            ' kegagalan beruntun. Terakhir: ' + hasil._error);
        }
        Utilities.sleep(TRK.jedaMs * 2);
        continue;
      }
      if (gagalBeruntun) trkLog_('Pulih setelah ' + gagalBeruntun + ' kegagalan.');
      gagalBeruntun = 0;

      grup.forEach(function (g) {
        var d = hasil[g.awb];
        var r = data[g.i];
        if (!d) { job.gagal++; trkLog_('KOSONG ' + g.awb + ' — J&T tidak mengembalikan data resi ini.', 'WARN'); return; }
        if (job.ok < 3) trkLog_('CONTOH ' + g.awb + ' -> "' + d.label + '"' +
                                (d.alasan ? ' · alasan: ' + d.alasan : ''));   // bukti awal parsing benar
        r[kol['Label Tracking']]      = d.label;
        r[kol['Kode Tracking']]       = d.kode;
        r[kol['Waktu Tracking']]      = d.waktu;
        r[kol['Keterangan Tracking']] = d.keterangan;
        r[kol['Alasan Tertunda']]     = d.alasan;
        r[kol['Kode Alasan']]         = d.kodeAlasan;
        r[kol['Posisi Terakhir']]     = d.posisi;
        r[kol['Kurir Terakhir']]      = d.kurir;
        r[kol['Foto Kurir']]          = d.foto;                 // jmsfile bertanda tangan (~24 jam)
        // Salinan permanen ke Drive. Kalau foto sudah pernah disimpan (dedup),
        // ini instan; kalau gagal, kolom Drive kosong tapi jmsfile tetap ada.
        if (kol['Foto Kurir Drive'] >= 0 && d.foto) {
          var drv = simpanFotoKeDrive_(d.foto);
          if (drv) { r[kol['Foto Kurir Drive']] = drv; if (job.ok < 3) trkLog_('Foto disalin ke Drive: ' + g.awb); }
        }
        r[kol['Cek Terakhir']]        = new Date();
        // KATEGORI MASALAH = klaim ekspedisi. Diisi dari alasan resmi J&T,
        // bukan tebakan CS. Hanya diisi bila memang ada alasannya.
        // Dicatat di katUbah supaya nanti hanya baris INI yang ditimpa —
        // baris lain milik CS tidak boleh ikut tersapu.
        if (iKat >= 0 && d.alasan) { r[iKat] = d.alasan; katUbah[g.i] = d.alasan; }
        if (adaCjk_(d.label)) cjk[d.label] = (cjk[d.label] || 0) + 1;   // dicatat, dilapor sekali di akhir
        tunda.push(g.i);
        job.ok++;
      });

      job.denyut = new Date().getTime();
      job.pesan = 'Berjalan… ' + job.ok + '/' + job.total + ' resi.';

      // CICIL: begitu terkumpul TRK.flushTiap baris, langsung dititipkan ke sheet.
      // "Cek Terakhir" ikut tertulis di sini — itulah yang membuat resi ini tidak
      // diambil ulang kalau eksekusi mati sedetik kemudian.
      if (tunda.length >= TRK.flushTiap) {
        var np = tulisBaris_(sh, data, kol, iKat, tunda, katUbah);
        trkLog_('Dicicil ke sheet: ' + tunda.length + ' baris (' + np + 'x tulis) · total ' + job.ok);
        tunda = []; katUbah = {};
        simpanJob_(job);
      }
      Utilities.sleep(TRK.jedaMs);
    }

    // sisa yang belum sempat dicicil
    if (tunda.length) {
      tulisBaris_(sh, data, kol, iKat, tunda, katUbah);
      tunda = []; katUbah = {};
    }
    laporLabelAsing_(cjk);

    var sisa = hitungKandidat_(job.mulai).belum;
    trkLog_('Putaran ' + job.putaran + ' selesai · berhasil ' + job.ok + ' · gagal ' + job.gagal + ' · sisa ' + sisa);
    if (sisa > 0) {
      job.pesan = 'Berjalan… sisa ' + sisa + ' resi.';
      job.denyut = new Date().getTime();
      simpanJob_(job);
      jadwalkanLagi_();
    } else {
      perbaruiKategoriDariTracking();       // segarkan dropdown kategori dari data lapangan
      selesaiJob_(job, 'Selesai.');
    }
  } finally { lock.releaseLock(); }
}

/**
 * Tulis HANYA kolom tracking — jangan pernah menulis ulang seluruh sheet.
 *
 * Kalau ke-10 kolom kebetulan berdampingan (kasus normal: dibuat sekaligus di
 * ujung kanan oleh ensureColumns_), cukup satu setValues.
 * Kalau tercerai — mis. sheet lama pernah diutak-atik manual — kolomnya ditulis
 * satu per satu. Menulis blok min..max di kondisi itu berarti ikut menimpa
 * kolom di antaranya dengan data lama yang kita baca beberapa menit lalu,
 * dan kolom di antaranya bisa saja "Status Followup" yang baru diisi CS.
 * 10x setValues jauh lebih murah daripada menghapus kerja CS.
 */
/**
 * Kelompokkan indeks baris jadi rentang berurutan.
 *   [3,4,5,9,10,20] -> [[3,5],[9,10],[20,20]]
 * Gunanya: resi yang kita proses hampir selalu berdekatan di sheet (semuanya
 * "Sedang Diantar"), jadi 5 baris biasanya cukup 1 panggilan setValues.
 */
function rentang_(idxs) {
  var a = idxs.slice().sort(function (x, y) { return x - y; });
  var out = [];
  for (var i = 0; i < a.length; i++) {
    if (i && a[i] === a[i - 1]) continue;              // buang kembar
    var s = a[i], e = a[i];
    while (i + 1 < a.length && (a[i + 1] === e + 1 || a[i + 1] === e)) { e = a[++i]; }
    out.push([s, e]);
  }
  return out;
}

/**
 * Tulis HANYA baris yang berubah — bukan seluruh sheet.
 *
 * Versi lama menulis ulang ke-304 baris tiap flush. Dengan flush tiap 40 resi
 * itu masih tertahankan; begitu dicicil tiap 5 resi, biayanya meledak jadi
 * 9x lipat — mencicil malah bikin lambat. Maka yang diperbaiki bukan angkanya,
 * tapi cara menulisnya: kumpulkan baris yang benar-benar berubah, gabungkan
 * yang berurutan, lalu tulis per rentang.
 *
 * Efek sampingnya justru yang paling penting: kita tidak lagi menyentuh baris
 * milik CS yang tidak ada urusannya dengan ronde ini.
 */
function tulisBaris_(sh, data, kol, iKat, baris, katUbah) {
  if (!baris || !baris.length) return 0;
  var idx = TRACK_COLS.map(function (c) { return kol[c]; });
  var min = Math.min.apply(null, idx), max = Math.max.apply(null, idx);
  var rapat = (max - min + 1 === TRACK_COLS.length);
  var panggilan = 0;

  rentang_(baris).forEach(function (r) {
    var n = r[1] - r[0] + 1;
    if (rapat) {                                       // jalur cepat: kolom berdampingan
      sh.getRange(r[0] + 2, min + 1, n, max - min + 1)
        .setValues(data.slice(r[0], r[1] + 1).map(function (x) { return x.slice(min, max + 1); }));
      panggilan++;
    } else {                                           // jalur aman: kolom tercerai
      idx.forEach(function (c) {
        if (c < 0) return;
        sh.getRange(r[0] + 2, c + 1, n, 1)
          .setValues(data.slice(r[0], r[1] + 1).map(function (x) { return [x[c]]; }));
        panggilan++;
      });
    }
  });

  // Kategori Masalah = kolom milik CS. Hanya sel yang benar-benar kita isi yang
  // disentuh, jadi kategori yang sedang diketik CS di baris lain tidak tersapu.
  if (iKat >= 0 && katUbah) {
    rentang_(Object.keys(katUbah).map(Number)).forEach(function (r) {
      sh.getRange(r[0] + 2, iKat + 1, r[1] - r[0] + 1, 1)
        .setValues(data.slice(r[0], r[1] + 1).map(function (x) { return [x[iKat]]; }));
      panggilan++;
    });
  }
  return panggilan;
}

function jadwalkanLagi_() {
  hapusTriggerTracking_();
  ScriptApp.newTrigger('lanjutRefreshTracking').timeBased().after(30 * 1000).create();
}
function selesaiJob_(job, pesan) {
  job.status = 'selesai'; job.pesan = pesan; job.beres = new Date().getTime();
  simpanJob_(job); hapusTriggerTracking_();
  logAct('Tracking J&T', pesan + ' ok=' + job.ok + ' gagal=' + job.gagal);
}
function gagalJob_(job, pesan) {
  job.status = 'gagal'; job.pesan = pesan; job.beres = new Date().getTime();
  simpanJob_(job); hapusTriggerTracking_();
  logAct('Tracking J&T', 'GAGAL — ' + pesan);
}

// ---------------------------------------------------------------------------
// PROGRES & RINGKASAN (untuk UI)
// ---------------------------------------------------------------------------
function getProgresTracking() {
  var job = bacaJob_();
  var k = hitungKandidat_(job ? job.mulai : 0);
  var out = {
    status: job ? job.status : 'idle',
    pesan:  job ? job.pesan : 'Belum pernah dijalankan.',
    total:  k.total, selesai: k.sudah, sisa: k.belum,
    ok: job ? job.ok : 0, gagal: job ? job.gagal : 0,
    putaran: job ? job.putaran : 0,
    errTerakhir: job ? (job.errTerakhir || '') : '',
    persen: k.total ? Math.round(k.sudah / k.total * 100) : 0,
    mulai: job && job.mulai ? Utilities.formatDate(new Date(job.mulai), Session.getScriptTimeZone(), 'dd/MM HH:mm:ss') : '',
    durasi: ''
  };
  if (job && job.mulai) {
    var akhir = (job.status === 'jalan') ? new Date().getTime() : (job.beres || job.mulai);
    var d = Math.max(0, Math.round((akhir - job.mulai) / 1000));
    out.durasi = Math.floor(d / 60) + 'm ' + (d % 60) + 's';
  }

  // Deteksi macet. Job bertuliskan "jalan" belum tentu benar-benar jalan:
  // kalau eksekusinya mati mendadak, tidak ada siapa pun yang membetulkan
  // statusnya. Tanda pastinya: tidak ada trigger tersisa DAN tidak ada denyut
  // selama beberapa menit. Lebih baik lapor macet daripada memutar bar 0%
  // selama 12 menit seperti kejadian sebelumnya.
  if (job && job.status === 'jalan') {
    var adaTrigger = ScriptApp.getProjectTriggers().some(function (t) {
      return t.getHandlerFunction() === 'lanjutRefreshTracking';
    });
    var diam = new Date().getTime() - (job.denyut || job.mulai);
    if (!adaTrigger && diam > 3 * 60 * 1000) {
      out.macet = true;
      out.pesan = 'Proses berhenti tanpa kabar (tidak ada denyut ' +
                  Math.round(diam / 60000) + ' menit & trigger hilang). Lihat Log di bawah, lalu Mulai lagi.';
    }
  }
  return out;
}

/** Rekap label tracking untuk visualisasi supervisor. */
function getRingkasTracking() {
  var sh = getSS().getSheetByName(CFG.masterSheet);
  var out = { total: 0, belumDicek: 0, label: [], alasan: [], perCS: [], terlama: [] };
  if (!sh || sh.getLastRow() < 2) return out;

  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var iSt = header.indexOf('Status Ekspedisi'), iKey = header.indexOf(CFG.keyCol);
  var iLab = header.indexOf('Label Tracking'), iAls = header.indexOf('Alasan Tertunda');
  var iWkt = header.indexOf('Waktu Tracking'), iPic = header.indexOf('PIC CS');
  var iProv = header.indexOf(CFG.provinceCol);
  if (iLab < 0) return out;                      // kolom belum ada -> belum pernah dijalankan

  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var lab = {}, als = {}, cs = {};
  var kini = new Date().getTime();

  data.forEach(function (r) {
    if (String(r[iSt]).trim() !== TRK.statusTarget) return;
    if (!String(r[iKey]).trim()) return;
    out.total++;
    var L = String(r[iLab] || '').trim();
    if (!L) { out.belumDicek++; return; }
    lab[L] = (lab[L] || 0) + 1;

    var A = String(iAls >= 0 ? r[iAls] : '').trim();
    if (A) als[A] = (als[A] || 0) + 1;

    var nama = String(iPic >= 0 ? r[iPic] : '').trim() || '(belum terdistribusi)';
    if (!cs[nama]) cs[nama] = { nama: nama, total: 0, label: {} };
    cs[nama].total++;
    cs[nama].label[L] = (cs[nama].label[L] || 0) + 1;

    // paket yang label terakhirnya sudah lama diam = paling berisiko
    var w = String(iWkt >= 0 ? r[iWkt] : '').trim();
    var t = w ? new Date(w.replace(' ', 'T')).getTime() : 0;
    if (t) {
      var hari = Math.floor((kini - t) / 86400000);
      if (hari >= 3) out.terlama.push({
        resi: String(r[iKey]).trim(), label: L, alasan: A, hari: hari,
        provinsi: String(iProv >= 0 ? r[iProv] : '').trim(), pic: nama
      });
    }
  });

  out.label  = urutTrk_(lab);
  out.alasan = urutTrk_(als);
  out.perCS  = Object.keys(cs).map(function (k) { return cs[k]; })
                 .sort(function (a, b) { return b.total - a.total; });
  out.terlama.sort(function (a, b) { return b.hari - a.hari; });
  out.terlama = out.terlama.slice(0, 50);
  return out;
}
function urutTrk_(o) {
  return Object.keys(o).map(function (k) { return { k: k, n: o[k] }; })
    .sort(function (a, b) { return b.n - a.n; });
}

// ---------------------------------------------------------------------------
// KATEGORI MASALAH DINAMIS (dari data lapangan, bukan daftar karangan)
// ---------------------------------------------------------------------------
/**
 * Susun ulang Ref_Kategori_Masalah dari alasan yang BENAR-BENAR muncul di
 * lapangan (remark1 J&T), diurut dari yang paling sering.
 *
 * Kenapa begini: daftar kategori lama disusun manual di awal proyek — tebakan.
 * Sekarang kita punya klaim asli ekspedisi, jadi dropdown CS memakai kata-kata
 * yang persis sama dengan yang tercatat di sistem J&T. Saat CS mendebat klaim
 * kurir, istilahnya cocok dan tidak bisa diperdebatkan.
 */
function perbaruiKategoriDariTracking() {
  var sh = getSS().getSheetByName(CFG.masterSheet);
  if (!sh || sh.getLastRow() < 2) return { ok: false, jumlah: 0 };

  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var iAls = header.indexOf('Alasan Tertunda'), iKode = header.indexOf('Kode Alasan');
  if (iAls < 0) return { ok: false, jumlah: 0 };

  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var m = {};
  data.forEach(function (r) {
    var a = normAlasan_(r[iAls]); if (!a) return;
    var k = kunciAlasan_(a);
    if (!m[k]) m[k] = { teks: a, kode: String(iKode >= 0 ? r[iKode] : '').trim(), n: 0 };
    m[k].n++;
  });

  var baris = Object.keys(m).map(function (k) { return m[k]; })
    .sort(function (a, b) { return b.n - a.n; })
    .map(function (x) {
      return [x.teks, 'Klaim ekspedisi J&T · ' + x.n + ' resi' + (x.kode ? ' · kode ' + x.kode : ''),
              x.kode, x.n, new Date()];
    });

  // opsi bawaan untuk kasus yang memang tidak punya klaim masalah dari J&T
  baris.unshift(['Belum ada klaim masalah dari ekspedisi',
                 'Paket berjalan normal — CS konfirmasi kesiapan terima', '', 0, new Date()]);
  baris.push(['Lainnya', 'Kasus di luar daftar — jelaskan di Catatan CS', '', 0, new Date()]);

  var ss = getSS();
  var k = ss.getSheetByName('Ref_Kategori_Masalah') || ss.insertSheet('Ref_Kategori_Masalah');
  k.clear();
  k.getRange(1, 1, 1, 5).setValues([['Kategori Masalah', 'Deskripsi', 'Kode J&T', 'Jumlah Resi', 'Diperbarui']]);
  if (baris.length) k.getRange(2, 1, baris.length, 5).setValues(baris);
  k.setFrozenRows(1);

  logAct('Kategori Masalah', 'Disusun ulang dari lapangan — ' + baris.length + ' opsi');
  return { ok: true, jumlah: baris.length };
}

// ---------------------------------------------------------------------------
// TES MANUAL (jalankan dari editor)
// ---------------------------------------------------------------------------
/** Lacak 1 resi & tampilkan hasilnya — untuk memastikan pipa jalan. */
function tesSatuResi() {
  var sesi = ambilSesi_();
  if (!sesi.ada) return cekSesi();
  var k = hitungKandidat_();
  var sh = getSS().getSheetByName(CFG.masterSheet);
  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var iKey = header.indexOf(CFG.keyCol), iSt = header.indexOf('Status Ekspedisi');
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var awb = '';
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][iSt]).trim() === TRK.statusTarget && String(data[i][iKey]).trim()) {
      awb = String(data[i][iKey]).trim(); break;
    }
  }
  if (!awb) return 'Tidak ada resi "' + TRK.statusTarget + '" untuk dites.';
  return tesResiMentah(awb);
}

/**
 * Tes satu resi dan TAMPILKAN BALASAN MENTAH J&T seutuhnya.
 *
 * Ini alat yang seharusnya ada sejak awal. Waktu J&T menolak, yang kita perlu
 * lihat adalah kalimat mereka sendiri — bukan tafsiran saya atas satu field
 * yang saya tebak namanya. Isi awb kalau mau menguji resi tertentu.
 */
function tesResiMentah(awb) {
  var sesi = ambilSesi_();
  if (!sesi.ada) return cekSesi();

  if (!awb) {
    var sh = getSS().getSheetByName(CFG.masterSheet);
    var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
      .map(function (x) { return String(x).trim(); }));
    var iKey = header.indexOf(CFG.keyCol), iSt = header.indexOf('Status Ekspedisi');
    var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    for (var i = 0; i < data.length && !awb; i++)
      if (String(data[i][iSt]).trim() === TRK.statusTarget) awb = String(data[i][iKey]).trim();
  }
  awb = String(awb || '').trim();
  if (!awb) return 'Tidak ada resi untuk dites.';

  var res = UrlFetchApp.fetch(TRK.apiUrl, {
    method: 'post',
    contentType: 'application/json;charset=UTF-8',
    payload: JSON.stringify({ type: 1, codes: [awb] }),
    muteHttpExceptions: true, followRedirects: false,
    headers: {
      'accept': 'application/json, text/plain, */*',
      'authToken': sesi.authToken, 'device-no': sesi.deviceNo,
      'language': TRK.language, 'routeName': TRK.routeName,
      'origin': TRK.origin, 'user-agent': TRK.ua
    }
  });

  var out =
    'Resi          : ' + awb + '\n' +
    'Sesi VIP      : authToken …' + sesi.authToken.slice(-8) + ' · device …' + sesi.deviceNo.slice(-6) + '\n' +
    'HTTP          : ' + res.getResponseCode() + '\n' +
    '--- BALASAN MENTAH J&T (VIP) ---\n' + potong_(res.getContentText(), 4000) + '\n' +
    '--- HASIL PARSING SISTEM ---\n' + JSON.stringify(lacak_([awb], sesi), null, 2);
  Logger.log(out);
  return out;
}

/**
 * Uji apakah satu permintaan boleh memuat BANYAK resi.
 * Kalau lolos, naikkan TRK.resiPerRequest ke 10 -> request turun 10x lipat,
 * dan risiko kena WAF ikut turun drastis.
 */
function tesMultiResi() {
  var sesi = ambilSesi_();
  if (!sesi.ada) return cekSesi();
  var sh = getSS().getSheetByName(CFG.masterSheet);
  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var iKey = header.indexOf(CFG.keyCol), iSt = header.indexOf('Status Ekspedisi');
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var awb = [];
  for (var i = 0; i < data.length && awb.length < 3; i++) {
    if (String(data[i][iSt]).trim() === TRK.statusTarget && String(data[i][iKey]).trim())
      awb.push(String(data[i][iKey]).trim());
  }
  if (awb.length < 2) return 'Perlu minimal 2 resi untuk dites.';

  var h = lacak_(awb, sesi);
  var dapat = Object.keys(h).filter(function (k) { return k !== '_error'; });
  var out = 'Dikirim   : ' + awb.join(', ') + '\n' +
            'Dikembalikan: ' + (h._error ? 'ERROR — ' + h._error : dapat.length + ' resi (' + dapat.join(', ') + ')') + '\n\n' +
            (dapat.length === awb.length
              ? '✔ MULTI-RESI DIDUKUNG. Naikkan TRK.resiPerRequest jadi 10 di JntTrack.gs.'
              : '✗ Hanya 1 resi per permintaan. Biarkan TRK.resiPerRequest = 1.');
  Logger.log(out);
  return out;
}
