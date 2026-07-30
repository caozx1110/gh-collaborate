#!/usr/bin/env python3
"""Read GitHub state after an ambiguous Issue, comment, PR, or branch operation."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from typing import Any


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


def reconcile_comments(repo: str, number: int, marker: str) -> tuple[list[dict[str, Any]], list[str]]:
    ok, data, error = gh([
        "api", "--paginate", "--slurp", "-X", "GET",
        f"repos/{repo}/issues/{number}/comments", "-f", "per_page=100",
    ])
    if not ok:
        return [], [error]
    pages = data if isinstance(data, list) else []
    comments = [comment for page in pages if isinstance(page, list) for comment in page]
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
    pages = data if isinstance(data, list) else []
    items = [item for page in pages if isinstance(page, dict) for item in page.get("items", [])]
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
    return [{"kind": "pr", **item} for item in data], []


def reconcile_branch(
    repo: str, branch: str, expected_sha: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    ok, data, error = gh(["api", f"repos/{repo}/git/ref/heads/{branch}"])
    if not ok:
        if "404" in error:
            return [], [], []
        return [], [], [error]
    actual_sha = data.get("object", {}).get("sha") if isinstance(data, dict) else None
    if not isinstance(actual_sha, str) or not FULL_SHA.fullmatch(actual_sha):
        return [], [], ["GitHub branch response did not contain a full object.sha"]
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
    return 2 if result["classification"] == "unknown" else 0


if __name__ == "__main__":
    raise SystemExit(main())
