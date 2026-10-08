import logging
import unicodedata
import numpy as np
import pandas as pd
from services.data_repository import data_repo
from services.cutoff_forecast_service import cutoff_forecast_service

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

# Mapping có chủ đích, dùng để so khớp hồ sơ sở thích khái quát với các thuộc
# tính đã có của phương án (tên ngành, nhóm ngành, nhóm nghề). Đây là content-
# based filtering, không suy diễn từ hành vi của những người dùng khác.
INTEREST_KEYWORDS = {
    "cong nghe": (
        "cong nghe", "tin hoc", "dien", "co khi", "tu dong hoa",
        "du lieu", "tri tue nhan tao", "phan mem", "game",
    ),
    "kinh doanh": (
        "kinh te", "quan tri", "thuong mai", "tai chinh", "ngan hang", "ke toan",
        "marketing", "logistics", "kinh doanh", "bao hiem",
    ),
    "sang tao": (
        "thiet ke", "truyen thong", "bao chi", "quang cao", "nghe thuat", "am nhac",
        "my thuat", "thoi trang", "da phuong tien", "game",
    ),
    "xa hoi & cong dong": (
        "xa hoi", "giao duc", "su pham", "tam ly", "luat", "y te", "dieu duong",
        "duoc", "van hoa", "quan ly nha nuoc", "cong tac xa hoi",
    ),
}


def calculate_interest_fit_scores(candidates: pd.DataFrame, interests: list[str]) -> np.ndarray:
    """Trả về mức khớp [0, 1] giữa sở thích trong hồ sơ và từng phương án.

    Mỗi sở thích có trọng số bằng nhau. Một phương án khớp ít nhất một từ khóa
    đại diện của sở thích đó được tính 1 điểm cho sở thích ấy; sau đó lấy trung
    bình theo số sở thích đã chọn. Không có sở thích thì trả về 0 để trọng số
    `interest_fit` được phân bổ lại cho các tiêu chí còn lại ở caller.
    """
    cleaned_interests = list(dict.fromkeys(
        str(interest).strip() for interest in interests if str(interest).strip()
    ))
    if not cleaned_interests:
        return np.zeros(len(candidates), dtype=float)

    searchable_columns = ("major_name", "major_group_name", "job_category")
    candidate_texts = candidates.apply(
        lambda row: " ".join(
            remove_accents(str(row.get(column, ""))).replace("_", " ")
            for column in searchable_columns
        ),
        axis=1,
    )
    interest_keywords = []
    for interest in cleaned_interests:
        normalized_interest = remove_accents(interest)
        interest_keywords.append(INTEREST_KEYWORDS.get(normalized_interest, (normalized_interest,)))

    scores = []
    for candidate_text in candidate_texts:
        matched_interests = sum(
            any(keyword and keyword in candidate_text for keyword in keywords)
            for keywords in interest_keywords
        )
        scores.append(matched_interests / len(interest_keywords))
    return np.asarray(scores, dtype=float)


class RecommendationEngine:
    def __init__(self):
        self.master_data = data_repo.get_master_data()
        self.exam_data = data_repo.get_exam_data()

    def process_recommendation(self, user_payload: dict) -> dict:
        """Lọc ứng viên hợp lệ và xếp hạng content-based theo hồ sơ người dùng."""
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
            matched_df = matched_df[group_mask].copy()
            if matched_df.empty:
                return self._fallback_empty_response(
                    user_total_score,
                    combination,
                    msg=f"Không tìm thấy phương án tuyển sinh nào thuộc nhóm ngành '{group_filter}' cho tổ hợp {combination}."
                )

        # Lọc theo Khu vực (region) từ profile nếu có
        region_pref = ""
        if isinstance(preferences, dict) and preferences.get("region"):
            region_pref = str(preferences["region"]).strip()
        elif user_payload.get("region"):
            region_pref = str(user_payload.get("region")).strip()

        if region_pref:
            norm_reg = remove_accents(region_pref)
            reg_mask = matched_df["region"].apply(
                lambda x: norm_reg in remove_accents(str(x)) or remove_accents(str(x)) in norm_reg
            )
            matched_df = matched_df[reg_mask].copy()
            if matched_df.empty:
                return self._fallback_empty_response(
                    user_total_score,
                    combination,
                    msg=f"Không tìm thấy phương án tuyển sinh nào tại khu vực '{region_pref}' cho tổ hợp {combination}."
                )

        # `interest` là từ khóa cụ thể do người dùng nhập nên được dùng để lọc
        # cứng. Các chip `preferences.interests` là sở thích khái quát, được
        # dùng để chấm interest_fit phía dưới thay vì loại hết kết quả.
        user_interests = []
        if isinstance(preferences, dict):
            if isinstance(preferences.get("interests"), list):
                user_interests = [str(i).strip() for i in preferences["interests"] if str(i).strip()]
            elif isinstance(preferences.get("interests"), str) and preferences.get("interests"):
                user_interests = [preferences["interests"].strip()]

        search_terms = [interest] if interest else []

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
            matched_df = matched_df[combined_mask].copy()
            if matched_df.empty:
                return self._fallback_empty_response(
                    user_total_score,
                    combination,
                    msg=f"Không tìm thấy phương án tuyển sinh nào phù hợp với từ khóa sở thích '{', '.join(search_terms)}' cho tổ hợp {combination}."
                )

        if matched_df.empty:
            return self._fallback_empty_response(user_total_score, combination)

        matched_df["historical_cutoff"] = pd.to_numeric(matched_df["cutoff_score_30"], errors="coerce")
        matched_df = matched_df.dropna(subset=["historical_cutoff"])

        # XGBoost dự báo điểm chuẩn 2025 từ feature lịch sử tính đến 2024.
        # Khi candidate không có modeling key, giữ điểm chuẩn lịch sử thay vì
        # tự dựng feature hoặc đưa ra dự báo thiếu căn cứ.
        matched_df = cutoff_forecast_service.add_forecasts(matched_df)
        matched_df["ranking_cutoff"] = matched_df["predicted_cutoff"].fillna(matched_df["historical_cutoff"])
        matched_df["cutoff_numeric"] = matched_df["ranking_cutoff"]
        matched_df["gap"] = (user_total_score - matched_df["ranking_cutoff"]).round(2)

        # Loại bỏ các phương án quá tầm với (gap < -3.0) trước khi tạo danh sách gợi ý.
        matched_df = matched_df[matched_df["gap"] >= -3.0].copy()
        if matched_df.empty:
            return self._fallback_empty_response(
                user_total_score,
                combination,
                msg=f"Mức điểm {user_total_score:.2f} hiện thấp hơn điểm chuẩn tối thiểu của các trường (vượt ngoài ngưỡng thử sức -3.0 điểm). Hệ thống khuyến nghị bạn cân nhắc cải thiện điểm thi hoặc lựa chọn các phương thức xét tuyển khác."
            )

        # 3. CONTENT-BASED SCORING
        # Điểm gợi ý dựa trên thuộc tính của ngành/trường và hồ sơ đã nhập,
        # không dùng AHP, TOPSIS hay Collaborative Filtering. Collaborative
        # Filtering cần ma trận tương tác từ nhiều người dùng, dữ liệu này chưa
        # thuộc phạm vi của đồ án.
        admission_fit_scores = np.clip((matched_df["gap"].to_numpy(dtype=float) + 3.0) / 4.0, 0.05, 1.0)
        interest_fit_scores = calculate_interest_fit_scores(matched_df, user_interests)

        salaries = matched_df["job_avg_salary_million"].fillna(15.0).clip(lower=5.0).to_numpy(dtype=float)
        postings = matched_df["job_posting_count"].fillna(500.0).clip(lower=10.0).to_numpy(dtype=float)

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

        def normalize_candidate_feature(values: np.ndarray) -> np.ndarray:
            """Đưa một đặc trưng ứng viên về [0, 1] mà không dùng ideal solution."""
            lower, upper = np.quantile(values, [0.05, 0.95])
            if upper <= lower:
                return np.full(len(values), 0.5)
            return np.clip((values - lower) / (upper - lower), 0.0, 1.0)

        salary_scores = normalize_candidate_feature(salaries)
        demand_scores = normalize_candidate_feature(postings)

        # Điều chỉnh trọng số rõ ràng theo preference do người dùng cung cấp.
        w_admission = 0.40
        w_interest = 0.00
        w_sal = 0.25
        w_dem = 0.20
        w_stab = 0.15

        # Khi hồ sơ có sở thích, dành 20% cho mức khớp hồ sơ-ngành. Không có
        # sở thích thì không giả định sở thích và giữ nguyên trọng số cũ.
        if user_interests:
            w_admission = 0.35
            w_interest = 0.20
            w_sal = 0.20
            w_dem = 0.15
            w_stab = 0.10

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
            w_admission -= 0.10
            w_stab -= 0.05
        if any(x in user_priorities for x in ["ổn định", "stability"]):
            w_stab += 0.15
            w_sal -= 0.05
            w_dem -= 0.10
        if any(x in user_priorities for x in ["cơ hội việc làm", "employment", "demand"]):
            w_dem += 0.15
            w_admission -= 0.10
            w_sal -= 0.05
        if any(x in user_priorities for x in ["cơ hội quốc tế", "international"]):
            w_dem += 0.10
            w_sal += 0.05
            w_admission -= 0.15

        weights = np.array([w_admission, w_interest, w_sal, w_dem, w_stab])
        weights = weights / np.sum(weights)

        content_scores = (
            weights[0] * admission_fit_scores
            + weights[1] * interest_fit_scores
            + weights[2] * salary_scores
            + weights[3] * demand_scores
            + weights[4] * stabilities
        )
        matched_df["recommendation_score"] = (content_scores * 100).round(1)
        matched_df["interest_fit"] = (interest_fit_scores * 100).round(0)
        matched_df["interest_fit_active"] = bool(user_interests)
        ranking_algo = "content_based_weighted_scoring"

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
                "cutoff": float(r.get("ranking_cutoff", 0.0)),
                "historical_cutoff_2024": float(r.get("historical_cutoff", 0.0)),
                "forecast_year": int(r["forecast_year"]) if pd.notna(r.get("forecast_year")) else None,
                "forecast_source": str(r.get("forecast_source", "historical_2024_fallback")),
                "gap": gap,
                "combination": combination,
                "note": str(r.get("note", "")),
                "recommendation_score": float(r.get("recommendation_score", 0.0)),
                "interest_fit": float(r.get("interest_fit", 0.0)),
                "interest_fit_active": bool(r.get("interest_fit_active", False)),
                "cutoff_trend": str(r.get("cutoff_trend", "")),
                "history_ambiguous": bool(r.get("history_ambiguous", False)),
                "job_category": str(r.get("job_category", "")),
                "region": str(r.get("region", "")),
                "province": str(r.get("province", "")),
            }
            if gap >= 1.0:
                buckets["safe"].append(item)
            elif gap >= -1.0:
                buckets["match"].append(item)
            elif gap >= -3.0:
                buckets["reach"].append(item)

        # Sắp xếp từng bucket theo content-based score và giới hạn tối đa 15 mục.
        for k in buckets:
            buckets[k].sort(key=lambda x: (x["recommendation_score"], -abs(x["gap"])), reverse=True)
            buckets[k] = buckets[k][:15]

        counts = {k: len(v) for k, v in buckets.items()}
        total_count = sum(counts.values())

        # Top 5 theo content-based score để giải thích cho người dùng.
        ranked_df = matched_df.sort_values(by="recommendation_score", ascending=False).head(5)
        ranking = []
        for _, r in ranked_df.iterrows():
            ranking.append({
                "ma_truong": str(r.get("university_admission_code", "")),
                "ten_truong": str(r.get("university_name", "")),
                "ma_nganh": str(r.get("major_code", "")),
                "ten_nganh": str(r.get("major_name", "")),
                "diem_chuan_2024": float(r.get("historical_cutoff", 0.0)),
                "du_bao_diem_chuan": float(r.get("ranking_cutoff", 0.0)),
                "nam_du_bao": int(r["forecast_year"]) if pd.notna(r.get("forecast_year")) else None,
                "nguon_du_bao": str(r.get("forecast_source", "historical_2024_fallback")),
                "model_version": r.get("forecast_model_version") if pd.notna(r.get("forecast_model_version")) else None,
                "is_cold_start": bool(r.get("forecast_is_cold_start", False)) if pd.notna(r.get("forecast_is_cold_start")) else False,
                "gap": float(r.get("gap", 0.0)),
                "recommendation_score": float(r.get("recommendation_score", 0.0)),
                "interest_fit": float(r.get("interest_fit", 0.0)),
                "job_category": str(r.get("job_category", "")),
                "cutoff_trend": str(r.get("cutoff_trend", "")),
                "history_ambiguous": bool(r.get("history_ambiguous", False)),
            })

        top_choice = ranking[0] if ranking else {}
        top_gap = top_choice.get("gap", 0.0)

        # 5. DỰ BÁO ĐIỂM CHUẨN: regression output, không phải xác suất đỗ.
        forecast_model = top_choice.get("model_version")
        forecast_source = top_choice.get("nguon_du_bao")
        prediction = {
            "model": str(forecast_model) if pd.notna(forecast_model) else "historical_2024_fallback",
            "forecast_source": str(forecast_source) if pd.notna(forecast_source) else "historical_2024_fallback",
            "forecast_year": top_choice.get("nam_du_bao"),
            "predicted_cutoff": round(float(top_choice.get("du_bao_diem_chuan", user_total_score)), 2),
            "score_gap_vs_predicted_cutoff": round(float(top_gap), 2),
            "is_cold_start": bool(top_choice.get("is_cold_start", False)),
            "target_school": top_choice.get("ten_truong", ""),
            "target_major": top_choice.get("ten_nganh", ""),
        }

        # 6. FEATURE ATTRIBUTION (So sánh điểm từng môn với phổ điểm trung bình toàn quốc 2024 thật)
        df_exam = data_repo.get_exam_data()
        nat_exam_2024 = df_exam[
            (df_exam["year"] == 2024) & (df_exam["province_code"] == "NATIONAL")
        ]

        feature_attributions = []
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
                "admission_fit": round(float(weights[0]), 3),
                "interest_fit": round(float(weights[1]), 3),
                "salary": round(float(weights[2]), 3),
                "job_demand": round(float(weights[3]), 3),
                "stability": round(float(weights[4]), 3),
            },
            "prediction": prediction,
            "feature_attributions": feature_attributions,
            "career_context": career_context,
            "what_if": {},
        }

    def _fallback_empty_response(
        self,
        user_total_score: float,
        combination: str,
        msg: str = "Chưa tìm thấy phương án tuyển sinh phù hợp với điều kiện lọc."
    ) -> dict:
        return {
            "user_score": user_total_score,
            "combination": combination,
            "combination_used": combination,
            "counts": {"safe": 0, "match": 0, "reach": 0},
            "results": {"safe": [], "match": [], "reach": []},
            "total_count": 0,
            "ranking_algorithm": "content_based_weighted_scoring",
            "ranking": [],
            "criteria_weights": {
                "admission_fit": 0.40,
                "interest_fit": 0.00,
                "salary": 0.25,
                "job_demand": 0.20,
                "stability": 0.15,
            },
            "prediction": {
                "model": "unavailable",
                "forecast_source": "unavailable",
                "forecast_year": None,
                "predicted_cutoff": user_total_score,
                "score_gap_vs_predicted_cutoff": 0.0,
                "is_cold_start": False,
            },
            "feature_attributions": [],
            "career_context": [],
            "message": msg,
            "what_if": {},
        }


recommendation_engine = RecommendationEngine()
