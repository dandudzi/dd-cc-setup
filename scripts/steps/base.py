"""Built-in step functions for the observability pipeline."""

from __future__ import annotations

from pathlib import Path


def _clone(context: dict, **updates: object) -> dict:
    result = dict(context)
    result.update(updates)
    return result


def _append_error(context: dict, message: str) -> dict:
    errors = list(context.get("errors", []))
    errors.append(message)
    return _clone(context, errors=errors)


def _redirect_for_read(context: dict) -> str:
    file_path = context.get("tool_input", {}).get("file_path", "")
    ext = (context.get("file_ext") or Path(file_path).suffix.lower()).lower()
    if ext in {".md", ".mdx", ".rst", ".txt", ".adoc", ".org"}:
        return "mcp__jdocmunch__get_file_content"
    if ext in {
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        ".csv", ".tsv", ".xml", ".log", ".jsonl", ".env",
    }:
        return "ctx_execute_file"
    return "mcp__jcodemunch__get_file_content"


def check_code_index_fresh(context: dict) -> dict:
    """Record code index freshness; default to fresh in observe-only mode."""
    is_fresh = context.get("index_fresh")
    if is_fresh is None:
        is_fresh = True
    return _clone(context, index_fresh=bool(is_fresh))


def check_doc_index_fresh(context: dict) -> dict:
    """Record doc index freshness; default to fresh in observe-only mode."""
    is_fresh = context.get("index_fresh")
    if is_fresh is None:
        is_fresh = True
    return _clone(context, index_fresh=bool(is_fresh))


def enrich_file_metadata(context: dict) -> dict:
    """Add file extension and size when the target path exists."""
    file_path = context.get("tool_input", {}).get("file_path")
    if not file_path:
        return context

    path = Path(file_path)
    updated = {"file_ext": path.suffix.lower()}
    try:
        updated["file_size"] = path.stat().st_size
    except OSError:
        updated["file_size"] = context.get("file_size")
        return _append_error(_clone(context, **updated), f"unable to stat file: {file_path}")

    return _clone(context, **updated)


def soft_deny_redirect(context: dict) -> dict:
    """Set an observe-only soft deny decision plus redirect target."""
    return _clone(
        context,
        decision="soft_deny",
        redirect_to=context.get("redirect_to") or _redirect_for_read(context),
    )


def hard_deny(context: dict) -> dict:
    """Set a hard deny decision while still exiting 0 in Phase 1."""
    redirect_to = context.get("redirect_to")
    tool_name = context.get("tool_name")
    if not redirect_to:
        if tool_name == "WebSearch":
            redirect_to = "mcp__exa__web_search_exa"
        elif tool_name == "WebFetch":
            redirect_to = "ctx_fetch_and_index"
    return _clone(context, decision="hard_deny", redirect_to=redirect_to)


def redirect_to_context_mode(context: dict) -> dict:
    """Route large-output commands to context-mode."""
    return _clone(context, decision="soft_deny", redirect_to="ctx_execute")


def format_deny_message(context: dict) -> dict:
    """Attach a human-readable deny message for file redirects."""
    file_path = context.get("tool_input", {}).get("file_path", "")
    redirect_to = context.get("redirect_to", "alternative tool")
    message = (
        f"BLOCKED: Use {redirect_to} instead of {context.get('tool_name')} "
        f"for {file_path or 'this file'}."
    )
    if file_path:
        message += f'\nSuggested: {redirect_to} with file_path="{file_path}"'
    return _clone(context, _stderr_message=message)


def format_redirect_message(context: dict) -> dict:
    """Attach a generic redirect suggestion message."""
    redirect_to = context.get("redirect_to", "alternative tool")
    message = f"Suggested: {redirect_to}"
    command = context.get("tool_input", {}).get("command")
    file_path = context.get("tool_input", {}).get("file_path")
    if command:
        message += f' for command="{command}"'
    elif file_path:
        message += f' for file_path="{file_path}"'
    return _clone(context, _stderr_message=message)


def format_exa_redirect(context: dict) -> dict:
    """Attach the canonical Exa MCP redirect for WebSearch."""
    return _clone(
        context,
        redirect_to=context.get("redirect_to") or "mcp__exa__web_search_exa",
        _stderr_message="BLOCKED: Use mcp__exa__web_search_exa instead of WebSearch.",
    )


def format_context_mode_web_redirect(context: dict) -> dict:
    """Attach the canonical context-mode redirect for WebFetch."""
    return _clone(
        context,
        redirect_to=context.get("redirect_to") or "ctx_fetch_and_index",
        _stderr_message="BLOCKED: Use ctx_fetch_and_index instead of WebFetch.",
    )


def pass_through(context: dict) -> dict:
    """Explicit no-op step for simple routes."""
    return _clone(context, decision="pass")
