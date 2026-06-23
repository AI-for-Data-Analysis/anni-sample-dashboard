# Build & Deploy a Static Dashboard​

See gitlab pages deployment: https://dashboard-starter-with-examples-8c1afe.pages.oit.duke.edu/ 

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
1. Move index.html, index.css, dashboard_data/ into a public/ folder
![](./imgs/0-move-into-public.png)

2. Create a new repo, push up your changes, visit Settings -> General -> Visibility
![](./imgs/1-go-to-setting.png)

3. Make sure the Gitlab Pages setting is on
![](./imgs/2-enable-pages.png)

4. Go to Deploy -> Pages, create a runner. Copy and paste the following setting
```
image: alpine:latest

pages:
  stage: deploy
  script:
    - echo "Deploying static assets..."
  artifacts:
    paths:
      - public
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'

```
![](./imgs/3-edit-yml.png)

5. Press commit. This step will generate a `.gitlab-ci.yml` file.
![](./imgs/4-commit-yml.png)

6. Check pipeline
![](./imgs/5-created-pipeline.png)

7. View the pipeline and see it runs
![](./imgs/6-see-pipeline.png)

8. When the pipeline succeeds, you'll be able to visit a link
![](./imgs/7-view-pages.png)

9. See the dashboard deployed!
![](./imgs/8-see-page.png)
