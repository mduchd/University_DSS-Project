"""
Bộ kiểm thử toàn diện cho module RAG + LLM Advice Service của Sơn:
1. Kiểm tra kho tri thức RAG (RAGService): truy xuất thông tin lương, kỹ năng, tin tuyển dụng, điểm chuẩn.
2. Kiểm tra tính an toàn ngôn ngữ của AdviceService (không cam kết tuyệt đối, không dùng từ cấm).
3. Kiểm tra tính dẫn chứng số liệu (grounded facts), không bịa đặt số liệu.
4. Kiểm tra Prompt Template (prompts/admission_advice.txt) được điền đầy đủ biến số.
5. Kiểm thử 5-10 kịch bản hồ sơ thí sinh đa dạng.
"""

import unittest
from services.recommendation_service import recommendation_engine
from services.rag_service import rag_service
from services.advice_service import advice_service, FORBIDDEN_PHRASES


class TestRAGAndAdviceService(unittest.TestCase):
    def test_rag_service_retrieval_facts(self):
        """1. Kiểm tra RAGService truy xuất đúng dữ kiện thị trường và điểm chuẩn chuẩn hóa."""
        context = rag_service.retrieve_context(
            major_name="Công nghệ thông tin",
            school_code="BKA",
            combination="A00",
        )
        self.assertIn("metadata", context)
        self.assertIn("admission_data", context)
        self.assertIn("labor_market", context)
        self.assertIn("skills", context)
        self.assertIn("formatted_context", context)

        # Dữ liệu thị trường phải có mức lương và số tin tuyển dụng hợp lệ
        market = context["labor_market"]
        self.assertGreaterEqual(market["posting_count"], 0)
        self.assertGreaterEqual(market["average_salary_million_vnd"], 0.0)

        # Kỹ năng phải được trích xuất từ khảo sát
        skills = context["skills"]
        self.assertIsInstance(skills["technical_skills"], list)
        self.assertIsInstance(skills["soft_skills"], list)

    def test_prompt_template_injection(self):
        """2. Kiểm tra template prompts/admission_advice.txt được inject đầy đủ, không sót placeholder."""
        rec = recommendation_engine.process_recommendation({
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        })
        advice_res = advice_service.generate_advice(rec)
        prompt = advice_res["prompt_rendered"]

        # Không còn sót các biến dạng {variable}
        self.assertNotIn("{combination}", prompt)
        self.assertNotIn("{user_score}", prompt)
        self.assertNotIn("{target_major}", prompt)
        self.assertNotIn("{target_school}", prompt)
        self.assertNotIn("{cutoff_2024}", prompt)
        self.assertNotIn("{rag_context}", prompt)

    def test_scenario_high_score_safe(self):
        """3. Kịch bản 1 - Thí sinh điểm cao (Vùng an toàn): Đưa ra đánh giá lợi thế và khuyến nghị thận trọng."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 9.5, "vatly": 9.0, "hoahoc": 8.5},  # 27.0đ
            "interest": "Công nghệ thông tin",
        }
        rec = recommendation_engine.process_recommendation(payload)
        adv = advice_service.generate_advice(rec)

        self.assertTrue(adv["safety_compliance"])
        self.assertEqual(len(adv["forbidden_terms_detected"]), 0)
        # Khẳng định không dùng từ cấm
        for term in FORBIDDEN_PHRASES:
            self.assertNotIn(term, adv["advice"].lower())

        # Phải có các phần tư vấn rõ ràng
        sections = adv["sections"]
        self.assertIn("suitability_and_competition", sections)
        self.assertIn("career_and_skills", sections)
        self.assertIn("strategic_recommendations", sections)

    def test_scenario_borderline_match(self):
        """4. Kịch bản 2 - Thí sinh điểm sát nút (Vùng phù hợp/cạnh tranh): Cảnh báo biến động điểm."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0},  # 24.0đ
            "interest": "Kỹ thuật phần mềm",
        }
        rec = recommendation_engine.process_recommendation(payload)
        adv = advice_service.generate_advice(rec)

        self.assertTrue(adv["safety_compliance"])
        for term in FORBIDDEN_PHRASES:
            self.assertNotIn(term, adv["advice"].lower())
        self.assertIn("dự phòng", adv["advice"].lower())

    def test_scenario_reach_challenge(self):
        """5. Kịch bản 3 - Thí sinh vùng thử sức (Reach): Khuyên đặt nguyện vọng ưu tiên kèm dự phòng an toàn."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 7.0, "vatly": 7.0, "hoahoc": 7.0},  # 21.0đ
            "interest": "Công nghệ thông tin",
        }
        rec = recommendation_engine.process_recommendation(payload)
        adv = advice_service.generate_advice(rec)

        self.assertTrue(adv["safety_compliance"])
        for term in FORBIDDEN_PHRASES:
            self.assertNotIn(term, adv["advice"].lower())

    def test_scenario_feature_attribution_strengths_and_weaknesses(self):
        """6. Kịch bản 4 - Phân tích thế mạnh môn thi (Feature Attribution SHAP): Nhận diện đúng môn mạnh/yếu."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 9.5, "vatly": 6.0, "hoahoc": 5.5},  # Toán rất cao (+3.05), Hóa thấp (-1.18)
            "interest": "Công nghệ thông tin",
        }
        rec = recommendation_engine.process_recommendation(payload)
        adv = advice_service.generate_advice(rec)

        # Môn Toán phải được nhận diện là thế mạnh vượt trội
        subj_text = adv["sections"]["subject_analysis"]
        self.assertIn("Toán", subj_text)

    def test_scenario_humanities_d01(self):
        """7. Kịch bản 5 - Khối Khoa học Xã hội / D01 (Toán, Văn, Ngoại ngữ): Tư vấn ngành Ngôn ngữ/Kinh tế."""
        payload = {
            "combination": "D01",
            "scores": {"toan": 8.0, "nguvan": 8.5, "ngoaingu": 8.5},  # 25.0đ
            "interest": "Ngôn ngữ Anh",
        }
        rec = recommendation_engine.process_recommendation(payload)
        adv = advice_service.generate_advice(rec)

        self.assertTrue(adv["safety_compliance"])
        self.assertGreater(len(adv["advice"]), 100)

    def test_scenario_ambiguous_history_cautious_advice(self):
        """8. Kịch bản 6 - Ngành có lịch sử điểm biến động/xung đột: Đưa ra cảnh báo tra cứu đề án chi tiết."""
        context = rag_service.retrieve_context(
            major_name="Kinh tế học",
            school_code="KHA",
            combination="A00",
        )
        self.assertTrue(context["admission_data"]["history_ambiguous"])
        # Format text phải có ghi chú lưu ý về phân hệ tuyển sinh
        self.assertIn("Lưu ý", context["formatted_context"])

    def test_llm_callable_custom_integration(self):
        """9. Kịch bản 7 - Kiểm tra khả năng tích hợp LLM client ngoài khi có API key."""
        mock_called = False

        def mock_llm_generator(prompt: str) -> str:
            nonlocal mock_called
            mock_called = True
            self.assertIn("thí sinh", prompt.lower())
            return "Lời khuyên từ LLM: Thí sinh có khả năng cạnh tranh rất thuận lợi vào ngành học này."

        rec = recommendation_engine.process_recommendation({
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        })
        adv = advice_service.generate_advice(rec, llm_callable=mock_llm_generator)
        self.assertTrue(mock_called)
        self.assertIn("Lời khuyên từ LLM", adv["advice"])

    def test_end_to_end_recommendation_includes_rag_and_advice(self):
        """10. Kịch bản 8 - End-to-end integration qua RecommendationEngine: trả về đầy đủ advice và rag_evidence."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
            "preferences": {"priorities": ["Cơ hội việc làm", "Thu nhập"]},
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertIn("advice", res)
        self.assertIn("detailed_advice", res)
        self.assertIn("rag_evidence", res)
        self.assertGreater(len(res["advice"]), 50)
        self.assertIn("labor_market", res["rag_evidence"])

    def test_rag_strict_retrieval_fail_closed(self):
        """11. Kiểm tra cơ chế fail-closed: Khi query trường/ngành không tồn tại, trả về found: False, tuyệt đối không lấy nhầm trường khác."""
        probe = rag_service.retrieve_context(
            major_name="Ngành Không Tồn Tại XYZ",
            school_code="ZZZ",
            combination="A00",
        )
        self.assertFalse(probe.get("found", True))
        self.assertIsNone(probe["admission_data"]["cutoff_2024"])
        self.assertIn("Không tìm thấy dữ liệu", probe["formatted_context"])
        # Đảm bảo không fallback trả về trường khác (như KHA)
        self.assertEqual(probe["metadata"]["school_code"], "ZZZ")

    def test_llm_hallucination_salary_rejection(self):
        """12. Kiểm tra bộ lọc Grounding: Phát hiện và từ chối phát ngôn bịa đặt số liệu lương (ví dụ: '999 triệu')."""
        def hallucinating_llm(prompt: str) -> str:
            return "Ngành này có mức lương khởi điểm trung bình là 999 triệu đồng/tháng theo khảo sát VietJobs."

        rec = recommendation_engine.process_recommendation({
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        })
        adv = advice_service.generate_advice(rec, llm_callable=hallucinating_llm)
        self.assertTrue(adv.get("fallback_applied", False))
        self.assertFalse(adv.get("safety_compliance", True))
        self.assertIn("hallucination_detected", adv.get("rejection_reasons", []))
        self.assertNotIn("999 triệu", adv["advice"])

    def test_forbidden_phrases_case_insensitive(self):
        """13. Kiểm tra bộ lọc an toàn: Bắt cả chữ hoa/thường cho từ cấm ('Chắc Chắn Đỗ', '100% ĐỖ')."""
        def risky_llm(prompt: str) -> str:
            return "Với mức điểm này, bạn Chắc Chắn Đỗ 100% ĐỖ vào ngành Công nghệ thông tin."

        rec = recommendation_engine.process_recommendation({
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        })
        adv = advice_service.generate_advice(rec, llm_callable=risky_llm)
        self.assertTrue(adv.get("fallback_applied", False))
        self.assertFalse(adv.get("safety_compliance", True))
        self.assertGreater(len(adv["forbidden_terms_detected"]), 0)
        # Lời khuyên cuối cùng đã được thay thế bằng fallback chuẩn tắc
        for term in FORBIDDEN_PHRASES:
            self.assertNotIn(term, adv["advice"].lower())


if __name__ == "__main__":
    unittest.main()

