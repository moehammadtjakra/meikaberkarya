# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

This repo holds **four independent systems** built for Meika Berkarya's J&T shipping/e-commerce operations. They don't share code or a deploy pipeline — treat each as its own project when making changes:

1. **Root — J&T BI Dashboard** (Python/Streamlit): local, offline analytics dashboard reading `JnT/jnt_recap.xlsx`.
2. **`Admin_Order_System/`** (Google Apps Script): OrderOnline ⇄ J&T order pipeline — import orders, manage stock, build J&T upload batches, pull tracking numbers back.
3. **`CS_Undelivered_System/`** (Google Apps Script, two separate Apps Script *projects* sharing one spreadsheet): `Sistem1_Supervisor` uploads/distributes undelivered-package data to CS reps by province and pulls J&T tracking; `Sistem2_CS` is the CS worklist for following up on those packages.
4. **`JnT_GSheet_System/`** (Google Apps Script): replaces an Excel Power Query workflow — uploads raw J&T export files into a Google Sheet with upsert-by-waybill, plus a settlement/dashboard view.

All UI text, code comments, and docs (`PANDUAN_*.md`) are in **Bahasa Indonesia** — keep new comments/UI text/commit-facing docs in Indonesian to match the existing codebase, unless told otherwise.

There is no test suite and no linter configured anywhere in this repo.

## Python dashboard (root)

### Running it

```bash
pip install -r requirements.txt
python run_dashboard.py        # or: streamlit run dashboard.py
# or double-click start.bat on Windows
```

Dashboard opens at `http://localhost:8501`. Data source is auto-detected — no upload UI: it reads `JnT/jnt_recap.xlsx` (see `data_loader.find_excel()`, which also falls back to any `*recap*.xlsx` in `JnT/`). To pick up new data, overwrite that file and click "🔄 Muat ulang data" in the sidebar.

### Building the .exe

```bash
build_exe.bat   # Windows only; PyInstaller onedir build -> dist/JnT-Dashboard/JnT-Dashboard.exe
```
The `JnT/` data folder and `assets/` are bundled into the exe at build time. `dist/` and `build/` output is checked into the repo (no `.gitignore`).

### Architecture — data pipeline

The pipeline is a strict one-directional chain; each module only depends on modules to its left:

```
config.py  ->  data_loader.py  ->  data_cleaning.py  ->  forecasting.py
                                                       -> settlement_engine.py
                                                       -> cashflow_engine.py
                                                       -> geography_engine.py
                                                       -> product_engine.py
                                                       -> target_engine.py
                                                       -> daily_engine.py
                                                            |
                                                            v
                                          visualization.py, insights.py, formatting.py
                                                            |
                                                            v
                                                     dashboard.py (Streamlit UI)
```

- **`config.py`** is the single source of truth for file paths, the Excel column-name mapping (`COLMAP_ALL_RESI`, `COLMAP_SETTLE` — raw Excel header -> canonical internal name), settlement-payout rules, default simulator assumptions (`DEFAULTS`), and the dark blue/green theme dict (`THEME`, `COLORSCALE`, `CATEGORICAL_COLORS`). Adding a new expedition (e.g. SiCepat) means adding its column mapping + data folder here, per the README.
- **`data_loader.py`**: finds the latest `.xlsx` and reads the `all_resi` / `settle_reconcile` (or `settle_reconsile`, both spellings supported) / `problem` sheets.
- **`data_cleaning.py`**: renames columns via the `COLMAP_*` dicts and standardizes types.
- Engine modules (`forecasting.py`, `settlement_engine.py`, `cashflow_engine.py`, `geography_engine.py`, `product_engine.py`, `target_engine.py`, `daily_engine.py`) each own one analytical concern and take cleaned DataFrames in, return computed metrics/DataFrames out — no Streamlit imports in these files.
- **`settlement_engine.py`** implements two COD payout modes (see `config.SETTLE_MODES`): Mode 1 = H+1 business day after delivery; Mode 2 (legacy default) = payout only on Mon/Tue/Thu per a receive-day -> payout-day map (`SETTLE_MODE2_RECEIVE_TO_PAYOUT`).
- **`visualization.py`** builds all Plotly charts using `config.THEME`/`COLORSCALE`; **`insights.py`** generates Indonesian-language auto-insights from computed metrics; **`formatting.py`** has Rupiah/number formatting helpers.
- **`dashboard.py`** is the only file that imports Streamlit and wires everything into the UI (Modul 1 = cashflow simulator, Modul 2 = wilayah/geography analysis, plus KPI cards and filters).

Key domain assumption baked into the model (see README "Catatan asumsi simulator"): `Proyeksi_Net` is net margin per successful waybill after shipping cost & COD fee; COD cash lands on the settlement date, non-COD (transfer) is treated as prepaid and lands on ship date.

## Google Apps Script systems

These are **not** deployed via `clasp` or any CLI — the workflow is manual: paste each `.gs`/`.html` file's contents into the Apps Script editor bound to a specific Google Sheet, run a one-time `setup()`/`setup2()` function, then `Deploy -> New deployment -> Web app`. The `.gs`/`.html` files in this repo are the source of truth that gets copy-pasted; there is no automatic sync to the live deployment. Full install steps for each system are in its `PANDUAN_*.md`.

**After editing any `.gs`/`.html` file, when instructing the user to redeploy: they must bump the `APP_VERSION` constant near the top of `Code.gs`.** Every one of these apps polls its own version against the server every ~90s and shows a "new version available" reload banner keyed off that constant — if it isn't bumped, deployed users silently keep running old code with no signal to refresh.

### Admin_Order_System

OrderOnline (marketplace) -> stock check -> J&T upload batch -> tracking pull-back, replacing a manual Excel workflow. Config lives in `CFG` at the top of `Code.gs` (`csSpreadsheetId` for cross-reading the CS Undelivered system's spreadsheet, `driveFolderId`, `jumlahKoli`).

- `Code.gs` — config, order import, region normalization, product/bump mapping.
- `Stok.gs` — multi-warehouse stock ledger, moving-average HPP (cost), SKU registry, category-guessing dictionary (`KAMUS_KATEGORI`).
- `Batch.gs` — FIFO stock allocation by region, batch creation, J&T upload file export.
- `Tracking.gs` — imports J&T's Url-Tracking export and produces `paid`/`unpaid` (retur) CSVs back to OrderOnline.
- `Handover.gs` — daily waybill handover + PDF pickup document generation.

Deliberately kept in its **own spreadsheet**, separate from `CS_Undelivered_System` — different access needs and write patterns (this system rewrites the whole `ORDERS` sheet per batch; CS Undelivered writes per-row from many concurrent users) would otherwise contend on `LockService`. Integration between them is one-directional read-only (Admin Order reads the CS system's spreadsheet by ID for retur status).

SKU matching for products/bumps is fuzzy (similarity-threshold based, not exact match) — see the "1 barang = 1 SKU" section of `PANDUAN_ADMIN_ORDER.md` before touching product-mapping logic in `Stok.gs`; the 93% threshold and 4-step resolution order there are intentional, tuned against real false-positive cases (e.g. `Lampu LED 3W` vs `5W`).

### CS_Undelivered_System

Two **separate** Apps Script projects sharing one spreadsheet (`MASTER_Undelivered` sheet), each deployed independently:

- **`Sistem1_Supervisor/`** — supervisor-facing. `Code.gs` (upload + upsert-by-waybill + auto-distribute to CS by province via `Ref_Provinsi_CS`), `Admin.gs` (manage CS accounts/province mapping), `Report.gs` (read-only CS performance dashboard), `JntTrack.gs` (pulls tracking/POD-photo data from J&T's **unofficial** internal VIP endpoint `jmsvipgw.jntexpress.id` — explicitly a stopgap; see `lacak_()` and the "SOLUSI SEMENTARA" section of `PANDUAN_SISTEM1.md` before relying on it or replacing it once an official API exists).
- **`Sistem2_CS/`** — CS-facing worklist. `Code.gs` only, config in `CFG2` (`spreadsheetId` must point at Sistem 1's spreadsheet, `podFolderId` for proof-of-delivery photo uploads). Writes are per-row (not full-sheet rewrites) specifically so 6–15 CS reps can work concurrently without lock contention — preserve that pattern in any edits.

Access-control model: CS reps only see rows for their assigned province(s), enforced server-side in `Code.gs`, not just hidden in the UI. `superadmin` role sees everything and is intentionally excluded from province-mapping UI.

Upload files are snapshot-reconciled per shipping month: rows previously in a status but missing from the latest upload for that month get auto-archived to `Arsip_Undelivered` (and restored if they reappear later). Don't treat a shrinking row count as data loss — it's the intended archive mechanism.

### JnT_GSheet_System

Replaces an Excel Power Query pipeline. `Code.gs` converts uploaded J&T export files (`.xlsx`/`.xls`) to Google Sheets via Drive, reproduces the old Power Query transforms (column rename/type coercion/computed columns), then **upserts by `No. Waybill`** into `All Resi` / `Settle Reconcile` sheets (waybill comparison ignores whitespace and trailing `.0`). `Dashboard.gs` computes delivery status buckets and J&T settlement-date projections from those two sheets. Supports two different raw formats of the "Settle Reconcile" export transparently (old 11-column and new 7-column J&T format) — see the format-mapping note in `PANDUAN_PASANG.md` before changing column handling in `Code.gs`.

Requires the Drive Advanced Service enabled in the Apps Script project (for `.xls`/`.xlsx` -> Sheet conversion) — this is a manual step in the Apps Script editor, not something expressible in `appsscript.json` dependencies alone for this project (only `Admin_Order_System` declares it there).
