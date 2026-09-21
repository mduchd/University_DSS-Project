"""Kiểm tra chất lượng dataset, time split và khả năng chống data leakage."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_series_equal

from models.build_cutoff_features import (
    TARGET,
    add_context_features,
    build_series_history_features,
)


def test_modeling_keys_are_unique(feature_data: pd.DataFrame) -> None:
    """Mỗi year, program series và tổ hợp chỉ được có một target modeling."""
    assert not feature_data["model_key"].duplicated().any()
    assert not feature_data.duplicated(["year", "series_combination_key"]).any()


def test_target_is_complete_and_in_agreed_domain(feature_data: pd.DataFrame) -> None:
    """Target không được thiếu và phải nằm trong thang điểm chuẩn hóa 0-30."""
    target = feature_data[TARGET]
    assert target.notna().all()
    assert target.between(0, 30, inclusive="both").all()


def test_time_splits_are_fixed_and_do_not_overlap(feature_data: pd.DataFrame) -> None:
    """Khẳng định train, validation và test tuân thủ đúng mốc năm đã khóa."""
    expected = pd.Series(
        np.select(
            [
                feature_data["year"].le(2022),
                feature_data["year"].eq(2023),
                feature_data["year"].eq(2024),
            ],
            ["train", "validation", "test"],
            default="out_of_scope",
        ),
        index=feature_data.index,
        name="model_split",
    )
    assert_series_equal(feature_data["model_split"], expected, check_dtype=False)
    split_years = {
        split: set(group["year"].unique())
        for split, group in feature_data.groupby("model_split")
    }
    assert split_years["train"].isdisjoint(split_years["validation"])
    assert split_years["train"].isdisjoint(split_years["test"])
    assert split_years["validation"].isdisjoint(split_years["test"])


def test_exact_lags_match_only_prior_year_targets(feature_data: pd.DataFrame) -> None:
    """Kiểm tra lag k năm luôn trỏ đúng target của năm t-k trong cùng series."""
    lookup = feature_data.set_index(["series_combination_key", "year"])[TARGET]
    for lag in (1, 2, 3):
        rows = feature_data.loc[
            feature_data[f"cutoff_lag_{lag}"].notna(),
            ["series_combination_key", "year", f"cutoff_lag_{lag}"],
        ]
        expected = np.array(
            [lookup.loc[(key, int(year) - lag)] for key, year in rows.iloc[:, :2].itertuples(index=False)],
            dtype=float,
        )
        np.testing.assert_allclose(rows[f"cutoff_lag_{lag}"].to_numpy(float), expected)


def test_current_target_perturbation_does_not_change_current_features() -> None:
    """Chứng minh thay target năm t không làm thay đổi feature của chính năm t."""
    # Đây là test leakage quan trọng nhất: sửa target năm t không được làm đổi feature năm t.
    source = pd.DataFrame(
        {
            "year": [2020, 2021, 2022, 2023],
            "series_combination_key": ["series-a"] * 4,
            "institution_entity_key": ["school-a"] * 4,
            "major_group_normalized": ["technology"] * 4,
            "subject_combination": ["A00"] * 4,
            TARGET: [20.0, 21.0, 22.0, 23.0],
        }
    )

    def build(frame: pd.DataFrame) -> pd.DataFrame:
        """Tạo lại toàn bộ feature cần so sánh cho một DataFrame thử nghiệm."""
        return add_context_features(build_series_history_features(frame)).set_index("year")

    original = build(source)
    perturbed_source = source.copy()
    perturbed_source.loc[perturbed_source["year"].eq(2022), TARGET] = 29.5
    perturbed = build(perturbed_source)
    generated = [
        column
        for column in original.columns
        if column not in {TARGET, "series_combination_key", "institution_entity_key", "major_group_normalized", "subject_combination"}
    ]
    pd.testing.assert_series_equal(
        original.loc[2022, generated],
        perturbed.loc[2022, generated],
        check_names=False,
    )
    assert original.loc[2023, "lag_1_year"] != perturbed.loc[2023, "lag_1_year"]


def test_exam_features_use_only_t_minus_one(feature_data: pd.DataFrame) -> None:
    """Phổ điểm dùng cho năm t phải có source year đúng bằng t-1."""
    available = feature_data["exam_feature_source_year"].notna()
    assert feature_data.loc[available, "exam_feature_source_year"].eq(
        feature_data.loc[available, "year"] - 1
    ).all()


def test_historical_count_and_mean_use_strictly_prior_rows(feature_data: pd.DataFrame) -> None:
    """Historical count và mean chỉ được tính từ các dòng đứng trước trong series."""
    # shift(1) tạo giá trị kỳ vọng chỉ từ các dòng trước trong cùng series.
    ordered = feature_data.sort_values(["series_combination_key", "year"], kind="stable")
    grouped = ordered.groupby("series_combination_key", sort=False)[TARGET]
    expected_count = grouped.cumcount().astype(float)
    expected_mean = grouped.transform(lambda values: values.shift(1).expanding().mean())
    np.testing.assert_allclose(ordered["historical_count"], expected_count)
    np.testing.assert_allclose(
        ordered["historical_mean"], expected_mean, equal_nan=True, rtol=1e-12, atol=1e-12
    )
