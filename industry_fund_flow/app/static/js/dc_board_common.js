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
    return n.toFixed(2) + "%";
  }

  async function apiGet(path) {
    const res = await fetch(path, { credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "请求失败");
    return data;
  }

  /** YYYY-MM-DD、YYYYMMDD、带时间的 datetime 字符串 → YYYY-MM-DD（供 input[type=date]） */
  function normalizeIsoDate(raw) {
    if (!raw) return "";
    const s = String(raw).trim();
    const iso = s.match(/^(\d{4}-\d{2}-\d{2})/);
    if (iso) return iso[1];
    if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    return "";
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
    const candidates = [data.latest, ...(data.dates || [])];
    for (const raw of candidates) {
      const iso = normalizeIsoDate(raw);
      if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
        inputEl.value = iso;
        return data;
      }
    }
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

  function escAttr(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function toApiTd(tradeDate) {
    if (!tradeDate) return "";
    const raw = String(tradeDate).trim();
    if (/^\d{8}$/.test(raw)) return raw;
    return toApiTradeDate(normalizeIsoDate(raw) || raw);
  }

  /** 跳转 K 线分析页（kind: stock | board） */
  function klineHref(kind, code, tradeDate) {
    if (!code) return "/dc/kline";
    const params = new URLSearchParams();
    params.set("kind", kind === "board" ? "board" : "stock");
    params.set("code", String(code));
    const apiTd = toApiTd(tradeDate);
    if (apiTd) params.set("trade_date", apiTd);
    return `/dc/kline?${params}`;
  }

  function klineLink(kind, code, tradeDate, label) {
    if (!code) return "—";
    const text = label || "K线分析";
    const href = klineHref(kind, code, tradeDate);
    const td = toApiTd(tradeDate);
    if (kind === "board") {
      return (
        `<a href="${href}" class="kline-link" data-pick-board="${escAttr(code)}" ` +
        `data-pick-name="" data-pick-td="${escAttr(td)}">${text}</a>`
      );
    }
    const ctx = getDecisionCtx();
    return (
      `<a href="${href}" class="kline-link" data-pick-stock="${escAttr(code)}" ` +
      `data-pick-sname="" data-pick-td="${escAttr(td)}" ` +
      `data-pick-board="${escAttr(ctx.industry_code || "")}" ` +
      `data-pick-bname="${escAttr(ctx.industry_name || "")}">${text}</a>`
    );
  }

  // ---------- 上下文（localStorage；页面顶栏「决策链路」已移除） ----------
  const CTX_KEY = "iff_decision_ctx";

  function getDecisionCtx() {
    try {
      return JSON.parse(localStorage.getItem(CTX_KEY) || "{}") || {};
    } catch (_e) {
      return {};
    }
  }

  function setDecisionCtx(patch) {
    const next = Object.assign({}, getDecisionCtx(), patch || {}, { updated_at: Date.now() });
    localStorage.setItem(CTX_KEY, JSON.stringify(next));
    return next;
  }

  function clearDecisionCtx() {
    localStorage.removeItem(CTX_KEY);
  }

  function pickBoard(code, name, tradeDate) {
    const patch = {
      industry_code: code || "",
      industry_name: name || "",
      ts_code: "",
      stock_name: "",
    };
    const td = toApiTd(tradeDate);
    if (td) patch.trade_date = td;
    return setDecisionCtx(patch);
  }

  function pickStock(tsCode, stockName, tradeDate, boardCode, boardName) {
    const patch = {
      ts_code: tsCode || "",
      stock_name: stockName || "",
    };
    const td = toApiTd(tradeDate);
    if (td) patch.trade_date = td;
    if (boardCode) {
      patch.industry_code = boardCode;
      patch.industry_name = boardName || "";
    }
    return setDecisionCtx(patch);
  }

  /** 板块页跳转 URL（不写 Context；点击时靠 data-pick-* 写入） */
  function boardPageHref(path, code, name, tradeDate) {
    const params = new URLSearchParams();
    if (code) params.set("industry_code", String(code));
    if (name) params.set("industry_name", String(name));
    const td = toApiTd(tradeDate);
    if (td) params.set("trade_date", td);
    const q = params.toString();
    return q ? `${path}?${q}` : path;
  }

  /**
   * 板块「下一步」链接
   * primary: vp | stock | members
   */
  function funnelBoardLinks(code, name, tradeDate, opts) {
    if (!code) return "—";
    const primary = (opts && opts.primary) || "vp";
    const td = toApiTd(tradeDate);
    const nm = name || "";
    const pick =
      ` data-pick-board="${escAttr(code)}" data-pick-name="${escAttr(nm)}" data-pick-td="${escAttr(td)}"`;
    const vp = boardPageHref("/dc/volume-price", code, nm, td);
    const dragon = boardPageHref("/dc/dragon", code, nm, td);
    const sectors = boardPageHref("/dc/sectors", code, nm, td);
    const boardK = klineHref("board", code, td);
    const a = (href, cls, text) =>
      `<a href="${href}" class="funnel-link ${cls}"${pick}>${text}</a>`;

    let html = "";
    if (primary === "stock") {
      html =
        a(sectors, "funnel-link--primary", "选股票") +
        a(dragon, "", "龙头") +
        a(boardK, "", "板块K线");
    } else if (primary === "members") {
      html =
        a(sectors, "funnel-link--primary", "成分选股") +
        a(vp, "", "量价") +
        a(dragon, "", "龙头");
    } else {
      html =
        a(vp, "funnel-link--primary", "量价确认") +
        a(dragon, "", "龙头") +
        a(sectors, "", "成分");
    }
    return `<div class="funnel-actions">${html}</div>`;
  }

  function stockKlineLink(tsCode, stockName, tradeDate, boardCode, boardName) {
    if (!tsCode) return "—";
    const href = klineHref("stock", tsCode, tradeDate);
    const td = toApiTd(tradeDate);
    const ctx = getDecisionCtx();
    const bCode = boardCode || ctx.industry_code || "";
    const bName = boardName || ctx.industry_name || "";
    return (
      `<a href="${href}" class="funnel-link funnel-link--primary" ` +
      `data-pick-stock="${escAttr(tsCode)}" data-pick-sname="${escAttr(stockName || "")}" ` +
      `data-pick-td="${escAttr(td)}" data-pick-board="${escAttr(bCode)}" ` +
      `data-pick-bname="${escAttr(bName)}">K线选点</a>`
    );
  }

  /** 读取 URL 漏斗参数（仅 URL 有 industry_code 时自动带入；Context 条仍用 localStorage） */
  function consumeFunnelParams(options) {
    const opts = options || {};
    const params = new URLSearchParams(window.location.search);
    const code = params.get("industry_code") || "";
    const name = params.get("industry_name") || "";
    let td = params.get("trade_date") || "";
    const stock = params.get("code") || params.get("ts_code") || "";
    const kind = params.get("kind") || "";

    if (td && opts.dateEl) {
      const iso = normalizeIsoDate(td);
      if (iso) opts.dateEl.value = iso;
    } else if (!td && opts.dateEl) {
      const ctxTd = getDecisionCtx().trade_date;
      const iso = normalizeIsoDate(ctxTd);
      if (iso && !opts.dateEl.value) opts.dateEl.value = iso;
    }

    if (code) {
      setDecisionCtx({
        industry_code: code,
        industry_name: name || "",
        trade_date: toApiTd(td) || getDecisionCtx().trade_date || "",
        ts_code: "",
        stock_name: "",
      });
    }
    if (stock && kind !== "board") {
      setDecisionCtx({
        ts_code: stock,
        stock_name: params.get("name") || "",
        trade_date: toApiTd(td) || getDecisionCtx().trade_date || "",
      });
    }

    if (!code) return null;
    return {
      industry_code: code,
      industry_name: name || "",
      trade_date: toApiTd(td) || getDecisionCtx().trade_date || "",
      fromUrl: true,
    };
  }

  function renderDecisionBar() {
    // 决策链路顶栏已下线：隐藏残留节点
    const el = document.getElementById("decision-ctx-bar");
    if (el) {
      el.innerHTML = "";
      el.classList.add("hidden");
      el.style.display = "none";
    }
  }

  function bindDecisionPickClicks() {
    // 保留 data-pick-* 写入 localStorage，但不渲染链路条
    if (document.documentElement.dataset.decisionPickBound) return;
    document.documentElement.dataset.decisionPickBound = "1";
    document.addEventListener("click", (e) => {
      const stockEl = e.target.closest("[data-pick-stock]");
      if (stockEl) {
        pickStock(
          stockEl.dataset.pickStock,
          stockEl.dataset.pickSname,
          stockEl.dataset.pickTd,
          stockEl.dataset.pickBoard,
          stockEl.dataset.pickBname
        );
        return;
      }
      const boardEl = e.target.closest("[data-pick-board]");
      if (boardEl) {
        pickBoard(boardEl.dataset.pickBoard, boardEl.dataset.pickName, boardEl.dataset.pickTd);
      }
    });
  }

  function mountDecisionBar() {
    bindDecisionPickClicks();
    renderDecisionBar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountDecisionBar);
  } else {
    mountDecisionBar();
  }

  window.DcBoard = {
    fmtNum,
    fmtPct,
    apiGet,
    normalizeIsoDate,
    toApiTradeDate,
    initTradeDateCalendar,
    renderHistoryChart,
    klineHref,
    klineLink,
    getDecisionCtx,
    setDecisionCtx,
    clearDecisionCtx,
    pickBoard,
    pickStock,
    boardPageHref,
    funnelBoardLinks,
    stockKlineLink,
    consumeFunnelParams,
    renderDecisionBar,
    mountDecisionBar,
  };
})();
