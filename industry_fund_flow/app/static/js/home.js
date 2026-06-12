(function () {
  const elDate = document.getElementById("breadth-date");
  const elGrid = document.getElementById("breadth-metrics");
  const elEmpty = document.getElementById("breadth-empty");
  const elError = document.getElementById("breadth-error");
  const elSummary = document.getElementById("breadth-summary");

  function fmtValue(val, fmt) {
    if (val === null || val === undefined || val === "") return "—";
    if (fmt === "int") return Number(val).toLocaleString("zh-CN");
    if (fmt === "pct") {
      const n = Number(val);
      if (Number.isNaN(n)) return val;
      const pct = n <= 1 && n >= -1 ? n * 100 : n;
      return pct.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + "%";
    }
    return val;
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  function renderMetrics(payload) {
    if (!payload.data) {
      elGrid.innerHTML = "";
      elEmpty.classList.remove("hidden");
      elSummary.textContent = payload.trade_date
        ? `${payload.trade_date} 暂无市场广度数据`
        : "暂无市场广度数据";
      return;
    }
    elEmpty.classList.add("hidden");
    const data = payload.data;
    elGrid.innerHTML = payload.metrics
      .filter((m) => m.key !== "trade_date")
      .map((m) => {
        const val = data[m.key];
        let cls = "metric-value";
        if (m.key === "advance_cnt" || m.key === "limit_up_cnt") cls += " metric-up";
        if (m.key === "decline_cnt" || m.key === "limit_down_cnt") cls += " metric-down";
        return (
          `<div class="metric-card">` +
          `<div class="metric-label">${m.label}</div>` +
          `<div class="${cls}">${fmtValue(val, m.fmt)}</div>` +
          `</div>`
        );
      })
      .join("");
    elSummary.textContent = `交易日期 ${data.trade_date} · 沪深 A 股全市场广度`;
  }

  async function loadDates() {
    const res = await apiGet("/api/market-breadth/trade-dates");
    elDate.innerHTML = res.dates
      .map((d) => `<option value="${d}">${d}</option>`)
      .join("");
    if (res.latest) {
      if (!res.dates.includes(res.latest)) {
        elDate.insertAdjacentHTML("afterbegin", `<option value="${res.latest}">${res.latest}</option>`);
      }
      elDate.value = res.latest;
    }
  }

  async function loadBreadth() {
    elError.classList.add("hidden");
    const td = elDate.value;
    const url = td
      ? `/api/market-breadth?trade_date=${encodeURIComponent(td)}`
      : "/api/market-breadth";
    const payload = await apiGet(url);
    if (payload.trade_date && elDate.value !== payload.trade_date) {
      elDate.value = payload.trade_date;
    }
    renderMetrics(payload);
  }

  elDate.addEventListener("change", () => {
    loadBreadth().catch((err) => {
      elError.textContent = err.message;
      elError.classList.remove("hidden");
    });
  });

  loadDates()
    .then(() => loadBreadth())
    .catch((err) => {
      elError.textContent = err.message;
      elError.classList.remove("hidden");
    });
})();
