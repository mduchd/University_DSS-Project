#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main entry script to run University Admission & Major Data Crawler.

Examples:
  # Cào thử nghiệm 3 trường tiêu biểu:
  python run_crawler.py --limit 3

  # Cào trường cụ thể (ĐH Kinh tế Quốc dân, ĐH Bách khoa Hà Nội, ĐH Công nghệ ĐHQGHN):
  python run_crawler.py --schools KHA,BKA,QHI --years 2025,2026

  # Cào toàn bộ các trường đại học:
  python run_crawler.py --formats csv,json,sqlite
"""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.crawler.cli import main

if __name__ == "__main__":
    main()
