import logging
import os
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

ROOT = Path(__file__).resolve().parents[1]


class DataRepository:
    _instance = None

    # Singleton Pattern: nạp và cache dữ liệu lên RAM một lần duy nhất
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataRepository, cls).__new__(cls)
            cls._instance._data_cache = {}
            cls._instance.load_all_data()
        return cls._instance

    def load_all_data(self):
        """Nạp và cache dữ liệu từ processed và master vào RAM"""
        logging.info("Khởi động DataRepository: Đang nạp dữ liệu lên RAM...")

        # 1. Nạp dữ liệu điểm thi (Processed)
        exam_path = ROOT / "data" / "processed" / "exam_processed.csv"
        if exam_path.exists():
            df_exam = pd.read_csv(exam_path, encoding="utf-8-sig")

            # BẢO MẬT: Đảm bảo không chứa Số báo danh (SBD) hoặc PII
            for pii_col in ["SBD", "sbd"]:
                if pii_col in df_exam.columns:
                    df_exam.drop(columns=[pii_col], inplace=True)

            self._data_cache["exam_data"] = df_exam
            logging.info(f"- Đã nạp dữ liệu điểm thi: {len(df_exam)} dòng (Đã gỡ SBD).")
        else:
            logging.warning(f"- Không tìm thấy file: {exam_path}")

        # 2. Nạp dữ liệu điểm chuẩn / ngành nghề (Master Admission)
        master_path = ROOT / "data" / "master" / "master_admission.csv"
        if master_path.exists():
            df_master = pd.read_csv(master_path, encoding="utf-8-sig")
            self._data_cache["master_data"] = df_master
            logging.info(f"- Đã nạp dữ liệu Master: {len(df_master)} dòng.")
        else:
            logging.warning(f"- Không tìm thấy file: {master_path}")

        # 3. Nạp dữ liệu thị trường việc làm theo danh mục (Jobs Summary)
        job_summary_path = ROOT / "data" / "processed" / "jobs" / "job_market_summary_by_category.csv"
        if job_summary_path.exists():
            df_jobs = pd.read_csv(job_summary_path, encoding="utf-8-sig")
            self._data_cache["job_market_data"] = df_jobs
            logging.info(f"- Đã nạp dữ liệu thị trường việc làm: {len(df_jobs)} nhóm nghề.")
        else:
            logging.warning(f"- Không tìm thấy file: {job_summary_path}")

    def get_exam_data(self) -> pd.DataFrame:
        """Cung cấp bản sao dữ liệu điểm thi cho Recommendation Service / ML"""
        df = self._data_cache.get("exam_data", pd.DataFrame())
        return df.copy()

    def get_master_data(self) -> pd.DataFrame:
        """Cung cấp bản sao dữ liệu tiêu chí ngành cho AHP/TOPSIS / Decision Engine"""
        df = self._data_cache.get("master_data", pd.DataFrame())
        return df.copy()

    def get_job_market_data(self) -> pd.DataFrame:
        """Cung cấp bản sao dữ liệu thị trường lao động (lương, nhu cầu) theo nhóm nghề"""
        df = self._data_cache.get("job_market_data", pd.DataFrame())
        return df.copy()

    def get_admission_by_combination(self, combination: str) -> pd.DataFrame:
        """Lọc danh sách các ngành tuyển sinh theo tổ hợp môn (A00, D01, ...)"""
        df = self.get_master_data()
        if df.empty or "subject_combination" not in df.columns:
            return pd.DataFrame()
        return df[df["subject_combination"].astype(str).str.upper() == combination.upper()].copy()

    def search_majors(self, query: str, combination: str | None = None) -> list[dict]:
        """Tìm kiếm phương án tuyển sinh theo tên ngành / trường / tổ hợp (an toàn regex)"""
        df = self.get_master_data()
        if df.empty:
            return []

        filtered = df
        if combination:
            filtered = filtered[filtered["subject_combination"].astype(str).str.upper() == combination.upper()]

        q = query.strip().casefold()
        if q:
            # Dùng regex=False để an toàn tuyệt đối với các ký tự đặc biệt như [, ], (, )...
            match_mask = (
                filtered["major_name"].astype(str).str.casefold().str.contains(q, regex=False, na=False)
                | filtered["university_name"].astype(str).str.casefold().str.contains(q, regex=False, na=False)
                | filtered["major_code"].astype(str).str.casefold().str.contains(q, regex=False, na=False)
                | filtered["university_admission_code"].astype(str).str.casefold().str.contains(q, regex=False, na=False)
            )
            filtered = filtered[match_mask]

        return filtered.head(50).to_dict(orient="records")


# Khởi tạo sẵn một instance toàn cục để app.py import
data_repo = DataRepository()

# Dành riêng cho việc test module độc lập
if __name__ == "__main__":
    print("=== TEST DATA REPOSITORY ===")
    repo = DataRepository()
    print("Các bảng đã cache:", list(repo._data_cache.keys()))
    df_m = repo.get_master_data()
    print(f"Master records: {len(df_m)}, columns: {len(df_m.columns)}")