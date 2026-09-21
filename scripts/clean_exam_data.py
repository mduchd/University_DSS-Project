#!/usr/bin/env python3
"""Làm sạch dữ liệu điểm thi THPT năm 2023 và 2024.

Pipeline chỉ dùng thư viện chuẩn Python, đọc từng dòng để phù hợp với các file
lớn và luôn ghi kết quả sang data/cleaned thay vì thay đổi dữ liệu gốc.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


SOURCE_COLUMNS = (
    "SBD",
    "Nam",
    "Tinh",
    "SBD_New",
    "Toan",
    "NguVan",
    "VatLy",
    "HoaHoc",
    "SinhHoc",
    "LichSu",
    "DiaLy",
    "GDCD",
    "NgoaiNgu",
    "MaMonNgoaiNgu",
    "TongDiem",
    "KhoiA",
    "KhoiA1",
    "KhoiB",
    "KhoiC",
    "KhoiD",
    "KHTN",
    "KHXH",
    "KhoiA02",
    "KhoiC01",
    "KhoiD07",
    "TongDiemKHTN",
    "TongDiemKHXH",
)

COLUMN_MAPPING = {
    "SBD": "sbd",
    "Nam": "nam",
    "Tinh": "ma_tinh",
    "SBD_New": "sbd_noi_tinh",
    "Toan": "toan",
    "NguVan": "ngu_van",
    "VatLy": "vat_ly",
    "HoaHoc": "hoa_hoc",
    "SinhHoc": "sinh_hoc",
    "LichSu": "lich_su",
    "DiaLy": "dia_ly",
    "GDCD": "gdcd",
    "NgoaiNgu": "ngoai_ngu",
    "MaMonNgoaiNgu": "ma_mon_ngoai_ngu",
    "TongDiem": "tong_diem",
    "KhoiA": "khoi_a",
    "KhoiA1": "khoi_a1",
    "KhoiB": "khoi_b",
    "KhoiC": "khoi_c",
    "KhoiD": "khoi_d",
    "KHTN": "khtn",
    "KHXH": "khxh",
    "KhoiA02": "khoi_a02",
    "KhoiC01": "khoi_c01",
    "KhoiD07": "khoi_d07",
    "TongDiemKHTN": "tong_diem_khtn",
    "TongDiemKHXH": "tong_diem_khxh",
}

OUTPUT_COLUMNS = tuple(COLUMN_MAPPING.values())
SUBJECT_COLUMNS = (
    "Toan",
    "NguVan",
    "VatLy",
    "HoaHoc",
    "SinhHoc",
    "LichSu",
    "DiaLy",
    "GDCD",
    "NgoaiNgu",
)
AVERAGE_COLUMNS = ("KHTN", "KHXH")
BLOCK_COLUMNS = (
    "KhoiA",
    "KhoiA1",
    "KhoiB",
    "KhoiC",
    "KhoiD",
    "KhoiA02",
    "KhoiC01",
    "KhoiD07",
)
TOTAL_COLUMNS = ("TongDiem", "TongDiemKHTN", "TongDiemKHXH")
NUMERIC_COLUMNS = SUBJECT_COLUMNS + AVERAGE_COLUMNS + BLOCK_COLUMNS + TOTAL_COLUMNS
LANGUAGE_CODES = {f"N{index}" for index in range(1, 8)}
FORMULAS = {
    "KhoiA": ("sum", ("Toan", "VatLy", "HoaHoc")),
    "KhoiA1": ("sum", ("Toan", "VatLy", "NgoaiNgu")),
    "KhoiB": ("sum", ("Toan", "HoaHoc", "SinhHoc")),
    "KhoiC": ("sum", ("NguVan", "LichSu", "DiaLy")),
    "KhoiD": ("sum", ("Toan", "NguVan", "NgoaiNgu")),
    "KHTN": ("average", ("VatLy", "HoaHoc", "SinhHoc")),
    "KHXH": ("average", ("LichSu", "DiaLy", "GDCD")),
    "KhoiA02": ("sum", ("Toan", "VatLy", "SinhHoc")),
    "KhoiC01": ("sum", ("NguVan", "Toan", "VatLy")),
    "KhoiD07": ("sum", ("Toan", "HoaHoc", "NgoaiNgu")),
}
SBD_PATTERN = re.compile(r"^\d{8}$")


class DataValidationError(ValueError):
    """Lỗi cấu trúc khiến pipeline không thể tiếp tục an toàn."""


def canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def parse_decimal(raw_value: str, column: str, errors: list[str]) -> Decimal | None:
    value = raw_value.strip()
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        errors.append(f"{column}:khong_phai_so")
        return None
    if not number.is_finite():
        errors.append(f"{column}:so_khong_huu_han")
        return None
    return number


def expected_year_value(raw_value: str, expected_year: int, errors: list[str]) -> str:
    value = raw_value.strip()
    accepted = {str(expected_year), str(expected_year)[-2:]}
    if value not in accepted:
        errors.append("Nam:khong_khop_nam_file")
    return str(expected_year)


def normalize_identifier(
    raw_value: str,
    width: int,
    column: str,
    errors: list[str],
) -> str:
    value = raw_value.strip()
    if not value or not value.isdigit():
        errors.append(f"{column}:khong_hop_le")
        return value
    if len(value) > width:
        errors.append(f"{column}:vuot_qua_{width}_chu_so")
        return value
    return value.zfill(width)


def validate_formula(
    target: str,
    mode: str,
    sources: Iterable[str],
    parsed: dict[str, Decimal | None],
    errors: list[str],
    formula_checks: Counter[str],
) -> None:
    actual = parsed[target]
    source_values = [parsed[source] for source in sources]
    # Không tự điền cột tổng hợp còn thiếu. Trong dữ liệu nguồn, điểm 0 có thể
    # khiến KHTN/KHXH bị để trống theo quy tắc công bố kết quả.
    if actual is None or any(value is None for value in source_values):
        formula_checks[f"{target}:bo_qua"] += 1
        return

    expected = sum(source_values, Decimal("0"))
    if mode == "average":
        expected /= Decimal(len(source_values))
    formula_checks[f"{target}:da_kiem_tra"] += 1
    if abs(actual - expected) > Decimal("0.01"):
        errors.append(f"{target}:sai_cong_thuc")
        formula_checks[f"{target}:sai_lech"] += 1


def clean_row(
    row: dict[str, str],
    expected_year: int,
    formula_checks: Counter[str],
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    cleaned = {column: (row.get(column) or "").strip() for column in SOURCE_COLUMNS}

    cleaned["SBD"] = normalize_identifier(cleaned["SBD"], 8, "SBD", errors)
    cleaned["Nam"] = expected_year_value(cleaned["Nam"], expected_year, errors)
    cleaned["Tinh"] = normalize_identifier(cleaned["Tinh"], 2, "Tinh", errors)
    cleaned["SBD_New"] = normalize_identifier(cleaned["SBD_New"], 6, "SBD_New", errors)

    if not SBD_PATTERN.fullmatch(cleaned["SBD"]):
        errors.append("SBD:khong_du_8_chu_so")
    elif cleaned["Tinh"] != cleaned["SBD"][:2]:
        errors.append("Tinh:khong_khop_SBD")
    if SBD_PATTERN.fullmatch(cleaned["SBD"]) and cleaned["SBD_New"] != cleaned["SBD"][2:]:
        errors.append("SBD_New:khong_khop_SBD")

    parsed: dict[str, Decimal | None] = {}
    for column in NUMERIC_COLUMNS:
        number = parse_decimal(cleaned[column], column, errors)
        parsed[column] = number
        if number is not None:
            cleaned[column] = canonical_decimal(number)

    for column in SUBJECT_COLUMNS + AVERAGE_COLUMNS:
        number = parsed[column]
        if number is not None and not Decimal("0") <= number <= Decimal("10"):
            errors.append(f"{column}:ngoai_khoang_0_10")
    for column in BLOCK_COLUMNS:
        number = parsed[column]
        if number is not None and not Decimal("0") <= number <= Decimal("30"):
            errors.append(f"{column}:ngoai_khoang_0_30")
    for column in TOTAL_COLUMNS:
        number = parsed[column]
        if number is not None and not Decimal("0") <= number <= Decimal("90"):
            errors.append(f"{column}:ngoai_khoang_0_90")

    language_code = cleaned["MaMonNgoaiNgu"].upper()
    cleaned["MaMonNgoaiNgu"] = language_code
    if language_code and language_code not in LANGUAGE_CODES:
        errors.append("MaMonNgoaiNgu:khong_hop_le")
    if bool(language_code) != (parsed["NgoaiNgu"] is not None):
        errors.append("MaMonNgoaiNgu:khong_dong_bo_diem_ngoai_ngu")

    subject_values = [parsed[column] for column in SUBJECT_COLUMNS if parsed[column] is not None]
    if parsed["TongDiem"] is not None:
        expected_total = sum(subject_values, Decimal("0"))
        if abs(parsed["TongDiem"] - expected_total) > Decimal("0.01"):
            errors.append("TongDiem:sai_tong_cac_mon")
            formula_checks["TongDiem:sai_lech"] += 1
        formula_checks["TongDiem:da_kiem_tra"] += 1
    else:
        formula_checks["TongDiem:bo_qua"] += 1

    for target, (mode, sources) in FORMULAS.items():
        validate_formula(target, mode, sources, parsed, errors, formula_checks)

    output = {COLUMN_MAPPING[column]: cleaned[column] for column in SOURCE_COLUMNS}
    return output, list(dict.fromkeys(errors))


def update_column_stats(
    row: dict[str, str],
    missing_counts: Counter[str],
    minima: dict[str, Decimal],
    maxima: dict[str, Decimal],
) -> None:
    for column in OUTPUT_COLUMNS:
        if row[column] == "":
            missing_counts[column] += 1
    for source_column in NUMERIC_COLUMNS:
        column = COLUMN_MAPPING[source_column]
        if not row[column]:
            continue
        number = Decimal(row[column])
        minima[column] = min(minima.get(column, number), number)
        maxima[column] = max(maxima.get(column, number), number)


def make_temp_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    return Path(temp_name)


def clean_file(input_path: Path, output_dir: Path, year: int) -> dict[str, object]:
    output_path = output_dir / f"diemthi_{year}.csv"
    output_temp = make_temp_path(output_path)

    counters: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    formula_checks: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    minima: dict[str, Decimal] = {}
    maxima: dict[str, Decimal] = {}
    seen_sbd: set[str] = set()
    started_at = datetime.now(timezone.utc)

    try:
        with (
            input_path.open("r", encoding="utf-8-sig", newline="") as source,
            output_temp.open("w", encoding="utf-8", newline="") as destination,
        ):
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
                raise DataValidationError(
                    f"Schema không hợp lệ ở {input_path}: {reader.fieldnames!r}"
                )

            writer = csv.DictWriter(destination, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()

            for row_number, row in enumerate(reader, start=2):
                counters["input_rows"] += 1
                if None in row or any(value is None for value in row.values()):
                    errors = ["dong_sai_so_luong_cot"]
                    cleaned = None
                else:
                    cleaned, errors = clean_row(row, year, formula_checks)

                sbd = cleaned["sbd"] if cleaned else (row.get("SBD") or "").strip()
                if sbd in seen_sbd:
                    errors.append("SBD:trung_lap")
                    counters["duplicate_rows_removed"] += 1
                else:
                    seen_sbd.add(sbd)

                if errors:
                    counters["rejected_rows"] += 1
                    rejection_reasons.update(errors)
                    continue

                writer.writerow(cleaned)
                counters["output_rows"] += 1
                update_column_stats(cleaned, missing_counts, minima, maxima)

        if counters["rejected_rows"]:
            reasons = ", ".join(
                f"{reason}={count}" for reason, count in sorted(rejection_reasons.items())
            )
            raise DataValidationError(
                f"{input_path}: có {counters['rejected_rows']} dòng không hợp lệ ({reasons})"
            )

        os.replace(output_temp, output_path)
        return {
            "year": year,
            "duration_seconds": round(
                (datetime.now(timezone.utc) - started_at).total_seconds(), 3
            ),
            "input_path": input_path.as_posix(),
            "output_path": output_path.as_posix(),
            "counts": dict(sorted(counters.items())),
            "rejection_reasons": dict(sorted(rejection_reasons.items())),
            "missing_by_column": {
                column: missing_counts[column] for column in OUTPUT_COLUMNS
            },
            "numeric_ranges": {
                column: {
                    "min": canonical_decimal(minima[column]),
                    "max": canonical_decimal(maxima[column]),
                }
                for column in minima
            },
            "formula_checks": dict(sorted(formula_checks.items())),
            "normalizations": [
                "Tên cột được chuẩn hóa sang snake_case.",
                "Năm được đổi từ 2 chữ số thành 4 chữ số.",
                "Mã tỉnh và SBD nội tỉnh được thêm số 0 ở đầu để giữ đúng độ dài.",
                "Giá trị số được chuẩn hóa dấu chấm thập phân và bỏ số 0 vô nghĩa ở cuối.",
                "Ô trống được giữ là ô trống; không tự suy diễn điểm còn thiếu.",
            ],
        }
    except Exception:
        output_temp.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Làm sạch dữ liệu điểm thi 2023/2024 theo luồng."
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        choices=(2023, 2024),
        default=(2023, 2024),
        help="Các năm cần xử lý (mặc định: 2023 2024).",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=repository_root / "data" / "raw" / "exam",
        help="Thư mục chứa diemthi_<năm>.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "data" / "cleaned" / "exam",
        help="Thư mục nhận CSV sạch và báo cáo chất lượng.",
    )
    return parser.parse_args()


def main() -> int:
    # PowerShell trên một số máy Windows vẫn dùng code page cũ (ví dụ cp1258),
    # không biểu diễn được đầy đủ tiếng Việt Unicode đã tổ hợp.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    reports = []
    for year in args.years:
        input_path = args.input_dir / f"diemthi_{year}.csv"
        if not input_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file đầu vào: {input_path}")
        report = clean_file(input_path, args.output_dir, year)
        reports.append(report)
        counts = report["counts"]
        print(
            f"{year}: {counts.get('input_rows', 0):,} dòng đầu vào -> "
            f"{counts.get('output_rows', 0):,} dòng sạch; "
            f"loại {counts.get('rejected_rows', 0):,} dòng."
        )

    total_input = sum(report["counts"].get("input_rows", 0) for report in reports)
    total_output = sum(report["counts"].get("output_rows", 0) for report in reports)
    print(f"Tổng: {total_input:,} dòng đầu vào -> {total_output:,} dòng sạch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
