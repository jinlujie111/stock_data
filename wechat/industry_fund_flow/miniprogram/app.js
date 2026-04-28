/**
 * 全局配置：API 基址。
 *
 * 本地调试（开发者工具）：
 *   使用下面默认 http://127.0.0.1:8000/api/v1
 *   并在「详情 → 本地设置」勾选「不校验合法域名 / web-view / TLS」。
 *
 * 上线：改为 https://你的备案域名/api/v1 ，并在公众平台配置服务器域名。
 */
App({
  globalData: {
    apiBase: 'http://127.0.0.1:8000/api/v1',
    token: ''
  },
  onLaunch() {
    try {
      const t = wx.getStorageSync('token')
      if (t) this.globalData.token = t
    } catch (e) {}
  }
})
