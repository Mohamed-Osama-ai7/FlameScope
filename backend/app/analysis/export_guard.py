"""Consumer-side guard for the Lab export: a value is returned only when the export marks it usable.

The export keeps the source number in `values` even for flagged cells (e.g. FLEX-114 ambient pressure 0.0 with
`invalid_nonpositive_pressure`), so consumers must not read `values` directly; `usable` follows the rule of
the analysis and the Data Platform (FlexRun.usable / usable_for_analysis).
"""

from __future__ import annotations

from typing import Any

REJECT_FLAGS = frozenset(
    {"missing_blank", "missing_dash_marker", "unparseable", "invalid_nonpositive_pressure"}
)


def usable_value(record: dict[str, Any], field: str) -> float | None:
    """The numeric value of `field`, or None when it is missing, invalid or not marked usable."""
    if not record.get("usable", {}).get(field, False):
        return None
    if set(record.get("field_flags", {}).get(field, [])) & REJECT_FLAGS:
        return None  # defence in depth: flags win over a stale usable map
    value = record.get("values", {}).get(field)
    return float(value) if isinstance(value, (int, float)) else None
