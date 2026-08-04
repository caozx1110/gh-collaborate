from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


render_work_item = load_script("render_work_item")
validate_work_item = load_script("validate_work_item")
inspect_repo = load_script("inspect_repo")
reconcile_state = load_script("reconcile_state")


FULL_SHA = "0123456789abcdef0123456789abcdef01234567"


def rendered_work_item(kind: str, **overrides: str) -> str:
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
            "BRANCH": "agent/issue-6-work-item-validator",
            "BLOCKER": "none",
            "NEXT_ACTION": "open the pull request",
            "VALIDATION": "unit tests passed",
            "BASE_EVIDENCE": f"main at {FULL_SHA}",
            "TESTS_AND_ACTIONS": "unit tests passed; Actions pending",
            "RISK_CLASS": "ordinary",
            "RISK_TRIGGERS": "none",
            "COMPLEXITY_ESTIMATE": (
                "production files=2; net production lines=80; new primitives=none"
            ),
        }
    )
    values.update({key.upper(): value for key, value in overrides.items()})
    return render_work_item.render(template, values)


def add_subsection(text: str, parent: str, title: str, content: str = "documented") -> str:
    marker = f"## {parent}\n"
    start = text.find(marker)
    if start < 0:
        raise AssertionError(f"missing parent section: {parent}")
    end = text.find("\n## ", start + len(marker))
    if end < 0:
        end = len(text)
    insertion = f"\n\n### {title}\n\n{content}"
    return text[:end].rstrip() + insertion + "\n" + text[end:]


class RenderTests(unittest.TestCase):
    def test_render_replaces_all_tokens(self):
        self.assertEqual(render_work_item.render("A {{VALUE}}", {"value": "ok"}), "A ok")

    def test_render_rejects_missing_values(self):
        with self.assertRaisesRegex(ValueError, "MISSING"):
            render_work_item.render("{{MISSING}}", {})

    def test_all_templates_render_to_valid_work_items(self):
        for kind in render_work_item.TEMPLATES:
            with self.subTest(kind=kind):
                self.assertEqual(validate_work_item.validate(kind, rendered_work_item(kind)), [])

    def test_issue_templates_render_markers_reconcilable_from_bodies(self):
        for index, filename in enumerate(("epic.md", "atomic-issue.md"), start=1):
            with self.subTest(template=filename):
                marker = f"ghc:issue:create:{index}"
                template = (ROOT / "assets" / "templates" / filename).read_text(encoding="utf-8")
                values = {token: "none" for token in render_work_item.TOKEN.findall(template)}
                values["OPERATION_MARKER"] = marker
                rendered = render_work_item.render(template, values)
                self.assertTrue(reconcile_state.has_exact_marker(rendered, marker))

                pages = [{"items": [{
                    "number": index,
                    "html_url": f"https://example.test/issues/{index}",
                    "body": rendered,
                }]}]
                with mock.patch.object(reconcile_state, "gh", return_value=(True, pages, "")):
                    matches, errors = reconcile_state.reconcile_bodies(
                        "owner/repo", "issue", marker
                    )
                self.assertEqual(errors, [])
                self.assertEqual([match["number"] for match in matches], [index])


class ValidateTests(unittest.TestCase):
    def test_rejects_issue_keyword_list_without_markdown_sections(self):
        text = "Problem Outcome Scope Non-goals approach Dependencies rollback Acceptance Test plan State"
        codes = {item["code"] for item in validate_work_item.validate("issue", text)}
        self.assertIn("missing-section", codes)

    def test_all_kinds_require_unique_nonempty_second_level_sections(self):
        for kind, required_sections in validate_work_item.SECTIONS.items():
            heading = required_sections[0]
            valid = rendered_work_item(kind)
            for marker in ("#", "###"):
                with self.subTest(kind=kind, error="wrong-level", marker=marker):
                    wrong_level = valid.replace(f"## {heading}", f"{marker} {heading}", 1)
                    codes = {
                        item["code"]
                        for item in validate_work_item.validate(kind, wrong_level)
                    }
                    self.assertIn("missing-section", codes)
            with self.subTest(kind=kind, error="wrong-case"):
                wrong_case = valid.replace(f"## {heading}", f"## {heading.upper()}", 1)
                codes = {item["code"] for item in validate_work_item.validate(kind, wrong_case)}
                self.assertIn("missing-section", codes)
            with self.subTest(kind=kind, error="duplicate"):
                duplicate = valid + f"\n## {heading}\n\nduplicate content\n"
                codes = {item["code"] for item in validate_work_item.validate(kind, duplicate)}
                self.assertIn("duplicate-section", codes)
            with self.subTest(kind=kind, error="empty"):
                empty = f"## {heading}\n\n"
                codes = {item["code"] for item in validate_work_item.validate(kind, empty)}
                self.assertIn("empty-section", codes)

    def test_allows_extra_sections_and_ignores_structures_in_code_fences(self):
        issue = rendered_work_item("issue") + "\n## Notes\n\nExtra context.\n"
        self.assertEqual(validate_work_item.validate("issue", issue), [])
        fenced = rendered_work_item("issue").replace(
            "## Problem and evidence",
            "```markdown\n## Problem and evidence",
            1,
        ).replace("## Outcome", "```\n\n## Outcome", 1)
        codes = {item["code"] for item in validate_work_item.validate("issue", fenced)}
        self.assertIn("missing-section", codes)

        quoted = rendered_work_item("issue").replace("## Outcome", "> ## Outcome", 1)
        codes = {item["code"] for item in validate_work_item.validate("issue", quoted)}
        self.assertIn("missing-section", codes)

    def test_ignores_sections_and_fields_in_html_comments(self):
        issue_without_marker = rendered_work_item("issue").partition("\n\n")[2]
        hidden_issue = "<!--\n" + issue_without_marker + "\n-->"
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", hidden_issue)
        }
        self.assertIn("missing-section", codes)

        issue = rendered_work_item("issue").replace(
            "- Stage: ready",
            "<!--\n- Stage: ready\n-->",
            1,
        )
        codes = {item["code"] for item in validate_work_item.validate("issue", issue)}
        self.assertIn("missing-field", codes)

        hidden_secret = hidden_issue + "\n<!-- github_pat_" + "A" * 80 + " -->"
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", hidden_secret)
        }
        self.assertIn("secret", codes)

    def test_code_literals_do_not_open_html_comments(self):
        quoted_sha = f"`{FULL_SHA}`"
        issue = rendered_work_item(
            "issue",
            baseline=quoted_sha,
            last_remote_sha=quoted_sha,
        )
        for literal in (
            "Literal opener syntax: `<!--`",
            "    <!-- literal indented code",
            "Literal multiline code: `<!--\nstill code`",
            "Escaped opener syntax: \\<!--",
        ):
            with self.subTest(literal=literal):
                body = issue.replace(
                    "## Problem and evidence",
                    f"## Notes\n\n{literal}\n\n## Problem and evidence",
                    1,
                )
                self.assertEqual(validate_work_item.validate("issue", body), [])

        unmatched = issue.replace(
            "## Problem and evidence\n\ndocumented",
            "## Notes\n\nUnmatched ` delimiter\n\n<!--\n"
            "## Problem and evidence\n\nhidden\n-->",
            1,
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", unmatched)
        }
        self.assertIn("missing-section", codes)

        later_inline_code = issue.replace(
            "## Problem and evidence\n\ndocumented",
            "## Problem and evidence\n\nUnmatched ` delimiter",
            1,
        )
        self.assertEqual(validate_work_item.validate("issue", later_inline_code), [])

        escaped_tick = issue.replace(
            "- Stage: ready",
            "Escaped \\` literal <!--\n- Stage: ready\n-->\n` later literal",
            1,
        )
        self.assertEqual(validate_work_item.validate("issue", escaped_tick), [])

    def test_rejects_indented_sections_fields_and_fences(self):
        issue = rendered_work_item("issue")
        for indentation in (" ", "  ", "   ", "\t"):
            with self.subTest(indentation=repr(indentation)):
                indented_heading = issue.replace(
                    "## Outcome", f"{indentation}## Outcome", 1
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "issue", indented_heading
                    )
                }
                self.assertIn("missing-section", codes)

        tabbed_field = issue.replace("- Stage: ready", "\t- Stage: ready", 1)
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", tabbed_field)
        }
        self.assertIn("missing-field", codes)

        tabbed_fence = "\t```not-a-fence\n" + issue
        self.assertEqual(validate_work_item.validate("issue", tabbed_fence), [])

    def test_issue_fields_must_be_unique_and_in_state_section(self):
        issue = rendered_work_item("issue")
        duplicate = issue.replace("- Stage: ready", "- Stage: ready\n- Stage: ready")
        codes = {item["code"] for item in validate_work_item.validate("issue", duplicate)}
        self.assertIn("duplicate-field", codes)

        misplaced = issue.replace("- Stage: ready\n", "")
        misplaced = misplaced.replace("## Outcome\n", "## Outcome\n\n- Stage: ready\n", 1)
        codes = {item["code"] for item in validate_work_item.validate("issue", misplaced)}
        self.assertIn("missing-field", codes)

        hidden = issue.replace("- Stage: ready", "```text\n- Stage: ready\n```", 1)
        codes = {item["code"] for item in validate_work_item.validate("issue", hidden)}
        self.assertIn("missing-field", codes)

        quoted = issue.replace("- Stage: ready", "> - Stage: ready", 1)
        codes = {item["code"] for item in validate_work_item.validate("issue", quoted)}
        self.assertIn("missing-field", codes)

        wrong_case = issue.replace("- Stage: ready", "- stage: ready", 1)
        codes = {item["code"] for item in validate_work_item.validate("issue", wrong_case)}
        self.assertIn("missing-field", codes)

        empty = issue.replace(
            "- Next action: open the pull request",
            "- Next action:",
            1,
        )
        codes = {item["code"] for item in validate_work_item.validate("issue", empty)}
        self.assertIn("invalid-value", codes)

    def test_issue_validates_stage_and_sha_state(self):
        invalid_stage = rendered_work_item("issue", stage="coding")
        codes = {item["code"] for item in validate_work_item.validate("issue", invalid_stage)}
        self.assertIn("invalid-value", codes)

        invalid_baseline = rendered_work_item("issue", baseline="none")
        codes = {item["code"] for item in validate_work_item.validate("issue", invalid_baseline)}
        self.assertIn("invalid-value", codes)

        self.assertEqual(
            validate_work_item.validate(
                "issue", rendered_work_item("issue", last_remote_sha="none")
            ),
            [],
        )
        invalid_remote = rendered_work_item(
            "issue", last_remote_sha=f"{FULL_SHA} {FULL_SHA}"
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", invalid_remote)
        }
        self.assertIn("invalid-value", codes)

    def test_issue_requires_screening_fields_in_dependencies_section(self):
        issue = rendered_work_item("issue")
        for field in ("Risk class", "Risk triggers", "Complexity estimate"):
            with self.subTest(field=field):
                missing = re.sub(rf"^- {re.escape(field)}:.*\n", "", issue, count=1, flags=re.MULTILINE)
                codes = {
                    item["code"]
                    for item in validate_work_item.validate("issue", missing)
                }
                self.assertIn("missing-field", codes)

        duplicate = issue.replace(
            "- Risk class: ordinary",
            "- Risk class: ordinary\n- Risk class: ordinary",
            1,
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", duplicate)
        }
        self.assertIn("duplicate-field", codes)

        misplaced = issue.replace("- Risk class: ordinary\n", "", 1)
        misplaced = misplaced.replace(
            "## Outcome\n", "## Outcome\n\n- Risk class: ordinary\n", 1
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", misplaced)
        }
        self.assertIn("missing-field", codes)

    def test_screening_rejects_invalid_class_trigger_and_complexity_syntax(self):
        cases = (
            ("risk_class", "routine"),
            ("risk_triggers", "security,unknown"),
            ("risk_triggers", "security,security"),
            ("complexity_estimate", "2 files and 80 lines"),
            (
                "complexity_estimate",
                "production files=-1; net production lines=80; new primitives=none",
            ),
            (
                "complexity_estimate",
                "production files=2; net production lines=80; new primitives=database",
            ),
            (
                "complexity_estimate",
                "production files=2; net production lines=80; new primitives=none; "
                "budget override=none; production file budget=20; "
                "net production line budget=1000",
            ),
            (
                "complexity_estimate",
                "production files=2; net production lines=80; new primitives=none; "
                "budget override=policy; production file budget=20; "
                "net production line budget=1000",
            ),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "issue", rendered_work_item("issue", **{field: value})
                    )
                }
                self.assertIn("invalid-value", codes)

    def test_risk_class_and_triggers_are_consistent(self):
        ordinary_with_trigger = rendered_work_item(
            "issue", risk_class="ordinary", risk_triggers="security"
        )
        ordinary_with_trigger = add_subsection(
            ordinary_with_trigger,
            "Risks, migration, and rollback",
            "Threat model",
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", ordinary_with_trigger)
        }
        self.assertIn("invalid-risk-class", codes)

        for risk_class in ("enhanced", "high"):
            with self.subTest(risk_class=risk_class):
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "issue",
                        rendered_work_item(
                            "issue", risk_class=risk_class, risk_triggers="none"
                        ),
                    )
                }
                self.assertIn("invalid-risk-class", codes)

    def test_default_budget_re_evaluates_without_forcing_decomposition(self):
        at_limit = rendered_work_item(
            "issue",
            complexity_estimate=(
                "production files=10; net production lines=500; new primitives=none"
            ),
        )
        self.assertEqual(validate_work_item.validate("issue", at_limit), [])

        for estimate in (
            "production files=11; net production lines=500; new primitives=none",
            "production files=10; net production lines=501; new primitives=none",
        ):
            with self.subTest(estimate=estimate):
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "issue",
                        rendered_work_item("issue", complexity_estimate=estimate),
                    )
                }
                self.assertIn("missing-risk-trigger", codes)
                self.assertIn("invalid-risk-class", codes)

        enhanced = rendered_work_item(
            "issue",
            risk_class="enhanced",
            risk_triggers="budget",
            complexity_estimate=(
                "production files=11; net production lines=501; new primitives=none"
            ),
        )
        enhanced = add_subsection(
            enhanced,
            "Design basis and approach",
            "Scope and budget decision",
        )
        self.assertEqual(validate_work_item.validate("issue", enhanced), [])

        overridden = rendered_work_item(
            "issue",
            complexity_estimate=(
                "production files=12; net production lines=600; new primitives=none; "
                "budget override=AGENTS.md#complexity; production file budget=20; "
                "net production line budget=1000"
            ),
        )
        self.assertEqual(validate_work_item.validate("issue", overridden), [])

        lower_override = rendered_work_item(
            "issue",
            complexity_estimate=(
                "production files=12; net production lines=600; new primitives=none; "
                "budget override=AGENTS.md#complexity; production file budget=5; "
                "net production line budget=100"
            ),
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", lower_override)
        }
        self.assertIn("missing-risk-trigger", codes)
        self.assertIn("invalid-risk-class", codes)

    def test_new_primitives_require_matching_trigger_and_material(self):
        cases = (
            ("storage", "persistence", "Risks, migration, and rollback", "Data invariants and recovery"),
            ("transaction", "transaction", "Risks, migration, and rollback", "Data invariants and recovery"),
            ("migration", "migration", "Risks, migration, and rollback", "Data invariants and recovery"),
            ("concurrency", "concurrency", "Design basis and approach", "Concurrency model"),
        )
        for primitive, trigger, parent, title in cases:
            estimate = (
                f"production files=2; net production lines=80; new primitives={primitive}"
            )
            with self.subTest(primitive=primitive, error="missing-trigger"):
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "issue", rendered_work_item("issue", complexity_estimate=estimate)
                    )
                }
                self.assertIn("missing-risk-trigger", codes)

            issue = rendered_work_item(
                "issue",
                risk_class="enhanced",
                risk_triggers=trigger,
                complexity_estimate=estimate,
            )
            issue = add_subsection(issue, parent, title)
            with self.subTest(primitive=primitive, result="valid"):
                self.assertEqual(validate_work_item.validate("issue", issue), [])

    def test_each_trigger_routes_only_its_matching_material(self):
        for trigger, (parent, title) in validate_work_item.RISK_MATERIALS.items():
            with self.subTest(trigger=trigger, result="missing"):
                issue = rendered_work_item(
                    "issue", risk_class="enhanced", risk_triggers=trigger
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate("issue", issue)
                }
                self.assertIn("missing-risk-material", codes)

            with self.subTest(trigger=trigger, result="valid"):
                issue = add_subsection(issue, parent, title)
                self.assertEqual(validate_work_item.validate("issue", issue), [])

    def test_risk_material_must_be_unique_nonempty_and_under_expected_parent(self):
        issue = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="security"
        )
        empty = add_subsection(
            issue, "Risks, migration, and rollback", "Additional context"
        )
        empty = add_subsection(
            empty, "Risks, migration, and rollback", "Threat model", ""
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", empty)
        }
        self.assertIn("empty-risk-material", codes)

        duplicate = add_subsection(
            add_subsection(
                issue, "Risks, migration, and rollback", "Threat model"
            ),
            "Risks, migration, and rollback",
            "Threat model",
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", duplicate)
        }
        self.assertIn("duplicate-risk-material", codes)

        misplaced = add_subsection(issue, "Design basis and approach", "Threat model")
        codes = {
            item["code"] for item in validate_work_item.validate("issue", misplaced)
        }
        self.assertIn("missing-risk-material", codes)

        fenced = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="concurrency"
        )
        fenced = add_subsection(
            fenced,
            "Design basis and approach",
            "Concurrency model",
            "```text\n```",
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", fenced)
        }
        self.assertIn("empty-risk-material", codes)

        nonempty_fence = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="concurrency"
        )
        nonempty_fence = add_subsection(
            nonempty_fence,
            "Design basis and approach",
            "Concurrency model",
            "```mermaid\nsequenceDiagram\n    A->>B: ordered handoff\n```",
        )
        self.assertEqual(validate_work_item.validate("issue", nonempty_fence), [])

        for trigger, title in (
            ("shared-paths", "Ownership and integration plan"),
            ("decomposition", "Parent/child delivery plan"),
        ):
            with self.subTest(trigger=trigger, error="empty-material"):
                empty_dependencies = rendered_work_item(
                    "issue", risk_class="enhanced", risk_triggers=trigger
                )
                empty_dependencies = add_subsection(
                    empty_dependencies,
                    "Dependencies and ownership",
                    title,
                    "",
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "issue", empty_dependencies
                    )
                }
                self.assertIn("empty-risk-material", codes)

    def test_screening_fields_cannot_hide_in_code_or_nested_material(self):
        issue = rendered_work_item("issue")
        screening = (
            "- Risk class: ordinary\n"
            "- Risk triggers: none\n"
            "- Complexity estimate: production files=2; net production lines=80; "
            "new primitives=none"
        )
        for replacement in (
            screening.replace("- ", ""),
            screening.replace("- ", "* "),
            "\n".join(f"`{line}`" for line in screening.splitlines()),
        ):
            with self.subTest(replacement=replacement.splitlines()[0]):
                hidden = issue.replace(screening, replacement, 1)
                codes = {
                    item["code"]
                    for item in validate_work_item.validate("issue", hidden)
                }
                self.assertIn("missing-field", codes)

        nested_only = issue.replace(screening, "", 1)
        nested_only = add_subsection(
            nested_only,
            "Dependencies and ownership",
            "Parent/child delivery plan",
            screening,
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", nested_only)
        }
        self.assertIn("missing-field", codes)

        nested_child = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="decomposition"
        )
        nested_child = add_subsection(
            nested_child,
            "Dependencies and ownership",
            "Parent/child delivery plan",
            "Child #12 delta:\n- Risk class: ordinary\n- Risk triggers: none\n"
            "- Complexity estimate: production files=1; net production lines=20; "
            "new primitives=none",
        )
        self.assertEqual(validate_work_item.validate("issue", nested_child), [])

    def test_raw_html_cannot_supply_required_risk_material(self):
        issue = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="concurrency"
        )
        issue = add_subsection(
            issue, "Design basis and approach", "Concurrency model"
        )
        for opener in (
            "<div>",
            '<x title=">">',
            "</script>",
            "<!DOCTYPE html>",
        ):
            with self.subTest(opener=opener):
                hidden = issue.replace(
                    "### Concurrency model\n\ndocumented",
                    f"{opener}\n### Concurrency model\ndocumented",
                    1,
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate("issue", hidden)
                }
                self.assertIn("raw-html", codes)

        inline_opener = rendered_work_item("issue").replace(
            "## Outcome",
            "prefix <!--\n<div>\nraw\n</div>\n-->\n## Outcome",
            1,
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", inline_opener)
        }
        self.assertIn("raw-html", codes)

        container_material = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="concurrency"
        ).replace(
            "## Design basis and approach\n\ndocumented",
            "## Design basis and approach\n\ndocumented\n\n"
            "- <div>\n  ### Concurrency model\n  documented",
            1,
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", container_material)
        }
        self.assertIn("missing-risk-material", codes)

        container_fence = rendered_work_item(
            "issue", risk_class="enhanced", risk_triggers="concurrency"
        ).replace(
            "## Design basis and approach\n\ndocumented",
            "## Design basis and approach\n\ndocumented\n\n"
            "- ```\n  ### Concurrency model\n  documented",
            1,
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("issue", container_fence)
        }
        self.assertIn("missing-risk-material", codes)

    def test_allows_html_comments_code_examples_and_autolinks(self):
        issue = rendered_work_item("issue").replace(
            "## Outcome",
            "<!-- <div> note only -->\n"
            "```html\n<div>\n```\n"
            "    <div>\n"
            "<https://example.test>\n\n"
            "## Outcome",
            1,
        )
        self.assertEqual(validate_work_item.validate("issue", issue), [])

        indented_container_comment = rendered_work_item("issue").replace(
            "## Outcome", "- item\n  <!--\n## Outcome\n-->", 1
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate(
                "issue", indented_container_comment
            )
        }
        self.assertIn("raw-html", codes)
        self.assertNotIn("missing-section", codes)

        indented_container_fence = rendered_work_item("issue").replace(
            "## Outcome", "- item\n  ```\n## Outcome", 1
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate(
                "issue", indented_container_fence
            )
        }
        self.assertIn("noncanonical-fence", codes)
        self.assertNotIn("missing-section", codes)

        raw_after_container_fence = (
            rendered_work_item("issue")
            + "\n- item\n  ```\n<div>\nraw\n</div>\n"
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate(
                "issue", raw_after_container_fence
            )
        }
        self.assertTrue({"noncanonical-fence", "raw-html"}.issubset(codes))

    def test_high_risk_requires_separate_preimplementation_design_audit(self):
        issue = rendered_work_item(
            "issue", risk_class="high", risk_triggers="security"
        )
        issue = add_subsection(
            issue, "Risks, migration, and rollback", "Threat model"
        )
        codes = {
            item["code"] for item in validate_work_item.validate("issue", issue)
        }
        self.assertIn("missing-risk-material", codes)

        issue = add_subsection(
            issue,
            "Design basis and approach",
            "Pre-implementation design audit",
        )
        self.assertEqual(validate_work_item.validate("issue", issue), [])

    def test_accepts_stable_stages_and_supported_sha_encodings(self):
        for stage in validate_work_item.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(
                    validate_work_item.validate(
                        "issue",
                        rendered_work_item("issue", stage=stage),
                    ),
                    [],
                )

        uppercase_sha = FULL_SHA.upper()
        for value in (uppercase_sha, f"`{uppercase_sha}`"):
            with self.subTest(sha=value):
                self.assertEqual(
                    validate_work_item.validate(
                        "issue",
                        rendered_work_item(
                            "issue",
                            baseline=value,
                            last_remote_sha=value,
                        ),
                    ),
                    [],
                )
                self.assertEqual(
                    validate_work_item.validate(
                        "checkpoint",
                        rendered_work_item("checkpoint", full_remote_sha=value),
                    ),
                    [],
                )
                self.assertEqual(
                    validate_work_item.validate(
                        "pr",
                        rendered_work_item("pr", candidate_full_sha=value),
                    ),
                    [],
                )

        for value in ("a" * 39, "a" * 41):
            with self.subTest(invalid_sha=value):
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "checkpoint",
                        rendered_work_item("checkpoint", full_remote_sha=value),
                    )
                }
                self.assertTrue({"invalid-value", "full-sha"}.issubset(codes))

    def test_detects_secret_local_path_and_placeholder(self):
        text = (
            rendered_work_item("issue")
            + "\ntoken=ghp_abcdefghijklmnopqrstuvwxyz123456\n/Users/alice/repo\n{{LEFT}}"
        )
        codes = {item["code"] for item in validate_work_item.validate("issue", text)}
        self.assertTrue({"secret", "local-path", "placeholder"}.issubset(codes))

    def test_rejects_pr_auto_close_keyword(self):
        text = rendered_work_item("pr") + "\nFixes #12"
        codes = {item["code"] for item in validate_work_item.validate("pr", text)}
        self.assertIn("auto-close", codes)

    def test_detects_fine_grained_github_pat(self):
        text = rendered_work_item("issue") + "\ngithub_pat_" + "A" * 80
        codes = {item["code"] for item in validate_work_item.validate("issue", text)}
        self.assertIn("secret", codes)

    def test_rejects_colon_and_cross_repo_auto_close_syntax(self):
        base = rendered_work_item("pr") + "\n"
        for syntax in ("Closes: #12", "CLOSES:#12", "Fixes owner/repo#12"):
            with self.subTest(syntax=syntax):
                codes = {item["code"] for item in validate_work_item.validate("pr", base + syntax)}
                self.assertIn("auto-close", codes)
        self.assertNotIn(
            "auto-close",
            {item["code"] for item in validate_work_item.validate("pr", base + "Refs #12")},
        )

    def test_checkpoint_sha_is_anchored_to_its_field(self):
        text = """## Checkpoint
- Stage: ready
- Branch: agent/issue-2-v1
- Full remote SHA: deadbeef
- Completed: implementation
- Remaining: pull request
- Validation: commit 0123456789abcdef0123456789abcdef01234567 passed
- Blocker: none
- Next action: open PR
"""
        codes = {item["code"] for item in validate_work_item.validate("checkpoint", text)}
        self.assertIn("full-sha", codes)

    def test_checkpoint_rejects_duplicate_sha_fields(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        text = f"""## Checkpoint
- Stage: ready
- Branch: agent/issue-2-v1
- Full remote SHA: {sha}
- Full remote SHA: {sha}
- Completed: implementation
- Remaining: pull request
- Validation: passed
- Blocker: none
- Next action: open PR
"""
        codes = {item["code"] for item in validate_work_item.validate("checkpoint", text)}
        self.assertIn("duplicate-field", codes)
        self.assertIn("full-sha", codes)

    def test_accepts_complete_checkpoint(self):
        text = """## Checkpoint
- Stage: ready
- Branch: agent/issue-2-v1
- Full remote SHA: 0123456789abcdef0123456789abcdef01234567
- Completed: implementation
- Remaining: pull request
- Validation: passed
- Blocker: none
- Next action: open PR
"""
        self.assertEqual(validate_work_item.validate("checkpoint", text), [])

    def test_checkpoint_accepts_legacy_and_list_field_syntax(self):
        checkpoint = rendered_work_item("checkpoint")
        for marker in ("", "* ", "+ "):
            with self.subTest(marker=marker or "plain"):
                variant = checkpoint.replace("- ", marker)
                self.assertEqual(validate_work_item.validate("checkpoint", variant), [])

        nested_legacy = checkpoint.replace(
            "## Checkpoint", "## Checkpoint\n\n### Legacy details", 1
        )
        self.assertEqual(
            validate_work_item.validate("checkpoint", nested_legacy), []
        )

    def test_checkpoint_rejects_fields_hidden_in_markdown_containers(self):
        checkpoint = rendered_work_item("checkpoint")
        fields = [
            "  " + line.removeprefix("- ")
            for line in checkpoint.splitlines()
            if line.startswith("- ")
        ]
        for opener, expected in (
            ("- <!--", "raw-html"),
            ("- prefix <!--", "raw-html"),
            ("- <div>", "raw-html"),
            ("- ```", "noncanonical-fence"),
        ):
            with self.subTest(opener=opener):
                hidden = "## Checkpoint\n\n" + opener + "\n" + "\n".join(fields)
                codes = {
                    item["code"]
                    for item in validate_work_item.validate("checkpoint", hidden)
                }
                self.assertIn(expected, codes)

        inline_comment = (
            "## Checkpoint\n\nprefix <!--\n"
            + "\n".join(fields)
            + "\n-->"
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate(
                "checkpoint", inline_comment
            )
        }
        self.assertIn("raw-html", codes)

        plain_fields = "\n".join(line.removeprefix("  ") for line in fields)
        for continuation in ("    <!--", "\t<!--"):
            with self.subTest(continuation=repr(continuation)):
                hidden_continuation = (
                    "## Checkpoint\n\nprefix\n"
                    + continuation
                    + "\n"
                    + plain_fields
                    + "\n-->"
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "checkpoint", hidden_continuation
                    )
                }
                self.assertIn("raw-html", codes)

                hidden_list_continuation = (
                    "## Checkpoint\n\n- prefix\n"
                    + continuation
                    + "\n"
                    + "\n".join(fields)
                    + "\n  -->"
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "checkpoint", hidden_list_continuation
                    )
                }
                self.assertIn("raw-html", codes)

        for literal in ("    <!-- literal", "\t<!-- literal"):
            with self.subTest(literal=repr(literal)):
                visible_fields = (
                    "## Checkpoint\n\n" + literal + "\n" + plain_fields
                )
                self.assertEqual(
                    validate_work_item.validate(
                        "checkpoint", visible_fields
                    ),
                    [],
                )

        for opener, expected in (
            ("> - <div>", "raw-html"),
            ("- > ```", "noncanonical-fence"),
        ):
            with self.subTest(opener=opener):
                nested = rendered_work_item("checkpoint") + "\n" + opener
                codes = {
                    item["code"]
                    for item in validate_work_item.validate("checkpoint", nested)
                }
                self.assertIn(expected, codes)

    def test_legacy_plain_fields_cannot_hide_in_multiline_code_spans(self):
        checkpoint = rendered_work_item("checkpoint")
        plain_checkpoint = checkpoint.replace("- ", "")
        hidden_checkpoint = plain_checkpoint.replace(
            "## Checkpoint\n\n", "## Checkpoint\n\n`\n", 1
        ).rstrip() + "\n`"
        codes = {
            item["code"]
            for item in validate_work_item.validate(
                "checkpoint", hidden_checkpoint
            )
        }
        self.assertIn("missing-field", codes)

        plain_fields = "\n".join(
            line
            for line in plain_checkpoint.splitlines()
            if ":" in line and not line.startswith("<!-")
        )
        for filler in (
            "    indented continuation",
            "\tindented continuation",
            "0. ordered continuation",
            "2. ordered continuation",
            "*",
            "+",
            "1.",
            "1)",
        ):
            with self.subTest(filler=repr(filler)):
                hidden_with_indent = (
                    "## Checkpoint\n\n`\n"
                    + filler
                    + "\n"
                    + plain_fields
                    + "\n`"
                )
                codes = {
                    item["code"]
                    for item in validate_work_item.validate(
                        "checkpoint", hidden_with_indent
                    )
                }
                self.assertIn("missing-field", codes)

        interrupted_ordered = (
            "## Checkpoint\n\n`\n1. list interruption\n"
            + plain_fields
            + "\n`"
        )
        self.assertEqual(
            validate_work_item.validate("checkpoint", interrupted_ordered), []
        )

        interrupted_setext = (
            "## Checkpoint\n\n`\n-\n" + plain_fields + "\n`"
        )
        self.assertEqual(
            validate_work_item.validate("checkpoint", interrupted_setext), []
        )

        interrupted_checkpoint = checkpoint.replace(
            "## Checkpoint\n\n", "## Checkpoint\n\n`\n", 1
        ).rstrip() + "\n`"
        self.assertEqual(
            validate_work_item.validate("checkpoint", interrupted_checkpoint), []
        )

        pr = rendered_work_item("pr")
        candidate_fields = (
            f"- Candidate full SHA: {FULL_SHA}\n"
            f"- Base evidence: main at {FULL_SHA}\n"
            "- Tests and Actions: unit tests passed; Actions pending"
        )
        hidden_pr = pr.replace(
            candidate_fields,
            "`\n" + candidate_fields.replace("- ", "") + "\n`",
            1,
        )
        codes = {
            item["code"]
            for item in validate_work_item.validate("pr", hidden_pr)
        }
        self.assertIn("missing-field", codes)

    def test_checkpoint_requires_all_fields_and_real_remote_sha(self):
        checkpoint = rendered_work_item("checkpoint")
        missing_completed = checkpoint.replace("- Completed: documented\n", "")
        codes = {
            item["code"]
            for item in validate_work_item.validate("checkpoint", missing_completed)
        }
        self.assertIn("missing-field", codes)

        empty_sha = rendered_work_item("checkpoint", full_remote_sha="none")
        codes = {item["code"] for item in validate_work_item.validate("checkpoint", empty_sha)}
        self.assertTrue({"invalid-value", "full-sha"}.issubset(codes))

    def test_pr_fields_are_required_and_candidate_is_exact_full_sha(self):
        pr = rendered_work_item("pr")
        missing_tests = pr.replace("- Tests and Actions: unit tests passed; Actions pending\n", "")
        codes = {item["code"] for item in validate_work_item.validate("pr", missing_tests)}
        self.assertIn("missing-field", codes)

        misplaced_candidate = pr.replace(f"- Candidate full SHA: {FULL_SHA}\n", "")
        misplaced_candidate = misplaced_candidate.replace(
            "## Implementation\n", f"## Implementation\n\n- Candidate full SHA: {FULL_SHA}\n", 1
        )
        codes = {item["code"] for item in validate_work_item.validate("pr", misplaced_candidate)}
        self.assertIn("missing-field", codes)

        multiple = rendered_work_item("pr", candidate_full_sha=f"{FULL_SHA} {FULL_SHA}")
        codes = {item["code"] for item in validate_work_item.validate("pr", multiple)}
        self.assertIn("invalid-value", codes)

    def test_cli_preserves_json_and_exit_code_contract(self):
        huge_estimate = (
            "production files="
            + "9" * 5000
            + "; net production lines=80; new primitives=none"
        )
        for valid, text in (
            (True, rendered_work_item("issue")),
            (False, "Problem Outcome Scope State"),
            (
                False,
                rendered_work_item(
                    "issue", complexity_estimate=huge_estimate
                ),
            ),
        ):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "issue.md"
                path.write_text(text, encoding="utf-8")
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "validate_work_item.py"),
                        "--kind",
                        "issue",
                        str(path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                payload = json.loads(result.stdout)
                self.assertEqual(payload["valid"], valid)
                self.assertEqual(result.returncode, 0 if valid else 1)


class InspectTests(unittest.TestCase):
    def test_unknown_github_state_stays_unknown(self):
        def fake_run(command, cwd):
            key = " ".join(command)
            if key.startswith("git rev-parse --show-toplevel"):
                return {"ok": True, "returncode": 0, "stdout": str(cwd), "stderr": ""}
            if key == "git status --porcelain=v1":
                return {"ok": True, "returncode": 0, "stdout": " M file", "stderr": ""}
            if key == "git branch --show-current":
                return {"ok": True, "returncode": 0, "stdout": "agent/issue-2-v1", "stderr": ""}
            if key == "git rev-parse HEAD":
                return {"ok": True, "returncode": 0, "stdout": "a" * 40, "stderr": ""}
            if key == "git remote get-url origin":
                return {"ok": True, "returncode": 0, "stdout": "https://github.com/o/r.git", "stderr": ""}
            return {"ok": False, "returncode": 1, "stdout": "", "stderr": "offline"}

        with mock.patch.object(inspect_repo, "run_command", side_effect=fake_run):
            result = inspect_repo.inspect(Path.cwd(), "o/r")
        self.assertTrue(result["git"]["dirty"])
        self.assertFalse(result["github"]["available"])
        self.assertIsNone(result["github"]["repository"])

    def test_clean_authorized_repository_is_preserved(self):
        repository = {
            "nameWithOwner": "owner/repo",
            "visibility": "PUBLIC",
            "viewerPermission": "WRITE",
            "defaultBranchRef": {"name": "main"},
        }

        def fake_run(command, cwd):
            key = " ".join(command)
            outputs = {
                "git rev-parse --show-toplevel": str(cwd),
                "git status --porcelain=v1": "",
                "git branch --show-current": "main",
                "git rev-parse HEAD": "a" * 40,
                "git remote get-url origin": "https://github.com/owner/repo.git",
                "gh api user --jq .login": "agent-user",
            }
            if key.startswith("gh repo view"):
                return {"ok": True, "returncode": 0, "stdout": json.dumps(repository), "stderr": ""}
            return {"ok": True, "returncode": 0, "stdout": outputs[key], "stderr": ""}

        with mock.patch.object(inspect_repo, "run_command", side_effect=fake_run):
            result = inspect_repo.inspect(Path.cwd(), "owner/repo")
        self.assertFalse(result["git"]["dirty"])
        self.assertEqual(result["github"]["actor"], "agent-user")
        self.assertEqual(result["github"]["repository"]["viewerPermission"], "WRITE")


class ReconcileTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(reconcile_state.classify([], []), "absent")
        self.assertEqual(reconcile_state.classify([{}], []), "present")
        self.assertEqual(reconcile_state.classify([{}, {}], []), "conflict")
        self.assertEqual(reconcile_state.classify([], ["offline"]), "unknown")

    def test_issue_comment_uses_numbered_comments_endpoint_and_exact_marker(self):
        marker = "ghc:2:candidate:fe33b18"
        comments = [[
            {"id": 10, "html_url": "https://example.test/10", "body": f"<!-- operation-marker: {marker}:other -->"},
            {"id": 11, "html_url": "https://example.test/11", "body": f"<!-- operation-marker: {marker} -->"},
        ]]
        with mock.patch.object(reconcile_state, "gh", return_value=(True, comments, "")) as gh_mock:
            matches, errors = reconcile_state.reconcile_comments("owner/repo", 2, marker)
        gh_mock.assert_called_once_with([
            "api", "--paginate", "--slurp", "-X", "GET",
            "repos/owner/repo/issues/2/comments", "-f", "per_page=100",
        ])
        self.assertEqual(errors, [])
        self.assertEqual([match["comment_id"] for match in matches], [11])

    def test_branch_requires_expected_sha_match(self):
        expected = "a" * 40
        response = {"ref": "refs/heads/agent/issue-2-v1", "object": {"sha": "b" * 40}}
        with mock.patch.object(reconcile_state, "gh", return_value=(True, response, "")):
            matches, conflicts, errors = reconcile_state.reconcile_branch(
                "owner/repo", "agent/issue-2-v1", expected
            )
        self.assertEqual(matches, [])
        self.assertEqual(errors, [])
        self.assertEqual(conflicts[0]["expected_sha"], expected)
        self.assertEqual(conflicts[0]["actual_sha"], "b" * 40)

        response["object"]["sha"] = expected
        with mock.patch.object(reconcile_state, "gh", return_value=(True, response, "")):
            matches, conflicts, errors = reconcile_state.reconcile_branch(
                "owner/repo", "agent/issue-2-v1", expected
            )
        self.assertEqual(len(matches), 1)
        self.assertEqual(conflicts, [])
        self.assertEqual(errors, [])


class SkillPolicyTests(unittest.TestCase):
    def test_merge_requires_current_message_and_forbids_admin_bypass(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        review = (ROOT / "references" / "pr-review-and-close.md").read_text(encoding="utf-8").lower()
        self.assertIn("current user message", skill)
        self.assertIn("never use admin bypass", review)
        self.assertIn("stop when the pr is ready for human review", review)

    def test_risk_controls_are_progressive_and_do_not_tax_ordinary_work(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        issue_reference = (ROOT / "references" / "issue-and-epic.md").read_text(
            encoding="utf-8"
        )
        risk = (ROOT / "references" / "risk-controls.md").read_text(encoding="utf-8")
        complexity = (
            ROOT / "references" / "complexity-and-decomposition.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Risk class", skill)
        self.assertIn("references/risk-controls.md", skill)
        self.assertIn("references/complexity-and-decomposition.md", skill)
        self.assertIn("read only the matching section", skill)
        for trigger in (
            "security",
            "privacy",
            "persistence",
            "transaction",
            "migration",
            "concurrency",
            "shared-paths",
            "decomposition",
        ):
            self.assertIn(trigger, issue_reference)
        self.assertIn("more than 10 production files or 500 net production lines", issue_reference)
        self.assertIn("New `storage`", issue_reference)
        self.assertIn("`ordinary`, `enhanced`, or `high`", issue_reference)
        self.assertIn("one or more comma-separated triggers", issue_reference)
        self.assertIn("uses the `budget` trigger", issue_reference)
        self.assertIn("budget override=<relative policy path>", issue_reference)
        self.assertIn("production file budget=<n>", issue_reference)
        self.assertIn("Do not load unmatched sections", issue_reference)
        self.assertIn("Read only the section linked", risk)
        self.assertIn("Ordinary work does not gain another GitHub write", complexity)
        self.assertIn("does not automatically split or terminate", complexity)
        self.assertIn("generated files, vendored code, tests, and documentation", complexity)

    def test_decomposition_keeps_integration_and_review_boundaries(self):
        reference = (
            ROOT / "references" / "complexity-and-decomposition.md"
        ).read_text(encoding="utf-8")
        risk = (ROOT / "references" / "risk-controls.md").read_text(encoding="utf-8")
        self.assertIn("independently reviewable, mergeable, acceptable, and reversible", reference)
        self.assertIn("one integrator and one consolidated delivery PR", reference)
        self.assertIn("never make the reviewer assemble track branches", reference)
        self.assertIn("Child level", reference)
        self.assertIn("Integration level", reference)
        self.assertIn("Parent level", reference)
        self.assertIn("A green child cannot override failed integration", reference)
        self.assertIn("unfinished optional child must be explicitly removed", reference)
        self.assertIn("only its design delta", reference)
        for evidence in ("exact baseline", "acceptance", "rollback", "PR", "actual merge SHA"):
            self.assertIn(evidence, reference)
        self.assertIn("existing `blocked` stage with `Blocker` and `Next action`", reference)
        self.assertIn("Close the parent last", reference)
        self.assertIn("not a GitHub PR approval", risk)


if __name__ == "__main__":
    unittest.main()
