"""Bước 7 đến 10 - Preprocess, chọn, đánh giá và lưu cutoff model.

Model chỉ được chọn bằng validation 2023. Test 2024 được giữ kín đến khi cấu
hình đã khóa; artifact cuối chứa cả fitted preprocessor và estimator.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/processed/admission_ml_features.csv"
DEFAULT_BASELINE_METRICS = ROOT / "data/processed/admission_ml_baseline_metrics.csv"
DEFAULT_MODEL = ROOT / "models/model.joblib"
DEFAULT_EVALUATION = ROOT / "models/evaluation.json"
DEFAULT_PREDICTIONS = ROOT / "data/processed/admission_ml_model_predictions_2024.csv"
DEFAULT_IMPORTANCE = ROOT / "data/processed/admission_ml_feature_importance.csv"
TARGET = "cutoff_score_30"
MODEL_VERSION = "cutoff_v1"
RANDOM_STATE = 42

# Feature phân loại đi qua imputer và OneHotEncoder(handle_unknown="ignore").
CATEGORICAL_FEATURES = [
    "university_admission_code",
    "canonical_program_id",
    "canonical_major_code",
    "major_group",
    "subject_combination",
]

# Toàn bộ feature số bên dưới đã được tạo theo nguyên tắc chỉ dùng quá khứ.
NUMERIC_FEATURES = [
    "year",
    "cutoff_lag_1",
    "cutoff_lag_2",
    "cutoff_lag_3",
    "last_observed_cutoff",
    "years_since_last_observation",
    "historical_mean",
    "historical_median",
    "historical_std",
    "historical_min",
    "historical_max",
    "historical_count",
    "last_year_change",
    "historical_trend_slope",
    "historical_mean_change_prior",
    "historical_range_prior",
    "school_historical_mean",
    "major_group_historical_mean",
    "combination_historical_mean",
    "school_combination_historical_mean",
    "major_group_combination_historical_mean",
    "global_historical_mean",
    "institution_combo_prev_mean",
    "group_combo_prev_mean",
    "combination_prev_mean",
    "global_prev_mean",
    "exam_combination_mean_t_minus_1",
    "exam_combination_count_t_minus_1",
    "group_mean_feature",
    "hybrid_baseline_feature",
]


def parse_args() -> argparse.Namespace:
    """Đọc feature dataset, baseline metrics và đường dẫn lưu artifact cuối."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--baseline-metrics", type=Path, default=DEFAULT_BASELINE_METRICS)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--evaluation-output", type=Path, default=DEFAULT_EVALUATION)
    parser.add_argument("--predictions-output", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--importance-output", type=Path, default=DEFAULT_IMPORTANCE)
    return parser.parse_args()


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Ghi evaluation JSON an toàn qua file tạm."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    """Ghi prediction hoặc feature importance CSV theo cơ chế atomic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(path)


def json_safe(value: Any) -> Any:
    """Chuyển đệ quy object NumPy/Pandas sang kiểu Python có thể serialize JSON."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def first_available(frame: pd.DataFrame, columns: list[str]) -> tuple[pd.Series, pd.Series]:
    """Chọn giá trị đầu tiên không thiếu theo thứ tự fallback và ghi lại nguồn đã dùng."""
    prediction = pd.Series(np.nan, index=frame.index, dtype=float)
    level = pd.Series("unavailable", index=frame.index, dtype="string")
    for column in columns:
        use = prediction.isna() & frame[column].notna()
        prediction.loc[use] = frame.loc[use, column].astype(float)
        level.loc[use] = column
    return prediction, level


def prepare_model_frame(source: pd.DataFrame) -> pd.DataFrame:
    """Tạo các alias canonical và fallback feature dùng chung cho mọi candidate."""
    data = source.copy()
    data["canonical_program_id"] = data["program_series_key"].astype("string")
    data["canonical_major_code"] = (
        data["major_code"].astype("string").fillna(data["major_admission_code"].astype("string"))
    )
    data["major_group"] = data["major_group_normalized"].astype("string")
    group_mean, group_level = first_available(
        data,
        [
            "school_combination_historical_mean",
            "major_group_combination_historical_mean",
            "school_historical_mean",
            "major_group_historical_mean",
            "combination_historical_mean",
            "global_historical_mean",
        ],
    )
    data["group_mean_feature"] = group_mean
    data["group_mean_feature_level"] = group_level
    data["hybrid_baseline_feature"] = data["last_observed_cutoff"].fillna(group_mean)
    for column in CATEGORICAL_FEATURES:
        data[column] = data[column].astype("string")
    return data


def make_preprocessor(scale_numeric: bool) -> ColumnTransformer:
    """Tạo preprocessing; Ridge cần scale, model cây chỉ cần impute."""
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="constant", fill_value="__MISSING__")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    min_frequency=10,
                    sparse_output=True,
                    dtype=np.float32,
                ),
            ),
        ]
    )
    numeric_steps: list[tuple[str, Any]] = [
        ("imputer", SimpleImputer(strategy="median", add_indicator=True))
    ]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler(with_mean=False)))
    numeric = Pipeline(numeric_steps)
    return ColumnTransformer(
        [
            ("categorical", categorical, CATEGORICAL_FEATURES),
            ("numeric", numeric, NUMERIC_FEATURES),
        ],
        sparse_threshold=1.0,
        verbose_feature_names_out=True,
    )


def regression_metrics(actual: pd.Series | np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    """Tính số mẫu, MAE, RMSE và R² cho bài toán regression."""
    y_true = np.asarray(actual, dtype=float)
    y_pred = np.asarray(predicted, dtype=float)
    return {
        "n_samples": int(len(y_true)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def segment_metrics(frame: pd.DataFrame, predicted: np.ndarray) -> dict[str, Any]:
    """Tính metric cho toàn bộ, known history và true cold start trên cùng prediction."""
    result: dict[str, Any] = {"all": regression_metrics(frame[TARGET], predicted)}
    prediction_series = pd.Series(predicted, index=frame.index)
    for segment in ["known_history", "cold_start"]:
        mask = frame["history_segment"].eq(segment)
        result[segment] = regression_metrics(
            frame.loc[mask, TARGET], prediction_series.loc[mask].to_numpy()
        )
    return result


def candidate_record(
    name: str,
    family: str,
    params: dict[str, Any],
    frame: pd.DataFrame,
    prediction: np.ndarray,
    fit_seconds: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Đóng gói cấu hình, thời gian fit và validation metrics của một candidate."""
    record = {
        "name": name,
        "family": family,
        "params": params,
        "validation": segment_metrics(frame, np.clip(prediction, 0.0, 30.0)),
        "fit_seconds": fit_seconds,
    }
    if extra:
        record.update(extra)
    return record


def load_baseline_metrics(path: Path) -> dict[str, Any]:
    """Đọc các mốc baseline cần thiết để kiểm tra điều kiện chấp nhận model."""
    metrics = pd.read_csv(path)
    selected = metrics.loc[
        metrics["segment"].eq("all") & metrics["split"].isin(["validation", "test"])
    ]
    result: dict[str, Any] = {}
    for row in selected.itertuples(index=False):
        result.setdefault(str(row.model), {})[str(row.split)] = {
            "n_samples": int(row.rows_evaluated),
            "coverage": float(row.coverage),
            "mae": None if pd.isna(row.mae) else float(row.mae),
            "rmse": None if pd.isna(row.rmse) else float(row.rmse),
            "r2": None if pd.isna(row.r2) else float(row.r2),
        }
    return result


def fit_validation_candidates(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Huấn luyện các cấu hình trên train và xếp hạng chỉ bằng validation."""
    x_train = train[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    x_validation = validation[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_train = train[TARGET]
    y_validation = validation[TARGET]
    candidates: list[dict[str, Any]] = []
    fitted: dict[str, Any] = {}

    linear_preprocessor = make_preprocessor(scale_numeric=True)
    # Chỉ fit preprocessor trên train; validation chỉ transform để không học trước phân phối 2023.
    x_train_linear = linear_preprocessor.fit_transform(x_train)
    x_validation_linear = linear_preprocessor.transform(x_validation)
    for alpha in [1.0, 10.0, 100.0]:
        start = time.perf_counter()
        estimator = Ridge(alpha=alpha, solver="lsqr")
        estimator.fit(x_train_linear, y_train)
        prediction = estimator.predict(x_validation_linear)
        name = f"ridge_alpha_{alpha:g}"
        candidates.append(
            candidate_record(
                name,
                "ridge",
                {"alpha": alpha, "solver": "lsqr"},
                validation,
                prediction,
                time.perf_counter() - start,
            )
        )
        fitted[name] = (linear_preprocessor, estimator)

    tree_preprocessor = make_preprocessor(scale_numeric=False)
    # Dùng cùng phép biến đổi đã học từ train cho cả Random Forest và XGBoost.
    x_train_tree = tree_preprocessor.fit_transform(x_train)
    x_validation_tree = tree_preprocessor.transform(x_validation)

    rf_configs = [
        {
            "n_estimators": 180,
            "max_depth": 18,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
            "max_samples": 0.85,
        },
        {
            "n_estimators": 240,
            "max_depth": 24,
            "min_samples_leaf": 4,
            "max_features": 0.2,
            "max_samples": 0.85,
        },
    ]
    for index, params in enumerate(rf_configs, start=1):
        start = time.perf_counter()
        estimator = RandomForestRegressor(
            **params,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        estimator.fit(x_train_tree, y_train)
        prediction = estimator.predict(x_validation_tree)
        name = f"random_forest_{index}"
        candidates.append(
            candidate_record(
                name,
                "random_forest",
                params,
                validation,
                prediction,
                time.perf_counter() - start,
            )
        )
        fitted[name] = (tree_preprocessor, estimator)

    xgb_configs = [
        {
            "max_depth": 6,
            "learning_rate": 0.05,
            "min_child_weight": 5,
            "subsample": 0.85,
            "colsample_bytree": 0.8,
        },
        {
            "max_depth": 4,
            "learning_rate": 0.04,
            "min_child_weight": 3,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
        },
    ]
    for index, params in enumerate(xgb_configs, start=1):
        start = time.perf_counter()
        # Early stopping dùng validation 2023 và dừng khi MAE không cải thiện 75 vòng.
        estimator = XGBRegressor(
            **params,
            n_estimators=2500,
            objective="reg:squarederror",
            eval_metric="mae",
            early_stopping_rounds=75,
            tree_method="hist",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        estimator.fit(
            x_train_tree,
            y_train,
            eval_set=[(x_validation_tree, y_validation)],
            verbose=False,
        )
        prediction = estimator.predict(x_validation_tree)
        name = f"xgboost_{index}"
        candidates.append(
            candidate_record(
                name,
                "xgboost",
                params,
                validation,
                prediction,
                time.perf_counter() - start,
                {
                    "best_iteration": int(estimator.best_iteration),
                    "best_score": float(estimator.best_score),
                },
            )
        )
        fitted[name] = (tree_preprocessor, estimator)

    return candidates, fitted


def refit_selected(
    selected: dict[str, Any],
    train_validation: pd.DataFrame,
) -> Pipeline:
    """Refit đúng cấu hình đã chọn trên train+validation, không tuning bằng test."""
    scale_numeric = selected["family"] == "ridge"
    preprocessor = make_preprocessor(scale_numeric=scale_numeric)
    x_full = train_validation[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_full = train_validation[TARGET]
    transformed = preprocessor.fit_transform(x_full)
    params = selected["params"]
    if selected["family"] == "ridge":
        estimator: Any = Ridge(**params)
    elif selected["family"] == "random_forest":
        estimator = RandomForestRegressor(
            **params,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    elif selected["family"] == "xgboost":
        estimator = XGBRegressor(
            **params,
            n_estimators=int(selected["best_iteration"]) + 1,
            objective="reg:squarederror",
            eval_metric="mae",
            tree_method="hist",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unsupported selected family: {selected['family']}")
    estimator.fit(transformed, y_full)
    return Pipeline([("preprocessor", preprocessor), ("model", estimator)])


def grouped_test_metrics(
    test: pd.DataFrame,
    prediction: np.ndarray,
    column: str,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Đánh giá test theo các nhóm lớn nhưng bỏ nhóm quá ít mẫu để tránh kết luận nhiễu."""
    working = test.copy()
    working["_prediction"] = prediction
    working[column] = working[column].astype("string").fillna("__MISSING__")
    top_values = working[column].value_counts().head(top_n).index
    rows: list[dict[str, Any]] = []
    for value in top_values:
        group = working.loc[working[column].eq(value)]
        record = regression_metrics(group[TARGET], group["_prediction"].to_numpy())
        record.update({"group": str(value), "group_column": column})
        rows.append(record)
    return rows


def feature_importance(pipeline: Pipeline) -> pd.DataFrame:
    """Ghép tên feature sau preprocessing với importance của estimator dạng cây."""
    preprocessor = pipeline.named_steps["preprocessor"]
    estimator = pipeline.named_steps["model"]
    names = preprocessor.get_feature_names_out()
    if hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype=float)
    elif hasattr(estimator, "coef_"):
        values = np.abs(np.asarray(estimator.coef_, dtype=float).ravel())
    else:
        return pd.DataFrame(columns=["feature", "importance"])
    return (
        pd.DataFrame({"feature": names, "importance": values})
        .sort_values("importance", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def main() -> None:
    """Huấn luyện candidate, chọn bằng validation, refit, test và lưu pipeline hoàn chỉnh."""
    args = parse_args()
    source = pd.read_csv(args.input.resolve(), low_memory=False)
    data = prepare_model_frame(source)
    required = set(CATEGORICAL_FEATURES + NUMERIC_FEATURES + [TARGET, "model_split", "history_segment"])
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Feature dataset is missing required columns: {missing}")

    train = data.loc[data["model_split"].eq("train")].copy()
    validation = data.loc[data["model_split"].eq("validation")].copy()
    test = data.loc[data["model_split"].eq("test")].copy()
    if not (train["year"].max() <= 2022 and validation["year"].eq(2023).all() and test["year"].eq(2024).all()):
        raise AssertionError("Fixed time split is not valid.")

    candidates, _ = fit_validation_candidates(train, validation)
    candidates = sorted(candidates, key=lambda item: item["validation"]["all"]["mae"])
    selected = candidates[0]
    baseline_metrics = load_baseline_metrics(args.baseline_metrics.resolve())
    historical_validation_mae = baseline_metrics["historical_mean"]["validation"]["mae"]
    if selected["validation"]["all"]["mae"] >= historical_validation_mae:
        raise RuntimeError("No ML candidate beat Historical Mean on validation 2023.")

    # Từ dòng này cấu hình đã khóa; test chưa từng được sử dụng ở phía trên.
    train_validation = data.loc[data["model_split"].isin(["train", "validation"])].copy()
    final_pipeline = refit_selected(selected, train_validation)
    x_test = test[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    raw_test_prediction = final_pipeline.predict(x_test)  # Test chỉ mở sau khi cấu hình đã khóa.
    test_prediction = np.clip(raw_test_prediction, 0.0, 30.0)
    final_test = segment_metrics(test, test_prediction)
    final_test["clipped_prediction_count"] = int(
        np.sum(~np.isclose(raw_test_prediction, test_prediction))
    )

    school_test_metrics = grouped_test_metrics(
        test, test_prediction, "canonical_university_name"
    )
    major_group_test_metrics = grouped_test_metrics(test, test_prediction, "major_group")
    school_maes = [
        row["mae"]
        for row in school_test_metrics
        if isinstance(row.get("mae"), (int, float)) and np.isfinite(row["mae"])
    ]
    school_robust = bool(
        school_maes
        and float(np.median(school_maes)) <= float(final_test["all"]["mae"]) * 1.5
    )

    hybrid_test_mae = baseline_metrics["hybrid_last_value_group_mean"]["test"]["mae"]
    validation_mae = selected["validation"]["all"]["mae"]
    known_history_validation_mae = selected["validation"]["known_history"]["mae"]
    severe_degradation = final_test["all"]["mae"] > max(
        validation_mae * 1.75,
        hybrid_test_mae * 1.15,
    )
    acceptance = {
        # Historical Mean không dự báo được cold start, nên phải so trên cùng
        # quần thể known_history để phép đánh giá công bằng.
        "beats_historical_mean_on_validation": bool(
            known_history_validation_mae < historical_validation_mae
        ),
        "no_severe_test_degradation": bool(not severe_degradation),
        "not_concentrated_in_few_large_schools": school_robust,
        "test_mae_vs_hybrid_baseline": float(final_test["all"]["mae"] - hybrid_test_mae),
    }
    acceptance["deployment_status"] = (
        "accepted" if all([
            acceptance["beats_historical_mean_on_validation"],
            acceptance["no_severe_test_degradation"],
            acceptance["not_concentrated_in_few_large_schools"],
        ])
        else "candidate_saved_not_promoted"
    )

    metadata = {
        "model_version": MODEL_VERSION,
        "dataset_version": "admission_ml_v1",
        "selected_candidate": selected["name"],
        "selected_family": selected["family"],
        "required_features": CATEGORICAL_FEATURES + NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "target": TARGET,
        "trained_through_year": 2023,
        "prediction_clip": [0.0, 30.0],
        "deployment_status": acceptance["deployment_status"],
        "library_versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "joblib": joblib.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    artifact = {"pipeline": final_pipeline, "metadata": metadata}
    args.model_output.resolve().parent.mkdir(parents=True, exist_ok=True)
    temporary_model = args.model_output.resolve().with_suffix(".joblib.tmp")
    # Lưu cả preprocessing và estimator để backend không tự xử lý feature khác lúc train.
    joblib.dump(artifact, temporary_model, compress=3)
    temporary_model.replace(args.model_output.resolve())

    importance = feature_importance(final_pipeline)
    atomic_csv(importance, args.importance_output.resolve())

    predictions = test[
        [
            "year",
            "university_admission_code",
            "canonical_university_name",
            "major_admission_code",
            "canonical_major_name",
            "major_group",
            "subject_combination",
            "history_segment",
            TARGET,
        ]
    ].copy()
    predictions["predicted_cutoff_raw"] = raw_test_prediction
    predictions["predicted_cutoff"] = test_prediction
    predictions["absolute_error"] = np.abs(test_prediction - predictions[TARGET])
    atomic_csv(predictions, args.predictions_output.resolve())

    cold_start_rate = float(test["history_segment"].eq("cold_start").mean())
    evaluation = {
        "dataset_version": "admission_ml_v1",
        "model_version": MODEL_VERSION,
        "target": TARGET,
        "split": {"train": "<=2022", "validation": "2023", "test": "2024"},
        "sample_counts": {
            "train": int(len(train)),
            "validation": int(len(validation)),
            "test": int(len(test)),
            "test_cold_start_rate": cold_start_rate,
        },
        "preprocessing": {
            "categorical_features": CATEGORICAL_FEATURES,
            "numeric_features": NUMERIC_FEATURES,
            "categorical": "constant imputation + OneHotEncoder(handle_unknown='ignore', min_frequency=10)",
            "numeric_tree": "median imputation with missing indicators",
            "numeric_ridge": "median imputation with missing indicators + StandardScaler",
        },
        "models": {
            "baselines": baseline_metrics,
            "validation_candidates": candidates,
        },
        "selection": {
            "metric": "validation_2023_mae",
            "selected_candidate": selected["name"],
            "selected_family": selected["family"],
            "selected_validation": selected["validation"],
            "configuration_locked_before_test": True,
            "test_used_for_hyperparameter_selection": False,
        },
        "final_test_2024": final_test,
        "test_by_large_school": school_test_metrics,
        "test_by_major_group": major_group_test_metrics,
        "acceptance": acceptance,
        "top_features": importance.head(30).to_dict(orient="records"),
        "outputs": {
            "model": str(args.model_output.resolve()),
            "evaluation": str(args.evaluation_output.resolve()),
            "test_predictions": str(args.predictions_output.resolve()),
            "feature_importance": str(args.importance_output.resolve()),
        },
    }
    atomic_json(json_safe(evaluation), args.evaluation_output.resolve())

    print(f"Validation candidates trained: {len(candidates)}")
    print(f"Selected: {selected['name']} ({selected['family']})")
    print(f"Validation MAE: {validation_mae:.6f}")
    print(f"Test MAE: {final_test['all']['mae']:.6f}")
    print(f"Test RMSE: {final_test['all']['rmse']:.6f}")
    print(f"Test R2: {final_test['all']['r2']:.6f}")
    print(f"Deployment status: {acceptance['deployment_status']}")


if __name__ == "__main__":
    main()
