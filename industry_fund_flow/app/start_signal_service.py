"""VIP 板块启动信号：短期 / 中期规则（查询时即时打分，不落新表）。

规则来源：需求整理/需求1-板块启动信号-使用文档.md §11
"""
from __future__ import annotations

from typing import Any

from app.db import fetch_all_stock
from app.dc_query_util import (
    latest_trade_date_from_table,
    list_trade_dates_from_table,
    resolve_trade_date,
    serialize_row,
)

MONITOR_TABLE = "dws_dc_industry_mainline_monitor_di"
FUND_TABLE = "dwm_dc_industry_fund_flow_di"
VP_TABLE = "dwm_industry_vp_score_di"
DRAGON_TABLE = "dwm_sector_dragon_summary_di"

DEFAULT_CONTENT_TYPES = ("行业", "概念")
SIGNAL_STATUSES = ("启动", "观察", "放弃")
MODE_SHORT = "short"
MODE_MID = "mid"

STATUS_LABEL = {
    "mainline_burst": "主线爆发",
    "trend_up": "趋势上升",
    "range_bound": "震荡",
    "weak": "弱势",
    "ebbing": "退潮",
}
SIGNAL_LABEL = {
    "main_rise": "主升",
    "launch": "启动",
    "none": "无",
    "distribution": "派发",
    "ebbing": "退潮",
}


def latest_trade_date() -> str | None:
    return latest_trade_date_from_table(MONITOR_TABLE, fallback_table=FUND_TABLE)


def list_trade_dates(limit: int = 60) -> list[str]:
    dates = list_trade_dates_from_table(MONITOR_TABLE, limit)
    if dates:
        return dates
    return list_trade_dates_from_table(FUND_TABLE, limit)


def _resolve_trade_date(trade_date: str | None) -> str:
    return resolve_trade_date(
        trade_date,
        table=MONITOR_TABLE,
        fallback_table=FUND_TABLE,
        empty_msg="暂无主线监控数据，请先运行日批 / 主线监控",
    )


def _parse_content_types(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(DEFAULT_CONTENT_TYPES)
    items = [x.strip() for x in raw.split(",") if x.strip()]
    filtered = [x for x in items if x in DEFAULT_CONTENT_TYPES]
    return filtered or list(DEFAULT_CONTENT_TYPES)


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clamp(score: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, score))


def _score_mainline(row: dict) -> tuple[float, dict[str, Any]]:
    level = row.get("mainline_level") or ""
    stage = row.get("mainline_stage") or ""
    main_score = _num(row.get("main_score"))
    ma5 = _num(row.get("total_score_ma5"))
    ma10 = _num(row.get("total_score_ma10"))

    level_score = {"超级主线": 15, "主线": 12, "轮动热点": 7, "跟风": 2}.get(level, 0)
    stage_score = {"机构化": 15, "板块爆发": 12, "资金试探": 10, "观察": 0}.get(stage, 0)

    trend_score = 0
    if main_score is not None and ma5 is not None and ma10 is not None and main_score > ma5 > ma10:
        trend_score = 8
    elif ma5 is not None and ma10 is not None and ma5 > ma10:
        trend_score = 5
    elif ma5 is not None and ma10 is not None and abs(ma5 - ma10) < 1.0:
        trend_score = 2

    total = min(30.0, float(level_score + stage_score + trend_score))
    return total, {
        "level_score": level_score,
        "stage_score": stage_score,
        "trend_score": trend_score,
    }


def _score_fund(row: dict, strength_rank_pct: float | None) -> tuple[float, dict[str, Any]]:
    days = int(_num(row.get("net_inflow_days")) or 0)
    accel = _num(row.get("fund_accel"))
    elg = _num(row.get("elg_net_ratio"))

    if days >= 5:
        days_score = 15
    elif days >= 3:
        days_score = 12
    elif days == 2:
        days_score = 8
    elif days == 1:
        days_score = 4
    else:
        days_score = 0

    if accel is None:
        accel_score = 0
    elif accel > 5e7:  # 明显 > 0（约 0.5 亿）
        accel_score = 10
    elif accel > 0:
        accel_score = 7
    elif abs(accel) < 1e6:
        accel_score = 3
    else:
        accel_score = 0

    if strength_rank_pct is None:
        strength_score = 0
    elif strength_rank_pct <= 0.10:
        strength_score = 10
    elif strength_rank_pct <= 0.20:
        strength_score = 8
    elif strength_rank_pct <= 0.30:
        strength_score = 6
    elif strength_rank_pct <= 0.50:
        strength_score = 3
    else:
        strength_score = 0

    if elg is None:
        elg_score = 0
    elif elg >= 0.4:
        elg_score = 5
    elif elg >= 0.15:
        elg_score = 2
    else:
        elg_score = 0

    total = min(35.0, float(days_score + accel_score + strength_score + elg_score))
    return total, {
        "days_score": days_score,
        "accel_score": accel_score,
        "strength_score": strength_score,
        "elg_score": elg_score,
        "strength_rank_pct": strength_rank_pct,
    }


def _score_vp(row: dict) -> tuple[float, dict[str, Any]]:
    vp_score = _num(row.get("vp_score"))
    status = (row.get("vp_status") or "").strip()
    signal = (row.get("vp_signal_type") or row.get("signal_type") or "").strip()
    rising = _num(row.get("rising_ratio"))
    breakout = _num(row.get("breakout_ratio"))
    streak = int(_num(row.get("amount_streak_days")) or 0)

    if vp_score is None:
        vp_part = 0
    elif vp_score >= 80:
        vp_part = 8
    elif vp_score >= 70:
        vp_part = 6
    elif vp_score >= 60:
        vp_part = 4
    else:
        vp_part = 0

    status_part = {
        "mainline_burst": 6,
        "trend_up": 5,
        "range_bound": 2,
        "weak": 0,
        "ebbing": 0,
    }.get(status, 0)

    signal_part = {
        "main_rise": 4,
        "launch": 3,
        "none": 0,
        "distribution": -2,
        "ebbing": -2,
    }.get(signal, 0)

    diffuse_hits = 0
    if rising is not None and rising >= 0.55:
        diffuse_hits += 1
    if breakout is not None and breakout >= 0.08:
        diffuse_hits += 1
    if streak >= 2:
        diffuse_hits += 1
    diffuse_part = 2 if diffuse_hits >= 2 else 0

    total = min(20.0, max(0.0, float(vp_part + status_part + signal_part + diffuse_part)))
    return total, {
        "vp_part": vp_part,
        "status_part": status_part,
        "signal_part": signal_part,
        "diffuse_part": diffuse_part,
    }


def _score_leader(row: dict) -> tuple[float, dict[str, Any], str]:
    """返回 (分数, 明细, 龙头清晰度标签: clear/unstable/unclear/drop)。"""
    name = (row.get("leader_composite_name") or "").strip()
    fund_name = (row.get("leader_fund_name") or "").strip()
    trend_name = (row.get("leader_trend_name") or "").strip()
    pct = _num(row.get("pct_change"))

    if name:
        clarity = "clear"
        clear_score = 6
    elif fund_name or trend_name:
        clarity = "unstable"
        clear_score = 3
    else:
        clarity = "unclear"
        clear_score = 0

    # 同步性：有综合龙头且板块涨跌不为明显下跌 → 同步
    if name and (pct is None or pct >= 0):
        sync_score = 6
        if clarity != "unclear":
            clarity = "clear"
    elif name:
        sync_score = 3
    elif clarity == "unstable":
        sync_score = 3
    else:
        sync_score = 0
        if pct is not None and pct > 1.0:
            clarity = "drop"

    # 稳定性：综合龙头与资金/趋势龙头一致则更稳
    if name and ((fund_name and name == fund_name) or (trend_name and name == trend_name)):
        stable_score = 3
    elif name:
        stable_score = 1
    else:
        stable_score = 0

    total = min(15.0, float(clear_score + sync_score + stable_score))
    return total, {
        "clear_score": clear_score,
        "sync_score": sync_score,
        "stable_score": stable_score,
        "clarity": clarity,
    }, clarity


def _apply_hard_filters(
    status: str,
    row: dict,
    leader_clarity: str,
) -> str:
    days = int(_num(row.get("net_inflow_days")) or 0)
    accel = _num(row.get("fund_accel"))
    stage = row.get("mainline_stage") or ""
    level = row.get("mainline_level") or ""
    vp_status = (row.get("vp_status") or "").strip()
    signal = (row.get("vp_signal_type") or "").strip()
    vp_score = _num(row.get("vp_score"))

    abandon_hits = 0
    if signal in ("distribution", "ebbing"):
        abandon_hits += 1
    if leader_clarity in ("unclear", "drop"):
        abandon_hits += 1
    if accel is not None and accel < 0:
        abandon_hits += 1
    if days <= 1:
        abandon_hits += 1
    if vp_score is not None and vp_score < 60:
        abandon_hits += 1
    if abandon_hits >= 2:
        return "放弃"

    downgrade = False
    if days < 2:
        downgrade = True
    if accel is not None and accel < 0:
        downgrade = True
    if stage == "观察":
        downgrade = True
    if vp_status in ("weak", "ebbing"):
        downgrade = True
    if leader_clarity != "clear":
        downgrade = True
    if vp_score is not None and vp_score < 70:
        downgrade = True
    if level not in ("主线", "超级主线") and stage not in ("板块爆发", "机构化"):
        downgrade = True
    if downgrade and status == "启动":
        return "观察"
    return status


def _short_flags(row: dict, strength_rank_pct: float | None, leader_clarity: str) -> dict[str, Any]:
    level = row.get("mainline_level") or ""
    stage = row.get("mainline_stage") or ""
    days = int(_num(row.get("net_inflow_days")) or 0)
    accel = _num(row.get("fund_accel"))
    vp_score = _num(row.get("vp_score"))
    signal = (row.get("vp_signal_type") or "").strip()
    status = (row.get("vp_status") or "").strip()
    streak = int(_num(row.get("amount_streak_days")) or 0)

    start_hits = [
        level in ("主线", "超级主线"),
        stage in ("资金试探", "板块爆发"),
        days >= 3,
        accel is not None and accel > 5e7,
        vp_score is not None and vp_score >= 75,
        signal in ("launch", "main_rise"),
        leader_clarity == "clear",
    ]
    incr_hits = [
        days >= 3,
        accel is not None and accel > 5e7,
        strength_rank_pct is not None and strength_rank_pct <= 0.20,
        streak >= 2,
        leader_clarity == "clear",
    ]
    abandon_hits = [
        accel is not None and accel < 0,
        days <= 1,
        status in ("weak", "ebbing"),
        signal in ("distribution", "ebbing"),
        leader_clarity in ("unclear", "drop"),
    ]

    start_cnt = sum(1 for x in start_hits if x)
    incr_cnt = sum(1 for x in incr_hits if x)
    abandon_cnt = sum(1 for x in abandon_hits if x)

    if abandon_cnt >= 2:
        signal_status = "放弃"
    elif start_cnt >= 5:
        signal_status = "启动"
    else:
        signal_status = "观察"

    return {
        "signal_status": signal_status,
        "start_hit_count": start_cnt,
        "incr_hit_count": incr_cnt,
        "abandon_hit_count": abandon_cnt,
        "is_incremental_fund_inflow": incr_cnt >= 3,
        "rule_mode": MODE_SHORT,
    }


def _mid_flags(row: dict, strength_rank_pct: float | None, leader_clarity: str) -> dict[str, Any]:
    level = row.get("mainline_level") or ""
    stage = row.get("mainline_stage") or ""
    main_score = _num(row.get("main_score"))
    ma5 = _num(row.get("total_score_ma5"))
    ma10 = _num(row.get("total_score_ma10"))
    days = int(_num(row.get("net_inflow_days")) or 0)
    accel = _num(row.get("fund_accel"))
    vp_status = (row.get("vp_status") or "").strip()

    ma_rising = False
    if main_score is not None and ma5 is not None and ma10 is not None and main_score > ma5 > ma10:
        ma_rising = True
    elif ma5 is not None and ma10 is not None and ma5 > ma10 + 0.5:
        ma_rising = True

    ma_flat_or_down = False
    if ma5 is not None and ma10 is not None:
        if ma5 <= ma10:
            ma_flat_or_down = True

    start_hits = [
        level in ("主线", "超级主线"),
        stage in ("板块爆发", "机构化"),
        ma_rising,
        days >= 4,
        accel is not None and accel > 5e7,
        leader_clarity == "clear",
    ]
    incr_hits = [
        days >= 4,
        accel is not None and accel > 5e7,
        strength_rank_pct is not None and strength_rank_pct <= 0.20,
        ma_rising,
        leader_clarity == "clear",
    ]
    abandon_hits = [
        stage == "观察",
        ma_flat_or_down,
        accel is not None and accel < 0,
        leader_clarity in ("drop", "unclear"),
        vp_status == "ebbing",
    ]

    start_cnt = sum(1 for x in start_hits if x)
    incr_cnt = sum(1 for x in incr_hits if x)
    abandon_cnt = sum(1 for x in abandon_hits if x)

    if abandon_cnt >= 2:
        signal_status = "放弃"
    elif start_cnt >= 5:
        signal_status = "启动"
    else:
        signal_status = "观察"

    return {
        "signal_status": signal_status,
        "start_hit_count": start_cnt,
        "incr_hit_count": incr_cnt,
        "abandon_hit_count": abandon_cnt,
        "is_incremental_fund_inflow": incr_cnt >= 4,
        "rule_mode": MODE_MID,
        "ma_rising": ma_rising,
    }


def _load_joined_rows(td: str, content_types: list[str]) -> list[dict]:
    placeholders = ", ".join(f":ct{i}" for i in range(len(content_types)))
    params: dict[str, Any] = {"td": td, **{f"ct{i}": ct for i, ct in enumerate(content_types)}}
    rows = fetch_all_stock(
        f"""
        SELECT
            m.trade_date, m.content_type, m.industry_code, m.industry_name,
            m.main_score, m.total_score, m.total_score_ma3, m.total_score_ma5, m.total_score_ma10,
            m.mainline_level, m.mainline_stage, m.fund_cont_days,
            m.score_fund, m.score_trend, m.rank_no,
            f.net_inflow_days, f.fund_accel, f.fund_inflow_strength, f.elg_net_ratio,
            f.pct_change, f.net_amount_wan, f.dc_rank,
            v.vp_score, v.vp_status, v.signal_type AS vp_signal_type,
            v.rising_ratio, v.breakout_ratio, v.amount_streak_days, v.industry_vol_ratio_20,
            d.leader_composite_name, d.leader_composite_ts,
            d.leader_fund_name, d.leader_trend_name
        FROM {MONITOR_TABLE} m
        LEFT JOIN {FUND_TABLE} f
          ON f.trade_date = m.trade_date AND f.industry_code = m.industry_code
        LEFT JOIN {VP_TABLE} v
          ON v.trade_date = m.trade_date AND v.industry_code = m.industry_code AND v.vp_window = 20
        LEFT JOIN {DRAGON_TABLE} d
          ON d.trade_date = m.trade_date
         AND d.industry_code = m.industry_code
         AND d.score_mode = 'mvp'
        WHERE m.trade_date = :td
          AND m.content_type IN ({placeholders})
        """,
        params,
    )
    return [serialize_row(r) for r in rows]


def _strength_rank_map(rows: list[dict]) -> dict[str, float]:
    """同 content_type 内按 fund_inflow_strength 降序，返回 code -> percentile(0=最强)。"""
    by_ct: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        strength = _num(r.get("fund_inflow_strength"))
        if strength is None:
            continue
        ct = r.get("content_type") or ""
        by_ct.setdefault(ct, []).append((r["industry_code"], strength))

    out: dict[str, float] = {}
    for items in by_ct.values():
        items.sort(key=lambda x: x[1], reverse=True)
        n = len(items)
        if n <= 1:
            if items:
                out[items[0][0]] = 0.0
            continue
        for i, (code, _) in enumerate(items):
            out[code] = i / (n - 1)
    return out


def evaluate(
    trade_date: str | None = None,
    *,
    mode: str = MODE_SHORT,
    content_types: str | None = "行业,概念",
    status_filter: str | None = None,
    top: int = 100,
) -> dict[str, Any]:
    mode = MODE_MID if mode == MODE_MID else MODE_SHORT
    td = _resolve_trade_date(trade_date)
    ctypes = _parse_content_types(content_types)
    top = max(1, min(top, 500))

    rows = _load_joined_rows(td, ctypes)
    strength_map = _strength_rank_map(rows)

    items: list[dict[str, Any]] = []
    for row in rows:
        code = row["industry_code"]
        rank_pct = strength_map.get(code)

        main_score, main_detail = _score_mainline(row)
        fund_score, fund_detail = _score_fund(row, rank_pct)
        vp_score, vp_detail = _score_vp(row)
        leader_score, leader_detail, clarity = _score_leader(row)
        total_score = round(main_score + fund_score + vp_score + leader_score, 2)

        if mode == MODE_SHORT:
            flags = _short_flags(row, rank_pct, clarity)
        else:
            flags = _mid_flags(row, rank_pct, clarity)

        # 完整评分阈值作展示；结论以拆分规则为准，再用硬过滤兜底
        score_status = "启动" if total_score >= 75 else ("观察" if total_score >= 55 else "放弃")
        signal_status = flags["signal_status"]
        # 若拆分规则与打分差距过大，不强行覆盖；硬过滤仍生效
        signal_status = _apply_hard_filters(signal_status, row, clarity)

        item = {
            **row,
            "mode": mode,
            "signal_status": signal_status,
            "score_status": score_status,
            "total_score": total_score,
            "score_mainline": round(main_score, 2),
            "score_fund_rule": round(fund_score, 2),
            "score_vp_rule": round(vp_score, 2),
            "score_leader_rule": round(leader_score, 2),
            "is_incremental_fund_inflow": flags["is_incremental_fund_inflow"],
            "start_hit_count": flags["start_hit_count"],
            "incr_hit_count": flags["incr_hit_count"],
            "abandon_hit_count": flags["abandon_hit_count"],
            "leader_clarity": clarity,
            "leader_name": row.get("leader_composite_name"),
            "vp_status_label": STATUS_LABEL.get(row.get("vp_status") or "", row.get("vp_status")),
            "vp_signal_label": SIGNAL_LABEL.get(row.get("vp_signal_type") or "", row.get("vp_signal_type")),
            "strength_rank_pct": None if rank_pct is None else round(rank_pct * 100, 1),
            "detail": {
                "mainline": main_detail,
                "fund": fund_detail,
                "vp": vp_detail,
                "leader": leader_detail,
                "flags": flags,
            },
        }
        items.append(item)

    if status_filter and status_filter in SIGNAL_STATUSES:
        items = [x for x in items if x["signal_status"] == status_filter]

    # 启动优先，再按总分
    priority = {"启动": 0, "观察": 1, "放弃": 2}
    items.sort(
        key=lambda x: (
            priority.get(x["signal_status"], 9),
            -(x["total_score"] or 0),
            x.get("industry_name") or "",
        )
    )
    items = items[:top]
    for i, it in enumerate(items, start=1):
        it["rank"] = i

    summary = {
        "启动": sum(1 for x in items if x["signal_status"] == "启动"),
        "观察": sum(1 for x in items if x["signal_status"] == "观察"),
        "放弃": sum(1 for x in items if x["signal_status"] == "放弃"),
        "incremental": sum(1 for x in items if x["is_incremental_fund_inflow"]),
    }
    return {
        "trade_date": td,
        "mode": mode,
        "mode_label": "短期" if mode == MODE_SHORT else "中期",
        "content_types": ctypes,
        "summary": summary,
        "items": items,
    }
