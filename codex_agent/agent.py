from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import load_settings
from .memory import SessionMemory
from .models import AgentResponse
from .project import ProjectAnalyzer
from .prompts import build_edit_prompt, build_prompt, extract_code_block, extract_paths
from .providers import ProviderError, build_providers
from .router import ModelRouter, classify_task
from .tools import ToolRegistry


class LocalCodexAgent:
    def __init__(self, config_path: str | None = None) -> None:
        self.settings = load_settings(config_path)
        self.project_analyzer = ProjectAnalyzer(self.settings)
        self.providers = build_providers(self.settings)
        self.router = ModelRouter(self.settings, self.providers)
        self.memory = SessionMemory(self.settings["memory_file"])
        self.tools = ToolRegistry(self.project_analyzer, self.settings)

    def doctor(self) -> Dict[str, Any]:
        provider_status = {
            name: provider.healthcheck()
            for name, provider in self.providers.items()
        }
        model_rows = []
        for profile in self.router.model_profiles():
            available = (
                profile.name in self.providers[profile.provider].available_models()
                if profile.provider in self.providers
                else False
            )
            model_rows.append(
                {
                    "name": profile.name,
                    "provider": profile.provider,
                    "roles": ", ".join(profile.roles),
                    "available": available,
                }
            )
        return {
            "config_path": self.settings["config_path"],
            "default_project": self.settings["default_project"],
            "providers": provider_status,
            "models": model_rows,
        }

    def model_inventory(self) -> List[Dict[str, Any]]:
        rows = []
        availability_cache = {
            name: provider.available_models()
            for name, provider in self.providers.items()
        }
        for profile in self.router.model_profiles():
            rows.append(
                {
                    "name": profile.name,
                    "provider": profile.provider,
                    "roles": ", ".join(profile.roles),
                    "available": profile.name in availability_cache.get(profile.provider, []),
                    "description": profile.description,
                }
            )
        return rows

    def scan_project(self, project_path: str | Path) -> Dict[str, Any]:
        inventory = self.project_analyzer.build_inventory(project_path)
        report = self.project_analyzer.report_inventory(inventory)
        return {"inventory": inventory, "report": report}

    def handle_request(
        self,
        user_goal: str,
        *,
        project_path: str | Path | None = None,
    ) -> AgentResponse:
        resolved_project = self._resolve_project_path(project_path)
        task_type = classify_task(user_goal, self.settings)
        routing = self.router.route(task_type)

        inventory = (
            self.project_analyzer.build_inventory(resolved_project)
            if resolved_project
            else None
        )
        explicit_paths = extract_paths(user_goal)
        context_snippets = (
            self.project_analyzer.collect_context(
                resolved_project,
                user_goal,
                explicit_paths=explicit_paths,
            )
            if resolved_project
            else []
        )

        if inventory:
            self.tools.call("scan_project", project_path=resolved_project)
        for path, _ in context_snippets:
            self.tools.call("read_file", path=path)

        prompt = build_prompt(
            user_goal=user_goal,
            task_type=task_type,
            routing=routing,
            inventory=inventory,
            context_snippets=context_snippets,
            tool_descriptions=self.tools.describe(),
            tool_calls=self.tools.consume_log(),
            recent_memory=self.memory.format_recent(limit=5),
        )

        provider = self.providers[routing.provider]
        system_prompt = self._system_prompt_for(task_type)
        try:
            output = provider.generate(
                routing.model,
                prompt,
                system_prompt=system_prompt,
            )
        except ProviderError as exc:
            output = f"Provider error: {exc}"

        response = AgentResponse(
            user_goal=user_goal,
            task_type=task_type,
            routing=routing,
            project_path=str(resolved_project) if resolved_project else None,
            inventory=inventory,
            tool_calls=[],
            prompt=prompt,
            output=output,
        )
        self._record_response(response)
        return response

    def edit_file(
        self,
        file_path: str | Path,
        instruction: str,
        *,
        task_type: str = "refactor",
        apply_changes: bool = True,
    ) -> AgentResponse:
        target = Path(file_path).resolve()
        if not target.exists():
            raise FileNotFoundError(target)

        routing = self.router.route(task_type)
        current_text = self.project_analyzer.read_text(target, max_chars=None)
        prompt = build_edit_prompt(str(target), instruction, current_text)

        provider = self.providers[routing.provider]
        system_prompt = self._system_prompt_for(task_type)
        output = provider.generate(
            routing.model,
            prompt,
            system_prompt=system_prompt,
        )

        files_written: List[str] = []
        backup_paths: List[str] = []
        proposed = extract_code_block(output)
        if apply_changes and proposed:
            if self.settings.get("tooling", {}).get("backup_writes", True):
                backup = self._backup_file(target)
                if backup:
                    backup_paths.append(str(backup))
            target.write_text(proposed, encoding="utf-8")
            files_written.append(str(target))

        response = AgentResponse(
            user_goal=instruction,
            task_type=task_type,
            routing=routing,
            project_path=str(target.parent),
            inventory=None,
            tool_calls=[],
            prompt=prompt,
            output=output,
            files_written=files_written,
            backup_paths=backup_paths,
        )
        self._record_response(response)
        return response

    def _resolve_project_path(self, project_path: str | Path | None) -> Optional[Path]:
        candidate = Path(project_path) if project_path else Path(self.settings["default_project"])
        if not candidate.exists():
            return None
        return candidate.resolve()

    def _record_response(self, response: AgentResponse) -> None:
        self.memory.append(
            {
                "user_goal": response.user_goal,
                "task_type": response.task_type,
                "model": response.routing.model,
                "provider": response.routing.provider,
                "project_path": response.project_path,
                "files_written": response.files_written,
            }
        )

    def _backup_file(self, path: Path) -> Optional[Path]:
        if not path.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak_{timestamp}")
        shutil.copy2(path, backup)
        return backup

    def _system_prompt_for(self, task_type: str) -> str:
        from .prompts import SYSTEM_PROMPTS

        return SYSTEM_PROMPTS.get(task_type, SYSTEM_PROMPTS["general"])
