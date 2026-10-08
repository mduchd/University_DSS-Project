import unittest
import pandas as pd
from services.recommendation_service import calculate_interest_fit_scores, recommendation_engine
from app import app


class TestRecommendationAndValidation(unittest.TestCase):
    def test_interest_mapping_scores_matching_major(self):
        """Kiểm tra mapping content-based: sở thích không phải bộ lọc cộng tác."""
        candidates = pd.DataFrame([
            {
                "major_name": "Công nghệ thông tin",
                "major_group_name": "Công nghệ thông tin - Tin học",
                "job_category": "công_nghệ_thông_tin_kỹ_thuật_số",
            },
            {
                "major_name": "Quản trị kinh doanh",
                "major_group_name": "Kinh tế - Quản trị kinh doanh - Thương Mại",
                "job_category": "kinh_doanh_bán_hàng_chăm_sóc_khách_hàng",
            },
        ])

        scores = calculate_interest_fit_scores(candidates, ["Công nghệ"])

        self.assertEqual(scores.tolist(), [1.0, 0.0])

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

    def test_single_alternative_content_score_not_zero(self):
        """Kiểm tra: một phương án duy nhất vẫn có content-based score hợp lệ."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Kỹ thuật phần mềm liên kết quốc tế - KNU",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertGreater(len(res["ranking"]), 0)
        for item in res["ranking"]:
            self.assertGreater(item["recommendation_score"], 0.0, "Điểm gợi ý phải dương")

    def test_preferences_dynamically_adjust_weights(self):
        """Kiểm tra: preferences người dùng làm thay đổi trọng số content-based."""
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

    def test_reach_bucket_lower_bound(self):
        """Kiểm tra: nhóm Thử sức (reach) chỉ chứa gap trong khoảng [-3.0, -1.0), không chứa gap < -3.0."""
        # Thí sinh có điểm rất thấp (10.0đ)
        payload = {
            "combination": "A00",
            "scores": {"toan": 3.0, "vatly": 3.5, "hoahoc": 3.5},
            "interest": "Công nghệ thông tin",
        }
        res = recommendation_engine.process_recommendation(payload)
        for item in res["results"]["reach"]:
            self.assertGreaterEqual(item["gap"], -3.0, "Nhóm reach không được chứa ngành có gap < -3.0")
            self.assertLess(item["gap"], -1.0, "Nhóm reach chỉ chứa ngành có gap < -1.0")

    def test_group_filter(self):
        """Kiểm tra: bộ lọc group từ giao diện chỉ trả về ngành thuộc đúng nhóm ngành."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0},
            "group": "Công nghệ thông tin - Tin học",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertGreater(res["total_count"], 0)
        for bucket in ["safe", "match", "reach"]:
            for item in res["results"][bucket]:
                self.assertIn("Công nghệ thông tin", item["group"])

    def test_frontend_profile_preferences_format(self):
        """Kiểm tra: nhận đúng payload preferences từ state.profile của frontend (interests, priorities mảng, region)."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0},
            "preferences": {
                "interests": ["Công nghệ", "Kinh doanh"],
                "priorities": ["Cơ hội quốc tế", "Thu nhập"],
                "region": "Miền Bắc",
            },
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertGreater(res["total_count"], 0)
        self.assertGreater(res["criteria_weights"]["interest_fit"], 0.0)
        # Kiểm tra ưu tiên Thu nhập được tăng trọng số
        self.assertGreater(res["criteria_weights"]["salary"], 0.25)

    def test_api_400_validation_error_format(self):
        """Kiểm tra: khi lỗi validation 400, API trả về trường 'error' dạng chuỗi để app.js hiển thị."""
        client = app.test_client()
        resp = client.post("/api/recommend", json={"combination": "A00", "scores": {}})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)
        self.assertIsInstance(data["error"], str)
        self.assertGreater(len(data["error"]), 0)

    def test_content_based_algorithm_name(self):
        """Kiểm tra: luồng recommendation không còn dùng TOPSIS."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interest": "Kỹ thuật phần mềm liên kết quốc tế - KNU",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertEqual(res["ranking_algorithm"], "content_based_weighted_scoring")

    def test_zero_score_returns_empty_ranking_and_clear_message(self):
        """Kiểm tra P1: Thí sinh tổng điểm 0.0 bị loại sạch vì gap < -3.0, không có ranking ảo."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 0.0, "vatly": 0.0, "hoahoc": 0.0},
            "interest": "Công nghệ thông tin",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertEqual(res["total_count"], 0)
        self.assertEqual(len(res["ranking"]), 0)
        self.assertEqual(len(res["results"]["safe"]), 0)
        self.assertEqual(len(res["results"]["match"]), 0)
        self.assertEqual(len(res["results"]["reach"]), 0)
        self.assertIn("thấp hơn điểm chuẩn tối thiểu", res["message"])

    def test_region_filter_strict_and_accurate(self):
        """Kiểm tra P2: Lọc Miền Bắc và Miền Nam trả về 100% ngành đúng vùng miền, không còn NaN."""
        base_scores = {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0}
        
        # Test Miền Bắc
        res_north = recommendation_engine.process_recommendation({
            "combination": "A00",
            "scores": base_scores,
            "region": "Miền Bắc",
        })
        self.assertGreater(res_north["total_count"], 0)
        for bucket in ["safe", "match", "reach"]:
            for item in res_north["results"][bucket]:
                self.assertEqual(item["region"], "Miền Bắc")

        # Test Miền Nam
        res_south = recommendation_engine.process_recommendation({
            "combination": "A00",
            "scores": base_scores,
            "region": "Miền Nam",
        })
        self.assertGreater(res_south["total_count"], 0)
        for bucket in ["safe", "match", "reach"]:
            for item in res_south["results"][bucket]:
                self.assertEqual(item["region"], "Miền Nam")

    def test_non_existent_group_returns_empty_no_filter_reset(self):
        """Kiểm tra P2: Khi nhóm ngành không tồn tại, trả về 0 kết quả, tuyệt đối không reset về 45 phương án."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0},
            "group": "Nhóm Ngành Không Tồn Tại 12345",
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertEqual(res["total_count"], 0)
        self.assertEqual(len(res["ranking"]), 0)


if __name__ == "__main__":
    unittest.main()


