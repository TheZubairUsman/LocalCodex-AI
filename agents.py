from __future__ import annotations

from controller import run_system


def run_agent(prompt: str, project_path: str | None = None) -> str:
    return run_system(prompt, project_path=project_path)
