"""Keyword table for the Central Manager's Demo routing. Edit the lists here — no other code.

The key is an Upazila template key (see migration 0003). A request is sent to the Upazila
whose keywords appear most often in the request text. A keyword is one word ("exam") or a
phrase ("data analysis"); single words also match their plain plural ("exams").

An Upazila that was not created from a template is matched by the words of its own name and
of its Union names instead.
"""

from __future__ import annotations

ROUTING_KEYWORDS: dict[str, tuple[str, ...]] = {
    "study": (
        "study", "studying", "exam", "class", "classes", "course", "assignment", "homework", "lecture",
        "tutor", "syllabus", "semester", "academic", "quiz", "revision", "lesson", "school", "university",
        "class routine", "note making",
    ),
    "business": (
        "business", "product", "marketing", "brand", "branding", "sales", "customer", "client", "revenue",
        "profit", "pricing", "price", "inventory", "stock", "invoice", "finance", "supplier", "shop", "refund",
    ),
    "career": (
        "career", "job", "cv", "resume", "portfolio", "interview", "internship", "hiring", "recruiter",
        "salary", "linkedin", "cover letter", "competitive programming", "leetcode", "codeforces",
    ),
    "research": (
        "research", "paper", "literature", "citation", "thesis", "dataset", "hypothesis", "experiment",
        "journal", "publication", "data analysis", "research topic",
    ),
    "project": (
        "project", "frontend", "backend", "database", "api", "deploy", "deployment", "bug", "feature", "code",
        "coding", "repository", "release", "sprint", "milestone",
    ),
    "personal": (
        "personal", "routine", "daily", "reminder", "habit", "todo", "to-do", "schedule", "calendar", "errand",
        "files", "daily report",
    ),
}

# Words too general to say anything about where a request belongs. They are ignored in Upazila,
# Union and Ward names and in the request text when an agent is chosen.
STOPWORDS = frozenset(
    """
    a an and the of for to in on at by with from my me i we you your our it its is are be do does please
    help need want make write create get give find show tell can could would should how what when where why
    this that these those about into new some any all more most upazila union ward office management
    preparation development general learning documentation
    """.split()
)
