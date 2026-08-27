/**
 * ============================================================================
 *  META ADS LOADER — Meika Berkarya  (tab "Meta Ads" di Data Loader)
 *
 *  Menarik report iklan Meta (Facebook/Instagram) via Marketing API untuk
 *  SELURUH ad account di Business Manager (token yang bisa mengaksesnya), lalu
 *  menuliskannya ke sheet `Meta-Ads` — lengkap dengan nama Business Manager &
 *  Ad Account, data campaign, dan metrik per hari.
 *
 *  Alur:
 *   1. /me/adaccounts -> daftar semua ad account + Business Manager-nya.
 *   2. Per akun: /insights (level=campaign, time_increment=1) untuk rentang
 *      tanggal pilihan user -> spend, impresi, klik, CPC, CPM, purchase, ATC, LPV.
 *   3. /campaigns -> budget + status (snapshot).
 *   4. Nama campaign DIBERSIHKAN lalu DICOCOKKAN ke "Nama Barang JNT"
 *      (petaProdukKanonik_ dari Order.gs — sumber kebenaran yang sama dengan
 *      dashboard OrderOnline). Hasil pelabelan disimpan di `Ref_Ads_Map`:
 *      sekali dikunci (locked), campaign itu diingat selamanya.
 *   5. UPSERT ke `Meta-Ads` berdasarkan kunci (tanggal | campaign_id).
 *   6. Tiap update dicatat ke `Log_Meta`.
 *
 *  Token disimpan di Script Property META_TOKEN (bisa ditempel dari tab).
 *  Anti-alias: Meta mengirim satu "purchase" dalam banyak label; kita ambil
 *  SATU kanonik ('purchase'), tidak menjumlahkan.
 *
 *  Catatan: getSpreadsheet(), SPREADSHEET_ID, APP_VERSION dipakai bersama dari
 *  Code.gs (jangan dideklarasikan ulang di sini).
 * ============================================================================
 */

var META_GRAPH_VERSION = 'v25.0';
var META_MATCH_THRESHOLD = 0.55;
var SHEET_META = 'Meta-Ads';
var SHEET_MAP = 'Ref_Ads_Map';
var SHEET_META_LOG = 'Log_Meta';

var META_ACT_PURCHASE = 'purchase';
var META_ACT_ATC = 'add_to_cart';
var META_ACT_LPV = 'landing_page_view';
var META_ACT_LINKCLICK = 'link_click';

var META_COLUMNS = [
  'date', 'portfolio', 'business_id', 'business_name', 'ad_account_id', 'ad_account_name',
  'campaign_id', 'campaign_name', 'produk', 'sku', 'match_status', 'match_confidence',
  'spend', 'impressions', 'clicks', 'link_click', 'cpc', 'cpm',
  'add_to_cart', 'landing_page_view', 'purchases', 'cost_per_purchase',
  'daily_budget', 'budget_remaining', 'budget_type', 'status', 'updated_at'
];
var MAP_COLUMNS = ['campaign_key', 'campaign_name', 'sku', 'nama_barang',
                   'confidence', 'locked', 'excluded', 'updated_at'];
var META_EXCL_NAMA = '(dikecualikan — bisnis lain)';   // label produk untuk campaign yang dikecualikan
var META_LOG_COLUMNS = ['Waktu', 'Rentang', 'Portfolio', 'Akun Ditarik', 'Jumlah Akun',
                        'Baris Baru', 'Baris Update', 'Total Baris', 'Perlu Review', 'Oleh', 'Catatan'];

// ---------------------------------------------------------------------------
// UTIL
// ---------------------------------------------------------------------------
function mNum_(v) {
  if (v === null || v === undefined || v === '') return 0;
  var n = parseFloat(String(v).replace(/,/g, ''));
  return isNaN(n) ? 0 : n;
}
function mFmtDate_(d) {
  return Utilities.formatDate(d, Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd');
}
var META_TOKENS_PROP = 'META_TOKENS';   // JSON: [{id,label,token,disimpan,oleh}]
function mParseTgl_(s) {
  // Sheets kadang menyimpan kolom 'date' sebagai objek Date (bukan teks) —
  // tangani keduanya, kalau tidak seluruh baris tersaring & report jadi kosong.
  if (s instanceof Date) return isNaN(s.getTime()) ? null : new Date(s.getFullYear(), s.getMonth(), s.getDate());
  var m = String(s || '').match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}

// ---------------------------------------------------------------------------
// TOKEN — DAFTAR per BUSINESS PORTFOLIO (banyak token)
//
// Tiap business portfolio punya token (System User) sendiri, dan tiap token
// bisa mengakses beberapa ad account. Sistem menyimpan DAFTAR token; saat
// menarik, semua token dilooping -> semua akun -> insight gabungan.
// ---------------------------------------------------------------------------
function mBacaTokens_() {
  var p = PropertiesService.getScriptProperties();
  var raw = p.getProperty(META_TOKENS_PROP);
  var list = [];
  if (raw) { try { list = JSON.parse(raw) || []; } catch (e) { list = []; } }
  // Migrasi token tunggal lama (META_TOKEN) -> jadi entri portfolio pertama.
  if (!list.length) {
    var old = p.getProperty('META_TOKEN');
    if (old) {
      list = [{ id: 'p' + Date.now(), label: 'Portofolio 1', token: old,
                disimpan: new Date().toISOString(), oleh: '' }];
      p.setProperty(META_TOKENS_PROP, JSON.stringify(list));
      p.deleteProperty('META_TOKEN');
    }
  }
  return list;
}
function mSimpanTokens_(list) {
  PropertiesService.getScriptProperties().setProperty(META_TOKENS_PROP, JSON.stringify(list));
}

/** Tambah/ubah token satu portfolio. id kosong = tambah baru. */
function metaSimpanToken(label, token, id) {
  label = String(label || '').trim();
  token = String(token || '').trim().replace(/^bearer\s+/i, '').replace(/^['"]|['"]$/g, '');
  if (!label) throw new Error('Beri nama portfolio dulu (mis. nama business).');
  if (!token) throw new Error('Token kosong.');
  if (token.length < 30) throw new Error('Token terlalu pendek — salin access token utuh.');
  var list = mBacaTokens_();
  var oleh = ''; try { oleh = Session.getActiveUser().getEmail() || ''; } catch (e) {}
  var rec = { id: id || ('p' + Date.now()), label: label, token: token,
              disimpan: new Date().toISOString(), oleh: oleh };
  var i = id ? list.map(function (x) { return x.id; }).indexOf(id) : -1;
  if (i >= 0) list[i] = rec; else list.push(rec);
  mSimpanTokens_(list);
  return metaStatus();
}
function metaHapusToken(id) {
  var list = mBacaTokens_().filter(function (x) { return x.id !== id; });
  mSimpanTokens_(list);
  return metaStatus();
}

/** Status semua portfolio (token disamarkan). */
function metaStatus() {
  var list = mBacaTokens_();
  var ss = getSpreadsheet();
  var sh = ss.getSheetByName(SHEET_META);
  return {
    portfolios: list.map(function (x) {
      return { id: x.id, label: x.label, ekor: '…' + String(x.token).slice(-6),
               disimpan: x.disimpan || '', oleh: x.oleh || '' };
    }),
    jumlah: list.length,
    graphVersion: META_GRAPH_VERSION,
    totalBaris: sh ? Math.max(0, sh.getLastRow() - 1) : 0
  };
}

// ---------------------------------------------------------------------------
// GRAPH API
// ---------------------------------------------------------------------------
function mGraphGet_(url) {
  var res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  var code = res.getResponseCode();
  var body = res.getContentText();
  if (code !== 200) throw new Error('Graph API ' + code + ': ' + body.slice(0, 400));
  return JSON.parse(body);
}
function mGraphGetAll_(url) {
  var out = [], guard = 0, next = url;
  while (next && guard < 80) {
    var j = mGraphGet_(next);
    if (j.data && j.data.length) out = out.concat(j.data);
    next = (j.paging && j.paging.next) ? j.paging.next : null;
    guard++;
  }
  return out;
}

/**
 * Semua ad account yang bisa diakses token + Business Manager-nya.
 * Nama BM butuh izin `business_management`. Kalau token belum punya izin itu,
 * Meta menolak field business{} (error #100). Maka: coba dengan BM dulu, kalau
 * ditolak mundur ke tanpa BM supaya penarikan data TETAP jalan (data campaign
 * lengkap, cuma kolom Business Manager kosong).
 */
function fetchAdAccounts_(token) {
  var base = 'https://graph.facebook.com/' + META_GRAPH_VERSION + '/me/adaccounts'
    + '?limit=200&access_token=' + encodeURIComponent(token) + '&fields=';
  var rows, punyaBiz = true;
  try {
    rows = mGraphGetAll_(base + encodeURIComponent('account_id,name,business{id,name},account_status'));
  } catch (e) {
    if (/business_management|permission|\(#100\)|\(#200\)|\(#10\)/i.test(String(e.message || e))) {
      rows = mGraphGetAll_(base + encodeURIComponent('account_id,name,account_status'));
      punyaBiz = false;
    } else { throw e; }
  }
  return rows.map(function (a) {
    var biz = a.business || {};
    return {
      actId: String(a.id || ('act_' + a.account_id)),      // 'act_XXXX'
      actName: a.name || '',
      bizId: biz.id || '',
      bizName: biz.name || (punyaBiz ? '(tanpa Business Manager)'
                                     : '(perlu izin business_management)'),
      status: a.account_status
    };
  });
}

function fetchInsights_(token, actId, since, until) {
  var fields = ['campaign_id', 'campaign_name', 'spend', 'impressions', 'clicks',
                'cpc', 'cpm', 'actions', 'cost_per_action_type'].join(',');
  var timeRange = JSON.stringify({ since: mFmtDate_(since), until: mFmtDate_(until) });
  var url = 'https://graph.facebook.com/' + META_GRAPH_VERSION + '/' + actId + '/insights'
    + '?level=campaign&time_increment=1'
    + '&fields=' + encodeURIComponent(fields)
    + '&time_range=' + encodeURIComponent(timeRange)
    + '&limit=300&access_token=' + encodeURIComponent(token);
  return mGraphGetAll_(url);
}

function fetchBudgets_(token, actId) {
  var fields = 'id,name,daily_budget,lifetime_budget,budget_remaining,effective_status';
  var url = 'https://graph.facebook.com/' + META_GRAPH_VERSION + '/' + actId + '/campaigns'
    + '?fields=' + encodeURIComponent(fields) + '&limit=300&access_token=' + encodeURIComponent(token);
  var rows = mGraphGetAll_(url), map = {};
  rows.forEach(function (c) {
    var daily = mNum_(c.daily_budget), life = mNum_(c.lifetime_budget);
    map[String(c.id)] = {
      daily_budget: daily, lifetime_budget: life, budget_remaining: mNum_(c.budget_remaining),
      budget_type: daily > 0 ? 'Harian' : (life > 0 ? 'Seumur Hidup' : '-'),
      status: c.effective_status || ''
    };
  });
  return map;
}

function mPickAction_(arr, type) {
  if (!arr || !arr.length) return 0;
  for (var i = 0; i < arr.length; i++) if (arr[i].action_type === type) return mNum_(arr[i].value);
  return 0;
}

// ---------------------------------------------------------------------------
// CLEANING NAMA CAMPAIGN + FUZZY MATCH -> "Nama Barang JNT"
// ---------------------------------------------------------------------------
function cleanCampaignName(name) {
  var s = String(name || '');
  s = s.replace(/\|/g, ' ');
  s = s.replace(/\b\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}\b/g, ' ');   // tanggal
  s = s.replace(/\bpost\s*id\s*\d*/gi, ' ');
  s = s.replace(/\bnew\b/gi, ' ').replace(/\bcopy\b/gi, ' ');
  s = s.replace(/\b(cbo|abo|adv|advantage|test|testing|scale|winning|ws|fb|ig|reels?)\b/gi, ' ');
  s = s.replace(/rp\.?\s*\d[\d.\,]*/gi, ' ');                   // harga
  s = s.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim();
  return s;
}
function mNorm_(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}
function mTokens_(s) {
  return mNorm_(s).split(' ').filter(function (x) { return x.length > 1; });
}
function mSimilarity_(a, b) {
  var na = mNorm_(a), nb = mNorm_(b);
  if (!na || !nb) return 0;
  if (na === nb) return 1;
  if (nb.indexOf(na) >= 0 || na.indexOf(nb) >= 0) return 0.9;
  var ta = mTokens_(a), tb = mTokens_(b);
  if (!ta.length || !tb.length) return 0;
  var setb = {}; tb.forEach(function (x) { setb[x] = 1; });
  var inter = 0; ta.forEach(function (x) { if (setb[x]) inter++; });
  var uni = {}; ta.concat(tb).forEach(function (x) { uni[x] = 1; });
  return inter / Object.keys(uni).length;
}

/** Acuan produk = SKU -> Nama Barang JNT (dari Impor-RefProduk via Order.gs). */
function loadProdukRef_() {
  var peta;
  try { peta = petaProdukKanonik_(); } catch (e) { peta = { bySku: {} }; }
  return Object.keys(peta.bySku).map(function (sku) { return { sku: sku, nama: peta.bySku[sku] }; });
}

function matchProduct_(cleanName, ref) {
  var best = { sku: '', nama: '', score: 0 };
  for (var i = 0; i < ref.length; i++) {
    var sc = mSimilarity_(cleanName, ref[i].nama);
    if (sc > best.score) best = { sku: ref[i].sku, nama: ref[i].nama, score: sc };
  }
  return best;
}

// ---------------------------------------------------------------------------
// MEMORY PELABELAN (Ref_Ads_Map)
// ---------------------------------------------------------------------------
function mMapKey_(campaignName) { return mNorm_(cleanCampaignName(campaignName)); }

function loadMap_() {
  var sh = getSpreadsheet().getSheetByName(SHEET_MAP);
  var map = {};
  if (!sh || sh.getLastRow() < 2) return map;
  var values = sh.getDataRange().getValues();
  var head = values[0].map(function (x) { return String(x).trim(); });
  var idx = {}; MAP_COLUMNS.forEach(function (c) { idx[c] = head.indexOf(c); });
  for (var r = 1; r < values.length; r++) {
    var key = String(values[r][idx.campaign_key] || '').trim();
    if (!key) continue;
    map[key] = {
      sku: String(values[r][idx.sku] || '').trim(),
      nama: String(values[r][idx.nama_barang] || '').trim(),
      confidence: mNum_(values[r][idx.confidence]),
      locked: String(values[r][idx.locked]).toUpperCase() === 'TRUE',
      excluded: idx.excluded >= 0 && String(values[r][idx.excluded]).toUpperCase() === 'TRUE',
      campaign_name: String(values[r][idx.campaign_name] || '').trim()
    };
  }
  return map;
}
function saveMap_(map) {
  var ss = getSpreadsheet();
  var sh = ss.getSheetByName(SHEET_MAP) || ss.insertSheet(SHEET_MAP);
  sh.clear();
  sh.getRange(1, 1, 1, MAP_COLUMNS.length).setValues([MAP_COLUMNS]);
  sh.setFrozenRows(1);
  var keys = Object.keys(map).sort();
  if (!keys.length) return;
  var now = mFmtDate_(new Date());
  var rows = keys.map(function (k) {
    var m = map[k];
    return [k, m.campaign_name, m.sku, m.nama, (m.confidence != null ? m.confidence : ''),
            m.locked ? 'TRUE' : 'FALSE', m.excluded ? 'TRUE' : 'FALSE', now];
  });
  sh.getRange(2, 1, rows.length, MAP_COLUMNS.length).setValues(rows);
}

/** campaign -> {sku, produk, status, confidence}; map diperbarui in-place. */
function resolveCampaign_(campaignName, ref, map) {
  var key = mMapKey_(campaignName);
  var clean = cleanCampaignName(campaignName);
  var m = map[key];
  // Campaign yang sengaja dikecualikan (akun iklan sempat dipakai bisnis lain).
  if (m && m.locked && m.excluded) {
    return { sku: '', produk: META_EXCL_NAMA, status: 'DIKECUALIKAN', confidence: 1 };
  }
  if (m && m.locked && (m.sku || m.nama)) {
    return { sku: m.sku, produk: m.nama || m.sku, status: 'TERKUNCI', confidence: m.confidence };
  }
  var best = matchProduct_(clean, ref);
  var conf = Math.round(best.score * 100) / 100;
  var out;
  if (best.sku && best.score >= META_MATCH_THRESHOLD) {
    out = { sku: best.sku, produk: best.nama, status: 'AUTO', confidence: conf };
  } else {
    out = { sku: (best.sku || ''), produk: (best.nama || clean), status: 'PERLU REVIEW', confidence: conf };
  }
  if (!(m && m.locked)) {
    map[key] = { sku: out.sku, nama: out.produk, confidence: out.confidence, locked: false, excluded: false, campaign_name: campaignName };
  }
  return out;
}

// ---------------------------------------------------------------------------
// RANGKAI BARIS + UPSERT
// ---------------------------------------------------------------------------
function buildMetaRows_(insights, budgets, akun, portfolio, ref, map) {
  var now = mFmtDate_(new Date());
  var rows = [];
  insights.forEach(function (r) {
    var cid = String(r.campaign_id || '');
    var res = resolveCampaign_(r.campaign_name || '', ref, map);
    var b = budgets[cid] || {};
    var purch = mPickAction_(r.actions, META_ACT_PURCHASE);
    var cpp = mPickAction_(r.cost_per_action_type, META_ACT_PURCHASE);
    rows.push([
      r.date_start || '', portfolio,
      akun.bizId, akun.bizName, akun.actId, akun.actName,
      cid, r.campaign_name || '', res.produk, res.sku, res.status, res.confidence,
      mNum_(r.spend), mNum_(r.impressions), mNum_(r.clicks),
      mPickAction_(r.actions, META_ACT_LINKCLICK), Math.round(mNum_(r.cpc)), Math.round(mNum_(r.cpm)),
      mPickAction_(r.actions, META_ACT_ATC), mPickAction_(r.actions, META_ACT_LPV),
      purch, purch > 0 ? Math.round(cpp) : '',
      (b.daily_budget != null ? b.daily_budget : ''), (b.budget_remaining != null ? b.budget_remaining : ''),
      (b.budget_type || '-'), (b.status || ''), now
    ]);
  });
  return rows;
}

function upsertMeta_(newRows) {
  var lock = LockService.getScriptLock(); lock.waitLock(60000);
  try {
    var ss = getSpreadsheet();
    var sh = ss.getSheetByName(SHEET_META) || ss.insertSheet(SHEET_META);
    var nCol = META_COLUMNS.length;
    var lastRow = sh.getLastRow(), lastCol = Math.max(1, sh.getLastColumn());

    // Baca header lama (kalau ada) untuk memindahkan baris lama ke SKEMA BARU
    // berdasarkan NAMA kolom — aman saat kolom bertambah (mis. 'portfolio').
    var headLama = lastRow >= 1 ? sh.getRange(1, 1, 1, lastCol).getValues()[0]
                                     .map(function (x) { return String(x).trim(); }) : [];
    var existing = [];
    if (lastRow > 1 && headLama.length) {
      var raw = sh.getRange(2, 1, lastRow - 1, lastCol).getValues();
      existing = raw.map(function (r) {
        return META_COLUMNS.map(function (nm) {
          var i = headLama.indexOf(nm);
          return i >= 0 ? r[i] : '';                 // kolom baru -> kosong utk baris lama
        });
      });
    }

    // Selalu tulis ulang header ke skema terbaru (menambahkan kolom baru)
    sh.getRange(1, 1, 1, nCol).setValues([META_COLUMNS]); sh.setFrozenRows(1);

    var iDate = META_COLUMNS.indexOf('date'), iCid = META_COLUMNS.indexOf('campaign_id');
    var K = function (row) { return String(row[iDate]) + '||' + String(row[iCid]); };
    var map = {}, list = [];
    existing.forEach(function (row) {
      var k = K(row);
      if (map.hasOwnProperty(k)) list[map[k]] = row;
      else { list.push(row); map[k] = list.length - 1; }
    });
    var added = 0, updated = 0;
    newRows.forEach(function (row) {
      var k = K(row);
      if (map.hasOwnProperty(k)) { list[map[k]] = row; updated++; }
      else { list.push(row); map[k] = list.length - 1; added++; }
    });
    list.sort(function (a, b) {
      var d = String(a[iDate]).localeCompare(String(b[iDate]));
      return d !== 0 ? d : String(a[iCid]).localeCompare(String(b[iCid]));
    });
    if (lastRow > 1) sh.getRange(2, 1, lastRow - 1, nCol).clearContent();
    if (list.length) sh.getRange(2, 1, list.length, nCol).setValues(list);
    return { added: added, updated: updated, total: list.length };
  } finally { lock.releaseLock(); }
}

function mCatatLog_(rentang, akunN, res, review, catatan, portfolioStr, akunStr) {
  var ss = getSpreadsheet();
  var sh = ss.getSheetByName(SHEET_META_LOG) || ss.insertSheet(SHEET_META_LOG);
  // Pastikan header sama dengan skema terbaru. Kalau berbeda (skema lama),
  // reset sheet sekali supaya kolom tidak bergeser (riwayat lama ikut dihapus).
  var headLama = sh.getLastRow() >= 1
    ? sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(function (x) { return String(x).trim(); })
    : [];
  if (headLama.join('|') !== META_LOG_COLUMNS.join('|')) {
    sh.clear();
    sh.getRange(1, 1, 1, META_LOG_COLUMNS.length).setValues([META_LOG_COLUMNS]);
    sh.setFrozenRows(1);
  }
  var oleh = ''; try { oleh = Session.getActiveUser().getEmail() || ''; } catch (e) {}
  sh.insertRowAfter(1);
  sh.getRange(2, 1, 1, META_LOG_COLUMNS.length).setValues([[
    Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Jakarta', 'yyyy-MM-dd HH:mm'),
    rentang, portfolioStr || '', akunStr || '', akunN,
    res.added, res.updated, res.total, review, oleh, catatan || ''
  ]]);
}

// ---------------------------------------------------------------------------
// ORKESTRASI — dipanggil dari UI
// ---------------------------------------------------------------------------
/**
 * Tarik data iklan untuk rentang [since,until].
 * portfolioIds (opsional): array ID business portfolio (token) yang ingin ditarik.
 *   - kosong / null  -> tarik SEMUA portfolio (semua token).
 *   - berisi         -> hanya portfolio yang ID-nya ada di daftar (bulk selektif).
 * Tiap portfolio yang dipilih tetap menarik SELURUH ad account di dalamnya.
 */
function metaTarik(sinceStr, untilStr, portfolioIds) {
  var since = mParseTgl_(sinceStr), until = mParseTgl_(untilStr);
  if (!since || !until) throw new Error('Rentang tanggal wajib diisi (yyyy-mm-dd).');
  if (since > until) { var t = since; since = until; until = t; }

  var tokens = mBacaTokens_();
  if (!tokens.length) throw new Error('Belum ada token. Tambahkan minimal satu business portfolio.');

  var filter = null;
  if (portfolioIds && portfolioIds.length) {
    filter = {}; portfolioIds.forEach(function (x) { filter[String(x).trim()] = 1; });
    tokens = tokens.filter(function (tk) { return filter[tk.id]; });
    if (!tokens.length) throw new Error('Portfolio terpilih tidak ditemukan.');
  }

  var ref = loadProdukRef_();
  var map = loadMap_();
  var allRows = [], review = 0, gagal = [], akunTotal = 0, akunPratinjau = [];
  var portfolioSet = {};

  tokens.forEach(function (tk) {
    var akunList;
    try { akunList = fetchAdAccounts_(tk.token); }
    catch (e) { gagal.push('[' + tk.label + '] token gagal: ' + (e && e.message ? e.message : e)); return; }
    akunList.forEach(function (akun) {
      akunTotal++;                                          // akun yang benar-benar dicoba
      try {
        var insights = fetchInsights_(tk.token, akun.actId, since, until);
        var budgets = fetchBudgets_(tk.token, akun.actId);
        var rows = buildMetaRows_(insights, budgets, akun, tk.label, ref, map);
        rows.forEach(function (r) { if (r[META_COLUMNS.indexOf('match_status')] === 'PERLU REVIEW') review++; });
        allRows = allRows.concat(rows);
        akunPratinjau.push({ portfolio: tk.label, biz: akun.bizName, akun: akun.actName, id: akun.actId });
        portfolioSet[tk.label] = 1;
      } catch (e) {
        gagal.push('[' + tk.label + '] ' + akun.actName + ' (' + akun.actId + '): ' + (e && e.message ? e.message : e));
      }
    });
  });

  var res = upsertMeta_(allRows);
  saveMap_(map);
  try { CacheService.getScriptCache().remove('metaReport'); } catch (e) {}
  var rentang = mFmtDate_(since) + ' s/d ' + mFmtDate_(until);
  var portoStr = Object.keys(portfolioSet).join(', ') || '-';
  var namaAkun = akunPratinjau.map(function (a) { return a.akun; });
  var akunStr = namaAkun.slice(0, 8).join(', ') + (namaAkun.length > 8 ? ' +' + (namaAkun.length - 8) + ' lagi' : '');
  var catatan = (filter ? 'Tarik portfolio terpilih' : 'Tarik semua portfolio') + (gagal.length ? ' · GAGAL sebagian: ' + gagal.join(' | ') : '');
  mCatatLog_(rentang, akunPratinjau.length, res, review, catatan, portoStr, akunStr);

  return {
    rentang: rentang, portfolioTotal: Object.keys(portfolioSet).length, akunTotal: akunTotal,
    akunSukses: akunPratinjau.length, akunGagal: gagal.length,
    added: res.added, updated: res.updated, total: res.total, review: review,
    gagal: gagal, akunList: akunPratinjau
  };
}

/** Deteksi ad account semua portfolio (tanpa menarik data) — pratinjau UI. */
function metaListAkun() {
  var out = [];
  mBacaTokens_().forEach(function (tk) {
    try {
      fetchAdAccounts_(tk.token).forEach(function (a) {
        out.push({ portfolio: tk.label, biz: a.bizName, bizId: a.bizId, akun: a.actName, id: a.actId, status: a.status });
      });
    } catch (e) {
      out.push({ portfolio: tk.label, biz: '(token gagal: ' + (e && e.message ? e.message : e) + ')', akun: '', id: '' });
    }
  });
  return out;
}

/** Diagnostik: cek tiap token & daftar akunnya. */
function metaTes() {
  var tokens = mBacaTokens_();
  if (!tokens.length) return 'Belum ada token.';
  var out = '';
  tokens.forEach(function (tk) {
    out += '● Portfolio: ' + tk.label + '\n';
    try {
      var ak = fetchAdAccounts_(tk.token);
      out += '   token OK, ' + ak.length + ' ad account:\n';
      ak.slice(0, 30).forEach(function (a) { out += '     • ' + a.bizName + ' — ' + a.actName + ' (' + a.actId + ')\n'; });
    } catch (e) { out += '   ✕ ' + (e && e.message ? e.message : e) + '\n'; }
  });
  return out;
}

function metaGetLog() {
  var sh = getSpreadsheet().getSheetByName(SHEET_META_LOG);
  if (!sh || sh.getLastRow() < 2) return [];
  var v = sh.getRange(1, 1, Math.min(sh.getLastRow(), 51), META_LOG_COLUMNS.length).getValues();
  var head = v[0];
  return v.slice(1).map(function (r) {
    var o = {}; head.forEach(function (h, i) { o[h] = r[i]; }); return o;
  });
}

// ---------------------------------------------------------------------------
// PELABELAN (UI): daftar perlu review, daftar produk, kunci label
// ---------------------------------------------------------------------------
function metaGetProdukList() {
  return loadProdukRef_().sort(function (a, b) { return a.nama < b.nama ? -1 : 1; });
}

/**
 * Semua campaign yang BELUM CLEAR di pelabelan — yakni belum dikunci DAN belum
 * dikecualikan (status di Ref_Ads_Map: locked=false).
 *
 * Sumber utama = sheet Meta-Ads (semua campaign yang benar-benar ada datanya),
 * bukan hanya Ref_Ads_Map. Ini memperbaiki kasus campaign yang masih
 * "PERLU REVIEW" di Meta-Ads tapi TIDAK tercatat di Ref_Ads_Map (mis. map
 * pernah ter-reset) sehingga sebelumnya tidak muncul di daftar.
 */
function metaGetReview() {
  var map = loadMap_();
  var byKey = {};

  var sh = getSpreadsheet().getSheetByName(SHEET_META);
  if (sh && sh.getLastRow() >= 2) {
    var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    var ix = {}; head.forEach(function (h, i) { ix[h] = i; });
    var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
    data.forEach(function (r) {
      var nm = String(r[ix.campaign_name] || '').trim();
      var key = mMapKey_(nm);
      if (!key) return;
      var m = map[key];
      if (m && m.locked) return;                 // sudah dikunci / dikecualikan -> lewati
      if (byKey[key]) return;                     // 1 baris per campaign
      byKey[key] = {
        key: key,
        campaign_name: nm || (m && m.campaign_name) || key,
        sku: (m && m.sku) || String(r[ix.sku] || '').trim(),
        nama: (m && m.nama) || String(r[ix.produk] || '').trim(),
        confidence: (m && m.confidence != null) ? m.confidence : mNum_(r[ix.match_confidence])
      };
    });
  }

  // Tambahkan juga entri map yang belum terkunci tapi tak ada di sheet (data lama).
  Object.keys(map).forEach(function (k) {
    var m = map[k];
    if (m.locked || byKey[k]) return;
    byKey[k] = { key: k, campaign_name: m.campaign_name, sku: m.sku, nama: m.nama, confidence: m.confidence };
  });

  var out = Object.keys(byKey).map(function (k) { return byKey[k]; });
  out.sort(function (a, b) { return (a.confidence || 0) - (b.confidence || 0); });  // paling ragu dulu
  return out;
}

/** Semua label terkunci (untuk ditinjau/diubah), termasuk yang dikecualikan. */
function metaGetLocked() {
  var map = loadMap_();
  return Object.keys(map).filter(function (k) { return map[k].locked; }).map(function (k) {
    return { key: k, campaign_name: map[k].campaign_name, sku: map[k].sku,
             nama: map[k].nama, excluded: !!map[k].excluded };
  }).sort(function (a, b) { return a.campaign_name < b.campaign_name ? -1 : 1; });
}

/**
 * Semua mutasi Ref_Ads_Map (kunci/kecualikan/buka) WAJIB lewat sini.
 * saveMap_ menghapus lalu menulis ulang seluruh sheet, jadi kalau dua klik
 * "Kunci" berjalan paralel bisa saling menimpa — bahkan satu bisa membaca
 * sheet saat sedang kosong lalu menyimpan map kosong (seluruh label hilang).
 * LockService membuat operasi baca-ubah-tulis ini ANTRE, bukan tabrakan.
 */
function mDenganKunciMap_(fn) {
  var lock = LockService.getScriptLock();
  // Antre & tahan banting: kalau banyak aksi datang serentak, tunggu giliran.
  // Coba beberapa kali sebelum menyerah supaya aksi tidak gampang gagal.
  var dapat = false;
  for (var i = 0; i < 3 && !dapat; i++) {
    try { lock.waitLock(45000); dapat = true; }
    catch (e) { if (i === 2) throw new Error('Sistem sedang sibuk memproses antrean, coba lagi sebentar.'); Utilities.sleep(300); }
  }
  try { return fn(); } finally { try { lock.releaseLock(); } catch (e) {} }
}

/** Kunci sebuah campaign_key ke SKU tertentu; sekaligus perbarui baris Meta-Ads. */
function metaSimpanLabel(campaignKey, sku) {
  campaignKey = String(campaignKey || '').trim();
  sku = String(sku || '').trim().toUpperCase();
  if (!campaignKey) throw new Error('campaign_key kosong.');

  var ref = loadProdukRef_();
  var nama = '';
  if (sku) {
    var f = ref.filter(function (x) { return x.sku.toUpperCase() === sku; })[0];
    nama = f ? f.nama : sku;
  }
  return mDenganKunciMap_(function () {
    var map = loadMap_();
    var lama = map[campaignKey] || {};
    map[campaignKey] = {
      sku: sku, nama: nama || lama.nama || '', confidence: 1,
      locked: true, excluded: false, campaign_name: lama.campaign_name || ''
    };
    saveMap_(map);
    var diperbarui = metaRelabelSheet_(campaignKey, sku, nama, 'TERKUNCI');
    try { CacheService.getScriptCache().remove('metaReport'); } catch (e) {}
    return { ok: true, sku: sku, nama: nama, barisDiperbarui: diperbarui };
  });
}

/**
 * Kecualikan sebuah campaign: akun iklan sempat dipakai bisnis lain, jadi
 * campaign ini TIDAK boleh ikut ke report/dashboard bisnis ini. Dikunci
 * (diingat) + baris Meta-Ads yang cocok ditandai status DIKECUALIKAN sehingga
 * langsung tersaring dari semua agregasi.
 */
function metaKecualikanCampaign(campaignKey) {
  campaignKey = String(campaignKey || '').trim();
  if (!campaignKey) throw new Error('campaign_key kosong.');
  return mDenganKunciMap_(function () {
    var map = loadMap_();
    var lama = map[campaignKey] || {};
    map[campaignKey] = {
      sku: '', nama: META_EXCL_NAMA, confidence: 1,
      locked: true, excluded: true, campaign_name: lama.campaign_name || ''
    };
    saveMap_(map);
    var diperbarui = metaRelabelSheet_(campaignKey, '', META_EXCL_NAMA, 'DIKECUALIKAN');
    try { CacheService.getScriptCache().remove('metaReport'); } catch (e) {}
    return { ok: true, barisDiperbarui: diperbarui };
  });
}

/** Buka kunci sebuah label / batalkan pengecualian (kembali auto-match). */
function metaHapusLabel(campaignKey) {
  return mDenganKunciMap_(function () {
    var map = loadMap_();
    if (map[campaignKey]) { map[campaignKey].locked = false; map[campaignKey].excluded = false; saveMap_(map); }
    return { ok: true };
  });
}

/** Perbarui kolom produk/sku/status pada baris Meta-Ads yang campaign-nya cocok. */
function metaRelabelSheet_(campaignKey, sku, nama, status) {
  status = status || 'TERKUNCI';
  var sh = getSpreadsheet().getSheetByName(SHEET_META);
  if (!sh || sh.getLastRow() < 2) return 0;
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var iName = head.indexOf('campaign_name'), iProd = head.indexOf('produk'),
      iSku = head.indexOf('sku'), iSt = head.indexOf('match_status'), iConf = head.indexOf('match_confidence');
  if (iName < 0) return 0;
  var rng = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn());
  var data = rng.getValues(), n = 0;
  data.forEach(function (r) {
    if (mMapKey_(r[iName]) === campaignKey) {
      if (iProd >= 0) r[iProd] = nama || sku;
      if (iSku >= 0) r[iSku] = sku;
      if (iSt >= 0) r[iSt] = status;
      if (iConf >= 0) r[iConf] = 1;
      n++;
    }
  });
  if (n) rng.setValues(data);
  return n;
}

// ---------------------------------------------------------------------------
// REPORT IKLAN (untuk tab Dashboard) — HANYA campaign produk yang SUDAH CLEAR
//
// "Clear" = campaign sudah cocok ke SKU yang ADA di "Nama Barang JNT"
// (status TERKUNCI/AUTO). Yang masih PERLU REVIEW, DIKECUALIKAN, atau SKU-nya
// tidak dikenal TIDAK dihitung — supaya dashboard bersih & tidak menyesatkan.
// Belanja yang tersaring tetap dilaporkan terpisah (spendBelumJelas) sbagai
// pengingat untuk dilabeli.
// ---------------------------------------------------------------------------
/** Set SKU valid (uppercase) -> nama kanonik, dari Impor-RefProduk. */
function mSetSkuValid_() {
  var set = {};
  loadProdukRef_().forEach(function (x) { set[String(x.sku).toUpperCase()] = x.nama; });
  return set;
}
/** Baris ikut dashboard? Hanya kalau SKU-nya jelas & ada di Nama Barang JNT. */
function mBarisClear_(r, ix, setSku) {
  var st = String(r[ix.match_status] || '').trim().toUpperCase();
  if (st === 'DIKECUALIKAN' || st === 'PERLU REVIEW') return false;
  var sku = String(r[ix.sku] || '').trim().toUpperCase();
  return !!(sku && setSku[sku]);
}

/** Ringkas Meta-Ads per produk (hanya produk clear) untuk rentang tanggal. */
function metaReportProduk(sinceStr, untilStr) {
  var sh = getSpreadsheet().getSheetByName(SHEET_META);
  var out = { ada: false, periode: { since: sinceStr || '', until: untilStr || '' },
              total: { spend: 0, purchases: 0, clicks: 0, impressions: 0 },
              spendBelumJelas: 0, campaignBelumJelas: 0, produk: [] };
  if (!sh || sh.getLastRow() < 2) return out;
  out.ada = true;
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var ix = {}; head.forEach(function (h, i) { ix[h] = i; });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var since = mParseTgl_(sinceStr), until = mParseTgl_(untilStr);
  var setSku = mSetSkuValid_();

  var byP = {}, belumSet = {};
  data.forEach(function (r) {
    var d = mParseTgl_(r[ix.date]);
    if (since && (!d || d < since)) return;
    if (until && (!d || d > until)) return;
    var st = String(r[ix.match_status] || '').trim().toUpperCase();
    if (st === 'DIKECUALIKAN') return;                        // bisnis lain — abaikan total
    if (!mBarisClear_(r, ix, setSku)) {                       // belum jelas -> jangan ke dashboard
      out.spendBelumJelas += mNum_(r[ix.spend]);
      belumSet[String(r[ix.campaign_id] || '')] = 1;
      return;
    }
    var skuU = String(r[ix.sku] || '').trim().toUpperCase();
    var nama = setSku[skuU];
    if (!byP[skuU]) byP[skuU] = { produk: nama, sku: String(r[ix.sku] || '').trim(),
                                  spend: 0, purchases: 0, clicks: 0, impressions: 0, atc: 0,
                                  link_click: 0, lpv: 0, budgets: {} };
    var o = byP[skuU];
    o.spend += mNum_(r[ix.spend]); o.purchases += mNum_(r[ix.purchases]);
    o.clicks += mNum_(r[ix.clicks]); o.impressions += mNum_(r[ix.impressions]);
    o.atc += mNum_(r[ix.add_to_cart]);
    o.link_click += mNum_(r[ix.link_click]); o.lpv += mNum_(r[ix.landing_page_view]);
    // daily_budget = snapshot per campaign (bukan metrik harian) -> ambil per campaign, jangan dijumlah per baris
    var cid = String(r[ix.campaign_id] || '');
    var db = mNum_(r[ix.daily_budget]);
    if (cid && db > 0) o.budgets[cid] = db;
    out.total.spend += mNum_(r[ix.spend]); out.total.purchases += mNum_(r[ix.purchases]);
    out.total.clicks += mNum_(r[ix.clicks]); out.total.impressions += mNum_(r[ix.impressions]);
  });
  out.campaignBelumJelas = Object.keys(belumSet).length;

  out.produk = Object.keys(byP).map(function (k) {
    var o = byP[k];
    o.cpp = o.purchases > 0 ? Math.round(o.spend / o.purchases) : '';       // cost per purchase
    o.ctr = o.impressions > 0 ? Math.round(o.clicks / o.impressions * 1000) / 10 : 0;
    o.cpc = o.clicks > 0 ? Math.round(o.spend / o.clicks) : '';             // cost per click
    o.cpm = o.impressions > 0 ? Math.round(o.spend / o.impressions * 1000) : '';  // cost per 1000 impresi
    o.daily_budget = Object.keys(o.budgets).reduce(function (s, c) { return s + o.budgets[c]; }, 0);
    delete o.budgets;
    return o;
  }).sort(function (a, b) { return b.spend - a.spend; });   // belanja terbesar dulu
  return out;
}

/**
 * Ringkas Meta-Ads per AD ACCOUNT untuk rentang tanggal (opsional).
 * Sama seperti per produk: HANYA campaign produk yang sudah clear yang
 * dihitung; DIKECUALIKAN & PERLU REVIEW tidak.
 */
function metaReportAkun(sinceStr, untilStr) {
  var sh = getSpreadsheet().getSheetByName(SHEET_META);
  var out = { ada: false, periode: { since: sinceStr || '', until: untilStr || '' },
              total: { spend: 0, purchases: 0, clicks: 0, impressions: 0 }, akun: [] };
  if (!sh || sh.getLastRow() < 2) return out;
  out.ada = true;
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var ix = {}; head.forEach(function (h, i) { ix[h] = i; });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  var since = mParseTgl_(sinceStr), until = mParseTgl_(untilStr);
  var setSku = mSetSkuValid_();

  var byA = {};
  data.forEach(function (r) {
    var d = mParseTgl_(r[ix.date]);
    if (since && (!d || d < since)) return;
    if (until && (!d || d > until)) return;
    if (!mBarisClear_(r, ix, setSku)) return;   // hanya produk clear
    var id = String(r[ix.ad_account_id] || '').trim() || '(tanpa id)';
    if (!byA[id]) byA[id] = {
      ad_account_id: id, ad_account_name: String(r[ix.ad_account_name] || '').trim(),
      portfolio: String(r[ix.portfolio] || '').trim(), business_name: String(r[ix.business_name] || '').trim(),
      spend: 0, purchases: 0, clicks: 0, impressions: 0, campaigns: {}
    };
    var o = byA[id];
    o.spend += mNum_(r[ix.spend]); o.purchases += mNum_(r[ix.purchases]);
    o.clicks += mNum_(r[ix.clicks]); o.impressions += mNum_(r[ix.impressions]);
    o.campaigns[String(r[ix.campaign_id] || '')] = 1;
    out.total.spend += mNum_(r[ix.spend]); out.total.purchases += mNum_(r[ix.purchases]);
    out.total.clicks += mNum_(r[ix.clicks]); out.total.impressions += mNum_(r[ix.impressions]);
  });

  out.akun = Object.keys(byA).map(function (k) {
    var o = byA[k];
    o.campaign_count = Object.keys(o.campaigns).length; delete o.campaigns;
    o.cpp = o.purchases > 0 ? Math.round(o.spend / o.purchases) : '';
    o.ctr = o.impressions > 0 ? Math.round(o.clicks / o.impressions * 1000) / 10 : 0;
    return o;
  }).sort(function (a, b) { return b.spend - a.spend; });
  return out;
}

/**
 * Tren SPEND HARIAN untuk satu bulan (yyyy-MM) — untuk line chart di dashboard.
 * Menghitung total spend iklan bisnis ini per hari; campaign DIKECUALIKAN
 * (bisnis lain) tidak dihitung. Juga mengembalikan daftar bulan yang tersedia
 * agar dropdown bisa diisi. Kalau bulan kosong -> pakai bulan terbaru di data.
 */
function metaSpendHarian(bulan) {
  var sh = getSpreadsheet().getSheetByName(SHEET_META);
  var out = { ada: false, bulan: bulan || '', bulanTersedia: [], hari: [], total: 0 };
  if (!sh || sh.getLastRow() < 2) return out;
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var ix = {}; head.forEach(function (h, i) { ix[h] = i; });
  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();

  // kumpulkan bulan yang ada + spend per tanggal (yyyy-MM-dd)
  var bulanSet = {}, perTgl = {};
  var p2 = function (n) { return (n < 10 ? '0' : '') + n; };
  data.forEach(function (r) {
    if (String(r[ix.match_status] || '').trim().toUpperCase() === 'DIKECUALIKAN') return;  // bisnis lain
    var d = mParseTgl_(r[ix.date]);
    if (!d) return;
    var ym = d.getFullYear() + '-' + p2(d.getMonth() + 1);
    bulanSet[ym] = 1;
    var ds = ym + '-' + p2(d.getDate());
    perTgl[ds] = (perTgl[ds] || 0) + mNum_(r[ix.spend]);
  });

  out.bulanTersedia = Object.keys(bulanSet).sort().reverse();
  if (!out.bulanTersedia.length) return out;
  var ym = (bulan && bulanSet[bulan]) ? bulan : out.bulanTersedia[0];
  out.bulan = ym; out.ada = true;

  var thn = +ym.split('-')[0], mon = +ym.split('-')[1];
  var jmlHari = new Date(thn, mon, 0).getDate();                 // jumlah hari di bulan itu
  var total = 0;
  for (var h = 1; h <= jmlHari; h++) {
    var ds = ym + '-' + p2(h);
    var sp = Math.round(perTgl[ds] || 0);
    total += sp;
    out.hari.push({ tgl: ds, hari: h, spend: sp });
  }
  out.total = total;
  return out;
}

/** Sekali jalan: buat sheet Meta-Ads, Ref_Ads_Map, Log_Meta dengan header. */
function metaSetup() {
  var ss = getSpreadsheet();
  [[SHEET_META, META_COLUMNS], [SHEET_MAP, MAP_COLUMNS], [SHEET_META_LOG, META_LOG_COLUMNS]].forEach(function (p) {
    var sh = ss.getSheetByName(p[0]) || ss.insertSheet(p[0]);
    if (sh.getLastRow() < 1 || String(sh.getRange(1, 1).getValue()).trim() === '') {
      sh.getRange(1, 1, 1, p[1].length).setValues([p[1]]); sh.setFrozenRows(1);
    }
  });
  return 'Setup Meta Ads selesai.';
}

/** Trigger harian opsional (tarik 7 hari terakhir). */
function metaHarian() {
  var until = new Date(), since = new Date(); since.setDate(since.getDate() - 7);
  return metaTarik(mFmtDate_(since), mFmtDate_(until));
}
function metaPasangTriggerHarian() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'metaHarian') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('metaHarian').timeBased().everyDays(1).atHour(6).create();
  return 'Trigger harian metaHarian() dipasang (~06:00).';
}
