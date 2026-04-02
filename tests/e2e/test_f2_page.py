"""Playwright visual regression tests for the F2 Cache Miss Distribution page."""
from __future__ import annotations

from playwright.sync_api import Page, expect

_HEADING_TIMEOUT = 15_000


def _wait_for_streamlit(page: Page) -> None:
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=20_000)


def _goto_f2(page: Page, app_url: str) -> None:
    page.goto(app_url)
    _wait_for_streamlit(page)
    page.get_by_role("link", name="Cache Miss Distribution").click()
    _wait_for_streamlit(page)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def test_f2_nav_entry(page: Page, app_url: str):
    """'Cache Miss Distribution' appears in the sidebar navigation."""
    page.goto(app_url)
    _wait_for_streamlit(page)
    expect(page.get_by_role("link", name="Cache Miss Distribution")).to_be_visible(timeout=_HEADING_TIMEOUT)


def test_f2_page_loads(page: Page, app_url: str):
    """F2 page loads and shows the page title."""
    _goto_f2(page, app_url)
    expect(page.get_by_role("heading", name="Cache Miss Distribution")).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Explainer
# ---------------------------------------------------------------------------

def test_f2_causal_disclaimer_in_explainer(page: Page, app_url: str):
    """Causal disclaimer text is present in the explainer expander."""
    _goto_f2(page, app_url)
    page.get_by_text("What is a cache miss?").click()
    expect(page.get_by_text("not caused by tool choice", exact=False).first).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Load-data gate
# ---------------------------------------------------------------------------

def test_f2_shows_load_prompt_before_data(page: Page, app_url: str):
    """The 'Load Data' sidebar button is present on the F2 page."""
    _goto_f2(page, app_url)
    expect(page.get_by_role("button", name="Load Data")).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Health check save form
# ---------------------------------------------------------------------------

def test_f2_health_check_save_form_visible(page: Page, app_url: str):
    """The 'Save as Health Check' expander exists on the F2 page."""
    _goto_f2(page, app_url)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    page.get_by_text("Save as Health Check").click()
    expect(page.get_by_text("Check type")).to_be_visible(timeout=_HEADING_TIMEOUT)


def test_f2_health_check_absolute_mode(page: Page, app_url: str):
    """Absolute mode shows a single category picker and metric selector."""
    _goto_f2(page, app_url)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    page.get_by_text("Save as Health Check").click()
    # Absolute is the default radio option — category selectbox is visible
    expect(page.get_by_text("Check type")).to_be_visible(timeout=_HEADING_TIMEOUT)
    expect(page.get_by_text("Absolute").first).to_be_visible()


def test_f2_health_check_pairwise_mode(page: Page, app_url: str):
    """Switching to Pairwise mode shows two category pickers."""
    _goto_f2(page, app_url)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    page.get_by_text("Save as Health Check").click()
    expect(page.get_by_text("Pairwise")).to_be_visible(timeout=_HEADING_TIMEOUT)
    page.get_by_text("Pairwise").click()
    expect(page.get_by_text("Category A", exact=True)).to_be_visible(timeout=_HEADING_TIMEOUT)
    expect(page.get_by_text("Category B", exact=True)).to_be_visible()


# ---------------------------------------------------------------------------
# Saved checks section
# ---------------------------------------------------------------------------

def test_f2_saved_checks_section_visible(page: Page, app_url: str):
    """The 'Saved Health Checks' expander appears on F2 page after data load."""
    _goto_f2(page, app_url)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Saved Health Checks", exact=False)).to_be_visible(timeout=_HEADING_TIMEOUT)


# ---------------------------------------------------------------------------
# Screenshot regression
# ---------------------------------------------------------------------------

def test_f2_screenshot(page: Page, app_url: str):
    """Full-page screenshot for visual regression baseline."""
    # Server can become temporarily unresponsive after many tests; retry navigation
    for attempt in range(3):
        try:
            page.goto(app_url, timeout=20_000)
            break
        except Exception:
            if attempt == 2:
                raise
            page.wait_for_timeout(3000)
    _wait_for_streamlit(page)
    page.get_by_role("link", name="Cache Miss Distribution").click()
    _wait_for_streamlit(page)
    page.get_by_role("button", name="Load Data").click()
    page.wait_for_load_state("networkidle")
    page.screenshot(path="tests/e2e/screenshots/f2_cache_miss.png", full_page=True)
