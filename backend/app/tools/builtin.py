"""The registered tools.

Real tools (they only read or write the village's own database):
  task.create_child, agent.request_info, org.read, memory.read, memory.write
  (memory: what an agent may read or write per scope is decided in app/memory.py)
SENSITIVE placeholders (ALWAYS need the Chairman's approval; when approved they only record
"approved — no external connector yet" and do nothing else):
  message.send_external, file.delete, money.spend, marketing.publish
Planned tools (registered so they can be assigned, but they answer "not available yet"):
  document.*, knowledge.search, pdf.generate, calendar.read, product.read, inventory.check,
  system.health_check

There is deliberately no shell, terminal, free-filesystem or network tool.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app import memory
from app.models import Agent, AgentMessage, Office, UnionUnit, Upazila, Ward
from app.tools.base import (
    ApprovalText,
    Risk,
    Tool,
    ToolContext,
    ToolDenied,
    ToolError,
    ToolResult,
    ToolUnavailable,
    register,
)

NO_CONNECTOR = "approved — no external connector yet"

# ---------------------------------------------------------------- argument helpers


def _only(args: dict[str, Any], *allowed: str) -> None:
    unknown = sorted(set(args) - set(allowed))
    if unknown:
        raise ToolError(f"Unknown argument: {', '.join(unknown)}. Allowed: {', '.join(allowed) or 'none'}.")


def _text(args: dict[str, Any], name: str, *, limit: int, required: bool = True) -> str:
    value = args.get(name, "")
    if not isinstance(value, str):
        raise ToolError(f"'{name}' must be text.")
    value = value.strip()
    if required and not value:
        raise ToolError(f"'{name}' is required.")
    if len(value) > limit:
        raise ToolError(f"'{name}' is too long (at most {limit} characters).")
    return value


def _other_active_agent(ctx: ToolContext, args: dict[str, Any]) -> Agent:
    agent_id = args.get("agent_id")
    if isinstance(agent_id, bool) or not isinstance(agent_id, int):
        raise ToolError("'agent_id' must be the number of an agent.")
    target = ctx.db.get(Agent, agent_id)
    if target is None:
        raise ToolError(f"Agent #{agent_id} does not exist.")
    if target.id == ctx.agent.id:
        raise ToolError("An agent cannot address itself.")
    if target.lifecycle != "active":
        raise ToolError(f"'{target.display_name}' is {target.lifecycle} and does not receive tasks or messages.")
    return target


def _need_task(ctx: ToolContext, tool_name: str):  # noqa: ANN202
    if ctx.task is None:
        raise ToolError(f"'{tool_name}' can only be used while working on a task.")
    return ctx.task


# ---------------------------------------------------------------- real tools


def _create_child(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    from app import central_manager  # imported here: central_manager → api.agents → app.tools

    _only(args, "agent_id", "title", "description", "routing")
    parent = _need_task(ctx, "Create child task")
    target = _other_active_agent(ctx, args)
    if target.is_central_manager:
        raise ToolError("The Central Manager routes requests; it does not take delegated work.")
    title = _text(args, "title", limit=200, required=False) or None
    description = _text(args, "description", limit=4000, required=False) if "description" in args else None
    routing = args.get("routing")
    if routing is not None and not isinstance(routing, dict):
        raise ToolError("'routing' must be an object.")
    try:
        child = central_manager.delegate(ctx.db, parent, target, routing, title=title, description=description)
    except central_manager.DelegationDepthError as exc:
        raise ToolError(str(exc)) from None
    return ToolResult(
        f"Created task #{child.id} for {target.display_name}.",
        {"task_id": child.id, "agent_id": target.id, "agent_name": target.display_name},
    )


def _request_info(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    # The payload has exactly one field. Nothing an agent writes into a message can change
    # another agent's tools or permissions: check_tool_use reads only the agent's own row.
    _only(args, "agent_id", "question")
    task = _need_task(ctx, "Ask another agent")
    target = _other_active_agent(ctx, args)
    question = _text(args, "question", limit=1000)
    message = AgentMessage(
        sender_agent_id=ctx.agent.id,
        receiver_agent_id=target.id,
        task_id=task.id,
        type="info_request",
        payload={"question": question},
    )
    ctx.db.add(message)
    ctx.db.flush()
    return ToolResult(
        f"Information request #{message.id} was recorded for {target.display_name}. "
        "Agents do not answer such requests on their own yet.",
        {"message_id": message.id, "agent_id": target.id},
    )


def _org_read(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    _only(args)
    wards_per_union = dict(ctx.db.execute(select(Ward.union_id, func.count()).group_by(Ward.union_id)).all())
    unions: dict[int, list[dict[str, Any]]] = {}
    for union in ctx.db.execute(select(UnionUnit).order_by(UnionUnit.sort_order, UnionUnit.id)).scalars():
        unions.setdefault(union.upazila_id, []).append(
            {"id": union.id, "name": union.name, "wards": wards_per_union.get(union.id, 0)}
        )
    upazilas = [
        {"id": upazila.id, "name": upazila.name, "unions": unions.get(upazila.id, [])}
        for upazila in ctx.db.execute(select(Upazila).order_by(Upazila.sort_order, Upazila.id)).scalars()
    ]
    offices = ctx.db.execute(select(func.count()).select_from(Office)).scalar_one()
    union_count = sum(len(item["unions"]) for item in upazilas)
    ward_count = sum(wards_per_union.values())
    return ToolResult(
        f"The village has {len(upazilas)} Upazila(s), {union_count} Union(s), {ward_count} Ward(s) and {offices} Office(s).",
        {"upazilas": upazilas, "offices": offices},
    )


# ---- memory: the scope rules live in app/memory.py; a refusal there is a denial here


def _scope(args: dict[str, Any], *, required: bool) -> str | None:
    value = args.get("scope")
    if value is None and not required:
        return None
    if not isinstance(value, str) or value.strip().upper() not in (*memory.SCOPES, memory.TASK):
        raise ToolError("'scope' must be one of: village, upazila, agent, task.")
    return value.strip().upper()


def _snippet(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _memory_read(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    _only(args, "scope", "query")
    scope = _scope(args, required=False)
    query = _text(args, "query", limit=200, required=False)
    if scope == memory.TASK:
        task = _need_task(ctx, "Read memory")
        notes = [{"key": row.key, "value": row.value} for row in memory.context_of(ctx.db, task)]
        return ToolResult(f"This task has {len(notes)} context note(s).", {"scope": "task", "notes": notes})
    try:
        found = memory.read_for_agent(ctx.db, ctx.agent, scope, query)
    except memory.MemoryDenied as exc:
        raise ToolDenied(str(exc)) from None
    entries = [
        {"id": row.id, "scope": row.scope.lower(), "title": row.title, "content": _snippet(row.content, 500)} for row in found
    ]
    where = scope.lower() if scope else " + ".join(item.lower() for item in memory.readable_scopes(ctx.db, ctx.agent))
    if not entries:
        return ToolResult(f"No memory found ({where}).", {"entries": []})
    listed = "; ".join(f"[{entry['scope']}] {entry['title']}: {_snippet(entry['content'])}" for entry in entries[:5])
    more = f" (+{len(entries) - 5} more)" if len(entries) > 5 else ""
    return ToolResult(f"Found {len(entries)} memory entr{'y' if len(entries) == 1 else 'ies'} ({where}): {listed}{more}", {"entries": entries})


def _memory_write(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    _only(args, "scope", "title", "content", "contains_customer_data")
    scope = _scope(args, required=True)
    title = _text(args, "title", limit=memory.TITLE_MAX)
    content = _text(args, "content", limit=memory.CONTENT_MAX)
    flagged = args.get("contains_customer_data", False)
    if not isinstance(flagged, bool):
        raise ToolError("'contains_customer_data' must be true or false.")
    try:
        if scope == memory.TASK:
            task = _need_task(ctx, "Write memory")
            memory.set_context(ctx.db, ctx.agent, task, title, content)
            return ToolResult(f"Kept '{title}' in the context of this task. It is deleted when the task ends.", {"scope": "task"})
        row = memory.write_for_agent(ctx.db, ctx.agent, scope, title, content, flagged)  # type: ignore[arg-type]
    except memory.MemoryDenied as exc:
        raise ToolDenied(str(exc)) from None
    except memory.MemoryRefused as exc:
        raise ToolError(str(exc)) from None
    note = " It is marked as customer data." if row.contains_customer_data else ""
    return ToolResult(f"Saved '{title}' to {scope.lower()} memory (entry #{row.id}).{note}", {"memory_id": row.id, "scope": scope.lower()})


register(
    Tool(
        key="task.create_child",
        name="Create child task",
        description="Hand a part of the current task to another active agent as a child task.",
        risk=Risk.WRITE,
        required_permission="delegate_tasks",
        run=_create_child,
    )
)
register(
    Tool(
        key="agent.request_info",
        name="Ask another agent",
        description="Send a structured information request to another active agent. It is recorded as an agent message.",
        risk=Risk.READ,
        run=_request_info,
    )
)
register(
    Tool(
        key="org.read",
        name="Read the organisation",
        description="Read the village's structure: Upazilas, Unions and the number of Wards and Offices.",
        risk=Risk.READ,
        run=_org_read,
    )
)
register(
    Tool(
        key="memory.read",
        name="Read memory",
        description="Read the memories the agent is allowed to see: village, its own Upazila, its own notes.",
        risk=Risk.READ,
        run=_memory_read,
    )
)
register(
    Tool(
        key="memory.write",
        name="Write memory",
        description="Save a note where the agent is permitted to write: its own notes, its Upazila or the village.",
        risk=Risk.WRITE,
        run=_memory_write,
    )
)


# ---------------------------------------------------------------- sensitive placeholders
#
# None of these does anything outside the database. They exist so that the approval flow is
# real: the call is checked, an approval is requested, and an approved call only RECORDS the
# approval. The connectors that would really send, delete, pay or publish do not exist.


def _placeholder(what: str):  # noqa: ANN202
    def run(_ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
        return ToolResult(f"{NO_CONNECTOR}. {what}", {"external_action": False})

    return run


def _send_external_args(args: dict[str, Any]) -> tuple[str, str, str]:
    _only(args, "recipient", "body", "channel")
    return (
        _text(args, "recipient", limit=120),
        _text(args, "body", limit=2000),
        _text(args, "channel", limit=40, required=False) or "message",
    )


def _describe_send(_ctx: ToolContext, args: dict[str, Any]) -> ApprovalText:
    recipient, body, channel = _send_external_args(args)
    return ApprovalText(
        action=f"Send a {channel} to {recipient}: “{body}”",
        expected_changes=(
            f"Once a connector exists, {recipient} would receive this {channel}. "
            "Today nothing leaves this PC: an approval is only recorded."
        ),
        risk_info="External message. It cannot be taken back once sent, and it speaks for you to someone outside the village.",
    )


def _describe_delete(_ctx: ToolContext, args: dict[str, Any]) -> ApprovalText:
    _only(args, "file")
    name = _text(args, "file", limit=200)
    return ApprovalText(
        action=f"Delete the file “{name}”",
        expected_changes="Once file storage exists, the file would be removed. Today no file is touched: an approval is only recorded.",
        risk_info="Irreversible. A deleted file can only come back from a backup.",
    )


def _describe_spend(_ctx: ToolContext, args: dict[str, Any]) -> ApprovalText:
    _only(args, "amount", "currency", "purpose")
    amount = args.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int | float) or amount <= 0:
        raise ToolError("'amount' must be a positive number.")
    currency = _text(args, "currency", limit=8, required=False) or "BDT"
    purpose = _text(args, "purpose", limit=300)
    return ApprovalText(
        action=f"Spend {amount:g} {currency} for: {purpose}",
        expected_changes="Once a payment connector exists, this amount would be paid. Today no money moves: an approval is only recorded.",
        risk_info="Spends money. Payments and refunds are hard or impossible to reverse.",
    )


def _describe_publish(_ctx: ToolContext, args: dict[str, Any]) -> ApprovalText:
    _only(args, "channel", "content")
    channel = _text(args, "channel", limit=80)
    content = _text(args, "content", limit=2000)
    return ApprovalText(
        action=f"Publish on {channel}: “{content}”",
        expected_changes=f"Once a connector exists, this would become public on {channel}. Today nothing is published: an approval is only recorded.",
        risk_info="Public content. It represents you and may be copied before it can be removed.",
    )


register(
    Tool(
        key="message.send_external",
        name="Send external message",
        description="Send a message to someone outside the village (customer, e-mail, chat). Always needs approval.",
        risk=Risk.SENSITIVE,
        required_permission="send_external_messages",
        run=_placeholder("Nothing was sent."),
        describe=_describe_send,
    )
)
register(
    Tool(
        key="file.delete",
        name="Delete a file",
        description="Delete a document or another file. Always needs approval.",
        risk=Risk.SENSITIVE,
        required_permission="delete_files",
        run=_placeholder("No file was deleted."),
        describe=_describe_delete,
    )
)
register(
    Tool(
        key="money.spend",
        name="Spend money",
        description="Make a purchase or issue a refund. Always needs approval.",
        risk=Risk.SENSITIVE,
        required_permission="spend_money",
        run=_placeholder("No money was spent."),
        describe=_describe_spend,
    )
)
register(
    Tool(
        key="marketing.publish",
        name="Publish marketing content",
        description="Publish marketing or other public material. Always needs approval.",
        risk=Risk.SENSITIVE,
        required_permission="publish_content",
        run=_placeholder("Nothing was published."),
        describe=_describe_publish,
    )
)


# ---------------------------------------------------------------- planned tools (not built)


def _not_built(_ctx: ToolContext, _args: dict[str, Any]) -> ToolResult:
    raise ToolUnavailable("This tool is not available yet.")


for _key, _name, _description, _risk, _permission, _milestone in (
    ("document.read", "Read permitted documents", "Read documents the agent has been given access to.", Risk.READ, None, "M6"),
    ("knowledge.search", "Search local knowledge", "Search the village's local knowledge base.", Risk.READ, None, "M6"),
    ("document.create", "Create a document", "Write a new document into the village's document folder.", Risk.WRITE, "create_files", "M6"),
    ("pdf.generate", "Generate PDF", "Turn a report or document into a PDF file.", Risk.WRITE, "create_files", "M6"),
    ("calendar.read", "Read calendar", "Read the configured calendar data.", Risk.READ, None, "M7"),
    ("product.read", "Product information", "Look up product information.", Risk.READ, None, "M7"),
    ("inventory.check", "Verify inventory", "Check stock levels.", Risk.READ, None, "M7"),
    ("system.health_check", "System health check", "Run the village's built-in, read-only health checks.", Risk.READ, None, "M8"),
):
    register(
        Tool(
            key=_key,
            name=_name,
            description=_description,
            risk=_risk,
            required_permission=_permission,
            run=_not_built,
            available=False,
            planned_for=_milestone,
        )
    )
