"""市场/板块情绪评分与历史曲线；大盘情绪为六维加权，并输出市场状态。"""
from __future__ import annotations

from typing import Any

from app.db import fetch_all_stock, fetch_one_stock
from app.dc_query_util import (
    latest_trade_date_from_table,
    list_trade_dates_from_table,
    resolve_trade_date,
    serialize_row,
)

MARKET_TABLE = "dwm_market_breadth_di"
FUND_TABLE = "dwm_dc_industry_fund_flow_di"
HEAT_TABLE = "dwm_dc_industry_market_heat_di"
MONITOR_TABLE = "dws_dc_industry_mainline_monitor_di"
DRAGON_TABLE = "dwm_sector_dragon_summary_di"
LIMIT_TABLE = "ods_limit_list_di"
INDEX_TABLE = "ods_index_daily_di"
HSGT_TABLE = "ods_moneyflow_hsgt_di"

DEFAULT_CONTENT_TYPES = ("行业", "概念")

# 趋势/量能计算需要额外回看交易日
_LOOKBACK_EXTRA = 130

REGIME_LABELS = {
    "broad_bull": "全面牛市",
    "structural_bull": "结构性牛市",
    "range": "震荡市",
    "bear": "熊市",
}


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(FUND_TABLE, fallback_table=MARKET_TABLE)


def list_trade_dates(limit: int = 90) -> list[str]:
    dates = list_trade_dates_from_table(FUND_TABLE, limit)
    if dates:
        return dates
    return list_trade_dates_from_table(MARKET_TABLE, limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=FUND_TABLE,
        fallback_table=MARKET_TABLE,
        empty_msg="暂无情绪数据，请先准备市场广度与板块行情数据",
    )


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _scale(value: float | None, lo: float, hi: float) -> float:
    if value is None:
        return 50.0
    if hi <= lo:
        return 50.0
    return _clamp((value - lo) * 100.0 / (hi - lo))


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 <= x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def _weighted_renorm(parts: list[tuple[float | None, float]]) -> float | None:
    """缺维（子分为 None）剔除后，按剩余权重重归一化的加权分。

    parts: [(子分, 权重), ...]。全部缺失时返回 None。
    这样可避免“缺数填 50 仍占权重”造成的虚假中性拉平。
    """
    used = [(s, w) for s, w in parts if s is not None and w > 0]
    total_w = sum(w for _, w in used)
    if total_w <= 0:
        return None
    return round(sum(s * w for s, w in used) / total_w, 2)


def _volume_score(vol_ratio: float | None, index_pct: float | None) -> float | None:
    """成交活跃度：成交额相对 20 日均的分段映射；大跌放量做恐慌折扣。

    口径说明：
    - vol_ratio 的分母/分子来自上证+深证指数成交额（近似全 A，非严格全 A）；
    - 恐慌折扣分支用的 index_pct 是沪深300(hs300)涨跌幅，与量比基准指数不完全一致，
      仅作“大跌放量偏出货”的定性折扣，不追求口径严格对齐。
    - 缺失（vol_ratio 为 None）时返回 None，交由上层按剩余权重重归一化（不再默认给 50）。
    """
    if vol_ratio is None:
        return None
    r = max(0.0, vol_ratio)
    if r <= 0.7:
        score = _lerp(r, 0.0, 0.7, 10.0, 25.0)
    elif r <= 1.0:
        score = _lerp(r, 0.7, 1.0, 25.0, 50.0)
    elif r <= 1.3:
        score = _lerp(r, 1.0, 1.3, 50.0, 70.0)
    elif r <= 1.6:
        score = _lerp(r, 1.3, 1.6, 70.0, 85.0)
    elif r <= 2.0:
        score = _lerp(r, 1.6, 2.0, 85.0, 100.0)
    else:
        score = 100.0

    # 大跌放量偏恐慌出货，避免成交额把情绪分托上去
    if index_pct is not None and index_pct <= -1.5 and r >= 1.2:
        score = score * 0.65 + 35.0 * 0.35
    return _clamp(score)


def _limit_up_score(limit_up: float, blast: float) -> tuple[float, float, float]:
    count_score = min(100.0, (limit_up / 120.0) * 100.0)
    denom = limit_up + blast
    if denom <= 0:
        seal_score = 50.0
        blast_rate = None
    else:
        blast_rate = blast / denom
        seal_score = 100.0 * (1.0 - blast_rate)
    score = count_score * 0.60 + seal_score * 0.40
    return _clamp(score), count_score, seal_score


def _board_height_score(max_boards: float | None) -> float:
    if max_boards is None or max_boards <= 0:
        return 15.0
    n = int(max_boards)
    mapping = {1: 25.0, 2: 45.0, 3: 60.0, 4: 75.0, 5: 88.0}
    if n >= 6:
        return 100.0
    return mapping.get(n, 25.0)


def _consecutive_score(
    max_boards: float | None,
    continue_cnt: float,
    limit_up: float,
    limit_down: float,
) -> tuple[float, dict[str, float]]:
    height = _board_height_score(max_boards)
    # continue_cnt = 当日 limit=U 且 limit_times>=2 的家数（即“多连板家数”），
    # 并非“昨涨停今晋级”口径；cont_ratio 表示多连板家数占当日涨停家数之比。
    cont_ratio = (continue_cnt / limit_up) if limit_up > 0 else 0.0
    cont_score = _clamp(cont_ratio * 100.0 / 0.35)  # 多连板家数占比约 35% 视为满分
    down_score = 100.0 - _scale(limit_down, 0.0, 80.0)
    score = height * 0.40 + cont_score * 0.30 + down_score * 0.30
    return _clamp(score), {
        "height_score": round(height, 2),
        "continue_score": round(cont_score, 2),
        "limit_down_control_score": round(down_score, 2),
        "max_boards": float(max_boards or 0),
        # 命名保留 continue_ratio 以兼容前端；实际口径为“多连板家数占比”
        "continue_ratio": round(cont_ratio, 4),
    }


def _capital_score(north_money: float | None) -> float | None:
    """北向资金（百万元）：约 ±150 亿映射到 0–100。

    2024-08 起北向资金常停更/为 NULL；缺失时返回 None，
    由上层将该维从加权中剔除并对其余维度按权重重归一化（不再默认给 50 占权重）。
    """
    if north_money is None:
        return None
    return _clamp(50.0 + (north_money / 15000.0) * 50.0)


def _trend_score(close: float | None, ma20: float | None, ma60: float | None, ma120: float | None) -> float | None:
    # 收盘缺失或所有均线均缺失时返回 None（缺维），由上层重归一化
    if close is None:
        return None
    score = 0.0
    weighed = 0.0
    if ma20 is not None:
        score += 40.0 if close > ma20 else 0.0
        weighed += 40.0
    if ma60 is not None:
        score += 30.0 if close > ma60 else 0.0
        weighed += 30.0
    if ma120 is not None:
        score += 30.0 if close > ma120 else 0.0
        weighed += 30.0
    if weighed <= 0:
        return None
    # 均线不足时按已有权重归一
    return _clamp(score * 100.0 / weighed)


def _sma(values: list[float | None], end_idx: int, window: int) -> float | None:
    if end_idx < 0 or window <= 0:
        return None
    start = end_idx - window + 1
    if start < 0:
        return None
    chunk = values[start : end_idx + 1]
    nums = [v for v in chunk if v is not None]
    if len(nums) < window:
        return None
    return sum(nums) / len(nums)


def _market_sentiment_score(ctx: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """
    大盘情绪六维（满权重）：
      0.25×Breadth + 0.20×LimitUp + 0.20×Volume
      + 0.15×Trend + 0.10×Capital + 0.10×连板

    统一缺维处理：任一维缺失（子分为 None）则从加权中剔除，
    并对剩余维度按其权重重归一化，避免缺数默认 50 占权重拉平真实情绪。
    区分 missing（None，不计入且 UI 显示“—”）与 neutral（真实中性 50）。
    """
    total_cnt = max(_num(ctx.get("total_cnt")) or 0.0, 1.0)
    # 广度维：仅当 advance_ratio 与 advance_cnt 均缺失时才算缺维（不再用 or 0.5 偏乐观）
    advance_ratio = _num(ctx.get("advance_ratio"))
    if advance_ratio is None:
        advance_cnt = _num(ctx.get("advance_cnt"))
        advance_ratio = (advance_cnt / total_cnt) if advance_cnt is not None else None
    elif advance_ratio > 1:
        advance_ratio = advance_ratio / 100.0

    limit_up = _num(ctx.get("limit_up_cnt")) or 0.0
    limit_down = _num(ctx.get("limit_down_cnt")) or 0.0
    blast_cnt = _num(ctx.get("blast_cnt")) or 0.0
    max_boards = _num(ctx.get("max_boards"))
    continue_cnt = _num(ctx.get("continue_cnt")) or 0.0

    breadth_score = _clamp(advance_ratio * 100.0) if advance_ratio is not None else None
    limit_score, limit_count_score, seal_score = _limit_up_score(limit_up, blast_cnt)
    volume_score = _volume_score(_num(ctx.get("vol_ratio")), _num(ctx.get("index_pct")))
    trend_score = _trend_score(
        _num(ctx.get("index_close")),
        _num(ctx.get("ma20")),
        _num(ctx.get("ma60")),
        _num(ctx.get("ma120")),
    )
    # 北向资金停更/NULL 时 capital_score=None，被剔除并重归一化
    capital_score = _capital_score(_num(ctx.get("north_money")))
    consecutive_score, consecutive_detail = _consecutive_score(
        max_boards, continue_cnt, limit_up, limit_down
    )

    score = _weighted_renorm(
        [
            (breadth_score, 0.25),
            (limit_score, 0.20),
            (volume_score, 0.20),
            (trend_score, 0.15),
            (capital_score, 0.10),
            (consecutive_score, 0.10),
        ]
    )
    # 缺维子分对外返回 None（前端显示“—”），不再伪装成 50
    detail = {
        "breadth_score": round(breadth_score, 2) if breadth_score is not None else None,
        "limit_up_score": round(limit_score, 2),
        "limit_count_score": round(limit_count_score, 2),
        "seal_score": round(seal_score, 2),
        "volume_score": round(volume_score, 2) if volume_score is not None else None,
        "vol_ratio": round(_num(ctx.get("vol_ratio")), 4) if _num(ctx.get("vol_ratio")) is not None else None,
        "trend_score": round(trend_score, 2) if trend_score is not None else None,
        "capital_score": round(capital_score, 2) if capital_score is not None else None,
        "consecutive_score": round(consecutive_score, 2),
        **consecutive_detail,
    }
    return score, detail


def _classify_regime(
    *,
    close: float | None,
    ma60: float | None,
    ma120: float | None,
    ret_60: float | None,
    ret_20: float | None,
    avg_advance_20: float | None,
) -> dict[str, Any]:
    """
    慢变量市场状态（规则型标签，非模型预测）：全面牛 / 结构牛 / 震荡 / 熊。
    - 趋势：相对 MA60/MA120 与 60 日收益
    - 广度：近 20 日平均上涨占比
    - 结构：指数偏强但广度偏弱 → 结构性牛市

    口径修正：
    - 多空条件对称：ret_60 缺失时对多/空一视同仁（原先多头宽松、空头严格）；
    - 缺广度时降级为“震荡”而非直接判熊，避免过度悲观。
    """
    metrics = {
        "avg_advance_ratio_20d": None if avg_advance_20 is None else round(avg_advance_20, 4),
        "index_return_20d": None if ret_20 is None else round(ret_20, 4),
        "index_return_60d": None if ret_60 is None else round(ret_60, 4),
        "above_ma60": bool(close is not None and ma60 is not None and close > ma60),
        "above_ma120": bool(close is not None and ma120 is not None and close > ma120),
    }

    breadth = avg_advance_20
    # ret_60 缺失时多空对称处理：均按“不否决”看待（None 不构成反向证据）
    bullish_trend = (
        close is not None
        and ma60 is not None
        and close > ma60
        and (ret_60 is None or ret_60 > 0)
    )
    bearish_trend = (
        close is not None
        and ma60 is not None
        and close < ma60
        and (ret_60 is None or ret_60 < 0)
    )

    if bullish_trend and breadth is not None:
        if breadth >= 0.55:
            code = "broad_bull"
        else:
            # 指数趋势向上但赚钱面不够宽 → 结构牛
            code = "structural_bull"
    elif bearish_trend and breadth is not None:
        if breadth < 0.45:
            code = "bear"
        else:
            code = "range"
    elif bullish_trend:
        # 缺广度时：有上行趋势暂判结构牛（宁可不叫全面牛）
        code = "structural_bull"
    elif bearish_trend:
        # 缺广度 + 下行趋势：降级为震荡而非直接判熊（避免过度悲观）
        code = "range"
    else:
        # 均线纠缠 / 方向不明
        if (
            breadth is not None
            and ret_20 is not None
            and ret_20 > 0.01
            and breadth < 0.50
            and close is not None
            and ma60 is not None
            and close >= ma60 * 0.98
        ):
            code = "structural_bull"
        else:
            code = "range"

    return {
        "code": code,
        "label": REGIME_LABELS.get(code, code),
        "note": "规则型标签，非模型预测；缺广度时倾向震荡",
        "metrics": metrics,
    }


def _fetch_market_enrichment(trade_date: str, limit: int) -> dict[str, dict[str, Any]]:
    """按交易日合并：涨停炸板、指数量价、北向资金。"""
    by_date: dict[str, dict[str, Any]] = {}

    limit_rows = fetch_all_stock(
        f"""
        SELECT
            trade_date,
            SUM(CASE WHEN `limit` = 'U' THEN 1 ELSE 0 END) AS limit_up_cnt,
            SUM(CASE WHEN `limit` = 'D' THEN 1 ELSE 0 END) AS limit_down_cnt,
            SUM(CASE WHEN `limit` = 'Z' THEN 1 ELSE 0 END) AS blast_cnt,
            MAX(CASE WHEN `limit` = 'U' THEN limit_times ELSE NULL END) AS max_boards,
            SUM(CASE WHEN `limit` = 'U' AND IFNULL(limit_times, 0) >= 2 THEN 1 ELSE 0 END) AS continue_cnt
        FROM {LIMIT_TABLE}
        WHERE trade_date <= :trade_date
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT {limit}
        """,
        {"trade_date": trade_date},
    )
    for raw in limit_rows:
        row = serialize_row(raw)
        td = row.get("trade_date")
        if not td:
            continue
        by_date.setdefault(td, {}).update(
            {
                "blast_cnt": _num(row.get("blast_cnt")) or 0.0,
                "max_boards": _num(row.get("max_boards")),
                "continue_cnt": _num(row.get("continue_cnt")) or 0.0,
                "limit_up_from_list": _num(row.get("limit_up_cnt")),
                "limit_down_from_list": _num(row.get("limit_down_cnt")),
            }
        )

    index_rows = fetch_all_stock(
        f"""
        SELECT
            trade_date,
            SUM(CASE WHEN ts_code IN ('000001.SH', '399001.SZ') THEN amount ELSE 0 END) AS mkt_amount,
            MAX(CASE WHEN ts_code = '000300.SH' THEN amount END) AS hs300_amount,
            MAX(CASE WHEN ts_code = '000300.SH' THEN close END) AS hs300_close,
            MAX(CASE WHEN ts_code = '000300.SH' THEN pct_chg END) AS hs300_pct
        FROM {INDEX_TABLE}
        WHERE trade_date <= :trade_date
          AND ts_code IN ('000001.SH', '399001.SZ', '000300.SH')
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT {limit}
        """,
        {"trade_date": trade_date},
    )
    for raw in index_rows:
        row = serialize_row(raw)
        td = row.get("trade_date")
        if not td:
            continue
        mkt_amount = _num(row.get("mkt_amount")) or 0.0
        if mkt_amount <= 0:
            mkt_amount = _num(row.get("hs300_amount"))
        by_date.setdefault(td, {}).update(
            {
                "mkt_amount": mkt_amount,
                "index_close": _num(row.get("hs300_close")),
                "index_pct": _num(row.get("hs300_pct")),
            }
        )

    hsgt_rows = fetch_all_stock(
        f"""
        SELECT trade_date, north_money
        FROM {HSGT_TABLE}
        WHERE trade_date <= :trade_date
        ORDER BY trade_date DESC
        LIMIT {limit}
        """,
        {"trade_date": trade_date},
    )
    for raw in hsgt_rows:
        row = serialize_row(raw)
        td = row.get("trade_date")
        if not td:
            continue
        by_date.setdefault(td, {})["north_money"] = _num(row.get("north_money"))

    return by_date


def _sector_sentiment_score(row: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """板块情绪七维；与大盘一致：缺维（子分 None）剔除后按剩余权重重归一化。"""
    pct_change = _num(row.get("pct_change"))
    up_ratio = _num(row.get("up_ratio"))
    if up_ratio is not None and up_ratio > 1:
        up_ratio = up_ratio / 100.0
    limit_up_ratio = _num(row.get("limit_up_ratio"))
    if limit_up_ratio is not None and limit_up_ratio > 1:
        limit_up_ratio = limit_up_ratio / 100.0
    net_amount_rate = _num(row.get("net_amount_rate"))
    turnover_rate = _num(row.get("turnover_rate"))
    main_score = _num(row.get("main_score"))
    leader_name = (row.get("leader_composite_name") or "").strip()

    price_score = _scale(pct_change, -6.0, 6.0) if pct_change is not None else None
    # up_ratio 缺失（热度表无行）→ 视为缺维（None），而非 0 或乐观 0.5
    breadth_score = _clamp(up_ratio * 100.0) if up_ratio is not None else None
    limit_score = _scale(limit_up_ratio, 0.0, 0.08) if limit_up_ratio is not None else None
    fund_score = _scale(net_amount_rate, -5.0, 5.0) if net_amount_rate is not None else None
    turnover_score = _scale(turnover_rate, 1.0, 8.0) if turnover_rate is not None else None
    mainline_score = _scale(main_score, 20.0, 100.0) if main_score is not None else None
    # leader_score 目前是二元 100/40（有龙头/无龙头），存在跳变抖动；
    # 无 leader_composite_name 字段支撑连续化，暂保留二元并标注
    leader_score = 100.0 if leader_name else 40.0

    score = _weighted_renorm(
        [
            (price_score, 0.20),
            (breadth_score, 0.20),
            (limit_score, 0.15),
            (fund_score, 0.15),
            (turnover_score, 0.10),
            (mainline_score, 0.12),
            (leader_score, 0.08),
        ]
    )
    return score, {
        "price_score": round(price_score, 2) if price_score is not None else None,
        "breadth_score": round(breadth_score, 2) if breadth_score is not None else None,
        "limit_score": round(limit_score, 2) if limit_score is not None else None,
        "fund_score": round(fund_score, 2) if fund_score is not None else None,
        "turnover_score": round(turnover_score, 2) if turnover_score is not None else None,
        "mainline_score": round(mainline_score, 2) if mainline_score is not None else None,
        "leader_score": round(leader_score, 2),
    }


def _latest_board_header(industry_code: str, end_trade_date: str) -> dict[str, Any] | None:
    row = fetch_one_stock(
        f"""
        SELECT industry_code, industry_name, content_type
        FROM {FUND_TABLE}
        WHERE industry_code = :industry_code
          AND trade_date <= :trade_date
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        {"industry_code": industry_code, "trade_date": end_trade_date},
    )
    return serialize_row(row) if row else None


def resolve_board(industry_code: str | None, keyword: str | None, trade_date: str | None = None) -> dict[str, Any] | None:
    td = _resolve_trade_date(trade_date)
    if industry_code and industry_code.strip():
        return _latest_board_header(industry_code.strip(), td)

    kw = (keyword or "").strip()
    if kw:
        row = fetch_one_stock(
            f"""
            SELECT industry_code, industry_name, content_type
            FROM {FUND_TABLE}
            WHERE trade_date = :trade_date
              AND content_type IN ('行业', '概念')
              AND (industry_name LIKE :kw OR industry_code LIKE :kw)
            ORDER BY pct_change DESC, industry_name
            LIMIT 1
            """,
            {"trade_date": td, "kw": f"%{kw}%"},
        )
        return serialize_row(row) if row else None

    row = fetch_one_stock(
        f"""
        SELECT industry_code, industry_name, content_type
        FROM {FUND_TABLE}
        WHERE trade_date = :trade_date
          AND content_type IN ('行业', '概念')
        ORDER BY pct_change DESC, net_amount DESC, industry_name
        LIMIT 1
        """,
        {"trade_date": td},
    )
    return serialize_row(row) if row else None


def _build_market_series(trade_date: str, days: int) -> list[dict[str, Any]]:
    fetch_n = days + _LOOKBACK_EXTRA
    market_rows = fetch_all_stock(
        f"""
        SELECT trade_date, total_cnt, advance_cnt, decline_cnt, flat_cnt, advance_ratio,
               limit_up_cnt, limit_down_cnt
        FROM {MARKET_TABLE}
        WHERE trade_date <= :trade_date
        ORDER BY trade_date DESC
        LIMIT {fetch_n}
        """,
        {"trade_date": trade_date},
    )
    enrichment = _fetch_market_enrichment(trade_date, fetch_n)

    chron = [serialize_row(r) for r in reversed(market_rows)]
    closes: list[float | None] = []
    amounts: list[float | None] = []
    advances: list[float | None] = []

    for row in chron:
        td = row["trade_date"]
        extra = enrichment.get(td, {})
        closes.append(extra.get("index_close"))
        amounts.append(extra.get("mkt_amount"))
        ar = _num(row.get("advance_ratio"))
        if ar is None:
            total = max(_num(row.get("total_cnt")) or 0.0, 1.0)
            ar = (_num(row.get("advance_cnt")) or 0.0) / total
        elif ar > 1:
            ar = ar / 100.0
        advances.append(ar)

    items: list[dict[str, Any]] = []
    for i, row in enumerate(chron):
        td = row["trade_date"]
        extra = enrichment.get(td, {})
        ma20 = _sma(closes, i, 20)
        ma60 = _sma(closes, i, 60)
        ma120 = _sma(closes, i, 120)
        amt_ma20 = _sma(amounts, i, 20)
        today_amt = amounts[i]
        vol_ratio = None
        if today_amt is not None and amt_ma20 and amt_ma20 > 0:
            vol_ratio = today_amt / amt_ma20

        close = closes[i]
        ret_20 = None
        ret_60 = None
        if close is not None and i >= 20 and closes[i - 20] not in (None, 0):
            ret_20 = close / closes[i - 20] - 1.0
        if close is not None and i >= 60 and closes[i - 60] not in (None, 0):
            ret_60 = close / closes[i - 60] - 1.0

        avg_adv_20 = None
        if i >= 19:
            window = [a for a in advances[i - 19 : i + 1] if a is not None]
            if len(window) >= 15:
                avg_adv_20 = sum(window) / len(window)

        # 涨跌停家数优先取 DWM 广度表；当 DWM 为 None 或 0（常见于口径缺失/未回填）
        # 且 ods_limit_list 有非零值时回退到 list，避免 DWM=0 导致封板率失真
        limit_up = _num(row.get("limit_up_cnt"))
        limit_up_list = extra.get("limit_up_from_list")
        if (limit_up is None or limit_up == 0) and limit_up_list:
            limit_up = limit_up_list
        elif limit_up is None:
            limit_up = 0.0
        limit_down = _num(row.get("limit_down_cnt"))
        limit_down_list = extra.get("limit_down_from_list")
        if (limit_down is None or limit_down == 0) and limit_down_list:
            limit_down = limit_down_list
        elif limit_down is None:
            limit_down = 0.0

        ctx = {
            **row,
            "limit_up_cnt": limit_up,
            "limit_down_cnt": limit_down,
            "blast_cnt": extra.get("blast_cnt") or 0.0,
            "max_boards": extra.get("max_boards"),
            "continue_cnt": extra.get("continue_cnt") or 0.0,
            "vol_ratio": vol_ratio,
            "index_pct": extra.get("index_pct"),
            "index_close": close,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
            "north_money": extra.get("north_money"),
        }
        score, detail = _market_sentiment_score(ctx)
        regime = _classify_regime(
            close=close,
            ma60=ma60,
            ma120=ma120,
            ret_60=ret_60,
            ret_20=ret_20,
            avg_advance_20=avg_adv_20,
        )
        items.append({**row, "score": score, "detail": detail, "regime": regime})

    # 仅返回请求的 days（尾部）
    if len(items) > days:
        items = items[-days:]
    return items


def get_sentiment_history(
    industry_code: str | None = None,
    *,
    keyword: str | None = None,
    trade_date: str | None = None,
    days: int = 365,
) -> dict[str, Any]:
    td = _resolve_trade_date(trade_date)
    days = max(30, min(days, 365))
    board = resolve_board(industry_code, keyword, td)

    market_items = _build_market_series(td, days)

    sector_items: list[dict[str, Any]] = []
    if board:
        sector_rows = fetch_all_stock(
            f"""
            SELECT
                ff.trade_date, ff.industry_code, ff.industry_name, ff.content_type,
                ff.pct_change, ff.net_amount, ff.net_amount_rate, ff.board_amount,
                -- 热度表缺行时 up_ratio 保持 NULL（视为缺维，不再 COALESCE 成 0 拉低广度分）
                mh.up_ratio AS up_ratio,
                COALESCE(mh.limit_up_ratio, 0) AS limit_up_ratio,
                COALESCE(mh.limit_up_cnt, 0) AS limit_up_cnt,
                COALESCE(daily.turnover_rate, idx.turnover_rate, mh.turnover_rate) AS turnover_rate,
                m.main_score,
                d.leader_composite_name
            FROM {FUND_TABLE} ff
            LEFT JOIN {HEAT_TABLE} mh
              ON mh.trade_date = ff.trade_date AND mh.industry_code = ff.industry_code
            LEFT JOIN ods_dc_daily_di daily
              ON daily.trade_date = ff.trade_date AND daily.ts_code = ff.industry_code
            LEFT JOIN ods_dc_index_di idx
              ON idx.trade_date = ff.trade_date AND idx.ts_code = ff.industry_code
            LEFT JOIN {MONITOR_TABLE} m
              ON m.trade_date = ff.trade_date AND m.industry_code = ff.industry_code
            LEFT JOIN {DRAGON_TABLE} d
              ON d.trade_date = ff.trade_date
             AND d.industry_code = ff.industry_code
             AND d.score_mode = 'mvp'
            WHERE ff.industry_code = :industry_code
              AND ff.trade_date <= :trade_date
            ORDER BY ff.trade_date DESC
            LIMIT {days}
            """,
            {"industry_code": board["industry_code"], "trade_date": td},
        )
        for raw in reversed(sector_rows):
            row = serialize_row(raw)
            score, detail = _sector_sentiment_score(row)
            sector_items.append({**row, "score": score, "detail": detail})

    latest_market = market_items[-1] if market_items else None
    latest_sector = sector_items[-1] if sector_items else None
    return {
        "trade_date": td,
        "days": days,
        "board": board,
        "market": {
            "label": "大盘情绪",
            "latest_score": latest_market["score"] if latest_market else None,
            "latest_detail": latest_market.get("detail") if latest_market else None,
            "regime": latest_market.get("regime") if latest_market else None,
            "items": market_items,
        },
        "sector": {
            "label": "板块情绪",
            "latest_score": latest_sector["score"] if latest_sector else None,
            "items": sector_items,
        },
    }
