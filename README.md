# J&T Business Intelligence Dashboard — Meika Berkarya

Dashboard analitik **lokal/offline** untuk data pengiriman J&T. Membaca otomatis
`JnT/jnt_recap.xlsx`, membersihkan data, menghitung baseline & forecast, lalu
menampilkan dashboard interaktif (Streamlit + Plotly) di browser. Tanpa server,
database, upload manual, atau deployment.

## Cara menjalankan (paling mudah)

1. Pastikan **Python 3.10+** terpasang (centang *Add Python to PATH* saat install).
2. **Double-click `start.bat`.**
   - Saat pertama kali, dependency akan dipasang otomatis (perlu internet sekali).
   - Browser akan terbuka di `http://localhost:8501`.
3. Untuk berhenti: tutup jendela hitam (CMD) atau tekan `Ctrl+C`.

> Alternatif: `python run_dashboard.py` dari terminal di folder ini.

## Memperbarui data

Cukup ganti / timpa file **`JnT/jnt_recap.xlsx`** dengan versi terbaru, lalu
klik tombol **🔄 Muat ulang data** di sidebar (atau restart). Sistem otomatis
mendeteksi file terbaru dan menghitung ulang seluruh analisis.

## Membuat file .EXE (opsional)

`.exe` Windows hanya bisa dibuat **di Windows**:

1. Double-click **`build_exe.bat`** (perlu internet, beberapa menit).
2. Hasil: `dist\JnT-Dashboard\JnT-Dashboard.exe` — double-click untuk menjalankan.

## Struktur kode (modular)

| File | Tanggung jawab |
|------|----------------|
| `config.py` | Konstanta: path, pemetaan kolom, aturan settlement, tema |
| `data_loader.py` | Deteksi & baca Excel terbaru otomatis |
| `data_cleaning.py` | Pembersihan & standarisasi data |
| `forecasting.py` | Baseline metrik + forecast volume (scikit-learn) |
| `settlement_engine.py` | Aturan pencairan Mode 1 (harian) & Mode 2 (Sen/Sel/Kam) |
| `cashflow_engine.py` | Simulator cashflow, outstanding, modal kerja |
| `geography_engine.py` | Agregasi wilayah + koordinat peta |
| `visualization.py` | Semua grafik Plotly (tema dark biru-hijau) |
| `insights.py` | Insight otomatis berbahasa Indonesia |
| `dashboard.py` | Antarmuka Streamlit (Modul 1 & 2, filter, KPI) |
| `run_dashboard.py` | Peluncur (skrip / exe) |

Desain modular memudahkan menambah ekspedisi lain (mis. SiCepat, JNE) di masa
depan: cukup tambah pemetaan kolom & folder data baru di `config.py`.

## Peta wilayah

Peta default = **bubble/scatter map offline** (centroid provinsi, tanpa internet).
Untuk choropleth area provinsi, letakkan file GeoJSON di
`assets/indonesia-provinces.geojson` (properti nama provinsi: `Propinsi`) — peta
otomatis beralih ke choropleth.

## Catatan asumsi simulator

- `Proyeksi_Net` = margin **bersih** per resi sukses (sudah dikurangi ongkir &
  COD fee). Ongkir & cashback ditampilkan sebagai komponen biaya informatif.
- COD: dana bersih cair pada tanggal pencairan (delay = distribusi waktu terima
  histori + aturan mode settlement).
- Transfer (non-COD): dianggap prabayar, kas masuk pada hari kirim.
- Semua nilai default diambil dari histori dan **bisa diubah** untuk simulasi
  skenario; proyeksi mengikuti angka yang Anda masukkan.
# meikaberkarya
