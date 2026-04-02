"""Shared tool classification registry for Observatory reports.

Add new categories here to extend the classification set.
Index operations (index_folder, index_local) are intentionally excluded —
they are infrastructure calls, not content retrieval.
"""
from __future__ import annotations

CATEGORIES: dict[str, frozenset[str]] = {
    "Read": frozenset({
        "Read",
    }),
    "jCodeMunch": frozenset({
        "mcp__jcodemunch__get_file_content",
        "mcp__jcodemunch__get_symbol_source",
        "mcp__jcodemunch__get_symbol",
        "mcp__jcodemunch__search_symbols",
        "mcp__jcodemunch__get_file_outline",
        "mcp__jcodemunch__get_related_symbols",
        "mcp__jcodemunch__get_ranked_context",
        "mcp__jcodemunch__get_context_bundle",
        "mcp__jcodemunch__get_repo_outline",
        "mcp__jcodemunch__search_text",
        "mcp__jcodemunch__get_symbol_diff",
        "mcp__jcodemunch__get_symbol_importance",
        "mcp__jcodemunch__get_dependency_graph",
        "mcp__jcodemunch__get_blast_radius",
        "mcp__jcodemunch__find_references",
        "mcp__jcodemunch__find_dead_code",
        "mcp__jcodemunch__find_importers",
        "mcp__jcodemunch__check_references",
    }),
    "jDocMunch": frozenset({
        "mcp__jdocmunch__get_section",
        "mcp__jdocmunch__search_sections",
        "mcp__jdocmunch__get_toc",
        "mcp__jdocmunch__get_sections",
        "mcp__jdocmunch__get_toc_tree",
        "mcp__jdocmunch__get_document_outline",
        "mcp__jdocmunch__get_section_context",
    }),
}


def classify_tool(tool_name: str) -> str | None:
    """Return the category for a tool name, or None if untracked.

    Iterates CATEGORIES in insertion order — add higher-priority categories first.
    """
    for category, tools in CATEGORIES.items():
        if tool_name in tools:
            return category
    return None
