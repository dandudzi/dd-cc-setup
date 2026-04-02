"""Playwright E2E test fixtures for Observatory Streamlit app."""
from __future__ import annotations

import socket
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_APP_PATH = _REPO_ROOT / "scripts" / "observatory" / "app.py"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def app_url() -> Generator[str, None, None]:
    """Start Streamlit once per session; yield the base URL; tear down after all tests."""
    port = _find_free_port()
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
        proc.terminate()
        raise RuntimeError(f"Streamlit did not start on port {port} within 30s")

    # Brief extra wait for Streamlit to finish initialising its UI
    time.sleep(2)

    yield f"http://localhost:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        proc.kill()
        proc.wait(timeout=5)
