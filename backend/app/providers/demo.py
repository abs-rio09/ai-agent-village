"""Demo provider: rule-based replies with no AI model and no network access.

Every reply starts with "[Demo]" and says in plain words that it is not an AI answer. The text
is a fixed outline for the agent's role, so the whole task flow can be tried without any key.
"""

from __future__ import annotations

import re

from app.providers.base import AgentContext, Provider, TaskContext

DEMO_PREFIX = "[Demo]"

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

    def reply(self, agent: AgentContext, task: TaskContext) -> str:
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
