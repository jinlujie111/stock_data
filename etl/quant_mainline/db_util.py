"""量化主线：建表、配置与交易日工具。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mysql_config import get_engine

DEFAULT_SIGNAL_THRESHOLDS: dict[str, Any] = {
    "rs_gt": 1.2,
    "a_up_3d": True,
    "z_gt_market_mult": 1.5,
    "leader_new_high": True,
    "r_le_days": 3,
    "rs_lt": 0.9,
    "a_down_2d": True,
    "leader_ash_pct": -7.0,
    "blast_gt": 0.4,
}


@dataclass
class QuantMainlineConfig:
    config_key: str = "__global__"
    content_types: tuple[str, ...] = ("行业", "概念")
    top_n: int = 3
    w_f: float = 0.2
    w_t: float = 0.2
    w_e: float = 0.2
    w_l: float = 0.2
    w_p: float = 0.2
    f_weights: dict[str, float] = field(
        default_factory=lambda: {"A": 0.4, "V": 0.3, "ETF": 0.2, "H": 0.1}
    )
    t_weights: dict[str, float] = field(
        default_factory=lambda: {"RS": 0.4, "N": 0.3, "R": 0.2, "M": 0.1}
    )
    e_weights: dict[str, float] = field(
        default_factory=lambda: {"Z": 0.35, "J": 0.25, "B": 0.2, "U": 0.2}
    )
    l_weights: dict[str, float] = field(
        default_factory=lambda: {"LR": 0.5, "LC": 0.3, "LP": 0.2}
    )
    p_weights: dict[str, float] = field(
        default_factory=lambda: {"Earnings": 0.5, "Policy": 0.3, "Forecast": 0.2}
    )
    signal_thresholds: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_THRESHOLDS)
    )
    ma_window_rank: int = 5


def parse_trade_date(s: str) -> date:
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise ValueError(f"invalid trade_date: {s}")
    return datetime.strptime(s, "%Y%m%d").date()


def get_engine_stock() -> Engine:
    return get_engine()


def _parse_json_weights(raw: Any, default: dict[str, float]) -> dict[str, float]:
    if raw is None:
        return dict(default)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return dict(default)
    if not isinstance(raw, dict):
        return dict(default)
    out = dict(default)
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def ensure_schema(engine: Engine) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS quant_mainline_config (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        config_key VARCHAR(64) NOT NULL DEFAULT '__global__' COMMENT '全局或板块代码',
        content_types VARCHAR(64) NOT NULL DEFAULT '行业,概念' COMMENT '评分板块类型,逗号分隔',
        top_n INT NOT NULL DEFAULT 3 COMMENT '主线TopN',
        w_f DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
        w_t DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
        w_e DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
        w_l DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
        w_p DECIMAL(5,4) NOT NULL DEFAULT 0.2000,
        f_weights JSON NULL,
        t_weights JSON NULL,
        e_weights JSON NULL,
        l_weights JSON NULL,
        p_weights JSON NULL,
        signal_thresholds JSON NULL,
        ma_window_rank INT NOT NULL DEFAULT 5,
        effective_date DATE NOT NULL,
        is_active TINYINT NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_quant_mainline_config (config_key, effective_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='量化主线FTELP参数';

    CREATE TABLE IF NOT EXISTS dws_dc_industry_quant_mainline_di (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        trade_date DATE NOT NULL,
        content_type VARCHAR(32) NULL,
        industry_code VARCHAR(32) NOT NULL,
        industry_name VARCHAR(128) NULL,
        score_f DECIMAL(10,2) NULL,
        score_t DECIMAL(10,2) NULL,
        score_e DECIMAL(10,2) NULL,
        score_l DECIMAL(10,2) NULL,
        score_p DECIMAL(10,2) NULL,
        main_score DECIMAL(10,2) NULL,
        main_score_ma3 DECIMAL(10,2) NULL,
        main_score_ma5 DECIMAL(10,2) NULL,
        main_score_ma10 DECIMAL(10,2) NULL,
        rank_no INT NULL,
        rank_score DECIMAL(10,2) NULL COMMENT '排序用分(默认MA5)',
        is_top3 TINYINT NOT NULL DEFAULT 0,
        amount_ratio DECIMAL(20,8) NULL,
        rs_ratio DECIMAL(10,4) NULL,
        limit_up_ratio DECIMAL(20,6) NULL,
        leader_code VARCHAR(16) NULL,
        leader_name VARCHAR(64) NULL,
        leader_pct_chg DECIMAL(10,4) NULL,
        detail_json JSON NULL,
        config_version VARCHAR(32) NULL DEFAULT '__global__',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_dc_quant_mainline (trade_date, industry_code),
        KEY idx_dc_quant_mainline_td (trade_date, content_type, is_top3)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财量化主线FTELP得分';

    CREATE TABLE IF NOT EXISTS dws_dc_industry_quant_mainline_signal_di (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        trade_date DATE NOT NULL,
        industry_code VARCHAR(32) NOT NULL,
        industry_name VARCHAR(128) NULL,
        content_type VARCHAR(32) NULL,
        signal_start TINYINT NOT NULL DEFAULT 0,
        signal_exit TINYINT NOT NULL DEFAULT 0,
        signal_status VARCHAR(16) NULL COMMENT '观察/启动/退潮',
        signal_reason JSON NULL,
        leader_code VARCHAR(16) NULL,
        leader_name VARCHAR(64) NULL,
        leader_pct_chg DECIMAL(10,4) NULL,
        config_version VARCHAR(32) NULL DEFAULT '__global__',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_dc_quant_signal (trade_date, industry_code),
        KEY idx_dc_quant_signal_td (trade_date, signal_start, signal_exit)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='东财量化主线启动退潮信号';
    """
    with engine.begin() as conn:
        for stmt in ddl.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

        cnt = conn.execute(
            text("SELECT COUNT(*) FROM quant_mainline_config WHERE config_key='__global__'")
        ).scalar()
        if not cnt:
            conn.execute(
                text(
                    """
                    INSERT INTO quant_mainline_config (
                        config_key, content_types, top_n,
                        w_f, w_t, w_e, w_l, w_p,
                        f_weights, t_weights, e_weights, l_weights, p_weights,
                        signal_thresholds, ma_window_rank, effective_date, is_active
                    ) VALUES (
                        '__global__', '行业,概念', 3,
                        0.2, 0.2, 0.2, 0.2, 0.2,
                        :f_w, :t_w, :e_w, :l_w, :p_w,
                        :sig, 5, CURDATE(), 1
                    )
                    """
                ),
                {
                    "f_w": json.dumps({"A": 0.4, "V": 0.3, "ETF": 0.2, "H": 0.1}),
                    "t_w": json.dumps({"RS": 0.4, "N": 0.3, "R": 0.2, "M": 0.1}),
                    "e_w": json.dumps({"Z": 0.35, "J": 0.25, "B": 0.2, "U": 0.2}),
                    "l_w": json.dumps({"LR": 0.5, "LC": 0.3, "LP": 0.2}),
                    "p_w": json.dumps({"Earnings": 0.5, "Policy": 0.3, "Forecast": 0.2}),
                    "sig": json.dumps(DEFAULT_SIGNAL_THRESHOLDS),
                },
            )


def load_config(engine: Engine, trade_date: date) -> QuantMainlineConfig:
    sql = """
    SELECT *
    FROM quant_mainline_config
    WHERE config_key = '__global__'
      AND is_active = 1
      AND effective_date <= :td
    ORDER BY effective_date DESC
    LIMIT 1
    """
    with engine.connect() as conn:
        row = conn.execute(text(sql), {"td": trade_date}).mappings().first()
    if not row:
        return QuantMainlineConfig()
    ctypes = tuple(x.strip() for x in str(row["content_types"]).split(",") if x.strip())
    sig = row.get("signal_thresholds")
    if isinstance(sig, str):
        try:
            sig = json.loads(sig)
        except json.JSONDecodeError:
            sig = dict(DEFAULT_SIGNAL_THRESHOLDS)
    if not isinstance(sig, dict):
        sig = dict(DEFAULT_SIGNAL_THRESHOLDS)
    return QuantMainlineConfig(
        config_key=str(row["config_key"]),
        content_types=ctypes or ("行业", "概念"),
        top_n=int(row.get("top_n") or 3),
        w_f=float(row.get("w_f") or 0.2),
        w_t=float(row.get("w_t") or 0.2),
        w_e=float(row.get("w_e") or 0.2),
        w_l=float(row.get("w_l") or 0.2),
        w_p=float(row.get("w_p") or 0.2),
        f_weights=_parse_json_weights(row.get("f_weights"), QuantMainlineConfig().f_weights),
        t_weights=_parse_json_weights(row.get("t_weights"), QuantMainlineConfig().t_weights),
        e_weights=_parse_json_weights(row.get("e_weights"), QuantMainlineConfig().e_weights),
        l_weights=_parse_json_weights(row.get("l_weights"), QuantMainlineConfig().l_weights),
        p_weights=_parse_json_weights(row.get("p_weights"), QuantMainlineConfig().p_weights),
        signal_thresholds=sig,
        ma_window_rank=int(row.get("ma_window_rank") or 5),
    )


def list_prev_trade_dates(engine: Engine, trade_date: date, limit: int = 10) -> list[date]:
    sql = """
    SELECT trade_date
    FROM ods_trading_day
    WHERE trade_date < :td
    ORDER BY trade_date DESC
    LIMIT :lim
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"td": trade_date, "lim": limit}).fetchall()
    if rows:
        return [r[0] for r in rows]
    sql2 = """
    SELECT DISTINCT trade_date
    FROM dwm_dc_industry_fund_flow_di
    WHERE trade_date < :td
    ORDER BY trade_date DESC
    LIMIT :lim
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql2), {"td": trade_date, "lim": limit}).fetchall()
    return [r[0] for r in rows]
