"""Unit tests for the independent AHP + TOPSIS decision engine."""

import unittest

import numpy as np

from services.decision_engine import (
    CRITERIA,
    DIRECTIONS,
    analyze_pairwise_matrix,
    calculate_admission_fit,
    calculate_ahp,
    rank_candidates,
    topsis_rank,
)


class DecisionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.priorities = {
            "academic": 5,
            "interest": 4,
            "admission": 3,
            "job_demand": 4,
            "salary": 2,
        }

    def test_ahp_weights_sum_to_one(self) -> None:
        result = calculate_ahp(self.priorities)
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0, places=8)

    def test_priority_matrix_is_consistent(self) -> None:
        result = calculate_ahp(self.priorities)
        self.assertLessEqual(result["consistency_ratio"], 0.10)
        self.assertTrue(result["is_consistent"])

    def test_inconsistent_pairwise_matrix_has_high_cr(self) -> None:
        # Reciprocal, but deliberately contradictory: A >> B, B >> C, C >> A.
        matrix = np.array([[1, 9, 1 / 3], [1 / 9, 1, 9], [3, 1 / 9, 1]], dtype=float)
        _, consistency_ratio = analyze_pairwise_matrix(matrix)
        self.assertGreater(consistency_ratio, 0.10)

    def test_admission_fit_increases_with_score_gap(self) -> None:
        low = calculate_admission_fit(24.0, 27.0)
        high = calculate_admission_fit(28.0, 27.0)
        self.assertLess(low, high)

    def test_topsis_returns_expected_benefit_order(self) -> None:
        rows = [
            {"candidate_id": "A", "criteria_scores": {criterion: 0.9 for criterion in CRITERIA}},
            {"candidate_id": "B", "criteria_scores": {criterion: 0.6 for criterion in CRITERIA}},
            {"candidate_id": "C", "criteria_scores": {criterion: 0.3 for criterion in CRITERIA}},
        ]
        weights = {criterion: 1 / len(CRITERIA) for criterion in CRITERIA}
        ranking = topsis_rank(rows, CRITERIA, weights, DIRECTIONS)
        self.assertEqual([item["candidate_id"] for item in ranking], ["A", "B", "C"])

    def test_cost_criterion_prefers_lower_value(self) -> None:
        rows = [
            {"candidate_id": "low-fee", "criteria_scores": {"quality": 0.8, "tuition": 0.2}},
            {"candidate_id": "high-fee", "criteria_scores": {"quality": 0.8, "tuition": 0.8}},
        ]
        ranking = topsis_rank(
            rows,
            ("quality", "tuition"),
            {"quality": 0.5, "tuition": 0.5},
            {"quality": "benefit", "tuition": "cost"},
        )
        self.assertEqual(ranking[0]["candidate_id"], "low-fee")

    def test_rank_candidates_returns_contract(self) -> None:
        profile = {
            "scores": {"toan": 8.5, "vatly": 8.0, "ngoaingu": 7.5},
            "combination": "A01",
            "interest": "Công nghệ thông tin",
            "priorities": self.priorities,
        }
        candidates = [
            {
                "candidate_id": "U01-7480201-A01",
                "university_id": "U01",
                "major_code": "7480201",
                "school": "Đại học A",
                "major": "Công nghệ thông tin",
                "combination": "A01",
                "predicted_cutoff": 23.0,
                "subject_weights": {"toan": 0.5, "vatly": 0.3, "ngoaingu": 0.2},
                "interest_relation": "exact",
                "job_demand": 0.85,
                "salary_score": 0.80,
            }
        ]
        result = rank_candidates(profile, candidates)
        self.assertIn("criteria_weights", result)
        self.assertIn("ahp", result)
        self.assertEqual(result["ranking"][0]["rank"], 1)
        self.assertIn("admission_fit", result["ranking"][0]["criteria_scores"])


if __name__ == "__main__":
    unittest.main()
