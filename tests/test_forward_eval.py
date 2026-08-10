from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_forward_eval", ROOT / "scripts" / "validate_forward_eval.py"
)
validate_forward_eval = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_forward_eval)


class ForwardEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "tests" / "forward_eval_result_contract.json").read_text(
                encoding="utf-8"
            )
        )
        cls.vocabularies, cls.contract_findings = (
            validate_forward_eval.validate_result_contract(cls.contract)
        )
        cls.manifest = json.loads(
            (ROOT / "tests" / "forward_eval_cases.json").read_text(encoding="utf-8")
        )
        cls.cases, cls.manifest_findings = validate_forward_eval.validate_manifest(
            cls.manifest, ROOT, cls.vocabularies
        )

    def test_manifest_fixtures_and_positive_results_are_valid(self):
        self.assertEqual(self.contract_findings, [])
        self.assertEqual(self.manifest_findings, [])
        self.assertEqual(
            set(self.cases),
            {
                "ordinary-read-only",
                "high-risk-migration-concurrency",
                "divergent-resume",
                "ambiguous-write",
            },
        )
        result_root = ROOT / "tests" / "forward_eval_results"
        for case_id, case in self.cases.items():
            with self.subTest(case_id=case_id):
                result = json.loads(
                    (result_root / f"{case_id}.valid.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    validate_forward_eval.validate_result(
                        result, case, self.vocabularies
                    ),
                    [],
                )

    def test_tracked_negative_results_fail_for_the_declared_reason(self):
        document = json.loads(
            (ROOT / "tests" / "forward_eval_invalid_results.json").read_text(
                encoding="utf-8"
            )
        )
        for example in document["examples"]:
            with self.subTest(example=example["id"]):
                codes = {
                    finding["code"]
                    for finding in validate_forward_eval.validate_result(
                        example["result"],
                        self.cases[example["case_id"]],
                        self.vocabularies,
                    )
                }
                self.assertIn(example["expected_code"], codes)

    def test_manifest_rejects_digest_drift_overlap_and_missing_fixture(self):
        cases = []
        wrong_digest = deepcopy(self.manifest)
        wrong_digest["cases"][0]["fixture"]["sha256"] = "0" * 64
        cases.append((wrong_digest, "fixture-digest"))
        overlap = deepcopy(self.manifest)
        overlap["cases"][0]["forbidden_resources"].append("SKILL.md")
        cases.append((overlap, "invalid-field"))
        missing = deepcopy(self.manifest)
        missing["cases"][0]["fixture"]["path"] = "tests/fixtures/forward_eval/missing.json"
        cases.append((missing, "missing-file"))
        for manifest, expected in cases:
            with self.subTest(expected=expected):
                _, findings = validate_forward_eval.validate_manifest(
                    manifest, ROOT, self.vocabularies
                )
                self.assertIn(expected, {finding["code"] for finding in findings})

    def test_result_rejects_machine_paths_and_transcript_fields(self):
        result = json.loads(
            (ROOT / "tests" / "forward_eval_results" / "ordinary-read-only.valid.json").read_text(
                encoding="utf-8"
            )
        )
        result["artifact"]["summary"] = "/" + "Users/example/private-output"
        result["artifact"]["chat_transcript"] = []
        codes = {
            finding["code"]
            for finding in validate_forward_eval.validate_result(
                result, self.cases["ordinary-read-only"], self.vocabularies
            )
        }
        self.assertTrue({"unknown-field", "unsafe-content"}.issubset(codes))

    def test_result_rejects_unknown_types_without_crashing(self):
        result = json.loads(
            (ROOT / "tests" / "forward_eval_results" / "ordinary-read-only.valid.json").read_text(
                encoding="utf-8"
            )
        )
        result["schema_version"] = True
        result["intent"] = []
        result["blocker"] = 0
        codes = {
            finding["code"]
            for finding in validate_forward_eval.validate_result(
                result, self.cases["ordinary-read-only"], self.vocabularies
            )
        }
        self.assertIn("invalid-field", codes)

    def test_cli_accepts_a_valid_result_and_rejects_unknown_case(self):
        result = ROOT / "tests" / "forward_eval_results" / "ordinary-read-only.valid.json"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "validate_forward_eval.py"),
            "--result",
            str(result),
            "--root",
            str(ROOT),
        ]
        valid = subprocess.run(
            command + ["--case", "ordinary-read-only"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(valid.returncode, 0)
        self.assertTrue(json.loads(valid.stdout)["valid"])
        invalid = subprocess.run(
            command + ["--case", "not-a-case"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(invalid.returncode, 1)
        self.assertIn(
            "unknown-case",
            {finding["code"] for finding in json.loads(invalid.stdout)["findings"]},
        )

    def test_result_contract_is_executable_and_does_not_reveal_case_expectations(self):
        self.assertEqual(self.contract_findings, [])
        self.assertEqual(
            set(self.contract["result_template"]),
            validate_forward_eval.RESULT_FIELDS,
        )
        serialized = json.dumps(self.contract, sort_keys=True)
        for case_id in self.cases:
            self.assertNotIn(case_id, serialized)
        self.assertNotIn("required_output_invariants", serialized)
        self.assertTrue(
            {"proceed", "request-design", "stop", "classify"}.issubset(
                self.vocabularies["decision"]
            )
        )

    def test_validator_and_corpus_have_no_live_execution_channel(self):
        source = (ROOT / "scripts" / "validate_forward_eval.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)
        for case in self.manifest["cases"]:
            self.assertEqual(case["allowed_mutations"], [])
        policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("tests/forward_eval_cases.json", policy)
        self.assertIn("tests/forward_eval_result_contract.json", policy)
        self.assertIn("expected invariants evaluator-side", policy)
        self.assertIn("Do not commit transcripts", policy)


if __name__ == "__main__":
    unittest.main()
