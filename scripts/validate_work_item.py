#!/usr/bin/env python3
"""Validate generated Epic, Issue, checkpoint, and PR Markdown before posting."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if __package__:
    from . import work_item_markdown as _markdown
    from . import work_item_schema as _schema
else:
    if SCRIPT_DIRECTORY not in sys.path:
        sys.path.insert(0, SCRIPT_DIRECTORY)
    import work_item_markdown as _markdown
    import work_item_schema as _schema


_MARKDOWN_EXPORTS = (
    "ATX_HEADING", "COMMONMARK_ATX_START", "COMMONMARK_BLOCK_RULE",
    "COMMONMARK_CONTAINER_START", "COMMONMARK_CONTAINER_WITH_CONTENT",
    "COMMONMARK_FENCE_START", "CONTAINER_FENCE_OPEN", "CONTAINER_HTML_COMMENT",
    "CONTAINER_PREFIX", "CONTAINER_RAW_HTML", "DocumentStructure", "FENCE_OPEN",
    "FIELD_LINE", "HTML_COMMENT_START", "INDENTED_FENCE_OPEN",
    "INDENTED_HTML_COMMENT", "ISSUE_FIELD_LINE", "RAW_HTML_DECLARATION",
    "RAW_HTML_TAG_START", "Section", "Subsection",
)
_SCHEMA_EXPORTS = (
    "DEFAULT_NET_LINE_BUDGET", "DEFAULT_PRODUCTION_FILE_BUDGET", "EMPTY_VALUE",
    "FIELDS", "FULL_SHA", "HIGH_RISK_AUDIT", "MAX_COUNT_DIGITS",
    "NEW_PRIMITIVES", "POLICY_REFERENCE", "PRIMITIVE_TRIGGERS", "REQUIRED",
    "RISK_CLASSES", "RISK_MATERIALS", "RISK_TRIGGERS", "SECTIONS", "STAGES",
    "ComplexityEstimate",
)
for _name in _MARKDOWN_EXPORTS:
    globals()[_name] = getattr(_markdown, _name)
for _name in _SCHEMA_EXPORTS:
    globals()[_name] = getattr(_schema, _name)
parse_document = _markdown.parse_document
validate_structure = _schema.validate_structure


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


def _finding(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def validate(kind: str, text: str) -> list[dict[str, str]]:
    """Validate one work item while preserving the legacy finding order.

    The parser owns all Markdown structure and visibility decisions. The scans
    below intentionally inspect the complete raw source: secrets and local paths
    remain unsafe inside comments or code, and auto-close syntax and unresolved
    placeholders are whole-document publication policies rather than Markdown
    structure.
    """

    findings = validate_structure(kind, parse_document(text))
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
