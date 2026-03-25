"""Tests for the classifier module.

Tests cover the resolution chain for classifying tool calls:
1. Exact match in mappings["tools"]
2. Longest matching prefix in mappings["mcp_prefixes"]
3. Fall back to mappings["_fallback"]
4. Hardcoded default if _fallback missing
"""

import json
from pathlib import Path

import pytest

from scripts.categorise.classifier import classify


@pytest.fixture
def minimal_mappings():
    """Minimal mappings dict for unit tests."""
    return {
        "tools": {
            "Read": {"category": "file_ops", "plugin": "core"},
            "Bash": {"category": "bash_exec", "plugin": "core"},
            "mcp__jcodemunch__search_symbols": {
                "category": "code_search",
                "plugin": "jcodemunch",
            },
        },
        "mcp_prefixes": {
            "mcp__jcodemunch__": {"category": "code_search", "plugin": "jcodemunch"},
            "mcp__jdocmunch__": {"category": "doc_read", "plugin": "jdocmunch"},
        },
        "_fallback": {"category": "unknown", "plugin": "unknown"},
    }


@pytest.fixture
def real_mappings():
    """Load the real mappings.json from the config directory."""
    config_path = Path(__file__).parent.parent / "config" / "mappings.json"
    with open(config_path) as f:
        return json.load(f)


class TestExactToolMatch:
    """Test exact matches in tools dict."""

    def test_exact_tool_match_read(self, minimal_mappings):
        """Exact match for Read tool."""
        result = classify("Read", minimal_mappings)
        assert result == {"category": "file_ops", "plugin": "core"}

    def test_exact_tool_match_bash(self, minimal_mappings):
        """Exact match for Bash tool."""
        result = classify("Bash", minimal_mappings)
        assert result == {"category": "bash_exec", "plugin": "core"}

    def test_exact_tool_match_real_mappings(self, real_mappings):
        """Exact match with real mappings.json."""
        result = classify("Read", real_mappings)
        assert result == {"category": "file_ops", "plugin": "core"}


class TestMCPPrefixMatch:
    """Test prefix matching for MCP tools."""

    def test_mcp_prefix_match_jcodemunch(self, minimal_mappings):
        """Prefix match for mcp__jcodemunch__ tools."""
        result = classify("mcp__jcodemunch__get_file", minimal_mappings)
        assert result == {"category": "code_search", "plugin": "jcodemunch"}

    def test_mcp_prefix_match_jdocmunch(self, minimal_mappings):
        """Prefix match for mcp__jdocmunch__ tools."""
        result = classify("mcp__jdocmunch__search_sections", minimal_mappings)
        assert result == {"category": "doc_read", "plugin": "jdocmunch"}

    def test_mcp_prefix_match_real_mappings(self, real_mappings):
        """Prefix match with real mappings.json."""
        result = classify("mcp__jcodemunch__get_file", real_mappings)
        assert result == {"category": "code_search", "plugin": "jcodemunch"}


class TestExactBeatsPrefix:
    """Test that exact matches take precedence over prefix matches."""

    def test_exact_beats_prefix(self, minimal_mappings):
        """Exact match in tools dict wins over prefix match."""
        # mcp__jcodemunch__search_symbols is in both tools (exact) and mcp_prefixes (prefix)
        result = classify("mcp__jcodemunch__search_symbols", minimal_mappings)
        assert result == {"category": "code_search", "plugin": "jcodemunch"}

    def test_exact_beats_prefix_real_mappings(self, real_mappings):
        """Exact match wins with real mappings.json."""
        result = classify("mcp__jcodemunch__search_symbols", real_mappings)
        assert result == {"category": "code_search", "plugin": "jcodemunch"}


class TestLongestPrefixWins:
    """Test that the longest matching prefix is used."""

    def test_longer_prefix_wins(self):
        """Longer prefix takes precedence over shorter prefix."""
        mappings = {
            "tools": {},
            "mcp_prefixes": {
                "mcp__foo__": {"category": "foo", "plugin": "foo"},
                "mcp__foo__bar__": {"category": "bar", "plugin": "bar"},
            },
            "_fallback": {"category": "unknown", "plugin": "unknown"},
        }
        # mcp__foo__bar__baz matches both prefixes, longer one should win
        result = classify("mcp__foo__bar__baz", mappings)
        assert result == {"category": "bar", "plugin": "bar"}

    def test_longer_prefix_wins_with_three_levels(self):
        """Test with three prefix levels."""
        mappings = {
            "tools": {},
            "mcp_prefixes": {
                "mcp__a__": {"category": "a", "plugin": "a"},
                "mcp__a__b__": {"category": "b", "plugin": "b"},
                "mcp__a__b__c__": {"category": "c", "plugin": "c"},
            },
            "_fallback": {"category": "unknown", "plugin": "unknown"},
        }
        result = classify("mcp__a__b__c__tool", mappings)
        assert result == {"category": "c", "plugin": "c"}


class TestFallbackBehavior:
    """Test fallback and default behavior."""

    def test_unknown_tool_uses_fallback(self, minimal_mappings):
        """Unknown tool falls back to _fallback."""
        result = classify("UnknownTool", minimal_mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}

    def test_missing_fallback_uses_hardcoded_default(self):
        """No _fallback key returns hardcoded default."""
        mappings = {
            "tools": {"Read": {"category": "file_ops", "plugin": "core"}},
            "mcp_prefixes": {},
        }
        result = classify("UnknownTool", mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}

    def test_fallback_with_extra_fields_ignored(self):
        """Extra fields in _fallback are not included in result."""
        mappings = {
            "tools": {},
            "mcp_prefixes": {},
            "_fallback": {
                "category": "unknown",
                "plugin": "unknown",
                "decision": "pass",
                "extra_field": "ignored",
            },
        }
        result = classify("UnknownTool", mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}
        assert "decision" not in result
        assert "extra_field" not in result


class TestReturnFormat:
    """Test return value format."""

    def test_returns_only_category_and_plugin(self, minimal_mappings):
        """Result dict contains only category and plugin keys."""
        result = classify("Read", minimal_mappings)
        assert set(result.keys()) == {"category", "plugin"}
        assert len(result) == 2

    def test_returns_only_category_and_plugin_prefix_match(self, minimal_mappings):
        """Prefix match result has only category and plugin."""
        result = classify("mcp__jcodemunch__get_file", minimal_mappings)
        assert set(result.keys()) == {"category", "plugin"}

    def test_returns_dict_type(self, minimal_mappings):
        """Result is always a dict."""
        result = classify("Read", minimal_mappings)
        assert isinstance(result, dict)


class TestIntegrationWithRealConfig:
    """Integration tests using real config/mappings.json."""

    def test_real_config_read_tool(self, real_mappings):
        """Test Read tool from real config."""
        result = classify("Read", real_mappings)
        assert result == {"category": "file_ops", "plugin": "core"}

    def test_real_config_bash_tool(self, real_mappings):
        """Test Bash tool from real config."""
        result = classify("Bash", real_mappings)
        assert result == {"category": "bash_exec", "plugin": "core"}

    def test_real_config_glob_tool(self, real_mappings):
        """Test Glob tool from real config."""
        result = classify("Glob", real_mappings)
        assert result == {"category": "file_ops", "plugin": "core"}

    def test_real_config_websearch_tool(self, real_mappings):
        """Test WebSearch tool from real config."""
        result = classify("WebSearch", real_mappings)
        assert result == {"category": "web_search", "plugin": "core"}

    def test_real_config_jcodemunch_exact(self, real_mappings):
        """Test mcp__jcodemunch__search_symbols exact match."""
        result = classify("mcp__jcodemunch__search_symbols", real_mappings)
        assert result == {"category": "code_search", "plugin": "jcodemunch"}

    def test_real_config_jcodemunch_prefix(self, real_mappings):
        """Test mcp__jcodemunch__ prefix match."""
        result = classify("mcp__jcodemunch__get_file", real_mappings)
        assert result == {"category": "code_search", "plugin": "jcodemunch"}

    def test_real_config_jdocmunch_prefix(self, real_mappings):
        """Test mcp__jdocmunch__ prefix match."""
        result = classify("mcp__jdocmunch__search_sections", real_mappings)
        assert result == {"category": "doc_read", "plugin": "jdocmunch"}

    def test_real_config_exa_prefix(self, real_mappings):
        """Test mcp__exa__ prefix match."""
        result = classify("mcp__exa__search", real_mappings)
        assert result == {"category": "web_search", "plugin": "exa"}

    def test_real_config_context7_prefix(self, real_mappings):
        """Test mcp__context7__ prefix match."""
        result = classify("mcp__context7__lookup", real_mappings)
        assert result == {"category": "doc_read", "plugin": "context7"}

    def test_real_config_unknown_tool(self, real_mappings):
        """Test unknown tool with real config."""
        result = classify("NonExistentTool", real_mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_tool_name(self, minimal_mappings):
        """Empty tool name falls back to default."""
        result = classify("", minimal_mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}

    def test_tool_name_none_raises_error(self, minimal_mappings):
        """None as tool name should raise TypeError."""
        with pytest.raises(TypeError):
            classify(None, minimal_mappings)

    def test_case_sensitive_matching(self, minimal_mappings):
        """Tool name matching is case-sensitive."""
        result = classify("read", minimal_mappings)  # lowercase, not "Read"
        assert result == {"category": "unknown", "plugin": "unknown"}

    def test_prefix_requires_exact_boundary(self, minimal_mappings):
        """Prefix must match exactly at tool name boundaries."""
        # "mcp__jcodemu nch__" is a prefix, but "mcp__jcodemuunch" doesn't start with it
        result = classify("mcp__jcodemuunch__get_file", minimal_mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}

    def test_empty_mappings_dict(self):
        """Empty mappings dict returns hardcoded default."""
        mappings = {}
        result = classify("AnyTool", mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}

    def test_mappings_with_none_values(self):
        """Graceful handling of None in mappings."""
        mappings = {
            "tools": None,
            "mcp_prefixes": None,
            "_fallback": {"category": "unknown", "plugin": "unknown"},
        }
        result = classify("AnyTool", mappings)
        assert result == {"category": "unknown", "plugin": "unknown"}


class TestTypeValidation:
    """Test type validation and error handling."""

    def test_mappings_none_raises_error(self):
        """None as mappings should raise TypeError."""
        with pytest.raises(TypeError):
            classify("Read", None)

    def test_tool_name_as_integer_raises_error(self, minimal_mappings):
        """Integer tool name should raise TypeError."""
        with pytest.raises(TypeError):
            classify(123, minimal_mappings)
