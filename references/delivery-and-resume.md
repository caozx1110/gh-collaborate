# Delivery and resume

## Start cleanly

1. Fetch the default branch and relevant remote refs.
2. Record the exact baseline SHA in the Issue.
3. Inspect the worktree and index. Preserve unrelated changes and unknown files.
4. Create the Issue branch from the recorded baseline. Follow repository naming; otherwise use `agent/issue-<number>-<short-name>`.
5. Use a separate worktree when the current checkout is dirty, another task is active, or parallel isolation is useful.

Never build on an accidental local-only commit. Never stage the whole repository. Add explicit paths after reviewing the diff.

## Implement and validate

Keep commits cohesive and traceable to the atomic outcome. Run the narrowest relevant tests while iterating and the repository-required gate before delivery. Confirm generated artifacts and migrations are intentional. For bug fixes and review findings, reproduce the claim before changing code and retain evidence of the failing and passing behavior.

## Push checkpoints

Push after every checkpoint another agent may need. Record in an Issue comment:

- stage and branch;
- full remote SHA;
- completed outcome and remaining work;
- exact validation commands and results;
- blocker, if any;
- next action;
- operation marker when the write required reconciliation.

Do not report unpushed commits or a stash as shared progress. Do not force-push a checkpoint branch unless repository policy and an explicit human instruction authorize a safe replacement.

## Resume from remote truth

1. Read policy, Issue, PR, checks, review threads, and remote branch state again.
2. Fetch refs and verify the recorded full SHA exists on the intended remote branch.
3. Compare remote head, Issue checkpoint, PR head, current base, and local checkout.
4. If local state is disposable and remote state is authoritative, create a fresh worktree from the remote SHA.
5. If states diverge or authorship is unknown, do not overwrite either side. Report the candidates and request resolution.
6. Continue from the Issue's recorded next action only after evidence agrees.

## Deliver a consolidated candidate

For one track, validate and push the Issue branch. For multiple tracks, use one delivery branch and one integrator; merge or cherry-pick in dependency order, preserve source SHAs, run relevant tests after each integration, then run the full gate. The human-facing PR must contain the complete candidate.
