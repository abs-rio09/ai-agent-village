"""organization: templates, upazila, union_unit, ward, office (+ seeded templates)

Revision ID: 0003
Revises: 0002

Seeds the six Upazila templates of docs/SPEC.md §5 with the five Union names each from §11,
a default ward set per template, and the single Central Administration office.
No Upazila, Union or Ward is created here: structure is generated on demand from the UI.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# (key, name, icon, [union names])  — names exactly as written in docs/SPEC.md §5 and §11.
TEMPLATES: list[tuple[str, str, str, list[str]]] = [
    (
        "study",
        "Study Upazila",
        "graduation-cap",
        ["Academic Management", "Course Learning", "Exam Preparation", "Research Paper Learning", "Academic Documentation"],
    ),
    (
        "business",
        "Business Upazila",
        "store",
        ["Business Strategy", "Product Management", "Marketing & Branding", "Customer & Sales", "Finance & Operations"],
    ),
    (
        "career",
        "Career & Job Preparation Upazila",
        "briefcase",
        ["Software Engineering Skills", "Competitive Programming", "Job Opportunities", "CV & Portfolio", "Interview Preparation"],
    ),
    (
        "research",
        "Research Upazila",
        "flask",
        ["Paper Discovery", "Literature Review", "Research Topic Discovery", "Data Analysis", "Research Documentation"],
    ),
    (
        "project",
        "Project Development Upazila",
        "code",
        ["Project Planning", "Frontend Development", "Backend Development", "Database & API", "Testing & Deployment"],
    ),
    (
        "personal",
        "Personal Management Upazila",
        "user",
        ["Daily Routine", "Task Management", "File Management", "Knowledge Management", "Daily Reporting"],
    ),
]

# SPEC §11 "Suggested Ward responsibilities" exists for Study only.
STUDY_WARDS = [
    "Class Routine",
    "Assignment & Deadline",
    "Exam Preparation",
    "Learning Materials",
    "Note Making",
    "Course Tutor",
    "Academic Progress",
    "Study Planning",
    "Daily Academic Reporting",
]
# The SPEC gives no ward list for the other templates: placeholders "Ward 1".."Ward 9" with an
# empty responsibility, to be renamed by the owner in the Templates editor (no code change).
PLACEHOLDER_WARD_COUNT = 9


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    ]


def _set_schema_version(version: str) -> None:
    op.execute(
        sa.text("UPDATE app_meta SET value = :v, updated_at = CURRENT_TIMESTAMP WHERE key = 'schema_version'").bindparams(
            v=version
        )
    )


def upgrade() -> None:
    upazila_template = op.create_table(
        "upazila_template",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_upazila_template_name"),
    )
    union_template = op.create_table(
        "union_template",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "upazila_template_key",
            sa.String(32),
            sa.ForeignKey("upazila_template.key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("upazila_template_key", "name", name="uq_union_template_key_name"),
    )
    ward_template = op.create_table(
        "ward_template",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "upazila_template_key",
            sa.String(32),
            sa.ForeignKey("upazila_template.key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("responsibility", sa.String(200), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("upazila_template_key", "number", name="uq_ward_template_key_number"),
        sa.CheckConstraint("number >= 1", name="ck_ward_template_number"),
    )
    op.create_table(
        "upazila",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("village_id", sa.Integer, sa.ForeignKey("village.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column(
            "template_key", sa.String(32), sa.ForeignKey("upazila_template.key", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("sort_order", sa.Integer, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("village_id", "name", name="uq_upazila_village_name"),
    )
    op.create_table(
        "union_unit",  # "union" is an SQL keyword
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("upazila_id", sa.Integer, sa.ForeignKey("upazila.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("upazila_id", "name", name="uq_union_unit_upazila_name"),
    )
    op.create_table(
        "ward",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("union_id", sa.Integer, sa.ForeignKey("union_unit.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("responsibility", sa.String(200), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("union_id", "number", name="uq_ward_union_number"),
        sa.CheckConstraint("number >= 1", name="ck_ward_number"),
    )
    office = op.create_table(
        "office",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ward_id", sa.Integer, sa.ForeignKey("ward.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("ward_id", name="uq_office_ward_id"),
        sa.CheckConstraint(
            "(kind = 'ward' AND ward_id IS NOT NULL) OR (kind = 'central' AND ward_id IS NULL)",
            name="ck_office_kind_ward",
        ),
    )
    # At most one central office: a partial unique index over the rows with kind='central'.
    op.create_index(
        "uq_office_single_central", "office", ["kind"], unique=True, sqlite_where=sa.text("kind = 'central'")
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    stamp = {"created_at": now, "updated_at": now}
    op.bulk_insert(
        upazila_template,
        [
            {"key": key, "name": name, "description": "", "icon": icon, "sort_order": index, **stamp}
            for index, (key, name, icon, _unions) in enumerate(TEMPLATES, start=1)
        ],
    )
    op.bulk_insert(
        union_template,
        [
            {"upazila_template_key": key, "name": union_name, "sort_order": index, **stamp}
            for key, _name, _icon, unions in TEMPLATES
            for index, union_name in enumerate(unions, start=1)
        ],
    )
    ward_rows = []
    for key, _name, _icon, _unions in TEMPLATES:
        if key == "study":
            wards = [(label, label) for label in STUDY_WARDS]
        else:
            wards = [(f"Ward {number}", "") for number in range(1, PLACEHOLDER_WARD_COUNT + 1)]
        for number, (ward_name, responsibility) in enumerate(wards, start=1):
            ward_rows.append(
                {
                    "upazila_template_key": key,
                    "number": number,
                    "name": ward_name,
                    "responsibility": responsibility,
                    **stamp,
                }
            )
    op.bulk_insert(ward_template, ward_rows)
    op.bulk_insert(
        office,
        [{"kind": "central", "ward_id": None, "name": "Central Administration", "description": "", **stamp}],
    )
    _set_schema_version("3")


def downgrade() -> None:
    op.drop_index("uq_office_single_central", table_name="office")
    op.drop_table("office")
    op.drop_table("ward")
    op.drop_table("union_unit")
    op.drop_table("upazila")
    op.drop_table("ward_template")
    op.drop_table("union_template")
    op.drop_table("upazila_template")
    _set_schema_version("2")
