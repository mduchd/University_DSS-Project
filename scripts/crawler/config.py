"""
Crawler Configuration and Constants
"""

import os
from pathlib import Path

# Paths
CRAWLER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CRAWLER_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
ADMISSION_RAW_DIR = RAW_DATA_DIR / "admission"
MASTER_RAW_DIR = RAW_DATA_DIR / "master"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CACHE_DIR = PROJECT_ROOT / ".cache"

# Ensure directories exist
for directory in [ADMISSION_RAW_DIR, MASTER_RAW_DIR, PROCESSED_DATA_DIR, CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Cache file paths
SCHOOL_CACHE_FILE = CACHE_DIR / "schools_cache.json"
MAJOR_CATALOG_FILE = MASTER_RAW_DIR / "danh_muc_nganh_chuan.json"

# Web Scraping Configuration
BASE_URL = "https://diemthi.vnexpress.net"
COLLEGE_SEARCH_ENDPOINT = f"{BASE_URL}/tra-cuu-dai-hoc/loadcollegev3"
BENCHMARK_ENDPOINT = f"{BASE_URL}/tra-cuu-dai-hoc/loadbenchmark/id/{{school_id}}/year/{{year}}/sortby/1/block_name/all"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}

# Scraping settings
DEFAULT_TIMEOUT = 15
DEFAULT_RETRY = 3
RETRY_DELAY = 1.5
REQUEST_DELAY = 0.3  # Polite rate limiting between requests

# Default recent 2 years
DEFAULT_YEARS = ["2026", "2025"]
