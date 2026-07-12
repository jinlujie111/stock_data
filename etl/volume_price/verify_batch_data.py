#!/usr/bin/env python3
"""核查 VP 批次数据（用法: python etl/volume_price/verify_batch_data.py 20260710）"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "dw-utils"))

try:
    import pymysql
except ImportError:
    print("ERROR: pip install pymysql")
    sys.exit(1)


def parse_td(raw: str) -> date:
    s = raw.strip().replace("-", "")
    return datetime.strptime(s, "%Y%m%d").date()


def main() -> int:
    td_raw = sys.argv[1] if len(sys.argv) > 1 else "20260710"
    td = parse_td(td_raw)

    host = os.getenv("MYSQL_HOST", os.getenv("STOCK_MYSQL_HOST", "127.0.0.1"))
    port = int(os.getenv("MYSQL_PORT", os.getenv("STOCK_MYSQL_PORT", "3306")))
    user = os.getenv("MYSQL_USER", os.getenv("STOCK_MYSQL_USER", "app_user"))
    password = os.getenv("MYSQL_PASSWORD", os.getenv("STOCK_MYSQL_PASSWORD", "jinlujie"))
    database = os.getenv("MYSQL_DATABASE", os.getenv("STOCK_MYSQL_DATABASE", "stock_data"))

    print(f"=== VP 数据核查 trade_date={td} db={host}:{port}/{database} ===")

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as exc:
        print(f"CONNECT_FAIL: {exc}")
        return 1

    issues: list[str] = []

    def qone(sql: str, params=()):
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def qall(sql: str, params=()):
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # ODS 前置
    ods = qone("SELECT COUNT(*) AS c FROM ods_stock_detail_di WHERE trade_date=%s", (td,))
    ods_cnt = int(ods["c"] or 0)
    print(f"[ODS] ods_stock_detail_di rows={ods_cnt}")
    if ods_cnt == 0:
        issues.append("ODS 无当日个股行情，VP 批无法正常运行")

    # 列是否存在
    cols = qall(
        """
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='dwm_industry_vp_score_di'
          AND COLUMN_NAME IN ('score_leader','continuity_strength','trend_return_20d','leader_strength')
        """,
        (database,),
    )
    col_names = {r["COLUMN_NAME"] for r in cols}
    print(f"[DDL] score 新列: {sorted(col_names) or '无'}")
    if len(col_names) < 4:
        issues.append("六维升级 DDL 未完整执行（dwm_industry_vp_score_di 缺新列）")

    strict_col = qone(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='dwm_stock_vp_factor_di'
          AND COLUMN_NAME='is_breakout_strict'
        """,
        (database,),
    )
    if int(strict_col["c"] or 0) == 0:
        issues.append("dwm_stock_vp_factor_di 缺 is_breakout_strict 列")

    # 批次产出
    score_cnt = int(
        qone(
            "SELECT COUNT(*) AS c FROM dwm_industry_vp_score_di WHERE trade_date=%s AND vp_window=20",
            (td,),
        )["c"]
        or 0
    )
    agg_cnt = int(
        qone(
            "SELECT COUNT(*) AS c FROM dwm_industry_vp_agg_di WHERE trade_date=%s AND vp_window=20",
            (td,),
        )["c"]
        or 0
    )
    factor_cnt = int(
        qone(
            "SELECT COUNT(*) AS c FROM dwm_stock_vp_factor_di WHERE trade_date=%s AND vp_window=20",
            (td,),
        )["c"]
        or 0
    )
    print(f"[DWM] factor={factor_cnt} agg={agg_cnt} score={score_cnt}")
    if score_cnt == 0:
        issues.append("dwm_industry_vp_score_di 无当日数据（批处理未成功或未跑）")
    if factor_cnt == 0 and ods_cnt > 0:
        issues.append("dwm_stock_vp_factor_di 无数据")

    if score_cnt > 0 and col_names:
        fill = qone(
            """
            SELECT COUNT(*) AS total,
                   SUM(continuity_strength IS NOT NULL) AS has_cont,
                   SUM(trend_return_20d IS NOT NULL) AS has_trend,
                   SUM(leader_strength IS NOT NULL) AS has_leader,
                   SUM(score_leader IS NOT NULL) AS has_sl
            FROM dwm_industry_vp_score_di
            WHERE trade_date=%s AND vp_window=20
            """,
            (td,),
        )
        print(
            f"[FILL] total={fill['total']} continuity={fill['has_cont']} "
            f"trend20={fill['has_trend']} leader={fill['has_leader']} score_leader={fill['has_sl']}"
        )
        total = int(fill["total"] or 0)
        if total and int(fill["has_cont"] or 0) < total * 0.5:
            issues.append("continuity_strength 大量 NULL（可能仍是旧版 ETL）")
        if total and int(fill["has_trend"] or 0) < total * 0.3:
            issues.append("trend_return_20d 大量 NULL（检查 ods_dc_daily_di 板块指数）")

        dist = qone(
            """
            SELECT MIN(vp_score) AS mn, MAX(vp_score) AS mx, ROUND(AVG(vp_score),2) AS av,
                   SUM(vp_score>=80) AS burst, COUNT(*) AS n
            FROM dwm_industry_vp_score_di WHERE trade_date=%s AND vp_window=20
            """,
            (td,),
        )
        print(
            f"[DIST] min={dist['mn']} max={dist['mx']} avg={dist['av']} "
            f"burst(>=80)={dist['burst']} n={dist['n']}"
        )
        if dist["mn"] == dist["mx"] and dist["n"] and int(dist["n"]) > 1:
            issues.append("所有板块 VP 分相同，百分位或权重可能异常")

        dup = qone(
            """
            SELECT COUNT(*) AS c FROM (
              SELECT rank_vp, COUNT(*) AS n FROM dwm_industry_vp_score_di
              WHERE trade_date=%s AND vp_window=20 GROUP BY rank_vp HAVING n>1
            ) t
            """,
            (td,),
        )
        if int(dup["c"] or 0) > 0:
            issues.append(f"rank_vp 重复 {dup['c']} 组")

        w = qone(
            """
            SELECT weight_vol, weight_trend, weight_continuity, weight_breadth,
                   weight_breakout, weight_leader
            FROM dwm_vp_config
            WHERE config_key='__global__' AND is_active=1
            ORDER BY effective_date DESC LIMIT 1
            """
        )
        if w:
            print(
                f"[CFG] w_vol={w['weight_vol']} w_trend={w['weight_trend']} "
                f"w_cont={w['weight_continuity']} w_breadth={w['weight_breadth']} "
                f"w_breakout={w['weight_breakout']} w_leader={w.get('weight_leader')}"
            )
            exp = (0.20, 0.20, 0.25, 0.15, 0.15, 0.05)
            got = (
                float(w["weight_vol"]),
                float(w["weight_trend"]),
                float(w["weight_continuity"]),
                float(w["weight_breadth"]),
                float(w["weight_breakout"]),
                float(w.get("weight_leader") or 0),
            )
            if any(abs(a - b) > 0.001 for a, b in zip(got, exp)):
                issues.append(f"配置权重非六维新默认值: {got}")

        print("[TOP5]")
        tops = qall(
            """
            SELECT rank_vp, content_type, industry_name, vp_score,
                   score_continuity, score_vol, score_trend, trend_return_20d
            FROM dwm_industry_vp_score_di
            WHERE trade_date=%s AND vp_window=20
            ORDER BY rank_vp LIMIT 5
            """,
            (td,),
        )
        for r in tops:
            print(
                f"  #{r['rank_vp']} [{r['content_type']}] {r['industry_name']} "
                f"VP={r['vp_score']} cont={r['score_continuity']} vol={r['score_vol']} "
                f"trend={r['score_trend']} ret20={r.get('trend_return_20d')}"
            )

    if strict_col and int(strict_col["c"] or 0) > 0:
        br = qone(
            """
            SELECT SUM(is_breakout_strict=1) AS strict_n, COUNT(*) AS n
            FROM dwm_stock_vp_factor_di WHERE trade_date=%s AND vp_window=20
            """,
            (td,),
        )
        print(f"[BREAKOUT] strict_stocks={br['strict_n']} / factor_rows={br['n']}")

    conn.close()

    print("---")
    if issues:
        print("ISSUES:")
        for i, msg in enumerate(issues, 1):
            print(f"  {i}. {msg}")
        return 2
    print("OK: 未发现明显数据问题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
