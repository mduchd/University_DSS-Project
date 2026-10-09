"""Tạo bản notebook có chú giải từ mã Python ML đang dùng trong dự án.

Notebook là bản đọc/thử nghiệm; file .py vẫn là nguồn chạy production.
"""

from __future__ import annotations

import ast
from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notebooks" / "ml"
SOURCES = {
    "models/prepare_cutoff_dataset.py": ("01", "Sàng lọc dữ liệu điểm chuẩn", "Chuẩn hóa target, khóa modeling, ghi nhận từng dòng bị loại thay vì tự suy đoán."),
    "models/analyze_cutoff_step2.py": ("02", "Rà soát định danh và dữ liệu bị loại", "Phân tích alias trường/ngành, tạo map và hàng đợi kiểm tra thủ công."),
    "models/review_high_priority_identities.py": ("03", "Ưu tiên rà soát định danh", "Tìm cặp tên hoặc mã đáng ngờ, không tự động gộp khi thiếu bằng chứng."),
    "models/build_cutoff_features.py": ("04", "Feature engineering theo thời gian", "Tạo lag, thống kê lịch sử, bối cảnh và cold-start chỉ từ dữ liệu trước năm dự báo."),
    "models/train_baselines.py": ("05", "Baseline đơn giản", "Đo Historical Mean, Last Value, Group Mean và hồi quy tuyến tính làm mốc so sánh."),
    "models/train_cutoff_model.py": ("06", "Huấn luyện và đánh giá model", "So sánh Ridge, Random Forest, XGBoost trên validation 2023; khóa cấu hình trước test 2024."),
    "models/predictor.py": ("07", "Predictor độc lập", "Nạp artifact gồm cả preprocessing và estimator, kiểm tra đầu vào, dự báo theo batch."),
    "models/generate_cutoff_evaluation_charts.py": ("08", "Biểu đồ đánh giá", "Tạo hình so sánh candidate, phân nhóm sai số, residual và feature importance."),
    "services/cutoff_forecast_service.py": ("09", "Tích hợp dự báo vào hệ thống", "Ghép feature forecast với phương án tuyển sinh và fallback khi không có dự báo hợp lệ."),
    "scripts/build_forecast_cache.py": ("10", "Tạo cache dự báo", "Chuẩn bị kết quả dự báo theo lô để ứng dụng tra cứu nhanh hơn."),
}


def source_cells(relative: str) -> list[nbformat.NotebookNode]:
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    cells: list[nbformat.NotebookNode] = []
    import_nodes = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if import_nodes:
        cells.append(nbformat.v4.new_markdown_cell("### 1.1 Thư viện và phụ thuộc\n\nCác import bên dưới khớp với file `.py` gốc."))
        cells.append(nbformat.v4.new_code_cell("\n".join("".join(lines[n.lineno - 1:n.end_lineno]).rstrip() for n in import_nodes)))
    cells.append(nbformat.v4.new_code_cell(
        "from pathlib import Path\nimport sys\n"
        "PROJECT_ROOT = Path.cwd().resolve()\n"
        "if not (PROJECT_ROOT / 'models').exists():\n"
        "    raise RuntimeError('Hãy mở Jupyter tại thư mục gốc DSS_Dataset.')\n"
        "if str(PROJECT_ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(PROJECT_ROOT))\n"
        f"__file__ = str(PROJECT_ROOT / {relative!r})\n"
        "print('Nguồn production:', __file__)"
    ))
    cells.append(nbformat.v4.new_markdown_cell(
        "### 1.2 Mã nguồn theo từng khối\n\n"
        "Mỗi hàm/lớp giữ nguyên từ file production. Chỉ lời gọi CLI cuối file được bỏ để tránh "
        "ghi đè dữ liệu hoặc train model khi người đọc bấm Run All. Nếu muốn chạy pipeline, "
        "dùng lệnh ở cuối notebook."
    ))
    pending: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__":
            continue
        code = "".join(lines[node.lineno - 1:node.end_lineno]).rstrip()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if pending:
                cells.append(nbformat.v4.new_code_cell("\n\n".join(pending)))
                pending.clear()
            doc = ast.get_docstring(node)
            role = doc.splitlines()[0] if doc else "Định nghĩa khối xử lý; xem tham số và giá trị trả về trong mã nguồn."
            cells.append(nbformat.v4.new_markdown_cell(f"#### `{node.name}`\n\nVai trò: {role}"))
            cells.append(nbformat.v4.new_code_cell(code))
        else:
            pending.append(code)
    if pending:
        cells.append(nbformat.v4.new_code_cell("\n\n".join(pending)))
    return cells


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for relative, (order, title, role) in SOURCES.items():
        intro = nbformat.v4.new_markdown_cell(
            f"# {order}. {title}\n\n"
            f"**Vai trò:** {role}\n\n"
            f"**Nguồn production:** `{relative}`. Notebook này là bản học tập chụp từ mã nguồn; "
            "nếu hai bản khác nhau, hãy ưu tiên file `.py` và chạy lại "
            "`python scripts/generate_ml_notebooks.py`.\n\n"
            "**Cách dùng:** mở Jupyter tại thư mục gốc repo, chạy Run All để nạp các hàm. "
            "Không tự động huấn luyện hay ghi đè artifact. Dữ liệu dùng trong ví dụ phải được xác minh "
            "về niên đại để tránh data leakage (rò rỉ thông tin tương lai)."
        )
        notebook = nbformat.v4.new_notebook(cells=[intro, *source_cells(relative)])
        notebook.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
        notebook.metadata.language_info = {"name": "python", "version": "3"}
        output = OUTPUT / f"{order}_{Path(relative).stem}.ipynb"
        nbformat.write(notebook, output)
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
