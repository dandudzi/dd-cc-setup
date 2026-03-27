"""Tests for scripts/observe/logger.py — JSONL log writer."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.observe.logger import get_log_path, write_error_log, write_log


class TestGetLogPath:
    def test_default_path(self):
        with patch.dict(os.environ, {}, clear=True):
            path = get_log_path()
        assert str(path).endswith(".claude/logs/actions.jsonl")
        assert isinstance(path, Path)

    def test_env_var_override(self):
        with patch.dict(os.environ, {"CC_ACTION_LOG": "/tmp/custom.jsonl"}):
            path = get_log_path()
        assert str(path) == "/tmp/custom.jsonl"

    def test_returns_path_object(self):
        assert isinstance(get_log_path(), Path)


class TestWriteLog:
    def test_writes_valid_jsonl_line(self, tmp_path):
        log_path = tmp_path / "actions.jsonl"
        entry = {"ts": 1000, "event_type": "decision", "tool_name": "Read"}

        with patch("scripts.observe.logger.get_log_path", return_value=log_path):
            write_log(entry)

        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == entry

    def test_appends_not_overwrites(self, tmp_path):
        log_path = tmp_path / "actions.jsonl"

        with patch("scripts.observe.logger.get_log_path", return_value=log_path):
            write_log({"ts": 1})
            write_log({"ts": 2})

        lines = log_path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["ts"] == 1
        assert json.loads(lines[1])["ts"] == 2

    def test_creates_parent_directories(self, tmp_path):
        log_path = tmp_path / "deep" / "nested" / "actions.jsonl"

        with patch("scripts.observe.logger.get_log_path", return_value=log_path):
            write_log({"ts": 1})

        assert log_path.exists()

    def test_never_raises_on_permission_error(self, tmp_path):
        unwriteable = Path("/proc/unwriteable/actions.jsonl")
        with patch("scripts.observe.logger.get_log_path", return_value=unwriteable):
            write_log({"ts": 1})  # must not raise

    def test_each_entry_on_separate_line(self, tmp_path):
        log_path = tmp_path / "actions.jsonl"
        with patch("scripts.observe.logger.get_log_path", return_value=log_path):
            write_log({"a": 1})
            write_log({"b": 2})
        content = log_path.read_text()
        assert content.count("\n") == 2  # two complete lines


class TestWriteErrorLog:
    def test_writes_error_entry(self, tmp_path):
        log_path = tmp_path / "actions.jsonl"
        with patch("scripts.observe.logger.get_log_path", return_value=log_path):
            write_error_log("Read", "stdin parse failed")

        entry = json.loads(log_path.read_text().strip())
        assert entry["event_type"] == "error"
        assert entry["tool_name"] == "Read"
        assert "stdin parse failed" in entry["errors"]

    def test_error_entry_has_ts(self, tmp_path):
        log_path = tmp_path / "actions.jsonl"
        with patch("scripts.observe.logger.get_log_path", return_value=log_path):
            write_error_log("Bash", "crash")
        entry = json.loads(log_path.read_text().strip())
        assert isinstance(entry["ts"], int)
