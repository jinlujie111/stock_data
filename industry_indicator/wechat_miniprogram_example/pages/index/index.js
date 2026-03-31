/**
 * 将 API_BASE 改为你的 HTTPS 服务根地址（须在微信公众平台配置为 request 合法域名）。
 * 若服务端设置了环境变量 API_KEY，请在 header 中填写 X-Api-Key。
 */
const API_BASE = "https://你的域名或内网穿透地址";

Page({
  data: {
    rows: [],
    loading: false,
    errMsg: "",
    periodTypes: [],
    tradeDate: "",
    periodType: "",
  },

  onLoad() {
    this.fetchPeriodTypes();
    this.fetchList();
  },

  fetchPeriodTypes() {
    wx.request({
      url: `${API_BASE}/api/v1/industry-fund-flow/period-types`,
      method: "GET",
      header: this._headers(),
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.code === 0) {
          const d = res.data.data || {};
          this.setData({
            periodTypes: d.period_types || [],
            tradeDate: d.trade_date || "",
          });
        }
      },
    });
  },

  fetchList() {
    this.setData({ loading: true, errMsg: "" });
    let url = `${API_BASE}/api/v1/industry-fund-flow?limit=200`;
    const { tradeDate, periodType } = this.data;
    if (tradeDate) {
      url += `&trade_date=${encodeURIComponent(tradeDate)}`;
    }
    if (periodType) {
      url += `&period_type=${encodeURIComponent(periodType)}`;
    }
    wx.request({
      url,
      method: "GET",
      header: this._headers(),
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.code === 0) {
          this.setData({ rows: res.data.data || [] });
        } else {
          const msg =
            (res.data && res.data.message) || `HTTP ${res.statusCode}`;
          this.setData({ errMsg: msg });
        }
      },
      fail: (e) => {
        this.setData({ errMsg: e.errMsg || "网络错误" });
      },
      complete: () => {
        this.setData({ loading: false });
      },
    });
  },

  _headers() {
    const key = ""; // 若使用 API_KEY，在此填写
    const h = { "content-type": "application/json" };
    if (key) {
      h["X-Api-Key"] = key;
    }
    return h;
  },

  onPullDownRefresh() {
    this.fetchPeriodTypes();
    this.fetchList();
    wx.stopPullDownRefresh();
  },
});
