"""
Command Line Interface (CLI) for University Admission Crawler
"""

import argparse
import sys
from typing import List

from .config import DEFAULT_YEARS
from .pipeline import CrawlerPipeline


def parse_args(args: List[str] = None):
    parser = argparse.ArgumentParser(
        description="Tool cào dữ liệu tuyển sinh đại học (Mã ngành, Tên ngành, Trường, Tổ hợp, Học phí, CTĐT, Mô tả, Cơ hội việc làm)"
    )

    parser.add_argument(
        "--years",
        type=str,
        default=",".join(DEFAULT_YEARS),
        help=f"Danh sách năm tuyển sinh (ngăn cách bằng dấu phẩy), mặc định: {','.join(DEFAULT_YEARS)}",
    )

    parser.add_argument(
        "--schools",
        type=str,
        default="",
        help="Mã hoặc tên trường cần cào (ví dụ: KHA,BKA,QHI hoặc bỏ trống để cào tất cả)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số lượng trường cần cào (dùng để kiểm thử nhanh)",
    )

    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Tắt tính năng làm giàu mô tả ngành, chương trình đào tạo và cơ hội nghề nghiệp",
    )

    parser.add_argument(
        "--formats",
        type=str,
        default="csv,json",
        help="Định dạng xuất file: csv,json,sqlite (mặc định: csv,json)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Số lượng luồng cào song song (mặc định: 6)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="university_admissions",
        help="Tiền tố tên file xuất ra (mặc định: university_admissions)",
    )

    parser.add_argument(
        "--force-refresh-schools",
        action="store_true",
        help="Tải mới lại danh bạ trường đại học thay vì dùng cache",
    )

    return parser.parse_args(args)


def main():
    args = parse_args()

    # Parse years
    years = [y.strip() for y in args.years.split(",") if y.strip()]

    # Parse school filters
    school_filters = [s.strip() for s in args.schools.split(",") if s.strip()] if args.schools else None

    # Parse export formats
    export_formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]

    enrich = not args.no_enrich

    pipeline = CrawlerPipeline(use_cache=not args.force_refresh_schools)
    pipeline.run(
        years=years,
        school_filters=school_filters,
        limit=args.limit,
        enrich=enrich,
        workers=args.workers,
        output_prefix=args.output,
        export_formats=export_formats,
    )


if __name__ == "__main__":
    main()
