from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "industry_fund_flow"))

from app.dc_registry import NAV_ITEMS, NAV_SECTIONS
from app.main import app


def test_vp_menu_items_and_routes_exist():
    paths = {route.path for route in app.router.routes}
    assert "/dc/volume-price" in paths
    assert "/api/v1/vp/trade-dates" in paths
    assert "/api/v1/vp/industries/rank" in paths
    assert "/api/v1/vp/signals" in paths

    nav_slugs = {item["slug"] for item in NAV_ITEMS}
    assert "volume-price" in nav_slugs

    sector_items = [
        item
        for section in NAV_SECTIONS
        if section["title"] == "板块分析"
        for item in section["items"]
    ]
    assert any(item["slug"] == "volume-price" for item in sector_items)
