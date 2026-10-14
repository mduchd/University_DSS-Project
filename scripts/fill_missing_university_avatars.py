"""Create deterministic local initials avatars for unresolved schools.

This is the final visual fallback: every school gets an image asset while the
metadata keeps the distinction between an official logo and a generated avatar.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "data" / "master" / "university_logos.csv"
ASSET_DIR = ROOT / "static" / "img" / "universities"
COMMON_WORDS = {"trường", "đại", "học", "viện", "khoa", "phân", "hiệu"}
PALETTE = ["#4255ff", "#0f766e", "#b45309", "#7c3aed", "#be123c", "#0369a1", "#4d7c0f"]


def initials(name: str) -> str:
    words = [word for word in re.split(r"\s+", name.strip()) if word]
    meaningful = [word for word in words if word.casefold() not in COMMON_WORDS]
    source = meaningful or words or ["DH"]
    letters = "".join(word[0] for word in source[-2:])
    return unicodedata.normalize("NFKD", letters).encode("ascii", "ignore").decode().upper() or "DH"


def avatar_svg(code: str, name: str) -> str:
    color = PALETTE[int(hashlib.sha1(code.encode()).hexdigest()[:8], 16) % len(PALETTE)]
    label = html.escape(initials(name))
    accessible_name = html.escape(f"Logo đại diện {name}")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="{accessible_name}">
  <rect width="128" height="128" rx="24" fill="{color}"/>
  <text x="64" y="70" text-anchor="middle" dominant-baseline="middle" fill="#ffffff" font-family="Arial, sans-serif" font-size="34" font-weight="700">{label}</text>
</svg>
'''


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    generated = 0
    for row in rows:
        if row.get("logo_path"):
            continue
        code = str(row.get("school_code", "")).strip().upper()
        name = str(row.get("school_name", "")).strip()
        if not code:
            continue
        filename = f"{code}.svg"
        (ASSET_DIR / filename).write_text(avatar_svg(code, name), encoding="utf-8")
        row["logo_path"] = f"/static/img/universities/{filename}"
        row["alt_text"] = f"Logo đại diện {name}"
        row["status"] = "generated_avatar"
        row["source_url"] = ""
        generated += 1

    fields = ["school_code", "school_name", "official_url", "source_url", "logo_path", "alt_text", "status"]
    with METADATA_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"generated={generated}")


if __name__ == "__main__":
    main()
