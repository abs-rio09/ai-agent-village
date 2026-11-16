"""Demo provider: rule-based replies with no AI model and no network access.

Every reply starts with "[Demo]" and says in plain words that it is not an AI answer. The text
is a fixed outline for the agent's role, so the whole task flow can be tried without any key.

Demo phrases: a few fixed wordings make the Demo agent ASK for a tool, so tools, permissions
and approvals can be tried without an AI model. Whether the tool runs is decided elsewhere
(app.tools.call_tool) — the provider only asks.
  "send message to customer"        → message.send_external (SENSITIVE: needs the Chairman's approval)
  "remember that <something>"       → memory.write into the agent's own notes
  "what do you remember …"          → memory.read of everything the agent may read
"""

from __future__ import annotations

import re

from app.providers.base import AgentContext, AgentReply, Provider, TaskContext, ToolRequest

DEMO_PREFIX = "[Demo]"
# The phrase documented for trying the approval flow. Any "send (a) message/email/reply to X" works.
DEMO_APPROVAL_PHRASE = "send message to customer"
DEMO_REMEMBER_PHRASE = "remember that my exam is on Friday"
DEMO_RECALL_PHRASE = "what do you remember about my exam"
_REMEMBER = re.compile(r"\b(?:remember|note)(?:\s+that\b|\s*:)\s*(.{3,})", re.I | re.S)
_RECALL = re.compile(r"\bwhat do you remember\b|\brecall\b", re.I)
_SEND_EXTERNAL = re.compile(
    r"\bsend\s+(?:(?:an?|the)\s+)?(message|e-?mail|reply)\s+to\s+(?:(?:the|a|an|our|my)\s+)?([a-z][a-z'-]{1,30})", re.I
)

# What an agent of each template would do with a request: three fixed steps per role.
_PLAYBOOKS: dict[str, tuple[str, str, str]] = {
    "village_manager": (
        "Work out which Upazila and Office the request belongs to.",
        "Delegate it to an active agent there.",
        "Collect the results and write the final report.",
    ),
    "office_manager": (
        "Check which agent in this Office is the right one for the request.",
        "Split the request into small tasks and hand them out.",
        "Follow up and report the Office's progress.",
    ),
    "pion_helper": (
        "Collect the information or files the request needs.",
        "File them where the Office keeps such things.",
        "Tell the Office Manager what was done and what is missing.",
    ),
    "study_assistant": (
        "List the subjects, topics and deadlines the request is about.",
        "Make a realistic study plan with short daily blocks and a revision slot.",
        "Set check points to measure progress before the deadline.",
    ),
    "teacher_tutor": (
        "Find out what is already understood and what is not.",
        "Explain the topic step by step with a small example.",
        "Give a few practice questions and review the answers.",
    ),
    "research_librarian": (
        "Turn the request into search terms and inclusion rules.",
        "Find and list the relevant sources among the permitted documents.",
        "Summarise each source and keep the references organised.",
    ),
    "business_manager": (
        "State the business goal and the assumptions behind it.",
        "Compare the options with their cost, effort and risk.",
        "Propose next steps and name what needs the Chairman's approval.",
    ),
    "sales_assistant": (
        "Look up the product details and availability.",
        "Draft the offer or the follow-up message.",
        "Hand the draft to the Chairman for approval before anything is sent.",
    ),
    "customer_support": (
        "Read the customer's question and find the facts that answer it.",
        "Draft a polite, accurate reply.",
        "Mark anything that needs a decision, such as a refund, for the Chairman.",
    ),
    "accountant": (
        "Collect the income and expense entries the request covers.",
        "Check them for gaps and obvious mistakes.",
        "Prepare a short summary with totals.",
    ),
    "daily_reporter": (
        "Collect what was finished today in each Office.",
        "List what is pending and what is blocked.",
        "Write a short report with the points that need the Chairman's attention.",
    ),
    "doctor_wellness": (
        "Share general, widely accepted health and wellness information on the topic.",
        "Suggest simple healthy-routine ideas such as sleep, water, movement and breaks.",
        "Point to a qualified doctor for symptoms, medicines or any medical decision.",
    ),
    "repair_technician": (
        "Describe the problem and collect what the approved health checks report.",
        "Name the most likely cause.",
        "Propose safe steps and ask for approval before any change is made.",
    ),
    "technical_support": (
        "Reproduce what the Chairman is trying to do.",
        "Explain the steps one by one.",
        "Point to the page of the village where it is done.",
    ),
    "project_manager": (
        "Break the project into milestones and small tasks.",
        "Name the risks and what each task depends on.",
        "Propose an order of work and a way to track progress.",
    ),
}
_GENERIC_PLAYBOOK = (
    "Read the request and note what is being asked.",
    "Do the part that belongs to this role.",
    "Report the result and what is still open.",
)

# Extra lines that must be part of every reply of a role, whatever the request says.
_ROLE_NOTES: dict[str, str] = {
    "doctor_wellness": (
        "Important: this is general wellness information only. It is not a diagnosis and not a prescription. "
        "For symptoms, medicines or an emergency, see a qualified doctor."
    ),
    "repair_technician": (
        "Important: a repair technician works with approved tools only and has no terminal access. "
        "No command was run."
    ),
}


def _one_line(value: str, limit: int = 200) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class DemoProvider(Provider):
    name = "demo"

    def is_configured(self) -> bool:
        return True  # needs no key and no network

    def reply(self, agent: AgentContext, task: TaskContext) -> str | AgentReply:
        text = self._outline(agent, task)
        request = f"{task.title}\n{task.description}"
        wanted = _SEND_EXTERNAL.search(request)
        if wanted is None:
            recall = _RECALL.search(request)
            if recall is not None:
                text += "\n\nThe request asks what this agent remembers, so it asks to use the tool “Read memory”."
                return AgentReply(text=text, tool_calls=(ToolRequest("memory.read", {}, reason="The request asks what is remembered."),))
            remember = _REMEMBER.search(request)
            if remember is not None:
                fact = _one_line(remember.group(1), 1000)
                text += "\n\nThe request asks to remember something, so this agent asks to use the tool “Write memory” for its own notes."
                call = ToolRequest(
                    "memory.write",
                    {"scope": "agent", "title": _one_line(fact, 80), "content": fact},
                    reason="The request asks to remember this.",
                )
                return AgentReply(text=text, tool_calls=(call,))
            return text  # plain text: no tool is asked for
        channel, recipient = wanted.group(1).lower().replace("-", ""), wanted.group(2).lower()
        text += (
            "\n\nThe request asks for a message to someone outside the village, so this agent asks to use the "
            "tool “Send external message”. That tool always needs the Chairman's approval — and even when it is "
            "approved, nothing is really sent: no connector exists yet."
        )
        call = ToolRequest(
            tool="message.send_external",
            args={
                "recipient": recipient,
                "channel": "message" if channel == "reply" else channel,
                "body": f"{DEMO_PREFIX} draft, not written by an AI model: {_one_line(task.title, 300)}",
            },
            reason=f"The request says: “{_one_line(task.title, 200)}”",
        )
        return AgentReply(text=text, tool_calls=(call,))

    def _outline(self, agent: AgentContext, task: TaskContext) -> str:
        steps = _PLAYBOOKS.get(agent.template_key or "", _GENERIC_PLAYBOOK)
        where = f", {agent.location}" if agent.location else ""
        lines = [
            f"{DEMO_PREFIX} {agent.display_name} ({agent.role}{where})",
            f"Task: {_one_line(task.title)}",
        ]
        if task.description.strip():
            lines.append(f"Details: {_one_line(task.description, 400)}")
        lines += [
            "",
            "This is a Demo Mode reply: no AI model was used and nothing was looked up. "
            f"It only shows the steps a {agent.role} would take with this request:",
            *[f"{number}. {step}" for number, step in enumerate(steps, start=1)],
        ]
        note = _ROLE_NOTES.get(agent.template_key or "")
        if note:
            lines += ["", note]
        return "\n".join(lines)
