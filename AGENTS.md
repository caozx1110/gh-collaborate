# AGENTS.md — Developing gh-collaborate

This repository is the source of the `gh-collaborate` skill. Develop it through GitHub Issues and pull requests, but do not load or invoke the in-development skill to define its own requirements or acceptance criteria. Treat `SKILL.md`, references, scripts, and templates as product source during development.

## Sources of truth

- Accepted behavior: default-branch source and tests.
- Planned outcome and acceptance: GitHub Epic and atomic Issue.
- Shared progress: pushed full SHAs, PRs, reviews, and Actions.
- Security reports: private channels described by GitHub Security Advisories; never public Issues.

Local chat, private Agent memory, untracked plans, stash, unpushed commits, and machine logs are not collaboration authority.

## Lightweight workflow

1. Fetch the default branch and record the exact baseline SHA.
2. Reuse an existing Epic for the same blueprint; create one only for a new multi-wave goal.
3. Before implementation, make one atomic Issue ready with problem, outcome, scope/non-goals, approach, risks/rollback, acceptance, test plan, baseline, blocker, and next action.
4. Work on `agent/issue-<number>-<short-name>` or a repository-approved equivalent. Preserve unrelated work, stage explicit paths, commit cohesively, push checkpoints, and record full remote SHAs.
5. Integrate parallel tracks into one delivery branch and one consolidated PR. The reviewer must not assemble branches.
6. Run `python3 -m unittest discover -s tests -v` and the official skill validator. Open Draft until acceptance and CI are complete.
7. Stop for human review. Never self-approve, use admin bypass, or merge without explicit current-message authorization after revalidating protections.
8. After human merge, verify default-branch Actions/smoke, update Issues with the actual merge SHA, and close only under human or documented workflow authority.

Never push or force-push the default branch, use `git add -A`, expose secrets or local paths in public records, retry ambiguous GitHub writes without reconciliation, or tag/release/publish without separate explicit authorization.
