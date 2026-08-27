/**
 * ============================================================================
 *  MODUL STOK — Sistem Admin Order (Meika Berkarya)
 *
 *  Konsep: BUKU BESAR MUTASI (STOK_MUTASI) sebagai jejak audit, dan
 *  STOK sebagai saldo berjalan per (SKU × Gudang). Keduanya diperbarui
 *  bersamaan di dalam LockService, jadi selalu konsisten.
 *
 *  HPP: rata-rata bergerak (moving average).
 *    hpp_baru = (stok_lama × hpp_lama + qty_masuk × hpp_masuk) / (stok_lama + qty_masuk)
 *  Jadi setiap pembelian dgn harga berbeda otomatis memperbarui HPP gudang.
 *
 *  Stok KELUAR karena pengiriman dipotong otomatis saat batch J&T dibuat.
 * ============================================================================
 */

var STOK_HEADER = ['SKU', 'Nama Produk', 'Gudang', 'Stok', 'HPP per Pcs'];
var MUTASI_HEADER = ['Waktu', 'Tipe', 'Kategori', 'SKU', 'Nama Produk', 'Gudang',
                     'Gudang Tujuan', 'Qty', 'HPP per Pcs', 'Nilai', 'Ref', 'Catatan', 'Oleh'];

var KAT_MASUK = ['Stok Awal', 'Belanja Supplier', 'Retur Konsumen', 'RTS (Balik ke Gudang)',
                 'Pindah Gudang', 'Koreksi Tambah'];
var KAT_KELUAR = ['Pengiriman', 'Hilang', 'Rusak', 'Pindah Gudang', 'Koreksi Kurang', 'Lainnya'];

// ---------------------------------------------------------------------------
// GUDANG
// ---------------------------------------------------------------------------
var GUDANG_HEADER = ['Kode', 'Nama Gudang', 'Provinsi', 'Aktif'];

function gudangList_() {
  var sh = getSS().getSheetByName(CFG.sh.gudang);
  var out = [];
  if (sh && sh.getLastRow() > 1) {
    var t = readTable_(sh);                    // berbasis nama kolom
    t.rows.forEach(function (r) {
      var k = t_(r['Kode']); if (!k) return;
      var a = lc_(r['Aktif']);
      out.push({ kode: k, nama: t_(r['Nama Gudang']) || k,
                 provinsi: t_(r['Provinsi']),
                 aktif: (a === '' || a === 'ya' || a === 'true' || a === 'aktif') });
    });
  }
  if (!out.length) out.push({ kode: CFG.gudangDefault, nama: 'Gudang Utama',
                              provinsi: '', aktif: true });
  return out;
}
function getGudangList() { me_(); return gudangList_(); }

function simpanGudang(g) {
  me_();
  var kode = t_(g.kode).toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!kode) throw new Error('Kode gudang wajib diisi.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.gudang);
    var t = readTable_(sh);
    var isi = { 'Kode': kode, 'Nama Gudang': t_(g.nama) || kode,
                'Provinsi': t_(g.provinsi), 'Aktif': (g.aktif === false ? 'Tidak' : 'Ya') };
    var idx = -1;
    for (var i = 0; i < t.rows.length; i++)
      if (lc_(t.rows[i]['Kode']) === lc_(kode)) { idx = i; break; }
    if (idx >= 0) {
      Object.keys(isi).forEach(function (k) { if (t.header.indexOf(k) >= 0) t.rows[idx][k] = isi[k]; });
      writeTable_(sh, t);
    } else {
      sh.appendRow(t.header.map(function (h) { return isi.hasOwnProperty(h) ? isi[h] : ''; }));
    }
    log_('Simpan Gudang', kode + ' | ' + isi['Nama Gudang'] + ' | ' + isi['Provinsi']);
    return { ok: true };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// SALDO STOK
// ---------------------------------------------------------------------------
/** Semua baris STOK sebagai objek. */
function stokRows_() {
  var sh = getSS().getSheetByName(CFG.sh.stok);
  var t = readTable_(sh);
  t.rows.forEach(function (r) {
    if (!t_(r['Gudang'])) r['Gudang'] = CFG.gudangDefault;   // data lama tanpa gudang
  });
  return { sh: sh, t: t };
}

/** Saldo per SKU untuk SATU gudang: { sku: {nama, stok, hpp} } */
function stokMap_(gudang) {
  gudang = t_(gudang) || CFG.gudangDefault;
  var m = {};
  stokRows_().t.rows.forEach(function (r) {
    if (lc_(r['Gudang']) !== lc_(gudang)) return;
    var sku = t_(r['SKU']); if (!sku) return;
    m[sku] = { nama: t_(r['Nama Produk']), stok: num_(r['Stok']) || 0, hpp: num_(r['HPP per Pcs']) || 0 };
  });
  return m;
}

/** Saldo gabungan seluruh gudang: { sku: {nama, total, perGudang{}, hpp(avg tertimbang), nilai} } */
function stokTotal_() {
  var m = {};
  stokRows_().t.rows.forEach(function (r) {
    var sku = t_(r['SKU']); if (!sku) return;
    var g = t_(r['Gudang']), q = num_(r['Stok']) || 0, h = num_(r['HPP per Pcs']) || 0;
    if (!m[sku]) m[sku] = { sku: sku, nama: t_(r['Nama Produk']), perGudang: {}, total: 0, nilai: 0 };
    m[sku].perGudang[g] = (m[sku].perGudang[g] || 0) + q;
    m[sku].total += q;
    m[sku].nilai += q * h;
    if (!m[sku].nama) m[sku].nama = t_(r['Nama Produk']);
  });
  Object.keys(m).forEach(function (sku) {
    m[sku].hpp = m[sku].total > 0 ? Math.round(m[sku].nilai / m[sku].total) : 0;
  });
  return m;
}

/**
 * Pastikan SKU terdaftar di STOK (gudang default, stok 0).
 * Penulisan BERBASIS NAMA KOLOM — aman walau urutan kolom sheet berbeda.
 */
function pastikanSku_(sku, nama, hpp) {
  sku = t_(sku);
  if (!sku) return false;
  var s = stokRows_();
  var ada = s.t.rows.some(function (r) { return lc_(r['SKU']) === lc_(sku); });
  if (ada) return false;

  var baru = {};
  s.t.header.forEach(function (h) { baru[h] = ''; });
  baru['SKU'] = sku;
  baru['Nama Produk'] = t_(nama);
  baru['Gudang'] = CFG.gudangDefault;
  baru['Stok'] = 0;
  baru['HPP per Pcs'] = num_(hpp) || 0;
  s.t.rows.push(baru);
  writeTable_(s.sh, s.t);
  return true;
}

/** Versi massal: daftarkan banyak SKU sekaligus (1x baca, 1x tulis). */
function pastikanSkuBatch_(list) {
  if (!list || !list.length) return 0;
  var s = stokRows_();
  var ada = {};
  s.t.rows.forEach(function (r) { if (t_(r['SKU'])) ada[t_(r['SKU']).toUpperCase()] = 1; });

  var n = 0;
  list.forEach(function (x) {
    var sku = t_(x.sku); if (!sku || ada[sku.toUpperCase()]) return;
    var baru = {};
    s.t.header.forEach(function (h) { baru[h] = ''; });
    baru['SKU'] = sku;
    baru['Nama Produk'] = t_(x.nama);
    baru['Gudang'] = CFG.gudangDefault;
    baru['Stok'] = 0;
    baru['HPP per Pcs'] = num_(x.hpp) || 0;
    s.t.rows.push(baru);
    ada[sku.toUpperCase()] = 1;
    n++;
  });
  if (n) writeTable_(s.sh, s.t);
  return n;
}

/**
 * Susun ulang kolom sheet STOK ke urutan baku (SKU | Nama Produk | Gudang | Stok | HPP per Pcs).
 * Aman: data dipindah berdasarkan NAMA kolom, bukan posisi.
 */
function rapikanStok_(sh) {
  var t = readTable_(sh);
  var sama = STOK_HEADER.length === t.header.length &&
             STOK_HEADER.every(function (h, i) { return h === t.header[i]; });
  if (sama) return 0;

  var rows = t.rows
    .filter(function (r) { return t_(r['SKU']); })
    .map(function (r) {
      if (!t_(r['Gudang'])) r['Gudang'] = CFG.gudangDefault;
      return STOK_HEADER.map(function (h) { return r.hasOwnProperty(h) ? r[h] : ''; });
    });
  sh.clear();
  sh.getRange(1, 1, 1, STOK_HEADER.length).setValues([STOK_HEADER]);
  if (rows.length) sh.getRange(2, 1, rows.length, STOK_HEADER.length).setValues(rows);
  sh.setFrozenRows(1);
  return rows.length;
}

/** Jalankan manual dari editor bila urutan kolom STOK terlanjur berantakan. */
function rapikanKolomStok() {
  me_();
  var n = rapikanStok_(getSS().getSheetByName(CFG.sh.stok));
  log_('Rapikan kolom STOK', n + ' baris');
  return 'Kolom STOK dirapikan → ' + STOK_HEADER.join(' | ') + ' (' + n + ' baris)';
}

/** Daftar produk (untuk dropdown modal). */
function getProdukOptions() {
  me_();
  var tot = stokTotal_();
  return Object.keys(tot).sort().map(function (k) {
    return { sku: k, nama: tot[k].nama, stok: tot[k].total, hpp: tot[k].hpp };
  });
}

// ---------------------------------------------------------------------------
// REGISTRY SKU  —  ATURAN: 1 SKU = 1 NAMA PRODUK (tidak boleh ganda)
//
// Masalah yang dicegah: product_code OrderOnline BISA dipakai untuk produk
// berbeda. Kalau dijadikan SKU mentah-mentah, stok dua produk akan tercampur.
// Karena itu SKU ditentukan OLEH SERVER, bukan diketik user.
// ---------------------------------------------------------------------------

/** Kunci pembanding nama produk (abaikan huruf besar/kecil, spasi, tanda baca). */
function namaKey_(s) { return t_(s).toLowerCase().replace(/[^a-z0-9]/g, ''); }

// ---------------------------------------------------------------------------
// NAMA KANONIK — inti solusi "1 barang, banyak nama"
//
// OrderOnline menulis barang yang SAMA dengan format berbeda:
//    "Semprotan Noozle 04"   dan   "(SF - Semprotan Noozle)"
// Barangnya identik, stoknya HARUS 1 SKU. Yang berbeda hanya VARIAN
// (beli 1 / beli 2 gratis 1) — itu memengaruhi "Pcs per Order", BUKAN SKU.
//
// kanonNama_ membuang embel-embel yang tidak mengubah identitas barang:
//   kurung, kode awalan ("SF - "), kata promo, dan nomor urut di belakang.
// ---------------------------------------------------------------------------
var STOPWORD_PROMO = ['promo', 'gratis', 'free', 'bonus', 'diskon', 'murah', 'terlaris',
                      'best seller', 'bestseller', 'new', 'baru', 'paket', 'grosir', 'ready'];

function kanonNama_(s) {
  var x = lc_(s);
  x = x.replace(/[\(\)\[\]\{\}]/g, ' ');                // buang kurung
  x = x.replace(/^\s*[a-z0-9]{1,6}\s*-\s+/, ' ');       // kode awalan: "SF - ", "MB- "
  x = x.replace(/\bbeli\s*\d+\b/g, ' ');                // "beli 2"
  x = x.replace(/\bgratis\s*\d*\b/g, ' ');              // "gratis 1"
  x = x.replace(/\bisi\s*\d+\b/g, ' ');                 // "isi 3"
  x = x.replace(/\b\d+\s*(pcs|pc|pack|pak|set|buah|lusin)\b/g, ' ');
  STOPWORD_PROMO.forEach(function (w) {
    x = x.replace(new RegExp('\\b' + w + '\\b', 'g'), ' ');
  });
  x = x.replace(/[^a-z0-9]+/g, ' ');
  x = x.replace(/\s+\d{1,3}\s*$/, ' ');                 // nomor urut di belakang: "... 04"
  return x.replace(/\s+/g, ' ').trim();
}
function kanonKey_(s) { return kanonNama_(s).replace(/\s/g, ''); }

// ---------------------------------------------------------------------------
// ALIAS NAMA PRODUK -> SKU
// Sekali admin menyatakan "Semprotan Noozle 04" = SKU SN, nama itu dicatat
// sebagai alias. Order berikutnya dengan nama itu langsung ketemu SKU-nya,
// tanpa perlu ditebak lagi.
// ---------------------------------------------------------------------------
var SKUALIAS_HEADER = ['Nama Produk OO', 'SKU', 'Waktu', 'Oleh'];

function aliasSkuRows_() {
  var sh = getSS().getSheetByName(CFG.sh.skualias);
  if (!sh || sh.getLastRow() < 1) return { sh: sh, t: { header: SKUALIAS_HEADER, rows: [] } };
  return { sh: sh, t: readTable_(sh) };
}

/** Tambah alias (lewati yang sudah ada). list: [{nama, sku}] */
function tambahAliasSku_(list) {
  if (!list || !list.length) return 0;
  var a = aliasSkuRows_();
  if (!a.sh) return 0;
  var ada = {};
  a.t.rows.forEach(function (r) { if (t_(r['Nama Produk OO'])) ada[namaKey_(r['Nama Produk OO'])] = 1; });

  var me = me_();
  var now = new Date();
  var baru = [];
  list.forEach(function (x) {
    var nama = t_(x.nama), sku = t_(x.sku);
    if (!nama || !sku) return;
    var k = namaKey_(nama);
    if (ada[k]) return;
    ada[k] = 1;
    baru.push([nama, sku, now, me.nama]);
  });
  if (baru.length)
    a.sh.getRange(a.sh.getLastRow() + 1, 1, baru.length, SKUALIAS_HEADER.length).setValues(baru);
  return baru.length;
}

/**
 * Registry SKU. Sumber kebenaran = sheet STOK, diperkaya sheet REF_SKU_ALIAS.
 *   bySku   : KODE      -> {sku, nama}
 *   byNama  : nama persis-> SKU   (termasuk semua alias)
 *   byKanon : nama kanonik -> SKU (untuk mendeteksi nama beda-format)
 */
function skuRegistry_() {
  var bySku = {}, byNama = {}, byKanon = {}, list = [];
  stokRows_().t.rows.forEach(function (r) {
    var sku = t_(r['SKU']); if (!sku) return;
    var nama = t_(r['Nama Produk']);
    if (!bySku[sku.toUpperCase()]) {
      bySku[sku.toUpperCase()] = { sku: sku, nama: nama };
      list.push({ sku: sku, nama: nama });
    } else if (nama && !bySku[sku.toUpperCase()].nama) {
      bySku[sku.toUpperCase()].nama = nama;
    }
    if (nama && !byNama[namaKey_(nama)]) byNama[namaKey_(nama)] = sku;
    if (nama && !byKanon[kanonKey_(nama)]) byKanon[kanonKey_(nama)] = sku;
  });

  // alias yang sudah dikonfirmasi admin (menang atas tebakan apa pun)
  aliasSkuRows_().t.rows.forEach(function (r) {
    var nama = t_(r['Nama Produk OO']), sku = t_(r['SKU']);
    if (!nama || !sku || !bySku[sku.toUpperCase()]) return;   // alias yatim -> abaikan
    byNama[namaKey_(nama)] = sku;
    if (!byKanon[kanonKey_(nama)]) byKanon[kanonKey_(nama)] = sku;
  });

  list.sort(function (a, b) { return a.sku < b.sku ? -1 : 1; });
  return { bySku: bySku, byNama: byNama, byKanon: byKanon, list: list };
}

function getSkuRegistry() { me_(); return skuRegistry_().list; }

/** Daftar SKU untuk dropdown (kode, nama, stok total). */
function getSkuOptions() {
  me_();
  var tot = stokTotal_();
  return skuRegistry_().list.map(function (x) {
    var s = tot[x.sku];
    return { sku: x.sku, nama: x.nama, stok: s ? s.total : 0 };
  });
}

/**
 * Cari SKU yang MIRIP (bukan sama persis) dengan sebuah nama produk.
 * Dipakai untuk SARAN di layar pemetaan — bukan untuk menggabung otomatis.
 * @return {sku, nama, skor(0-100)} | null
 */
function miripSku_(nama, reg) {
  var k = kanonNama_(nama);
  if (!k) return null;
  reg = reg || skuRegistry_();
  var best = null;
  reg.list.forEach(function (x) {
    var kk = kanonNama_(x.nama);
    if (!kk) return;
    var s = sim_(k, kk);
    if (!best || s > best.skor) best = { sku: x.sku, nama: x.nama, skor: s };
  });
  if (!best) return null;
  best.skor = Math.round(best.skor * 100);
  return best.skor >= 78 ? best : null;
}

// ---------------------------------------------------------------------------
// NORMALISASI ISIAN OTOMATIS (nama label, rincian isi, kategori)
// ---------------------------------------------------------------------------
var AMBANG_SAMA = 93;    // >= ini dianggap barang yang sama (SKU disatukan)

/** Rapikan nama untuk LABEL RESI: buang kurung/kode/promo, Huruf Kapital Tiap Kata. */
function rapikanNama_(s) {
  var k = kanonNama_(s);                    // sudah bersih dari promo, kurung, nomor urut
  if (!k) k = lc_(s).replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
  return k.split(' ').filter(function (w) { return w; })
          .map(function (w) { return w.charAt(0).toUpperCase() + w.substring(1); })
          .join(' ');
}

/** Rincian Isi -> kolom Keterangan resi. "3 pcs Semprotan Noozle (Beli 2 Gratis 1)" */
function rincianIsi_(namaBersih, pcs, variation) {
  pcs = num_(pcs) || 1;
  var v = t_(variation);
  var promo = /gratis|bonus|free/i.test(v) ? ' (' + v + ')' : '';
  return pcs + ' pcs ' + namaBersih + promo;
}

/**
 * Kamus kata-kunci: kata pada NAMA PRODUK -> kata petunjuk yang dicari di NAMA KATEGORI J&T.
 * Ini menjembatani celah semantik: "Gelang Retro" tidak memuat kata "Perhiasan",
 * jadi pencocokan huruf saja tidak akan pernah ketemu.
 * Silakan tambah sendiri sesuai produk Anda.
 */
var KAMUS_KATEGORI = [
  { kata: ['gelang','kalung','cincin','anting','liontin','perhiasan'], petunjuk: ['perhiasan','aksesoris'] },
  { kata: ['jam','arloji'],                                            petunjuk: ['jam','aksesoris'] },
  { kata: ['vacum','vacuum','blender','mixer','kipas','setrika','lampu','led','charger','kabel','powerbank','speaker','earphone','headset'],
    petunjuk: ['elektronik','listrik'] },
  { kata: ['handphone','hp','casing','tempered','holder'],             petunjuk: ['handphone','ponsel','aksesoris'] },
  { kata: ['mobil','motor','ban','oli','wiper','helm','spion','klakson','aspal'],
    petunjuk: ['kendaraan','otomotif','mobil','motor'] },
  { kata: ['sikat','sapu','pel','lap','kain','pembersih','semprotan','spray','noozle','nozzle','selang','keran','kran'],
    petunjuk: ['rumah tangga','kebersihan','peralatan'] },
  { kata: ['panci','wajan','pisau','talenan','sendok','garpu','piring','gelas','termos','dapur'],
    petunjuk: ['dapur','peralatan'] },
  { kata: ['sabun','shampo','sampo','parfum','lotion','krim','serum','bedak','lipstik','masker'],
    petunjuk: ['kosmetik','kecantikan','perawatan'] },
  { kata: ['baju','kaos','celana','jaket','kemeja','daster','hijab','jilbab'], petunjuk: ['pakaian','fashion'] },
  { kata: ['sepatu','sandal'],                                          petunjuk: ['sepatu','alas kaki'] },
  { kata: ['tas','dompet','ransel','koper'],                            petunjuk: ['tas','dompet'] },
  { kata: ['obat','vitamin','suplemen','madu','herbal','masker','termometer'], petunjuk: ['kesehatan','obat'] },
  { kata: ['mainan','boneka','puzzle'],                                 petunjuk: ['mainan'] },
  { kata: ['snack','kopi','teh','minuman','makanan','keripik'],         petunjuk: ['makanan','minuman'] },
  { kata: ['bantal','guling','sprei','selimut','handuk','tirai','karpet'], petunjuk: ['rumah tangga','tekstil'] },
  { kata: ['cukur','pisau cukur','gunting','sisir','kuku'],             petunjuk: ['perawatan','kecantikan'] }
];

/** Cari kategori pada daftar J&T yang namanya memuat salah satu kata petunjuk. */
function kategoriDariPetunjuk_(petunjuk, katList) {
  var best = null;
  katList.forEach(function (kat) {
    var kk = kanonNama_(kat);
    petunjuk.forEach(function (p, i) {
      if (kk.indexOf(kanonNama_(p)) < 0) return;
      // makin awal di daftar petunjuk = makin spesifik; kategori pendek lebih umum
      var skor = 80 - i * 5 - Math.min(15, kk.length / 4);
      if (!best || skor > best.skor) best = { kategori: kat, skor: Math.round(skor) };
    });
  });
  return best;
}

/**
 * Tebak Kategori Barang J&T dari nama produk. Tiga lapis, berhenti di yang pertama cocok:
 *   1. BELAJAR — produk yang SUDAH dipetakan dan namanya mirip -> pakai kategorinya
 *   2. HARFIAH — kata kategori muncul di nama produk (mis. "Sikat Gigi" -> kategori "Sikat Gigi")
 *   3. KAMUS   — kata kunci produk -> kata petunjuk kategori (mis. "Gelang" -> "Perhiasan")
 * Tidak yakin -> '' (dikosongkan; admin yang isi).
 */
function tebakKategori_(nama, katList, terpetakan) {
  if (!katList || !katList.length) return { kategori: '', skor: 0 };
  var kn = kanonNama_(nama);
  if (!kn) return { kategori: '', skor: 0 };

  // 1) belajar dari produk yang sudah dipetakan
  if (terpetakan && terpetakan.length) {
    var b = null;
    terpetakan.forEach(function (x) {
      if (!x.kategori) return;
      var s = Math.round(sim_(kn, kanonNama_(x.nama)) * 100);
      if (s >= 85 && (!b || s > b.skor)) b = { kategori: x.kategori, skor: s };
    });
    if (b) return b;
  }

  // 2) pencocokan harfiah: SELURUH kata kategori harus ada di nama produk.
  //    Sengaja ketat — kalau hanya sebagian ("mobil" saja) hasilnya menyesatkan:
  //    "Vacum Cleaner Mobil" bisa terbaca "Sparepart Mobil" padahal itu elektronik.
  var kata = kn.split(' ').filter(function (w) { return w.length >= 3; });
  var best = { kategori: '', skor: 0 };
  katList.forEach(function (kat) {
    var kw = kanonNama_(kat).split(' ').filter(function (w) { return w.length >= 3; });
    if (!kw.length) return;
    var penuh = kw.every(function (w) {
      return kata.some(function (x) { return x === w || sim_(x, w) >= 0.88; });
    });
    if (!penuh) return;
    var skor = 90 + kw.length;              // kategori makin spesifik = makin yakin
    if (skor > best.skor) best = { kategori: kat, skor: Math.min(99, skor) };
  });
  if (best.kategori) return best;

  // 3) kamus kata kunci -> petunjuk kategori
  var petunjuk = [];
  KAMUS_KATEGORI.forEach(function (e) {
    var kena = e.kata.some(function (w) {
      return kata.some(function (x) { return x === kanonNama_(w) || sim_(x, kanonNama_(w)) >= 0.9; });
    });
    if (kena) petunjuk = petunjuk.concat(e.petunjuk);
  });
  if (petunjuk.length) {
    var k = kategoriDariPetunjuk_(petunjuk, katList);
    if (k) return k;
  }
  return { kategori: '', skor: 0 };
}

/** Produk yang SUDAH dipetakan: [{nama, kategori}] — bahan belajar tebakan kategori. */
function kategoriTerpetakan_() {
  var sh = getSS().getSheetByName(CFG.sh.produk);
  if (!sh || sh.getLastRow() < 2) return [];
  var t = readTable_(sh);
  var out = [];
  t.rows.forEach(function (r) {
    var kat = t_(r['Kategori Barang']);
    var nm = t_(r['Nama Barang JNT']);
    if (kat && nm) out.push({ nama: nm, kategori: kat });
  });
  return out;
}

/**
 * SATU-SATUNYA penentu SKU untuk baris pemetaan produk.
 * Dipakai BERSAMA oleh layar saran (produkBelumDipetakan) dan penyimpanan
 * (simpanProdukBatch) supaya keputusannya PERSIS SAMA.
 *
 * Urutan:
 *   1. sudah pernah diputuskan di daftar yang sama  -> ikut grup itu
 *   2. nama/alias persis                            -> SKU lama
 *   3. nama beda format, barang sama (kanonik)      -> SKU lama
 *   4. mirip >= 93% dengan SKU terdaftar            -> SKU lama
 *   5. mirip >= 93% dengan BARIS LAIN yang juga baru-> ikut SKU baru baris itu
 *   6. benar-benar baru                             -> kode unik baru
 *
 * @param lokal  {} peta keputusan dalam satu daftar/batch (wajib dibagi antar baris)
 */
function saranSkuBaris_(nama, kodeHint, reg, lokal, pending) {
  nama = t_(nama);
  reg = reg || skuRegistry_();
  lokal = lokal || {};
  pending = pending || {};

  var kk = kanonKey_(nama);
  if (kk && lokal[kk]) {
    var g = lokal[kk];
    return { sku: g.sku, nama: g.nama, reused: g.reused, sumber: 'grup', skor: 100 };
  }

  var out;
  var l = nama ? reg.byNama[namaKey_(nama)] : null;
  if (l) {
    out = { sku: l, nama: reg.bySku[l.toUpperCase()].nama || nama, reused: true, sumber: 'nama', skor: 100 };
  } else {
    var k = kk ? reg.byKanon[kk] : null;
    if (k) {
      out = { sku: k, nama: reg.bySku[k.toUpperCase()].nama || nama, reused: true, sumber: 'kanon', skor: 100 };
    } else {
      var m = miripSku_(nama, reg);
      if (m && m.skor >= AMBANG_SAMA) {
        out = { sku: m.sku, nama: m.nama, reused: true, sumber: 'mirip', skor: m.skor };
      } else {
        // bandingkan dengan baris lain di daftar yang sama (belum terdaftar di STOK)
        var kn = kanonNama_(nama), best = null;
        Object.keys(lokal).forEach(function (key) {
          var s = Math.round(sim_(kn, kanonNama_(lokal[key].nama)) * 100);
          if (s >= AMBANG_SAMA && (!best || s > best.skor))
            best = { sku: lokal[key].sku, nama: lokal[key].nama, reused: lokal[key].reused, skor: s };
        });
        if (best) {
          out = { sku: best.sku, nama: best.nama, reused: best.reused, sumber: 'grup', skor: best.skor };
        } else {
          out = { sku: generateSkuUnik_(nama, kodeHint, reg, pending), nama: nama,
                  reused: false, sumber: 'baru', skor: 0, mirip: m || null };
        }
      }
    }
  }
  if (kk) lokal[kk] = { sku: out.sku, nama: out.nama, reused: out.reused };
  return out;
}

/** Bersihkan calon kode: huruf besar, hanya A-Z 0-9. */
function bersihKode_(s) { return t_(s).toUpperCase().replace(/[^A-Z0-9]/g, ''); }

/**
 * Buat kode SKU yang DIJAMIN UNIK.
 * Urutan calon: kode usulan (mis. product_code) -> inisial nama -> potongan nama.
 * Kalau calon sudah dipakai produk LAIN, ditambahkan angka: GR, GR2, GR3, ...
 */
function generateSkuUnik_(nama, hint, reg, pending) {
  reg = reg || skuRegistry_();
  pending = pending || {};
  var terpakai = function (k) {
    return !!reg.bySku[k.toUpperCase()] || !!pending[k.toUpperCase()];
  };

  var kata = t_(nama).toUpperCase().replace(/[^A-Z0-9 ]/g, ' ').split(/\s+/)
               .filter(function (w) { return w; });
  var inisial = kata.map(function (w) { return w.charAt(0); }).join('').substring(0, 5);
  var potong = (kata[0] || 'SKU').substring(0, 4);

  var calon = [];
  var h = bersihKode_(hint);
  if (h) calon.push(h.substring(0, 6));
  if (inisial.length >= 2) calon.push(inisial);
  calon.push(potong);
  calon.push('SKU');

  for (var i = 0; i < calon.length; i++) {
    var base = calon[i];
    if (!base) continue;
    if (!terpakai(base)) { pending[base.toUpperCase()] = 1; return base; }
  }
  // semua calon terpakai -> tambahkan angka pada calon pertama
  var b = calon[0] || 'SKU', n = 2;
  while (terpakai(b + n)) n++;
  pending[(b + n).toUpperCase()] = 1;
  return b + n;
}

/**
 * Tentukan SKU untuk sebuah produk. Ini SATU-SATUNYA pintu penentuan SKU.
 *  - Nama produk sudah ada di registry  -> pakai SKU lama (tidak bikin ganda)
 *  - Nama produk baru                   -> buat kode unik baru
 *  - skuHint (mis. product_code) dipakai HANYA bila belum dipakai produk lain
 */
function resolveSku_(nama, skuHint, reg, pending) {
  reg = reg || skuRegistry_();
  pending = pending || {};
  nama = t_(nama);

  // 1) nama persis sudah dikenal (termasuk alias yang pernah dikonfirmasi admin)
  //    -> pakai SKU-nya. Perbandingan abaikan huruf besar/kecil, spasi, tanda baca.
  var lama = nama ? reg.byNama[namaKey_(nama)] : null;
  if (lama) return { sku: lama, nama: reg.bySku[lama.toUpperCase()].nama || nama,
                     reused: true, konflik: false, sumber: 'nama' };

  // 2) nama BEDA FORMAT tapi barangnya sama ("Semprotan Noozle 04" vs
  //    "(SF - Semprotan Noozle)") -> satukan ke SKU yang sudah ada.
  var kan = nama ? reg.byKanon[kanonKey_(nama)] : null;
  if (kan) return { sku: kan, nama: reg.bySku[kan.toUpperCase()].nama || nama,
                    reused: true, konflik: false, sumber: 'kanon' };

  // 3) kode petunjuk (mis. product_code OrderOnline) sudah terdaftar?
  //    HANYA boleh dipakai ulang kalau NAMA PRODUKNYA SAMA.
  //    Kalau kode itu milik produk LAIN -> KONFLIK: jangan digabung, buat kode baru.
  var hint = bersihKode_(skuHint);
  var konflik = false;
  if (hint && reg.bySku[hint]) {
    var pemilik = reg.bySku[hint];
    if (!nama || namaKey_(pemilik.nama) === namaKey_(nama)) {
      return { sku: pemilik.sku, nama: pemilik.nama || nama, reused: true,
               konflik: false, sumber: 'kode' };
    }
    konflik = true;   // kode sama, produk beda -> WAJIB kode baru
  }

  // 4) produk baru (atau konflik kode) -> kode unik baru
  return { sku: generateSkuUnik_(nama, hint, reg, pending), nama: nama,
           reused: false, konflik: konflik, sumber: konflik ? 'konflik' : 'baru' };
}

/** Pratinjau kode SKU untuk nama produk baru (dipakai front-end, read-only). */
function generateSku(nama) {
  me_();
  var reg = skuRegistry_();
  var lama = reg.byNama[namaKey_(nama)];
  if (lama) return lama;                       // nama sudah ada -> pakai SKU itu
  return generateSkuUnik_(nama, '', reg, {});
}

/**
 * Dipakai modal STOK MASUK saat user mengetik / memilih nama produk.
 * Keputusan "produk lama atau baru" DITENTUKAN SERVER dengan logika yang sama
 * seperti pemetaan produk — jadi mengetik nama tidak lagi berbeda hasilnya
 * dengan memilih dari daftar.
 */
function cekProdukStok(nama) {
  me_();
  nama = t_(nama);
  if (!nama) return { sku: '', nama: '', baru: false, sumber: 'kosong' };

  var reg = skuRegistry_();
  var res = saranSkuBaris_(nama, '', reg, {}, {});      // nama -> alias -> kanonik -> mirip -> baru
  var tot = stokTotal_();
  var s = tot[res.sku];

  return {
    sku: res.sku,
    nama: res.nama || nama,               // nama resmi produk (kalau memakai SKU lama)
    baru: !res.reused,
    sumber: res.sumber,                   // nama | kanon | mirip | baru
    skor: res.skor || 0,
    stok: s ? s.total : 0,
    hpp: s ? s.hpp : 0,
    mirip: res.mirip || null              // kandidat terdekat yang ditolak (< 93%)
  };
}

// ---------------------------------------------------------------------------
// STOK TERKINI (tabel utama)
// ---------------------------------------------------------------------------
/**
 * NILAI JUAL PER PCS tiap SKU — diturunkan dari `product_price` OrderOnline.
 *
 * `product_price` adalah harga SATU ORDER, dan satu order bisa berisi 1, 2, 4 pcs
 * (tergantung varian promo). Jadi harga itu TIDAK bisa langsung dipakai sebagai
 * harga satuan — harus dibagi jumlah pcs order tersebut lebih dulu.
 *
 * Rata-rata yang dipakai = TERTIMBANG:  total rupiah ÷ total pcs.
 *   Contoh: 10 order @1 pcs Rp100.000  +  1 order @4 pcs Rp300.000
 *     -> (1.000.000 + 300.000) / (10 + 4) = Rp92.857 / pcs
 *   Ini mencerminkan harga jual yang BENAR-BENAR terjadi; bundel yang murah
 *   per pcs ikut menekan angkanya sesuai porsi penjualannya. (Kalau memakai
 *   rata-rata biasa dari harga satuan tiap order, bundel besar akan
 *   under-weighted dan nilai jual jadi terlalu optimistis.)
 *
 * @return { SKU: { jual: rp/pcs, order: jumlah order, pcs: total pcs terjual } }
 */
var JUAL_HEADER = ['SKU', 'Jual per Pcs', 'Diupdate Oleh', 'Waktu'];

/** Harga jual yang DIISI MANUAL admin (sheet REF_HARGA_JUAL). Kunci = SKU huruf besar. */
function jualManualMap_() {
  var sh = getSS().getSheetByName(CFG.sh.jual);
  var m = {};
  if (!sh || sh.getLastRow() < 2) return m;
  var t = readTable_(sh);
  t.rows.forEach(function (r) {
    var sku = t_(r['SKU']); if (!sku) return;
    var v = num_(r['Jual per Pcs']);
    if (v === '' || v <= 0) return;
    m[sku.toUpperCase()] = { jual: Math.round(v), oleh: t_(r['Diupdate Oleh']) };
  });
  return m;
}

/**
 * Harga jual per pcs tiap SKU. Dua sumber, MANUAL menang:
 *   1. manual  — diisi admin di tabel Stok (untuk produk yang belum pernah terjual,
 *                atau bila admin ingin memakai harga lain)
 *   2. OO      — rata-rata TERTIMBANG dari product_price OrderOnline (lihat catatan
 *                di jualMapOO_)
 * Kunci peta = SKU huruf besar.
 */
function jualMap_() {
  var m = jualMapOO_();
  var man = jualManualMap_();
  Object.keys(man).forEach(function (k) {
    var oo = m[k];
    m[k] = { jual: man[k].jual, sumber: 'manual', oleh: man[k].oleh,
             jualOO: oo ? oo.jual : 0,                 // pembanding: harga otomatis
             order: oo ? oo.order : 0, pcs: oo ? oo.pcs : 0 };
  });
  return m;
}

/**
 * Harga jual per pcs dari `product_price` OrderOnline.
 *
 * `product_price` adalah harga SATU ORDER, dan satu order bisa berisi 1, 2, 4 pcs
 * (tergantung varian promo). Jadi harga itu TIDAK bisa langsung dipakai sebagai
 * harga satuan — harus dibagi jumlah pcs order tersebut lebih dulu.
 *
 * Rata-rata yang dipakai = TERTIMBANG:  total rupiah ÷ total pcs.
 *   Contoh: 10 order @1 pcs Rp100.000  +  1 order @4 pcs Rp300.000
 *     -> (1.000.000 + 300.000) / (10 + 4) = Rp92.857 / pcs
 *   Ini mencerminkan harga jual yang BENAR-BENAR terjadi; bundel yang murah
 *   per pcs ikut menekan angkanya sesuai porsi penjualannya.
 */
function jualMapOO_() {
  var sh = getSS().getSheetByName(CFG.sh.orders);
  if (!sh || sh.getLastRow() < 2) return {};
  var t = readTable_(sh);
  var acc = {};
  t.rows.forEach(function (r) {
    var sku = t_(r['SKU']); if (!sku) return;
    var harga = num_(r['product_price']);
    var pcs = num_(r['Pcs']) || 1;
    if (harga === '' || harga <= 0 || pcs <= 0) return;
    var k = sku.toUpperCase();
    if (!acc[k]) acc[k] = { rp: 0, pcs: 0, order: 0 };
    acc[k].rp += harga;
    acc[k].pcs += pcs;
    acc[k].order++;
  });
  var m = {};
  Object.keys(acc).forEach(function (k) {
    m[k] = { jual: Math.round(acc[k].rp / acc[k].pcs), sumber: 'oo',
             order: acc[k].order, pcs: acc[k].pcs };
  });
  return m;
}

/**
 * Simpan harga jual manual — BANYAK SKU sekaligus (satu tombol untuk seluruh tabel).
 * Nilai kosong / 0 = hapus override -> harga kembali dihitung otomatis dari OrderOnline.
 * @param {Array<{sku:string, jual:*}>} list
 */
function simpanHargaJual(list) {
  var me = me_();
  if (!list || !list.length) throw new Error('Tidak ada perubahan harga untuk disimpan.');

  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var sh = getSS().getSheetByName(CFG.sh.jual);
    if (!sh) throw new Error('Sheet ' + CFG.sh.jual + ' belum ada — jalankan fungsi setup() sekali.');
    var t = readTable_(sh);

    var idx = {};
    t.rows.forEach(function (r, i) { var s = t_(r['SKU']).toUpperCase(); if (s) idx[s] = i; });

    var now = new Date();
    var disimpan = 0, dihapus = 0, buang = {};

    list.forEach(function (x) {
      var sku = t_(x.sku).toUpperCase(); if (!sku) return;
      var v = num_(x.jual);

      if (v === '' || v <= 0) {                       // dikosongkan -> kembali otomatis
        if (idx.hasOwnProperty(sku)) { buang[idx[sku]] = 1; dihapus++; }
        return;
      }
      v = Math.round(v);
      if (idx.hasOwnProperty(sku)) {
        var r = t.rows[idx[sku]];
        r['Jual per Pcs'] = v; r['Diupdate Oleh'] = me.nama; r['Waktu'] = now;
      } else {
        var baru = {};
        t.header.forEach(function (h) { baru[h] = ''; });
        baru['SKU'] = sku; baru['Jual per Pcs'] = v;
        baru['Diupdate Oleh'] = me.nama; baru['Waktu'] = now;
        t.rows.push(baru);
        idx[sku] = t.rows.length - 1;
      }
      disimpan++;
    });

    if (Object.keys(buang).length)
      t.rows = t.rows.filter(function (_, i) { return !buang[i]; });

    writeTable_(sh, t);
    log_('Update Harga Jual', disimpan + ' SKU diset manual, ' + dihapus + ' dikembalikan ke otomatis');
    cacheClear_();
    return { ok: true, disimpan: disimpan, dihapus: dihapus };
  } finally { lock.releaseLock(); }
}

/**
 * Tambah PRODUK BARU langsung dari tab Stok.
 * Input: nama produk, HPP, harga jual, gudang, (qty awal opsional).
 * SKU dibuat OTOMATIS & unik lewat resolveSku_ (kalau nama persis sudah ada,
 * SKU lama dipakai ulang supaya tidak ganda). Row STOK dibuat di gudang pilihan
 * (qty awal 0 kalau tidak diisi), lalu harga jual manual disimpan bila diisi.
 */
function tambahProdukBaru(nama, hpp, jual, gudang, qty) {
  var me = me_();
  nama = t_(nama);
  if (!nama) throw new Error('Nama produk wajib diisi.');
  hpp = num_(hpp) || 0;
  var q = num_(qty) || 0;
  if (q < 0) throw new Error('Qty awal tidak boleh negatif.');
  gudang = t_(gudang) || CFG.gudangDefault;

  var sku, baru, namaResmi;
  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var reg = skuRegistry_();
    var res = resolveSku_(nama, '', reg, {});     // nama lama -> SKU lama; nama baru -> SKU unik baru
    sku = res.sku; baru = !res.reused; namaResmi = res.nama || nama;

    var s = stokRows_();
    terapkanSaldo_(s.t, sku, namaResmi, gudang, q, hpp, 'MASUK');   // qty 0 pun bikin row + set HPP
    writeTable_(s.sh, s.t);
    if (q > 0) {
      catatMutasi_([[new Date(), 'MASUK', 'Belanja Supplier', sku, namaResmi, gudang, '',
                     q, hpp, q * hpp, '', 'Produk baru', me.nama]]);
    }
    log_('Tambah Produk', sku + ' — ' + namaResmi + (baru ? ' (baru)' : ' (SKU lama dipakai ulang)'));
    cacheClear_();
  } finally { lock.releaseLock(); }

  var jualN = num_(jual) || 0;
  if (jualN > 0) { try { simpanHargaJual([{ sku: sku, jual: jualN }]); } catch (e) {} }

  return { ok: true, sku: sku, nama: namaResmi, baru: baru, stok: q, gudang: gudang, jual: jualN };
}

function getStokTerkini() {
  me_();
  var gud = gudangList_().filter(function (g) { return g.aktif; });
  var tot = stokTotal_();
  var dm = demandMap_();          // kebutuhan order aktif (dari Batch.gs)
  var jm = jualMap_();            // nilai jual per pcs (dari product_price OrderOnline)

  var rows = Object.keys(tot).sort().map(function (sku) {
    var x = tot[sku];
    var butuh = dm.butuh[sku] || 0;
    var kurang = Math.max(0, butuh - x.total);
    var j = jm[sku.toUpperCase()] || null;
    var jual = j ? j.jual : 0;                 // rupiah per pcs
    var nilaiJual = jual * x.total;            // nilai jual seluruh stok SKU ini
    return { sku: sku, nama: x.nama, perGudang: x.perGudang, total: x.total,
             hpp: x.hpp, nilai: x.nilai, butuh: butuh, kurang: kurang,
             budget: kurang * x.hpp,
             jual: jual, nilaiJual: nilaiJual,
             margin: nilaiJual - x.nilai,      // potensi laba kotor bila stok ini terjual
             jualSumber: j ? j.sumber : '',    // 'manual' | 'oo' | '' (belum ada)
             jualOO: j ? (j.sumber === 'manual' ? (j.jualOO || 0) : j.jual) : 0,
             jualOrder: j ? j.order : 0 };     // banyak order jadi dasar harga (kepercayaan angka)
  });
  var ringkas = {
    totalSku: rows.length,
    totalPcs: rows.reduce(function (a, b) { return a + b.total; }, 0),
    totalNilai: rows.reduce(function (a, b) { return a + b.nilai; }, 0),
    totalBudget: rows.reduce(function (a, b) { return a + b.budget; }, 0),
    totalJual: rows.reduce(function (a, b) { return a + b.nilaiJual; }, 0),
    totalMargin: rows.reduce(function (a, b) { return a + b.margin; }, 0),
    tanpaHarga: rows.filter(function (b) { return !b.jual && b.total > 0; }).length
  };
  return { gudang: gud, rows: rows, ringkas: ringkas,
           katMasuk: KAT_MASUK, katKeluar: KAT_KELUAR };
}

// ---------------------------------------------------------------------------
// MUTASI: catat + perbarui saldo (moving average)
// ---------------------------------------------------------------------------
/**
 * Terapkan satu mutasi ke saldo STOK.
 * tipe: 'MASUK' | 'KELUAR'
 */
function terapkanSaldo_(t, sku, nama, gudang, qty, hpp, tipe) {
  var idx = -1;
  for (var i = 0; i < t.rows.length; i++) {
    if (lc_(t.rows[i]['SKU']) === lc_(sku) && lc_(t.rows[i]['Gudang']) === lc_(gudang)) { idx = i; break; }
  }
  if (idx < 0) {
    var baru = {};
    t.header.forEach(function (h) { baru[h] = ''; });
    baru['SKU'] = sku; baru['Nama Produk'] = nama; baru['Gudang'] = gudang;
    baru['Stok'] = 0; baru['HPP per Pcs'] = 0;
    t.rows.push(baru);
    idx = t.rows.length - 1;
  }
  var r = t.rows[idx];
  var lama = num_(r['Stok']) || 0;
  var hppLama = num_(r['HPP per Pcs']) || 0;

  if (tipe === 'MASUK') {
    var baruStok = lama + qty;
    // rata-rata bergerak: hanya bila HPP masuk diisi (> 0)
    if (hpp > 0) {
      r['HPP per Pcs'] = (lama > 0 && hppLama > 0)
        ? Math.round(((lama * hppLama) + (qty * hpp)) / baruStok)
        : Math.round(hpp);
    }
    r['Stok'] = baruStok;
  } else {
    if (lama < qty) throw new Error('Stok ' + sku + ' di gudang ' + gudang +
      ' hanya ' + lama + ' pcs, tidak cukup untuk keluar ' + qty + ' pcs.');
    r['Stok'] = lama - qty;   // HPP tidak berubah saat barang keluar
  }
  if (nama && !t_(r['Nama Produk'])) r['Nama Produk'] = nama;
  return r;
}

function catatMutasi_(list) {
  if (!list.length) return;
  var sh = getSS().getSheetByName(CFG.sh.mutasi);
  sh.getRange(sh.getLastRow() + 1, 1, list.length, MUTASI_HEADER.length).setValues(list);
}

// ---------------------------------------------------------------------------
// STOK MASUK (banyak baris sekaligus)
//   rows: [{ sku, nama, qty, kategori, hpp, gudang, catatan }]
// ---------------------------------------------------------------------------
function stokMasukBatch(rows) {
  var me = me_();
  if (!rows || !rows.length) throw new Error('Belum ada baris yang diisi.');

  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var s = stokRows_();
    var reg = skuRegistry_();      // registry dibaca sekali
    var pending = {};              // kode yang "dipesan" dalam batch ini (cegah kembar)
    var now = new Date();
    var mut = [];
    var hasil = [];

    rows.forEach(function (r, i) {
      var qty = num_(r.qty);
      var hpp = num_(r.hpp) || 0;
      var gudang = t_(r.gudang) || CFG.gudangDefault;
      var kat = t_(r.kategori) || 'Belanja Supplier';
      var namaInput = t_(r.nama);

      if (!namaInput && !t_(r.sku))
        throw new Error('Baris ' + (i + 1) + ': nama produk wajib diisi.');
      if (qty === '' || qty <= 0)
        throw new Error('Baris ' + (i + 1) + ': qty harus lebih dari 0.');

      // SKU DITENTUKAN SERVER — input user hanya dipakai sebagai petunjuk.
      var res = resolveSku_(namaInput, r.sku, reg, pending);
      var sku = res.sku;
      var nama = res.nama || namaInput;

      // daftarkan ke registry lokal supaya baris berikutnya di batch ini konsisten
      if (!reg.bySku[sku.toUpperCase()]) {
        reg.bySku[sku.toUpperCase()] = { sku: sku, nama: nama };
        if (nama) {
          reg.byNama[namaKey_(nama)] = sku;
          reg.byKanon[kanonKey_(nama)] = sku;
        }
      }

      terapkanSaldo_(s.t, sku, nama, gudang, qty, hpp, 'MASUK');
      mut.push([now, 'MASUK', kat, sku, nama, gudang, '', qty, hpp, qty * hpp, '',
                t_(r.catatan), me.nama]);
      hasil.push({ sku: sku, nama: nama, baru: !res.reused });
    });

    writeTable_(s.sh, s.t);
    catatMutasi_(mut);
    log_('Stok Masuk', rows.length + ' baris');
    cacheClear_();
    return { ok: true, jumlah: rows.length, hasil: hasil,
             skuBaru: hasil.filter(function (h) { return h.baru; }).length };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// STOK KELUAR (banyak baris sekaligus)
//   rows: [{ sku, qty, kategori, gudang, gudangTujuan, catatan }]
//   Kategori "Pindah Gudang" -> otomatis membuat KELUAR (asal) + MASUK (tujuan).
// ---------------------------------------------------------------------------
function stokKeluarBatch(rows) {
  var me = me_();
  if (!rows || !rows.length) throw new Error('Belum ada baris yang diisi.');

  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var s = stokRows_();
    var now = new Date();
    var mut = [];

    rows.forEach(function (r, i) {
      var sku = t_(r.sku).toUpperCase();
      var qty = num_(r.qty);
      var kat = t_(r.kategori) || 'Lainnya';
      var gudang = t_(r.gudang) || CFG.gudangDefault;
      var tujuan = t_(r.gudangTujuan);

      if (!sku) throw new Error('Baris ' + (i + 1) + ': SKU kosong.');
      if (qty === '' || qty <= 0) throw new Error('Baris ' + (i + 1) + ' (' + sku + '): qty harus > 0.');
      if (kat === 'Pindah Gudang') {
        if (!tujuan) throw new Error('Baris ' + (i + 1) + ': gudang tujuan wajib diisi untuk pindah gudang.');
        if (lc_(tujuan) === lc_(gudang)) throw new Error('Baris ' + (i + 1) + ': gudang tujuan sama dengan asal.');
      }

      // ambil HPP saat ini (untuk nilai mutasi & bawa ke gudang tujuan)
      var cur = stokMap_(gudang)[sku];
      var hpp = cur ? cur.hpp : 0;
      var nama = cur ? cur.nama : '';

      terapkanSaldo_(s.t, sku, nama, gudang, qty, 0, 'KELUAR');
      mut.push([now, 'KELUAR', kat, sku, nama, gudang, tujuan, qty, hpp, qty * hpp, '',
                t_(r.catatan), me.nama]);

      if (kat === 'Pindah Gudang') {
        terapkanSaldo_(s.t, sku, nama, tujuan, qty, hpp, 'MASUK');   // bawa HPP-nya
        mut.push([now, 'MASUK', 'Pindah Gudang', sku, nama, tujuan, '', qty, hpp, qty * hpp, '',
                  'Pindahan dari ' + gudang, me.nama]);
      }
    });

    writeTable_(s.sh, s.t);
    catatMutasi_(mut);
    log_('Stok Keluar', rows.length + ' baris');
    cacheClear_();
    return { ok: true, jumlah: rows.length };
  } finally { lock.releaseLock(); }
}

/** Dipakai buatBatch(): potong stok karena pengiriman. Dipanggil DI DALAM lock. */
function keluarPengiriman_(s, butuh, gudang, batchId, namaOleh) {
  var now = new Date();
  var mut = [];
  Object.keys(butuh).forEach(function (sku) {
    var qty = butuh[sku];
    var cur = stokMap_(gudang)[sku];
    var hpp = cur ? cur.hpp : 0;
    var nama = cur ? cur.nama : '';
    terapkanSaldo_(s.t, sku, nama, gudang, qty, 0, 'KELUAR');
    mut.push([now, 'KELUAR', 'Pengiriman', sku, nama, gudang, '', qty, hpp, qty * hpp,
              batchId, 'Batch J&T', namaOleh]);
  });
  writeTable_(s.sh, s.t);
  catatMutasi_(mut);
}

// ---------------------------------------------------------------------------
// GABUNG SKU — untuk data yang TERLANJUR pecah
//
// Kasus: "Semprotan Noozle 04" sudah terlanjur jadi SKU SN04, padahal barangnya
// sama dengan SKU SN. Fungsi ini menyatukan keduanya:
//   stok dijumlahkan (HPP rata-rata tertimbang), pemetaan produk & order
//   dialihkan, nama lama disimpan sebagai ALIAS supaya tidak terpecah lagi.
// ---------------------------------------------------------------------------
function previewGabungSku(dari, ke) {
  me_();
  dari = t_(dari); ke = t_(ke);
  if (!dari || !ke) throw new Error('Pilih SKU asal dan SKU tujuan.');
  if (lc_(dari) === lc_(ke)) throw new Error('SKU asal dan tujuan tidak boleh sama.');

  var reg = skuRegistry_();
  var rd = reg.bySku[dari.toUpperCase()], rk = reg.bySku[ke.toUpperCase()];
  if (!rd) throw new Error('SKU ' + dari + ' tidak ditemukan.');
  if (!rk) throw new Error('SKU ' + ke + ' tidak ditemukan.');

  var tot = stokTotal_();
  var a = tot[rd.sku] || { total: 0, hpp: 0, nilai: 0, perGudang: {} };
  var b = tot[rk.sku] || { total: 0, hpp: 0, nilai: 0, perGudang: {} };
  var qty = a.total + b.total;

  var pr = readTable_(getSS().getSheetByName(CFG.sh.produk));
  var nMap = pr.rows.filter(function (r) { return lc_(r['SKU']) === lc_(dari); }).length;
  var or = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var nOrd = or.rows.filter(function (r) { return lc_(r['SKU']) === lc_(dari); }).length;

  return {
    dari: { sku: rd.sku, nama: rd.nama, stok: a.total, hpp: a.hpp, perGudang: a.perGudang },
    ke:   { sku: rk.sku, nama: rk.nama, stok: b.total, hpp: b.hpp, perGudang: b.perGudang },
    hasil: { stok: qty, hpp: qty > 0 ? Math.round((a.nilai + b.nilai) / qty) : 0 },
    mapping: nMap, order: nOrd
  };
}

function gabungSku(dari, ke) {
  var me = me_();
  var pv = previewGabungSku(dari, ke);          // sekaligus validasi
  dari = pv.dari.sku; ke = pv.ke.sku;

  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var ss = getSS();
    var now = new Date();
    var mut = [];

    // 1) STOK — pindahkan saldo per gudang, bawa HPP-nya (rata-rata bergerak)
    var s = stokRows_();
    var barisDari = s.t.rows.filter(function (r) { return lc_(r['SKU']) === lc_(dari); });
    barisDari.forEach(function (r) {
      var g = t_(r['Gudang']) || CFG.gudangDefault;
      var q = num_(r['Stok']) || 0;
      var h = num_(r['HPP per Pcs']) || 0;
      if (q > 0) {
        terapkanSaldo_(s.t, ke, pv.ke.nama, g, q, h, 'MASUK');
        mut.push([now, 'KELUAR', 'Koreksi Kurang', dari, pv.dari.nama, g, '', q, h, q * h,
                  'GABUNG', 'Gabung SKU ' + dari + ' -> ' + ke, me.nama]);
        mut.push([now, 'MASUK', 'Koreksi Tambah', ke, pv.ke.nama, g, '', q, h, q * h,
                  'GABUNG', 'Gabung SKU ' + dari + ' -> ' + ke, me.nama]);
      }
    });
    s.t.rows = s.t.rows.filter(function (r) { return lc_(r['SKU']) !== lc_(dari); });
    writeTable_(s.sh, s.t);
    catatMutasi_(mut);

    // 2) REF_PRODUK — alihkan pemetaan
    var pshe = ss.getSheetByName(CFG.sh.produk);
    var pt = readTable_(pshe);
    var nMap = 0;
    pt.rows.forEach(function (r) {
      if (lc_(r['SKU']) === lc_(dari)) { r['SKU'] = ke; nMap++; }
    });
    if (nMap) writeTable_(pshe, pt);

    // 3) ORDERS — alihkan SKU (riwayat & order aktif ikut benar)
    var oshe = ss.getSheetByName(CFG.sh.orders);
    var ot = readTable_(oshe);
    var nOrd = 0;
    ot.rows.forEach(function (r) {
      if (lc_(r['SKU']) === lc_(dari)) { r['SKU'] = ke; nOrd++; }
    });
    if (nOrd) writeTable_(oshe, ot);

    // 4) ALIAS — arahkan alias lama ke SKU tujuan + daftarkan nama lama sbg alias
    var a = aliasSkuRows_();
    if (a.sh) {
      var ubah = 0;
      a.t.rows.forEach(function (r) { if (lc_(r['SKU']) === lc_(dari)) { r['SKU'] = ke; ubah++; } });
      if (ubah) writeTable_(a.sh, a.t);
    }
    tambahAliasSku_([{ nama: pv.dari.nama, sku: ke }]);

    log_('Gabung SKU', dari + ' -> ' + ke + ' | stok ' + pv.hasil.stok +
         ' pcs, ' + nMap + ' pemetaan, ' + nOrd + ' order');
    cacheClear_();
    return { ok: true, dari: dari, ke: ke, stok: pv.hasil.stok, hpp: pv.hasil.hpp,
             mapping: nMap, order: nOrd };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// RINGKASAN HARI INI + mutasi terakhir
// ---------------------------------------------------------------------------
function getRingkasanStok() {
  me_();
  var sh = getSS().getSheetByName(CFG.sh.mutasi);
  var tz = Session.getScriptTimeZone();
  var hari = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');

  var out = { tanggal: hari,
              masuk: { qty: 0, nilai: 0, byKategori: {} },
              keluar: { qty: 0, nilai: 0, byKategori: {} },
              terakhir: [] };
  if (!sh || sh.getLastRow() < 2) return out;

  var data = sh.getRange(2, 1, sh.getLastRow() - 1, MUTASI_HEADER.length).getValues();
  for (var i = data.length - 1; i >= 0; i--) {
    var r = data[i];
    var w = r[0];
    var tgl = (w instanceof Date) ? Utilities.formatDate(w, tz, 'yyyy-MM-dd') : '';
    var tipe = t_(r[1]), kat = t_(r[2]), qty = num_(r[7]) || 0, nilai = num_(r[9]) || 0;

    if (out.terakhir.length < 25) {
      out.terakhir.push({
        waktu: (w instanceof Date) ? Utilities.formatDate(w, tz, 'dd/MM HH:mm') : t_(w),
        tipe: tipe, kategori: kat, sku: t_(r[3]), nama: t_(r[4]),
        gudang: t_(r[5]), tujuan: t_(r[6]), qty: qty, hpp: num_(r[8]) || 0,
        ref: t_(r[10]), oleh: t_(r[12])
      });
    }
    if (tgl !== hari) continue;
    var b = (tipe === 'MASUK') ? out.masuk : out.keluar;
    b.qty += qty; b.nilai += nilai;
    b.byKategori[kat] = (b.byKategori[kat] || 0) + qty;
  }
  return out;
}
