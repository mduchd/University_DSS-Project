"""
Script trích xuất và chuẩn hóa kho kỹ năng theo nhóm nghề (Job Category Skills Builder).
Đọc từ: data/processed/jobs/vietjobs_postings.csv
Chuẩn hóa:
- Quy chuẩn tên kỹ năng chuyên môn (tránh trùng biến thể như AutoCAD/Autocad, Photoshop/Adobe Photoshop).
- Tách bạch kỹ năng chuyên môn (technical_skills) và kỹ năng mềm (soft_skills).
- Xuất file: data/processed/jobs/job_category_skills.json.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_POSTINGS_PATH = ROOT / "data" / "processed" / "jobs" / "vietjobs_postings.csv"
OUTPUT_SKILLS_PATH = ROOT / "data" / "processed" / "jobs" / "job_category_skills.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CANONICAL_TECH_SKILLS = {
    "photoshop": "Photoshop",
    "adobe photoshop": "Photoshop",
    "pts": "Photoshop",
    "illustrator": "Illustrator",
    "adobe illustrator": "Illustrator",
    "ai": "Illustrator",
    "autocad": "AutoCAD",
    "auto cad": "AutoCAD",
    "cad": "AutoCAD",
    "excel": "Excel",
    "ms excel": "Excel",
    "word": "Word",
    "ms word": "Word",
    "powerpoint": "PowerPoint",
    "ms powerpoint": "PowerPoint",
    "tin học văn phòng": "Tin học văn phòng",
    "office": "Tin học văn phòng",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "python": "Python",
    "java": "Java",
    "c++": "C++",
    "c#": "C#",
    "php": "PHP",
    "sql": "SQL",
    "mysql": "SQL/MySQL",
    "html": "HTML/CSS",
    "html5": "HTML/CSS",
    "css": "HTML/CSS",
    "css3": "HTML/CSS",
    "react": "React",
    "reactjs": "React",
    "node": "Node.js",
    "nodejs": "Node.js",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "after effects": "After Effects",
    "premiere": "Premiere",
    "figma": "Figma",
    "solidworks": "SolidWorks",
    "revit": "Revit",
}

CANONICAL_SOFT_SKILLS = {
    "kỹ năng giao tiếp": "Kỹ năng giao tiếp",
    "giao tiếp": "Kỹ năng giao tiếp",
    "kỹ năng làm việc nhóm": "Làm việc nhóm",
    "làm việc nhóm": "Làm việc nhóm",
    "teamwork": "Làm việc nhóm",
    "quản lý thời gian": "Quản lý thời gian",
    "kỹ năng giải quyết vấn đề": "Giải quyết vấn đề",
    "giải quyết vấn đề": "Giải quyết vấn đề",
    "chịu áp lực": "Chịu áp lực công việc",
    "chịu được áp lực": "Chịu áp lực công việc",
    "chịu áp lực cao": "Chịu áp lực công việc",
    "trung thực": "Trung thực",
    "cẩn thận": "Cẩn thận",
    "nhanh nhẹn": "Nhanh nhẹn",
    "tinh thần trách nhiệm": "Tinh thần trách nhiệm",
    "trách nhiệm": "Tinh thần trách nhiệm",
    "kỹ năng đàm phán": "Kỹ năng đàm phán",
    "đàm phán": "Kỹ năng đàm phán",
    "thuyết trình": "Kỹ năng thuyết trình",
    "tư duy logic": "Tư duy logic",
    "tư duy sáng tạo": "Tư duy sáng tạo",
    "sáng tạo": "Tư duy sáng tạo",
}


def normalize_skill_name(raw: str, canonical_dict: dict[str, str]) -> str:
    cleaned = raw.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned in canonical_dict:
        return canonical_dict[cleaned]
    # Viết hoa chữ cái đầu từ
    return raw.strip().title()


def build_job_category_skills():
    import pandas as pd

    logging.info("Bắt đầu trích xuất kỹ năng từ vietjobs_postings.csv...")
    if not INPUT_POSTINGS_PATH.exists():
        logging.error(f"Không tìm thấy file: {INPUT_POSTINGS_PATH}")
        return

    df = pd.read_csv(INPUT_POSTINGS_PATH, usecols=["job_category", "technical_skills", "soft_skills"])
    skills_by_cat = {}

    for cat, grp in df.groupby("job_category"):
        cat_str = str(cat).strip()
        if not cat_str or cat_str in ["nan", "None"]:
            continue

        tech_counter = Counter()
        soft_counter = Counter()

        for item in grp["technical_skills"].dropna():
            try:
                val = ast.literal_eval(item)
                if isinstance(val, list):
                    for s in val:
                        s_clean = s.strip()
                        if len(s_clean) >= 2:
                            norm = normalize_skill_name(s_clean, CANONICAL_TECH_SKILLS)
                            tech_counter[norm] += 1
            except Exception:
                pass

        for item in grp["soft_skills"].dropna():
            try:
                val = ast.literal_eval(item)
                if isinstance(val, list):
                    for s in val:
                        s_clean = s.strip()
                        if len(s_clean) >= 2:
                            norm = normalize_skill_name(s_clean, CANONICAL_SOFT_SKILLS)
                            soft_counter[norm] += 1
            except Exception:
                pass

        # Lọc kỹ năng chuyên môn: loại bỏ nếu nằm trong kỹ năng mềm
        top_tech = []
        for s, _ in tech_counter.most_common(20):
            if s not in CANONICAL_SOFT_SKILLS.values() and s not in top_tech:
                top_tech.append(s)
            if len(top_tech) >= 10:
                break

        top_soft = []
        for s, _ in soft_counter.most_common(10):
            if s not in top_soft:
                top_soft.append(s)
            if len(top_soft) >= 6:
                break

        skills_by_cat[cat_str] = {
            "top_technical_skills": top_tech,
            "top_soft_skills": top_soft,
        }

    OUTPUT_SKILLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_SKILLS_PATH, "w", encoding="utf-8") as f:
        json.dump(skills_by_cat, f, ensure_ascii=False, indent=2)

    logging.info(f"Đã xuất file kỹ năng chuẩn hóa: {OUTPUT_SKILLS_PATH} ({len(skills_by_cat)} nhóm nghề)")


if __name__ == "__main__":
    build_job_category_skills()
