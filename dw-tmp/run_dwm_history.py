#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DWM 层历史数据回补：按依赖顺序依次调用 dw-dwm/pro_dwm_*.sh（脚本内部按日循环）。

默认：20250101 ~ 昨日；跑完全部 13 个 DWM 任务。
各 pro_dwm 脚本已支持 start~end 区间，本程序负责编排顺序与失败策略。

用法（建议先 source dw-utils/func.sh）：
  python dw-tmp/run_dwm_history.py
  python dw-tmp/run_dwm_history.py --start 20250101 --end 20260609
  python dw-tmp/run_dwm_history.py --group dc
  python dw-tmp/run_dwm_history.py --jobs market_breadth,dc_fund_flow,dc_trend
  python dw-tmp/run_dwm_history.py --dry-run
  python dw-tmp/run_dwm_history.py --continue-on-error --sleep-job 3

依赖顺序（简）：
  market_breadth → 资金/趋势/景气/热度 → 扩散（扩散依赖 market_breadth）
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

_DW_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_START = "20250101"
DEFAULT_SLEEP_JOB = 2.0


@dataclass(frozen=True)
class DwmJob:
    job_id: str
    script: str
    desc: str
    groups: frozenset[str]


# 执行顺序：扩散层依赖 market_breadth；其余主要依赖 ODS 已回补
DWM_JOBS: tuple[DwmJob, ...] = (
    DwmJob(
        "market_breadth",
        "dw-dwm/pro_dwm_market_breadth_di.sh",
        "全市场广度",
        frozenset({"base", "dc", "ths", "sw", "all"}),
    ),
    DwmJob(
        "dc_fund_flow",
        "dw-dwm/pro_dwm_dc_industry_fund_flow_di.sh",
        "东财板块资金强度",
        frozenset({"dc", "all"}),
    ),
    DwmJob(
        "ths_fund_flow",
        "dw-dwm/pro_dwm_ths_industry_fund_flow_di.sh",
        "同花顺板块资金强度",
        frozenset({"ths", "all"}),
    ),
    DwmJob(
        "dc_trend",
        "dw-dwm/pro_dwm_dc_industry_trend_strength_di.sh",
        "东财板块趋势强度",
        frozenset({"dc", "all"}),
    ),
    DwmJob(
        "ths_trend",
        "dw-dwm/pro_dwm_ths_industry_trend_strength_di.sh",
        "同花顺板块趋势强度",
        frozenset({"ths", "all"}),
    ),
    DwmJob(
        "dc_prosperity",
        "dw-dwm/pro_dwm_dc_industry_prosperity_di.sh",
        "东财板块产业景气",
        frozenset({"dc", "all"}),
    ),
    DwmJob(
        "ths_prosperity",
        "dw-dwm/pro_dwm_ths_industry_prosperity_di.sh",
        "同花顺板块产业景气",
        frozenset({"ths", "all"}),
    ),
    DwmJob(
        "sw_prosperity",
        "dw-dwm/pro_dwm_sw_industry_prosperity_di.sh",
        "申万板块产业景气",
        frozenset({"sw", "all"}),
    ),
    DwmJob(
        "dc_market_heat",
        "dw-dwm/pro_dwm_dc_industry_market_heat_di.sh",
        "东财板块市场热度",
        frozenset({"dc", "all"}),
    ),
    DwmJob(
        "ths_market_heat",
        "dw-dwm/pro_dwm_ths_industry_market_heat_di.sh",
        "同花顺板块市场热度",
        frozenset({"ths", "all"}),
    ),
    DwmJob(
        "dc_diffusion",
        "dw-dwm/pro_dwm_dc_industry_diffusion_di.sh",
        "东财板块扩散效应",
        frozenset({"dc", "all"}),
    ),
    DwmJob(
        "ths_diffusion",
        "dw-dwm/pro_dwm_ths_industry_diffusion_di.sh",
        "同花顺板块扩散效应",
        frozenset({"ths", "all"}),
    ),
    DwmJob(
        "sw_diffusion",
        "dw-dwm/pro_dwm_sw_industry_diffusion_di.sh",
        "申万板块扩散效应",
        frozenset({"sw", "all"}),
    ),
)

JOB_MAP = {j.job_id: j for j in DWM_JOBS}
ALL_JOB_IDS = tuple(j.job_id for j in DWM_JOBS)


def parse_yyyymmdd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def default_end_yesterday() -> date:
    return date.today() - timedelta(days=1)


def resolve_jobs(
    *,
    group: str | None,
    jobs_arg: str | None,
) -> list[DwmJob]:
    if jobs_arg:
        ids = [x.strip() for x in jobs_arg.split(",") if x.strip()]
        unknown = [i for i in ids if i not in JOB_MAP]
        if unknown:
            raise SystemExit(
                f"未知 job: {', '.join(unknown)}；可选: {', '.join(ALL_JOB_IDS)}"
            )
        return [JOB_MAP[i] for i in ids]

    grp = (group or "all").lower()
    if grp == "all":
        return list(DWM_JOBS)

    selected = [j for j in DWM_JOBS if grp in j.groups]
    if not selected:
        raise SystemExit(f"未知 group: {grp}；可选: base, dc, ths, sw, all")
    return selected


def run_job(
    job: DwmJob,
    start_s: str,
    end_s: str,
    *,
    dry_run: bool,
) -> int:
    script = _DW_ROOT / job.script
    if not script.is_file():
        logger.error("未找到脚本: %s", script)
        return 127

    cmd = ["bash", str(script), start_s, end_s]
    logger.info("=== DWM %s (%s) %s ~ %s ===", job.job_id, job.desc, start_s, end_s)
    logger.info("CMD: %s", " ".join(cmd))
    if dry_run:
        return 0

    proc = subprocess.run(cmd, cwd=str(_DW_ROOT))
    if proc.returncode == 0:
        logger.info("OK %s", job.job_id)
    else:
        logger.error("FAIL %s exit_code=%s", job.job_id, proc.returncode)
    return proc.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DWM 层历史数据回补")
    parser.add_argument("--start", default=DEFAULT_START, help="YYYYMMDD，默认 20250101")
    parser.add_argument("--end", default=None, help="YYYYMMDD，默认昨日")
    parser.add_argument(
        "--group",
        default="all",
        choices=["all", "base", "dc", "ths", "sw"],
        help="按业务分组跑任务（默认 all）",
    )
    parser.add_argument(
        "--jobs",
        default=None,
        help="逗号分隔 job id，指定后忽略 --group；见 --list-jobs",
    )
    parser.add_argument(
        "--list-jobs",
        action="store_true",
        help="列出全部 job id 后退出",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的命令")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="单个 DWM 脚本失败不中断后续任务",
    )
    parser.add_argument(
        "--sleep-job",
        type=float,
        default=DEFAULT_SLEEP_JOB,
        help=f"每个 DWM 脚本完成后的休眠秒数，默认 {DEFAULT_SLEEP_JOB}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_jobs:
        for j in DWM_JOBS:
            groups = ",".join(sorted(j.groups))
            print(f"{j.job_id:20} [{groups:20}] {j.desc}  -> {j.script}")
        return 0

    start = parse_yyyymmdd(args.start)
    end = parse_yyyymmdd(args.end) if args.end else default_end_yesterday()
    if start > end:
        logger.error("start=%s 不能晚于 end=%s", args.start, args.end or end)
        return 1

    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")
    jobs = resolve_jobs(group=None if args.jobs else args.group, jobs_arg=args.jobs)

    logger.info(
        "DWM 历史回补: %s ~ %s, jobs=%s, sleep_job=%s",
        start_s,
        end_s,
        len(jobs),
        args.sleep_job,
    )

    fail_cnt = 0
    for idx, job in enumerate(jobs):
        code = run_job(job, start_s, end_s, dry_run=args.dry_run)
        if code != 0:
            fail_cnt += 1
            if not args.continue_on_error:
                logger.error("任务 %s 失败，已中止", job.job_id)
                return code if code != 0 else 1
        if args.sleep_job > 0 and idx + 1 < len(jobs) and not args.dry_run:
            logger.info("休眠 %.2fs (DWM 任务间隔)", args.sleep_job)
            time.sleep(args.sleep_job)

    if fail_cnt:
        logger.warning("DWM 历史回补完成，失败任务数=%s", fail_cnt)
        return 1
    logger.info("DWM 历史回补全部成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
