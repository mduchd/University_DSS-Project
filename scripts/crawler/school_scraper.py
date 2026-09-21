"""
University and College Discovery Scraper
Fetches all universities across Vietnam with school codes, names, and internal IDs.
"""

import json
import re
import string
import time
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup

from .config import (
    COLLEGE_SEARCH_ENDPOINT,
    DEFAULT_HEADERS,
    DEFAULT_RETRY,
    DEFAULT_TIMEOUT,
    REQUEST_DELAY,
    RETRY_DELAY,
    SCHOOL_CACHE_FILE,
)


class SchoolScraper:
    def __init__(self, use_cache: bool = True):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.use_cache = use_cache

    def fetch_all_schools(self, force_refresh: bool = False) -> List[Dict]:
        """
        Fetches all available universities and colleges.
        Uses cached data if available unless force_refresh is True.
        """
        if self.use_cache and not force_refresh and SCHOOL_CACHE_FILE.exists():
            try:
                with open(SCHOOL_CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_schools = json.load(f)
                if cached_schools and len(cached_schools) > 100:
                    return cached_schools
            except Exception:
                pass

        print("Fetching fresh university directory...")
        discovered: Dict[str, Dict] = {}

        # Queries covering all Vietnamese schools
        queries = (
            list(string.ascii_lowercase)
            + ["đ", "ă", "â", "ê", "ô", "ơ", "ư"]
            + [str(i) for i in range(10)]
            + ["đại học", "học viện", "trường", "phân hiệu"]
        )

        for q in queries:
            schools_chunk = self._search_schools(q)
            for s in schools_chunk:
                discovered[s["school_id"]] = s
            time.sleep(REQUEST_DELAY)

        schools_list = list(discovered.values())
        # Sort by school_code, then school_name
        schools_list.sort(key=lambda x: (x.get("school_code") or "", x.get("school_name") or ""))

        # Save to cache
        try:
            with open(SCHOOL_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(schools_list, f, ensure_ascii=False, indent=2)
            print(f"Discovered and cached {len(schools_list)} universities/colleges.")
        except Exception as e:
            print(f"Warning: Could not save school cache: {e}")

        return schools_list

    def _search_schools(self, query: str) -> List[Dict]:
        """Queries the autocomplete endpoint for matching schools."""
        for attempt in range(DEFAULT_RETRY):
            try:
                resp = self.session.get(
                    COLLEGE_SEARCH_ENDPOINT,
                    params={"input_college": query},
                    timeout=DEFAULT_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    html_content = data.get("html", "")
                    return self._parse_schools_from_html(html_content)
            except Exception as e:
                if attempt == DEFAULT_RETRY - 1:
                    print(f"Error querying '{query}': {e}")
                time.sleep(RETRY_DELAY)
        return []

    def _parse_schools_from_html(self, html: str) -> List[Dict]:
        """Parses schools from autocomplete HTML snippet."""
        results = []
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("a", class_="licollege")

        for item in items:
            school_id = item.get("data-id")
            school_name = item.get("data-name", "").strip()
            data_text = item.get("data-text", "").strip()
            href = item.get("href", "").strip()

            if not school_id or not school_name:
                continue

            # Extract school_code from data_text: e.g. "KHA - Đại học Kinh tế Quốc dân"
            school_code = ""
            if " - " in data_text:
                school_code = data_text.split(" - ")[0].strip()
            elif " | " in data_text:
                school_code = data_text.split(" | ")[0].strip()

            results.append(
                {
                    "school_id": str(school_id),
                    "school_code": school_code,
                    "school_name": school_name,
                    "full_title": data_text,
                    "url": href,
                }
            )

        return results

    def filter_schools(
        self,
        schools: List[Dict],
        codes_or_names: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """Filters schools by codes or names, with optional limit."""
        if not codes_or_names:
            filtered = schools
        else:
            targets = {t.strip().upper() for t in codes_or_names}
            filtered = []
            for s in schools:
                sc = (s.get("school_code") or "").upper()
                sn = (s.get("school_name") or "").upper()
                if sc in targets or any(t in sn for t in targets):
                    filtered.append(s)

        if limit and limit > 0:
            filtered = filtered[:limit]

        return filtered
