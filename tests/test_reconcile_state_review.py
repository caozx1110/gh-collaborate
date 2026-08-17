from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconcile_state_review", ROOT / "scripts" / "reconcile_state.py"
)
reconcile_state = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconcile_state)


class ReconcileStateReviewTests(unittest.TestCase):
    marker = "ghc:21:review:reconciliation"
    body = f"<!-- operation-marker: {marker} -->\n\nexpected body"

    def verify_arguments(self, kind: str) -> dict[str, object]:
        arguments: dict[str, object] = {
            "repo": "owner/repo",
            "actor": "agent-user",
            "marker": self.marker,
            "body": self.body,
        }
        if kind == "comment":
            arguments["parent_number"] = 10
        if kind == "pr":
            arguments.update(
                {
                    "head_ref": "agent/issue-21-review-blockers",
                    "head_sha": "a" * 40,
                    "base_ref": "development",
                    "base_sha": "b" * 40,
                }
            )
        return arguments

    def issue_response(self) -> dict[str, object]:
        return {
            "number": 10,
            "html_url": "https://github.com/owner/repo/issues/10",
            "repository_url": "https://api.github.com/repos/owner/repo",
            "user": {"login": "agent-user"},
            "body": self.body,
        }

    def comment_response(self) -> dict[str, object]:
        return {
            "id": 99,
            "html_url": (
                "https://github.com/owner/repo/issues/10#issuecomment-99"
            ),
            "issue_url": "https://api.github.com/repos/owner/repo/issues/10",
            "user": {"login": "agent-user"},
            "body": self.body,
        }

    def pr_response(self) -> dict[str, object]:
        return {
            "number": 20,
            "html_url": "https://github.com/owner/repo/pull/20",
            "user": {"login": "agent-user"},
            "body": self.body,
            "head": {
                "ref": "agent/issue-21-review-blockers",
                "sha": "a" * 40,
            },
            "base": {
                "ref": "development",
                "sha": "b" * 40,
                "repo": {"full_name": "owner/repo"},
            },
        }

    def branch_response(
        self,
        branch: str,
        sha: str,
        *,
        repo: str = "owner/repo",
        api_host: str = "api.github.com",
        api_prefix: str = "",
    ) -> dict[str, object]:
        encoded = branch.replace("%", "%25").replace("#", "%23").replace("{", "%7B").replace("}", "%7D")
        repo_path = f"{api_prefix}/repos/{repo}"
        return {
            "ref": f"refs/heads/{branch}",
            "url": f"https://{api_host}{repo_path}/git/refs/heads/{encoded}",
            "object": {
                "type": "commit",
                "sha": sha,
                "url": f"https://{api_host}{repo_path}/git/commits/{sha}",
            },
        }

    def repository_response(self, *, default_branch: str = "main") -> dict[str, object]:
        return {
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
            "url": "https://api.github.com/repos/owner/repo",
            "default_branch": default_branch,
        }

    def pr_list_item(self) -> dict[str, object]:
        return {
            "number": 20,
            "state": "OPEN",
            "url": "https://github.com/owner/repo/pull/20",
            "headRefName": "agent/issue-21",
            "headRefOid": "a" * 40,
            "baseRefName": "development",
            "baseRefOid": "b" * 40,
            "headRepository": {"nameWithOwner": "owner/repo"},
            "headRepositoryOwner": {"login": "owner"},
            "isCrossRepository": False,
        }

    def exact_pr_response(self) -> dict[str, object]:
        return {
            "number": 20,
            "html_url": "https://github.com/owner/repo/pull/20",
            "head": {
                "ref": "agent/issue-21",
                "sha": "a" * 40,
                "repo": {"full_name": "owner/repo"},
            },
            "base": {
                "ref": "development",
                "sha": "b" * 40,
                "repo": {"full_name": "owner/repo"},
            },
        }

    def test_write_response_urls_require_exact_github_identity(self):
        cases = []
        for kind, response in (
            ("issue", self.issue_response()),
            ("comment", self.comment_response()),
            ("pr", self.pr_response()),
        ):
            hostile = dict(response)
            hostile["html_url"] = str(hostile["html_url"]).replace(
                "github.com", "evil.test"
            )
            cases.append((f"{kind}-html-host", kind, hostile))

        hostile_repository = self.issue_response()
        hostile_repository["repository_url"] = (
            "https://evil.test/repos/owner/repo"
        )
        cases.append(("issue-api-host", "issue", hostile_repository))

        hostile_parent = self.comment_response()
        hostile_parent["issue_url"] = (
            "https://evil.test/repos/owner/repo/issues/10"
        )
        cases.append(("comment-api-host", "comment", hostile_parent))

        wrong_parent = self.comment_response()
        wrong_parent["html_url"] = (
            "https://github.com/owner/repo/issues/11#issuecomment-99"
        )
        cases.append(("comment-html-parent", "comment", wrong_parent))

        wrong_comment = self.comment_response()
        wrong_comment["html_url"] = (
            "https://github.com/owner/repo/issues/10#issuecomment-100"
        )
        cases.append(("comment-html-id", "comment", wrong_comment))

        malformed_url = self.issue_response()
        malformed_url["html_url"] = "https://[::1"
        cases.append(("malformed-html-url", "issue", malformed_url))

        controlled_url = self.issue_response()
        controlled_url["html_url"] = (
            "https://github.com/owner/repo/issues/\n10"
        )
        cases.append(("controlled-html-url", "issue", controlled_url))

        for name, kind, response in cases:
            with self.subTest(name=name):
                result = reconcile_state.verify_write_response(
                    kind, response, **self.verify_arguments(kind)
                )
                self.assertEqual(result["classification"], "conflict")
                self.assertTrue(result["conflicts"])

    def test_search_empty_or_incomplete_is_unknown_not_absent(self):
        responses = (
            [{"total_count": 0, "incomplete_results": False, "items": []}],
            [
                {
                    "total_count": 1,
                    "incomplete_results": True,
                    "items": [],
                }
            ],
            [
                {
                    "total_count": 2,
                    "incomplete_results": False,
                    "items": [
                        {
                            "number": 10,
                            "html_url": "https://github.com/owner/repo/issues/10",
                            "body": self.body,
                        }
                    ],
                }
            ],
            [
                {
                    "total_count": 2,
                    "incomplete_results": False,
                    "items": [
                        {
                            "number": 10,
                            "html_url": "https://github.com/owner/repo/issues/10",
                            "body": self.body,
                        }
                    ],
                },
                {
                    "total_count": 2,
                    "incomplete_results": False,
                    "items": [
                        {
                            "number": 10,
                            "html_url": "https://github.com/owner/repo/issues/10",
                            "body": self.body,
                        }
                    ],
                },
            ],
        )
        for response in responses:
            with self.subTest(response=response), mock.patch.object(
                reconcile_state, "gh", return_value=(True, response, "")
            ):
                matches, errors = reconcile_state.reconcile_bodies(
                    "owner/repo", "issue", self.marker
                )
            self.assertEqual(matches, [])
            self.assertTrue(errors)
            self.assertEqual(
                reconcile_state.classify(matches, errors), "unknown"
            )

    def test_empty_comment_slurp_is_unknown_not_absent(self):
        with mock.patch.object(
            reconcile_state, "gh", return_value=(True, [], "")
        ):
            matches, errors = reconcile_state.reconcile_comments(
                "owner/repo", 10, self.marker
            )
        self.assertEqual(matches, [])
        self.assertTrue(errors)
        self.assertEqual(reconcile_state.classify(matches, errors), "unknown")

    def test_comment_body_must_be_present_to_prove_marker_absence(self):
        comment = {
            "id": 99,
            "html_url": (
                "https://github.com/owner/repo/issues/10#issuecomment-99"
            ),
        }
        for candidate in (dict(comment), dict(comment, body=None)):
            with self.subTest(candidate=candidate):
                with mock.patch.object(
                    reconcile_state,
                    "gh",
                    return_value=(True, [[candidate]], ""),
                ):
                    matches, errors = reconcile_state.reconcile_comments(
                        "owner/repo", 10, self.marker
                    )
                self.assertEqual(matches, [])
                self.assertTrue(errors)
                self.assertEqual(
                    reconcile_state.classify(matches, errors), "unknown"
                )

    def test_every_search_and_exact_candidate_requires_a_body(self):
        valid = {
            "number": 10,
            "html_url": "https://github.com/owner/repo/issues/10",
            "body": self.body,
        }
        missing_body = {
            "number": 11,
            "html_url": "https://github.com/owner/repo/issues/11",
        }
        with mock.patch.object(
            reconcile_state,
            "gh",
            return_value=(
                True,
                [
                    {
                        "total_count": 2,
                        "incomplete_results": False,
                        "items": [valid, missing_body],
                    }
                ],
                "",
            ),
        ):
            matches, errors = reconcile_state.reconcile_bodies(
                "owner/repo", "issue", self.marker
            )
        self.assertEqual(matches, [])
        self.assertTrue(errors)

        exact_missing_body = dict(valid)
        exact_missing_body.pop("body")
        with mock.patch.object(
            reconcile_state,
            "gh",
            side_effect=(
                (
                    True,
                    [
                        {
                            "total_count": 1,
                            "incomplete_results": False,
                            "items": [valid],
                        }
                    ],
                    "",
                ),
                (True, exact_missing_body, ""),
            ),
        ):
            matches, errors = reconcile_state.reconcile_bodies(
                "owner/repo", "issue", self.marker
            )
        self.assertEqual(matches, [])
        self.assertTrue(errors)

    def test_malformed_configured_host_is_unknown_not_an_exception(self):
        with mock.patch.dict(
            reconcile_state.os.environ, {"GH_HOST": "[::1"}, clear=False
        ):
            matches, errors = reconcile_state.reconcile_comments(
                "owner/repo", 10, self.marker
            )
        self.assertEqual(matches, [])
        self.assertTrue(errors)

    def test_search_candidates_are_verified_by_exact_object_endpoint(self):
        search_item = {
            "number": 10,
            "html_url": "https://github.com/owner/repo/issues/10",
            "body": self.body,
        }
        exact_issue = dict(search_item)
        responses = iter(
            (
                (
                    True,
                    [
                        {
                            "total_count": 1,
                            "incomplete_results": False,
                            "items": [search_item],
                        }
                    ],
                    "",
                ),
                (True, exact_issue, ""),
            )
        )
        with mock.patch.object(
            reconcile_state, "gh", side_effect=lambda arguments: next(responses)
        ) as gh_mock:
            matches, errors = reconcile_state.reconcile_bodies(
                "owner/repo", "issue", self.marker
            )
        self.assertEqual(errors, [])
        self.assertEqual(matches, [{"kind": "issue", "number": 10, "url": search_item["html_url"]}])
        self.assertEqual(
            gh_mock.call_args_list[-1],
            mock.call(["api", "-X", "GET", "repos/owner/repo/issues/10"]),
        )

    def test_pr_marker_reconciliation_is_bound_to_head_and_base_identity(self):
        search_item = {
            "number": 20,
            "html_url": "https://github.com/owner/repo/pull/20",
            "body": self.body,
            "pull_request": {},
        }
        search = [
            {
                "total_count": 1,
                "incomplete_results": False,
                "items": [search_item],
            }
        ]
        exact = self.exact_pr_response()
        exact["body"] = self.body

        with mock.patch.object(
            reconcile_state,
            "gh",
            side_effect=((True, search, ""), (True, exact, "")),
        ):
            matches, errors = reconcile_state.reconcile_bodies(
                "owner/repo",
                "pr",
                self.marker,
                head_ref="agent/issue-21",
                head_sha="a" * 40,
                base_ref="development",
                base_sha="b" * 40,
            )
        self.assertEqual(errors, [])
        self.assertEqual(matches[0]["number"], 20)

        wrong_base = dict(exact)
        wrong_base["base"] = dict(exact["base"])
        wrong_base["base"]["ref"] = "main"
        with mock.patch.object(
            reconcile_state,
            "gh",
            side_effect=((True, search, ""), (True, wrong_base, "")),
        ):
            matches, errors = reconcile_state.reconcile_bodies(
                "owner/repo",
                "pr",
                self.marker,
                head_ref="agent/issue-21",
                head_sha="a" * 40,
                base_ref="development",
                base_sha="b" * 40,
            )
        self.assertEqual(matches, [])
        self.assertTrue(errors)

    def test_search_and_exact_object_numbers_must_be_positive(self):
        for search_number, exact_number in ((0, 0), (10, 0)):
            with self.subTest(
                search_number=search_number, exact_number=exact_number
            ):
                search_item = {
                    "number": search_number,
                    "html_url": (
                        f"https://github.com/owner/repo/issues/{search_number}"
                    ),
                    "body": self.body,
                }
                exact_item = dict(
                    search_item,
                    number=exact_number,
                    html_url=(
                        f"https://github.com/owner/repo/issues/{exact_number}"
                    ),
                )
                responses = [
                    (
                        True,
                        [
                            {
                                "total_count": 1,
                                "incomplete_results": False,
                                "items": [search_item],
                            }
                        ],
                        "",
                    ),
                    (True, exact_item, ""),
                ]
                with mock.patch.object(
                    reconcile_state, "gh", side_effect=responses
                ):
                    matches, errors = reconcile_state.reconcile_bodies(
                        "owner/repo", "issue", self.marker
                    )
                self.assertEqual(matches, [])
                self.assertTrue(errors)

    def test_comment_reconciliation_requires_parent_bound_github_url(self):
        base = {
            "id": 99,
            "html_url": (
                "https://github.com/owner/repo/issues/10#issuecomment-99"
            ),
            "body": self.body,
        }
        invalid_comments = []
        for url in (
            "https://evil.test/owner/repo/issues/10#issuecomment-99",
            "http://github.com/owner/repo/issues/10#issuecomment-99",
            "https://github.com/owner/repo/issues/11#issuecomment-99",
            "https://github.com/owner/repo/issues/10#issuecomment-100",
        ):
            invalid_comments.append(dict(base, html_url=url))
        invalid_comments.append(dict(base, id=True))
        invalid_comments.append(
            dict(
                base,
                id=0,
                html_url=(
                    "https://github.com/owner/repo/issues/10#issuecomment-0"
                ),
            )
        )

        for comment in invalid_comments:
            with self.subTest(comment=comment), mock.patch.object(
                reconcile_state, "gh", return_value=(True, [[comment]], "")
            ):
                matches, errors = reconcile_state.reconcile_comments(
                    "owner/repo", 10, self.marker
                )
            self.assertEqual(matches, [])
            self.assertTrue(errors)
            self.assertEqual(
                reconcile_state.classify(matches, errors), "unknown"
            )

        pull_comment = dict(
            base,
            html_url=(
                "https://github.com/owner/repo/pull/10#issuecomment-99"
            ),
        )
        with mock.patch.object(
            reconcile_state, "gh", return_value=(True, [[pull_comment]], "")
        ):
            matches, errors = reconcile_state.reconcile_comments(
                "owner/repo", 10, self.marker
            )
        self.assertEqual(errors, [])
        self.assertEqual(matches[0]["comment_id"], 99)

        with mock.patch.object(
            reconcile_state, "gh", return_value=(True, [[base, base]], "")
        ):
            matches, errors = reconcile_state.reconcile_comments(
                "owner/repo", 10, self.marker
            )
        self.assertEqual(matches, [])
        self.assertTrue(errors)

    def test_branch_absence_requires_structured_not_found_status(self):
        expected_sha = "a" * 40
        with mock.patch.object(
            reconcile_state,
            "gh",
            return_value=(False, None, "404 rate limited"),
        ):
            matches, conflicts, errors = reconcile_state.reconcile_branch(
                "owner/repo", "agent/issue-21", expected_sha
            )
        self.assertEqual(matches, [])
        self.assertEqual(conflicts, [])
        self.assertTrue(errors)

        with mock.patch.object(
            reconcile_state,
            "gh",
            side_effect=(
                (
                    False,
                    {"message": "Not Found", "status": "404"},
                    "gh: Not Found (HTTP 404)",
                ),
                (
                    True,
                    self.repository_response(),
                    "",
                ),
                (
                    True,
                    self.branch_response("main", "c" * 40),
                    "",
                ),
                (
                    False,
                    {"message": "Not Found", "status": "404"},
                    "gh: Not Found (HTTP 404)",
                ),
            ),
        ):
            matches, conflicts, errors = reconcile_state.reconcile_branch(
                "owner/repo", "agent/issue-21", expected_sha
            )
        self.assertEqual(matches, [])
        self.assertEqual(conflicts, [])
        self.assertEqual(errors, [])

        with mock.patch.object(
            reconcile_state,
            "gh",
            side_effect=(
                (
                    False,
                    {"message": "Not Found", "status": "404"},
                    "gh: Not Found (HTTP 404)",
                ),
                (
                    True,
                    self.repository_response(),
                    "",
                ),
                (
                    False,
                    {"message": "Not Found", "status": "404"},
                    "gh: Not Found (HTTP 404)",
                ),
            ),
        ):
            matches, conflicts, errors = reconcile_state.reconcile_branch(
                "owner/repo", "agent/issue-21", expected_sha
            )
        self.assertEqual(matches, [])
        self.assertEqual(conflicts, [])
        self.assertTrue(errors)

    def test_branch_name_is_encoded_without_losing_ref_identity(self):
        cases = (
            ("agent/issue-21#review", "agent/issue-21%23review"),
            ("agent/issue-21%review", "agent/issue-21%25review"),
            ("agent/{owner}/review", "agent/%7Bowner%7D/review"),
        )
        for branch, encoded in cases:
            response = self.branch_response(branch, "a" * 40)
            with self.subTest(branch=branch), mock.patch.object(
                reconcile_state, "gh", return_value=(True, response, "")
            ) as gh_mock:
                matches, conflicts, errors = reconcile_state.reconcile_branch(
                    "owner/repo", branch, "a" * 40
                )

            self.assertEqual(errors, [])
            self.assertEqual(conflicts, [])
            self.assertEqual(len(matches), 1)
            self.assertEqual(
                gh_mock.call_args,
                mock.call(
                    [
                        "api",
                        f"repos/owner/repo/git/ref/heads/{encoded}",
                    ]
                ),
            )

    def test_branch_404_is_unknown_when_repository_identity_is_unproven(self):
        ref_not_found = (
            False,
            {"message": "Not Found", "status": "404"},
            "gh: Not Found (HTTP 404)",
        )
        repository_responses = (
            (False, {"status": "404"}, "gh: Not Found (HTTP 404)"),
            (
                True,
                {
                    "full_name": "other/repo",
                    "html_url": "https://github.com/other/repo",
                    "url": "https://api.github.com/repos/other/repo",
                    "default_branch": "main",
                },
                "",
            ),
        )
        for repository_response in repository_responses:
            with self.subTest(repository_response=repository_response), mock.patch.object(
                reconcile_state,
                "gh",
                side_effect=(ref_not_found, repository_response),
            ):
                matches, conflicts, errors = reconcile_state.reconcile_branch(
                    "owner/repo", "agent/issue-21", "a" * 40
                )
            self.assertEqual(matches, [])
            self.assertEqual(conflicts, [])
            self.assertTrue(errors)

    def test_pr_branch_reconciliation_checks_returned_identity(self):
        base = self.pr_list_item()
        invalid_items = (
            dict(base, url="https://evil.test/owner/repo/pull/20"),
            dict(base, url="https://github.com/other/repo/pull/20"),
            dict(base, url="https://github.com/owner/repo/pull/21"),
            dict(base, headRefName="agent/other"),
            dict(base, headRefOid="short"),
            dict(base, number=True),
            dict(base, state="BROKEN"),
            dict(base, state=[]),
            dict(base, headRepository={"nameWithOwner": "attacker/fork"}),
            dict(base, headRepositoryOwner={"login": "attacker"}),
            dict(base, isCrossRepository=True),
        )
        for item in invalid_items:
            with self.subTest(item=item), mock.patch.object(
                reconcile_state, "gh", return_value=(True, [item], "")
            ):
                matches, errors = reconcile_state.reconcile_pr_branch(
                    "owner/repo",
                    "agent/issue-21",
                    "a" * 40,
                    "development",
                    "b" * 40,
                )
            self.assertEqual(matches, [])
            self.assertTrue(errors)

        with mock.patch.object(
            reconcile_state,
            "gh",
            side_effect=(
                (True, [base], ""),
                (True, self.exact_pr_response(), ""),
            ),
        ):
            matches, errors = reconcile_state.reconcile_pr_branch(
                "owner/repo",
                "agent/issue-21",
                "a" * 40,
                "development",
                "b" * 40,
            )
        self.assertEqual(errors, [])
        self.assertEqual(matches[0]["number"], 20)

    def test_pr_branch_reconciliation_rejects_stale_or_wrong_base_identity(self):
        variants = (
            dict(self.pr_list_item(), headRefOid="c" * 40),
            dict(self.pr_list_item(), baseRefName="main"),
            dict(self.pr_list_item(), baseRefOid="d" * 40),
        )
        for item in variants:
            with self.subTest(item=item), mock.patch.object(
                reconcile_state, "gh", return_value=(True, [item], "")
            ):
                matches, errors = reconcile_state.reconcile_pr_branch(
                    "owner/repo",
                    "agent/issue-21",
                    "a" * 40,
                    "development",
                    "b" * 40,
                )
            self.assertEqual(matches, [])
            self.assertTrue(errors)

    def test_successful_branch_response_is_bound_to_repository_urls(self):
        response = self.branch_response("agent/issue-21", "a" * 40)
        variants = []
        wrong_ref_url = dict(response)
        wrong_ref_url["url"] = (
            "https://api.github.com/repos/other/repo/git/refs/heads/agent/issue-21"
        )
        variants.append(wrong_ref_url)
        wrong_object_url = dict(response)
        wrong_object_url["object"] = dict(response["object"])
        wrong_object_url["object"]["url"] = (
            "https://api.github.com/repos/other/repo/git/commits/" + "a" * 40
        )
        variants.append(wrong_object_url)

        for candidate in variants:
            with self.subTest(candidate=candidate), mock.patch.object(
                reconcile_state, "gh", return_value=(True, candidate, "")
            ):
                matches, conflicts, errors = reconcile_state.reconcile_branch(
                    "owner/repo", "agent/issue-21", "a" * 40
                )
            self.assertEqual(matches, [])
            self.assertEqual(conflicts, [])
            self.assertTrue(errors)

    def test_branch_response_requires_an_object_mapping(self):
        with mock.patch.object(
            reconcile_state,
            "gh",
            return_value=(
                True,
                {
                    "ref": "refs/heads/agent/issue-21",
                    "object": [],
                },
                "",
            ),
        ):
            matches, conflicts, errors = reconcile_state.reconcile_branch(
                "owner/repo", "agent/issue-21", "a" * 40
            )
        self.assertEqual(matches, [])
        self.assertEqual(conflicts, [])
        self.assertTrue(errors)

    def test_configured_github_enterprise_urls_are_supported(self):
        issue = self.issue_response()
        issue["html_url"] = "https://github.example.test/owner/repo/issues/10"
        issue["repository_url"] = (
            "https://github.example.test/api/v3/repos/owner/repo"
        )
        with mock.patch.dict(
            reconcile_state.os.environ,
            {"GH_HOST": "github.example.test"},
            clear=False,
        ):
            result = reconcile_state.verify_write_response(
                "issue", issue, **self.verify_arguments("issue")
            )
        self.assertEqual(result["classification"], "verified")

    def test_configured_enterprise_cloud_urls_are_supported(self):
        issue = self.issue_response()
        issue["html_url"] = "https://tenant.ghe.com/owner/repo/issues/10"
        issue["repository_url"] = (
            "https://api.tenant.ghe.com/repos/owner/repo"
        )
        with mock.patch.dict(
            reconcile_state.os.environ,
            {"GH_HOST": "tenant.ghe.com"},
            clear=False,
        ):
            result = reconcile_state.verify_write_response(
                "issue", issue, **self.verify_arguments("issue")
            )
        self.assertEqual(result["classification"], "verified")

    def test_configured_enterprise_branch_urls_are_supported(self):
        cases = (
            (
                "github.example.test",
                "github.example.test",
                "/api/v3",
            ),
            ("tenant.ghe.com", "api.tenant.ghe.com", ""),
        )
        for host, api_host, api_prefix in cases:
            response = self.branch_response(
                "agent/issue-21",
                "a" * 40,
                api_host=api_host,
                api_prefix=api_prefix,
            )
            with self.subTest(host=host), mock.patch.dict(
                reconcile_state.os.environ,
                {"GH_HOST": host},
                clear=False,
            ), mock.patch.object(
                reconcile_state, "gh", return_value=(True, response, "")
            ):
                matches, conflicts, errors = reconcile_state.reconcile_branch(
                    "owner/repo", "agent/issue-21", "a" * 40
                )
            self.assertEqual(errors, [])
            self.assertEqual(conflicts, [])
            self.assertEqual(len(matches), 1)

    @mock.patch.object(reconcile_state.subprocess, "run")
    def test_gh_extracts_status_from_json_error_body(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=(
                '{"message":"Not Found","documentation_url":'
                '"https://docs.github.com/rest/git/refs#get-a-reference",'
                '"status":"404"}'
            ),
            stderr="gh: Not Found (HTTP 404)\n",
        )
        ok, data, error = reconcile_state.gh(
            ["api", "repos/owner/repo/git/ref/heads/missing"]
        )
        self.assertFalse(ok)
        self.assertEqual(data["status"], "404")
        self.assertEqual(error, "gh: Not Found (HTTP 404)")


if __name__ == "__main__":
    unittest.main()
