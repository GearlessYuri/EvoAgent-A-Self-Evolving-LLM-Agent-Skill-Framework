"""技能注册表门面：版本 CRUD + 状态机 + active 指针 + 内容 JSON 归档（§3.1）。

只经 `Storage` 的通用 CRUD 持久化，不直接操作 SQLite、不访问 `storage.conn`。
持久化映射（§5）：元数据（含 `name`/`description`/`tags`）写 SQLite `skills` 表；
内容本体（`prompt_template` / `few_shots` / `tools`）写 JSON 归档。
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..models import Skill
from ..storage import Storage


class SkillRegistry:
    """技能版本管理 + active 指针（§10 状态机，单 active 不变量）。"""

    def __init__(self, storage: Storage, skills_dir: str | Path = config.SKILLS_DIR):
        self.storage = storage
        self.skills_dir = Path(skills_dir)

    # ── 写入 ────────────────────────────────────────────────────────────

    def register(self, skill: Skill) -> None:
        """元数据写 `skills` 表，内容本体写 JSON 归档。

        尊重 `skill.status`：为 `""` 或 `None` 时才默认置 `"active"`。
        重复 `(skill_id, version)` 时由底层 `sqlite3.IntegrityError` 上抛（不 upsert）。
        """
        status = skill.status if skill.status else "active"

        self.storage.insert(
            "skills",
            {
                "skill_id": skill.skill_id,
                "version": skill.version,
                "name": skill.name,
                "description": skill.description,
                "tags": skill.tags,  # list[str]，由 Storage 自动 json.dumps
                "status": status,
                "parent_version": skill.parent_version,
                "change_log": skill.change_log,
                "metrics": skill.metrics,  # dict，由 Storage 自动 json.dumps
                "created_at": skill.created_at,
                "updated_at": skill.updated_at,
            },
        )

        content = {
            "prompt_template": skill.prompt_template,
            "few_shots": [fs.to_dict() for fs in skill.few_shots],
            "tools": [t.to_dict() for t in skill.tools],
        }
        path = self.skills_dir / skill.skill_id / f"{skill.version}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 读取 ────────────────────────────────────────────────────────────

    def get(self, skill_id: str, version: str) -> Skill | None:
        """合并元数据（SQLite）+ 内容（JSON）重建完整 `Skill`；行不存在 → `None`。"""
        rows = self.storage.query(
            "skills", where="skill_id = ? AND version = ?", params=(skill_id, version)
        )
        if not rows:
            return None
        row = rows[0]

        content_path = self.skills_dir / skill_id / f"{version}.json"
        # 内容本体缺失则无法重建完整 Skill，FileNotFoundError 自然上抛
        content = json.loads(content_path.read_text(encoding="utf-8"))

        return Skill.from_dict(
            {
                "skill_id": row["skill_id"],
                "name": row["name"],
                "description": row["description"],
                "version": row["version"],
                "tags": json.loads(row["tags"]),
                "prompt_template": content["prompt_template"],
                "few_shots": content["few_shots"],
                "tools": content["tools"],
                "status": row["status"],
                "parent_version": row["parent_version"],
                "change_log": row["change_log"],
                "metrics": json.loads(row["metrics"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    def get_active(self, skill_id: str) -> Skill | None:
        """返回当前 `status="active"` 的版本；无 active → `None`。"""
        rows = self.storage.query(
            "skills", where="skill_id = ? AND status = ?", params=(skill_id, "active")
        )
        if not rows:
            return None
        return self.get(skill_id, rows[0]["version"])

    def list(self, tags: list[str] | None = None) -> list[Skill]:
        """返回全部 active 版本（每 `skill_id` 至多一个），按 `skill_id` 升序。

        `tags` 为 `None` 不过滤；否则只返回与给定列表有交集（至少一个匹配）的 skill。
        """
        rows = self.storage.query(
            "skills", where="status = ?", params=("active",), order_by="skill_id"
        )
        result = []
        for row in rows:
            if tags is not None:
                row_tags = json.loads(row["tags"])
                if not (set(row_tags) & set(tags)):
                    continue
            result.append(self.get(row["skill_id"], row["version"]))
        return result

    # ── 状态机 ──────────────────────────────────────────────────────────

    def _set_active(self, skill_id: str, version: str) -> None:
        """目标版本置 active、该 skill 下其它 active 转 deprecated（单 active 不变量）。"""
        rows = self.storage.query(
            "skills", where="skill_id = ? AND version = ?", params=(skill_id, version)
        )
        if not rows:
            raise ValueError(f"skill version not found: {skill_id}@{version}")
        self.storage.update(
            "skills",
            {"status": "deprecated"},
            "skill_id = ? AND status = ? AND version != ?",
            (skill_id, "active", version),
        )
        self.storage.update(
            "skills",
            {"status": "active"},
            "skill_id = ? AND version = ?",
            (skill_id, version),
        )

    def promote(self, skill_id: str, version: str) -> None:
        """目标版本置 active、旧 active 转 deprecated；目标不存在 → `ValueError`。"""
        self._set_active(skill_id, version)

    def rollback(self, skill_id: str, to_version: str) -> None:
        """active 指回历史版本（§10 回滚边 `deprecated → active`，promote 的镜像操作）。"""
        self._set_active(skill_id, to_version)

    def deprecate(self, skill_id: str) -> None:
        """当前 active 转 deprecated；无 active → no-op。"""
        self.storage.update(
            "skills",
            {"status": "deprecated"},
            "skill_id = ? AND status = ?",
            (skill_id, "active"),
        )
