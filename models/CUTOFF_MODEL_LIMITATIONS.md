# Mô hình dự báo điểm chuẩn: phạm vi, giới hạn và integration contract

## Phạm vi và khả năng tái lập

- Target là `cutoff_score_30`, được giới hạn trong miền giá trị đã thống nhất `[0, 30]`.
- Dữ liệu modeling gồm các quan sát điểm chuẩn theo phương thức THPTQG trong giai đoạn 2018–2024.
- Dữ liệu được chia theo thời gian cố định: train `<= 2022`, validation `2023`, test `2024`.
- Quá trình lựa chọn model chỉ sử dụng validation 2023. Test 2024 chỉ được sử dụng một lần sau khi cấu hình đã được khóa.
- Có thể huấn luyện lại bằng lệnh `python models/train_cutoff_model.py` và kiểm tra bằng lệnh `python -m pytest -q`.

## Giới hạn của dữ liệu nguồn

- Dữ liệu nguồn có 126.185 dòng; trong đó 86.064 dòng được chấp nhận cho modeling và 39.513 dòng bị loại với lý do có thể truy vết, kiểm tra lại.
- Các trường hợp bị loại gồm: phương thức không phải THPT, target bị thiếu hoặc không phải số, tổ hợp môn không hợp lệ, sai thang điểm và có nhiều điểm chuẩn xung đột trên cùng một modeling key.
- Có 4.481 nhóm khóa bị xung đột và tiếp tục bị loại cho đến khi có nguồn chính thức để xác minh. Không có dòng dữ liệu mơ hồ nào được tự động đưa trở lại tập modeling.
- Trường hợp tái sử dụng mã trường hoặc mã chương trình được xử lý theo hướng thận trọng. Những alias có khả năng trùng nhau chỉ được đưa vào danh sách cần rà soát, không được tự động merge.
- Trường `major_group` của năm 2024 gần như bị thiếu hoàn toàn trong dữ liệu nguồn hiện tại. Vì vậy, các metric được chia theo nhóm ngành chỉ có giá trị tham khảo hạn chế.

Thông tin chi tiết về các dòng bị loại và kết quả rà soát định danh được lưu tại:

- `data/processed/admission_ml_quality_report.json`
- `data/processed/admission_ml_rejected.csv`
- `data/processed/admission_ml_rejection_review.csv`
- `data/processed/admission_ml_step2_report.json`
- `data/processed/admission_ml_high_priority_report.json`

## Cold start

- Một program series được xác định là true cold start khi không có bất kỳ quan sát nào của chính program series đó trong các năm trước.
- Trong test 2024, có 11.572 trên tổng số 19.827 dòng (58,36%) thuộc nhóm true cold start.
- MAE năm 2024 của model được chọn là 1,603 đối với nhóm `known_history` và 2,839 đối với nhóm `cold_start`. Vì vậy, dự báo cho nhóm cold start có độ tin cậy thấp hơn đáng kể.
- Các giá trị lịch sử bị thiếu vẫn được giữ là missing value và được xử lý bởi fitted pipeline; chúng không bao giờ được điền bằng 0.
- Dữ liệu fallback được sử dụng theo thứ tự phân cấp: trường + tổ hợp, nhóm ngành + tổ hợp, trường, nhóm ngành, tổ hợp và cuối cùng là lịch sử toàn cục.

## Thời điểm dự báo và ranh giới chống data leakage

- Mỗi feature của năm `t` chỉ được tính từ dữ liệu của các năm trước `t`.
- Các feature về phân phối điểm thi sử dụng dữ liệu của năm `t-1`, không sử dụng phân phối điểm thi của chính năm `t`.
- Nếu sản phẩm sau này chuyển từ dự báo trước kỳ thi sang dự báo sau khi đã có điểm thi, sự thay đổi về thời điểm này phải được versioning và ghi rõ trong tài liệu. Dữ liệu điểm thi của năm hiện tại không được âm thầm bổ sung vào model này.

## Output contract

Predictor trả về kết quả theo cấu trúc:

```json
{
  "university": "UIT",
  "major": "Công nghệ thông tin",
  "year": 2025,
  "predicted_cutoff": 26.35,
  "model_version": "cutoff_v1",
  "is_cold_start": false
}
```

`predicted_cutoff` là giá trị ước lượng từ bài toán regression, không phải xác suất trúng tuyển. Backend không được trả về `chance_of_admission` hoặc mô tả kết quả này là “xác suất đỗ”. Ở bước sau, decision layer có thể so sánh điểm của học sinh với `predicted_cutoff`, nhưng kết quả so sánh đó không phải là một calibrated probability.

## Dependency cho quá trình tích hợp

Hiện tại chưa có file `integrated_dataset.csv`. Trước khi thay thế dữ liệu admission đang sử dụng, người phụ trách Data Integration và người phụ trách Machine Learning cần thống nhất và khóa các nội dung sau:

- program identity/key;
- tên và kiểu dữ liệu của các cột;
- thời điểm sử dụng các feature về phân phối điểm thi;
- chính sách xử lý cold start;
- cách bàn giao danh sách các dòng bị loại;
- dataset version.

Model pipeline vẫn có thể chạy khi chưa có file này. Tuy nhiên, ứng dụng hoàn chỉnh của nhóm chưa được xem là đã tích hợp cho đến khi backend cung cấp đầy đủ các engineered feature bắt buộc và sử dụng `predicted_cutoff` theo đúng contract nêu trên.
