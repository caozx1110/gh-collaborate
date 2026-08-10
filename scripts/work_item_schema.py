#!/usr/bin/env python3
"""Validate work-item schema and risk policy from parsed Markdown structure."""

from __future__ import annotations

import re
from typing import TypedDict

if __package__:
    from .work_item_markdown import DocumentStructure, Section, Subsection
else:
    from work_item_markdown import DocumentStructure, Section, Subsection


SECTIONS = {
    "epic": (
        "Final goal",
        "Success criteria",
        "Baseline and design",
        "Scope",
        "Non-goals",
        "Waves and dependencies",
        "Risks, migration, and rollback",
        "Global definition of done",
    ),
    "issue": (
        "Problem and evidence",
        "Outcome",
        "Scope",
        "Non-goals",
        "Design basis and approach",
        "Dependencies and ownership",
        "Risks, migration, and rollback",
        "Acceptance checklist",
        "Test plan",
        "State",
    ),
    "checkpoint": ("Checkpoint",),
    "pr": (
        "Outcome and references",
        "Scope and non-goals",
        "Implementation",
        "Candidate and validation",
        "Risks and rollback",
        "Known limits and follow-ups",
    ),
}
FIELDS = {
    "issue": {
        "Dependencies and ownership": (
            "Risk class",
            "Risk triggers",
            "Complexity estimate",
        ),
        "State": (
            "Stage",
            "Baseline",
            "Last remote SHA",
            "Blocker",
            "Next action",
        ),
    },
    "checkpoint": {
        "Checkpoint": (
            "Stage",
            "Branch",
            "Full remote SHA",
            "Completed",
            "Remaining",
            "Validation",
            "Blocker",
            "Next action",
        ),
    },
    "pr": {
        "Candidate and validation": (
            "Candidate full SHA",
            "Base evidence",
            "Tests and Actions",
        ),
    },
}
REQUIRED = {kind: list(sections) for kind, sections in SECTIONS.items()}
STAGES = frozenset(
    {"draft", "ready", "in-progress", "blocked", "in-review", "merged", "closed"}
)
EMPTY_VALUE = "none"
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")
POLICY_REFERENCE = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+"
    r"(?:#[A-Za-z0-9_.-]+)?"
)
RISK_CLASSES = frozenset({"ordinary", "enhanced", "high"})
RISK_TRIGGERS = frozenset(
    {
        "security",
        "privacy",
        "persistence",
        "transaction",
        "migration",
        "concurrency",
        "shared-paths",
        "budget",
        "decomposition",
    }
)
NEW_PRIMITIVES = frozenset({"storage", "transaction", "migration", "concurrency"})
DEFAULT_PRODUCTION_FILE_BUDGET = 10
DEFAULT_NET_LINE_BUDGET = 500
MAX_COUNT_DIGITS = 9
PRIMITIVE_TRIGGERS = {
    "storage": "persistence",
    "transaction": "transaction",
    "migration": "migration",
    "concurrency": "concurrency",
}
RISK_MATERIALS = {
    "security": ("Risks, migration, and rollback", "Threat model"),
    "privacy": ("Risks, migration, and rollback", "Threat model"),
    "persistence": ("Risks, migration, and rollback", "Data invariants and recovery"),
    "transaction": ("Risks, migration, and rollback", "Data invariants and recovery"),
    "migration": ("Risks, migration, and rollback", "Data invariants and recovery"),
    "concurrency": ("Design basis and approach", "Concurrency model"),
    "shared-paths": ("Dependencies and ownership", "Ownership and integration plan"),
    "budget": ("Design basis and approach", "Scope and budget decision"),
    "decomposition": ("Dependencies and ownership", "Parent/child delivery plan"),
}
HIGH_RISK_AUDIT = ("Design basis and approach", "Pre-implementation design audit")


class ComplexityEstimate(TypedDict):
    production_files: int
    net_production_lines: int
    new_primitives: set[str]
    budget_override: str | None
    production_file_budget: int
    net_production_line_budget: int


def _code_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1]
    return stripped


def _parse_named_set(
    value: str, allowed: frozenset[str], label: str
) -> tuple[set[str] | None, str | None]:
    normalized = _code_value(value)
    if normalized == EMPTY_VALUE:
        return set(), None
    items = [item.strip() for item in normalized.split(",")]
    if any(not item for item in items):
        return None, f"{label} must be none or a comma-separated list"
    if len(items) != len(set(items)):
        return None, f"{label} must not contain duplicates"
    unknown = sorted(set(items) - allowed)
    if unknown:
        return None, f"{label} contains unsupported values: {', '.join(unknown)}"
    return set(items), None


def _parse_complexity(value: str) -> tuple[ComplexityEstimate | None, str | None]:
    parts: dict[str, str] = {}
    for segment in _code_value(value).split(";"):
        if "=" not in segment:
            return None, "must use key=value segments separated by semicolons"
        key, item = (part.strip() for part in segment.split("=", 1))
        if not key or not item:
            return None, "must not contain an empty key or value"
        if key in parts:
            return None, f"must not repeat {key}"
        parts[key] = item

    required = {"production files", "net production lines", "new primitives"}
    override_fields = {
        "budget override",
        "production file budget",
        "net production line budget",
    }
    allowed = required | override_fields
    missing = sorted(required - set(parts))
    unknown = sorted(set(parts) - allowed)
    if missing:
        return None, "is missing: " + ", ".join(missing)
    if unknown:
        return None, "contains unsupported keys: " + ", ".join(unknown)
    present_overrides = set(parts) & override_fields
    if present_overrides and present_overrides != override_fields:
        missing_overrides = sorted(override_fields - present_overrides)
        return None, "budget override is missing: " + ", ".join(missing_overrides)
    numeric_fields = ["production files", "net production lines"]
    if present_overrides:
        numeric_fields.extend(["production file budget", "net production line budget"])
    for key in numeric_fields:
        if not re.fullmatch(r"\d+", parts[key]):
            return None, f"requires a non-negative integer for {key}"
        if len(parts[key]) > MAX_COUNT_DIGITS:
            return None, f"requires at most {MAX_COUNT_DIGITS} digits for {key}"
    primitives, error = _parse_named_set(
        parts["new primitives"], NEW_PRIMITIVES, "new primitives"
    )
    if error or primitives is None:
        return None, error
    override = parts.get("budget override")
    if override is not None:
        policy_path = override.split("#", 1)[0]
        if (
            not POLICY_REFERENCE.fullmatch(override)
            or any(part in {".", ".."} for part in policy_path.split("/"))
        ):
            return None, "budget override must be a relative tracked-policy reference"
    production_file_budget = int(
        parts.get("production file budget", str(DEFAULT_PRODUCTION_FILE_BUDGET))
    )
    net_production_line_budget = int(
        parts.get("net production line budget", str(DEFAULT_NET_LINE_BUDGET))
    )
    return {
        "production_files": int(parts["production files"]),
        "net_production_lines": int(parts["net production lines"]),
        "new_primitives": primitives,
        "budget_override": override,
        "production_file_budget": production_file_budget,
        "net_production_line_budget": net_production_line_budget,
    }, None


def _invalid_value(field: str, value: str) -> str | None:
    normalized = _code_value(value)
    if not normalized:
        return "must not be empty"
    if field == "Stage":
        if normalized not in STAGES:
            return "must be one of: " + ", ".join(sorted(STAGES))
        return None
    if field == "Risk class":
        if normalized not in RISK_CLASSES:
            return "must be one of: " + ", ".join(sorted(RISK_CLASSES))
        return None
    if field == "Risk triggers":
        _, error = _parse_named_set(value, RISK_TRIGGERS, "risk triggers")
        return error
    if field == "Complexity estimate":
        _, error = _parse_complexity(value)
        return error
    if field in {"Baseline", "Full remote SHA", "Candidate full SHA"}:
        if not FULL_SHA.fullmatch(normalized):
            return "must contain exactly one 40-character SHA"
        return None
    if field == "Last remote SHA":
        if normalized == EMPTY_VALUE or FULL_SHA.fullmatch(normalized):
            return None
        return "must be a 40-character SHA or the explicit value none"
    if field == "Blocker":
        return None
    if normalized == EMPTY_VALUE:
        return "must not use the empty value none"
    return None


def _finding(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def _validate_issue_screening(
    unique: dict[str, Section], subsections: list[Subsection]
) -> list[dict[str, str]]:
    section = unique.get("Dependencies and ownership")
    if section is None:
        return []
    fields = section["canonical_fields"]
    required = ("Risk class", "Risk triggers", "Complexity estimate")
    if any(len(fields.get(field, [])) != 1 for field in required):
        return []

    risk_class = _code_value(fields["Risk class"][0])
    triggers, trigger_error = _parse_named_set(
        fields["Risk triggers"][0], RISK_TRIGGERS, "risk triggers"
    )
    estimate, estimate_error = _parse_complexity(fields["Complexity estimate"][0])
    if risk_class not in RISK_CLASSES or trigger_error or estimate_error:
        return []
    assert triggers is not None and estimate is not None

    findings: list[dict[str, str]] = []
    if risk_class == "ordinary" and triggers:
        findings.append(
            _finding("invalid-risk-class", "ordinary Issues must use Risk triggers: none")
        )
    if risk_class != "ordinary" and not triggers:
        findings.append(
            _finding("invalid-risk-class", f"{risk_class} Issues require at least one risk trigger")
        )

    expected: set[str] = {
        PRIMITIVE_TRIGGERS[primitive] for primitive in estimate["new_primitives"]
    }
    if (
        estimate["production_files"] > estimate["production_file_budget"]
        or estimate["net_production_lines"] > estimate["net_production_line_budget"]
    ):
        expected.add("budget")
    for missing in sorted(expected - triggers):
        findings.append(
            _finding(
                "missing-risk-trigger",
                f"Complexity estimate requires the {missing} risk trigger",
            )
        )
    if risk_class == "ordinary" and expected:
        findings.append(
            _finding(
                "invalid-risk-class",
                "ordinary Issues cannot exceed the applicable budget or add new primitives",
            )
        )

    by_identity: dict[tuple[str, str], list[Subsection]] = {}
    for subsection in subsections:
        identity = (subsection["parent"], subsection["title"])
        by_identity.setdefault(identity, []).append(subsection)
    materials = {RISK_MATERIALS[trigger] for trigger in triggers}
    if risk_class == "high":
        materials.add(HIGH_RISK_AUDIT)
    for parent, title in sorted(materials):
        matches = by_identity.get((parent, title), [])
        identity = f"{parent}: {title}"
        if not matches:
            findings.append(_finding("missing-risk-material", identity))
            continue
        if len(matches) > 1:
            findings.append(_finding("duplicate-risk-material", identity))
        if any(not match["has_material_content"] for match in matches):
            findings.append(_finding("empty-risk-material", identity))
    return findings


def validate_structure(
    kind: str, document: DocumentStructure
) -> list[dict[str, str]]:
    """Validate schema and policy without reading raw Markdown."""

    findings: list[dict[str, str]] = []
    if document["has_raw_html"]:
        findings.append(
            _finding(
                "raw-html",
                "line-start raw HTML is not allowed; use Markdown or a code block",
            )
        )
    if document["has_noncanonical_fence"]:
        findings.append(
            _finding(
                "noncanonical-fence",
                "fenced code openers must start at column zero",
            )
        )
    by_title: dict[str, list[Section]] = {}
    for section in document["sections"]:
        by_title.setdefault(str(section["title"]), []).append(section)

    unique: dict[str, Section] = {}
    for title in SECTIONS[kind]:
        matches = by_title.get(title, [])
        if not matches:
            findings.append(_finding("missing-section", title))
            continue
        if len(matches) > 1:
            findings.append(_finding("duplicate-section", title))
        else:
            unique[title] = matches[0]
        if any(not section["has_content"] for section in matches):
            findings.append(_finding("empty-section", title))

    for section_title, required_fields in FIELDS.get(kind, {}).items():
        section = unique.get(section_title)
        if section is None:
            continue
        parsed_fields = (
            section["canonical_fields"] if kind == "issue" else section["fields"]
        )
        for field in required_fields:
            values = parsed_fields.get(field, [])
            if not values:
                findings.append(_finding("missing-field", f"{section_title}: {field}"))
                if kind == "checkpoint" and field == "Full remote SHA":
                    findings.append(
                        _finding(
                            "full-sha",
                            "Full remote SHA must contain exactly one 40-character SHA",
                        )
                    )
                continue
            if len(values) > 1:
                findings.append(_finding("duplicate-field", f"{section_title}: {field}"))
                if kind == "checkpoint" and field == "Full remote SHA":
                    findings.append(
                        _finding(
                            "full-sha",
                            "Full remote SHA must contain exactly one 40-character SHA",
                        )
                    )
                continue
            error = _invalid_value(field, values[0])
            if error:
                findings.append(
                    _finding("invalid-value", f"{section_title}: {field} {error}")
                )
                if kind == "checkpoint" and field == "Full remote SHA":
                    findings.append(
                        _finding(
                            "full-sha",
                            "Full remote SHA must contain exactly one 40-character SHA",
                        )
                    )
    if kind == "issue":
        findings.extend(_validate_issue_screening(unique, document["subsections"]))
    return findings
