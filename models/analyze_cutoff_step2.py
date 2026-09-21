"""Step 2: resolve temporal identities and review rejected/flagged cutoff rows.

The script is deliberately conservative. It creates safer institution/program
series keys and review queues, but never silently restores a rejected row or
merges identities whose names conflict.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_INPUT = PROJECT_ROOT / "data/processed/admission_ml_base.csv"
DEFAULT_REJECTED_INPUT = PROJECT_ROOT / "data/processed/admission_ml_rejected.csv"
DEFAULT_STEP2_OUTPUT = PROJECT_ROOT / "data/processed/admission_ml_step2.csv"
DEFAULT_INSTITUTION_MAP = PROJECT_ROOT / "data/processed/admission_ml_institution_map.csv"
DEFAULT_PROGRAM_MAP = PROJECT_ROOT / "data/processed/admission_ml_program_map.csv"
DEFAULT_REJECTION_REVIEW = PROJECT_ROOT / "data/processed/admission_ml_rejection_review.csv"
DEFAULT_REVIEW_QUEUE = PROJECT_ROOT / "data/processed/admission_ml_review_queue.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data/processed/admission_ml_step2_report.json"

MODEL_KEY = ["year", "university_admission_code", "major_admission_code", "subject_combination"]
AMBIGUOUS_REASON = "ambiguous_multiple_cutoffs_for_model_key"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-input", type=Path, default=DEFAULT_BASE_INPUT)
    parser.add_argument("--rejected-input", type=Path, default=DEFAULT_REJECTED_INPUT)
    parser.add_argument("--step2-output", type=Path, default=DEFAULT_STEP2_OUTPUT)
    parser.add_argument("--institution-map", type=Path, default=DEFAULT_INSTITUTION_MAP)
    parser.add_argument("--program-map", type=Path, default=DEFAULT_PROGRAM_MAP)
    parser.add_argument("--rejection-review", type=Path, default=DEFAULT_REJECTION_REVIEW)
    parser.add_argument("--review-queue", type=Path, default=DEFAULT_REVIEW_QUEUE)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def text(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def normalize_text(value: Any) -> str:
    raw = text(value).lower().replace("đ", "d")
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(character for character in raw if not unicodedata.combining(character))
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def normalize_institution_name(value: Any) -> str:
    """Normalize display-only legal prefixes while preserving identity words."""
    normalized = normalize_text(value)
    normalized = re.sub(r"\btruong\b", " ", normalized)
    normalized = re.sub(r"\bdai hoc\b", " ", normalized)
    normalized = normalized.replace("thanh pho ho chi minh", "tphcm")
    normalized = re.sub(r"\btp hcm\b", "tphcm", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def stable_join(values: Iterable[Any], separator: str = " || ") -> str:
    cleaned = sorted({text(value) for value in values if text(value)})
    return separator.join(cleaned)


def year_join(values: Iterable[Any]) -> str:
    years = sorted({int(value) for value in values if not pd.isna(value)})
    return ";".join(str(year) for year in years)


def choose_display(group: pd.DataFrame, column: str) -> str:
    """Choose the most recent non-empty display value, then the most frequent."""
    candidates = group.loc[group[column].notna() & group[column].astype("string").str.strip().ne("")].copy()
    if candidates.empty:
        return ""
    counts = candidates[column].value_counts()
    candidates["_display_count"] = candidates[column].map(counts)
    candidates = candidates.sort_values(["year", "_display_count"], ascending=[False, False], kind="stable")
    return text(candidates.iloc[0][column])


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


def classify_note(note: Any) -> tuple[str, str]:
    normalized = normalize_text(note)
    if not normalized:
        return "empty", "none"

    categories: list[str] = []
    if re.search(r"hoc ba|dgnl|danh gia nang luc|chua co diem", normalized):
        categories.append("method_or_target_mismatch")
    if re.search(
        r"chat luong cao|\bclc\b|tien tien|dai tra|tang cuong|quoc te|lien ket|"
        r"tieng anh|tieng viet|chuong trinh",
        normalized,
    ):
        categories.append("program_variant")
    if re.search(r"co so|phan hieu|phia bac|phia nam|mien bac|mien nam|thi sinh nam|thi sinh nu", normalized):
        categories.append("location_or_candidate_scope")
    if re.search(
        r"tieu chi phu|ttnv|thu tu nguyen vong|mon chinh|nhan he so|hoc luc|dtb|"
        r"nguyen vong\s*[<=>]|>=|<=",
        normalized,
    ):
        categories.append("eligibility_or_tiebreak")
    if re.search(r"thang diem\s*(30|40)", normalized):
        categories.append("score_scale_description")
    if re.search(r"diem thi|tot nghiep thpt|tn thpt|tnthpt", normalized):
        categories.append("exam_method_description")

    if not categories:
        return "other_note", "medium"
    priority = "high" if any(
        category in categories
        for category in {
            "method_or_target_mismatch",
            "program_variant",
            "location_or_candidate_scope",
            "eligibility_or_tiebreak",
        }
    ) else "low"
    return "|".join(categories), priority


def prepare_identity_columns(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["institution_name_normalized"] = data["university_name"].map(normalize_institution_name)
    fallback_institution = data["university_code"].map(normalize_text)
    data["institution_name_normalized"] = data["institution_name_normalized"].mask(
        data["institution_name_normalized"].eq(""), fallback_institution
    )
    data["institution_entity_key"] = (
        data["university_admission_code"].astype("string").str.strip()
        + "|"
        + data["institution_name_normalized"]
    )
    data["major_name_normalized"] = data["major_name"].map(normalize_text)
    fallback_major = data["major_code"].map(normalize_text)
    data["major_name_normalized"] = data["major_name_normalized"].mask(
        data["major_name_normalized"].eq(""), fallback_major
    )
    data["major_group_normalized"] = data["major_group_name"].map(normalize_text)
    data["program_series_key"] = (
        data["institution_entity_key"]
        + "|"
        + data["major_admission_code"].astype("string").str.strip()
        + "|"
        + data["major_name_normalized"]
    )
    return data


def build_institution_map(data: pd.DataFrame) -> pd.DataFrame:
    code_variant_counts = data.groupby("university_admission_code")["institution_entity_key"].nunique()
    rows: list[dict[str, Any]] = []
    for entity_key, group in data.groupby("institution_entity_key", sort=True, dropna=False):
        admission_code = text(group["university_admission_code"].iloc[0])
        rows.append(
            {
                "institution_entity_key": entity_key,
                "university_admission_code": admission_code,
                "canonical_university_name": choose_display(group, "university_name"),
                "university_name_variants": stable_join(group["university_name"]),
                "university_code_variants": stable_join(group["university_code"]),
                "years": year_join(group["year"]),
                "year_count": int(group["year"].nunique()),
                "row_count": int(len(group)),
                "entities_sharing_admission_code": int(code_variant_counts.loc[admission_code]),
                "institution_code_reuse": bool(code_variant_counts.loc[admission_code] > 1),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["university_admission_code", "institution_entity_key"], kind="stable"
    ).reset_index(drop=True)


def build_program_map(data: pd.DataFrame) -> pd.DataFrame:
    parent = ["institution_entity_key", "major_admission_code"]
    name_counts = data.groupby(parent, dropna=False)["major_name_normalized"].nunique()
    rows: list[dict[str, Any]] = []
    for series_key, group in data.groupby("program_series_key", sort=True, dropna=False):
        parent_key = (group["institution_entity_key"].iloc[0], group["major_admission_code"].iloc[0])
        raw_name_count = int(group["major_name"].dropna().nunique())
        normalized_count = int(name_counts.loc[parent_key])
        major_code_count = int(group["major_code"].dropna().nunique())
        group_count = int(group["major_group_name"].dropna().nunique())
        if not text(group["major_name_normalized"].iloc[0]):
            status = "review_missing_major_name"
        elif normalized_count > 1:
            status = "split_program_code_reuse"
        elif raw_name_count > 1:
            status = "safe_text_normalization"
        else:
            status = "stable_exact_name"
        rows.append(
            {
                "program_series_key": series_key,
                "institution_entity_key": parent_key[0],
                "university_admission_code": text(group["university_admission_code"].iloc[0]),
                "major_admission_code": text(parent_key[1]),
                "canonical_major_name": choose_display(group, "major_name"),
                "major_name_variants": stable_join(group["major_name"]),
                "major_code_variants": stable_join(group["major_code"]),
                "major_group_variants": stable_join(group["major_group_name"]),
                "years": year_join(group["year"]),
                "year_count": int(group["year"].nunique()),
                "row_count": int(len(group)),
                "normalized_names_sharing_program_code": normalized_count,
                "major_code_variant_count": major_code_count,
                "major_group_variant_count_step2": group_count,
                "program_identity_status": status,
                "program_code_reuse": bool(normalized_count > 1),
                "major_code_conflict": bool(major_code_count > 1),
                "group_taxonomy_changed": bool(group_count > 1),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["university_admission_code", "major_admission_code", "program_series_key"], kind="stable"
    ).reset_index(drop=True)


def analyze_ambiguous_groups(rejected: pd.DataFrame) -> pd.DataFrame:
    ambiguous = rejected.loc[rejected["rejection_reason"].eq(AMBIGUOUS_REASON)].copy()
    if ambiguous.empty:
        return pd.DataFrame(columns=MODEL_KEY + ["ambiguity_class", "recommended_action"])
    ambiguous = prepare_identity_columns(ambiguous)
    results: list[dict[str, Any]] = []
    for key, group in ambiguous.groupby(MODEL_KEY, sort=True, dropna=False):
        identity_columns = ["major_code", "major_name_normalized"]
        identity_targets = group.groupby(identity_columns, dropna=False)["cutoff_score_30"].nunique()
        scoped_columns = identity_columns + ["gender_requirement", "campus"]
        scoped_targets = group.groupby(scoped_columns, dropna=False)["cutoff_score_30"].nunique()
        if len(identity_targets) > 1 and bool(identity_targets.le(1).all()):
            classification = "candidate_split_by_program_identity"
            action = "Verify distinct major/program identities; do not average their cutoffs."
        elif len(scoped_targets) > 1 and bool(scoped_targets.le(1).all()):
            classification = "candidate_split_by_gender_or_campus"
            action = "Add candidate scope/campus to the product requirements before restoring."
        else:
            classification = "unresolved_conflicting_cutoffs"
            action = "Check the original source or official admission notice."
        record = dict(zip(MODEL_KEY, key, strict=True))
        record.update(
            {
                "ambiguity_class": classification,
                "recommended_action": action,
                "source_row_count": int(len(group)),
                "target_variant_count": int(group["cutoff_score_30"].nunique()),
                "target_values": stable_join(group["cutoff_score_30"], separator=";"),
                "major_name_variants": stable_join(group["major_name"]),
                "major_code_variants": stable_join(group["major_code"]),
                "gender_variants": stable_join(group["gender_requirement"]),
                "campus_variants": stable_join(group["campus"]),
                "note_variants": stable_join(group["note"]),
            }
        )
        results.append(record)
    return pd.DataFrame(results)


def annotate_rejections(rejected: pd.DataFrame, ambiguous_groups: pd.DataFrame) -> pd.DataFrame:
    reviewed = rejected.copy()
    if not ambiguous_groups.empty:
        reviewed = reviewed.merge(
            ambiguous_groups[MODEL_KEY + ["ambiguity_class", "recommended_action"]],
            on=MODEL_KEY,
            how="left",
            validate="many_to_one",
        )
    else:
        reviewed["ambiguity_class"] = pd.NA
        reviewed["recommended_action"] = pd.NA

    reason = reviewed["rejection_reason"].fillna("")
    category = pd.Series("other_rejection", index=reviewed.index, dtype="string")
    action = pd.Series("Inspect source row manually.", index=reviewed.index, dtype="string")

    non_thpt = reason.str.contains("non_thpt_admission_method", regex=False)
    invalid_combo = reason.str.contains("invalid_subject_combination", regex=False) & ~non_thpt
    invalid_score = reason.str.contains("cutoff_score_30_outside_0_30", regex=False)
    ambiguous = reason.eq(AMBIGUOUS_REASON)

    category = category.mask(non_thpt, "out_of_scope_non_thpt")
    action = action.mask(non_thpt, "Keep outside the THPTQG cutoff prediction dataset.")
    category = category.mask(invalid_combo, "unsupported_nonstandard_combination")
    action = action.mask(
        invalid_combo,
        "Verify whether this is an aptitude/competency route or a malformed subject combination.",
    )
    category = category.mask(invalid_score, "score_scale_mismatch")
    action = action.mask(invalid_score, "Verify the original scale and normalization rule.")
    category = category.mask(ambiguous, reviewed["ambiguity_class"].fillna("unresolved_conflicting_cutoffs"))
    action = action.mask(ambiguous, reviewed["recommended_action"].fillna("Check the original source."))

    reviewed["step2_rejection_category"] = category
    reviewed["step2_recommended_action"] = action
    reviewed["step2_recover_automatically"] = False
    return reviewed


def build_review_queue(
    data: pd.DataFrame,
    institution_map: pd.DataFrame,
    program_map: pd.DataFrame,
    ambiguous_groups: pd.DataFrame,
    rejected_review: pd.DataFrame,
) -> pd.DataFrame:
    queue: list[dict[str, Any]] = []

    for code, group in institution_map.loc[institution_map["institution_code_reuse"]].groupby(
        "university_admission_code", sort=True
    ):
        queue.append(
            {
                "review_type": "institution_code_reuse",
                "priority": "high",
                "review_key": code,
                "affected_rows": int(group["row_count"].sum()),
                "details": stable_join(group["canonical_university_name"]),
                "recommended_action": "Confirm that each normalized institution entity is a distinct school/campus.",
            }
        )

    reused_programs = program_map.loc[program_map["program_code_reuse"]]
    for parent, group in reused_programs.groupby(
        ["institution_entity_key", "major_admission_code"], sort=True, dropna=False
    ):
        queue.append(
            {
                "review_type": "program_code_reuse",
                "priority": "high",
                "review_key": f"{parent[0]}|{parent[1]}",
                "affected_rows": int(group["row_count"].sum()),
                "details": stable_join(group["canonical_major_name"]),
                "recommended_action": "Confirm the split program series; never combine unrelated historical cutoffs.",
            }
        )

    for _, row in program_map.loc[program_map["major_code_conflict"]].iterrows():
        queue.append(
            {
                "review_type": "major_code_conflict",
                "priority": "high",
                "review_key": row["program_series_key"],
                "affected_rows": int(row["row_count"]),
                "details": row["major_code_variants"],
                "recommended_action": "Verify the official major code by year.",
            }
        )

    high_notes = data.loc[data["note_review_priority"].eq("high")]
    for series_key, group in high_notes.groupby("program_series_key", sort=True, dropna=False):
        queue.append(
            {
                "review_type": "sensitive_source_note",
                "priority": "high",
                "review_key": series_key,
                "affected_rows": int(len(group)),
                "details": stable_join(group["note_category"]),
                "recommended_action": "Decide whether program variant/scope must become a model feature.",
            }
        )

    for _, row in ambiguous_groups.iterrows():
        queue.append(
            {
                "review_type": "ambiguous_cutoff",
                "priority": "high",
                "review_key": "|".join(text(row[column]) for column in MODEL_KEY),
                "affected_rows": int(row["source_row_count"]),
                "details": f"{row['ambiguity_class']}: {row['target_values']}",
                "recommended_action": row["recommended_action"],
            }
        )

    non_ambiguous_rejects = rejected_review.loc[
        ~rejected_review["rejection_reason"].eq(AMBIGUOUS_REASON)
    ]
    for (category, value), group in non_ambiguous_rejects.groupby(
        ["step2_rejection_category", "subject_combination"], sort=True, dropna=False
    ):
        queue.append(
            {
                "review_type": category,
                "priority": "high" if category == "score_scale_mismatch" else "medium",
                "review_key": text(value) or "<blank>",
                "affected_rows": int(len(group)),
                "details": stable_join(group["admission_method"]),
                "recommended_action": text(group["step2_recommended_action"].iloc[0]),
            }
        )

    result = pd.DataFrame(queue)
    priority_order = pd.Categorical(result["priority"], categories=["high", "medium", "low"], ordered=True)
    result = result.assign(_priority_order=priority_order).sort_values(
        ["_priority_order", "review_type", "affected_rows"], ascending=[True, True, False], kind="stable"
    )
    return result.drop(columns="_priority_order").reset_index(drop=True)


def counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts(dropna=False).items()}


def main() -> None:
    args = parse_args()
    base = pd.read_csv(args.base_input.resolve(), low_memory=False)
    rejected = pd.read_csv(args.rejected_input.resolve(), low_memory=False)

    data = prepare_identity_columns(base)
    note_classification = data["note"].map(classify_note)
    data["note_category"] = note_classification.map(lambda value: value[0])
    data["note_review_priority"] = note_classification.map(lambda value: value[1])

    institution_map = build_institution_map(data)
    program_map = build_program_map(data)
    data = data.merge(
        institution_map[
            [
                "institution_entity_key",
                "canonical_university_name",
                "entities_sharing_admission_code",
                "institution_code_reuse",
            ]
        ],
        on="institution_entity_key",
        how="left",
        validate="many_to_one",
    )
    data = data.merge(
        program_map[
            [
                "program_series_key",
                "canonical_major_name",
                "program_identity_status",
                "program_code_reuse",
                "major_code_conflict",
                "group_taxonomy_changed",
            ]
        ],
        on="program_series_key",
        how="left",
        validate="many_to_one",
    )

    data["step2_review_priority"] = "none"
    medium = (
        data["source_note_review_flag"].fillna(False)
        | data["group_taxonomy_changed"]
        | data["duplicate_same_target_collapsed"].fillna(False)
    )
    high = (
        data["institution_code_reuse"]
        | data["program_code_reuse"]
        | data["major_code_conflict"]
        | data["note_review_priority"].eq("high")
    )
    data.loc[medium, "step2_review_priority"] = "medium"
    data.loc[high, "step2_review_priority"] = "high"
    data["step2_manual_review_required"] = data["step2_review_priority"].eq("high")
    data["training_eligible_step2"] = True

    data["series_combination_key"] = data["program_series_key"] + "|" + data["subject_combination"]
    history = data.groupby("series_combination_key").agg(
        series_year_count=("year", "nunique"),
        series_first_year=("year", "min"),
        series_last_year=("year", "max"),
    )
    data = data.merge(history, on="series_combination_key", how="left", validate="many_to_one")

    ambiguous_groups = analyze_ambiguous_groups(rejected)
    rejected_review = annotate_rejections(rejected, ambiguous_groups)
    review_queue = build_review_queue(data, institution_map, program_map, ambiguous_groups, rejected_review)

    step2_key = ["year", "program_series_key", "subject_combination"]
    duplicate_step2_keys = int(data.duplicated(step2_key).sum())
    if duplicate_step2_keys:
        raise AssertionError(f"Step 2 produced {duplicate_step2_keys} duplicate temporal keys.")
    if len(data) != len(base):
        raise AssertionError("Step 2 unexpectedly changed the accepted row count.")
    if len(rejected_review) != len(rejected):
        raise AssertionError("Step 2 unexpectedly changed the rejected row count.")

    data = data.sort_values(step2_key, kind="stable").reset_index(drop=True)
    report = {
        "step": "02_identity_and_review_analysis",
        "policy": {
            "identity": (
                "Use normalized institution and major names to split reused codes. "
                "Never merge conflicting names automatically."
            ),
            "rejected_rows": "Annotate only; no rejected row is restored automatically.",
            "group_taxonomy": (
                "A changing major group is a review signal, not by itself proof that the program identity changed."
            ),
        },
        "accepted_data": {
            "input_rows": int(len(base)),
            "output_rows": int(len(data)),
            "institution_entities": int(data["institution_entity_key"].nunique()),
            "admission_codes_used_by_multiple_institution_entities": int(
                institution_map.loc[institution_map["institution_code_reuse"], "university_admission_code"].nunique()
            ),
            "program_series": int(data["program_series_key"].nunique()),
            "program_parent_keys_split_by_name": int(
                program_map.loc[program_map["program_code_reuse"],
                                ["institution_entity_key", "major_admission_code"]].drop_duplicates().shape[0]
            ),
            "program_series_with_major_code_conflict": int(program_map["major_code_conflict"].sum()),
            "program_series_with_group_taxonomy_change": int(program_map["group_taxonomy_changed"].sum()),
            "review_priority_counts": counts(data["step2_review_priority"]),
            "note_category_counts": counts(data["note_category"]),
            "series_year_count_distribution": counts(data["series_year_count"]),
        },
        "rejected_data": {
            "input_rows": int(len(rejected)),
            "output_rows": int(len(rejected_review)),
            "category_counts": counts(rejected_review["step2_rejection_category"]),
            "ambiguous_group_counts": counts(ambiguous_groups["ambiguity_class"]),
            "automatically_recovered_rows": int(rejected_review["step2_recover_automatically"].sum()),
        },
        "review_queue": {
            "items": int(len(review_queue)),
            "priority_counts": counts(review_queue["priority"]),
            "type_counts": counts(review_queue["review_type"]),
        },
        "validation": {
            "accepted_row_count_preserved": bool(len(data) == len(base)),
            "rejected_row_count_preserved": bool(len(rejected_review) == len(rejected)),
            "step2_temporal_key_is_unique": bool(duplicate_step2_keys == 0),
            "no_rejected_row_was_auto_recovered": bool(
                not rejected_review["step2_recover_automatically"].any()
            ),
        },
        "outputs": {
            "step2_dataset": str(args.step2_output.resolve()),
            "institution_map": str(args.institution_map.resolve()),
            "program_map": str(args.program_map.resolve()),
            "rejection_review": str(args.rejection_review.resolve()),
            "review_queue": str(args.review_queue.resolve()),
            "report": str(args.report_output.resolve()),
        },
    }

    atomic_csv(data, args.step2_output.resolve())
    atomic_csv(institution_map, args.institution_map.resolve())
    atomic_csv(program_map, args.program_map.resolve())
    atomic_csv(rejected_review, args.rejection_review.resolve())
    atomic_csv(review_queue, args.review_queue.resolve())
    atomic_json(report, args.report_output.resolve())

    print(f"Accepted rows enriched: {len(data):,}")
    print(f"Institution entities: {data['institution_entity_key'].nunique():,}")
    print(f"Program series: {data['program_series_key'].nunique():,}")
    print(f"High-priority accepted rows: {data['step2_manual_review_required'].sum():,}")
    print(f"Rejected rows annotated: {len(rejected_review):,}")
    print(f"Review queue items: {len(review_queue):,}")


if __name__ == "__main__":
    main()
