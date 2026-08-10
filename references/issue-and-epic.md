# Issue and Epic planning

## Contents

- [Search before creation](#search-before-creation)
- [Create an Epic only when useful](#create-an-epic-only-when-useful)
- [Make the atomic Issue ready](#make-the-atomic-issue-ready)
  - [Keep ordinary Issues compact](#keep-ordinary-issues-compact)
- [Maintain state without destroying authorship](#maintain-state-without-destroying-authorship)
- [Handle scope change](#handle-scope-change)

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
- one lightweight screen using `Risk class`, `Risk triggers`, and `Complexity estimate`;
- compatibility, security, migration, and rollback considerations;
- acceptance checklist and test plan;
- state block: stage, exact baseline/full remote SHA, blocker, next action.

Do not begin implementation while the outcome, scope, acceptance criteria, important design decision, dependency, or ownership is unresolved.

Write every required `##` heading and conditional `###` heading at column zero. Write every required Issue field as a column-zero Markdown list item in the exact form `- Field: value`, directly under its required `##` section and before any `###` subsection. The validator rejects block-form raw HTML, HTML-comment openers, and fenced-code openers inside Markdown list or blockquote containers, along with one-to-three-space-indented comments or fence openers. Use Markdown for structure, column-zero HTML comments only for operation markers or notes, column-zero fenced code, and four-space or tab-indented code for literal examples. Checkpoint and PR records retain their legacy field syntax.

`Risk class` is `ordinary`, `enhanced`, or `high`. Use `ordinary` only with `Risk triggers: none`; use `enhanced` or `high` with one or more comma-separated triggers. Choose `high` when tracked policy or concrete impact requires an independent pre-implementation audit.

Use `ordinary / none / production files=<n>; net production lines=<n>; new primitives=none` for a small ordinary task. Route `security` or `privacy` to [Threat model](risk-controls.md#security-and-privacy), `persistence`/`transaction`/`migration` to [Data invariants and recovery](risk-controls.md#persistent-data-transactions-and-migrations), and `concurrency` to [Concurrency model](risk-controls.md#concurrency). New `storage`, `transaction`, `migration`, and `concurrency` primitives require those corresponding triggers. A `high` classification also routes to [Pre-implementation design audit](risk-controls.md#high-risk-design-audit).

The default budget gate is more than 10 production files or 500 net production lines. A crossed applicable cap uses the `budget` trigger and routes with scope drift to [Budget and drift](complexity-and-decomposition.md#budget-and-drift); `shared-paths` routes to [Shared paths and internal tracks](complexity-and-decomposition.md#shared-paths-and-internal-tracks), and `decomposition` routes to [Parent/child delivery](complexity-and-decomposition.md#parentchild-delivery). When tracked policy overrides the default caps, append `budget override=<relative policy path>; production file budget=<n>; net production line budget=<n>` inside `Complexity estimate`; an estimate within those caps may remain ordinary. Do not load unmatched sections.

### Keep ordinary Issues compact

For `ordinary` with no matching trigger, fill the same Atomic Issue template and all recovery fields, then compress each prose section to one or two sentences by default. Keep acceptance to at most three checks and the test plan to at most two checks unless repository policy, uncertainty, or concrete evidence requires expansion; these are brevity defaults, not validator limits, so a justified detailed ordinary Issue remains legal.

Use this compact canonical example for a one-file documentation correction:

```markdown
<!-- operation-marker: ghc:issue:create:readme-typo:sample -->

## Problem and evidence

README.md says `dependancies`; the project consistently uses `dependencies`.

## Outcome

README.md uses the project spelling in that sentence.

## Scope

Correct that word in README.md only.

## Non-goals

Do not change code, behavior, or adjacent documentation.

## Design basis and approach

Preserve the sentence and replace only the misspelled word.

## Dependencies and ownership

- Risk class: ordinary
- Risk triggers: none
- Complexity estimate: production files=0; net production lines=0; new primitives=none

One owner makes the documentation-only change; there are no dependencies.

## Risks, migration, and rollback

The risk is an adjacent edit; inspect the one-file diff and roll back by reverting the documentation commit.

## Acceptance checklist

- [ ] The misspelled word is corrected.
- [ ] No other file or sentence changes.

## Test plan

- [ ] Inspect the one-file diff.
- [ ] Run a repository-required documentation check, if one exists.

## State

- Stage: ready
- Baseline: 1111111111111111111111111111111111111111
- Last remote SHA: none
- Blocker: none
- Next action: create the Issue branch from the recorded baseline.
```

## Maintain state without destroying authorship

Prefer append-only comments for checkpoints and handoffs. Edit the Issue body only when repository policy designates it as a maintained control record or the user explicitly requests the edit. Never erase human discussion or silently rewrite accepted scope.

Use stable stages such as `draft`, `ready`, `in-progress`, `blocked`, `in-review`, `merged`, and `closed`. A local commit is not a shared checkpoint. Record only a pushed full SHA.
The baseline is always a full SHA. Before the first pushed checkpoint, use the literal `none` for `Last remote SHA`; replace it with the pushed full SHA afterward.

## Handle scope change

Pause implementation before a material change to outcome, scope, acceptance, security posture, migration, or rollback. Update and reconfirm the Issue. If a PR is already under review, prefer a replacement Issue/PR with explicit lineage rather than expanding the old candidate unnoticed.
