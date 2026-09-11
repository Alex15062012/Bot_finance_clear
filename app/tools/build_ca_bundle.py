"""Сборка CA-бандла: certifi + сертификаты Минцифры (для TLS к platform-api2.max.ru)."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[2]
CERTS_DIR = ROOT / "certs"
BUNDLE_PATH = CERTS_DIR / "ca-bundle.pem"

ROOT_CA_URL = "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt"
SUB_CA_URL = "https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt"


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        dest.write_bytes(resp.read())


def build() -> Path:
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    root_ca = CERTS_DIR / "russian_trusted_root_ca.crt"
    sub_ca = CERTS_DIR / "russian_trusted_sub_ca.crt"

    if not root_ca.exists():
        download(ROOT_CA_URL, root_ca)
    if not sub_ca.exists():
        download(SUB_CA_URL, sub_ca)

    parts = [
        Path(certifi.where()).read_text(encoding="utf-8"),
        root_ca.read_text(encoding="utf-8"),
        sub_ca.read_text(encoding="utf-8"),
    ]
    BUNDLE_PATH.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Wrote {BUNDLE_PATH} ({BUNDLE_PATH.stat().st_size} bytes)")
    return BUNDLE_PATH


if __name__ == "__main__":
    build()
