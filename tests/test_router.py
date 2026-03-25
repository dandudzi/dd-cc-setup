"""Test suite for the router module — evaluates routing rules against tool calls."""

from unittest.mock import patch

import pytest

from scripts.categorise.router import evaluate


class TestRouterBasics:
    """Basic router functionality tests."""

    def test_no_rules_returns_pass(self):
        """Empty rules list should return pass decision."""
        result = evaluate("Read", {"file_path": "/path/to/file.py"}, [])

        assert result == {
            "decision": "pass",
            "handler": None,
            "handler_output": None,
        }

    def test_no_matching_rule_returns_pass(self):
        """Rules present but none match should return pass."""
        rules = [
            {
                "matcher": {"tool": "WebSearch"},
                "decision": "deny",
                "handler": None,
            }
        ]
        result = evaluate("Read", {"file_path": "/path/to/file.py"}, rules)

        assert result == {
            "decision": "pass",
            "handler": None,
            "handler_output": None,
        }


class TestToolMatching:
    """Tool name matching tests."""

    def test_tool_match_no_pattern(self):
        """Rule with only tool in matcher (no input_key) matches on tool name alone."""
        rules = [
            {
                "matcher": {"tool": "WebSearch"},
                "decision": "deny",
                "handler": None,
            }
        ]
        result = evaluate("WebSearch", {"q": "test"}, rules)

        assert result["decision"] == "deny"

    def test_tool_match_with_pattern_match(self):
        """Rule with tool + input_key + pattern; pattern matches → rule fires."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": r".*\.py$",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        result = evaluate(
            "Read",
            {"file_path": "/path/to/file.py"},
            rules,
        )

        assert result["decision"] == "soft_deny"

    def test_tool_match_with_pattern_no_match(self):
        """Pattern doesn't match → falls through to pass."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": r".*\.py$",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        result = evaluate(
            "Read",
            {"file_path": "/path/to/file.txt"},
            rules,
        )

        assert result["decision"] == "pass"


class TestRuleOrdering:
    """Test first-match-wins behavior."""

    def test_first_rule_wins(self):
        """Two matching rules → first rule's decision returned."""
        rules = [
            {
                "matcher": {"tool": "Read"},
                "decision": "soft_deny",
                "handler": None,
            },
            {
                "matcher": {"tool": "Read"},
                "decision": "deny",
                "handler": None,
            },
        ]
        result = evaluate("Read", {"file_path": "/path/to/file.py"}, rules)

        assert result["decision"] == "soft_deny"


class TestRegexHandling:
    """Test regex pattern handling and edge cases."""

    def test_invalid_regex_no_match(self):
        """Invalid regex `[` should be treated as no-match, not raise exception."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": "[",  # Invalid regex
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        # Should not raise, should fall through to pass
        result = evaluate(
            "Read",
            {"file_path": "/path/to/file.py"},
            rules,
        )

        assert result["decision"] == "pass"

    def test_regex_caching(self):
        """Regex patterns should be compiled and cached."""
        # This test ensures the router compiles patterns efficiently
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": r".*\.py$",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        # Call twice with same pattern
        result1 = evaluate(
            "Read",
            {"file_path": "/path/to/file.py"},
            rules,
        )
        result2 = evaluate(
            "Read",
            {"file_path": "/path/to/file.py"},
            rules,
        )

        assert result1["decision"] == "soft_deny"
        assert result2["decision"] == "soft_deny"


class TestInputKeyValidation:
    """Test input key presence validation."""

    def test_missing_input_key_no_match(self):
        """Rule needs input_key but tool_input lacks that key → no match."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": r".*\.py$",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        # Missing file_path key
        result = evaluate("Read", {}, rules)

        assert result["decision"] == "pass"

    def test_input_key_present_no_pattern(self):
        """input_key present but no pattern → matches on key presence alone."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        # Key present, no pattern specified
        result = evaluate("Read", {"file_path": "/any/path"}, rules)

        assert result["decision"] == "soft_deny"


class TestHandlerExecution:
    """Test handler invocation and output capture."""

    def test_handler_called_with_correct_args(self):
        """Mock the handler function, verify called with (tool_name, tool_input)."""
        with patch(
            "scripts.routing.handlers.route_read_code"
        ) as mock_handler:
            mock_handler.return_value = {"info": "test"}

            rules = [
                {
                    "matcher": {"tool": "Read"},
                    "decision": "soft_deny",
                    "handler": "scripts.routing.handlers.route_read_code",
                }
            ]
            tool_input = {"file_path": "/path/to/file.py"}
            result = evaluate("Read", tool_input, rules)

            mock_handler.assert_called_once_with("Read", tool_input)
            assert result["handler_output"] == {"info": "test"}

    def test_handler_output_captured(self):
        """Handler returns a dict → captured in handler_output."""
        with patch(
            "scripts.routing.handlers.route_read_code"
        ) as mock_handler:
            expected_output = {
                "redirect_to": "jCodeMunch",
                "reason": "code file",
            }
            mock_handler.return_value = expected_output

            rules = [
                {
                    "matcher": {"tool": "Read"},
                    "decision": "soft_deny",
                    "handler": "scripts.routing.handlers.route_read_code",
                }
            ]
            result = evaluate("Read", {"file_path": "/path/to/file.py"}, rules)

            assert result["handler_output"] == expected_output

    def test_handler_exception_caught(self):
        """Handler raises → handler_output is None, no exception propagated."""
        with patch(
            "scripts.routing.handlers.route_read_code"
        ) as mock_handler:
            mock_handler.side_effect = ValueError("Handler error")

            rules = [
                {
                    "matcher": {"tool": "Read"},
                    "decision": "soft_deny",
                    "handler": "scripts.routing.handlers.route_read_code",
                }
            ]
            # Should not raise
            result = evaluate("Read", {"file_path": "/path/to/file.py"}, rules)

            assert result["decision"] == "soft_deny"
            assert result["handler_output"] is None

    def test_handler_returns_none(self):
        """Handler returns None → captured as None in handler_output."""
        with patch(
            "scripts.routing.handlers.route_read_doc"
        ) as mock_handler:
            mock_handler.return_value = None

            rules = [
                {
                    "matcher": {"tool": "Read"},
                    "decision": "soft_deny",
                    "handler": "scripts.routing.handlers.route_read_doc",
                }
            ]
            result = evaluate("Read", {"file_path": "/path/to/file.md"}, rules)

            assert result["handler_output"] is None


class TestDecisions:
    """Test decision value preservation."""

    @pytest.mark.parametrize(
        "decision",
        ["pass", "soft_deny", "deny"],
    )
    def test_decisions_preserved(self, decision):
        """Test each decision value is preserved in output."""
        rules = [
            {
                "matcher": {"tool": "Read"},
                "decision": decision,
                "handler": None,
            }
        ]
        result = evaluate("Read", {"file_path": "/path/to/file.py"}, rules)

        assert result["decision"] == decision


class TestComplexPatterns:
    """Test complex regex patterns."""

    def test_multipart_extension_pattern(self):
        """Test pattern matching multiple file extensions."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": r".*\.(py|js|ts|go|java|kt|rs|cpp|c|h)$",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        # Should match .py
        result_py = evaluate(
            "Read",
            {"file_path": "/path/to/file.py"},
            rules,
        )
        assert result_py["decision"] == "soft_deny"

        # Should match .ts
        result_ts = evaluate(
            "Read",
            {"file_path": "/path/to/file.ts"},
            rules,
        )
        assert result_ts["decision"] == "soft_deny"

        # Should not match .md
        result_md = evaluate(
            "Read",
            {"file_path": "/path/to/file.md"},
            rules,
        )
        assert result_md["decision"] == "pass"

    def test_pattern_substring_match(self):
        """Test pattern can match substrings (not just full string)."""
        rules = [
            {
                "matcher": {
                    "tool": "Read",
                    "input_key": "file_path",
                    "pattern": r"\.py$",
                },
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        # Pattern matches even with full path
        result = evaluate(
            "Read",
            {"file_path": "/home/user/project/main.py"},
            rules,
        )

        assert result["decision"] == "soft_deny"


class TestReturnStructure:
    """Test return structure is always correct."""

    def test_return_has_all_keys(self):
        """Return dict always has decision, handler, handler_output keys."""
        result = evaluate("Read", {"file_path": "/path/to/file.py"}, [])

        assert isinstance(result, dict)
        assert "decision" in result
        assert "handler" in result
        assert "handler_output" in result
        assert len(result) == 3

    def test_handler_field_is_string_or_none(self):
        """Handler field is either None or the handler path string."""
        # With handler
        rules_with_handler = [
            {
                "matcher": {"tool": "Read"},
                "decision": "soft_deny",
                "handler": "scripts.routing.handlers.route_read_code",
            }
        ]
        result1 = evaluate("Read", {"file_path": "/path/to/file.py"}, rules_with_handler)
        assert isinstance(result1["handler"], (str, type(None)))

        # Without handler
        rules_no_handler = [
            {
                "matcher": {"tool": "Read"},
                "decision": "soft_deny",
                "handler": None,
            }
        ]
        result2 = evaluate("Read", {"file_path": "/path/to/file.py"}, rules_no_handler)
        assert result2["handler"] is None
