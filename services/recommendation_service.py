import logging
import math
import unicodedata
import numpy as np
import pandas as pd
from services.data_repository import data_repo

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def remove_accents(input_str: str) -> str:
    if not input_str:
        return ""
    nfkd = unicodedata.normalize("NFKD", input_str)
    unaccented = "".join(c for c in nfkd if not unicodedata.combining(c))
    return unaccented.replace("đ", "d").replace("Đ", "D").casefold()


COMBINATIONS = {
    "A00": ("toan", "vatly", "hoahoc"),
    "A01": ("toan", "vatly", "ngoaingu"),
    "A02": ("toan", "vatly", "sinhhoc"),
    "B00": ("toan", "hoahoc", "sinhhoc"),
    "B08": ("toan", "sinhhoc", "ngoaingu"),
    "C00": ("nguvan", "lichsu", "dialy"),
    "C01": ("nguvan", "toan", "vatly"),
    "C02": ("nguvan", "toan", "hoahoc"),
    "D01": ("toan", "nguvan", "ngoaingu"),
    "D07": ("toan", "hoahoc", "ngoaingu"),
}

SUBJECT_NAMES = {
    "toan": "Toán",
    "vatly": "Vật lý",
    "hoahoc": "Hóa học",
    "sinhhoc": "Sinh học",
    "nguvan": "Ngữ văn",
    "lichsu": "Lịch sử",
    "dialy": "Địa lý",
    "ngoaingu": "Ngoại ngữ",
    "gdcd": "GDCD",
    "tinhoc": "Tin học",
}

SUBJECT_EXAM_COLUMN_MAP = {
    "toan": "math",
    "vatly": "physics",
    "hoahoc": "chemistry",
    "sinhhoc": "biology",
    "nguvan": "literature",
    "lichsu": "history",
    "dialy": "geography",
    "gdcd": "civics",
    "ngoaingu": "foreign_language",
    "tinhoc": "informatics",
}


class RecommendationEngine:
    def __init__(self):
        self.master_data = data_repo.get_master_data()
        self.exam_data = data_repo.get_exam_data()

    def process_recommendation(self, user_payload: dict) -> dict:
        """Xử lý hồ sơ: kiểm tra tổ hợp bắt buộc, chạy thuật toán TOPSIS đa tiêu chí, tính độ lệch phổ điểm."""
        combination = str(user_payload.get("combination", "A00")).strip().upper()
        raw_scores = user_payload.get("scores", {})
        interest = str(user_payload.get("interest", "")).strip()
        preferences = user_payload.get("preferences", {}) or {}
        priorities = user_payload.get("priorities", {}) or {}

        required_subjects = COMBINATIONS.get(combination)
        if not required_subjects:
            raise ValueError(f"Tổ hợp {combination} chưa được hỗ trợ.")

        # 1. KIỂM TRA & CHỈ CỘNG 3 MÔN CỦA TỔ HỢP (Loại bỏ triệt để môn thừa)
        user_scores_float = {}
        missing_subjects = []
        for subj in required_subjects:
            if subj not in raw_scores:
                missing_subjects.append(SUBJECT_NAMES.get(subj, subj))
            else:
                try:
                    val = float(raw_scores[subj])
                    if val < 0 or val > 10:
                        raise ValueError(f"Điểm môn {subj} phải từ 0 đến 10.")
                    user_scores_float[subj] = val
                except (ValueError, TypeError):
                    raise ValueError(f"Điểm môn {subj} không hợp lệ.")

        if missing_subjects:
            raise ValueError(f"Thiếu điểm các môn bắt buộc của tổ hợp {combination}: {', '.join(missing_subjects)}")

        # Chỉ tính tổng 3 môn của tổ hợp
        user_total_score = round(sum(user_scores_float[s] for s in required_subjects), 2)
        logging.info(f"Hồ sơ: Tổ hợp {combination} - Tổng 3 môn: {user_total_score} - Sở thích: '{interest}'")

        # 2. LẤY & LỌC DỮ LIỆU TỪ MASTER ADMISSION
        df = data_repo.get_master_data()
        if df.empty:
            return self._fallback_empty_response(user_total_score, combination)

        matched_df = df[df["subject_combination"].astype(str).str.upper() == combination].copy()

        # TÁCH PHƯƠNG ÁN THANG 40 KHỎI RANKING THANG 30
        matched_df = matched_df[matched_df["is_scale_40"] == False].copy()

        # Lọc theo Nhóm ngành (group) từ giao diện nếu có
        group_filter = str(user_payload.get("group", "")).strip()
        if group_filter:
            norm_grp = remove_accents(group_filter)
            group_mask = matched_df["major_group_name"].apply(
                lambda x: norm_grp in remove_accents(str(x)) or remove_accents(str(x)) in norm_grp
            )
            if group_mask.any():
                matched_df = matched_df[group_mask].copy()
            else:
                matched_df = matched_df.iloc[0:0].copy()

        # Lọc theo Khu vực (region) từ profile nếu có
        region_pref = ""
        if isinstance(preferences, dict) and preferences.get("region"):
            region_pref = str(preferences["region"]).strip()
        elif user_payload.get("region"):
            region_pref = str(user_payload.get("region")).strip()

        if region_pref:
            reg_mask = matched_df["region"].astype(str).str.strip().str.lower() == region_pref.lower()
            if reg_mask.any():
                matched_df = matched_df[reg_mask].copy()

        # Lọc theo sở thích hoặc danh sách interests từ profile
        user_interests = []
        if isinstance(preferences, dict):
            if isinstance(preferences.get("interests"), list):
                user_interests = [str(i).strip() for i in preferences["interests"] if str(i).strip()]
            elif isinstance(preferences.get("interests"), str) and preferences.get("interests"):
                user_interests = [preferences["interests"].strip()]

        search_terms = []
        if interest:
            search_terms.append(interest)
        search_terms.extend(user_interests)

        if search_terms:
            term_masks = []
            for term in search_terms:
                nt = remove_accents(term)
                tm = (
                    matched_df["major_name"].apply(lambda x: nt in remove_accents(str(x)))
                    | matched_df["major_group_name"].apply(lambda x: nt in remove_accents(str(x)))
                    | matched_df["university_name"].apply(lambda x: nt in remove_accents(str(x)))
                )
                term_masks.append(tm)
            combined_mask = pd.concat(term_masks, axis=1).any(axis=1)
            if combined_mask.any():
                matched_df = matched_df[combined_mask].copy()

        if matched_df.empty:
            matched_df = df[
                (df["subject_combination"].astype(str).str.upper() == combination)
                & (df["is_scale_40"] == False)
            ].copy()

        if matched_df.empty:
            return self._fallback_empty_response(user_total_score, combination)

        matched_df["cutoff_numeric"] = pd.to_numeric(matched_df["cutoff_score_30"], errors="coerce")
        matched_df = matched_df.dropna(subset=["cutoff_numeric"])
        matched_df["gap"] = (user_total_score - matched_df["cutoff_numeric"]).round(2)

        # 3. THUẬT TOÁN TOPSIS (Đa tiêu chí có tích hợp Preferences người dùng)
        # Tiêu chí:
        # - C1: Mức độ tương thích điểm số (gap fit)
        # - C2: Mức lương thị trường (salary)
        # - C3: Nhu cầu tuyển dụng (job_demand)
        # - C4: Độ ổn định điểm chuẩn (stability)
        gap_scores = matched_df["gap"].apply(
            lambda g: max(0.1, 10.0 - abs(g - 1.0)) if g >= -2.0 else max(0.01, 10.0 - abs(g) * 2.0)
        ).to_numpy()

        salaries = matched_df["job_avg_salary_million"].fillna(15.0).clip(lower=5.0).to_numpy()
        postings = matched_df["job_posting_count"].fillna(500.0).clip(lower=10.0).to_numpy()

        # KHẮC PHỤC TRIỆT ĐỂ: Nếu thiếu lịch sử quan sát (< 2 năm) hoặc có xung đột, gán stability trung tính 0.5
        years_obs = matched_df["years_observed"].fillna(1).to_numpy()
        stds = matched_df["cutoff_std_recent"].to_numpy()
        is_ambig = (
            matched_df["history_ambiguous"].fillna(False).astype(bool).to_numpy()
            if "history_ambiguous" in matched_df.columns
            else np.zeros(len(matched_df), dtype=bool)
        )
        stabilities = np.where(
            (years_obs >= 2) & pd.notna(stds) & (~is_ambig),
            1.0 / (1.0 + np.nan_to_num(stds, nan=0.5)),
            0.5  # Mức trung tính khi thiếu dữ liệu lịch sử hoặc xung đột
        )

        X = np.column_stack([gap_scores, salaries, postings, stabilities])

        # ĐIỀU CHỈNH TRỌNG SỐ THEO PREFERENCES NGƯỜI DÙNG (Phân biệt chính xác từng tag)
        w_fit = 0.40
        w_sal = 0.25
        w_dem = 0.20
        w_stab = 0.15

        # Đọc preferences dạng list/dict từ frontend (state.profile) và priorities
        user_priorities = set()
        if isinstance(preferences, dict):
            p_val = preferences.get("priorities", [])
            if isinstance(p_val, list):
                for p in p_val:
                    user_priorities.add(str(p).strip().lower())
            elif isinstance(p_val, dict):
                for p in p_val.keys():
                    user_priorities.add(str(p).strip().lower())
            elif isinstance(p_val, str):
                user_priorities.add(p_val.strip().lower())

            if preferences.get("priority"):
                user_priorities.add(str(preferences["priority"]).strip().lower())

        if isinstance(priorities, dict):
            for k in priorities.keys():
                user_priorities.add(str(k).strip().lower())
        elif isinstance(priorities, list):
            for p in priorities:
                user_priorities.add(str(p).strip().lower())

        if any(x in user_priorities for x in ["thu nhập", "salary", "income"]):
            w_sal += 0.15
            w_fit -= 0.10
            w_stab -= 0.05
        if any(x in user_priorities for x in ["ổn định", "stability"]):
            w_stab += 0.15
            w_sal -= 0.05
            w_dem -= 0.10
        if any(x in user_priorities for x in ["cơ hội việc làm", "employment", "demand"]):
            w_dem += 0.15
            w_fit -= 0.10
            w_sal -= 0.05
        if any(x in user_priorities for x in ["cơ hội quốc tế", "international"]):
            w_dem += 0.10
            w_sal += 0.05
            w_fit -= 0.15

        weights = np.array([w_fit, w_sal, w_dem, w_stab])
        weights = weights / np.sum(weights)

        # Vector normalization
        norm_denom = np.sqrt(np.sum(X ** 2, axis=0))
        norm_denom[norm_denom == 0] = 1e-9
        R = X / norm_denom
        V = R * weights

        ideal_best = np.max(V, axis=0)
        ideal_worst = np.min(V, axis=0)

        dist_best = np.sqrt(np.sum((V - ideal_best) ** 2, axis=1))
        dist_worst = np.sqrt(np.sum((V - ideal_worst) ** 2, axis=1))

        # KHẮC PHỤC TRIỆT ĐỂ CHO TRƯỜNG HỢP 1 PHƯƠNG ÁN (m = 1)
        if len(matched_df) == 1:
            g = float(matched_df["gap"].iloc[0])
            single_closeness = max(0.2, min(0.95, 0.70 + (g * 0.05)))
            closeness = np.array([single_closeness])
            ranking_algo = "TOPSIS_fallback_heuristic"
        else:
            denom = dist_best + dist_worst
            closeness = np.where(denom > 1e-9, dist_worst / np.maximum(denom, 1e-9), 0.5)
            ranking_algo = "TOPSIS_multi_criteria"

        matched_df["topsis_closeness"] = closeness
        matched_df["match_score"] = (closeness * 100).round(1)

        # 4. PHÂN CHIA VÀO CÁC NHÓM SAFE / MATCH / REACH CHO FRONTEND
        # Nghiệp vụ:
        # - safe: gap >= +1.0
        # - match: -1.0 <= gap < +1.0
        # - reach: -3.0 <= gap < -1.0 (Có chặn cận dưới -3.0!)
        buckets = {"safe": [], "match": [], "reach": []}
        for _, r in matched_df.iterrows():
            gap = float(r["gap"])
            item = {
                "school_code": str(r.get("university_admission_code", "")),
                "school": str(r.get("university_name", "")),
                "major": str(r.get("major_name", "")),
                "major_code": str(r.get("major_code", "")),
                "group": str(r.get("major_group_name", "Khác")),
                "cutoff": float(r.get("cutoff_numeric", 0.0)),
                "gap": gap,
                "combination": combination,
                "note": str(r.get("note", "")),
                "topsis_score": float(r.get("match_score", 0.0)),
                "cutoff_trend": str(r.get("cutoff_trend", "")),
                "history_ambiguous": bool(r.get("history_ambiguous", False)),
                "job_category": str(r.get("job_category", "")),
            }
            if gap >= 1.0:
                buckets["safe"].append(item)
            elif gap >= -1.0:
                buckets["match"].append(item)
            elif gap >= -3.0:
                buckets["reach"].append(item)

        # Sắp xếp từng bucket theo điểm TOPSIS và giới hạn tối đa 15 mục
        for k in buckets:
            buckets[k].sort(key=lambda x: (x["topsis_score"], -abs(x["gap"])), reverse=True)
            buckets[k] = buckets[k][:15]

        counts = {k: len(v) for k, v in buckets.items()}
        total_count = sum(counts.values())

        # Top 5 tổng thể cho bảng xếp hạng TOPSIS
        ranked_df = matched_df.sort_values(by="topsis_closeness", ascending=False).head(5)
        ranking = []
        for _, r in ranked_df.iterrows():
            ranking.append({
                "ma_truong": str(r.get("university_admission_code", "")),
                "ten_truong": str(r.get("university_name", "")),
                "ma_nganh": str(r.get("major_code", "")),
                "ten_nganh": str(r.get("major_name", "")),
                "diem_chuan_2024": float(r.get("cutoff_score_30", 0.0)),
                "gap": float(r.get("gap", 0.0)),
                "match_score": float(r.get("match_score", 0.0)),
                "job_category": str(r.get("job_category", "")),
                "cutoff_trend": str(r.get("cutoff_trend", "")),
                "history_ambiguous": bool(r.get("history_ambiguous", False)),
            })

        top_choice = ranking[0] if ranking else {}
        top_gap = top_choice.get("gap", 0.0)

        # 5. ĐÁNH GIÁ MỨC ĐỘ CẠNH TRANH (Đổi tên minh bạch heuristic_score_gap_estimator)
        prob = 1.0 / (1.0 + math.exp(-1.5 * top_gap)) if ranking else 0.5
        competitiveness_index = round(min(0.95, max(0.05, prob)), 2)
        predicted_score = round(float(top_choice.get("diem_chuan_2024", user_total_score)), 2)
        if top_choice.get("cutoff_trend") == "Tăng":
            predicted_score += 0.25
        elif top_choice.get("cutoff_trend") == "Giảm":
            predicted_score -= 0.25

        prediction = {
            "model": "heuristic_score_gap_estimator",
            "competitiveness_index": competitiveness_index,
            "chance_of_admission": competitiveness_index,
            "predicted_score": round(predicted_score, 2),
            "target_school": top_choice.get("ten_truong", ""),
            "target_major": top_choice.get("ten_nganh", ""),
        }

        # 6. FEATURE ATTRIBUTION (So sánh điểm từng môn với phổ điểm trung bình toàn quốc 2024 thật)
        df_exam = data_repo.get_exam_data()
        nat_exam_2024 = df_exam[
            (df_exam["year"] == 2024) & (df_exam["province_code"] == "NATIONAL")
        ]

        feature_attributions = []
        strong_subjects = []
        weak_subjects = []

        for subj_key, user_subj_score in user_scores_float.items():
            col_key = SUBJECT_EXAM_COLUMN_MAP.get(subj_key, subj_key)
            mean_col = f"mean_{col_key}_score"

            if not nat_exam_2024.empty and mean_col in nat_exam_2024.columns:
                nat_mean = float(nat_exam_2024.iloc[0][mean_col])
            else:
                nat_mean = 6.5

            diff = round(user_subj_score - nat_mean, 2)
            impact_str = f"+{diff}" if diff >= 0 else f"{diff}"

            subj_name = SUBJECT_NAMES.get(subj_key, subj_key.capitalize())
            feature_attributions.append({
                "feature": subj_key,
                "subject_name": subj_name,
                "score": user_subj_score,
                "national_mean": round(nat_mean, 4),
                "deviation": impact_str,
            })

            if diff >= 1.0:
                strong_subjects.append(subj_name)
            elif diff < 0:
                weak_subjects.append(subj_name)

        # 7. THÔNG TIN THỊ TRƯỜNG LAO ĐỘNG (VietJobs - Trung thực khi thiếu mapping)
        career_context = []
        top_cat = top_choice.get("job_category", "")
        if top_choice and top_cat and top_cat not in ["nhóm_nghề_khác", "cần_xác_nhận_liên_ngành"]:
            matched_top = ranked_df.iloc[0]
            sal_avg = matched_top.get("job_avg_salary_million")
            demand = matched_top.get("job_demand_level", "")
            cnt = matched_top.get("job_posting_count")

            msg = f"Ngành '{top_choice.get('ten_nganh')}' thuộc nhóm nghề '{top_cat}', mức lương tham khảo trung bình khoảng {sal_avg:.1f} triệu VNĐ/tháng với nhu cầu tuyển dụng ở mức {demand} ({int(cnt)} tin tuyển dụng trong khảo sát VietJobs)."
            career_context.append(msg)
        else:
            career_context.append("Chưa đủ dữ liệu thị trường việc làm đã xác minh cho ngành này trong khảo sát VietJobs.")

        # 8. LỜI KHUYÊN TƯ VẤN (Tích hợp AdviceService & RAG Service - Không cam kết tuyệt đối)
        from services.advice_service import advice_service
        current_res = {
            "user_score": user_total_score,
            "combination": combination,
            "ranking": ranking,
            "prediction": prediction,
            "feature_attributions": feature_attributions,
            "criteria_weights": {
                "score_fit": round(float(weights[0]), 3),
                "salary": round(float(weights[1]), 3),
                "job_demand": round(float(weights[2]), 3),
                "stability": round(float(weights[3]), 3),
            },
        }
        adv_res = advice_service.generate_advice(current_res)
        advice_text = adv_res.get("advice", "")

        return {
            "user_score": user_total_score,
            "combination": combination,
            "combination_used": combination,
            "counts": counts,
            "results": buckets,
            "total_count": total_count,
            "ranking_algorithm": ranking_algo,
            "ranking": ranking,
            "criteria_weights": {
                "score_fit": round(float(weights[0]), 3),
                "salary": round(float(weights[1]), 3),
                "job_demand": round(float(weights[2]), 3),
                "stability": round(float(weights[3]), 3),
            },
            "prediction": prediction,
            "feature_attributions": feature_attributions,
            "career_context": career_context,
            "advice": advice_text,
            "detailed_advice": adv_res.get("sections", {}),
            "rag_evidence": adv_res.get("rag_evidence", {}),
            "what_if": {},
        }

    def _fallback_empty_response(self, user_total_score: float, combination: str) -> dict:
        return {
            "user_score": user_total_score,
            "combination": combination,
            "combination_used": combination,
            "counts": {"safe": 0, "match": 0, "reach": 0},
            "results": {"safe": [], "match": [], "reach": []},
            "total_count": 0,
            "ranking_algorithm": "TOPSIS_multi_criteria",
            "ranking": [],
            "criteria_weights": {"score_fit": 0.40, "salary": 0.25, "job_demand": 0.20, "stability": 0.15},
            "prediction": {"chance_of_admission": 0.5, "predicted_score": user_total_score},
            "feature_attributions": [],
            "career_context": [],
            "advice": "Chưa tìm thấy phương án tuyển sinh phù hợp với điều kiện lọc.",
            "what_if": {},
        }


recommendation_engine = RecommendationEngine()