"""申万板块轮动回测 / 信号入口。

用法:
  python -m etl.sector_rotation.batch --ingest-dumps
  python -m etl.sector_rotation.batch 20250716 20260715 --regime auto
  python -m etl.sector_rotation.batch 20250716 20260715 --regime reversal
  python -m etl.sector_rotation.batch --from-mysql 20250716 20260715
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etl.sector_rotation.backtest import run_backtest  # noqa: E402
from etl.sector_rotation.engine import FactorSpec, RotationConfig  # noqa: E402
from etl.sector_rotation.factors import (  # noqa: E402
    CACHE_DIR,
    SW2021_L1,
    load_benchmark_from_csv,
    load_benchmark_from_mysql,
    load_panel_from_csv,
    load_panel_from_mysql,
    merge_mcp_dumps,
    merge_mcp_fund_flow,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CSV = CACHE_DIR / "sw_l1_daily.csv"
DEFAULT_FLOW_CSV = CACHE_DIR / "sw_l1_fund_flow.csv"
DEFAULT_DUMP_DIR = (
    Path.home() / ".cursor" / "projects" / "c-jinlujie-code-stock-data" / "agent-tools"
)
OUT_DIR = CACHE_DIR / "backtest_out"

DEFAULT_FACTORS = [
    FactorSpec("mom20", 0.35, 1),
    FactorSpec("mom60", 0.25, 1),
    FactorSpec("flow5", 0.25, 1),
    FactorSpec("amt_ratio20", 0.15, 1),
]


def _parse_date(s: str) -> date:
    return datetime.strptime(str(s).strip().replace("-", ""), "%Y%m%d").date()


def ingest(dump_dir: Path, out_csv: Path, flow_csv: Path) -> int:
    merge_mcp_dumps(dump_dir, out_csv)
    try:
        merge_mcp_fund_flow(dump_dir, flow_csv)
    except RuntimeError as exc:
        logger.warning("资金流 cache 未生成: %s", exc)
        return 1
    df = __import__("pandas").read_csv(out_csv)
    sw = df[df["ts_code"].isin(SW2021_L1)]
    logger.info(
        "申万 L1: codes=%d rows=%d range=%s~%s",
        sw["ts_code"].nunique(),
        len(sw),
        sw["trade_date"].min(),
        sw["trade_date"].max(),
    )
    return 0


def _build_cfg(top_n: int, rebalance: str, regime: str) -> RotationConfig:
    mode = regime
    if regime == "auto":
        mode = "auto"
    elif regime in ("momentum", "fixed_momentum"):
        mode = "momentum"
    elif regime in ("reversal", "fixed_reversal"):
        mode = "reversal"
    return RotationConfig(
        top_n=top_n,
        rebalance=rebalance,
        factors=list(DEFAULT_FACTORS),
        regime=mode,  # type: ignore[arg-type]
    )


def run(
    start: date,
    end: date,
    *,
    csv_path: Path,
    flow_csv: Path,
    top_n: int,
    rebalance: str,
    regime: str,
    from_mysql: bool,
) -> int:
    cfg = _build_cfg(top_n, rebalance, regime)
    if from_mysql:
        sys.path.insert(0, str(_ROOT / "dw-utils"))
        from mysql_config import get_engine

        engine = get_engine()
        panel = load_panel_from_mysql(engine, start, end)
        bench = load_benchmark_from_mysql(engine, start, end)
    else:
        if not csv_path.exists():
            logger.error("缺少行情 cache: %s ，请先 --ingest-dumps", csv_path)
            return 1
        panel = load_panel_from_csv(
            csv_path, flow_csv if flow_csv.exists() else None
        )
        bench = load_benchmark_from_csv(csv_path, "000300.SH")

    has_flow = panel.net_flow is not None and not panel.net_flow.empty
    logger.info(
        "回测 %s~%s regime=%s top_n=%d rebalance=%s industries=%d flow=%s",
        start,
        end,
        cfg.regime,
        top_n,
        rebalance,
        panel.close.shape[1],
        has_flow,
    )
    result = run_backtest(panel, cfg, start, end, benchmark=bench or None)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    stamp = (
        f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
        f"_{cfg.regime}_top{top_n}_{rebalance}"
    )
    pd.DataFrame(result.nav).to_csv(
        OUT_DIR / f"nav_{stamp}.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(result.trades).to_csv(
        OUT_DIR / f"trades_{stamp}.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(result.holdings).to_csv(
        OUT_DIR / f"holdings_{stamp}.csv", index=False, encoding="utf-8-sig"
    )
    if result.regimes:
        pd.DataFrame(result.regimes).to_csv(
            OUT_DIR / f"regimes_{stamp}.csv", index=False, encoding="utf-8-sig"
        )
    metrics_path = OUT_DIR / f"metrics_{stamp}.json"
    metrics_path.write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    m = result.metrics
    logger.info("==== 回测结果 ====")
    logger.info("总收益      %.2f%%", (m.get("total_return") or 0) * 100)
    logger.info("年化        %.2f%%", (m.get("annual_return") or 0) * 100)
    logger.info("最大回撤    %.2f%%", (m.get("max_drawdown") or 0) * 100)
    logger.info("Sharpe      %s", m.get("sharpe"))
    logger.info("沪深300     %.2f%%", (m.get("bench_return") or 0) * 100)
    logger.info("相对300超额 %.2f%%", (m.get("excess_vs_300") or 0) * 100)
    logger.info(
        "状态机 动量周=%s 反转周=%s",
        m.get("regime_momentum_weeks"),
        m.get("regime_reversal_weeks"),
    )
    if result.holdings:
        logger.info("最近调仓:")
        for h in result.holdings[-5:]:
            logger.info(
                "  %s [%s] %s",
                h["trade_date"],
                h.get("regime"),
                " / ".join(h["names"]),
            )
    logger.info("输出 %s", OUT_DIR)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="申万一级行业板块轮动回测")
    parser.add_argument("start", nargs="?", default="20250716")
    parser.add_argument("end", nargs="?", default="20260715")
    parser.add_argument("--ingest-dumps", action="store_true")
    parser.add_argument("--dump-dir", type=Path, default=DEFAULT_DUMP_DIR)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--flow-csv", type=Path, default=DEFAULT_FLOW_CSV)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument(
        "--rebalance", choices=["weekly", "monthly", "daily"], default="weekly"
    )
    parser.add_argument(
        "--regime",
        choices=["auto", "momentum", "reversal"],
        default="auto",
        help="auto=状态机切换; momentum/reversal=固定风格",
    )
    parser.add_argument(
        "--from-mysql",
        action="store_true",
        help="从 ods_industry_daily_di / ods_industry_fund_flow_di 读数",
    )
    args = parser.parse_args(argv)

    if args.ingest_dumps:
        return ingest(args.dump_dir, args.csv, args.flow_csv)
    return run(
        _parse_date(args.start),
        _parse_date(args.end),
        csv_path=args.csv,
        flow_csv=args.flow_csv,
        top_n=args.top_n,
        rebalance=args.rebalance,
        regime=args.regime,
        from_mysql=args.from_mysql,
    )


if __name__ == "__main__":
    raise SystemExit(main())
