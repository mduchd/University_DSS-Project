"""Lookup local university logo metadata by admission code."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGO_METADATA_PATH = ROOT / "data" / "master" / "university_logos.csv"


class UniversityLogoService:
    @staticmethod
    def _normalise_code(value: object) -> str:
        return str(value or "").strip().upper()

    @lru_cache(maxsize=1)
    def _load(self) -> dict[str, dict[str, str]]:
        if not LOGO_METADATA_PATH.exists():
            return {}
        with LOGO_METADATA_PATH.open("r", encoding="utf-8-sig", newline="") as file:
            return {
                self._normalise_code(row.get("school_code")): row
                for row in csv.DictReader(file)
                if self._normalise_code(row.get("school_code"))
            }

    def get(self, school_code: object, school_name: object = "") -> dict[str, object]:
        row = self._load().get(self._normalise_code(school_code), {})
        name = str(school_name or row.get("school_name", "")).strip()
        logo_path = str(row.get("logo_path", "")).strip()
        return {
            "logo_url": logo_path or None,
            "logo_alt": str(row.get("alt_text", "")).strip() or f"Logo {name}",
            "has_logo": bool(logo_path),
        }

    def clear_cache(self) -> None:
        self._load.cache_clear()


university_logo_service = UniversityLogoService()
