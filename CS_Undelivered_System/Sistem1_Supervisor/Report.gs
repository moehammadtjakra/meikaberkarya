/**
 * ============================================================================
 *  SISTEM 1 — SUPERVISOR: PERFORMA FOLLOWUP TIM CS   (READ-ONLY)
 *
 *  Supervisor bisa melihat:
 *   1. Ringkasan tim         — beban, penyelesaian, bukti POD, uang berisiko
 *   2. Produktivitas harian  — matriks CS x tanggal (berapa resi difollowup/hari)
 *   3. Kualitas per CS       — %selesai, %ada POD, klaim kurir yang dibantah
 *   4. Integritas klaim kurir— silang KATEGORI MASALAH (kata kurir)
 *                              vs HASIL POD PEMBANDING (kata konsumen)
 *   5. Detail per resi       — sampai foto POD & catatan CS, bisa diexport CSV
 *
 *  Modul ini TIDAK PERNAH menulis ke MASTER. Supervisor hanya membaca.
 *  Sumber angka harian: Log_Aktivitas (aksi "Followup") yang ditulis Sistem 2.
 * ============================================================================
 */

var RPT = {
  // kolom kerja CS (nama kolom sama persis dengan Sistem 2)
  cPIC: 'PIC CS', cFU: 'Status Followup', cKat: 'Kategori Masalah',
  cHasil: 'Hasil Konfirmasi',                 // label UI: Hasil POD Pembanding
  cPOD: 'Link POD Pembanding', cCatatan: 'Catatan CS',
  cTime: 'Timestamp Update', cBy: 'Diupdate Oleh',

  codCol: 'Nilai COD', ongkirCol: 'Total Biaya', codFlagCol: 'COD',
  penerimaCol: 'Penerima', teleponCol: 'Telepon Penerima',
  kotaCol: 'Kota Penerima', barangCol: 'Nama Barang',

  statusFollowup: ['Belum Followup', 'Dalam Proses', 'No Respon',
                   'Tidak Dapat Dihubungi', 'Selesai'],

  // hasil POD yang membantah klaim kurir -> indikasi klaim tidak valid
  hasilKlaimTidakValid: [
    'Penerima membantah minta retur (klaim kurir tidak benar)',
    'Penerima belum dihubungi kurir'
  ],
  hasilReturValid: ['Penerima konfirmasi minta retur/cancel'],
  hasilSelamat: [
    'Penerima siap menerima paket',
    'Penerima minta jadwal tertentu',
    'Penerima sudah menerima paket',
    'Penerima membantah minta retur (klaim kurir tidak benar)',
    'Alamat diperbaiki penerima'
  ],
  hasilHilang: ['Penerima konfirmasi minta retur/cancel'],

  // kategori masalah yang berupa KLAIM kurir (dasar hitung integritas)
  prefixKlaimKurir: 'Kurir klaim',

  maxDetail: 500          // batas baris tabel detail di layar
};

// ---------------------------------------------------------------------------
// PILIHAN FILTER (untuk mengisi dropdown di layar)
// ---------------------------------------------------------------------------
function getFilterOptions() {
  var ss = getSS();
  var out = { cs: [], status: [], kategori: [], hasil: [], provinsi: [],
              bulanIni: rentangBulanIni_() };

  var u = loadUsers(ss);
  out.cs = u.list
    .filter(function (x) { return x.aktif !== false; })
    .map(function (x) { return { email: x.email, nama: x.nama || x.email }; })
    .sort(function (a, b) { return a.nama < b.nama ? -1 : 1; });

  var t = bacaMaster_();
  if (!t.rows.length) {
    out.status = [CFG.statusLabel.diantar];
    return out;
  }
  var setK = {}, setH = {}, setS = {}, setP = {};
  t.rows.forEach(function (r) {
    var k = s_(r[RPT.cKat]);   if (k) setK[k] = 1;
    var h = s_(r[RPT.cHasil]); if (h) setH[h] = 1;
    var st = s_(r['Status Ekspedisi']); if (st) setS[st] = 1;
    var p = s_(r[CFG.provinceCol]);     if (p) setP[p] = 1;
  });
  out.kategori = Object.keys(setK).sort();
  out.hasil    = Object.keys(setH).sort();
  out.status   = Object.keys(setS).sort();
  out.provinsi = Object.keys(setP).sort();
  return out;
}

/** Rentang bawaan: tanggal 1 bulan berjalan s/d hari ini. */
function rentangBulanIni_() {
  var tz = Session.getScriptTimeZone();
  var now = new Date();
  var awal = new Date(now.getFullYear(), now.getMonth(), 1);
  return { dari: Utilities.formatDate(awal, tz, 'yyyy-MM-dd'),
           sampai: Utilities.formatDate(now, tz, 'yyyy-MM-dd') };
}

// ---------------------------------------------------------------------------
// LAPORAN PERFORMA (agregat)
//   f: { dari, sampai, cs, status, kategori, hasil, pod, provinsi, q }
// ---------------------------------------------------------------------------
function getPerforma(f) {
  f = f || {};
  var tz = Session.getScriptTimeZone();
  var per = periode_(f, tz);

  var t = bacaMaster_();
  var users = loadUsers(getSS());
  var namaOf = function (email) {
    var u = users.map[String(email || '').toLowerCase()];
    return (u && u.nama) ? u.nama : String(email || '');
  };

  var out = {
    periode: per,
    ringkas: { total: 0, belum: 0, proses: 0, selesai: 0, pctSelesai: 0,
               pod: 0, pctPod: 0, terverifikasi: 0, klaimTidakValid: 0, pctTidakValid: 0,
               returTerkonfirmasi: 0, nilaiCOD: 0, nilaiProduk: 0,
               nilaiSelamat: 0, nilaiHilang: 0, belumTerdistribusi: 0 },
    aging: { '0–1 hari': 0, '2–3 hari': 0, '4–7 hari': 0, '> 7 hari': 0 },
    byKategori: [], byHasil: [], byStatus: [],
    silang: [],                 // integritas: kategori klaim kurir x hasil POD
    perCS: [], matriks: { hari: per.hari, rows: [], totalHari: [] },
    daily: [], sumberHarian: '—',
    jumlahDetail: 0
  };

  var today = new Date();
  var rows = t.rows.filter(function (r) { return cocokFilter_(r, f); });
  out.jumlahDetail = rows.length;

  var pic = {};   // nama CS -> statistik beban & kualitas
  var kat = {}, hasil = {}, status = {}, silang = {};

  rows.forEach(function (r) {
    var R = out.ringkas;
    R.total++;

    var fu = normFu2_(r[RPT.cFU]);
    if (fu === 'Belum Followup') R.belum++;
    else if (fu === 'Selesai') R.selesai++;
    else R.proses++;

    var st = s_(r['Status Ekspedisi']) || '(kosong)';
    status[st] = (status[st] || 0) + 1;

    var k = s_(r[RPT.cKat]);
    if (k) kat[k] = (kat[k] || 0) + 1;

    var cod = n_(r[RPT.codCol]);
    var ong = n_(r[RPT.ongkirCol]);
    var produk = (cod === '' || ong === '') ? 0 : (cod - ong);
    R.nilaiCOD += (cod === '' ? 0 : cod);
    R.nilaiProduk += produk;

    var h = s_(r[RPT.cHasil]);
    if (h) {
      hasil[h] = (hasil[h] || 0) + 1;
      R.terverifikasi++;
      if (RPT.hasilKlaimTidakValid.indexOf(h) >= 0) R.klaimTidakValid++;
      if (RPT.hasilReturValid.indexOf(h) >= 0) R.returTerkonfirmasi++;
      if (RPT.hasilSelamat.indexOf(h) >= 0) R.nilaiSelamat += produk;
      if (RPT.hasilHilang.indexOf(h) >= 0) R.nilaiHilang += produk;
    }

    // silang: hanya untuk kategori yang berupa KLAIM kurir
    if (k && k.indexOf(RPT.prefixKlaimKurir) === 0) {
      if (!silang[k]) silang[k] = { kategori: k, total: 0, dibantah: 0, dikonfirmasi: 0,
                                    lain: 0, belumCek: 0 };
      silang[k].total++;
      if (!h) silang[k].belumCek++;
      else if (RPT.hasilKlaimTidakValid.indexOf(h) >= 0) silang[k].dibantah++;
      else if (RPT.hasilReturValid.indexOf(h) >= 0) silang[k].dikonfirmasi++;
      else silang[k].lain++;          // hasil lain (mis. penerima siap terima) — bukan sengketa
    }

    var adaPod = pods_(r[RPT.cPOD]).length > 0;
    if (adaPod) R.pod++;

    var nm = s_(r[RPT.cPIC]);
    if (!nm) R.belumTerdistribusi++;
    else {
      if (!pic[nm]) pic[nm] = { nama: nm, total: 0, belum: 0, proses: 0, selesai: 0,
                                pod: 0, verif: 0, dibantah: 0, nilaiCOD: 0 };
      var P = pic[nm];
      P.total++;
      if (fu === 'Belum Followup') P.belum++;
      else if (fu === 'Selesai') P.selesai++;
      else P.proses++;
      if (adaPod) P.pod++;
      if (h) { P.verif++; if (RPT.hasilKlaimTidakValid.indexOf(h) >= 0) P.dibantah++; }
      P.nilaiCOD += (cod === '' ? 0 : cod);
    }

    // aging: hanya yang belum difollowup
    if (fu === 'Belum Followup') {
      var base = d_(r['Tanggal Update Status']) || d_(r[CFG.shipDateCol]);
      var d = base ? Math.floor((today - base) / 86400000) : 0;
      if (d <= 1) out.aging['0–1 hari']++;
      else if (d <= 3) out.aging['2–3 hari']++;
      else if (d <= 7) out.aging['4–7 hari']++;
      else out.aging['> 7 hari']++;
    }
  });

  var R = out.ringkas;
  R.pctSelesai    = R.total ? Math.round(R.selesai / R.total * 100) : 0;
  R.pctPod        = R.total ? Math.round(R.pod / R.total * 100) : 0;
  R.pctTidakValid = R.terverifikasi ? Math.round(R.klaimTidakValid / R.terverifikasi * 100) : 0;

  out.byKategori = urut_(kat);
  out.byHasil    = urut_(hasil);
  out.byStatus   = urut_(status);
  out.silang = Object.keys(silang).map(function (x) {
    var s = silang[x];
    s.pctDibantah = (s.dibantah + s.dikonfirmasi)
      ? Math.round(s.dibantah / (s.dibantah + s.dikonfirmasi) * 100) : 0;
    return s;
  }).sort(function (a, b) { return b.total - a.total; });

  // ---------- produktivitas harian dari Log_Aktivitas ----------
  var prod = produktivitas_(per, tz, namaOf, f);
  out.daily = prod.daily;
  out.sumberHarian = prod.sumber;

  // gabungkan ke tabel per CS
  Object.keys(prod.perCS).forEach(function (nm) {
    if (!pic[nm]) pic[nm] = { nama: nm, total: 0, belum: 0, proses: 0, selesai: 0,
                              pod: 0, verif: 0, dibantah: 0, nilaiCOD: 0 };
  });
  Object.keys(pic).forEach(function (nm) {
    var P = pic[nm];
    var dmap = prod.perCS[nm] || {};
    P.perHari = per.hari.map(function (d) { return dmap[d.d] || 0; });
    P.fuPeriode = P.perHari.reduce(function (a, b) { return a + b; }, 0);
    P.hariAktif = P.perHari.filter(function (x) { return x > 0; }).length;
    P.rerata = per.hari.length ? Math.round(P.fuPeriode / per.hari.length * 10) / 10 : 0;
    P.pctSelesai = P.total ? Math.round(P.selesai / P.total * 100) : 0;
    P.pctPod     = P.total ? Math.round(P.pod / P.total * 100) : 0;
  });

  out.perCS = Object.keys(pic).map(function (k2) { return pic[k2]; })
    .sort(function (a, b) { return b.fuPeriode - a.fuPeriode || b.total - a.total; });

  out.matriks.rows = out.perCS.map(function (P) {
    return { nama: P.nama, perHari: P.perHari, total: P.fuPeriode,
             hariAktif: P.hariAktif, rerata: P.rerata };
  });
  out.matriks.totalHari = per.hari.map(function (_, i) {
    return out.matriks.rows.reduce(function (a, r) { return a + (r.perHari[i] || 0); }, 0);
  });

  return out;
}

/** Produktivitas harian: 1 resi per CS per hari dihitung SEKALI. */
function produktivitas_(per, tz, namaOf, f) {
  var out = { daily: [], perCS: {}, sumber: 'log aktivitas' };
  var sh = getSS().getSheetByName(CFG.logSheet);
  var perDay = {}, perCSDay = {}, seen = {};
  var csFilter = String((f && f.cs) || '').toLowerCase();

  if (sh && sh.getLastRow() > 1) {
    var data = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues();
    data.forEach(function (r) {
      var t = (r[0] instanceof Date) ? r[0] : new Date(r[0]);
      if (isNaN(t.getTime())) return;
      var ds = Utilities.formatDate(t, tz, 'yyyy-MM-dd');
      if (ds < per.dari || ds > per.sampai) return;
      if (String(r[2] || '').indexOf('Followup') < 0) return;      // hanya aksi followup

      var email = String(r[1] || '').trim().toLowerCase();
      if (csFilter && email !== csFilter) return;
      var key = (String(r[3] || '').split('|')[0] || '').trim();   // detail: "<resi> | klaim: ..."
      var uk = ds + '|' + email + '|' + key;
      if (seen[uk]) return;
      seen[uk] = 1;

      perDay[ds] = (perDay[ds] || 0) + 1;
      var nm = namaOf(email) || email;
      if (!perCSDay[nm]) perCSDay[nm] = {};
      perCSDay[nm][ds] = (perCSDay[nm][ds] || 0) + 1;
    });
  }

  // fallback bila Log_Aktivitas belum terisi: pakai Timestamp Update di MASTER
  if (!Object.keys(perDay).length) {
    out.sumber = 'perkiraan (dari Timestamp Update)';
    bacaMaster_().rows.forEach(function (r) {
      var t = d_(r[RPT.cTime]); if (!t) return;
      var ds = Utilities.formatDate(t, tz, 'yyyy-MM-dd');
      if (ds < per.dari || ds > per.sampai) return;
      var nm = s_(r[RPT.cPIC]); if (!nm) return;
      perDay[ds] = (perDay[ds] || 0) + 1;
      if (!perCSDay[nm]) perCSDay[nm] = {};
      perCSDay[nm][ds] = (perCSDay[nm][ds] || 0) + 1;
    });
  }

  out.daily = per.hari.map(function (d) { return { d: d.d, label: d.label, n: perDay[d.d] || 0 }; });
  out.perCS = perCSDay;
  return out;
}

// ---------------------------------------------------------------------------
// DETAIL PER RESI (read-only) — sampai foto POD & catatan CS
// ---------------------------------------------------------------------------
function getDetailFollowup(f, page, size) {
  f = f || {};
  page = Math.max(1, parseInt(page || 1, 10));
  size = Math.min(200, Math.max(10, parseInt(size || 25, 10)));

  var t = bacaMaster_();
  var rows = t.rows.filter(function (r) { return cocokFilter_(r, f); });

  rows.sort(function (a, b) {
    var ta = d_(a[RPT.cTime]), tb = d_(b[RPT.cTime]);
    return (tb ? tb.getTime() : 0) - (ta ? ta.getTime() : 0);   // terbaru dulu
  });

  var total = rows.length;
  var mulai = (page - 1) * size;
  var hal = rows.slice(mulai, mulai + size).map(mapDetail_);

  return { total: total, page: page, size: size,
           halaman: Math.max(1, Math.ceil(total / size)), rows: hal };
}

function mapDetail_(r) {
  var cod = n_(r[RPT.codCol]), ong = n_(r[RPT.ongkirCol]);
  return {
    waybill:  s_(r[CFG.keyCol]),
    tglKirim: fmtD_(r[CFG.shipDateCol]),
    penerima: s_(r[RPT.penerimaCol]),
    telepon:  s_(r[RPT.teleponCol]),
    provinsi: s_(r[CFG.provinceCol]),
    kota:     s_(r[RPT.kotaCol]),
    barang:   s_(r[RPT.barangCol]),
    status:   s_(r['Status Ekspedisi']),
    cod:      (cod === '' ? 0 : cod),
    produk:   (cod === '' || ong === '') ? 0 : (cod - ong),
    isCod:    isCod2_(r[RPT.codFlagCol], cod),
    pic:      s_(r[RPT.cPIC]),
    kategori: s_(r[RPT.cKat]),
    followup: normFu2_(r[RPT.cFU]),
    hasil:    s_(r[RPT.cHasil]),
    catatan:  s_(r[RPT.cCatatan]),
    pods:     pods_(r[RPT.cPOD]),
    waktu:    fmtDT_(r[RPT.cTime]),
    oleh:     s_(r[RPT.cBy])
  };
}

/** Export CSV dari SELURUH baris yang lolos filter (bukan hanya halaman aktif). */
function exportDetailCsv(f) {
  var t = bacaMaster_();
  var rows = t.rows.filter(function (r) { return cocokFilter_(r, f || {}); }).map(mapDetail_);

  var head = ['No. Waybill', 'Tanggal Pengiriman', 'Penerima', 'Telepon', 'Provinsi', 'Kota',
              'Nama Barang', 'Status Ekspedisi', 'COD/Non-COD', 'Nilai COD', 'Nilai Produk',
              'PIC CS', 'Kategori Masalah (klaim kurir)', 'Status Followup',
              'Hasil POD Pembanding (kata konsumen)', 'Jumlah Foto POD', 'Link Foto POD',
              'Catatan CS', 'Waktu Update', 'Diupdate Oleh'];

  var lines = [head.map(csv_).join(',')];
  rows.forEach(function (r) {
    lines.push([r.waybill, r.tglKirim, r.penerima, r.telepon, r.provinsi, r.kota, r.barang,
      r.status, (r.isCod ? 'COD' : 'Non-COD'), r.cod, r.produk, r.pic, r.kategori, r.followup,
      r.hasil, r.pods.length, r.pods.join(' | '), r.catatan, r.waktu, r.oleh
    ].map(csv_).join(','));
  });

  var tz = Session.getScriptTimeZone();
  var nama = 'Followup_CS_' + Utilities.formatDate(new Date(), tz, 'yyyyMMdd_HHmm') + '.csv';
  logAct('Export Detail Followup', nama + ' | ' + rows.length + ' baris');

  // ﻿ = BOM, supaya Excel membaca UTF-8 dengan benar
  return { nama: nama, jumlah: rows.length,
           b64: Utilities.base64Encode('﻿' + lines.join('\r\n'), Utilities.Charset.UTF_8) };
}

// ---------------------------------------------------------------------------
// HELPER
// ---------------------------------------------------------------------------
/** Baca MASTER sekali sebagai objek per nama kolom (aman thd urutan kolom). */
function bacaMaster_() {
  var sh = getSS().getSheetByName(CFG.masterSheet);
  if (!sh || sh.getLastRow() < 2) return { header: [], rows: [] };
  var header = renameHead_(sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function (x) { return String(x).trim(); }));
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var rows = data.map(function (r) {
    var o = {};
    header.forEach(function (h, i) { if (h) o[h] = r[i]; });
    return o;
  });
  return { header: header, rows: rows };
}

function periode_(f, tz) {
  var def = rentangBulanIni_();
  var dari = String(f.dari || def.dari);
  var sampai = String(f.sampai || def.sampai);
  if (dari > sampai) { var x = dari; dari = sampai; sampai = x; }

  var hari = [];
  var d0 = new Date(dari + 'T00:00:00');
  var d1 = new Date(sampai + 'T00:00:00');
  var maks = 62;                                  // batas kolom matriks
  for (var d = new Date(d0); d <= d1 && hari.length < maks; d.setDate(d.getDate() + 1)) {
    hari.push({ d: Utilities.formatDate(d, tz, 'yyyy-MM-dd'),
                label: Utilities.formatDate(d, tz, 'dd/MM') });
  }
  return { dari: dari, sampai: sampai, hari: hari, jumlahHari: hari.length };
}

/** Filter baris MASTER. Filter tanggal HANYA berlaku bila "periode" dicentang. */
function cocokFilter_(r, f) {
  if (f.cs) {
    // f.cs berisi EMAIL; PIC CS berisi NAMA -> cocokkan lewat Users
    var nm = namaCs_(f.cs);
    if (s_(r[RPT.cPIC]).toLowerCase() !== String(nm).toLowerCase()) return false;
  }
  if (f.status   && s_(r['Status Ekspedisi']) !== f.status) return false;
  if (f.provinsi && s_(r[CFG.provinceCol])    !== f.provinsi) return false;
  if (f.kategori && s_(r[RPT.cKat])           !== f.kategori) return false;
  if (f.hasil    && s_(r[RPT.cHasil])         !== f.hasil) return false;
  if (f.followup && normFu2_(r[RPT.cFU])      !== f.followup) return false;

  // Label tracking J&T. "__kosong" = resi yang belum pernah dicek trackingnya.
  if (f.label) {
    var lab = s_(r['Label Tracking']);
    if (f.label === '__kosong') { if (lab) return false; }
    else if (lab !== f.label) return false;
  }

  if (f.pod === 'ada'   && pods_(r[RPT.cPOD]).length === 0) return false;
  if (f.pod === 'tidak' && pods_(r[RPT.cPOD]).length > 0) return false;

  if (f.pakaiPeriode) {
    var t = d_(r[RPT.cTime]);
    if (!t) return false;
    var ds = Utilities.formatDate(t, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    var per = periode_(f, Session.getScriptTimeZone());
    if (ds < per.dari || ds > per.sampai) return false;
  }

  if (f.q) {
    var q = String(f.q).toLowerCase();
    var blob = [r[CFG.keyCol], r[RPT.penerimaCol], r[RPT.teleponCol], r[RPT.barangCol],
                r[RPT.cCatatan], r[CFG.provinceCol], r[RPT.kotaCol]]
      .map(function (x) { return String(x == null ? '' : x).toLowerCase(); }).join(' ');
    if (blob.indexOf(q) < 0) return false;
  }
  return true;
}

var _namaCsCache = null;
function namaCs_(email) {
  if (!_namaCsCache) {
    _namaCsCache = {};
    var u = loadUsers(getSS());
    u.list.forEach(function (x) { _namaCsCache[String(x.email).toLowerCase()] = x.nama || x.email; });
  }
  return _namaCsCache[String(email).toLowerCase()] || email;
}

function urut_(obj) {
  return Object.keys(obj).map(function (k) { return { k: k, n: obj[k] }; })
    .sort(function (a, b) { return b.n - a.n; });
}
function pods_(v) {
  if (v === null || v === undefined || v === '') return [];
  return String(v).split(/[\n,;\s]+/).map(function (s) { return s.trim(); })
    .filter(function (s) { return s.indexOf('http') === 0; });
}
function normFu2_(v) {
  var s = String(v == null ? '' : v).trim();
  return s === '' ? 'Belum Followup' : s;
}
function isCod2_(flag, nilai) {
  var f = String(flag == null ? '' : flag).trim().toUpperCase();
  if (f) {
    if (f === 'Y' || f === 'YA' || f === 'TRUE' || f === '1') return true;
    if (f === 'N' || f === 'TIDAK' || f === 'FALSE' || f === '0') return false;
    if (f.indexOf('NON') >= 0) return false;
    if (f.indexOf('COD') >= 0) return true;
  }
  return (nilai !== '' && Number(nilai) > 0);
}
function s_(v) { return String(v == null ? '' : v).trim(); }
function n_(v) {
  if (v === null || v === undefined || v === '') return '';
  var x = Number(String(v).replace(/[^\d.-]/g, ''));
  return isNaN(x) ? '' : x;
}
function d_(v) {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  var m = String(v).match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  var d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
}
function fmtD_(v) {
  var d = d_(v);
  return d ? Utilities.formatDate(d, Session.getScriptTimeZone(), 'dd/MM/yyyy') : s_(v);
}
function fmtDT_(v) {
  var d = d_(v);
  return d ? Utilities.formatDate(d, Session.getScriptTimeZone(), 'dd/MM/yyyy HH:mm') : '';
}
function csv_(v) {
  var s = String(v == null ? '' : v).replace(/"/g, '""');
  return '"' + s + '"';
}
