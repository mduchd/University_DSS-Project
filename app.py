from __future__ import annotations

import csv
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import unicodedata
from services.assistant_service import AssistantError, answer_question, stream_answer
from services.auth_service import AuthError, decode_token, login_google_user, login_user, register_user
from services.data_repository import get_db_connection
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from services.recommendation_service import recommendation_engine
from services.university_logo_service import university_logo_service
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from flask import Flask, Response, jsonify, render_template, request


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
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "")
app.config["GOOGLE_CLIENT_ID"] = os.environ.get("GOOGLE_CLIENT_ID", "")


def _auth_secret() -> str:
    return str(app.config.get("JWT_SECRET_KEY", ""))


def _google_client_id() -> str:
    return str(app.config.get("GOOGLE_CLIENT_ID", ""))


def _bearer_token() -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise AuthError("Cần đăng nhập để thực hiện yêu cầu này.", 401)
    return token.strip()


@app.post("/api/auth/register")
def register_api():
    payload = request.get_json(silent=True) or {}
    try:
        account = register_user(payload.get("username"), payload.get("password"), _auth_secret())
        return jsonify({"status": "success", "message": "Đăng ký thành công.", **account}), 201
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code


@app.post("/api/auth/login")
def login_api():
    payload = request.get_json(silent=True) or {}
    try:
        account = login_user(payload.get("username"), payload.get("password"), _auth_secret())
        return jsonify({"status": "success", "message": "Đăng nhập thành công.", **account})
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code


@app.get("/api/auth/config")
def auth_config_api():
    return jsonify({"google_client_id": _google_client_id(), "google_enabled": bool(_google_client_id())})


@app.post("/api/auth/google")
def google_login_api():
    payload = request.get_json(silent=True) or {}
    try:
        account = login_google_user(payload.get("credential"), _google_client_id(), _auth_secret())
        return jsonify({"status": "success", "message": "Đăng nhập Google thành công.", **account})
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code


@app.get("/api/auth/me")
def current_user_api():
    try:
        return jsonify({"status": "success", "user": decode_token(_bearer_token(), _auth_secret())})
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code


@app.post("/api/assistant/chat")
def assistant_chat_api():
    payload = request.get_json(silent=True) or {}
    try:
        # Authentication limits paid-model access to signed-in users.
        decode_token(_bearer_token(), _auth_secret())
        response = answer_question(payload.get("message"), payload.get("profile"), payload.get("history"))
        return jsonify({"status": "success", **response})
    except (AuthError, AssistantError) as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code


@app.post("/api/assistant/chat/stream")
def assistant_chat_stream_api():
    payload = request.get_json(silent=True) or {}
    try:
        decode_token(_bearer_token(), _auth_secret())
        events = stream_answer(payload.get("message"), payload.get("profile"), payload.get("history"))
        return Response(
            events,
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )
    except (AuthError, AssistantError) as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code


def _create_wishlist_table(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS wishlist_items (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                school TEXT NOT NULL,
                major TEXT NOT NULL,
                school_code TEXT,
                cutoff TEXT,
                gap TEXT,
                logo_url TEXT,
                logo_alt TEXT,
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, school, major)
            )
            """
        )
    )


@app.get("/api/wishlist")
def get_wishlist():
    try:
        user = decode_token(_bearer_token(), _auth_secret())
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code
    connection = get_db_connection()
    if connection is None:
        return jsonify({"status": "error", "message": "Không thể kết nối cơ sở dữ liệu."}), 503
    try:
        with connection.begin():
            _create_wishlist_table(connection)
            rows = connection.execute(
                text(
                    "SELECT id, school, major, school_code, cutoff, gap, logo_url, logo_alt, position "
                    "FROM wishlist_items WHERE user_id = :uid ORDER BY position ASC, created_at ASC"
                ),
                {"uid": user["id"]},
            ).fetchall()
        items = [
            {
                "id": row.id,
                "school": row.school,
                "major": row.major,
                "school_code": row.school_code,
                "cutoff": row.cutoff,
                "gap": row.gap,
                "logo_url": row.logo_url,
                "logo_alt": row.logo_alt,
                "position": row.position,
            }
            for row in rows
        ]
        return jsonify({"items": items})
    except SQLAlchemyError as error:
        logging.error(f"Lỗi GET /api/wishlist: {error}")
        return jsonify({"status": "error", "message": "Lỗi truy vấn cơ sở dữ liệu."}), 500
    finally:
        connection.close()


@app.post("/api/wishlist")
def add_wishlist():
    try:
        user = decode_token(_bearer_token(), _auth_secret())
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code
    body = request.get_json(silent=True) or {}
    school = str(body.get("school", "")).strip()
    major = str(body.get("major", "")).strip()
    if not school or not major:
        return jsonify({"status": "error", "message": "school và major là bắt buộc."}), 400
    connection = get_db_connection()
    if connection is None:
        return jsonify({"status": "error", "message": "Không thể kết nối cơ sở dữ liệu."}), 503
    try:
        with connection.begin():
            _create_wishlist_table(connection)
            row = connection.execute(
                text(
                    "INSERT INTO wishlist_items (user_id, school, major, school_code, cutoff, gap, logo_url, logo_alt) "
                    "VALUES (:uid, :school, :major, :school_code, :cutoff, :gap, :logo_url, :logo_alt) "
                    "ON CONFLICT (user_id, school, major) DO NOTHING "
                    "RETURNING id, school, major, school_code, cutoff, gap, logo_url, logo_alt, position"
                ),
                {
                    "uid": user["id"],
                    "school": school,
                    "major": major,
                    "school_code": str(body.get("school_code", "") or "").strip() or None,
                    "cutoff": str(body.get("cutoff", "") or "").strip() or None,
                    "gap": str(body.get("gap", "") or "").strip() or None,
                    "logo_url": str(body.get("logo_url", "") or "").strip() or None,
                    "logo_alt": str(body.get("logo_alt", "") or "").strip() or None,
                },
            ).fetchone()
        if row is None:
            # Already exists — fetch existing record
            with connection.begin():
                row = connection.execute(
                    text(
                        "SELECT id, school, major, school_code, cutoff, gap, logo_url, logo_alt, position "
                        "FROM wishlist_items WHERE user_id = :uid AND school = :school AND major = :major"
                    ),
                    {"uid": user["id"], "school": school, "major": major},
                ).fetchone()
        return jsonify({
            "id": row.id,
            "school": row.school,
            "major": row.major,
            "school_code": row.school_code,
            "cutoff": row.cutoff,
            "gap": row.gap,
            "logo_url": row.logo_url,
            "logo_alt": row.logo_alt,
            "position": row.position,
        })
    except SQLAlchemyError as error:
        logging.error(f"Lỗi POST /api/wishlist: {error}")
        return jsonify({"status": "error", "message": "Lỗi truy vấn cơ sở dữ liệu."}), 500
    finally:
        connection.close()


@app.delete("/api/wishlist/<int:item_id>")
def delete_wishlist(item_id: int):
    try:
        user = decode_token(_bearer_token(), _auth_secret())
    except AuthError as error:
        return jsonify({"status": "error", "message": error.message}), error.status_code
    connection = get_db_connection()
    if connection is None:
        return jsonify({"status": "error", "message": "Không thể kết nối cơ sở dữ liệu."}), 503
    try:
        with connection.begin():
            _create_wishlist_table(connection)
            connection.execute(
                text("DELETE FROM wishlist_items WHERE id = :id AND user_id = :uid"),
                {"id": item_id, "uid": user["id"]},
            )
        return jsonify({"status": "success"})
    except SQLAlchemyError as error:
        logging.error(f"Lỗi DELETE /api/wishlist/{item_id}: {error}")
        return jsonify({"status": "error", "message": "Lỗi truy vấn cơ sở dữ liệu."}), 500
    finally:
        connection.close()


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
        results[-1].update(
            university_logo_service.get(
                results[-1].get("school_code", ""),
                results[-1].get("school", ""),
            )
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

    interests = data.get("interests", [])
    if not isinstance(interests, list):
        errors.append({"field": "interests", "message": "Sở thích phải là một danh sách."})
    elif len(interests) > 2:
        errors.append({"field": "interests", "message": "Chỉ được chọn tối đa 2 sở thích."})
    elif any(not isinstance(value, str) or not value.strip() for value in interests):
        errors.append({"field": "interests", "message": "Sở thích không hợp lệ."})
            
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
