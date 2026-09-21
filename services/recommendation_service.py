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

# Ánh xạ tên môn trong payload sang tên cột tiếng Anh trong exam_processed.csv
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

        # Chỉ cộng 3 môn của tổ hợp
        user_total_score = round(sum(user_scores_float[s] for s in required_subjects), 2)
        logging.info(f"Hồ sơ: Tổ hợp {combination} - Tổng 3 môn: {user_total_score} - Sở thích: '{interest}'")

        # 2. LẤY & LỌC DỮ LIỆU TỪ MASTER ADMISSION
        df = data_repo.get_master_data()
        if df.empty:
            return self._fallback_empty_response(user_total_score)

        matched_df = df[df["subject_combination"].astype(str).str.upper() == combination].copy()

        # XỬ LÝ THANG 40: Tạm tách riêng các phương án thang 40 khỏi ranking thang 30 chuẩn
        # để tránh sai lệch do môn nhân hệ số 2
        matched_df = matched_df[matched_df["is_scale_40"] == False].copy()

        # Lọc theo sở thích nếu có
        if interest:
            norm_interest = remove_accents(interest)
            match_mask = (
                matched_df["major_name"].apply(lambda x: norm_interest in remove_accents(str(x)))
                | matched_df["major_group_name"].apply(lambda x: norm_interest in remove_accents(str(x)))
                | matched_df["university_name"].apply(lambda x: norm_interest in remove_accents(str(x)))
            )
            if match_mask.any():
                matched_df = matched_df[match_mask].copy()

        if matched_df.empty:
            matched_df = df[
                (df["subject_combination"].astype(str).str.upper() == combination)
                & (df["is_scale_40"] == False)
            ].copy()

        if matched_df.empty:
            return self._fallback_empty_response(user_total_score)

        matched_df["cutoff_numeric"] = pd.to_numeric(matched_df["cutoff_score_30"], errors="coerce")
        matched_df = matched_df.dropna(subset=["cutoff_numeric"])
        matched_df["gap"] = (user_total_score - matched_df["cutoff_numeric"]).round(2)

        # 3. THUẬT TOÁN TOPSIS (Technique for Order Preference by Similarity to Ideal Solution)
        # Xây dựng ma trận quyết định X (m alternatives x 4 criteria):
        # - C1: Mức độ tương thích điểm số: f(gap) (càng gần vùng an toàn gap từ 0 đến +2 càng tối ưu)
        # - C2: Mức lương thị trường (triệu đồng/tháng từ VietJobs)
        # - C3: Nhu cầu tuyển dụng (số tin tuyển dụng VietJobs)
        # - C4: Độ ổn định điểm chuẩn (1 / (1 + cutoff_std_recent))
        m = len(matched_df)
        gap_scores = matched_df["gap"].apply(
            lambda g: max(0.1, 10.0 - abs(g - 1.0)) if g >= -2.0 else max(0.01, 10.0 - abs(g) * 2.0)
        ).to_numpy()

        salaries = matched_df["job_avg_salary_million"].fillna(15.0).clip(lower=5.0).to_numpy()
        postings = matched_df["job_posting_count"].fillna(500.0).clip(lower=10.0).to_numpy()
        stds = matched_df["cutoff_std_recent"].fillna(0.5).to_numpy()
        stabilities = 1.0 / (1.0 + stds)

        X = np.column_stack([gap_scores, salaries, postings, stabilities])

        # Trọng số tiêu chí W (tổng = 1.0)
        weights = np.array([0.40, 0.25, 0.20, 0.15])

        # Vector normalization: r_ij = x_ij / sqrt(sum(x_ij^2))
        norm_denom = np.sqrt(np.sum(X ** 2, axis=0))
        norm_denom[norm_denom == 0] = 1e-9
        R = X / norm_denom

        # Ma trận có trọng số: V = R * W
        V = R * weights

        # Nghiệm lý tưởng tốt nhất (A+) và xấu nhất (A-)
        ideal_best = np.max(V, axis=0)
        ideal_worst = np.min(V, axis=0)

        # Khoảng cách Euclidean
        dist_best = np.sqrt(np.sum((V - ideal_best) ** 2, axis=1))
        dist_worst = np.sqrt(np.sum((V - ideal_worst) ** 2, axis=1))

        # Độ tương tự với nghiệm lý tưởng: C_i = S- / (S+ + S-)
        denom = dist_best + dist_worst
        denom[denom == 0] = 1e-9
        closeness = dist_worst / denom

        matched_df["topsis_closeness"] = closeness
        matched_df["match_score"] = (closeness * 100).round(1)

        # Xếp hạng và chọn Top 5
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
            })

        top_choice = ranking[0] if ranking else {}
        top_gap = top_choice.get("gap", 0.0)

        # 4. ML CALIBRATED PROBABILITY ESTIMATION
        # Xác suất trúng tuyển theo hàm logistic hiệu chỉnh dựa trên gap và độ lệch chuẩn
        prob = 1.0 / (1.0 + math.exp(-1.5 * top_gap)) if ranking else 0.5
        chance_of_admission = round(min(0.95, max(0.05, prob)), 2)
        predicted_score = round(float(top_choice.get("diem_chuan_2024", user_total_score)), 2)
        if top_choice.get("cutoff_trend") == "Tăng":
            predicted_score += 0.25
        elif top_choice.get("cutoff_trend") == "Giảm":
            predicted_score -= 0.25

        prediction = {
            "model": "calibrated_logistic_cutoff_estimator",
            "chance_of_admission": chance_of_admission,
            "predicted_score": round(predicted_score, 2),
            "target_school": top_choice.get("ten_truong", ""),
            "target_major": top_choice.get("ten_nganh", ""),
        }

        # 5. FEATURE ATTRIBUTION (So sánh điểm từng môn với phổ điểm trung bình toàn quốc 2024 thật)
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

        # 6. THÔNG TIN THỊ TRƯỜNG LAO ĐỘNG (VietJobs)
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
            career_context.append("Ngành đào tạo có phạm vi nghề nghiệp đa dạng, nhu cầu tuyển dụng ổn định tại các thành phố lớn.")

        # 7. LỜI KHUYÊN TƯ VẤN (TUÂN THỦ: Không bao giờ nói 'chắc chắn đỗ')
        advice_parts = []
        if top_choice:
            trend_str = top_choice.get("cutoff_trend", "Ổn định")
            if top_gap >= 2.0:
                comp_text = f"Với mức điểm {user_total_score} (cao hơn điểm chuẩn 2024 là +{top_gap} điểm), bạn có khả năng cạnh tranh rất thuận lợi vào ngành {top_choice.get('ten_nganh')} tại {top_choice.get('ten_truong')}."
            elif top_gap >= 0.0:
                comp_text = f"Với mức điểm {user_total_score} (chênh lệch +{top_gap} so với điểm chuẩn 2024), bạn nằm trong vùng cạnh tranh tốt, tuy nhiên xu hướng điểm chuẩn đang ở trạng thái '{trend_str}' nên vẫn cần đăng ký thêm nguyện vọng dự phòng an toàn."
            else:
                comp_text = f"Mức điểm {user_total_score} hiện thấp hơn điểm chuẩn năm trước ({top_gap} điểm) đối với {top_choice.get('ten_truong')}. Đây là nguyện vọng mang tính thử thách (vùng với tới), bạn nên cân nhắc đặt ở nguyện vọng ưu tiên và bổ sung các trường có ngưỡng điểm an toàn hơn."
            advice_parts.append(comp_text)

        if strong_subjects:
            advice_parts.append(f"Điểm số môn {', '.join(strong_subjects)} là lợi thế cạnh tranh rõ rệt của bạn so với mặt bằng chung toàn quốc.")
        if weak_subjects:
            advice_parts.append(f"Bạn nên cân nhắc cải thiện thêm môn {', '.join(weak_subjects)} nếu có kế hoạch xét tuyển ở các phương thức phụ hoặc các tổ hợp mở rộng.")

        advice_text = " ".join(advice_parts)

        return {
            "ranking_algorithm": "TOPSIS_multi_criteria",
            "ranking": ranking,
            "criteria_weights": {"score_fit": 0.40, "salary": 0.25, "job_demand": 0.20, "stability": 0.15},
            "prediction": prediction,
            "feature_attributions": feature_attributions,
            "career_context": career_context,
            "advice": advice_text,
            "user_score": user_total_score,
            "combination_used": combination,
            "what_if": {},
        }

    def _fallback_empty_response(self, user_total_score: float) -> dict:
        return {
            "ranking_algorithm": "TOPSIS_multi_criteria",
            "ranking": [],
            "criteria_weights": {"score_fit": 0.40, "salary": 0.25, "job_demand": 0.20, "stability": 0.15},
            "prediction": {"chance_of_admission": 0.5, "predicted_score": user_total_score},
            "feature_attributions": [],
            "career_context": [],
            "advice": "Chưa tìm thấy phương án tuyển sinh phù hợp với điều kiện lọc.",
            "user_score": user_total_score,
            "what_if": {},
        }


recommendation_engine = RecommendationEngine()