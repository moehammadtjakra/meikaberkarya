/**
 * ============================================================================
 *  ADMIN — Kelola CS & Pemetaan Provinsi (Sistem 1, Meika Berkarya)
 *  Dipakai oleh panel "Kelola CS & Wilayah" di web app.
 *
 *  Sheet:
 *   - Users:           Email | Nama | Peran | Aktif
 *   - Ref_Provinsi_CS: Provinsi | Email CS      (satu provinsi -> satu CS)
 * ============================================================================
 */

// ---------------------------------------------------------------------------
// LOADERS
// ---------------------------------------------------------------------------
function loadUsers(ss) {
  var sh = ss.getSheetByName(CFG.usersSheet);
  var res = { list: [], map: {} };
  if (!sh || sh.getLastRow() < 2) return res;
  var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var ei = h.indexOf('Email'), ni = h.indexOf('Nama'), pi = h.indexOf('Peran'), ai = h.indexOf('Aktif');
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  data.forEach(function (r) {
    var email = String(ei >= 0 ? r[ei] : '').trim();
    if (!email) return;
    var aktifRaw = ai >= 0 ? String(r[ai]).trim().toLowerCase() : '';
    var aktif = (aktifRaw === '' || aktifRaw === 'ya' || aktifRaw === 'true' || aktifRaw === 'aktif');
    var o = { email: email, nama: String(ni >= 0 ? r[ni] : '').trim(),
              peran: (String(pi >= 0 ? r[pi] : '').trim() || 'CS'), aktif: aktif };
    res.list.push(o); res.map[email.toLowerCase()] = o;
  });
  return res;
}

function loadAssignments(ss) {
  var sh = ss.getSheetByName(CFG.mapSheet);
  var res = { list: [], byProv: {} };
  if (!sh || sh.getLastRow() < 2) return res;
  var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var pi = h.indexOf('Provinsi');
  var ei = h.indexOf('Email CS'); if (ei < 0) ei = h.indexOf('Email');
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  data.forEach(function (r) {
    var prov = String(pi >= 0 ? r[pi] : '').trim();
    var email = String(ei >= 0 ? r[ei] : '').trim();
    if (!prov || !email) return;
    var pl = prov.toLowerCase();
    res.list.push({ provinsi: prov, email: email, provLower: pl });
    res.byProv[pl] = email;
  });
  return res;
}

// ---------------------------------------------------------------------------
// DATA UNTUK PANEL ADMIN (rekap beban per CS / provinsi / status)
// ---------------------------------------------------------------------------
function getAdmin() {
  var ss = getSS();
  var u = loadUsers(ss);
  var a = loadAssignments(ss);
  var statuses = [CFG.statusLabel.diantar];

  // rekap per provinsi dari MASTER
  var provStats = {}; // provLower -> {provinsi, byStatus:{}, total}
  var sh = ss.getSheetByName(CFG.masterSheet);
  if (sh && sh.getLastRow() > 1) {
    var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var pi = header.indexOf(CFG.provinceCol), si = header.indexOf('Status Ekspedisi');
    var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    data.forEach(function (r) {
      var prov = String(pi >= 0 ? r[pi] : '').trim() || '(kosong)';
      var pl = prov.toLowerCase();
      var st = String(si >= 0 ? r[si] : '').trim() || '(kosong)';
      if (!provStats[pl]) provStats[pl] = { provinsi: prov, byStatus: {}, total: 0 };
      provStats[pl].byStatus[st] = (provStats[pl].byStatus[st] || 0) + 1;
      provStats[pl].total++;
    });
  }

  var assignMap = {}; a.list.forEach(function (x) { assignMap[x.provLower] = x.email; });

  // rekap per CS
  var csStats = u.list.map(function (us) {
    var provs = a.list.filter(function (x) { return x.email.toLowerCase() === us.email.toLowerCase(); })
      .map(function (x) {
        var ps = provStats[x.provLower] || { provinsi: x.provinsi, byStatus: {}, total: 0 };
        return { provinsi: ps.provinsi, byStatus: ps.byStatus, total: ps.total };
      });
    var totalByStatus = {}, total = 0;
    provs.forEach(function (p) {
      total += p.total;
      statuses.forEach(function (s) { totalByStatus[s] = (totalByStatus[s] || 0) + (p.byStatus[s] || 0); });
    });
    return { email: us.email, nama: us.nama, peran: us.peran, aktif: us.aktif,
             provinces: provs, totalByStatus: totalByStatus, total: total };
  });

  // provinsi di MASTER yg belum dipetakan
  var unassigned = [];
  Object.keys(provStats).forEach(function (pl) {
    if (pl !== '(kosong)' && !assignMap[pl]) unassigned.push(provStats[pl]);
  });
  unassigned.sort(function (a2, b2) { return b2.total - a2.total; });

  // opsi provinsi (union MASTER + yg sudah dipetakan) untuk dropdown
  var allProv = {};
  Object.keys(provStats).forEach(function (pl) { if (pl !== '(kosong)') allProv[pl] = provStats[pl].provinsi; });
  a.list.forEach(function (x) { if (!allProv[x.provLower]) allProv[x.provLower] = x.provinsi; });
  var provinceOptions = Object.keys(allProv).map(function (pl) { return allProv[pl]; }).sort();

  return { statuses: statuses, users: u.list, csStats: csStats,
           unassigned: unassigned, provinceOptions: provinceOptions };
}

// ---------------------------------------------------------------------------
// CRUD USERS
// ---------------------------------------------------------------------------
function saveUser(user) {
  var email = String(user.email || '').trim();
  if (!email || email.indexOf('@') < 0) throw new Error('Email tidak valid.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var ss = getSS();
    var sh = ss.getSheetByName(CFG.usersSheet) || ensureSheet(ss, CFG.usersSheet, ['Email', 'Nama', 'Peran', 'Aktif']);
    var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var ei = h.indexOf('Email'), ni = h.indexOf('Nama'), pi = h.indexOf('Peran'), ai = h.indexOf('Aktif');
    var peran = (String(user.peran || 'CS').trim() || 'CS');
    var aktif = (user.aktif === false) ? 'Tidak' : 'Ya';
    var nama = String(user.nama || '').trim();

    var rowVals = []; rowVals[ei] = email; rowVals[ni] = nama; rowVals[pi] = peran; rowVals[ai] = aktif;
    for (var i = 0; i < h.length; i++) if (rowVals[i] === undefined) rowVals[i] = '';

    // cari existing by email
    var foundRow = -1;
    if (sh.getLastRow() > 1) {
      var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
      for (var r = 0; r < data.length; r++) {
        if (String(data[r][ei]).trim().toLowerCase() === email.toLowerCase()) { foundRow = r + 2; break; }
      }
    }
    if (foundRow > 0) sh.getRange(foundRow, 1, 1, h.length).setValues([rowVals]);
    else sh.appendRow(rowVals);

    logAct('Simpan CS', email + ' (' + peran + ', ' + aktif + ')');
    CacheService.getScriptCache().remove('dash1');
    return { ok: true };
  } finally { lock.releaseLock(); }
}

function deleteUser(email) {
  email = String(email || '').trim();
  if (!email) throw new Error('Email kosong.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var ss = getSS();
    // hapus dari Users
    var sh = ss.getSheetByName(CFG.usersSheet);
    if (sh && sh.getLastRow() > 1) {
      var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
      var ei = h.indexOf('Email');
      var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
      for (var r = data.length - 1; r >= 0; r--) {
        if (String(data[r][ei]).trim().toLowerCase() === email.toLowerCase()) sh.deleteRow(r + 2);
      }
    }
    // hapus semua assignment provinsi milik CS ini
    var msh = ss.getSheetByName(CFG.mapSheet);
    if (msh && msh.getLastRow() > 1) {
      var mh = msh.getRange(1, 1, 1, msh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
      var mei = mh.indexOf('Email CS'); if (mei < 0) mei = mh.indexOf('Email');
      var md = msh.getRange(2, 1, msh.getLastRow() - 1, msh.getLastColumn()).getValues();
      for (var i = md.length - 1; i >= 0; i--) {
        if (String(md[i][mei]).trim().toLowerCase() === email.toLowerCase()) msh.deleteRow(i + 2);
      }
    }
    logAct('Hapus CS', email);
    redistribute();
    return { ok: true };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// ASSIGN / UNASSIGN PROVINSI  (satu provinsi -> satu CS)
// ---------------------------------------------------------------------------
function assignProvince(provinsi, emailCS) {
  provinsi = String(provinsi || '').trim();
  emailCS = String(emailCS || '').trim();
  if (!provinsi || !emailCS) throw new Error('Provinsi & CS wajib diisi.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var ss = getSS();
    var sh = ss.getSheetByName(CFG.mapSheet) || ensureSheet(ss, CFG.mapSheet, ['Provinsi', 'Email CS']);
    var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
    var pi = h.indexOf('Provinsi'); var ei = h.indexOf('Email CS'); if (ei < 0) ei = h.indexOf('Email');
    // upsert by provinsi (unik)
    var foundRow = -1;
    if (sh.getLastRow() > 1) {
      var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
      for (var r = 0; r < data.length; r++) {
        if (String(data[r][pi]).trim().toLowerCase() === provinsi.toLowerCase()) { foundRow = r + 2; break; }
      }
    }
    var rowVals = []; rowVals[pi] = provinsi; rowVals[ei] = emailCS;
    for (var i = 0; i < h.length; i++) if (rowVals[i] === undefined) rowVals[i] = '';
    if (foundRow > 0) sh.getRange(foundRow, 1, 1, h.length).setValues([rowVals]);
    else sh.appendRow(rowVals);

    logAct('Assign provinsi', provinsi + ' -> ' + emailCS);
    var res = redistribute();
    return { ok: true, updated: res.updated };
  } finally { lock.releaseLock(); }
}

function unassignProvince(provinsi) {
  provinsi = String(provinsi || '').trim();
  if (!provinsi) throw new Error('Provinsi kosong.');
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var ss = getSS();
    var sh = ss.getSheetByName(CFG.mapSheet);
    if (sh && sh.getLastRow() > 1) {
      var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
      var pi = h.indexOf('Provinsi');
      var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
      for (var r = data.length - 1; r >= 0; r--) {
        if (String(data[r][pi]).trim().toLowerCase() === provinsi.toLowerCase()) sh.deleteRow(r + 2);
      }
    }
    logAct('Unassign provinsi', provinsi);
    var res = redistribute();
    return { ok: true, updated: res.updated };
  } finally { lock.releaseLock(); }
}

// ---------------------------------------------------------------------------
// RE-DISTRIBUSI: set ulang PIC CS seluruh MASTER dari pemetaan terbaru
// ---------------------------------------------------------------------------
function redistribute() {
  var ss = getSS();
  var provMap = loadProvinceMap(ss); // provLower -> label
  var sh = ss.getSheetByName(CFG.masterSheet);
  if (!sh || sh.getLastRow() < 2) { CacheService.getScriptCache().remove('dash1'); return { updated: 0 }; }
  var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (x) { return String(x).trim(); });
  var pi = header.indexOf(CFG.provinceCol), pic = header.indexOf('PIC CS');
  if (pi < 0 || pic < 0) return { updated: 0 };
  var rng = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn());
  var data = rng.getValues(), n = 0;
  data.forEach(function (r) {
    var label = provMap[String(r[pi]).trim().toLowerCase()] || '';
    if (r[pic] !== label) { r[pic] = label; n++; }
  });
  rng.setValues(data);
  CacheService.getScriptCache().remove('dash1');
  return { updated: n };
}
