"""Organization limits: the single source of truth, also sent to the frontend by the API."""

from __future__ import annotations

# docs/SPEC.md: every Union has 9 Wards. A Union may never hold more than this, whether the
# wards come from "Add ward", from "Generate Standard Structure", or from a template.
MAX_WARDS_PER_UNION = 9
