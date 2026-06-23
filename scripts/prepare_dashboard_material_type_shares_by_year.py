#!/usr/bin/env python3
"""Prepare sampled material-type shares by year for the dashboard.

Important caveat:
The digital and physical inputs are sampled title-month rows. The outputs from
this script summarize the sampled rows only. They are useful for comparing the
sample composition by year and material type, but they do not describe complete
system totals.
"""

from __future__ import annotations

# %%

from pathlib import Path

import pandas as pd

# %%

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "seattle-public-library"
OUTPUT_DIR = BASE_DIR / "dashboard_data"

DIGITAL_SOURCE = SOURCE_DIR / "digital_checkout_title_sample_balanced_250k.csv"
PHYSICAL_SOURCE = SOURCE_DIR / "physical_checkout_title_sample_balanced_250k.csv"

# %%

def prepare_material_type_shares(source_path: Path, output_path: Path) -> pd.DataFrame:
    """Aggregate sampled title-month rows into year and material type shares."""
    sampled_rows = pd.read_csv(
        source_path,
        usecols=["usageclass", "materialtype", "checkoutyear", "checkouts"],
        dtype={
            "usageclass": "string",
            "materialtype": "string",
            "checkoutyear": "int64",
            "checkouts": "int64",
        },
    )

    required_columns = {
        "usageclass",
        "materialtype",
        "checkoutyear",
        "checkouts",
    }
    missing_columns = sorted(required_columns.difference(sampled_rows.columns))
    if missing_columns:
        raise ValueError(
            f"{source_path.name} is missing required columns: {', '.join(missing_columns)}"
        )

    # Each row is one sampled title-month record, so a row count is a sample-size
    # measure for the grouped output, not a total from the full library system.
    material_by_year = (
        sampled_rows.groupby(
            ["usageclass", "checkoutyear", "materialtype"], as_index=False
        )
        .agg(
            sampled_material_checkouts=("checkouts", "sum"),
            sample_rows=("checkouts", "size"),
        )
        .sort_values(["checkoutyear", "materialtype"], kind="stable")
        .reset_index(drop=True)
    )

    year_totals = (
        sampled_rows.groupby(["usageclass", "checkoutyear"], as_index=False)
        .agg(sampled_year_checkouts=("checkouts", "sum"))
        .sort_values(["checkoutyear"], kind="stable")
        .reset_index(drop=True)
    )

    result = material_by_year.merge(
        year_totals,
        on=["usageclass", "checkoutyear"],
        how="left",
        validate="many_to_one",
    )

    result["sampled_material_share"] = (
        result["sampled_material_checkouts"] / result["sampled_year_checkouts"]
    )

    result = result[
        [
            "usageclass",
            "checkoutyear",
            "materialtype",
            "sampled_material_checkouts",
            "sampled_year_checkouts",
            "sampled_material_share",
            "sample_rows",
        ]
    ].sort_values(["checkoutyear", "materialtype"], kind="stable")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result

# %%

def main() -> None:
    digital_output = OUTPUT_DIR / "digital_material_type_shares_by_year.csv"
    physical_output = OUTPUT_DIR / "physical_material_type_shares_by_year.csv"

    digital_result = prepare_material_type_shares(DIGITAL_SOURCE, digital_output)
    physical_result = prepare_material_type_shares(PHYSICAL_SOURCE, physical_output)

    print(
        f"Wrote {digital_output.relative_to(BASE_DIR)} with {digital_result.shape[0]} rows "
        f"and {digital_result.shape[1]} columns."
    )
    print(
        f"Wrote {physical_output.relative_to(BASE_DIR)} with {physical_result.shape[0]} rows "
        f"and {physical_result.shape[1]} columns."
    )

# %%

if __name__ == "__main__":
    main()
