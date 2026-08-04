#!/usr/bin/env python3
"""Validate generated Epic, Issue, checkpoint, and PR Markdown before posting."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import TypedDict


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
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_.-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic secret assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s]{8,}"
    ),
}
LOCAL_PATH = re.compile(
    r"(?:^|[\s(`])(?:~/(?:\.[\w.-]+/)?|/(?:Users|home|private|tmp|var/folders)/)",
    re.MULTILINE,
)
AUTO_CLOSE = re.compile(
    r"(?i)\b(?:close(?:s|d)?|fix(?:es|ed)?|resolve(?:s|d)?)"
    r"(?:[ \t]*:[ \t]*|[ \t]+)"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+\b"
)
ATX_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.*?)[ \t]*|[ \t]*)$")
FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")
INDENTED_FENCE_OPEN = re.compile(r"^ {1,3}(`{3,}|~{3,})(.*)$")
FIELD_LINE = re.compile(
    r"^ {0,3}(?:[-*+][ \t]+)?([^:\n]+?):[ \t]*(.*?)[ \t]*$"
)
ISSUE_FIELD_LINE = re.compile(r"^- ([^:\n]+?):[ \t]*(.*?)[ \t]*$")
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")
RAW_HTML_TAG_START = re.compile(
    r"^ {0,3}</?[A-Za-z][A-Za-z0-9-]*(?:[\t />]|$)"
)
RAW_HTML_DECLARATION = re.compile(r"^ {0,3}(?:<\?|<!\[CDATA\[|<![A-Za-z])")
HTML_COMMENT_START = re.compile(r"^<!--")
INDENTED_HTML_COMMENT = re.compile(r"^ {1,3}<!--")
CONTAINER_PREFIX = (
    r"^ {0,3}(?:(?:(?:[-+*]|\d{1,9}[.)])[\t ]+|>[\t ]*)[ ]{0,3})+"
)
CONTAINER_HTML_COMMENT = re.compile(CONTAINER_PREFIX + r".*<!--")
CONTAINER_RAW_HTML = re.compile(
    CONTAINER_PREFIX
    + r"(?:</?[A-Za-z][A-Za-z0-9-]*(?:[\t />]|$)|<\?|<!\[CDATA\[|<![A-Za-z])"
)
CONTAINER_FENCE_OPEN = re.compile(CONTAINER_PREFIX + r"(?:`{3,}|~{3,})")
COMMONMARK_ATX_START = re.compile(r"^ {0,3}#{1,6}(?:[\t ]+|$)")
COMMONMARK_FENCE_START = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")
COMMONMARK_CONTAINER_START = re.compile(
    r"^ {0,3}(?:(?:[-+*]|1[.)])[\t ]+\S|>)"
)
COMMONMARK_CONTAINER_WITH_CONTENT = re.compile(
    r"^ {0,3}(?:(?:[-+*]|1[.)])[\t ]+\S|>[\t ]*\S)"
)
COMMONMARK_BLOCK_RULE = re.compile(
    r"^ {0,3}(?:(?:\*[\t ]*){3,}|(?:_[\t ]*){3,}|(?:-[\t ]*){3,}|"
    r"(?:=+|-+)[\t ]*)$"
)
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


class Section(TypedDict):
    title: str
    lines: list[str]
    direct_lines: list[str]


class Subsection(TypedDict):
    parent: str
    title: str
    lines: list[str]


class ComplexityEstimate(TypedDict):
    production_files: int
    net_production_lines: int
    new_primitives: set[str]
    budget_override: str | None
    production_file_budget: int
    net_production_line_budget: int


def _heading_title(value: str) -> str:
    return re.sub(r"[ \t]+#+[ \t]*$", "", value).strip()


def _fence_marker(line: str) -> tuple[str, int] | None:
    match = FENCE_OPEN.match(line)
    if not match:
        return None
    marker = match.group(1)
    return marker[0], len(marker)


def _is_fence_close(line: str, marker: tuple[str, int]) -> bool:
    character, minimum = marker
    return bool(
        re.fullmatch(
            rf" {{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*",
            line,
        )
    )


def _is_indented_code(line: str) -> bool:
    if not line.strip():
        return False
    columns = 0
    for character in line:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - (columns % 4)
        else:
            break
        if columns >= 4:
            return True
    return False


def _backtick_run(line: str, start: int) -> tuple[int, int] | None:
    position = line.find("`", start)
    if position < 0:
        return None
    end = position + 1
    while end < len(line) and line[end] == "`":
        end += 1
    return position, end


def _is_escaped(line: str, position: int) -> bool:
    backslashes = 0
    position -= 1
    while position >= 0 and line[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def _is_code_span_boundary(line: str) -> bool:
    return bool(
        not line.strip()
        or COMMONMARK_ATX_START.match(line)
        or COMMONMARK_FENCE_START.match(line)
        or COMMONMARK_CONTAINER_START.match(line)
        or COMMONMARK_BLOCK_RULE.match(line)
        or RAW_HTML_TAG_START.match(line)
        or RAW_HTML_DECLARATION.match(line)
        or re.match(r"^ {0,3}<!--", line)
    )


def _find_backtick_close(
    lines: list[str], line_index: int, start: int, tick_count: int
) -> tuple[int, int] | None:
    for index in range(line_index, len(lines)):
        if index != line_index and _is_code_span_boundary(lines[index]):
            return None
        cursor = start if index == line_index else 0
        while True:
            tick_run = _backtick_run(lines[index], cursor)
            if tick_run is None:
                break
            tick_start, tick_end = tick_run
            if not _is_escaped(lines[index], tick_start):
                if tick_end - tick_start == tick_count:
                    return index, tick_end
            cursor = tick_end
    return None


def _find_html_comment_close(
    lines: list[str], line_index: int, start: int
) -> tuple[int, int] | None:
    for index in range(line_index, len(lines)):
        if index != line_index and _is_code_span_boundary(lines[index]):
            return None
        position = lines[index].find("-->", start if index == line_index else 0)
        if position >= 0:
            return index, position + 3
    return None


def _outside_multiline_code_spans(lines: list[str]) -> list[str]:
    outside: list[str] = []
    close_line = -1
    for line_index, line in enumerate(lines):
        if line_index <= close_line:
            if line_index == close_line:
                close_line = -1
            continue
        outside.append(line)
        cursor = 0
        while True:
            tick_run = _backtick_run(line, cursor)
            if tick_run is None:
                break
            tick_start, tick_end = tick_run
            if _is_escaped(line, tick_start):
                cursor = tick_start + 1
                continue
            close = _find_backtick_close(
                lines, line_index, tick_end, tick_end - tick_start
            )
            if close is None:
                cursor = tick_end
                continue
            if close[0] > line_index:
                close_line = close[0]
                break
            cursor = close[1]
    return outside


def _mask_html_comments(text: str) -> str:
    masked_lines: list[str] = []
    comment_open = False
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        if fence is not None:
            masked_lines.append(line)
            if _is_fence_close(line, fence):
                fence = None
            continue
        if comment_open:
            end = line.find("-->")
            if end < 0:
                masked_lines.append(" " * len(line))
                continue
            masked_lines.append(" " * (end + 3) + line[end + 3 :])
            comment_open = False
            continue
        if _is_indented_code(line):
            masked_lines.append(line)
            continue
        fence = _fence_marker(line)
        if fence is not None:
            masked_lines.append(line)
            continue
        match = HTML_COMMENT_START.match(line)
        if match is None:
            masked_lines.append(line)
            continue
        start = line.find("<!--")
        end = line.find("-->", start + 4)
        if end < 0:
            masked_lines.append(line[:start] + " " * (len(line) - start))
            comment_open = True
            continue
        masked_lines.append(
            line[:start] + " " * (end + 3 - start) + line[end + 3 :]
        )
    return "\n".join(masked_lines)


def _parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    direct = False
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
            if _is_fence_close(line, fence):
                fence = None
            continue
        fence = _fence_marker(line)
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
            continue
        match = ATX_HEADING.match(line)
        if match:
            level = len(match.group(1))
            if level <= 2:
                current = None
                direct = False
            if level == 2:
                current = {
                    "title": _heading_title(match.group(2) or ""),
                    "lines": [],
                    "direct_lines": [],
                }
                sections.append(current)
                direct = True
            elif level >= 3:
                direct = False
            continue
        if current is not None:
            current["lines"].append(line)
            if direct:
                current["direct_lines"].append(line)
    return sections


def _parse_subsections(text: str) -> list[Subsection]:
    subsections: list[Subsection] = []
    parent: str | None = None
    current: Subsection | None = None
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
            if _is_fence_close(line, fence):
                fence = None
            continue
        fence = _fence_marker(line)
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
            continue
        match = ATX_HEADING.match(line)
        if match:
            level = len(match.group(1))
            title = _heading_title(match.group(2) or "")
            if level <= 2:
                parent = title if level == 2 else None
                current = None
            elif level == 3:
                current = None
                if parent is not None:
                    current = {"parent": parent, "title": title, "lines": []}
                    subsections.append(current)
            continue
        if current is not None:
            current["lines"].append(line)
    return subsections


def _outside_fences(text: str) -> list[str]:
    lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        if fence is not None:
            if _is_fence_close(line, fence):
                fence = None
            continue
        fence = _fence_marker(line)
        if fence is None:
            lines.append(line)
    return lines


def _has_raw_html(text: str) -> bool:
    for line in _outside_fences(text):
        if _is_indented_code(line):
            continue
        if (
            RAW_HTML_TAG_START.match(line)
            or RAW_HTML_DECLARATION.match(line)
            or INDENTED_HTML_COMMENT.match(line)
            or CONTAINER_HTML_COMMENT.match(line)
            or CONTAINER_RAW_HTML.match(line)
        ):
            return True
    return _has_inline_html_comment(text)


def _has_inline_html_comment(text: str) -> bool:
    lines = text.splitlines()
    close_line = -1
    close_end = 0
    fence: tuple[str, int] | None = None
    paragraph_open = False
    for line_index, line in enumerate(lines):
        if fence is not None:
            if _is_fence_close(line, fence):
                fence = None
            paragraph_open = False
            continue
        if line_index < close_line:
            paragraph_open = True
            continue
        cursor = close_end if line_index == close_line else 0
        if line_index == close_line:
            close_line = -1
            close_end = 0
        if not line.strip():
            paragraph_open = False
            continue
        fence = _fence_marker(line)
        if fence is not None:
            paragraph_open = False
            continue
        if _is_indented_code(line) and not paragraph_open:
            continue
        while cursor < len(line):
            comment = line.find("<!--", cursor)
            tick_run = _backtick_run(line, cursor)
            if comment >= 0 and (tick_run is None or comment < tick_run[0]):
                close = _find_html_comment_close(
                    lines, line_index, comment + 4
                )
                if not _is_escaped(line, comment) and close is not None:
                    return True
                cursor = comment + 4
                continue
            if tick_run is None:
                break
            tick_start, tick_end = tick_run
            if _is_escaped(line, tick_start):
                cursor = tick_start + 1
                continue
            close = _find_backtick_close(
                lines, line_index, tick_end, tick_end - tick_start
            )
            if close is None:
                cursor = tick_end
                continue
            if close[0] > line_index:
                close_line, close_end = close
                break
            cursor = close[1]
        if (
            COMMONMARK_ATX_START.match(line)
            or COMMONMARK_FENCE_START.match(line)
            or COMMONMARK_BLOCK_RULE.match(line)
            or RAW_HTML_TAG_START.match(line)
            or RAW_HTML_DECLARATION.match(line)
            or re.match(r"^ {0,3}<!--", line)
        ):
            paragraph_open = False
        elif COMMONMARK_CONTAINER_WITH_CONTENT.match(line):
            paragraph_open = True
        elif COMMONMARK_CONTAINER_START.match(line):
            paragraph_open = False
        else:
            paragraph_open = True
    return False


def _has_noncanonical_fence(text: str) -> bool:
    for line in _outside_fences(text):
        if not _is_indented_code(line) and (
            INDENTED_FENCE_OPEN.match(line) or CONTAINER_FENCE_OPEN.match(line)
        ):
            return True
    return False


def _has_material_content(lines: list[str]) -> bool:
    fence: tuple[str, int] | None = None
    for line in lines:
        if fence is not None:
            if _is_fence_close(line, fence):
                fence = None
            elif line.strip():
                return True
            continue
        fence = _fence_marker(line)
        if fence is None and line.strip():
            return True
    return False


def _section_body(section: Section) -> str:
    return "\n".join(section["lines"])


def _has_content(section: Section) -> bool:
    return bool(_section_body(section).strip())


def _parse_fields(
    section: Section, *, canonical: bool = False
) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    pattern = ISSUE_FIELD_LINE if canonical else FIELD_LINE
    source_lines = section["direct_lines"] if canonical else section["lines"]
    lines = _outside_fences("\n".join(source_lines))
    if not canonical:
        lines = _outside_multiline_code_spans(lines)
    for line in lines:
        match = pattern.fullmatch(line)
        if match:
            fields.setdefault(match.group(1).strip(), []).append(match.group(2).strip())
    return fields


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


def _validate_issue_screening(
    unique: dict[str, Section], subsections: list[Subsection]
) -> list[dict[str, str]]:
    section = unique.get("Dependencies and ownership")
    if section is None:
        return []
    fields = _parse_fields(section, canonical=True)
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
        if any(not _has_material_content(match["lines"]) for match in matches):
            findings.append(_finding("empty-risk-material", identity))
    return findings


def _finding(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def _validate_structure(kind: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    masked = _mask_html_comments(text)
    if _has_raw_html(masked):
        findings.append(
            _finding(
                "raw-html",
                "line-start raw HTML is not allowed; use Markdown or a code block",
            )
        )
    if _has_noncanonical_fence(masked):
        findings.append(
            _finding(
                "noncanonical-fence",
                "fenced code openers must start at column zero",
            )
        )
    parsed = _parse_sections(masked)
    by_title: dict[str, list[Section]] = {}
    for section in parsed:
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
        if any(not _has_content(section) for section in matches):
            findings.append(_finding("empty-section", title))

    for section_title, required_fields in FIELDS.get(kind, {}).items():
        section = unique.get(section_title)
        if section is None:
            continue
        parsed_fields = _parse_fields(section, canonical=kind == "issue")
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
                findings.append(_finding("invalid-value", f"{section_title}: {field} {error}"))
                if kind == "checkpoint" and field == "Full remote SHA":
                    findings.append(
                        _finding(
                            "full-sha",
                            "Full remote SHA must contain exactly one 40-character SHA",
                        )
                    )
    if kind == "issue":
        findings.extend(_validate_issue_screening(unique, _parse_subsections(masked)))
    return findings


def validate(kind: str, text: str) -> list[dict[str, str]]:
    findings = _validate_structure(kind, text)
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            findings.append(_finding("secret", name))
    if LOCAL_PATH.search(text):
        findings.append(_finding("local-path", "machine-local path"))
    if kind == "pr" and AUTO_CLOSE.search(text):
        findings.append(
            _finding(
                "auto-close",
                "use Refs unless repository policy requires auto-close",
            )
        )
    if "{{" in text or "}}" in text:
        findings.append(_finding("placeholder", "unresolved template placeholder"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(REQUIRED), required=True)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    findings = validate(args.kind, args.path.read_text(encoding="utf-8"))
    result = {"valid": not findings, "findings": findings}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
