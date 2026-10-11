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

        scores = calculate_interest_fit_scores(candidates, ["Khám phá máy tính, dữ liệu & AI"])

        self.assertEqual(scores.tolist(), [1.0, 0.0])

    def test_job_category_alone_cannot_change_major_interest(self):
        """Mapping VietJobs nhiễu không được làm sai lĩnh vực của ngành học."""
        candidates = pd.DataFrame([{
            "major_name": "Quản trị kinh doanh",
            "major_group_name": "Kinh tế - Quản trị kinh doanh - Thương Mại",
            "job_category": "sản_xuất_lao_động_phổ_thông_cơ_khí",
        }])

        scores = calculate_interest_fit_scores(candidates, ["Khám phá máy tính, dữ liệu & AI"])

        self.assertEqual(scores.tolist(), [0.0])

    def test_digital_technology_and_engineering_construction_are_separate(self):
        """Tên ngành xây dựng vẫn bị loại dù dữ liệu lịch sử gán nhầm nhóm CNTT."""
        candidates = pd.DataFrame([
            {
                "major_name": "Công nghệ thông tin",
                "major_group_name": "Công nghệ thông tin - Tin học",
            },
            {
                "major_name": "Quản lý xây dựng",
                # Mô phỏng nhãn nhóm sai có trong một số bản ghi lịch sử.
                "major_group_name": "Công nghệ thông tin - Tin học",
            },
            {
                "major_name": "Công nghệ kỹ thuật xây dựng",
                "major_group_name": "Xây dựng - Kiến trúc - Giao thông",
            },
            {
                "major_name": "Kỹ thuật cơ điện tử",
                "major_group_name": "Cơ khí - Tự động hóa",
            },
        ])

        digital_scores = calculate_interest_fit_scores(candidates, ["Khám phá máy tính, dữ liệu & AI"])
        engineering_scores = calculate_interest_fit_scores(candidates, ["Thiết kế, chế tạo & xây dựng"])

        self.assertEqual(digital_scores.tolist(), [1.0, 0.0, 0.0, 0.0])
        self.assertEqual(engineering_scores.tolist(), [0.0, 1.0, 1.0, 1.0])

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
            "interests": ["Công nghệ"],
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
            "interests": ["Công nghệ"],
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
            "interests": ["Công nghệ"],
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

    def test_ranked_alternatives_have_positive_content_scores(self):
        """Kiểm tra: các phương án gợi ý có content-based score hợp lệ."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interests": ["Công nghệ"],
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertGreater(len(res["ranking"]), 0)
        for item in res["ranking"]:
            self.assertGreater(item["recommendation_score"], 0.0, "Điểm gợi ý phải dương")

    def test_interests_activate_interest_fit_weight(self):
        """Kiểm tra: sở thích là đầu vào duy nhất ngoài tổ hợp và điểm."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interests": ["Công nghệ", "Kinh doanh"],
        }
        result = recommendation_engine.process_recommendation(payload)
        self.assertGreater(result["criteria_weights"]["interest_fit"], 0.0)

    def test_selected_interest_excludes_zero_fit_majors(self):
        """Chọn Công nghệ không được trả ngành không khớp như Luật kinh tế."""
        result = recommendation_engine.process_recommendation({
            "combination": "D01",
            "scores": {"toan": 9.0, "nguvan": 9.0, "ngoaingu": 9.0},
            "interests": ["Công nghệ"],
        })

        self.assertGreater(result["total_count"], 0)
        returned = [item for bucket in result["results"].values() for item in bucket]
        self.assertTrue(all(item["interest_fit"] > 0 for item in returned))
        self.assertNotIn("Luật kinh tế", {item["major"] for item in returned})
        self.assertNotIn("Quản trị kinh doanh", {item["major"] for item in returned})

    def test_reach_bucket_lower_bound(self):
        """Kiểm tra: nhóm Thử sức (reach) chỉ chứa gap trong khoảng [-3.0, -1.0), không chứa gap < -3.0."""
        # Thí sinh có điểm rất thấp (10.0đ)
        payload = {
            "combination": "A00",
            "scores": {"toan": 3.0, "vatly": 3.5, "hoahoc": 3.5},
            "interests": ["Công nghệ"],
        }
        res = recommendation_engine.process_recommendation(payload)
        for item in res["results"]["reach"]:
            self.assertGreaterEqual(item["gap"], -3.0, "Nhóm reach không được chứa ngành có gap < -3.0")
            self.assertLess(item["gap"], -1.0, "Nhóm reach chỉ chứa ngành có gap < -1.0")

    def test_frontend_interests_payload_format(self):
        """Kiểm tra: backend nhận trực tiếp danh sách interests từ frontend."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0},
            "interests": ["Công nghệ", "Kinh doanh"],
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertGreater(res["total_count"], 0)
        self.assertGreater(res["criteria_weights"]["interest_fit"], 0.0)
        self.assertAlmostEqual(res["criteria_weights"]["salary"], 0.20)

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
        """Kiểm tra: luồng gợi ý dùng content-based weighted scoring."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5},
            "interests": ["Công nghệ"],
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertEqual(res["ranking_algorithm"], "content_based_weighted_scoring")

    def test_zero_score_returns_empty_ranking_and_clear_message(self):
        """Kiểm tra P1: Thí sinh tổng điểm 0.0 bị loại sạch vì gap < -3.0, không có ranking ảo."""
        payload = {
            "combination": "A00",
            "scores": {"toan": 0.0, "vatly": 0.0, "hoahoc": 0.0},
            "interests": ["Công nghệ"],
        }
        res = recommendation_engine.process_recommendation(payload)
        self.assertEqual(res["total_count"], 0)
        self.assertEqual(len(res["ranking"]), 0)
        self.assertEqual(len(res["results"]["safe"]), 0)
        self.assertEqual(len(res["results"]["match"]), 0)
        self.assertEqual(len(res["results"]["reach"]), 0)
        self.assertIn("thấp hơn điểm chuẩn tối thiểu", res["message"])

    def test_more_than_two_interests_is_rejected(self):
        client = app.test_client()
        response = client.post(
            "/api/recommend",
            json={
                "combination": "A00",
                "scores": {"toan": 8.0, "vatly": 8.0, "hoahoc": 8.0},
                "interests": ["Công nghệ", "Kinh doanh", "Sáng tạo"],
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()


