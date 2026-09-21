#Decision Engine: AHP + TOPSIS

from __future__ import annotations
from math import exp
from typing import any 

import numpy as np

# 5 tiêu chí đánh giá: academic_fit, interest_fit, addmission_fit, job_demand, salary_score
CRITERIA = (
    "academic_fit", 
    "interest_fit", 
    "addmission_fit",
    "job_demand",
    "salary_score",
)

# key nội bộ của engine 
PRIORITY_KEY_MAP = {
    "academic": "academic_fit",
    "interest": "interest_fit",
    "admission": "addmission_fit",
    "job": "job_demand",
    "salary": "salary_score",
}

# Hiện tại cả 5 tiêu chí đều là benefit 
# điểm cao hơn nghĩa là phù hợp hơn 
DIRECTION = { 
    "academic_fit": "benefit",
    "interest_fit": "benefit",
    "addmission_fit": "benefit",
    "job_demand": "benefit",
    "salary_score": "benefit",
}

# Random Index của Saaty, dùng khi tính Consistency Ratio.
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

# Mapping này nên minh bạch, không dùng NPL mơ hồ ở bản đầu 
INTEREST_RELATION_SCORES = {
    "exact": 1.00,     # đúng ngành người dùng chọn 
    "close": 0.80,     # ngành gần 
    "related": 0.50,   # cùng nhóm/ nghề liên quan
    "unrelated": 0.20, # ít liên quan
}

class DecisionEngineError(ValueError):
    """Lỗi input của Decision Engine."""

def _validate_score_01(value: Any, field_name: str) -> float:
    """Ép score về float và bắt buộc trong khoảng 0-1."""
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DecisionEngineError(f"{field_name} phải là số.") from error

    if not 0.0 <= number <= 1.0:
        raise DecisionEngineError(f"{field_name} phải nằm trong khoảng 0-1.")

    return number 

def build_pairwise_matrix(priorities: dict[str, Any]) -> np.ndarray:
    """
    Tạo ma trận AHP từ priority 1-5.

    Ví dụ:
    academic = 5, salary = 2
    => academic so với salary = 5 / 2 = 2.5
    => salary so với academic = 2 / 5 = 0.4
    """
    expected_keys = set(PRIORITY_KEY_MAP.keys())

    if set(priorities.keys()) != expected_keys:
        raise DecisionEngineError(
            f"priorities phải có đúng các key: {sorted(expected_keys)}"
        )

    values = []
    for key in PRIORITY_KEY_MAP:
        value = priorities[key]

        # Không nhận 0 vì không thể tạo tỉ lệ a_ij = p_i / p_j.
        if not isinstance(value, int) or value < 1 or value > 5:
            raise DecisionEngineError(
                f"priorities.{key} phải là số nguyên từ 1 đến 5."
            )

        values.append(float(value))

    values_array = np.array(values, dtype=float)

    # Broadcasting của NumPy:
    # [[p1/p1, p1/p2, ...],
    #  [p2/p1, p2/p2, ...], ...]
    return values_array[:, None] / values_array[None, :]

