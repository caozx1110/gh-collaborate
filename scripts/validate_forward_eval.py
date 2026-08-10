#!/usr/bin/env python3
"""Validate a deterministic forward-eval case and structured Agent result."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


CASE_FIELDS = {
    "id", "prompt", "fixture", "allowed_resources", "forbidden_resources",
    "allowed_mutations", "expected",
}
EXPECTED_FIELDS = {
    "intent", "risk_route", "risk_triggers", "decision", "blocker",
    "required_resources", "required_output_invariants",
}
RESULT_FIELDS = {
    "schema_version", "case_id", "loaded_skill_resources", "attempted_mutations",
    "intent", "risk_route", "risk_triggers", "decision", "blocker",
    "next_action", "artifact",
}
CONTRACT_FIELDS = {"schema_version", "result_template", "reporting_rules", "vocabulary"}
REPORTING_RULE_FIELDS = {"loaded_skill_resources", "attempted_mutations", "blocker"}
VOCABULARY_FIELDS = {"intent", "risk_route", "risk_trigger", "decision", "invariant"}
RESULT_TEMPLATE = {
    "schema_version": 1,
    "case_id": "",
    "loaded_skill_resources": [],
    "attempted_mutations": [],
    "intent": "",
    "risk_route": "",
    "risk_triggers": [],
    "decision": "",
    "blocker": False,
    "next_action": "",
    "artifact": {"summary": "", "invariants": []},
}
ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
LOCAL_PATH = re.compile(r"(?:^|[\s(`])(?:~/|/(?:Users|home|private|tmp|var/folders)/)")
SECRET = re.compile(
    r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_.-]{20,}\b|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?i:\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s]{8,})"
)
TRANSCRIPT_KEYS = {"chat_log", "chat_transcript", "messages", "model_transcript"}


def _finding(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _fields(value: Any, required: set[str], label: str, findings: list[dict[str, str]]) -> bool:
    if not isinstance(value, dict):
        findings.append(_finding("invalid-field", f"{label} must be an object"))
        return False
    for name in sorted(required - set(value)):
        findings.append(_finding("missing-field", f"{label}.{name}"))
    for name in sorted(set(value) - required):
        findings.append(_finding("unknown-field", f"{label}.{name}"))
    return required.issubset(value)


def _text(value: Any, label: str, findings: list[dict[str, str]]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        findings.append(_finding("invalid-field", f"{label} must be non-empty text"))
        return None
    return value


def _strings(value: Any, label: str, findings: list[dict[str, str]]) -> list[str] | None:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        findings.append(_finding("invalid-field", f"{label} must be a unique string array"))
        return None
    return value


def _vocabulary(value: Any, label: str, findings: list[dict[str, str]]) -> set[str] | None:
    if not isinstance(value, dict) or not value:
        findings.append(_finding("invalid-field", f"{label} must be a non-empty object"))
        return None
    invalid = [
        token for token, description in value.items()
        if not isinstance(token, str) or not ID.fullmatch(token)
        or not isinstance(description, str) or not description.strip()
    ]
    if invalid:
        findings.append(_finding("invalid-field", f"{label} has invalid tokens or descriptions"))
        return None
    return set(value)


def _unsafe(value: Any, label: str, findings: list[dict[str, str]]) -> None:
    stack = [value]
    unsafe = False
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if TRANSCRIPT_KEYS.intersection(current):
                findings.append(_finding("unsafe-content", f"{label} contains transcript fields"))
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str) and (LOCAL_PATH.search(current) or SECRET.search(current)):
            unsafe = True
    if unsafe:
        findings.append(_finding("unsafe-content", f"{label} contains local or secret material"))


def _file(root: Path, value: Any, label: str, findings: list[dict[str, str]]) -> Path | None:
    text = _text(value, label, findings)
    if text is None:
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        findings.append(_finding("invalid-path", f"{label} must be a safe relative path"))
        return None
    candidate = (root / Path(*path.parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        findings.append(_finding("invalid-path", f"{label} escapes the repository"))
        return None
    if not candidate.is_file():
        findings.append(_finding("missing-file", f"{label} does not exist"))
        return None
    return candidate


def validate_result_contract(document: Any) -> tuple[dict[str, set[str]], list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if not _fields(document, CONTRACT_FIELDS, "contract", findings):
        return {}, findings
    if type(document.get("schema_version")) is not int or document.get("schema_version") != 1:
        findings.append(_finding("invalid-field", "contract.schema_version must be 1"))
    template = document.get("result_template")
    if template != RESULT_TEMPLATE:
        findings.append(_finding("invalid-field", "contract.result_template is not canonical"))
    rules = document.get("reporting_rules")
    if _fields(rules, REPORTING_RULE_FIELDS, "contract.reporting_rules", findings):
        for name in REPORTING_RULE_FIELDS:
            _text(rules.get(name), f"contract.reporting_rules.{name}", findings)
    vocabularies: dict[str, set[str]] = {}
    vocabulary = document.get("vocabulary")
    if _fields(vocabulary, VOCABULARY_FIELDS, "contract.vocabulary", findings):
        for name in VOCABULARY_FIELDS:
            values = _vocabulary(vocabulary.get(name), f"contract.vocabulary.{name}", findings)
            if values is not None:
                vocabularies[name] = values
    _unsafe(document, "contract", findings)
    return vocabularies, findings


def validate_manifest(
    document: Any, root: Path, vocabularies: dict[str, set[str]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if not _fields(document, {"schema_version", "cases"}, "manifest", findings):
        return {}, findings
    if type(document.get("schema_version")) is not int or document.get("schema_version") != 1:
        findings.append(_finding("invalid-field", "manifest.schema_version must be 1"))
    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        findings.append(_finding("invalid-field", "manifest.cases must be a non-empty array"))
        return {}, findings
    cases: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(raw_cases):
        label = f"cases[{index}]"
        if not _fields(case, CASE_FIELDS, label, findings):
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not ID.fullmatch(case_id):
            findings.append(_finding("invalid-field", f"{label}.id is invalid"))
            continue
        if case_id in cases:
            findings.append(_finding("duplicate-case", case_id))
        cases[case_id] = case
        _text(case.get("prompt"), f"{label}.prompt", findings)
        allowed = _strings(case.get("allowed_resources"), f"{label}.allowed_resources", findings)
        forbidden = _strings(case.get("forbidden_resources"), f"{label}.forbidden_resources", findings)
        mutations = _strings(case.get("allowed_mutations"), f"{label}.allowed_mutations", findings)
        if mutations != []:
            findings.append(_finding("forbidden-mutation", f"{label} must allow no mutations"))
        for name, resources in (("allowed_resources", allowed), ("forbidden_resources", forbidden)):
            for resource in resources or []:
                _file(root, resource, f"{label}.{name}", findings)
                path = PurePosixPath(resource)
                if resource != "SKILL.md" and path.parts[0] not in {"references", "scripts"}:
                    findings.append(_finding("invalid-field", f"{label}.{name} is not a skill resource"))
        if allowed is not None and forbidden is not None and set(allowed).intersection(forbidden):
            findings.append(_finding("invalid-field", f"{label} resource lists overlap"))

        fixture = case.get("fixture")
        if _fields(fixture, {"path", "sha256"}, f"{label}.fixture", findings):
            fixture_path = _file(root, fixture.get("path"), f"{label}.fixture.path", findings)
            digest = fixture.get("sha256")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                findings.append(_finding("invalid-field", f"{label}.fixture.sha256 is invalid"))
            elif fixture_path and hashlib.sha256(fixture_path.read_bytes()).hexdigest() != digest:
                findings.append(_finding("fixture-digest", case_id))
            if fixture_path:
                try:
                    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    findings.append(_finding("invalid-fixture", case_id))
                else:
                    _unsafe(fixture_data, f"fixture {case_id}", findings)
                    if not isinstance(fixture_data, dict) or fixture_data.get("fixture_id") != case_id:
                        findings.append(_finding("invalid-fixture", f"{case_id} identity mismatch"))
                    if not isinstance(fixture_data, dict) or fixture_data.get("allowed_mutations") != []:
                        findings.append(_finding("forbidden-mutation", f"fixture {case_id}"))

        expected = case.get("expected")
        if _fields(expected, EXPECTED_FIELDS, f"{label}.expected", findings):
            for name in ("intent", "risk_route", "decision"):
                value = _text(expected.get(name), f"{label}.expected.{name}", findings)
                if value is not None and value not in vocabularies.get(name, set()):
                    findings.append(_finding("invalid-field", f"{label}.expected.{name} is unknown"))
            triggers = _strings(expected.get("risk_triggers"), f"{label}.expected.risk_triggers", findings)
            if triggers is not None and set(triggers) - vocabularies.get("risk_trigger", set()):
                findings.append(_finding("invalid-field", f"{label}.expected.risk_triggers is unknown"))
            if not isinstance(expected.get("blocker"), bool):
                findings.append(_finding("invalid-field", f"{label}.expected.blocker"))
            required = _strings(expected.get("required_resources"), f"{label}.expected.required_resources", findings)
            invariants = _strings(
                expected.get("required_output_invariants"),
                f"{label}.expected.required_output_invariants",
                findings,
            )
            if invariants is not None and set(invariants) - vocabularies.get("invariant", set()):
                findings.append(_finding("invalid-field", f"{label}.expected.required_output_invariants is unknown"))
            if required is not None and allowed is not None and not set(required).issubset(allowed):
                findings.append(_finding("invalid-field", f"{label} requires a disallowed resource"))
        _unsafe(case, f"case {case_id}", findings)
    return cases, findings


def validate_result(
    result: Any, case: dict[str, Any], vocabularies: dict[str, set[str]]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not _fields(result, RESULT_FIELDS, "result", findings):
        return findings
    if type(result.get("schema_version")) is not int or result.get("schema_version") != 1:
        findings.append(_finding("invalid-field", "result.schema_version must be 1"))
    if result.get("case_id") != case["id"]:
        findings.append(_finding("incorrect-decision", "result identity does not match the case"))
    loaded = _strings(
        result.get("loaded_skill_resources"), "result.loaded_skill_resources", findings
    )
    mutations = _strings(result.get("attempted_mutations"), "result.attempted_mutations", findings)
    allowed = set(case["allowed_resources"])
    forbidden = set(case["forbidden_resources"])
    required = set(case["expected"]["required_resources"])
    if loaded is not None:
        if set(loaded) - allowed or set(loaded).intersection(forbidden):
            findings.append(_finding("forbidden-resource", "result loaded a disallowed resource"))
        if required - set(loaded):
            findings.append(_finding("missing-resource", "result omitted a required resource"))
    if mutations is not None and set(mutations) - set(case["allowed_mutations"]):
        findings.append(_finding("forbidden-mutation", "result attempted a disallowed mutation"))
    expected = case["expected"]
    for name in ("intent", "risk_route", "decision"):
        value = _text(result.get(name), f"result.{name}", findings)
        if value is not None and value not in vocabularies.get(name, set()):
            findings.append(_finding("invalid-field", f"result.{name} is unknown"))
        if result.get(name) != expected[name]:
            findings.append(_finding("incorrect-decision", f"result.{name}"))
    triggers = _strings(result.get("risk_triggers"), "result.risk_triggers", findings)
    if triggers is not None:
        if set(triggers) - vocabularies.get("risk_trigger", set()):
            findings.append(_finding("invalid-field", "result.risk_triggers is unknown"))
        if set(triggers) != set(expected["risk_triggers"]):
            findings.append(_finding("incorrect-decision", "result.risk_triggers"))
    if not isinstance(result.get("blocker"), bool):
        findings.append(_finding("invalid-field", "result.blocker must be boolean"))
    if result.get("blocker") != expected["blocker"]:
        findings.append(_finding("incorrect-decision", "result.blocker"))
    _text(result.get("next_action"), "result.next_action", findings)
    artifact = result.get("artifact")
    if _fields(artifact, {"summary", "invariants"}, "result.artifact", findings):
        _text(artifact.get("summary"), "result.artifact.summary", findings)
        invariants = _strings(artifact.get("invariants"), "result.artifact.invariants", findings)
        if invariants is not None:
            if set(invariants) - vocabularies.get("invariant", set()):
                findings.append(_finding("invalid-field", "result.artifact.invariants is unknown"))
            if set(expected["required_output_invariants"]) - set(invariants):
                findings.append(_finding("missing-invariant", "result omitted a required invariant"))
    _unsafe(result, "result", findings)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("tests/forward_eval_cases.json"))
    parser.add_argument("--contract", type=Path, default=Path("tests/forward_eval_result_contract.json"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[dict[str, str]] = []
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = json.loads(args.result.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        cases = {}
        findings.append(_finding("invalid-json", str(error)))
    else:
        vocabularies, findings = validate_result_contract(contract)
        cases: dict[str, dict[str, Any]] = {}
        if not findings:
            cases, manifest_findings = validate_manifest(manifest, root, vocabularies)
            findings.extend(manifest_findings)
        if not findings:
            if args.case not in cases:
                findings.append(_finding("unknown-case", args.case))
            else:
                findings.extend(validate_result(result, cases[args.case], vocabularies))
    print(json.dumps({"valid": not findings, "case_id": args.case, "findings": findings}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
