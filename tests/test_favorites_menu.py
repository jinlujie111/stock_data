from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "industry_fund_flow"))

from app.dc_registry import NAV_ITEMS, NAV_SECTIONS
from app.main import app


def test_favorites_menu_items_and_routes_exist():
    paths = {route.path for route in app.router.routes}
    assert "/favorites/boards" in paths
    assert "/favorites/stocks" in paths
    assert "/api/v1/favorites/boards" in paths
    assert "/api/v1/favorites/boards/table" in paths
    assert "/api/v1/favorites/stocks" in paths

    nav_labels = {item["label"] for item in NAV_ITEMS}
    assert "板块自选" in nav_labels
    assert "股票自选" in nav_labels

    section_titles = {section["title"] for section in NAV_SECTIONS}
    assert "板块分析" in section_titles
    assert "我的自选" in section_titles
    sector_slugs = {
        item["slug"]
        for section in NAV_SECTIONS
        if section["title"] == "板块分析"
        for item in section["items"]
    }
    assert "sectors" in sector_slugs
