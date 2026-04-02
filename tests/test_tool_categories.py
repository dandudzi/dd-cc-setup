"""Tests for scripts/observatory/data/tool_categories.py — shared tool classification registry."""
from __future__ import annotations

import pytest

from scripts.observatory.data.tool_categories import CATEGORIES, classify_tool


class TestCategories:
    def test_read_category_exists(self):
        assert "Read" in CATEGORIES

    def test_jcodemunch_category_exists(self):
        assert "jCodeMunch" in CATEGORIES

    def test_jdocmunch_category_exists(self):
        assert "jDocMunch" in CATEGORIES

    def test_all_values_are_frozensets(self):
        for name, tools in CATEGORIES.items():
            assert isinstance(tools, frozenset), f"{name} should be a frozenset"

    def test_no_tool_appears_in_multiple_categories(self):
        seen: dict[str, str] = {}
        for category, tools in CATEGORIES.items():
            for tool in tools:
                assert tool not in seen, (
                    f"{tool!r} appears in both {seen[tool]!r} and {category!r}"
                )
                seen[tool] = category


class TestClassifyTool:
    def test_read_returns_read(self):
        assert classify_tool("Read") == "Read"

    def test_jcodemunch_retrieval_tool(self):
        assert classify_tool("mcp__jcodemunch__get_file_content") == "jCodeMunch"

    def test_jcodemunch_search_symbols(self):
        assert classify_tool("mcp__jcodemunch__search_symbols") == "jCodeMunch"

    def test_jdocmunch_retrieval_tool(self):
        assert classify_tool("mcp__jdocmunch__get_section") == "jDocMunch"

    def test_jdocmunch_search_sections(self):
        assert classify_tool("mcp__jdocmunch__search_sections") == "jDocMunch"

    def test_unknown_tool_returns_none(self):
        assert classify_tool("Bash") is None

    def test_index_operations_return_none(self):
        assert classify_tool("mcp__jcodemunch__index_folder") is None
        assert classify_tool("mcp__jdocmunch__index_local") is None

    def test_empty_string_returns_none(self):
        assert classify_tool("") is None
