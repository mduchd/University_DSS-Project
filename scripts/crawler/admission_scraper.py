"""
Admission & Tuition Scraper
Fetches major code, major name, admission combinations, scores, and tuition fees per school and year.
"""

import time
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup

from .config import (
    BENCHMARK_ENDPOINT,
    DEFAULT_HEADERS,
    DEFAULT_RETRY,
    DEFAULT_TIMEOUT,
    REQUEST_DELAY,
    RETRY_DELAY,
)


class AdmissionScraper:
    def __init__(self, pool_size: int = 20):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def scrape_school_admission(
        self,
        school: Dict,
        years: List[str],
    ) -> List[Dict]:
        """
        Scrapes admission data for a single school across specified years.
        Returns a list of records containing major codes, names, combinations, scores, and tuition.
        """
        school_id = school["school_id"]
        school_code = school.get("school_code", "")
        school_name = school.get("school_name", "")

        records: List[Dict] = []

        for year in years:
            html = self._fetch_benchmark_html(school_id, year)
            if not html:
                continue

            year_records = self._parse_benchmark_table(
                html=html,
                school_id=school_id,
                school_code=school_code,
                school_name=school_name,
                year=year,
            )
            records.extend(year_records)
            time.sleep(REQUEST_DELAY)

        return records

    def _fetch_benchmark_html(self, school_id: str, year: str) -> Optional[str]:
        """Calls the benchmark endpoint for school_id and year."""
        url = BENCHMARK_ENDPOINT.format(school_id=school_id, year=year)

        for attempt in range(DEFAULT_RETRY):
            try:
                resp = self.session.get(url, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("html", "")
            except Exception as e:
                if attempt == DEFAULT_RETRY - 1:
                    print(f"Error fetching benchmark for school {school_id}, year {year}: {e}")
                time.sleep(RETRY_DELAY)

        return None

    def _parse_benchmark_table(
        self,
        html: str,
        school_id: str,
        school_code: str,
        school_name: str,
        year: str,
    ) -> List[Dict]:
        """Parses HTML table rows into structured dictionaries."""
        results = []
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr", class_="university__benchmark")

        for r in rows:
            # Skip chart details container row
            classes = r.get("class", [])
            if "university__benchmark--chart" in classes:
                continue

            tds = r.find_all("td")
            if len(tds) < 4:
                continue

            # Column 0: Tên ngành, mã ngành
            td0 = tds[0]
            major_elem = td0.find("strong")
            major_name = major_elem.get_text(strip=True) if major_elem else ""

            # Extract 7-digit code (e.g. 7480202 or 7340204)
            spans = td0.find_all("span")
            major_code = ""
            for s in reversed(spans):
                text = s.get_text(strip=True)
                if text and any(c.isdigit() for c in text):
                    major_code = text
                    break

            # Fallback for major_name if not in <strong>
            if not major_name and td0.contents:
                major_name = td0.contents[0].get_text(strip=True) if hasattr(td0.contents[0], "get_text") else str(td0.contents[0]).strip()

            # Column 1: Tổ hợp môn xét tuyển
            combination = tds[1].get_text(strip=True)

            # Column 2: Điểm chuẩn THPT
            score_elem = tds[2].find("span")
            thpt_score = score_elem.get_text(strip=True) if score_elem else tds[2].get_text(strip=True)

            # Column 3: Phương thức khác / ghi chú
            other_criteria = tds[3].get_text(strip=True) if len(tds) > 3 else ""

            # Column 4: Học phí (nếu có cột học phí)
            tuition_fee = ""
            if len(tds) >= 5:
                tuition_fee = tds[4].get_text(strip=True)

            if major_name or major_code:
                results.append(
                    {
                        "school_id": school_id,
                        "school_code": school_code,
                        "school_name": school_name,
                        "major_code": major_code,
                        "major_name": major_name,
                        "subject_group": combination,
                        "thpt_score": thpt_score,
                        "tuition_fee": tuition_fee,
                        "other_criteria": other_criteria,
                        "admission_year": year,
                    }
                )

        return results
