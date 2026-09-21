"""Independent AHP + TOPSIS engine for university recommendation ranking.

This module deliberately has no dependency on Flask, CSV files, or ML models.
The caller prepares candidate features and calls :func:`rank_candidates`.
"""

from __future__ import annotations

from math import exp
from typing import Any

import numpy as np


# The five criteria agreed by the project team. All values supplied to TOPSIS
# must be normalized to the closed range [0, 1].
CRITERIA = (
    "academic_fit",
    "interest_fit",
    "admission_fit",
    "job_demand",
    "salary_score",
)

# Public input from UI -> internal criterion name.
PRIORITY_KEY_MAP = {
    "academic": "academic_fit",
    "interest": "interest_fit",
    "admission": "admission_fit",
    "job_demand": "job_demand",
    "salary": "salary_score",
}

# TOPSIS supports both directions. The current five product criteria are all
# benefits: a larger value means a more desirable option.
DIRECTIONS = {criterion: "benefit" for criterion in CRITERIA}

# Saaty's Random Index values, used by Consistency Ratio (CR).
RI_VALUES = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}

INTEREST_RELATION_SCORES = {
    "exact": 1.00,
    "close": 0.80,
    "related": 0.50,
    "unrelated": 0.20,
}


class DecisionEngineError(ValueError):
    """Raised when the engine receives an invalid input contract."""


def _score_01(value: Any, field_name: str) -> float:
    """Return a numeric score constrained to [0, 1]."""
    try:
        score = float(value)
    except (TypeError, ValueError) as error:
        raise DecisionEngineError(f"{field_name} must be numeric.") from error

    if not 0.0 <= score <= 1.0:
        raise DecisionEngineError(f"{field_name} must be between 0 and 1.")
    return score


def build_pairwise_matrix(priorities: dict[str, Any]) -> np.ndarray:
    """Build an AHP reciprocal matrix from the UI priority scale 1--5.

    ``a_ij = priority_i / priority_j``. A priority of zero is disallowed,
    because it makes pairwise ratios undefined.
    """
    expected = set(PRIORITY_KEY_MAP)
    if set(priorities) != expected:
        raise DecisionEngineError(
            f"priorities must contain exactly: {sorted(expected)}"
        )

    values: list[float] = []
    for key in PRIORITY_KEY_MAP:
        value = priorities[key]
        # bool is an int subclass, but it is not a valid UI priority.
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise DecisionEngineError(
                f"priorities.{key} must be an integer from 1 to 5."
            )
        values.append(float(value))

    priority_vector = np.array(values, dtype=float)
    return priority_vector[:, None] / priority_vector[None, :]


def analyze_pairwise_matrix(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Return the AHP principal-eigenvector weights and Consistency Ratio.

    Kept public so tests can pass a deliberately inconsistent matrix and prove
    that the CR calculation works independently from UI-generated priorities.
    """
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise DecisionEngineError("Pairwise matrix must be square.")

    size = matrix.shape[0]
    if size not in RI_VALUES:
        raise DecisionEngineError("Pairwise matrix size must be from 1 to 10.")
    if np.any(matrix <= 0):
        raise DecisionEngineError("Pairwise matrix entries must be positive.")
    if not np.allclose(matrix * matrix.T, np.ones((size, size)), atol=1e-8):
        raise DecisionEngineError("Pairwise matrix must be reciprocal.")

    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    main_index = int(np.argmax(eigenvalues.real))
    lambda_max = float(eigenvalues[main_index].real)

    raw_weights = np.abs(eigenvectors[:, main_index].real)
    weights = raw_weights / raw_weights.sum()

    if size <= 2:
        return weights, 0.0

    consistency_index = (lambda_max - size) / (size - 1)
    consistency_ratio = consistency_index / RI_VALUES[size]
    return weights, float(consistency_ratio)


def calculate_ahp(priorities: dict[str, Any]) -> dict[str, Any]:
    """Calculate criterion weights and AHP consistency metadata."""
    matrix = build_pairwise_matrix(priorities)
    weights_array, consistency_ratio = analyze_pairwise_matrix(matrix)
    weights = {
        criterion: float(weight)
        for criterion, weight in zip(CRITERIA, weights_array)
    }
    return {
        "weights": weights,
        "pairwise_matrix": matrix.tolist(),
        "consistency_ratio": consistency_ratio,
        "is_consistent": consistency_ratio <= 0.10,
    }


def calculate_academic_fit(
    scores: dict[str, Any], subject_weights: dict[str, Any]
) -> float:
    """Calculate weighted subject fit, converting 0--10 exam scores to 0--1."""
    if not subject_weights:
        raise DecisionEngineError("subject_weights cannot be empty.")

    total_weight = 0.0
    weighted_score = 0.0
    for subject, raw_weight in subject_weights.items():
        if subject not in scores:
            raise DecisionEngineError(f"Missing score for subject: {subject}.")
        try:
            score = float(scores[subject])
            weight = float(raw_weight)
        except (TypeError, ValueError) as error:
            raise DecisionEngineError(f"Invalid score or weight for {subject}.") from error
        if not 0.0 <= score <= 10.0:
            raise DecisionEngineError(f"Score for {subject} must be between 0 and 10.")
        if weight < 0.0:
            raise DecisionEngineError(f"Weight for {subject} cannot be negative.")
        total_weight += weight
        weighted_score += (score / 10.0) * weight

    if total_weight <= 0.0:
        raise DecisionEngineError("The sum of subject_weights must be positive.")
    return weighted_score / total_weight


def calculate_interest_fit(interest_relation: str) -> float:
    """Convert transparent interest mapping relation to a score in [0, 1]."""
    relation = str(interest_relation).strip().lower()
    if relation not in INTEREST_RELATION_SCORES:
        raise DecisionEngineError(
            "interest_relation must be one of: "
            f"{sorted(INTEREST_RELATION_SCORES)}"
        )
    return INTEREST_RELATION_SCORES[relation]


def calculate_admission_fit(
    student_score: float, predicted_cutoff: float, sensitivity: float = 1.1
) -> float:
    """Convert score gap to a smooth competitiveness score via a sigmoid.

    It measures relative competitiveness against a *predicted reference cutoff*,
    never an individual student's true admission probability.
    """
    gap = float(student_score) - float(predicted_cutoff)
    z = max(-60.0, min(60.0, sensitivity * gap))  # avoid exp overflow
    return 1.0 / (1.0 + exp(-z))


def build_criteria_scores(profile: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    """Build all five TOPSIS input scores for one candidate."""
    if candidate.get("combination") != profile.get("combination"):
        raise DecisionEngineError("Candidate combination does not match profile combination.")

    scores = profile.get("scores")
    if not isinstance(scores, dict) or not scores:
        raise DecisionEngineError("profile.scores must be a non-empty object.")

    # Caller supplies only the three subjects of the selected combination.
    student_score = sum(float(score) for score in scores.values())
    return {
        "academic_fit": calculate_academic_fit(scores, candidate["subject_weights"]),
        "interest_fit": calculate_interest_fit(candidate.get("interest_relation", "unrelated")),
        "admission_fit": calculate_admission_fit(student_score, candidate["predicted_cutoff"]),
        "job_demand": _score_01(candidate["job_demand"], "candidate.job_demand"),
        "salary_score": _score_01(candidate["salary_score"], "candidate.salary_score"),
    }


def topsis_rank(
    rows: list[dict[str, Any]],
    criteria: tuple[str, ...],
    weights: dict[str, float],
    directions: dict[str, str],
) -> list[dict[str, Any]]:
    """Rank rows with TOPSIS and return closeness coefficient as topsis_score."""
    if not rows:
        return []

    weight_vector = np.array([float(weights[name]) for name in criteria], dtype=float)
    if np.any(weight_vector < 0) or not np.isclose(weight_vector.sum(), 1.0):
        raise DecisionEngineError("TOPSIS weights must be non-negative and sum to 1.")

    matrix = np.array(
        [
            [_score_01(row["criteria_scores"][criterion], criterion) for criterion in criteria]
            for row in rows
        ],
        dtype=float,
    )

    # Vector normalization, then AHP-weighting.
    denominators = np.sqrt((matrix**2).sum(axis=0))
    normalized = np.divide(matrix, denominators, out=np.zeros_like(matrix), where=denominators != 0)
    weighted = normalized * weight_vector

    positive: list[float] = []
    negative: list[float] = []
    for index, criterion in enumerate(criteria):
        column = weighted[:, index]
        direction = directions.get(criterion)
        if direction == "benefit":
            positive.append(float(column.max()))
            negative.append(float(column.min()))
        elif direction == "cost":
            positive.append(float(column.min()))
            negative.append(float(column.max()))
        else:
            raise DecisionEngineError(f"Direction for {criterion} must be benefit or cost.")

    positive_array = np.array(positive)
    negative_array = np.array(negative)
    distance_positive = np.sqrt(((weighted - positive_array) ** 2).sum(axis=1))
    distance_negative = np.sqrt(((weighted - negative_array) ** 2).sum(axis=1))
    total_distance = distance_positive + distance_negative
    closeness = np.divide(
        distance_negative,
        total_distance,
        out=np.full(len(rows), 0.5),
        where=total_distance != 0,
    )

    ranked = [{**row, "topsis_score": float(score)} for row, score in zip(rows, closeness)]
    # Deterministic tie-breaker makes API results stable.
    ranked.sort(key=lambda item: (-item["topsis_score"], str(item.get("candidate_id", ""))))
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


def rank_candidates(profile: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Main public API for the backend integration layer.

    The backend filters candidates by region and joins data/ML features first.
    This function computes the dynamic fits, AHP weights and TOPSIS ranking.
    """
    if not candidates:
        return {
            "criteria_weights": {},
            "ahp": {"consistency_ratio": 0.0, "is_consistent": True},
            "ranking": [],
        }

    ahp = calculate_ahp(profile["priorities"])
    rows = []
    for candidate in candidates:
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "university_id": candidate["university_id"],
                "major_code": candidate["major_code"],
                "school": candidate.get("school", ""),
                "major": candidate.get("major", ""),
                "combination": candidate["combination"],
                "predicted_cutoff": float(candidate["predicted_cutoff"]),
                "criteria_scores": build_criteria_scores(profile, candidate),
            }
        )

    return {
        "criteria_weights": ahp["weights"],
        "ahp": {
            "consistency_ratio": ahp["consistency_ratio"],
            "is_consistent": ahp["is_consistent"],
        },
        "ranking": topsis_rank(rows, CRITERIA, ahp["weights"], DIRECTIONS),
    }
