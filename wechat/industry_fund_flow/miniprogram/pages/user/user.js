const { request } = require('../../utils/request')
const app = getApp()

Page({
  data: { user: null },
  onShow() {
    this.profile()
  },
  mockLogin() {
    wx.login({
      success: async () => {
        try {
          const body = await request('/auth/wechat/login', 'POST', { code: 'dev_local_user' })
          app.globalData.token = body.token
          wx.setStorageSync('token', body.token)
          await this.profile()
          wx.showToast({ title: '登录成功' })
        } catch (e) {
          wx.showToast({ title: '登录失败', icon: 'none' })
        }
      }
    })
  },
  async profile() {
    try {
      const user = await request('/user/me')
      this.setData({ user })
    } catch (e) {
      this.setData({ user: null })
    }
  },
  logout() {
    app.globalData.token = ''
    wx.removeStorageSync('token')
    this.setData({ user: null })
  }
})
