import unittest
from services.recommendation_service import recommendation_engine
from app import app


class TestRecommendationAndValidation(unittest.TestCase):
    def test_extra_subject_ignored_and_exact_combination_summed(self):
        """Kiểm tra: chỉ cộng đúng 3 môn của tổ hợp, loại bỏ triệt để môn thừa."""
        payload = {
            "combination": "A00",
            "scores": {
                "toan": 8.5,
                "vatly": 8.0,
                "hoahoc": 7.5,
                "nguvan": 10.0,  # Môn thừa ngoài tổ hợp A00
            },
            "interest": "Công nghệ thông tin",
        }
        res = recommendation_engine.process_recommendation(payload)
        # Tổng điểm phải đúng 24.0 (8.5 + 8.0 + 7.5), tuyệt đối không được cộng thêm Văn 10 thành 34.0
        self.assertEqual(res["user_score"], 24.0)
        self.assertEqual(res["combination_used"], "A00")

    def test_missing_subject_rejected(self):
        """Kiểm tra: từ chối hồ sơ thiếu môn của tổ hợp."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5},  # Thiếu Lý và Hóa
            "interest": "Công nghệ thông tin",
        }
        with self.assertRaises(ValueError):
            recommendation_engine.process_recommendation(payload)

    def test_national_exam_means_exact_mapping(self):
        """Kiểm tra: so sánh với điểm trung bình toàn quốc thật, không fallback về 6.5."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
        }
        res = recommendation_engine.process_recommendation(payload)
        attrs = {a["feature"]: a for a in res["feature_attributions"]}

        # Môn Toán năm 2024: 6.4473
        self.assertAlmostEqual(attrs["toan"]["national_mean"], 6.4473, places=3)
        # Môn Vật lý năm 2024: 6.6669
        self.assertAlmostEqual(attrs["vatly"]["national_mean"], 6.6669, places=3)
        # Môn Hóa học năm 2024: 6.6808
        self.assertAlmostEqual(attrs["hoahoc"]["national_mean"], 6.6808, places=3)

    def test_api_validation_rejects_missing_subjects(self):
        """Kiểm tra: API /api/recommend trả lỗi 400 khi thiếu môn bắt buộc."""
        client = app.test_client()
        # Thiếu Lý và Hóa của A00
        bad_payload = {
            "combination": "A00",
            "scores": {"toan": 8.5},
        }
        resp = client.post("/api/recommend", json=bad_payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        error_fields = [e["field"] for e in data["errors"]]
        self.assertIn("scores.vatly", error_fields)
        self.assertIn("scores.hoahoc", error_fields)

    def test_topsis_ranking_structure_and_criteria_weights(self):
        """Kiểm tra: thuật toán TOPSIS trả về ma trận và tiêu chí đầy đủ."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertEqual(res["ranking_algorithm"], "TOPSIS_multi_criteria")
        self.assertIn("score_fit", res["criteria_weights"])
        self.assertIn("salary", res["criteria_weights"])
        self.assertGreater(len(res["ranking"]), 0)
        # Kiểm tra điểm tương đồng TOPSIS match_score trong khoảng [0, 100]
        for item in res["ranking"]:
            self.assertGreaterEqual(item["match_score"], 0.0)
            self.assertLessEqual(item["match_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
