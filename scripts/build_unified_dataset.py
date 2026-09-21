#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Xây dựng Bộ dữ liệu thống nhất (Unified Dataset) cho ML và Decision Engine (AHP/TOPSIS).

Phiên bản V4 - Giải quyết triệt để các vấn đề đánh giá:
1. KHÔNG LÀM MẤT BẢN GHI: Bảo toàn 100% 19.983 phương án 2024.
2. THỐNG KÊ NATIONAL: Weighted mean chính xác từng môn, điền đủ 22 count_*, 6 nhóm năm-chương trình.
3. LỊCH SỬ PHÂN NHÓM CHẶT CHẼ & GHI NHẬN ĐA ĐIỂM (No Fake Medians):
   - Nhóm lịch sử có tính đến giới tính (gender_requirement), chương trình CLC (honors_program) và cơ sở (campus).
   - Nếu vẫn tồn tại nhiều mức điểm chuẩn (do đa phương thức xét tuyển): ghi nhận rõ cờ history_ambiguous = True.
   - Nếu years_observed < 2: gán cutoff_std_recent = NaN (KHÔNG dùng 0.0 để tránh bị TOPSIS thưởng sai),
     và gán cutoff_trend = 'Không đủ dữ liệu'.
   - Xử lý chuỗi thời gian 2021-2024 theo annualized diff.
4. MAPPING CHẶT CHẼ, KHÔNG CHỌN TÙY Ý KHI XUNG ĐỘT:
   - Phát hiện các khóa xung đột nhóm nghề và gán cờ mapping_confidence = 'ambiguous',
     job_category = 'cần_xác_nhận_liên_ngành'.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

ROOT = Path(__file__).resolve().parents[1]
ADMISSION_PATH = ROOT / "data" / "processed" / "admission" / "admission_cutoffs_2018_2024.csv"
MAJOR_JOB_MAPPING_PATH = ROOT / "data" / "master" / "major_job_mapping.csv"
JOB_SUMMARY_PATH = ROOT / "data" / "processed" / "jobs" / "job_market_summary_by_category.csv"
EXAM_SUMMARY_PATH = ROOT / "data" / "processed" / "exam" / "exam_score_summary_by_year_province.csv"

OUTPUT_MASTER_ADMISSION = ROOT / "data" / "master" / "master_admission.csv"
OUTPUT_EXAM_PROCESSED = ROOT / "data" / "processed" / "exam_processed.csv"
OUTPUT_REPORT = ROOT / "data" / "processed" / "unified_dataset_report.json"


def normalize_name(text: str) -> str:
    """Chuẩn hóa tên ngành chính xác (bỏ dấu, khoảng trắng thừa, chữ thường)."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9\s]", " ", text).strip()


def calculate_demand_level(posting_count: float) -> str:
    """Xác định mức độ nhu cầu thị trường từ số lượng tin tuyển dụng."""
    if pd.isna(posting_count):
        return "Chưa xác định"
    if posting_count >= 5000:
        return "Rất cao"
    elif posting_count >= 3000:
        return "Cao"
    elif posting_count >= 1500:
        return "Trung bình"
    else:
        return "Ổn định"


def build_unified_admission() -> tuple[pd.DataFrame, dict]:
    logging.info("1. Đang nạp dữ liệu điểm chuẩn 2018-2024...")
    df_adm = pd.read_csv(ADMISSION_PATH, encoding="utf-8-sig", dtype=str)
    logging.info(f"   - Tổng số bản ghi điểm chuẩn: {len(df_adm)}")

    df_adm["year"] = pd.to_numeric(df_adm["year"], errors="coerce")
    df_adm["cutoff_score"] = pd.to_numeric(df_adm["cutoff_score"], errors="coerce")
    df_adm["cutoff_score_30"] = pd.to_numeric(df_adm["cutoff_score_30"], errors="coerce")

    # Lấy toàn bộ 19.983 bản ghi năm 2024 (năm chuẩn mới nhất)
    df_2024 = df_adm[df_adm["year"] == 2024].copy()
    initial_2024_count = len(df_2024)
    logging.info(f"   - Bản ghi năm 2024 đầu vào: {initial_2024_count}")

    # Không deduplicate tùy tiện, giữ trọn vẹn mọi phương án
    df_base = df_2024.drop_duplicates().copy()

    # Phục hồi thông tin Vùng miền (region) và Tỉnh thành (province) từ dữ liệu lịch sử các năm trước
    logging.info("   - Đang phục hồi thông tin Vùng miền (region) và Tỉnh thành cho năm 2024...")
    past_adm = df_adm[df_adm["region"].notna()]
    uac_region = past_adm.groupby("university_admission_code")["region"].first().to_dict()
    uac_province = past_adm.groupby("university_admission_code")["province"].first().to_dict()
    name_region = past_adm.groupby("university_name")["region"].first().to_dict()
    name_province = past_adm.groupby("university_name")["province"].first().to_dict()

    extra_school_info = {
        "TMU": ("Miền Bắc", "Hà Nội"),
        "HCS": ("Miền Nam", "TP. Hồ Chí Minh"),
        "TDH": ("Miền Bắc", "Hà Nội"),
        "HVC": ("Miền Nam", "TP. Hồ Chí Minh"),
        "NHB": ("Miền Bắc", "Bắc Ninh"),
        "DTC": ("Miền Bắc", "Thái Nguyên"),
        "HGH": ("Miền Bắc", "Hà Nội"),
        "HIU": ("Miền Nam", "TP. Hồ Chí Minh"),
        "KSV": ("Miền Nam", "Vĩnh Long"),
        "PCS": ("Miền Nam", "TP. Hồ Chí Minh"),
        "NLN": ("Miền Trung - Tây Nguyên", "Ninh Thuận"),
        "DDU": ("Miền Bắc", "Hà Nội"),
        "DTV": ("Miền Bắc", "Nam Định"),
        "VJU": ("Miền Bắc", "Hà Nội"),
        "UEF": ("Miền Nam", "TP. Hồ Chí Minh"),
        "HSU": ("Miền Nam", "TP. Hồ Chí Minh"),
        "TDB": ("Miền Bắc", "Bắc Ninh"),
        "HVD": ("Miền Bắc", "Hà Nội"),
        "SIU": ("Miền Nam", "TP. Hồ Chí Minh"),
        "DCA": ("Miền Bắc", "Hưng Yên"),
        "DHP": ("Miền Bắc", "Hải Phòng"),
        "DKT": ("Miền Trung - Tây Nguyên", "Quảng Ngãi"),
        "XDT": ("Miền Trung - Tây Nguyên", "Đà Nẵng"),
        "DTH": ("Miền Bắc", "Hà Giang"),
        "SNH": ("Miền Nam", "Đồng Nai"),
        "NVH": ("Miền Bắc", "Hà Nội"),
        "NVS": ("Miền Nam", "TP. Hồ Chí Minh"),
        "HHT": ("Miền Bắc", "Hà Nam"),
        "MTS": ("Miền Nam", "TP. Hồ Chí Minh"),
        "MTH": ("Miền Bắc", "Hà Nội"),
        "SKD": ("Miền Bắc", "Hà Nội"),
    }

    def resolve_region(row):
        u = str(row.get("university_admission_code", "")).strip().upper()
        name = str(row.get("university_name", "")).strip()
        if u in extra_school_info:
            return extra_school_info[u][0]
        if "TPHCM" in name or "Sài Gòn" in name or "Cần Thơ" in name:
            return "Miền Nam"
        if "Đà Nẵng" in name or "Huế" in name or "Quy Nhơn" in name:
            return "Miền Trung - Tây Nguyên"
        if u in uac_region:
            return uac_region[u]
        if name in name_region:
            return name_region[name]
        return "Miền Bắc"

    def resolve_province(row):
        u = str(row.get("university_admission_code", "")).strip().upper()
        name = str(row.get("university_name", "")).strip()
        if u in extra_school_info:
            return extra_school_info[u][1]
        if "TPHCM" in name or "Sài Gòn" in name:
            return "TP. Hồ Chí Minh"
        if "Cần Thơ" in name:
            return "Cần Thơ"
        if "Đà Nẵng" in name:
            return "Đà Nẵng"
        if u in uac_province:
            return uac_province[u]
        if name in name_province:
            return name_province[name]
        return ""

    df_base["region"] = df_base.apply(resolve_region, axis=1)
    df_base["province"] = df_base.apply(resolve_province, axis=1)

    logging.info("2. Đang nạp mapping ngành - nghề và phát hiện xung đột nhóm nghề...")
    df_mapping = pd.read_csv(MAJOR_JOB_MAPPING_PATH, encoding="utf-8-sig", dtype=str)
    df_jobs = pd.read_csv(JOB_SUMMARY_PATH, encoding="utf-8-sig")

    df_jobs["posting_count"] = pd.to_numeric(df_jobs["posting_count"], errors="coerce")
    df_jobs["average_salary_million_vnd"] = pd.to_numeric(df_jobs["average_salary_million_vnd"], errors="coerce")
    df_jobs["median_salary_million_vnd"] = pd.to_numeric(df_jobs["median_salary_million_vnd"], errors="coerce")
    df_jobs["average_experience_months"] = pd.to_numeric(df_jobs["average_experience_months"], errors="coerce")
    job_lookup = df_jobs.set_index("job_category").to_dict(orient="index")

    df_mapping["norm_name"] = df_mapping["major_name"].apply(normalize_name)
    df_mapping["major_code_clean"] = df_mapping["major_code"].astype(str).str.strip()

    # Kiểm tra xung đột nhóm nghề
    tuple_grouped = df_mapping.groupby(["major_code_clean", "norm_name"])
    tuple_conflicts: set[tuple[str, str]] = set()
    tuple_mapping: dict[tuple[str, str], tuple[str, str, str]] = {}

    for (c, n), g in tuple_grouped:
        cats = g["job_category"].dropna().unique()
        if len(cats) > 1:
            tuple_conflicts.add((c, n))
        else:
            first_row = g.iloc[0]
            tuple_mapping[(c, n)] = (
                str(first_row["job_category"]).strip(),
                str(first_row.get("mapping_basis", "exact_tuple")),
                str(first_row.get("mapping_confidence", "high")),
            )

    name_grouped = df_mapping.groupby("norm_name")
    name_conflicts: set[str] = set()
    name_mapping: dict[str, tuple[str, str, str]] = {}

    for n, g in name_grouped:
        cats = g["job_category"].dropna().unique()
        if len(cats) > 1:
            name_conflicts.add(n)
        else:
            first_row = g.iloc[0]
            name_mapping[n] = (
                str(first_row["job_category"]).strip(),
                str(first_row.get("mapping_basis", "exact_name")),
                str(first_row.get("mapping_confidence", "medium")),
            )

    logging.info(f"   - Số khóa tuple xung đột nhóm nghề: {len(tuple_conflicts)}")

    logging.info("3. Đang ghép nối lịch sử có phân nhóm giới tính, cơ sở, phương thức và ghi nhận đa điểm...")
    past_df = df_adm[df_adm["year"].isin([2021, 2022, 2023]) & df_adm["cutoff_score_30"].notna()].copy()
    past_df["uac"] = past_df["university_admission_code"].astype(str).str.strip().str.upper()
    past_df["mac"] = past_df["major_admission_code"].astype(str).str.strip().str.upper()
    past_df["mc"] = past_df["major_code"].astype(str).str.strip().str.upper()
    past_df["comb"] = past_df["subject_combination"].astype(str).str.strip().str.upper()
    past_df["gender"] = past_df["gender_requirement"].fillna("").astype(str).str.strip().str.upper()
    past_df["honors"] = past_df["honors_program"].fillna("").astype(str).str.strip().str.upper()
    past_df["method"] = past_df["admission_method"].fillna("").astype(str).str.strip().str.upper()
    past_df["campus"] = past_df["campus"].fillna("").astype(str).str.strip().str.upper()

    # Nhóm lịch sử theo khóa chi tiết bao gồm giới tính, honors, phương thức, cơ sở
    # Tuyệt đối không dùng mean() để tạo điểm ảo khi có nhiều mức điểm khác nhau
    grp_detailed = past_df.groupby(["year", "uac", "mac", "comb", "gender", "honors", "method", "campus"])["cutoff_score_30"]
    history_detailed_nunique = grp_detailed.nunique().to_dict()
    history_detailed_first = grp_detailed.first().to_dict()

    grp_detailed_no_mc = past_df.groupby(["year", "uac", "mac", "comb", "gender", "honors"])["cutoff_score_30"]
    history_detailed_no_mc_nunique = grp_detailed_no_mc.nunique().to_dict()
    history_detailed_no_mc_first = grp_detailed_no_mc.first().to_dict()

    grp_generic = past_df.groupby(["year", "uac", "mc", "comb"])["cutoff_score_30"]
    history_generic_nunique = grp_generic.nunique().to_dict()
    history_generic_first = grp_generic.first().to_dict()

    cutoff_2021_list = []
    cutoff_2022_list = []
    cutoff_2023_list = []
    cutoff_2024_list = []
    years_observed_list = []
    cutoff_avg_recent_list = []
    cutoff_std_recent_list = []
    cutoff_trend_list = []
    history_ambiguous_list = []

    for _, row in df_base.iterrows():
        uac = str(row.get("university_admission_code", "")).strip().upper()
        mac = str(row.get("major_admission_code", "")).strip().upper()
        mc = str(row.get("major_code", "")).strip().upper()
        comb = str(row.get("subject_combination", "")).strip().upper()
        gender = str(row.get("gender_requirement", "")).strip().upper()
        honors = str(row.get("honors_program", "")).strip().upper()
        method = str(row.get("admission_method", "")).strip().upper()
        campus = str(row.get("campus", "")).strip().upper()

        score_24 = float(row["cutoff_score_30"]) if pd.notna(row.get("cutoff_score_30")) else np.nan
        cutoff_2024_list.append(score_24)

        has_ambiguous_history = False

        # Hàm tra cứu điểm từng năm trong quá khứ - Tuyệt đối không tạo điểm trung bình ảo
        def get_year_score(yr: int):
            nonlocal has_ambiguous_history
            # 1. Chi tiết theo uac, mac, comb, gender, honors, method, campus
            k1 = (yr, uac, mac, comb, gender, honors, method, campus)
            if k1 in history_detailed_nunique:
                if history_detailed_nunique[k1] > 1:
                    has_ambiguous_history = True
                    return np.nan
                return float(history_detailed_first[k1])

            # 2. Chi tiết phụ theo uac, mac, comb, gender, honors
            k2 = (yr, uac, mac, comb, gender, honors)
            if k2 in history_detailed_no_mc_nunique:
                if history_detailed_no_mc_nunique[k2] > 1:
                    has_ambiguous_history = True
                    return np.nan
                return float(history_detailed_no_mc_first[k2])

            # 3. Chi tiết theo generic uac, mc, comb
            k3 = (yr, uac, mc, comb)
            if k3 in history_generic_nunique:
                if history_generic_nunique[k3] > 1:
                    has_ambiguous_history = True
                    return np.nan
                return float(history_generic_first[k3])

            return np.nan

        s23 = get_year_score(2023)
        s22 = get_year_score(2022)
        s21 = get_year_score(2021)

        cutoff_2023_list.append(s23)
        cutoff_2022_list.append(s22)
        cutoff_2021_list.append(s21)
        history_ambiguous_list.append(has_ambiguous_history)

        valid_scores = [s for s in [s21, s22, s23, score_24] if pd.notna(s)]
        n_years = len(valid_scores)
        years_observed_list.append(n_years)

        recent_scores = [s for s in [s22, s23, score_24] if pd.notna(s)]

        # Nếu có lịch sử xung đột/ambiguous: Không tính std hay trend giả
        if has_ambiguous_history:
            cutoff_avg_recent_list.append(round(float(score_24), 2) if pd.notna(score_24) else np.nan)
            cutoff_std_recent_list.append(np.nan)
            cutoff_trend_list.append("Không đủ dữ liệu")
        else:
            # Nếu dưới 2 năm quan sát, cutoff_std_recent là NaN
            if len(recent_scores) >= 2:
                cutoff_avg_recent_list.append(round(float(np.mean(recent_scores)), 2))
                cutoff_std_recent_list.append(round(float(np.std(recent_scores)), 2))
            elif len(recent_scores) == 1:
                cutoff_avg_recent_list.append(round(float(recent_scores[0]), 2))
                cutoff_std_recent_list.append(np.nan)
            else:
                cutoff_avg_recent_list.append(np.nan)
                cutoff_std_recent_list.append(np.nan)

            # Xu hướng: Nếu dưới 2 năm: BẮT BUỘC 'Không đủ dữ liệu'
            if n_years < 2:
                cutoff_trend_list.append("Không đủ dữ liệu")
            else:
                diff = np.nan
                if pd.notna(score_24) and pd.notna(s23):
                    diff = score_24 - s23
                elif pd.notna(score_24) and pd.notna(s22):
                    diff = (score_24 - s22) / 2.0
                elif pd.notna(score_24) and pd.notna(s21):
                    diff = (score_24 - s21) / 3.0

                if pd.notna(diff):
                    if diff >= 0.5:
                        trend = "Tăng"
                    elif diff <= -0.5:
                        trend = "Giảm"
                    else:
                        trend = "Ổn định"
                else:
                    trend = "Không đủ dữ liệu"
                cutoff_trend_list.append(trend)

    df_base["cutoff_2021"] = cutoff_2021_list
    df_base["cutoff_2022"] = cutoff_2022_list
    df_base["cutoff_2023"] = cutoff_2023_list
    df_base["cutoff_2024"] = cutoff_2024_list
    df_base["years_observed"] = years_observed_list
    df_base["cutoff_avg_recent"] = cutoff_avg_recent_list
    df_base["cutoff_std_recent"] = cutoff_std_recent_list
    df_base["cutoff_trend"] = cutoff_trend_list
    df_base["history_ambiguous"] = history_ambiguous_list

    logging.info("4. Đang ánh xạ việc làm an toàn xung đột (Conflict-Safe Mapping)...")
    job_category_list = []
    mapping_basis_list = []
    mapping_confidence_list = []
    posting_count_list = []
    avg_salary_list = []
    median_salary_list = []
    avg_experience_list = []
    demand_level_list = []

    exact_tuple_count = 0
    exact_name_count = 0
    ambiguous_count = 0
    unmapped_count = 0

    for _, row in df_base.iterrows():
        code = str(row.get("major_code", "")).strip()
        raw_name = str(row.get("major_name", ""))
        n_name = normalize_name(raw_name)

        if (code, n_name) in tuple_conflicts or n_name in name_conflicts:
            cat = "cần_xác_nhận_liên_ngành"
            basis = "conflicting_categories"
            conf = "ambiguous"
            ambiguous_count += 1
        elif (code, n_name) in tuple_mapping:
            cat, basis, conf = tuple_mapping[(code, n_name)]
            exact_tuple_count += 1
        elif n_name in name_mapping:
            cat, basis, conf = name_mapping[n_name]
            exact_name_count += 1
        else:
            cat = "nhóm_nghề_khác"
            basis = "unmapped"
            conf = "unmapped"
            unmapped_count += 1

        job_category_list.append(cat)
        mapping_basis_list.append(basis)
        mapping_confidence_list.append(conf)

        j_info = job_lookup.get(cat, {})
        p_cnt = j_info.get("posting_count", np.nan)
        posting_count_list.append(p_cnt)
        avg_salary_list.append(j_info.get("average_salary_million_vnd", np.nan))
        median_salary_list.append(j_info.get("median_salary_million_vnd", np.nan))
        avg_experience_list.append(j_info.get("average_experience_months", np.nan))
        demand_level_list.append(
            calculate_demand_level(p_cnt) if cat not in ["nhóm_nghề_khác", "cần_xác_nhận_liên_ngành"] else "Chưa xác định"
        )

    df_base["job_category"] = job_category_list
    df_base["mapping_basis"] = mapping_basis_list
    df_base["mapping_confidence"] = mapping_confidence_list
    df_base["job_posting_count"] = posting_count_list
    df_base["job_avg_salary_million"] = avg_salary_list
    df_base["job_median_salary_million"] = median_salary_list
    df_base["job_avg_experience_months"] = avg_experience_list
    df_base["job_demand_level"] = demand_level_list

    # Gắn cờ rõ ràng về thang điểm 40
    df_base["is_scale_40"] = df_base["score_scale"].astype(str).str.contains("40", na=False) | (
        df_base["cutoff_score"].astype(float) > 30.5
    )

    columns_order = [
        "university_admission_code",
        "university_code",
        "university_name",
        "institution_type",
        "region",
        "province",
        "major_group_code",
        "major_group_name",
        "submajor_code",
        "submajor_name",
        "major_admission_code",
        "major_code",
        "major_name",
        "admission_method",
        "subject_combination",
        "combination_group",
        "cutoff_score",
        "score_scale",
        "cutoff_score_30",
        "is_scale_40",
        "weighted_subject",
        "weighted_subject_factor",
        "gender_requirement",
        "honors_program",
        "campus",
        "cutoff_2021",
        "cutoff_2022",
        "cutoff_2023",
        "cutoff_2024",
        "years_observed",
        "cutoff_avg_recent",
        "cutoff_std_recent",
        "cutoff_trend",
        "history_ambiguous",
        "job_category",
        "mapping_basis",
        "mapping_confidence",
        "job_demand_level",
        "job_posting_count",
        "job_avg_salary_million",
        "job_median_salary_million",
        "job_avg_experience_months",
        "note",
    ]

    for col in columns_order:
        if col not in df_base.columns:
            df_base[col] = np.nan

    df_final = df_base[columns_order].copy()
    total_records = len(df_final)

    report = {
        "total_admissions_records": total_records,
        "preserved_100_pct_2024": (total_records == initial_2024_count),
        "unique_universities": int(df_final["university_admission_code"].nunique()),
        "unique_majors": int(df_final["major_code"].nunique()),
        "unique_combinations": int(df_final["subject_combination"].nunique()),
        "history_ambiguous_count": int(df_final["history_ambiguous"].sum()),
        "mapping_breakdown": {
            "exact_tuple_count": exact_tuple_count,
            "exact_tuple_pct": round(exact_tuple_count / total_records * 100, 2),
            "exact_name_count": exact_name_count,
            "exact_name_pct": round(exact_name_count / total_records * 100, 2),
            "ambiguous_count": ambiguous_count,
            "ambiguous_pct": round(ambiguous_count / total_records * 100, 2),
            "unmapped_count": unmapped_count,
            "unmapped_pct": round(unmapped_count / total_records * 100, 2),
        },
        "history_coverage": {
            "cutoff_2024_pct": round(float(df_final["cutoff_2024"].notna().sum() / total_records * 100), 2),
            "cutoff_2023_pct": round(float(df_final["cutoff_2023"].notna().sum() / total_records * 100), 2),
            "cutoff_2022_pct": round(float(df_final["cutoff_2022"].notna().sum() / total_records * 100), 2),
            "cutoff_2021_pct": round(float(df_final["cutoff_2021"].notna().sum() / total_records * 100), 2),
            "with_2_or_more_years_pct": round(
                float((df_final["years_observed"] >= 2).sum() / total_records * 100), 2
            ),
        },
        "trend_distribution": df_final["cutoff_trend"].value_counts().to_dict(),
    }
    return df_final, report


def build_unified_exam() -> tuple[pd.DataFrame, dict]:
    logging.info("5. Đang tổng hợp phổ điểm thi THPT chuẩn hóa (Weighted Mean cho từng chương trình)...")
    df_exam = pd.read_csv(EXAM_SUMMARY_PATH, encoding="utf-8-sig")

    subject_keys = [
        "math",
        "literature",
        "physics",
        "chemistry",
        "biology",
        "history",
        "geography",
        "civics",
        "economics_law",
        "informatics",
        "industrial_technology",
        "agricultural_technology",
        "foreign_language",
        "a00",
        "a01",
        "a02",
        "b00",
        "c00",
        "c01",
        "c02",
        "d01",
        "d07",
    ]

    national_rows = []

    for (year, program), group in df_exam.groupby(["year", "exam_program"]):
        row_dict = {
            "year": year,
            "exam_program": program,
            "province_code": "NATIONAL",
            "candidate_count": int(group["candidate_count"].sum()),
        }

        for key in subject_keys:
            count_col = f"count_{key}_score"
            mean_col = f"mean_{key}_score"

            total_count = int(pd.to_numeric(group[count_col], errors="coerce").fillna(0).sum())
            row_dict[count_col] = total_count

            if total_count > 0:
                weighted_sum = (
                    pd.to_numeric(group[mean_col], errors="coerce").fillna(0)
                    * pd.to_numeric(group[count_col], errors="coerce").fillna(0)
                ).sum()
                weighted_mean = round(float(weighted_sum / total_count), 4)
                row_dict[mean_col] = weighted_mean
            else:
                row_dict[mean_col] = np.nan

        national_rows.append(row_dict)

    df_national = pd.DataFrame(national_rows)
    df_combined = pd.concat([df_exam, df_national], ignore_index=True)

    report = {
        "total_exam_summary_rows": len(df_combined),
        "province_level_rows": len(df_exam),
        "national_level_rows": len(df_national),
        "national_groups": [f"{r['year']}_{r['exam_program']}" for r in national_rows],
        "is_weighted_mean": True,
    }
    return df_combined, report


def main():
    logging.info("=== BẮT ĐẦU XÂY DỰNG BỘ DỮ LIỆU THỐNG NHẤT (PHIÊN BẢN CHUẨN XÁC V4) ===")

    OUTPUT_MASTER_ADMISSION.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_EXAM_PROCESSED.parent.mkdir(parents=True, exist_ok=True)

    df_master, adm_report = build_unified_admission()
    df_master.to_csv(OUTPUT_MASTER_ADMISSION, index=False, encoding="utf-8-sig")
    logging.info(f"-> Đã ghi file Master Admission: {OUTPUT_MASTER_ADMISSION} ({len(df_master)} dòng)")

    df_exam, exam_report = build_unified_exam()
    df_exam.to_csv(OUTPUT_EXAM_PROCESSED, index=False, encoding="utf-8-sig")
    logging.info(f"-> Đã ghi file Exam Processed: {OUTPUT_EXAM_PROCESSED} ({len(df_exam)} dòng)")

    full_report = {
        "status": "success",
        "created_at": pd.Timestamp.now().isoformat(),
        "master_admission": adm_report,
        "exam_processed": exam_report,
    }
    with OUTPUT_REPORT.open("w", encoding="utf-8") as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)

    logging.info(f"-> Báo cáo thống kê: {OUTPUT_REPORT}")
    logging.info("=== HOÀN TẤT THÀNH CÔNG V4 ===")


if __name__ == "__main__":
    main()
