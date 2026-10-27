"""Chat retrieval must ground a question in the requested major and score."""

from __future__ import annotations

import pandas as pd

from services import assistant_service


def test_it_question_uses_requested_score_and_relevant_d01_majors(monkeypatch):
    rows = pd.DataFrame([
        {"university_name": "Đại học A", "major_name": "Sư phạm Ngữ văn", "major_code": "7140217", "subject_combination": "D01", "cutoff_score_30": 27.0},
        {"university_name": "Đại học B", "major_name": "Công nghệ thông tin", "major_code": "7480201", "subject_combination": "D01", "cutoff_score_30": 27.1},
        {"university_name": "Đại học C", "major_name": "Kỹ thuật phần mềm", "major_code": "7480103", "subject_combination": "D01", "cutoff_score_30": 26.6},
        {"university_name": "Đại học D", "major_name": "Công nghệ thông tin", "major_code": "7480201", "subject_combination": "A00", "cutoff_score_30": 27.0},
    ])
    monkeypatch.setattr(assistant_service.data_repo, "get_master_data", lambda: rows.copy())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    messages, admissions, _ = assistant_service._prepare_request(
        "27 điểm D01 học IT thì sao",
        {"combination": "A00", "scores": {"toan": 8, "vatly": 8, "hoahoc": 8}},
        [],
    )

    assert [item["major_name"] for item in admissions] == ["Công nghệ thông tin", "Kỹ thuật phần mềm"]
    assert all(item["subject_combination"] == "D01" and item["cutoff_year"] == "2024" for item in admissions)
    assert "'lookup_combination': 'D01'" in messages[-1]["content"]
    assert "'lookup_score': 27.0" in messages[-1]["content"]


def test_it_question_does_not_substitute_unrelated_majors(monkeypatch):
    rows = pd.DataFrame([
        {"university_name": "Đại học A", "major_name": "Sư phạm Tin học", "subject_combination": "D01", "cutoff_score_30": 27.0},
    ])
    monkeypatch.setattr(assistant_service.data_repo, "get_master_data", lambda: rows.copy())

    assert assistant_service._admission_context("27 điểm D01 học CNTT thì sao", "D01", 27) == []


def test_it_job_context_skips_unrelated_categories(monkeypatch):
    rows = pd.DataFrame([
        {"job_category": "tài_chính_kế_toán_ngân_hàng", "posting_count": 100},
        {"job_category": "công_nghệ_thông_tin_kỹ_thuật_số", "posting_count": 200},
    ])
    monkeypatch.setattr(assistant_service.data_repo, "get_job_market_data", lambda: rows.copy())

    jobs = assistant_service._job_context("27 điểm D01 học IT thì sao")

    assert len(jobs) == 1
    assert jobs[0]["job_category"] == "công_nghệ_thông_tin_kỹ_thuật_số"
    assert assistant_service._job_context("Sắp xếp nguyện vọng như thế nào?") == []


def test_wishlist_order_question_does_not_select_unrelated_major(monkeypatch):
    rows = pd.DataFrame([
        {"university_name": "Đại học A", "major_name": "Máy và tự động hóa xếp dỡ", "subject_combination": "D01", "cutoff_score_30": 27.0},
    ])
    monkeypatch.setattr(assistant_service.data_repo, "get_master_data", lambda: rows.copy())

    assert assistant_service._admission_context("Tôi nên sắp xếp nguyện vọng thế nào?", "D01", 27) == []
