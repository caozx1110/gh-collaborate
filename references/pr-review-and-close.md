# Pull request, review, and close

## Create or update the PR

Search by head branch, atomic Issue, and operation marker before creation. Use Draft while required work, acceptance, or checks remain incomplete. The body should state:

- outcome and Issue/Epic references using `Refs #...` unless repository policy says otherwise;
- scope and non-goals;
- implementation summary and candidate full SHA;
- tests, Actions, and current base/merge-candidate evidence;
- compatibility, security, migration, risks, and rollback;
- known limits and follow-up Issues;
- for parallel work: track, source SHA, integration commit, owned paths, and evidence.

Avoid auto-close keywords for critical Issues when post-merge smoke is required. Re-read the PR after creation or update and confirm head/base identity.

## Validate the candidate

Branch CI validates the pushed head. PR CI validates the candidate against the current base where the repository supports it. If head or base changes, treat previous merge-candidate results as stale and rerun required gates. Do not claim green from checks attached to another SHA.

## Address review

Read all review summaries, inline comments, unresolved threads, requested changes, and check annotations. Reproduce load-bearing findings before modifying code. Keep fixes within accepted scope; open a follow-up Issue for unrelated improvements. Push a new checkpoint, rerun affected tests, reply with evidence, and let the human resolve or approve according to repository policy.

Never submit an approval using the implementation identity. On a repository with one human account, do not simulate a second reviewer.

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

After a human merge, fetch the default branch and identify the actual merge SHA. Verify default-branch Actions and required smoke checks. Append the merge SHA, results, known limits, and follow-ups to the atomic Issue. Close it only when repository policy or explicit authority permits closure and smoke has passed. Update the Epic wave; close the Epic only after every wave and global criterion is complete. Regressions use a new fix-forward Issue and PR, never rewritten default history.
