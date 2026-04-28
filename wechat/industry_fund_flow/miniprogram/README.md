# 小程序说明

当前界面已改为 **微信原生组件 + app.wxss**，**无需** `npm install` / **构建 npm**，导入项目即可预览。

若日后重新接入 Vant：安装 `@vant/weapp` 后在开发者工具 **工具 → 构建 npm**，并在 `app.json` 配置 `usingComponents`。

1. 修改 `app.js` 中 `apiBase` 为 `https://域名/api/v1`（本地可调 `http://127.0.0.1:8000/api/v1` 并勾选不校验域名）
2. 真机调试需配置合法域名与 HTTPS 证书
