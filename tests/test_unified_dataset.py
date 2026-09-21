import unittest
from pathlib import Path
import pandas as pd
from services.data_repository import data_repo
from services.recommendation_service import recommendation_engine

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "master" / "master_admission.csv"
EXAM_PATH = ROOT / "data" / "processed" / "exam_processed.csv"
REPORT_PATH = ROOT / "data" / "processed" / "unified_dataset_report.json"


class TestUnifiedDatasetSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df_master = pd.read_csv(MASTER_PATH, encoding="utf-8-sig", dtype=str)
        cls.df_exam = pd.read_csv(EXAM_PATH, encoding="utf-8-sig")

    def test_no_lost_admission_options_and_preserves_all_2024(self):
        """1. Kiểm tra không làm mất phương án tuyển sinh: phải giữ đủ 19.983 dòng năm 2024."""
        self.assertEqual(
            len(self.df_master),
            19983,
            f"Tổng số dòng phải đúng 19.983, thực tế: {len(self.df_master)}"
        )

        # Kiểm tra trường hợp trường BVH ngành 7340115 khối A00 phải giữ trọn vẹn cả 3 chương trình
        bvh_records = self.df_master[
            (self.df_master["university_admission_code"] == "BVH")
            & (self.df_master["major_code"] == "7340115")
            & (self.df_master["subject_combination"] == "A00")
        ]
        self.assertEqual(
            len(bvh_records),
            3,
            "BVH ngành 7340115 khối A00 phải có đủ 3 phương án (Chuẩn, CLC, Quan hệ công chúng)"
        )
        scores = set(bvh_records["cutoff_score"].tolist())
        self.assertEqual(len(scores), 3, "Ba phương án BVH phải có 3 mức điểm khác nhau")

    def test_national_weighted_mean_correctness(self):
        """2. Kiểm tra tính điểm trung bình toàn quốc có trọng số chuẩn xác."""
        national_rows = self.df_exam[self.df_exam["province_code"] == "NATIONAL"]
        self.assertEqual(len(national_rows), 6, "Phải có 6 nhóm NATIONAL tương ứng với các năm và chương trình")

        province_rows = self.df_exam[self.df_exam["province_code"] != "NATIONAL"]

        for _, nat_row in national_rows.iterrows():
            yr = nat_row["year"]
            prog = nat_row["exam_program"]

            prov_group = province_rows[
                (province_rows["year"] == yr) & (province_rows["exam_program"] == prog)
            ]

            # Kiểm tra toán và lý
            for subj in ["math", "physics", "literature", "foreign_language"]:
                count_col = f"count_{subj}_score"
                mean_col = f"mean_{subj}_score"

                counts = prov_group[count_col].fillna(0)
                tot_count = counts.sum()
                self.assertEqual(
                    int(nat_row[count_col]),
                    int(tot_count),
                    f"Count {subj} của NATIONAL {yr} {prog} phải bằng tổng count các tỉnh"
                )

                if tot_count > 0:
                    exp_mean = round(
                        float((prov_group[mean_col] * counts).sum() / tot_count),
                        4
                    )
                    act_mean = round(float(nat_row[mean_col]), 4)
                    self.assertAlmostEqual(
                        exp_mean,
                        act_mean,
                        places=3,
                        msg=f"NATIONAL {mean_col} {yr} {prog} phải tính theo weighted mean"
                    )

    def test_trend_requires_at_least_two_years(self):
        """3. Kiểm tra tính nhất quán của xu hướng: dưới 2 năm quan sát phải gán 'Không đủ dữ liệu'."""
        df = self.df_master.copy()
        df["years_observed"] = pd.to_numeric(df["years_observed"], errors="coerce")

        one_year_records = df[df["years_observed"] < 2]
        self.assertGreater(len(one_year_records), 0)

        # Tuyệt đối không được gán 'Ổn định' cho các phương án chỉ quan sát được 1 năm
        invalid_trends = one_year_records[one_year_records["cutoff_trend"] == "Ổn định"]
        self.assertEqual(
            len(invalid_trends),
            0,
            f"Có {len(invalid_trends)} dòng dưới 2 năm dữ liệu nhưng lại bị gán 'Ổn định'"
        )

        all_under_two_are_unknown = (one_year_records["cutoff_trend"] == "Không đủ dữ liệu").all()
        self.assertTrue(all_under_two_are_unknown, "Mọi phương án dưới 2 năm quan sát phải là 'Không đủ dữ liệu'")

    def test_strict_mapping_no_false_substring_matching(self):
        """4. Kiểm tra mapping có kiểm soát: không mapping tùy tiện theo chuỗi chứa nhau."""
        van_hoc = self.df_master[self.df_master["major_name"] == "Văn học"]
        self.assertGreater(len(van_hoc), 0)

        # 'Văn học' không được map nhầm vào 'marketing_truyền_thông_quảng_cáo_nội_dung'
        false_mapped = van_hoc[van_hoc["job_category"] == "marketing_truyền_thông_quảng_cáo_nội_dung"]
        self.assertEqual(
            len(false_mapped),
            0,
            f"Văn học bị map sai vào Marketing ({len(false_mapped)} dòng)"
        )

        # Các khóa tuple xung đột nhiều nhóm nghề phải được gắn 'ambiguous'
        ambiguous_rows = self.df_master[self.df_master["mapping_confidence"] == "ambiguous"]
        self.assertGreater(len(ambiguous_rows), 0, "Phải có các dòng được gắn cờ ambiguous thay vì chọn tùy ý")

        # Cột mapping_basis và mapping_confidence phải tồn tại và có giá trị
        self.assertIn("mapping_basis", self.df_master.columns)
        self.assertIn("mapping_confidence", self.df_master.columns)

    def test_scale_40_flag_present(self):
        """Kiểm tra: gắn cờ is_scale_40 chính xác cho các phương án thang 40."""
        scale_40_rows = self.df_master[self.df_master["is_scale_40"] == "True"]
        self.assertGreater(len(scale_40_rows), 500, "Phải nhận diện được các phương án thang 40")


    def test_data_repository_regex_safety_and_copies(self):
        """5. Kiểm tra tính an toàn regex và bảo vệ bộ nhớ cache của DataRepository."""
        # Query chứa ký tự regex đặc biệt không được gây crash
        res = data_repo.search_majors("[")
        self.assertIsInstance(res, list)

        # Đảm bảo getter trả về bản sao copy, không làm hỏng cache
        df_copy = data_repo.get_master_data()
        df_copy.drop(columns=["university_name"], inplace=True)
        self.assertIn("university_name", data_repo.get_master_data().columns)

    def test_recommendation_engine_semantics_and_safety(self):
        """6. Kiểm tra Recommendation Engine sinh kết quả thật và tuân thủ nguyên tắc an toàn."""
        # Profile 1: 24 điểm CNTT
        p1 = {"combination": "A00", "scores": {"toan": 8.5, "vatly": 8.0, "hoahoc": 7.5}, "interest": "Công nghệ thông tin"}
        r1 = recommendation_engine.process_recommendation(p1)

        # Profile 2: 12 điểm Ngôn ngữ
        p2 = {"combination": "A00", "scores": {"toan": 4.0, "vatly": 4.0, "hoahoc": 4.0}, "interest": "Ngôn ngữ"}
        r2 = recommendation_engine.process_recommendation(p2)

        # 2 profile phải có kết quả khác nhau
        self.assertNotEqual(r1["prediction"]["chance_of_admission"], r2["prediction"]["chance_of_admission"])
        self.assertGreater(r1["prediction"]["chance_of_admission"], r2["prediction"]["chance_of_admission"])

        # Kiểm tra nguyên tắc cấm dùng từ khẳng định tuyệt đối trong cả 2 lời khuyên
        forbidden_phrases = ["chắc chắn đỗ", "bao đỗ", "100% đỗ", "chắc chắn trúng tuyển", "đảm bảo đỗ"]
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, r1["advice"].lower(), f"Lời khuyên chứa từ cấm: {phrase}")
            self.assertNotIn(phrase, r2["advice"].lower(), f"Lời khuyên chứa từ cấm: {phrase}")


if __name__ == "__main__":
    unittest.main()
