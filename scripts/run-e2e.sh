#!/usr/bin/env bash
# Run Playwright E2E tests in Docker for reproducible results.
#
# Usage:
#   ./scripts/run-e2e.sh                                     # run all E2E tests
#   ./scripts/run-e2e.sh --build                             # rebuild image, then run
#   ./scripts/run-e2e.sh --update-snapshots                  # regenerate screenshot baselines
#   ./scripts/run-e2e.sh --build --update-snapshots          # rebuild + regenerate (first time)
#   ./scripts/run-e2e.sh tests/e2e/test_dashboard.py -v      # pass args to pytest
#
# To run locally without Docker (faster, less reproducible screenshots):
#   uv run pytest tests/e2e/

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.e2e.yml"

BUILD=false
PYTEST_ARGS=()

for arg in "$@"; do
  if [[ "$arg" == "--build" ]]; then
    BUILD=true
  else
    PYTEST_ARGS+=("$arg")
  fi
done

cd "$REPO_ROOT"

if [[ "$BUILD" == true ]]; then
  docker compose -f "$COMPOSE_FILE" build e2e
fi

if [[ ${#PYTEST_ARGS[@]} -gt 0 ]]; then
  docker compose -f "$COMPOSE_FILE" run --rm e2e uv run pytest "${PYTEST_ARGS[@]}"
else
  docker compose -f "$COMPOSE_FILE" run --rm e2e
fi
