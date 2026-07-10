(function () {
  const { fmtNum, fmtPct, apiGet, toApiTradeDate, initTradeDateCalendar, renderHistoryChart, klineLink } = window.DcBoard;
  const elDate = document.getElementById("trade-date");
  const elMa = document.getElementById("ma-window");
  const elTop = document.getElementById("top-n");
  const elTop20 = document.getElementById("top20-only");
  const typeChips = document.getElementById("content-type-chips");
  const levelChips = document.getElementById("level-chips");
  const elRankBody = document.getElementById("rank-body");
  const elRankEmpty = document.getElementById("rank-empty");
  const elRankUpdated = document.getElementById("rank-updated");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const elHistoryCard = document.getElementById("history-card");
  const elHistoryTitle = document.getElementById("history-title");
  const elHistoryBody = document.getElementById("history-body");
  const elHistoryChart = document.getElementById("history-chart");
  const btnQuery = document.getElementById("btn-query");
  const btnCloseHistory = document.getElementById("btn-close-history");

  let selectedTypes = ["行业", "概念"];
  let selectedLevels = [];

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
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

  function scoreBar(item) {
    const parts = [
      { w: 35, v: item.score_fund, c: "dim-fund" },
      { w: 25, v: item.score_trend, c: "dim-trend" },
      { w: 15, v: item.score_heat, c: "dim-heat" },
      { w: 15, v: item.score_prosperity, c: "dim-pros" },
      { w: 10, v: item.score_diffusion, c: "dim-diff" },
    ];
    const spans = parts
      .map((p) => {
        const h = p.v == null ? 0 : Math.max(0, Math.min(100, Number(p.v)));
        return `<span class="${p.c}" style="width:${(p.w * h) / 100}px" title="${p.c}: ${fmtNum(p.v)}"></span>`;
      })
      .join("");
    return `<div class="score-bar" title="资金/趋势/热度/景气/扩散">${spans}</div>`;
  }

  function bindChips(group, multi, onChange) {
    if (!group) return;
    group.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const val = btn.dataset.value;
      if (multi) {
        if (!val) {
          group.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
          btn.classList.add("active");
          onChange([]);
          return;
        }
        const allBtn = group.querySelector('.chip[data-value=""]');
        if (allBtn) allBtn.classList.remove("active");
        btn.classList.toggle("active");
        const active = Array.from(group.querySelectorAll(".chip.active"))
          .map((c) => c.dataset.value)
          .filter(Boolean);
        if (!active.length && allBtn) allBtn.classList.add("active");
        onChange(active);
      } else {
        group.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        onChange(val ? [val] : []);
      }
    });
  }

  bindChips(levelChips, true, (vals) => {
    selectedLevels = vals;
  });

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      btn.classList.toggle("active");
      selectedTypes = Array.from(typeChips.querySelectorAll(".chip.active"))
        .map((c) => c.dataset.value)
        .filter(Boolean);
      if (!selectedTypes.length) {
        btn.classList.add("active");
        selectedTypes = [btn.dataset.value];
      }
    });
  }

  function buildRankUrl() {
    const params = new URLSearchParams();
    if (elDate.value) params.set("trade_date", toApiTradeDate(elDate.value));
    params.set("ma_window", elMa.value);
    params.set("top", elTop.value);
    if (selectedTypes.length) params.set("content_types", selectedTypes.join(","));
    if (selectedLevels.length) params.set("level", selectedLevels.join(","));
    if (elTop20.checked) params.set("top20_only", "true");
    return `/api/v1/mainline/rank?${params}`;
  }

  function renderRank(data) {
    elRankUpdated.textContent = `交易日 ${data.trade_date} · ${data.ma_window} 日均分排序 · ${data.items.length} 条`;
    if (!data.items.length) {
      elRankBody.innerHTML = "";
      elRankEmpty.classList.remove("hidden");
      return;
    }
    elRankEmpty.classList.add("hidden");
    elRankBody.innerHTML = data.items
      .map(
        (row) => `
      <tr>
        <td>${row.rank ?? "—"}</td>
        <td>${row.content_type || "—"}</td>
        <td>${row.industry_name || "—"}<br><span class="muted">${row.industry_code || ""}</span></td>
        <td><strong>${fmtNum(row.main_score)}</strong></td>
        <td>${fmtNum(row.total_score)}</td>
        <td class="${levelClass(row.mainline_level)}">${row.mainline_level || "—"}</td>
        <td><span class="${stageClass(row.stage)}">${row.stage || "—"}</span></td>
        <td>${row.fund_cont_days != null ? row.fund_cont_days + "天" : "—"}</td>
        <td>${fmtPct(row.rs_5d)}</td>
        <td>${row.limit_up_cnt ?? "—"}</td>
        <td>${scoreBar(row)}</td>
        <td>${klineLink("board", row.industry_code, elDate.value)}</td>
        <td><button type="button" class="btn btn-ghost btn-sm btn-history" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">历史</button></td>
      </tr>`
      )
      .join("");
    elRankBody.querySelectorAll(".btn-history").forEach((btn) => {
      btn.addEventListener("click", () => loadHistory(btn.dataset.code, btn.dataset.name));
    });
  }

  function renderHistoryChartLocal(items) {
    renderHistoryChart(elHistoryChart, items, {
      scoreKey: "total_score_ma5",
      fallbackKey: "total_score",
      stroke: "#3b82f6",
    });
  }

  async function loadHistory(code, name) {
    clearError();
    try {
      const td = elDate.value ? toApiTradeDate(elDate.value) : "";
      const q = td ? `?industry_code=${encodeURIComponent(code)}&trade_date=${td}&days=60` : `?industry_code=${encodeURIComponent(code)}&days=60`;
      const data = await apiGet(`/api/v1/mainline/history${q}`);
      elHistoryTitle.textContent = `${name || data.industry_name || code} · 近60日得分`;
      renderHistoryChartLocal(data.items);
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
    } catch (err) {
      showError(err.message);
    }
  }

  async function loadTradeDates() {
    await initTradeDateCalendar(elDate, "/api/v1/mainline/trade-dates?limit=90");
  }

  async function queryRank() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const data = await apiGet(buildRankUrl());
      renderRank(data);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  btnQuery.addEventListener("click", queryRank);
  btnCloseHistory.addEventListener("click", () => elHistoryCard.classList.add("hidden"));

  (async function init() {
    try {
      await loadTradeDates();
      await queryRank();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
