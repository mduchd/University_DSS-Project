# Báo cáo Data & Model

## 1. Mục tiêu

Mô-đun dữ liệu và mô hình hỗ trợ luồng DSS của hệ thống: từ điểm ba môn của học sinh, hệ thống lọc phương án trường-ngành, ước lượng một mốc điểm chuẩn và xếp các phương án thành An toàn, Phù hợp hoặc Thử sức. Kết quả chỉ dùng để tham khảo, không phải xác suất trúng tuyển.

## 2. Nguồn dữ liệu và quy mô

| Thành phần | Phạm vi | Số dòng | Mục đích |
| --- | --- | ---: | --- |
| Điểm chuẩn canonical | 2018–2024 | 126.185 | Nguồn đầu vào cho pipeline model |
| Điểm chuẩn hợp lệ cho model | 2018–2024 | 86.064 | Huấn luyện, validation và test |
| Master admission | Luồng ứng dụng | 19.983 | Lọc/xếp hạng phương án trả về UI |
| Phổ điểm tổng hợp | 2021–2025 | 384 | Feature bối cảnh, không chứa SBD |
| Tin VietJobs chuẩn hoá | Khảo sát việc làm | 47.698 | Tổng hợp lương, nhu cầu, kỹ năng |
| Mapping ngành–nghề | Theo mã/tên ngành | 3.992 | Ghép bối cảnh việc làm; còn 133 ngành chưa map |

Nguồn dữ liệu được lưu theo lớp `raw` → `cleaned` → `processed`/`master`. Bản ghi thô không bị sửa trực tiếp. API công khai chỉ dùng các bảng đã tổng hợp và không nhận/tra cứu số báo danh.

## 3. Làm sạch và chuẩn bị dữ liệu điểm chuẩn

Từ 126.185 dòng canonical, pipeline chỉ giữ phương án xét tuyển `THPTQG` có điểm chuẩn chuẩn hoá trong `[0, 30]` và tổ hợp hợp lệ theo mẫu `A00`, `D01`, … Các bước chính:

1. Loại phương thức không thuộc phạm vi THPTQG, điểm thiếu/không phải số và sai thang điểm.
2. Chuẩn hoá mã trường, mã ngành/chương trình, tổ hợp và điểm chuẩn về `cutoff_score_30`.
3. Dùng khóa thời gian `(year, university_admission_code, major_admission_code, subject_combination)` để kiểm tra trùng lặp.
4. Gộp nhóm trùng khi có cùng mốc điểm; loại cả nhóm khi một khóa có nhiều mốc điểm mâu thuẫn, không tự chọn một giá trị.
5. Tách trường hợp tái sử dụng mã trường/chương trình theo tên chuẩn hoá; các trường hợp chưa rõ được đánh dấu để rà soát, không tự gộp.

Kết quả là 86.064 dòng hợp lệ. Có 39.513 dòng bị loại, trong đó 9.498 dòng có điểm chuẩn mâu thuẫn trên cùng khóa model. Báo cáo kiểm tra xác nhận target đầy đủ, trong miền `[0, 30]`, khóa model duy nhất và toàn bộ dòng nguồn được hạch toán.

## 4. Input và output của model

**Target:** `cutoff_score_30`, là điểm chuẩn đã chuẩn hoá về thang 30.

**Input:**

- Nhóm phân loại: mã trường tuyển sinh, định danh chương trình/ngành, nhóm ngành và tổ hợp môn.
- Lịch sử: điểm chuẩn gần nhất, lag 1–3 năm, trung bình, trung vị, độ lệch chuẩn, xu hướng và số năm quan sát.
- Context: thống kê theo trường, ngành, tổ hợp; phổ điểm của tổ hợp từ năm trước.

**Output:** `predicted_cutoff`, một ước lượng điểm chuẩn trong miền `[0, 30]`, kèm `model_version` và cờ `is_cold_start`. Output không có trường “xác suất đỗ”.

Trong ứng dụng, khi một phương án không ghép được feature dự báo hợp lệ, backend giữ điểm chuẩn lịch sử 2024 làm fallback. Mốc đó được dùng để tính `gap = tổng_điểm_người_dùng − mốc_tham_chiếu`.

## 5. Chia dữ liệu theo thời gian

| Tập | Năm | Số dòng | Vai trò |
| --- | --- | ---: | --- |
| Train | 2018–2022 | 55.713 | Huấn luyện mô hình |
| Validation | 2023 | 10.524 | Chọn cấu hình |
| Test | 2024 | 19.827 | Đánh giá một lần sau khi khóa cấu hình |

Việc chia theo thời gian thay vì ngẫu nhiên mô phỏng đúng bối cảnh dự báo: chỉ dùng dữ liệu của các năm trước để ước lượng năm sau. Test 2024 không được dùng để chỉnh siêu tham số.

## 6. Model, baseline và kết quả

Baseline được dùng để có mốc so sánh gồm trung bình lịch sử, giá trị năm gần nhất, trung bình nhóm và hybrid giữa giá trị gần nhất với trung bình nhóm. Model được chọn là **XGBoost (`xgboost_1`)** theo MAE trên validation 2023.

| Mô hình/nhóm | Tập đánh giá | MAE | RMSE | R² |
| --- | --- | ---: | ---: | ---: |
| XGBoost đã chọn | Validation 2023, toàn bộ | 1,360 | 1,931 | 0,785 |
| Baseline giá trị gần nhất | Test 2024, có lịch sử | 1,430 | 2,411 | 0,698 |
| XGBoost đã chọn | Test 2024, toàn bộ | 2,325 | 3,250 | 0,456 |
| XGBoost đã chọn | Test 2024, có lịch sử | 1,603 | 2,409 | 0,699 |
| XGBoost đã chọn | Test 2024, cold-start | 2,839 | 3,736 | 0,277 |

- **MAE** là độ lệch tuyệt đối trung bình, đơn vị là điểm chuẩn.
- **RMSE** phạt mạnh hơn các dự báo sai lệch lớn.
- **R²** phản ánh mức độ giải thích biến thiên trên tập đánh giá.

Baseline “giá trị gần nhất” chỉ phủ 41,64% test vì nhiều trường-ngành không có điểm năm trước, nên không thể so sánh trực tiếp với toàn bộ test. Model XGBoost dùng cơ chế fallback feature để dự báo cho toàn bộ 19.827 dòng.

## 7. Tích hợp vào DSS

```text
Điểm ba môn + tổ hợp + hồ sơ sở thích/khu vực/ưu tiên
        ↓
Lọc tổ hợp, nhóm ngành, khu vực và từ khóa cụ thể từ master admission
        ↓
XGBoost forecast hoặc historical fallback
        ↓
Tính gap và loại phương án gap < -3,0
        ↓
Content-Based Filtering + weighted scoring
        ↓
An toàn (gap ≥ 1) / Phù hợp (-1 ≤ gap < 1) / Thử sức (-3 ≤ gap < -1)
```

Khi không chọn sở thích, điểm xếp hạng kết hợp bốn tín hiệu: độ khớp điểm (0,40), lương tham khảo (0,25), nhu cầu việc làm (0,20) và độ ổn định lịch sử (0,15). Khi chọn sở thích, hệ thống dành 0,20 cho `interest_fit`; các trọng số ban đầu lần lượt là độ khớp điểm 0,35, lương 0,20, nhu cầu 0,15 và ổn định 0,10. Người dùng có thể thay đổi tương quan các trọng số bằng ưu tiên đã chọn.

`interest_fit` được tính minh bạch từ mapping sở thích → từ khóa đặc trưng trong tên ngành, nhóm ngành và nhóm nghề: **Công nghệ**, **Kinh doanh**, **Sáng tạo**, **Xã hội & cộng đồng**. Mỗi sở thích khớp được 1 điểm, sau đó lấy trung bình theo số sở thích đã chọn. Đây là Content-Based Filtering; hệ thống không dùng Collaborative Filtering vì chưa thu thập ma trận tương tác/rating từ nhiều học sinh. Từ khóa trường/ngành người dùng tự nhập là bộ lọc cụ thể, không phải dữ liệu huấn luyện.

## 8. Giới hạn và cách diễn giải

- Dữ liệu model kết thúc ở 2024 và output hiện tại là mốc dự báo 2025; không được trình bày như điểm chuẩn chính thức hoặc dự báo thời gian thực 2026.
- 58,36% test 2024 là cold-start (không có lịch sử của chính series chương trình); sai số của nhóm này cao hơn rõ rệt.
- Điểm chuẩn còn phụ thuộc đề thi, chỉ tiêu, quy chế, số lượng hồ sơ và từng chương trình đào tạo; model không quan sát hết các yếu tố này.
- Mapping ngành–nghề chỉ cung cấp bối cảnh lương và nhu cầu, không cam kết việc làm.
- Danh sách nguyện vọng là dữ liệu cục bộ trên trình duyệt, không phải chức năng đăng ký tuyển sinh.

## 9. Khả năng tái lập

```powershell
.\.venv\Scripts\python models\train_cutoff_model.py
.\.venv\Scripts\python -m pytest -q
```

Artifact triển khai là `models/model.joblib`; chỉ số chi tiết nằm tại `models/evaluation.json`. Báo cáo kiểm tra dữ liệu nằm tại `data/processed/admission_ml_quality_report.json` và `data/processed/admission_ml_step2_report.json`.
