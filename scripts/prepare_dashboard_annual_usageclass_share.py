#!/usr/bin/env python3
"""Build annual digital vs physical checkout share data for the dashboard.

This script uses the grouped monthly totals file only. It treats usageclass
labels case-insensitively, but only for the known digital and physical classes.
If a new label appears, the script stops so we do not silently invent meaning.
"""

# %%
from pathlib import Path

import pandas as pd

# %%
SOURCE_PATH = Path("seattle-public-library/combined_checkout_totals_by_month_usageclass.csv")
OUTPUT_PATH = Path("dashboard_data/annual_usageclass_share.csv")

KNOWN_USAGECLASS_LABELS = {
    "digital": "digital",
    "physical": "physical",
}


def load_monthly_usageclass_totals(source_path: Path) -> pd.DataFrame:
    """Read the monthly grouped totals file and validate the input labels."""
    monthly_totals = pd.read_csv(source_path)

    required_columns = {
        "checkout_year",
        "checkout_month",
        "usageclass",
        "total_checkouts",
        "month_total_checkouts",
    }
    missing_columns = required_columns.difference(monthly_totals.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    monthly_totals["usageclass_clean"] = (
        monthly_totals["usageclass"].astype("string").str.strip().str.lower()
    )

    unexpected_labels = sorted(
        set(monthly_totals["usageclass_clean"].dropna().unique())
        - set(KNOWN_USAGECLASS_LABELS)
    )
    if unexpected_labels:
        raise ValueError(
            "Unexpected usageclass labels found in source file: "
            f"{unexpected_labels}. The script only handles digital and physical."
        )

    monthly_totals["usageclass_group"] = monthly_totals["usageclass_clean"].map(
        KNOWN_USAGECLASS_LABELS
    )

    numeric_columns = [
        "checkout_year",
        "checkout_month",
        "total_checkouts",
        "month_total_checkouts",
    ]
    for column_name in numeric_columns:
        monthly_totals[column_name] = pd.to_numeric(monthly_totals[column_name], errors="raise")

    return monthly_totals


def validate_monthly_totals(monthly_totals: pd.DataFrame) -> None:
    """Check that the monthly grouped totals still reconcile to the month total."""
    monthly_check = (
        monthly_totals.groupby(["checkout_year", "checkout_month"], as_index=False)
        .agg(
            usageclass_checkouts=("total_checkouts", "sum"),
            month_total_checkouts=("month_total_checkouts", "first"),
        )
    )

    mismatched_months = monthly_check[
        monthly_check["usageclass_checkouts"] != monthly_check["month_total_checkouts"]
    ]
    if not mismatched_months.empty:
        raise ValueError(
            "Monthly usageclass totals do not match month_total_checkouts for some rows."
        )


def build_annual_share(monthly_totals: pd.DataFrame) -> pd.DataFrame:
    """Aggregate monthly rows to annual digital and physical checkout totals."""
    annual_totals = (
        monthly_totals.groupby(["checkout_year", "usageclass_group"], as_index=False)
        .agg(annual_checkouts=("total_checkouts", "sum"))
    )

    annual_pivot = (
        annual_totals.pivot(
            index="checkout_year",
            columns="usageclass_group",
            values="annual_checkouts",
        )
        .reindex(columns=["digital", "physical"])
        .fillna(0)
        .reset_index()
    )

    annual_pivot["digital_checkouts"] = annual_pivot["digital"]
    annual_pivot["physical_checkouts"] = annual_pivot["physical"]
    annual_pivot["total_checkouts"] = (
        annual_pivot["digital_checkouts"] + annual_pivot["physical_checkouts"]
    )

    # Shares are calculated from annual totals, not by averaging monthly shares.
    annual_pivot["digital_share"] = (
        annual_pivot["digital_checkouts"] / annual_pivot["total_checkouts"]
    )
    annual_pivot["physical_share"] = (
        annual_pivot["physical_checkouts"] / annual_pivot["total_checkouts"]
    )

    output_columns = [
        "checkout_year",
        "digital_checkouts",
        "physical_checkouts",
        "total_checkouts",
        "digital_share",
        "physical_share",
    ]

    annual_output = annual_pivot.loc[:, output_columns].copy()
    annual_output["checkout_year"] = annual_output["checkout_year"].astype(int)

    return annual_output.sort_values("checkout_year").reset_index(drop=True)


def main() -> None:
    monthly_totals = load_monthly_usageclass_totals(SOURCE_PATH)
    validate_monthly_totals(monthly_totals)

    annual_share = build_annual_share(monthly_totals)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    annual_share.to_csv(OUTPUT_PATH, index=False, float_format="%.8f")

    print(f"Wrote {len(annual_share)} rows to {OUTPUT_PATH}")


# %%
if __name__ == "__main__":
    main()
