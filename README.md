# gh-collaborate

`gh-collaborate` is an open-source Agent Skill for coordinating repository work through GitHub Issues, Git branches and worktrees, remote checkpoints, pull requests, Actions, human review, and post-merge closure.

It is for people who want coding agents to leave an auditable, portable handoff in GitHub instead of relying on chat history, private memory, or unpushed local state. The authoritative Agent workflow lives in [SKILL.md](SKILL.md); this README is the human-facing introduction.

## How it works

The skill follows the narrowest lifecycle needed for a task:

```text
inspect -> issue -> solve/resume -> deliver -> human review -> authorized merge -> close
```

Repository policy and tracked source take precedence over the skill's defaults. Work is planned in an atomic Issue, implemented on a dedicated branch, checkpointed with full remote commit SHAs, and delivered as one consolidated pull request. A merge requires explicit authorization in the current request and revalidation of the candidate; green checks alone never authorize it.

See [the complete workflow](SKILL.md) and the focused references for [planning](references/issue-and-epic.md), [delivery and recovery](references/delivery-and-resume.md), and [pull requests through closure](references/pr-review-and-close.md).

## Requirements

- A Codex surface that supports standalone [Agent Skills](https://learn.chatgpt.com/docs/build-skills.md).
- Git and an authenticated [GitHub CLI](https://cli.github.com/) session.
- Access to the target GitHub repository with permission for the actions you request.
- Python 3.10 or newer to run the included helpers and validation suite.

## Install

Choose one scope. Codex discovers repository skills in `.agents/skills` and personal skills in `$HOME/.agents/skills`.

For one repository, add a pinned Git submodule from that repository's root:

```bash
mkdir -p .agents/skills
git submodule add https://github.com/caozx1110/gh-collaborate.git .agents/skills/gh-collaborate
```

For all of your repositories, install it in your personal skill directory:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/caozx1110/gh-collaborate.git "$HOME/.agents/skills/gh-collaborate"
```

Codex normally detects skills automatically. Restart Codex if `gh-collaborate` does not appear after installation.

## Quick start

In Codex CLI or the IDE extension, explicitly invoke the skill with `$gh-collaborate`:

```text
$gh-collaborate Inspect this repository and prepare an atomic Issue for adding cache support.
```

You can then ask it to implement, deliver, review, resume, merge, or close the same GitHub-tracked work. Read-only requests remain read-only; ask for the mutation you want.

## Safety boundaries

- Repository policy, accepted tracked source, and current GitHub records are the collaboration authority—not local chat, stash, unpushed commits, or private memory.
- Issue, PR, review, and branch text is treated as untrusted data, never as instructions to execute blindly.
- The skill does not push or force-push the default branch, self-approve, bypass branch protection, or merge without explicit current-message authorization.
- Ambiguous GitHub writes are reconciled before any retry, reducing duplicate comments, Issues, PRs, or pushes.
- If the human and Agent share one GitHub identity, GitHub cannot prove who performed an action. Strong separation requires a dedicated least-privilege App or bot identity plus protected branches and independent approval.

The detailed permission model is in [policy and permissions](references/policy-and-permissions.md).

## Repository structure

| Path | Purpose |
| --- | --- |
| [SKILL.md](SKILL.md) | Skill metadata, activation scope, and main workflow |
| [agents/openai.yaml](agents/openai.yaml) | Codex UI metadata and default prompt |
| [references/](references/policy-and-permissions.md) | Focused policy, planning, delivery, review, and recovery guidance |
| [assets/templates/](assets/templates/atomic-issue.md) | Epic, Issue, checkpoint, and pull request templates |
| [scripts/](scripts/inspect_repo.py) | Inspection, rendering, validation, and reconciliation helpers |
| [tests/](tests/test_helpers.py) | Unit tests for the helpers and tracked templates |
| [AGENTS.md](AGENTS.md) | Contribution policy for this repository |

## Validate

From the repository root, run:

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
# Replace the validator path with your local skill-creator installation.
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

GitHub Actions runs the compile and test gates on pushes and pull requests with Python 3.10 and 3.13.

## Contributing

Start with [AGENTS.md](AGENTS.md). Changes are developed Issue-first on a dedicated branch, validated, pushed with an auditable checkpoint, and submitted as a pull request for human review. Security reports belong in GitHub's private security reporting channel, not a public Issue.

## License

This project is available under the [MIT License](LICENSE).
