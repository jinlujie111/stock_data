from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "industry_fund_flow"))

from app.dc_registry import NAV_ITEMS, NAV_SECTIONS
from app.main import app


def test_favorites_menu_board_only():
    paths = {route.path for route in app.router.routes}
    assert "/favorites/boards" in paths
    assert "/favorites/stocks" in paths  # 仍注册，handler 返回 404
    assert "/api/v1/favorites/boards" in paths

    nav_slugs = {item["slug"] for item in NAV_ITEMS}
    assert nav_slugs == {"board-timing", "board-favorites"}
    assert "stock-favorites" not in nav_slugs

    nav_labels = {item["label"] for item in NAV_ITEMS}
    assert "板块自选" in nav_labels
    assert "股票自选" not in nav_labels

    section_titles = {section["title"] for section in NAV_SECTIONS}
    assert "我的自选" in section_titles
    assert "板块择时" in section_titles
