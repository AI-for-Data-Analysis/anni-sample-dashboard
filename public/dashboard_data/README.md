# Seattle Public Library Dashboard Data

This directory contains CSV files prepared for the Seattle Public Library checkout dashboard.
The files are generated from percent-cell Python scripts in `scripts/`.

## Regenerate all dashboard data

From the repository root, run:

```bash
.venv/bin/python scripts/prepare_dashboard_annual_usageclass_share.py
.venv/bin/python scripts/prepare_dashboard_top_sampled_titles_by_year.py
.venv/bin/python scripts/prepare_dashboard_material_type_shares_by_year.py
```

## File provenance

| Dashboard CSV | Generating script | Source file(s) | Data basis | Row meaning |
| --- | --- | --- | --- | --- |
| `annual_usageclass_share.csv` | `scripts/prepare_dashboard_annual_usageclass_share.py` | `seattle-public-library/combined_checkout_totals_by_month_usageclass.csv` | Complete grouped monthly totals | One row per checkout year with annual digital, physical, and total checkouts plus digital and physical annual share. |
| `digital_top_sampled_titles_by_year.csv` | `scripts/prepare_dashboard_top_sampled_titles_by_year.py` | `seattle-public-library/digital_checkout_title_sample_balanced_250k.csv` | Sampled title-month rows | One row per checkout year and ranked sampled digital title, limited to the top 10 sampled titles per year by total sampled checkouts. |
| `physical_top_sampled_titles_by_year.csv` | `scripts/prepare_dashboard_top_sampled_titles_by_year.py` | `seattle-public-library/physical_checkout_title_sample_balanced_250k.csv` | Sampled title-month rows | One row per checkout year and ranked sampled physical title, limited to the top 10 sampled titles per year by total sampled checkouts. |
| `digital_material_type_shares_by_year.csv` | `scripts/prepare_dashboard_material_type_shares_by_year.py` | `seattle-public-library/digital_checkout_title_sample_balanced_250k.csv` | Sampled title-month rows | One row per checkout year and digital material type with sampled checkouts, sampled year checkouts, material share, and sample row count. |
| `physical_material_type_shares_by_year.csv` | `scripts/prepare_dashboard_material_type_shares_by_year.py` | `seattle-public-library/physical_checkout_title_sample_balanced_250k.csv` | Sampled title-month rows | One row per checkout year and physical material type with sampled checkouts, sampled year checkouts, material share, and sample row count. |

## Caveats to preserve

- Use `annual_usageclass_share.csv` for system-level digital versus physical checkout trends because it comes from complete grouped monthly totals.
- The title and material-type outputs come from balanced sampled title-month files. They support dashboard views of sample composition and sampled title behavior, not complete library-wide title or material totals.
- In the top-title files, `total_sampled_checkouts` is the sum of `checkouts` within the sampled rows for that checkout year and title.
- Top-title metadata is preserved by concatenating distinct values when a title has multiple metadata values within the same checkout year.
- Subject, creator, publisher, ISBN, and publication year fields can be missing or messy in the sampled files.
