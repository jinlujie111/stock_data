const { request } = require('../../utils/request')
const { pct2 } = require('../../utils/format')

function formatToday() {
  const d = new Date()
  const p = (n) => (n < 10 ? '0' + n : '' + n)
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

Page({
  data: {
    panel: 'overview',
    loading: true,
    rankLoading: false,
    dash: null,
    latent: null,
    err: '',
    useServerDefault: true,
    tradeDate: '',
    dateStart: '2020-01-01',
    dateEnd: formatToday(),
    tab: 0,
    inflow: [],
    acc: [],
    exit: []
  },
  onLoad() {
    this.setData({ dateEnd: formatToday() })
  },
  onShow() {
    this.loadOverview().then(() => {
      if (this.data.panel === 'rank') this.reloadRank()
    })
  },
  onPanel(e) {
    const panel = e.currentTarget.dataset.panel
    if (panel === this.data.panel) return
    this.setData({ panel })
    if (panel === 'rank') this.reloadRank()
  },
  async onTradeDateChange(e) {
    const v = e.detail.value
    this.setData({ useServerDefault: false, tradeDate: v })
    await this.loadOverview()
    await this.reloadRank()
  },
  async loadOverview() {
    this.setData({ loading: true, err: '' })
    try {
      const params = {}
      if (!this.data.useServerDefault && this.data.tradeDate) {
        params.trade_date = this.data.tradeDate
      }
      let dash = await request('/dashboard', 'GET', params)
      if (dash && Array.isArray(dash.mainline_top10)) {
        dash = Object.assign({}, dash, {
          mainline_top10: dash.mainline_top10.map((row) =>
            Object.assign({}, row, { chg_pct: pct2(row.industry_change_pct) })
          )
        })
      }
      const latent = await request('/rank/latent', 'GET', params)
      const patch = { dash, latent, loading: false }
      if (this.data.useServerDefault && dash && dash.trade_date) {
        patch.tradeDate = dash.trade_date
      }
      this.setData(patch)
    } catch (e) {
      const hint = (e && e.errMsg) || (e && e.message) || '请求失败'
      const tip =
        '拉取失败：' +
        hint +
        '。请确认后端与 app.js 中 apiBase，并勾选不校验合法域名。'
      this.setData({ loading: false, err: tip })
    }
  },
  qp(extra) {
    const o = Object.assign({}, extra || {})
    if (this.data.tradeDate) {
      o.trade_date = this.data.tradeDate
    }
    return o
  },
  async reloadRank() {
    this.setData({ rankLoading: true })
    try {
      const [inflow, acc, exit] = await Promise.all([
        request('/rank/inflow', 'GET', this.qp({ page: 1, page_size: 50 })),
        request('/rank/accumulate', 'GET', this.qp({ days: 5 })),
        request('/rank/exit', 'GET', this.qp({}))
      ])
      this.setData({
        inflow: inflow.items || [],
        acc: acc.items || [],
        exit: exit.items || [],
        rankLoading: false
      })
    } catch (e) {
      this.setData({ rankLoading: false })
      wx.showToast({ title: '榜单加载失败', icon: 'none' })
    }
  },
  openDetail(e) {
    const name = e.currentTarget.dataset.name
    if (!name) return
    const td = this.data.tradeDate || ''
    const np = `name=${encodeURIComponent(name)}`
    const url = td
      ? `/pages/detail/detail?${np}&trade_date=${encodeURIComponent(td)}`
      : `/pages/detail/detail?${np}`
    wx.navigateTo({ url })
  },
  onChangeTab(e) {
    const tab = Number(e.currentTarget.dataset.tab)
    this.setData({ tab })
  }
})
