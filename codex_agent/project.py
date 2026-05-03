from __future__ import annotations

import configparser
import json
import os
import tomllib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .models import ProjectInventory
from .router import tokenize_for_search


SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".rst",
    ".ps1",
    ".bat",
    ".cmd",
    ".sh",
    ".html",
    ".css",
    ".env",
}

MODEL_EXTENSIONS = {
    ".gguf",
    ".safetensors",
    ".bin",
    ".onnx",
    ".pt",
    ".pth",
}


class ProjectAnalyzer:
    def __init__(self, settings: Dict[str, Any]) -> None:
        tooling = settings.get("tooling", {})
        self.max_file_chars = int(tooling.get("max_file_chars", 6000))
        self.max_context_files = int(tooling.get("max_context_files", 10))
        self.max_tree_entries = int(tooling.get("max_tree_entries", 120))

    def build_inventory(self, project_path: str | Path) -> ProjectInventory:
        root = Path(project_path).resolve()
        category_map: Dict[str, List[str]] = {
            "python_files": [],
            "config_files": [],
            "launch_scripts": [],
            "docs": [],
            "tests": [],
            "notebooks": [],
            "logs": [],
            "model_files": [],
            "executables": [],
            "datasets": [],
            "env_files": [],
        }
        detected_components: List[str] = []
        total_files = 0
        tree_lines = [f"{root}"]

        for path in self._iter_files(root):
            total_files += 1
            relative = str(path.relative_to(root))
            category = self._categorize(path)
            if category:
                category_map[category].append(relative)

            if len(tree_lines) <= self.max_tree_entries:
                tree_lines.append(relative)

            if path.suffix.lower() == ".py":
                content = self.read_text(path, max_chars=2500)
                detected_components.extend(self._detect_python_components(content))

        notes = []
        if not category_map["model_files"]:
            notes.append("No local model weight files were found inside the project.")
        if not any(component.endswith("_api") for component in detected_components):
            notes.append("No FastAPI/Flask-style API server was detected in project code.")
        if not category_map["tests"]:
            notes.append("No test files were detected in the project tree.")

        return ProjectInventory(
            root_path=str(root),
            total_files=total_files,
            category_map={key: sorted(value) for key, value in category_map.items()},
            detected_components=sorted(set(detected_components)),
            tree_preview="\n".join(tree_lines[: self.max_tree_entries + 1]),
            notes=notes,
        )

    def report_inventory(self, inventory: ProjectInventory) -> str:
        lines = [
            f"Project: {inventory.root_path}",
            f"Total files: {inventory.total_files}",
            "",
            "Categories:",
        ]
        for name, files in inventory.category_map.items():
            if files:
                lines.append(f"- {name}: {len(files)}")
        if inventory.detected_components:
            lines.extend(["", "Detected components:"])
            lines.extend(f"- {item}" for item in inventory.detected_components)
        if inventory.notes:
            lines.extend(["", "Notes:"])
            lines.extend(f"- {note}" for note in inventory.notes)
        lines.extend(["", "Tree preview:", inventory.tree_preview])
        return "\n".join(lines)

    def collect_context(
        self,
        project_path: str | Path,
        user_goal: str,
        explicit_paths: Sequence[str] | None = None,
    ) -> List[Tuple[str, str]]:
        root = Path(project_path).resolve()
        selected: List[Path] = []

        for raw in explicit_paths or []:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = root / raw
            if candidate.exists() and candidate.is_file():
                selected.append(candidate.resolve())

        if selected:
            return [
                (
                    str(path),
                    self.read_text(path, max_chars=self.max_file_chars),
                )
                for path in selected[: self.max_context_files]
            ]

        if len(selected) < self.max_context_files:
            for candidate in self._score_candidate_files(root, user_goal):
                if candidate not in selected:
                    selected.append(candidate)
                if len(selected) >= self.max_context_files:
                    break

        snippets = []
        for path in selected[: self.max_context_files]:
            snippets.append(
                (
                    str(path),
                    self.read_text(path, max_chars=self.max_file_chars),
                )
            )
        return snippets

    def read_text(self, path: str | Path, max_chars: int | None = None) -> str:
        target = Path(path)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"[read failed: {exc}]"
        limit = max_chars if max_chars is not None else self.max_file_chars
        return text[:limit]

    def parse_config(self, path: str | Path) -> str:
        target = Path(path)
        suffix = target.suffix.lower()

        if suffix == ".json":
            data = json.loads(target.read_text(encoding="utf-8"))
            return json.dumps(data, indent=2, ensure_ascii=False)[: self.max_file_chars]
        if suffix == ".toml":
            data = tomllib.loads(target.read_text(encoding="utf-8"))
            return json.dumps(data, indent=2, ensure_ascii=False)[: self.max_file_chars]
        if suffix in {".ini", ".cfg"}:
            parser = configparser.ConfigParser()
            parser.read(target, encoding="utf-8")
            data = {section: dict(parser[section]) for section in parser.sections()}
            return json.dumps(data, indent=2, ensure_ascii=False)[: self.max_file_chars]

        return self.read_text(target)

    def search_text(
        self,
        project_path: str | Path,
        pattern: str,
        *,
        max_hits: int = 20,
    ) -> List[str]:
        root = Path(project_path).resolve()
        hits: List[str] = []
        lowered = pattern.lower()
        for path in self._iter_files(root):
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                for line_no, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(),
                    start=1,
                ):
                    if lowered in line.lower():
                        rel = path.relative_to(root)
                        hits.append(f"{rel}:{line_no}: {line.strip()}")
                        if len(hits) >= max_hits:
                            return hits
            except OSError:
                continue
        return hits

    def _iter_files(self, root: Path) -> Iterable[Path]:
        for current_root, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                yield Path(current_root) / filename

    def _categorize(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        name = path.name.lower()

        if name.startswith("test_") or "tests" in path.parts:
            return "tests"
        if name in {".env", "requirements.txt", "pyproject.toml"}:
            return "env_files"
        if suffix == ".py":
            return "python_files"
        if suffix in {".json", ".toml", ".ini", ".cfg", ".yaml", ".yml"}:
            return "config_files"
        if suffix in {".ps1", ".bat", ".cmd", ".sh"}:
            return "launch_scripts"
        if suffix in {".md", ".txt", ".rst"}:
            return "docs"
        if suffix == ".ipynb":
            return "notebooks"
        if suffix in {".log", ".jsonl"}:
            return "logs"
        if suffix in MODEL_EXTENSIONS:
            return "model_files"
        if suffix in {".exe", ".dll"}:
            return "executables"
        if suffix in {".csv", ".tsv", ".parquet"}:
            return "datasets"
        return None

    def _detect_python_components(self, content: str) -> List[str]:
        lowered = content.lower()
        components = []
        if "from interpreter import openinterpreter" in lowered or "openinterpreter()" in lowered:
            components.append("open_interpreter_wrapper")
        if "ollama" in lowered or "/api/generate" in lowered or "/api/tags" in lowered:
            components.append("ollama_client")
        if "import tkinter" in lowered or "from tkinter" in lowered:
            components.append("tkinter_gui")
        if "fastapi" in lowered:
            components.append("fastapi_api")
        if "flask(" in lowered or "@app.route" in lowered:
            components.append("flask_api")
        if "requests" in lowered:
            components.append("http_client")
        if "subprocess.run" in lowered:
            components.append("command_runner")
        if "duckduckgo" in lowered:
            components.append("web_search")
        if "def run(" in lowered or "argparse" in lowered:
            components.append("cli_entrypoint")
        if "wf_" in lowered or "detect_task" in lowered:
            components.append("agent_workflow")
        return components

    def _score_candidate_files(self, root: Path, user_goal: str) -> List[Path]:
        tokens = tokenize_for_search(user_goal)
        scored: List[Tuple[int, Path]] = []
        for path in self._iter_files(root):
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            score = 0
            lowered_name = path.name.lower()
            if path.suffix.lower() == ".py":
                score += 4
            if lowered_name in {"readme.md", "requirements.txt", "pyproject.toml"}:
                score += 8
            if "config" in lowered_name or "app" in lowered_name or "controller" in lowered_name:
                score += 5
            for token in tokens:
                if token in lowered_name:
                    score += 3
            if score:
                scored.append((score, path))
        scored.sort(key=lambda item: (-item[0], str(item[1])))
        return [path for _, path in scored]
