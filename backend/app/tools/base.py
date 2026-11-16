"""Tool registry: what a tool is, the one catalogue of tools, and what a tool is handed.

A tool is a small internal function. It gets a `ToolContext` — the calling agent, the task it
is working on and a database session — and nothing else: no file path, no shell, no network
handle. Every tool in this application only reads or writes the village's own SQLite database.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Task


class Risk(StrEnum):
    READ = "READ"  # looks things up; runs at once
    WRITE = "WRITE"  # changes the village's own data; runs at once
    SENSITIVE = "SENSITIVE"  # external or irreversible; ALWAYS needs the Chairman's approval


class ToolError(Exception):
    """The tool could not do what was asked (bad arguments, missing target, a rule). The message
    is shown to the Chairman, so it must be plain and must not contain secrets."""


class ToolUnavailable(ToolError):
    """The tool is registered but not built yet. Never pretend: say so."""


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool may touch."""

    db: Session
    agent: Agent
    task: Task | None = None


@dataclass(frozen=True)
class ToolResult:
    summary: str  # one or two plain sentences: what happened
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalText:
    """What the Chairman is shown before deciding about a SENSITIVE tool (docs/SPEC.md §8F)."""

    action: str
    expected_changes: str
    risk_info: str


ToolRun = Callable[[ToolContext, dict[str, Any]], ToolResult]
ToolDescribe = Callable[[ToolContext, dict[str, Any]], ApprovalText]


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    description: str
    risk: Risk
    run: ToolRun
    required_permission: str | None = None  # a key of agent_catalog.PERMISSIONS, or None
    available: bool = True  # False = registered, but answers "not available yet"
    planned_for: str = ""  # the milestone an unavailable tool is planned for, e.g. "M6"
    describe: ToolDescribe | None = None  # SENSITIVE tools: the text of the approval request

    @property
    def needs_approval(self) -> bool:
        return self.risk is Risk.SENSITIVE


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.key in _REGISTRY:
        raise ValueError(f"tool '{tool.key}' is registered twice")
    if tool.risk is Risk.SENSITIVE and tool.describe is None:
        raise ValueError(f"sensitive tool '{tool.key}' must describe its approval request")
    _REGISTRY[tool.key] = tool
    return tool


def get_tool(key: str) -> Tool | None:
    return _REGISTRY.get(key)


def all_tools() -> list[Tool]:
    """Every registered tool, in registration order."""
    return list(_REGISTRY.values())


def tool_keys() -> frozenset[str]:
    return frozenset(_REGISTRY)
