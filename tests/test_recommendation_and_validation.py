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

    def test_api_frontend_contract_and_buckets(self):
        """Kiểm tra: API /api/recommend trả về đầy đủ schema tương thích 100% với app.js."""
        client = app.test_client()
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        }
        resp = client.post("/api/recommend", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        # Kiểm tra các trường top-level mà renderRecommendationResults(data) trong app.js đọc
        self.assertIn("user_score", data)
        self.assertEqual(data["user_score"], 24.0)
        self.assertIn("combination", data)
        self.assertEqual(data["combination"], "A00")
        self.assertIn("counts", data)
        self.assertIn("safe", data["counts"])
        self.assertIn("match", data["counts"])
        self.assertIn("reach", data["counts"])

        # Kiểm tra danh sách results.safe, results.match, results.reach
        self.assertIn("results", data)
        self.assertIsInstance(data["results"]["safe"], list)
        self.assertIsInstance(data["results"]["match"], list)
        self.assertIsInstance(data["results"]["reach"], list)

        # Kiểm tra các trường của card hiển thị
        if data["results"]["safe"]:
            card = data["results"]["safe"][0]
            self.assertIn("school", card)
            self.assertIn("major", card)
            self.assertIn("cutoff", card)
            self.assertIn("gap", card)

        # Kiểm tra backward compatibility
        self.assertIn("data", data)
        self.assertIn("status", data)
        self.assertEqual(data["status"], "success")

    def test_single_alternative_topsis_not_zero(self):
        """Kiểm tra: khi bộ lọc chỉ có 1 phương án duy nhất, match_score không bị trả 0.0."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Kỹ thuật phần mềm liên kết quốc tế - KNU",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertGreater(len(res["ranking"]), 0)
        for item in res["ranking"]:
            self.assertGreater(item["match_score"], 50.0, "Điểm tương đồng phương án duy nhất phải > 50")

    def test_preferences_dynamically_adjust_weights(self):
        """Kiểm tra: preferences người dùng làm thay đổi trọng số ma trận TOPSIS."""
        base_payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Công nghệ thông tin",
        }

        # Ưu tiên thu nhập
        p_income = {**base_payload, "preferences": {"priority": "thu nhập"}}
        r_income = recommendation_engine.process_recommendation(p_income)

        # Ưu tiên ổn định
        p_stab = {**base_payload, "preferences": {"priority": "ổn định"}}
        r_stab = recommendation_engine.process_recommendation(p_stab)

        self.assertGreater(r_income["criteria_weights"]["salary"], r_stab["criteria_weights"]["salary"])
        self.assertGreater(r_stab["criteria_weights"]["stability"], r_income["criteria_weights"]["stability"])


if __name__ == "__main__":
    unittest.main()
