# Build & Deploy a Static Dashboard​

## Create a dashboard
```
Create a static dashboard website using plain HTML, CSS, and JavaScript that loads data directly at runtime from dashboard_data/digital_material_type_shares_by_year.csv, do not embed it; use Plotly.js to render exactly one interactive chart and one clearly written interesting finding derived from the CSV data, make the page responsive and visually polished.
```

### Try a new chart
Prompt:
```
Change to a stacked bar chart in Plotly.js
```

### Try a new library
- Plotly.js [(link)​](https://plotly.com/javascript/)
- Apache Echarts [(link)​](https://echarts.apache.org/examples/en/index.html#chart-type-bar)
- Map: Leaflet [(link)](https://leafletjs.com/examples.html)
Prompt:
```
Change to Apache Echarts
```

### Try the bar race chart
Prompt:
```
Change to a bar race chart
```

## Create a Table
```
Create a table below the chart showing the most popular material type of each year using AG Grid Community 32
```

## Create a new data viz
```
Create a new data visualization that loads data directly at runtime from dashboard_data/digital_top_sampled_titles_by_year.csv, do not embed it; render exactly one interactive chart and one clearly written interesting finding derived from the CSV data. Adds it below the exisitng ones.
```

## Create a sub-agent
```
Create a repo-local subagent definition for CSV data visualization work, saved under agents/. The subagent should accept a CSV path and output location, inspect the CSV schema first, build a static responsive HTML/CSS/JS visualization, load the CSV directly at runtime with fetch() and never embed data or derived full datasets, use a browser visualization library such as Plotly.js, Apache ECharts, AG Grid Community 32 for tables, or Leaflet for map-style views, render exactly one interactive chart or requested table, compute exactly one clear finding from the runtime-loaded CSV, keep edits scoped to the requested output files, and verify syntax plus confirm the CSV is referenced rather than embedded.
```

## Use Data Viz Accessibility Skill
```
use $data-viz-accessibility to audit the dashboard
```

## Deploy on Gitlab Pages
