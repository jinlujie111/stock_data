(function () {
  const { fmtNum, apiGet, toApiTradeDate, initTradeDateCalendar } = window.DcBoard;

  const elDate = document.getElementById("trade-date");
  const elAddSearch = document.getElementById("stock-add-search");
  const elAddDropdown = document.getElementById("stock-add-dropdown");
  const elStockBody = document.getElementById("stock-body");
  const elStockEmpty = document.getElementById("stock-empty");
  const elStockUpdated = document.getElementById("stock-updated");
  const elPageError = document.getElementById("page-error");
  const btnQuery = document.getElementById("btn-query");

  let stockFavCodes = new Set();
  let addSearchTimer = null;

  function tdParam() {
    return elDate.value ? toApiTradeDate(elDate.value) : "";
  }

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

  function fmtPctCell(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    const pct = Math.abs(n) <= 1 && Math.abs(n) !== 0 ? n * 100 : n;
    return pct.toFixed(2) + "%";
  }

  function fmtYi(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(2) + "亿";
  }

  function fmtWan(v, unit) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(2) + (unit || "万手");
  }

  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  async function apiDelete(path) {
    const res = await fetch(path, { method: "DELETE", credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function hideDropdown() {
    elAddDropdown.classList.add("hidden");
  }

  function renderStockTable(data) {
    const items = data.items || [];
    stockFavCodes = new Set(items.map((x) => x.ts_code));
    elStockUpdated.textContent = `交易日 ${data.trade_date || "—"} · ${items.length} 条`;
    if (!items.length) {
      elStockBody.innerHTML = "";
      elStockEmpty.classList.remove("hidden");
      return;
    }
    elStockEmpty.classList.add("hidden");
    elStockBody.innerHTML = items
      .map(
        (row) => `
      <tr>
        <td>${row.ts_code || "—"}</td>
        <td>${row.stock_name || "—"}</td>
        <td>${row.close != null ? fmtNum(row.close, 2) : "—"}</td>
        <td>${row.total_mv_yi != null ? fmtYi(row.total_mv_yi) : "—"}</td>
        <td>${row.vol_wan != null ? fmtWan(row.vol_wan) : "—"}</td>
        <td>${row.amount_yi != null ? fmtYi(row.amount_yi) : "—"}</td>
        <td class="${cellClass(row.net_mf_today_yi)}">${row.net_mf_today_yi != null ? fmtYi(row.net_mf_today_yi) : "—"}</td>
        <td class="${cellClass(row.net_mf_5d_yi)}">${row.net_mf_5d_yi != null ? fmtYi(row.net_mf_5d_yi) : "—"}</td>
        <td class="${cellClass(row.net_mf_20d_yi)}">${row.net_mf_20d_yi != null ? fmtYi(row.net_mf_20d_yi) : "—"}</td>
        <td class="${cellClass(row.ytd_pct)}">${row.ytd_pct != null ? fmtPctCell(row.ytd_pct) : "—"}</td>
        <td><button type="button" class="btn btn-ghost btn-sm" data-del="${row.ts_code}">移除</button></td>
      </tr>`
      )
      .join("");
    elStockBody.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", () =>
        removeStockFav(btn.dataset.del).catch((err) => showError(err.message))
      );
    });
  }

  async function loadStocks() {
    clearError();
    const td = tdParam();
    const q = td ? `?trade_date=${td}` : "";
    const data = await apiGet(`/api/v1/favorites/stocks${q}`);
    renderStockTable(data);
  }

  async function addStockFav(item) {
    await apiPost("/api/v1/favorites/stocks", {
      ts_code: item.ts_code,
      stock_name: item.stock_name || null,
    });
    elAddSearch.value = "";
    hideDropdown();
    await loadStocks();
  }

  async function removeStockFav(tsCode) {
    await apiDelete(`/api/v1/favorites/stocks/${encodeURIComponent(tsCode)}`);
    await loadStocks();
  }

  function onAddStockInput() {
    const q = elAddSearch.value.trim();
    if (!q) {
      hideDropdown();
      return;
    }
    clearTimeout(addSearchTimer);
    addSearchTimer = setTimeout(async () => {
      try {
        const td = tdParam();
        const params = new URLSearchParams({ keyword: q });
        if (td) params.set("trade_date", td);
        const data = await apiGet(`/api/v1/sectors/lookup/stock?${params}`);
        const items = (data.items || []).filter((s) => !stockFavCodes.has(s.ts_code));
        if (!items.length) {
          elAddDropdown.innerHTML = '<div class="board-option board-option--empty">无匹配或未添加的新股票</div>';
          elAddDropdown.classList.remove("hidden");
          return;
        }
        elAddDropdown.innerHTML = items
          .map(
            (s) =>
              `<button type="button" class="board-option" data-code="${s.ts_code}">${s.stock_name || s.ts_code} (${s.ts_code})</button>`
          )
          .join("");
        elAddDropdown.classList.remove("hidden");
        elAddDropdown.querySelectorAll(".board-option[data-code]").forEach((btn) => {
          btn.addEventListener("click", () => {
            const item = items.find((s) => s.ts_code === btn.dataset.code);
            if (item) addStockFav(item).catch((err) => showError(err.message));
          });
        });
      } catch (err) {
        showError(err.message);
      }
    }, 250);
  }

  btnQuery.addEventListener("click", () => loadStocks().catch((err) => showError(err.message)));
  elAddSearch.addEventListener("input", onAddStockInput);
  document.addEventListener("click", (e) => {
    if (elAddSearch && !elAddSearch.parentElement.contains(e.target)) hideDropdown();
  });

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/sectors/trade-dates?limit=90");
      await loadStocks();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
