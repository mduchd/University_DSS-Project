"""Bước 6 - Huấn luyện và đánh giá baseline với time split cố định.

Baseline là mốc tối thiểu để biết model phức tạp có thật sự tạo thêm giá trị hay
không. File này triển khai Historical Mean, Last Value, Group Mean, Hybrid và OLS.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/processed/admission_ml_features.csv"
DEFAULT_PREDICTIONS = ROOT / "data/processed/admission_ml_baseline_predictions.csv"
DEFAULT_METRICS = ROOT / "data/processed/admission_ml_baseline_metrics.csv"
DEFAULT_MODEL = ROOT / "models/baseline_linear_model.json"
DEFAULT_EVALUATION = ROOT / "models/evaluation.json"
TARGET = "cutoff_score_30"

# Chỉ dùng feature được tạo từ quá khứ; target hiện tại nằm trong danh sách cấm bên dưới.
LINEAR_FEATURES = [
    "year",
    "cutoff_lag_1",
    "cutoff_lag_2",
    "cutoff_lag_3",
    "historical_mean",
    "historical_median",
    "historical_std",
    "historical_min",
    "historical_max",
    "historical_count",
    "last_year_change",
    "historical_trend_slope",
    "school_historical_mean",
    "major_group_historical_mean",
    "combination_historical_mean",
    "exam_combination_mean_t_minus_1",
]

TARGET_DERIVED_COLUMNS_FORBIDDEN = {
    "cutoff_score",
    "cutoff_score_30",
    "baseline_prediction",
}


def parse_args() -> argparse.Namespace:
    """Đọc feature dataset và đường dẫn lưu prediction, metric, model baseline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--predictions-output", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--evaluation-output", type=Path, default=DEFAULT_EVALUATION)
    return parser.parse_args()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    """Ghi bảng kết quả CSV qua file tạm rồi thay thế atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Ghi tham số baseline hoặc evaluation JSON theo cơ chế atomic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def fit_linear_regression(frame: pd.DataFrame) -> dict[str, Any]:
    """Fit OLS bằng nghiệm bình phương tối thiểu sau impute và standardize."""
    x = frame[LINEAR_FEATURES].astype(float)
    missing = x.isna().astype(float)
    medians = x.median(axis=0).fillna(0.0)
    filled = x.fillna(medians)
    means = filled.mean(axis=0)
    scales = filled.std(axis=0, ddof=0).replace(0, 1.0).fillna(1.0)
    standardized = (filled - means) / scales
    design = np.column_stack(
        [
            np.ones(len(frame), dtype=float),
            standardized.to_numpy(dtype=float),
            missing.to_numpy(dtype=float),
        ]
    )
    target = frame[TARGET].to_numpy(dtype=float)
    # Nghiệm beta tối thiểu hóa tổng bình phương sai số ||X beta - y||^2.
    coefficients, residuals, rank, singular_values = np.linalg.lstsq(
        design, target, rcond=None
    )
    return {
        "model_type": "ordinary_least_squares",
        "feature_names": LINEAR_FEATURES,
        "missing_indicator_features": [f"{name}__missing" for name in LINEAR_FEATURES],
        "medians": medians.to_dict(),
        "means": means.to_dict(),
        "scales": scales.to_dict(),
        "intercept": float(coefficients[0]),
        "feature_coefficients": {
            name: float(value)
            for name, value in zip(LINEAR_FEATURES, coefficients[1 : 1 + len(LINEAR_FEATURES)], strict=True)
        },
        "missing_coefficients": {
            f"{name}__missing": float(value)
            for name, value in zip(LINEAR_FEATURES, coefficients[1 + len(LINEAR_FEATURES) :], strict=True)
        },
        "matrix_rank": int(rank),
        "singular_values": [float(value) for value in singular_values],
        "training_rows": int(len(frame)),
        "clip_range": [0.0, 30.0],
    }


def predict_linear(frame: pd.DataFrame, model: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Áp dụng đúng median, scale và coefficient đã fit; trả cả raw và clipped prediction."""
    features = model["feature_names"]
    x = frame[features].astype(float)
    missing = x.isna().astype(float)
    medians = pd.Series(model["medians"], dtype=float)
    means = pd.Series(model["means"], dtype=float)
    scales = pd.Series(model["scales"], dtype=float)
    standardized = (x.fillna(medians) - means) / scales
    beta = np.array([model["feature_coefficients"][name] for name in features], dtype=float)
    missing_beta = np.array(
        [model["missing_coefficients"][f"{name}__missing"] for name in features],
        dtype=float,
    )
    # Công thức dự báo OLS: intercept + X chuẩn hóa nhân beta + cờ missing nhân beta_missing.
    raw = (
        float(model["intercept"])
        + standardized.to_numpy(dtype=float) @ beta
        + missing.to_numpy(dtype=float) @ missing_beta
    )
    clipped = np.clip(raw, model["clip_range"][0], model["clip_range"][1])
    return raw, clipped


def add_group_mean_baseline(frame: pd.DataFrame) -> pd.DataFrame:
    """Dự báo fallback theo cấp chi tiết nhất đang có dữ liệu lịch sử."""
    result = frame.copy()
    hierarchy = [
        ("school_combination_historical_mean", "school_combination_history"),
        ("major_group_combination_historical_mean", "major_group_combination_history"),
        ("school_historical_mean", "school_history"),
        ("major_group_historical_mean", "major_group_history"),
        ("combination_historical_mean", "combination_history"),
        ("global_historical_mean", "global_history"),
    ]
    result["prediction_group_mean"] = np.nan
    result["group_mean_level"] = "unavailable"
    for column, label in hierarchy:
        use = result["prediction_group_mean"].isna() & result[column].notna()
        result.loc[use, "prediction_group_mean"] = result.loc[use, column]
        result.loc[use, "group_mean_level"] = label
    return result


def metric_row(
    frame: pd.DataFrame,
    prediction_column: str,
    model_name: str,
    split: str,
    segment: str,
) -> dict[str, Any]:
    """Tính coverage, MAE, RMSE và R² cho một model trên một segment."""
    available = frame[prediction_column].notna() & frame[TARGET].notna()
    evaluated = frame.loc[available]
    total = int(len(frame))
    if evaluated.empty:
        return {
            "split": split,
            "segment": segment,
            "model": model_name,
            "rows_total": total,
            "rows_evaluated": 0,
            "coverage": 0.0,
            "mae": None,
            "rmse": None,
            "r2": None,
        }
    actual = evaluated[TARGET].to_numpy(dtype=float)
    predicted = evaluated[prediction_column].to_numpy(dtype=float)
    error = predicted - actual
    denominator = float(np.square(actual - actual.mean()).sum())
    r2 = None if denominator == 0 else 1.0 - float(np.square(error).sum()) / denominator
    return {
        "split": split,
        "segment": segment,
        "model": model_name,
        "rows_total": total,
        "rows_evaluated": int(len(evaluated)),
        "coverage": round(len(evaluated) / total, 6) if total else 0.0,
        "mae": round(float(np.abs(error).mean()), 6),
        "rmse": round(float(np.sqrt(np.square(error).mean())), 6),
        "r2": None if r2 is None else round(float(r2), 6),
    }


def evaluate_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    """Tính metric của từng baseline theo split và segment cold start/known history."""
    models = {
        "historical_mean": "prediction_historical_mean",
        "last_value": "prediction_last_value",
        "group_mean": "prediction_group_mean",
        "hybrid_last_value_group_mean": "prediction_hybrid_last_group",
        "linear_regression": "prediction_linear_regression",
    }
    rows: list[dict[str, Any]] = []
    for split in ["validation", "test"]:
        split_frame = frame.loc[frame["model_split"].eq(split)]
        segments = {
            "all": split_frame,
            "known_history": split_frame.loc[split_frame["history_segment"].eq("known_history")],
            "cold_start": split_frame.loc[split_frame["history_segment"].eq("cold_start")],
            "known_history_1_year": split_frame.loc[
                split_frame["history_depth_group"].eq("known_history_1_year")
            ],
            "known_history_2plus": split_frame.loc[
                split_frame["history_depth_group"].eq("known_history_2plus")
            ],
        }
        for segment, segment_frame in segments.items():
            for model_name, prediction_column in models.items():
                rows.append(
                    metric_row(
                        segment_frame,
                        prediction_column,
                        model_name,
                        split,
                        segment,
                    )
                )
    return pd.DataFrame(rows)


def main() -> None:
    """Huấn luyện baseline, đánh giá theo thời gian và ghi toàn bộ artifact bước 6."""
    args = parse_args()
    data = pd.read_csv(args.input.resolve(), low_memory=False)
    missing = sorted(set(LINEAR_FEATURES + [TARGET, "model_split", "history_segment", "history_depth_group"]).difference(data.columns))
    if missing:
        raise ValueError(f"Feature dataset is missing required columns: {missing}")
    leakage = sorted(set(LINEAR_FEATURES) & TARGET_DERIVED_COLUMNS_FORBIDDEN)
    if leakage:
        raise AssertionError(f"Linear feature list contains target leakage columns: {leakage}")

    data["prediction_historical_mean"] = data["historical_mean"]
    data["prediction_last_value"] = data["last_observed_cutoff"]
    data = add_group_mean_baseline(data)
    data["prediction_hybrid_last_group"] = data["prediction_last_value"].fillna(
        data["prediction_group_mean"]
    )
    data["prediction_linear_regression_raw"] = np.nan
    data["prediction_linear_regression"] = np.nan

    # Train <= 2022, chọn/đánh giá cấu hình trên 2023, test cuối trên 2024.
    train = data.loc[data["model_split"].eq("train")]
    validation = data.loc[data["model_split"].eq("validation")]
    test = data.loc[data["model_split"].eq("test")]
    validation_model = fit_linear_regression(train)
    validation_raw, validation_clipped = predict_linear(validation, validation_model)
    data.loc[validation.index, "prediction_linear_regression_raw"] = validation_raw
    data.loc[validation.index, "prediction_linear_regression"] = validation_clipped

    # Sau khi đặc tả baseline đã khóa, refit train+validation để đánh giá 2024.
    train_validation = data.loc[data["model_split"].isin(["train", "validation"])]
    final_model = fit_linear_regression(train_validation)
    final_model["trained_through_year"] = 2023
    final_model["prediction_year_evaluated"] = 2024
    test_raw, test_clipped = predict_linear(test, final_model)
    data.loc[test.index, "prediction_linear_regression_raw"] = test_raw
    data.loc[test.index, "prediction_linear_regression"] = test_clipped

    metrics = evaluate_predictions(data)
    full_validation = metrics.loc[
        metrics["split"].eq("validation")
        & metrics["segment"].eq("all")
        & metrics["coverage"].eq(1.0)
    ].sort_values("mae")
    best_full_coverage = (
        None
        if full_validation.empty
        else {
            "model": str(full_validation.iloc[0]["model"]),
            "mae": float(full_validation.iloc[0]["mae"]),
            "rmse": float(full_validation.iloc[0]["rmse"]),
            "r2": float(full_validation.iloc[0]["r2"]),
        }
    )

    output_columns = [
        "year",
        "model_split",
        "history_segment",
        "history_depth_group",
        "university_admission_code",
        "canonical_university_name",
        "major_admission_code",
        "canonical_major_name",
        "subject_combination",
        TARGET,
        "prediction_historical_mean",
        "prediction_last_value",
        "prediction_group_mean",
        "prediction_hybrid_last_group",
        "group_mean_level",
        "prediction_linear_regression_raw",
        "prediction_linear_regression",
    ]
    output_columns = [column for column in output_columns if column in data.columns]
    predictions = data.loc[data["model_split"].isin(["validation", "test"]), output_columns].copy()

    evaluation = {
        "steps": ["04_leakage_safe_features", "05_fixed_time_split", "06_baselines"],
        "split_policy": {
            "train": "year <= 2022",
            "validation": "year == 2023",
            "test": "year == 2024",
            "random_split_used": False,
            "random_kfold_used": False,
            "test_linear_fit_policy": "Refit on 2018-2023 after the baseline specification was fixed.",
        },
        "row_counts": {
            "train": int(len(train)),
            "validation": int(len(validation)),
            "test": int(len(test)),
        },
        "linear_regression": {
            "implementation": "NumPy ordinary least squares with train-only median imputation, standardization and missing indicators.",
            "features": LINEAR_FEATURES,
            "prediction_clip": [0.0, 30.0],
            "validation_training_rows": int(len(train)),
            "final_training_rows": int(len(train_validation)),
        },
        "baseline_definitions": {
            "historical_mean": "Mean of the same series using only years before t.",
            "last_value": "Most recent prior cutoff from the same series.",
            "group_mean": "Prior-only hierarchical mean: school+combination, major-group+combination, school, major-group, combination, global.",
            "hybrid_last_value_group_mean": "Use Last Value for known history and Group Mean for cold start.",
            "linear_regression": "OLS on the leakage-safe numeric features listed above.",
        },
        "best_full_coverage_validation_baseline": best_full_coverage,
        "metrics": (
            metrics.astype(object)
            .where(pd.notna(metrics), None)
            .to_dict(orient="records")
        ),
        "validation": {
            "target_columns_excluded_from_linear_features": bool(not leakage),
            "all_validation_linear_predictions_available": bool(
                data.loc[validation.index, "prediction_linear_regression"].notna().all()
            ),
            "all_test_linear_predictions_available": bool(
                data.loc[test.index, "prediction_linear_regression"].notna().all()
            ),
            "all_predictions_within_0_30": bool(
                data.loc[
                    data["model_split"].isin(["validation", "test"]),
                    "prediction_linear_regression",
                ].between(0, 30).all()
            ),
        },
        "outputs": {
            "predictions": str(args.predictions_output.resolve()),
            "metrics_csv": str(args.metrics_output.resolve()),
            "linear_model": str(args.model_output.resolve()),
            "evaluation": str(args.evaluation_output.resolve()),
        },
    }

    atomic_csv(predictions, args.predictions_output.resolve())
    atomic_csv(metrics, args.metrics_output.resolve())
    atomic_json(final_model, args.model_output.resolve())
    atomic_json(evaluation, args.evaluation_output.resolve())
    print(f"Train rows: {len(train):,}")
    print(f"Validation rows: {len(validation):,}")
    print(f"Test rows: {len(test):,}")
    print(f"Best full-coverage validation baseline: {best_full_coverage}")


if __name__ == "__main__":
    main()
