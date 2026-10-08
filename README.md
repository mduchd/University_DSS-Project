# La Bàn Đại Học — Hệ thống hỗ trợ lựa chọn ngành và trường

Đây là đồ án môn học về **hệ thống hỗ trợ ra quyết định (DSS)** cho học sinh THPT. Hệ thống nhận tổ hợp và điểm ba môn, đối chiếu dữ liệu điểm chuẩn lịch sử, sau đó trả về các phương án theo ba mức: **An toàn**, **Phù hợp** và **Thử sức**.

> Kết quả là gợi ý tham khảo, không phải cam kết trúng tuyển hay dự báo xác suất đỗ.

## Chức năng đang chạy

- Nhập điểm theo 10 tổ hợp xét tuyển: `A00`, `A01`, `A02`, `B00`, `B08`, `C00`, `C01`, `C02`, `D01`, `D07`.
- Lọc theo nhóm ngành, khu vực và từ khóa trường/ngành; chấm `interest_fit` từ hồ sơ sở thích đã chọn.
- Phân loại phương án bằng chênh lệch giữa tổng điểm của người dùng và mốc điểm chuẩn dự báo/tham chiếu.
- Xếp hạng content-based theo độ khớp điểm, sở thích-ngành, lương tham khảo, nhu cầu tuyển dụng và độ ổn định của lịch sử điểm chuẩn.
- Tra cứu điểm chuẩn, xem bối cảnh nghề nghiệp và lưu danh sách nguyện vọng trong trình duyệt.

Luồng recommendation hiện dùng Content-Based Filtering kết hợp weighted scoring: sở thích được đối chiếu minh bạch với đặc trưng của ngành/trường, không sử dụng Collaborative Filtering vì hệ thống chưa có dữ liệu tương tác đa người dùng. Mô-đun AHP + TOPSIS trong `services/decision_engine.py` chỉ được giữ để tham khảo, không nằm trên đường đi của API.

## Kiến trúc

```text
Browser (HTML/CSS/JS)
        │ POST /api/recommend
        ▼
Flask API
        │
        ├─ master_admission.csv: lọc phương án tuyển sinh
        ├─ model.joblib: dự báo mốc điểm chuẩn 2025
        ├─ VietJobs summaries: bối cảnh việc làm
        └─ content-based scoring: xếp hạng và phân nhóm
```

- Frontend: HTML, CSS, JavaScript thuần.
- Backend: Flask, pandas, scikit-learn, XGBoost.
- Deploy: Vercel host frontend và chuyển `/api/*` tới Flask API trên Render.

## Dữ liệu đang dùng

| Dữ liệu | Vai trò | Quy mô hiện có |
| --- | --- | ---: |
| Điểm chuẩn 2018–2024 | Huấn luyện/đánh giá mô hình | 126.185 dòng canonical; 86.064 dòng hợp lệ cho modeling |
| `master_admission.csv` | Lọc và hiển thị phương án trong ứng dụng | 19.983 dòng |
| Phổ điểm thi tổng hợp | Feature bối cảnh theo tổ hợp | 384 dòng tổng hợp, không có SBD |
| VietJobs đã chuẩn hoá | Lương, nhu cầu và kỹ năng theo nhóm nghề | 47.698 tin; 16 nhóm nghề tổng hợp |
| Mapping ngành–nghề | Ghép ngành với bối cảnh việc làm | 3.992 mapping; 133 ngành chưa map |

Nguồn và quy trình làm sạch/model được trình bày tại [docs/data-model-report.md](docs/data-model-report.md). Dữ liệu 2025–2026 do crawler thu thập được lưu riêng để tham khảo, **chưa được đưa vào mô hình hay mốc hiển thị của luồng recommendation hiện tại**.

## Chạy cục bộ

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Mở `http://127.0.0.1:5000`.

## Kiểm thử

```powershell
.\.venv\Scripts\python -m pytest -q
```

Test bao phủ làm sạch dữ liệu, feature/model dự báo, validation payload, recommendation và decision engine tham khảo.

## Phạm vi và giới hạn

- Mô hình dùng dữ liệu điểm chuẩn 2018–2024 để tạo **mốc dự báo 2025**; đây là thí nghiệm lịch sử, không phải mốc tuyển sinh thời gian thực.
- Trường/ngành chưa có lịch sử (cold-start) có sai số cao hơn; hệ thống giữ fallback lịch sử thay vì tạo dữ liệu giả.
- Danh sách nguyện vọng chỉ lưu ở `localStorage`, không có tài khoản hay đồng bộ nhiều thiết bị.
- Không có tra cứu số báo danh hoặc dữ liệu cá nhân của thí sinh trong API/giao diện công khai.

## Cấu trúc chính

```text
app.py                              Flask routes
services/recommendation_service.py  Lọc, dự báo và xếp hạng
services/cutoff_forecast_service.py Feature store và batch prediction
models/                             Artifact model, training và evaluation
data/master/                        Dataset tích hợp dùng cho ứng dụng
data/processed/                     Dataset/report trung gian và tổng hợp
docs/data-model-report.md           Tài liệu Data & Model cho báo cáo môn học
tests/                              Automated tests
```
