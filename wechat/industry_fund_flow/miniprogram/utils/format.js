/**
 * 涨跌幅等百分比展示：固定保留两位小数（与常见行情展示一致）。
 */
function pct2(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  return n.toFixed(2)
}

module.exports = { pct2 }
