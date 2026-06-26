(function () {
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

  let selectedType = "";

  function fmtNum(v, d) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(d === undefined ? 1 : d);
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

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
    const showIndustry = !selectedType || selectedType === "行业";
    const showConcept = !selectedType || selectedType === "概念";
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
      </tr>`
      )
      .join("");
  }

  function renderHistoryChart(items) {
    if (!items.length) {
      elHistoryChart.innerHTML = '<div class="table-empty">暂无历史数据</div>';
      return;
    }
    const w = 640;
    const h = 200;
    const pad = { l: 40, r: 12, t: 12, b: 28 };
    const scores = items.map((x) => Number(x.main_score_ma5 ?? x.main_score ?? 0));
    const minY = Math.min(...scores) - 5;
    const maxY = Math.max(...scores) + 5;
    const span = maxY - minY || 1;
    const innerW = w - pad.l - pad.r;
    const innerH = h - pad.t - pad.b;
    const pts = items.map((x, i) => {
      const y = pad.t + innerH - ((Number(x.main_score_ma5 ?? x.main_score ?? 0) - minY) / span) * innerH;
      const px = pad.l + (i / Math.max(1, items.length - 1)) * innerW;
      return `${px},${y}`;
    });
    elHistoryChart.innerHTML = `
      <svg class="history-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline fill="none" stroke="#22c55e" stroke-width="2" points="${pts.join(" ")}"/>
      </svg>`;
  }

  async function loadHistory(code, name) {
    clearError();
    try {
      const td = elDate.value ? elDate.value.replace(/-/g, "") : "";
      const q = td ? `?industry_code=${encodeURIComponent(code)}&trade_date=${td}&days=60` : `?industry_code=${encodeURIComponent(code)}&days=60`;
      const data = await apiGet(`/api/v1/quant-mainline/history${q}`);
      elHistoryTitle.textContent = `${name || data.industry_name || code} · FTELP 近60日`;
      renderHistoryChart(data.items);
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
    const data = await apiGet("/api/v1/quant-mainline/trade-dates?limit=90");
    elDate.innerHTML = (data.dates || [])
      .map((d) => `<option value="${d}">${d}</option>`)
      .join("");
    if (data.latest && !elDate.value) elDate.value = data.latest;
  }

  function selectedContentTypesParam() {
    if (selectedType === "行业" || selectedType === "概念") return selectedType;
    return "行业,概念";
  }

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      typeChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      selectedType = btn.dataset.value || "";
      queryAll();
    });
  }

  async function queryAll() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const td = elDate.value ? elDate.value.replace(/-/g, "") : "";
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
  btnCloseHistory.addEventListener("click", () => elHistoryCard.classList.add("hidden"));

  (async function init() {
    try {
      await loadTradeDates();
      await queryAll();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
