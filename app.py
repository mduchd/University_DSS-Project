from __future__ import annotations

import csv
from functools import lru_cache
import json
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
JOB_SUMMARY_PATH = PROJECT_ROOT / "data" / "processed" / "jobs" / "job_market_summary_by_category.csv"
JOB_SKILLS_PATH = PROJECT_ROOT / "data" / "processed" / "jobs" / "job_category_skills.json"

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
            err_msg = errors[0]["message"] if errors else "Dữ liệu yêu cầu không hợp lệ."
            return jsonify({
                "status": "error",
                "error": err_msg,
                "message": err_msg,
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

def _demand_label(posting_count: int) -> str:
    if posting_count >= 5_000:
        return "Rất cao"
    if posting_count >= 3_000:
        return "Cao"
    if posting_count >= 1_500:
        return "Trung bình"
    return "Ổn định"


@lru_cache(maxsize=1)
def _career_insights_from_data() -> dict:
    """Tổng hợp màn hình nghề nghiệp từ các file VietJobs đã xử lý, không dùng số liệu hard-code."""
    if not JOB_SUMMARY_PATH.exists() or not JOB_SKILLS_PATH.exists():
        return {"sectors": [], "in_demand_skills": [], "data_source": "unavailable"}

    with JOB_SUMMARY_PATH.open(encoding="utf-8-sig", newline="") as source:
        summaries = list(csv.DictReader(source))
    with JOB_SKILLS_PATH.open(encoding="utf-8") as source:
        skills_lookup = json.load(source)

    skill_counts: dict[str, int] = {}
    skill_labels: dict[str, str] = {}
    sectors = []
    for row in sorted(summaries, key=lambda item: int(float(item.get("posting_count", 0))), reverse=True)[:6]:
        category = str(row.get("job_category", "")).strip()
        skill_data = skills_lookup.get(category, {})
        skills = [
            str(skill).strip()
            for skill in skill_data.get("top_technical_skills", []) + skill_data.get("top_soft_skills", [])
            if str(skill).strip()
        ]
        for skill in dict.fromkeys(skills):
            normalized = skill.casefold()
            skill_counts[normalized] = skill_counts.get(normalized, 0) + 1
            skill_labels.setdefault(normalized, skill)

        posting_count = int(float(row.get("posting_count", 0)))
        average_salary = float(row.get("average_salary_million_vnd", 0))
        median_salary = float(row.get("median_salary_million_vnd", 0))
        experience = float(row.get("average_experience_months", 0))
        sectors.append(
            {
                "name": category.replace("_", " "),
                "icon": "school",
                "demand": _demand_label(posting_count),
                "posting_count": posting_count,
                "average_salary_million_vnd": round(average_salary, 1),
                "median_salary_million_vnd": round(median_salary, 1),
                "average_experience_months": round(experience, 1),
                "skills": list(dict.fromkeys(skills))[:6],
            }
        )

    in_demand_skills = [
        {"skill": skill_labels[key], "level": f"Xuất hiện trong {count} nhóm nghề của dữ liệu VietJobs"}
        for key, count in sorted(skill_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {"sectors": sectors, "in_demand_skills": in_demand_skills, "data_source": "VietJobs"}


@app.get("/api/career/insights")
def career_insights():
    return jsonify(_career_insights_from_data())


if __name__ == "__main__":
    app.run(debug=False)
