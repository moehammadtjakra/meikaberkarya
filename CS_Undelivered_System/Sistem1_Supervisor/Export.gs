/**
 * ============================================================================
 *  SISTEM 1 — EXPORT EXCEL (.xlsx)
 *
 *  Supervisor memilih filter (label tracking, status followup, kategori,
 *  provinsi) di modal, lalu file Excel langsung terunduh.
 *
 *  Kenapa .xlsx asli, bukan CSV: header tebal, angka COD terformat, dan lebar
 *  kolom rapi — supervisor bisa langsung memakainya tanpa merapikan dulu.
 *  Caranya: tulis data ke SPREADSHEET SEMENTARA, minta Google meng-export-nya
 *  sebagai xlsx lewat OAuth, ambil byte-nya, lalu spreadsheet sementara dibuang.
 *  Tidak ada file sampah yang tertinggal.
 * ============================================================================
 */

/** Kolom export — data konsumen -> tracking J&T -> progress followup. */
var EXPORT_COLS = [
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

/** Kolom yang diformat sebagai angka (ribuan). */
var EXPORT_NUM_COLS = ['Nilai COD', 'Total Biaya', 'Nilai Produk', 'Jumlah Foto POD'];

/** Opsi dropdown untuk modal export — dari data nyata di sheet. */
function getExportOptions() {
  var o = getFilterOptions();            // sudah punya kategori, status, provinsi, dll.
  var t = bacaMaster_();
  var setL = {};
  t.rows.forEach(function (r) {
    var l = s_(r['Label Tracking']); if (l) setL[l] = 1;
  });
  return {
    label:    Object.keys(setL).sort(),
    followup: RPT.statusFollowup,
    kategori: o.kategori,
    provinsi: o.provinsi
  };
}

/**
 * Export SELURUH baris yang lolos filter (bukan hanya yang tampil di layar).
 * f: { label, followup, kategori, provinsi }  (+ boleh filter lain dari cocokFilter_)
 */
function exportExcel(f) {
  f = f || {};
  var t = bacaMaster_();
  var rows = t.rows.filter(function (r) { return cocokFilter_(r, f); });

  var body = rows.map(function (r) { return barisExport_(r); });
  var hasil = bikinXlsx_('Undelivered_MeikaBerkarya', EXPORT_COLS, body, EXPORT_NUM_COLS);
  logAct('Export Excel', hasil.nama + ' | ' + rows.length + ' baris');
  return hasil;
}

/** Satu baris MASTER -> array selaras EXPORT_COLS. */
function barisExport_(r) {
  var cod = n_(r[RPT.codCol]), ong = n_(r[RPT.ongkirCol]);
  var produk = (cod === '' || ong === '') ? '' : (cod - ong);
  var pods = pods_(r[RPT.cPOD]);
  return [
    s_(r[CFG.keyCol]),
    fmtD_(r[CFG.shipDateCol]),
    s_(r[RPT.penerimaCol]),
    s_(r[RPT.teleponCol]),
    s_(r[CFG.provinceCol]),
    s_(r[RPT.kotaCol]),
    s_(r['Kecamatan Penerima']),
    s_(r['Alamat Penerima']),
    s_(r[RPT.barangCol]),
    isCod2_(r[RPT.codFlagCol], cod) ? 'COD' : 'Non-COD',
    cod === '' ? '' : cod,
    ong === '' ? '' : ong,
    produk,
    s_(r['Status Ekspedisi']),
    s_(r['Label Tracking']),
    s_(r['Kode Tracking']),
    s_(r['Waktu Tracking']),
    s_(r['Keterangan Tracking']),
    s_(r['Alasan Tertunda']),
    s_(r['Kode Alasan']),
    s_(r['Posisi Terakhir']),
    s_(r['Kurir Terakhir']),
    s_(r['Foto Kurir']),            // link jmsfile (bertanda tangan, ~24 jam)
    s_(r['Foto Kurir Drive']),      // salinan permanen di Google Drive
    fmtDT_(r['Cek Terakhir']),
    s_(r[RPT.cPIC]),
    s_(r[RPT.cKat]),
    normFu2_(r[RPT.cFU]),
    s_(r[RPT.cHasil]),
    pods.length,
    pods.join(' | '),
    s_(r[RPT.cCatatan]),
    fmtDT_(r[RPT.cTime]),
    s_(r[RPT.cBy])
  ];
}

/**
 * Bangun file .xlsx dari header + baris. Dipakai bersama oleh export mana pun.
 * Mengembalikan { nama, jumlah, mime, b64 } untuk diunduh di sisi klien.
 */
function bikinXlsx_(namaDasar, header, rows, numCols) {
  var tz = Session.getScriptTimeZone() || 'Asia/Jakarta';
  var stamp = Utilities.formatDate(new Date(), tz, 'yyyyMMdd_HHmm');
  var namaFile = namaDasar + '_' + stamp + '.xlsx';

  // Spreadsheet sementara — dibuang di 'finally', apa pun yang terjadi.
  var tmp = SpreadsheetApp.create('__tmp_export_' + stamp + '_' + Math.floor(Math.random() * 1e6));
  var tmpId = tmp.getId();
  try {
    var sh = tmp.getSheets()[0];
    sh.setName('Export');

    var all = [header].concat(rows.length ? rows : [header.map(function () { return ''; })]);
    sh.getRange(1, 1, all.length, header.length).setValues(all);

    // header: tebal, latar merah J&T, teks putih, dibekukan
    sh.getRange(1, 1, 1, header.length)
      .setFontWeight('bold').setBackground('#9E1B1B').setFontColor('#ffffff');
    sh.setFrozenRows(1);

    // format angka pada kolom nilai
    (numCols || []).forEach(function (nm) {
      var c = header.indexOf(nm);
      if (c >= 0 && rows.length) sh.getRange(2, c + 1, rows.length, 1).setNumberFormat('#,##0');
    });

    // lebar kolom: default sedang, beberapa kolom teks dilebarkan
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
