"""用途：全局配置，支持环境变量覆盖。"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "industry-fund-flow-api"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    # 与主工程 industry_indicator/config 一致；勿在仓库提交真实生产密码。务必用 .env 或环境变量覆盖。
    mysql_password: str = "jinlujie"
    mysql_database: str = "stock_data"

    redis_url: str | None = None

    period_instant: str = "即时"

    wechat_appid: str = ""
    wechat_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
