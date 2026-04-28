# 部署手册（Linux ECS 2C4G + Nginx + HTTPS + Supervisor）

## 1. 系统与依赖

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip mysql-server nginx git
sudo mysql_secure_installation
```

## 2. MySQL 8.0

```bash
sudo mysql -uroot -p <<'SQL'
CREATE DATABASE stock_data DEFAULT CHARACTER SET utf8mb4;
CREATE USER 'app'@'127.0.0.1' IDENTIFIED BY 'StrongPass!';
GRANT ALL ON stock_data.* TO 'app'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

mysql -uapp -pStrongPass! stock_data < sql/schema.sql
```

将现有 `industry_fund_flow_di` 数据导入同一库即可。

## 3. Python 虚拟环境与后端

```bash
cd /opt/industry_fund_flow/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：MYSQL_* / SECRET_KEY / WECHAT_*

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 4. Supervisor 守护

`/etc/supervisor/conf.d/industry-api.conf`：

```ini
[program:industry-api]
directory=/opt/industry_fund_flow/backend
command=/opt/industry_fund_flow/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/industry-api.err.log
stdout_logfile=/var/log/industry-api.out.log
```

```bash
sudo supervisorctl reread && sudo supervisorctl update && sudo supervisorctl start industry-api
```

## 5. Nginx 反向代理 + HTTPS（Let’s Encrypt）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
```

```bash
sudo certbot --nginx -d your-domain.com
```

## 6. Redis（可选）

```bash
sudo apt install -y redis-server
# .env REDIS_URL=redis://127.0.0.1:6379/0
```

## 7. 微信小程序上线步骤（个人主体）

1. 微信公众平台注册小程序，拿到 AppID。
2. 开发 → 开发管理 → 服务器域名：添加 `https://your-domain.com`。
3. 将 `miniprogram/project.config.json` 的 `appid` 改为正式 AppID。
4. `miniprogram/app.js` 设置 `apiBase` 为 `https://your-domain.com/api/v1`。
5. 本地执行 `npm install`，微信开发者工具：工具 → 构建 npm。
6. 上传代码 → 提交审核 → 发布。

## 8. 定时任务说明

后端内置 APScheduler：每日 **15:10**（上海时区）执行评分与市场快照。确保服务器时区：

```bash
sudo timedatectl set-timezone Asia/Shanghai
```

## 9. 一键健康检查

```bash
curl -s https://your-domain.com/health
```
