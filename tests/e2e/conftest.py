"""Playwright E2E test fixtures for Observatory Streamlit app."""
from __future__ import annotations

import io
import os
import socket
import subprocess
import time
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_APP_PATH = _REPO_ROOT / "scripts" / "observatory" / "app.py"
_SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


# ---------------------------------------------------------------------------
# Auto-skip E2E when playwright is not installed
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(items: list) -> None:  # type: ignore[type-arg]
    """Skip E2E tests gracefully when playwright is not installed."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        skip = pytest.mark.skip(
            reason="playwright not installed — run: uv sync --extra e2e && playwright install chromium"
        )
        for item in items:
            if "e2e" in str(item.fspath):
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _compare_screenshot(actual: bytes, baseline: Path, name: str, max_diff_pixel_ratio: float) -> None:
    """Pixel-level comparison using PIL. Raises AssertionError on excess drift."""
    from PIL import Image, ImageChops

    img_actual = Image.open(io.BytesIO(actual)).convert("RGB")
    img_expected = Image.open(baseline).convert("RGB")

    if img_actual.size != img_expected.size:
        raise AssertionError(
            f"Screenshot size mismatch for {name!r}: "
            f"actual={img_actual.size}, expected={img_expected.size}. "
            f"Run with --update-snapshots to regenerate."
        )

    diff = ImageChops.difference(img_actual, img_expected)
    raw = diff.tobytes()
    channels = len(raw) // (diff.size[0] * diff.size[1])
    nonzero = sum(1 for i in range(0, len(raw), channels) if any(raw[i : i + channels]))
    ratio = nonzero / (diff.size[0] * diff.size[1])
    if ratio > max_diff_pixel_ratio:
        raise AssertionError(
            f"Screenshot mismatch for {name!r}: "
            f"{ratio:.2%} of pixels differ (threshold {max_diff_pixel_ratio:.2%}). "
            f"Run with --update-snapshots to regenerate."
        )


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def e2e_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Seed a minimal isolated data directory for hermetic E2E tests."""
    from tests.e2e.fixtures.seed_data import seed_fixture_transcripts

    base = tmp_path_factory.mktemp("observatory-data")
    seed_fixture_transcripts(base)
    return base


@pytest.fixture(scope="session")
def app_url(e2e_data_dir: Path) -> Generator[str, None, None]:
    """Start Streamlit once per session; yield the base URL; tear down after all tests."""
    port = _find_free_port()
    env = {
        **os.environ,
        # Point Observatory at fixture data — no dependency on ~/.claude/ state
        "OBSERVATORY_DATA_DIR": str(e2e_data_dir),
        "OBSERVATORY_HEALTH_DIR": str(e2e_data_dir / "observatory"),
    }
    proc = subprocess.Popen(
        [
            "uv", "run", "streamlit", "run",
            str(_APP_PATH),
            "--server.port", str(port),
            "--server.headless", "true",
            "--server.runOnSave", "false",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait up to 30s for the port to open
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    else:
        out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        proc.terminate()
        raise RuntimeError(
            f"Streamlit did not start on port {port} within 30s\n"
            f"--- stdout (last 2000 chars) ---\n{out[-2000:]}\n"
            f"--- stderr (last 2000 chars) ---\n{err[-2000:]}"
        )

    # Brief extra wait for Streamlit to finish initialising its UI
    time.sleep(2)

    yield f"http://localhost:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:  # type: ignore[type-arg]
    """Fix viewport and scale for deterministic screenshots across environments."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "device_scale_factor": 1,
    }


# ---------------------------------------------------------------------------
# Snapshot assertion fixture (Finding 3 — real visual regression)
# ---------------------------------------------------------------------------

@pytest.fixture
def assert_snapshot(pytestconfig: pytest.Config) -> Callable[[bytes, str], None]:
    """Assert a screenshot matches a committed baseline PNG.

    On first run (or with --update-snapshots), saves the baseline.
    On subsequent runs, compares pixel-by-pixel with 1% tolerance.

    Baselines are stored in tests/e2e/snapshots/ and committed to git.
    Regenerate after intentional UI changes: ./scripts/run-e2e.sh --update-snapshots
    """
    update = pytestconfig.getoption("--update-snapshots", default=False)

    def _assert(screenshot: bytes, name: str, max_diff_pixel_ratio: float = 0.01) -> None:
        baseline = _SNAPSHOTS_DIR / name
        if update or not baseline.exists():
            _SNAPSHOTS_DIR.mkdir(exist_ok=True)
            baseline.write_bytes(screenshot)
            return
        _compare_screenshot(screenshot, baseline, name, max_diff_pixel_ratio)

    return _assert
