const { request } = require('../../utils/request')

Page({
  data: {
    loading: true,
    dash: null,
    latent: null,
    err: ''
  },
  onShow() {
    this.load()
  },
  async load() {
    this.setData({ loading: true, err: '' })
    try {
      const dash = await request('/dashboard')
      const latent = await request('/rank/latent')
      this.setData({ dash, latent, loading: false })
    } catch (e) {
      const hint =
        (e && e.errMsg) ||
        (e && e.message) ||
        '请求失败'
      const tip =
        '拉取失败：' +
        hint +
        '。请确认：1) 后端已启动 uvicorn 8000 端口；2) app.js 中 apiBase 指向该地址；3) 开发者工具已勾选「不校验合法域名」。'
      this.setData({ loading: false, err: tip })
    }
  },
  goRank() { wx.navigateTo({ url: '/pages/rank/rank' }) },
  goVip() { wx.navigateTo({ url: '/pages/vip/vip' }) }
})
