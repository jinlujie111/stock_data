/**
 * 封装 wx.request：Bearer JWT、统一响应解析。
 */
const app = getApp()

function request(path, method = 'GET', data) {
  const url = `${app.globalData.apiBase}${path}`
  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method,
      data: data || {},
      header: {
        'Content-Type': 'application/json',
        Authorization: app.globalData.token ? `Bearer ${app.globalData.token}` : ''
      },
      success(res) {
        const body = res.data
        const okHttp = res.statusCode >= 200 && res.statusCode < 300
        if (okHttp && body && body.code === 0) {
          resolve(body.data)
          return
        }
        const msg =
          (body && body.message) ||
          (typeof body === 'string' ? body : '') ||
          `HTTP ${res.statusCode}`
        reject({ errMsg: msg, statusCode: res.statusCode, raw: body, url })
      },
      fail(err) {
        reject({
          errMsg: err.errMsg || String(err),
          url,
          detail: err
        })
      }
    })
  })
}

module.exports = { request }
