/**
 * ============================================================================
 *  SISTEM ADMIN ORDER — Meika Berkarya   [v2]
 *  OrderOnline (3 akun)  ->  (stok + normalisasi wilayah)  ->  J&T  ->  balik ke OO
 *
 *  KUNCI PENCOCOKAN: "#<KodeAkun>-<order_id>" disisipkan ke Nama Barang saat
 *  upload J&T, karena J&T tidak mengembalikan kolom "Nomor pesanan e-commerce".
 *  Kode akun ikut disisipkan agar order_id dari akun berbeda tidak tertukar.
 *
 *  AKSES: setiap admin login dgn akun Google-nya; semua aktivitas & batch
 *  tercatat atas nama siapa. Deploy: "Execute as: User accessing the web app".
 * ============================================================================
 */

/**
 * Penanda versi aplikasi. NAIKKAN angka ini setiap kali Anda mengubah kode,
 * lalu deploy ulang. Versinya tampil di pojok kanan atas aplikasi, sehingga
 * Anda bisa langsung memastikan deployment sudah memakai kode terbaru.
 *
 * Cara update tanpa mengganti URL:
 *   Deploy → Manage deployments → (pilih deployment yg ID-nya sama dgn link Anda)
 *   → ikon pensil → dropdown Version → pilih "New version" → Deploy
 *   ⚠ Kalau dropdown Version tidak diubah ke "New version", kode lama tetap jalan.
 */
var APP_VERSION = 'v8.2 — handover resi harian (PDF pickup J&T)';

var CFG = {
  spreadsheetId: '',              // '' = spreadsheet aktif
  csSpreadsheetId: '',            // (opsional) ID spreadsheet Sistem CS Undelivered
  csMasterSheet: 'MASTER_Undelivered',
  driveFolderId: '',              // (opsional) folder Drive utk file hasil; '' = My Drive

  sh: {
    orders:   'ORDERS',
    akun:     'REF_AKUN',
    users:    'USERS',
    produk:   'REF_PRODUK',
    stok:     'STOK',
    skualias: 'REF_SKU_ALIAS',      // nama produk OO yang beda format -> SKU yang sama
    jual:     'REF_HARGA_JUAL',     // harga jual/pcs yang diisi manual admin (per SKU)
    bump:     'REF_BUMP',           // nama produk bump dari OO -> SKU stok
    mutasi:   'STOK_MUTASI',
    gudang:   'GUDANG',
    wilayah:  'REF_WILAYAH',
    alias:    'REF_ALIAS_PROVINSI',
    area:     'AREA_JNT',
    kategori: 'KATEGORI_JNT',
    batch:    'BATCH',
    ekspor:   'EXPORT_LOG',
    pengirim: 'PENGIRIM',
    log:      'LOG'
  },

  ST: {
    baru:        'Baru',
    perluCekKurir:'Perlu Cek Kurir',
    perluMapping:'Perlu Mapping',
    pendingStok: 'Pending Stok',
    siapKirim:   'Siap Kirim',
    diBatch:     'Terkirim ke J&T',
    dapatAWB:    'Dapat AWB',
    trackingOK:  'Tracking Terkirim ke OO',
    retur:       'Retur'
  },

  jumlahKoli: 1,
  layanan:    'Ez',
  caraBayar:  'BULANAN',
  jenisBarang:'BARANG',
  inputAsuransi: 0,                 // kolom "Apakah Input Asuransi?" -> selalu 0
  noteResi: 'Hubungi penerima',     // ditambahkan di kolom Keterangan resi J&T

  gudangDefault: 'G1'     // gudang bawaan (dipakai utk data lama tanpa gudang)
};

var JNT_HEADER = ['Berat','Nama Pengirim','Telepon Pengirim','Provinsi Pengirim','Kota Pengirim',
  'Daerah Pengirim','Alamat Pengirim','Informasi Alamat Pengirim','Apakah Dropship?',' Nama Dropshiper',
  'Telfon Dropshiper','Nama Penerima','Telepon Penerima','Provinsi Penerima','Kota Penerima','Kecamatan',
  'Alamat Penerima','Informasi Alamat Penerima','Cara Pembayaran','Nama Barang','Kategori Barang',
  'Nilai Barang','Jenis asuransi',' Apakah Input Asuransi? \n','Jumlah','Jenis Barang','Keterangan',
  'Nomor pesanan e-commerce','COD','Jenis Layanan','Biaya Pengiriman','Biaya Lainnya'];

var ORDERS_HEADER = ['order_id','Akun OO','Tanggal Order','Nama Penerima','Telepon','Alamat',
  'Provinsi OO','Kota OO','Kecamatan OO','Provinsi JNT','Kota JNT','Kecamatan JNT','Status Wilayah',
  'Produk','product_code','Variation','SKU','Nama Barang JNT','Rincian Isi','Kategori Barang','Pcs',
  'Bump','SKU Bump','Pcs Bump','Berat',
  'payment_method','product_price','bump_price','gross_revenue','COD','cogs','HPP','courier',
  'Status Order','Batch ID','No. Waybill','URL Tracking','Catatan',
  'Diimport Oleh','Waktu Import','Waktu Batch','Waktu AWB'];

function getSS() {
  return CFG.spreadsheetId ? SpreadsheetApp.openById(CFG.spreadsheetId)
                           : SpreadsheetApp.getActiveSpreadsheet();
}

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Admin Order — Meika Berkarya')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// ---------------------------------------------------------------------------
// SETUP & MIGRASI
// ---------------------------------------------------------------------------
function setup() {
  var ss = getSS();
  var o = ensure_(ss, CFG.sh.orders, ORDERS_HEADER);
  ensureColumns_(o, ORDERS_HEADER);          // migrasi: tambah kolom baru bila belum ada

  ensure_(ss, CFG.sh.akun,     ['Kode','Nama Akun','Aktif']);
  ensure_(ss, CFG.sh.users,    ['Email','Nama','Peran','Aktif']);
  var PRODUK_HEADER = ['product_code','Variation','SKU','Nama Barang JNT','Rincian Isi',
                       'Kategori Barang','Pcs per Order','HPP per Pcs'];
  var pr = ensure_(ss, CFG.sh.produk, PRODUK_HEADER);
  ensureColumns_(pr, PRODUK_HEADER);
  var st = ensure_(ss, CFG.sh.stok, STOK_HEADER);
  ensureColumns_(st, STOK_HEADER);   // tambah kolom yg belum ada (mis. Gudang)
  isiGudangKosong_(st);              // baris lama tanpa gudang -> gudang default
  rapikanStok_(st);                  // susun ulang ke urutan baku: SKU|Nama|Gudang|Stok|HPP
  ensure_(ss, CFG.sh.skualias, SKUALIAS_HEADER);
  ensure_(ss, CFG.sh.jual, JUAL_HEADER);
  ensure_(ss, CFG.sh.bump, BUMP_HEADER);
  ensure_(ss, CFG.sh.mutasi, MUTASI_HEADER);
  var gd = ensure_(ss, CFG.sh.gudang, GUDANG_HEADER);
  ensureColumns_(gd, GUDANG_HEADER);      // tambah kolom Provinsi bila belum ada
  if (gd.getLastRow() < 2) gd.appendRow([CFG.gudangDefault, 'Gudang Utama', 'Jawa Barat', 'Ya']);
  ensure_(ss, CFG.sh.wilayah,  ['Provinsi OO','Kota OO','Kecamatan OO','Provinsi JNT','Kota JNT','Kecamatan JNT']);
  ensure_(ss, CFG.sh.alias,    ['Provinsi OO','Provinsi JNT']);
  ensure_(ss, CFG.sh.area,     ['Provinsi','Kota','Kecamatan']);
  ensure_(ss, CFG.sh.kategori, ['Kategori Barang']);
  ensure_(ss, CFG.sh.batch,    ['Batch ID','Waktu','Akun','Jumlah Order','Total Pcs','Status','Oleh','Email','File ID','File']);
  ensure_(ss, CFG.sh.ekspor,   ['Waktu','Jenis','Akun','Jumlah Order','Nama File','File ID','Oleh']);
  ensure_(ss, CFG.sh.log,      ['Waktu','Email','Nama','Aksi','Detail']);

  var pg = ensure_(ss, CFG.sh.pengirim, ['Kunci','Nilai']);
  if (pg.getLastRow() < 2) {
    pg.getRange(2, 1, 7, 2).setValues([
      ['Nama Pengirim',    'Meika Berkarya'],
      ['Telepon Pengirim', '6287818525580'],
      ['Provinsi Pengirim','Jawa Barat'],
      ['Kota Pengirim',    'Kab. Kuningan'],
      ['Daerah Pengirim',  'Cigandamekar'],
      ['Alamat Pengirim',  'Jl. Panawuan Indrapatra, Panawuan'],
      ['Jenis Layanan',    'Ez']
    ]);
  }
  var al = ss.getSheetByName(CFG.sh.alias);
  if (al.getLastRow() < 2) {
    al.getRange(2, 1, 6, 2).setValues([
      ['DI Yogyakarta',                     'Daerah Istimewa Yogyakarta'],
      ['D.I. Yogyakarta',                   'Daerah Istimewa Yogyakarta'],
      ['Nanggroe Aceh Darussalam (NAD)',    'Aceh'],
      ['Nusa Tenggara Barat (NTB)',         'Nusa Tenggara Barat'],
      ['Nusa Tenggara Timur (NTT)',         'Nusa Tenggara Timur'],
      ['Kepulauan Bangka Belitung (Babel)', 'Kepulauan Bangka Belitung']
    ]);
  }
  var ak = ss.getSheetByName(CFG.sh.akun);
  if (ak.getLastRow() < 2) {
    ak.getRange(2, 1, 3, 3).setValues([
      ['A1', 'Akun OrderOnline 1', 'Ya'],
      ['A2', 'Akun OrderOnline 2', 'Ya'],
      ['A3', 'Akun OrderOnline 3', 'Ya']
    ]);
  }
  // daftarkan pemilik script sbg superadmin
  var us = ss.getSheetByName(CFG.sh.users);
  if (us.getLastRow() < 2) {
    var em = '';
    try { em = Session.getEffectiveUser().getEmail(); } catch (e) {}
    if (em) us.appendRow([em, 'Superadmin', 'superadmin', 'Ya']);
  }
  return 'Setup selesai. Berikutnya: daftarkan admin di tab Master Data, import Informasi Area & Kategori.';
}

function ensure_(ss, name, header) {
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sh.getLastRow() < 1 || String(sh.getRange(1, 1).getValue()).trim() === '') {
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.setFrozenRows(1);
  }
  return sh;
}
/** Baris STOK lama yang belum punya Gudang -> isi gudang default. */
function isiGudangKosong_(sh) {
  var t = readTable_(sh);
  if (!t.rows.length || t.header.indexOf('Gudang') < 0) return;
  var ubah = false;
  t.rows.forEach(function (r) {
    if (t_(r['SKU']) && !t_(r['Gudang'])) { r['Gudang'] = CFG.gudangDefault; ubah = true; }
  });
  if (ubah) writeTable_(sh, t);
}

/** Tambahkan kolom yang belum ada di sheet (tanpa merusak data lama). */
function ensureColumns_(sh, header) {
  var cur = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0]
              .map(function (x) { return t_(x); }).filter(function (x) { return x !== ''; });
  var miss = header.filter(function (h) { return cur.indexOf(h) < 0; });
  if (!miss.length) return 0;
  sh.getRange(1, cur.length + 1, 1, miss.length).setValues([miss]);
  return miss.length;
}

// ---------------------------------------------------------------------------
// USER & AKSES
// ---------------------------------------------------------------------------
function me_() {
  var email = '';
  try { email = t_(Session.getActiveUser().getEmail()); } catch (e) {}
  if (!email) {
    throw new Error('Akun Google Anda tidak terbaca. Pastikan web app di-deploy dengan ' +
      '"Execute as: User accessing the web app" dan Anda sudah login.');
  }
  var u = usersMap_()[email.toLowerCase()];
  if (!u) throw new Error('Akun ' + email + ' belum terdaftar sebagai admin. ' +
    'Minta superadmin menambahkan Anda di tab Master Data → Admin.');
  if (!u.aktif) throw new Error('Akun Anda nonaktif. Hubungi superadmin.');
  return u;
}
function getMe() {
  var u = me_();
  return { email: u.email, nama: u.nama, peran: u.peran,
           isSuper: lc_(u.peran) === 'superadmin',
           versi: APP_VERSION };
}

/**
 * Cek versi — SENGAJA seringan mungkin (tanpa buka spreadsheet / cek user),
 * karena dipanggil berkala oleh halaman yang sedang terbuka.
 */
function getVersi() { return APP_VERSION; }

/** URL web app aktif — dipakai untuk memuat ulang halaman ke versi terbaru. */
function getWebAppUrl() {
  try { return ScriptApp.getService().getUrl(); } catch (e) { return ''; }
}
function usersMap_() {
  var sh = getSS().getSheetByName(CFG.sh.users);
  var m = {};
  if (sh && sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues().forEach(function (r) {
      var e = t_(r[0]); if (!e) return;
      var a = lc_(r[3]);
      m[e.toLowerCase()] = { email: e, nama: t_(r[1]) || e, peran: t_(r[2]) || 'admin',
                             aktif: (a === '' || a === 'ya' || a === 'true' || a === 'aktif') };
    });
  }
  return m;
}
function getUsers() {
  me_();
  var m = usersMap_();
  return Object.keys(m).map(function (k) { return m[k]; });
}
function simpanUser(u) {
  var me = me_();
  if (lc_(me.peran) !== 'superadmin') throw new Error('Hanya superadmin yang boleh mengelola admin.');
  var email = t_(u.email);
  if (!email || email.indexOf('@') < 0) throw new Error('Email tidak valid.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.users);
    var row = [email, t_(u.nama), t_(u.peran) || 'admin', (u.aktif === false ? 'Tidak' : 'Ya')];
    var found = -1;
    if (sh.getLastRow() > 1) {
      var d = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues();
      for (var i = 0; i < d.length; i++) if (lc_(d[i][0]) === lc_(email)) { found = i + 2; break; }
    }
    if (found > 0) sh.getRange(found, 1, 1, 4).setValues([row]);
    else sh.appendRow(row);
    log_('Simpan Admin', row.join(' | '));
    return { ok: true };
  } finally { lock.releaseLock(); }
}
function hapusUser(email) {
  var me = me_();
  if (lc_(me.peran) !== 'superadmin') throw new Error('Hanya superadmin yang boleh mengelola admin.');
  if (lc_(email) === lc_(me.email)) throw new Error('Tidak bisa menghapus akun Anda sendiri.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.users);
    if (sh.getLastRow() > 1) {
      var d = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues();
      for (var i = d.length - 1; i >= 0; i--) if (lc_(d[i][0]) === lc_(email)) sh.deleteRow(i + 2);
    }
    log_('Hapus Admin', email);
    return { ok: true };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// AKUN ORDERONLINE
// ---------------------------------------------------------------------------
function akunMap_() {
  var sh = getSS().getSheetByName(CFG.sh.akun);
  var m = {};
  if (sh && sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues().forEach(function (r) {
      var k = t_(r[0]); if (!k) return;
      var a = lc_(r[2]);
      m[k] = { kode: k, nama: t_(r[1]) || k,
               aktif: (a === '' || a === 'ya' || a === 'true' || a === 'aktif') };
    });
  }
  return m;
}
function getAkunList() {
  var m = akunMap_();
  return Object.keys(m).map(function (k) { return m[k]; });
}
function simpanAkun(a) {
  me_();
  var kode = t_(a.kode).toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!kode) throw new Error('Kode akun wajib diisi (huruf/angka, tanpa spasi).');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.akun);
    var row = [kode, t_(a.nama) || kode, (a.aktif === false ? 'Tidak' : 'Ya')];
    var found = -1;
    if (sh.getLastRow() > 1) {
      var d = sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues();
      for (var i = 0; i < d.length; i++) if (lc_(d[i][0]) === lc_(kode)) { found = i + 2; break; }
    }
    if (found > 0) sh.getRange(found, 1, 1, 3).setValues([row]);
    else sh.appendRow(row);
    log_('Simpan Akun OO', row.join(' | '));
    return { ok: true };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// IMPORT MASTER (Area & Kategori)
// ---------------------------------------------------------------------------
function importArea(b64, filename) {
  me_();
  var rows = readSheet_(b64, filename, 1);
  var out = [];
  rows.forEach(function (r) {
    var p = t_(r['Provinsi Baru']), k = t_(r['Kota Baru']), c = t_(r['Kecamatan Baru']);
    if (p && k && c) out.push([p, k, c]);
  });
  if (!out.length) throw new Error('Kolom "Provinsi Baru / Kota Baru / Kecamatan Baru" tidak ditemukan.');
  var sh = getSS().getSheetByName(CFG.sh.area);
  sh.clear();
  sh.getRange(1, 1, 1, 3).setValues([['Provinsi', 'Kota', 'Kecamatan']]);
  sh.getRange(2, 1, out.length, 3).setValues(out);
  sh.setFrozenRows(1);
  cacheClear_();
  log_('Import Area', out.length + ' baris');
  return { ok: true, jumlah: out.length };
}
function importKategori(b64, filename) {
  me_();
  var rows = readSheet_(b64, filename, 0);
  var key = Object.keys(rows[0] || {})[0];
  var out = rows.map(function (r) { return [t_(r['Kategori Barang'] || r[key])]; })
                .filter(function (r) { return r[0]; });
  if (!out.length) throw new Error('Tidak ada data kategori.');
  var sh = getSS().getSheetByName(CFG.sh.kategori);
  sh.clear();
  sh.getRange(1, 1, 1, 1).setValues([['Kategori Barang']]);
  sh.getRange(2, 1, out.length, 1).setValues(out);
  sh.setFrozenRows(1);
  log_('Import Kategori', out.length + ' baris');
  return { ok: true, jumlah: out.length };
}

// ---------------------------------------------------------------------------
// IMPORT ORDER (WAJIB pilih akun OrderOnline)
// ---------------------------------------------------------------------------
function importOrders(b64, filename, kodeAkun) {
  var me = me_();
  kodeAkun = t_(kodeAkun);
  if (!kodeAkun) throw new Error('Pilih akun OrderOnline terlebih dahulu.');
  var ak = akunMap_()[kodeAkun];
  if (!ak) throw new Error('Akun "' + kodeAkun + '" tidak dikenal.');

  var rows = readSheet_(b64, filename, 0);
  if (!rows.length) throw new Error('File kosong.');
  if (!rows[0].hasOwnProperty('order_id'))
    throw new Error('Kolom "order_id" tidak ditemukan — pastikan ini file export OrderOnline.');

  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var ss = getSS();
    var sh = ss.getSheetByName(CFG.sh.orders);
    ensureColumns_(sh, ORDERS_HEADER);
    var t = readTable_(sh);

    // kunci unik = akun|order_id  (order_id bisa sama antar akun)
    var seen = {};
    t.rows.forEach(function (r) { seen[t_(r['Akun OO']) + '|' + t_(r['order_id'])] = 1; });

    var area = areaIndex_(), alias = aliasMap_(), wil = wilayahMap_(), prod = produkMap_();
    var bmap = bumpMap_();
    var baru = 0, dup = 0, perluMap = 0, perluProd = 0, perluBump = 0, cekKurir = 0;
    var add = [];
    var now = new Date();

    rows.forEach(function (r) {
      var oid = t_(r['order_id']);
      if (!oid) return;
      if (seen[kodeAkun + '|' + oid]) { dup++; return; }
      seen[kodeAkun + '|' + oid] = 1;

      var norm = normArea_(r['province'], r['city'], r['subdistrict'], area, alias, wil);
      var pm = produkLookup_(prod, t_(r['product_code']), t_(r['variation']));
      var bumpNm = bumpNama_(r['bump']);              // "-" -> '' (tidak ada bump)
      var bm = bumpNm ? bumpLookup_(bmap, bumpNm) : null;
      var isCod = lc_(r['payment_method']) === 'cod';
      var gross = num_(r['gross_revenue']);
      // Non-COD (transfer bank) -> kolom COD di template J&T harus KOSONG, bukan 0.
      var cod = isCod ? (gross === '' ? 0 : gross) : '';
      var berat = Math.max(1, Math.ceil((num_(r['weight']) || 1000) / 1000));
      var cogs = num_(r['cogs']);
      var hargaProduk = num_(r['product_price']);   // -> kolom "Nilai Barang" di J&T
      // HPP order: pakai HPP master bila ada, kalau tidak pakai cogs dari OrderOnline
      var hppOrder = (pm && pm.hpp !== '' && pm.hpp !== undefined)
        ? pm.hpp * (pm.pcs || 1) : (cogs === '' ? '' : cogs);

      var status = '', catatan = [];
      if (!norm.ok) { status = CFG.ST.perluMapping; perluMap++; catatan.push('Wilayah belum dipetakan'); }
      if (!pm) { status = CFG.ST.perluMapping; perluProd++; catatan.push('Produk belum dipetakan'); }
      // bump ada tapi belum dipetakan -> tahan; kalau tidak, stoknya mustahil dipotong benar
      if (bumpNm && !bm) { status = CFG.ST.perluMapping; perluBump++;
                           catatan.push('Bump belum dipetakan: ' + bumpNm); }
      var kurirOK = /j&t/i.test(t_(r['courier']));
      if (!status && !kurirOK) { status = CFG.ST.perluCekKurir; cekKurir++; catatan.push('Kurir: ' + t_(r['courier'])); }
      if (!status) status = CFG.ST.baru;

      var row = {
        'order_id': oid, 'Akun OO': kodeAkun,
        'Tanggal Order': t_(r['created_at']), 'Nama Penerima': t_(r['name']),
        'Telepon': t_(r['phone']), 'Alamat': t_(r['address']),
        'Provinsi OO': t_(r['province']), 'Kota OO': t_(r['city']), 'Kecamatan OO': t_(r['subdistrict']),
        'Provinsi JNT': norm.ok ? norm.prov : '', 'Kota JNT': norm.ok ? norm.kota : '',
        'Kecamatan JNT': norm.ok ? norm.kec : '', 'Status Wilayah': norm.ok ? 'Valid' : 'Perlu Dipetakan',
        'Produk': t_(r['product']), 'product_code': t_(r['product_code']), 'Variation': t_(r['variation']),
        'SKU': pm ? pm.sku : '', 'Nama Barang JNT': pm ? pm.nama : '',
        'Rincian Isi': pm ? pm.rincian : '',
        'Kategori Barang': pm ? pm.kategori : '', 'Pcs': pm ? pm.pcs : '',
        'Bump': bumpNm, 'SKU Bump': bm ? bm.sku : '', 'Pcs Bump': bumpNm ? (bm ? bm.pcs : '') : '',
        'Berat': berat,
        'payment_method': t_(r['payment_method']),
        'product_price': hargaProduk,
        'bump_price': bumpNm ? (num_(r['bump_price']) || 0) : '',
        'gross_revenue': gross, 'COD': cod,
        'cogs': cogs, 'HPP': hppOrder,
        'courier': t_(r['courier']), 'Status Order': status, 'Catatan': catatan.join('; '),
        'Diimport Oleh': me.nama, 'Waktu Import': now
      };
      add.push(t.header.map(function (h) { return row.hasOwnProperty(h) ? row[h] : ''; }));
      baru++;
    });

    if (add.length) sh.getRange(sh.getLastRow() + 1, 1, add.length, t.header.length).setValues(add);
    log_('Import Order', '[' + kodeAkun + '] ' + filename + ' | baru ' + baru + ', duplikat ' + dup);
    cacheClear_();
    return { ok: true, akun: ak.nama, baru: baru, duplikat: dup, perluMapping: perluMap,
             produkBelumDipetakan: perluProd, bumpBelumDipetakan: perluBump,
             perluCekKurir: cekKurir, total: rows.length };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// NORMALISASI WILAYAH
// ---------------------------------------------------------------------------
function normArea_(prov, kota, kec, area, alias, wil) {
  var p0 = t_(prov), k0 = t_(kota), c0 = t_(kec);
  var wkey = lc_(p0) + '|' + lc_(k0) + '|' + lc_(c0);
  if (wil[wkey]) return { ok: true, prov: wil[wkey][0], kota: wil[wkey][1], kec: wil[wkey][2] };

  var pc = [p0];
  if (alias[lc_(p0)]) pc.unshift(alias[lc_(p0)]);
  var kc = [k0];
  if (/^kota\s+/i.test(k0)) kc.push(k0.replace(/^kota\s+/i, '').trim());
  if (/^kabupaten\s+/i.test(k0)) kc.push(k0.replace(/^kabupaten\s+/i, 'Kab. ').trim());
  var cc = [c0];
  var noParen = c0.replace(/\s*\(.*?\)\s*/g, ' ').trim();
  if (noParen && noParen !== c0) cc.push(noParen);
  if (noParen.indexOf('/') >= 0) cc.push(noParen.split('/').pop().trim());
  if (c0.indexOf('/') >= 0) cc.push(c0.split('/').pop().trim());

  for (var i = 0; i < pc.length; i++)
    for (var j = 0; j < kc.length; j++)
      for (var m = 0; m < cc.length; m++) {
        var hit = area[lc_(pc[i]) + '|' + lc_(kc[j]) + '|' + squash_(cc[m])];
        if (hit) return { ok: true, prov: hit[0], kota: hit[1], kec: hit[2] };
      }
  return { ok: false, prov: '', kota: '', kec: '' };
}

function areaIndex_() {
  var c = cacheGet_('area');
  if (c) return c;
  var sh = getSS().getSheetByName(CFG.sh.area);
  var idx = {};
  if (sh && sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues().forEach(function (r) {
      var p = t_(r[0]), k = t_(r[1]), c2 = t_(r[2]);
      if (p && k && c2) idx[lc_(p) + '|' + lc_(k) + '|' + squash_(c2)] = [p, k, c2];
    });
  }
  return cachePut_('area', idx);
}
function aliasMap_() {
  var sh = getSS().getSheetByName(CFG.sh.alias);
  var m = {};
  if (sh && sh.getLastRow() > 1)
    sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues().forEach(function (r) {
      if (t_(r[0]) && t_(r[1])) m[lc_(r[0])] = t_(r[1]);
    });
  return m;
}
function wilayahMap_() {
  var sh = getSS().getSheetByName(CFG.sh.wilayah);
  var m = {};
  if (sh && sh.getLastRow() > 1)
    sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues().forEach(function (r) {
      if (t_(r[0]) && t_(r[3])) m[lc_(r[0]) + '|' + lc_(r[1]) + '|' + lc_(r[2])] = [t_(r[3]), t_(r[4]), t_(r[5])];
    });
  return m;
}

// ---------------------------------------------------------------------------
// MAPPING PRODUK
// ---------------------------------------------------------------------------
function produkMap_() {
  var sh = getSS().getSheetByName(CFG.sh.produk);
  var m = {};
  if (!sh || sh.getLastRow() < 2) return m;
  var t = readTable_(sh);                     // berbasis nama kolom, aman thd urutan
  t.rows.forEach(function (r) {
    var pc = lc_(r['product_code']), v = lc_(r['Variation'] || '*');
    if (!pc) return;
    m[pc + '|' + v] = { sku: t_(r['SKU']), nama: t_(r['Nama Barang JNT']),
                        rincian: t_(r['Rincian Isi']), kategori: t_(r['Kategori Barang']),
                        pcs: num_(r['Pcs per Order']) || 1, hpp: num_(r['HPP per Pcs']) };
  });
  return m;
}
function produkLookup_(m, code, variation) {
  if (!code) return null;
  return m[lc_(code) + '|' + lc_(variation)] || m[lc_(code) + '|*'] || null;
}

// ---------------------------------------------------------------------------
// BUMP / BUNDLING TAMBAHAN
//
// OrderOnline mengirim bump HANYA sebagai NAMA (kolom `bump`) — tidak ada
// product_code-nya. Kalau tidak ada bump, isinya "-" (bukan sel kosong).
// Karena itu bump dipetakan NAMA -> SKU lewat sheet REF_BUMP.
// ---------------------------------------------------------------------------
var BUMP_HEADER = ['Nama Bump', 'SKU', 'Pcs per Order', 'Diupdate Oleh', 'Waktu'];

/** Bersihkan nilai kolom `bump`. "-" / "" / "0" dianggap TIDAK ada bump. */
function bumpNama_(v) {
  var s = t_(v);
  if (!s || s === '-' || s === '–' || s === '0' || lc_(s) === 'none' || lc_(s) === 'null') return '';
  return s;
}

/** Peta nama bump -> { sku, pcs, nama }. Kunci = nama yang sudah dinormalkan. */
function bumpMap_() {
  var sh = getSS().getSheetByName(CFG.sh.bump);
  var m = {};
  if (!sh || sh.getLastRow() < 2) return m;
  var t = readTable_(sh);
  t.rows.forEach(function (r) {
    var nama = t_(r['Nama Bump']), sku = t_(r['SKU']);
    if (!nama || !sku) return;
    m[namaKey_(nama)] = { sku: sku, pcs: num_(r['Pcs per Order']) || 1, nama: nama };
  });
  return m;
}
function bumpLookup_(m, nama) {
  var b = bumpNama_(nama);
  return b ? (m[namaKey_(b)] || null) : null;
}
function tebakPcs(variation) {
  var s = lc_(variation);
  var beli = (s.match(/beli\s+(\d+)/) || [, 0])[1] * 1;
  var gratis = (s.match(/gratis\s+(\d+)/) || [, 0])[1] * 1;
  var total = beli + gratis;
  return total > 0 ? total : 1;
}
function produkBelumDipetakan() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var m = produkMap_();
  var out = {};
  t.rows.forEach(function (r) {
    var code = t_(r['product_code']), v = t_(r['Variation']);
    if (!code || produkLookup_(m, code, v)) return;
    var k = code + '|' + v;
    if (!out[k]) out[k] = { product_code: code, variation: v, produk: t_(r['Produk']),
                            saran_pcs: tebakPcs(v), jumlah: 0, _cogs: [] };
    out[k].jumlah++;
    var c = num_(r['cogs']);
    if (c !== '' && c > 0) out[k]._cogs.push(c);
  });
  var reg = skuRegistry_();
  var pending = {};
  var lokal = {};                        // grup keputusan LINTAS BARIS di daftar ini
  var katList = getKategoriList();       // master kategori J&T
  var katBelajar = kategoriTerpetakan_(); // produk yang sudah dipetakan (bahan belajar)

  return Object.keys(out).map(function (k) {
    var o = out[k];
    // saran HPP per pcs = rata-rata cogs OrderOnline dibagi jumlah pcs
    var avg = o._cogs.length
      ? o._cogs.reduce(function (a, b) { return a + b; }, 0) / o._cogs.length : 0;
    o.saran_hpp = o.saran_pcs ? Math.round(avg / o.saran_pcs) : Math.round(avg);
    delete o._cogs;

    // --- SKU ditentukan SERVER. Pengecekan mencakup SKU terdaftar DAN
    //     baris-baris lain di daftar ini (lewat objek `lokal`). ---
    var res = saranSkuBaris_(o.produk, o.product_code, reg, lokal, pending);
    o.saran_sku = res.sku;
    o.sku_reuse = res.reused;          // true = memakai SKU produk yang sudah ada
    o.sumber    = res.sumber;          // nama | kanon | mirip | grup | baru
    o.sku_nama  = res.nama || '';
    o.skor      = res.skor || 0;
    o.mirip     = res.mirip || null;   // kandidat terdekat yang DITOLAK (< 93%)

    // --- NORMALISASI ISIAN OTOMATIS ---
    var bersih = rapikanNama_(o.produk);                       // buang kurung/kode/promo
    o.saran_nama    = bersih;                                  // -> Nama Barang J&T (label resi)
    o.saran_rincian = rincianIsi_(bersih, o.saran_pcs, o.variation);   // -> Keterangan resi
    var tk = tebakKategori_(o.produk, katList, katBelajar);
    o.saran_kategori = tk.kategori;                            // '' bila tidak yakin
    o.kategori_skor  = tk.skor;

    // --- DETEKSI KONFLIK: product_code sudah dipakai produk LAIN ---
    var kode = bersihKode_(o.product_code);
    var pemilik = kode ? reg.bySku[kode] : null;
    o.konflik = !!(pemilik && namaKey_(pemilik.nama) !== namaKey_(o.produk) &&
                   lc_(pemilik.sku) !== lc_(o.saran_sku));
    o.konflikNama = o.konflik ? pemilik.nama : '';
    return o;
  });
}
function simpanProduk(p) { return simpanProdukBatch([p]); }

/** Simpan BANYAK pemetaan produk sekaligus (1x baca/tulis, 1x reapply). */
function simpanProdukBatch(list) {
  me_();
  if (!list || !list.length) throw new Error('Tidak ada baris untuk disimpan.');

  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.produk);
    var t = readTable_(sh);
    var reg = skuRegistry_();
    var pending = {};
    var lokal = {};                    // grup keputusan LINTAS BARIS (sama seperti di layar)
    var hasil = [], skuBaru = [], aliasBaru = [], lewat = 0;

    list.forEach(function (p) {
      if (!t_(p.nama)) { lewat++; return; }   // Nama Barang J&T wajib

      var namaOO = t_(p.produk) || t_(p.nama);     // nama produk dari OrderOnline

      // SKU DITENTUKAN SERVER — logika persis sama dengan yang ditampilkan di layar,
      // termasuk penyatuan antar-baris yang namanya mirip.
      var res = saranSkuBaris_(namaOO, p.product_code, reg, lokal, pending);

      // SKU lama -> pakai nama resmi yang sudah terdaftar.
      // SKU baru -> daftarkan nama yang SUDAH DIRAPIKAN (tanpa kurung/kode/promo),
      //             sedangkan nama asli OrderOnline disimpan sebagai alias.
      var namaStok = res.reused ? (res.nama || namaOO) : (rapikanNama_(namaOO) || namaOO);
      var pcs = num_(p.pcs) || 1;
      var hpp = num_(p.hpp) || 0;
      var rincian = t_(p.rincian) || rincianIsi_(namaStok, pcs, p.variation);

      // daftarkan ke registry lokal agar baris berikutnya konsisten
      if (!reg.bySku[res.sku.toUpperCase()]) {
        reg.bySku[res.sku.toUpperCase()] = { sku: res.sku, nama: namaStok };
        if (namaStok) {
          reg.byNama[namaKey_(namaStok)] = res.sku;
          reg.byKanon[kanonKey_(namaStok)] = res.sku;
        }
        skuBaru.push({ sku: res.sku, nama: namaStok, hpp: hpp });
      }

      // Nama OO beda dengan nama resmi SKU -> catat sebagai ALIAS,
      // supaya nama versi ini langsung dikenali pada import berikutnya.
      if (namaOO && namaStok && namaKey_(namaOO) !== namaKey_(namaStok)) {
        aliasBaru.push({ nama: namaOO, sku: res.sku });
        reg.byNama[namaKey_(namaOO)] = res.sku;
      }

      var isi = {
        'product_code': t_(p.product_code), 'Variation': t_(p.variation), 'SKU': res.sku,
        'Nama Barang JNT': t_(p.nama), 'Rincian Isi': rincian,
        'Kategori Barang': t_(p.kategori), 'Pcs per Order': pcs, 'HPP per Pcs': hpp
      };
      var idx = -1;
      for (var i = 0; i < t.rows.length; i++) {
        if (lc_(t.rows[i]['product_code']) === lc_(isi['product_code']) &&
            lc_(t.rows[i]['Variation']) === lc_(isi['Variation'])) { idx = i; break; }
      }
      if (idx >= 0) {
        Object.keys(isi).forEach(function (k) { if (t.header.indexOf(k) >= 0) t.rows[idx][k] = isi[k]; });
      } else {
        var baru = {};
        t.header.forEach(function (h) { baru[h] = isi.hasOwnProperty(h) ? isi[h] : ''; });
        t.rows.push(baru);
      }
      hasil.push({ sku: res.sku, nama: t_(p.nama), reused: res.reused, sumber: res.sumber });
    });

    if (!hasil.length) throw new Error('Tidak ada baris valid (Nama Barang J&T wajib diisi).');

    writeTable_(sh, t);
    pastikanSkuBatch_(skuBaru);          // daftarkan SKU baru ke STOK sekaligus
    var nAlias = tambahAliasSku_(aliasBaru);   // nama beda-format -> SKU yang sama
    var ubah = reapplyMapping_();        // terapkan ke order sekali saja

    log_('Simpan Produk', hasil.length + ' produk, ' + skuBaru.length + ' SKU baru, ' +
         nAlias + ' alias nama');
    return { ok: true, jumlah: hasil.length, dilewati: lewat,
             skuBaru: skuBaru.length, alias: nAlias, hasil: hasil, orderDiperbarui: ubah };
  } finally { lock.releaseLock(); }
}
// ---------------------------------------------------------------------------
// PEMETAAN BUMP  (nama bump dari OO -> SKU stok)
// ---------------------------------------------------------------------------
/** Nama bump yang muncul di ORDERS tapi belum ada di REF_BUMP. */
function bumpBelumDipetakan() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var m = bumpMap_();
  var out = {};
  t.rows.forEach(function (r) {
    var b = bumpNama_(r['Bump']); if (!b) return;
    if (bumpLookup_(m, b)) return;                  // sudah dipetakan
    var k = namaKey_(b);
    if (!out[k]) out[k] = { nama: b, jumlah: 0, _rp: [] };
    out[k].jumlah++;
    var p = num_(r['bump_price']);
    if (p !== '' && p > 0) out[k]._rp.push(p);
  });

  var reg = skuRegistry_();
  var pending = {}, lokal = {};
  return Object.keys(out).map(function (k) {
    var o = out[k];
    // SKU ditentukan server, logika sama dengan pemetaan produk:
    // nama/alias persis -> kanonik -> mirip >=93% -> baris lain di daftar ini -> baru
    var res = saranSkuBaris_(o.nama, '', reg, lokal, pending);
    o.saran_sku = res.sku;
    o.sku_reuse = res.reused;
    o.sumber = res.sumber;
    o.sku_nama = res.nama || '';
    o.skor = res.skor || 0;
    o.mirip = res.mirip || null;
    o.saran_pcs = 1;                                // OO tidak mengirim qty bump
    var rp = o._rp;
    o.harga = rp.length ? Math.round(rp.reduce(function (a, b) { return a + b; }, 0) / rp.length) : 0;
    delete o._rp;
    return o;
  }).sort(function (a, b) { return b.jumlah - a.jumlah; });
}

/** Simpan pemetaan bump — SELURUH tabel sekaligus (satu tombol). */
function simpanBumpBatch(list) {
  me_();
  if (!list || !list.length) throw new Error('Tidak ada baris untuk disimpan.');

  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var me = me_();
    var sh = getSS().getSheetByName(CFG.sh.bump);
    if (!sh) throw new Error('Sheet ' + CFG.sh.bump + ' belum ada — jalankan setup() sekali.');
    var t = readTable_(sh);
    var reg = skuRegistry_();
    var pending = {}, lokal = {};
    var now = new Date();
    var hasil = [], skuBaru = [], lewat = 0;

    list.forEach(function (b) {
      var nama = bumpNama_(b.nama);
      if (!nama) { lewat++; return; }

      // SKU DITENTUKAN SERVER (bukan dari layar) — konsisten dgn pemetaan produk
      var res = saranSkuBaris_(nama, '', reg, lokal, pending);
      var namaStok = res.reused ? (res.nama || nama) : (rapikanNama_(nama) || nama);
      var pcs = num_(b.pcs) || 1;

      if (!reg.bySku[res.sku.toUpperCase()]) {
        reg.bySku[res.sku.toUpperCase()] = { sku: res.sku, nama: namaStok };
        if (namaStok) {
          reg.byNama[namaKey_(namaStok)] = res.sku;
          reg.byKanon[kanonKey_(namaStok)] = res.sku;
        }
        skuBaru.push({ sku: res.sku, nama: namaStok, hpp: 0 });
      }
      // nama bump versi OO dicatat sebagai alias -> import berikutnya langsung kenal
      if (namaKey_(nama) !== namaKey_(namaStok)) reg.byNama[namaKey_(nama)] = res.sku;

      var isi = { 'Nama Bump': nama, 'SKU': res.sku, 'Pcs per Order': pcs,
                  'Diupdate Oleh': me.nama, 'Waktu': now };
      var idx = -1;
      for (var i = 0; i < t.rows.length; i++) {
        if (namaKey_(t.rows[i]['Nama Bump']) === namaKey_(nama)) { idx = i; break; }
      }
      if (idx >= 0) Object.keys(isi).forEach(function (k) { if (t.header.indexOf(k) >= 0) t.rows[idx][k] = isi[k]; });
      else {
        var baru = {};
        t.header.forEach(function (h) { baru[h] = isi.hasOwnProperty(h) ? isi[h] : ''; });
        t.rows.push(baru);
      }
      hasil.push({ nama: nama, sku: res.sku, reused: res.reused });
    });

    if (!hasil.length) throw new Error('Tidak ada baris valid.');

    writeTable_(sh, t);
    pastikanSkuBatch_(skuBaru);                    // SKU bump baru masuk ke STOK (stok 0)
    var aliasBaru = hasil.filter(function (h) { return h.reused; })
      .map(function (h) { return { nama: h.nama, sku: h.sku }; });
    var nAlias = tambahAliasSku_(aliasBaru);
    var ubah = reapplyMapping_();

    log_('Simpan Bump', hasil.length + ' bump, ' + skuBaru.length + ' SKU baru');
    return { ok: true, jumlah: hasil.length, dilewati: lewat, skuBaru: skuBaru.length,
             alias: nAlias, orderDiperbarui: ubah, hasil: hasil };
  } finally { lock.releaseLock(); }
}

function simpanWilayah(w) { return simpanWilayahBatch([w]); }

/** Simpan BANYAK pemetaan wilayah sekaligus (1x tulis, 1x reapply). */
function simpanWilayahBatch(list) {
  me_();
  if (!list || !list.length) throw new Error('Tidak ada baris untuk disimpan.');
  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.wilayah);
    var rows = [], lewat = 0;
    list.forEach(function (w) {
      if (!t_(w.provJNT) || !t_(w.kotaJNT) || !t_(w.kecJNT)) { lewat++; return; }
      rows.push([t_(w.provOO), t_(w.kotaOO), t_(w.kecOO), t_(w.provJNT), t_(w.kotaJNT), t_(w.kecJNT)]);
    });
    if (!rows.length) throw new Error('Belum ada baris yang lengkap (provinsi, kota, kecamatan J&T).');
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, 6).setValues(rows);

    var ubah = reapplyMapping_();
    log_('Simpan Wilayah', rows.length + ' pemetaan');
    return { ok: true, jumlah: rows.length, dilewati: lewat, orderDiperbarui: ubah };
  } finally { lock.releaseLock(); }
}

function reapplyMapping_() {
  var sh = getSS().getSheetByName(CFG.sh.orders);
  var t = readTable_(sh);
  if (!t.rows.length) return 0;
  var area = areaIndex_(), alias = aliasMap_(), wil = wilayahMap_(), prod = produkMap_();
  var bmap = bumpMap_();
  var changed = 0;
  t.rows.forEach(function (r) {
    var st = t_(r['Status Order']);
    if ([CFG.ST.perluMapping, CFG.ST.perluCekKurir, CFG.ST.baru, CFG.ST.pendingStok].indexOf(st) < 0) return;
    var catatan = [];
    if (t_(r['Status Wilayah']) !== 'Valid') {
      var n = normArea_(r['Provinsi OO'], r['Kota OO'], r['Kecamatan OO'], area, alias, wil);
      if (n.ok) { r['Provinsi JNT'] = n.prov; r['Kota JNT'] = n.kota; r['Kecamatan JNT'] = n.kec;
                  r['Status Wilayah'] = 'Valid'; changed++; }
      else catatan.push('Wilayah belum dipetakan');
    }
    if (!t_(r['SKU'])) {
      var pm = produkLookup_(prod, t_(r['product_code']), t_(r['Variation']));
      if (pm) {
        r['SKU'] = pm.sku; r['Nama Barang JNT'] = pm.nama;
        r['Rincian Isi'] = pm.rincian;
        r['Kategori Barang'] = pm.kategori; r['Pcs'] = pm.pcs;
        r['HPP'] = (pm.hpp !== '' && pm.hpp !== undefined && pm.hpp > 0)
          ? pm.hpp * (pm.pcs || 1) : (num_(r['cogs']) === '' ? '' : num_(r['cogs']));
        changed++;
      } else catatan.push('Produk belum dipetakan');
    }
    // bump: isi SKU-nya begitu pemetaannya tersedia
    var bnm = bumpNama_(r['Bump']);
    if (bnm && !t_(r['SKU Bump'])) {
      var bm = bumpLookup_(bmap, bnm);
      if (bm) { r['SKU Bump'] = bm.sku; r['Pcs Bump'] = bm.pcs; changed++; }
      else catatan.push('Bump belum dipetakan: ' + bnm);
    }
    var siap = (t_(r['Status Wilayah']) === 'Valid') && t_(r['SKU']) && (!bnm || t_(r['SKU Bump']));
    if (siap) {
      if (st === CFG.ST.perluMapping)
        r['Status Order'] = /j&t/i.test(t_(r['courier'])) ? CFG.ST.baru : CFG.ST.perluCekKurir;
    } else r['Status Order'] = CFG.ST.perluMapping;
    r['Catatan'] = catatan.join('; ');
  });
  writeTable_(sh, t);
  cacheClear_();
  return changed;
}

function setujuiKurir(orderKeys) {
  me_();
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.orders);
    var t = readTable_(sh);
    var set = {}; (orderKeys || []).forEach(function (x) { set[String(x)] = 1; });
    var n = 0;
    t.rows.forEach(function (r) {
      var key = t_(r['Akun OO']) + '|' + t_(r['order_id']);
      if (set[key] && t_(r['Status Order']) === CFG.ST.perluCekKurir) {
        r['Status Order'] = CFG.ST.baru; r['Catatan'] = 'Kurir disetujui admin'; n++;
      }
    });
    writeTable_(sh, t);
    cacheClear_();
    log_('Setujui Kurir', n + ' order');
    return { ok: true, jumlah: n };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// PENCOCOKAN MIRIP (saran wilayah)
// ---------------------------------------------------------------------------
function nk_(s) { return t_(s).toLowerCase().replace(/[^a-z0-9]/g, ''); }
function lev_(a, b) {
  a = a || ''; b = b || '';
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  var prev = [], cur = [], i, j;
  for (j = 0; j <= b.length; j++) prev[j] = j;
  for (i = 1; i <= a.length; i++) {
    cur[0] = i;
    for (j = 1; j <= b.length; j++) {
      var cost = (a.charAt(i - 1) === b.charAt(j - 1)) ? 0 : 1;
      cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    prev = cur.slice();
  }
  return prev[b.length];
}
function sim_(a, b) {
  a = nk_(a); b = nk_(b);
  if (!a || !b) return 0;
  if (a === b) return 1;
  var s = 1 - (lev_(a, b) / Math.max(a.length, b.length));
  if (a.indexOf(b) >= 0 || b.indexOf(a) >= 0) s = Math.max(s, 0.88);
  return s;
}
function bestMatch_(target, list) {
  var best = { value: '', score: 0 };
  for (var i = 0; i < list.length; i++) {
    var s = sim_(target, list[i]);
    if (s > best.score) best = { value: list[i], score: s };
    if (s === 1) break;
  }
  return best;
}
function areaTree_() {
  var sh = getSS().getSheetByName(CFG.sh.area);
  var tree = {};
  if (!sh || sh.getLastRow() < 2) return tree;
  sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues().forEach(function (r) {
    var p = t_(r[0]), k = t_(r[1]), c = t_(r[2]);
    if (!p || !k || !c) return;
    if (!tree[p]) tree[p] = {};
    if (!tree[p][k]) tree[p][k] = [];
    if (tree[p][k].indexOf(c) < 0) tree[p][k].push(c);
  });
  return tree;
}
function getAreaTree() {
  me_();
  var tree = areaTree_();
  Object.keys(tree).forEach(function (p) {
    Object.keys(tree[p]).forEach(function (k) { tree[p][k].sort(); });
  });
  return tree;
}

/** Saran bertingkat: provinsi → kota (di provinsi itu) → kecamatan (di kota itu). */
function saranWilayah_(provOO, kotaOO, kecOO, tree, alias) {
  var provList = Object.keys(tree);
  if (!provList.length) return { prov: '', kota: '', kec: '', skor: 0 };

  var pT = t_(provOO);
  if (alias[lc_(pT)]) pT = alias[lc_(pT)];
  var pBest = bestMatch_(pT, provList);
  var prov = pBest.value;

  var k0 = t_(kotaOO);
  var kCand = [k0];
  if (/^kota\s+/i.test(k0)) kCand.push(k0.replace(/^kota\s+/i, '').trim());
  if (/^kabupaten\s+/i.test(k0)) kCand.push(k0.replace(/^kabupaten\s+/i, 'Kab. ').trim());

  function bestKota(p) {
    var list = Object.keys(tree[p] || {});
    var b = { value: '', score: 0 };
    kCand.forEach(function (c) { var m = bestMatch_(c, list); if (m.score > b.score) b = m; });
    return b;
  }
  var kBest = bestKota(prov);
  if (kBest.score < 0.95) {   // mungkin kotanya pindah provinsi (pemekaran)
    var alt = { prov: '', value: '', score: kBest.score };
    provList.forEach(function (p) {
      var b = bestKota(p);
      if (b.score > alt.score) alt = { prov: p, value: b.value, score: b.score };
    });
    if (alt.prov && alt.score > kBest.score + 0.05) { prov = alt.prov; kBest = { value: alt.value, score: alt.score }; }
  }
  var kota = kBest.value;

  var c0 = t_(kecOO);
  var cCand = [c0];
  var noParen = c0.replace(/\s*\(.*?\)\s*/g, ' ').trim();
  if (noParen && noParen !== c0) cCand.push(noParen);
  if (noParen.indexOf('/') >= 0) cCand.push(noParen.split('/').pop().trim());
  if (c0.indexOf('/') >= 0) cCand.push(c0.split('/').pop().trim());

  function bestKec(p, k) {
    var list = (tree[p] && tree[p][k]) ? tree[p][k] : [];
    var b = { value: '', score: 0 };
    cCand.forEach(function (c) { var m = bestMatch_(c, list); if (m.score > b.score) b = m; });
    return b;
  }
  var cBest = bestKec(prov, kota);
  if (cBest.score < 0.75) {   // mungkin kabupatennya dipecah
    var bk = kota, bv = cBest.value, bs = cBest.score;
    Object.keys(tree[prov] || {}).forEach(function (k2) {
      var b = bestKec(prov, k2);
      if (b.score > bs) { bk = k2; bv = b.value; bs = b.score; }
    });
    if (bs > cBest.score + 0.1) { kota = bk; cBest = { value: bv, score: bs }; }
  }
  return { prov: prov, kota: kota, kec: cBest.value,
           skor: Math.round(Math.min(pBest.score, cBest.score || 0) * 100) };
}

// ---------------------------------------------------------------------------
// UTIL
// ---------------------------------------------------------------------------
function t_(v) { return (v === null || v === undefined) ? '' : String(v).trim(); }
function lc_(v) { return t_(v).toLowerCase(); }
function squash_(v) { return lc_(v).replace(/\s+/g, ''); }
function num_(v) {
  if (v === null || v === undefined || v === '') return '';
  var n = parseFloat(String(v).replace(/[^0-9.\-]/g, ''));
  return isNaN(n) ? '' : n;
}
function readTable_(sh) {
  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return t_(x); });
  var rows = [];
  if (sh.getLastRow() > 1)
    sh.getRange(2, 1, sh.getLastRow() - 1, header.length).getValues().forEach(function (r) {
      var o = {}; header.forEach(function (h, i) { o[h] = r[i]; });
      rows.push(o);
    });
  return { header: header, rows: rows };
}
function writeTable_(sh, t) {
  if (!t.rows.length) return;
  var vals = t.rows.map(function (o) { return t.header.map(function (h) { return o.hasOwnProperty(h) ? o[h] : ''; }); });
  sh.getRange(2, 1, vals.length, t.header.length).setValues(vals);
}
function readSheet_(b64, filename, hdrRow) {
  hdrRow = hdrRow || 0;
  var bytes = Utilities.base64Decode(b64);
  if (lc_(filename).slice(-4) === '.csv') {
    return toObjects_(Utilities.parseCsv(Utilities.newBlob(bytes).getDataAsString('UTF-8')), hdrRow);
  }
  var blob = Utilities.newBlob(bytes,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename || 'f.xlsx');
  var tmp = driveConvert_(blob);
  try {
    return toObjects_(SpreadsheetApp.openById(tmp.id).getSheets()[0].getDataRange().getValues(), hdrRow);
  } finally { DriveApp.getFileById(tmp.id).setTrashed(true); }
}
function toObjects_(vals, hdrRow) {
  if (!vals || vals.length <= hdrRow) return [];
  var header = vals[hdrRow].map(function (x) { return t_(x); });
  var out = [];
  for (var i = hdrRow + 1; i < vals.length; i++) {
    var o = {}, blank = true;
    for (var j = 0; j < header.length; j++) {
      if (!header[j]) continue;
      o[header[j]] = vals[i][j];
      if (vals[i][j] !== '' && vals[i][j] !== null) blank = false;
    }
    if (!blank) out.push(o);
  }
  return out;
}
function driveConvert_(blob) {
  var name = '__tmp_ao_' + Date.now();
  if (typeof Drive.Files.create === 'function')
    return Drive.Files.create({ name: name, mimeType: MimeType.GOOGLE_SHEETS }, blob, { supportsAllDrives: true });
  return Drive.Files.insert({ title: name, mimeType: MimeType.GOOGLE_SHEETS }, blob, { convert: true });
}
function outFolder_() {
  return CFG.driveFolderId ? DriveApp.getFolderById(CFG.driveFolderId) : DriveApp.getRootFolder();
}

var MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/**
 * Bagikan file hasil ke SEMUA admin terdaftar.
 * Tanpa ini, file batch hanya bisa dibuka oleh admin yang membuatnya
 * (karena web app berjalan atas nama masing-masing admin).
 */
function bagikanKeAdmin_(file) {
  try {
    var users = usersMap_();
    Object.keys(users).forEach(function (k) {
      var u = users[k];
      if (!u.aktif) return;
      try { file.addViewer(u.email); } catch (e) {}
    });
  } catch (e) {}
}

/** Buat xlsx: simpan ke Drive + kembalikan base64 agar bisa auto-download. */
function makeXlsx_(header, rows, filename) {
  var tmp = SpreadsheetApp.create('__tmp_out_' + Date.now());
  try {
    var sh = tmp.getSheets()[0];
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    if (rows.length) sh.getRange(2, 1, rows.length, header.length).setValues(rows);
    SpreadsheetApp.flush();
    var blob = UrlFetchApp.fetch(
      'https://docs.google.com/spreadsheets/d/' + tmp.getId() + '/export?format=xlsx',
      { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() } }).getBlob().setName(filename);
    var file = outFolder_().createFile(blob);
    bagikanKeAdmin_(file);                    // semua admin bisa unduh ulang
    return { name: filename, id: file.getId(), url: file.getUrl(),
             mime: MIME_XLSX, b64: Utilities.base64Encode(blob.getBytes()) };
  } finally { DriveApp.getFileById(tmp.getId()).setTrashed(true); }
}
function makeCsv_(header, rows, filename) {
  var esc = function (v) {
    var s = (v === null || v === undefined) ? '' : String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  var lines = [header.map(esc).join(',')];
  rows.forEach(function (r) { lines.push(r.map(esc).join(',')); });
  var text = lines.join('\r\n');
  var blob = Utilities.newBlob(text, 'text/csv', filename);
  var file = outFolder_().createFile(blob);
  bagikanKeAdmin_(file);                      // semua admin bisa unduh ulang
  return { name: filename, id: file.getId(), url: file.getUrl(),
           mime: 'text/csv', b64: Utilities.base64Encode(Utilities.newBlob(text).getBytes()) };
}
/** Unduh ulang file lama (dari riwayat batch). */
function downloadFile(fileId) {
  me_();
  var f = DriveApp.getFileById(fileId);
  var blob = f.getBlob();
  return { name: f.getName(), mime: blob.getContentType() || MIME_XLSX,
           b64: Utilities.base64Encode(blob.getBytes()) };
}

function log_(aksi, detail) {
  try {
    var sh = getSS().getSheetByName(CFG.sh.log);
    if (!sh) return;
    var email = '', nama = '';
    try {
      email = t_(Session.getActiveUser().getEmail());
      var u = usersMap_()[email.toLowerCase()];
      nama = u ? u.nama : '';
    } catch (e) {}
    sh.appendRow([new Date(), email, nama, aksi, detail]);
  } catch (e) {}
}
/**
 * Kunci cache DIIKAT ke APP_VERSION.
 * Efeknya: begitu versi dinaikkan lalu dideploy, seluruh cache lama otomatis
 * tidak terpakai lagi (kuncinya beda) — tidak perlu dibersihkan manual, dan
 * mustahil kode baru membaca data berformat lama.
 */
function ck_(k) { return 'ao_' + APP_VERSION.split(' ')[0] + '_' + k; }

function cacheGet_(k) {
  try { var v = CacheService.getScriptCache().get(ck_(k)); return v ? JSON.parse(v) : null; } catch (e) { return null; }
}
function cachePut_(k, v) {
  try { CacheService.getScriptCache().put(ck_(k), JSON.stringify(v), 600); } catch (e) {}
  return v;
}
function cacheClear_() {
  try { CacheService.getScriptCache().removeAll([ck_('area')]); } catch (e) {}
}
