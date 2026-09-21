"""Prediction interface for the admission-cutoff model.

The persisted artifact contains the fitted preprocessing pipeline and estimator.
This module loads it once per process, validates the feature contract, and never
returns an admission-probability field.
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd


DEFAULT_MODEL_PATH = Path(__file__).resolve().with_name("model.joblib")

GROUP_FALLBACK_COLUMNS = [
    "school_combination_historical_mean",
    "major_group_combination_historical_mean",
    "school_historical_mean",
    "major_group_historical_mean",
    "combination_historical_mean",
    "global_historical_mean",
]


@lru_cache(maxsize=4)
def load_artifact(model_path: str | Path = DEFAULT_MODEL_PATH) -> dict[str, Any]:
    """Load and cache an artifact; repeated predictions do not reload the file."""
    resolved = str(Path(model_path).resolve())
    artifact = joblib.load(resolved)
    if not isinstance(artifact, dict) or "pipeline" not in artifact or "metadata" not in artifact:
        raise ValueError("Invalid artifact: expected fitted pipeline and metadata.")
    if not hasattr(artifact["pipeline"], "predict"):
        raise ValueError("Invalid artifact: pipeline does not implement predict().")
    return artifact


def _first_present(record: Mapping[str, Any], names: list[str]) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None and not (isinstance(value, float) and np.isnan(value)):
            return value
    return None


def _derive_features(record: Mapping[str, Any]) -> dict[str, Any]:
    prepared = dict(record)
    if prepared.get("canonical_program_id") is None and prepared.get("program_series_key") is not None:
        prepared["canonical_program_id"] = prepared["program_series_key"]
    if prepared.get("canonical_major_code") is None:
        prepared["canonical_major_code"] = _first_present(
            prepared, ["major_code", "major_admission_code"]
        )
    if prepared.get("major_group") is None and prepared.get("major_group_normalized") is not None:
        prepared["major_group"] = prepared["major_group_normalized"]
    if prepared.get("group_mean_feature") is None:
        prepared["group_mean_feature"] = _first_present(prepared, GROUP_FALLBACK_COLUMNS)
    if prepared.get("hybrid_baseline_feature") is None:
        prepared["hybrid_baseline_feature"] = _first_present(
            prepared, ["last_observed_cutoff", "group_mean_feature"]
        )
    return prepared


class CutoffPredictor:
    """Validated single-row and batch prediction API."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
        self.model_path = Path(model_path).resolve()
        self.artifact = load_artifact(self.model_path)
        self.pipeline = self.artifact["pipeline"]
        self.metadata = self.artifact["metadata"]
        self.required_features = list(self.metadata["required_features"])

    def prepare(self, records: Mapping[str, Any] | list[Mapping[str, Any]]) -> pd.DataFrame:
        rows = [records] if isinstance(records, Mapping) else list(records)
        if not rows:
            raise ValueError("At least one input record is required.")
        prepared = [_derive_features(row) for row in rows]
        missing_by_row: dict[int, list[str]] = {}
        for index, row in enumerate(prepared):
            missing = [feature for feature in self.required_features if feature not in row]
            if missing:
                missing_by_row[index] = missing
        if missing_by_row:
            details = "; ".join(
                f"row {index}: {', '.join(features)}"
                for index, features in missing_by_row.items()
            )
            raise ValueError(f"Missing required feature columns ({details}).")
        return pd.DataFrame(prepared).loc[:, self.required_features]

    def predict_values(
        self, records: Mapping[str, Any] | list[Mapping[str, Any]]
    ) -> np.ndarray:
        frame = self.prepare(records)
        predictions = np.asarray(self.pipeline.predict(frame), dtype=float)
        lower, upper = self.metadata.get("prediction_clip", [0.0, 30.0])
        return np.clip(predictions, float(lower), float(upper))

    def predict_one(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = _derive_features(record)
        predicted = float(self.predict_values(prepared)[0])
        historical_count = prepared.get("historical_count")
        is_cold_start = prepared.get("history_segment") == "cold_start"
        if historical_count is not None and not pd.isna(historical_count):
            is_cold_start = float(historical_count) <= 0
        major = _first_present(
            prepared,
            ["canonical_major_name", "major_name", "canonical_program_id", "canonical_major_code"],
        )
        return {
            "university": prepared.get("university_admission_code"),
            "major": major,
            "year": int(prepared["year"]),
            "predicted_cutoff": round(predicted, 2),
            "model_version": self.metadata["model_version"],
            "is_cold_start": bool(is_cold_start),
        }

    def predict_batch(self, records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        values = self.predict_values(records)
        outputs: list[dict[str, Any]] = []
        for record, value in zip(records, values, strict=True):
            prepared = _derive_features(record)
            count = prepared.get("historical_count")
            cold = prepared.get("history_segment") == "cold_start"
            if count is not None and not pd.isna(count):
                cold = float(count) <= 0
            outputs.append(
                {
                    "university": prepared.get("university_admission_code"),
                    "major": _first_present(
                        prepared,
                        ["canonical_major_name", "major_name", "canonical_program_id", "canonical_major_code"],
                    ),
                    "year": int(prepared["year"]),
                    "predicted_cutoff": round(float(value), 2),
                    "model_version": self.metadata["model_version"],
                    "is_cold_start": bool(cold),
                }
            )
        return outputs


@lru_cache(maxsize=1)
def get_default_predictor() -> CutoffPredictor:
    return CutoffPredictor(DEFAULT_MODEL_PATH)


def predict_cutoff(record: Mapping[str, Any]) -> dict[str, Any]:
    """Convenience function for application code."""
    return get_default_predictor().predict_one(record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    predictor = CutoffPredictor(args.model)
    result = (
        predictor.predict_batch(payload)
        if isinstance(payload, list)
        else predictor.predict_one(payload)
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
