from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelProfile:
    name: str
    provider: str
    roles: List[str]
    description: str
    priority: int = 50
    strengths: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    task_type: str
    provider: str
    model: str
    reason: str
    available_models: List[str] = field(default_factory=list)
    fallbacks: List[str] = field(default_factory=list)


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    summary: str


@dataclass
class ProjectInventory:
    root_path: str
    total_files: int
    category_map: Dict[str, List[str]]
    detected_components: List[str]
    tree_preview: str
    notes: List[str] = field(default_factory=list)


@dataclass
class AgentResponse:
    user_goal: str
    task_type: str
    routing: RoutingDecision
    project_path: Optional[str]
    inventory: Optional[ProjectInventory]
    tool_calls: List[ToolCall]
    prompt: str
    output: str
    files_written: List[str] = field(default_factory=list)
    backup_paths: List[str] = field(default_factory=list)
