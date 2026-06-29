/** 东财板块页面公共工具（主线榜 / 量化主线 / 资金强度共用） */
(function () {
  function fmtNum(v, d) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(d === undefined ? 1 : d);
  }

  function fmtPct(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return (n * (Math.abs(n) <= 1 ? 100 : 1)).toFixed(2) + "%";
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  /** YYYY-MM-DD 或 YYYYMMDD → YYYY-MM-DD（供 input[type=date]） */
  function normalizeIsoDate(raw) {
    if (!raw) return "";
    const s = String(raw).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    return s;
  }

  /** input[type=date] → API 参数 YYYYMMDD */
  function toApiTradeDate(isoDate) {
    if (!isoDate) return "";
    return String(isoDate).replace(/-/g, "");
  }

  /** 拉取最新交易日并写入日历控件 */
  async function initTradeDateCalendar(inputEl, datesApiUrl) {
    if (!inputEl) return null;
    const data = await apiGet(datesApiUrl);
    const latest = normalizeIsoDate(data.latest || (data.dates && data.dates[0]) || "");
    if (latest) inputEl.value = latest;
    return data;
  }

  function renderHistoryChart(container, items, options) {
    const opts = options || {};
    const scoreKey = opts.scoreKey || "total_score_ma5";
    const fallbackKey = opts.fallbackKey || "total_score";
    const stroke = opts.stroke || "#3b82f6";
    if (!items.length) {
      container.innerHTML = '<div class="table-empty">暂无历史数据</div>';
      return;
    }
    const w = 640;
    const h = 200;
    const pad = { l: 40, r: 12, t: 12, b: 28 };
    const scores = items.map((x) => Number(x[scoreKey] ?? x[fallbackKey] ?? 0));
    const minY = Math.min(...scores) - 5;
    const maxY = Math.max(...scores) + 5;
    const span = maxY - minY || 1;
    const innerW = w - pad.l - pad.r;
    const innerH = h - pad.t - pad.b;
    const pts = items.map((x, i) => {
      const y =
        pad.t + innerH - ((Number(x[scoreKey] ?? x[fallbackKey] ?? 0) - minY) / span) * innerH;
      const px = pad.l + (i / Math.max(1, items.length - 1)) * innerW;
      return `${px},${y}`;
    });
    container.innerHTML = `
      <svg class="history-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline fill="none" stroke="${stroke}" stroke-width="2" points="${pts.join(" ")}"/>
      </svg>`;
  }

  window.DcBoard = {
    fmtNum,
    fmtPct,
    apiGet,
    normalizeIsoDate,
    toApiTradeDate,
    initTradeDateCalendar,
    renderHistoryChart,
  };
})();
