# Decision Engine: AHP + TOPSIS

## Phạm vi

`services/decision_engine.py` xếp hạng các phương án trường-ngành độc lập với Flask, UI, CSV và mô hình ML. Backend có trách nhiệm lọc theo khu vực, ghép dữ liệu, và truyền `profile` cùng danh sách `candidates` vào `rank_candidates`.

## Năm tiêu chí TOPSIS

| Key | Ý nghĩa | Nguồn | Hướng |
| --- | --- | --- | --- |
| `academic_fit` | Độ phù hợp theo các môn xét tuyển | Điểm người dùng + trọng số môn ngành | benefit |
| `interest_fit` | Độ khớp sở thích-ngành | Mapping minh bạch | benefit |
| `admission_fit` | Mức cạnh tranh so với điểm chuẩn dự báo | Điểm người dùng + ML | benefit |
| `job_demand` | Nhu cầu việc làm tương đối | Feature VietJobs | benefit |
| `salary_score` | Điểm lương tham chiếu chuẩn hóa | Feature VietJobs | benefit |

`career_prospect` không tham gia TOPSIS để tránh đếm chồng với `job_demand` và `salary_score`; backend có thể dùng nó để giải thích kết quả.

## Input contract

```json
{
  "profile": {
    "scores": {"toan": 8.0, "nguvan": 7.5, "ngoaingu": 8.2},
    "combination": "D01",
    "interest": "Công nghệ thông tin",
    "priorities": {
      "academic": 5,
      "interest": 4,
      "admission": 3,
      "job_demand": 4,
      "salary": 2
    }
  },
  "candidate": {
    "candidate_id": "U01-7480201-D01",
    "university_id": "U01",
    "major_code": "7480201",
    "combination": "D01",
    "predicted_cutoff": 26.35,
    "subject_weights": {"toan": 0.5, "nguvan": 0.2, "ngoaingu": 0.3},
    "interest_relation": "exact",
    "job_demand": 0.82,
    "salary_score": 0.76
  }
}
```

Priority là số nguyên từ 1 đến 5. Không nhận 0 vì AHP tạo tỷ lệ `a_ij = priority_i / priority_j`.

## Công thức

### Academic Fit

```
academic_fit = sum((subject_score / 10) * subject_weight) / sum(subject_weight)
```

### Admission Fit

```
gap = student_score - predicted_cutoff
admission_fit = 1 / (1 + exp(-1.1 * gap))
```

Đây là mức cạnh tranh tham chiếu, không phải xác suất đỗ thật.

### AHP

```
a_ij = priority_i / priority_j
CI = (lambda_max - n) / (n - 1)
CR = CI / RI
```

CR nhỏ hơn hoặc bằng 0.10 được coi là nhất quán. Với ma trận dựng trực tiếp từ tỷ lệ priority, CR thường gần 0.

### TOPSIS

1. Chuẩn hóa vector từng cột của ma trận tiêu chí.
2. Nhân với trọng số AHP.
3. Tìm nghiệm lý tưởng dương `A+` và âm `A-`.
4. Tính khoảng cách `D+`, `D-`.
5. Tính closeness coefficient:

```
C_i = D_i- / (D_i+ + D_i-)
```

`topsis_score` càng gần 1, phương án càng phù hợp.

## Chạy test

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```
