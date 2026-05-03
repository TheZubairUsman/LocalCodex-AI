from __future__ import annotations

import importlib.util
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List

from .models import ToolCall
from .project import ProjectAnalyzer


class ToolRegistry:
    def __init__(self, analyzer: ProjectAnalyzer, settings: Dict[str, Any]) -> None:
        self.analyzer = analyzer
        self.settings = settings
        self.tools: Dict[str, Callable[..., Any]] = {}
        self.descriptions: Dict[str, str] = {}
        self.command_log: List[ToolCall] = []
        self._register_builtin_tools()
        self._load_plugins()

    def register(self, name: str, description: str, func: Callable[..., Any]) -> None:
        self.tools[name] = func
        self.descriptions[name] = description

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        result = self.tools[name](**kwargs)
        self.command_log.append(
            ToolCall(
                name=name,
                arguments=kwargs,
                summary=str(result)[:400],
            )
        )
        return result

    def describe(self) -> str:
        lines = []
        for name in sorted(self.tools):
            lines.append(f"- {name}: {self.descriptions[name]}")
        return "\n".join(lines)

    def consume_log(self) -> List[ToolCall]:
        calls = list(self.command_log)
        self.command_log.clear()
        return calls

    def _register_builtin_tools(self) -> None:
        self.register(
            "scan_project",
            "Scan a project folder and produce a categorized inventory.",
            lambda project_path: self.analyzer.report_inventory(
                self.analyzer.build_inventory(project_path)
            ),
        )
        self.register(
            "read_file",
            "Read a text file with truncation for prompt context.",
            lambda path: self.analyzer.read_text(path),
        )
        self.register(
            "search_code",
            "Search for text across project files.",
            lambda project_path, pattern: "\n".join(
                self.analyzer.search_text(project_path, pattern)
            ),
        )
        self.register(
            "inspect_config",
            "Parse JSON/TOML/INI config files and return structured output.",
            lambda path: self.analyzer.parse_config(path),
        )
        self.register(
            "run_command",
            "Run an allowlisted local command with optional dry-run mode.",
            self._run_command,
        )

    def _run_command(
        self,
        command: str | List[str],
        *,
        cwd: str | None = None,
        dry_run: bool = True,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        tooling = self.settings.get("tooling", {})
        allow_execution = bool(tooling.get("allow_command_execution", False))
        parts = command if isinstance(command, list) else shlex.split(command, posix=False)
        if not parts:
            return {"executed": False, "reason": "empty command"}

        if any(token in {"&&", "||", "|", ";"} for token in parts):
            return {"executed": False, "reason": "shell control operators are blocked"}

        executable_name = Path(parts[0]).name.lower()
        if executable_name in {
            "rm",
            "del",
            "erase",
            "format",
            "shutdown",
            "reboot",
            "taskkill",
            "remove-item",
        }:
            return {"executed": False, "reason": "dangerous commands are blocked"}

        allowed = {
            entry.lower() for entry in tooling.get("allowed_command_prefixes", [])
        }
        if executable_name not in allowed and parts[0].lower() not in allowed:
            return {
                "executed": False,
                "reason": f"command '{parts[0]}' is not in the allowlist",
            }

        if dry_run or not allow_execution:
            return {
                "executed": False,
                "reason": "dry-run",
                "command": parts,
            }

        result = subprocess.run(
            parts,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return {
            "executed": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _load_plugins(self) -> None:
        plugin_paths = self.settings.get("tooling", {}).get("plugin_paths", [])
        for raw_path in plugin_paths:
            path = Path(raw_path)
            if not path.exists() or path.suffix.lower() != ".py":
                continue
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "register_tools"):
                module.register_tools(self)
