"""Integration test for scripts/analyze/__main__.py CLI."""
import json
import subprocess
import sys
from pathlib import Path


def _make_transcript(tmp_path: Path, session_id: str = "session-abc") -> Path:
    """Create a minimal transcript JSONL file under a fake projects dir."""
    proj = tmp_path / "proj-123"
    proj.mkdir()
    f = proj / f"{session_id}.jsonl"
    entries = [
        {
            "type": "assistant",
            "requestId": "req-1",
            "message": {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu-1",
                        "name": "Read",
                        "input": {"file_path": "/src/app.py"},
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu-1",
                        "content": "x" * 5000,
                    }
                ]
            },
            "permissionMode": "default",
        },
    ]
    import json
    f.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return tmp_path


class TestMainCLI:
    def test_produces_valid_json_output(self, tmp_path: Path):
        projects_dir = _make_transcript(tmp_path)
        output_file = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable, "-m", "scripts.analyze",
                "--output", str(output_file),
                "--projects-dir", str(projects_dir),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
        assert output_file.exists(), "Output file not created"
        report = json.loads(output_file.read_text())
        assert "corpus" in report
        assert "waste_analysis" in report
        assert report["corpus"]["session_count"] == 1

    def test_report_has_all_sections(self, tmp_path: Path):
        projects_dir = _make_transcript(tmp_path)
        output_file = tmp_path / "report.json"
        subprocess.run(
            [
                sys.executable, "-m", "scripts.analyze",
                "--output", str(output_file),
                "--projects-dir", str(projects_dir),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        report = json.loads(output_file.read_text())
        for section in [
            "corpus", "per_tool_costs", "per_extension_costs",
            "waste_analysis", "session_modes", "decision_tree_validation",
            "sequence_analysis",
        ]:
            assert section in report, f"Missing section: {section}"

    def test_empty_projects_dir_exits_zero(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        output_file = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable, "-m", "scripts.analyze",
                "--output", str(output_file),
                "--projects-dir", str(empty_dir),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0
