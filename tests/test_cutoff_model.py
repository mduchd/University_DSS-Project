from __future__ import annotations

import joblib
import numpy as np

from models.train_cutoff_model import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from tests.conftest import MODEL_PATH


def test_artifact_contains_fitted_preprocessing_and_model() -> None:
    artifact = joblib.load(MODEL_PATH)
    assert set(artifact) == {"pipeline", "metadata"}
    assert list(artifact["pipeline"].named_steps) == ["preprocessor", "model"]
    assert artifact["metadata"]["required_features"] == CATEGORICAL_FEATURES + NUMERIC_FEATURES


def test_reloaded_model_returns_identical_prediction(prepared_test_record: dict) -> None:
    first = joblib.load(MODEL_PATH)
    second = joblib.load(MODEL_PATH)
    columns = first["metadata"]["required_features"]
    frame = __import__("pandas").DataFrame([prepared_test_record]).loc[:, columns]
    np.testing.assert_array_equal(
        first["pipeline"].predict(frame), second["pipeline"].predict(frame)
    )


def test_model_was_selected_without_using_test(evaluation: dict) -> None:
    selection = evaluation["selection"]
    assert selection["metric"] == "validation_2023_mae"
    assert selection["configuration_locked_before_test"] is True
    assert selection["test_used_for_hyperparameter_selection"] is False
    assert selection["selected_candidate"]


def test_evaluation_contains_required_metrics_and_segments(evaluation: dict) -> None:
    required_metrics = {"n_samples", "mae", "rmse", "r2"}
    for segment in ("all", "known_history", "cold_start"):
        assert required_metrics.issubset(evaluation["final_test_2024"][segment])
    assert evaluation["sample_counts"] == {
        "train": 55713,
        "validation": 10524,
        "test": 19827,
        "test_cold_start_rate": evaluation["sample_counts"]["test_cold_start_rate"],
    }
    assert 0 < evaluation["sample_counts"]["test_cold_start_rate"] < 1


def test_saved_model_predictions_stay_in_score_domain(prepared_test_record: dict) -> None:
    artifact = joblib.load(MODEL_PATH)
    columns = artifact["metadata"]["required_features"]
    frame = __import__("pandas").DataFrame([prepared_test_record]).loc[:, columns]
    prediction = float(artifact["pipeline"].predict(frame)[0])
    lower, upper = artifact["metadata"]["prediction_clip"]
    assert lower <= prediction <= upper
