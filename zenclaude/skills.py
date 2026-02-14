from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


@dataclass
class SkillInfo:
    name: str
    description: str
    argument_hint: str
    prompt_body: str
    source: Path


def discover_skills(workspace: Optional[Path] = None) -> dict[str, SkillInfo]:
    skills: dict[str, SkillInfo] = {}

    for directory in _skill_dirs(workspace):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            skill_file = _find_skill_file(entry)
            if not skill_file:
                continue
            info = _parse_skill(skill_file)
            if info and info.name not in skills:
                skills[info.name] = info

    return skills


def expand_skill(skill: SkillInfo, arguments: str) -> str:
    parts = [skill.prompt_body.strip()]
    if arguments.strip():
        parts.append(f"\n## Task\n\n{arguments.strip()}")
    return "\n\n".join(parts)


def _skill_dirs(workspace: Optional[Path]) -> list[Path]:
    dirs = []
    if workspace:
        local = workspace.resolve() / ".claude" / "skills"
        if local.is_dir():
            dirs.append(local)
    if GLOBAL_SKILLS_DIR.is_dir():
        dirs.append(GLOBAL_SKILLS_DIR)
    return dirs


def _find_skill_file(entry: Path) -> Optional[Path]:
    if entry.is_file() and entry.name == "SKILL.md":
        return entry
    if entry.is_dir():
        candidate = entry / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


def _parse_skill(path: Path) -> Optional[SkillInfo]:
    text = path.read_text()

    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    frontmatter = text[3:end].strip()
    body = text[end + 3:].strip()

    meta = _parse_frontmatter(frontmatter)
    name = meta.get("name", "")
    if not name:
        return None

    return SkillInfo(
        name=name,
        description=meta.get("description", ""),
        argument_hint=meta.get("argument-hint", ""),
        prompt_body=body,
        source=path,
    )


def _parse_frontmatter(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_key = ""
    current_value = ""

    for line in raw.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            if current_key:
                result[current_key] = current_value.strip()
            key, _, value = line.partition(":")
            current_key = key.strip()
            value = value.strip()
            if value == ">":
                current_value = ""
            else:
                current_value = value.strip('"').strip("'")
        elif current_key:
            current_value += " " + line.strip()

    if current_key:
        result[current_key] = current_value.strip()

    return result
