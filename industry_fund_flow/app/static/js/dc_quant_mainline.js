(function () {
  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar, renderHistoryChart, klineLink } = window.DcBoard;
  const elDate = document.getElementById("trade-date");
  const elMa = document.getElementById("ma-window");
  const elSignalStatus = document.getElementById("signal-status");
  const typeChips = document.getElementById("content-type-chips");
  const elIndustrySection = document.getElementById("top-industry-section");
  const elConceptSection = document.getElementById("top-concept-section");
  const elIndustryBody = document.getElementById("top-industry-body");
  const elConceptBody = document.getElementById("top-concept-body");
  const elIndustryEmpty = document.getElementById("top-industry-empty");
  const elConceptEmpty = document.getElementById("top-concept-empty");
  const elIndustryUpdated = document.getElementById("top-industry-updated");
  const elConceptUpdated = document.getElementById("top-concept-updated");
  const elSignalBody = document.getElementById("signal-body");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const elHistoryCard = document.getElementById("history-card");
  const elHistoryTitle = document.getElementById("history-title");
  const elHistoryBody = document.getElementById("history-body");
  const elHistoryChart = document.getElementById("history-chart");
  const btnQuery = document.getElementById("btn-query");
  const btnCloseHistory = document.getElementById("btn-close-history");

  let selectedType = "行业";

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function signalClass(status) {
    if (status === "启动") return "signal-start";
    if (status === "退潮") return "signal-exit";
    return "signal-watch";
  }

  function ftelpBar(item) {
    const parts = [
      { w: 20, v: item.score_f, c: "dim-f", t: "F" },
      { w: 20, v: item.score_t, c: "dim-t", t: "T" },
      { w: 20, v: item.score_e, c: "dim-e", t: "E" },
      { w: 20, v: item.score_l, c: "dim-l", t: "L" },
      { w: 20, v: item.score_p, c: "dim-p", t: "P" },
    ];
    const spans = parts
      .map((p) => {
        const h = p.v == null ? 0 : Math.max(0, Math.min(100, Number(p.v)));
        return `<span class="${p.c}" style="width:${(p.w * h) / 100}px" title="${p.t}: ${fmtNum(p.v)}"></span>`;
      })
      .join("");
    return `<div class="ftelp-bar" title="F/T/E/L/P">${spans}</div>`;
  }

  function topRowHtml(row) {
    const inTop = row.is_topn || row.is_top3;
    return `
      <tr>
        <td>${row.rank_no ?? "—"} ${inTop ? '<span class="top-badge">TOP</span>' : ""}</td>
        <td>${row.industry_name || "—"}<br><span class="muted">${row.industry_code || ""}</span></td>
        <td><strong>${fmtNum(row.display_score)}</strong></td>
        <td>${fmtNum(row.main_score)}</td>
        <td class="${signalClass(row.signal_status)}">${row.signal_status || "—"}</td>
        <td>${row.leader_name || "—"}<br><span class="muted">${row.leader_code || ""} ${row.leader_pct_chg != null ? fmtNum(row.leader_pct_chg, 2) + "%" : ""}</span></td>
        <td>${ftelpBar(row)}</td>
        <td>${klineLink("board", row.industry_code, elDate.value)}</td>
        <td><button type="button" class="btn btn-ghost btn-sm btn-history" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">历史</button></td>
      </tr>`;
  }

  function bindHistoryButtons(container) {
    container.querySelectorAll(".btn-history").forEach((btn) => {
      btn.addEventListener("click", () => loadHistory(btn.dataset.code, btn.dataset.name));
    });
  }

  function renderTopGroup(contentType, items, meta) {
    const isIndustry = contentType === "行业";
    const body = isIndustry ? elIndustryBody : elConceptBody;
    const empty = isIndustry ? elIndustryEmpty : elConceptEmpty;
    const updated = isIndustry ? elIndustryUpdated : elConceptUpdated;
    updated.textContent = `交易日 ${meta.trade_date} · ${meta.ma_window} 日均分 · ${contentType} Top${meta.top}`;
    if (!items.length) {
      body.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    body.innerHTML = items.map(topRowHtml).join("");
    bindHistoryButtons(body);
  }

  function applyTypeVisibility() {
    const showIndustry = selectedType === "行业";
    const showConcept = selectedType === "概念";
    elIndustrySection.classList.toggle("hidden", !showIndustry);
    elConceptSection.classList.toggle("hidden", !showConcept);
  }

  function renderTopGroups(data) {
    const meta = { trade_date: data.trade_date, ma_window: data.ma_window, top: data.top };
    const groups = data.groups || [];
    const industry = groups.find((g) => g.content_type === "行业");
    const concept = groups.find((g) => g.content_type === "概念");
    renderTopGroup("行业", industry ? industry.items : [], meta);
    renderTopGroup("概念", concept ? concept.items : [], meta);
    applyTypeVisibility();
  }

  function renderSignals(data) {
    elSignalBody.innerHTML = (data.items || [])
      .map(
        (row) => `
      <tr>
        <td>${row.content_type || "—"}</td>
        <td>${row.industry_name || "—"}<br><span class="muted">${row.industry_code || ""}</span></td>
        <td class="${signalClass(row.signal_status)}">${row.signal_status || "—"}</td>
        <td>${row.signal_start ? "是" : "—"}</td>
        <td>${row.signal_exit ? "是" : "—"}</td>
        <td>${row.rank_no ?? "—"}</td>
        <td>${fmtNum(row.main_score)}</td>
        <td>${ftelpBar(row)}</td>
        <td>${klineLink("board", row.industry_code, elDate.value)}</td>
      </tr>`
      )
      .join("");
  }

  function renderHistoryChartLocal(items) {
    renderHistoryChart(elHistoryChart, items, {
      scoreKey: "main_score_ma5",
      fallbackKey: "main_score",
      stroke: "#22c55e",
    });
  }

  async function loadHistory(code, name) {
    clearError();
    try {
      const td = elDate.value ? toApiTradeDate(elDate.value) : "";
      const q = td ? `?industry_code=${encodeURIComponent(code)}&trade_date=${td}&days=60` : `?industry_code=${encodeURIComponent(code)}&days=60`;
      const data = await apiGet(`/api/v1/quant-mainline/history${q}`);
      elHistoryTitle.textContent = `${name || data.industry_name || code} · FTELP 近60日`;
      renderHistoryChartLocal(data.items);
      elHistoryBody.innerHTML = data.items
        .slice()
        .reverse()
        .map(
          (r) => `
        <tr>
          <td>${r.trade_date}</td>
          <td>${fmtNum(r.main_score)}</td>
          <td>${fmtNum(r.main_score_ma3)}</td>
          <td>${fmtNum(r.main_score_ma5)}</td>
          <td>${fmtNum(r.main_score_ma10)}</td>
          <td class="${signalClass(r.signal_status)}">${r.signal_status || "—"}</td>
          <td>${r.is_top3 ? "是" : "—"}</td>
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
    await initTradeDateCalendar(elDate, "/api/v1/quant-mainline/trade-dates?limit=90");
  }

  function selectedContentTypesParam() {
    return selectedType === "概念" ? "概念" : "行业";
  }

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn || !btn.dataset.value) return;
      typeChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      selectedType = btn.dataset.value;
      queryAll();
    });
  }

  async function queryAll() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const td = elDate.value ? toApiTradeDate(elDate.value) : "";
      const ma = elMa.value;
      const ctypes = selectedContentTypesParam();
      const topData = await apiGet(
        `/api/v1/quant-mainline/top-groups?trade_date=${td}&ma_window=${ma}&top=10&top_only=true&content_types=${encodeURIComponent(ctypes)}`
      );
      renderTopGroups(topData);
      const sigParams = new URLSearchParams({
        trade_date: td,
        content_types: ctypes,
        limit: "200",
      });
      if (elSignalStatus.value) sigParams.set("status", elSignalStatus.value);
      const sigData = await apiGet(`/api/v1/quant-mainline/signals?${sigParams}`);
      renderSignals(sigData);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  btnQuery.addEventListener("click", queryAll);
  if (elSignalStatus) {
    elSignalStatus.addEventListener("change", queryAll);
  }
  btnCloseHistory.addEventListener("click", () => elHistoryCard.classList.add("hidden"));

  (async function init() {
    applyTypeVisibility();
    try {
      await loadTradeDates();
      await queryAll();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
