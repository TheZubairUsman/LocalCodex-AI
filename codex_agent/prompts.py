from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, Tuple

from .models import ProjectInventory, RoutingDecision, ToolCall


SYSTEM_PROMPTS = {
    "coding": (
        "You are a practical local coding assistant. "
        "Write complete, runnable code when asked. Prefer concise explanations, "
        "call out assumptions, and preserve existing project structure."
    ),
    "debug": (
        "You are a senior debugger. State the likely root cause, explain the fix, "
        "and prefer full-file corrections over vague snippets."
    ),
    "refactor": (
        "You are a senior code reviewer. Improve readability, naming, cohesion, "
        "and safety without changing behavior unless the user asked for it."
    ),
    "test": (
        "You are a QA-focused Python engineer. Generate deterministic tests, cover "
        "edge cases, and avoid brittle mocking."
    ),
    "architecture": (
        "You are a local LLM systems architect. Focus on providers, routing, tool "
        "design, observability, and Windows-friendly runtime choices."
    ),
    "summarize": (
        "You are a technical analyst. Summarize structure, identify reusable parts, "
        "and call out missing or broken pieces."
    ),
    "explain": (
        "You are a patient coding mentor. Explain code in plain technical language, "
        "but do not simplify away important implementation details."
    ),
    "research": (
        "You are a research assistant. Summarize findings, compare options, and "
        "state uncertainty explicitly."
    ),
    "general": (
        "You are a practical local engineering assistant. Be direct, technical, "
        "and explicit about what you inferred from the supplied context."
    ),
}


def build_prompt(
    *,
    user_goal: str,
    task_type: str,
    routing: RoutingDecision,
    inventory: ProjectInventory | None,
    context_snippets: Sequence[Tuple[str, str]],
    tool_descriptions: str,
    tool_calls: Sequence[ToolCall],
    recent_memory: str,
) -> str:
    sections: List[str] = [
        f"Task type: {task_type}",
        f"Selected model: {routing.model} via {routing.provider}",
        f"Routing reason: {routing.reason}",
        "",
        "Available tools:",
        tool_descriptions or "- none",
        "",
        "User goal:",
        user_goal,
    ]

    if inventory:
        sections.extend(
            [
                "",
                "Project inventory:",
                f"- Root: {inventory.root_path}",
                f"- Total files: {inventory.total_files}",
                f"- Detected components: {', '.join(inventory.detected_components) or 'none'}",
            ]
        )
        for category, files in inventory.category_map.items():
            if files:
                sections.append(f"- {category}: {len(files)}")
        if inventory.notes:
            sections.extend(["- Notes:"] + [f"  {note}" for note in inventory.notes])

    if context_snippets:
        sections.extend(["", "Relevant file context:"])
        for path, content in context_snippets:
            sections.append(f"=== {path} ===")
            sections.append(content)
        sections.append("Focus on the explicitly supplied file context before describing the wider project.")

    if tool_calls:
        sections.extend(["", "Tool outputs used:"])
        for call in tool_calls:
            sections.append(f"- {call.name}: {call.summary}")

    if recent_memory:
        sections.extend(["", "Recent session memory:", recent_memory])

    sections.extend(
        [
            "",
            "Response rules:",
            "- If context is insufficient, say exactly what is missing.",
            "- If suggesting edits, preserve Windows-safe paths and commands.",
            "- Prefer modular steps and exact file references.",
            "- Do not invent APIs, models, files, or test results.",
        ]
    )
    return "\n".join(sections).strip()


def build_edit_prompt(file_path: str, instruction: str, current_text: str) -> str:
    language = guess_language(file_path)
    return (
        f"Update the file at `{file_path}`.\n"
        f"Instruction: {instruction}\n\n"
        "Return only one complete replacement file inside a single fenced code block. "
        "Do not omit imports or existing required logic.\n\n"
        f"```{language}\n{current_text}\n```"
    )


def guess_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".json": "json",
        ".toml": "toml",
        ".html": "html",
        ".css": "css",
        ".sh": "bash",
        ".ps1": "powershell",
    }.get(suffix, "")


def extract_paths(text: str) -> List[str]:
    found = []
    for match in re.finditer(r'["\']([A-Za-z]:[\\/][^"\']+|/[^"\']+)["\']', text):
        found.append(match.group(1))
    for match in re.finditer(r"\b([A-Za-z]:[/\\][^ \t,;\"\']+)", text):
        candidate = match.group(1).rstrip("\\/.,;")
        if candidate not in found:
            found.append(candidate)
    for token in text.split():
        candidate = token.strip('"\'.,;')
        if ("/" in candidate or "\\" in candidate) and candidate not in found:
            found.append(candidate)
    return found


def extract_code_block(text: str) -> str | None:
    match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    stripped = text.strip()
    if stripped.startswith("# filename:") or stripped.startswith("import ") or stripped.startswith("from "):
        return stripped
    return None
