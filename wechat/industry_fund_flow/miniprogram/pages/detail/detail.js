const { request } = require('../../utils/request')

Page({
  data: { name: '', detail: null, loading: true },
  onLoad(q) {
    const name = decodeURIComponent(q.name || '')
    this.setData({ name })
    this.fetch(name)
  },
  async fetch(name) {
    this.setData({ loading: true })
    try {
      const detail = await request(`/industry/${encodeURIComponent(name)}/detail`)
      this.setData({ detail, loading: false })
    } catch (e) {
      this.setData({ loading: false })
    }
  }
})
