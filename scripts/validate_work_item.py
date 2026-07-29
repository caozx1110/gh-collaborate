#!/usr/bin/env python3
"""Validate generated Epic, Issue, checkpoint, and PR Markdown before posting."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = {
    "epic": ["Final goal", "Success criteria", "Scope", "Non-goals", "Waves", "rollback", "definition of done"],
    "issue": ["Problem", "Outcome", "Scope", "Non-goals", "approach", "Dependencies", "rollback", "Acceptance", "Test plan", "State"],
    "checkpoint": ["Checkpoint", "Stage:", "Branch:", "Full remote SHA:", "Validation:", "Next action:"],
    "pr": ["Outcome", "references", "Scope", "Implementation", "Candidate", "validation", "Risks", "rollback", "Known limits"],
}
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic secret assignment": re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s]{8,}"),
}
LOCAL_PATH = re.compile(r"(?:^|[\s(`])(?:~/(?:\.[\w.-]+/)?|/(?:Users|home|private|tmp|var/folders)/)", re.MULTILINE)
AUTO_CLOSE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#\d+")
FULL_SHA = re.compile(r"\b[0-9a-fA-F]{40}\b")


def validate(kind: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    lowered = text.lower()
    for required in REQUIRED[kind]:
        if required.lower() not in lowered:
            findings.append({"severity": "error", "code": "missing-section", "message": required})
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            findings.append({"severity": "error", "code": "secret", "message": name})
    if LOCAL_PATH.search(text):
        findings.append({"severity": "error", "code": "local-path", "message": "machine-local path"})
    if kind == "pr" and AUTO_CLOSE.search(text):
        findings.append({"severity": "error", "code": "auto-close", "message": "use Refs unless repository policy requires auto-close"})
    if kind == "checkpoint" and "none" not in lowered and not FULL_SHA.search(text):
        findings.append({"severity": "error", "code": "full-sha", "message": "checkpoint requires a 40-character SHA"})
    if "{{" in text or "}}" in text:
        findings.append({"severity": "error", "code": "placeholder", "message": "unresolved template placeholder"})
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
