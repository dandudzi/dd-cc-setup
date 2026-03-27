"""Built-in matcher functions for the observability pipeline."""

from __future__ import annotations

import re
from pathlib import Path

CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsonnet",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
DOC_EXTENSIONS = {
    ".adoc",
    ".md",
    ".mdx",
    ".org",
    ".pdf",
    ".rst",
    ".rtf",
    ".text",
    ".txt",
}
DATA_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".csv",
    ".env",
    ".ini",
    ".json",
    ".jsonl",
    ".log",
    ".toml",
    ".tsv",
    ".xml",
    ".yaml",
    ".yml",
}
UNBOUNDED_BASH_TOKENS = {
    "cat",
    "find",
    "git diff",
    "git log",
    "grep",
    "head",
    "jq",
    "ls -R",
    "npm test",
    "pytest",
    "rg",
    "tail",
}


def _file_path_from_context(context: dict) -> Path | None:
    path = context.get("tool_input", {}).get("file_path")
    if not path:
        return None
    return Path(path)


def _line_count(path: Path) -> int | None:
    try:
        with path.open() as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def is_code_file(context: dict) -> bool:
    """Match source-code reads by file extension."""
    path = _file_path_from_context(context)
    return bool(path and path.suffix.lower() in CODE_EXTENSIONS)


def is_doc_file(context: dict) -> bool:
    """Match documentation reads by file extension."""
    path = _file_path_from_context(context)
    return bool(path and path.suffix.lower() in DOC_EXTENSIONS)


def is_large_data_file(context: dict) -> bool:
    """Match data/config files that are likely too large for raw Read."""
    path = _file_path_from_context(context)
    if not path or path.suffix.lower() not in DATA_EXTENSIONS:
        return False

    line_count = _line_count(path)
    return bool(line_count and line_count > 100)


def is_unbounded_bash(context: dict) -> bool:
    """Match shell commands that are likely to emit large output.

    Uses word-boundary regex matching for single-word tokens to avoid
    false positives (e.g., 'cat' matching 'category'). Multi-word tokens
    like 'git diff' and 'npm test' use substring matching since spaces
    act as natural separators.
    """
    command = context.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        return False

    normalized = " ".join(command.split())

    # Single-word tokens: use word-boundary regex to avoid false positives
    single_word_tokens = {"cat", "find", "grep", "head", "jq", "pytest", "rg", "tail"}
    for token in single_word_tokens:
        pattern = re.compile(rf"\b{re.escape(token)}\b")
        if pattern.search(normalized):
            return True

    # Multi-word tokens: use substring matching (spaces are natural separators)
    multi_word_tokens = {"git diff", "git log", "ls -R", "npm test"}
    if any(token in normalized for token in multi_word_tokens):
        return True

    return False


def always(_: dict) -> bool:
    """Matcher used for unconditional routes."""
    return True
