"""Central tool registry and its enforcement (docs/SPEC.md §8E).

    from app.tools import all_tools, call_tool, check_tool_use

Importing this package registers every tool (app/tools/builtin.py).
"""

from __future__ import annotations

from app.agent_catalog import AGENT_TEMPLATES, PERMISSION_KEYS
from app.tools import builtin  # noqa: F401  (registers the tools)
from app.tools.base import (
    ApprovalText,
    Risk,
    Tool,
    ToolContext,
    ToolError,
    ToolResult,
    ToolUnavailable,
    all_tools,
    get_tool,
    tool_keys,
)
from app.tools.calls import Decision, ToolOutcome, call_tool, check_tool_use

# The registry, the permission catalogue and the agent templates must agree with each other.
for _tool in all_tools():
    assert _tool.required_permission is None or _tool.required_permission in PERMISSION_KEYS, _tool.key
for _template in AGENT_TEMPLATES:
    assert set(_template.default_tools) <= tool_keys(), _template.key

__all__ = [
    "ApprovalText",
    "Decision",
    "Risk",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolOutcome",
    "ToolResult",
    "ToolUnavailable",
    "all_tools",
    "call_tool",
    "check_tool_use",
    "get_tool",
    "tool_keys",
]
