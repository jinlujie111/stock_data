const { request } = require('../../utils/request')
const { pct2 } = require('../../utils/format')

function decorateDetail(d) {
  if (!d || typeof d !== 'object') return d
  const out = Object.assign({}, d)
  if (Array.isArray(out.fund_trend_20d)) {
    out.fund_trend_20d = out.fund_trend_20d.map((r) =>
      Object.assign({}, r, { chg_pct: pct2(r.industry_change_pct) })
    )
  }
  if (Array.isArray(out.leaders)) {
    out.leaders = out.leaders.map((r) =>
      Object.assign({}, r, { chg_pct: pct2(r.change_pct) })
    )
  }
  return out
}

Page({
  data: { name: '', tradeDate: '', detail: null, loading: true },
  onLoad(q) {
    const name = decodeURIComponent(q.name || '')
    const tradeDate = q.trade_date ? decodeURIComponent(q.trade_date) : ''
    this.setData({ name, tradeDate })
    this.fetch(name, tradeDate)
  },
  async fetch(name, tradeDate) {
    this.setData({ loading: true })
    try {
      const params = {}
      if (tradeDate) params.trade_date = tradeDate
      const raw = await request(
        `/industry/${encodeURIComponent(name)}/detail`,
        'GET',
        params
      )
      const detail = decorateDetail(raw)
      this.setData({ detail, loading: false })
    } catch (e) {
      this.setData({ loading: false })
    }
  }
})
