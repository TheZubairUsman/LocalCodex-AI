from __future__ import annotations

from codex_agent.agent import LocalCodexAgent


def read_project(path: str) -> str:
    agent = LocalCodexAgent()
    scanned = agent.scan_project(path)
    return scanned["report"]
