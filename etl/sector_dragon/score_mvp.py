"""单板块 MVP 四因子评分。"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.sector_dragon.db_util import DragonConfig, list_trading_days, load_members
from etl.sector_dragon.scoring import (
    build_summary_text,
    composite_mvp,
    detail_json,
    mark_leader,
    percentile_score,
    rank_desc,
    rs_to_score,
)

logger = logging.getLogger(__name__)


def _compound_return(conn, codes: list[str], start: date, end: date) -> dict[str, float]:
    if not codes:
        return {}
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"start": start, "end": end}
    for i, c in enumerate(codes):
        params[f"c{i}"] = c
    sql = f"""
        SELECT ts_code,
               EXP(SUM(LN(GREATEST(1 + pct_chg / 100, 1e-8)))) - 1 AS ret
        FROM ods_stock_detail_di
        WHERE trade_date BETWEEN :start AND :end
          AND ts_code IN ({placeholders})
        GROUP BY ts_code
    """
    rows = conn.execute(text(sql), params).mappings().all()
    return {r["ts_code"]: float(r["ret"] or 0) for r in rows}


def _board_return(conn, industry_code: str, start: date, end: date) -> float | None:
    row = conn.execute(
        text(
            """
            SELECT EXP(SUM(LN(GREATEST(1 + pct_change / 100, 1e-8)))) - 1 AS ret
            FROM ods_dc_daily_di
            WHERE ts_code = :ic AND trade_date BETWEEN :start AND :end
            """
        ),
        {"ic": industry_code, "start": start, "end": end},
    ).mappings().first()
    if not row or row["ret"] is None:
        return None
    return float(row["ret"])


def score_board_mvp(
    engine: Engine,
    trade_date: date,
    board: dict[str, Any],
    cfg: DragonConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    industry_code = board["industry_code"]
    industry_name = board.get("industry_name") or industry_code
    content_type = board.get("content_type") or ""

    members = load_members(engine, trade_date, industry_code)
    if len(members) < cfg.min_constituents:
        logger.debug("skip %s: constituents=%d", industry_code, len(members))
        return [], None

    codes = [m["ts_code"] for m in members]
    name_map = {m["ts_code"]: m["stock_name"] for m in members}

    trading_days = list_trading_days(engine, trade_date, max(cfg.ret_window_days, cfg.fund_window_days) + 5)
    if trade_date not in trading_days:
        trading_days.append(trade_date)
        trading_days.sort()
    idx = trading_days.index(trade_date)
    start_ret = trading_days[max(0, idx - cfg.ret_window_days + 1)]
    start_fund = trading_days[max(0, idx - cfg.fund_window_days + 1)]
    start_amt = trading_days[max(0, idx - cfg.amount_window_days + 1)]

    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    base_params: dict[str, Any] = {"td": trade_date, "start_f": start_fund, "start_a": start_amt}
    for i, c in enumerate(codes):
        base_params[f"c{i}"] = c

    with engine.connect() as conn:
        fund_rows = conn.execute(
            text(
                f"""
                SELECT ts_code, SUM(net_mf_amount) AS fund_net
                FROM ods_stock_fund_flow_di
                WHERE trade_date BETWEEN :start_f AND :td
                  AND ts_code IN ({placeholders})
                GROUP BY ts_code
                """
            ),
            base_params,
        ).mappings().all()
        fund_map = {r["ts_code"]: float(r["fund_net"] or 0) for r in fund_rows}

        amt_rows = conn.execute(
            text(
                f"""
                SELECT ts_code, AVG(amount) AS avg_amt
                FROM ods_stock_detail_di
                WHERE trade_date BETWEEN :start_a AND :td
                  AND ts_code IN ({placeholders})
                GROUP BY ts_code
                """
            ),
            base_params,
        ).mappings().all()
        amt_map = {r["ts_code"]: float(r["avg_amt"] or 0) for r in amt_rows}

        mv_rows = conn.execute(
            text(
                f"""
                SELECT ts_code, total_mv
                FROM ods_limit_list_di
                WHERE trade_date = :td AND ts_code IN ({placeholders})
                """
            ),
            base_params,
        ).mappings().all()
        mv_map = {r["ts_code"]: float(r["total_mv"] or 0) for r in mv_rows}

        for c in codes:
            if c not in mv_map:
                close_row = conn.execute(
                    text(
                        "SELECT close, amount FROM ods_stock_detail_di "
                        "WHERE trade_date = :td AND ts_code = :c LIMIT 1"
                    ),
                    {"td": trade_date, "c": c},
                ).mappings().first()
                if close_row and close_row["close"]:
                    mv_map[c] = float(close_row["close"]) * float(close_row.get("amount") or 0)

        stock_ret = _compound_return(conn, codes, start_ret, trade_date)
        board_ret = _board_return(conn, industry_code, start_ret, trade_date)

        inst_rows = conn.execute(
            text(
                f"""
                SELECT ts_code, COUNT(*) AS cnt
                FROM ods_report_rc_di
                WHERE report_date BETWEEN DATE_SUB(:td, INTERVAL 30 DAY) AND :td
                  AND ts_code IN ({placeholders})
                GROUP BY ts_code
                """
            ),
            base_params,
        ).mappings().all()
        inst_map = {r["ts_code"]: float(r["cnt"] or 0) for r in inst_rows}

    rs_raw: dict[str, float | None] = {}
    for c in codes:
        sr = stock_ret.get(c)
        if sr is None or board_ret is None or board_ret == 0:
            rs_raw[c] = None
        else:
            rs_raw[c] = sr / board_ret

    rs_score_map = {
        c: rs_to_score(rs_raw.get(c), board_ret, cap=cfg.rs_cap, cap_score=cfg.rs_cap_score)
        for c in codes
    }

    fund_pct = {c: percentile_score(fund_map, c) for c in codes}
    amt_pct = {c: percentile_score(amt_map, c) for c in codes}
    mv_pct = {c: percentile_score(mv_map, c) for c in codes}
    inst_pct = {c: percentile_score(inst_map, c) for c in codes}

    composite_map: dict[str, float | None] = {}
    rows: list[dict[str, Any]] = []
    for c in codes:
        sf = fund_pct.get(c)
        srs = rs_score_map.get(c)
        sa = amt_pct.get(c)
        smv = mv_pct.get(c)
        comp = composite_mvp(
            sf, srs, sa, smv,
            w_fund=cfg.w_fund, w_rs=cfg.w_rs, w_amount=cfg.w_amount, w_mv=cfg.w_mv,
        )
        composite_map[c] = comp
        trend_proxy = None
        if srs is not None and sa is not None:
            trend_proxy = round((srs + sa) / 2, 2)
        elif srs is not None:
            trend_proxy = srs
        elif sa is not None:
            trend_proxy = sa

        rows.append(
            {
                "trade_date": trade_date,
                "industry_code": industry_code,
                "industry_name": industry_name,
                "content_type": content_type,
                "ts_code": c,
                "stock_name": name_map.get(c, ""),
                "score_industry": None,
                "score_fund": sf,
                "score_trend": trend_proxy,
                "score_inst": inst_pct.get(c),
                "score_composite": comp,
                "score_mode": cfg.score_mode,
                "detail_json": detail_json(
                    fund_net_20d=fund_map.get(c),
                    rs_raw=rs_raw.get(c),
                    rs_score=srs,
                    avg_amount=amt_map.get(c),
                    mv_proxy=mv_map.get(c),
                    report_cnt_30d=inst_map.get(c),
                    board_ret_60d=board_ret,
                ),
            }
        )

    rank_fund = rank_desc({x["ts_code"]: x["score_fund"] for x in rows})
    rank_trend = rank_desc({x["ts_code"]: x["score_trend"] for x in rows})
    rank_inst = rank_desc({x["ts_code"]: x["score_inst"] for x in rows})
    rank_comp = rank_desc(composite_map)

    for r in rows:
        c = r["ts_code"]
        r["rank_fund"] = rank_fund.get(c)
        r["rank_trend"] = rank_trend.get(c)
        r["rank_inst"] = rank_inst.get(c)
        r["rank_composite"] = rank_comp.get(c)
        r["rank_industry"] = None
        r["is_industry_leader"] = 0
        r["industry_as_of"] = None
        r["inst_as_of"] = trade_date if r["score_inst"] is not None else None

    mark_leader(rows, "score_fund", "is_fund_leader")
    mark_leader(rows, "score_trend", "is_trend_leader")
    mark_leader(rows, "score_inst", "is_inst_leader")
    mark_leader(rows, "score_composite", "is_composite_leader")
    for r in rows:
        r["is_inst_leader"] = r["is_inst_leader"] or 0

    def pick_leader(flag: str, name_key: str) -> tuple[str | None, str | None]:
        for r in rows:
            if r.get(flag):
                return r["ts_code"], r["stock_name"]
        return None, None

    li_ts, li_nm = pick_leader("is_industry_leader", "industry")
    lf_ts, lf_nm = pick_leader("is_fund_leader", "fund")
    lt_ts, lt_nm = pick_leader("is_trend_leader", "trend")
    lin_ts, lin_nm = pick_leader("is_inst_leader", "inst")
    lc_ts, lc_nm = pick_leader("is_composite_leader", "composite")

    summary = {
        "trade_date": trade_date,
        "industry_code": industry_code,
        "industry_name": industry_name,
        "content_type": content_type,
        "leader_industry_ts": li_ts,
        "leader_industry_name": li_nm,
        "leader_fund_ts": lf_ts,
        "leader_fund_name": lf_nm,
        "leader_trend_ts": lt_ts,
        "leader_trend_name": lt_nm,
        "leader_inst_ts": lin_ts,
        "leader_inst_name": lin_nm,
        "leader_composite_ts": lc_ts,
        "leader_composite_name": lc_nm,
        "score_mode": cfg.score_mode,
        "summary_text": build_summary_text(
            industry_name,
            str(trade_date),
            {
                "industry": li_nm,
                "fund": lf_nm,
                "trend": lt_nm,
                "inst": lin_nm,
                "composite": lc_nm,
            },
        ),
    }
    return rows, summary
