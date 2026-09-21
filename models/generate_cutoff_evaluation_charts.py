"""Tạo bộ biểu đồ đánh giá model điểm chuẩn bằng Seaborn và Matplotlib.

Script chỉ đọc các artifact đã được pipeline huấn luyện sinh ra. Mỗi biểu đồ được
lưu dưới dạng PNG 300 DPI để có thể chèn trực tiếp vào báo cáo hoặc slide.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # Backend không cần giao diện, phù hợp khi chạy bằng CMD hoặc CI.

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATION = ROOT / "models/evaluation.json"
DEFAULT_PREDICTIONS = ROOT / "data/processed/admission_ml_model_predictions_2024.csv"
DEFAULT_IMPORTANCE = ROOT / "data/processed/admission_ml_feature_importance.csv"
DEFAULT_OUTPUT_DIR = ROOT / "docs/figures/cutoff_model"

FAMILY_LABELS = {
    "ridge": "Ridge",
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
}
SEGMENT_LABELS = {
    "all": "Toàn bộ",
    "known_history": "Có lịch sử",
    "cold_start": "Cold start",
}
PALETTE = {
    "Ridge": "#4C78A8",
    "Random Forest": "#59A14F",
    "XGBoost": "#E45756",
    "Có lịch sử": "#4C78A8",
    "Cold start": "#E45756",
}


def parse_args() -> argparse.Namespace:
    """Đọc đường dẫn artifact và thư mục lưu hình từ command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--importance", type=Path, default=DEFAULT_IMPORTANCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def configure_style() -> None:
    """Đặt theme thống nhất, dễ đọc khi chèn vào Word hoặc PowerPoint."""
    sns.set_theme(style="whitegrid", context="talk", font="DejaVu Sans")
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.titleweight": "bold",
            "axes.titlesize": 18,
            "axes.labelsize": 13,
            "legend.frameon": False,
            "savefig.bbox": "tight",
        }
    )


def save_figure(fig: plt.Figure, path: Path) -> None:
    """Lưu hình 300 DPI rồi đóng figure để giải phóng bộ nhớ."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, facecolor="white")
    plt.close(fig)


def candidate_frame(evaluation: dict[str, Any]) -> pd.DataFrame:
    """Chuyển danh sách candidate trong evaluation.json thành bảng phẳng để vẽ."""
    rows: list[dict[str, Any]] = []
    for candidate in evaluation["models"]["validation_candidates"]:
        metrics = candidate["validation"]["all"]
        rows.append(
            {
                "candidate": candidate["name"],
                "family": FAMILY_LABELS[candidate["family"]],
                "MAE": metrics["mae"],
                "RMSE": metrics["rmse"],
                "R²": metrics["r2"],
                "fit_seconds": candidate["fit_seconds"],
            }
        )
    return pd.DataFrame(rows).sort_values("MAE", kind="stable").reset_index(drop=True)


def plot_candidate_comparison(data: pd.DataFrame, selected: str, output: Path) -> None:
    """So sánh MAE và RMSE validation của toàn bộ cấu hình ứng viên."""
    long = data.melt(
        id_vars=["candidate", "family"],
        value_vars=["MAE", "RMSE"],
        var_name="Chỉ số",
        value_name="Sai số",
    )
    order = data["candidate"].tolist()
    fig, ax = plt.subplots(figsize=(14, 8))
    sns.barplot(
        data=long,
        y="candidate",
        x="Sai số",
        hue="Chỉ số",
        order=order,
        palette={"MAE": "#4C78A8", "RMSE": "#F28E2B"},
        ax=ax,
    )
    ax.set_title("So sánh candidate trên validation 2023")
    ax.set_xlabel("Sai số trên thang điểm chuẩn 0–30 (thấp hơn tốt hơn)")
    ax.set_ylabel("Cấu hình model")
    ax.set_yticks(
        range(len(order)),
        [f"{name} (được chọn)" if name == selected else name for name in order],
    )
    ax.legend(title="Chỉ số", loc="upper right")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.3f", padding=3, fontsize=9)
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output)


def plot_test_segments(evaluation: dict[str, Any], output: Path) -> None:
    """Trực quan hóa chênh lệch sai số giữa toàn bộ, known history và cold start."""
    final = evaluation["final_test_2024"]
    rows = []
    for key in ["all", "known_history", "cold_start"]:
        for metric in ["mae", "rmse"]:
            rows.append(
                {
                    "Phân nhóm": SEGMENT_LABELS[key],
                    "Chỉ số": metric.upper(),
                    "Sai số": final[key][metric],
                    "Số mẫu": final[key]["n_samples"],
                }
            )
    frame = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(
        data=frame,
        x="Phân nhóm",
        y="Sai số",
        hue="Chỉ số",
        palette={"MAE": "#4C78A8", "RMSE": "#F28E2B"},
        ax=ax,
    )
    ax.set_title("Hiệu năng model cuối trên test 2024 theo nhóm lịch sử")
    ax.set_xlabel("")
    ax.set_ylabel("Sai số trên thang điểm chuẩn 0–30")
    ax.legend(title="Chỉ số")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.3f", padding=4, fontsize=10)
    counts = frame.drop_duplicates("Phân nhóm").set_index("Phân nhóm")["Số mẫu"]
    labels = ["Toàn bộ", "Có lịch sử", "Cold start"]
    ax.set_xticks(
        range(len(labels)),
        [f"{label}\n(n = {int(counts[label]):,})" for label in labels],
    )
    ax.margins(y=0.12)
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output)


def plot_actual_vs_predicted(predictions: pd.DataFrame, output: Path) -> None:
    """So sánh điểm thật và điểm dự báo; đường chéo biểu diễn dự báo hoàn hảo."""
    frame = predictions.copy()
    frame["Phân nhóm"] = frame["history_segment"].map(SEGMENT_LABELS).fillna(frame["history_segment"])
    # Lấy mẫu cố định giúp file hình nhẹ nhưng vẫn giữ đúng hình dạng phân phối.
    sample = frame.sample(n=min(8_000, len(frame)), random_state=42)
    fig, ax = plt.subplots(figsize=(10, 9))
    sns.scatterplot(
        data=sample,
        x="cutoff_score_30",
        y="predicted_cutoff",
        hue="Phân nhóm",
        palette=PALETTE,
        alpha=0.32,
        s=24,
        linewidth=0,
        ax=ax,
    )
    ax.plot([0, 30], [0, 30], linestyle="--", linewidth=2, color="#333333", label="Dự báo hoàn hảo")
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 30)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Điểm chuẩn thực tế và dự báo trên test 2024")
    ax.set_xlabel("Điểm chuẩn thực tế")
    ax.set_ylabel("Điểm chuẩn dự báo")
    ax.legend(title="Phân nhóm", loc="upper left")
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output)


def plot_residual_distribution(predictions: pd.DataFrame, output: Path) -> None:
    """Biểu diễn phân phối residual để nhìn hướng lệch và mức phân tán của từng nhóm."""
    frame = predictions.copy()
    frame["Residual"] = frame["predicted_cutoff"] - frame["cutoff_score_30"]
    frame["Phân nhóm"] = frame["history_segment"].map(SEGMENT_LABELS).fillna(frame["history_segment"])
    fig, ax = plt.subplots(figsize=(13, 7))
    sns.histplot(
        data=frame,
        x="Residual",
        hue="Phân nhóm",
        hue_order=["Có lịch sử", "Cold start"],
        palette=PALETTE,
        bins=np.arange(-12, 12.5, 0.5),
        stat="density",
        common_norm=False,
        element="step",
        fill=True,
        alpha=0.25,
        ax=ax,
    )
    ax.axvline(0, color="#333333", linestyle="--", linewidth=2)
    ax.set_title("Phân phối residual trên test 2024")
    ax.set_xlabel("Residual = điểm dự báo − điểm thực tế")
    ax.set_ylabel("Mật độ")
    ax.text(0.01, 0.96, "Residual > 0: dự báo cao hơn thực tế", transform=ax.transAxes, va="top", fontsize=10)
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output)


def plot_feature_importance(importance: pd.DataFrame, output: Path) -> None:
    """Vẽ 20 feature có importance cao nhất của model cây đã chọn."""
    top = importance.nlargest(20, "importance").sort_values("importance", ascending=True).copy()
    # Bỏ prefix của ColumnTransformer để nhãn trên hình ngắn và dễ đọc hơn.
    top["feature_label"] = top["feature"].str.replace(r"^(numeric|categorical)__", "", regex=True)
    fig, ax = plt.subplots(figsize=(13, 9))
    sns.barplot(data=top, x="importance", y="feature_label", color="#4C78A8", ax=ax)
    ax.set_title("20 feature quan trọng nhất của XGBoost")
    ax.set_xlabel("Feature importance tương đối")
    ax.set_ylabel("Feature sau preprocessing")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.4f", padding=3, fontsize=8)
    ax.margins(x=0.12)
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output)


def main() -> None:
    """Đọc artifact, tạo năm biểu đồ và in đường dẫn để người dùng kiểm tra."""
    args = parse_args()
    evaluation = json.loads(args.evaluation.resolve().read_text(encoding="utf-8"))
    predictions = pd.read_csv(args.predictions.resolve(), low_memory=False)
    importance = pd.read_csv(args.importance.resolve())
    output_dir = args.output_dir.resolve()
    configure_style()

    candidates = candidate_frame(evaluation)
    outputs = [
        output_dir / "01_so_sanh_candidate_validation.png",
        output_dir / "02_hieu_nang_theo_segment_test_2024.png",
        output_dir / "03_thuc_te_va_du_bao_test_2024.png",
        output_dir / "04_phan_phoi_residual_test_2024.png",
        output_dir / "05_top_feature_importance.png",
    ]
    plot_candidate_comparison(candidates, evaluation["selection"]["selected_candidate"], outputs[0])
    plot_test_segments(evaluation, outputs[1])
    plot_actual_vs_predicted(predictions, outputs[2])
    plot_residual_distribution(predictions, outputs[3])
    plot_feature_importance(importance, outputs[4])

    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
