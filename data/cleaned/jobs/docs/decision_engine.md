# Decision Engine: AHP + TOPSIS

## Phạm vi

Module xếp hạng ngành/trường độc lập với Flask, UI và database.

## Tiêu chí

1. `academic_fit`
2. `interest_fit`
3. `admission_fit`
4. `job_demand`
5. `salary_score`

Tất cả là benefit criteria.

## AHP

Người dùng nhập priority 1-5.

Pairwise matrix:

a_ij = priority_i / priority_j

Trọng số lấy từ eigenvector chính của ma trận.

CR = CI / RI

Ngưỡng chấp nhận:

CR <= 0.10

## Admission Fit

gap = student_score - predicted_cutoff

admission_fit = 1 / (1 + exp(-1.1 * gap))

Đây là mức cạnh tranh tham chiếu, không phải xác suất đỗ.

## TOPSIS

1. Chuẩn hóa ma trận quyết định.
2. Nhân trọng số AHP.
3. Tính positive ideal solution và negative ideal solution.
4. Tính khoảng cách D+ và D-.
5. Tính closeness coefficient:

C_i = D_i- / (D_i+ + D_i-)

C_i càng gần 1, phương án càng được ưu tiên.