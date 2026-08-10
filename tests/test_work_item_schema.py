from __future__ import annotations

import importlib
import inspect
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = str(ROOT / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

work_item_markdown = importlib.import_module("work_item_markdown")
work_item_schema = importlib.import_module("work_item_schema")
validate_work_item = importlib.import_module("validate_work_item")


FULL_SHA = "0123456789abcdef0123456789abcdef01234567"
VALID_CHECKPOINT = "\n".join(
    (
        "## Checkpoint",
        "",
        "- Stage: ready",
        "- Branch: agent/issue-14-validator-layers",
        f"- Full remote SHA: {FULL_SHA}",
        "- Completed: documented",
        "- Remaining: documented",
        "- Validation: passed",
        "- Blocker: none",
        "- Next action: review",
    )
)


class WorkItemSchemaTests(unittest.TestCase):
    def test_schema_validates_a_preparsed_document(self):
        document = work_item_markdown.parse_document(VALID_CHECKPOINT)
        self.assertEqual(
            work_item_schema.validate_structure("checkpoint", document), []
        )
        missing = deepcopy(document)
        missing["sections"][0]["fields"].pop("Stage")
        self.assertEqual(
            work_item_schema.validate_structure("checkpoint", missing),
            [
                {
                    "severity": "error",
                    "code": "missing-field",
                    "message": "Checkpoint: Stage",
                }
            ],
        )

    def test_structural_flags_preserve_finding_order_without_source_text(self):
        document = work_item_markdown.parse_document(VALID_CHECKPOINT)
        document["has_raw_html"] = True
        document["has_noncanonical_fence"] = True
        findings = work_item_schema.validate_structure("checkpoint", document)
        self.assertEqual(
            [finding["code"] for finding in findings[:2]],
            ["raw-html", "noncanonical-fence"],
        )

    def test_value_policy_is_independently_testable(self):
        estimate, error = work_item_schema._parse_complexity(
            "production files=4; net production lines=180; new primitives=none"
        )
        self.assertIsNone(error)
        self.assertEqual(estimate["production_file_budget"], 10)
        self.assertEqual(estimate["net_production_line_budget"], 500)
        self.assertIn(
            "must be one of",
            work_item_schema._invalid_value("Stage", "coding"),
        )

    def test_dependencies_are_one_way_and_schema_does_not_rescan_markdown(self):
        markdown_source = inspect.getsource(work_item_markdown)
        schema_source = inspect.getsource(work_item_schema)
        orchestrator_source = inspect.getsource(validate_work_item)
        validate_source = inspect.getsource(validate_work_item.validate)
        self.assertNotIn("work_item_schema", markdown_source)
        self.assertNotIn("validate_work_item", markdown_source)
        self.assertIn("from work_item_markdown import", schema_source)
        self.assertNotIn("validate_work_item", schema_source)
        self.assertNotIn("splitlines(", schema_source)
        for parser_symbol in ("ATX_HEADING", "FENCE_OPEN", "HTML_COMMENT_START"):
            self.assertNotIn(parser_symbol, schema_source)
            self.assertNotIn(parser_symbol, validate_source)
        self.assertIn("validate_structure(kind, parse_document(text))", orchestrator_source)

    def test_legacy_public_constants_are_reexported(self):
        self.assertIs(validate_work_item.SECTIONS, work_item_schema.SECTIONS)
        self.assertIs(validate_work_item.STAGES, work_item_schema.STAGES)
        self.assertIs(validate_work_item.RISK_MATERIALS, work_item_schema.RISK_MATERIALS)
        package_schema = importlib.import_module("scripts.work_item_schema")
        package_validator = importlib.import_module("scripts.validate_work_item")
        self.assertIs(package_validator.SECTIONS, package_schema.SECTIONS)


if __name__ == "__main__":
    unittest.main()
