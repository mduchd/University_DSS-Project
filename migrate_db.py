"""Synchronise the job-market summary CSV to the Neon PostgreSQL database.

Admission data remains in ``data/master/master_admission.csv``. Keeping that
dataset in one source of truth prevents a partial, stale database copy.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parent
CONNECTION_STRING = os.environ.get("DATABASE_URL")


def calculate_demand_level(posting_count: float) -> str:
    """Classify hiring demand using the same thresholds as the application."""
    if pd.isna(posting_count):
        return "Chưa xác định"
    if posting_count >= 5_000:
        return "Rất cao"
    if posting_count >= 3_000:
        return "Cao"
    if posting_count >= 1_500:
        return "Trung bình"
    return "Ổn định"


def run_migration() -> None:
    if not CONNECTION_STRING:
        raise RuntimeError("DATABASE_URL must be set before running a database migration.")

    jobs_path = ROOT / "data" / "processed" / "jobs" / "job_market_summary_by_category.csv"
    df_jobs = pd.read_csv(jobs_path, encoding="utf-8-sig")
    df_jobs_clean = pd.DataFrame(
        {
            "category_name": df_jobs.get("category_name", df_jobs.get("job_category", "")),
            "posting_count": pd.to_numeric(
                df_jobs.get("posting_count", df_jobs.get("job_posting_count", 0)), errors="coerce"
            ).fillna(0).astype(int),
            "avg_salary_million": pd.to_numeric(
                df_jobs.get("average_salary_million_vnd", df_jobs.get("job_avg_salary_million", 0)),
                errors="coerce",
            ),
            "median_salary_million": pd.to_numeric(
                df_jobs.get("median_salary_million_vnd", df_jobs.get("job_median_salary_million", 0)),
                errors="coerce",
            ),
        }
    )
    df_jobs_clean = df_jobs_clean[df_jobs_clean["category_name"].notna()]
    df_jobs_clean = df_jobs_clean[df_jobs_clean["category_name"].astype(str).str.strip() != ""]
    df_jobs_clean["demand_level"] = df_jobs_clean["posting_count"].map(calculate_demand_level)

    engine = create_engine(CONNECTION_STRING)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS job_categories (
                    id SERIAL PRIMARY KEY,
                    category_name VARCHAR(255) UNIQUE NOT NULL,
                    demand_level VARCHAR(50) NOT NULL,
                    posting_count INT NOT NULL DEFAULT 0,
                    avg_salary_million DECIMAL(5,2),
                    median_salary_million DECIMAL(5,2)
                )
                """
            )
        )
        connection.execute(text("TRUNCATE TABLE job_categories RESTART IDENTITY"))
        df_jobs_clean.to_sql("job_categories", con=connection, if_exists="append", index=False)

    print(f"Synchronised {len(df_jobs_clean)} job categories to PostgreSQL.")


if __name__ == "__main__":
    run_migration()
