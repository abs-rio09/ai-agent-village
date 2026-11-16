"""The Central Manager (Demo): keyword routing, delegation and the final report.

It never does the work itself (docs/SPEC.md §5): it classifies a request, picks an ACTIVE
agent in the matching Upazila, delegates a child task to that agent and, when the child tasks
are finished, collects their outputs into a report. There is no AI in here — the routing is
the keyword table in app/routing_keywords.py.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.agents import agent_rows_query, location_of
from app.models import Agent, AgentMessage, Task, UnionUnit, Upazila, UpazilaTemplate
from app.providers import DEMO_PREFIX
from app.routing_keywords import ROUTING_KEYWORDS, STOPWORDS
from app.task_status import ASSIGNED, SUCCEEDED

MAX_DELEGATION_DEPTH = 3  # the Chairman's task is depth 0; its children 1, then 2, then 3


class DelegationDepthError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            f"Delegation stopped: a task can be handed on at most {MAX_DELEGATION_DEPTH} times."
        )


# ---------------------------------------------------------------- text matching (no database)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def keyword_hit(keyword: str, text: str) -> bool:
    """`keyword` (a word or a phrase) appears in `text` as whole words; single words also match
    their plain plural. `text` must already be lower-case."""
    plural = "(?:e?s)?" if " " not in keyword and "-" not in keyword else ""
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}{plural}(?![a-z0-9])", text) is not None


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def significant_words(text: str) -> list[str]:
    """Lower-case words of `text` without stop words and very short words, in order, no repeats."""
    words = [word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) >= 3 and word not in STOPWORDS]
    return list(dict.fromkeys(words))


@dataclass(frozen=True)
class UpazilaInfo:
    id: int
    name: str
    template_key: str | None
    sort_order: int = 0
    union_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class Classification:
    upazila: UpazilaInfo | None
    matched: tuple[str, ...] = ()
    reason: str | None = None  # why nothing matched (only when upazila is None)


def upazila_keywords(upazila: UpazilaInfo) -> list[str]:
    """The keywords that speak for an Upazila: its template's list plus the words of its own name.
    An Upazila without a template is also known by the words of its Union names."""
    keywords = list(ROUTING_KEYWORDS.get(upazila.template_key or "", ()))
    keywords += significant_words(upazila.name)
    if upazila.template_key is None:
        for union_name in upazila.union_names:
            keywords += significant_words(union_name)
    return list(dict.fromkeys(keywords))


def classify(text: str, upazilas: Sequence[UpazilaInfo], topic_names: dict[str, str] | None = None) -> Classification:
    """Pick the Upazila whose keywords appear most often in `text` (ties: the first in the village's
    order). With no hit at all the result carries a human-readable reason instead."""
    normalised = _normalise(text)
    best: tuple[int, int, int] | None = None
    winner: tuple[UpazilaInfo, list[str]] | None = None
    for upazila in upazilas:
        matched = [keyword for keyword in upazila_keywords(upazila) if keyword_hit(keyword, normalised)]
        if not matched:
            continue
        rank = (-len(matched), upazila.sort_order, upazila.id)
        if best is None or rank < best:
            best, winner = rank, (upazila, matched)
    if winner is not None:
        return Classification(upazila=winner[0], matched=tuple(winner[1]))

    # Nothing in the village matched. Say whether the request at least looks like a known topic.
    topics = []
    for key, keywords in ROUTING_KEYWORDS.items():
        matched = [keyword for keyword in keywords if keyword_hit(keyword, normalised)]
        if matched:
            topics.append((-len(matched), key, matched))
    if topics:
        _score, key, matched = min(topics)
        label = (topic_names or {}).get(key, key.capitalize())
        return Classification(
            upazila=None,
            reason=(
                f"This looks like a request for '{label}' (matched: {', '.join(matched)}), but the village has no "
                "Upazila for it. Create that Upazila under Upazila Management, add an agent to it and send the "
                "request again."
            ),
        )
    if not upazilas:
        return Classification(
            upazila=None,
            reason="The village has no Upazilas yet, so there is nowhere to send this request. "
            "Create an Upazila and an agent first.",
        )
    return Classification(
        upazila=None,
        reason=(
            "The Central Manager could not tell which Upazila this request belongs to: none of its routing "
            "keywords appear in the text. Mention the subject (for example study, exam, business, job, research, "
            "project or routine) or the name of the Upazila."
        ),
    )


def agent_match(text: str, row: Any) -> list[str]:
    """Words of the request that also describe the agent: its role and description, its Ward and
    its Union. `row` is a row of `agent_rows_query`."""
    agent, _template, _office, ward, union, _upazila = row
    about = " ".join(
        [agent.role, agent.description, ward.name if ward else "", ward.responsibility if ward else "", union.name if union else ""]
    )
    known = {_stem(word) for word in significant_words(about)}
    return [word for word in significant_words(text) if _stem(word) in known]


def pick_agent(text: str, rows: Sequence[Any]) -> tuple[Any, list[str]] | None:
    """The agent with the most matching words; with no match at all, simply the first one."""
    best: tuple[int, int] | None = None
    winner: tuple[Any, list[str]] | None = None
    for row in rows:
        matched = agent_match(text, row)
        rank = (-len(matched), row[0].id)
        if best is None or rank < best:
            best, winner = rank, (row, matched)
    return winner


# ---------------------------------------------------------------- database side


def central_manager(db: Session) -> Agent | None:
    return db.execute(select(Agent).where(Agent.is_central_manager.is_(True))).scalar_one_or_none()


def load_upazilas(db: Session) -> list[UpazilaInfo]:
    unions: dict[int, list[str]] = {}
    for upazila_id, name in db.execute(select(UnionUnit.upazila_id, UnionUnit.name).order_by(UnionUnit.sort_order)):
        unions.setdefault(upazila_id, []).append(name)
    return [
        UpazilaInfo(
            id=upazila.id,
            name=upazila.name,
            template_key=upazila.template_key,
            sort_order=upazila.sort_order,
            union_names=tuple(unions.get(upazila.id, ())),
        )
        for upazila in db.execute(select(Upazila).order_by(Upazila.sort_order, Upazila.id)).scalars()
    ]


def request_text(task: Task) -> str:
    return f"{task.title}\n{task.description}".strip()


@dataclass(frozen=True)
class Routing:
    """Where the Central Manager sends a request — or why it cannot (`reason`)."""

    row: Any | None = None  # the chosen agent (a row of agent_rows_query)
    details: dict[str, Any] | None = None  # stored with the delegation: Upazila, keywords, agent
    reason: str | None = None


def route(db: Session, task: Task) -> Routing:
    text = request_text(task)
    topic_names = dict(db.execute(select(UpazilaTemplate.key, UpazilaTemplate.name)).all())
    found = classify(text, load_upazilas(db), topic_names)
    if found.upazila is None:
        return Routing(reason=found.reason)
    upazila = found.upazila
    keywords = ", ".join(found.matched)
    in_upazila = agent_rows_query().where(Upazila.id == upazila.id, Agent.is_central_manager.is_(False))
    # Paused and disabled agents never receive tasks.
    candidates = db.execute(in_upazila.where(Agent.lifecycle == "active").order_by(Agent.id)).all()
    picked = pick_agent(text, candidates)
    if picked is None:
        inactive = db.execute(
            select(func.count()).select_from(in_upazila.where(Agent.lifecycle != "active").subquery())
        ).scalar_one()
        resting = f" ({inactive} agent{'s' if inactive != 1 else ''} there {'are' if inactive != 1 else 'is'} paused or disabled.)" if inactive else ""
        return Routing(
            reason=(
                f"The request was matched to '{upazila.name}' (keywords: {keywords}), but that Upazila has no "
                f"active agent.{resting} Create or activate an agent in one of its Offices and send the request again."
            )
        )
    row, agent_words = picked
    agent, _template, office, ward, union, upazila_row = row
    location = location_of(office, ward, union, upazila_row)
    return Routing(
        row=row,
        details={
            "upazila_id": upazila.id,
            "upazila_name": upazila.name,
            "matched_keywords": list(found.matched),
            "agent_id": agent.id,
            "agent_name": agent.display_name,
            "agent_role": agent.role,
            "agent_path": location.path,
            "agent_matched_words": agent_words,
            "active_candidates": len(candidates),
            "method": "demo keyword routing",
        },
    )


def delegate(
    db: Session,
    parent: Task,
    agent: Agent,
    routing: dict[str, Any] | None = None,
    *,
    title: str | None = None,
    description: str | None = None,
) -> Task:
    """Create a child task of `parent` for `agent` and log the delegation as a message. The child
    repeats the parent's title and description unless others are given.

    Permission is NOT checked here: callers go through the `task.create_child` tool
    (app.tools.call_tool). The caller commits. Raises DelegationDepthError beyond
    MAX_DELEGATION_DEPTH.
    """
    if parent.depth + 1 > MAX_DELEGATION_DEPTH:
        raise DelegationDepthError
    if parent.assigned_agent_id is None:
        raise ValueError("only a task that has an agent can be delegated")
    child = Task(
        title=title or parent.title,
        description=parent.description if description is None else description,
        created_by=f"agent:{parent.assigned_agent_id}",
        assigned_agent_id=agent.id,
        parent_task_id=parent.id,
        depth=parent.depth + 1,
        kind="delegated",
        priority=parent.priority,
        input={"request": request_text(parent), "parent_task_id": parent.id, "routing": routing or {}},
        status=ASSIGNED,
    )
    db.add(child)
    db.flush()
    db.add(
        AgentMessage(
            sender_agent_id=parent.assigned_agent_id,
            receiver_agent_id=agent.id,
            task_id=child.id,
            type="delegation",
            payload={"parent_task_id": parent.id, "title": child.title, "routing": routing or {}},
        )
    )
    return child


def child_results(children: Sequence[Task], agent_names: dict[int, str]) -> str:
    """What every child task returned, one block per child."""
    lines: list[str] = []
    for child in children:
        name = agent_names.get(child.assigned_agent_id or 0, "an agent")
        if lines:
            lines.append("")
        if child.status == SUCCEEDED:
            lines += [f"--- Result from {name} (task #{child.id}) ---", child.output or ""]
        else:
            lines += [f"--- No result from {name} (task #{child.id}: {child.status}) ---", child.error or ""]
    return "\n".join(lines)


def final_report(parent: Task, children: Sequence[Task], agent_names: dict[int, str]) -> str:
    """The parent's output: where the request went and what every child task returned."""
    done = [child for child in children if child.status == SUCCEEDED]
    lines = [f"{DEMO_PREFIX} Central Manager report", f"Request: {parent.title}"]
    for child in children:
        routing = (child.input or {}).get("routing") or {}
        if routing:
            lines.append(
                f"Routed to: {routing.get('upazila_name')} (matched: {', '.join(routing.get('matched_keywords', []))})"
                f" → {routing.get('agent_name')} ({routing.get('agent_role')}), {routing.get('agent_path')}"
            )
    lines.append(f"Delegated tasks: {len(done)} succeeded, {len(children) - len(done)} not completed")
    lines += ["", child_results(children, agent_names)]
    lines += [
        "",
        "The Central Manager did not do this work itself: it routed the request by keywords and collected the "
        "result. No AI model was used and the result was not checked.",
    ]
    return "\n".join(lines)
