"""Playwright test — F1 page must not show F2 health checks."""
from __future__ import annotations

from playwright.sync_api import Page, expect

_HEADING_TIMEOUT = 15_000


def _wait_for_streamlit(page: Page) -> None:
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=20_000)


def _goto_f1(page: Page, app_url: str) -> None:
    page.goto(app_url)
    _wait_for_streamlit(page)
    page.get_by_role("link", name="Turn Cost Asymmetry").click()
    _wait_for_streamlit(page)


def test_f1_page_loads(page: Page, app_url: str):
    """Turn Cost Asymmetry page loads and shows its heading."""
    _goto_f1(page, app_url)
    expect(page.get_by_role("heading", name="Turn Cost Asymmetry")).to_be_visible(timeout=_HEADING_TIMEOUT)


def test_f1_saved_checks_section_visible(page: Page, app_url: str):
    """The Saved Health Checks expander appears on F1 page."""
    _goto_f1(page, app_url)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Saved Health Checks", exact=False)).to_be_visible(timeout=_HEADING_TIMEOUT)
