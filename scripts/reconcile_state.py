#!/usr/bin/env python3
"""Verify complete GitHub write objects or read state after ambiguous operations."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from typing import Any
from urllib.parse import urlparse


FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")
MARKER_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}")
MARKER_COMMENT = re.compile(
    r"(?m)^[ \t]*<!--[ \t]*operation-marker:[ \t]*([^\r\n<>]+?)[ \t]*-->[ \t]*$"
)


def gh(arguments: list[str]) -> tuple[bool, Any, str]:
    environment = os.environ.copy()
    environment.update({"GH_PAGER": "cat", "NO_COLOR": "1"})
    process = subprocess.run(["gh", *arguments], env=environment, text=True, capture_output=True, check=False)
    if process.returncode:
        return False, None, process.stderr.strip()
    try:
        return True, json.loads(process.stdout or "null"), ""
    except json.JSONDecodeError:
        return False, None, "GitHub response was not JSON"


def has_exact_marker(body: str | None, marker: str) -> bool:
    return marker in MARKER_COMMENT.findall(body or "")


def marker_count(body: str | None, marker: str) -> int:
    return MARKER_COMMENT.findall(body or "").count(marker)


def _nested(value: Any, *path: str) -> tuple[bool, Any]:
    current = value
    for name in path:
        if not isinstance(current, dict) or name not in current:
            return False, None
        current = current[name]
    return True, current


def _url_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlparse(value)
    return parsed.path.rstrip("/") if parsed.scheme and parsed.netloc else None


def verify_write_response(
    kind: str,
    response: Any,
    *,
    repo: str,
    actor: str,
    author: str | None = None,
    marker: str,
    body: str,
    number: int | None = None,
    parent_number: int | None = None,
    head_ref: str | None = None,
    head_sha: str | None = None,
    base_ref: str | None = None,
    base_sha: str | None = None,
) -> dict[str, Any]:
    """Classify whether a successful Issue/comment/PR object is sufficient."""
    if kind not in {"issue", "comment", "pr"}:
        raise ValueError("kind must be issue, comment, or pr")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
        raise ValueError("repo must be canonical owner/repo")
    if not actor or (author is not None and not author) or not MARKER_VALUE.fullmatch(marker):
        raise ValueError("actor, author, and marker must be valid")
    if marker_count(body, marker) != 1:
        raise ValueError("expected body must contain one exact standalone marker")
    if kind == "comment" and (parent_number is None or parent_number < 1):
        raise ValueError("comment verification requires a positive parent_number")
    if number is not None and number < 1:
        raise ValueError("number must be positive")
    if kind == "pr":
        pr_inputs = (head_ref, head_sha, base_ref, base_sha)
        if any(value is None for value in pr_inputs):
            raise ValueError("PR verification requires head/base refs and full SHAs")
        if not FULL_SHA.fullmatch(head_sha or "") or not FULL_SHA.fullmatch(base_sha or ""):
            raise ValueError("PR head/base SHAs must be full hexadecimal SHAs")

    missing: list[str] = []
    conflicts: list[dict[str, Any]] = []

    def expect(path: tuple[str, ...], expected: Any, *, folded: bool = False) -> Any:
        present, actual = _nested(response, *path)
        label = ".".join(path)
        if not present:
            missing.append(label)
            return None
        left, right = actual, expected
        if folded and isinstance(left, str) and isinstance(right, str):
            left, right = left.lower(), right.lower()
        if left != right:
            conflicts.append({"field": label, "expected": expected, "actual": actual})
        return actual

    if not isinstance(response, dict):
        missing.append("structured-object")
    response_body = expect(("body",), body) if isinstance(response, dict) else None
    response_author = (
        expect(("user", "login"), author or actor, folded=True)
        if isinstance(response, dict)
        else None
    )

    identifier_name = "id" if kind == "comment" else "number"
    present, identifier = _nested(response, identifier_name)
    if not present:
        missing.append(identifier_name)
        identifier = None
    elif not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1:
        conflicts.append({"field": identifier_name, "expected": "positive integer", "actual": identifier})
    if number is not None and present and identifier != number:
        conflicts.append({"field": identifier_name, "expected": number, "actual": identifier})

    html_present, html_url = _nested(response, "html_url")
    html_path = _url_path(html_url) if html_present else None
    if not html_present or html_path is None:
        missing.append("html_url")

    repo_path = f"/{repo}"
    if kind == "issue":
        present, repository_url = _nested(response, "repository_url")
        if not present:
            missing.append("repository_url")
        elif (_url_path(repository_url) or "").lower() != f"/repos/{repo}".lower():
            conflicts.append({"field": "repository_url", "expected": repo, "actual": repository_url})
        if isinstance(response, dict) and "pull_request" in response:
            conflicts.append({"field": "object-type", "expected": "issue", "actual": "pr"})
        if html_path and identifier and html_path.lower() != f"{repo_path}/issues/{identifier}".lower():
            conflicts.append({"field": "html_url", "expected": f"{repo_path}/issues/{identifier}", "actual": html_url})
    elif kind == "comment":
        present, issue_url = _nested(response, "issue_url")
        expected_parent = f"/repos/{repo}/issues/{parent_number}"
        if not present:
            missing.append("issue_url")
        elif (_url_path(issue_url) or "").lower() != expected_parent.lower():
            conflicts.append({"field": "issue_url", "expected": expected_parent, "actual": issue_url})
        if html_path and not html_path.lower().startswith(f"{repo_path}/".lower()):
            conflicts.append({"field": "html_url", "expected": repo_path, "actual": html_url})
    else:
        expect(("base", "repo", "full_name"), repo, folded=True)
        expect(("head", "ref"), head_ref)
        expect(("head", "sha"), head_sha, folded=True)
        expect(("base", "ref"), base_ref)
        expect(("base", "sha"), base_sha, folded=True)
        if html_path and identifier and html_path.lower() != f"{repo_path}/pull/{identifier}".lower():
            conflicts.append({"field": "html_url", "expected": f"{repo_path}/pull/{identifier}", "actual": html_url})

    if isinstance(response_body, str) and marker_count(response_body, marker) != 1:
        conflicts.append({"field": "operation-marker", "expected": "one exact marker", "actual": marker_count(response_body, marker)})
    classification = "conflict" if conflicts else "readback-required" if missing else "verified"
    return {
        "classification": classification,
        "identity": {
            "kind": kind,
            identifier_name: identifier,
            "actor": actor,
            "author": response_author,
            "url": html_url if html_present else None,
        },
        "missing": sorted(set(missing)),
        "conflicts": conflicts,
    }


def classify(items: list[Any], errors: list[str], conflicts: list[Any] | None = None) -> str:
    if errors:
        return "unknown"
    if conflicts:
        return "conflict"
    if not items:
        return "absent"
    if len(items) == 1:
        return "present"
    return "conflict"


def exit_code(classification: str) -> int:
    return {"unknown": 2, "conflict": 3}.get(classification, 0)


def reconcile_comments(repo: str, number: int, marker: str) -> tuple[list[dict[str, Any]], list[str]]:
    ok, data, error = gh([
        "api", "--paginate", "--slurp", "-X", "GET",
        f"repos/{repo}/issues/{number}/comments", "-f", "per_page=100",
    ])
    if not ok:
        return [], [error]
    if (
        not isinstance(data, list)
        or any(not isinstance(page, list) for page in data)
        or any(not isinstance(comment, dict) for page in data for comment in page)
    ):
        return [], ["GitHub comments response was not a paginated array"]
    comments = [comment for page in data for comment in page]
    if any(
        not isinstance(comment.get("id"), int)
        or not isinstance(comment.get("html_url"), str)
        or (comment.get("body") is not None and not isinstance(comment.get("body"), str))
        for comment in comments
    ):
        return [], ["GitHub comments response omitted required identity fields"]
    duplicate_ids = [comment.get("id") for comment in comments if marker_count(comment.get("body"), marker) > 1]
    if duplicate_ids:
        return [], [f"duplicate operation marker in comments: {duplicate_ids}"]
    return [
        {
            "kind": "comment",
            "number": number,
            "comment_id": comment["id"],
            "url": comment["html_url"],
        }
        for comment in comments
        if has_exact_marker(comment.get("body"), marker)
    ], []


def reconcile_bodies(repo: str, kind: str, marker: str) -> tuple[list[dict[str, Any]], list[str]]:
    query = f'repo:{repo} "{marker}" in:body'
    ok, data, error = gh([
        "api", "-X", "GET", "--paginate", "--slurp", "search/issues",
        "-f", f"q={query}", "-f", "per_page=100",
    ])
    if not ok:
        return [], [error]
    if (
        not isinstance(data, list)
        or any(not isinstance(page, dict) or not isinstance(page.get("items"), list) for page in data)
        or any(
            not isinstance(item, dict)
            for page in data
            if isinstance(page, dict) and isinstance(page.get("items"), list)
            for item in page["items"]
        )
    ):
        return [], ["GitHub search response was not a paginated result"]
    items = [item for page in data for item in page["items"]]
    if any(
        not isinstance(item.get("number"), int)
        or not isinstance(item.get("html_url"), str)
        or (item.get("body") is not None and not isinstance(item.get("body"), str))
        for item in items
    ):
        return [], ["GitHub search response omitted required identity fields"]
    duplicate_numbers = [item.get("number") for item in items if marker_count(item.get("body"), marker) > 1]
    if duplicate_numbers:
        return [], [f"duplicate operation marker in bodies: {duplicate_numbers}"]
    matches = []
    for item in items:
        item_kind = "pr" if "pull_request" in item else "issue"
        if item_kind == kind and has_exact_marker(item.get("body"), marker):
            matches.append({"kind": item_kind, "number": item["number"], "url": item["html_url"]})
    return matches, []


def reconcile_pr_branch(repo: str, branch: str) -> tuple[list[dict[str, Any]], list[str]]:
    ok, data, error = gh([
        "pr", "list", "--repo", repo, "--state", "all", "--head", branch,
        "--json", "number,state,url,headRefName,headRefOid",
    ])
    if not ok:
        return [], [error]
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        return [], ["GitHub PR response was not an array"]
    required = {"number", "state", "url", "headRefName", "headRefOid"}
    if any(not required.issubset(item) for item in data):
        return [], ["GitHub PR response omitted required identity fields"]
    return [{"kind": "pr", **item} for item in data], []


def reconcile_branch(
    repo: str, branch: str, expected_sha: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if not FULL_SHA.fullmatch(expected_sha):
        return [], [], ["expected SHA was not a full hexadecimal SHA"]
    ok, data, error = gh(["api", f"repos/{repo}/git/ref/heads/{branch}"])
    if not ok:
        if "404" in error:
            return [], [], []
        return [], [], [error]
    actual_sha = data.get("object", {}).get("sha") if isinstance(data, dict) else None
    if not isinstance(actual_sha, str) or not FULL_SHA.fullmatch(actual_sha):
        return [], [], ["GitHub branch response did not contain a full object.sha"]
    expected_ref = f"refs/heads/{branch}"
    actual_ref = data.get("ref") if isinstance(data, dict) else None
    if actual_ref != expected_ref:
        return [], [], ["GitHub branch response did not match the requested ref"]
    result = {
        "kind": "branch",
        "ref": data.get("ref") if isinstance(data, dict) else None,
        "expected_sha": expected_sha.lower(),
        "actual_sha": actual_sha.lower(),
    }
    if isinstance(actual_sha, str) and actual_sha.lower() == expected_sha.lower():
        return [result], [], []
    result["reason"] = "sha-mismatch"
    return [], [result], []


def item_identity(item: dict[str, Any]) -> tuple[str, str]:
    identifier = item.get("comment_id", item.get("number", item.get("ref", "")))
    return item["kind"], str(identifier)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="canonical owner/repo")
    parser.add_argument("--kind", choices=("issue", "comment", "pr", "branch"), required=True)
    parser.add_argument("--marker", help="exact operation marker value")
    parser.add_argument("--number", type=int, help="parent Issue/PR number for comment reconciliation")
    parser.add_argument("--branch", help="head branch to search")
    parser.add_argument("--expected-sha", help="expected full SHA for branch reconciliation")
    args = parser.parse_args()

    if args.marker and not MARKER_VALUE.fullmatch(args.marker):
        parser.error("--marker must contain only letters, digits, dots, colons, underscores, and hyphens")
    if args.number is not None and args.number < 1:
        parser.error("--number must be positive")
    if args.kind == "comment" and (args.number is None or not args.marker):
        parser.error("comment reconciliation requires --number and --marker")
    if args.kind != "comment" and args.number is not None:
        parser.error("--number is only valid with --kind comment")
    if args.kind == "issue" and not args.marker:
        parser.error("issue reconciliation requires --marker")
    if args.kind == "pr" and not args.marker and not args.branch:
        parser.error("PR reconciliation requires --marker or --branch")
    if args.kind == "branch":
        if not args.branch or not args.expected_sha:
            parser.error("branch reconciliation requires --branch and --expected-sha")
        if not FULL_SHA.fullmatch(args.expected_sha):
            parser.error("--expected-sha must be a 40-character hexadecimal SHA")
    elif args.expected_sha:
        parser.error("--expected-sha is only valid with --kind branch")

    matches: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    errors: list[str] = []
    if args.kind == "comment":
        found, failures = reconcile_comments(args.repo, args.number, args.marker)
        matches.extend(found)
        errors.extend(failures)
    if args.marker and args.kind in ("issue", "pr"):
        found, failures = reconcile_bodies(args.repo, args.kind, args.marker)
        matches.extend(found)
        errors.extend(failures)
    if args.branch and args.kind == "pr":
        found, failures = reconcile_pr_branch(args.repo, args.branch)
        matches.extend(found)
        errors.extend(failures)
    if args.kind == "branch":
        found, mismatches, failures = reconcile_branch(args.repo, args.branch, args.expected_sha)
        matches.extend(found)
        conflicts.extend(mismatches)
        errors.extend(failures)

    unique = {item_identity(item): item for item in matches}
    result = {
        "classification": classify(list(unique.values()), errors, conflicts),
        "matches": list(unique.values()),
        "conflicts": conflicts,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code(result["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
