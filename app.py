from __future__ import annotations

import csv
from functools import lru_cache
import math
from pathlib import Path
import unicodedata
from services.recommendation_service import recommendation_engine
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from flask import Flask, jsonify, render_template, request


def remove_accents(input_str: str) -> str:
    if not input_str:
        return ""
    nfkd = unicodedata.normalize("NFKD", input_str)
    unaccented = "".join(c for c in nfkd if not unicodedata.combining(c))
    return unaccented.replace("đ", "d").replace("Đ", "D").casefold()


PROJECT_ROOT = Path(__file__).resolve().parent
ADMISSION_PATH = PROJECT_ROOT / "data" / "raw" / "admission" / "diemchuan_2024.csv"

COMBINATIONS = {
    "A00": ("toan", "vatly", "hoahoc"),
    "A01": ("toan", "vatly", "ngoaingu"),
    "A02": ("toan", "vatly", "sinhhoc"),
    "B00": ("toan", "hoahoc", "sinhhoc"),
    "B08": ("toan", "sinhhoc", "ngoaingu"),
    "C00": ("nguvan", "lichsu", "dialy"),
    "C01": ("nguvan", "toan", "vatly"),
    "C02": ("nguvan", "toan", "hoahoc"),
    "D01": ("toan", "nguvan", "ngoaingu"),
    "D07": ("toan", "hoahoc", "ngoaingu"),
}

SUBJECT_NAMES = {
    "toan": "Toán",
    "vatly": "Vật lý",
    "hoahoc": "Hóa học",
    "sinhhoc": "Sinh học",
    "nguvan": "Ngữ văn",
    "lichsu": "Lịch sử",
    "dialy": "Địa lý",
    "ngoaingu": "Ngoại ngữ",
}

app = Flask(__name__)
@app.get("/api/health")
def health_check():
    return jsonify({
        "status": "success",
        "message": "Dịch vụ hoạt động bình thường",
        "data": {
            "service_status": "up",
            "data_cached": True
        },
        "errors": None
    }), 200

def as_number(value: str | float | int | None) -> float | None:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def admissions() -> list[dict[str, str | float | bool]]:
    rows: list[dict[str, str | float | bool]] = []
    if not ADMISSION_PATH.exists():
        return rows
    with ADMISSION_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            cutoff = as_number(row.get("Điểm chuẩn"))
            if cutoff is None:
                continue
            scale_type = str(row.get("Loại điểm", "")).strip()
            is_scale_40 = "thang 40" in scale_type.casefold() or cutoff > 30.5
            rows.append({**row, "cutoff": cutoff, "is_scale_40": is_scale_40})
    return rows


@lru_cache(maxsize=1)
def get_unique_major_groups() -> list[str]:
    groups = {
        str(row.get("Nhóm ngành", "")).strip()
        for row in admissions()
        if str(row.get("Nhóm ngành", "")).strip()
    }
    return sorted(groups)


def classify(gap: float) -> str | None:
    if gap >= 1.0:
        return "safe"
    if gap >= -1.0:
        return "match"
    if gap >= -3.0:
        return "reach"
    return None


@app.get("/")
def home():
    return render_template(
        "index.html",
        combinations=COMBINATIONS,
        subject_names=SUBJECT_NAMES,
        major_groups=get_unique_major_groups(),
    )


@app.get("/api/overview")
def overview():
    rows = admissions()
    schools = {str(row.get("Trường đào tạo", "")).strip() for row in rows}
    groups = get_unique_major_groups()
    return jsonify(
        {
            "admission_rows": len(rows),
            "schools": len(schools),
            "major_groups": len(groups),
            "year": 2024,
            "groups_list": groups,
        }
    )


@app.get("/api/admissions/search")
def search_admissions():
    q = request.args.get("q", "").strip().casefold()
    combination = request.args.get("combination", "").strip().upper()
    group = request.args.get("group", "").strip().casefold()
    scale = request.args.get("scale", "all").strip().lower()  # 30, 40, all
    sort_by = request.args.get("sort", "cutoff_desc").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        limit = min(100, max(5, int(request.args.get("limit", 15))))
    except ValueError:
        limit = 15

    results = []
    for row in admissions():
        if scale == "30" and row.get("is_scale_40"):
            continue
        if scale == "40" and not row.get("is_scale_40"):
            continue

        if combination:
            offered = str(row.get("Tổ hợp môn", "")).upper()
            if combination not in offered:
                continue

        if group:
            row_group = str(row.get("Nhóm ngành", "")).casefold()
            if group not in row_group:
                continue

        if q:
            searchable = " ".join(
                str(row.get(k, ""))
                for k in ("Mã trường", "Trường đào tạo", "Tên ngành", "Ngành", "Mã ngành", "Nhóm ngành")
            ).casefold()
            if q not in searchable and remove_accents(q) not in remove_accents(searchable):
                continue

        results.append(
            {
                "school_code": row.get("Mã trường", "—"),
                "school": row.get("Trường đào tạo", "Chưa rõ trường"),
                "major": row.get("Tên ngành") or row.get("Ngành") or "Chưa rõ ngành",
                "major_code": row.get("Mã ngành", "—"),
                "group": row.get("Nhóm ngành", "Khác"),
                "combination": row.get("Tổ hợp môn", "—"),
                "cutoff": row["cutoff"],
                "note": row.get("Ghi chú", ""),
                "scale": "Thang 40" if row.get("is_scale_40") else "Thang 30",
            }
        )

    # Sorting
    if sort_by == "cutoff_asc":
        results.sort(key=lambda x: float(x["cutoff"]))
    elif sort_by == "cutoff_desc":
        results.sort(key=lambda x: float(x["cutoff"]), reverse=True)
    elif sort_by == "school_asc":
        results.sort(key=lambda x: x["school"])

    total = len(results)
    pages = math.ceil(total / limit) if total > 0 else 1
    offset = (page - 1) * limit
    paginated_items = results[offset : offset + limit]

    return jsonify(
        {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": pages,
            "items": paginated_items,
        }
    )
@app.post("/api/recommend")
def recommend_api():
    try:
        # Lấy dữ liệu JSON từ Frontend gửi lên
        payload = request.get_json(silent=True) or {}
        
        # KIỂM TRA ĐẦU VÀO (Validation)
        errors = validate_payload(payload)
        if errors:
            return jsonify({
                "status": "error",
                "data": None,
                "errors": errors
            }), 400
            
        # GỌI ENGINE XỬ LÝ (Phase 3)
        result = recommendation_engine.process_recommendation(payload)
        
        # Trả về đầy đủ top-level fields cho Frontend (app.js) và backward-compatible data wrapper
        response_payload = {
            **result,
            "status": "success",
            "data": result,
            "errors": None,
        }
        return jsonify(response_payload), 200
        
    except Exception as e:
        logging.error(f"Lỗi Server: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "message": "Lỗi hệ thống cục bộ, vui lòng thử lại sau.",
            "data": None,
            "errors": [{"message": str(e)}]
        }), 500

# Hàm kiểm tra logic đầu vào
def validate_payload(data):
    errors = []
    
    combination = str(data.get("combination", "")).strip().upper()
    if not combination:
        errors.append({"field": "combination", "message": "Bắt buộc phải chọn tổ hợp môn."})
    elif combination not in COMBINATIONS:
        errors.append({"field": "combination", "message": f"Tổ hợp {combination} chưa được hỗ trợ."})

    scores = data.get("scores", {})
    if not scores:
        errors.append({"field": "scores", "message": "Bắt buộc phải có điểm thi."})
    elif combination in COMBINATIONS:
        required_subjects = COMBINATIONS[combination]
        for subject in required_subjects:
            if subject not in scores:
                subj_name = SUBJECT_NAMES.get(subject, subject)
                errors.append({"field": f"scores.{subject}", "message": f"Bắt buộc phải nhập điểm môn {subj_name} cho tổ hợp {combination}."})
            else:
                score = scores[subject]
                if not isinstance(score, (int, float)) or score < 0 or score > 10:
                    errors.append({"field": f"scores.{subject}", "message": "Điểm phải là số nằm trong khoảng 0-10."})

    priorities = data.get("priorities", {})
    for key, value in priorities.items():
        if not isinstance(value, (int, float)) or value < 0:
            errors.append({"field": f"priorities.{key}", "message": "Mức độ ưu tiên không được là số âm."})
            
    return errors

@app.get("/api/career/insights")
def career_insights():
    """Insights derived from VietJobs market context and job trends."""
    insights = {
        "market_summary": "Tổng hợp xu hướng tuyển dụng dựa trên dữ liệu VietJobs và thị trường lao động Việt Nam giai đoạn 2024–2025.",
        "sectors": [
            {
                "name": "Công nghệ thông tin & Phần mềm",
                "demand": "Rất cao",
                "salary_range": "12 – 35+ triệu VNĐ",
                "roles": ["Kỹ sư phần mềm", "Data Analyst", "Chuyên viên An toàn thông tin", "AI/ML Engineer"],
                "skills": ["Python / JavaScript / Java", "Tư duy thuật toán", "SQL & Dữ liệu", "Tiếng Anh chuyên ngành"],
                "highlight": "Nhu cầu chuyển đổi số và phát triển giải pháp AI đang bùng nổ mạnh mẽ tại Hà Nội và TP.HCM."
            },
            {
                "name": "Kinh doanh, Marketing & Thương mại điện tử",
                "demand": "Cao",
                "salary_range": "10 – 28 triệu VNĐ",
                "roles": ["Digital Marketer", "Quản lý kinh doanh (Account / Sales)", "E-commerce Specialist", "Brand Executive"],
                "skills": ["Phân tích thị trường", "Content & SEO", "Chạy quảng cáo số", "Đàm phán & Thuyết trình"],
                "highlight": "Thương mại điện tử và tiếp thị số mở rộng tuyển dụng ở cả khối doanh nghiệp vừa và lớn."
            },
            {
                "name": "Tài chính, Ngân hàng & Phân tích đầu tư",
                "demand": "Ổn định",
                "salary_range": "11 – 32 triệu VNĐ",
                "roles": ["Chuyên viên tín dụng", "Phân tích tài chính", "Kiểm toán viên", "Tư vấn quản trị rủi ro"],
                "skills": ["Mô hình hóa tài chính", "Kế toán / IFRS", "Phân tích báo cáo", "Chứng chỉ CFA/ACCA"],
                "highlight": "Các vị trí kết hợp tài chính với công nghệ (Fintech) có mức đãi ngộ tăng trưởng vượt trội."
            },
            {
                "name": "Logistics & Quản trị chuỗi cung ứng",
                "demand": "Rất cao",
                "salary_range": "10 – 26 triệu VNĐ",
                "roles": ["Điều phối Logistics", "Thu mua (Procurement)", "Xuất nhập khẩu", "Quản trị kho vận"],
                "skills": ["Thủ tục hải quan", "Tiếng Anh / Tiếng Trung", "Tối ưu chuỗi cung ứng", "ERP / SAP"],
                "highlight": "Việt Nam tiếp tục là trung tâm sản xuất khu vực, tạo dư địa việc làm dồi dào cho ngành chuỗi cung ứng."
            },
            {
                "name": "Kỹ thuật, Điện tử & Tự động hóa",
                "demand": "Cao",
                "salary_range": "12 – 30 triệu VNĐ",
                "roles": ["Kỹ sư tự động hóa", "Thiết kế vi mạch / Bán dẫn", "Kỹ sư cơ điện tử", "Bảo trì công nghiệp"],
                "skills": ["PLC / IoT", "AutoCAD / SolidWorks", "Lập trình nhúng", "Kỹ năng thực hành phòng lab"],
                "highlight": "Làn sóng đầu tư bán dẫn và công nghệ cao mở ra cơ hội hấp dẫn cho khối ngành kỹ thuật."
            },
            {
                "name": "Y tế, Dược phẩm & Chăm sóc sức khỏe",
                "demand": "Bền vững",
                "salary_range": "10 – 35 triệu VNĐ",
                "roles": ["Bác sĩ đa khoa", "Dược sĩ nghiên cứu / lâm sàng", "Điều dưỡng viên", "Quản lý y tế"],
                "skills": ["Chuyên môn y khoa", "Thực hành lâm sàng", "Đạo đức nghề nghiệp", "Ngoại ngữ"],
                "highlight": "Ngành nghề có tính ổn định cao, nhu cầu dịch vụ chăm sóc sức khỏe chất lượng cao ngày càng tăng."
            },
        ],
        "in_demand_skills": [
            {"skill": "Ngoại ngữ (Tiếng Anh, Tiếng Trung, Tiếng Nhật)", "level": "Yếu tố tạo đột phá thu nhập (+30% đến +50%)"},
            {"skill": "Kỹ năng số & Phân tích dữ liệu cơ bản", "level": "Cần thiết cho mọi nhóm ngành nghề hiện đại"},
            {"skill": "Tư duy phản biện & Giải quyết vấn đề", "level": "Nhà tuyển dụng đánh giá cao nhất ở ứng viên mới tốt nghiệp"},
            {"skill": "Thích nghi & Tự học liên tục", "level": "Chìa khóa then chốt trước sự biến chuyển của công nghệ"},
        ]
    }
    return jsonify(insights)


if __name__ == "__main__":
    app.run(debug=False)
