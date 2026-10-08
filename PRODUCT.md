# Product

<!-- impeccable:product-schema 1 -->

## Platform

Web application.

## Stack

HTML, CSS và JavaScript thuần ở frontend; Python/Flask ở backend; pandas, scikit-learn và XGBoost cho xử lý dữ liệu và dự báo.

## Users

Học sinh THPT muốn lập danh sách trường/ngành tham khảo sau khi có hoặc ước lượng điểm thi.

## Product Purpose

Hệ thống DSS biến điểm ba môn của người dùng thành một danh sách ngắn phương án tuyển sinh. Mỗi phương án được phân thành An toàn, Phù hợp hoặc Thử sức và kèm bối cảnh nghề nghiệp để hỗ trợ cân nhắc.

## Active Decision Flow

1. Người dùng chọn tổ hợp, nhập điểm và có thể chọn nhóm ngành/khu vực.
2. Backend lọc `master_admission.csv` theo tổ hợp và điều kiện đã chọn.
3. Với các phương án có feature hợp lệ, model XGBoost gắn mốc điểm dự báo 2025; các phương án còn lại dùng điểm chuẩn 2024 làm fallback.
4. Hệ thống tính chênh lệch điểm, loại phương án thấp hơn quá 3 điểm so với mốc và xếp hạng phần còn lại bằng Content-Based Filtering (độ khớp hồ sơ sở thích-ngành) kết hợp weighted scoring.
5. Giao diện hiển thị tối đa 15 phương án cho từng nhóm và cho phép lưu nguyện vọng cục bộ.

## Data and Constraints

- Điểm chuẩn dùng cho mô hình: 2018–2024; output forecast hiện tại là năm 2025.
- `master_admission.csv`, phổ điểm thi tổng hợp và summary VietJobs đã được tích hợp vào luồng đang chạy.
- Dữ liệu thô có thể chứa SBD, nhưng ứng dụng chỉ nạp bảng phổ điểm tổng hợp không có SBD.
- Kết quả là gợi ý tham khảo; không thể hiện xác suất trúng tuyển hoặc cam kết việc làm.
- Danh sách nguyện vọng và profile chỉ lưu trong `localStorage`, không có đăng nhập hay đồng bộ thiết bị.

## Product Principles

1. Giải thích được: hiển thị mốc điểm và chênh lệch thay vì kết luận tuyệt đối.
2. Tập trung vào luồng DSS cốt lõi: điểm đầu vào → lọc → xếp hạng → danh sách nguyện vọng.
3. Tách dữ liệu lịch sử, dự báo và bối cảnh việc làm.
4. Bảo vệ dữ liệu cá nhân: không tra cứu hay công khai điểm theo SBD.

## Non-goals for This Course Project

- Không phải cổng tuyển sinh chính thức hay hệ thống đăng ký nguyện vọng.
- Không cập nhật điểm chuẩn thời gian thực.
- Không có tài khoản người dùng, thanh toán, thông báo hay đồng bộ cloud.
- Logo trường, hồ sơ cá nhân hoá sâu và dữ liệu tuyển sinh các năm mới là hướng phát triển, không phải phần cốt lõi của bản nộp.
