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
│   └── master/                  # Dành cho bảng danh mục tham chiếu
│       └── danh_muc_nganh_chuan.json
├── cleaned/                     # Dữ liệu sau làm sạch và chuẩn hóa
└── processed/                   # Dữ liệu đã tổng hợp, sẵn sàng phân tích
    ├── university_admissions_2025_2026.csv
    └── university_admissions.db (SQLite)
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
- [x] Xây dựng công cụ cào dữ liệu tuyển sinh, học phí, mô tả ngành và việc làm
- [x] Bổ sung danh mục ngành và bảng mapping ngành–nghề
- [ ] Làm sạch, chuẩn hóa schema giữa các năm
- [ ] Tạo bảng tổng hợp phục vụ phân tích và hệ thống gợi ý
