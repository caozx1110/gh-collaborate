#!/usr/bin/env python3
"""Emit a normalized, read-only Git and GitHub repository snapshot as JSON."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update({"GH_PAGER": "cat", "NO_COLOR": "1"})
    process = subprocess.run(command, cwd=cwd, env=environment, text=True, capture_output=True, check=False)
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }


def json_output(result: dict[str, Any]) -> Any:
    if not result["ok"]:
        return None
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None


def inspect(root: Path, repo: str | None) -> dict[str, Any]:
    root_result = run_command(["git", "rev-parse", "--show-toplevel"], root)
    worktree = Path(root_result["stdout"]) if root_result["ok"] else root
    status = run_command(["git", "status", "--porcelain=v1"], worktree)
    branch = run_command(["git", "branch", "--show-current"], worktree)
    head = run_command(["git", "rev-parse", "HEAD"], worktree)
    remote = run_command(["git", "remote", "get-url", "origin"], worktree)
    target = repo or None
    gh_command = ["gh", "repo", "view"]
    if target:
        gh_command.append(target)
    gh_command += ["--json", "nameWithOwner,url,visibility,isFork,parent,defaultBranchRef,viewerPermission"]
    repository_result = run_command(gh_command, worktree)
    actor_result = run_command(["gh", "api", "user", "--jq", ".login"], worktree)
    repository = json_output(repository_result)
    return {
        "schema_version": 1,
        "git": {
            "inside_worktree": root_result["ok"],
            "branch": branch["stdout"] if branch["ok"] else None,
            "head": head["stdout"] if head["ok"] else None,
            "dirty": bool(status["stdout"]) if status["ok"] else None,
            "origin": remote["stdout"] if remote["ok"] else None,
        },
        "github": {
            "actor": actor_result["stdout"] if actor_result["ok"] else None,
            "repository": repository,
            "available": repository is not None,
        },
        "errors": [
            {"source": source, "message": result["stderr"]}
            for source, result in (("git", root_result), ("github", repository_result), ("actor", actor_result))
            if not result["ok"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="canonical owner/repo")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    snapshot = inspect(args.root.resolve(), args.repo)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
