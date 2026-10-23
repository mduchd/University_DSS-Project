import pandas as pd

df = pd.read_csv('data/cleaned/exam/diemthi_2021_cleaned.csv', dtype={'SBD': str})
print("=== BÁO CÁO KIỂM TRA CHẤT LƯỢNG DỮ LIỆU ===")

print(f"1. Số dòng trùng lặp: {df.duplicated().sum()} (Kỳ vọng: 0)")
print(f"2. Tổng số ô bị trống (NaN): {df.isna().sum().sum()} (Kỳ vọng: 0)")

# Chỉ quét dải điểm từ -1 đến 10 cho các môn học đơn lẻ
subject_cols = ['Toan', 'NguVan', 'VatLy', 'HoaHoc', 'SinhHoc', 'LichSu', 'DiaLy', 'GDCD', 'NgoaiNgu']
invalid_scores = 0

for col in subject_cols:
    if col in df.columns: # Kiểm tra xem cột môn học có tồn tại trong file không
        invalid_mask = (df[col] < -1.0) | (df[col] > 10.0)
        invalid_scores += invalid_mask.sum()

print(f"3. Điểm dị biệt (ngoài dải -1 đến 10): {invalid_scores} (Kỳ vọng: 0)")

if df.duplicated().sum() == 0 and df.isna().sum().sum() == 0 and invalid_scores == 0:
    print("\n=> KẾT LUẬN: Dữ liệu đã sạch 100%, sẵn sàng cho bước Processed!")
else:
    print("\n=> CẢNH BÁO: Dữ liệu vẫn còn rác, cần review lại script Cleaned.")