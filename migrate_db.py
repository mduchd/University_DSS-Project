import pandas as pd
from sqlalchemy import create_engine, text
from pathlib import Path

# Cấu hình CSDL Cloud (Neon - PostgreSQL)
CONNECTION_STRING = "postgresql+psycopg2://neondb_owner:npg_9WInofGih6qx@ep-bold-boat-azdvc0lj-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
engine = create_engine(CONNECTION_STRING)
ROOT = Path(__file__).resolve().parent

def run_migration():
    print("🚀 Bắt đầu chuyển đổi dữ liệu từ CSV sang PostgreSQL (Neon Cloud)...")
    
    # 0. KHỞI TẠO BẢNG & DỌN DẸP DỮ LIỆU
    print("- Đang kiểm tra cấu trúc bảng trên Cloud và dọn dẹp...")
    with engine.begin() as conn:
        # Tạo bảng tự động theo chuẩn PostgreSQL nếu chưa có
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS subject_combinations (
                id SERIAL PRIMARY KEY,
                code VARCHAR(10) UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS universities (
                id SERIAL PRIMARY KEY,
                uni_code VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS majors (
                id SERIAL PRIMARY KEY,
                major_code VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                major_group_code VARCHAR(50),
                major_group_name VARCHAR(255)
            );
            CREATE TABLE IF NOT EXISTS job_categories (
                id SERIAL PRIMARY KEY,
                category_name VARCHAR(255) UNIQUE NOT NULL,
                demand_level VARCHAR(50),
                posting_count INT DEFAULT 0,
                avg_salary_million DECIMAL(5,2),
                median_salary_million DECIMAL(5,2)
            );
            CREATE TABLE IF NOT EXISTS admission_options (
                id SERIAL PRIMARY KEY,
                university_id INT,
                major_id INT,
                combination_id INT,
                year INT NOT NULL,
                cutoff_score DECIMAL(5,2),
                cutoff_score_30 DECIMAL(5,2),
                CONSTRAINT unique_admission UNIQUE (university_id, major_id, combination_id, year)
            );
        """))
        
        # Xóa sạch dữ liệu cũ (nếu có) bằng TRUNCATE CASCADE an toàn hơn DELETE
        conn.execute(text("TRUNCATE TABLE admission_options, subject_combinations, majors, universities, job_categories RESTART IDENTITY CASCADE;"))
    
    # 1. Đọc file CSV
    master_path = ROOT / "data" / "master" / "master_admission.csv"
    jobs_path = ROOT / "data" / "processed" / "jobs" / "job_market_summary_by_category.csv"
    
    print("- Đang đọc file CSV...")
    df_master = pd.read_csv(master_path, encoding="utf-8-sig")
    df_jobs = pd.read_csv(jobs_path, encoding="utf-8-sig")
    
    # 2. Xử lý và import bảng universities
    print("- Đang import bảng Universities (Trường đại học)...")
    df_uni = df_master[['university_admission_code', 'university_name']].drop_duplicates()
    df_uni = df_uni.rename(columns={'university_admission_code': 'uni_code', 'university_name': 'name'})
    df_uni.to_sql('universities', con=engine, if_exists='append', index=False)
    uni_db = pd.read_sql("SELECT id, uni_code FROM universities", con=engine)
    
    # 3. Xử lý và import bảng majors
    print("- Đang import bảng Majors (Ngành học)...")
    df_major = df_master[['major_code', 'major_name', 'major_group_code', 'major_group_name']].drop_duplicates(subset=['major_code'])
    df_major = df_major.rename(columns={'major_name': 'name'})
    df_major.to_sql('majors', con=engine, if_exists='append', index=False)
    major_db = pd.read_sql("SELECT id, major_code FROM majors", con=engine)
    
    # 4. Xử lý và import bảng subject_combinations
    print("- Đang import bảng Subject Combinations (Tổ hợp môn)...")
    df_combo = df_master[['subject_combination']].drop_duplicates()
    df_combo = df_combo.rename(columns={'subject_combination': 'code'})
    df_combo.to_sql('subject_combinations', con=engine, if_exists='append', index=False)
    combo_db = pd.read_sql("SELECT id, code FROM subject_combinations", con=engine)
    
    # 5. Xử lý và import bảng job_categories
    print("- Đang import bảng Job Categories (Nhóm nghề nghiệp)...")
    df_jobs_clean = pd.DataFrame()
    df_jobs_clean['category_name'] = df_jobs.get('category_name', df_jobs.get('job_category', ''))
    df_jobs_clean['posting_count'] = df_jobs.get('posting_count', df_jobs.get('job_posting_count', 0))
    df_jobs_clean['avg_salary_million'] = df_jobs.get('average_salary_million_vnd', df_jobs.get('job_avg_salary_million', 0.0))
    df_jobs_clean['median_salary_million'] = df_jobs.get('median_salary_million_vnd', df_jobs.get('job_median_salary_million', 0.0))
    df_jobs_clean['demand_level'] = 'Ổn định'
    
    df_jobs_clean = df_jobs_clean[df_jobs_clean['category_name'] != '']
    df_jobs_clean.to_sql('job_categories', con=engine, if_exists='append', index=False)
    
    # 6. Import bảng admission_options (Bảng quan trọng nhất chứa điểm chuẩn)
    print("- Đang xử lý Mapping ID và import bảng Admission Options...")
    df_admin = df_master.copy()
    
    df_admin['year'] = df_admin.get('year', df_admin.get('Year', df_admin.get('nam', 2024)))
    df_admin['cutoff_score'] = df_admin.get('cutoff_score', df_admin.get('diem_chuan', 0.0))
    df_admin['cutoff_score_30'] = df_admin.get('cutoff_score_30', df_admin.get('diem_chuan_30', df_admin['cutoff_score']))
    
    df_admin = df_admin.merge(uni_db, left_on='university_admission_code', right_on='uni_code', how='left').rename(columns={'id': 'university_id'})
    df_admin = df_admin.merge(major_db, left_on='major_code', right_on='major_code', how='left').rename(columns={'id': 'major_id'})
    df_admin = df_admin.merge(combo_db, left_on='subject_combination', right_on='code', how='left').rename(columns={'id': 'combination_id'})
    
    df_admin_final = df_admin[['university_id', 'major_id', 'combination_id', 'year', 'cutoff_score', 'cutoff_score_30']]
    df_admin_final = df_admin_final.dropna(subset=['university_id', 'major_id', 'combination_id'])
    df_admin_final = df_admin_final.drop_duplicates(subset=['university_id', 'major_id', 'combination_id', 'year'])
    
    df_admin_final.to_sql('admission_options', con=engine, if_exists='append', index=False)
    
    print("✅ HOÀN TẤT! Toàn bộ dữ liệu đã được migrate thành công vào PostgreSQL trên Cloud.")

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {e}")