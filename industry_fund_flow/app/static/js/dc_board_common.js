/** 东财板块页面公共工具（主线榜 / 量化主线共用） */
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
    renderHistoryChart,
  };
})();
