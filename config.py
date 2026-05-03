from __future__ import annotations

from pathlib import Path

from codex_agent.config import load_settings


PROJECT_PATH = str(Path(__file__).resolve().parent)
CONFIG_PATH = Path(__file__).resolve().parent / "agent_config.json"

_SETTINGS = load_settings(CONFIG_PATH)

MODELS = {
    role: entry["name"]
    for entry in _SETTINGS.get("model_catalog", [])
    for role in entry.get("roles", [])
}

# Backwards compatibility for older imports.
MODEL = MODELS.get("general", "phi3:latest")
