#!/usr/bin/env python3
"""Parse the validator's bounded Markdown subset into one structural representation.

This module owns every Markdown visibility state machine used by work-item
validation. Consumers must use :func:`parse_document` instead of rescanning raw
Markdown for headings, fields, comments, fences, code spans, or risk material.
"""

from __future__ import annotations

import re
from typing import TypedDict


ATX_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.*?)[ \t]*|[ \t]*)$")
FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")
INDENTED_FENCE_OPEN = re.compile(r"^ {1,3}(`{3,}|~{3,})(.*)$")
FIELD_LINE = re.compile(
    r"^ {0,3}(?:[-*+][ \t]+)?([^:\n]+?):[ \t]*(.*?)[ \t]*$"
)
ISSUE_FIELD_LINE = re.compile(r"^- ([^:\n]+?):[ \t]*(.*?)[ \t]*$")
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


class Section(TypedDict):
    title: str
    lines: list[str]
    direct_lines: list[str]
    start_line: int
    end_line: int
    fields: dict[str, list[str]]
    canonical_fields: dict[str, list[str]]
    has_content: bool


class Subsection(TypedDict):
    parent: str
    title: str
    lines: list[str]
    start_line: int
    end_line: int
    has_material_content: bool


class DocumentStructure(TypedDict):
    line_count: int
    sections: list[Section]
    subsections: list[Subsection]
    has_raw_html: bool
    has_noncanonical_fence: bool


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
    for line_number, line in enumerate(text.splitlines(), start=1):
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
                current["end_line"] = line_number
            if _is_fence_close(line, fence):
                fence = None
            continue
        fence = _fence_marker(line)
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
                current["end_line"] = line_number
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
                    "start_line": line_number,
                    "end_line": line_number,
                    "fields": {},
                    "canonical_fields": {},
                    "has_content": False,
                }
                sections.append(current)
                direct = True
            elif level >= 3:
                if current is not None:
                    current["end_line"] = line_number
                direct = False
            continue
        if current is not None:
            current["lines"].append(line)
            current["end_line"] = line_number
            if direct:
                current["direct_lines"].append(line)
    return sections


def _parse_subsections(text: str) -> list[Subsection]:
    subsections: list[Subsection] = []
    parent: str | None = None
    current: Subsection | None = None
    fence: tuple[str, int] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
                current["end_line"] = line_number
            if _is_fence_close(line, fence):
                fence = None
            continue
        fence = _fence_marker(line)
        if fence is not None:
            if current is not None:
                current["lines"].append(line)
                current["end_line"] = line_number
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
                    current = {
                        "parent": parent,
                        "title": title,
                        "lines": [],
                        "start_line": line_number,
                        "end_line": line_number,
                        "has_material_content": False,
                    }
                    subsections.append(current)
            elif current is not None:
                current["end_line"] = line_number
            continue
        if current is not None:
            current["lines"].append(line)
            current["end_line"] = line_number
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
                if not _is_escaped(line, comment):
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


def parse_document(text: str) -> DocumentStructure:
    """Return the authoritative visible structure for one untrusted document."""

    masked = _mask_html_comments(text)
    sections = _parse_sections(masked)
    for section in sections:
        section["fields"] = _parse_fields(section)
        section["canonical_fields"] = _parse_fields(section, canonical=True)
        section["has_content"] = bool("\n".join(section["lines"]).strip())
    subsections = _parse_subsections(masked)
    for subsection in subsections:
        subsection["has_material_content"] = _has_material_content(
            subsection["lines"]
        )
    return {
        "line_count": len(text.splitlines()),
        "sections": sections,
        "subsections": subsections,
        "has_raw_html": _has_raw_html(masked),
        "has_noncanonical_fence": _has_noncanonical_fence(masked),
    }
