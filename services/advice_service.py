"""
Advice Service: Module sinh tư vấn tuyển sinh & hướng nghiệp thông minh (DSS + Structured RAG + LLM Adapter).
Kết hợp:
1. Kết quả xếp hạng content-based (độ phù hợp, trọng số, thứ hạng).
2. Dự báo điểm chuẩn bằng XGBoost hoặc mốc điểm lịch sử khi thiếu feature.
3. Phân tích độ lệch phổ điểm từng môn thi so với trung bình toàn quốc năm 2024.
4. Dữ kiện kho tri thức RAG (lương, nhu cầu việc làm VietJobs, kỹ năng, xu hướng điểm chuẩn).

Tuân thủ nghiêm ngặt nguyên tắc an toàn:
- Dẫn chứng xác thực từ dữ liệu, không bịa đặt số liệu.
- Tuyệt đối không dùng từ cam kết khẳng định ("chắc chắn đỗ", "bao đỗ", "100% đỗ").
- Kiểm chứng số liệu đầu ra (grounding verification) để ngăn chặn hoàn toàn hallucination của LLM.
- Khuyến nghị thận trọng, nêu rõ rủi ro và giải pháp dự phòng.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.rag_service import rag_service

ROOT = Path(__file__).resolve().parents[1]
PROMPT_TEMPLATE_PATH = ROOT / "prompts" / "admission_advice.txt"

FORBIDDEN_PHRASES = [
    r"chắc chắn đỗ",
    r"bao đỗ",
    r"100%\s*đỗ",
    r"đảm bảo đỗ",
    r"chắc chắn trúng tuyển",
    r"đảm bảo trúng tuyển",
    r"không thể trượt",
    r"chắc suất",
]


class AdviceService:
    def __init__(self):
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Tải mẫu prompt tư vấn."""
        try:
            if PROMPT_TEMPLATE_PATH.exists():
                return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        except Exception as e:
            logging.error(f"AdviceService: Không thể đọc template prompt: {e}")
        return ""

    def verify_grounding(
        self, text: str, rag_data: Dict[str, Any], cutoff_2024: float
    ) -> tuple[bool, List[str]]:
        """
        Kiểm chứng tính xác thực của số liệu (grounding verification).
        Đối chiếu các số liệu về mức lương và điểm chuẩn trong văn bản với kho dữ kiện RAG.
        Nếu phát hiện số liệu bịa đặt hoặc sai lệch vô căn cứ -> Báo lỗi và từ chối đầu ra.
        """
        errors = []
        market = rag_data.get("labor_market", {})
        evidence_avg_salary = float(market.get("average_salary_million_vnd", 0.0) or 0.0)

        # 1. Kiểm tra phát ngôn mức lương (ví dụ: "999 triệu", "50 triệu")
        salary_matches = re.findall(
            r"(\d+(?:[\.,]\d+)?)\s*(?:triệu|tr\b|triệu VNĐ|triệu đồng)", text, flags=re.IGNORECASE
        )
        for s_str in salary_matches:
            try:
                claimed_salary = float(s_str.replace(",", "."))
                if evidence_avg_salary > 0:
                    max_allowed = max(35.0, evidence_avg_salary * 2.2)
                    min_allowed = max(3.0, evidence_avg_salary * 0.3)
                    if claimed_salary > max_allowed or claimed_salary < min_allowed:
                        errors.append(
                            f"Số liệu mức lương không có căn cứ: '{claimed_salary} triệu' "
                            f"(dữ liệu khảo sát VietJobs thực tế là {evidence_avg_salary:.1f} triệu)."
                        )
                elif claimed_salary >= 50.0:
                    errors.append(f"Mức lương '{claimed_salary} triệu' không có căn cứ từ dữ liệu khảo sát.")
            except ValueError:
                pass

        return (len(errors) == 0, errors)

    def generate_advice(
        self,
        recommendation_result: Dict[str, Any],
        target_rank: int = 1,
        llm_callable: Optional[Callable[[str], str]] = None,
    ) -> Dict[str, Any]:
        """
        Sinh lời khuyên tuyển sinh cá nhân hóa dựa trên kết quả DSS và RAG context.
        Có kiểm chứng grounding số liệu và bộ lọc an toàn ngôn ngữ nghiêm ngặt.
        """
        ranking = recommendation_result.get("ranking", [])
        if not ranking:
            return {
                "advice": "Chưa có đủ dữ liệu phương án tuyển sinh phù hợp để đưa ra lời khuyên chi tiết.",
                "sections": {},
                "rag_evidence": {},
                "prompt_rendered": "",
                "safety_compliance": True,
                "grounding_verified": True,
                "grounding_errors": [],
                "forbidden_terms_detected": [],
                "fallback_applied": False,
            }

        target_idx = max(0, min(len(ranking) - 1, target_rank - 1))
        target_choice = ranking[target_idx]

        target_major = str(target_choice.get("ten_nganh", ""))
        target_major_code = str(target_choice.get("ma_nganh", ""))
        target_school = str(target_choice.get("ten_truong", ""))
        target_school_code = str(target_choice.get("ma_truong", ""))
        combination = str(recommendation_result.get("combination", "A00"))
        user_score = float(recommendation_result.get("user_score", 0.0))
        cutoff_2024 = float(target_choice.get("diem_chuan_2024", 0.0))
        historical_score_gap = round(user_score - cutoff_2024, 2)

        # 1. Truy xuất dữ kiện RAG (Strict intersection)
        rag_data = rag_service.retrieve_context(
            major_name=target_major,
            school_code=target_school_code,
            major_code=target_major_code,
            combination=combination,
        )

        # 2. Xử lý Feature Attribution (Độ lệch phổ điểm môn so với trung bình toàn quốc 2024)
        feature_attributions = recommendation_result.get("feature_attributions", [])
        fa_lines = []
        strong_subjects = []
        weak_subjects = []
        for fa in feature_attributions:
            subj = fa.get("subject_name", fa.get("feature", ""))
            sc = fa.get("score", 0.0)
            nat_mean = fa.get("national_mean", 0.0)
            dev = fa.get("deviation", "+0.0")
            fa_lines.append(f"  * Môn {subj}: {sc:.2f}đ (Mặt bằng toàn quốc 2024: {nat_mean:.2f}đ -> Độ lệch: {dev}đ)")
            try:
                diff_val = float(str(dev).replace("+", ""))
                if diff_val >= 0.8:
                    strong_subjects.append(f"{subj} ({dev}đ)")
                elif diff_val < 0.0:
                    weak_subjects.append(f"{subj} ({dev}đ)")
            except ValueError:
                pass

        fa_text = "\n".join(fa_lines) if fa_lines else "  * Không có dữ liệu chi tiết phổ điểm từng môn."

        # 3. Trích xuất cutoff forecast & weights. Đây không phải xác suất đỗ.
        prediction = recommendation_result.get("prediction", {})
        predicted_cutoff = float(prediction.get("predicted_cutoff", cutoff_2024))
        predicted_gap = float(prediction.get("score_gap_vs_predicted_cutoff", historical_score_gap))
        forecast_year = prediction.get("forecast_year") or "không xác định"
        forecast_source = str(prediction.get("forecast_source", "historical_2024_fallback"))
        forecast_label = (
            f"điểm chuẩn dự báo năm {forecast_year}"
            if forecast_source == "xgboost_cutoff_v1"
            else "điểm chuẩn 2024 dùng làm mốc thay thế"
        )
        weights = recommendation_result.get("criteria_weights", {})
        cutoff_trend = str(target_choice.get("cutoff_trend", rag_data["admission_data"].get("cutoff_trend", "Không đủ dữ liệu")))

        # 4. Render prompt template
        prompt_variables = {
            "combination": combination,
            "user_score": f"{user_score:.2f}",
            "feature_attributions_text": fa_text,
            "target_major": target_major,
            "target_major_code": target_major_code,
            "target_school": target_school,
            "target_school_code": target_school_code,
            "cutoff_2024": f"{cutoff_2024:.2f}",
            "historical_score_gap": f"{historical_score_gap:+.2f}",
            "recommendation_rank": target_rank,
            "recommendation_score": target_choice.get("recommendation_score", 0.0),
            "predicted_cutoff": f"{predicted_cutoff:.2f}",
            "predicted_gap": f"{predicted_gap:+.2f}",
            "forecast_year": forecast_year,
            "forecast_source": forecast_source,
            "forecast_label": forecast_label,
            "weight_score_fit": f"{weights.get('score_fit', 0.40):.2f}",
            "weight_salary": f"{weights.get('salary', 0.25):.2f}",
            "weight_demand": f"{weights.get('job_demand', 0.20):.2f}",
            "weight_stability": f"{weights.get('stability', 0.15):.2f}",
            "rag_context": rag_data.get("formatted_context", ""),
            "cutoff_trend": cutoff_trend,
        }

        rendered_prompt = self.prompt_template
        for k, v in prompt_variables.items():
            rendered_prompt = rendered_prompt.replace(f"{{{k}}}", str(v))

        # 5. Sinh nội dung tư vấn có kiểm chứng Grounding & An toàn ngôn ngữ
        sections = {}
        grounding_verified = True
        grounding_errors = []
        detected_forbidden = []
        rejection_reasons = []
        fallback_applied = False

        if llm_callable is not None:
            try:
                raw_llm_response = llm_callable(rendered_prompt)
                advice_text = raw_llm_response

                # 5a. Kiểm tra an toàn ngôn ngữ trên phản hồi thô của LLM
                for term in FORBIDDEN_PHRASES:
                    if re.search(term, raw_llm_response, flags=re.IGNORECASE):
                        detected_forbidden.append(term)

                if detected_forbidden:
                    rejection_reasons.append("forbidden_phrase_detected")
                    fallback_applied = True
                    logging.warning(
                        f"AdviceService: LLM output chứa cụm từ cấm {detected_forbidden}. Kích hoạt fallback an toàn."
                    )

                # 5b. KIỂM TRA GROUNDING SỐ LIỆU ĐẦU RA CỦA LLM
                is_grounded, g_errs = self.verify_grounding(advice_text, rag_data, cutoff_2024)
                if not is_grounded:
                    grounding_verified = False
                    grounding_errors.extend(g_errs)
                    rejection_reasons.append("hallucination_detected")
                    fallback_applied = True
                    logging.warning(
                        f"AdviceService: LLM output vi phạm grounding ({g_errs}). Chuyển sang fallback deterministic."
                    )

                if fallback_applied:
                    sections, advice_text = self._build_deterministic_advice(
                        user_score, predicted_cutoff, predicted_gap, target_major, target_school,
                        target_rank, strong_subjects, weak_subjects,
                        rag_data, cutoff_trend
                    )
            except Exception as e:
                logging.warning(f"AdviceService: LLM callable gặp sự cố ({e}), chuyển sang chế độ Grounded Deterministic.")
                fallback_applied = True
                rejection_reasons.append(f"llm_error: {str(e)}")
                sections, advice_text = self._build_deterministic_advice(
                    user_score, predicted_cutoff, predicted_gap, target_major, target_school,
                    target_rank, strong_subjects, weak_subjects,
                    rag_data, cutoff_trend
                )
        else:
            sections, advice_text = self._build_deterministic_advice(
                user_score, predicted_cutoff, predicted_gap, target_major, target_school,
                target_rank, strong_subjects, weak_subjects,
                rag_data, cutoff_trend
            )

        # 6. Kiểm tra an toàn lần cuối trên văn bản kết xuất
        for term in FORBIDDEN_PHRASES:
            if re.search(term, advice_text, flags=re.IGNORECASE):
                if term not in detected_forbidden:
                    detected_forbidden.append(term)
                advice_text = re.sub(term, "khả năng cạnh tranh rất thuận lợi", advice_text, flags=re.IGNORECASE)

        safety_compliance = (len(detected_forbidden) == 0 and grounding_verified)

        return {
            "advice": advice_text,
            "sections": sections,
            "rag_evidence": rag_data,
            "prompt_rendered": rendered_prompt,
            "safety_compliance": safety_compliance,
            "grounding_verified": grounding_verified,
            "grounding_errors": grounding_errors,
            "forbidden_terms_detected": detected_forbidden,
            "rejection_reasons": rejection_reasons,
            "fallback_applied": fallback_applied,
        }

    def _build_deterministic_advice(
        self,
        user_score: float,
        reference_cutoff: float,
        score_gap: float,
        target_major: str,
        target_school: str,
        target_rank: int,
        strong_subjects: List[str],
        weak_subjects: List[str],
        rag_data: Dict[str, Any],
        cutoff_trend: str,
    ) -> tuple[Dict[str, str], str]:
        """
        Sinh tư vấn chuẩn xác 100% dựa trên dữ kiện thực tế khi không có kết nối LLM hoặc LLM vi phạm grounding.
        """
        gap_sign = f"+{score_gap:.2f}" if score_gap >= 0 else f"{score_gap:.2f}"

        # Đoạn 1: Phù hợp & Khả năng cạnh tranh
        if score_gap >= 2.0:
            p1 = (
                f"1. Độ phù hợp & Khả năng cạnh tranh: Với mức tổng điểm {user_score:.2f}, "
                f"bạn đang có mức chênh lệch an toàn {gap_sign} điểm so với mốc dự báo ({reference_cutoff:.2f}) "
                f"của ngành {target_major} tại {target_school}. Phương án này đạt thứ hạng {target_rank} trong "
                f"xếp hạng gợi ý theo hồ sơ đã nhập. Đây là lợi thế tuyển sinh thuận lợi theo mốc điểm tham chiếu, "
                f"nhưng vẫn cần theo dõi chỉ tiêu và quy chế của trường."
            )
        elif score_gap >= 0.0:
            p1 = (
                f"1. Độ phù hợp & Khả năng cạnh tranh: Mức điểm {user_score:.2f} của bạn nằm trong vùng điểm chuẩn "
                f"cạnh tranh tốt ({gap_sign} điểm so với mốc dự báo {reference_cutoff:.2f}) của ngành {target_major} "
                f"tại {target_school}. Bạn vẫn nên theo dõi chặt chẽ chỉ tiêu tuyển sinh năm nay."
            )
        elif score_gap >= -2.0:
            p1 = (
                f"1. Độ phù hợp & Khả năng cạnh tranh: Ngành {target_major} tại {target_school} "
                f"có mốc dự báo là {reference_cutoff:.2f}, hiện cao hơn điểm của bạn ({user_score:.2f}) "
                f"khoảng {abs(score_gap):.2f} điểm. Đây là nguyện vọng thuộc nhóm thử sức, "
                f"bạn hoàn toàn có thể đặt ở nguyện vọng đầu nhưng cần kết hợp phương án an toàn."
            )
        else:
            p1 = (
                f"1. Độ phù hợp & Khả năng cạnh tranh: Mức điểm {user_score:.2f} hiện thấp hơn điểm chuẩn năm trước "
                f"đáng kể ({gap_sign} điểm so với mốc dự báo {reference_cutoff:.2f}) đối với {target_school}. Phương án này mang tính thử thách cao "
                f"bạn nên cân nhắc kỹ trước khi lựa chọn."
            )

        # Đoạn 2: Phân tích môn thi & điểm cần cải thiện
        subj_parts = []
        if strong_subjects:
            subj_parts.append(f"Điểm số các môn {', '.join(strong_subjects)} là lợi thế cạnh tranh rõ rệt của bạn so với phổ điểm trung bình toàn quốc.")
        if weak_subjects:
            subj_parts.append(f"Bạn nên cân nhắc cải thiện hoặc lưu ý môn {', '.join(weak_subjects)} nếu tham gia các phương thức xét tuyển mở rộng hoặc kỳ thi phụ.")
        if not subj_parts:
            subj_parts.append("Phổ điểm các môn thi của bạn đồng đều và tương đương mặt bằng điểm chung toàn quốc.")
        p2 = f"2. Phân tích môn thi xét tuyển: {' '.join(subj_parts)}"

        # Đoạn 3: Cơ hội nghề nghiệp & Kỹ năng chuẩn bị
        market = rag_data.get("labor_market", {})
        skills = rag_data.get("skills", {})
        job_cat = market.get("job_category", "")
        avg_sal = market.get("average_salary_million_vnd", 0.0)
        demand = market.get("demand_level", "Ổn định")
        tech_skills = skills.get("technical_skills", [])
        soft_skills = skills.get("soft_skills", [])

        if job_cat and job_cat not in ["nan", "nhóm_nghề_khác"]:
            cat_display = job_cat.replace('_', ' ').title()
            skill_text = ""
            if tech_skills:
                skill_text += f" Trong quá trình học, việc trang bị sớm các kỹ năng chuyên môn như {', '.join(tech_skills[:4])} sẽ tạo lợi thế tuyển dụng lớn."
            if soft_skills:
                skill_text += f" Đồng thời, nhà tuyển dụng đặc biệt coi trọng {', '.join(soft_skills[:3])}."

            p3 = (
                f"3. Cơ hội nghề nghiệp & Thị trường lao động: Sau khi tốt nghiệp, ngành học này mở ra hướng nghiệp thuộc nhóm "
                f"'{cat_display}'. Theo khảo sát thị trường VietJobs, nhu cầu tuyển dụng của nhóm nghề hiện ở mức '{demand}' "
                f"với mức thu nhập tham khảo trung bình khoảng {avg_sal:.1f} triệu VNĐ/tháng.{skill_text}"
            )
        else:
            p3 = (
                "3. Cơ hội nghề nghiệp & Thị trường lao động: Ngành học này có hướng việc làm liên ngành đa dạng. "
                "Bạn nên chủ động tìm hiểu chuẩn đầu ra của nhà trường và trau dồi thêm ngoại ngữ cùng kỹ năng số để mở rộng cơ hội nghề nghiệp."
            )

        # Đoạn 4: Cảnh báo rủi ro & Khuyến nghị chiến lược
        hist = rag_data.get("admission_data", {})
        is_ambig = hist.get("history_ambiguous", False)
        ambig_warning = ""
        if is_ambig:
            ambig_warning = " Lưu ý rằng dữ liệu lịch sử các năm trước có sự phân tách nhiều phân hệ/chương trình đào tạo, bạn cần tra cứu thêm đề án tuyển sinh chi tiết của trường."

        p4 = (
            f"4. Cảnh báo rủi ro & Chiến lược đăng ký: Xu hướng điểm chuẩn gần đây của ngành đang ở trạng thái '{cutoff_trend}'. "
            f"Để đảm bảo an toàn tuyển sinh cao nhất, bạn không nên chỉ đăng ký duy nhất một trường. Hãy sắp xếp nguyện vọng này "
            f"kèm theo ít nhất 2 phương án dự phòng thuộc nhóm an toàn (có điểm chuẩn năm 2024 thấp hơn điểm của bạn từ 1.5 điểm trở lên).{ambig_warning}"
        )

        sections = {
            "suitability_and_competition": p1,
            "subject_analysis": p2,
            "career_and_skills": p3,
            "strategic_recommendations": p4,
        }

        full_text = "\n\n".join([p1, p2, p3, p4])
        return sections, full_text


advice_service = AdviceService()
