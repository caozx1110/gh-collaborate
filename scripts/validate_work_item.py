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
ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)[ \t]*|[ \t]*)$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FIELD_LINE = re.compile(
    r"^ {0,3}(?:[-*+][ \t]+)?([^:\n]+?):[ \t]*(.*?)[ \t]*$"
)
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")


class Section(TypedDict):
    title: str
    lines: list[str]


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


def _has_backtick_close(
    lines: list[str], line_index: int, start: int, tick_count: int
) -> bool:
    for index in range(line_index, len(lines)):
        if index != line_index and (
            not lines[index].strip()
            or ATX_HEADING.match(lines[index])
            or _fence_marker(lines[index]) is not None
            or re.match(r"^ {0,3}<!--", lines[index])
        ):
            return False
        cursor = start if index == line_index else 0
        while True:
            tick_run = _backtick_run(lines[index], cursor)
            if tick_run is None:
                break
            tick_start, tick_end = tick_run
            if tick_end - tick_start == tick_count:
                return True
            cursor = tick_end
    return False


def _mask_html_comments(text: str) -> str:
    lines = text.splitlines()
    masked_lines: list[str] = []
    comment_open = False
    code_span_ticks: int | None = None
    fence: tuple[str, int] | None = None
    for line_index, line in enumerate(lines):
        if fence is not None:
            masked_lines.append(line)
            if _is_fence_close(line, fence):
                fence = None
            continue
        if not comment_open and code_span_ticks is None and _is_indented_code(line):
            masked_lines.append(line)
            continue
        if not comment_open and code_span_ticks is None:
            fence = _fence_marker(line)
            if fence is not None:
                masked_lines.append(line)
                continue

        masked = list(line)
        cursor = 0
        while cursor < len(line):
            if comment_open:
                end = line.find("-->", cursor)
                if end < 0:
                    masked[cursor:] = " " * (len(line) - cursor)
                    break
                masked[cursor : end + 3] = " " * (end + 3 - cursor)
                cursor = end + 3
                comment_open = False
                continue

            if code_span_ticks is not None:
                tick_run = _backtick_run(line, cursor)
                if tick_run is None:
                    break
                tick_start, tick_end = tick_run
                if tick_end - tick_start == code_span_ticks:
                    code_span_ticks = None
                cursor = tick_end
                continue

            tick_run = _backtick_run(line, cursor)
            start = line.find("<!--", cursor)
            if tick_run is not None and (start < 0 or tick_run[0] < start):
                tick_start, tick_end = tick_run
                if _is_escaped(line, tick_start):
                    cursor = tick_start + 1
                    continue
                tick_count = tick_end - tick_start
                if _has_backtick_close(lines, line_index, tick_end, tick_count):
                    code_span_ticks = tick_count
                cursor = tick_end
                continue
            if start < 0:
                break
            if _is_escaped(line, start):
                cursor = start + 4
                continue
            masked[start : start + 4] = " " * 4
            cursor = start + 4
            comment_open = True
        masked_lines.append("".join(masked))
    return "\n".join(masked_lines)


def _parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
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
            if level == 2:
                current = {
                    "title": _heading_title(match.group(2) or ""),
                    "lines": [],
                }
                sections.append(current)
            continue
        if current is not None:
            current["lines"].append(line)
    return sections


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


def _section_body(section: Section) -> str:
    return "\n".join(section["lines"])


def _has_content(section: Section) -> bool:
    return bool(_section_body(section).strip())


def _parse_fields(section: Section) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in _outside_fences(_section_body(section)):
        match = FIELD_LINE.fullmatch(line)
        if match:
            fields.setdefault(match.group(1).strip(), []).append(match.group(2).strip())
    return fields


def _code_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1]
    return stripped


def _invalid_value(field: str, value: str) -> str | None:
    normalized = _code_value(value)
    if not normalized:
        return "must not be empty"
    if field == "Stage":
        if normalized not in STAGES:
            return "must be one of: " + ", ".join(sorted(STAGES))
        return None
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


def _validate_structure(kind: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    parsed = _parse_sections(_mask_html_comments(text))
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
        parsed_fields = _parse_fields(section)
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
