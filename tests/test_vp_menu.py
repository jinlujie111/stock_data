from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "industry_fund_flow"))

from app.dc_registry import DISABLED_DC_SLUGS, NAV_ITEMS, NAV_SECTIONS, RETIRED_DC_PAGES
from app.main import app


def test_nav_after_decision_chain_retirement():
    paths = {route.path for route in app.router.routes}
    assert "/dc/board-timing" in paths
    assert "/dc/timing-kline" in paths
    assert "/favorites/boards" in paths

    nav_slugs = {item["slug"] for item in NAV_ITEMS}
    assert nav_slugs == {"board-timing", "board-favorites"}
    assert "dragon" not in nav_slugs
    assert "fund-flow" not in nav_slugs
    assert "volume-price" not in nav_slugs
    assert "mainline" not in nav_slugs
    assert "stock-favorites" not in nav_slugs
    assert "决策链路" not in {s["title"] for s in NAV_SECTIONS}

    assert "fund-flow" in DISABLED_DC_SLUGS
    assert "dragon" in RETIRED_DC_PAGES
    assert "volume-price" in RETIRED_DC_PAGES

    # 已下线页面路由仍注册但应 404（由 handler 抛出）
    assert "/dc/dragon" in paths
    assert "/dc/volume-price" in paths
    assert "/dc/sentiment" not in paths
    # 首页大盘情绪仍依赖 sentiment API
    assert "/api/v1/sentiment/history" in paths
