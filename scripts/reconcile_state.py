#!/usr/bin/env python3
"""Verify complete GitHub write objects or read state after ambiguous operations."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from typing import Any
from urllib.parse import quote, urlparse


FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")
REPO_SLUG = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
MARKER_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}")
MARKER_COMMENT = re.compile(
    r"(?m)^[ \t]*<!--[ \t]*operation-marker:[ \t]*([^\r\n<>]+?)[ \t]*-->[ \t]*$"
)


def gh(arguments: list[str]) -> tuple[bool, Any, str]:
    environment = os.environ.copy()
    environment.update({"GH_PAGER": "cat", "NO_COLOR": "1"})
    process = subprocess.run(["gh", *arguments], env=environment, text=True, capture_output=True, check=False)
    if process.returncode:
        try:
            error_data = json.loads(process.stdout) if process.stdout else None
        except json.JSONDecodeError:
            error_data = None
        return False, error_data, process.stderr.strip()
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


def _url_identity(value: Any, host: str) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value:
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or parsed.netloc.lower() != host.lower()
        or parsed.params
        or parsed.query
    ):
        return None
    return parsed.path.rstrip("/"), parsed.fragment


def _url_path(value: Any, host: str) -> str | None:
    identity = _url_identity(value, host)
    return identity[0] if identity is not None and not identity[1] else None


def _github_url_config() -> tuple[str, str, str] | None:
    """Return the configured web host, API host, and API path prefix."""

    host = os.environ.get("GH_HOST", "github.com").strip().lower()
    if not host:
        return None
    try:
        parsed = urlparse(f"https://{host}")
    except ValueError:
        return None
    if (
        parsed.netloc.lower() != host
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    if host == "github.com":
        return host, "api.github.com", ""
    if host.endswith(".ghe.com") and not host.startswith("api."):
        return host, f"api.{host}", ""
    return host, host, "/api/v3"


def _github_paths(repo: str) -> tuple[str, str, str] | None:
    if (
        not isinstance(repo, str)
        or not REPO_SLUG.fullmatch(repo)
        or any(part in {".", ".."} for part in repo.split("/"))
    ):
        return None
    config = _github_url_config()
    if config is None:
        return None
    web_host, api_host, api_prefix = config
    return web_host, api_host, f"{api_prefix}/repos/{repo}"


def _error_status(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    if isinstance(status, bool):
        return None
    if isinstance(status, int) and 100 <= status <= 599:
        return status
    if isinstance(status, str) and re.fullmatch(r"[1-5][0-9]{2}", status):
        return int(status)
    return None


def _repository_default_branch(
    data: Any,
    *,
    repo: str,
    web_host: str,
    api_host: str,
    api_repo_path: str,
) -> tuple[str | None, str | None]:
    """Validate repository identity and return its recorded default branch."""

    if not isinstance(data, dict):
        return None, "GitHub repository response was not an object"
    full_name = data.get("full_name")
    html_url = data.get("html_url")
    api_url = data.get("url")
    default_branch = data.get("default_branch")
    if (
        not isinstance(full_name, str)
        or full_name.lower() != repo.lower()
        or (_url_path(html_url, web_host) or "").lower() != f"/{repo}".lower()
        or (_url_path(api_url, api_host) or "").lower() != api_repo_path.lower()
        or not isinstance(default_branch, str)
        or not default_branch
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in default_branch)
    ):
        return (
            None,
            "GitHub repository response did not match the requested repository identity",
        )
    return default_branch, None


def _branch_response_sha(
    data: Any,
    *,
    repo: str,
    branch: str,
    api_host: str,
    api_repo_path: str,
) -> tuple[str | None, str | None]:
    """Validate a Git ref response against its repository and branch identity."""

    if not isinstance(data, dict):
        return None, "GitHub branch response was not an object"
    expected_ref = f"refs/heads/{branch}"
    encoded_branch = quote(branch, safe="/")
    expected_ref_path = f"{api_repo_path}/git/refs/heads/{encoded_branch}"
    actual_ref = data.get("ref")
    ref_url = data.get("url")
    object_data = data.get("object")
    if not isinstance(object_data, dict):
        return None, "GitHub branch response did not contain an object mapping"
    actual_sha = object_data.get("sha")
    object_type = object_data.get("type")
    object_url = object_data.get("url")
    expected_object_path = (
        f"{api_repo_path}/git/commits/{actual_sha}"
        if isinstance(actual_sha, str)
        else ""
    )
    if (
        actual_ref != expected_ref
        or not isinstance(actual_sha, str)
        or not FULL_SHA.fullmatch(actual_sha)
        or object_type != "commit"
        or (_url_path(ref_url, api_host) or "").lower()
        != expected_ref_path.lower()
        or (_url_path(object_url, api_host) or "").lower()
        != expected_object_path.lower()
    ):
        return None, "GitHub branch response did not match the requested ref identity"
    return actual_sha, None


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
    if not REPO_SLUG.fullmatch(repo) or any(
        part in {".", ".."} for part in repo.split("/")
    ):
        raise ValueError("repo must be canonical owner/repo")
    if not actor or (author is not None and not author) or not MARKER_VALUE.fullmatch(marker):
        raise ValueError("actor, author, and marker must be valid")
    if marker_count(body, marker) != 1:
        raise ValueError("expected body must contain one exact standalone marker")
    github_paths = _github_paths(repo)
    if github_paths is None:
        raise ValueError("GH_HOST must be a canonical GitHub hostname")
    web_host, api_host, api_repo_path = github_paths
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
    html_identity = _url_identity(html_url, web_host) if html_present else None
    html_path = html_identity[0] if html_identity is not None else None
    if not html_present or html_path is None:
        if not html_present:
            missing.append("html_url")
        else:
            conflicts.append({"field": "html_url", "expected": "canonical GitHub URL", "actual": html_url})

    repo_path = f"/{repo}"
    if kind == "issue":
        present, repository_url = _nested(response, "repository_url")
        if not present:
            missing.append("repository_url")
        elif (_url_path(repository_url, api_host) or "").lower() != api_repo_path.lower():
            conflicts.append({"field": "repository_url", "expected": repo, "actual": repository_url})
        if isinstance(response, dict) and "pull_request" in response:
            conflicts.append({"field": "object-type", "expected": "issue", "actual": "pr"})
        if (
            html_identity is not None
            and identifier
            and (
                html_path.lower() != f"{repo_path}/issues/{identifier}".lower()
                or html_identity[1]
            )
        ):
            conflicts.append({"field": "html_url", "expected": f"{repo_path}/issues/{identifier}", "actual": html_url})
    elif kind == "comment":
        present, issue_url = _nested(response, "issue_url")
        expected_parent = f"{api_repo_path}/issues/{parent_number}"
        if not present:
            missing.append("issue_url")
        elif (_url_path(issue_url, api_host) or "").lower() != expected_parent.lower():
            conflicts.append({"field": "issue_url", "expected": expected_parent, "actual": issue_url})
        if html_identity is not None and isinstance(identifier, int):
            expected_paths = {
                f"{repo_path}/issues/{parent_number}".lower(),
                f"{repo_path}/pull/{parent_number}".lower(),
            }
            expected_fragment = f"issuecomment-{identifier}"
            if (
                html_path.lower() not in expected_paths
                or html_identity[1] != expected_fragment
            ):
                conflicts.append(
                    {
                        "field": "html_url",
                        "expected": (
                            f"{repo_path}/issues-or-pull/{parent_number}"
                            f"#{expected_fragment}"
                        ),
                        "actual": html_url,
                    }
                )
    else:
        expect(("base", "repo", "full_name"), repo, folded=True)
        expect(("head", "ref"), head_ref)
        expect(("head", "sha"), head_sha, folded=True)
        expect(("base", "ref"), base_ref)
        expect(("base", "sha"), base_sha, folded=True)
        if (
            html_identity is not None
            and identifier
            and (
                html_path.lower() != f"{repo_path}/pull/{identifier}".lower()
                or html_identity[1]
            )
        ):
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
    github_paths = _github_paths(repo)
    if github_paths is None:
        return [], ["GH_HOST was not a canonical GitHub hostname"]
    web_host, _, _ = github_paths
    ok, data, error = gh([
        "api", "--paginate", "--slurp", "-X", "GET",
        f"repos/{repo}/issues/{number}/comments", "-f", "per_page=100",
    ])
    if not ok:
        return [], [error]
    if (
        not isinstance(data, list)
        or not data
        or any(not isinstance(page, list) for page in data)
        or any(not isinstance(comment, dict) for page in data for comment in page)
    ):
        return [], ["GitHub comments response was not a paginated array"]
    comments = [comment for page in data for comment in page]
    if any(
        not isinstance(comment.get("id"), int)
        or isinstance(comment.get("id"), bool)
        or comment["id"] < 1
        or not isinstance(comment.get("html_url"), str)
        or not isinstance(comment.get("body"), str)
        for comment in comments
    ):
        return [], ["GitHub comments response omitted required identity fields"]
    comment_ids = [comment["id"] for comment in comments]
    if len(set(comment_ids)) != len(comment_ids):
        return [], ["GitHub comments response contained duplicate identities"]
    repo_path = f"/{repo}"
    for comment in comments:
        identity = _url_identity(comment["html_url"], web_host)
        expected_paths = {
            f"{repo_path}/issues/{number}".lower(),
            f"{repo_path}/pull/{number}".lower(),
        }
        if (
            identity is None
            or identity[0].lower() not in expected_paths
            or identity[1] != f"issuecomment-{comment['id']}"
        ):
            return [], ["GitHub comment URL did not match its parent and comment identity"]
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


def reconcile_bodies(
    repo: str,
    kind: str,
    marker: str,
    *,
    head_ref: str | None = None,
    head_sha: str | None = None,
    base_ref: str | None = None,
    base_sha: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if kind == "pr" and (
        not head_ref
        or not isinstance(head_sha, str)
        or not FULL_SHA.fullmatch(head_sha)
        or not base_ref
        or not isinstance(base_sha, str)
        or not FULL_SHA.fullmatch(base_sha)
    ):
        return [], ["PR body reconciliation requires exact head/base refs and full SHAs"]
    github_paths = _github_paths(repo)
    if github_paths is None:
        return [], ["GH_HOST was not a canonical GitHub hostname"]
    web_host, _, _ = github_paths
    query = f'repo:{repo} "{marker}" in:body'
    ok, data, error = gh([
        "api", "-X", "GET", "--paginate", "--slurp", "search/issues",
        "-f", f"q={query}", "-f", "per_page=100",
    ])
    if not ok:
        return [], [error]
    if (
        not isinstance(data, list)
        or any(
            not isinstance(page, dict)
            or not isinstance(page.get("items"), list)
            or not isinstance(page.get("incomplete_results"), bool)
            or not isinstance(page.get("total_count"), int)
            or isinstance(page.get("total_count"), bool)
            or page["total_count"] < 0
            for page in data
        )
        or any(
            not isinstance(item, dict)
            for page in data
            if isinstance(page, dict) and isinstance(page.get("items"), list)
            for item in page["items"]
        )
    ):
        return [], ["GitHub search response was not a paginated result"]
    if any(page["incomplete_results"] for page in data):
        return [], ["GitHub search response was incomplete"]
    items = [item for page in data for item in page["items"]]
    total_counts = {page["total_count"] for page in data}
    if len(total_counts) != 1 or total_counts != {len(items)}:
        return [], ["GitHub search response did not include every reported result"]
    if not items:
        return [], ["GitHub search returned no authoritative candidates"]
    if any(
        not isinstance(item.get("number"), int)
        or isinstance(item.get("number"), bool)
        or item["number"] < 1
        or not isinstance(item.get("html_url"), str)
        or not isinstance(item.get("body"), str)
        for item in items
    ):
        return [], ["GitHub search response omitted required identity fields"]
    numbers = [item["number"] for item in items]
    if len(set(numbers)) != len(numbers):
        return [], ["GitHub search response contained duplicate object identities"]
    duplicate_numbers = [item.get("number") for item in items if marker_count(item.get("body"), marker) > 1]
    if duplicate_numbers:
        return [], [f"duplicate operation marker in bodies: {duplicate_numbers}"]
    candidates = []
    for item in items:
        item_kind = "pr" if "pull_request" in item else "issue"
        if item_kind == kind and has_exact_marker(item.get("body"), marker):
            candidates.append(item)
    if not candidates:
        return [], ["GitHub search returned no authoritative candidates"]

    matches = []
    endpoint_kind = "pulls" if kind == "pr" else "issues"
    for candidate in candidates:
        number = candidate["number"]
        ok, exact, error = gh(
            ["api", "-X", "GET", f"repos/{repo}/{endpoint_kind}/{number}"]
        )
        if not ok:
            return [], [error or "GitHub exact-object read failed"]
        if not isinstance(exact, dict):
            return [], ["GitHub exact-object response was not an object"]
        exact_kind = "pr" if "pull_request" in exact or endpoint_kind == "pulls" else "issue"
        exact_number = exact.get("number")
        exact_body = exact.get("body")
        exact_url = exact.get("html_url")
        expected_path = f"/{repo}/{'pull' if kind == 'pr' else 'issues'}/{number}"
        if (
            exact_kind != kind
            or exact_number != number
            or not isinstance(exact_number, int)
            or isinstance(exact_number, bool)
            or exact_number < 1
            or not isinstance(exact_url, str)
            or (_url_path(exact_url, web_host) or "").lower()
            != expected_path.lower()
            or not isinstance(exact_body, str)
        ):
            return [], ["GitHub exact-object response did not match the candidate identity"]
        if marker_count(exact_body, marker) > 1:
            return [], [f"duplicate operation marker in bodies: [{number}]"]
        if not has_exact_marker(exact_body, marker):
            return [], ["GitHub exact-object response did not contain the operation marker"]
        if kind == "pr":
            exact_head = exact.get("head")
            exact_base = exact.get("base")
            if (
                not isinstance(exact_head, dict)
                or not isinstance(exact_base, dict)
                or exact_head.get("ref") != head_ref
                or not isinstance(exact_head.get("sha"), str)
                or exact_head["sha"].lower() != (head_sha or "").lower()
                or not isinstance(exact_head.get("repo"), dict)
                or not isinstance(exact_head["repo"].get("full_name"), str)
                or exact_head["repo"]["full_name"].lower() != repo.lower()
                or exact_base.get("ref") != base_ref
                or not isinstance(exact_base.get("sha"), str)
                or exact_base["sha"].lower() != (base_sha or "").lower()
                or not isinstance(exact_base.get("repo"), dict)
                or not isinstance(exact_base["repo"].get("full_name"), str)
                or exact_base["repo"]["full_name"].lower() != repo.lower()
            ):
                return [], ["GitHub exact PR response did not match the requested identity"]
        matches.append(
            {"kind": kind, "number": exact_number, "url": exact_url}
        )
    return matches, []


def reconcile_pr_branch(
    repo: str,
    branch: str,
    head_sha: str,
    base_ref: str,
    base_sha: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if (
        not FULL_SHA.fullmatch(head_sha)
        or not base_ref
        or not FULL_SHA.fullmatch(base_sha)
    ):
        return [], ["PR reconciliation requires exact head/base refs and full SHAs"]
    github_paths = _github_paths(repo)
    if github_paths is None:
        return [], ["GH_HOST was not a canonical GitHub hostname"]
    web_host, _, _ = github_paths
    ok, data, error = gh([
        "pr", "list", "--repo", repo, "--state", "all", "--head", branch,
        "--json",
        (
            "number,state,url,headRefName,headRefOid,baseRefName,baseRefOid,"
            "headRepository,headRepositoryOwner,isCrossRepository"
        ),
    ])
    if not ok:
        return [], [error]
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        return [], ["GitHub PR response was not an array"]
    required = {
        "number", "state", "url", "headRefName", "headRefOid",
        "baseRefName", "baseRefOid", "headRepository", "headRepositoryOwner",
        "isCrossRepository",
    }
    if any(not required.issubset(item) for item in data):
        return [], ["GitHub PR response omitted required identity fields"]
    candidates: list[dict[str, Any]] = []
    for item in data:
        number = item["number"]
        head_repository = item["headRepository"]
        head_owner = item["headRepositoryOwner"]
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 1
            or not isinstance(item["state"], str)
            or item["state"] not in {"OPEN", "CLOSED", "MERGED"}
            or item["headRefName"] != branch
            or not isinstance(item["headRefOid"], str)
            or not FULL_SHA.fullmatch(item["headRefOid"])
            or not isinstance(item["baseRefName"], str)
            or not isinstance(item["baseRefOid"], str)
            or not FULL_SHA.fullmatch(item["baseRefOid"])
            or item["isCrossRepository"] is not False
            or not isinstance(head_repository, dict)
            or not isinstance(head_owner, dict)
            or not isinstance(head_repository.get("nameWithOwner"), str)
            or head_repository["nameWithOwner"].lower() != repo.lower()
            or not isinstance(head_owner.get("login"), str)
            or head_owner["login"].lower() != repo.split("/", 1)[0].lower()
            or (_url_path(item["url"], web_host) or "").lower()
            != f"/{repo}/pull/{number}".lower()
        ):
            return [], ["GitHub PR response did not match the requested branch identity"]
        if (
            item["headRefOid"].lower() == head_sha.lower()
            and item["baseRefName"] == base_ref
            and item["baseRefOid"].lower() == base_sha.lower()
        ):
            candidates.append(item)
    numbers = [item["number"] for item in data]
    if len(set(numbers)) != len(numbers):
        return [], ["GitHub PR response contained duplicate identities"]
    if not candidates:
        return [], ["GitHub PR list returned no exact identity candidate"]

    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        number = candidate["number"]
        exact_ok, exact, exact_error = gh(
            ["api", "-X", "GET", f"repos/{repo}/pulls/{number}"]
        )
        if not exact_ok:
            return [], [exact_error or "GitHub exact PR read failed"]
        if not isinstance(exact, dict):
            return [], ["GitHub exact PR response was not an object"]
        exact_url = exact.get("html_url")
        exact_number = exact.get("number")
        exact_head = exact.get("head")
        exact_base = exact.get("base")
        if (
            exact_number != number
            or not isinstance(exact_number, int)
            or isinstance(exact_number, bool)
            or not isinstance(exact_head, dict)
            or not isinstance(exact_base, dict)
            or (_url_path(exact_url, web_host) or "").lower()
            != f"/{repo}/pull/{number}".lower()
            or exact_head.get("ref") != branch
            or not isinstance(exact_head.get("sha"), str)
            or exact_head["sha"].lower() != head_sha.lower()
            or not isinstance(exact_head.get("repo"), dict)
            or not isinstance(exact_head["repo"].get("full_name"), str)
            or exact_head["repo"]["full_name"].lower() != repo.lower()
            or exact_base.get("ref") != base_ref
            or not isinstance(exact_base.get("sha"), str)
            or exact_base["sha"].lower() != base_sha.lower()
            or not isinstance(exact_base.get("repo"), dict)
            or not isinstance(exact_base["repo"].get("full_name"), str)
            or exact_base["repo"]["full_name"].lower() != repo.lower()
        ):
            return [], ["GitHub exact PR response did not match the requested identity"]
        matches.append(
            {
                "kind": "pr",
                "number": number,
                "state": candidate["state"],
                "url": exact_url,
                "headRefName": branch,
                "headRefOid": head_sha.lower(),
                "baseRefName": base_ref,
                "baseRefOid": base_sha.lower(),
            }
        )
    return matches, []


def reconcile_branch(
    repo: str, branch: str, expected_sha: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if not FULL_SHA.fullmatch(expected_sha):
        return [], [], ["expected SHA was not a full hexadecimal SHA"]
    github_paths = _github_paths(repo)
    if github_paths is None:
        return [], [], ["GH_HOST was not a canonical GitHub hostname"]
    web_host, api_host, api_repo_path = github_paths
    encoded_branch = quote(branch, safe="/")
    endpoint = f"repos/{repo}/git/ref/heads/{encoded_branch}"

    def classify_response(response: Any) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]], list[str]
    ]:
        actual_sha, response_error = _branch_response_sha(
            response,
            repo=repo,
            branch=branch,
            api_host=api_host,
            api_repo_path=api_repo_path,
        )
        if response_error is not None or actual_sha is None:
            return [], [], [response_error or "GitHub branch response was invalid"]
        result = {
            "kind": "branch",
            "ref": f"refs/heads/{branch}",
            "expected_sha": expected_sha.lower(),
            "actual_sha": actual_sha.lower(),
        }
        if actual_sha.lower() == expected_sha.lower():
            return [result], [], []
        result["reason"] = "sha-mismatch"
        return [], [result], []

    ok, data, error = gh(["api", endpoint])
    if ok:
        return classify_response(data)
    if _error_status(data) != 404:
        return [], [], [error]

    repo_ok, repo_data, repo_error = gh(
        ["api", "-X", "GET", f"repos/{repo}"]
    )
    if not repo_ok:
        return [], [], [repo_error or "GitHub repository read failed"]
    default_branch, repository_error = _repository_default_branch(
        repo_data,
        repo=repo,
        web_host=web_host,
        api_host=api_host,
        api_repo_path=api_repo_path,
    )
    if repository_error is not None or default_branch is None:
        return [], [], [repository_error or "GitHub repository response was invalid"]

    permission_probe_endpoint = (
        f"repos/{repo}/git/ref/heads/{quote(default_branch, safe='/')}"
    )
    probe_ok, probe_data, probe_error = gh(
        ["api", "-X", "GET", permission_probe_endpoint]
    )
    if not probe_ok:
        return [], [], [
            probe_error or "GitHub ref permission probe did not succeed"
        ]
    _, probe_validation_error = _branch_response_sha(
        probe_data,
        repo=repo,
        branch=default_branch,
        api_host=api_host,
        api_repo_path=api_repo_path,
    )
    if probe_validation_error is not None:
        return [], [], [probe_validation_error]

    retry_ok, retry_data, retry_error = gh(["api", "-X", "GET", endpoint])
    if retry_ok:
        return classify_response(retry_data)
    if _error_status(retry_data) == 404:
        return [], [], []
    return [], [], [retry_error or "GitHub branch read retry failed"]


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
    parser.add_argument("--head-sha", help="expected PR head full SHA")
    parser.add_argument("--base-ref", help="expected PR base branch")
    parser.add_argument("--base-sha", help="expected PR base full SHA")
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
    if args.kind == "pr" and not args.branch:
        parser.error("PR reconciliation requires --branch")
    pr_identity = (args.head_sha, args.base_ref, args.base_sha)
    if args.kind == "pr" and args.branch and any(value is None for value in pr_identity):
        parser.error("PR branch reconciliation requires --head-sha, --base-ref, and --base-sha")
    if args.kind != "pr" and any(value is not None for value in pr_identity):
        parser.error("--head-sha, --base-ref, and --base-sha are only valid with --kind pr")
    if args.head_sha and not FULL_SHA.fullmatch(args.head_sha):
        parser.error("--head-sha must be a 40-character hexadecimal SHA")
    if args.base_sha and not FULL_SHA.fullmatch(args.base_sha):
        parser.error("--base-sha must be a 40-character hexadecimal SHA")
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
        found, failures = reconcile_bodies(
            args.repo,
            args.kind,
            args.marker,
            head_ref=args.branch if args.kind == "pr" else None,
            head_sha=args.head_sha if args.kind == "pr" else None,
            base_ref=args.base_ref if args.kind == "pr" else None,
            base_sha=args.base_sha if args.kind == "pr" else None,
        )
        matches.extend(found)
        errors.extend(failures)
    if args.branch and args.kind == "pr":
        found, failures = reconcile_pr_branch(
            args.repo,
            args.branch,
            args.head_sha,
            args.base_ref,
            args.base_sha,
        )
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
