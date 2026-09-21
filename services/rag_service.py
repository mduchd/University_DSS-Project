"""
RAG Service: Kho tri thức ngành học & thị trường lao động (Knowledge Base & Retrieval).
Tập hợp và truy xuất dữ kiện thực tế từ:
- major_job_mapping.csv (Ánh xạ ngành - nhóm nghề)
- job_market_summary_by_category.csv (Mức lương, số tin tuyển dụng, kinh nghiệm)
- job_category_skills.json (Kỹ năng chuyên môn, kỹ năng mềm)
- master_admission.csv (Điểm chuẩn 2024, lịch sử 2021-2023, xu hướng điểm)

Cung cấp context có cấu trúc chính xác cho LLM nhằm ngăn chặn hoàn toàn hiện tượng ảo giác (hallucination).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER_ADMISSION_PATH = ROOT / "data" / "master" / "master_admission.csv"
MAJOR_JOB_MAPPING_PATH = ROOT / "data" / "master" / "major_job_mapping.csv"
JOB_SUMMARY_PATH = ROOT / "data" / "processed" / "jobs" / "job_market_summary_by_category.csv"
JOB_SKILLS_PATH = ROOT / "data" / "processed" / "jobs" / "job_category_skills.json"


def normalize_str(text: str) -> str:
    """Chuẩn hóa chuỗi tiếng Việt để tìm kiếm không dấu."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9\s]", " ", text).strip()


class RAGService:
    def __init__(self):
        self.master_df: Optional[pd.DataFrame] = None
        self.job_summary_df: Optional[pd.DataFrame] = None
        self.mapping_df: Optional[pd.DataFrame] = None
        self.skills_lookup: Dict[str, Dict[str, List[str]]] = {}
        self._load_data()

    def _load_data(self):
        """Tải và lập chỉ mục kho tri thức."""
        try:
            if MASTER_ADMISSION_PATH.exists():
                self.master_df = pd.read_csv(MASTER_ADMISSION_PATH, encoding="utf-8-sig", dtype=str)
                # Parse các cột số
                for col in ["cutoff_score_30", "cutoff_2021", "cutoff_2022", "cutoff_2023", "cutoff_2024", "job_posting_count", "job_avg_salary_million"]:
                    if col in self.master_df.columns:
                        self.master_df[col] = pd.to_numeric(self.master_df[col], errors="coerce")
            else:
                self.master_df = pd.DataFrame()

            if JOB_SUMMARY_PATH.exists():
                self.job_summary_df = pd.read_csv(JOB_SUMMARY_PATH, encoding="utf-8-sig")
            else:
                self.job_summary_df = pd.DataFrame()

            if MAJOR_JOB_MAPPING_PATH.exists():
                self.mapping_df = pd.read_csv(MAJOR_JOB_MAPPING_PATH, encoding="utf-8-sig", dtype=str)
            else:
                self.mapping_df = pd.DataFrame()

            if JOB_SKILLS_PATH.exists():
                with open(JOB_SKILLS_PATH, "r", encoding="utf-8") as f:
                    self.skills_lookup = json.load(f)
            else:
                self.skills_lookup = {}

            logging.info("RAGService: Khởi tạo kho tri thức hoàn tất.")
        except Exception as e:
            logging.error(f"RAGService: Lỗi tải dữ liệu kho tri thức: {e}")

    def retrieve_context(
        self,
        major_name: str,
        school_code: Optional[str] = None,
        major_code: Optional[str] = None,
        combination: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Truy xuất dữ kiện có cấu trúc cho ngành học và trường cụ thể.
        Trả về dictionary gồm:
        - metadata: ngành, trường, nhóm ngành
        - admission_data: điểm chuẩn 2024, lịch sử 2021-2023, xu hướng, độ ổn định
        - labor_market: nhóm nghề liên quan, mức lương tham khảo, nhu cầu tuyển dụng, số tin tuyển dụng
        - skills: kỹ năng chuyên môn và kỹ năng mềm cốt lõi
        - formatted_context: Chuỗi văn bản dẫn chứng dùng để tiêm trực tiếp vào LLM prompt
        """
        norm_query = normalize_str(major_name)
        school_clean = str(school_code).strip().upper() if school_code else ""
        major_code_clean = str(major_code).strip().upper() if major_code else ""
        combo_clean = str(combination).strip().upper() if combination else ""

        # 1. Tìm phương án tuyển sinh trong master_admission (Áp dụng phép giao chặt chẽ - Strict Conjunction)
        matched_rows = pd.DataFrame()
        if self.master_df is not None and not self.master_df.empty:
            df = self.master_df.copy()

            # Lọc theo trường nếu có
            if school_clean:
                df = df[df["university_admission_code"].astype(str).str.upper() == school_clean]

            # Lọc theo mã ngành nếu có
            if major_code_clean:
                df = df[df["major_code"].astype(str).str.upper() == major_code_clean]

            # Lọc theo tổ hợp nếu có
            if combo_clean:
                df = df[df["subject_combination"].astype(str).str.upper() == combo_clean]

            # Khớp theo tên ngành nếu có
            if norm_query and not df.empty:
                name_mask = df["major_name"].apply(
                    lambda x: norm_query in normalize_str(str(x)) or normalize_str(str(x)) in norm_query
                )
                df = df[name_mask]

            matched_rows = df

        # NẾU KHÔNG TÌM THẤY: Fail-closed, báo rõ not_found, TUYỆT ĐỐI không lấy dữ liệu trường khác
        if matched_rows.empty:
            return {
                "found": False,
                "metadata": {
                    "major_name": major_name,
                    "major_code": major_code_clean,
                    "school_name": "",
                    "school_code": school_clean,
                    "major_group": "",
                },
                "admission_data": {
                    "cutoff_2024": None,
                    "cutoff_2023": None,
                    "cutoff_2022": None,
                    "cutoff_2021": None,
                    "cutoff_trend": "Không đủ dữ liệu",
                    "history_ambiguous": False,
                },
                "labor_market": {
                    "job_category": "",
                    "demand_level": "Chưa xác định",
                    "posting_count": 0,
                    "average_salary_million_vnd": 0.0,
                    "median_salary_million_vnd": 0.0,
                    "average_experience_months": 0.0,
                },
                "skills": {
                    "technical_skills": [],
                    "soft_skills": [],
                },
                "formatted_context": (
                    f"CẢNH BÁO DẪN CHỨNG: Không tìm thấy dữ liệu tuyển sinh khớp với tiêu chí "
                    f"(mã trường '{school_code or 'N/A'}', mã ngành '{major_code or 'N/A'}', tên ngành '{major_name}'). "
                    f"Tuyệt đối không sử dụng dữ liệu của cơ sở đào tạo khác để thay thế."
                ),
            }

        # Lấy dòng đại diện chính xác
        target_row = matched_rows.iloc[0]

        # 2. Trích xuất thông tin tuyển sinh & lịch sử điểm
        actual_major_name = str(target_row.get("major_name", major_name))
        actual_major_code = str(target_row.get("major_code", major_code or ""))
        actual_school_code = str(target_row.get("university_admission_code", school_code or ""))
        actual_school_name = str(target_row.get("university_name", ""))
        major_group = str(target_row.get("major_group_name", "Chưa phân loại"))
        cutoff_2024 = target_row.get("cutoff_score_30", np.nan)
        if pd.isna(cutoff_2024):
            cutoff_2024 = target_row.get("cutoff_score", np.nan)

        c21 = target_row.get("cutoff_2021", np.nan)
        c22 = target_row.get("cutoff_2022", np.nan)
        c23 = target_row.get("cutoff_2023", np.nan)
        c24 = target_row.get("cutoff_2024", np.nan)
        cutoff_trend = str(target_row.get("cutoff_trend", "Không đủ dữ liệu"))
        history_ambiguous = str(target_row.get("history_ambiguous", "False")).lower() == "true"

        # 3. Trích xuất thông tin thị trường việc làm từ VietJobs
        job_category = str(target_row.get("job_category", "")).strip()
        if not job_category or job_category in ["nan", "None", "nhóm_nghề_khác"]:
            # Tra cứu fallback từ mapping_df
            if self.mapping_df is not None and not self.mapping_df.empty:
                map_match = self.mapping_df[
                    self.mapping_df["major_code"].astype(str).str.strip() == actual_major_code
                ]
                if not map_match.empty:
                    job_category = str(map_match.iloc[0].get("job_category", "")).strip()

        # Dữ liệu thị trường theo nhóm nghề
        posting_count = 0
        avg_salary = 0.0
        median_salary = 0.0
        avg_exp_months = 0.0
        demand_level = "Chưa xác định"

        if job_category and self.job_summary_df is not None and not self.job_summary_df.empty:
            cat_row = self.job_summary_df[self.job_summary_df["job_category"] == job_category]
            if not cat_row.empty:
                r = cat_row.iloc[0]
                posting_count = int(r.get("posting_count", 0))
                avg_salary = round(float(r.get("average_salary_million_vnd", 0.0)), 1)
                median_salary = round(float(r.get("median_salary_million_vnd", 0.0)), 1)
                avg_exp_months = round(float(r.get("average_experience_months", 0.0)), 1)

                if posting_count >= 5000:
                    demand_level = "Rất cao"
                elif posting_count >= 3000:
                    demand_level = "Cao"
                elif posting_count >= 1500:
                    demand_level = "Trung bình"
                elif posting_count > 0:
                    demand_level = "Ổn định"

        # 4. Trích xuất kỹ năng liên quan
        tech_skills = []
        soft_skills = []
        if job_category in self.skills_lookup:
            tech_skills = self.skills_lookup[job_category].get("top_technical_skills", [])[:6]
            soft_skills = self.skills_lookup[job_category].get("top_soft_skills", [])[:4]

        # 5. Xây dựng formatted_context làm căn cứ văn bản cho LLM
        history_desc_parts = []
        if pd.notna(c21):
            history_desc_parts.append(f"2021: {c21:.2f}")
        if pd.notna(c22):
            history_desc_parts.append(f"2022: {c22:.2f}")
        if pd.notna(c23):
            history_desc_parts.append(f"2023: {c23:.2f}")
        if pd.notna(c24):
            history_desc_parts.append(f"2024: {c24:.2f}")

        history_str = ", ".join(history_desc_parts) if history_desc_parts else "Chưa có đủ số liệu liên tục các năm"
        if history_ambiguous:
            history_str += " (Lưu ý: Năm trước có nhiều phân hệ tuyển sinh với các mức điểm khác nhau, cần kiểm tra đề án chi tiết)"

        formatted_lines = [
            f"- Ngành đào tạo: {actual_major_name} (Mã ngành: {actual_major_code or 'N/A'})",
            f"- Nhóm ngành: {major_group}",
        ]
        if actual_school_name or actual_school_code:
            formatted_lines.append(f"- Cơ sở đào tạo: {actual_school_name} (Mã trường: {actual_school_code})")

        if pd.notna(cutoff_2024):
            formatted_lines.append(f"- Điểm chuẩn chuẩn hóa năm 2024 (thang 30): {cutoff_2024:.2f}")
        formatted_lines.append(f"- Lịch sử điểm chuẩn: {history_str}")
        formatted_lines.append(f"- Xu hướng điểm chuẩn gần đây: {cutoff_trend}")

        if job_category and job_category != "nan":
            formatted_lines.append(f"- Nhóm nghề đầu ra liên quan (VietJobs): {job_category.replace('_', ' ').title()}")
            formatted_lines.append(f"- Nhu cầu tuyển dụng: {demand_level} (Tổng {posting_count} tin tuyển dụng ghi nhận)")
            if avg_salary > 0:
                formatted_lines.append(f"- Mức lương tham khảo thị trường: Trung bình khoảng {avg_salary} triệu VNĐ/tháng (Trung vị: {median_salary} triệu VNĐ/tháng)")
            if tech_skills:
                formatted_lines.append(f"- Kỹ năng chuyên môn thị trường yêu cầu phổ biến: {', '.join(tech_skills)}")
            if soft_skills:
                formatted_lines.append(f"- Kỹ năng mềm được nhà tuyển dụng chú trọng: {', '.join(soft_skills)}")
        else:
            formatted_lines.append("- Nhóm nghề đầu ra: Chưa có ánh xạ chính thức với khảo sát tuyển dụng VietJobs.")

        formatted_context = "\n".join(formatted_lines)

        return {
            "found": True,
            "metadata": {
                "major_name": actual_major_name,
                "major_code": actual_major_code,
                "school_name": actual_school_name,
                "school_code": actual_school_code,
                "major_group": major_group,
            },
            "admission_data": {
                "cutoff_2024": float(cutoff_2024) if pd.notna(cutoff_2024) else None,
                "cutoff_2023": float(c23) if pd.notna(c23) else None,
                "cutoff_2022": float(c22) if pd.notna(c22) else None,
                "cutoff_2021": float(c21) if pd.notna(c21) else None,
                "cutoff_trend": cutoff_trend,
                "history_ambiguous": history_ambiguous,
            },
            "labor_market": {
                "job_category": job_category,
                "demand_level": demand_level,
                "posting_count": posting_count,
                "average_salary_million_vnd": avg_salary,
                "median_salary_million_vnd": median_salary,
                "average_experience_months": avg_exp_months,
            },
            "skills": {
                "technical_skills": tech_skills,
                "soft_skills": soft_skills,
            },
            "formatted_context": formatted_context,
        }


rag_service = RAGService()
