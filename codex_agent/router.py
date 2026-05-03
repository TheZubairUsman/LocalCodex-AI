from __future__ import annotations

import re
from typing import Any, Dict, List

from .models import ModelProfile, RoutingDecision


KEYWORDS = {
    "debug": [
        "debug",
        "fix",
        "traceback",
        "error",
        "exception",
        "broken",
        "not working",
        "runtime",
    ],
    "refactor": [
        "refactor",
        "cleanup",
        "simplify",
        "optimize",
        "restructure",
    ],
    "test": [
        "test",
        "pytest",
        "unit test",
        "coverage",
    ],
    "architecture": [
        "architecture",
        "design",
        "router",
        "provider",
        "workflow",
    ],
    "explain": [
        "explain",
        "what does",
        "how does",
        "understand",
        "walk through",
    ],
    "summarize": [
        "summarize",
        "summary",
        "scan",
        "inventory",
        "analyze",
        "analyse",
        "review",
    ],
    "research": [
        "research",
        "compare",
        "best",
        "latest",
        "recommend",
    ],
    "coding": [
        "build",
        "create",
        "write",
        "generate",
        "implement",
        "code",
        "add feature",
    ],
}

PREFIX_HINTS = [
    ("explain", "explain"),
    ("what does", "explain"),
    ("how does", "explain"),
    ("summarize", "summarize"),
    ("summary", "summarize"),
    ("scan", "summarize"),
    ("analyze", "summarize"),
    ("analyse", "summarize"),
    ("debug", "debug"),
    ("fix", "debug"),
    ("refactor", "refactor"),
    ("test", "test"),
    ("design", "architecture"),
    ("architect", "architecture"),
    ("research", "research"),
    ("compare", "research"),
    ("build", "coding"),
    ("create", "coding"),
    ("write", "coding"),
    ("generate", "coding"),
]


def _strip_paths(text: str) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^ \t\"']+", " ", text)
    text = re.sub(r"/[^ \t\"']+", " ", text)
    return text


def classify_task(user_goal: str, settings: Dict[str, Any]) -> str:
    text = _strip_paths(user_goal.lower()).strip()
    for prefix, task in PREFIX_HINTS:
        if text.startswith(prefix):
            aliases = settings.get("routing", {}).get("task_aliases", {})
            return aliases.get(task, task)

    scores = {
        task: sum(1 for keyword in keywords if keyword in text)
        for task, keywords in KEYWORDS.items()
    }
    task = max(scores, key=scores.get)
    if scores[task] == 0:
        task = "general"

    aliases = settings.get("routing", {}).get("task_aliases", {})
    return aliases.get(task, task)


class ModelRouter:
    def __init__(self, settings: Dict[str, Any], providers: Dict[str, Any]) -> None:
        self.settings = settings
        self.providers = providers
        self.catalog = [
            ModelProfile(**entry) for entry in settings.get("model_catalog", [])
        ]

    def model_profiles(self) -> List[ModelProfile]:
        return list(self.catalog)

    def route(self, task_type: str) -> RoutingDecision:
        available_by_provider = {
            name: provider.available_models()
            for name, provider in self.providers.items()
        }

        candidates = [
            profile
            for profile in self.catalog
            if task_type in profile.roles
        ]
        if not candidates:
            fallback_role = self.settings.get("routing", {}).get("fallback_role", "general")
            candidates = [
                profile
                for profile in self.catalog
                if fallback_role in profile.roles or "fallback" in profile.roles
            ]

        ordered = sorted(candidates, key=lambda item: item.priority, reverse=True)
        for profile in ordered:
            available = available_by_provider.get(profile.provider, [])
            if profile.name in available:
                fallbacks = [
                    candidate.name
                    for candidate in ordered
                    if candidate.name != profile.name
                ]
                return RoutingDecision(
                    task_type=task_type,
                    provider=profile.provider,
                    model=profile.name,
                    reason=profile.description,
                    available_models=available,
                    fallbacks=fallbacks,
                )

        for profile in sorted(self.catalog, key=lambda item: item.priority, reverse=True):
            available = available_by_provider.get(profile.provider, [])
            if available:
                fallback = available[0]
                return RoutingDecision(
                    task_type=task_type,
                    provider=profile.provider,
                    model=fallback,
                    reason=(
                        f"Configured model '{profile.name}' was unavailable; "
                        f"fell back to installed model '{fallback}'."
                    ),
                    available_models=available,
                    fallbacks=[],
                )

        raise RuntimeError("No enabled provider exposed any available local models.")


def tokenize_for_search(text: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower())
        if token not in {"the", "and", "with", "from", "into", "that"}
    ]
