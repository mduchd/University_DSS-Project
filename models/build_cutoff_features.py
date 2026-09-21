"""Bước 4 và 5 - Tạo feature lịch sử chống leakage và thiết kế cold start.

Nguyên tắc bất biến: feature của mẫu năm t chỉ được dùng target từ các năm nhỏ
hơn t. Các thống kê cùng năm hoặc tương lai tuyệt đối không được đưa vào input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/processed/admission_ml_step2.csv"
DEFAULT_EXAM_SUMMARY = ROOT / "data/processed/exam/exam_score_summary_by_year_province.csv"
DEFAULT_FEATURES = ROOT / "data/processed/admission_ml_features.csv"
DEFAULT_COLD_START = ROOT / "data/processed/admission_ml_cold_start_2024.csv"
DEFAULT_REPORT = ROOT / "data/processed/admission_ml_feature_report.json"
TARGET = "cutoff_score_30"
SERIES = "series_combination_key"


def parse_args() -> argparse.Namespace:
    """Đọc đường dẫn dataset bước 2, phổ điểm và các output feature engineering."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--exam-summary", type=Path, default=DEFAULT_EXAM_SUMMARY)
    parser.add_argument("--features-output", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--cold-start-output", type=Path, default=DEFAULT_COLD_START)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    """Ghi CSV qua file tạm để tránh dataset feature bị ghi nửa chừng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Ghi feature report JSON UTF-8 theo cơ chế atomic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def count_dict(series: pd.Series) -> dict[str, int]:
    """Đếm tần suất theo nhãn để tóm tắt split và loại cold start."""
    return {str(key): int(value) for key, value in series.value_counts(dropna=False).items()}


def build_series_history_features(data: pd.DataFrame) -> pd.DataFrame:
    """Tạo lag và thống kê riêng cho từng series bằng phần lịch sử trước năm t."""
    result = data.sort_values([SERIES, "year"], kind="stable").reset_index(drop=True).copy()
    size = len(result)
    feature_names = [
        "lag_1_year",
        "lag_2_year",
        "lag_3_year",
        "last_observed_cutoff",
        "years_since_last_observation",
        "historical_count_prior",
        "historical_mean_prior",
        "historical_median_prior",
        "historical_std_prior",
        "historical_min_prior",
        "historical_max_prior",
        "historical_trend_prior",
        "historical_mean_change_prior",
    ]
    arrays = {name: np.full(size, np.nan, dtype=float) for name in feature_names}

    # Xử lý từng chuỗi độc lập để lag của ngành này không lẫn sang ngành khác.
    for positions in result.groupby(SERIES, sort=False).indices.values():
        positions = np.asarray(positions, dtype=int)
        years = result.loc[positions, "year"].to_numpy(dtype=int)
        targets = result.loc[positions, TARGET].to_numpy(dtype=float)
        year_to_target = {int(year): float(target) for year, target in zip(years, targets, strict=True)}
        for offset, row_position in enumerate(positions):
            year = int(years[offset])
            # Cắt đến offset (không gồm dòng hiện tại) là điểm chặn data leakage.
            previous_years = years[:offset]
            previous_targets = targets[:offset]
            arrays["historical_count_prior"][row_position] = offset
            arrays["lag_1_year"][row_position] = year_to_target.get(year - 1, np.nan)
            arrays["lag_2_year"][row_position] = year_to_target.get(year - 2, np.nan)
            arrays["lag_3_year"][row_position] = year_to_target.get(year - 3, np.nan)
            if offset == 0:
                continue
            arrays["last_observed_cutoff"][row_position] = previous_targets[-1]
            arrays["years_since_last_observation"][row_position] = year - int(previous_years[-1])
            arrays["historical_mean_prior"][row_position] = float(previous_targets.mean())
            arrays["historical_median_prior"][row_position] = float(np.median(previous_targets))
            arrays["historical_min_prior"][row_position] = float(previous_targets.min())
            arrays["historical_max_prior"][row_position] = float(previous_targets.max())
            if offset >= 2:
                arrays["historical_std_prior"][row_position] = float(previous_targets.std(ddof=0))
                arrays["historical_mean_change_prior"][row_position] = float(np.diff(previous_targets).mean())
                centered_years = previous_years - previous_years.mean()
                denominator = float(np.square(centered_years).sum())
                if denominator > 0:
                    centered_targets = previous_targets - previous_targets.mean()
                    arrays["historical_trend_prior"][row_position] = float(
                        np.sum(centered_years * centered_targets) / denominator
                    )

    for name, values in arrays.items():
        result[name] = values
    result["historical_range_prior"] = result["historical_max_prior"] - result["historical_min_prior"]
    result["lag_change_1_2"] = result["lag_1_year"] - result["lag_2_year"]
    result["has_exact_previous_year"] = result["lag_1_year"].notna()
    result["has_two_exact_lags"] = result[["lag_1_year", "lag_2_year"]].notna().all(axis=1)
    result["cutoff_lag_1"] = result["lag_1_year"]
    result["cutoff_lag_2"] = result["lag_2_year"]
    result["cutoff_lag_3"] = result["lag_3_year"]
    result["historical_mean"] = result["historical_mean_prior"]
    result["historical_median"] = result["historical_median_prior"]
    result["historical_std"] = result["historical_std_prior"]
    result["historical_min"] = result["historical_min_prior"]
    result["historical_max"] = result["historical_max_prior"]
    result["historical_count"] = result["historical_count_prior"]
    result["last_year_change"] = result["lag_change_1_2"]
    result["historical_trend_slope"] = result["historical_trend_prior"]
    return result


def add_previous_year_aggregate(
    data: pd.DataFrame,
    keys: list[str],
    output_prefix: str,
) -> pd.DataFrame:
    """Gắn thống kê đúng năm t-1 bằng cách dịch năm tổng hợp tiến thêm một đơn vị."""
    aggregate = (
        data.groupby(["year", *keys], dropna=False)[TARGET]
        .agg([("mean", "mean"), ("count", "size")])
        .reset_index()
    )
    aggregate["year"] = aggregate["year"] + 1
    aggregate = aggregate.rename(
        columns={
            "mean": f"{output_prefix}_prev_mean",
            "count": f"{output_prefix}_prev_count",
        }
    )
    # validate many_to_one chặn aggregate vô tình nhân bản số dòng gốc.
    return data.merge(aggregate, on=["year", *keys], how="left", validate="many_to_one")


def add_prior_history_aggregate(
    data: pd.DataFrame,
    keys: list[str],
    output_prefix: str,
) -> pd.DataFrame:
    """Tính trung bình có trọng số của nhóm chỉ từ các năm trước t."""
    annual = (
        data.groupby([*keys, "year"], dropna=False)[TARGET]
        .agg([("annual_sum", "sum"), ("annual_count", "size")])
        .reset_index()
        .sort_values([*keys, "year"], kind="stable")
    )
    if keys:
        grouped = annual.groupby(keys, dropna=False, sort=False)
        # Trừ thống kê năm hiện tại khỏi cumulative sum/count để không rò rỉ target.
        annual["prior_sum"] = grouped["annual_sum"].cumsum() - annual["annual_sum"]
        annual["prior_count"] = grouped["annual_count"].cumsum() - annual["annual_count"]
    else:
        annual["prior_sum"] = annual["annual_sum"].cumsum() - annual["annual_sum"]
        annual["prior_count"] = annual["annual_count"].cumsum() - annual["annual_count"]
    annual[f"{output_prefix}_historical_mean"] = (
        annual["prior_sum"] / annual["prior_count"].replace(0, np.nan)
    )
    annual = annual.rename(
        columns={"prior_count": f"{output_prefix}_historical_count"}
    )
    columns = [
        *keys,
        "year",
        f"{output_prefix}_historical_mean",
        f"{output_prefix}_historical_count",
    ]
    return data.merge(
        annual[columns], on=[*keys, "year"], how="left", validate="many_to_one"
    )


def add_context_features(data: pd.DataFrame) -> pd.DataFrame:
    """Tạo thống kê quá khứ theo trường, nhóm ngành và tổ hợp xét tuyển."""
    result = data.copy()
    result = add_previous_year_aggregate(
        result,
        ["institution_entity_key", "major_group_normalized", "subject_combination"],
        "institution_group_combo",
    )
    result = add_previous_year_aggregate(
        result,
        ["institution_entity_key", "subject_combination"],
        "institution_combo",
    )
    result = add_previous_year_aggregate(
        result,
        ["major_group_normalized", "subject_combination"],
        "group_combo",
    )
    result = add_previous_year_aggregate(result, ["subject_combination"], "combination")
    result = add_previous_year_aggregate(result, [], "global")
    result = add_prior_history_aggregate(
        result, ["institution_entity_key"], "school"
    )
    result = add_prior_history_aggregate(
        result, ["major_group_normalized"], "major_group"
    )
    result = add_prior_history_aggregate(
        result, ["subject_combination"], "combination"
    )
    result = add_prior_history_aggregate(
        result,
        ["institution_entity_key", "subject_combination"],
        "school_combination",
    )
    result = add_prior_history_aggregate(
        result,
        ["major_group_normalized", "subject_combination"],
        "major_group_combination",
    )
    result = add_prior_history_aggregate(result, [], "global")

    missing_group = result["major_group_normalized"].fillna("").astype("string").str.strip().eq("")
    for prefix in ["institution_group_combo", "group_combo"]:
        result.loc[missing_group, [f"{prefix}_prev_mean", f"{prefix}_prev_count"]] = np.nan
    for prefix in ["major_group", "major_group_combination"]:
        result.loc[
            missing_group,
            [f"{prefix}_historical_mean", f"{prefix}_historical_count"],
        ] = np.nan
    return result


def add_exam_distribution_features(data: pd.DataFrame, summary_path: Path) -> pd.DataFrame:
    """Gắn trung bình tổ hợp toàn quốc năm t-1 cho kịch bản dự báo trước kỳ thi."""
    summary = pd.read_csv(summary_path, low_memory=False)
    combinations = ["A00", "A01", "A02", "B00", "C00", "C01", "C02", "D01", "D07"]
    rows: list[dict[str, Any]] = []
    for combination in combinations:
        mean_column = f"mean_{combination.lower()}_score"
        count_column = f"count_{combination.lower()}_score"
        if mean_column not in summary.columns or count_column not in summary.columns:
            continue
        valid = summary.loc[
            summary[mean_column].notna() & summary[count_column].gt(0),
            ["year", mean_column, count_column],
        ].copy()
        for exam_year, group in valid.groupby("year", sort=True):
            count = float(group[count_column].sum())
            weighted_mean = float(
                (group[mean_column] * group[count_column]).sum() / count
            )
            rows.append(
                {
                    "year": int(exam_year) + 1,
                    "subject_combination": combination,
                    "exam_combination_mean_t_minus_1": weighted_mean,
                    "exam_combination_count_t_minus_1": int(count),
                    "exam_feature_source_year": int(exam_year),
                }
            )
    national = pd.DataFrame(rows)
    return data.merge(
        national,
        on=["year", "subject_combination"],
        how="left",
        validate="many_to_one",
    )


def add_cold_start_design(data: pd.DataFrame) -> pd.DataFrame:
    """Phân loại cold start và chọn fallback đầu tiên có dữ liệu theo thứ bậc."""
    result = data.copy()
    result["cold_start_required"] = result["lag_1_year"].isna()
    result["cold_start_type"] = "not_cold_start"
    result.loc[
        result["cold_start_required"] & result["historical_count_prior"].eq(0),
        "cold_start_type",
    ] = "new_series"
    result.loc[
        result["cold_start_required"] & result["historical_count_prior"].gt(0),
        "cold_start_type",
    ] = "history_gap"

    # Thứ tự từ thông tin riêng nhất đến thông tin chung nhất.
    hierarchy = [
        ("lag_1_year", "exact_series_previous_year"),
        ("institution_group_combo_prev_mean", "institution_group_combo_previous_year"),
        ("institution_combo_prev_mean", "institution_combo_previous_year"),
        ("group_combo_prev_mean", "group_combo_previous_year"),
        ("combination_prev_mean", "combination_previous_year"),
        ("global_prev_mean", "global_previous_year"),
    ]
    result["baseline_prediction"] = np.nan
    result["baseline_level"] = "unavailable"
    for column, label in hierarchy:
        use = result["baseline_prediction"].isna() & result[column].notna()
        result.loc[use, "baseline_prediction"] = result.loc[use, column]
        result.loc[use, "baseline_level"] = label
    result["baseline_available"] = result["baseline_prediction"].notna()
    return result


def metric_block(frame: pd.DataFrame) -> dict[str, Any]:
    """Tóm tắt số mẫu và tỷ lệ cold start cho một tập dữ liệu."""
    evaluated = frame.loc[frame["baseline_prediction"].notna() & frame[TARGET].notna()]
    if evaluated.empty:
        return {"rows": 0, "mae": None, "rmse": None}
    error = evaluated["baseline_prediction"] - evaluated[TARGET]
    return {
        "rows": int(len(evaluated)),
        "mae": round(float(error.abs().mean()), 6),
        "rmse": round(float(np.sqrt(np.square(error).mean())), 6),
    }


def validate_exact_lags(data: pd.DataFrame) -> bool:
    """Đối chiếu lag theo năm với target lịch sử; trả False nếu có sai lệch."""
    lookup = data.set_index([SERIES, "year"])[TARGET]
    checked = data.loc[data["lag_1_year"].notna(), [SERIES, "year", "lag_1_year"]]
    for row in checked.itertuples(index=False):
        expected = float(lookup.loc[(getattr(row, SERIES), int(row.year) - 1)])
        if not np.isclose(float(row.lag_1_year), expected):
            return False
    return True


def main() -> None:
    """Điều phối feature engineering, time split, kiểm tra leakage và xuất kết quả."""
    args = parse_args()
    source = pd.read_csv(args.input.resolve(), low_memory=False)
    required = {
        "year",
        TARGET,
        SERIES,
        "institution_entity_key",
        "major_group_normalized",
        "subject_combination",
    }
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"Step 2 input is missing required columns: {missing}")

    # Pipeline feature: lịch sử series -> ngữ cảnh nhóm -> phổ điểm -> cold start.
    features = build_series_history_features(source)
    features = add_context_features(features)
    features = add_exam_distribution_features(features, args.exam_summary.resolve())
    features = add_cold_start_design(features)
    # Chia theo thời gian, không shuffle, để mô phỏng dự báo năm tương lai.
    features["model_split"] = np.select(
        [features["year"].le(2022), features["year"].eq(2023), features["year"].eq(2024)],
        ["train", "validation", "test"],
        default="out_of_scope",
    )
    features["history_segment"] = np.where(
        features["historical_count_prior"].eq(0), "cold_start", "known_history"
    )
    features["history_depth_group"] = np.select(
        [
            features["historical_count_prior"].eq(0),
            features["historical_count_prior"].eq(1),
            features["historical_count_prior"].ge(2),
        ],
        ["cold_start", "known_history_1_year", "known_history_2plus"],
        default="unknown",
    )

    # Cổng kiểm tra leakage và toàn vẹn trước khi xuất dataset modeling.
    if len(features) != len(source):
        raise AssertionError("Feature construction changed the number of rows.")
    if features.duplicated(["year", SERIES]).any():
        raise AssertionError("Feature construction produced duplicate year-series keys.")
    if not features.loc[features["year"].eq(features["year"].min()), "historical_count_prior"].eq(0).all():
        raise AssertionError("The earliest year unexpectedly has prior-series history.")
    exact_lags_valid = validate_exact_lags(features)
    if not exact_lags_valid:
        raise AssertionError("At least one lag_1_year value does not match the exact prior year.")

    cold_start_2024 = features.loc[
        features["year"].eq(2024) & features["cold_start_required"]
    ].copy()
    selected_cold_columns = [
        "year",
        "university_admission_code",
        "canonical_university_name",
        "major_admission_code",
        "canonical_major_name",
        "subject_combination",
        TARGET,
        SERIES,
        "cold_start_type",
        "historical_count_prior",
        "years_since_last_observation",
        "baseline_prediction",
        "baseline_level",
        "institution_group_combo_prev_mean",
        "institution_combo_prev_mean",
        "group_combo_prev_mean",
        "combination_prev_mean",
        "global_prev_mean",
        "step2_review_priority",
    ]
    selected_cold_columns = [column for column in selected_cold_columns if column in cold_start_2024.columns]
    cold_start_2024 = cold_start_2024[selected_cold_columns]

    split_metrics = {
        split: metric_block(group)
        for split, group in features.groupby("model_split", sort=True)
    }
    test = features.loc[features["model_split"].eq("test")]
    report = {
        "step": "03b_leakage_safe_feature_engineering_and_cold_start",
        "input_rows": int(len(source)),
        "output_rows": int(len(features)),
        "split_counts": count_dict(features["model_split"]),
        "feature_definitions": {
            "lag_1_year": "Cutoff for the exact same series in year t-1.",
            "lag_2_year": "Cutoff for the exact same series in year t-2.",
            "lag_3_year": "Cutoff for the exact same series in year t-3.",
            "historical_statistics": "Count/mean/median/std/min/max calculated only from years before t.",
            "historical_trend_prior": "Least-squares slope fitted only on observations before t.",
            "context_previous_year": "Means from exactly t-1; the current year's targets are never used.",
            "context_historical_means": "School, major-group and combination means use all observations strictly before t.",
            "exam_distribution": "National weighted mean for the same combination from year t-1; current-year exam scores are not used.",
        },
        "history_segments_by_split": {
            split: count_dict(group["history_depth_group"])
            for split, group in features.groupby("model_split", sort=True)
        },
        "cold_start_policy": {
            "definition": "lag_1_year is unavailable.",
            "hierarchy": [label for _, label in [
                ("lag_1_year", "exact_series_previous_year"),
                ("institution_group_combo_prev_mean", "institution_group_combo_previous_year"),
                ("institution_combo_prev_mean", "institution_combo_previous_year"),
                ("group_combo_prev_mean", "group_combo_previous_year"),
                ("combination_prev_mean", "combination_previous_year"),
                ("global_prev_mean", "global_previous_year"),
            ]],
            "missing_values": "Historical features remain missing; they are not filled with zero.",
        },
        "test_2024": {
            "rows": int(len(test)),
            "cold_start_rows": int(test["cold_start_required"].sum()),
            "cold_start_type_counts": count_dict(test.loc[test["cold_start_required"], "cold_start_type"]),
            "baseline_level_counts": count_dict(test["baseline_level"]),
            "baseline_metrics_all": metric_block(test),
            "baseline_metrics_cold_start": metric_block(test.loc[test["cold_start_required"]]),
            "exact_series_metrics": metric_block(test.loc[~test["cold_start_required"]]),
        },
        "baseline_metrics_by_split": split_metrics,
        "validation": {
            "row_count_preserved": bool(len(features) == len(source)),
            "year_series_key_unique": bool(not features.duplicated(["year", SERIES]).any()),
            "exact_lag_values_verified": bool(exact_lags_valid),
            "earliest_year_has_no_prior_history": bool(
                features.loc[features["year"].eq(features["year"].min()), "historical_count_prior"].eq(0).all()
            ),
            "current_year_target_not_used_in_context_features": True,
            "exam_feature_uses_t_minus_1_only": bool(
                features.loc[features["exam_feature_source_year"].notna(), "exam_feature_source_year"]
                .eq(features.loc[features["exam_feature_source_year"].notna(), "year"] - 1)
                .all()
            ),
        },
        "outputs": {
            "features": str(args.features_output.resolve()),
            "cold_start_2024": str(args.cold_start_output.resolve()),
            "report": str(args.report_output.resolve()),
        },
    }

    features = features.sort_values(["year", SERIES], kind="stable").reset_index(drop=True)
    atomic_csv(features, args.features_output.resolve())
    atomic_csv(cold_start_2024, args.cold_start_output.resolve())
    atomic_json(report, args.report_output.resolve())
    print(f"Feature rows: {len(features):,}")
    print(f"2024 cold-start rows: {len(cold_start_2024):,}")
    print(f"2024 baseline MAE: {report['test_2024']['baseline_metrics_all']['mae']}")
    print(f"2024 cold-start baseline MAE: {report['test_2024']['baseline_metrics_cold_start']['mae']}")


if __name__ == "__main__":
    main()
