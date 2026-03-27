"""Tests for built-in matcher functions."""

from pathlib import Path

import pytest

from scripts.matchers import (
    always,
    is_code_file,
    is_doc_file,
    is_large_data_file,
    is_unbounded_bash,
)


def _context(**overrides):
    base = {"tool_input": {}}
    base.update(overrides)
    return base


def test_is_code_file_matches_source_extensions():
    assert is_code_file(_context(tool_input={"file_path": "/tmp/app.py"})) is True
    assert is_code_file(_context(tool_input={"file_path": "/tmp/readme.md"})) is False


def test_is_doc_file_matches_document_extensions():
    assert is_doc_file(_context(tool_input={"file_path": "/tmp/guide.md"})) is True
    assert is_doc_file(_context(tool_input={"file_path": "/tmp/app.ts"})) is False


def test_is_large_data_file_requires_data_extension_and_more_than_100_lines(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text("\n".join(f"line-{idx}" for idx in range(101)))
    assert is_large_data_file(_context(tool_input={"file_path": str(path)})) is True


def test_is_large_data_file_returns_false_for_small_file(tmp_path: Path):
    path = tmp_path / "data.yaml"
    path.write_text("a: 1\nb: 2\n")
    assert is_large_data_file(_context(tool_input={"file_path": str(path)})) is False


def test_is_unbounded_bash_uses_command_heuristics():
    assert is_unbounded_bash(_context(tool_input={"command": "rg TODO ."})) is True
    assert is_unbounded_bash(_context(tool_input={"command": "echo ok"})) is False


def test_always_matcher():
    assert always({}) is True


@pytest.mark.parametrize(
    "ext",
    [
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".java",
        ".kt",
        ".rs",
        ".cpp",
        ".c",
        ".h",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".scala",
        ".sh",
        ".sql",
        ".vue",
        ".lua",
    ],
)
def test_is_code_file_parametrized(ext):
    ctx = _context(tool_input={"file_path": f"/tmp/app{ext}"})
    assert is_code_file(ctx) is True


@pytest.mark.parametrize("ext", [".md", ".txt", ".rst"])
def test_is_code_file_false_for_non_code(ext):
    ctx = _context(tool_input={"file_path": f"/tmp/file{ext}"})
    assert is_code_file(ctx) is False


def test_is_code_file_no_file_path():
    assert is_code_file(_context(tool_input={})) is False


def test_is_code_file_case_insensitive():
    assert is_code_file(_context(tool_input={"file_path": "/tmp/app.PY"})) is True


@pytest.mark.parametrize("ext", [".md", ".mdx", ".rst", ".txt", ".adoc"])
def test_is_doc_file_parametrized(ext):
    ctx = _context(tool_input={"file_path": f"/tmp/guide{ext}"})
    assert is_doc_file(ctx) is True


@pytest.mark.parametrize("ext", [".py", ".go", ".exe"])
def test_is_doc_file_false_for_non_doc(ext):
    ctx = _context(tool_input={"file_path": f"/tmp/file{ext}"})
    assert is_doc_file(ctx) is False


def test_is_doc_file_no_file_path():
    assert is_doc_file(_context(tool_input={})) is False


def test_large_data_code_file_not_matched(tmp_path: Path):
    # .py is in CODE_EXTENSIONS but NOT DATA_EXTENSIONS — large .py should not match
    path = tmp_path / "big.py"
    path.write_text("\n".join(f"line-{i}" for i in range(200)))
    assert is_large_data_file(_context(tool_input={"file_path": str(path)})) is False


def test_large_data_file_missing():
    path = "/tmp/nonexistent-xyzabc.json"
    assert is_large_data_file(_context(tool_input={"file_path": path})) is False


def test_large_data_no_file_path():
    assert is_large_data_file(_context(tool_input={})) is False


@pytest.mark.parametrize(
    "cmd",
    [
        "find . -name *.py",
        "cat /etc/passwd",
        "git log --oneline",
        "grep -r TODO",
        "pytest tests/",
        "rg foo .",
        "head -100 file.log",
        "tail -f app.log",
    ],
)
def test_unbounded_bash_parametrized(cmd):
    assert is_unbounded_bash(_context(tool_input={"command": cmd})) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "git status",
        "git add .",
        "mkdir -p /tmp/foo",
        "rm -f /tmp/x",
        "echo hello",
        "uv sync",
        "python --version",
        "git commit -m 'msg'",
    ],
)
def test_bounded_bash_parametrized(cmd):
    assert is_unbounded_bash(_context(tool_input={"command": cmd})) is False


def test_unbounded_bash_no_command():
    assert is_unbounded_bash(_context(tool_input={})) is False


def test_always_with_populated_dict():
    assert always({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.py"}}) is True


# Finding 6: yaml/toml/xml extension overlap fix tests
def test_is_code_file_excludes_yaml():
    """YAML is a data/config format, not code."""
    assert is_code_file(_context(tool_input={"file_path": "/tmp/config.yaml"})) is False
    assert is_code_file(_context(tool_input={"file_path": "/tmp/settings.yml"})) is False


def test_is_code_file_excludes_toml():
    """TOML is a data/config format, not code."""
    assert is_code_file(_context(tool_input={"file_path": "/tmp/pyproject.toml"})) is False


def test_is_code_file_excludes_xml():
    """XML is a data/config format, not code."""
    assert is_code_file(_context(tool_input={"file_path": "/tmp/config.xml"})) is False


def test_is_large_data_file_yaml(tmp_path: Path):
    """Large YAML files should match DATA_EXTENSIONS, not CODE_EXTENSIONS."""
    path = tmp_path / "data.yaml"
    path.write_text("\n".join(f"key-{idx}: value-{idx}" for idx in range(101)))
    assert is_large_data_file(_context(tool_input={"file_path": str(path)})) is True


def test_is_unbounded_bash_no_false_positive_category():
    """Command 'echo category' contains 'cat' but should not match."""
    assert is_unbounded_bash(_context(tool_input={"command": "echo category"})) is False


def test_is_unbounded_bash_no_false_positive_marginal():
    """Command 'printf 'marginal'' contains 'rg' but should not match."""
    assert is_unbounded_bash(_context(tool_input={"command": "printf 'marginal'"})) is False


def test_is_unbounded_bash_no_false_positive_heading():
    """Command 'echo heading' contains 'head' but should not match."""
    assert is_unbounded_bash(_context(tool_input={"command": "echo heading"})) is False
