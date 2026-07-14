(function () {
  const {
    klineLink,
    funnelBoardLinks,
    stockKlineLink,
    consumeFunnelParams,
    pickBoard,
    pickStock,
  } = window.DcBoard || {};

  const elDate = document.getElementById("trade-date");
  const elTypes = document.getElementById("content-types");
  const elBoardSearch = document.getElementById("board-search");
  const elBoardDropdown = document.getElementById("board-dropdown");
  const elBoardSelected = document.getElementById("board-selected");
  const elBoardPicker = document.getElementById("board-picker");
  const elFilterHint = document.getElementById("filter-hint");
  const elLeadersBody = document.getElementById("leaders-body");
  const elLeadersEmpty = document.getElementById("leaders-empty");
  const elLeadersUpdated = document.getElementById("leaders-updated");
  const elPageError = document.getElementById("page-error");
  const elDetailCard = document.getElementById("detail-card");
  const elDetailTitle = document.getElementById("detail-title");
  const elDetailMetrics = document.getElementById("detail-metrics");
  const elScoresBody = document.getElementById("scores-body");
  const detailSortableHeaders = Array.from(document.querySelectorAll("#scores-table .sortable-th"));
  const btnQuery = document.getElementById("btn-query");
  const btnClose = document.getElementById("btn-close-detail");
  const btnResetBoards = document.getElementById("btn-reset-boards");

  let allBoards = [];
  const selectedBoards = new Map();
  let currentIndustryCode = "";
  let activeDetailCode = "";
  let detailSort = "composite";
  let detailOrder = "desc";
  let boardSearchTimer = null;

  function fmtNum(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(1);
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

  function getContentTypesParam() {
    return elTypes && elTypes.value ? elTypes.value : "行业,概念";
  }

  function boardLabel(b) {
    return `[${b.content_type}] ${b.industry_name} (${b.industry_code})`;
  }

  function selectedBoardCodes() {
    return Array.from(selectedBoards.keys());
  }

  function matchBoard(board, q) {
    const text = `${board.industry_name} ${board.industry_code} ${board.content_type}`.toLowerCase();
    const tokens = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return true;
    return tokens.every((t) => text.includes(t));
  }

  function scoreTone(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return "";
    if (n >= 80) return "vp-l1";
    if (n >= 65) return "vp-l2";
    if (n >= 50) return "vp-l3";
    if (n >= 35) return "vp-l4";
    return "vp-l5";
  }

  function vpVal(text, tone, badge) {
    const cls = badge ? `vp-val vp-badge ${tone}` : `vp-val ${tone}`;
    return `<span class="${cls}">${text ?? "—"}</span>`;
  }

  function renderSelectedTags() {
    if (!selectedBoards.size) {
      elBoardSelected.innerHTML = '<span class="board-placeholder">未选择板块（展示全部）</span>';
      return;
    }
    elBoardSelected.innerHTML = Array.from(selectedBoards.values())
      .map(
        (b) =>
          `<span class="board-tag" data-code="${b.industry_code}">` +
          `${boardLabel(b)}<button type="button" aria-label="移除">×</button></span>`
      )
      .join("");
  }

  function updateFilterHint() {
    if (!elFilterHint) return;
    const typeHint = getContentTypesParam().replace(",", "、");
    elFilterHint.textContent = `共 ${allBoards.length} 个板块可选；输入名称或代码后点选；未选表示全部（类型：${typeHint}）`;
  }

  function hideDropdown() {
    elBoardDropdown.classList.add("hidden");
  }

  function renderDropdown(matches) {
    if (!matches.length) {
      elBoardDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配板块</div>';
      elBoardDropdown.classList.remove("hidden");
      return;
    }
    elBoardDropdown.innerHTML = matches
      .slice(0, 50)
      .map(
        (b) =>
          `<button type="button" class="board-option" data-code="${b.industry_code}">` +
          `${boardLabel(b)}</button>`
      )
      .join("");
    elBoardDropdown.classList.remove("hidden");
  }

  async function fetchBoards(keyword) {
    const td = elDate.value;
    if (!td) return [];
    const params = new URLSearchParams({
      trade_date: td,
      content_types: getContentTypesParam(),
    });
    const kw = (keyword || "").trim();
    if (kw) params.set("keyword", kw);
    const data = await apiGet(`/api/v1/dragon/boards?${params}`);
    return data.items || [];
  }

  function onBoardSearchInput() {
    const q = elBoardSearch.value;
    if (!q.trim()) {
      hideDropdown();
      return;
    }
    clearTimeout(boardSearchTimer);
    boardSearchTimer = setTimeout(async () => {
      try {
        const remote = await fetchBoards(q);
        const pool = remote.length ? remote : allBoards;
        const matches = pool.filter(
          (b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q)
        );
        renderDropdown(matches);
      } catch (e) {
        const matches = allBoards.filter(
          (b) => !selectedBoards.has(b.industry_code) && matchBoard(b, q)
        );
        renderDropdown(matches);
        if (!matches.length) showError(e.message || String(e));
      }
    }, 200);
  }

  function addBoard(code) {
    const board = allBoards.find((b) => b.industry_code === code);
    if (!board) return;
    selectedBoards.set(code, board);
    renderSelectedTags();
    elBoardSearch.value = "";
    hideDropdown();
    refresh();
  }

  async function loadBoardOptions() {
    allBoards = await fetchBoards("");
    const keep = new Map();
    selectedBoards.forEach((b, code) => {
      if (allBoards.some((x) => x.industry_code === code)) keep.set(code, b);
    });
    selectedBoards.clear();
    keep.forEach((b, code) => selectedBoards.set(code, b));
    renderSelectedTags();
    updateFilterHint();
  }

  async function loadTradeDates() {
    const data = await apiGet("/api/v1/dragon/trade-dates");
    elDate.innerHTML = "";
    (data.dates || []).forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      elDate.appendChild(opt);
    });
    if (data.latest) elDate.value = data.latest;
  }

  async function loadLeaders() {
    clearError();
    const td = elDate.value;
    const boardCodes = selectedBoardCodes();
    const params = new URLSearchParams({
      trade_date: td,
      content_types: getContentTypesParam(),
      top: boardCodes.length ? String(Math.max(boardCodes.length, 20)) : "100",
    });
    if (boardCodes.length) params.set("industry_codes", boardCodes.join(","));
    const data = await apiGet(`/api/v1/dragon/leaders?${params}`);
    elLeadersUpdated.textContent = `交易日 ${data.trade_date || td} · ${ (data.items || []).length } 条`;
    const items = data.items || [];
    if (!items.length) {
      elLeadersBody.innerHTML = "";
      elLeadersEmpty.classList.remove("hidden");
      return;
    }
    elLeadersEmpty.classList.add("hidden");
    elLeadersBody.innerHTML = items
      .map((r) => {
        const active = r.industry_code === activeDetailCode ? " vp-row-active" : "";
        return (
          `<tr class="${active.trim()}">` +
          `<td>${r.content_type || "—"}</td>` +
          `<td>${r.industry_name || r.industry_code}<br><span class="muted">${r.industry_code || ""}</span></td>` +
          `<td>${r.leader_composite_name || "—"}</td>` +
          `<td>${vpVal(fmtNum(r.score_composite), scoreTone(r.score_composite), true)}</td>` +
          `<td>${r.leader_fund_name || "—"}</td>` +
          `<td>${r.leader_trend_name || "—"}</td>` +
          `<td>${
            funnelBoardLinks
              ? funnelBoardLinks(r.industry_code, r.industry_name, td, { primary: "members" })
              : klineLink
                ? klineLink("board", r.industry_code, td)
                : "—"
          }</td>` +
          `<td><button type="button" class="btn-vp-detail${r.industry_code === activeDetailCode ? " is-active" : ""}" data-code="${r.industry_code}" data-name="${r.industry_name || ""}">数据分析</button></td>` +
          `</tr>`
        );
      })
      .join("");
    elLeadersBody.querySelectorAll(".btn-vp-detail").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (pickBoard) pickBoard(btn.dataset.code, btn.dataset.name, elDate.value);
        openDetail(btn.dataset.code);
      });
    });
  }

  function markDetailSortHeaders() {
    detailSortableHeaders.forEach((th) => {
      const key = th.dataset.sort;
      const arrow = key === detailSort ? (detailOrder === "asc" ? " ▲" : " ▼") : "";
      const base = th.textContent.replace(/\s[▲▼]$/, "");
      th.textContent = `${base}${arrow}`;
    });
  }

  function metricItem(label, value) {
    return `<div class="metric-item"><span class="metric-label">${label}</span><strong class="metric-value">${value}</strong></div>`;
  }

  async function openDetail(industryCode) {
    clearError();
    currentIndustryCode = industryCode;
    activeDetailCode = industryCode;
    const td = elDate.value;
    const [summary, scores] = await Promise.all([
      apiGet(`/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/summary?trade_date=${td}`),
      apiGet(
        `/api/v1/dragon/boards/${encodeURIComponent(industryCode)}/scores?trade_date=${td}` +
          `&top=10&sort=${encodeURIComponent(detailSort)}&order=${encodeURIComponent(detailOrder)}`
      ),
    ]);
    if (pickBoard) pickBoard(industryCode, summary.industry_name || industryCode, td);
    elDetailTitle.textContent = `${summary.industry_name || industryCode} · 成分股评分`;
    if (elDetailMetrics) {
      const topScore = (scores.items || []).find((x) => x.is_composite_leader) || (scores.items || [])[0] || {};
      elDetailMetrics.innerHTML =
        `<div class="vp-metric-block"><div class="vp-metric-block-title">龙头摘要</div>` +
        `<div class="metric-grid metric-grid--vp-row">` +
        metricItem("综合龙头", summary.leader_composite_name || "—") +
        metricItem("综合分", fmtNum(summary.score_composite ?? topScore.score_composite)) +
        metricItem("资金龙头", summary.leader_fund_name || "—") +
        metricItem("趋势龙头", summary.leader_trend_name || "—") +
        metricItem("机构龙头", summary.leader_inst_name || "—") +
        metricItem("交易日", summary.trade_date || td) +
        `</div></div>` +
        (summary.summary_text
          ? `<div class="vp-metric-block"><div class="vp-metric-block-title">说明</div><p class="muted" style="margin:0;line-height:1.6">${summary.summary_text}</p></div>`
          : "");
    }
    const items = scores.items || [];
    markDetailSortHeaders();
    const boardName = summary.industry_name || industryCode;
    elScoresBody.innerHTML = items
      .map(
        (r) =>
          `<tr${r.is_composite_leader ? ' class="row-leader"' : ""}>` +
          `<td>${r.stock_name || r.ts_code}</td>` +
          `<td>${r.ts_code || "—"}</td>` +
          `<td>${vpVal(fmtNum(r.score_composite), scoreTone(r.score_composite), true)}</td>` +
          `<td>${fmtNum(r.score_fund)}</td>` +
          `<td>${fmtNum(r.score_trend)}</td>` +
          `<td>${fmtNum(r.score_inst)}</td>` +
          `<td>${r.rank_composite ?? "—"}</td>` +
          `<td>${
            stockKlineLink
              ? stockKlineLink(r.ts_code, r.stock_name, td, industryCode, boardName)
              : klineLink
                ? klineLink("stock", r.ts_code, td)
                : "—"
          }</td>` +
          `</tr>`
      )
      .join("");
    elDetailCard.classList.remove("hidden");
    elDetailCard.scrollIntoView({ behavior: "smooth", block: "start" });
    loadLeaders().catch(() => {});
  }

  async function refresh() {
    try {
      await loadLeaders();
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  btnQuery.addEventListener("click", refresh);
  btnClose.addEventListener("click", () => {
    elDetailCard.classList.add("hidden");
    activeDetailCode = "";
    refresh();
  });
  btnResetBoards.addEventListener("click", () => {
    selectedBoards.clear();
    elBoardSearch.value = "";
    hideDropdown();
    renderSelectedTags();
    refresh();
  });
  elBoardSearch.addEventListener("input", onBoardSearchInput);
  elBoardSearch.addEventListener("focus", onBoardSearchInput);
  elBoardDropdown.addEventListener("click", async (e) => {
    const btn = e.target.closest(".board-option[data-code]");
    if (!btn) return;
    const code = btn.dataset.code;
    if (!allBoards.some((b) => b.industry_code === code)) {
      try {
        const found = await fetchBoards(code);
        const board = found.find((b) => b.industry_code === code);
        if (board) allBoards.push(board);
      } catch (err) {
        showError(err.message || String(err));
        return;
      }
    }
    addBoard(code);
  });
  elBoardSelected.addEventListener("click", (e) => {
    const tag = e.target.closest(".board-tag");
    if (!tag) return;
    if (e.target.tagName === "BUTTON") {
      selectedBoards.delete(tag.dataset.code);
      renderSelectedTags();
      refresh();
    }
  });
  detailSortableHeaders.forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (!key) return;
      if (detailSort === key) {
        detailOrder = detailOrder === "asc" ? "desc" : "asc";
      } else {
        detailSort = key;
        detailOrder = "desc";
      }
      if (currentIndustryCode) {
        openDetail(currentIndustryCode).catch((e) => showError(e.message || String(e)));
      }
    });
  });
  elDate.addEventListener("change", () => {
    loadBoardOptions()
      .then(() => refresh())
      .catch((e) => showError(e.message || String(e)));
  });
  if (elTypes) {
    elTypes.addEventListener("change", () => {
      loadBoardOptions()
        .then(() => refresh())
        .catch((e) => showError(e.message || String(e)));
    });
  }
  document.addEventListener("click", (e) => {
    if (!elBoardPicker.contains(e.target)) hideDropdown();
  });

  renderSelectedTags();
  loadTradeDates()
    .then(() => loadBoardOptions())
    .then(async () => {
      const funnel = consumeFunnelParams ? consumeFunnelParams({ dateEl: elDate }) : null;
      if (funnel && funnel.industry_code) {
        selectedBoards.set(funnel.industry_code, {
          industry_code: funnel.industry_code,
          industry_name: funnel.industry_name || funnel.industry_code,
          content_type: "",
        });
        renderSelectedTags();
      }
      await refresh();
      if (funnel && funnel.industry_code) {
        await openDetail(funnel.industry_code);
      }
    })
    .catch((e) => showError(e.message || String(e)));
})();
