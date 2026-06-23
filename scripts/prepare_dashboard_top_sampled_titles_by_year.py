#!/usr/bin/env python3
"""Prepare top sampled titles by year for the Seattle Public Library dashboard.

This script works from the sampled title-month files, not the source system totals.
The outputs are therefore top titles within the sampled rows and should not be
described as complete library-wide totals.
"""

from __future__ import annotations

# %%

from pathlib import Path

import pandas as pd

# %%

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "seattle-public-library"
OUTPUT_DIR = BASE_DIR / "dashboard_data"

TOP_N_PER_YEAR = 10

OUTPUT_COLUMNS = [
    "checkoutyear",
    "rank_in_year",
    "total_sampled_checkouts",
    "usageclass",
    "checkouttype",
    "materialtype",
    "title",
    "isbn",
    "creator",
    "subjects",
    "publisher",
    "publicationyear",
    "sample_design",
]

TEXT_COLUMNS = [
    "usageclass",
    "checkouttype",
    "materialtype",
    "title",
    "isbn",
    "creator",
    "subjects",
    "publisher",
    "publicationyear",
    "sample_design",
]

# %%


def join_distinct_values(values: pd.Series) -> str:
    """Join distinct non-empty values in a deterministic order."""
    cleaned_values = []
    for value in values:
        if pd.isna(value):
            continue
        text_value = str(value).strip()
        if text_value == "":
            continue
        cleaned_values.append(text_value)

    distinct_values = sorted(set(cleaned_values))
    return " | ".join(distinct_values)


def load_sample_file(path: Path) -> pd.DataFrame:
    """Load one sampled title-month file and normalize text fields."""
    read_dtype = {column: "string" for column in TEXT_COLUMNS}
    frame = pd.read_csv(path, dtype=read_dtype, low_memory=False)

    frame["checkoutyear"] = pd.to_numeric(frame["checkoutyear"], errors="coerce").astype("Int64")
    frame["checkouts"] = pd.to_numeric(frame["checkouts"], errors="coerce")

    return frame


def top_titles_by_year(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sampled checkouts by year and title, then rank the titles."""
    aggregation_map = {"checkouts": "sum"}
    metadata_columns = [column for column in TEXT_COLUMNS if column != "title"]
    for column in metadata_columns:
        aggregation_map[column] = join_distinct_values

    grouped = (
        frame.groupby(["checkoutyear", "title"], dropna=False, as_index=False)
        .agg(aggregation_map)
        .rename(columns={"checkouts": "total_sampled_checkouts"})
    )

    grouped["checkoutyear"] = grouped["checkoutyear"].astype(int)
    grouped["total_sampled_checkouts"] = grouped["total_sampled_checkouts"].fillna(0).astype(int)

    grouped = grouped.sort_values(
        by=["checkoutyear", "total_sampled_checkouts", "title"],
        ascending=[True, False, True],
        kind="mergesort",
    )

    grouped["rank_in_year"] = grouped.groupby("checkoutyear").cumcount() + 1
    top_grouped = grouped[grouped["rank_in_year"] <= TOP_N_PER_YEAR].copy()

    top_grouped = top_grouped[OUTPUT_COLUMNS]
    top_grouped = top_grouped.sort_values(
        by=["checkoutyear", "rank_in_year", "title"],
        ascending=[True, True, True],
        kind="mergesort",
    )

    return top_grouped.reset_index(drop=True)


def prepare_one_class(input_filename: str, output_filename: str) -> pd.DataFrame:
    """Build one dashboard CSV for a single usage class."""
    input_path = INPUT_DIR / input_filename
    output_path = OUTPUT_DIR / output_filename

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sample_frame = load_sample_file(input_path)
    top_frame = top_titles_by_year(sample_frame)
    top_frame.to_csv(output_path, index=False)

    return top_frame

# %%


def main() -> None:
    """Write the digital and physical dashboard extracts."""
    digital = prepare_one_class(
        "digital_checkout_title_sample_balanced_250k.csv",
        "digital_top_sampled_titles_by_year.csv",
    )
    physical = prepare_one_class(
        "physical_checkout_title_sample_balanced_250k.csv",
        "physical_top_sampled_titles_by_year.csv",
    )

    print(
        f"Wrote {OUTPUT_DIR / 'digital_top_sampled_titles_by_year.csv'} "
        f"with shape {digital.shape}"
    )
    print(
        f"Wrote {OUTPUT_DIR / 'physical_top_sampled_titles_by_year.csv'} "
        f"with shape {physical.shape}"
    )


if __name__ == "__main__":
    main()
