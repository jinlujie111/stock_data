# 阿里云 ECS 部署指南（小程序 API + 现有 stock_data 库）

假定：**Ubuntu 22.04**、项目仓库已包含 `stock_data` 与 `wechat/industry_fund_flow/backend`，MySQL 内 **数据已就绪**。

---

## 一、阿里云控制台

1. **ECS**：2核4G，分配 **公网 IP**（或绑定 EIP）。
2. **安全组入方向**放行：**22**（SSH）、**80**、**443**。  
   - **不要**对 `0.0.0.0/0` 放行 **3306**（数据库仅本机或内网）。
3. **域名**（小程序正式环境需要）：备案域名解析到 ECS 公网 IP。
4. （可选）**RDS MySQL**：若使用 RDS，把连接串写入后端 `.env` 的 `MYSQL_HOST` 等。

---

## 二、服务器初始化

SSH 登录后：

```bash
sudo timedatectl set-timezone Asia/Shanghai
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip nginx supervisor certbot python3-certbot-nginx
```

若 MySQL 在本机且尚未安装：

```bash
sudo apt install -y mysql-server
sudo mysql_secure_installation
```

---

## 三、上传代码

**方式 A：Git**

```bash
sudo mkdir -p /opt && sudo chown $USER:$USER /opt
cd /opt
git clone <你的仓库地址> stock_data
```

**方式 B：本机打包上传**

在本机打包 `stock_data` 目录，用 SFTP/插件上传到 `/opt/stock_data`。

下文假定代码路径为：**`/opt/stock_data`**。

---

## 四、数据库（已与本地一致时）

若库已在 **阿里云 RDS** 或本机 **已导入过**，只需保证 `.env` 中账号与库名一致，**可跳过建库**。

若需在新机建空库并建表：

```bash
mysql -u root -p <<'SQL'
CREATE DATABASE IF NOT EXISTS stock_data DEFAULT CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'app'@'127.0.0.1' IDENTIFIED BY '你的强密码';
GRANT ALL ON stock_data.* TO 'app'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

mysql -uapp -p你的强密码 stock_data < /opt/stock_data/mysql_tables/schema.sql
```

再把本地数据 **mysqldump 导入** 到该库（你本地已「数据 ok」则执行导入即可）。

---

## 五、部署 FastAPI 小程序后端

```bash
cd /opt/stock_data/wechat/industry_fund_flow/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
nano .env
```

**`.env` 必改项：**

| 变量 | 说明 |
|------|------|
| `MYSQL_HOST` | 本机 `127.0.0.1` 或 RDS 内网地址 |
| `MYSQL_PORT` | 默认 `3306` |
| `MYSQL_USER` / `MYSQL_PASSWORD` | 与库一致 |
| `MYSQL_DATABASE` | `stock_data` |
| `SECRET_KEY` | 长随机串，勿泄露 |

自测（先不挂 Nginx）：

```bash
source /opt/stock_data/wechat/industry_fund_flow/backend/.venv/bin/activate
cd /opt/stock_data/wechat/industry_fund_flow/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

另开终端：

```bash
curl -s http://127.0.0.1:8000/health
# 应返回 {"status":"ok"}
```

按 `Ctrl+C` 停掉 uvicorn，下面用 **Supervisor** 常驻。

---

## 六、Supervisor 守护进程

```bash
sudo tee /etc/supervisor/conf.d/stock-api.conf <<'EOF'
[program:stock-api]
directory=/opt/stock_data/wechat/industry_fund_flow/backend
command=/opt/stock_data/wechat/industry_fund_flow/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
user=www-data
autostart=true
autorestart=true
startsecs=3
stderr_logfile=/var/log/stock-api.err.log
stdout_logfile=/var/log/stock-api.out.log
environment=PATH="/opt/stock_data/wechat/industry_fund_flow/backend/.venv/bin"
EOF

sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start stock-api
sudo supervisorctl status stock-api
```

> 若 `www-data` 无读权限，可 `sudo chown -R www-data:www-data /opt/stock_data`（按你安全策略调整）。

---

## 七、Nginx 反向代理 + HTTPS

将 **`你的域名.com`** 换成已解析到本机的备案域名。

```bash
sudo tee /etc/nginx/sites-available/stock-api <<'NGX'
server {
    listen 80;
    server_name 你的域名.com;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name 你的域名.com;
    ssl_certificate     /etc/letsencrypt/live/你的域名.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/你的域名.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
    }
}
NGX

sudo ln -sf /etc/nginx/sites-available/stock-api /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

**首次申请证书**（需 80 端口可访问、域名已解析）：

```bash
sudo certbot --nginx -d 你的域名.com
```

或先只配 80 用 `certbot certonly --webroot` 再补全上面 `ssl_certificate` 路径（以 certbot 提示为准）。

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -s https://你的域名.com/health
```

---

## 八、小程序端配置

1. 打开 `miniprogram/app.js`，设置：

   `apiBase: 'https://你的域名.com/api/v1'`

2. 微信公众平台 → 开发管理 → **服务器域名** → request 合法域名：  
   `https://你的域名.com`

3. 微信开发者工具 **上传** 代码，真机预览前确保域名为 **HTTPS** 且证书有效。

---

## 九、ETL 定时（可选，与主工程一致）

若要在云上继续跑 `run_main_python.py` 拉数：

```bash
crontab -e
# 每个交易日收盘后（示例 15:30，按你实际改）
# 30 15 * * 1-5 cd /opt/stock_data && /opt/stock_data/venv/bin/python run_main_python.py >> /var/log/stock_etl.log 2>&1
```

需自行准备 **虚拟环境** 与 **AkShare/网络** 依赖；路径按你服务器实际 `python` 与 `run_main_python.py` 调整。

---

## 十、自检清单

| 检查项 | 命令 / 操作 |
|--------|-------------|
| 本机 API | `curl http://127.0.0.1:8000/health` |
| 经域名 | `curl https://你的域名.com/health` |
| 进程 | `sudo supervisorctl status stock-api` |
| 时区 | `timedatectl` 应为 `Asia/Shanghai` |

更多通用说明见同目录 `DEPLOY.md`。
