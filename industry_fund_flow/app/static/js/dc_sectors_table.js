/** 行业板块表格：排序与渲染（行业板块 / 板块自选共用） */
(function () {
  const fmtNum =
    window.DcBoard && window.DcBoard.fmtNum
      ? window.DcBoard.fmtNum
      : function (v, d) {
          if (v === null || v === undefined || v === "") return "—";
          const n = Number(v);
          if (Number.isNaN(n)) return v;
          return n.toFixed(d === undefined ? 1 : d);
        };

  const SORT_COLUMNS = [
    { key: "pct_change", label: "涨幅" },
    { key: "net_amount_yi", label: "资金流入" },
    { key: "board_amount_yi", label: "成交额" },
    { key: "turnover_rate", label: "换手" },
    { key: "up_down", label: "上涨/下跌" },
    { key: "limit_up_cnt", label: "涨停数" },
    { key: "total_mv_yi", label: "流通市值" },
  ];

  const DEFAULT_SORT = { key: "pct_change", dir: "desc" };

  function cellClass(v) {
    const n = Number(v);
    if (Number.isNaN(n) || v === null || v === "") return "";
    return n > 0 ? "cell-rise" : n < 0 ? "cell-fall" : "";
  }

  function fmtPctCell(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return n.toFixed(2) + "%";
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

  function sortValue(row, key) {
    if (key === "up_down") {
      const up = row.up_num;
      const down = row.down_num;
      if (up == null && down == null) return null;
      return Number(up ?? 0);
    }
    return row[key];
  }

  function compareRows(a, b, key, dir) {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
    const aNull = va === null || va === undefined || va === "";
    const bNull = vb === null || vb === undefined || vb === "";
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    const na = Number(va);
    const nb = Number(vb);
    const cmp = Number.isNaN(na) || Number.isNaN(nb) ? String(va).localeCompare(String(vb)) : na - nb;
    return dir === "asc" ? cmp : -cmp;
  }

  function sortItems(items, sortKey, sortDir) {
    return [...items].sort((a, b) => compareRows(a, b, sortKey, sortDir));
  }

  function sortColumnLabel(key) {
    const col = SORT_COLUMNS.find((c) => c.key === key);
    return col ? col.label : key;
  }

  function renderTableHead(theadRow, sortKey, sortDir) {
    const sortHeaders = SORT_COLUMNS.map((c) => {
      const active = c.key === sortKey;
      const arrow = active ? (sortDir === "asc" ? " ▲" : " ▼") : "";
      return `<th class="sortable-th" data-key="${c.key}" title="点击排序">${c.label}${arrow}</th>`;
    }).join("");
    theadRow.innerHTML = `<th>名称</th>${sortHeaders}<th>板块龙头</th><th>操作</th>`;
  }

  function bindSortHeaders(theadEl, state, onChange) {
    if (theadEl.dataset.sortBound) return;
    theadEl.dataset.sortBound = "1";
    theadEl.addEventListener("click", (e) => {
      const th = e.target.closest(".sortable-th");
      if (!th) return;
      const key = th.dataset.key;
      if (!key) return;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = "desc";
      }
      onChange();
    });
  }

  function renderTableBody(tbodyEl, items, opts) {
    const boardFavCodes = opts.boardFavCodes || new Set();
    const showMembers = opts.showMembers !== false;
    if (!items.length) {
      tbodyEl.innerHTML = "";
      return;
    }
    tbodyEl.innerHTML = items
      .map((row) => {
        const isFav = boardFavCodes.has(row.industry_code);
        const membersBtn = showMembers
          ? `<button type="button" class="btn btn-ghost btn-sm" data-action="members" data-code="${row.industry_code}" data-name="${row.industry_name || ""}">成分</button>`
          : "";
        return `
      <tr data-code="${row.industry_code}">
        <td>
          <button type="button" class="star-btn${isFav ? " is-fav" : ""}" data-action="fav-board" data-code="${row.industry_code}" data-name="${row.industry_name || ""}" data-ct="${row.content_type || ""}" title="加入板块自选">★</button>
          <span class="sector-name">${row.industry_name || "—"}</span>
        </td>
        <td class="${cellClass(row.pct_change)}">${fmtPctCell(row.pct_change)}</td>
        <td class="${cellClass(row.net_amount_yi)}">${row.net_amount_yi != null ? fmtYi(row.net_amount_yi) : "—"}</td>
        <td>${row.board_amount_yi != null ? fmtYi(row.board_amount_yi) : "—"}</td>
        <td>${row.turnover_rate != null ? fmtNum(row.turnover_rate, 2) + "%" : "—"}</td>
        <td>${row.up_num ?? "—"} / ${row.down_num ?? "—"}</td>
        <td>${row.limit_up_cnt ?? "—"}</td>
        <td>${row.total_mv_yi != null ? fmtYi(row.total_mv_yi, 0) : "—"}</td>
        <td>${leaderText(row)}</td>
        <td>${membersBtn}</td>
      </tr>`;
      })
      .join("");
  }

  function toolbarText(data, sortKey, sortDir, count) {
    const n = count != null ? count : (data.items || []).length;
    const order = sortDir === "asc" ? "升序" : "降序";
    return `交易日 ${data.trade_date} · ${data.content_type} · 按${sortColumnLabel(sortKey)}${order} · ${n} 条`;
  }

  window.DcSectorTable = {
    SORT_COLUMNS,
    DEFAULT_SORT,
    cellClass,
    fmtPctCell,
    fmtYi,
    leaderText,
    sortItems,
    renderTableHead,
    bindSortHeaders,
    renderTableBody,
    toolbarText,
  };
})();
