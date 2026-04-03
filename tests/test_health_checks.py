"""Tests for scripts/observatory/data/health_checks.py."""
from __future__ import annotations

import json

import pytest

from scripts.observatory.data.health_checks import (
    OVERALL_CATEGORY,
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
# Load/save robustness (Finding #9)
# ---------------------------------------------------------------------------

class TestLoadSaveRobustness:
    def test_load_returns_empty_on_invalid_json(self, tmp_path):
        """Corrupt JSON file → returns [] with warning, does not crash."""
        path = tmp_path / "hc.json"
        path.write_text("not valid json", encoding="utf-8")
        result = load_health_checks(path)
        assert result == []

    def test_load_skips_invalid_entries_keeps_valid(self, tmp_path):
        """Array with one valid + one missing-field entry → only valid returned."""
        from dataclasses import asdict
        valid = asdict(_make(name="valid"))
        invalid = {"bad_field": "no required fields here"}
        path = tmp_path / "hc.json"
        path.write_text(json.dumps([valid, invalid]), encoding="utf-8")
        result = load_health_checks(path)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_save_produces_valid_json_after_save(self, tmp_path):
        """File contents are valid JSON immediately after save."""
        path = tmp_path / "hc.json"
        save_health_checks([_make(name="atomic")], path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["name"] == "atomic"

    def test_save_no_leftover_tmp_file(self, tmp_path):
        """After a successful save, no .tmp file is left behind."""
        path = tmp_path / "hc.json"
        save_health_checks([_make()], path)
        tmp_file = path.with_suffix(".tmp")
        assert not tmp_file.exists()


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

    def test_content_ratio_none_when_a_content_zero(self):
        assert compute_actual_value(None, 0.0, None, 570.0, "content_ratio") is None


# ---------------------------------------------------------------------------
# HealthCheck model extensions — category_b optional, report field
# ---------------------------------------------------------------------------

class TestHealthCheckModelExtensions:
    def test_overall_category_constant_exported(self):
        assert OVERALL_CATEGORY == "_overall"

    def test_create_absolute_check_category_b_none(self):
        hc = _make(category_b=None)
        assert hc.category_b is None

    def test_create_with_report_field(self):
        hc = _make(report="f2_cache_miss")
        assert hc.report == "f2_cache_miss"

    def test_create_default_report_is_f1(self):
        hc = _make()
        assert hc.report == "f1_turn_cost"

    def test_roundtrip_absolute_check(self, tmp_path):
        hc = _make(category_b=None, report="f2_cache_miss")
        path = tmp_path / "hc.json"
        save_health_checks([hc], path)
        loaded = load_health_checks(path)
        assert loaded[0].category_b is None
        assert loaded[0].report == "f2_cache_miss"

    def test_backward_compat_default_report(self, tmp_path):
        """Old JSON files without 'report' field load with report='f1_turn_cost'."""
        hc = _make()
        raw = {
            "id": hc.id,
            "name": hc.name,
            "category_a": hc.category_a,
            "category_b": hc.category_b,
            "metric": hc.metric,
            "expected": hc.expected,
            "warning_threshold": hc.warning_threshold,
            "error_threshold": hc.error_threshold,
            "created_at": hc.created_at,
            # no 'report' key
        }
        path = tmp_path / "hc.json"
        path.write_text(json.dumps([raw]))
        loaded = load_health_checks(path)
        assert loaded[0].report == "f1_turn_cost"

    def test_backward_compat_missing_category_b(self, tmp_path):
        """Old JSON files without 'category_b' field load with category_b=None."""
        hc = _make()
        raw = {
            "id": hc.id,
            "name": hc.name,
            "category_a": hc.category_a,
            # no 'category_b'
            "metric": hc.metric,
            "expected": hc.expected,
            "warning_threshold": hc.warning_threshold,
            "error_threshold": hc.error_threshold,
            "created_at": hc.created_at,
            "report": "f1_turn_cost",
        }
        path = tmp_path / "hc.json"
        path.write_text(json.dumps([raw]))
        loaded = load_health_checks(path)
        assert loaded[0].category_b is None


# ---------------------------------------------------------------------------
# compute_actual_value — F2 metrics
# ---------------------------------------------------------------------------

class TestComputeActualValueF2:
    def test_miss_rate_returns_value(self):
        result = compute_actual_value(
            None, None, None, None, "miss_rate",
            a_miss_rate=0.05,
        )
        assert result == pytest.approx(0.05)

    def test_miss_rate_none_when_missing(self):
        result = compute_actual_value(
            None, None, None, None, "miss_rate",
            a_miss_rate=None,
        )
        assert result is None

    def test_miss_rate_overall_sentinel(self):
        # When category_a == OVERALL_CATEGORY, caller passes overall rate as a_miss_rate
        result = compute_actual_value(
            None, None, None, None, "miss_rate",
            a_miss_rate=0.0083,
        )
        assert result == pytest.approx(0.0083)

    def test_miss_rate_delta(self):
        result = compute_actual_value(
            None, None, None, None, "miss_rate_delta",
            a_miss_rate=0.10,
            b_miss_rate=0.04,
        )
        assert result == pytest.approx(0.06)

    def test_miss_rate_delta_none_when_a_missing(self):
        result = compute_actual_value(
            None, None, None, None, "miss_rate_delta",
            a_miss_rate=None,
            b_miss_rate=0.04,
        )
        assert result is None

    def test_miss_rate_delta_none_when_b_missing(self):
        result = compute_actual_value(
            None, None, None, None, "miss_rate_delta",
            a_miss_rate=0.10,
            b_miss_rate=None,
        )
        assert result is None

    def test_mean_miss_tokens_returns_value(self):
        result = compute_actual_value(
            None, None, None, None, "mean_miss_tokens",
            a_mean_miss_tokens=4096.0,
        )
        assert result == pytest.approx(4096.0)

    def test_mean_miss_tokens_none_when_missing(self):
        result = compute_actual_value(
            None, None, None, None, "mean_miss_tokens",
            a_mean_miss_tokens=None,
        )
        assert result is None

    def test_compute_status_works_with_miss_rate(self):
        hc = _make(metric="miss_rate", category_b=None, expected=0.01,
                   warning_threshold=0.005, error_threshold=0.02)
        assert compute_status(hc, 0.012) == "OK"      # diff=0.002
        assert compute_status(hc, 0.018) == "WARNING" # diff=0.008
        assert compute_status(hc, 0.035) == "ERROR"   # diff=0.025
