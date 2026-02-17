"""Procedure version diff logic."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepDiff:
    """Diff result for a single step."""

    status: str  # "added", "removed", "modified", "unchanged"
    step_a: dict[str, Any] | None = None
    step_b: dict[str, Any] | None = None
    changed_fields: list[str] = field(default_factory=list)


_STEP_COMPARE_FIELDS = [
    "title",
    "instructions",
    "is_contingency",
    "estimated_duration_minutes",
    "required_data_schema",
]


def diff_procedure_versions(
    content_a: dict[str, Any],
    content_b: dict[str, Any],
) -> tuple[list[str], list[StepDiff]]:
    """Compare two procedure version content dicts.

    Returns:
        Tuple of (procedure-level changed field names, list of StepDiff).
    """
    # Procedure-level changes
    proc_changes: list[str] = []
    for pf in ("procedure_name", "procedure_description"):
        if content_a.get(pf) != content_b.get(pf):
            proc_changes.append(pf)

    # Build step lookups keyed by step_number
    steps_a = {s["step_number"]: s for s in content_a.get("steps", []) if "step_number" in s}
    steps_b = {s["step_number"]: s for s in content_b.get("steps", []) if "step_number" in s}

    all_step_numbers = sorted(
        set(steps_a.keys()) | set(steps_b.keys()),
        key=_step_sort_key,
    )

    diffs: list[StepDiff] = []
    for sn in all_step_numbers:
        sa = steps_a.get(sn)
        sb = steps_b.get(sn)

        if sa and not sb:
            diffs.append(StepDiff(status="removed", step_a=sa))
        elif sb and not sa:
            diffs.append(StepDiff(status="added", step_b=sb))
        else:
            # Both exist — compare fields
            changed = []
            for f in _STEP_COMPARE_FIELDS:
                if sa.get(f) != sb.get(f):
                    changed.append(f)
            if changed:
                diffs.append(StepDiff(status="modified", step_a=sa, step_b=sb, changed_fields=changed))
            else:
                diffs.append(StepDiff(status="unchanged", step_a=sa, step_b=sb))

    return proc_changes, diffs


def _step_sort_key(sn: str) -> tuple:
    """Sort step numbers: 1, 1.1, 1.2, 2, C1, C2."""
    is_contingency = sn.startswith("C")
    num_part = sn.lstrip("C")
    parts = num_part.split(".")
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return (is_contingency, nums)
