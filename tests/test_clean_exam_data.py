import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.clean_exam_data import DataValidationError, SOURCE_COLUMNS, clean_file, clean_row


def source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SOURCE_COLUMNS}
    row.update(
        {
            "SBD": "01000001",
            "Nam": "23",
            "Tinh": "1",
            "SBD_New": "1",
            "Toan": "8.40",
            "NguVan": "6.75",
            "NgoaiNgu": "8.0",
            "MaMonNgoaiNgu": "n1",
            "TongDiem": "23.15",
            "KhoiD": "23.15",
        }
    )
    row.update(overrides)
    return row


class CleanRowTests(unittest.TestCase):
    def test_chuan_hoa_dinh_danh_nam_va_so(self) -> None:
        cleaned, errors = clean_row(source_row(), 2023, Counter())

        self.assertEqual(errors, [])
        self.assertEqual(cleaned["sbd"], "01000001")
        self.assertEqual(cleaned["nam"], "2023")
        self.assertEqual(cleaned["ma_tinh"], "01")
        self.assertEqual(cleaned["sbd_noi_tinh"], "000001")
        self.assertEqual(cleaned["toan"], "8.4")
        self.assertEqual(cleaned["ma_mon_ngoai_ngu"], "N1")

    def test_khong_tu_dien_khtn_khi_diem_mon_co_so_0(self) -> None:
        row = source_row(
            NguVan="",
            NgoaiNgu="",
            MaMonNgoaiNgu="",
            TongDiem="",
            KhoiD="",
            VatLy="0.0",
            HoaHoc="7.25",
            SinhHoc="7.75",
            KhoiA="15.65",
            KhoiB="23.4",
            KhoiA02="16.15",
            KHTN="",
        )
        cleaned, errors = clean_row(row, 2023, Counter())

        self.assertEqual(errors, [])
        self.assertEqual(cleaned["khtn"], "")

    def test_loi_diem_ngoai_khoang(self) -> None:
        _, errors = clean_row(
            source_row(Toan="11", TongDiem="25.75", KhoiD="25.75"),
            2023,
            Counter(),
        )

        self.assertIn("Toan:ngoai_khoang_0_10", errors)


class CleanFileTests(unittest.TestCase):
    def test_tao_file_voi_ten_ngan_gon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "diemthi_2023.csv"
            output_dir = root / "cleaned"
            with input_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=SOURCE_COLUMNS)
                writer.writeheader()
                writer.writerow(source_row())

            report = clean_file(input_path, output_dir, 2023)

            self.assertEqual(report["counts"]["input_rows"], 1)
            self.assertEqual(report["counts"]["output_rows"], 1)
            self.assertTrue((output_dir / "diemthi_2023.csv").is_file())
            self.assertEqual(list(output_dir.iterdir()), [output_dir / "diemthi_2023.csv"])

    def test_gap_dong_trung_va_khong_tao_file_dau_ra(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "diemthi_2023.csv"
            output_dir = root / "cleaned"
            with input_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=SOURCE_COLUMNS)
                writer.writeheader()
                writer.writerow(source_row())
                writer.writerow(source_row())

            with self.assertRaises(DataValidationError):
                clean_file(input_path, output_dir, 2023)

            self.assertFalse((output_dir / "diemthi_2023.csv").exists())


if __name__ == "__main__":
    unittest.main()
