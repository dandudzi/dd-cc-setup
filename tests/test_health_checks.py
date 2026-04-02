"""Tests for scripts/observatory/data/health_checks.py."""
from __future__ import annotations

import json

import pytest

from scripts.observatory.data.health_checks import (
    HealthCheck,
    add_health_check,
    compute_actual_value,
    compute_status,
    load_health_checks,
    remove_health_check,
    save_health_checks,
    update_health_check,
)


def _make(**kwargs) -> HealthCheck:
    defaults = dict(
        name="Read vs jCodeMunch",
        category_a="Read",
        category_b="jCodeMunch",
        metric="input_delta",
        expected=235.0,
        warning_threshold=50.0,
        error_threshold=150.0,
    )
    defaults.update(kwargs)
    return HealthCheck.create(**defaults)


# ---------------------------------------------------------------------------
# HealthCheck.create
# ---------------------------------------------------------------------------

class TestHealthCheckCreate:
    def test_id_is_set(self):
        assert _make().id

    def test_created_at_is_set(self):
        assert _make().created_at

    def test_fields_stored(self):
        hc = _make(name="test", category_a="Read", category_b="jDocMunch")
        assert hc.name == "test"
        assert hc.category_a == "Read"
        assert hc.category_b == "jDocMunch"

    def test_two_creates_have_different_ids(self):
        assert _make().id != _make().id


# ---------------------------------------------------------------------------
# load / save
# ---------------------------------------------------------------------------

class TestLoadSave:
    def test_load_returns_empty_when_file_missing(self, tmp_path):
        assert load_health_checks(tmp_path / "hc.json") == []

    def test_roundtrip_single(self, tmp_path):
        hc = _make()
        path = tmp_path / "hc.json"
        save_health_checks([hc], path)
        loaded = load_health_checks(path)
        assert loaded == [hc]

    def test_roundtrip_multiple(self, tmp_path):
        checks = [_make(name="A"), _make(name="B")]
        path = tmp_path / "hc.json"
        save_health_checks(checks, path)
        assert load_health_checks(path) == checks

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "dir" / "hc.json"
        save_health_checks([_make()], path)
        assert path.exists()

    def test_save_writes_valid_json(self, tmp_path):
        path = tmp_path / "hc.json"
        save_health_checks([_make()], path)
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1


# ---------------------------------------------------------------------------
# add / remove
# ---------------------------------------------------------------------------

class TestAddRemove:
    def test_add_to_empty(self):
        hc = _make()
        assert add_health_check([], hc) == [hc]

    def test_add_preserves_existing(self):
        a, b = _make(name="A"), _make(name="B")
        result = add_health_check([a], b)
        assert result == [a, b]

    def test_add_does_not_mutate_original(self):
        original = [_make()]
        add_health_check(original, _make())
        assert len(original) == 1

    def test_remove_by_id(self):
        hc = _make()
        assert remove_health_check([hc], hc.id) == []

    def test_remove_leaves_others(self):
        a, b = _make(name="A"), _make(name="B")
        result = remove_health_check([a, b], a.id)
        assert result == [b]

    def test_remove_unknown_id_is_noop(self):
        hc = _make()
        assert remove_health_check([hc], "nonexistent-id") == [hc]

    def test_remove_does_not_mutate_original(self):
        hc = _make()
        original = [hc]
        remove_health_check(original, hc.id)
        assert len(original) == 1


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

class TestUpdateHealthCheck:
    def test_update_replaces_matching_id(self):
        hc = _make(name="Original")
        import dataclasses
        updated = dataclasses.replace(hc, name="Updated")
        result = update_health_check([hc], updated)
        assert result[0].name == "Updated"

    def test_update_preserves_id(self):
        hc = _make()
        import dataclasses
        updated = dataclasses.replace(hc, name="New Name")
        result = update_health_check([hc], updated)
        assert result[0].id == hc.id

    def test_update_preserves_order(self):
        a, b, c = _make(name="A"), _make(name="B"), _make(name="C")
        import dataclasses
        updated_b = dataclasses.replace(b, name="B-updated")
        result = update_health_check([a, b, c], updated_b)
        assert [r.name for r in result] == ["A", "B-updated", "C"]

    def test_update_unknown_id_is_noop(self):
        hc = _make()
        import dataclasses
        stranger = dataclasses.replace(_make(), name="Stranger")
        result = update_health_check([hc], stranger)
        assert result == [hc]

    def test_update_does_not_mutate_original(self):
        hc = _make(name="Original")
        original = [hc]
        import dataclasses
        update_health_check(original, dataclasses.replace(hc, name="Updated"))
        assert original[0].name == "Original"

    def test_update_editable_fields(self):
        hc = _make(expected=100.0, warning_threshold=10.0, error_threshold=30.0)
        import dataclasses
        updated = dataclasses.replace(
            hc, name="Renamed", expected=200.0, warning_threshold=20.0, error_threshold=60.0
        )
        result = update_health_check([hc], updated)
        r = result[0]
        assert r.name == "Renamed"
        assert r.expected == 200.0
        assert r.warning_threshold == 20.0
        assert r.error_threshold == 60.0


# ---------------------------------------------------------------------------
# compute_status
# ---------------------------------------------------------------------------

class TestComputeStatus:
    def test_insufficient_when_none(self):
        assert compute_status(_make(), None) == "INSUFFICIENT"

    def test_ok_within_warning(self):
        hc = _make(expected=235.0, warning_threshold=50.0, error_threshold=150.0)
        assert compute_status(hc, 250.0) == "OK"   # diff=15

    def test_ok_at_exact_warning_boundary(self):
        hc = _make(expected=235.0, warning_threshold=50.0, error_threshold=150.0)
        assert compute_status(hc, 285.0) == "OK"   # diff=50, on boundary

    def test_warning_just_beyond_warning(self):
        hc = _make(expected=235.0, warning_threshold=50.0, error_threshold=150.0)
        assert compute_status(hc, 286.0) == "WARNING"  # diff=51

    def test_warning_at_exact_error_boundary(self):
        hc = _make(expected=235.0, warning_threshold=50.0, error_threshold=150.0)
        assert compute_status(hc, 385.0) == "WARNING"  # diff=150

    def test_error_beyond_error_threshold(self):
        hc = _make(expected=235.0, warning_threshold=50.0, error_threshold=150.0)
        assert compute_status(hc, 390.0) == "ERROR"    # diff=155

    def test_works_with_negative_delta(self):
        hc = _make(expected=235.0, warning_threshold=50.0, error_threshold=150.0)
        assert compute_status(hc, 200.0) == "OK"   # diff=35, below

    def test_ratio_metric_ok(self):
        hc = _make(metric="content_ratio", expected=0.59, warning_threshold=0.10, error_threshold=0.25)
        assert compute_status(hc, 0.62) == "OK"

    def test_ratio_metric_warning(self):
        hc = _make(metric="content_ratio", expected=0.59, warning_threshold=0.10, error_threshold=0.25)
        assert compute_status(hc, 0.72) == "WARNING"   # diff=0.13

    def test_ratio_metric_error(self):
        hc = _make(metric="content_ratio", expected=0.59, warning_threshold=0.10, error_threshold=0.25)
        assert compute_status(hc, 0.90) == "ERROR"     # diff=0.31


# ---------------------------------------------------------------------------
# compute_actual_value
# ---------------------------------------------------------------------------

class TestComputeActualValue:
    def test_input_delta(self):
        result = compute_actual_value(238.0, None, 3.0, None, "input_delta")
        assert result == pytest.approx(235.0)

    def test_input_delta_none_when_a_missing(self):
        assert compute_actual_value(None, None, 3.0, None, "input_delta") is None

    def test_input_delta_none_when_b_missing(self):
        assert compute_actual_value(238.0, None, None, None, "input_delta") is None

    def test_content_ratio(self):
        result = compute_actual_value(None, 968.0, None, 570.0, "content_ratio")
        assert result == pytest.approx(570.0 / 968.0)

    def test_content_ratio_none_when_a_content_missing(self):
        assert compute_actual_value(None, None, None, 570.0, "content_ratio") is None

    def test_content_ratio_none_when_b_content_missing(self):
        assert compute_actual_value(None, 968.0, None, None, "content_ratio") is None
