"""Chạy tuần tự mọi notebook ML để phát hiện lỗi cú pháp/phụ thuộc."""

from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    for path in sorted((ROOT / "notebooks" / "ml").glob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
        print(f"OK {path.name}")


if __name__ == "__main__":
    main()
