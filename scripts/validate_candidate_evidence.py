#!/usr/bin/env python3
"""Validate exact-SHA candidate and complexity evidence against repository state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")
POLICY_CAPS = re.compile(
    r"production file budget\s*=\s*(\d+)\s*;\s*"
    r"net production line budget\s*=\s*(\d+)",
    re.IGNORECASE,
)
DEFAULT_FILE_BUDGET = 10
DEFAULT_LINE_BUDGET = 500
PRIMITIVES = frozenset({"storage", "transaction", "migration", "concurrency"})
DECISIONS = frozenset({"continue", "reduce", "split", "replace"})
CLAIM_INPUTS = {
    "stable-full-suite": {"head_sha", "dependencies", "environment"},
    "complexity-reconciliation": {
        "head_sha",
        "dependencies",
        "scope",
        "counting_method",
        "budget_policy",
    },
    "implementation-review": {"head_sha"},
    "branch-ci": {"head_sha", "dependencies", "workflow", "rules"},
    "tested-merge-ci": {
        "head_sha",
        "base_sha",
        "dependencies",
        "workflow",
        "rules",
    },
}


def _finding(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )


def _mapping(value: Any, name: str, findings: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        findings.append(_finding("invalid-evidence", f"{name} must be an object"))
        return {}
    return value


def _text(value: Any, name: str, findings: list[dict[str, str]]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        findings.append(_finding("invalid-evidence", f"{name} must be non-empty text"))
        return None
    return value.strip()


def _count(value: Any, name: str, findings: list[dict[str, str]]) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        findings.append(_finding("invalid-evidence", f"{name} must be a non-negative integer"))
        return None
    return value


def _boolean(value: Any, name: str, findings: list[dict[str, str]]) -> bool | None:
    if not isinstance(value, bool):
        findings.append(_finding("invalid-evidence", f"{name} must be a boolean"))
        return None
    return value


def _primitive_set(
    value: Any, name: str, findings: list[dict[str, str]]
) -> set[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        findings.append(_finding("invalid-evidence", f"{name} must be a string array"))
        return None
    items = set(value)
    if len(items) != len(value) or items - PRIMITIVES:
        findings.append(
            _finding(
                "invalid-evidence",
                f"{name} must contain unique supported primitives",
            )
        )
        return None
    return items


def _policy_section(text: str, fragment: str) -> str | None:
    wanted = fragment.lower().strip()
    lines = text.splitlines()
    start = None
    level = None
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        slug = re.sub(r"[^a-z0-9 -]", "", match.group(2).lower())
        slug = re.sub(r"[ -]+", "-", slug).strip("-")
        if start is None and slug == wanted:
            start, level = index + 1, len(match.group(1))
            continue
        if start is not None and len(match.group(1)) <= int(level):
            return "\n".join(lines[start:index])
    return "\n".join(lines[start:]) if start is not None else None


def _policy_caps(root: Path, reference: str) -> tuple[int, int] | None:
    path_text, separator, fragment = reference.partition("#")
    path = Path(path_text)
    if (
        not separator
        or not fragment
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    tracked = _git(root, "ls-files", "--error-unmatch", "--", path.as_posix())
    if tracked.returncode != 0:
        return None
    policy = root / path
    if not policy.is_file():
        return None
    try:
        policy_text = policy.read_text(encoding="utf-8")
    except OSError:
        return None
    section = _policy_section(policy_text, fragment)
    match = POLICY_CAPS.search(section or "")
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _claim_inputs(document: dict[str, Any]) -> dict[str, Any]:
    identity = document.get("identity", {})
    complexity = document.get("complexity", {})
    if not isinstance(identity, dict):
        identity = {}
    if not isinstance(complexity, dict):
        complexity = {}
    return {
        "head_sha": identity.get("head_sha"),
        "base_sha": identity.get("base_sha"),
        "dependencies": identity.get("dependencies"),
        "environment": identity.get("environment"),
        "workflow": identity.get("workflow"),
        "rules": identity.get("rules"),
        "scope": identity.get("scope"),
        "counting_method": complexity.get("counting_method"),
        "budget_policy": (
            complexity.get("budget_override"),
            complexity.get("production_file_budget"),
            complexity.get("net_production_line_budget"),
        ),
    }


def invalidated_claims(recorded: dict[str, Any], current: dict[str, Any]) -> set[str]:
    """Return only evidence claims whose declared inputs changed."""
    recorded_inputs = _claim_inputs(recorded)
    current_inputs = _claim_inputs(current)
    changed = {
        key
        for key in {item for inputs in CLAIM_INPUTS.values() for item in inputs}
        if recorded_inputs.get(key) != current_inputs.get(key)
    }
    return {
        claim for claim, inputs in CLAIM_INPUTS.items() if changed.intersection(inputs)
    }


def validate(
    document: Any, root: Path, *, actual_head: str | None = None
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    data = _mapping(document, "document", findings)
    identity = _mapping(data.get("identity"), "identity", findings)
    complexity = _mapping(data.get("complexity"), "complexity", findings)
    declared = _mapping(complexity.get("declared"), "complexity.declared", findings)
    actual = _mapping(complexity.get("actual"), "complexity.actual", findings)

    head = _text(identity.get("head_sha"), "identity.head_sha", findings)
    base = _text(identity.get("base_sha"), "identity.base_sha", findings)
    review_head = _text(
        identity.get("review_head_sha"), "identity.review_head_sha", findings
    )
    for name in ("environment", "dependencies", "workflow", "rules", "scope"):
        _text(identity.get(name), f"identity.{name}", findings)
    commands = identity.get("commands")
    if (
        not isinstance(commands, list)
        or not commands
        or any(not isinstance(item, str) or not item.strip() for item in commands)
    ):
        findings.append(
            _finding("invalid-evidence", "identity.commands must be a non-empty string array")
        )
    for name, value in (("head_sha", head), ("base_sha", base), ("review_head_sha", review_head)):
        if value is not None and FULL_SHA.fullmatch(value) is None:
            findings.append(_finding("invalid-sha", f"identity.{name} must be a full SHA"))
    if head is not None and review_head is not None and head != review_head:
        findings.append(_finding("stale-review", "review evidence is bound to another head SHA"))
    repository_check = actual_head is None
    if repository_check:
        result = _git(root, "rev-parse", "HEAD")
        actual_head = result.stdout.strip() if result.returncode == 0 else None
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
        if status.returncode != 0 or status.stdout.strip():
            findings.append(
                _finding("dirty-worktree", "tracked candidate state does not equal HEAD")
            )
        base_is_sha = base is not None and FULL_SHA.fullmatch(base) is not None
        base_exists = bool(
            base_is_sha
            and _git(root, "cat-file", "-e", f"{base}^{{commit}}").returncode == 0
        )
        if base_is_sha and not base_exists:
            findings.append(
                _finding("missing-base", "recorded base SHA is not a local commit")
            )
        elif base_exists and (
            head is not None
            and FULL_SHA.fullmatch(head)
            and _git(root, "merge-base", "--is-ancestor", base, head).returncode
        ):
            findings.append(
                _finding("invalid-base", "recorded base is not an ancestor of candidate head")
            )
    if head is not None and actual_head != head:
        findings.append(_finding("stale-head", "candidate evidence is bound to another head SHA"))

    declared_files = _count(
        declared.get("production_files"), "complexity.declared.production_files", findings
    )
    declared_lines = _count(
        declared.get("net_production_lines"),
        "complexity.declared.net_production_lines",
        findings,
    )
    declared_primitives = _primitive_set(
        declared.get("new_primitives"), "complexity.declared.new_primitives", findings
    )
    actual_files = _count(
        actual.get("production_files"), "complexity.actual.production_files", findings
    )
    actual_lines = _count(
        actual.get("net_production_lines"),
        "complexity.actual.net_production_lines",
        findings,
    )
    actual_primitives = _primitive_set(
        actual.get("new_primitives"), "complexity.actual.new_primitives", findings
    )
    _text(complexity.get("counting_method"), "complexity.counting_method", findings)
    material_divergence = _boolean(
        complexity.get("material_divergence"),
        "complexity.material_divergence",
        findings,
    )
    exclusions = complexity.get("exclusions")
    if not isinstance(exclusions, list) or any(
        not isinstance(item, str) or not item.strip() for item in exclusions
    ):
        findings.append(
            _finding("invalid-evidence", "complexity.exclusions must be a string array")
        )

    file_budget = _count(
        complexity.get("production_file_budget"),
        "complexity.production_file_budget",
        findings,
    )
    line_budget = _count(
        complexity.get("net_production_line_budget"),
        "complexity.net_production_line_budget",
        findings,
    )
    override = complexity.get("budget_override")
    expected_caps = (DEFAULT_FILE_BUDGET, DEFAULT_LINE_BUDGET)
    if override is not None:
        policy_caps = _policy_caps(root, override) if isinstance(override, str) else None
        if policy_caps is None:
            findings.append(
                _finding("invalid-budget-policy", "budget override is missing, untracked, or unstructured")
            )
        else:
            expected_caps = policy_caps
    if file_budget is not None and line_budget is not None:
        if (file_budget, line_budget) != expected_caps:
            findings.append(
                _finding("budget-cap-mismatch", "recorded effective caps do not match repository policy")
            )

    values = (
        declared_files,
        declared_lines,
        declared_primitives,
        actual_files,
        actual_lines,
        actual_primitives,
        file_budget,
        line_budget,
        material_divergence,
    )
    if all(value is not None for value in values):
        drift = bool(
            actual_files > file_budget
            or actual_lines > line_budget
            or actual_primitives - declared_primitives
            or material_divergence
        )
        decision = complexity.get("decision")
        if drift and decision not in DECISIONS:
            findings.append(
                _finding("missing-drift-decision", "complexity drift requires a delivery decision")
            )
        if decision is not None and decision not in DECISIONS:
            findings.append(
                _finding("invalid-drift-decision", "decision must be continue, reduce, split, or replace")
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        findings = [_finding("invalid-evidence", str(error))]
    else:
        findings = validate(document, args.root.resolve())
    print(json.dumps({"valid": not findings, "findings": findings}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
