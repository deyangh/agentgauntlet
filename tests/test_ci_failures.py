from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from agentgauntlet.cli import app


def test_cli_fails_when_all_adapters_error(tmp_path: Path) -> None:
    # A nonexistent executable works on every supported platform.
    result = CliRunner().invoke(app, [
        "run", "--adapter", "subprocess", "--target", str(tmp_path / "missing-agent"),
        "--repeats", "1", "--quiet", "--fail-over-asr", "0", "--fail-under-utility", "1",
    ])
    assert result.exit_code != 0
    assert "100.0%" not in result.stdout


def test_pytest_fails_for_errors_and_refusal(tmp_path: Path, scenarios_dir: Path) -> None:
    agent = tmp_path / "agents.py"
    agent.write_text(
        'def broken(messages, tools):\n    raise RuntimeError("unavailable")\n\n'
        'def refusal(messages, tools):\n    return "I refuse."\n'
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), env.get("PYTHONPATH", "")])
    scenario = scenarios_dir / "direct_injection" / "di-summarize-doc-01.yaml"
    for target in ("agents:broken", "agents:refusal"):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(scenario),
             "--agentgauntlet-scenarios", str(scenarios_dir),
             "--agentgauntlet-adapter", "callable", "--agentgauntlet-target", target],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "1 failed" in result.stdout
