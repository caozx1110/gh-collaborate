from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = "0123456789abcdef0123456789abcdef01234567"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


render_work_item = load_script("render_work_item")
validate_work_item = load_script("validate_work_item")


def rendered(kind: str) -> str:
    filename = render_work_item.TEMPLATES[kind]
    template = (ROOT / "assets" / "templates" / filename).read_text(encoding="utf-8")
    values = {token: "documented" for token in render_work_item.TOKEN.findall(template)}
    values.update(
        {
            "BASELINE": FULL_SHA,
            "LAST_REMOTE_SHA": "none",
            "FULL_REMOTE_SHA": FULL_SHA,
            "CANDIDATE_FULL_SHA": FULL_SHA,
            "STAGE": "ready",
            "BRANCH": "agent/issue-14-validator-layers",
            "BLOCKER": "none",
            "NEXT_ACTION": "open the pull request",
            "VALIDATION": "unit tests passed",
            "BASE_EVIDENCE": f"main at {FULL_SHA}",
            "TESTS_AND_ACTIONS": "unit tests passed; Actions pending",
            "EVIDENCE_IDENTITY": "head, base, commands, environment, dependencies, workflow, and rules recorded",
            "INVALIDATED_EVIDENCE": "none",
            "COMPLEXITY_RECONCILIATION": "declared and actual counts match",
            "RISK_CLASS": "ordinary",
            "RISK_TRIGGERS": "none",
            "COMPLEXITY_ESTIMATE": (
                "production files=2; net production lines=80; new primitives=none"
            ),
        }
    )
    return render_work_item.render(template, values)


def apply_operations(text: str, operations: list[dict[str, str]]) -> str:
    for operation in operations:
        if operation["op"] == "replace":
            if text.count(operation["old"]) != 1:
                raise AssertionError(f"replacement is not unique: {operation['old']!r}")
            text = text.replace(operation["old"], operation["new"], 1)
        elif operation["op"] == "append":
            text += operation["text"]
        else:
            raise AssertionError(f"unsupported operation: {operation['op']}")
    return text


class WorkItemCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(
            (ROOT / "tests" / "work_item_compatibility.json").read_text(
                encoding="utf-8"
            )
        )

    def test_frozen_library_results_match_exactly(self):
        self.assertEqual(self.corpus["schema_version"], 1)
        for case in self.corpus["cases"]:
            with self.subTest(case=case["id"]):
                text = apply_operations(rendered(case["kind"]), case["operations"])
                self.assertEqual(
                    validate_work_item.validate(case["kind"], text),
                    case["expected_findings"],
                )

    def test_frozen_cli_json_shape_and_exit_codes_match_exactly(self):
        command = [
            sys.executable,
            str(ROOT / "scripts" / "validate_work_item.py"),
        ]
        for case in self.corpus["cases"]:
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as directory:
                text = apply_operations(rendered(case["kind"]), case["operations"])
                path = Path(directory) / "work-item.md"
                path.write_text(text, encoding="utf-8")
                result = subprocess.run(
                    command + ["--kind", case["kind"], str(path)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                expected = {
                    "valid": not case["expected_findings"],
                    "findings": case["expected_findings"],
                }
                self.assertEqual(json.loads(result.stdout), expected)
                self.assertEqual(result.returncode, 0 if expected["valid"] else 1)


if __name__ == "__main__":
    unittest.main()
