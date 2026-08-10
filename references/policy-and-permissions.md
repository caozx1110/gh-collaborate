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
- Put a unique marker such as `ghc:<parent>:<operation>:<random>` in the original Issue, comment, or PR create/update request. Use one exact standalone hidden comment and bind searches to the canonical repository and intended parent.
- Verify every write. A complete structured success object may supply the evidence directly; a zero exit code, URL-only output, or object missing required identity requires one bounded readback.
- Treat rate limits, timeouts, connection resets, 5xx responses, and interrupted commands as unknown outcomes until reconciled.

## Write verification

For an Issue, comment, or PR response or successful readback, require the canonical repository, object type and positive ID, authenticated actor from preflight, returned resource author, exact body or independently checkable summary, and remote URL. On create, author normally equals actor; on update, preserve and verify the existing author instead of mistaking it for the updater. Also require the intended Issue/PR number for an update, the parent number for a comment, and exact head/base refs and full SHAs for a PR. A missing field is `readback-required`; a present but mismatched repository, author, parent, body, type, or head/base is a conflict. Never treat an incomplete response as proof of success.

A branch push is different: always read the remote ref and require equality with the expected 40-character SHA. A missing ref can prove absence only from a healthy authoritative read; the same branch name at another SHA is a conflict.

Use `reconcile_state.verify_write_response` or equivalent local checks for a complete object. The helper is read-only: it verifies supplied JSON and performs bounded searches or GETs for reconciliation; it never creates, comments, updates, pushes, or merges. Write verification itself does not create another lifecycle stage or checkpoint.

## Sensitive material

Use the repository's private security reporting route for vulnerabilities, credential exposure, governance bypass, path traversal, data loss, or private data. Do not open a public Issue containing reproduction details before triage. Redact tokens, cookies, environment values, user names, machine paths, private repository names, and proprietary datasets from public records.

## GitHub's identity boundary

When the human and Agent share one GitHub token, GitHub cannot prove which party clicked merge. The skill can enforce a behavioral stop but not an independent identity boundary. For strong assurance, use a separate GitHub App or bot account with least privilege, protected branches, required independent approvals, and no bot merge permission.
