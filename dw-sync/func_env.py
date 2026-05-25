#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 dw/utils/func.sh 注入的环境变量读取配置。
禁止在 Python 中写死账号密码；须通过 dw/sync/sync_runner.sh 或先 source func.sh 启动。
"""
from __future__ import annotations

import os


class FuncEnvError(RuntimeError):
    pass


def ensure_func_loaded() -> None:
    if os.getenv("DW_FUNC_LOADED") != "1":
        raise FuncEnvError(
            "配置未加载：请先执行 source dw/utils/func.sh，"
            "或使用 bash dw/sync/sync_runner.sh 启动（禁止直接 python 裸跑）。"
        )


def require_env(name: str) -> str:
    ensure_func_loaded()
    val = os.getenv(name)
    if val is None or str(val).strip() == "":
        raise FuncEnvError(f"环境变量 {name} 未设置，请检查 dw/utils/func.sh 是否已 source。")
    return str(val).strip()


def require_env_int(name: str) -> int:
    return int(require_env(name))
