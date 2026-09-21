"""
Crawler Pipeline Orchestrator
Coordinates school discovery, admission scraping, major knowledge enrichment, and multi-format exports.
"""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from tqdm import tqdm

from .admission_scraper import AdmissionScraper
from .config import (
    ADMISSION_RAW_DIR,
    DEFAULT_YEARS,
    PROCESSED_DATA_DIR,
)
from .major_enricher import MajorEnricher
from .school_scraper import SchoolScraper


class CrawlerPipeline:
    def __init__(self, use_cache: bool = True):
        self.school_scraper = SchoolScraper(use_cache=use_cache)
        self.admission_scraper = AdmissionScraper()
        self.major_enricher = MajorEnricher()

    def run(
        self,
        years: Optional[List[str]] = None,
        school_filters: Optional[List[str]] = None,
        limit: Optional[int] = None,
        enrich: bool = True,
        workers: int = 6,
        output_prefix: str = "admission_data",
        export_formats: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Runs the complete extraction, enrichment, and export pipeline.
        """
        target_years = years or DEFAULT_YEARS
        target_formats = export_formats or ["csv", "json"]

        print(f"\n{'='*60}")
        print(f"[*] Starting University Admission Crawler Pipeline")
        print(f"[*] Target Years: {', '.join(target_years)}")
        print(f"[*] School Filters: {school_filters if school_filters else 'All Schools'}")
        print(f"[*] Limit: {limit if limit else 'None'}")
        print(f"[*] Enrich Major Details: {enrich}")
        print(f"{'='*60}\n")

        # Step 1: Discover schools
        all_schools = self.school_scraper.fetch_all_schools()
        target_schools = self.school_scraper.filter_schools(
            all_schools, codes_or_names=school_filters, limit=limit
        )

        print(f"Found {len(target_schools)} schools matching criteria.\n")
        if not target_schools:
            print("[!] No schools matched criteria. Exiting.")
            return pd.DataFrame()

        # Step 2: Scrape admission data
        raw_records: List[Dict] = []
        with tqdm(total=len(target_schools), desc="Scraping Schools", unit="school") as pbar:
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_school = {
                        executor.submit(
                            self.admission_scraper.scrape_school_admission,
                            school,
                            target_years,
                        ): school
                        for school in target_schools
                    }
                    for future in as_completed(future_to_school):
                        school = future_to_school[future]
                        try:
                            school_records = future.result()
                            raw_records.extend(school_records)
                        except Exception as e:
                            print(f"[!] Error scraping {school.get('school_code', '')}: {e}")
                        pbar.set_postfix_str(f"{school.get('school_code', '')} - {school.get('school_name', '')[:20]}")
                        pbar.update(1)
            else:
                for school in target_schools:
                    pbar.set_postfix_str(f"{school.get('school_code', '')} - {school.get('school_name', '')[:20]}")
                    school_records = self.admission_scraper.scrape_school_admission(
                        school=school,
                        years=target_years,
                    )
                    raw_records.extend(school_records)
                    pbar.update(1)

        print(f"\nScraped {len(raw_records)} raw admission records.")
        if not raw_records:
            print("[!] No admission records collected.")
            return pd.DataFrame()

        # Step 3: Enrich with Major Description, Curriculum, and Career Opportunities
        enriched_records: List[Dict] = []
        desc = "Enriching Major Info" if enrich else "Structuring Records"
        for rec in tqdm(raw_records, desc=desc, unit="record"):
            item = {
                "ma_truong": rec.get("school_code") or "",
                "ten_truong": rec.get("school_name") or "",
                "ma_nganh": rec.get("major_code") or "",
                "ten_nganh": rec.get("major_name") or "",
                "to_hop_xet_tuyen": rec.get("subject_group") or "",
                "diem_chuan": rec.get("thpt_score") or "",
                "hoc_phi": rec.get("tuition_fee") or "",
                "nam_tuyen_sinh": rec.get("admission_year") or "",
                "phuong_thuc_khac": rec.get("other_criteria") or "",
            }

            if enrich:
                enrichment = self.major_enricher.enrich(
                    major_code=rec.get("major_code", ""),
                    major_name=rec.get("major_name", ""),
                )
                item["mo_ta_nganh"] = enrichment.get("major_description", "")
                item["chuong_trinh_dao_tao"] = enrichment.get("curriculum", "")
                item["co_hoi_nghe_nghiep"] = enrichment.get("career_opportunities", "")
                item["nhom_nganh"] = enrichment.get("major_group", "")
            else:
                item["mo_ta_nganh"] = ""
                item["chuong_trinh_dao_tao"] = ""
                item["co_hoi_nghe_nghiep"] = ""
                item["nhom_nganh"] = ""

            enriched_records.append(item)

        df = pd.DataFrame(enriched_records)

        # Step 4: Export to designated formats
        years_suffix = "_".join(target_years)
        file_base_name = f"{output_prefix}_{years_suffix}"

        self._export_data(df, file_base_name, target_formats)

        print(f"\n[+] Pipeline complete! Processed {len(df)} records across {df['ma_truong'].nunique()} universities.\n")
        return df

    def _export_data(self, df: pd.DataFrame, file_base_name: str, formats: List[str]):
        """Exports dataframe to CSV, JSON, and SQLite."""
        # 1. Export CSV (utf-8-sig for perfect Excel compatibility with Vietnamese)
        if "csv" in formats:
            raw_csv = ADMISSION_RAW_DIR / f"{file_base_name}.csv"
            proc_csv = PROCESSED_DATA_DIR / f"{file_base_name}.csv"
            df.to_csv(raw_csv, index=False, encoding="utf-8-sig")
            df.to_csv(proc_csv, index=False, encoding="utf-8-sig")
            print(f"[+] Saved CSV: {raw_csv}")

        # 2. Export JSON
        if "json" in formats:
            raw_json = ADMISSION_RAW_DIR / f"{file_base_name}.json"
            proc_json = PROCESSED_DATA_DIR / f"{file_base_name}.json"
            records = df.to_dict(orient="records")
            with open(raw_json, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            with open(proc_json, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print(f"[+] Saved JSON: {raw_json}")

        # 3. Export SQLite Database
        if "sqlite" in formats:
            db_path = PROCESSED_DATA_DIR / "university_admissions.db"
            conn = sqlite3.connect(db_path)
            df.to_sql("admissions", conn, if_exists="replace", index=False)
            conn.close()
            print(f"[+] Saved SQLite Database: {db_path}")
