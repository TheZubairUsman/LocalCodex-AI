from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "agent_config.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_project": str(ROOT_DIR),
    "logs_dir": str(ROOT_DIR / "logs"),
    "memory_file": str(ROOT_DIR / "logs" / "session_memory.jsonl"),
    "providers": {
        "ollama": {
            "type": "ollama",
            "enabled": True,
            "base_url": "http://127.0.0.1:11434",
            "timeout_seconds": 180,
        },
        "open_interpreter": {
            "type": "open_interpreter",
            "enabled": False,
            "auto_run": False,
        },
    },
    "model_catalog": [
        {
            "name": "codellama:7b",
            "provider": "ollama",
            "roles": ["coding", "debug", "refactor", "test"],
            "description": "Best installed local model for code generation, fixes, and refactors.",
            "priority": 100,
            "strengths": ["code generation", "debugging", "full-file rewrites"],
            "constraints": ["slower than phi3 for simple chat"],
        },
        {
            "name": "mistral:latest",
            "provider": "ollama",
            "roles": ["architecture", "summarize", "explain", "research"],
            "description": "Best installed local model for architecture, summaries, and longer explanations.",
            "priority": 90,
            "strengths": ["system design", "documentation", "analysis"],
            "constraints": ["weaker than codellama on code edits"],
        },
        {
            "name": "phi3:latest",
            "provider": "ollama",
            "roles": ["general", "fallback", "chat"],
            "description": "Fast fallback model for quick answers and lightweight tasks.",
            "priority": 80,
            "strengths": ["latency", "lightweight chat"],
            "constraints": ["less capable for complex code changes"],
        },
    ],
    "routing": {
        "fallback_role": "general",
        "task_aliases": {
            "code": "coding",
            "fix": "debug",
            "analyze": "summarize",
            "design": "architecture",
            "write": "summarize",
        },
    },
    "tooling": {
        "max_file_chars": 6000,
        "max_context_files": 10,
        "max_tree_entries": 120,
        "allow_command_execution": False,
        "allowed_command_prefixes": [
            "python",
            "py",
            "pytest",
            "git",
            "rg",
        ],
        "backup_writes": True,
        "plugin_paths": [],
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(config_path: str | Path | None = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    settings = deepcopy(DEFAULT_SETTINGS)

    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        settings = _deep_merge(settings, loaded)

    logs_dir = Path(settings["logs_dir"])
    memory_file = Path(settings["memory_file"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    settings["config_path"] = str(path.resolve())
    settings["logs_dir"] = str(logs_dir.resolve())
    settings["memory_file"] = str(memory_file.resolve())
    settings["default_project"] = str(Path(settings["default_project"]).resolve())
    return settings
