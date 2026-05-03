from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class SessionMemory:
    def __init__(self, memory_file: str) -> None:
        self.path = Path(memory_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, payload: Dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            **payload,
        }
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        lines = self.path.read_text(encoding="utf-8").splitlines()
        rows = []
        for line in lines[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def format_recent(self, limit: int = 5) -> str:
        rows = self.recent(limit=limit)
        if not rows:
            return ""

        parts = []
        for row in rows:
            goal = str(row.get("user_goal", ""))[:180]
            task_type = row.get("task_type", "general")
            model = row.get("model", "unknown")
            parts.append(f"- [{task_type}] {model}: {goal}")
        return "\n".join(parts)
