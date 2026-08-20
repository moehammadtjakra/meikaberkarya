/**
 * ============================================================================
 *  HANDOVER RESI HARIAN — Sistem Admin Order (Meika Berkarya)
 *
 *  Dokumen serah-terima paket ke kurir J&T saat pickup.
 *
 *  Pengelompokan  : per TANGGAL BATCH (kapan paket disiapkan/dibatch).
 *  Cakupan        : semua order yang SUDAH punya No. Waybill — termasuk yang
 *                   belakangan retur, karena paketnya memang benar-benar
 *                   diserahkan hari itu. Dokumen handover = catatan historis;
 *                   isinya tidak boleh berubah gara-gara status paket berubah
 *                   di kemudian hari.
 *  Nilai Barang   : sama persis dengan yang dikirim ke J&T
 *                   (product_price + bump_price).
 *
 *  PDF dibuat dari HTML lalu dikonversi (Utilities.newBlob(...).getAs(PDF)) —
 *  tidak butuh library tambahan.
 * ============================================================================
 */

var HO = {
  // tata letak PDF (contoh dokumen Anda: 4 kelompok kolom x 20 baris = 80 resi/halaman)
  barisPerKolom: 20,
  kolomPerHalaman: 4,

  ekspedisi: 'JNT',
  gudang: 'GUDANG MEIKA JAYA ABADI',
  ttdNama: 'Wasrip',
  ttdJabatan: 'Kepala Administrasi Gudang'
};

var HARI_ID = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
var BULAN_ID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];

/** "Jumat, 17 Jul 2026" */
function tglPanjang_(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  return HARI_ID[d.getDay()] + ', ' + d.getDate() + ' ' + BULAN_ID[d.getMonth()] + ' ' + d.getFullYear();
}
function tglKunci_(d) {
  return Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}
/** 'yyyy-MM-dd' -> Date lokal (tanpa jam), aman dari geser zona waktu */
function dariKunci_(s) {
  var m = String(s || '').match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}
/** Nilai Barang sebuah order — HARUS sama dengan yang dikirim ke resi J&T. */
function nilaiBarangOrder_(r) {
  return (num_(r['product_price']) || 0) + (num_(r['bump_price']) || 0);
}

// ---------------------------------------------------------------------------
// DAFTAR HANDOVER PER HARI
// ---------------------------------------------------------------------------
function getHandoverList() {
  me_();
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var g = {};

  t.rows.forEach(function (r) {
    if (!t_(r['No. Waybill'])) return;                 // belum ada resi -> belum bisa diserahkan
    var d = parseTgl_(r['Waktu Batch']);
    if (!d) return;
    var dt = new Date(d);
    var k = tglKunci_(dt);
    if (!g[k]) g[k] = { tanggal: k, label: tglPanjang_(dt), jumlah: 0, nilai: 0, akun: {} };
    g[k].jumlah++;
    g[k].nilai += nilaiBarangOrder_(r);
    var a = t_(r['Akun OO']); if (a) g[k].akun[a] = (g[k].akun[a] || 0) + 1;
  });

  return Object.keys(g).sort().reverse().map(function (k) {      // terbaru di atas
    var x = g[k];
    x.akunTxt = Object.keys(x.akun).sort().map(function (a) { return a + ': ' + x.akun[a]; }).join(' · ');
    delete x.akun;
    return x;
  });
}

/** Detail resi satu tanggal (untuk pratinjau ikon mata). */
function getHandoverDetail(tanggal) {
  me_();
  var rows = ambilResiTanggal_(tanggal);
  return {
    tanggal: tanggal,
    label: tglPanjang_(dariKunci_(tanggal)),
    jumlah: rows.length,
    nilai: rows.reduce(function (a, b) { return a + b.nilai; }, 0),
    rows: rows
  };
}

/** Ambil resi pada satu tanggal batch, urut sesuai waktu batch lalu nomor resi. */
function ambilResiTanggal_(tanggal) {
  var t = readTable_(getSS().getSheetByName(CFG.sh.orders));
  var out = [];
  t.rows.forEach(function (r) {
    var awb = t_(r['No. Waybill']); if (!awb) return;
    var d = parseTgl_(r['Waktu Batch']); if (!d) return;
    if (tglKunci_(new Date(d)) !== tanggal) return;
    out.push({
      resi: awb,
      nilai: nilaiBarangOrder_(r),
      order_id: t_(r['order_id']),
      akun: t_(r['Akun OO']),
      penerima: t_(r['Nama Penerima']),
      kota: t_(r['Kota JNT']),
      status: t_(r['Status Order']),
      batch: t_(r['Batch ID']),
      _urut: d
    });
  });
  out.sort(function (a, b) { return (a._urut - b._urut) || (a.resi < b.resi ? -1 : 1); });
  out.forEach(function (x) { delete x._urut; });
  return out;
}

// ---------------------------------------------------------------------------
// PDF HANDOVER
// ---------------------------------------------------------------------------
/**
 * @param {string} tanggal        kunci grup 'yyyy-MM-dd' (tanggal batch)
 * @param {string} tanggalPickup  'yyyy-MM-dd' — tanggal pickup yang dipilih admin
 */
function buatHandoverPdf(tanggal, tanggalPickup) {
  var me = me_();
  var rows = ambilResiTanggal_(tanggal);
  if (!rows.length) throw new Error('Tidak ada resi pada tanggal tersebut.');

  var dPick = dariKunci_(tanggalPickup) || dariKunci_(tanggal);
  var html = htmlHandover_(rows, dPick);

  var nama = 'Handover_JNT_' + Utilities.formatDate(dPick, Session.getScriptTimeZone(), 'yyyyMMdd') +
             '_' + rows.length + 'resi.pdf';
  var blob = Utilities.newBlob(html, MimeType.HTML, 'handover.html').getAs(MimeType.PDF).setName(nama);

  log_('Cetak Handover', nama + ' | ' + rows.length + ' resi | pickup ' + tanggalPickup);
  return { nama: nama, mime: MimeType.PDF, jumlah: rows.length,
           nilai: rows.reduce(function (a, b) { return a + b.nilai; }, 0),
           b64: Utilities.base64Encode(blob.getBytes()) };
}

function rupiah_(v) {
  var x = Math.round(Number(v) || 0);
  var s = String(Math.abs(x)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return 'Rp ' + s + ',00';
}
function esc_(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Susun HTML handover. Otomatis berhalaman: tiap halaman memuat
 * kolomPerHalaman x barisPerKolom resi, dan SETIAP halaman punya blok tanda tangan.
 */
function htmlHandover_(rows, dPick) {
  var perHal = HO.barisPerKolom * HO.kolomPerHalaman;
  var totalHal = Math.max(1, Math.ceil(rows.length / perHal));
  var totalNilai = rows.reduce(function (a, b) { return a + b.nilai; }, 0);

  var css =
    '<style>' +
    '@page{size:A4 portrait;margin:12mm 10mm;}' +
    'body{font-family:Arial,Helvetica,sans-serif;font-size:9pt;color:#000;margin:0;}' +
    '.hal{page-break-after:always;}' +
    '.hal:last-child{page-break-after:auto;}' +
    'h1{font-size:17pt;margin:0 0 1mm;letter-spacing:1px;}' +
    '.sub{font-size:9.5pt;font-weight:bold;margin:0 0 3mm;}' +
    '.meta{font-size:9pt;margin-bottom:3mm;}' +
    '.meta td{padding:0.6mm 0;}' +
    '.meta td.k{width:33mm;}' +
    '.meta td.t{width:3mm;}' +
    'table.data{border-collapse:collapse;width:100%;font-size:8pt;}' +
    'table.data th,table.data td{border:0.4pt solid #333;padding:1mm 1.2mm;}' +
    'table.data th{background:#e8e8e8;font-size:7.5pt;text-align:center;}' +
    '.no{width:6%;text-align:right;}' +
    '.resi{width:11%;text-align:right;}' +
    '.nilai{width:8%;text-align:right;white-space:nowrap;}' +
    '.kosong{background:#fafafa;}' +
    '.tot{margin-top:3mm;font-size:9pt;}' +
    '.tot td{padding:0.8mm 0;}' +
    '.tot td.k{width:33mm;} .tot td.t{width:3mm;} .tot b{font-size:10pt;}' +
    '.ttd{width:100%;margin-top:8mm;border-collapse:collapse;}' +
    '.ttd td{width:33.33%;vertical-align:top;font-size:8.5pt;padding:0 3mm;}' +
    '.ttd .judul{margin-bottom:1mm;}' +
    '.ttd .org{font-weight:bold;}' +
    '.ttd .ruang{height:20mm;}' +
    '.ttd .garis{border-top:0.6pt solid #000;padding-top:1mm;}' +
    '.ttd .nama{font-weight:bold;}' +
    '.hno{text-align:right;font-size:7.5pt;color:#555;margin-top:2mm;}' +
    '</style>';

  var out = ['<html><head><meta charset="utf-8">', css, '</head><body>'];

  for (var h = 0; h < totalHal; h++) {
    var mulai = h * perHal;
    var isi = rows.slice(mulai, mulai + perHal);

    out.push('<div class="hal">');
    out.push('<h1>HANDOVER</h1>');
    out.push('<div class="sub">BACK-UP DATA PEMERIKSAAN &amp; PERHITUNGAN</div>');
    out.push('<table class="meta">' +
      '<tr><td class="k">TANGGAL PICK UP</td><td class="t">:</td><td><b>' +
        esc_(tglPanjang_(dPick)) + '</b></td></tr>' +
      '<tr><td class="k">EKSPEDISI</td><td class="t">:</td><td>' + esc_(HO.ekspedisi) + '</td></tr>' +
      '</table>');

    out.push(tabelResi_(isi, mulai));

    // total hanya di halaman TERAKHIR supaya tidak membingungkan
    if (h === totalHal - 1) {
      out.push('<table class="tot">' +
        '<tr><td class="k">Total Resi</td><td class="t">:</td><td><b>' + rows.length +
          ' Resi</b></td></tr>' +
        '<tr><td class="k">Total Nilai Barang</td><td class="t">:</td><td><b>' +
          rupiah_(totalNilai) + '</b></td></tr>' +
        '</table>');
    } else {
      out.push('<table class="tot"><tr><td class="k">Resi di halaman ini</td><td class="t">:</td>' +
        '<td><b>' + isi.length + ' Resi</b> (' + rupiah_(isi.reduce(function (a, b) { return a + b.nilai; }, 0)) +
        ')</td></tr></table>');
    }

    // blok tanda tangan — ada di SETIAP halaman
    out.push('<table class="ttd">' +
      '<tr>' +
        '<td><div class="judul">Disetujui Oleh</div><div class="org">' + esc_(HO.gudang) + '</div></td>' +
        '<td><div class="judul">Diketahui Oleh,</div></td>' +
        '<td><div class="judul">Diperiksa Oleh,</div></td>' +
      '</tr>' +
      '<tr><td class="ruang"></td><td class="ruang"></td><td class="ruang"></td></tr>' +
      '<tr>' +
        '<td class="garis"><span class="nama">' + esc_(HO.ttdNama) + '</span><br>' +
          esc_(HO.ttdJabatan) + '</td>' +
        '<td class="garis">Supervisi Ekspedisi</td>' +
        '<td class="garis">Kurir</td>' +
      '</tr></table>');

    out.push('<div class="hno">Halaman ' + (h + 1) + ' dari ' + totalHal + '</div>');
    out.push('</div>');
  }

  out.push('</body></html>');
  return out.join('');
}

/**
 * Tabel resi bergaya dokumen Anda: beberapa KELOMPOK kolom bersebelahan,
 * dibaca dari atas ke bawah per kelompok (1-20, 21-40, 41-60, 61-80).
 * Kelompok yang kosong tetap digambar agar lebarnya rapi.
 */
function tabelResi_(isi, offset) {
  var bpk = HO.barisPerKolom;
  var nKol = Math.max(1, Math.min(HO.kolomPerHalaman, Math.ceil(isi.length / bpk)));

  var th = '<tr>';
  for (var c = 0; c < nKol; c++) {
    th += '<th class="no">NO</th><th class="resi">NOMOR RESI</th><th class="nilai">Nilai Barang</th>';
  }
  th += '</tr>';

  var tb = '';
  for (var b = 0; b < bpk; b++) {
    tb += '<tr>';
    for (var k = 0; k < nKol; k++) {
      var i = k * bpk + b;
      var x = isi[i];
      if (x) {
        tb += '<td class="no">' + (offset + i + 1) + '</td>' +
              '<td class="resi">' + esc_(x.resi) + '</td>' +
              '<td class="nilai">' + rupiah_(x.nilai) + '</td>';
      } else {
        tb += '<td class="no kosong"></td><td class="resi kosong"></td><td class="nilai kosong"></td>';
      }
    }
    tb += '</tr>';
  }
  return '<table class="data">' + th + tb + '</table>';
}
