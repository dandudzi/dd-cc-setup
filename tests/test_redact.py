"""Tests for scripts/redact.py — sensitive payload redaction for logging."""
import pytest

from scripts.redact import redact_tool_input


class TestReadRedaction:
    """Read tool: keep only file_path."""

    def test_read_keeps_file_path(self):
        result = redact_tool_input("Read", {"file_path": "/src/app.py"})
        assert result == {"file_path": "/src/app.py"}

    def test_read_drops_other_keys(self):
        result = redact_tool_input(
            "Read",
            {"file_path": "/src/app.py", "limit": 100, "offset": 0, "pages": "1-5"},
        )
        assert result == {"file_path": "/src/app.py"}

    def test_read_empty_input(self):
        result = redact_tool_input("Read", {})
        assert result == {}


class TestWriteRedaction:
    """Write tool: keep only file_path, drop content."""

    def test_write_keeps_file_path(self):
        result = redact_tool_input(
            "Write",
            {"file_path": "/src/app.py", "content": "secret_code_here"},
        )
        assert result == {"file_path": "/src/app.py"}

    def test_write_drops_content(self):
        result = redact_tool_input(
            "Write",
            {"file_path": "/out.txt", "content": "very sensitive data"},
        )
        assert "content" not in result

    def test_write_empty_input(self):
        result = redact_tool_input("Write", {})
        assert result == {}


class TestEditRedaction:
    """Edit tool: keep only file_path, drop old_string and new_string."""

    def test_edit_keeps_file_path(self):
        result = redact_tool_input(
            "Edit",
            {
                "file_path": "/src/app.py",
                "old_string": "password = 'secret'",
                "new_string": "password = 'new_secret'",
            },
        )
        assert result == {"file_path": "/src/app.py"}

    def test_edit_drops_old_and_new_string(self):
        result = redact_tool_input(
            "Edit",
            {
                "file_path": "/src/app.py",
                "old_string": "password = 'secret'",
                "new_string": "password = 'new_secret'",
            },
        )
        assert "old_string" not in result
        assert "new_string" not in result

    def test_edit_empty_input(self):
        result = redact_tool_input("Edit", {})
        assert result == {}


class TestBashRedaction:
    """Bash tool: truncate command at 80 chars, drop sensitive env vars."""

    def test_bash_short_command_kept_as_is(self):
        result = redact_tool_input("Bash", {"command": "ls -la /tmp"})
        assert result == {"command": "ls -la /tmp"}

    def test_bash_command_exactly_80_chars_kept(self):
        cmd_80 = "a" * 80
        result = redact_tool_input("Bash", {"command": cmd_80})
        assert result == {"command": cmd_80}

    def test_bash_command_longer_than_80_chars_truncated(self):
        cmd_100 = "a" * 100
        result = redact_tool_input("Bash", {"command": cmd_100})
        assert result["command"] == "a" * 80 + "...[truncated]"
        assert len(result["command"]) == 80 + len("...[truncated]")  # 94 chars total

    def test_bash_drops_env_key(self):
        result = redact_tool_input(
            "Bash",
            {"command": "echo test", "env": {"PATH": "/usr/bin"}},
        )
        assert "env" not in result
        assert result == {"command": "echo test"}

    def test_bash_drops_token_key(self):
        result = redact_tool_input(
            "Bash",
            {"command": "curl api", "token": "secret-token-123"},
        )
        assert "token" not in result
        assert result == {"command": "curl api"}

    def test_bash_drops_secret_key(self):
        result = redact_tool_input(
            "Bash",
            {"command": "deploy", "secret": "my-secret"},
        )
        assert "secret" not in result
        assert result == {"command": "deploy"}

    def test_bash_drops_password_key(self):
        result = redact_tool_input(
            "Bash",
            {"command": "login", "password": "hunter2"},
        )
        assert "password" not in result
        assert result == {"command": "login"}

    def test_bash_case_insensitive_sensitive_key_drop(self):
        result = redact_tool_input(
            "Bash",
            {
                "command": "test",
                "TOKEN": "secret",
                "Secret": "value",
                "PASSWORD": "pass",
            },
        )
        assert "TOKEN" not in result
        assert "Secret" not in result
        assert "PASSWORD" not in result
        assert result == {"command": "test"}

    def test_bash_empty_input(self):
        result = redact_tool_input("Bash", {})
        assert result == {}

    def test_bash_command_truncation_at_81_chars(self):
        cmd_81 = "a" * 81
        result = redact_tool_input("Bash", {"command": cmd_81})
        expected = "a" * 80 + "...[truncated]"
        assert result["command"] == expected


class TestGlobRedaction:
    """Glob tool: keep only pattern and path."""

    def test_glob_keeps_pattern_and_path(self):
        result = redact_tool_input(
            "Glob",
            {"pattern": "*.py", "path": "/src"},
        )
        assert result == {"pattern": "*.py", "path": "/src"}

    def test_glob_drops_other_keys(self):
        result = redact_tool_input(
            "Glob",
            {"pattern": "*.py", "path": "/src", "limit": 10, "sort": "modified"},
        )
        assert result == {"pattern": "*.py", "path": "/src"}

    def test_glob_empty_input(self):
        result = redact_tool_input("Glob", {})
        assert result == {}


class TestGrepRedaction:
    """Grep tool: keep pattern, path, glob, type."""

    def test_grep_keeps_allowed_keys(self):
        result = redact_tool_input(
            "Grep",
            {
                "pattern": "TODO",
                "path": "/src",
                "glob": "*.py",
                "type": "py",
            },
        )
        assert result == {
            "pattern": "TODO",
            "path": "/src",
            "glob": "*.py",
            "type": "py",
        }

    def test_grep_drops_other_keys(self):
        result = redact_tool_input(
            "Grep",
            {
                "pattern": "secret",
                "path": "/src",
                "glob": "*.py",
                "type": "py",
                "-A": 3,
                "-B": 2,
                "head_limit": 50,
                "output_mode": "content",
            },
        )
        assert result == {
            "pattern": "secret",
            "path": "/src",
            "glob": "*.py",
            "type": "py",
        }

    def test_grep_empty_input(self):
        result = redact_tool_input("Grep", {})
        assert result == {}


class TestWebSearchRedaction:
    """WebSearch tool: keep only query."""

    def test_websearch_keeps_query(self):
        result = redact_tool_input("WebSearch", {"query": "how to deploy"})
        assert result == {"query": "how to deploy"}

    def test_websearch_drops_other_keys(self):
        result = redact_tool_input(
            "WebSearch",
            {"query": "deploy", "api_key": "secret-key", "limit": 10},
        )
        assert result == {"query": "deploy"}

    def test_websearch_empty_input(self):
        result = redact_tool_input("WebSearch", {})
        assert result == {}


class TestWebFetchRedaction:
    """WebFetch tool: keep only url."""

    def test_webfetch_keeps_url(self):
        result = redact_tool_input("WebFetch", {"url": "https://example.com"})
        assert result == {"url": "https://example.com"}

    def test_webfetch_drops_other_keys(self):
        result = redact_tool_input(
            "WebFetch",
            {"url": "https://example.com", "timeout": 30, "headers": {"Auth": "token"}},
        )
        assert result == {"url": "https://example.com"}

    def test_webfetch_empty_input(self):
        result = redact_tool_input("WebFetch", {})
        assert result == {}


class TestDefaultRedaction:
    """Unknown/default tool: drop any key with 'token', 'key', 'secret', 'password', 'credential', 'auth' in name."""

    def test_default_keeps_safe_keys(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "safe", "path": "/tmp", "limit": 10},
        )
        assert result == {"query": "safe", "path": "/tmp", "limit": 10}

    def test_default_drops_token(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "test", "token": "secret"},
        )
        assert "token" not in result

    def test_default_drops_key_case_insensitive(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "test", "API_KEY": "secret", "MyKey": "value"},
        )
        assert "API_KEY" not in result
        assert "MyKey" not in result
        assert result == {"query": "test"}

    def test_default_drops_secret(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "test", "secret": "value"},
        )
        assert "secret" not in result

    def test_default_drops_password(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "test", "password": "hunter2"},
        )
        assert "password" not in result

    def test_default_drops_credential(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "test", "credential": "cred-value"},
        )
        assert "credential" not in result

    def test_default_drops_auth(self):
        result = redact_tool_input(
            "UnknownTool",
            {"query": "test", "auth": "bearer-token"},
        )
        assert "auth" not in result

    def test_default_empty_input(self):
        result = redact_tool_input("UnknownTool", {})
        assert result == {}


class TestRedactionEdgeCases:
    """Edge cases: None input, non-dict input, etc."""

    def test_empty_dict_returns_empty_dict(self):
        result = redact_tool_input("Read", {})
        assert result == {}

    def test_tool_name_case_sensitive(self):
        """Tool names should be treated as case-sensitive."""
        result = redact_tool_input("read", {"file_path": "/src/app.py", "limit": 10})
        # "read" is not "Read", so uses default rules (drops no keys unless they contain sensitive keywords)
        assert result == {"file_path": "/src/app.py", "limit": 10}

    def test_non_dict_input_returns_empty_dict(self):
        result = redact_tool_input("Read", None)
        assert result == {}

    def test_list_input_returns_empty_dict(self):
        result = redact_tool_input("Read", [])
        assert result == {}

    def test_string_input_returns_empty_dict(self):
        result = redact_tool_input("Read", "invalid")
        assert result == {}

    def test_int_input_returns_empty_dict(self):
        result = redact_tool_input("Read", 123)
        assert result == {}

    def test_bash_command_value_truncation_precise(self):
        """Test exact truncation behavior: keep first 80 chars, append marker."""
        cmd = "x" * 150
        result = redact_tool_input("Bash", {"command": cmd})
        assert result["command"] == "x" * 80 + "...[truncated]"
        assert result["command"].startswith("x" * 80)

    def test_sensitive_keys_not_case_sensitive_for_keywords(self):
        """SENSITIVE keyword matching should be case-insensitive across tools."""
        result = redact_tool_input(
            "Bash",
            {
                "command": "test",
                "TOKEN": "secret",
                "token": "secret",
                "Token": "secret",
            },
        )
        # All should be dropped
        assert "TOKEN" not in result
        assert "token" not in result
        assert "Token" not in result
