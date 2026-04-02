"""Root conftest — registers options that must be available before subdirectory conftests load."""
import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Regenerate E2E screenshot baselines instead of comparing against them",
    )
