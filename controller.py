from __future__ import annotations

from codex_agent.agent import LocalCodexAgent


_AGENT: LocalCodexAgent | None = None


def _get_agent(config_path: str | None = None) -> LocalCodexAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = LocalCodexAgent(config_path)
    return _AGENT


def run_system(task: str, project_path: str | None = None) -> str:
    response = _get_agent().handle_request(task, project_path=project_path)
    return _format_response(response)


def scan_system(project_path: str | None = None) -> str:
    agent = _get_agent()
    project = project_path or agent.settings["default_project"]
    scanned = agent.scan_project(project)
    return scanned["report"]


def doctor_system() -> str:
    report = _get_agent().doctor()
    lines = [
        f"Config: {report['config_path']}",
        f"Default project: {report['default_project']}",
        "",
        "Providers:",
    ]
    for name, status in report["providers"].items():
        lines.append(f"- {name}: ok={status.get('ok')} reason={status.get('reason')}")
    return "\n".join(lines)


def _format_response(response) -> str:
    lines = [
        f"Task type: {response.task_type}",
        f"Model: {response.routing.model} ({response.routing.provider})",
        f"Reason: {response.routing.reason}",
    ]
    if response.files_written:
        lines.append(f"Files written: {', '.join(response.files_written)}")
    if response.backup_paths:
        lines.append(f"Backups: {', '.join(response.backup_paths)}")
    lines.extend(["", response.output])
    return "\n".join(lines)
