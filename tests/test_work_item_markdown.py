from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "work_item_markdown_under_test", ROOT / "scripts" / "work_item_markdown.py"
)
work_item_markdown = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(work_item_markdown)


class WorkItemMarkdownTests(unittest.TestCase):
    def test_structure_records_visible_fields_material_and_source_spans(self):
        text = "\n".join(
            (
                "<!--",
                "## Hidden",
                "-->",
                "## State",
                "",
                "- Stage: ready",
                "### Detail",
                "",
                "- Stage: nested",
                "```markdown",
                "## Fenced",
                "- Stage: fenced",
                "```",
            )
        )
        document = work_item_markdown.parse_document(text)
        self.assertEqual(document["line_count"], 13)
        self.assertFalse(document["has_raw_html"])
        self.assertFalse(document["has_noncanonical_fence"])
        self.assertEqual([section["title"] for section in document["sections"]], ["State"])
        section = document["sections"][0]
        self.assertEqual((section["start_line"], section["end_line"]), (4, 13))
        self.assertEqual(section["canonical_fields"]["Stage"], ["ready"])
        self.assertEqual(section["fields"]["Stage"], ["ready", "nested"])
        self.assertTrue(section["has_content"])
        subsection = document["subsections"][0]
        self.assertEqual(
            (subsection["parent"], subsection["title"]), ("State", "Detail")
        )
        self.assertEqual((subsection["start_line"], subsection["end_line"]), (7, 13))
        self.assertTrue(subsection["has_material_content"])

    def test_comment_code_and_container_visibility_is_fail_closed(self):
        cases = (
            ("## Notes\n\nLiteral `<!--` opener", False, False),
            ("## Notes\n\nVisible <!-- hidden -->", True, False),
            ("## Notes\n\n- ```\n## Still visible", False, True),
            ("## Notes\n\n> <div>hidden", True, False),
        )
        for text, raw_html, noncanonical_fence in cases:
            with self.subTest(text=text):
                document = work_item_markdown.parse_document(text)
                self.assertEqual(document["has_raw_html"], raw_html)
                self.assertEqual(
                    document["has_noncanonical_fence"], noncanonical_fence
                )

    def test_fenced_material_requires_visible_content(self):
        empty = work_item_markdown.parse_document(
            "## Design\n\n### Model\n\n```text\n```"
        )
        nonempty = work_item_markdown.parse_document(
            "## Design\n\n### Model\n\n```text\nordered handoff\n```"
        )
        self.assertFalse(empty["subsections"][0]["has_material_content"])
        self.assertTrue(nonempty["subsections"][0]["has_material_content"])

    def test_parser_returns_structure_without_raw_document_copy(self):
        document = work_item_markdown.parse_document("## Outcome\n\nsecret-free text")
        self.assertEqual(
            set(document),
            {
                "line_count",
                "sections",
                "subsections",
                "has_raw_html",
                "has_noncanonical_fence",
            },
        )


if __name__ == "__main__":
    unittest.main()
