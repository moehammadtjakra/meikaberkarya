# -*- coding: utf-8 -*-
"""
planning.py
===========
Simpan / muat / hapus "planning" simulasi ke file JSON di folder `plans/`.
Tiap plan berisi nilai parameter global + tabel produk, diberi nama.

Catatan: penyimpanan berbasis file lokal. Di server ephemeral (mis. Streamlit
Cloud) file bisa hilang saat reboot — untuk arsip permanen, jalankan lokal.
"""
from __future__ import annotations
import json
import os
import re

import config

PLAN_DIR = os.path.join(config.BASE_DIR, "plans")


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip())
    return s[:60] or "plan"


def list_plans() -> list[str]:
    if not os.path.isdir(PLAN_DIR):
        return []
    out = []
    for f in os.listdir(PLAN_DIR):
        if f.endswith(".json"):
            try:
                out.append(json.load(open(os.path.join(PLAN_DIR, f),
                                          encoding="utf-8")).get("name", f[:-5]))
            except Exception:
                out.append(f[:-5])
    return sorted(out)


def save_plan(name: str, data: dict) -> str:
    os.makedirs(PLAN_DIR, exist_ok=True)
    path = os.path.join(PLAN_DIR, _slug(name) + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"name": name, "data": data}, f, ensure_ascii=False,
                  indent=2, default=str)
    return path


def load_plan(name: str) -> dict | None:
    path = os.path.join(PLAN_DIR, _slug(name) + ".json")
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))


def delete_plan(name: str) -> bool:
    path = os.path.join(PLAN_DIR, _slug(name) + ".json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
