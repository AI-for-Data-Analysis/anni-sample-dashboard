# Analysis Output Provenance

These files were generated from the Seattle Public Library checkout data in this
repository.

## Source Files

- `seattle-public-library/digital_checkout_title_sample_balanced_250k.csv`
  - One row represents one sampled digital title in one month of one year.
  - Used to create the digital title popularity outputs and the digital
    material-type share output.
- `seattle-public-library/physical_checkout_title_sample_balanced_250k.csv`
  - One row represents one sampled physical title in one month of one year.
  - Used to create the physical title popularity outputs and the physical
    material-type share output.
- `seattle-public-library/combined_checkout_totals_by_month_usageclass.csv`
  - One row represents one usage class in one month of one year.
  - Used to create the annual digital vs. physical share output.

The schema reference for these source files is
`seattle-public-library/README.md`.

## Generated Files

- `most_popular_digital_titles_by_year.csv`
  - One row per year.
  - Shows the digital title with the highest summed sampled checkouts in that
    year.
  - Includes collapsed descriptive fields for the winning title-year, using
    semicolon-separated unique values where multiple source values are present.
- `most_popular_physical_titles_by_year.csv`
  - One row per year.
  - Shows the physical title with the highest summed sampled checkouts in that
    year.
  - Includes collapsed descriptive fields for the winning title-year, using
    semicolon-separated unique values where multiple source values are present.
- `title_popularity_winning_digital_title_month_rows.csv`
  - Preserves all original sampled digital title-month rows for the winning
    digital title-year combinations.
- `title_popularity_winning_physical_title_month_rows.csv`
  - Preserves all original sampled physical title-month rows for the winning
    physical title-year combinations.
- `digital_physical_share_by_year.csv`
  - One row per year and usage class.
  - Uses complete monthly totals, aggregated to annual totals.
  - Includes annual usage-class checkouts, annual total checkouts, annual share,
    months represented, and supporting row-count fields.
- `physical_material_share_by_year.csv`
  - One row per year and physical `materialtype`.
  - Uses sampled physical title-month rows.
  - Material type labels are normalized to uppercase before grouping.
  - Includes material-type checkouts, annual sampled physical checkouts,
    material-type share, and sampled title-month row count.
- `digital_material_share_by_year.csv`
  - One row per year and digital `materialtype`.
  - Uses sampled digital title-month rows.
  - Material type labels are normalized to uppercase before grouping.
  - Includes material-type checkouts, annual sampled digital checkouts,
    material-type share, and sampled title-month row count.

## Methods

Title popularity was calculated separately for digital and physical samples:

1. Group title-month rows by `usageclass`, `checkoutyear`, and `title`.
2. Sum `checkouts`.
3. Sort by summed checkouts descending and title ascending.
4. Keep the first title in each usage-class/year group.
5. Export both a compact winner summary and all original rows for those winning
   title-year combinations.

Annual digital vs. physical share was calculated from the complete monthly
totals file:

1. Group monthly totals by `checkout_year` and `usageclass`.
2. Sum `total_checkouts`.
3. Sum usage-class totals within each year.
4. Divide annual usage-class checkouts by annual total checkouts.

Physical material-type share was calculated from the sampled physical title
file:

1. Group sampled physical title-month rows by `checkoutyear` and `materialtype`.
2. Sum `checkouts`.
3. Sum material-type totals within each year.
4. Divide material-type checkouts by annual sampled physical checkouts.

Digital material-type share was calculated from the sampled digital title file
using the same method.

## Caveats

The title popularity outputs use balanced title-level sample files. They should
be described as the most popular titles in the sampled records, not the true
most popular titles across the complete library system.

The physical material-type share output also uses the balanced physical sample,
so it describes the distribution within sampled physical checkout rows.

The digital material-type share output also uses the balanced digital sample,
so it describes the distribution within sampled digital checkout rows.

The digital vs. physical share output uses the complete aggregated monthly
totals file, so it is the appropriate output for overall annual checkout share.

## Regeneration

From the repository root, run:

```bash
python scripts/title_popularity_by_year.py
python scripts/digital_physical_share_by_year.py
python scripts/physical_material_share_by_year.py
python scripts/digital_material_share_by_year.py
```

If the virtual environment is not available, use a project-specific Python
environment with `pandas` installed.
