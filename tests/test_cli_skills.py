"""CLI and skills installer tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from payagent.cli import main
from payagent.skills_install import install_skills, package_skill_root, resolve_agents


def test_package_skill_root_has_skill_md() -> None:
    root = package_skill_root()
    assert (root / "SKILL.md").is_file()
    text = (root / "SKILL.md").read_text()
    assert "payagent" in text.lower()
    assert "payagent get" in text or "payagent pay" in text


def test_resolve_agents() -> None:
    assert "grok" in resolve_agents("all")
    assert resolve_agents("grok,claude") == ["grok", "claude"]
    with pytest.raises(ValueError):
        resolve_agents("nope")


def test_install_skills_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".grok").mkdir()
    results = install_skills(
        ["grok"],
        scope="project",
        project=tmp_path,
        force=True,
        only_if_home_exists=False,
    )
    assert any(r.status == "installed" for r in results)
    skill = tmp_path / ".grok" / "skills" / "payagent" / "SKILL.md"
    assert skill.is_file()


def test_cli_pay_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYAGENT_MOCK", "1")
    monkeypatch.setenv("PAYAGENT_MAX_PER_TX", "1")
    monkeypatch.setenv("PAYAGENT_DAILY_LIMIT", "10")
    rc = main(["pay", "--to", "0xS", "--amount", "0.05", "--json"])
    assert rc == 0


def test_cli_pay_budget(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PAYAGENT_MOCK", "1")
    monkeypatch.setenv("PAYAGENT_MAX_PER_TX", "0.01")
    monkeypatch.setenv("PAYAGENT_DAILY_LIMIT", "10")
    rc = main(["pay", "--to", "0xS", "--amount", "0.5", "--json"])
    assert rc == 2
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["ok"] is False


@respx.mock
def test_cli_get_402(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYAGENT_MOCK", "1")
    monkeypatch.setenv("PAYAGENT_MAX_PER_TX", "1")
    monkeypatch.setenv("PAYAGENT_DAILY_LIMIT", "10")
    url = "https://seller.test/premium"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(
                402,
                headers={
                    "X-PAYMENT-ADDRESS": "0xSeller",
                    "X-PAYMENT-AMOUNT": "0.05",
                    "X-PAYMENT-CURRENCY": "USDC",
                },
            ),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    rc = main(["get", url, "--json"])
    assert rc == 0


def test_cli_skills_list() -> None:
    assert main(["skills", "list", "--json"]) == 0


def test_cli_skills_path() -> None:
    assert main(["skills", "path", "--json"]) == 0


def test_cli_skills_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()
    rc = main(
        [
            "skills",
            "install",
            "--agents",
            "claude",
            "--project",
            "--force",
            "--cwd",
            str(tmp_path),
            "--json",
        ]
    )
    assert rc == 0
    assert (tmp_path / ".claude" / "skills" / "payagent" / "SKILL.md").is_file()
