#!/usr/bin/env python3
"""需求3 量化主线数据验收（东财行业 Top10 + 概念 Top10 分榜）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_UTILS = _ROOT / "dw-utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from sqlalchemy import text

from mysql_config import get_engine
from etl.quant_mainline.db_util import parse_trade_date

TOP_TYPES = ("行业", "概念")


def _q(conn, sql: str, params: dict | None = None):
    return conn.execute(text(sql), params or {}).mappings().all()


def _expected_topn(board_cnt: int, cfg_top: int) -> int:
    return min(int(board_cnt or 0), cfg_top)


def check_prerequisites(conn, td: date) -> list[str]:
    issues: list[str] = []
    checks = [
        ("dwm_dc_industry_fund_flow_di", "SELECT COUNT(*) AS c FROM dwm_dc_industry_fund_flow_di WHERE trade_date=:td"),
        ("dwm_dc_industry_market_heat_di", "SELECT COUNT(*) AS c FROM dwm_dc_industry_market_heat_di WHERE trade_date=:td"),
        ("dwm_dc_industry_trend_strength_di", "SELECT COUNT(*) AS c FROM dwm_dc_industry_trend_strength_di WHERE trade_date=:td"),
        ("dwm_dc_industry_diffusion_di", "SELECT COUNT(*) AS c FROM dwm_dc_industry_diffusion_di WHERE trade_date=:td"),
        ("dwm_dc_industry_prosperity_di", "SELECT COUNT(*) AS c FROM dwm_dc_industry_prosperity_di WHERE trade_date=:td"),
        ("dwm_sector_dragon_summary_di", "SELECT COUNT(*) AS c FROM dwm_sector_dragon_summary_di WHERE trade_date=:td AND score_mode='mvp'"),
    ]
    for name, sql in checks:
        c = _q(conn, sql, {"td": td})[0]["c"]
        if not c:
            issues.append(f"前置缺失: {name} 当日 0 行")
        else:
            print(f"  OK  {name}: {c} 行")
    return issues


def _check_top_list_order(rows: list[dict], content_type: str) -> list[str]:
    issues: list[str] = []
    prev_rank_score = None
    for r in rows:
        if r.get("content_type") != content_type:
            issues.append(f"{content_type} Top 列表含其他类型: {r.get('content_type')}")
        rs = r.get("rank_score")
        if rs is not None and prev_rank_score is not None and float(rs) > float(prev_rank_score):
            issues.append(f"{content_type} Top 列表 rank_score 未降序")
            break
        prev_rank_score = rs
    ranks = [int(r["rank_no"]) for r in rows if r.get("rank_no") is not None]
    if ranks and ranks != list(range(1, len(ranks) + 1)):
        issues.append(f"{content_type} Top rank_no 不连续: {ranks}")
    return issues


def check_output(conn, td: date) -> tuple[list[str], dict]:
    issues: list[str] = []
    stats: dict = {}

    row = _q(
        conn,
        """
        SELECT COUNT(*) AS total,
            SUM(content_type='行业') AS cnt_industry,
            SUM(content_type='概念') AS cnt_concept,
            SUM(is_top3=1) AS topn_total,
            SUM(main_score IS NOT NULL) AS has_score,
            AVG(main_score) AS avg_score
        FROM dws_dc_industry_quant_mainline_di
        WHERE trade_date = :td
        """,
        {"td": td},
    )[0]
    stats["mainline"] = dict(row)
    total = int(row["total"] or 0)
    cnt_industry = int(row["cnt_industry"] or 0)
    cnt_concept = int(row["cnt_concept"] or 0)
    if total == 0:
        issues.append("输出为空: dws_dc_industry_quant_mainline_di 当日无数据")
        return issues, stats

    cfg = _q(
        conn,
        """
        SELECT content_types, top_n, ma_window_rank
        FROM dwm_dc_mainline_config
        WHERE config_key='__global__' AND is_active=1
        ORDER BY effective_date DESC LIMIT 1
        """,
    )
    cfg_top = int(cfg[0]["top_n"]) if cfg else 10
    if cfg:
        stats["config"] = dict(cfg[0])
        if "概念" not in str(cfg[0]["content_types"]):
            issues.append(f"配置未含概念: content_types={cfg[0]['content_types']}")
        if "行业" not in str(cfg[0]["content_types"]):
            issues.append(f"配置未含行业: content_types={cfg[0]['content_types']}")

    exp_industry = _expected_topn(cnt_industry, cfg_top)
    exp_concept = _expected_topn(cnt_concept, cfg_top)
    stats["expected_top_industry"] = exp_industry
    stats["expected_top_concept"] = exp_concept

    top_by_type: dict[str, list[dict]] = {}
    for ct in TOP_TYPES:
        cnt = _q(
            conn,
            """
            SELECT COUNT(*) AS c FROM dws_dc_industry_quant_mainline_di
            WHERE trade_date=:td AND content_type=:ct AND is_top3=1
            """,
            {"td": td, "ct": ct},
        )[0]["c"]
        top_by_type[ct] = int(cnt or 0)

    stats["top_industry"] = top_by_type["行业"]
    stats["top_concept"] = top_by_type["概念"]

    print(f"\n  主表 {td}: 共 {total} 行 (行业 {cnt_industry}, 概念 {cnt_concept})")
    print(
        f"  TopN: 行业={top_by_type['行业']}/{exp_industry} 概念={top_by_type['概念']}/{exp_concept} "
        f"(配置 top_n={cfg_top}), 均分={float(row['avg_score'] or 0):.2f}"
    )

    if top_by_type["行业"] != exp_industry:
        issues.append(f"行业 TopN 数量异常: 期望 {exp_industry}，实际 {top_by_type['行业']}")
    if top_by_type["概念"] != exp_concept:
        issues.append(f"概念 TopN 数量异常: 期望 {exp_concept}，实际 {top_by_type['概念']}")

    top_rows = _q(
        conn,
        """
        SELECT rank_no, content_type, industry_code, industry_name,
            main_score, main_score_ma5, rank_score, is_top3,
            score_f, score_t, score_e, score_l, score_p
        FROM dws_dc_industry_quant_mainline_di
        WHERE trade_date = :td AND is_top3 = 1
        ORDER BY content_type, rank_no
        """,
        {"td": td},
    )
    stats["top_rows"] = [dict(r) for r in top_rows]
    print("\n  === 行业/概念 TopN ===")
    for r in top_rows:
        print(
            f"  [{r['content_type']}] #{r['rank_no']} {r['industry_name']} ({r['industry_code']}) "
            f"score={float(r['main_score'] or 0):.1f} rank_score={r['rank_score']}"
        )

    for ct in TOP_TYPES:
        ct_rows = [dict(r) for r in top_rows if r["content_type"] == ct]
        issues.extend(_check_top_list_order(ct_rows, ct))

    dup_rank = _q(
        conn,
        """
        SELECT content_type, rank_no, COUNT(*) AS c
        FROM dws_dc_industry_quant_mainline_di
        WHERE trade_date = :td AND rank_no IS NOT NULL
        GROUP BY content_type, rank_no HAVING c > 1
        """,
        {"td": td},
    )
    if dup_rank:
        issues.append(f"同类型内排名重复: {[dict(r) for r in dup_rank]}")

    wrong_top_flag = _q(
        conn,
        """
        SELECT COUNT(*) AS c FROM dws_dc_industry_quant_mainline_di
        WHERE trade_date = :td
          AND content_type IN ('行业', '概念')
          AND (
            (is_top3 = 1 AND rank_no > :top_n)
            OR (is_top3 = 0 AND rank_no IS NOT NULL AND rank_no <= :top_n
                AND content_type IN ('行业', '概念'))
          )
        """,
        {"td": td, "top_n": cfg_top},
    )[0]["c"]
    if wrong_top_flag:
        issues.append(f"is_top3 与 rank_no 不一致: {wrong_top_flag} 行")

    null_ftelp = _q(
        conn,
        """
        SELECT COUNT(*) AS c FROM dws_dc_industry_quant_mainline_di
        WHERE trade_date = :td
          AND (score_f IS NULL OR score_t IS NULL OR score_e IS NULL
               OR score_l IS NULL OR score_p IS NULL OR main_score IS NULL)
        """,
        {"td": td},
    )[0]["c"]
    if null_ftelp:
        issues.append(f"FTELP 空值: {null_ftelp} 行")

    sig_row = _q(
        conn,
        """
        SELECT COUNT(*) AS total,
            SUM(signal_start=1) AS start_cnt,
            SUM(signal_exit=1) AS exit_cnt,
            SUM(signal_status='启动') AS status_start,
            SUM(signal_status='退潮') AS status_exit,
            SUM(signal_status='观察') AS status_watch
        FROM dws_dc_industry_quant_mainline_signal_di
        WHERE trade_date = :td
        """,
        {"td": td},
    )[0]
    stats["signal"] = dict(sig_row)
    sig_total = int(sig_row["total"] or 0)
    if sig_total != total:
        issues.append(f"信号表行数不一致: mainline={total} signal={sig_total}")
    else:
        print(
            f"\n  信号表: 启动={sig_row['start_cnt']} 退潮={sig_row['exit_cnt']} "
            f"(状态 启动/退潮/观察 = {sig_row['status_start']}/{sig_row['status_exit']}/{sig_row['status_watch']})"
        )

    if cfg:
        print(f"\n  配置: content_types={cfg[0]['content_types']} top_n={cfg[0]['top_n']}")

    return issues, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="需求3 量化主线数据测试（行业/概念分榜 Top10）")
    parser.add_argument("trade_date", nargs="?", help="YYYYMMDD，默认取 DWM 最新日")
    parser.add_argument("--run-etl", action="store_true", help="先执行 ETL 批处理")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args()

    engine = get_engine()
    with engine.connect() as conn:
        if args.trade_date:
            td = parse_trade_date(args.trade_date)
        else:
            r = conn.execute(
                text("SELECT MAX(trade_date) AS d FROM dwm_dc_industry_fund_flow_di")
            ).scalar()
            if not r:
                print("ERROR: dwm_dc_industry_fund_flow_di 无数据")
                return 1
            td = r

    print(f"=== 需求3 数据测试 trade_date={td} ===\n")

    if args.run_etl:
        from etl.quant_mainline.batch import run_batch

        print("运行 ETL ...")
        n = run_batch(td, TOP_TYPES)
        print(f"ETL 写入 {n} 行\n")

    all_issues: list[str] = []
    with engine.connect() as conn:
        print("--- 前置 DWM ---")
        all_issues.extend(check_prerequisites(conn, td))
        print("\n--- 输出验收 ---")
        out_issues, stats = check_output(conn, td)
        all_issues.extend(out_issues)

    report = {"trade_date": str(td), "issues": all_issues, "stats": stats}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    print("\n=== 结果 ===")
    if all_issues:
        print(f"FAIL: {len(all_issues)} 项")
        for i in all_issues:
            print(f"  - {i}")
        return 1
    print("PASS: 全部检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
