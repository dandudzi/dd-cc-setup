"""Playwright visual regression tests for the Observatory Dashboard."""
from __future__ import annotations

from playwright.sync_api import Page, expect

_HEADING_TIMEOUT = 15_000  # Streamlit React app needs time to hydrate


def _wait_for_streamlit(page: Page) -> None:
    """Wait for Streamlit's main app container to be present."""
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=20_000)


def _goto_dashboard(page: Page, app_url: str) -> None:
    page.goto(app_url)
    _wait_for_streamlit(page)


# ---------------------------------------------------------------------------
# Basic load
# ---------------------------------------------------------------------------

def test_dashboard_loads(page: Page, app_url: str):
    """Dashboard page loads and shows the title."""
    _goto_dashboard(page, app_url)
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=_HEADING_TIMEOUT)


def test_dashboard_is_default_page(page: Page, app_url: str):
    """Dashboard is the first page shown when navigating to the root."""
    page.goto(app_url)
    _wait_for_streamlit(page)
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Status legend
# ---------------------------------------------------------------------------

def test_dashboard_status_legend_expander(page: Page, app_url: str):
    """Status Legend expander exists on the dashboard."""
    _goto_dashboard(page, app_url)
    expect(page.get_by_text("Status Legend")).to_be_visible(timeout=_HEADING_TIMEOUT)


def test_dashboard_status_legend_content(page: Page, app_url: str):
    """Expanding the legend shows all four status levels."""
    _goto_dashboard(page, app_url)
    page.get_by_text("Status Legend").click()
    for status in ("OK", "WARNING", "ERROR", "INSUFFICIENT"):
        expect(page.get_by_text(status, exact=True).first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Health checks expander
# ---------------------------------------------------------------------------

def test_dashboard_health_checks_expander_visible(page: Page, app_url: str):
    """Health checks section (or empty-state info) is visible on load."""
    _goto_dashboard(page, app_url)
    # Either the checks expander or the empty-state info message is present
    checks = page.get_by_text("health check", exact=False)
    info = page.locator("[data-testid='stAlert']")
    expect(checks.or_(info).first).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Navigation — sidebar links
# ---------------------------------------------------------------------------

def test_dashboard_nav_has_f1_link(page: Page, app_url: str):
    """Sidebar contains Turn Cost Asymmetry link."""
    _goto_dashboard(page, app_url)
    expect(page.get_by_role("link", name="Turn Cost Asymmetry")).to_be_visible(timeout=_HEADING_TIMEOUT)


def test_dashboard_nav_has_f2_link(page: Page, app_url: str):
    """Sidebar contains Cache Miss Distribution link."""
    _goto_dashboard(page, app_url)
    expect(page.get_by_role("link", name="Cache Miss Distribution")).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Screenshot regression
# ---------------------------------------------------------------------------

def test_dashboard_screenshot(page: Page, app_url: str, assert_snapshot):
    """Visual regression snapshot — fails on pixel drift vs committed baseline."""
    _goto_dashboard(page, app_url)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    assert_snapshot(page.screenshot(full_page=True), "dashboard.png")
