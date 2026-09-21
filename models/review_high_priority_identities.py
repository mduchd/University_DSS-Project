"""Review high-priority identity issues from Step 2 without unsafe auto-merges."""

from __future__ import annotations

import argparse
import json
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STEP2 = ROOT / "data/processed/admission_ml_step2.csv"
DEFAULT_QUEUE = ROOT / "data/processed/admission_ml_review_queue.csv"
DEFAULT_REJECTIONS = ROOT / "data/processed/admission_ml_rejection_review.csv"
DEFAULT_PAIR_REVIEW = ROOT / "data/processed/admission_ml_identity_pair_review.csv"
DEFAULT_HIGH_REVIEW = ROOT / "data/processed/admission_ml_high_priority_reviewed.csv"
DEFAULT_REPORT = ROOT / "data/processed/admission_ml_high_priority_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2-input", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--queue-input", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--rejections-input", type=Path, default=DEFAULT_REJECTIONS)
    parser.add_argument("--pair-review-output", type=Path, default=DEFAULT_PAIR_REVIEW)
    parser.add_argument("--high-review-output", type=Path, default=DEFAULT_HIGH_REVIEW)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def text(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def token_similarity(left: str, right: str) -> tuple[float, float, float]:
    left = text(left)
    right = text(right)
    sequence = SequenceMatcher(None, left, right).ratio() if left and right else 0.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return sequence, jaccard, max(sequence, jaccard)


def parse_years(values: pd.Series) -> set[int]:
    return {int(value) for value in values.dropna().unique()}


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def pairwise_institution_review(data: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reused = data.loc[data["institution_code_reuse"].fillna(False)]
    for admission_code, code_group in reused.groupby("university_admission_code", sort=True):
        entities = sorted(code_group["institution_entity_key"].dropna().unique())
        for left_key, right_key in combinations(entities, 2):
            left = code_group.loc[code_group["institution_entity_key"].eq(left_key)]
            right = code_group.loc[code_group["institution_entity_key"].eq(right_key)]
            left_years = parse_years(left["year"])
            right_years = parse_years(right["year"])
            overlap = sorted(left_years & right_years)
            left_name = text(left["institution_name_normalized"].iloc[0])
            right_name = text(right["institution_name_normalized"].iloc[0])
            sequence, jaccard, similarity = token_similarity(left_name, right_name)
            if overlap:
                decision = "keep_split_same_year_coexistence"
                evidence = "strong_local_evidence"
            elif similarity >= 0.90:
                decision = "candidate_alias_requires_official_verification"
                evidence = "name_similarity_only"
            else:
                decision = "keep_split_conservative"
                evidence = "different_names_no_overlap"
            rows.append(
                {
                    "review_scope": "institution_pair",
                    "parent_key": admission_code,
                    "left_key": left_key,
                    "right_key": right_key,
                    "left_name": text(left["canonical_university_name"].iloc[0]),
                    "right_name": text(right["canonical_university_name"].iloc[0]),
                    "left_years": ";".join(map(str, sorted(left_years))),
                    "right_years": ";".join(map(str, sorted(right_years))),
                    "overlap_years": ";".join(map(str, overlap)),
                    "sequence_similarity": round(sequence, 4),
                    "token_jaccard": round(jaccard, 4),
                    "combined_similarity": round(similarity, 4),
                    "review_decision": decision,
                    "evidence_level": evidence,
                    "auto_merge_applied": False,
                }
            )
    return rows


def pairwise_program_review(data: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reused = data.loc[data["program_code_reuse"].fillna(False)]
    parent_columns = ["institution_entity_key", "major_admission_code"]
    for parent, parent_group in reused.groupby(parent_columns, sort=True, dropna=False):
        series = sorted(parent_group["program_series_key"].dropna().unique())
        for left_key, right_key in combinations(series, 2):
            left = parent_group.loc[parent_group["program_series_key"].eq(left_key)]
            right = parent_group.loc[parent_group["program_series_key"].eq(right_key)]
            left_years = parse_years(left["year"])
            right_years = parse_years(right["year"])
            overlap = sorted(left_years & right_years)
            left_name = text(left["major_name_normalized"].iloc[0])
            right_name = text(right["major_name_normalized"].iloc[0])
            sequence, jaccard, similarity = token_similarity(left_name, right_name)
            left_codes = {text(value) for value in left["major_code"].dropna() if text(value)}
            right_codes = {text(value) for value in right["major_code"].dropna() if text(value)}
            code_overlap = bool(left_codes & right_codes)
            if overlap:
                decision = "keep_split_same_year_coexistence"
                evidence = "strong_local_evidence"
            elif similarity >= 0.90 and code_overlap:
                decision = "candidate_alias_high_confidence_needs_official_verification"
                evidence = "similar_name_and_shared_major_code"
            elif similarity >= 0.78:
                decision = "candidate_alias_medium_confidence_needs_official_verification"
                evidence = "name_similarity_only"
            else:
                decision = "keep_split_conservative"
                evidence = "different_program_names"
            rows.append(
                {
                    "review_scope": "program_pair",
                    "parent_key": f"{parent[0]}|{parent[1]}",
                    "left_key": left_key,
                    "right_key": right_key,
                    "left_name": text(left["canonical_major_name"].iloc[0]),
                    "right_name": text(right["canonical_major_name"].iloc[0]),
                    "left_years": ";".join(map(str, sorted(left_years))),
                    "right_years": ";".join(map(str, sorted(right_years))),
                    "overlap_years": ";".join(map(str, overlap)),
                    "sequence_similarity": round(sequence, 4),
                    "token_jaccard": round(jaccard, 4),
                    "combined_similarity": round(similarity, 4),
                    "major_code_overlap": code_overlap,
                    "review_decision": decision,
                    "evidence_level": evidence,
                    "auto_merge_applied": False,
                }
            )
    return rows


def annotate_high_queue(queue: pd.DataFrame) -> pd.DataFrame:
    high = queue.loc[queue["priority"].eq("high")].copy()
    decisions = {
        "institution_code_reuse": (
            "conservative_split_retained",
            "Pairwise evidence is available; merge only after official verification.",
        ),
        "program_code_reuse": (
            "conservative_split_retained",
            "Pairwise evidence is available; merge only after official verification.",
        ),
        "major_code_conflict": (
            "retain_series_and_verify_official_major_code",
            "The display identity is retained, but the official code requires verification by year.",
        ),
        "sensitive_source_note": (
            "retain_with_sensitive_note_flag",
            "Keep for feature engineering; decide later whether scope/program variant becomes an input feature.",
        ),
        "ambiguous_cutoff": (
            "keep_rejected_until_source_verified",
            "Conflicting targets must not be averaged or restored without source evidence.",
        ),
        "score_scale_mismatch": (
            "keep_rejected_until_scale_verified",
            "Verify original score scale before any normalization.",
        ),
    }
    high["review_decision"] = high["review_type"].map(lambda value: decisions.get(value, ("manual_review", "Inspect source."))[0])
    high["decision_explanation"] = high["review_type"].map(lambda value: decisions.get(value, ("manual_review", "Inspect source."))[1])
    high["data_change_applied"] = False
    return high


def count_dict(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts(dropna=False).items()}


def main() -> None:
    args = parse_args()
    data = pd.read_csv(args.step2_input.resolve(), low_memory=False)
    queue = pd.read_csv(args.queue_input.resolve(), low_memory=False)
    rejections = pd.read_csv(args.rejections_input.resolve(), low_memory=False)

    pair_rows = pairwise_institution_review(data) + pairwise_program_review(data)
    pair_review = pd.DataFrame(pair_rows)
    pair_review = pair_review.sort_values(
        ["review_scope", "parent_key", "review_decision", "combined_similarity"],
        ascending=[True, True, True, False],
        kind="stable",
    ).reset_index(drop=True)
    high_review = annotate_high_queue(queue)

    report = {
        "step": "03a_high_priority_review",
        "policy": {
            "same_year_coexistence": "Strong local evidence to keep two identities separate.",
            "name_similarity": "Creates an alias candidate only; never triggers an automatic merge.",
            "conflicting_cutoffs": "Remain rejected until verified against the original/official source.",
        },
        "high_priority_queue": {
            "items_reviewed": int(len(high_review)),
            "type_counts": count_dict(high_review["review_type"]),
            "decision_counts": count_dict(high_review["review_decision"]),
        },
        "pairwise_identity_review": {
            "pairs": int(len(pair_review)),
            "scope_counts": count_dict(pair_review["review_scope"]),
            "decision_counts": count_dict(pair_review["review_decision"]),
            "strong_keep_split_pairs": int(pair_review["review_decision"].eq("keep_split_same_year_coexistence").sum()),
            "alias_candidates": int(pair_review["review_decision"].str.startswith("candidate_alias").sum()),
            "automatic_merges": int(pair_review["auto_merge_applied"].sum()),
        },
        "rejected_rows_still_rejected": int(len(rejections)),
        "validation": {
            "all_high_priority_items_have_a_decision": bool(high_review["review_decision"].notna().all()),
            "no_identity_merge_applied_without_official_evidence": bool(not pair_review["auto_merge_applied"].any()),
            "no_rejected_row_restored": True,
        },
        "outputs": {
            "identity_pair_review": str(args.pair_review_output.resolve()),
            "high_priority_review": str(args.high_review_output.resolve()),
            "report": str(args.report_output.resolve()),
        },
    }

    atomic_csv(pair_review, args.pair_review_output.resolve())
    atomic_csv(high_review, args.high_review_output.resolve())
    atomic_json(report, args.report_output.resolve())
    print(f"High-priority queue items reviewed: {len(high_review):,}")
    print(f"Identity pairs evaluated: {len(pair_review):,}")
    print(f"Alias candidates requiring official verification: {report['pairwise_identity_review']['alias_candidates']:,}")
    print(f"Automatic identity merges: {report['pairwise_identity_review']['automatic_merges']:,}")


if __name__ == "__main__":
    main()
