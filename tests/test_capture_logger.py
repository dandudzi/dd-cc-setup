"""Test suite for the capture logger module.

Tests cover the action capture pipeline:
- Loading mappings from config file
- Building JSONL entries with classification and routing results
- Appending entries to log file
- Main orchestration function that ties everything together
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.capture import logger


@pytest.fixture
def config_path():
    """Path to real config/mappings.json."""
    return (
        Path(__file__).parent.parent / "config" / "mappings.json"
    )


@pytest.fixture
def temp_log_file():
    """Temporary log file for testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False
    ) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    if Path(temp_path).exists():
        Path(temp_path).unlink()


@pytest.fixture
def sample_event():
    """Sample event from stdin hook."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/src/app.py"},
        "session_id": "abc-123",
    }


@pytest.fixture
def sample_classification():
    """Sample classification result from classifier."""
    return {
        "category": "file_ops",
        "plugin": "core",
    }


@pytest.fixture
def sample_routing_result():
    """Sample routing result from router."""
    return {
        "decision": "soft_deny",
        "handler": "scripts.routing.handlers.route_read_code",
        "handler_output": {"redirect_to": "jCodeMunch"},
    }


class TestLoadMappings:
    """Test loading and validating mappings config file."""

    def test_load_mappings_from_path(self, config_path):
        """load_mappings() loads and returns dict from config file."""
        mappings = logger.load_mappings(config_path)

        assert isinstance(mappings, dict)
        assert "tools" in mappings
        assert "mcp_prefixes" in mappings
        assert "_fallback" in mappings

    def test_load_mappings_has_required_keys(self, config_path):
        """Loaded mappings has required _fallback key."""
        mappings = logger.load_mappings(config_path)
        fallback = mappings.get("_fallback")

        assert fallback is not None
        assert "category" in fallback
        assert "plugin" in fallback

    def test_load_mappings_auto_detect_path(self):
        """load_mappings() with no arg auto-detects relative to logger.py."""
        # Should find config/mappings.json relative to logger.py
        mappings = logger.load_mappings()

        assert isinstance(mappings, dict)
        assert "tools" in mappings

    def test_load_mappings_from_env(self, monkeypatch, tmp_path):
        """load_mappings() uses CC_MAPPINGS_CONFIG env var when set."""
        config = {"_version": "1.0", "_fallback": {"category": "unknown", "plugin": "unknown", "decision": "pass"}, "tools": {}, "mcp_prefixes": {}, "routing": []}
        config_file = tmp_path / "mappings.json"
        config_file.write_text(json.dumps(config))
        monkeypatch.setenv("CC_MAPPINGS_CONFIG", str(config_file))
        result = logger.load_mappings()
        assert result["_version"] == "1.0"

    def test_load_mappings_invalid_path_raises(self):
        """load_mappings() with invalid path raises FileNotFoundError."""
        invalid_path = Path("/nonexistent/mappings.json")

        with pytest.raises(FileNotFoundError):
            logger.load_mappings(invalid_path)


class TestGetLogPath:
    """Test log path resolution."""

    def test_get_log_path_default(self):
        """get_log_path() defaults to ~/.claude/logs/actions.jsonl."""
        with patch.dict(os.environ, {}, clear=True):
            path = logger.get_log_path()

            assert str(path) == os.path.expanduser("~/.claude/logs/actions.jsonl")

    def test_get_log_path_from_env(self):
        """get_log_path() reads CC_ACTION_LOG env var."""
        custom_path = "/tmp/custom-action.jsonl"

        with patch.dict(os.environ, {"CC_ACTION_LOG": custom_path}):
            path = logger.get_log_path()

            assert str(path) == custom_path

    def test_get_log_path_returns_path_object(self):
        """get_log_path() returns a Path object."""
        with patch.dict(os.environ, {}, clear=True):
            path = logger.get_log_path()

            assert isinstance(path, Path)


class TestBuildEntry:
    """Test JSONL entry construction."""

    def test_entry_has_all_required_fields(
        self,
        sample_event,
        sample_classification,
        sample_routing_result,
    ):
        """build_entry() returns dict with all 12 required fields."""
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            sample_routing_result,
            latency_ms=42,
        )

        required_fields = [
            "ts",
            "event_type",
            "tool_name",
            "category",
            "plugin",
            "args",
            "input_size",
            "decision",
            "handler",
            "handler_output",
            "latency_ms",
            "session_id",
        ]

        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    def test_ts_is_unix_epoch_int(
        self,
        sample_event,
        sample_classification,
        sample_routing_result,
    ):
        """ts field is int (Unix epoch), not str or float."""
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert isinstance(entry["ts"], int)
        # Should be close to current time (within 5 seconds)
        assert abs(entry["ts"] - int(time.time())) <= 5

    def test_event_type_from_stdin(
        self,
        sample_classification,
        sample_routing_result,
    ):
        """event_type comes from event hook_event_name."""
        event = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {},
        }
        entry = logger.build_entry(
            event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["event_type"] == "PostToolUse"

    def test_event_type_unknown_when_missing(
        self,
        sample_classification,
        sample_routing_result,
    ):
        """event_type is 'unknown' if hook_event_name missing."""
        event = {
            "tool_name": "Read",
            "tool_input": {},
        }
        entry = logger.build_entry(
            event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["event_type"] == "unknown"

    def test_tool_name_from_stdin(
        self,
        sample_event,
        sample_classification,
        sample_routing_result,
    ):
        """tool_name comes from event."""
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["tool_name"] == "Read"

    def test_category_from_classification(
        self,
        sample_event,
        sample_routing_result,
    ):
        """category comes from classification result."""
        classification = {"category": "code_search", "plugin": "jcodemunch"}
        entry = logger.build_entry(
            sample_event,
            classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["category"] == "code_search"

    def test_plugin_from_classification(
        self,
        sample_event,
        sample_routing_result,
    ):
        """plugin comes from classification result."""
        classification = {"category": "code_search", "plugin": "jcodemunch"}
        entry = logger.build_entry(
            sample_event,
            classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["plugin"] == "jcodemunch"

    def test_args_from_tool_input(
        self,
        sample_classification,
        sample_routing_result,
    ):
        """args field is tool_input from event."""
        tool_input = {"file_path": "/src/app.py", "lines": 10}
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": tool_input,
        }
        entry = logger.build_entry(
            event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["args"] == tool_input

    def test_input_size_is_byte_count(
        self,
        sample_classification,
        sample_routing_result,
    ):
        """input_size is len(json.dumps(args))."""
        tool_input = {"file_path": "/src/app.py"}
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": tool_input,
        }
        entry = logger.build_entry(
            event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        expected_size = len(json.dumps(tool_input))
        assert entry["input_size"] == expected_size

    def test_decision_from_routing_result(
        self,
        sample_event,
        sample_classification,
    ):
        """decision comes from routing result."""
        routing_result = {
            "decision": "deny",
            "handler": None,
            "handler_output": None,
        }
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            routing_result,
            latency_ms=1,
        )

        assert entry["decision"] == "deny"

    def test_handler_from_routing_result(
        self,
        sample_event,
        sample_classification,
    ):
        """handler comes from routing result."""
        routing_result = {
            "decision": "soft_deny",
            "handler": "scripts.routing.handlers.route_read_code",
            "handler_output": None,
        }
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            routing_result,
            latency_ms=1,
        )

        assert entry["handler"] == "scripts.routing.handlers.route_read_code"

    def test_handler_none_when_no_routing_handler(
        self,
        sample_event,
        sample_classification,
    ):
        """handler is None when routing result has no handler."""
        routing_result = {
            "decision": "pass",
            "handler": None,
            "handler_output": None,
        }
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            routing_result,
            latency_ms=1,
        )

        assert entry["handler"] is None

    def test_handler_output_from_routing_result(
        self,
        sample_event,
        sample_classification,
    ):
        """handler_output comes from routing result."""
        routing_result = {
            "decision": "soft_deny",
            "handler": "scripts.routing.handlers.route_read_code",
            "handler_output": {"redirect_to": "jCodeMunch", "reason": "code"},
        }
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            routing_result,
            latency_ms=1,
        )

        assert entry["handler_output"] == {"redirect_to": "jCodeMunch", "reason": "code"}

    def test_handler_output_none_when_no_handler(
        self,
        sample_event,
        sample_classification,
    ):
        """handler_output is None when no handler was called."""
        routing_result = {
            "decision": "pass",
            "handler": None,
            "handler_output": None,
        }
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            routing_result,
            latency_ms=1,
        )

        assert entry["handler_output"] is None

    def test_latency_ms_is_non_negative_int(
        self,
        sample_event,
        sample_classification,
        sample_routing_result,
    ):
        """latency_ms is a non-negative int."""
        entry = logger.build_entry(
            sample_event,
            sample_classification,
            sample_routing_result,
            latency_ms=42,
        )

        assert isinstance(entry["latency_ms"], int)
        assert entry["latency_ms"] >= 0
        assert entry["latency_ms"] == 42

    def test_session_id_from_event(
        self,
        sample_classification,
        sample_routing_result,
    ):
        """session_id comes from event."""
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {},
            "session_id": "xyz-789",
        }
        entry = logger.build_entry(
            event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["session_id"] == "xyz-789"

    def test_session_id_none_when_missing(
        self,
        sample_classification,
        sample_routing_result,
    ):
        """session_id is None when not in event."""
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {},
        }
        entry = logger.build_entry(
            event,
            sample_classification,
            sample_routing_result,
            latency_ms=1,
        )

        assert entry["session_id"] is None


class TestAppendEntry:
    """Test appending entries to JSONL log."""

    def test_append_entry_writes_valid_jsonl(self, temp_log_file):
        """append_entry() writes a valid JSON line."""
        entry = {
            "ts": 1234567890,
            "event_type": "PreToolUse",
            "tool_name": "Read",
            "category": "file_ops",
            "plugin": "core",
            "args": {"file_path": "/src/app.py"},
            "input_size": 23,
            "decision": "soft_deny",
            "handler": "scripts.routing.handlers.route_read_code",
            "handler_output": None,
            "latency_ms": 5,
            "session_id": "abc-123",
        }

        logger.append_entry(Path(temp_log_file), entry)

        # Read and parse the line
        with open(temp_log_file) as f:
            line = f.readline()

        parsed = json.loads(line)
        assert parsed == entry

    def test_append_entry_appends_not_overwrites(self, temp_log_file):
        """append_entry() appends to file, doesn't overwrite."""
        entry1 = {
            "ts": 1,
            "event_type": "PreToolUse",
            "tool_name": "Read",
            "category": "file_ops",
            "plugin": "core",
            "args": {},
            "input_size": 2,
            "decision": "pass",
            "handler": None,
            "handler_output": None,
            "latency_ms": 1,
            "session_id": "s1",
        }
        entry2 = {
            "ts": 2,
            "event_type": "PreToolUse",
            "tool_name": "Read",
            "category": "file_ops",
            "plugin": "core",
            "args": {},
            "input_size": 2,
            "decision": "pass",
            "handler": None,
            "handler_output": None,
            "latency_ms": 1,
            "session_id": "s2",
        }

        logger.append_entry(Path(temp_log_file), entry1)
        logger.append_entry(Path(temp_log_file), entry2)

        # Both entries should be in file
        with open(temp_log_file) as f:
            lines = f.readlines()

        assert len(lines) == 2
        assert json.loads(lines[0])["ts"] == 1
        assert json.loads(lines[1])["ts"] == 2

    def test_append_entry_creates_parent_dirs(self):
        """append_entry() creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "deep" / "nested" / "dir" / "log.jsonl"

            entry = {
                "ts": 1234567890,
                "event_type": "PreToolUse",
                "tool_name": "Read",
                "category": "file_ops",
                "plugin": "core",
                "args": {},
                "input_size": 2,
                "decision": "pass",
                "handler": None,
                "handler_output": None,
                "latency_ms": 1,
                "session_id": None,
            }

            logger.append_entry(log_path, entry)

            assert log_path.exists()
            # Verify content
            with open(log_path) as f:
                line = f.readline()
            assert json.loads(line)["ts"] == 1234567890


class TestMain:
    """Test the main orchestration function."""

    def test_main_orchestrates_full_pipeline(
        self,
        temp_log_file,
        sample_event,
        sample_classification,
        sample_routing_result,
    ):
        """main() orchestrates classify → route → build → append."""
        with patch("scripts.capture.logger.load_mappings") as mock_load, \
             patch("scripts.capture.logger.get_log_path") as mock_log_path, \
             patch("scripts.capture.logger.classify") as mock_classify, \
             patch("scripts.capture.logger.evaluate") as mock_evaluate, \
             patch("sys.stdin") as mock_stdin, \
             patch("scripts.capture.logger.append_entry") as mock_append:

            mock_stdin.readline.return_value = json.dumps(sample_event)
            mock_load.return_value = {"tools": {}, "mcp_prefixes": {}, "_fallback": {}, "routing": []}
            mock_log_path.return_value = Path(temp_log_file)
            mock_classify.return_value = sample_classification
            mock_evaluate.return_value = sample_routing_result

            exit_code = logger.main()

            # Verify the pipeline was called in order
            mock_load.assert_called_once()
            mock_classify.assert_called_once()
            mock_evaluate.assert_called_once()
            mock_append.assert_called_once()
            assert exit_code == 0

    def test_main_exits_zero_always(self, sample_event):
        """main() always exits 0, even on exception."""
        with patch("scripts.capture.logger.load_mappings") as mock_load, \
             patch("sys.stdin") as mock_stdin:

            mock_stdin.readline.return_value = json.dumps(sample_event)
            mock_load.side_effect = Exception("Simulated error")

            exit_code = logger.main()

            assert exit_code == 0

    def test_main_handles_malformed_stdin_gracefully(self):
        """main() handles malformed JSON stdin without exception."""
        with patch("sys.stdin") as mock_stdin, \
             patch("scripts.capture.logger.append_entry") as mock_append:

            mock_stdin.readline.return_value = "{ invalid json"

            exit_code = logger.main()

            # Should exit cleanly without writing entry
            assert exit_code == 0
            mock_append.assert_not_called()

    def test_main_skips_entry_on_classifier_error(self, sample_event):
        """main() skips entry if classifier raises, but still exits 0."""
        with patch("scripts.capture.logger.load_mappings") as mock_load, \
             patch("scripts.capture.logger.classify") as mock_classify, \
             patch("sys.stdin") as mock_stdin, \
             patch("scripts.capture.logger.append_entry") as mock_append:

            mock_stdin.readline.return_value = json.dumps(sample_event)
            mock_load.return_value = {"tools": {}, "mcp_prefixes": {}, "routing": []}
            mock_classify.side_effect = Exception("Classifier error")

            exit_code = logger.main()

            assert exit_code == 0
            mock_append.assert_not_called()

    def test_main_skips_entry_on_router_error(
        self,
        sample_event,
        sample_classification,
    ):
        """main() skips entry if router raises, but still exits 0."""
        with patch("scripts.capture.logger.load_mappings") as mock_load, \
             patch("scripts.capture.logger.classify") as mock_classify, \
             patch("scripts.capture.logger.evaluate") as mock_evaluate, \
             patch("sys.stdin") as mock_stdin, \
             patch("scripts.capture.logger.append_entry") as mock_append:

            mock_stdin.readline.return_value = json.dumps(sample_event)
            mock_load.return_value = {"tools": {}, "mcp_prefixes": {}, "routing": []}
            mock_classify.return_value = sample_classification
            mock_evaluate.side_effect = Exception("Router error")

            exit_code = logger.main()

            assert exit_code == 0
            mock_append.assert_not_called()

    def test_main_skips_entry_on_append_error(
        self,
        sample_event,
        sample_classification,
        sample_routing_result,
    ):
        """main() skips entry if append raises, but still exits 0."""
        with patch("scripts.capture.logger.load_mappings") as mock_load, \
             patch("scripts.capture.logger.classify") as mock_classify, \
             patch("scripts.capture.logger.evaluate") as mock_evaluate, \
             patch("sys.stdin") as mock_stdin, \
             patch("scripts.capture.logger.append_entry") as mock_append:

            mock_stdin.readline.return_value = json.dumps(sample_event)
            mock_load.return_value = {"tools": {}, "mcp_prefixes": {}, "routing": []}
            mock_classify.return_value = sample_classification
            mock_evaluate.return_value = sample_routing_result
            mock_append.side_effect = Exception("Append error")

            exit_code = logger.main()

            assert exit_code == 0
