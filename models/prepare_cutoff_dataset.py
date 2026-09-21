"""Bước 1 - Chuẩn bị dataset điểm chuẩn chặt chẽ và có thể tái lập.

File này chưa huấn luyện model. Nhiệm vụ của nó là kiểm tra dữ liệu canonical,
tách các dòng không sử dụng được hoặc mơ hồ, chỉ gộp duplicate khi target giống
hệt nhau, rồi xuất báo cáo chất lượng có thể kiểm tra bằng máy.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data/processed/admission/admission_cutoffs_2018_2024.csv"
DEFAULT_BASE_OUTPUT = PROJECT_ROOT / "data/processed/admission_ml_base.csv"
DEFAULT_REJECTED_OUTPUT = PROJECT_ROOT / "data/processed/admission_ml_rejected.csv"
DEFAULT_REPORT_OUTPUT = PROJECT_ROOT / "data/processed/admission_ml_quality_report.json"

# Các ràng buộc nghiệp vụ được cố định để mọi lần chạy cho cùng kết quả.
YEAR_MIN = 2018
YEAR_MAX = 2024
SCORE_MIN = 0.0
SCORE_MAX = 30.0
COMBINATION_PATTERN = re.compile(r"^[A-Z][0-9]{2}$")

REQUIRED_COLUMNS = {
    "year",
    "university_admission_code",
    "major_admission_code",
    "major_code",
    "major_name",
    "major_group_name",
    "subject_combination",
    "admission_method",
    "cutoff_score",
    "score_scale",
    "cutoff_score_30",
    "note_requires_review",
    "outlier_score",
    "note",
}

# Một modeling key biểu diễn duy nhất một mức điểm chuẩn của một phương án tuyển sinh.
MODEL_KEY_COLUMNS = [
    "year",
    "university_admission_code",
    "major_admission_code",
    "subject_combination",
]
PROGRAM_KEY_COLUMNS = ["university_admission_code", "major_admission_code"]


def parse_args() -> argparse.Namespace:
    """Đọc đường dẫn input/output từ command line và giữ cấu hình mặc định của dự án."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--base-output", type=Path, default=DEFAULT_BASE_OUTPUT)
    parser.add_argument("--rejected-output", type=Path, default=DEFAULT_REJECTED_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    return parser.parse_args()


def as_bool(series: pd.Series) -> pd.Series:
    """Chuẩn hóa các cách ghi boolean trong CSV và không coi NaN là True."""
    return series.astype("string").str.strip().str.lower().isin({"true", "1", "yes", "y"})


def joined_reasons(reason_masks: dict[str, pd.Series], index: pd.Index) -> pd.Series:
    """Ghép mọi lý do loại của từng dòng thành chuỗi audit phân cách bằng ký tự ``|``."""
    reasons = pd.Series("", index=index, dtype="string")
    for reason, mask in reason_masks.items():
        reasons = reasons.mask(mask & reasons.eq(""), reason)
        reasons = reasons.mask(mask & reasons.ne("") & ~reasons.str.contains(reason, regex=False), reasons + "|" + reason)
    return reasons


def json_number(value: Any) -> Any:
    """Đổi scalar NumPy/Pandas sang kiểu JSON thuần và đổi missing thành ``null``."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def value_counts_dict(series: pd.Series) -> dict[str, int]:
    """Chuyển bảng tần suất thành dictionary có khóa chuỗi để ghi vào quality report."""
    return {str(key): int(value) for key, value in series.value_counts(dropna=False).sort_index().items()}


def target_stats(frame: pd.DataFrame) -> dict[str, Any]:
    """Tóm tắt count, min, mean, median và max của target điểm chuẩn."""
    if frame.empty:
        return {"count": 0, "min": None, "mean": None, "median": None, "max": None}
    values = frame["cutoff_score_30"]
    return {
        "count": int(values.count()),
        "min": json_number(values.min()),
        "mean": json_number(round(float(values.mean()), 6)),
        "median": json_number(values.median()),
        "max": json_number(values.max()),
    }


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Ghi CSV qua file tạm rồi replace để không để lại output dở dang."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    """Ghi JSON UTF-8 theo cơ chế atomic và giữ nguyên ký tự tiếng Việt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    """Điều phối bước lọc, gộp duplicate, kiểm tra chất lượng và xuất dataset modeling."""
    args = parse_args()
    input_path = args.input.resolve()
    base_output = args.base_output.resolve()
    rejected_output = args.rejected_output.resolve()
    report_output = args.report_output.resolve()

    # 1. Đọc dữ liệu canonical và fail-fast nếu thiếu cột bắt buộc.
    source = pd.read_csv(input_path, low_memory=False)
    missing_columns = sorted(REQUIRED_COLUMNS.difference(source.columns))
    if missing_columns:
        raise ValueError(f"Input is missing required columns: {missing_columns}")

    data = source.copy()
    data["_source_row_number"] = data.index + 2

    string_columns = data.select_dtypes(include=["object", "string"]).columns
    for column in string_columns:
        data[column] = data[column].astype("string").str.strip()

    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["cutoff_score_30"] = pd.to_numeric(data["cutoff_score_30"], errors="coerce")
    data["source_note_review_flag"] = as_bool(data["note_requires_review"])
    data["source_outlier_flag"] = as_bool(data["outlier_score"])

    normalized_method = data["admission_method"].fillna("").str.upper()
    normalized_combo = data["subject_combination"].fillna("").str.upper()
    data["subject_combination"] = normalized_combo

    # 2. Mỗi điều kiện loại được giữ thành một mask riêng để có thể audit lý do.
    reason_masks = {
        "non_thpt_admission_method": ~normalized_method.str.contains("THPTQG", regex=False),
        "missing_or_non_numeric_cutoff_score_30": data["cutoff_score_30"].isna(),
        "cutoff_score_30_outside_0_30": data["cutoff_score_30"].notna()
        & ~data["cutoff_score_30"].between(SCORE_MIN, SCORE_MAX, inclusive="both"),
        "year_outside_2018_2024": data["year"].isna()
        | ~data["year"].between(YEAR_MIN, YEAR_MAX, inclusive="both"),
        "missing_university_admission_code": data["university_admission_code"].fillna("").eq(""),
        "missing_major_admission_code": data["major_admission_code"].fillna("").eq(""),
        "missing_subject_combination": normalized_combo.eq(""),
        "invalid_subject_combination": normalized_combo.ne("")
        & ~normalized_combo.str.match(COMBINATION_PATTERN),
    }
    data["rejection_reason"] = joined_reasons(reason_masks, data.index)

    hard_rejected = data.loc[data["rejection_reason"].ne("")].copy()
    eligible = data.loc[data["rejection_reason"].eq("")].copy()
    eligible["year"] = eligible["year"].astype("int64")
    eligible["model_key"] = eligible[MODEL_KEY_COLUMNS].astype("string").agg("|".join, axis=1)

    # Thống kê biến thể tên giúp phát hiện một mã ngành bị dùng cho nhiều cách gọi.
    program_variants = (
        eligible.groupby(PROGRAM_KEY_COLUMNS, dropna=False)
        .agg(
            program_name_variant_count=("major_name", lambda values: values.dropna().nunique()),
            program_group_variant_count=("major_group_name", lambda values: values.dropna().nunique()),
        )
        .reset_index()
    )
    eligible = eligible.merge(program_variants, on=PROGRAM_KEY_COLUMNS, how="left", validate="many_to_one")
    eligible["program_identity_requires_review"] = (
        eligible["program_name_variant_count"].gt(1) | eligible["program_group_variant_count"].gt(1)
    )

    # 3. Không lấy trung bình các target xung đột: loại toàn bộ khóa mơ hồ.
    grouped = eligible.groupby(MODEL_KEY_COLUMNS, dropna=False, sort=False)
    target_variants = grouped["cutoff_score_30"].transform("nunique")  # >1 nghĩa là nhãn xung đột.
    ambiguous_mask = target_variants.gt(1)

    ambiguous = eligible.loc[ambiguous_mask].copy()
    ambiguous["rejection_reason"] = "ambiguous_multiple_cutoffs_for_model_key"

    unambiguous = eligible.loc[~ambiguous_mask].copy()
    unambiguous["source_row_count"] = unambiguous.groupby(MODEL_KEY_COLUMNS, dropna=False)[
        "_source_row_number"
    ].transform("size")
    unambiguous["source_row_numbers"] = unambiguous.groupby(MODEL_KEY_COLUMNS, dropna=False)[
        "_source_row_number"
    ].transform(lambda values: ";".join(str(value) for value in sorted(values)))
    unambiguous["duplicate_same_target_collapsed"] = unambiguous["source_row_count"].gt(1)

    # 4. Duplicate cùng target được gộp về một dòng nhưng vẫn lưu số dòng nguồn.
    base = (
        unambiguous.sort_values("_source_row_number")
        .drop_duplicates(MODEL_KEY_COLUMNS, keep="first")
        .copy()
    )
    base["manual_review_required"] = (
        base["source_note_review_flag"]
        | base["source_outlier_flag"]
        | base["program_identity_requires_review"]
        | base["duplicate_same_target_collapsed"]
    )
    base["step1_status"] = base["manual_review_required"].map(
        {True: "accepted_review", False: "accepted_clean"}
    )
    base = base.drop(columns=["rejection_reason"])
    base = base.sort_values(MODEL_KEY_COLUMNS, kind="stable").reset_index(drop=True)

    rejected = pd.concat([hard_rejected, ambiguous], ignore_index=True, sort=False)
    rejected = rejected.sort_values("_source_row_number", kind="stable").reset_index(drop=True)

    # 5. Các assertion là cổng chất lượng cuối trước khi ghi file.
    if base.duplicated(MODEL_KEY_COLUMNS).any():
        raise AssertionError("The prepared dataset still contains duplicate model keys.")
    if not base["cutoff_score_30"].between(SCORE_MIN, SCORE_MAX, inclusive="both").all():
        raise AssertionError("The prepared dataset contains a target outside the accepted range.")
    if not base["subject_combination"].str.match(COMBINATION_PATTERN).all():
        raise AssertionError("The prepared dataset contains an invalid subject combination.")

    hard_reason_counts = {reason: int(mask.sum()) for reason, mask in reason_masks.items()}
    ambiguous_group_count = int(ambiguous[MODEL_KEY_COLUMNS].drop_duplicates().shape[0])
    collapsed_groups = int(
        base.loc[base["duplicate_same_target_collapsed"], MODEL_KEY_COLUMNS].drop_duplicates().shape[0]
    )
    collapsed_source_rows = int(
        base.loc[base["duplicate_same_target_collapsed"], "source_row_count"].sum()
    )
    accepted_source_rows_represented = int(base["source_row_count"].sum())
    duplicate_source_rows_removed = accepted_source_rows_represented - int(len(base))

    by_year_stats = {
        str(int(year)): target_stats(group)
        for year, group in base.groupby("year", sort=True)
    }
    report = {
        "step": "01_prepare_cutoff_dataset",
        "description": "Validate and prepare THPTQG cutoff observations before feature engineering.",
        "input": str(input_path),
        "outputs": {
            "accepted": str(base_output),
            "rejected": str(rejected_output),
            "quality_report": str(report_output),
        },
        "rules": {
            "accepted_year_range": [YEAR_MIN, YEAR_MAX],
            "accepted_cutoff_score_30_range": [SCORE_MIN, SCORE_MAX],
            "accepted_admission_method_contains": "THPTQG",
            "subject_combination_regex": COMBINATION_PATTERN.pattern,
            "model_key_columns": MODEL_KEY_COLUMNS,
            "duplicate_policy": (
                "Collapse rows only when a model key has one target value; reject the entire key "
                "when it has multiple target values."
            ),
            "review_flag_policy": (
                "Source review/outlier flags are retained for audit and do not automatically remove a row."
            ),
        },
        "counts": {
            "input_rows": int(len(data)),
            "hard_rejected_rows": int(len(hard_rejected)),
            "hard_rejection_reason_counts_nonexclusive": hard_reason_counts,
            "eligible_rows_before_key_resolution": int(len(eligible)),
            "ambiguous_model_key_groups": ambiguous_group_count,
            "ambiguous_rows_rejected": int(len(ambiguous)),
            "same_target_duplicate_groups_collapsed": collapsed_groups,
            "source_rows_in_collapsed_groups": collapsed_source_rows,
            "duplicate_source_rows_removed_by_collapse": duplicate_source_rows_removed,
            "accepted_source_rows_represented": accepted_source_rows_represented,
            "accepted_rows": int(len(base)),
            "accepted_clean_rows": int(base["step1_status"].eq("accepted_clean").sum()),
            "accepted_review_rows": int(base["step1_status"].eq("accepted_review").sum()),
            "rejected_rows_total": int(len(rejected)),
            "accepted_rows_by_year": value_counts_dict(base["year"]),
            "rejected_rows_by_reason": value_counts_dict(rejected["rejection_reason"]),
        },
        "review_indicators_in_accepted_data": {
            "source_note_review_flag": int(base["source_note_review_flag"].sum()),
            "source_outlier_flag": int(base["source_outlier_flag"].sum()),
            "program_identity_requires_review": int(base["program_identity_requires_review"].sum()),
            "duplicate_same_target_collapsed": int(base["duplicate_same_target_collapsed"].sum()),
        },
        "target_statistics": {
            "overall": target_stats(base),
            "by_year": by_year_stats,
        },
        "validation": {
            "model_key_is_unique": bool(~base.duplicated(MODEL_KEY_COLUMNS).any()),
            "target_is_complete": bool(base["cutoff_score_30"].notna().all()),
            "target_is_within_range": bool(
                base["cutoff_score_30"].between(SCORE_MIN, SCORE_MAX, inclusive="both").all()
            ),
            "year_is_within_range": bool(base["year"].between(YEAR_MIN, YEAR_MAX).all()),
            "subject_combination_is_valid": bool(
                base["subject_combination"].str.match(COMBINATION_PATTERN).all()
            ),
            "source_rows_are_fully_accounted_for": bool(
                len(data) == len(hard_rejected) + len(ambiguous) + accepted_source_rows_represented
            ),
        },
    }

    # 6. Ghi file theo kiểu atomic để tránh tạo output dở dang khi chương trình lỗi.
    atomic_write_csv(base, base_output)
    atomic_write_csv(rejected, rejected_output)
    atomic_write_json(report, report_output)

    print(f"Input rows: {len(data):,}")
    print(f"Accepted model observations: {len(base):,}")
    print(f"Rejected source rows: {len(rejected):,}")
    print(f"Accepted rows requiring review: {int(base['manual_review_required'].sum()):,}")
    print(f"Quality report: {report_output}")


if __name__ == "__main__":
    main()
