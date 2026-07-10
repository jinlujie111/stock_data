(function () {
  const elDate = document.getElementById("trade-date");
  const elWindow = document.getElementById("window");
  const elTypes = document.getElementById("content-types");
  const elError = document.getElementById("page-error");
  const elMarketChart = document.getElementById("market-chart");
  const elMarketLegend = document.getElementById("market-legend");
  const elIndustryChart = document.getElementById("industry-chart");
  const elIndustryLegend = document.getElementById("industry-legend");
  const elRankBody = document.getElementById("rank-body");
  const elRankEmpty = document.getElementById("rank-empty");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const btnQuery = document.getElementById("btn-query");
  const btnReset = document.getElementById("btn-reset-boards");

  const SERIES_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#ef4444", "#14b8a6"];
  const selectedBoards = new Map();
  const boardSearchResults = new Map();
  let defaultBoardNames = [];
  let boardSearchTimer = null;
  const elBoardPicker = document.getElementById("board-picker");

  function fmt(v, digits) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(digits == null ? 2 : digits);
  }

  function pct(v) {
    if (v === null || v === undefined || v === "") return "—";
    return fmt(v, 2) + "%";
  }

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }

  function clearError() {
    elError.classList.add("hidden");
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function currentCodes() {
    return Array.from(selectedBoards.keys());
  }

  function boardLabel(item) {
    return `[${item.content_type}] ${item.industry_name} (${item.industry_code})`;
  }

  function renderSelectedBoards() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择板块（展示默认常看板块）</span>';
      return;
    }
    elBoardSelected.innerHTML = "";
    selectedBoards.forEach((item, code) => {
      const wrap = document.createElement("span");
      wrap.className = "board-tag";
      wrap.innerHTML = `${boardLabel(item)}<button type="button" data-code="${code}">×</button>`;
      elBoardSelected.appendChild(wrap);
    });
    elBoardSelected.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedBoards.delete(btn.dataset.code);
        renderSelectedBoards();
      });
    });
  }

  function setDefaultBoards(names) {
    defaultBoardNames = names || [];
    return apiGet(
      `/api/v1/volatility/boards/history?trade_date=${encodeURIComponent(elDate.value)}` +
        `&window=${encodeURIComponent(elWindow.value)}` +
        `&content_types=${encodeURIComponent(elTypes.value)}` +
        `&board_keywords=${encodeURIComponent(defaultBoardNames.join(","))}` +
        `&days=365`
    ).then((data) => {
      selectedBoards.clear();
      (data.boards || []).forEach((b) => selectedBoards.set(b.industry_code, b));
      renderSelectedBoards();
      return data;
    });
  }

  async function loadDates() {
    const data = await apiGet("/api/v1/volatility/trade-dates?limit=365");
    elDate.innerHTML = "";
    const dates = data.dates || [];
    if (!dates.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "暂无数据";
      opt.disabled = true;
      elDate.appendChild(opt);
      throw new Error("暂无波动率数据，请先执行波动率批处理");
    }
    dates.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) elDate.value = data.latest;
  }

  function lineChartSvg(seriesList, dates, title) {
    const width = 900;
    const height = 320;
    const pad = { left: 52, right: 18, top: 18, bottom: 34 };
    const values = [];
    seriesList.forEach((s) =>
      (s.points || []).forEach((p) => {
        const v = Number(p.annual_vol);
        if (!Number.isNaN(v)) values.push(v);
      })
    );
    if (!values.length || dates.length < 2) {
      return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}">
        <text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#94a3b8">暂无数据</text>
      </svg>`;
    }
    let minV = Math.min.apply(null, values);
    let maxV = Math.max.apply(null, values);
    if (minV === maxV) {
      minV = Math.max(0, minV - 5);
      maxV = maxV + 5;
    }
    const xSpan = width - pad.left - pad.right;
    const ySpan = height - pad.top - pad.bottom;
    const x = (idx) => pad.left + (xSpan * idx) / Math.max(1, dates.length - 1);
    const y = (val) => pad.top + ((maxV - val) / (maxV - minV)) * ySpan;

    const grid = [];
    for (let i = 0; i <= 4; i += 1) {
      const gv = minV + ((maxV - minV) * i) / 4;
      const gy = y(gv);
      grid.push(`<line x1="${pad.left}" y1="${gy}" x2="${width - pad.right}" y2="${gy}" stroke="rgba(148,163,184,.2)" />`);
      grid.push(`<text x="${pad.left - 8}" y="${gy + 4}" text-anchor="end" fill="#94a3b8" font-size="11">${fmt(gv, 1)}%</text>`);
    }
    const xTicks = [0, Math.floor((dates.length - 1) / 2), dates.length - 1]
      .filter((v, i, arr) => arr.indexOf(v) === i);
    xTicks.forEach((idx) => {
      grid.push(
        `<text x="${x(idx)}" y="${height - 8}" text-anchor="middle" fill="#94a3b8" font-size="11">${dates[idx]}</text>`
      );
    });

    const lines = seriesList.map((s, idx) => {
      const d = [];
      (s.points || []).forEach((p, pointIdx) => {
        const v = Number(p.annual_vol);
        if (Number.isNaN(v)) return;
        d.push(`${d.length ? "L" : "M"} ${x(pointIdx)} ${y(v)}`);
      });
      if (!d.length) return "";
      const last = [...(s.points || [])].reverse().find((p) => p.annual_vol !== null && p.annual_vol !== undefined);
      const lastIdx = last ? (s.points || []).findIndex((p) => p.trade_date === last.trade_date) : -1;
      const circle =
        last && lastIdx >= 0
          ? `<circle cx="${x(lastIdx)}" cy="${y(Number(last.annual_vol))}" r="3.5" fill="${SERIES_COLORS[idx % SERIES_COLORS.length]}" />`
          : "";
      return `<path d="${d.join(" ")}" fill="none" stroke="${SERIES_COLORS[idx % SERIES_COLORS.length]}" stroke-width="2.25" />${circle}`;
    });
    return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}">
      <rect x="0" y="0" width="${width}" height="${height}" fill="transparent" />
      ${grid.join("")}
      ${lines.join("")}
    </svg>`;
  }

  function renderLegend(el, seriesList) {
    el.innerHTML = (seriesList || [])
      .map(
        (s, idx) =>
          `<span class="legend-item"><span class="legend-dot" style="background:${SERIES_COLORS[idx % SERIES_COLORS.length]}"></span>${s.index_name || s.industry_name || s.index_code || s.industry_code}</span>`
      )
      .join("");
  }

  async function loadMarketChart() {
    const data = await apiGet(
      `/api/v1/volatility/market/history?trade_date=${encodeURIComponent(elDate.value)}&window=${encodeURIComponent(elWindow.value)}&days=365`
    );
    elMarketChart.innerHTML = lineChartSvg(data.series || [], data.dates || [], "大盘年化波动率");
    renderLegend(elMarketLegend, data.series || []);
  }

  function hideDropdown() {
    elBoardDropdown.classList.add("hidden");
  }

  function addBoard(item) {
    if (!item || !item.industry_code) return;
    selectedBoards.set(item.industry_code, item);
    renderSelectedBoards();
    elBoardSearch.value = "";
    hideDropdown();
  }

  async function searchBoards(keyword) {
    if (!keyword || !keyword.trim()) {
      elBoardDropdown.innerHTML = "";
      hideDropdown();
      return;
    }
    const data = await apiGet(
      `/api/v1/volatility/boards/search?trade_date=${encodeURIComponent(elDate.value)}` +
        `&content_types=${encodeURIComponent(elTypes.value)}` +
        `&keyword=${encodeURIComponent(keyword.trim())}&limit=20`
    );
    const items = data.items || [];
    boardSearchResults.clear();
    if (!items.length) {
      elBoardDropdown.innerHTML = "";
      hideDropdown();
      return;
    }
    items.forEach((item) => boardSearchResults.set(item.industry_code, item));
    elBoardDropdown.innerHTML = items
      .map(
        (item) =>
          `<button type="button" class="board-option" data-code="${item.industry_code}">` +
          `${boardLabel(item)}</button>`
      )
      .join("");
    elBoardDropdown.classList.remove("hidden");
  }

  async function loadIndustryChart() {
    const codes = currentCodes();
    const codeParam = codes.join(",");
    const data = await apiGet(
      `/api/v1/volatility/boards/history?trade_date=${encodeURIComponent(elDate.value)}` +
        `&window=${encodeURIComponent(elWindow.value)}` +
        `&content_types=${encodeURIComponent(elTypes.value)}` +
        `&industry_codes=${encodeURIComponent(codeParam)}&days=365`
    );
    if (!codes.length && data.default_board_names) {
      defaultBoardNames = data.default_board_names;
    }
    elIndustryChart.innerHTML = lineChartSvg(data.series || [], data.dates || [], "板块年化波动率");
    renderLegend(elIndustryLegend, data.series || []);
  }

  async function loadRank() {
    const data = await apiGet(
      `/api/v1/volatility/boards/rank?trade_date=${encodeURIComponent(elDate.value)}` +
        `&window=${encodeURIComponent(elWindow.value)}` +
        `&content_types=${encodeURIComponent(elTypes.value)}&top=50`
    );
    elRankBody.innerHTML = "";
    const items = data.items || [];
    if (!items.length) {
      elRankEmpty.classList.remove("hidden");
      return;
    }
    elRankEmpty.classList.add("hidden");
    items.forEach((row, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${idx + 1}</td>` +
        `<td>${row.industry_name || row.industry_code}</td>` +
        `<td>${row.content_type || "—"}</td>` +
        `<td>${fmt(row.close, 2)}</td>` +
        `<td>${pct(row.pct_change)}</td>` +
        `<td>${pct(row.annual_vol_20d)}</td>` +
        `<td>${pct(row.annual_vol_60d)}</td>`;
      elRankBody.appendChild(tr);
    });
  }

  async function refresh() {
    clearError();
    await loadMarketChart();
    await loadIndustryChart();
    await loadRank();
  }

  elBoardSearch.addEventListener("input", () => {
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(() => {
      searchBoards(elBoardSearch.value).catch((e) => showError(e.message || String(e)));
    }, 180);
  });
  elBoardSearch.addEventListener("focus", () => {
    if (elBoardSearch.value.trim()) {
      searchBoards(elBoardSearch.value).catch((e) => showError(e.message || String(e)));
    }
  });
  elBoardDropdown.addEventListener("mousedown", (e) => {
    e.preventDefault();
  });
  elBoardDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    const item = boardSearchResults.get(btn.dataset.code);
    if (item) addBoard(item);
  });
  document.addEventListener("click", (e) => {
    if (!elBoardPicker.contains(e.target)) hideDropdown();
  });

  btnReset.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown();
    renderSelectedBoards();
    refresh().catch((e) => showError(e.message || String(e)));
  });
  btnQuery.addEventListener("click", () => {
    refresh().catch((e) => showError(e.message || String(e)));
  });

  loadDates()
    .then(() => setDefaultBoards(["半导体", "通信", "创新药", "机器人"]))
    .then((data) => {
      defaultBoardNames = data.default_board_names || ["半导体", "通信", "创新药", "机器人"];
      return refresh();
    })
    .catch((e) => showError(e.message || String(e)));
})();
