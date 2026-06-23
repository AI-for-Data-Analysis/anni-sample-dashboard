const csvPath = "dashboard_data/digital_material_type_shares_by_year.csv";
const titlesCsvPath = "dashboard_data/digital_top_sampled_titles_by_year.csv";
const physicalTitlesCsvPath = "dashboard_data/physical_top_sampled_titles_by_year.csv";
const chartEl = document.getElementById("material-chart");
const findingEl = document.getElementById("finding-text");
const gridEl = document.getElementById("data-grid");
const titlesChartEl = document.getElementById("titles-chart");
const titlesFindingEl = document.getElementById("titles-finding");
const physicalTitlesChartEl = document.getElementById("physical-titles-chart");
const physicalTitlesFindingEl = document.getElementById("physical-titles-finding");
let raceTimer;

const palette = {
  EBOOK: "#28666e",
  AUDIOBOOK: "#d1663f",
  MAGAZINE: "#6f7f52",
  SONG: "#7d5ba6",
  MUSIC: "#e0a458",
  VIDEO: "#4c6f9f",
  MOVIE: "#b64f6f",
  TELEVISION: "#577590",
  COMIC: "#2f9c95",
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const nextChar = text[index + 1];

    if (char === "\"" && inQuotes && nextChar === "\"") {
      value += "\"";
      index += 1;
    } else if (char === "\"") {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(value);
      value = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && nextChar === "\n") {
        index += 1;
      }
      row.push(value);
      if (row.some((cell) => cell !== "")) {
        rows.push(row);
      }
      row = [];
      value = "";
    } else {
      value += char;
    }
  }

  row.push(value);
  if (row.some((cell) => cell !== "")) {
    rows.push(row);
  }

  const [headers, ...dataRows] = rows;
  return dataRows.map((dataRow) =>
    Object.fromEntries(headers.map((header, index) => [header, dataRow[index] || ""])),
  );
}

function aggregateShares(rows) {
  const byYear = new Map();

  rows.forEach((row) => {
    const year = Number(row.checkoutyear);
    const material = row.materialtype.trim().toUpperCase();
    const share = Number(row.sampled_material_share);

    if (!byYear.has(year)) {
      byYear.set(year, new Map());
    }

    const materialShares = byYear.get(year);
    materialShares.set(material, (materialShares.get(material) || 0) + share);
  });

  return byYear;
}

function percent(value, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function buildFinding(byYear) {
  const years = [...byYear.keys()].sort((a, b) => a - b);
  const firstEbookLeadYear = years.find((year) => {
    const shares = byYear.get(year);
    return (shares.get("EBOOK") || 0) > (shares.get("AUDIOBOOK") || 0);
  });
  const ebookPeakYear = years.reduce((best, year) => {
    const share = byYear.get(year).get("EBOOK") || 0;
    return share > best.share ? { year, share } : best;
  }, { year: null, share: -Infinity });
  const latestYear = years[years.length - 1];
  const latest = byYear.get(latestYear);
  const latestGap = (latest.get("EBOOK") || 0) - (latest.get("AUDIOBOOK") || 0);

  return `Ebooks first passed audiobooks in ${firstEbookLeadYear}, peaked at ${percent(
    ebookPeakYear.share,
  )} of sampled digital checkouts in ${ebookPeakYear.year}, and by ${latestYear} led audiobooks by only ${percent(
    latestGap,
  )}.`;
}

function buildChart(byYear) {
  const years = [...byYear.keys()].sort((a, b) => a - b);
  const materialTotals = new Map();

  byYear.forEach((shares) => {
    shares.forEach((share, material) => {
      materialTotals.set(material, (materialTotals.get(material) || 0) + share);
    });
  });

  const materials = [...materialTotals.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([material]) => material);

  const labelFor = (material) => material.charAt(0) + material.slice(1).toLowerCase();
  const dataForYear = (year) =>
    materials.map((material) => ({
      name: labelFor(material),
      value: Number(((byYear.get(year).get(material) || 0) * 100).toFixed(3)),
      itemStyle: { color: palette[material] || "#8a8f98" },
    }));

  const chart = echarts.init(chartEl, null, { renderer: "canvas" });
  const makeYearGraphic = (year) => ({
    type: "text",
    right: 24,
    bottom: 82,
    style: {
      text: String(year),
      fill: "rgba(23, 32, 51, 0.18)",
      font: "700 76px Inter, sans-serif",
    },
    z: 10,
  });

  chart.setOption({
    color: materials.map((material) => palette[material] || "#8a8f98"),
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value) => `${Number(value).toFixed(1)}%`,
    },
    grid: {
      top: 18,
      right: 16,
      bottom: 36,
      left: 108,
      containLabel: true,
    },
    xAxis: {
      type: "value",
      name: "Share of checkouts",
      min: 0,
      max: 100,
      axisLabel: {
        color: "#657087",
        formatter: "{value}%",
      },
      axisLine: { lineStyle: { color: "rgba(23, 32, 51, 0.22)" } },
      nameTextStyle: { color: "#657087" },
      splitLine: { lineStyle: { color: "rgba(23, 32, 51, 0.1)" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      max: Math.min(materials.length - 1, 7),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: "#657087",
        fontWeight: 700,
      },
      data: materials.map(labelFor),
    },
    series: [
      {
        type: "bar",
        realtimeSort: true,
        data: dataForYear(years[0]),
        barWidth: 22,
        label: {
          show: true,
          position: "right",
          color: "#172033",
          fontWeight: 800,
          formatter: ({ value }) => `${Number(value).toFixed(1)}%`,
        },
      },
    ],
    graphic: makeYearGraphic(years[0]),
    animationDuration: 900,
    animationDurationUpdate: 900,
    animationEasing: "cubicOut",
    animationEasingUpdate: "cubicOut",
  });

  let yearIndex = 0;
  clearInterval(raceTimer);
  raceTimer = setInterval(() => {
    yearIndex = (yearIndex + 1) % years.length;
    const year = years[yearIndex];

    chart.setOption({
      series: [{ data: dataForYear(year) }],
      graphic: makeYearGraphic(year),
    });
  }, 1300);

  window.addEventListener("resize", () => chart.resize());
}

function buildDataGrid(byYear) {
  const rowData = [...byYear.entries()]
    .map(([year, shares]) => {
      const [materialType, share] = [...shares.entries()].sort((a, b) => b[1] - a[1])[0];
      const runnerUp = [...shares.entries()].sort((a, b) => b[1] - a[1])[1];

      return {
        year,
        materialType,
        share,
        runnerUpType: runnerUp?.[0] || "",
        lead: runnerUp ? share - runnerUp[1] : share,
      };
    })
    .sort((a, b) => b.year - a.year);

  const percentFormatter = ({ value }) => percent(Number(value));

  const gridOptions = {
    rowData,
    columnDefs: [
      { field: "year", headerName: "Year", width: 110, sort: "desc", filter: "agNumberColumnFilter" },
      { field: "materialType", headerName: "Top material type", minWidth: 190, filter: "agTextColumnFilter" },
      {
        field: "share",
        headerName: "Top share",
        width: 130,
        filter: "agNumberColumnFilter",
        valueFormatter: percentFormatter,
        cellClass: "share-cell",
      },
      {
        field: "runnerUpType",
        headerName: "Runner-up",
        minWidth: 160,
        filter: "agTextColumnFilter",
      },
      {
        field: "lead",
        headerName: "Lead over runner-up",
        minWidth: 190,
        filter: "agNumberColumnFilter",
        valueFormatter: percentFormatter,
      },
    ],
    defaultColDef: {
      flex: 1,
      minWidth: 110,
      sortable: true,
      filter: true,
      resizable: true,
    },
    pagination: true,
    paginationPageSize: 20,
    paginationPageSizeSelector: [10, 20],
    animateRows: true,
  };

  agGrid.createGrid(gridEl, gridOptions);
}

function buildTitlesVisualization(rows) {
  const topRows = rows
    .filter((row) => Number(row.rank_in_year) === 1)
    .map((row) => ({
      year: Number(row.checkoutyear),
      title: row.title,
      creator: row.creator,
      materialType: row.materialtype,
      checkouts: Number(row.total_sampled_checkouts),
    }))
    .sort((a, b) => a.year - b.year);

  const peak = topRows.reduce(
    (best, row) => (row.checkouts > best.checkouts ? row : best),
    topRows[0],
  );
  const biggestJump = topRows.slice(1).reduce(
    (best, row, index) => {
      const previous = topRows[index];
      const jump = row.checkouts - previous.checkouts;
      return jump > best.jump ? { row, previous, jump } : best;
    },
    { row: topRows[1], previous: topRows[0], jump: topRows[1].checkouts - topRows[0].checkouts },
  );

  const chart = echarts.init(titlesChartEl, null, { renderer: "canvas" });
  chart.setOption({
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: (params) => {
        const point = params[0];
        const row = topRows[point.dataIndex];
        return `<strong>${row.year}</strong><br>${row.title}<br>${row.creator || "Unknown creator"}<br>${row.checkouts.toLocaleString()} sampled checkouts`;
      },
    },
    grid: {
      top: 26,
      right: 24,
      bottom: 56,
      left: 72,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: topRows.map((row) => row.year),
      axisLabel: { color: "#657087" },
      axisLine: { lineStyle: { color: "rgba(23, 32, 51, 0.22)" } },
    },
    yAxis: {
      type: "value",
      name: "Sampled checkouts",
      axisLabel: {
        color: "#657087",
        formatter: (value) => Number(value).toLocaleString(),
      },
      nameTextStyle: { color: "#657087" },
      splitLine: { lineStyle: { color: "rgba(23, 32, 51, 0.1)" } },
    },
    series: [
      {
        name: "Top title checkouts",
        type: "line",
        smooth: true,
        symbolSize: 9,
        lineStyle: { color: "#28666e", width: 4 },
        itemStyle: { color: "#d1663f" },
        areaStyle: { color: "rgba(40, 102, 110, 0.13)" },
        data: topRows.map((row) => row.checkouts),
      },
    ],
  });

  titlesFindingEl.innerHTML = `The top-title count surged most from ${biggestJump.previous.year} to ${biggestJump.row.year}, rising by <strong>${biggestJump.jump.toLocaleString()}</strong> sampled checkouts; the overall peak was <strong>${peak.title}</strong> in ${peak.year} with <strong>${peak.checkouts.toLocaleString()}</strong> sampled checkouts.`;
  window.addEventListener("resize", () => chart.resize());
}

function buildPhysicalTitlesVisualization(rows) {
  const labelFor = (materialType) =>
    materialType.charAt(0) + materialType.slice(1).toLowerCase();
  const topRows = rows
    .filter((row) => Number(row.rank_in_year) >= 1 && Number(row.rank_in_year) <= 10)
    .map((row) => ({
      year: Number(row.checkoutyear),
      rank: Number(row.rank_in_year),
      title: row.title,
      materialType: row.materialtype.split("|")[0].trim().toUpperCase(),
      checkouts: Number(row.total_sampled_checkouts),
    }))
    .sort((a, b) => a.year - b.year || a.rank - b.rank);

  const years = [...new Set(topRows.map((row) => row.year))].sort((a, b) => a - b);
  const materialTypes = [...new Set(topRows.map((row) => row.materialType))].sort();
  const yearMaterialTotals = new Map();

  topRows.forEach((row) => {
    if (!yearMaterialTotals.has(row.year)) {
      yearMaterialTotals.set(row.year, new Map());
    }
    const totals = yearMaterialTotals.get(row.year);
    totals.set(row.materialType, (totals.get(row.materialType) || 0) + row.checkouts);
  });

  const peakYear = years.reduce(
    (best, year) => {
      const total = [...yearMaterialTotals.get(year).values()].reduce((sum, value) => sum + value, 0);
      return total > best.total ? { year, total } : best;
    },
    { year: null, total: -Infinity },
  );
  const dominantYears = years.reduce((counts, year) => {
    const [materialType] = [...yearMaterialTotals.get(year).entries()].sort((a, b) => b[1] - a[1])[0];
    counts.set(materialType, (counts.get(materialType) || 0) + 1);
    return counts;
  }, new Map());
  const [mostFrequentMaterial, dominantCount] = [...dominantYears.entries()].sort((a, b) => b[1] - a[1])[0];

  const chart = echarts.init(physicalTitlesChartEl, null, { renderer: "canvas" });
  chart.setOption({
    color: ["#28666e", "#d1663f", "#6f7f52", "#7d5ba6", "#4c6f9f", "#e0a458"],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value) => Number(value).toLocaleString(),
    },
    legend: {
      top: 0,
      textStyle: { color: "#657087", fontWeight: 700 },
    },
    grid: {
      top: 54,
      right: 24,
      bottom: 58,
      left: 72,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: years,
      axisLabel: { color: "#657087" },
      axisLine: { lineStyle: { color: "rgba(23, 32, 51, 0.22)" } },
    },
    yAxis: {
      type: "value",
      name: "Top-10 sampled checkouts",
      axisLabel: {
        color: "#657087",
        formatter: (value) => Number(value).toLocaleString(),
      },
      nameTextStyle: { color: "#657087" },
      splitLine: { lineStyle: { color: "rgba(23, 32, 51, 0.1)" } },
    },
    series: materialTypes.map((materialType) => ({
      name: labelFor(materialType),
      type: "bar",
      stack: "physical-top-titles",
      emphasis: { focus: "series" },
      data: years.map((year) => yearMaterialTotals.get(year).get(materialType) || 0),
    })),
  });

  physicalTitlesFindingEl.innerHTML = `Among the annual physical top-10 titles, <strong>${labelFor(mostFrequentMaterial)}</strong> contributed the largest checkout total in <strong>${dominantCount}</strong> of ${years.length} years, while the combined top-10 peak came in <strong>${peakYear.year}</strong> with <strong>${peakYear.total.toLocaleString()}</strong> sampled checkouts.`;
  window.addEventListener("resize", () => chart.resize());
}

async function init() {
  try {
    const [response, titlesResponse, physicalTitlesResponse] = await Promise.all([
      fetch(csvPath),
      fetch(titlesCsvPath),
      fetch(physicalTitlesCsvPath),
    ]);
    if (!response.ok) {
      throw new Error(`Could not load ${csvPath}`);
    }
    if (!titlesResponse.ok) {
      throw new Error(`Could not load ${titlesCsvPath}`);
    }
    if (!physicalTitlesResponse.ok) {
      throw new Error(`Could not load ${physicalTitlesCsvPath}`);
    }

    const rows = parseCsv(await response.text());
    const titleRows = parseCsv(await titlesResponse.text());
    const physicalTitleRows = parseCsv(await physicalTitlesResponse.text());
    const byYear = aggregateShares(rows);

    findingEl.innerHTML = buildFinding(byYear).replace(
      /(\d+\.\d%)/g,
      "<strong>$1</strong>",
    );
    buildChart(byYear);
    buildDataGrid(byYear);
    buildTitlesVisualization(titleRows);
    buildPhysicalTitlesVisualization(physicalTitleRows);
  } catch (error) {
    chartEl.innerHTML = "<p class=\"error\">The chart could not load.</p>";
    titlesChartEl.innerHTML = "<p class=\"error\">The titles chart could not load.</p>";
    physicalTitlesChartEl.innerHTML = "<p class=\"error\">The physical titles chart could not load.</p>";
    findingEl.textContent = error.message;
    titlesFindingEl.textContent = error.message;
    physicalTitlesFindingEl.textContent = error.message;
  }
}

window.addEventListener("DOMContentLoaded", init);
