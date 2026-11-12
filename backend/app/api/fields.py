"""Shared request field types for the organization and template APIs."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

# Names are trimmed and must be 1-80 characters.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Responsibility = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
# An icon is a short key (for example "graduation-cap") that the frontend maps to a drawing.
IconKey = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40, pattern=r"^[a-z0-9-]*$")]
