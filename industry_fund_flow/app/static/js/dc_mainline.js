(function () {
  const { fmtNum, fmtPct, apiGet, toApiTradeDate, renderHistoryChart, funnelBoardLinks, pickBoard } =
    window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const elMa = document.getElementById("ma-window");
  const elTop = document.getElementById("top-n");
  const elTop20 = document.getElementById("top20-only");
  const elTypes = document.getElementById("content-types");
  const elLevel = document.getElementById("level-filter");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elRankBody = document.getElementById("rank-body");
  const elRankEmpty = document.getElementById("rank-empty");
  const elRankUpdated = document.getElementById("rank-updated");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const elHistoryCard = document.getElementById("history-card");
  const elHistoryTitle = document.getElementById("history-title");
  const elHistoryBody = document.getElementById("history-body");
  const elHistoryChart = document.getElementById("history-chart");
  const elHistoryMetrics = document.getElementById("history-metrics");
  const btnQuery = document.getElementById("btn-query");
  const btnReset = document.getElementById("btn-reset-boards");
  const btnCloseHistory = document.getElementById("btn-close-history");

  const selectedBoards = new Map();
  const boardSearchResults = new Map();
  let boardSearchTimer = null;
  let activeDetailCode = "";

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }
  function clearError() {
    elPageError.classList.add("hidden");
  }

  function apiDate() {
    return elDate.value || "";
  }

  function levelClass(level) {
    if (level === "超级主线") return "level-super";
    if (level === "主线") return "level-main";
    if (level === "轮动热点") return "level-rotate";
    return "level-follow";
  }

  function stageClass(stage) {
    if (stage === "板块爆发") return "stage-tag stage-burst";
    if (stage === "机构化") return "stage-tag stage-inst";
    if (stage === "资金试探") return "stage-tag stage-probe";
    return "stage-tag";
  }

  function scoreTone(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return "";
    if (n >= 85) return "vp-l1";
    if (n >= 70) return "vp-l2";
    if (n >= 60) return "vp-l3";
    if (n >= 40) return "vp-l4";
    return "vp-l5";
  }

  function vpVal(text, tone, badge) {
    const cls = badge ? `vp-val vp-badge ${tone}` : `vp-val ${tone}`;
    return `<span class="${cls}">${text ?? "—"}</span>`;
  }

  function scoreBar(item) {
    const parts = [
      { w: 35, v: item.score_fund, c: "dim-fund", t: "资金" },
      { w: 25, v: item.score_trend, c: "dim-trend", t: "趋势" },
      { w: 15, v: item.score_heat, c: "dim-heat", t: "热度" },
      { w: 15, v: item.score_prosperity, c: "dim-pros", t: "景气" },
      { w: 10, v: item.score_diffusion, c: "dim-diff", t: "扩散" },
    ];
    const spans = parts
      .map((p) => {
        const h = p.v == null ? 0 : Math.max(0, Math.min(100, Number(p.v)));
        return `<span class="${p.c}" style="width:${(p.w * h) / 100}px" title="${p.t}: ${fmtNum(p.v)}"></span>`;
      })
      .join("");
    return `<div class="score-bar" title="资金/趋势/热度/景气/扩散">${spans}</div>`;
  }

  function boardLabel(item) {
    return `[${item.content_type || ""}] ${item.industry_name} (${item.industry_code})`;
  }

  function renderSelectedBoards() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = "";
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
      `/api/v1/mainline/boards/search?trade_date=${encodeURIComponent(apiDate())}` +
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

  function buildRankUrl() {
    const params = new URLSearchParams();
    if (apiDate()) params.set("trade_date", apiDate());
    params.set("ma_window", elMa.value);
    params.set("top", elTop.value);
    params.set("content_types", elTypes.value);
    if (elLevel.value) params.set("level", elLevel.value);
    if (elTop20.checked) params.set("top20_only", "true");
    const codes = Array.from(selectedBoards.keys());
    if (codes.length) params.set("industry_codes", codes.join(","));
    return `/api/v1/mainline/rank?${params}`;
  }

  function renderRank(data) {
    elRankUpdated.textContent = `交易日 ${data.trade_date} · ${data.ma_window} 日均分 · ${data.items.length} 条`;
    if (!data.items.length) {
      elRankBody.innerHTML = "";
      elRankEmpty.classList.remove("hidden");
      return;
    }
    elRankEmpty.classList.add("hidden");
    elRankBody.innerHTML = data.items
      .map((row) => {
        const active = row.industry_code === activeDetailCode ? " vp-row-active" : "";
        return `
      <tr class="${active.trim()}">
        <td>${row.rank ?? "—"}</td>
        <td>${row.content_type || "—"}</td>
        <td>${row.industry_name || "—"}<br><span class="muted">${row.industry_code || ""}</span></td>
        <td>${vpVal(fmtNum(row.main_score), scoreTone(row.main_score), true)}</td>
        <td>${fmtNum(row.total_score)}</td>
        <td class="${levelClass(row.mainline_level)}">${row.mainline_level || "—"}</td>
        <td><span class="${stageClass(row.stage)}">${row.stage || "—"}</span></td>
        <td>${row.fund_cont_days != null ? row.fund_cont_days + "天" : "—"}</td>
        <td>${fmtPct(row.rs_5d)}</td>
        <td>${row.limit_up_cnt ?? "—"}</td>
        <td>${scoreBar(row)}</td>
        <td>${funnelBoardLinks(row.industry_code, row.industry_name, apiDate(), { primary: "vp" })}</td>
        <td><button type="button" class="btn-vp-detail${row.industry_code === activeDetailCode ? " is-active" : ""}" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">数据分析</button></td>
      </tr>`;
      })
      .join("");
    elRankBody.querySelectorAll(".btn-vp-detail").forEach((btn) => {
      btn.addEventListener("click", () => loadHistory(btn.dataset.code, btn.dataset.name));
    });
  }

  function metricItem(label, value) {
    return `<div class="metric-item"><span class="metric-label">${label}</span><strong class="metric-value">${value}</strong></div>`;
  }

  async function loadHistory(code, name) {
    clearError();
    activeDetailCode = code;
    try {
      const td = apiDate();
      if (pickBoard) pickBoard(code, name, td);
      const q = td
        ? `?industry_code=${encodeURIComponent(code)}&trade_date=${td}&days=60`
        : `?industry_code=${encodeURIComponent(code)}&days=60`;
      const data = await apiGet(`/api/v1/mainline/history${q}`);
      elHistoryTitle.textContent = `${name || data.industry_name || code} · 近60日得分`;
      const latest = (data.items || [])[data.items.length - 1] || {};
      if (elHistoryMetrics) {
        elHistoryMetrics.innerHTML =
          `<div class="vp-metric-block"><div class="vp-metric-block-title">最新快照</div>` +
          `<div class="metric-grid metric-grid--vp-row">` +
          metricItem("总分", fmtNum(latest.total_score)) +
          metricItem("MA5", fmtNum(latest.total_score_ma5)) +
          metricItem("等级", latest.mainline_level || "—") +
          metricItem("阶段", latest.stage || "—") +
          metricItem("资金子分", fmtNum(latest.score_fund)) +
          metricItem("趋势子分", fmtNum(latest.score_trend)) +
          `</div></div>`;
      }
      renderHistoryChart(elHistoryChart, data.items, {
        scoreKey: "total_score_ma5",
        fallbackKey: "total_score",
        stroke: "#3b82f6",
      });
      elHistoryBody.innerHTML = data.items
        .slice()
        .reverse()
        .map(
          (r) => `
        <tr>
          <td>${r.trade_date}</td>
          <td>${fmtNum(r.total_score)}</td>
          <td>${fmtNum(r.total_score_ma3)}</td>
          <td>${fmtNum(r.total_score_ma5)}</td>
          <td>${fmtNum(r.total_score_ma10)}</td>
          <td class="${levelClass(r.mainline_level)}">${r.mainline_level || "—"}</td>
          <td>${r.stage || "—"}</td>
        </tr>`
        )
        .join("");
      elHistoryCard.classList.remove("hidden");
      elHistoryCard.scrollIntoView({ behavior: "smooth", block: "start" });
      queryRank(false);
    } catch (err) {
      showError(err.message);
    }
  }

  async function loadTradeDates() {
    const data = await apiGet("/api/v1/mainline/trade-dates?limit=90");
    const dates = data.dates || [];
    elDate.innerHTML = "";
    dates.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = toApiTradeDate(d) || String(d).replace(/-/g, "");
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) {
      const latest = toApiTradeDate(data.latest) || String(data.latest).replace(/-/g, "");
      elDate.value = latest;
    }
  }

  async function queryRank(scrollTop) {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const data = await apiGet(buildRankUrl());
      renderRank(data);
      elFilterHint.textContent = selectedBoards.size
        ? `已筛选 ${selectedBoards.size} 个板块`
        : "";
      if (scrollTop) window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  elBoardSearch.addEventListener("input", () => {
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(() => {
      searchBoards(elBoardSearch.value).catch((e) => showError(e.message));
    }, 220);
  });
  elBoardDropdown.addEventListener("click", (e) => {
    const btn = e.target.closest(".board-option");
    if (!btn) return;
    const item = boardSearchResults.get(btn.dataset.code);
    if (item) addBoard(item);
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#board-picker")) hideDropdown();
  });

  btnQuery.addEventListener("click", () => queryRank(false));
  btnReset.addEventListener("click", () => {
    selectedBoards.clear();
    renderSelectedBoards();
    queryRank(false);
  });
  btnCloseHistory.addEventListener("click", () => {
    elHistoryCard.classList.add("hidden");
    activeDetailCode = "";
    queryRank(false);
  });

  (async function init() {
    try {
      await loadTradeDates();
      await queryRank(false);
    } catch (err) {
      showError(err.message);
    }
  })();
})();
