import pandas as pd
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class DataRepository:
    _instance = None
    
    # Thiết kế theo Singleton Pattern để đảm bảo chỉ có 1 bản sao dữ liệu trên RAM
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
        # Giả định team đã đẩy file điểm thi tính toán sẵn vào thư mục processed
        exam_path = 'data/processed/exam_processed.csv'
        if os.path.exists(exam_path):
            df_exam = pd.read_csv(exam_path, encoding='utf-8-sig')
            
            # BẢO MẬT: Xóa bỏ hoàn toàn cột Số báo danh (SBD) hoặc thông tin cá nhân (PII)
            if 'SBD' in df_exam.columns:
                df_exam.drop(columns=['SBD'], inplace=True)
                
            self._data_cache['exam_data'] = df_exam
            logging.info(f"- Đã nạp dữ liệu điểm thi: {len(df_exam)} dòng (Đã gỡ SBD).")
        else:
            logging.warning(f"- Không tìm thấy file: {exam_path}")

        # 2. Nạp dữ liệu điểm chuẩn / ngành nghề (Master)
        master_path = 'data/master/master_admission.csv'
        if os.path.exists(master_path):
            df_master = pd.read_csv(master_path, encoding='utf-8-sig')
            self._data_cache['master_data'] = df_master
            logging.info(f"- Đã nạp dữ liệu Master: {len(df_master)} dòng.")
        else:
            logging.warning(f"- Không tìm thấy file: {master_path}")
            
    def get_exam_data(self):
        """Cung cấp dữ liệu điểm thi cho Recommendation Service"""
        return self._data_cache.get('exam_data', pd.DataFrame())

    def get_master_data(self):
        """Cung cấp dữ liệu tiêu chí ngành cho AHP/TOPSIS"""
        return self._data_cache.get('master_data', pd.DataFrame())

# Khởi tạo sẵn một instance toàn cục để app.py import
data_repo = DataRepository()

# Dành riêng cho việc test module độc lập
if __name__ == "__main__":
    print("=== TEST DATA REPOSITORY ===")
    repo = DataRepository()
    print("Các bảng đã cache:", repo._data_cache.keys())