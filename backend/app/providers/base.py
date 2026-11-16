"""The provider interface: how an agent turns a task into a reply.

A provider gets plain, read-only descriptions of the agent and the task (no database objects),
so it cannot change anything in the village by itself. A reply may ASK for tools
(`AgentReply.tool_calls`); whether a tool really runs is decided by the task runner through
`app.tools.call_tool` — never by the provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentContext:
    display_name: str
    role: str
    template_key: str | None = None
    system_instructions: str = ""
    location: str = ""  # "Study Upazila › Academic Management › Ward 1: Class Routine"


@dataclass(frozen=True)
class TaskContext:
    title: str
    description: str = ""


@dataclass(frozen=True)
class ToolRequest:
    """A tool the agent wants to use, with its arguments and its reason."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class AgentReply:
    text: str
    tool_calls: tuple[ToolRequest, ...] = ()


class Provider(ABC):
    """One way of producing replies (Demo today; real AI providers in a later milestone)."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the provider can be used right now (for example: its key is set)."""

    @abstractmethod
    def reply(self, agent: AgentContext, task: TaskContext) -> str | AgentReply:
        """The agent's answer to the task: plain text, or text plus the tools it asks for."""
