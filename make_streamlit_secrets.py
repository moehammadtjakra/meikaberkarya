# -*- coding: utf-8 -*-
"""
make_streamlit_secrets.py
=========================
Ubah credentials/oauth_client.json + credentials/authorized_user.json + GSHEET_ID
menjadi blok TOML siap tempel ke Streamlit Cloud -> Settings -> Secrets.

Jalankan SETELAH `python gsheet_login.py` berhasil:
    python make_streamlit_secrets.py
Lalu salin seluruh output di bawah garis ke kolom Secrets di Streamlit.
"""
import json
import os
import config


def _v(x):
    """Format satu nilai sebagai TOML."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (int, float)):
        return str(x)
    if isinstance(x, (list, tuple)):
        return "[" + ", ".join(_v(i) for i in x) + "]"
    s = str(x).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _table(header, d):
    lines = [f"[{header}]"]
    for k, val in d.items():
        if val is None:
            continue
        lines.append(f"{k} = {_v(val)}")
    return "\n".join(lines)


def main():
    cred = config.GSHEET_OAUTH_CRED
    authf = config.GSHEET_OAUTH_TOKEN
    for p in (cred, authf):
        if not os.path.exists(p):
            raise SystemExit(f"[!] Belum ada: {p}\n    Jalankan dulu: python gsheet_login.py")

    client = json.load(open(cred, encoding="utf-8"))
    inner = client.get("installed") or client.get("web") or client
    auth = json.load(open(authf, encoding="utf-8"))

    print("\n" + "=" * 64)
    print(" SALIN MULAI DARI SINI ke Streamlit -> Settings -> Secrets ")
    print("=" * 64 + "\n")
    print("[gsheet]")
    print(f'id = {_v(config.GSHEET_ID)}\n')
    print(_table("gsheet.oauth_client.installed", inner) + "\n")
    print(_table("gsheet.authorized_user", auth))
    print("\n" + "=" * 64)
    print(" SAMPAI SINI ")
    print("=" * 64)


if __name__ == "__main__":
    main()
