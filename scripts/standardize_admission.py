"""Standardize cleaned university admission cut-offs for 2018–2024.

The pipeline preserves each source score and only creates ``cutoff_score_30``
for THPTQG scores on a 30- or 40-point scale. Scores from DGNL, DGTD and
academic transcripts are intentionally left unconverted.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLEANED_DIR = ROOT / "data" / "cleaned" / "admission"
OUTPUT_DIR = ROOT / "data" / "processed" / "admission"


@dataclass(frozen=True)
class SourceSpec:
    filename: str
    default_year: int | None


SOURCES = (
    SourceSpec("diemchuan_2018_2023_cleaned.csv", None),
    SourceSpec("diemchuan_2024_cleaned.csv", 2024),
)

CANONICAL_COLUMNS = (
    "year",
    "university_admission_code",
    "university_code",
    "university_name",
    "institution_type",
    "region",
    "province",
    "major_group_code",
    "major_group_name",
    "submajor_code",
    "submajor_name",
    "major_admission_code",
    "major_code",
    "major_name",
    "admission_method",
    "subject_combination",
    "combination_group",
    "cutoff_score",
    "score_scale",
    "cutoff_score_30",
    "weighted_subject",
    "weighted_subject_factor",
    "gender_requirement",
    "honors_program",
    "campus",
    "max_preference",
    "note",
    "note_requires_review",
    "outlier_score",
)

# Mã ngành cấp III theo danh mục giáo dục quốc gia đáng tin cậy hơn nhãn nhóm
# ngành nguồn khi hai trường mâu thuẫn. Dữ liệu nguồn 2024 có nhiều ngành 738
# (Luật) bị gắn nhầm sang Báo chí/Marketing hoặc Công an/Quân đội.
MAJOR_GROUP_OVERRIDES = {
    "738": ("738", "Pháp luật"),
}


class DataValidationError(ValueError):
    """Raised when a cleaned source cannot satisfy the processed-data contract."""


def text_column(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name].astype("string").str.strip().replace("", pd.NA)
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def numeric_column(values: pd.Series, field: str, source_name: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype("Float64")
    invalid = values.notna() & numeric.isna()
    if invalid.any():
        examples = values[invalid].head(5).tolist()
        raise DataValidationError(f"{source_name}: {field} has non-numeric values {examples}")
    return numeric


def boolean_column(values: pd.Series, field: str, source_name: str) -> pd.Series:
    result = pd.Series(pd.NA, index=values.index, dtype="boolean")
    true_values = {"true", "1", "yes"}
    false_values = {"false", "0", "no"}
    normalized = values.astype("string").str.strip().str.casefold()
    result[normalized.isin(true_values)] = True
    result[normalized.isin(false_values)] = False
    invalid = values.notna() & result.isna()
    if invalid.any():
        examples = values[invalid].head(5).tolist()
        raise DataValidationError(f"{source_name}: {field} has invalid boolean values {examples}")
    return result


def normalize_code(values: pd.Series) -> pd.Series:
    return values.astype("string").str.upper().str.replace(r"\s+", "", regex=True)


def normalize_scale(values: pd.Series) -> pd.Series:
    normalized = values.astype("string").str.strip().str.casefold()
    normalized = normalized.str.replace(r"\.0$", "", regex=True)
    return normalized.replace({"biến thiên": "variable", "khác": "other"})


def normalize_year(values: pd.Series, default_year: int | None, source_name: str) -> pd.Series:
    if default_year is not None:
        return pd.Series(default_year, index=values.index, dtype="Int64")
    parsed = pd.to_numeric(values, errors="coerce").astype("Int64")
    invalid = parsed.isna() | ~parsed.between(2018, 2024)
    if invalid.any():
        examples = values[invalid].head(5).tolist()
        raise DataValidationError(f"{source_name}: invalid year values {examples}")
    return parsed


def standardize(frame: pd.DataFrame, spec: SourceSpec) -> pd.DataFrame:
    source_name = spec.filename
    result = pd.DataFrame(index=frame.index)

    result["year"] = normalize_year(text_column(frame, "Năm"), spec.default_year, source_name)
    result["university_admission_code"] = normalize_code(
        text_column(frame, "Mã trường xét tuyển", "Mã trường")
    )
    result["university_code"] = normalize_code(text_column(frame, "Mã Trường", "Mã trường"))
    result["university_name"] = text_column(frame, "Tên Trường", "Trường đào tạo")
    result["institution_type"] = text_column(frame, "Loại đơn vị")
    result["region"] = text_column(frame, "Khu vực")
    result["province"] = text_column(frame, "Tỉnh/ Thành phố")
    result["major_group_code"] = normalize_code(text_column(frame, "Mã nhóm ngành"))
    result["major_group_name"] = text_column(frame, "Nhóm ngành")
    result["submajor_code"] = normalize_code(text_column(frame, "Mã phân ngành"))
    result["submajor_name"] = text_column(frame, "Phân ngành")
    result["major_admission_code"] = normalize_code(text_column(frame, "Mã xét tuyển", "Mã ngành"))
    result["major_code"] = normalize_code(text_column(frame, "Ma_nganh_goc"))
    missing_major_code = result["major_code"].isna()
    result.loc[missing_major_code, "major_code"] = (
        result.loc[missing_major_code, "major_admission_code"].str.split("_").str[0]
    )
    result["major_name"] = text_column(frame, "Tên Ngành", "Tên ngành", "Ngành")
    for prefix, (group_code, group_name) in MAJOR_GROUP_OVERRIDES.items():
        mask = result["major_code"].str.startswith(prefix, na=False)
        result.loc[mask, "major_group_code"] = group_code
        result.loc[mask, "major_group_name"] = group_name
    result["admission_method"] = text_column(frame, "Loại điểm")
    result["subject_combination"] = normalize_code(text_column(frame, "Tổ hợp", "Tổ hợp môn"))
    result["combination_group"] = text_column(frame, "Khoi_to_hop")
    missing_group = result["combination_group"].isna()
    result.loc[missing_group, "combination_group"] = result.loc[
        missing_group, "subject_combination"
    ].str.extract(r"^([A-Z]+)", expand=False)

    result["cutoff_score"] = numeric_column(
        text_column(frame, "Điểm chuẩn"), "cutoff_score", source_name
    )
    result["score_scale"] = normalize_scale(text_column(frame, "Thang_diem_goc"))
    result["weighted_subject"] = text_column(frame, "Mon_he_so", "Mon_he_so_2")
    result["weighted_subject_factor"] = numeric_column(
        text_column(frame, "He_so_mon"), "weighted_subject_factor", source_name
    )
    needs_default_factor = result["weighted_subject"].notna() & result["weighted_subject_factor"].isna()
    result.loc[needs_default_factor, "weighted_subject_factor"] = 2.0
    result["gender_requirement"] = text_column(frame, "Dieu_kien_gioi_tinh")
    result["honors_program"] = boolean_column(
        text_column(frame, "Chuong_trinh_CLC"), "honors_program", source_name
    )
    result["campus"] = text_column(frame, "Phan_hieu_co_so")
    result["max_preference"] = numeric_column(
        text_column(frame, "TTNV_max"), "max_preference", source_name
    )
    result["note"] = text_column(frame, "Ghi chú")
    result["note_requires_review"] = boolean_column(
        text_column(frame, "Ghi_chu_can_review"), "note_requires_review", source_name
    )
    result["outlier_score"] = boolean_column(
        text_column(frame, "Outlier_diem"), "outlier_score", source_name
    )

    method = result["admission_method"].fillna("").str.casefold()
    is_thpt = method.str.startswith("thptqg")
    result["cutoff_score_30"] = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    direct = is_thpt & result["score_scale"].eq("30")
    weighted = is_thpt & result["score_scale"].eq("40")
    result.loc[direct, "cutoff_score_30"] = result.loc[direct, "cutoff_score"]
    result.loc[weighted, "cutoff_score_30"] = (result.loc[weighted, "cutoff_score"] * 0.75).round(2)

    invalid_thpt = is_thpt & result["cutoff_score"].notna() & ~result["score_scale"].isin(("30", "40"))
    if invalid_thpt.any():
        scales = result.loc[invalid_thpt, "score_scale"].dropna().unique().tolist()
        raise DataValidationError(f"{source_name}: THPTQG rows have unsupported scales {scales}")
    return result.loc[:, CANONICAL_COLUMNS]


def build_summary(frame: pd.DataFrame) -> pd.DataFrame:
    eligible = frame.loc[frame["cutoff_score_30"].notna()].copy()
    group_columns = ["year", "major_code", "major_name", "subject_combination"]
    return (
        eligible.groupby(group_columns, dropna=False)["cutoff_score_30"]
        .agg(cutoff_count="count", minimum_cutoff="min", average_cutoff="mean", median_cutoff="median", maximum_cutoff="max")
        .reset_index()
        .sort_values(group_columns, kind="stable")
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    source_reports = []
    for spec in SOURCES:
        source = CLEANED_DIR / spec.filename
        frame = pd.read_csv(source, encoding="utf-8-sig", dtype="string", keep_default_na=False)
        standardized = standardize(frame, spec)
        frames.append(standardized)
        source_reports.append(
            {
                "input": str(source.relative_to(ROOT)).replace("\\", "/"),
                "rows_written": len(standardized),
                "years": sorted(int(year) for year in standardized["year"].dropna().unique()),
            }
        )

    output = pd.concat(frames, ignore_index=True)
    output_path = OUTPUT_DIR / "admission_cutoffs_2018_2024.csv"
    temporary = output_path.with_suffix(".csv.tmp")
    output.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(output_path)

    summary = build_summary(output)
    summary_path = OUTPUT_DIR / "admission_cutoff_summary_by_year_major.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8", lineterminator="\n")

    report = {
        "contract_version": 1,
        "record_schema": list(CANONICAL_COLUMNS),
        "sources": source_reports,
        "records_written": len(output),
        "thpt_rows_with_cutoff_score_30": int(output["cutoff_score_30"].notna().sum()),
        "summary": str(summary_path.relative_to(ROOT)).replace("\\", "/"),
    }
    report_path = OUTPUT_DIR / "standardization_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
