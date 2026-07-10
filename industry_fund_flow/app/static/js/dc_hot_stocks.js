(function () {
  const { apiGet, toApiTradeDate, initTradeDateCalendar, klineLink } = window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const marketChips = document.getElementById("market-chips");
  const hotTypeTabs = document.getElementById("hot-type-tabs");
  const elHotBody = document.getElementById("hot-body");
  const elHotEmpty = document.getElementById("hot-empty");
  const elHotUpdated = document.getElementById("hot-updated");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const btnQuery = document.getElementById("btn-query");

  let market = "A股市场";
  let hotType = "人气榜";

  function showError(msg) {
    elPageError.textContent = msg;
    elPageError.classList.remove("hidden");
  }

  function clearError() {
    elPageError.classList.add("hidden");
  }

  function cellClass(v) {
    const n = Number(v);
    if (Number.isNaN(n) || v === null || v === "") return "";
    return n > 0 ? "cell-rise" : n < 0 ? "cell-fall" : "";
  }

  function fmtPct(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(2) + "%";
  }

  function fmtNum(v, d) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(d === undefined ? 2 : d);
  }

  if (marketChips) {
    marketChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      marketChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      market = btn.dataset.value || "A股市场";
    });
  }

  if (hotTypeTabs) {
    hotTypeTabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".tab");
      if (!btn) return;
      hotTypeTabs.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      hotType = btn.dataset.type || "人气榜";
      queryHot().catch((err) => showError(err.message));
    });
  }

  function buildListUrl() {
    const params = new URLSearchParams();
    if (elDate.value) params.set("trade_date", toApiTradeDate(elDate.value));
    params.set("hot_type", hotType);
    params.set("market", market);
    return `/api/v1/hot-stocks/list?${params}`;
  }

  function renderTable(data) {
    elHotUpdated.textContent = `${data.trade_date} · ${data.market} · ${data.hot_type} · ${data.items.length} 条`;
    if (!data.items.length) {
      elHotBody.innerHTML = "";
      elHotEmpty.classList.remove("hidden");
      return;
    }
    elHotEmpty.classList.add("hidden");
    elHotBody.innerHTML = data.items
      .map(
        (row) => `
      <tr>
        <td>${row.dc_rank ?? "—"}</td>
        <td>${row.ts_code || "—"}</td>
        <td>${row.ts_name || "—"}</td>
        <td class="${cellClass(row.pct_change)}">${fmtPct(row.pct_change)}</td>
        <td>${fmtNum(row.current_price, 2)}</td>
        <td>${row.amount_yi != null ? row.amount_yi + "亿" : "—"}</td>
        <td>${row.turnover_rate != null ? fmtNum(row.turnover_rate, 2) + "%" : "—"}</td>
        <td>${row.pe_ttm != null ? fmtNum(row.pe_ttm, 2) : "—"}</td>
        <td>${row.rank_time || "—"}</td>
        <td>${klineLink("stock", row.ts_code, elDate.value)}</td>
      </tr>`
      )
      .join("");
  }

  async function queryHot() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const data = await apiGet(buildListUrl());
      renderTable(data);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  btnQuery.addEventListener("click", () => queryHot().catch((err) => showError(err.message)));
  elDate.addEventListener("change", () => queryHot().catch((err) => showError(err.message)));

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/hot-stocks/trade-dates?limit=90");
      await queryHot();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
