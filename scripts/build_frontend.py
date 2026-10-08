"""Build the static Vercel frontend from the Flask template.

The production frontend calls relative ``/api/*`` URLs. Vercel rewrites those
requests to Render, while local Flask development continues to use the Jinja
template directly.
"""

from __future__ import annotations

import json
import shutil
import csv
import re
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "index.html"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "dist"
ADMISSION_PATH = ROOT / "data" / "raw" / "admission" / "diemchuan_2024.csv"

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


def build_group_options() -> str:
    """Render the Jinja major-group loop for the static Vercel frontend."""
    with ADMISSION_PATH.open(encoding="utf-8-sig", newline="") as source:
        groups = sorted(
            {
                str(row.get("Nhóm ngành", "")).strip()
                for row in csv.DictReader(source)
                if str(row.get("Nhóm ngành", "")).strip()
            }
        )
    return "\n".join(
        f'<option value="{escape(group, quote=True)}">{escape(group)}</option>'
        for group in groups
    )


def main() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace(
        "{{ url_for('static', filename='css/style.css') }}", "/static/css/style.css"
    ).replace(
        "{{ url_for('static', filename='js/app.js') }}", "/static/js/app.js"
    )
    template_config = """window.APP_CONFIG = {
        combinations: {{ combinations | tojson }},
        subjectNames: {{ subject_names | tojson }}
      };"""
    static_config = "window.APP_CONFIG = " + json.dumps(
        {"combinations": COMBINATIONS, "subjectNames": SUBJECT_NAMES},
        ensure_ascii=False,
    ) + ";"
    if template_config not in html:
        raise RuntimeError("Không tìm thấy cấu hình Jinja cần thay thế trong index.html")
    html = html.replace(template_config, static_config)

    group_loop_pattern = (
        r"\{%\s*for group in major_groups\s*%\}\s*"
        r"<option value=\"\{\{ group \}\}\">\{\{ group \}\}</option>\s*"
        r"\{%\s*endfor\s*%\}"
    )
    html, group_loop_count = re.subn(group_loop_pattern, build_group_options(), html)
    if group_loop_count != 2:
        raise RuntimeError("Không tìm thấy vòng lặp nhóm ngành cần thay thế trong index.html")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(STATIC_DIR, OUTPUT_DIR / "static")


if __name__ == "__main__":
    main()
