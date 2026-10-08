"""Feature store và adapter dự báo điểm chuẩn cho luồng gợi ý.

Mô hình cutoff_v1 cần feature lịch sử được tính theo đúng mốc thời gian. Module
này tạo feature cho năm kế tiếp từ dữ liệu đã chấp nhận đến 2024, sau đó chỉ
đưa các feature đó vào artifact đã huấn luyện. Vì vậy application không tự
điền giá trị 0 hay dùng điểm chuẩn cùng năm làm input cho model.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from models.build_cutoff_features import (
    TARGET,
    add_cold_start_design,
    add_context_features,
    add_exam_distribution_features,
    build_series_history_features,
)
from models.predictor import get_default_predictor
from models.train_cutoff_model import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    prepare_model_frame,
)


ROOT = Path(__file__).resolve().parents[1]
STEP2_PATH = ROOT / "data" / "processed" / "admission_ml_step2.csv"
EXAM_SUMMARY_PATH = (
    ROOT / "data" / "processed" / "exam" / "exam_score_summary_by_year_province.csv"
)
JOIN_KEYS = [
    "university_admission_code",
    "major_admission_code",
    "subject_combination",
]
SOURCE_COLUMNS = [
    "year",
    TARGET,
    "series_combination_key",
    "institution_entity_key",
    "major_group_normalized",
    "subject_combination",
    "university_admission_code",
    "program_series_key",
    "major_code",
    "major_admission_code",
    "canonical_major_name",
    "training_eligible_step2",
]


def _normalise_join_key(series: pd.Series) -> pd.Series:
    """Chuẩn hóa key join mà không biến mã tuyển sinh thành số thực."""
    return series.astype("string").fillna("").str.strip()


class CutoffForecastService:
    """Tạo forecast feature store một lần, sau đó dự báo theo batch ứng viên."""

    @lru_cache(maxsize=1)
    def _forecast_features(self) -> pd.DataFrame:
        """Sinh các feature của năm kế tiếp chỉ từ lịch sử đã có.

        Các dòng 2025 được sao từ identity của các series hợp lệ năm 2024 nhưng
        target để missing. Các hàm feature engineering vì thế chỉ nhìn thấy
        target của các năm trước khi tạo lag và aggregate cho 2025.
        """
        if not STEP2_PATH.exists() or not EXAM_SUMMARY_PATH.exists():
            raise FileNotFoundError("Không tìm thấy dữ liệu feature hoặc tóm tắt phổ điểm cho cutoff model.")

        source = pd.read_csv(STEP2_PATH, usecols=SOURCE_COLUMNS, low_memory=False)
        eligible = source["training_eligible_step2"].astype("string").str.casefold().isin(["true", "1"])
        history = source.loc[eligible].drop(columns=["training_eligible_step2"]).copy()
        if history.empty:
            raise ValueError("Không có dòng dữ liệu tuyển sinh hợp lệ để tạo forecast feature store.")

        latest_year = int(history["year"].max())
        future_year = latest_year + 1
        future = history.loc[history["year"].eq(latest_year)].copy()
        future["year"] = future_year
        future[TARGET] = np.nan

        combined = pd.concat([history, future], ignore_index=True)
        enriched = build_series_history_features(combined)
        enriched = add_context_features(enriched)
        enriched = add_exam_distribution_features(enriched, EXAM_SUMMARY_PATH)
        enriched = add_cold_start_design(enriched)
        enriched["history_segment"] = np.where(
            enriched["historical_count_prior"].eq(0), "cold_start", "known_history"
        )
        prepared = prepare_model_frame(enriched.loc[enriched["year"].eq(future_year)].copy())

        keep = list(dict.fromkeys(
            JOIN_KEYS + ["canonical_major_name", "history_segment"] + CATEGORICAL_FEATURES + NUMERIC_FEATURES
        ))
        forecast = prepared.loc[:, keep].copy()
        for key in JOIN_KEYS:
            forecast[key] = _normalise_join_key(forecast[key])
        forecast = forecast.drop_duplicates(JOIN_KEYS, keep="first")
        forecast["forecast_year"] = future_year
        return forecast

    def add_forecasts(self, candidates: pd.DataFrame) -> pd.DataFrame:
        """Gắn điểm chuẩn dự báo cho các candidate, fallback về dữ liệu lịch sử.

        Không có forecast feature hợp lệ thì candidate vẫn được giữ; frontend có
        thể hiển thị mốc điểm chuẩn đã quan sát thay vì một dự báo bịa ra.
        """
        result = candidates.copy()
        result["forecast_source"] = "historical_2024_fallback"
        result["forecast_year"] = pd.NA
        result["forecast_model_version"] = pd.NA
        result["forecast_is_cold_start"] = pd.NA
        result["predicted_cutoff"] = np.nan

        if result.empty:
            return result

        try:
            features = self._forecast_features()
            # Merge từ candidate gốc để metadata fallback khởi tạo ở ``result``
            # không che khuất các cột forecast bên phải.
            working = candidates.copy()
            for key in JOIN_KEYS:
                if key not in working.columns:
                    raise ValueError(f"Candidate thiếu khóa forecast '{key}'.")
                working[key] = _normalise_join_key(working[key])

            merged = working.merge(features, on=JOIN_KEYS, how="left", suffixes=("", "_forecast"))
            required = CATEGORICAL_FEATURES + NUMERIC_FEATURES
            # Numeric missing là một tín hiệu cold-start được pipeline xử lý bằng imputer;
            # chỉ cần các cột feature tồn tại sau merge để đưa vào model.
            ready = merged["forecast_year"].notna()
            if ready.any():
                predictor = get_default_predictor()
                records = merged.loc[ready, required].to_dict(orient="records")
                outputs = predictor.predict_batch(records)
                predicted = pd.DataFrame(outputs, index=merged.index[ready])
                merged.loc[ready, "predicted_cutoff"] = predicted["predicted_cutoff"]
                merged.loc[ready, "forecast_model_version"] = predicted["model_version"]
                merged.loc[ready, "forecast_is_cold_start"] = predicted["is_cold_start"].astype(bool)
                merged.loc[ready, "forecast_source"] = "xgboost_cutoff_v1"

            # Giữ nguyên cấu trúc candidate, chỉ copy các metadata forecast cần dùng.
            for column in [
                "predicted_cutoff",
                "forecast_source",
                "forecast_year",
                "forecast_model_version",
                "forecast_is_cold_start",
            ]:
                available = merged[column]
                mask = available.notna().to_numpy()
                if mask.any():
                    column_position = result.columns.get_loc(column)
                    result.iloc[np.flatnonzero(mask), column_position] = available.to_numpy()[mask]
        except Exception as exc:  # Application vẫn hoạt động khi artifact/dataset bị thiếu.
            logging.warning("Không thể gắn XGBoost cutoff forecast, dùng điểm lịch sử: %s", exc)

        return result


cutoff_forecast_service = CutoffForecastService()
