"""Tests for built-in pipeline step functions."""

from pathlib import Path

from scripts.steps import (
    check_code_index_fresh,
    check_doc_index_fresh,
    enrich_file_metadata,
    format_context_mode_web_redirect,
    format_deny_message,
    format_exa_redirect,
    format_redirect_message,
    hard_deny,
    pass_through,
    redirect_to_context_mode,
    soft_deny_redirect,
)


def _context(**overrides):
    base = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/app.py"},
        "decision": "pass",
        "errors": [],
    }
    base.update(overrides)
    return base


def test_check_code_index_fresh_defaults_true():
    assert check_code_index_fresh(_context())["index_fresh"] is True


def test_check_doc_index_fresh_preserves_false():
    assert check_doc_index_fresh(_context(index_fresh=False))["index_fresh"] is False


def test_enrich_file_metadata_sets_size_and_extension(tmp_path: Path):
    path = tmp_path / "app.py"
    path.write_text("print('x')\n")
    result = enrich_file_metadata(_context(tool_input={"file_path": str(path)}))
    assert result["file_ext"] == ".py"
    assert result["file_size"] == path.stat().st_size


def test_soft_deny_redirect_sets_decision_and_default_target():
    result = soft_deny_redirect(_context(tool_input={"file_path": "/tmp/app.py"}))
    assert result["decision"] == "soft_deny"
    assert result["redirect_to"] == "mcp__jcodemunch__get_file_content"


def test_redirect_to_context_mode_sets_ctx_execute():
    ctx = _context(tool_name="Bash", tool_input={"command": "rg foo ."})
    result = redirect_to_context_mode(ctx)
    assert result["decision"] == "soft_deny"
    assert result["redirect_to"] == "ctx_execute"


def test_hard_deny_sets_default_redirect():
    result = hard_deny(_context(tool_name="WebSearch", tool_input={}))
    assert result["decision"] == "hard_deny"
    assert result["redirect_to"] == "mcp__exa__web_search_exa"


def test_format_deny_message_mentions_file_path():
    result = format_deny_message(_context(redirect_to="mcp__jcodemunch__get_file_content"))
    assert "BLOCKED" in result["_stderr_message"]
    assert 'file_path="/tmp/app.py"' in result["_stderr_message"]


def test_format_redirect_message_includes_command():
    ctx = _context(
        tool_name="Bash",
        tool_input={"command": "rg foo ."},
        redirect_to="ctx_execute",
    )
    result = format_redirect_message(ctx)
    assert (
        result["_stderr_message"]
        == 'Suggested: ctx_execute for command="rg foo ."'
    )


def test_format_exa_redirect_sets_canonical_message():
    result = format_exa_redirect(_context(tool_name="WebSearch", tool_input={}))
    assert result["redirect_to"] == "mcp__exa__web_search_exa"
    assert "mcp__exa__web_search_exa" in result["_stderr_message"]


def test_format_context_mode_web_redirect_sets_canonical_message():
    result = format_context_mode_web_redirect(_context(tool_name="WebFetch", tool_input={}))
    assert result["redirect_to"] == "ctx_fetch_and_index"
    assert "ctx_fetch_and_index" in result["_stderr_message"]


def test_pass_through_forces_pass():
    assert pass_through(_context(decision="hard_deny"))["decision"] == "pass"


def test_check_code_does_not_set_check_failed():
    result = check_code_index_fresh(_context())
    assert "_check_failed" not in result


def test_check_code_returns_dict():
    assert isinstance(check_code_index_fresh(_context()), dict)


def test_check_doc_sets_index_fresh_true_when_none():
    # When index_fresh not set, stub defaults to True
    ctx = {k: v for k, v in _context().items() if k != "index_fresh"}
    result = check_doc_index_fresh(ctx)
    assert result["index_fresh"] is True


def test_check_doc_does_not_set_check_failed():
    result = check_doc_index_fresh(_context())
    assert "_check_failed" not in result


def test_enrich_file_not_found_leaves_size_none():
    result = enrich_file_metadata(_context(tool_input={"file_path": "/nonexistent/path/app.py"}))
    assert result["file_ext"] == ".py"
    assert result["file_size"] is None


def test_enrich_no_file_path_leaves_both_none():
    result = enrich_file_metadata(_context(tool_input={}))
    assert result.get("file_ext") is None
    assert result.get("file_size") is None


def test_soft_deny_does_not_change_other_keys():
    ctx = _context(my_custom_key="preserved")
    result = soft_deny_redirect(ctx)
    assert result["my_custom_key"] == "preserved"


def test_format_deny_message_contains_redirect():
    result = format_deny_message(_context(redirect_to="mcp__jcodemunch__get_file_content"))
    msg = result["_stderr_message"]
    assert "jcodemunch" in msg.lower() or "mcp__jcodemunch__get_file_content" in msg


def test_format_deny_message_without_redirect():
    ctx = _context()
    ctx.pop("redirect_to", None)
    result = format_deny_message(ctx)
    assert "_stderr_message" in result
    assert result["_stderr_message"]  # non-empty


def test_format_context_mode_web_redirect_includes_url():
    ctx = _context(tool_name="WebFetch", tool_input={"url": "https://example.com/api/docs"})
    result = format_context_mode_web_redirect(ctx)
    # Canonical message is always the same regardless of URL
    assert "ctx_fetch_and_index" in result["_stderr_message"]
    assert result["redirect_to"] == "ctx_fetch_and_index"


def test_pass_through_returns_context_unchanged():
    ctx = _context(some_key="some_value")
    result = pass_through(ctx)
    assert result["some_key"] == "some_value"
    assert result["decision"] == "pass"
