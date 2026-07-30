from __future__ import annotations

import importlib.util
import json
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


class RenderTests(unittest.TestCase):
    def test_render_replaces_all_tokens(self):
        self.assertEqual(render_work_item.render("A {{VALUE}}", {"value": "ok"}), "A ok")

    def test_render_rejects_missing_values(self):
        with self.assertRaisesRegex(ValueError, "MISSING"):
            render_work_item.render("{{MISSING}}", {})

    def test_all_templates_render_to_valid_work_items(self):
        for kind, filename in render_work_item.TEMPLATES.items():
            with self.subTest(kind=kind):
                template = (ROOT / "assets" / "templates" / filename).read_text(encoding="utf-8")
                values = {token: "none" for token in render_work_item.TOKEN.findall(template)}
                for key in ("FULL_REMOTE_SHA", "CANDIDATE_FULL_SHA", "BASELINE", "LAST_REMOTE_SHA"):
                    if key in values:
                        values[key] = "0123456789abcdef0123456789abcdef01234567"
                rendered = render_work_item.render(template, values)
                self.assertEqual(validate_work_item.validate(kind, rendered), [])


class ValidateTests(unittest.TestCase):
    def test_detects_secret_local_path_and_placeholder(self):
        text = "token=ghp_abcdefghijklmnopqrstuvwxyz123456\n/Users/alice/repo\n{{LEFT}}"
        codes = {item["code"] for item in validate_work_item.validate("issue", text)}
        self.assertTrue({"secret", "local-path", "placeholder"}.issubset(codes))

    def test_rejects_pr_auto_close_keyword(self):
        text = "Outcome references Scope Implementation Candidate validation Risks rollback Known limits\nFixes #12"
        codes = {item["code"] for item in validate_work_item.validate("pr", text)}
        self.assertIn("auto-close", codes)

    def test_detects_fine_grained_github_pat(self):
        text = "github_pat_" + "A" * 80
        codes = {item["code"] for item in validate_work_item.validate("issue", text)}
        self.assertIn("secret", codes)

    def test_rejects_colon_and_cross_repo_auto_close_syntax(self):
        base = "Outcome references Scope Implementation Candidate validation Risks rollback Known limits\n"
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
Stage: ready
Branch: agent/issue-2-v1
Full remote SHA: deadbeef
Validation: commit 0123456789abcdef0123456789abcdef01234567 passed
Blocker: none
Next action: open PR
"""
        codes = {item["code"] for item in validate_work_item.validate("checkpoint", text)}
        self.assertIn("full-sha", codes)

    def test_checkpoint_rejects_duplicate_sha_fields(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        text = f"""## Checkpoint
Stage: ready
Branch: agent/issue-2-v1
Full remote SHA: {sha}
Full remote SHA: {sha}
Validation: passed
Next action: open PR
"""
        codes = {item["code"] for item in validate_work_item.validate("checkpoint", text)}
        self.assertIn("full-sha", codes)

    def test_accepts_complete_checkpoint(self):
        text = """## Checkpoint
Stage: ready
Branch: agent/issue-2-v1
Full remote SHA: 0123456789abcdef0123456789abcdef01234567
Validation: passed
Next action: open PR
"""
        self.assertEqual(validate_work_item.validate("checkpoint", text), [])


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


if __name__ == "__main__":
    unittest.main()
