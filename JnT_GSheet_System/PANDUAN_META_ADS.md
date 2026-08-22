# PANDUAN PASANG — Meta Ads Loader (Modul 5)

Menarik data iklan Meta (spend, purchase, CPM, CPC, budget) otomatis ke sheet
`Meta-Ads` di spreadsheet dashboard, lalu dipetakan ke produk/SKU dan dipakai
Modul 5 dashboard untuk keputusan **scale / optimize / kill**.

---

## 1. Buat Meta App + System User token (sekali saja)

Ringkas (detail lengkap sudah dibahas di chat):

1. **developers.facebook.com** → My Apps → Create App → tipe **Business** → tambah produk **Marketing API**.
2. **business.facebook.com/settings** → Users → **System users** → Add → role **Employee** (bukan Admin — Admin butuh usia 7 hari).
3. **Add assets** → App (Full control) + **Ad account** (View performance).
4. **Generate new token** → pilih app → **Never expire** → centang **`ads_read`** (+ `read_insights`) → **salin token**.
5. Catat **Ad Account ID** format `act_XXXXXXXXXX`.

Tes di browser (ganti `<ID>` & `<TOKEN>`):
```
https://graph.facebook.com/v25.0/act_<ID>/insights?level=campaign&fields=campaign_name,spend&date_preset=last_7d&access_token=<TOKEN>
```
Balik JSON = berhasil.

---

## 2. Pasang script (di project J&T Data Loader yang sudah ada)

MetaAds.gs **satu project** dengan `Code.gs` (J&T Data Loader) karena keduanya
terikat ke **spreadsheet yang sama** yang dibaca dashboard. Jadi cukup tambah
satu file, tidak perlu project/binding baru.

1. Buka **spreadsheet dashboard** → **Extensions → Apps Script** (project J&T Data
   Loader yang sudah berisi `Code.gs`, `Order.gs`, dll).
2. **+ File → Script**, beri nama `MetaAds`, tempel **seluruh isi** `JnT_GSheet_System/MetaAds.gs`.
   (File ini memakai ulang `getSpreadsheet()` & `SPREADSHEET_ID` dari `Code.gs` — jangan
   dideklarasikan ulang.)
3. **Project Settings** (⚙️) → **Script properties** → tambah dua:
   - `META_TOKEN` = token dari langkah 1.4
   - `META_ADACCT` = `act_<ID>` dari langkah 1.5
4. Kembali ke editor → pilih fungsi **`setupMetaAds`** → **Run** (approve izin saat diminta).
   Ini membuat sheet `Meta-Ads` & `Ref_Ads_Map`.
5. Pilih **`testMeta`** → **Run** → cek **Execution log**: harus muncul jumlah baris insights
   + jumlah campaign budget. Kalau error, cek token/aset (langkah 1.3).

> Jangan lupa: setiap kali mengubah kode di project ini dan men-deploy ulang web
> app-nya, naikkan `APP_VERSION` di `Code.gs` (banner "versi baru").

---

## 3. Tarik data pertama + jadwalkan

- **Backfill** (isi histori): buka fungsi `jalankanBackfill`, ubah tanggal `since` di dalamnya bila perlu, lalu **Run**. Default menarik sejak 1 Juli 2026 s/d hari ini.
- **Otomatis harian**: pilih `pasangTriggerHarian` → **Run**. Terpasang jalan ~06:00 tiap hari, menarik ulang **7 hari terakhir** (karena angka Meta bisa berubah retroaktif ~72 jam) dan meng-upsert (tidak menduplikasi).
- Bila script terikat pada Sheet, akan muncul menu **"Meta Ads"** di toolbar Sheet untuk menjalankan manual.

---

## 4. Memory pelabelan campaign → produk (`Ref_Ads_Map`)

Nama campaign Meta memuat nama barang + "noise" (`| tanggal`, `POSTID n`, `NEW`).
Sistem membersihkannya lalu mencocokkan ke **`Import-Stock` kolom `Nama Produk`**.

Kolom `match_status` di `Meta-Ads`:

| Status | Arti | Tindakan |
|---|---|---|
| `AUTO` | cocok otomatis (skor ≥ 0.55) | biasanya sudah benar |
| `TERKUNCI` | Anda sudah konfirmasi di `Ref_Ads_Map` | permanen |
| `PERLU REVIEW` | tak yakin / produk belum ada di katalog | **labeli manual** |

**Cara mengunci pelabelan (sekali saja):** buka sheet **`Ref_Ads_Map`**, cari baris
campaign, isi kolom **`sku`** (dan `nama_barang`) yang benar, lalu set **`locked` = `TRUE`**.
Sejak run berikutnya, campaign itu **selalu** dipetakan ke SKU tersebut — tidak
akan ditimpa auto-match lagi. Campaign untuk produk yang memang belum ada di
`Import-Stock` akan tetap `PERLU REVIEW` sampai produknya masuk katalog.

> Catatan: satu campaign = satu SKU utama. Bundel multi-produk ditangani menyusul.

---

## 5. Arti kolom `Meta-Ads`

`date, campaign_id, campaign_name, produk, sku, match_status, match_confidence,
spend, impressions, clicks, link_click, cpc, cpm, add_to_cart, landing_page_view,
purchases, cost_per_purchase, daily_budget, budget_remaining, budget_type, status, updated_at`

- **purchases / cost_per_purchase** = event *purchase* dari Pixel Meta (satu kanonik, bukan
  penjumlahan alias). Ini "order ditempatkan di web", **belum tentu = order COD terbayar**.
- **daily_budget / budget_remaining** = snapshot budget campaign saat penarikan (IDR apa adanya).
- Angka **purchase/CPA nyata** (berbasis order internal & retur) dihitung di **Modul 5 dashboard**,
  bukan di sheet ini.

---

## 6. Langkah berikutnya

Setelah `Meta-Ads` & `Ref_Ads_Map` terisi, lanjut membangun **Modul 5** di dashboard:
join `Meta-Ads` ↔ katalog (per SKU) → CPA/CPP nyata, ROAS, CM setelah iklan, dan
verdict 🟢 Scale / 🟡 Optimize / 🔴 Kill.
