"""东财 FTELP 量化主线日批：得分、Top3、启动/退潮信号。"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_UTILS = _ROOT / "dw-utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from etl.quant_mainline.db_util import (  # noqa: E402
    QuantMainlineConfig,
    ensure_schema,
    get_engine_stock,
    list_prev_trade_dates,
    load_config,
    parse_trade_date,
)
from etl.quant_mainline.scoring import percentile_scores, weighted_sum  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAINLINE_INSERT = """
INSERT INTO dws_dc_industry_quant_mainline_di (
    trade_date, content_type, industry_code, industry_name,
    score_f, score_t, score_e, score_l, score_p,
    main_score, main_score_ma3, main_score_ma5, main_score_ma10,
    rank_no, rank_score, is_top3,
    amount_ratio, rs_ratio, limit_up_ratio,
    leader_code, leader_name, leader_pct_chg,
    detail_json, config_version
) VALUES (
    :trade_date, :content_type, :industry_code, :industry_name,
    :score_f, :score_t, :score_e, :score_l, :score_p,
    :main_score, :main_score_ma3, :main_score_ma5, :main_score_ma10,
    :rank_no, :rank_score, :is_top3,
    :amount_ratio, :rs_ratio, :limit_up_ratio,
    :leader_code, :leader_name, :leader_pct_chg,
    :detail_json, :config_version
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), content_type=VALUES(content_type),
    score_f=VALUES(score_f), score_t=VALUES(score_t), score_e=VALUES(score_e),
    score_l=VALUES(score_l), score_p=VALUES(score_p),
    main_score=VALUES(main_score), main_score_ma3=VALUES(main_score_ma3),
    main_score_ma5=VALUES(main_score_ma5), main_score_ma10=VALUES(main_score_ma10),
    rank_no=VALUES(rank_no), rank_score=VALUES(rank_score), is_top3=VALUES(is_top3),
    amount_ratio=VALUES(amount_ratio), rs_ratio=VALUES(rs_ratio),
    limit_up_ratio=VALUES(limit_up_ratio),
    leader_code=VALUES(leader_code), leader_name=VALUES(leader_name),
    leader_pct_chg=VALUES(leader_pct_chg),
    detail_json=VALUES(detail_json), config_version=VALUES(config_version),
    updated_at=CURRENT_TIMESTAMP
"""

SIGNAL_INSERT = """
INSERT INTO dws_dc_industry_quant_mainline_signal_di (
    trade_date, industry_code, industry_name, content_type,
    signal_start, signal_exit, signal_status, signal_reason,
    leader_code, leader_name, leader_pct_chg, config_version
) VALUES (
    :trade_date, :industry_code, :industry_name, :content_type,
    :signal_start, :signal_exit, :signal_status, :signal_reason,
    :leader_code, :leader_name, :leader_pct_chg, :config_version
)
ON DUPLICATE KEY UPDATE
    industry_name=VALUES(industry_name), content_type=VALUES(content_type),
    signal_start=VALUES(signal_start), signal_exit=VALUES(signal_exit),
    signal_status=VALUES(signal_status), signal_reason=VALUES(signal_reason),
    leader_code=VALUES(leader_code), leader_name=VALUES(leader_name),
    leader_pct_chg=VALUES(leader_pct_chg), config_version=VALUES(config_version),
    updated_at=CURRENT_TIMESTAMP
"""


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    return x


def _load_base_rows(engine, td: date, ctypes: tuple[str, ...]) -> list[dict[str, Any]]:
    ph = ", ".join(f":ct{i}" for i in range(len(ctypes)))
    params: dict[str, Any] = {"td": td}
    for i, ct in enumerate(ctypes):
        params[f"ct{i}"] = ct
    sql = f"""
    SELECT
        ff.industry_code,
        ff.industry_name,
        ff.content_type,
        h.amount_ratio,
        h.turnover_rate,
        h.board_amount,
        t.rs_20d,
        t.rs_5d,
        t.ma_bullish,
        t.is_new_high_60d,
        t.recovery_days,
        t.pct_change AS board_pct,
        d.limit_up_ratio,
        d.continue_limit_ratio,
        d.blast_ratio,
        d.board_success_ratio,
        d.up_ratio,
        d.max_limit_times,
        p.earnings_yoy,
        p.upgrade_ratio,
        p.forecast_rev_pct,
        p.policy_score
    FROM dwm_dc_industry_fund_flow_di ff
    LEFT JOIN dwm_dc_industry_market_heat_di h
        ON h.trade_date = ff.trade_date AND h.industry_code = ff.industry_code
    LEFT JOIN dwm_dc_industry_trend_strength_di t
        ON t.trade_date = ff.trade_date AND t.industry_code = ff.industry_code
    LEFT JOIN dwm_dc_industry_diffusion_di d
        ON d.trade_date = ff.trade_date AND d.industry_code = ff.industry_code
    LEFT JOIN dwm_dc_industry_prosperity_di p
        ON p.trade_date = ff.trade_date AND p.industry_code = ff.industry_code
    WHERE ff.trade_date = :td
      AND ff.content_type IN ({ph})
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def _load_v_ratio(engine, td: date) -> dict[str, float]:
    sql = """
    WITH bd AS (
        SELECT ts_code, trade_date, amount,
            AVG(amount) OVER (
                PARTITION BY ts_code ORDER BY trade_date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS ma5_amt,
            AVG(amount) OVER (
                PARTITION BY ts_code ORDER BY trade_date
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) AS ma20_amt
        FROM ods_dc_daily_di
        WHERE trade_date <= :td
          AND trade_date >= DATE_SUB(:td, INTERVAL 90 DAY)
    )
    SELECT ts_code,
        CASE WHEN ma20_amt > 0 THEN ma5_amt / ma20_amt ELSE NULL END AS v_ratio
    FROM bd
    WHERE trade_date = :td
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"td": td}).fetchall()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def _load_rs_ratio(engine, td: date) -> dict[str, float]:
    sql = """
    WITH bench AS (
        SELECT trade_date, close,
            close / NULLIF(
                LAG(close, 20) OVER (ORDER BY trade_date), 0
            ) - 1 AS ret_20d
        FROM ods_index_daily_di
        WHERE ts_code = '000300.SH'
          AND trade_date <= :td
          AND trade_date >= DATE_SUB(:td, INTERVAL 60 DAY)
    ),
    board AS (
        SELECT ts_code, trade_date, close,
            close / NULLIF(
                LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date), 0
            ) - 1 AS ret_20d
        FROM ods_dc_daily_di
        WHERE trade_date <= :td
          AND trade_date >= DATE_SUB(:td, INTERVAL 60 DAY)
    )
    SELECT b.ts_code,
        CASE
            WHEN bench.ret_20d IS NULL OR bench.ret_20d <= -1 THEN NULL
            ELSE (1 + b.ret_20d) / (1 + bench.ret_20d)
        END AS rs_ratio
    FROM board b
    JOIN bench ON bench.trade_date = b.trade_date
    WHERE b.trade_date = :td
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"td": td}).fetchall()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def _load_leaders(engine, td: date) -> dict[str, dict[str, Any]]:
    sql = """
    SELECT s.industry_code, s.leader_composite_ts, s.leader_composite_name,
        d.pct_chg AS leader_pct_chg
    FROM dwm_sector_dragon_summary_di s
    LEFT JOIN ods_stock_detail_di d
        ON d.trade_date = s.trade_date AND d.ts_code = s.leader_composite_ts
    WHERE s.trade_date = :td AND s.score_mode = 'mvp'
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"td": td}).mappings().all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[str(r["industry_code"])] = dict(r)
    return out


def _load_leader_excess(engine, td: date) -> dict[str, float]:
    sql = """
    WITH board_ret AS (
        SELECT ts_code, trade_date,
            close / NULLIF(LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date), 0) - 1 AS ret_20d
        FROM ods_dc_daily_di
        WHERE trade_date <= :td AND trade_date >= DATE_SUB(:td, INTERVAL 60 DAY)
    ),
    stk_ret AS (
        SELECT ts_code, trade_date,
            close / NULLIF(LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date), 0) - 1 AS ret_20d
        FROM ods_stock_detail_di
        WHERE trade_date <= :td AND trade_date >= DATE_SUB(:td, INTERVAL 60 DAY)
    )
    SELECT s.industry_code,
        (stk.ret_20d - br.ret_20d) * 100 AS leader_excess
    FROM dwm_sector_dragon_summary_di s
    JOIN board_ret br ON br.ts_code = s.industry_code AND br.trade_date = :td
    JOIN stk_ret stk ON stk.ts_code = s.leader_composite_ts AND stk.trade_date = :td
    WHERE s.trade_date = :td AND s.score_mode = 'mvp'
      AND s.leader_composite_ts IS NOT NULL
    """
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(sql), {"td": td}).fetchall()
        except Exception:
            return {}
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def _load_amount_history(engine, dates: list[date]) -> dict[str, list[float | None]]:
    if not dates:
        return {}
    ph = ", ".join(f":d{i}" for i in range(len(dates)))
    params = {f"d{i}": d for i, d in enumerate(dates)}
    sql = f"""
    SELECT industry_code, trade_date, amount_ratio
    FROM dwm_dc_industry_market_heat_di
    WHERE trade_date IN ({ph})
    ORDER BY industry_code, trade_date
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    hist: dict[str, list[float | None]] = {}
    for code, _td, ar in rows:
        hist.setdefault(str(code), []).append(_f(ar))
    return hist


def _load_main_score_history(
    engine, td: date, codes: list[str], days: int = 12
) -> dict[str, list[float]]:
    if not codes:
        return {}
    ph = ", ".join(f":c{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"td": td, "lim": days}
    for i, c in enumerate(codes):
        params[f"c{i}"] = c
    sql = f"""
    SELECT industry_code, trade_date, main_score
    FROM dws_dc_industry_quant_mainline_di
    WHERE industry_code IN ({ph})
      AND trade_date < :td
    ORDER BY industry_code, trade_date DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    hist: dict[str, list[float]] = {c: [] for c in codes}
    for code, _d, sc in rows:
        if sc is None:
            continue
        lst = hist.setdefault(str(code), [])
        if len(lst) < days:
            lst.append(float(sc))
    return hist


def _moving_avg(vals: list[float], window: int) -> float | None:
    if len(vals) < window:
        return None
    chunk = vals[:window]
    return round(sum(chunk) / window, 2)


def _compute_scores(
    rows: list[dict[str, Any]],
    cfg: QuantMainlineConfig,
    v_map: dict[str, float],
    rs_map: dict[str, float],
    leader_excess: dict[str, float],
) -> list[dict[str, Any]]:
    n = len(rows)
    if n == 0:
        return []

    raw_a = [_f(r.get("amount_ratio")) for r in rows]
    raw_v = [v_map.get(str(r["industry_code"])) for r in rows]
    raw_h = [_f(r.get("turnover_rate")) for r in rows]
    raw_etf = [None] * n  # MVP：ETF 子因子中性，待 dim ETF 映射增强

    raw_rs = [rs_map.get(str(r["industry_code"])) for r in rows]
    raw_n = [_f(r.get("is_new_high_60d")) for r in rows]
    raw_r = [_f(r.get("recovery_days")) for r in rows]
    raw_m = [_f(r.get("ma_bullish")) for r in rows]

    raw_z = [_f(r.get("limit_up_ratio")) for r in rows]
    raw_j = [_f(r.get("continue_limit_ratio")) for r in rows]
    raw_b = [_f(r.get("board_success_ratio")) for r in rows]
    raw_u = [_f(r.get("up_ratio")) for r in rows]

    raw_lr = [leader_excess.get(str(r["industry_code"])) for r in rows]
    raw_lc = [_f(r.get("max_limit_times")) for r in rows]
    raw_lp = [50.0] * n

    raw_pe = [_f(r.get("earnings_yoy")) for r in rows]
    raw_pp = [_f(r.get("policy_score")) for r in rows]
    raw_pf = [_f(r.get("forecast_rev_pct")) for r in rows]

    s_a = percentile_scores(raw_a)
    s_v = percentile_scores(raw_v)
    s_etf = percentile_scores(raw_etf)
    s_h = percentile_scores(raw_h)

    s_rs = percentile_scores(raw_rs)
    s_n = percentile_scores(raw_n)
    s_r = percentile_scores(raw_r, higher_is_better=False)
    s_m = percentile_scores(raw_m)

    s_z = percentile_scores(raw_z)
    s_j = percentile_scores(raw_j)
    s_b = percentile_scores(raw_b)
    s_u = percentile_scores(raw_u)

    s_lr = percentile_scores(raw_lr)
    s_lc = percentile_scores(raw_lc)
    s_lp = percentile_scores(raw_lp)

    s_pe = percentile_scores(raw_pe)
    s_pp = percentile_scores(raw_pp)
    s_pf = percentile_scores(raw_pf)

    fw, tw, ew, lw, pw = cfg.f_weights, cfg.t_weights, cfg.e_weights, cfg.l_weights, cfg.p_weights
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        score_f = weighted_sum(
            [
                (fw.get("A", 0.4), s_a[i]),
                (fw.get("V", 0.3), s_v[i]),
                (fw.get("ETF", 0.2), s_etf[i]),
                (fw.get("H", 0.1), s_h[i]),
            ]
        )
        score_t = weighted_sum(
            [
                (tw.get("RS", 0.4), s_rs[i]),
                (tw.get("N", 0.3), s_n[i]),
                (tw.get("R", 0.2), s_r[i]),
                (tw.get("M", 0.1), s_m[i]),
            ]
        )
        score_e = weighted_sum(
            [
                (ew.get("Z", 0.35), s_z[i]),
                (ew.get("J", 0.25), s_j[i]),
                (ew.get("B", 0.2), s_b[i]),
                (ew.get("U", 0.2), s_u[i]),
            ]
        )
        score_l = weighted_sum(
            [
                (lw.get("LR", 0.5), s_lr[i]),
                (lw.get("LC", 0.3), s_lc[i]),
                (lw.get("LP", 0.2), s_lp[i]),
            ]
        )
        score_p = weighted_sum(
            [
                (pw.get("Earnings", 0.5), s_pe[i]),
                (pw.get("Policy", 0.3), s_pp[i]),
                (pw.get("Forecast", 0.2), s_pf[i]),
            ]
        )
        out.append(
            {
                **r,
                "score_f": score_f,
                "score_t": score_t,
                "score_e": score_e,
                "score_l": score_l,
                "score_p": score_p,
                "rs_ratio": raw_rs[i],
                "detail": {
                    "sub_f": {"A": s_a[i], "V": s_v[i], "ETF": s_etf[i], "H": s_h[i]},
                    "sub_t": {"RS": s_rs[i], "N": s_n[i], "R": s_r[i], "M": s_m[i]},
                    "sub_e": {"Z": s_z[i], "J": s_j[i], "B": s_b[i], "U": s_u[i]},
                    "sub_l": {"LR": s_lr[i], "LC": s_lc[i], "LP": s_lp[i]},
                    "sub_p": {"Earnings": s_pe[i], "Policy": s_pp[i], "Forecast": s_pf[i]},
                },
            }
        )

    sf = percentile_scores([x["score_f"] for x in out])
    st = percentile_scores([x["score_t"] for x in out])
    se = percentile_scores([x["score_e"] for x in out])
    sl = percentile_scores([x["score_l"] for x in out])
    sp = percentile_scores([x["score_p"] for x in out])

    for i, row in enumerate(out):
        main = weighted_sum(
            [
                (cfg.w_f, sf[i]),
                (cfg.w_t, st[i]),
                (cfg.w_e, se[i]),
                (cfg.w_l, sl[i]),
                (cfg.w_p, sp[i]),
            ]
        )
        row["score_f"] = sf[i]
        row["score_t"] = st[i]
        row["score_e"] = se[i]
        row["score_l"] = sl[i]
        row["score_p"] = sp[i]
        row["main_score"] = main
    return out


def _amount_up_3d(hist: list[float | None]) -> bool:
    if len(hist) < 4:
        return False
    seq = [x for x in hist[-4:] if x is not None]
    if len(seq) < 4:
        return False
    return seq[0] < seq[1] < seq[2] < seq[3]


def _amount_down_2d(hist: list[float | None]) -> bool:
    if len(hist) < 3:
        return False
    seq = [x for x in hist[-3:] if x is not None]
    if len(seq) < 3:
        return False
    return seq[0] > seq[1] > seq[2]


def _eval_signals(
    row: dict[str, Any],
    cfg: QuantMainlineConfig,
    amount_hist: list[float | None],
    mean_z: float | None,
) -> dict[str, Any]:
    th = cfg.signal_thresholds
    rs = _f(row.get("rs_ratio"))
    z = _f(row.get("limit_up_ratio"))
    blast = _f(row.get("blast_ratio"))
    leader_pct = _f(row.get("leader_pct_chg"))
    is_nh = int(row.get("is_new_high_60d") or 0) == 1
    recovery = int(row.get("recovery_days") or 0)

    reasons: dict[str, bool] = {}
    start_parts: list[str] = []
    exit_parts: list[str] = []

    rs_gt = float(th.get("rs_gt", 1.2))
    reasons["rs_gt"] = rs is not None and rs > rs_gt
    if reasons["rs_gt"]:
        start_parts.append(f"RS>{rs_gt}")

    if th.get("a_up_3d", True):
        reasons["a_up_3d"] = _amount_up_3d(amount_hist)
        if reasons["a_up_3d"]:
            start_parts.append("成交额占比连升3日")

    z_mult = float(th.get("z_gt_market_mult", 1.5))
    z_thr = (mean_z or 0) * z_mult
    reasons["z_gt"] = z is not None and mean_z is not None and z > z_thr
    if reasons["z_gt"]:
        start_parts.append("涨停扩散强于市场")

    if th.get("leader_new_high", True):
        reasons["leader_new_high"] = is_nh
        if reasons["leader_new_high"]:
            start_parts.append("板块/趋势创新高")

    r_days = int(th.get("r_le_days", 3))
    reasons["r_le"] = recovery <= r_days
    if reasons["r_le"]:
        start_parts.append(f"回撤修复<={r_days}日")

    rs_lt = float(th.get("rs_lt", 0.9))
    reasons["rs_lt"] = rs is not None and rs < rs_lt
    if reasons["rs_lt"]:
        exit_parts.append(f"RS<{rs_lt}")

    if th.get("a_down_2d", True):
        reasons["a_down_2d"] = _amount_down_2d(amount_hist)
        if reasons["a_down_2d"]:
            exit_parts.append("成交额占比连降2日")

    ash = float(th.get("leader_ash_pct", -7.0))
    reasons["leader_ash"] = leader_pct is not None and leader_pct <= ash
    if reasons["leader_ash"]:
        exit_parts.append(f"龙头跌超{abs(ash)}%")

    blast_gt = float(th.get("blast_gt", 0.4))
    reasons["blast_gt"] = blast is not None and blast > blast_gt
    if reasons["blast_gt"]:
        exit_parts.append("炸板率过高")

    signal_start = all(
        [
            reasons.get("rs_gt"),
            reasons.get("a_up_3d"),
            reasons.get("z_gt"),
            reasons.get("leader_new_high"),
            reasons.get("r_le"),
        ]
    )
    signal_exit = any(
        [
            reasons.get("rs_lt"),
            reasons.get("a_down_2d"),
            reasons.get("leader_ash"),
            reasons.get("blast_gt"),
        ]
    )
    if signal_exit:
        status = "退潮"
    elif signal_start:
        status = "启动"
    else:
        status = "观察"

    return {
        "signal_start": 1 if signal_start else 0,
        "signal_exit": 1 if signal_exit else 0,
        "signal_status": status,
        "signal_reason": {
            "start": start_parts,
            "exit": exit_parts,
            "checks": reasons,
        },
    }


def run_batch(trade_date: date, content_types: tuple[str, ...] | None = None) -> int:
    engine = get_engine_stock()
    ensure_schema(engine)
    cfg = load_config(engine, trade_date)
    ctypes = content_types or cfg.content_types

    base = _load_base_rows(engine, trade_date, ctypes)
    if not base:
        logger.warning("no boards for %s types=%s", trade_date, ctypes)
        return 0

    v_map = _load_v_ratio(engine, trade_date)
    rs_map = _load_rs_ratio(engine, trade_date)
    leader_excess = _load_leader_excess(engine, trade_date)
    leaders = _load_leaders(engine, trade_date)

    scored = _compute_scores(base, cfg, v_map, rs_map, leader_excess)
    codes = [str(r["industry_code"]) for r in scored]
    hist_map = _load_main_score_history(engine, trade_date, codes)

    prev_dates = list_prev_trade_dates(engine, trade_date, 5)
    amt_dates = sorted(prev_dates + [trade_date])[-4:]
    amount_hist_all = _load_amount_history(engine, amt_dates)

    z_vals = [_f(r.get("limit_up_ratio")) for r in scored]
    z_valid = [z for z in z_vals if z is not None]
    mean_z = sum(z_valid) / len(z_valid) if z_valid else None

    ma_key = {3: "main_score_ma3", 5: "main_score_ma5", 10: "main_score_ma10"}
    mainline_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []

    for row in scored:
        code = str(row["industry_code"])
        hist_scores = hist_map.get(code, [])
        ms = row.get("main_score")
        series = [ms] + hist_scores if ms is not None else hist_scores
        ma3 = _moving_avg(series, 3)
        ma5 = _moving_avg(series, 5)
        ma10 = _moving_avg(series, 10)
        rank_score = ma5 if cfg.ma_window_rank == 5 else (ma3 if cfg.ma_window_rank == 3 else ma10)
        if rank_score is None:
            rank_score = ms

        leader = leaders.get(code, {})
        row["leader_code"] = leader.get("leader_composite_ts")
        row["leader_name"] = leader.get("leader_composite_name")
        row["leader_pct_chg"] = leader.get("leader_pct_chg")

        amt_hist = amount_hist_all.get(code, [])
        sig = _eval_signals(row, cfg, amt_hist, mean_z)

        mainline_rows.append(
            {
                "trade_date": trade_date,
                "content_type": row.get("content_type"),
                "industry_code": code,
                "industry_name": row.get("industry_name"),
                "score_f": row.get("score_f"),
                "score_t": row.get("score_t"),
                "score_e": row.get("score_e"),
                "score_l": row.get("score_l"),
                "score_p": row.get("score_p"),
                "main_score": ms,
                "main_score_ma3": ma3,
                "main_score_ma5": ma5,
                "main_score_ma10": ma10,
                "rank_no": None,
                "rank_score": rank_score,
                "is_top3": 0,
                "amount_ratio": row.get("amount_ratio"),
                "rs_ratio": row.get("rs_ratio"),
                "limit_up_ratio": row.get("limit_up_ratio"),
                "leader_code": row.get("leader_code"),
                "leader_name": row.get("leader_name"),
                "leader_pct_chg": row.get("leader_pct_chg"),
                "detail_json": json.dumps(row.get("detail") or {}, ensure_ascii=False),
                "config_version": cfg.config_key,
            }
        )
        signal_rows.append(
            {
                "trade_date": trade_date,
                "industry_code": code,
                "industry_name": row.get("industry_name"),
                "content_type": row.get("content_type"),
                "leader_code": row.get("leader_code"),
                "leader_name": row.get("leader_name"),
                "leader_pct_chg": row.get("leader_pct_chg"),
                "config_version": cfg.config_key,
                "signal_reason": json.dumps(sig["signal_reason"], ensure_ascii=False),
                **{k: sig[k] for k in ("signal_start", "signal_exit", "signal_status")},
            }
        )

    # 各 content_type 内分别排名取 TopN（行业 Top10 + 概念 Top10）
    top_types = list(cfg.content_types)
    top_n = cfg.top_n
    rank_lookup: dict[str, int] = {}
    top_lookup: dict[str, int] = {}
    for ct in top_types:
        type_rows = [r for r in mainline_rows if r.get("content_type") == ct]
        type_rows.sort(key=lambda x: (x.get("rank_score") or 0), reverse=True)
        for i, r in enumerate(type_rows):
            code = str(r["industry_code"])
            rank_no = i + 1
            is_top = 1 if i < top_n else 0
            r["rank_no"] = rank_no
            r["is_top3"] = is_top
            rank_lookup[code] = rank_no
            top_lookup[code] = is_top
    for r in mainline_rows:
        code = r["industry_code"]
        if code in rank_lookup:
            r["rank_no"] = rank_lookup[code]
            r["is_top3"] = top_lookup.get(code, 0)
        else:
            r["rank_no"] = None
            r["is_top3"] = 0

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM dws_dc_industry_quant_mainline_di WHERE trade_date = :td"),
            {"td": trade_date},
        )
        conn.execute(
            text("DELETE FROM dws_dc_industry_quant_mainline_signal_di WHERE trade_date = :td"),
            {"td": trade_date},
        )
        for row in mainline_rows:
            conn.execute(text(MAINLINE_INSERT), row)
        for row in signal_rows:
            conn.execute(text(SIGNAL_INSERT), row)

    top_cnt = sum(1 for r in mainline_rows if r.get("is_top3"))
    logger.info(
        "quant_mainline %s: boards=%d top%d=%d signals_start=%d",
        trade_date,
        len(mainline_rows),
        top_n,
        top_cnt,
        sum(1 for s in signal_rows if s.get("signal_start")),
    )
    return len(mainline_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="东财 FTELP 量化主线日批")
    parser.add_argument("trade_date", help="YYYYMMDD")
    parser.add_argument(
        "--content-types",
        default="",
        help="板块类型，逗号分隔，默认读 dwm_dc_mainline_config",
    )
    args = parser.parse_args(argv)
    td = parse_trade_date(args.trade_date)
    ctypes: tuple[str, ...] | None = None
    if args.content_types.strip():
        ctypes = tuple(x.strip() for x in args.content_types.split(",") if x.strip())
    n = run_batch(td, ctypes)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
