#!/usr/bin/env python3
"""Read GitHub state after an ambiguous Issue, PR, or branch operation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from typing import Any


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


def classify(items: list[Any], errors: list[str]) -> str:
    if errors:
        return "unknown"
    if not items:
        return "absent"
    if len(items) == 1:
        return "present"
    return "conflict"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="canonical owner/repo")
    parser.add_argument("--kind", choices=("issue", "pr", "branch"), required=True)
    parser.add_argument("--marker", help="unique operation marker")
    parser.add_argument("--branch", help="head branch to search")
    args = parser.parse_args()
    if args.kind in ("issue", "pr") and not args.marker and not args.branch:
        parser.error("issue/pr reconciliation requires --marker or --branch")
    if args.kind == "issue" and not args.marker:
        parser.error("issue reconciliation requires --marker")
    if args.kind == "branch" and not args.branch:
        parser.error("branch reconciliation requires --branch")

    matches: list[dict[str, Any]] = []
    errors: list[str] = []
    if args.marker and args.kind in ("issue", "pr"):
        query = f'\"{args.marker}\" in:body'
        ok, data, error = gh(["api", "-X", "GET", "search/issues", "-f", f"q=repo:{args.repo} {query}"])
        if ok:
            for item in data.get("items", []):
                item_kind = "pr" if "pull_request" in item else "issue"
                if item_kind == args.kind:
                    matches.append({"kind": item_kind, "number": item["number"], "url": item["html_url"]})
        else:
            errors.append(error)
    if args.branch and args.kind == "pr":
        ok, data, error = gh(["pr", "list", "--repo", args.repo, "--state", "all", "--head", args.branch, "--json", "number,state,url,headRefName,headRefOid"])
        if ok:
            matches.extend({"kind": "pr", **item} for item in data)
        else:
            errors.append(error)
    if args.branch and args.kind == "branch":
        ok, data, error = gh(["api", f"repos/{args.repo}/git/ref/heads/{args.branch}"])
        if ok and data:
            matches.append({"kind": "branch", "ref": data.get("ref"), "sha": data.get("object", {}).get("sha")})
        elif error and "404" not in error:
            errors.append(error)

    unique = {
        (item["kind"], str(item.get("number", item.get("ref", "")))): item
        for item in matches
    }
    result = {"classification": classify(list(unique.values()), errors), "matches": list(unique.values()), "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["classification"] != "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
