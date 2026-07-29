# Issue and Epic planning

## Search before creation

Search open and recently closed Issues for the same outcome, design identifier, error signature, affected component, and proposed branch. Search PRs and remote branches as well. Reuse a suitable open record. When duplicates conflict, stop and ask the human to choose the authority instead of silently merging their scope.

## Create an Epic only when useful

Create or reuse an Epic when the request introduces a new blueprint with multiple independently deliverable waves. An Epic records:

- final goal and measurable success criteria;
- accepted baseline and tracked design links;
- scope and non-goals;
- ordered waves and dependencies;
- cross-wave risks, migration, rollback, and global definition of done.

Prefer the repository's native issue type, label, Project field, or template. If none exists, use an Issue titled `[Epic] <goal>`. Include a stable blueprint identifier only when the repository already uses one.

## Make the atomic Issue ready

An atomic Issue owns one independently reviewable and reversible outcome. Include:

- problem and concise evidence;
- observable outcome;
- scope and non-goals;
- accepted design or current behavior basis;
- implementation approach without pretending proposals are facts;
- dependencies, owner, and owned paths when needed;
- compatibility, security, migration, and rollback considerations;
- acceptance checklist and test plan;
- state block: stage, exact baseline/full remote SHA, blocker, next action.

Do not begin implementation while the outcome, scope, acceptance criteria, important design decision, dependency, or ownership is unresolved.

## Maintain state without destroying authorship

Prefer append-only comments for checkpoints and handoffs. Edit the Issue body only when repository policy designates it as a maintained control record or the user explicitly requests the edit. Never erase human discussion or silently rewrite accepted scope.

Use stable stages such as `draft`, `ready`, `in-progress`, `blocked`, `in-review`, `merged`, and `closed`. A local commit is not a shared checkpoint. Record only a pushed full SHA.

## Handle scope change

Pause implementation before a material change to outcome, scope, acceptance, security posture, migration, or rollback. Update and reconfirm the Issue. If a PR is already under review, prefer a replacement Issue/PR with explicit lineage rather than expanding the old candidate unnoticed.
