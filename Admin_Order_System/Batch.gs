/**
 * ============================================================================
 *  BATCH & PERENCANAAN — Sistem Admin Order (Meika Berkarya) [v6]
 *  Fungsi stok pindah ke Stok.gs. Di sini: dashboard, perencanaan FIFO,
 *  pembuatan batch (memotong stok dari GUDANG terpilih), riwayat batch.
 * ============================================================================
 */

function getDashboard() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var by = {}, byAkun = {};
  t.rows.forEach(function (r) {
    var s = t_(r['Status Order']) || '(kosong)';
    by[s] = (by[s] || 0) + 1;
    var a = t_(r['Akun OO']) || '(?)';
    byAkun[a] = (byAkun[a] || 0) + 1;
  });
  return { total: t.rows.length, byStatus: by, byAkun: byAkun };
}

// ---------------------------------------------------------------------------
// KEBUTUHAN STOK SEBUAH ORDER  —  produk UTAMA + BUMP
//
// Satu order bisa memotong DUA SKU: barang utama dan barang bump (bundling
// tambahan dari OrderOnline). Order baru boleh dikirim kalau KEDUANYA cukup —
// kalau bump-nya habis, order tetap Pending Stok. (Kirim tanpa bump = konsumen
// sudah bayar tapi tidak menerimanya.)
//
// Kalau bump kebetulan produk yang SAMA dengan barang utama, kebutuhannya
// menumpuk di SKU yang sama — ditangani otomatis karena dijumlahkan per SKU.
// ---------------------------------------------------------------------------
function kebutuhanOrder_(r) {
  var out = [];
  var sku = t_(r['SKU']);
  if (sku) out.push({ sku: sku, pcs: num_(r['Pcs']) || 1 });
  var bs = t_(r['SKU Bump']);
  if (bs) out.push({ sku: bs, pcs: num_(r['Pcs Bump']) || 1 });
  return out;
}
/** Order muat kalau SELURUH SKU-nya (utama + bump) tersedia di sisa stok. */
function orderMuat_(need, sisa) {
  return need.every(function (x) { return (sisa[x.sku] || 0) >= x.pcs; });
}
function ambilStok_(need, sisa) {
  need.forEach(function (x) { sisa[x.sku] = (sisa[x.sku] || 0) - x.pcs; });
}

// ---------------------------------------------------------------------------
// KEBUTUHAN & ALOKASI
// ---------------------------------------------------------------------------
/**
 * butuh   = total pcs seluruh order aktif (siap + pending) — termasuk bump
 * alokasi = pcs yang tertutup stok gudang terpilih (FIFO)
 * kurang  = butuh - alokasi
 */
function demandMap_(gudang) {
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var stok = stokMap_(gudang);
  var butuh = {}, alokasi = {}, pakai = {};

  var kandidat = [];
  t.rows.forEach(function (r) {
    var s = t_(r['Status Order']), sku = t_(r['SKU']);
    if (!sku) return;
    if (s !== CFG.ST.trackingOK && s !== CFG.ST.retur) {
      pakai[sku] = (pakai[sku] || 0) + 1;
      var bs = t_(r['SKU Bump']);
      if (bs) pakai[bs] = (pakai[bs] || 0) + 1;
    }
    if (s === CFG.ST.baru || s === CFG.ST.pendingStok || s === CFG.ST.siapKirim) {
      if (t_(r['Status Wilayah']) !== 'Valid') return;
      kebutuhanOrder_(r).forEach(function (x) {
        butuh[x.sku] = (butuh[x.sku] || 0) + x.pcs;
      });
      kandidat.push(r);
    }
  });
  kandidat.sort(function (a, b) { return parseTgl_(a['Tanggal Order']) - parseTgl_(b['Tanggal Order']); });

  var sisa = {};
  Object.keys(stok).forEach(function (k) { sisa[k] = stok[k].stok; });
  kandidat.forEach(function (r) {
    var need = kebutuhanOrder_(r);
    if (!orderMuat_(need, sisa)) return;
    ambilStok_(need, sisa);
    need.forEach(function (x) { alokasi[x.sku] = (alokasi[x.sku] || 0) + x.pcs; });
  });
  return { butuh: butuh, alokasi: alokasi, pakai: pakai };
}

/**
 * HPP per pcs tiap SKU:
 *   1) HPP gudang (rata-rata bergerak dari stok masuk)  -> 'gudang'
 *   2) perkiraan dari cogs OrderOnline                   -> 'estimasi'
 */
function hppMap_(gudang) {
  var m = {};
  var sm = stokMap_(gudang);
  Object.keys(sm).forEach(function (sku) {
    if (sm[sku].hpp > 0) m[sku] = { hpp: sm[sku].hpp, sumber: 'gudang' };
  });
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var acc = {};
  t.rows.forEach(function (r) {
    var sku = t_(r['SKU']); if (!sku || m[sku]) return;
    var c = num_(r['cogs']), pcs = num_(r['Pcs']) || 1;
    if (c === '' || c <= 0) return;
    if (!acc[sku]) acc[sku] = { sum: 0, n: 0 };
    acc[sku].sum += (c / pcs); acc[sku].n++;
  });
  Object.keys(acc).forEach(function (sku) {
    m[sku] = { hpp: Math.round(acc[sku].sum / acc[sku].n), sumber: 'estimasi' };
  });
  return m;
}

// ---------------------------------------------------------------------------
// SKEMA URUTAN PEMILIHAN ORDER
//
// Prioritas UTAMA selalu: TRANSFER BANK dulu, baru COD.
//   (paket non-COD sudah dibayar -> risikonya nol, harus jalan lebih dulu)
// Lalu skema yang dipilih admin:
//   'fifo'    -> order paling lama dulu
//   'wilayah' -> paling dekat dari gudang dulu (provinsi sama > sepulau > pulau tetangga)
// ---------------------------------------------------------------------------
var PULAU = {
  'Jawa':        ['Banten','DKI Jakarta','Jawa Barat','Jawa Tengah','Daerah Istimewa Yogyakarta','Jawa Timur'],
  'Sumatera':    ['Aceh','Sumatera Utara','Sumatera Barat','Riau','Kepulauan Riau','Jambi',
                  'Sumatera Selatan','Kepulauan Bangka Belitung','Bengkulu','Lampung'],
  'Kalimantan':  ['Kalimantan Barat','Kalimantan Tengah','Kalimantan Selatan','Kalimantan Timur','Kalimantan Utara'],
  'Sulawesi':    ['Sulawesi Utara','Sulawesi Tengah','Sulawesi Selatan','Sulawesi Tenggara',
                  'Sulawesi Barat','Gorontalo'],
  'BaliNusa':    ['Bali','Nusa Tenggara Barat','Nusa Tenggara Timur'],
  'MalukuPapua': ['Maluku','Maluku Utara','Papua','Papua Barat','Papua Barat Daya',
                  'Papua Pegunungan','Papua Selatan','Papua Tengah']
};
/** Urutan kedekatan antar-pulau, dilihat dari pulau gudang. */
var URUT_PULAU = {
  'Jawa':        ['Jawa','BaliNusa','Sumatera','Kalimantan','Sulawesi','MalukuPapua'],
  'Sumatera':    ['Sumatera','Jawa','Kalimantan','BaliNusa','Sulawesi','MalukuPapua'],
  'Kalimantan':  ['Kalimantan','Jawa','Sulawesi','Sumatera','BaliNusa','MalukuPapua'],
  'Sulawesi':    ['Sulawesi','Kalimantan','MalukuPapua','BaliNusa','Jawa','Sumatera'],
  'BaliNusa':    ['BaliNusa','Jawa','Sulawesi','Kalimantan','Sumatera','MalukuPapua'],
  'MalukuPapua': ['MalukuPapua','Sulawesi','BaliNusa','Jawa','Kalimantan','Sumatera']
};
function pulauDari_(prov) {
  var p = lc_(prov);
  var hasil = '';
  Object.keys(PULAU).forEach(function (k) {
    PULAU[k].forEach(function (x) { if (lc_(x) === p) hasil = k; });
  });
  return hasil;
}
/** Peringkat kedekatan: 0 = provinsi sama, 1 = sepulau, 2+ = pulau makin jauh. */
function rankWilayah_(provOrder, provGudang) {
  if (!provGudang) return 99;
  if (lc_(provOrder) === lc_(provGudang)) return 0;
  var pg = pulauDari_(provGudang), po = pulauDari_(provOrder);
  if (!pg || !po) return 98;
  var urut = URUT_PULAU[pg] || [];
  var i = urut.indexOf(po);
  return (i < 0) ? 97 : (i + 1);
}
/** true bila order dibayar transfer/non-COD (prioritas tertinggi). */
function isTransfer_(r) { return lc_(r['payment_method']) !== 'cod'; }

/** Bandingkan 2 order sesuai skema. */
function bandingOrder_(a, b, skema, provGudang) {
  // 1) transfer bank selalu duluan
  var ta = isTransfer_(a) ? 0 : 1, tb = isTransfer_(b) ? 0 : 1;
  if (ta !== tb) return ta - tb;

  if (skema === 'wilayah') {
    var ra = rankWilayah_(a['Provinsi JNT'], provGudang);
    var rb = rankWilayah_(b['Provinsi JNT'], provGudang);
    if (ra !== rb) return ra - rb;
  }
  // 2) default & tiebreaker: FIFO
  return parseTgl_(a['Tanggal Order']) - parseTgl_(b['Tanggal Order']);
}

// ---------------------------------------------------------------------------
// PERENCANAAN — berdasarkan gudang & skema terpilih
// ---------------------------------------------------------------------------
function getPlanning(gudang, skema) {
  me_();
  gudang = t_(gudang) || CFG.gudangDefault;
  skema = (t_(skema) === 'wilayah') ? 'wilayah' : 'fifo';

  var gList = gudangList_().filter(function (g) { return g.aktif; });
  var gInfo = gList.filter(function (g) { return lc_(g.kode) === lc_(gudang); })[0] || gList[0] || {};
  var provGudang = t_(gInfo.provinsi) || t_(pengirimMap_()['Provinsi Pengirim']);

  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var stok = stokMap_(gudang);
  var hpp = hppMap_(gudang);

  var kandidat = t.rows.filter(function (r) {
    var s = t_(r['Status Order']);
    return (s === CFG.ST.baru || s === CFG.ST.pendingStok || s === CFG.ST.siapKirim) &&
           t_(r['Status Wilayah']) === 'Valid' && t_(r['SKU']);
  });
  kandidat.sort(function (a, b) { return bandingOrder_(a, b, skema, provGudang); });

  var butuh = {}, alokasi = {};
  kandidat.forEach(function (r) {
    kebutuhanOrder_(r).forEach(function (x) { butuh[x.sku] = (butuh[x.sku] || 0) + x.pcs; });
  });

  var sisa = {};
  Object.keys(stok).forEach(function (k) { sisa[k] = stok[k].stok; });

  var sum = { siap: { jumlah: 0, cod: 0, hpp: 0, pcs: 0, transfer: 0 },
              pending: { jumlah: 0, cod: 0, hpp: 0, pcs: 0, transfer: 0 } };

  var list = kandidat.map(function (r) {
    var sku = t_(r['SKU']), pcs = num_(r['Pcs']) || 1;
    var bsku = t_(r['SKU Bump']), bpcs = bsku ? (num_(r['Pcs Bump']) || 1) : 0;
    var need = kebutuhanOrder_(r);

    // muat hanya kalau SEMUA SKU cukup (utama DAN bump)
    var muat = orderMuat_(need, sisa);
    if (muat) { ambilStok_(need, sisa);
                need.forEach(function (x) { alokasi[x.sku] = (alokasi[x.sku] || 0) + x.pcs; }); }

    // SKU mana yang bikin order ini tertahan (buat ditampilkan ke admin)
    var kurangSku = muat ? [] : need.filter(function (x) { return (sisa[x.sku] || 0) < x.pcs; })
                                    .map(function (x) { return x.sku; });

    var cod = num_(r['COD']) || 0;
    var trf = isTransfer_(r);
    var h = (hpp[sku] ? hpp[sku].hpp * pcs : (num_(r['HPP']) || 0)) +
            (bsku && hpp[bsku] ? hpp[bsku].hpp * bpcs : 0);           // HPP bump ikut dihitung
    var b = muat ? sum.siap : sum.pending;
    b.jumlah++; b.cod += cod; b.hpp += h; b.pcs += (pcs + bpcs);
    if (trf) b.transfer++;

    return {
      key: t_(r['Akun OO']) + '|' + t_(r['order_id']),
      order_id: t_(r['order_id']), akun: t_(r['Akun OO']),
      tanggal: t_(r['Tanggal Order']), nama: t_(r['Nama Penerima']),
      wilayah: t_(r['Kecamatan JNT']) + ', ' + t_(r['Kota JNT']),
      provinsi: t_(r['Provinsi JNT']),
      rank: rankWilayah_(r['Provinsi JNT'], provGudang),
      transfer: trf, bayar: trf ? 'Transfer' : 'COD',
      sku: sku, pcs: pcs,
      bump: t_(r['Bump']), bumpSku: bsku, bumpPcs: bpcs,
      cod: cod, hpp: h, muat: muat, kurangSku: kurangSku
    };
  });

  var totalBudget = 0;
  var stokTable = Object.keys(butuh).sort().map(function (sku) {
    var s = stok[sku] ? stok[sku].stok : 0;
    var al = alokasi[sku] || 0;
    var kurangPcs = Math.max(0, butuh[sku] - al);
    var h = hpp[sku] ? hpp[sku].hpp : 0;
    var budget = kurangPcs * h;
    totalBudget += budget;
    return { sku: sku, nama: stok[sku] ? stok[sku].nama : '(belum ada di gudang ini)',
             butuh: butuh[sku], stok: s, alokasi: al, kurang: kurangPcs,
             hpp: h, hppSumber: hpp[sku] ? hpp[sku].sumber : '-',
             budget: budget, cukup: kurangPcs === 0 };
  });

  var blok = { perluMapping: 0, perluCekKurir: 0 };
  t.rows.forEach(function (r) {
    var s = t_(r['Status Order']);
    if (s === CFG.ST.perluMapping) blok.perluMapping++;
    if (s === CFG.ST.perluCekKurir) blok.perluCekKurir++;
  });

  return { gudang: gudang, gudangList: gList, skema: skema, provGudang: provGudang,
           orders: list, stok: stokTable, blok: blok, ringkasan: sum,
           totalBudget: totalBudget, bisaKirim: sum.siap.jumlah };
}

function parseTgl_(v) {
  if (v instanceof Date) return v.getTime();
  var s = t_(v);
  var m = s.match(/(\d{1,2})-(\d{1,2})-(\d{4})(?:\s*-\s*(\d{1,2}):(\d{2}))?/);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0)).getTime();
  var d = new Date(s);
  return isNaN(d.getTime()) ? 0 : d.getTime();
}

// ---------------------------------------------------------------------------
// BUAT BATCH + FILE UPLOAD J&T  (stok dipotong dari gudang terpilih)
// ---------------------------------------------------------------------------
function buatBatch(orderKeys, gudang, skema) {
  var me = me_();
  if (!orderKeys || !orderKeys.length) throw new Error('Belum ada order yang dipilih.');
  gudang = t_(gudang) || CFG.gudangDefault;
  skema = (t_(skema) === 'wilayah') ? 'wilayah' : 'fifo';

  var lock = LockService.getScriptLock(); lock.waitLock(120000);
  try {
    var ss = getSS();
    var shO = ss.getSheetByName(CFG.sh.orders);
    var t = readTable_(shO);
    var pengirim = pengirimMap_();
    var stok = stokMap_(gudang);
    var pilih = {}; orderKeys.forEach(function (x) { pilih[String(x)] = 1; });

    var target = [];
    t.rows.forEach(function (r) {
      var key = t_(r['Akun OO']) + '|' + t_(r['order_id']);
      if (!pilih[key]) return;
      var s = t_(r['Status Order']);
      if ([CFG.ST.diBatch, CFG.ST.dapatAWB, CFG.ST.trackingOK].indexOf(s) >= 0)
        throw new Error('Order ' + r['order_id'] + ' sudah dikirim ke J&T (batch ' + t_(r['Batch ID']) + ').');
      if (t_(r['Status Wilayah']) !== 'Valid') throw new Error('Order ' + r['order_id'] + ': wilayah belum dipetakan.');
      if (!t_(r['SKU'])) throw new Error('Order ' + r['order_id'] + ': produk belum dipetakan.');
      // bump ada tapi SKU-nya belum ditunjuk -> tolak, stoknya tidak bisa dipotong
      if (bumpNama_(r['Bump']) && !t_(r['SKU Bump']))
        throw new Error('Order ' + r['order_id'] + ': bump "' + bumpNama_(r['Bump']) +
                        '" belum dipetakan ke SKU.');
      target.push(r);
    });
    if (!target.length) throw new Error('Tidak ada order valid yang dipilih.');

    // kebutuhan = barang utama + bump
    var butuh = {};
    target.forEach(function (r) {
      kebutuhanOrder_(r).forEach(function (x) { butuh[x.sku] = (butuh[x.sku] || 0) + x.pcs; });
    });
    var kurang = [];
    Object.keys(butuh).forEach(function (sku) {
      var ada = stok[sku] ? stok[sku].stok : 0;
      if (ada < butuh[sku]) kurang.push(sku + ' (butuh ' + butuh[sku] + ', stok ' + ada + ')');
    });
    if (kurang.length) throw new Error('Stok gudang ' + gudang + ' tidak cukup: ' + kurang.join('; '));

    var now = new Date();
    var tz = Session.getScriptTimeZone();
    var batchId = 'B-' + Utilities.formatDate(now, tz, 'yyyyMMdd') + '-' +
                  ('0' + (hitungBatchHariIni_() + 1)).slice(-2);

    var akunSet = {};
    var rows = target.map(function (r) {
      var akun = t_(r['Akun OO']);
      akunSet[akun] = 1;
      var o = {};
      o['Berat'] = num_(r['Berat']) || 1;
      o['Nama Pengirim']     = pengirim['Nama Pengirim'];
      o['Telepon Pengirim']  = pengirim['Telepon Pengirim'];
      o['Provinsi Pengirim'] = pengirim['Provinsi Pengirim'];
      o['Kota Pengirim']     = pengirim['Kota Pengirim'];
      o['Daerah Pengirim']   = pengirim['Daerah Pengirim'];
      o['Alamat Pengirim']   = pengirim['Alamat Pengirim'];
      o['Apakah Dropship?']  = 0;
      o['Nama Penerima']     = t_(r['Nama Penerima']);
      o['Telepon Penerima']  = t_(r['Telepon']);
      o['Provinsi Penerima'] = t_(r['Provinsi JNT']);
      o['Kota Penerima']     = t_(r['Kota JNT']);
      o['Kecamatan']         = t_(r['Kecamatan JNT']);
      o['Alamat Penerima']   = t_(r['Alamat']);
      o['Cara Pembayaran']   = CFG.caraBayar;
      // KUNCI PENCOCOKAN: "<Nama> <AKUN>-<order_id>"
      // JANGAN pakai '#' — J&T mengubahnya jadi ',' di export Url-Tracking.
      // Spasi dan tanda '-' terbukti aman (tidak diubah J&T).
      o['Nama Barang']       = t_(r['Nama Barang JNT']) + ' ' + akun + '-' + t_(r['order_id']);
      o['Kategori Barang']   = t_(r['Kategori Barang']);

      // KETERANGAN: rincian isi paket (acuan tim gudang) + catatan kurir.
      // Label resi J&T hanya mencetak ~20 karakter Nama Barang, jadi detail
      // qty/bonus/bump ditaruh di sini.
      var rincian = t_(r['Rincian Isi']) ||
                    ((num_(r['Pcs']) || 1) + ' pcs ' + t_(r['Produk']));
      // BUMP ikut disebut supaya tim gudang memasukkannya ke paket:
      //   "2 pcs Sikat Punggung + 1 pcs Kunci Gembok Motor - Hubungi penerima"
      var nb = bumpNama_(r['Bump']);
      if (nb) rincian += ' + ' + (num_(r['Pcs Bump']) || 1) + ' pcs ' + nb;
      o['Keterangan'] = rincian + (CFG.noteResi ? ' - ' + CFG.noteResi : '');

      // Nilai Barang = harga produk + harga bump (isi paket sebenarnya).
      // Catatan: kolom product_price di ORDERS sengaja TIDAK ditambahi bump_price,
      // supaya perhitungan harga jual per pcs (jualMapOO_) tidak ikut tercemar.
      o['Nilai Barang']  = (num_(r['product_price']) || 0) + (num_(r['bump_price']) || 0);
      o[' Apakah Input Asuransi? \n'] = CFG.inputAsuransi;  // wajib 0
      o['Jumlah']        = CFG.jumlahKoli;
      o['Jenis Barang']  = CFG.jenisBarang;
      o['Nomor pesanan e-commerce'] = t_(r['order_id']);

      // COD: kosong (bukan 0) untuk order non-COD / transfer bank
      o['COD'] = (t_(r['COD']) === '') ? '' : (num_(r['COD']) || 0);

      o['Jenis Layanan'] = pengirim['Jenis Layanan'] || CFG.layanan;
      return JNT_HEADER.map(function (h) { return o.hasOwnProperty(h) ? o[h] : ''; });
    });

    var file = makeXlsx_(JNT_HEADER, rows, 'Upload_JNT_' + batchId + '.xlsx');

    // potong stok gudang + catat mutasi KELUAR (Pengiriman)
    var s = stokRows_();
    keluarPengiriman_(s, butuh, gudang, batchId, me.nama);

    var totalPcs = 0;
    target.forEach(function (r) {
      r['Status Order'] = CFG.ST.diBatch;
      r['Batch ID'] = batchId;
      r['Waktu Batch'] = now;
      kebutuhanOrder_(r).forEach(function (x) { totalPcs += x.pcs; });   // utama + bump
    });
    writeTable_(shO, t);
    tandaiPending_(shO, gudang, skema);

    ss.getSheetByName(CFG.sh.batch).appendRow(
      [batchId, now, Object.keys(akunSet).join(', '), target.length, totalPcs, 'Dibuat',
       me.nama, me.email, file.id, file.url]);

    log_('Buat Batch', batchId + ' | ' + target.length + ' order | ' + totalPcs + ' pcs | gudang ' + gudang);
    cacheClear_();
    return { ok: true, batchId: batchId, jumlah: target.length, totalPcs: totalPcs, gudang: gudang,
             file: file.name, url: file.url, mime: file.mime, b64: file.b64 };
  } finally { lock.releaseLock(); }
}

function hitungBatchHariIni_() {
  var sh = getSS().getSheetByName(CFG.sh.batch);
  if (!sh || sh.getLastRow() < 2) return 0;
  var hari = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd');
  var n = 0;
  sh.getRange(2, 1, sh.getLastRow() - 1, 1).getValues().forEach(function (r) {
    if (String(r[0]).indexOf('B-' + hari) === 0) n++;
  });
  return n;
}

function tandaiPending_(shO, gudang, skema) {
  skema = (t_(skema) === 'wilayah') ? 'wilayah' : 'fifo';
  var gInfo = gudangList_().filter(function (g) { return lc_(g.kode) === lc_(gudang); })[0] || {};
  var provGudang = t_(gInfo.provinsi) || t_(pengirimMap_()['Provinsi Pengirim']);

  var t = readTable_(shO);
  var stok = stokMap_(gudang);
  var sisa = {}; Object.keys(stok).forEach(function (k) { sisa[k] = stok[k].stok; });
  var kandidat = t.rows.filter(function (r) {
    var s = t_(r['Status Order']);
    return (s === CFG.ST.baru || s === CFG.ST.pendingStok || s === CFG.ST.siapKirim) &&
           t_(r['Status Wilayah']) === 'Valid' && t_(r['SKU']);
  });
  kandidat.sort(function (a, b) { return bandingOrder_(a, b, skema, provGudang); });
  kandidat.forEach(function (r) {
    var need = kebutuhanOrder_(r);                  // utama + bump
    if (orderMuat_(need, sisa)) { ambilStok_(need, sisa); r['Status Order'] = CFG.ST.siapKirim; }
    else r['Status Order'] = CFG.ST.pendingStok;    // salah satu SKU kurang -> tetap pending
  });
  writeTable_(shO, t);
}

function pengirimMap_() {
  var sh = getSS().getSheetByName(CFG.sh.pengirim);
  var m = {};
  if (sh && sh.getLastRow() > 1)
    sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues().forEach(function (r) {
      if (t_(r[0])) m[t_(r[0])] = t_(r[1]);
    });
  return m;
}

function getBatchList() {
  me_();
  var sh = getSS().getSheetByName(CFG.sh.batch);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 10).getValues().map(function (r) {
    return { id: t_(r[0]), waktu: fmtDT_(r[1]), akun: t_(r[2]), jumlah: num_(r[3]), pcs: num_(r[4]),
             status: t_(r[5]), oleh: t_(r[6]), email: t_(r[7]), fileId: t_(r[8]), url: t_(r[9]) };
  }).reverse();
}
function fmtDT_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  return t_(v);
}

function getKategoriList() {
  var sh = getSS().getSheetByName(CFG.sh.kategori);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 1).getValues()
    .map(function (r) { return t_(r[0]); }).filter(function (x) { return x; });
}

function getPerluCekKurir() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  return t.rows.filter(function (r) { return t_(r['Status Order']) === CFG.ST.perluCekKurir; })
    .map(function (r) {
      return { key: t_(r['Akun OO']) + '|' + t_(r['order_id']), order_id: t_(r['order_id']),
               akun: t_(r['Akun OO']), nama: t_(r['Nama Penerima']), produk: t_(r['Produk']),
               courier: t_(r['courier']), cod: num_(r['COD']) || 0, tanggal: t_(r['Tanggal Order']) };
    });
}

function getWilayahBelumDipetakan() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var out = {};
  t.rows.forEach(function (r) {
    if (t_(r['Status Wilayah']) === 'Valid') return;
    var k = t_(r['Provinsi OO']) + '|' + t_(r['Kota OO']) + '|' + t_(r['Kecamatan OO']);
    if (!out[k]) out[k] = { provOO: t_(r['Provinsi OO']), kotaOO: t_(r['Kota OO']),
                            kecOO: t_(r['Kecamatan OO']), jumlah: 0 };
    out[k].jumlah++;
  });
  var list = Object.keys(out).map(function (k) { return out[k]; });
  if (!list.length) return list;
  var tree = areaTree_(), alias = aliasMap_();
  list.forEach(function (w) {
    var s = saranWilayah_(w.provOO, w.kotaOO, w.kecOO, tree, alias);
    w.saranProv = s.prov; w.saranKota = s.kota; w.saranKec = s.kec; w.skor = s.skor;
  });
  return list;
}
