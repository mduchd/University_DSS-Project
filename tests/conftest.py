"""Fixture dùng chung để test không phải đọc lại dataset và model nhiều lần."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "data/processed/admission_ml_features.csv"
MODEL_PATH = ROOT / "models/model.joblib"
EVALUATION_PATH = ROOT / "models/evaluation.json"


@pytest.fixture(scope="session")
def feature_data() -> pd.DataFrame:
    """Đọc feature dataset một lần cho toàn bộ test session."""
    return pd.read_csv(FEATURES_PATH, low_memory=False)


@pytest.fixture(scope="session")
def evaluation() -> dict:
    """Đọc báo cáo evaluation một lần cho toàn bộ test session."""
    return json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def prepared_test_record(feature_data: pd.DataFrame) -> dict:
    """Lấy một record test 2024 đã có đủ feature theo contract của predictor."""
    from models.train_cutoff_model import prepare_model_frame

    prepared = prepare_model_frame(feature_data)
    return prepared.loc[prepared["model_split"].eq("test")].iloc[0].to_dict()
