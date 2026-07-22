"""Install payagent skills into local coding-agent directories."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable


# Canonical skill name as seen by agents
SKILL_NAME = "payagent"


@dataclass(frozen=True)
class AgentTarget:
    key: str
    label: str
    # relative to home unless absolute; may use {project} placeholder
    user_dir: str
    project_dir: str | None = None
    # "skill_dir" = copy whole skill folder as <parent>/payagent
    # "file" = copy a single file into path
    mode: str = "skill_dir"
    source_extra: str | None = None  # e.g. agents/cursor.mdc


TARGETS: dict[str, AgentTarget] = {
    "grok": AgentTarget(
        key="grok",
        label="Grok",
        user_dir="~/.grok/skills",
        project_dir="{project}/.grok/skills",
    ),
    "claude": AgentTarget(
        key="claude",
        label="Claude Code",
        user_dir="~/.claude/skills",
        project_dir="{project}/.claude/skills",
    ),
    "codex": AgentTarget(
        key="codex",
        label="Codex",
        user_dir="~/.codex/skills",
        project_dir="{project}/.codex/skills",
    ),
    "cursor": AgentTarget(
        key="cursor",
        label="Cursor",
        user_dir="~/.cursor/skills",
        project_dir="{project}/.cursor/rules",
        mode="cursor_both",
    ),
    "pi": AgentTarget(
        key="pi",
        label="Pi",
        user_dir="~/.pi/agent/skills",
        project_dir="{project}/.pi/skills",
    ),
    "continue": AgentTarget(
        key="continue",
        label="Continue",
        user_dir="~/.continue/skills",
        project_dir="{project}/.continue/skills",
    ),
    "antigravity": AgentTarget(
        key="antigravity",
        label="Antigravity",
        user_dir="~/.gemini/antigravity/skills",
        project_dir=None,
    ),
    "windsurf": AgentTarget(
        key="windsurf",
        label="Windsurf",
        user_dir="~/.codeium/windsurf/skills",
        project_dir="{project}/.windsurf/skills",
    ),
}


def package_skill_root() -> Path:
    """Return filesystem path to bundled skill directory."""
    # payagent/agent_skills/payagent/
    trav = resources.files("payagent.agent_skills").joinpath("payagent")
    # as_file for zipimport; for normal installs path is real
    if hasattr(trav, "_path") or True:
        # Prefer concrete path when available
        try:
            p = Path(str(trav))
            if (p / "SKILL.md").is_file():
                return p
        except Exception:  # noqa: BLE001
            pass
    # Fallback: relative to this file
    here = Path(__file__).resolve().parent / "agent_skills" / "payagent"
    if (here / "SKILL.md").is_file():
        return here
    raise FileNotFoundError("bundled payagent skill not found in package")


def _expand(path: str, project: Path | None) -> Path:
    s = path.replace("~", str(Path.home()))
    if "{project}" in s:
        if project is None:
            raise ValueError("project path required for project-scoped install")
        s = s.replace("{project}", str(project.resolve()))
    return Path(s).expanduser()


def _copy_tree(src: Path, dest: Path, *, force: bool) -> None:
    if dest.exists() or dest.is_symlink():
        if not force:
            raise FileExistsError(f"already exists (use --force): {dest}")
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)


def _copy_file(src: Path, dest: Path, *, force: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        raise FileExistsError(f"already exists (use --force): {dest}")
    shutil.copy2(src, dest)


def resolve_agents(spec: str) -> list[str]:
    spec = spec.strip().lower()
    if spec in {"all", "*"}:
        return list(TARGETS.keys())
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    unknown = [p for p in parts if p not in TARGETS]
    if unknown:
        raise ValueError(f"unknown agents: {unknown}; choose from {list(TARGETS)}")
    return parts


@dataclass
class InstallResult:
    agent: str
    path: str
    status: str  # installed | skipped | error
    detail: str = ""


def install_skills(
    agents: Iterable[str],
    *,
    scope: str = "user",
    project: Path | None = None,
    force: bool = False,
    only_if_home_exists: bool = True,
) -> list[InstallResult]:
    """Copy bundled skill into agent skill directories."""
    src = package_skill_root()
    results: list[InstallResult] = []
    project = project or Path.cwd()

    for key in agents:
        target = TARGETS[key]
        try:
            if scope == "project":
                if not target.project_dir:
                    results.append(
                        InstallResult(key, "", "skipped", "no project path for agent")
                    )
                    continue
                parent = _expand(target.project_dir, project)
            else:
                parent = _expand(target.user_dir, project)
                # Skip creating random home dirs for agents user never installed
                if only_if_home_exists and scope == "user":
                    # parent is .../skills — check grandparent product dir
                    product_home = parent.parent
                    if not product_home.exists() and key not in {"grok", "claude", "codex"}:
                        # still allow creating for major three always
                        results.append(
                            InstallResult(
                                key,
                                str(parent / SKILL_NAME),
                                "skipped",
                                f"{product_home} not found",
                            )
                        )
                        continue

            if target.mode == "skill_dir":
                dest = parent / SKILL_NAME
                _copy_tree(src, dest, force=force)
                results.append(InstallResult(key, str(dest), "installed"))
            elif target.mode == "cursor_both":
                # skills folder + rules mdc
                skill_dest = parent / SKILL_NAME
                # For project cursor rules, parent may be .cursor/rules
                if parent.name == "rules":
                    mdc_src = src / "agents" / "cursor.mdc"
                    mdc_dest = parent / "payagent.mdc"
                    _copy_file(mdc_src, mdc_dest, force=force)
                    results.append(InstallResult(key, str(mdc_dest), "installed", "rule"))
                    # also project skills if .cursor exists
                    skills_parent = parent.parent / "skills"
                    _copy_tree(src, skills_parent / SKILL_NAME, force=force)
                    results.append(
                        InstallResult(
                            key,
                            str(skills_parent / SKILL_NAME),
                            "installed",
                            "skill",
                        )
                    )
                else:
                    _copy_tree(src, skill_dest, force=force)
                    results.append(InstallResult(key, str(skill_dest), "installed"))
                    # user-level rules optional
                    rules = Path.home() / ".cursor" / "rules"
                    mdc_src = src / "agents" / "cursor.mdc"
                    if rules.parent.exists() or force:
                        _copy_file(mdc_src, rules / "payagent.mdc", force=True)
                        results.append(
                            InstallResult(key, str(rules / "payagent.mdc"), "installed", "rule")
                        )
            else:
                results.append(InstallResult(key, "", "error", f"unknown mode {target.mode}"))
        except FileExistsError as exc:
            results.append(InstallResult(key, "", "skipped", str(exc)))
        except Exception as exc:  # noqa: BLE001
            results.append(InstallResult(key, "", "error", str(exc)))

    # Always drop AGENTS.md snippet into project if project scope requested
    if scope == "project":
        try:
            agents_md_src = src / "agents" / "AGENTS.md"
            agents_md_dest = project / "AGENTS.payagent.md"
            if agents_md_src.is_file():
                _copy_file(agents_md_src, agents_md_dest, force=force or True)
                results.append(
                    InstallResult("generic", str(agents_md_dest), "installed", "AGENTS snippet")
                )
        except Exception as exc:  # noqa: BLE001
            results.append(InstallResult("generic", "", "error", str(exc)))

    return results


def list_targets() -> list[dict[str, str]]:
    return [
        {
            "key": t.key,
            "label": t.label,
            "user_dir": t.user_dir,
            "project_dir": t.project_dir or "",
        }
        for t in TARGETS.values()
    ]


def detect_installed_agents() -> list[str]:
    found: list[str] = []
    home = Path.home()
    checks = {
        "grok": home / ".grok",
        "claude": home / ".claude",
        "codex": home / ".codex",
        "cursor": home / ".cursor",
        "pi": home / ".pi",
        "continue": home / ".continue",
        "antigravity": home / ".gemini" / "antigravity",
        "windsurf": home / ".codeium" / "windsurf",
    }
    for key, path in checks.items():
        if path.exists():
            found.append(key)
    return found
