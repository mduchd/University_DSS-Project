# DSS Dataset — Hỗ trợ lựa chọn ngành học và trường đại học

Kho dữ liệu cho đề tài **“Xây dựng hệ thống hỗ trợ ra quyết định trong lựa chọn ngành học và trường đại học cho học sinh THPT.”**

Mục tiêu của bộ dữ liệu là hỗ trợ phân tích và gợi ý tham khảo dựa trên ba góc nhìn:

- **Năng lực đầu vào:** điểm thi tốt nghiệp THPT.
- **Khả năng trúng tuyển:** điểm chuẩn theo trường, ngành và tổ hợp xét tuyển.
- **Thị trường lao động:** tin tuyển dụng, kỹ năng, địa điểm và thông tin lương (nếu có).

> Hệ thống chỉ nhằm cung cấp gợi ý tham khảo, không thay thế quyết định cá nhân hoặc tư vấn tuyển sinh chính thức.

## Cấu trúc repository

```text
data/
├── raw/                         # Dữ liệu gốc, không chỉnh sửa trực tiếp
│   ├── admission/
│   │   ├── diemchuan_2018_2023.xlsx
│   │   ├── diemchuan_2024.csv
│   │   └── university_admissions_2025_2026.csv   # Dữ liệu cào mới có học phí & mô tả
│   ├── exam/
│   │   ├── diemthi_2021.csv
│   │   ├── diemthi_2022.csv
│   │   ├── diemthi_2023.csv
│   │   ├── diemthi_2024.csv
│   │   ├── diemthi_2025_ct2006.csv
│   │   └── diemthi_2025_ct2018.csv
│   ├── jobs/
│   │   └── VietJobs/
│   │       └── VietJobs.csv
│   └── master/                  # Dữ liệu danh mục gốc
│       └── danh_muc_nganh_chuan.json
├── cleaned/                     # Dữ liệu sau làm sạch và chuẩn hóa
│   ├── admission/
│   ├── exam/
│   └── jobs/
├── master/                      # Data contract và danh mục chuẩn dùng chung
├── processed/                   # Dữ liệu chuẩn hóa/tổng hợp, sẵn sàng phân tích
│   ├── exam/                    # Điểm thi đã chuẩn hóa theo năm/chương trình
│   ├── university_admissions_2026_2025.csv
│   └── university_admissions.db # SQLite
scripts/
├── crawler/                     # Module cào dữ liệu tuyển sinh & làm giàu ngành học
│   ├── __init__.py
│   ├── config.py
│   ├── school_scraper.py
│   ├── admission_scraper.py
│   ├── major_enricher.py
│   ├── pipeline.py
│   └── cli.py
└── run_crawler.py               # Launcher dòng lệnh
```

`raw/` luôn được giữ nguyên so với dữ liệu đã tải. Toàn bộ thao tác loại trùng, đổi kiểu dữ liệu, chuẩn hóa tên cột hoặc mapping phải tạo kết quả mới trong `cleaned/` hoặc `processed/`.

## Nguồn dữ liệu

| Nhóm dữ liệu | Phạm vi | Nguồn |
| --- | --- | --- |
| Điểm chuẩn đại học | 2018–2024 | [HTNam1710/ADS_Final](https://github.com/HTNam1710/ADS_Final) |
| Tuyển sinh, Điểm chuẩn & Học phí | 2025–2026 | Cổng thông tin Tuyển sinh Đại học (UniCrawler) |
| Điểm thi tốt nghiệp THPT | 2021–2025 | [sdgedfegw/du-lieu-diem-thi](https://github.com/sdgedfegw/du-lieu-diem-thi) |
| Tin tuyển dụng Việt Nam | VietJobs | [dinhieufam/VietJobs](https://huggingface.co/datasets/dinhieufam/VietJobs) |
| Danh mục chuẩn ngành học | Cấp 4 | Thông tư 09/2022/TT-BGDĐT |

Các file được lấy riêng theo năm thay vì dùng một file điểm thi tổng hợp để quá trình kiểm tra schema, làm sạch và chuẩn hóa có thể được tái lập rõ ràng.

## Lưu ý dữ liệu

- Hai file điểm thi năm 2025 được tách theo **chương trình 2006** và **chương trình 2018**. Không nên so sánh trực tiếp phân phối điểm 2025 với các năm trước mà không nêu rõ sự khác biệt chương trình và môn thi.
- Dữ liệu điểm thi có cột `SBD`. Không công bố lại bản ghi cá nhân, kết quả truy vấn theo số báo danh hoặc dashboard có thể nhận diện cá nhân.
- Việc liên kết ngành học với thị trường việc làm cần một bảng mapping rõ ràng, ví dụ `major_code`, `major_name`, `major_group`, `job_category`, `mapping_confidence`.
- Một số file CSV lớn hơn 50 MB. GitHub đã chấp nhận chúng, nhưng Git LFS nên được cân nhắc nếu dữ liệu tiếp tục tăng.

## Công cụ cào dữ liệu tuyển sinh & ngành học (UniCrawler)

Repository tích hợp module cào dữ liệu tự động tại `scripts/crawler/` và entry point `run_crawler.py`, thu thập đầy đủ 8 trường thông tin:
1. **Mã ngành**
2. **Tên ngành**
3. **Trường** (Mã trường, Tên trường)
4. **Tổ hợp xét tuyển**
5. **Học phí**
6. **Chương trình đào tạo**
7. **Mô tả ngành**
8. **Cơ hội nghề nghiệp**

### Cách sử dụng:

```powershell
# 1. Cào thử nghiệm N trường tiêu biểu:
python run_crawler.py --limit 5

# 2. Cào các trường theo mã (ví dụ NEU, HUST, UET):
python run_crawler.py --schools KHA,BKA,QHI --years 2025,2026

# 3. Cào toàn diện tất cả các trường trên cả nước trong 2 năm gần nhất:
python run_crawler.py --formats csv,json,sqlite
```

Dữ liệu kết quả được lưu tại:
- `data/raw/admission/university_admissions_{years}.csv` và `.json`
- `data/processed/university_admissions_{years}.csv` và `university_admissions.db` (SQLite)
- `data/raw/master/danh_muc_nganh_chuan.json`

## Quy trình đề xuất

```text
raw
  → kiểm tra schema, giá trị thiếu, trùng lặp và kiểu dữ liệu
  → cleaned
  → chuẩn hóa mã/tên trường, ngành, tổ hợp, tỉnh/thành và nhóm nghề
  → processed
  → phân tích, dashboard hoặc mô hình gợi ý
```

## Trạng thái

- [x] Tải dữ liệu gốc về `data/raw/`
- [x] Làm sạch dữ liệu điểm chuẩn, điểm thi và VietJobs
- [x] Chuẩn hóa dữ liệu điểm thi 2021–2025 sang cùng một schema
- [x] Tạo bảng tổng hợp điểm thi theo năm, chương trình và mã tỉnh
- [x] Chuẩn hóa dữ liệu điểm chuẩn 2018–2024 sang cùng một schema
- [x] Chuẩn hóa VietJobs sang cùng một schema
- [x] Tạo danh mục ngành và bảng mapping ngành–nghề
- [x] Xây dựng công cụ cào dữ liệu tuyển sinh, học phí và thông tin ngành
- [ ] Tạo bảng tổng hợp phục vụ hệ thống gợi ý

## Làm sạch điểm chuẩn 2018–2023

Chạy script sau để tạo một bản dữ liệu clean. File gốc trong `data/raw/` không bị thay đổi.

```bash
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\clean_diemchuan_2018_2023.py
```

Kết quả: `data/cleaned/admission/diemchuan_2018_2023_cleaned.csv`.

## Làm sạch tin tuyển dụng VietJobs

```bash
.\.venv\Scripts\python scripts\clean_vietjobs.py
```

Kết quả: `data/cleaned/jobs/VietJobs_cleaned.csv`. File raw được giữ nguyên.

## Làm sạch điểm thi 2021–2022

```powershell
.\.venv\Scripts\python scripts/clean_exam.py
```

Kết quả:

- `data/cleaned/exam/diemthi_2021_cleaned.csv`
- `data/cleaned/exam/diemthi_2022_cleaned.csv`

Các file gốc trong `data/raw/exam/` được giữ nguyên.

## Chuẩn hóa điểm thi 2021–2025

Script chuẩn hóa các file trong `data/cleaned/exam/` sang một schema chung,
đồng thời tính lại các tổ hợp A00, A01, A02, B00, C00, C01, C02, D01 và D07.
Contract cột nằm tại `data/master/exam_schema.csv`.

```powershell
.\.venv\Scripts\python scripts\standardize_exam.py
```

Kết quả nằm trong `data/processed/exam/`:

- `scores_*.csv`: dữ liệu bản ghi đã chuẩn hóa, chỉ dùng cho phân tích nội bộ.
- `exam_score_summary_by_year_province.csv`: bảng tổng hợp an toàn hơn cho ứng dụng; không có số báo danh.
- `standardization_report.json`: số dòng đã xử lý và schema đầu ra.

Không hiển thị `candidate_id` hoặc `candidate_number` trong giao diện hay API công khai.

## Chuẩn hóa điểm chuẩn 2018–2024

Script hợp nhất hai nguồn điểm chuẩn đã clean thành một schema chung. Chỉ các
dòng `THPTQG` dùng thang 30 hoặc 40 có `cutoff_score_30`; các phương thức học
bạ, DGNL và DGTD giữ nguyên thang điểm nguồn để tránh so sánh sai.

```powershell
.\.venv\Scripts\python scripts\standardize_admission.py
```

Kết quả nằm trong `data/processed/admission/`:

- `admission_cutoffs_2018_2024.csv`: 126.185 bản ghi điểm chuẩn canonical.
- `admission_cutoff_summary_by_year_major.csv`: thống kê xu hướng thang 30 theo năm, ngành và tổ hợp.
- `standardization_report.json`: nguồn đầu vào, số dòng và schema đầu ra.

Contract cột nằm tại `data/master/admission_schema.csv`.

## Chuẩn hóa VietJobs

Script chuẩn hóa các tin tuyển dụng thành bản ghi có `job_id` ổn định, lương
triệu VND/tháng và kinh nghiệm theo tháng. Các trường kỹ năng, bằng cấp, ngôn
ngữ và phúc lợi được lưu dưới dạng JSON list. Script không tự suy đoán ngành
học phù hợp với nghề; quan hệ đó được tạo ở bước mapping sau.

```powershell
.\.venv\Scripts\python scripts\standardize_vietjobs.py
```

Kết quả nằm trong `data/processed/jobs/`:

- `vietjobs_postings.csv`: 47.698 tin tuyển dụng canonical.
- `job_market_summary_by_category.csv`: tổng hợp số tin, lương và kinh nghiệm theo nhóm nghề.
- `standardization_report.json`: số dòng và các bản ghi cần rà soát.

Contract cột nằm tại `data/master/jobs_schema.csv`.

## Mapping ngành học với nhóm nghề

Script tạo catalog ngành từ dữ liệu điểm chuẩn và mapping một ngành sang nhóm
nghề VietJobs bằng quy tắc từ khóa có thể kiểm tra. Mỗi liên kết ghi rõ cơ sở
mapping và mức tin cậy; mapping chỉ thể hiện liên quan chủ đề, không phải cam
kết việc làm.

```powershell
.\.venv\Scripts\python scripts\build_major_job_mapping.py
```

Kết quả trong `data/master/`:

- `major_catalog.csv`: 4.125 tổ hợp mã/tên/nhóm ngành có trong dữ liệu điểm chuẩn.
- `major_job_mapping.csv`: 3.992 liên kết ngành–nhóm nghề (coverage 96,78%).
- `unmapped_majors.csv`: 133 ngành cần quyết định thủ công thay vì tự suy đoán.
- `major_job_mapping_report.json`: coverage, mức tin cậy và quy tắc áp dụng.

Contract của bảng mapping nằm tại `data/master/major_job_mapping_schema.csv`.

## Chạy giao diện web

Giao diện MVP dùng **HTML, CSS, JavaScript** và **Flask**. Nó hiện đối chiếu điểm người dùng với dữ liệu điểm chuẩn 2024, theo các tổ hợp `A00`, `A01`, `B00`, `C00` và `D01`.

```bash
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Sau đó mở `http://127.0.0.1:5000` trên trình duyệt.

Các phần VietJobs và xu hướng nhiều năm đã có vị trí trong giao diện, nhưng chỉ được cá nhân hóa sau khi hoàn tất cleaning và bảng mapping ngành–nghề.
