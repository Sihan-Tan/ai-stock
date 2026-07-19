"""Skill 加载：仓库 skills/*/SKILL.md。"""

from __future__ import annotations

from pathlib import Path

from desk_common.settings import get_settings


def _default_skills_root() -> Path:
    """解析 skills 目录：优先 Settings，再尝试仓库根。"""
    settings = get_settings()
    candidate = Path(settings.skills_dir)
    if candidate.exists():
        return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        skill_dir = parent / "skills"
        if skill_dir.is_dir():
            return skill_dir
    return candidate


class SkillLoader:
    """加载仓库 skills/*/SKILL.md。"""

    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else _default_skills_root()

    def list(self) -> list[dict[str, str]]:
        """列出 skill。"""
        if not self.root.exists():
            return []
        out = []
        for d in sorted(self.root.iterdir()):
            skill = d / "SKILL.md"
            if d.is_dir() and skill.exists():
                text = skill.read_text(encoding="utf-8")
                name = d.name
                desc = ""
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        for line in parts[1].splitlines():
                            if line.startswith("description:"):
                                desc = line.split(":", 1)[1].strip()
                out.append({"name": name, "path": str(skill), "description": desc})
        return out

    def load(self, name: str) -> str:
        """读取完整 SKILL.md。"""
        path = self.root / name / "SKILL.md"
        if not path.exists():
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8")
