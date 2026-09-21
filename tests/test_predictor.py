from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from models.predictor import CutoffPredictor, load_artifact
from tests.conftest import MODEL_PATH, ROOT


EXPECTED_OUTPUT_FIELDS = {
    "university",
    "major",
    "year",
    "predicted_cutoff",
    "model_version",
    "is_cold_start",
}


def test_predictor_accepts_unseen_categories(prepared_test_record: dict) -> None:
    record = dict(prepared_test_record)
    record["university_admission_code"] = "__NEW_UNIVERSITY__"
    record["canonical_program_id"] = "__NEW_PROGRAM__"
    result = CutoffPredictor(MODEL_PATH).predict_one(record)
    assert result["university"] == "__NEW_UNIVERSITY__"
    assert 0 <= result["predicted_cutoff"] <= 30


def test_predictor_validates_required_features(prepared_test_record: dict) -> None:
    record = dict(prepared_test_record)
    record.pop("year")
    with pytest.raises(ValueError, match=r"Missing required feature.*year"):
        CutoffPredictor(MODEL_PATH).predict_one(record)


def test_output_contract_has_no_admission_probability(prepared_test_record: dict) -> None:
    result = CutoffPredictor(MODEL_PATH).predict_one(prepared_test_record)
    assert set(result) == EXPECTED_OUTPUT_FIELDS
    assert "chance_of_admission" not in result
    assert "xác suất đỗ" not in result
    assert isinstance(result["is_cold_start"], bool)


def test_model_is_cached_and_prediction_is_repeatable(prepared_test_record: dict) -> None:
    assert load_artifact(MODEL_PATH) is load_artifact(MODEL_PATH)
    predictor = CutoffPredictor(MODEL_PATH)
    assert predictor.predict_one(prepared_test_record) == predictor.predict_one(prepared_test_record)


def test_predictor_runs_as_standalone_script(
    prepared_test_record: dict, tmp_path: Path
) -> None:
    input_path = tmp_path / "predictor_input.json"
    serializable = {
        key: (None if _is_missing(value) else _to_builtin(value))
        for key, value in prepared_test_record.items()
    }
    input_path.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "models/predictor.py"),
            "--input-json",
            str(input_path),
            "--model",
            str(MODEL_PATH),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    output = json.loads(completed.stdout)
    assert set(output) == EXPECTED_OUTPUT_FIELDS
    assert 0 <= output["predicted_cutoff"] <= 30


def _is_missing(value: object) -> bool:
    import pandas as pd

    result = pd.isna(value)
    return bool(result) if not hasattr(result, "__len__") else False


def _to_builtin(value: object) -> object:
    return value.item() if hasattr(value, "item") else value
