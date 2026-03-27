"""Tests for built-in matcher functions."""

from pathlib import Path

from scripts.matchers import always, is_code_file, is_doc_file, is_large_data_file, is_unbounded_bash


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
