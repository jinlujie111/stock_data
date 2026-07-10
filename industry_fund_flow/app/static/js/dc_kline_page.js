(function () {
  const board = window.DcBoard;
  const kline = window.DcKline;
  if (!board || !kline) return;

  const { apiGet, toApiTradeDate, initTradeDateCalendar, normalizeIsoDate } = board;

  const elDate = document.getElementById("trade-date");
  const kindChips = document.getElementById("kind-chips");
  const indicatorChips = document.getElementById("indicator-chips");
  const elSearch = document.getElementById("symbol-search");
  const elDropdown = document.getElementById("symbol-dropdown");
  const elSymbolLabel = document.getElementById("symbol-label");
  const elDays = document.getElementById("kline-days");
  const btnLoad = document.getElementById("btn-load");
  const elHeader = document.getElementById("kline-header");
  const elChart = document.getElementById("kline-chart");
  const elLevels = document.getElementById("kline-levels");
  const elError = document.getElementById("page-error");

  let kind = "stock";
  let selectedCode = "";
  let selectedName = "";
  let searchTimer = null;
  let chartInstance = null;
  const activeIndicators = new Set();

  function showError(msg) {
    elError.textContent = msg;
    elError.classList.remove("hidden");
  }

  function clearError() {
    elError.classList.add("hidden");
  }

  function tdParam() {
    return elDate.value ? toApiTradeDate(elDate.value) : "";
  }

  function updateKindUi() {
    if (elSymbolLabel) {
      elSymbolLabel.textContent = kind === "board" ? "板块（名称/代码搜索）" : "股票（名称/代码搜索）";
    }
    if (elSearch) {
      elSearch.placeholder = kind === "board" ? "输入板块名称或代码…" : "输入股票名称或代码…";
    }
  }

  if (kindChips) {
    kindChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      kindChips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      kind = btn.dataset.value || "stock";
      selectedCode = "";
      selectedName = "";
      if (elSearch) elSearch.value = "";
      updateKindUi();
    });
  }

  if (indicatorChips) {
    indicatorChips.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const key = btn.dataset.value;
      if (!key) return;
      if (activeIndicators.has(key)) {
        activeIndicators.delete(key);
        btn.classList.remove("active");
      } else {
        activeIndicators.add(key);
        btn.classList.add("active");
      }
      if (window._klinePayload) {
        refreshChart(window._klinePayload);
      }
    });
  }

  function hideDropdown() {
    if (elDropdown) elDropdown.classList.add("hidden");
  }

  function showDropdown(items) {
    if (!elDropdown) return;
    if (!items.length) {
      elDropdown.innerHTML = '<div class="board-dropdown-item muted">无匹配结果</div>';
    } else {
      elDropdown.innerHTML = items
        .map((it) => {
          if (kind === "board") {
            return `<button type="button" class="board-dropdown-item" data-code="${it.industry_code}" data-name="${it.industry_name || ""}">[${it.content_type || ""}] ${it.industry_name} (${it.industry_code})</button>`;
          }
          return `<button type="button" class="board-dropdown-item" data-code="${it.ts_code}" data-name="${it.stock_name || it.name || ""}">${it.stock_name || it.name || ""} (${it.ts_code})</button>`;
        })
        .join("");
    }
    elDropdown.classList.remove("hidden");
  }

  async function searchSymbol(keyword) {
    const q = encodeURIComponent(keyword);
    const td = tdParam();
    const tdQ = td ? `&trade_date=${td}` : "";
    const data = await apiGet(`/api/v1/chart/search?kind=${kind}&keyword=${q}${tdQ}`);
    showDropdown(data.items || []);
  }

  if (elSearch) {
    elSearch.addEventListener("input", () => {
      clearTimeout(searchTimer);
      const kw = elSearch.value.trim();
      if (kw.length < 1) {
        hideDropdown();
        return;
      }
      searchTimer = setTimeout(() => searchSymbol(kw).catch(() => hideDropdown()), 250);
    });
    elSearch.addEventListener("focus", () => {
      const kw = elSearch.value.trim();
      if (kw.length >= 1) searchSymbol(kw).catch(() => {});
    });
  }

  if (elDropdown) {
    elDropdown.addEventListener("click", (e) => {
      const btn = e.target.closest(".board-dropdown-item");
      if (!btn) return;
      selectedCode = btn.dataset.code || "";
      selectedName = btn.dataset.name || "";
      elSearch.value = selectedName ? `${selectedName} (${selectedCode})` : selectedCode;
      hideDropdown();
    });
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#symbol-picker")) hideDropdown();
  });

  function refreshChart(payload) {
    window._klinePayload = payload;
    kline.renderSnapshotHeader(elHeader, payload);
    chartInstance = kline.renderKlineChart(elChart, payload, {
      activeIndicators: Array.from(activeIndicators),
      existingChart: chartInstance,
    });
    kline.renderLevelPanel(elLevels, Array.from(activeIndicators), payload.levels || {});
  }

  async function loadKline() {
    clearError();
    const code = selectedCode || elSearch.value.trim();
    if (!code) {
      showError("请先搜索并选择股票或板块");
      return;
    }
    const td = tdParam();
    const days = elDays ? elDays.value : "120";
    const tdQ = td ? `&trade_date=${td}` : "";
    try {
      const payload = await apiGet(
        `/api/v1/chart/kline?kind=${kind}&code=${encodeURIComponent(code)}&days=${days}${tdQ}`
      );
      selectedCode = payload.code;
      refreshChart(payload);
    } catch (err) {
      showError(err.message || "加载 K 线失败");
    }
  }

  if (btnLoad) btnLoad.addEventListener("click", () => loadKline().catch((e) => showError(e.message)));

  const params = new URLSearchParams(window.location.search);
  const urlKind = params.get("kind");
  const urlCode = params.get("code");
  const urlIndicator = params.get("indicator");
  const urlTradeDate = params.get("trade_date");

  if (urlKind && kindChips) {
    kind = urlKind;
    kindChips.querySelectorAll(".chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.value === urlKind);
    });
    updateKindUi();
  }
  if (urlIndicator && indicatorChips) {
    urlIndicator.split(",").forEach((key) => {
      const btn = indicatorChips.querySelector(`[data-value="${key}"]`);
      if (btn) {
        activeIndicators.add(key);
        btn.classList.add("active");
      }
    });
  }
  if (urlCode) {
    selectedCode = urlCode;
    if (elSearch) elSearch.value = urlCode;
  }

  initTradeDateCalendar(elDate, "/api/v1/sectors/trade-dates")
    .then(() => {
      if (urlTradeDate && elDate) {
        const iso = normalizeIsoDate(urlTradeDate);
        if (iso) elDate.value = iso;
      }
      if (selectedCode) return loadKline();
      return null;
    })
    .catch((e) => showError(e.message || "初始化失败"));
})();
