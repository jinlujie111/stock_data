(function () {
  const { fmtNum, fmtPct, apiGet, toApiTradeDate, initTradeDateCalendar } = window.DcBoard;
  const { renderSnapshotHeader, renderKlineChart } = window.DcKline;

  const elDate = document.getElementById("trade-date");
  const typeChips = document.getElementById("content-type-chips");
  const elKeyword = document.getElementById("sector-keyword");
  const elSectorBody = document.getElementById("sector-body");
  const elSectorEmpty = document.getElementById("sector-empty");
  const elSectorUpdated = document.getElementById("sector-updated");
  const elPageError = document.getElementById("page-error");
  const elFilterHint = document.getElementById("filter-hint");
  const btnQuery = document.getElementById("btn-query");
  const elMembersCard = document.getElementById("members-card");
  const elMembersTitle = document.getElementById("members-title");
  const elMembersBody = document.getElementById("members-body");
  const elMembersEmpty = document.getElementById("members-empty");
  const btnCloseMembers = document.getElementById("btn-close-members");
  const elBoardFavSearch = document.getElementById("board-fav-search");
  const elBoardFavDropdown = document.getElementById("board-fav-dropdown");
  const elBoardFavList = document.getElementById("board-fav-list");
  const elStockFavSearch = document.getElementById("stock-fav-search");
  const elStockFavDropdown = document.getElementById("stock-fav-dropdown");
  const elStockFavList = document.getElementById("stock-fav-list");
  const elKlineCard = document.getElementById("kline-card");
  const elKlineHeader = document.getElementById("kline-header");
  const elKlineChart = document.getElementById("kline-chart");
  const elKlineEmpty = document.getElementById("kline-empty");
  const elKlineSubtitle = document.getElementById("kline-subtitle");
  const btnCloseKline = document.getElementById("btn-close-kline");
  const btnKlineMembers = document.getElementById("btn-kline-members");

  let contentType = "行业";
  let boardFavCodes = new Set();
  let stockFavCodes = new Set();
  let klineChart = null;
  let activeKlineBoard = null;

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

  function fmtYi(v, digits) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(digits === undefined ? 2 : digits) + "亿";
  }

  function leaderText(row) {
    const parts = [];
    if (row.leader_composite_name) parts.push(row.leader_composite_name);
    else if (row.dc_leading) parts.push(row.dc_leading);
    if (row.leader_fund_name && row.leader_fund_name !== parts[0]) {
      parts.push("资金:" + row.leader_fund_name);
    }
    return parts.length ? parts.join(" · ") : "—";
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

  if (typeChips) {
    typeChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      typeChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      contentType = btn.dataset.value || "行业";
    });
  }

  function buildListUrl() {
    const params = new URLSearchParams();
    const td = tdParam();
    if (td) params.set("trade_date", td);
    params.set("content_type", contentType);
    const kw = elKeyword.value.trim();
    if (kw) params.set("keyword", kw);
    return `/api/v1/sectors/list?${params}`;
  }

  function renderSectorTable(data) {
    elSectorUpdated.textContent = `交易日 ${data.trade_date} · ${data.content_type} · 按涨幅降序 · ${data.items.length} 条`;
    if (!data.items.length) {
      elSectorBody.innerHTML = "";
      elSectorEmpty.classList.remove("hidden");
      return;
    }
    elSectorEmpty.classList.add("hidden");
    elSectorBody.innerHTML = data.items
      .map((row) => {
        const isFav = boardFavCodes.has(row.industry_code);
        return `
      <tr data-code="${row.industry_code}">
        <td>
          <button type="button" class="star-btn${isFav ? " is-fav" : ""}" data-action="fav-board" data-code="${row.industry_code}" data-name="${row.industry_name || ""}" data-ct="${row.content_type || ""}" title="加入板块自选">★</button>
          <button type="button" class="link-name" data-action="members" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">${row.industry_name || "—"}</button>
        </td>
        <td class="${cellClass(row.pct_change)}">${fmtPctCell(row.pct_change)}</td>
        <td class="${cellClass(row.net_amount_yi)}">${row.net_amount_yi != null ? fmtYi(row.net_amount_yi) : "—"}</td>
        <td>${row.board_amount_yi != null ? fmtYi(row.board_amount_yi) : "—"}</td>
        <td>${row.turnover_rate != null ? fmtNum(row.turnover_rate, 2) + "%" : "—"}</td>
        <td>${row.up_num ?? "—"} / ${row.down_num ?? "—"}</td>
        <td>${row.limit_up_cnt ?? "—"}</td>
        <td>${row.total_mv_yi != null ? fmtYi(row.total_mv_yi, 0) : "—"}</td>
        <td>${leaderText(row)}</td>
        <td><button type="button" class="btn btn-ghost btn-sm" data-action="members" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">成分</button></td>
      </tr>`;
      })
      .join("");
    bindSectorActions();
  }

  function bindSectorActions() {
    elSectorBody.querySelectorAll("[data-action=members]").forEach((btn) => {
      btn.addEventListener("click", () => loadMembers(btn.dataset.code, btn.dataset.name));
    });
    elSectorBody.querySelectorAll("[data-action=fav-board]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleBoardFav(btn.dataset.code, btn.dataset.name, btn.dataset.ct, btn);
      });
    });
  }

  function setFavActive(kind, code) {
    elBoardFavList.querySelectorAll(".fav-item").forEach((el) => {
      el.classList.toggle("active", kind === "board" && el.dataset.code === code);
    });
    elStockFavList.querySelectorAll(".fav-item").forEach((el) => {
      el.classList.toggle("active", kind === "stock" && el.dataset.code === code);
    });
  }

  function showKlineCard() {
    elKlineCard.classList.remove("hidden");
    elKlineEmpty.classList.add("hidden");
  }

  function hideKlineCard() {
    elKlineCard.classList.add("hidden");
    activeKlineBoard = null;
    btnKlineMembers.classList.add("hidden");
    setFavActive(null, null);
    if (klineChart) {
      klineChart.dispose();
      klineChart = null;
    }
  }

  async function loadBoardKline(code, name) {
    clearError();
    setFavActive("board", code);
    activeKlineBoard = { code, name };
    btnKlineMembers.classList.remove("hidden");
    elKlineSubtitle.textContent = "板块 K 线";
    try {
      const td = tdParam();
      const q = new URLSearchParams({ days: "120" });
      if (td) q.set("trade_date", td);
      const data = await apiGet(`/api/v1/sectors/${encodeURIComponent(code)}/kline?${q}`);
      renderSnapshotHeader(elKlineHeader, data);
      klineChart = renderKlineChart(elKlineChart, data, klineChart);
      showKlineCard();
      elKlineCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showError(err.message);
    }
  }

  async function loadStockKline(tsCode, name) {
    clearError();
    setFavActive("stock", tsCode);
    activeKlineBoard = null;
    btnKlineMembers.classList.add("hidden");
    elKlineSubtitle.textContent = "个股 K 线";
    try {
      const td = tdParam();
      const q = new URLSearchParams({ days: "120" });
      if (td) q.set("trade_date", td);
      const data = await apiGet(`/api/v1/sectors/stock/${encodeURIComponent(tsCode)}/kline?${q}`);
      if (name && !data.name) data.name = name;
      renderSnapshotHeader(elKlineHeader, data);
      klineChart = renderKlineChart(elKlineChart, data, klineChart);
      showKlineCard();
      elKlineCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showError(err.message);
    }
  }

  async function loadMembers(code, name) {
    clearError();
    try {
      const td = tdParam();
      const q = td ? `?trade_date=${td}` : "";
      const data = await apiGet(`/api/v1/sectors/${encodeURIComponent(code)}/members${q}`);
      elMembersTitle.textContent = `${name || data.industry_name || code} · 成分股（${data.trade_date}）`;
      if (!data.items.length) {
        elMembersBody.innerHTML = "";
        elMembersEmpty.classList.remove("hidden");
      } else {
        elMembersEmpty.classList.add("hidden");
        elMembersBody.innerHTML = data.items
          .map((row) => {
            const isFav = stockFavCodes.has(row.ts_code);
            return `
          <tr>
            <td>${row.ts_code || "—"}</td>
            <td>${row.stock_name || "—"}</td>
            <td class="${cellClass(row.pct_chg)}">${fmtPctCell(row.pct_chg)}</td>
            <td>${row.close != null ? fmtNum(row.close, 2) : "—"}</td>
            <td>${row.amount_yi != null ? fmtYi(row.amount_yi) : "—"}</td>
            <td>${row.turnover_rate != null ? fmtNum(row.turnover_rate, 2) + "%" : "—"}</td>
            <td>${row.pe_ttm != null ? fmtNum(row.pe_ttm, 2) : "—"}</td>
            <td class="${cellClass(row.net_mf_yi)}">${row.net_mf_yi != null ? fmtYi(row.net_mf_yi) : "—"}</td>
            <td><button type="button" class="star-btn${isFav ? " is-fav" : ""}" data-ts="${row.ts_code}" data-name="${row.stock_name || ""}">★</button></td>
          </tr>`;
          })
          .join("");
        elMembersBody.querySelectorAll(".star-btn").forEach((btn) => {
          btn.addEventListener("click", () => toggleStockFav(btn.dataset.ts, btn.dataset.name, btn));
        });
      }
      elMembersCard.classList.remove("hidden");
      elMembersCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showError(err.message);
    }
  }

  async function querySectors() {
    clearError();
    elFilterHint.textContent = "查询中…";
    try {
      const data = await apiGet(buildListUrl());
      renderSectorTable(data);
      elFilterHint.textContent = "";
    } catch (err) {
      elFilterHint.textContent = "";
      showError(err.message);
    }
  }

  async function loadBoardFavorites() {
    const td = tdParam();
    const q = td ? `?trade_date=${td}` : "";
    const data = await apiGet(`/api/v1/favorites/boards${q}`);
    boardFavCodes = new Set(data.items.map((x) => x.industry_code));
    if (!data.items.length) {
      elBoardFavList.innerHTML = '<div class="fav-empty">暂无自选板块</div>';
      return;
    }
    elBoardFavList.innerHTML = data.items
      .map(
        (item) => `
      <div class="fav-item" data-code="${item.industry_code}" data-name="${item.industry_name || item.industry_code}">
        <div class="fav-item-main">
          <div class="fav-item-name">${item.industry_name || item.industry_code}</div>
          <div class="fav-item-meta">${item.content_type || ""} · <span class="${cellClass(item.pct_change)}">${item.pct_change != null ? fmtPctCell(item.pct_change) : "—"}</span></div>
        </div>
        <button type="button" class="fav-item-del" data-del-board="${item.industry_code}" title="移除">×</button>
      </div>`
      )
      .join("");
    elBoardFavList.querySelectorAll(".fav-item").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("[data-del-board]")) return;
        loadBoardKline(el.dataset.code, el.dataset.name);
      });
    });
    elBoardFavList.querySelectorAll("[data-del-board]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeBoardFav(btn.dataset.delBoard);
      });
    });
  }

  async function loadStockFavorites() {
    const td = tdParam();
    const q = td ? `?trade_date=${td}` : "";
    const data = await apiGet(`/api/v1/favorites/stocks${q}`);
    stockFavCodes = new Set(data.items.map((x) => x.ts_code));
    if (!data.items.length) {
      elStockFavList.innerHTML = '<div class="fav-empty">暂无自选股票</div>';
      return;
    }
    elStockFavList.innerHTML = data.items
      .map(
        (item) => `
      <div class="fav-item" data-code="${item.ts_code}" data-name="${item.stock_name || item.ts_code}">
        <div class="fav-item-main">
          <div class="fav-item-name">${item.stock_name || item.ts_code}</div>
          <div class="fav-item-meta">${item.ts_code} · <span class="${cellClass(item.pct_chg)}">${item.pct_chg != null ? fmtPctCell(item.pct_chg) : "—"}</span></div>
        </div>
        <button type="button" class="fav-item-del" data-del-stock="${item.ts_code}" title="移除">×</button>
      </div>`
      )
      .join("");
    elStockFavList.querySelectorAll(".fav-item").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("[data-del-stock]")) return;
        loadStockKline(el.dataset.code, el.dataset.name);
      });
    });
    elStockFavList.querySelectorAll("[data-del-stock]").forEach((btn) => {
      btn.addEventListener("click", () => removeStockFav(btn.dataset.delStock));
    });
  }

  async function refreshFavorites() {
    await Promise.all([loadBoardFavorites(), loadStockFavorites()]);
  }

  async function addBoardFav(code, name, ct) {
    await apiPost("/api/v1/favorites/boards", {
      industry_code: code,
      industry_name: name || null,
      content_type: ct || null,
    });
    await refreshFavorites();
  }

  async function removeBoardFav(code) {
    await apiDelete(`/api/v1/favorites/boards/${encodeURIComponent(code)}`);
    await refreshFavorites();
    await querySectors();
  }

  async function toggleBoardFav(code, name, ct, btn) {
    try {
      if (boardFavCodes.has(code)) {
        await removeBoardFav(code);
      } else {
        await addBoardFav(code, name, ct);
        if (btn) btn.classList.add("is-fav");
        await querySectors();
      }
    } catch (err) {
      showError(err.message);
    }
  }

  async function addStockFav(tsCode, name) {
    await apiPost("/api/v1/favorites/stocks", { ts_code: tsCode, stock_name: name || null });
    await refreshFavorites();
  }

  async function removeStockFav(tsCode) {
    await apiDelete(`/api/v1/favorites/stocks/${encodeURIComponent(tsCode)}`);
    await refreshFavorites();
  }

  async function toggleStockFav(tsCode, name, btn) {
    try {
      if (stockFavCodes.has(tsCode)) {
        await removeStockFav(tsCode);
        if (btn) btn.classList.remove("is-fav");
      } else {
        await addStockFav(tsCode, name);
        if (btn) btn.classList.add("is-fav");
      }
    } catch (err) {
      showError(err.message);
    }
  }

  function bindFavSearch(inputEl, dropdownEl, lookupPath, onPick) {
    inputEl.addEventListener("input", () => {
      clearTimeout(inputEl._timer);
      const kw = inputEl.value.trim();
      if (!kw) {
        dropdownEl.classList.add("hidden");
        dropdownEl.innerHTML = "";
        return;
      }
      inputEl._timer = setTimeout(async () => {
        try {
          const td = tdParam();
          const params = new URLSearchParams({ keyword: kw });
          if (td) params.set("trade_date", td);
          const data = await apiGet(`${lookupPath}?${params}`);
          if (!data.items.length) {
            dropdownEl.innerHTML = '<div class="fav-option">无匹配结果</div>';
          } else {
            dropdownEl.innerHTML = data.items
              .map((item, i) => {
                const label =
                  lookupPath.includes("board")
                    ? `${item.industry_name || item.industry_code} (${item.content_type || ""})`
                    : `${item.stock_name || item.ts_code} ${item.ts_code || ""}`;
                return `<button type="button" class="fav-option" data-idx="${i}">${label}</button>`;
              })
              .join("");
            dropdownEl.querySelectorAll(".fav-option[data-idx]").forEach((btn) => {
              btn.addEventListener("click", () => {
                const item = data.items[Number(btn.dataset.idx)];
                onPick(item);
                inputEl.value = "";
                dropdownEl.classList.add("hidden");
                dropdownEl.innerHTML = "";
              });
            });
          }
          dropdownEl.classList.remove("hidden");
        } catch (err) {
          showError(err.message);
        }
      }, 300);
    });
  }

  bindFavSearch(elBoardFavSearch, elBoardFavDropdown, "/api/v1/sectors/lookup/board", (item) => {
    addBoardFav(item.industry_code, item.industry_name, item.content_type)
      .then(() => querySectors())
      .catch((e) => showError(e.message));
  });

  bindFavSearch(elStockFavSearch, elStockFavDropdown, "/api/v1/sectors/lookup/stock", (item) => {
    addStockFav(item.ts_code, item.stock_name).catch((e) => showError(e.message));
  });

  btnQuery.addEventListener("click", async () => {
    await refreshFavorites();
    await querySectors();
  });
  btnCloseMembers.addEventListener("click", () => elMembersCard.classList.add("hidden"));
  btnCloseKline.addEventListener("click", hideKlineCard);
  btnKlineMembers.addEventListener("click", () => {
    if (activeKlineBoard) loadMembers(activeKlineBoard.code, activeKlineBoard.name);
  });
  elKeyword.addEventListener("keydown", (e) => {
    if (e.key === "Enter") btnQuery.click();
  });

  (async function init() {
    try {
      await initTradeDateCalendar(elDate, "/api/v1/sectors/trade-dates?limit=90");
      await refreshFavorites();
      await querySectors();
    } catch (err) {
      showError(err.message);
    }
  })();
})();
