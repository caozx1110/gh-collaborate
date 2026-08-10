# Pull request, review, and close

## Create or update the PR

Search by head branch, atomic Issue, and operation marker before creation. Use Draft while required work, acceptance, or checks remain incomplete. The body should state:

- outcome and Issue/Epic references using `Refs #...` unless repository policy says otherwise;
- scope and non-goals;
- implementation summary and candidate full SHA;
- tests, Actions, and current base/merge-candidate evidence;
- evidence identity, invalidated claims, and declared-versus-actual complexity reconciliation;
- compatibility, security, migration, risks, and rollback;
- known limits and follow-up Issues;
- for parallel work: track, source SHA, integration commit, owned paths, and evidence.

Avoid auto-close keywords for critical Issues when post-merge smoke is required. Verify the PR after creation or update from a sufficient structured response, or use one bounded readback when the response is URL-only or incomplete; confirm repository, actor, body, URL, and exact head/base identity.

## Validate the candidate

Branch CI validates the pushed head. PR CI validates the candidate against the current base where the repository supports it. Preserve pure head evidence when only the base changes, but invalidate tested-merge evidence. A changed head invalidates the previous implementation review, head-bound candidate claim, complexity reconciliation, and CI. Dependency, workflow, rules, or environment changes invalidate the evidence that consumes that input; scope, counting-rule, or budget-policy changes invalidate complexity reconciliation. Do not claim green from checks attached to another identity.

## Address review

Read all review summaries, inline comments, unresolved threads, requested changes, and check annotations. Reproduce load-bearing findings before modifying code. Keep fixes within accepted scope; open a follow-up Issue for unrelated improvements. Push a new checkpoint, rerun affected tests, reply with evidence, and let the human resolve or approve according to repository policy.

Never submit an approval using the implementation identity. On a repository with one human account, do not simulate a second reviewer.

A high-risk pre-implementation design audit covers the proposed risk materials, acceptance, and test matrix. It is not a native approval and cannot replace final implementation review on the exact candidate SHA.

## Merge boundary

Stop when the PR is ready for human review. Merge only if the current user message explicitly asks for it. Immediately before merging, verify:

- exact current head and base;
- required checks on the current candidate;
- required approvals from independent identities;
- no requested changes or unresolved required threads;
- branch protection and repository merge policy;
- no new security or migration blocker.

Never use admin bypass. If authorization or a gate is missing, report the precise blocker and stop.

## Post-merge close

After an authorized merge, fetch the integration branch and identify the actual merge SHA. Verify its Actions and required smoke checks. Append the merge SHA, results, known limits, and follow-ups to the atomic Issue. Close it only when repository policy or explicit authority permits closure and smoke has passed. Update the Epic wave; close the Epic only after every wave and global criterion is complete. Regressions use a new fix-forward Issue and PR, never rewritten integration history.
