const { request } = require('../../utils/request')

Page({
  data: { tab: 0, inflow: [], acc: [], exit: [], loading: true },
  onLoad() { this.reload() },
  onChangeTab(e) {
    const tab = Number(e.currentTarget.dataset.tab)
    this.setData({ tab })
  },
  async reload() {
    this.setData({ loading: true })
    try {
      const [inflow, acc, exit] = await Promise.all([
        request('/rank/inflow?page=1&page_size=50'),
        request('/rank/accumulate?days=5'),
        request('/rank/exit')
      ])
      this.setData({ inflow: inflow.items || [], acc: acc.items || [], exit: exit.items || [], loading: false })
    } catch (e) {
      this.setData({ loading: false })
      wx.showToast({ title: '加载失败', icon: 'none' })
    }
  },
  openDetail(e) {
    const name = e.currentTarget.dataset.name
    wx.navigateTo({ url: `/pages/detail/detail?name=${encodeURIComponent(name)}` })
  }
})
