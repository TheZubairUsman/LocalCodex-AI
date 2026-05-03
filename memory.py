from __future__ import annotations

from pathlib import Path

from codex_agent.memory import SessionMemory


_MEMORY = SessionMemory(str(Path(__file__).resolve().parent / "logs" / "legacy_memory.jsonl"))


def save(data: str) -> None:
    _MEMORY.append({"legacy": True, "user_goal": data})


def recall() -> str:
    return "\n".join(
        str(row.get("user_goal", ""))
        for row in _MEMORY.recent(limit=5)
    )
