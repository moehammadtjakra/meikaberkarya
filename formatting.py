# -*- coding: utf-8 -*-
"""
formatting.py
=============
Format angka gaya Indonesia yang konsisten di seluruh dashboard.

- rupiah(v)  -> ringkas + satuan: 4000 -> "Rp4.000", 90 juta -> "Rp90 juta",
                1,5 miliar -> "Rp1,5 miliar". Pemisah ribuan titik, desimal koma.
- ribuan(v)  -> angka penuh dgn pemisah ribuan: 1234567 -> "1.234.567".
- jumlah(v)  -> bilangan cacah (lead/order/resi) dgn pemisah ribuan.
- persen(v)  -> "85,3%".
"""

from __future__ import annotations


def _id(s: str) -> str:
    """Ubah format en (1,234.5) -> id (1.234,5)."""
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def rupiah(v, prefix: str = "Rp") -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if v != v:  # NaN
        return "-"
    sign = "-" if v < 0 else ""
    n = abs(v)
    if n >= 1e12:
        s = _id(f"{n/1e12:.2f}").rstrip("0").rstrip(",") + " triliun"
    elif n >= 1e9:
        s = _id(f"{n/1e9:.2f}").rstrip("0").rstrip(",") + " miliar"
    elif n >= 1e6:
        s = _id(f"{n/1e6:.1f}").rstrip("0").rstrip(",") + " juta"
    else:
        s = f"{n:,.0f}".replace(",", ".")
    return f"{sign}{prefix}{s}"


def ribuan(v) -> str:
    try:
        return f"{float(v):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def jumlah(v) -> str:
    try:
        return f"{round(float(v)):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def persen(v, dec: int = 1) -> str:
    try:
        return _id(f"{float(v):.{dec}f}") + "%"
    except (TypeError, ValueError):
        return "-"
