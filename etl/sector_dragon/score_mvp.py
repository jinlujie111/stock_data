"""单板块 MVP 四因子评分。"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.sector_dragon.db_util import (
    DragonConfig,
    _board_code_variants,
    list_trading_days,
    load_members,
)
from etl.sector_dragon.scoring import (
    build_summary_text,
    composite_mvp,
    composite_weighted,
    detail_json,
    mark_leader,
    percentile_score,
    rank_desc,
    rs_to_score,
)

logger = logging.getLogger(__name__)

# 综合分纳入产业/机构(研报活跃度)维度的附加权重（本地常量，DragonConfig 未含此配置）。
# 使“综合龙头”与 UI「四龙头 + 综合」口径一致；缺失时 composite_weighted 自动降权并重归一。
W_INDUSTRY_COMPOSITE = 0.15
W_INST_COMPOSITE = 0.10


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
    for ic in _board_code_variants(industry_code):
        row = conn.execute(
            text(
                """
                SELECT EXP(SUM(LN(GREATEST(1 + pct_change / 100, 1e-8)))) - 1 AS ret
                FROM ods_dc_daily_di
                WHERE ts_code = :ic AND trade_date BETWEEN :start AND :end
                """
            ),
            {"ic": ic, "start": start, "end": end},
        ).mappings().first()
        if row and row["ret"] is not None:
            return float(row["ret"])
    return None


def _load_fina_latest(
    conn,
    codes: list[str],
    trade_date: date,
    placeholders: str,
    base_params: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    rows = conn.execute(
        text(
            f"""
            SELECT ts_code, netprofit_yoy, q_profit_yoy, roe, end_date, ann_date
            FROM (
                SELECT f.ts_code, f.netprofit_yoy, f.q_profit_yoy, f.roe,
                       f.end_date, f.ann_date,
                       ROW_NUMBER() OVER (
                           PARTITION BY f.ts_code
                           ORDER BY f.end_date DESC, f.ann_date DESC
                       ) AS rn
                FROM ods_fina_indicator f
                WHERE f.ann_date <= :td
                  AND f.ts_code IN ({placeholders})
            ) x
            WHERE rn = 1
            """
        ),
        base_params,
    ).mappings().all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = r["ts_code"]
        out[code] = {
            "netprofit_yoy": float(r["netprofit_yoy"]) if r["netprofit_yoy"] is not None else None,
            "q_profit_yoy": float(r["q_profit_yoy"]) if r["q_profit_yoy"] is not None else None,
            "roe": float(r["roe"]) if r["roe"] is not None else None,
            "end_date": r["end_date"],
            "ann_date": r["ann_date"],
        }
    return out


def _load_report_industry(
    conn,
    placeholders: str,
    base_params: dict[str, Any],
) -> dict[str, dict[str, float | None]]:
    """个股近30日研报：上调占比、预测净利润环比(%)。"""
    rows = conn.execute(
        text(
            f"""
            WITH reports AS (
                SELECT ts_code, report_date, np, rating
                FROM ods_report_rc_di
                WHERE report_date BETWEEN DATE_SUB(:td, INTERVAL 60 DAY) AND :td
                  AND ts_code IN ({placeholders})
            ),
            r30 AS (
                SELECT
                    ts_code,
                    AVG(np) AS np_avg,
                    SUM(
                        CASE
                            WHEN rating IS NOT NULL
                             AND (
                                rating LIKE '%买%'
                                OR rating LIKE '%增持%'
                                OR rating LIKE '%推荐%'
                                OR rating LIKE '%强推%'
                                OR UPPER(rating) IN ('BUY', 'OVERWEIGHT', 'OUTPERFORM')
                             )
                            THEN 1 ELSE 0
                        END
                    ) AS upgrade_cnt,
                    SUM(
                        CASE WHEN rating IS NOT NULL AND TRIM(rating) <> '' THEN 1 ELSE 0 END
                    ) AS rated_cnt
                FROM reports
                WHERE report_date > DATE_SUB(:td, INTERVAL 30 DAY)
                GROUP BY ts_code
            ),
            rprev AS (
                SELECT ts_code, AVG(np) AS np_avg_prev
                FROM reports
                WHERE report_date > DATE_SUB(:td, INTERVAL 60 DAY)
                  AND report_date <= DATE_SUB(:td, INTERVAL 30 DAY)
                GROUP BY ts_code
            )
            SELECT
                r30.ts_code,
                CASE
                    WHEN r30.rated_cnt > 0 THEN r30.upgrade_cnt / r30.rated_cnt
                    ELSE NULL
                END AS upgrade_ratio,
                CASE
                    WHEN rprev.np_avg_prev IS NOT NULL AND rprev.np_avg_prev <> 0
                    THEN (r30.np_avg - rprev.np_avg_prev) / ABS(rprev.np_avg_prev) * 100
                    ELSE NULL
                END AS forecast_rev_pct
            FROM r30
            LEFT JOIN rprev ON r30.ts_code = rprev.ts_code
            """
        ),
        base_params,
    ).mappings().all()
    return {
        r["ts_code"]: {
            "upgrade_ratio": float(r["upgrade_ratio"]) if r["upgrade_ratio"] is not None else None,
            "forecast_rev_pct": float(r["forecast_rev_pct"]) if r["forecast_rev_pct"] is not None else None,
        }
        for r in rows
    }


def score_board_mvp(
    engine: Engine,
    trade_date: date,
    board: dict[str, Any],
    cfg: DragonConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    industry_code = board["industry_code"]
    industry_name = board.get("industry_name") or industry_code
    content_type = board.get("content_type") or ""
    member_date = board.get("member_date") or trade_date
    if isinstance(member_date, str):
        member_date = date.fromisoformat(member_date[:10])

    members = load_members(engine, trade_date, industry_code, member_date)
    if len(members) < cfg.min_constituents:
        logger.debug(
            "skip %s: constituents=%d member_date=%s",
            industry_code, len(members), member_date,
        )
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

        # 市值口径修正：主来源改为 ods_daily_basic_di.total_mv（全市场覆盖、真实总市值），
        # 缺失兜底流通市值 circ_mv；不再用涨跌停表(覆盖低)或 close*amount(根本不是市值)。
        mv_rows = conn.execute(
            text(
                f"""
                SELECT ts_code, total_mv, circ_mv
                FROM ods_daily_basic_di
                WHERE trade_date = :td AND ts_code IN ({placeholders})
                """
            ),
            base_params,
        ).mappings().all()
        mv_map = {}
        for r in mv_rows:
            tv = float(r["total_mv"]) if r["total_mv"] is not None else None
            cv = float(r["circ_mv"]) if r["circ_mv"] is not None else None
            val = tv if (tv and tv > 0) else (cv if (cv and cv > 0) else None)
            if val is not None:
                mv_map[r["ts_code"]] = val

        stock_ret = _compound_return(conn, codes, start_ret, trade_date)
        board_ret = _board_return(conn, industry_code, start_ret, trade_date)

        # 注意：inst 维度取的是近30日研报篇数（研报活跃度），并非机构持仓/机构资金。
        # 字段名保持 score_inst 不变，仅以文案/注释据实说明（见 build_summary_text）。
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

        fina_map = _load_fina_latest(conn, codes, trade_date, placeholders, base_params)
        report_ind_map = _load_report_industry(conn, placeholders, base_params)

    rs_raw: dict[str, float | None] = {}
    for c in codes:
        sr = stock_ret.get(c)
        if sr is None or board_ret is None or board_ret == 0:
            rs_raw[c] = None
        else:
            rs_raw[c] = sr / board_ret

    # 传入个股自身收益 stock_ret，供板块走平(board_ret≈0)时的 RS 兜底定分使用。
    rs_score_map = {
        c: rs_to_score(
            rs_raw.get(c),
            board_ret,
            cap=cfg.rs_cap,
            cap_score=cfg.rs_cap_score,
            stock_ret=stock_ret.get(c),
        )
        for c in codes
    }

    fund_pct = {c: percentile_score(fund_map, c) for c in codes}
    amt_pct = {c: percentile_score(amt_map, c) for c in codes}
    mv_pct = {c: percentile_score(mv_map, c) for c in codes}
    inst_pct = {c: percentile_score(inst_map, c) for c in codes}

    np_yoy_map = {c: fina_map.get(c, {}).get("netprofit_yoy") for c in codes}
    q_yoy_map = {c: fina_map.get(c, {}).get("q_profit_yoy") for c in codes}
    roe_map = {c: fina_map.get(c, {}).get("roe") for c in codes}
    upgrade_map = {c: report_ind_map.get(c, {}).get("upgrade_ratio") for c in codes}
    forecast_rev_map = {c: report_ind_map.get(c, {}).get("forecast_rev_pct") for c in codes}

    np_pct = {c: percentile_score(np_yoy_map, c) for c in codes}
    q_pct = {c: percentile_score(q_yoy_map, c) for c in codes}
    roe_pct = {c: percentile_score(roe_map, c) for c in codes}
    upgrade_pct = {c: percentile_score(upgrade_map, c) for c in codes}
    forecast_rev_pct_score = {c: percentile_score(forecast_rev_map, c) for c in codes}

    industry_map: dict[str, float | None] = {}
    industry_as_of_map: dict[str, date | None] = {}
    for c in codes:
        industry_map[c] = composite_weighted(
            (cfg.w_np_yoy, np_pct.get(c)),
            (cfg.w_q_yoy, q_pct.get(c)),
            (cfg.w_roe, roe_pct.get(c)),
            (cfg.w_upgrade, upgrade_pct.get(c)),
            (cfg.w_forecast_rev, forecast_rev_pct_score.get(c)),
        )
        fina = fina_map.get(c)
        industry_as_of_map[c] = fina.get("end_date") if fina else None

    composite_map: dict[str, float | None] = {}
    rows: list[dict[str, Any]] = []
    for c in codes:
        sf = fund_pct.get(c)
        srs = rs_score_map.get(c)
        sa = amt_pct.get(c)
        smv = mv_pct.get(c)
        # 综合分纳入产业(score_industry)与机构/研报(score_inst)维度，与 UI 四龙头口径一致；
        # 缺失维度由 composite_weighted 自动降权重归一。
        comp = composite_mvp(
            sf, srs, sa, smv,
            w_fund=cfg.w_fund, w_rs=cfg.w_rs, w_amount=cfg.w_amount, w_mv=cfg.w_mv,
            score_industry=industry_map.get(c), score_inst=inst_pct.get(c),
            w_industry=W_INDUSTRY_COMPOSITE, w_inst=W_INST_COMPOSITE,
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
                "score_industry": industry_map.get(c),
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
                    member_date=str(member_date),
                    netprofit_yoy=np_yoy_map.get(c),
                    q_profit_yoy=q_yoy_map.get(c),
                    roe=roe_map.get(c),
                    upgrade_ratio=upgrade_map.get(c),
                    forecast_rev_pct=forecast_rev_map.get(c),
                    fina_end_date=str(industry_as_of_map.get(c) or ""),
                ),
            }
        )

    rank_industry = rank_desc(industry_map)
    rank_fund = rank_desc({x["ts_code"]: x["score_fund"] for x in rows})
    rank_trend = rank_desc({x["ts_code"]: x["score_trend"] for x in rows})
    rank_inst = rank_desc({x["ts_code"]: x["score_inst"] for x in rows})
    rank_comp = rank_desc(composite_map)

    for r in rows:
        c = r["ts_code"]
        r["rank_industry"] = rank_industry.get(c)
        r["rank_fund"] = rank_fund.get(c)
        r["rank_trend"] = rank_trend.get(c)
        r["rank_inst"] = rank_inst.get(c)
        r["rank_composite"] = rank_comp.get(c)
        r["is_industry_leader"] = 0
        r["industry_as_of"] = industry_as_of_map.get(c)
        r["inst_as_of"] = trade_date if r["score_inst"] is not None else None

    mark_leader(rows, "score_industry", "is_industry_leader")
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
