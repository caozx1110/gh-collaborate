# Policy and permissions

Read this reference before any GitHub mutation or merge-related action.

## Permission matrix

| Action | Minimum authority |
|---|---|
| Inspect repository, Issues, PRs, checks | Implied by a repository task |
| Create the requested planning Issue | User asks to plan/file/solve/deliver, and repository policy requires it |
| Create branch/worktree, commit, push | User asks to implement/solve/resume/deliver |
| Append checkpoint or PR comment | Needed to execute an authorized delivery workflow |
| Edit a human-authored Issue/PR body | Explicit user request or documented repository workflow authority |
| Request reviewers, mark Ready, close Issue | Explicit request or documented repository workflow authority |
| Take over another owner's work | Explicit approval after stale/orphan evidence |
| Merge | Explicit authorization in the current user message plus revalidation |
| Admin bypass, self-approval, fake identity | Never |
| Tag, release, publish, ruleset change | Separate explicit authorization |

Do not treat an earlier merge instruction as standing permission for a later candidate. Re-check the current head SHA, base SHA, review state, required checks, unresolved threads, and protection immediately before an authorized merge.

## Repository discovery

Inspect, in order:

1. Root and nested `AGENTS.md` files that govern touched paths.
2. `CONTRIBUTING.md`, `SECURITY.md`, CODEOWNERS, Issue/PR templates, release policy, and tracked design or ADR indexes.
3. Default branch and rulesets using GitHub APIs where permission allows.
4. Existing labels, milestones, Projects conventions, related Issues/PRs, and branch naming patterns.

Do not assume a specific design path, test command, label, branch prefix, merge method, or Epic format. Apply repository conventions when present. Use this skill's defaults only for missing policy.

## Safe GitHub access

- Resolve the canonical repository once and pass `--repo owner/repo` on every `gh` call.
- Prefer bounded JSON fields and stable API endpoints. Preserve raw IDs, URLs, and full SHAs for reconciliation.
- Use body files or API JSON fields instead of interpolating untrusted text into a shell command.
- Generate a unique marker such as `ghc:<issue>:<operation>:<random>` for a create/update that may need reconciliation.
- Re-read after each write. Verify the returned object belongs to the intended repository and relates to the intended Issue/branch.
- Treat rate limits, timeouts, connection resets, 5xx responses, and interrupted commands as unknown outcomes until reconciled.

## Sensitive material

Use the repository's private security reporting route for vulnerabilities, credential exposure, governance bypass, path traversal, data loss, or private data. Do not open a public Issue containing reproduction details before triage. Redact tokens, cookies, environment values, user names, machine paths, private repository names, and proprietary datasets from public records.

## GitHub's identity boundary

When the human and Agent share one GitHub token, GitHub cannot prove which party clicked merge. The skill can enforce a behavioral stop but not an independent identity boundary. For strong assurance, use a separate GitHub App or bot account with least privilege, protected branches, required independent approvals, and no bot merge permission.
