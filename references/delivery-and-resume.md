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

Use this evidence ladder without inventing lifecycle stages:

1. targeted tests while the local change is unstable;
2. the full required suite on a stable head;
3. a final candidate push and remote full-SHA check;
4. branch-head CI on that pushed head;
5. tested-merge CI on that head plus the current base;
6. post-merge smoke on the actual merge SHA.

Record enough identity to reproduce each claim: exact command and environment, head SHA, base SHA when applicable, dependency or lockfile identity, workflow and rules identity, accepted scope, and actual merge SHA for post-merge evidence. A head change invalidates head-bound tests, implementation review, complexity reconciliation, and branch CI. A base-only change preserves pure head evidence but invalidates tested-merge evidence. Dependency, workflow, rules, or environment changes invalidate only claims that consume the changed input; scope, counting-rule, or budget-policy changes invalidate complexity reconciliation. Waiting, comments, and local exploration do not invalidate evidence or trigger another full suite when those inputs are unchanged; repository-required checks always take precedence. Keep lifecycle stages stable, treat native GitHub checks and reviews as their authority, and do not mirror transient CI or review state into a composite stage.

Before Ready, reconcile the Issue estimate with the exact candidate. Record actual production-file count, net production code or protocol lines, counting method, exclusions, new primitives, applicable caps, and any tracked budget policy. Candidate evidence JSON uses `identity` for head/base/review SHAs, commands, environment, dependencies, workflow, rules, and scope, plus `complexity` for declared/actual counts, counting method, exclusions, caps, override, material-divergence judgment, and decision. Run `python scripts/validate_candidate_evidence.py evidence.json --root .` when available. Static work-item validation checks override syntax only; repository-aware preflight must prove the policy path is tracked and its structured effective caps match. A crossed cap, newly discovered primitive, or recorded material estimate divergence requires a `continue`, `reduce`, `split`, or `replace` decision checkpoint.

## Push checkpoints

Push a checkpoint only for handoff; a blocker; scope, acceptance, or budget drift; decomposition or replacement; a new or updated final candidate; merge; or closure. Ordinary internal fixes, local exploration that does not change the shared candidate, and unchanged CI waiting state do not each receive a push or comment, and there is no hard comment-count limit. Record in an Issue comment:

- stage and branch;
- full remote SHA;
- completed outcome and remaining work;
- exact validation commands and results;
- evidence identity, invalidated claims, and final complexity reconciliation when applicable;
- blocker, if any;
- next action;
- preissued operation marker and whether the write was verified from its response, a bounded readback, or ambiguous reconciliation.

Do not report unpushed commits or a stash as shared progress. Do not force-push a checkpoint branch unless repository policy and an explicit human instruction authorize a safe replacement.

The ordinary path does not add a reviewer or GitHub write, load enhanced-only guidance, or prescribe a full-suite run beyond the applicable ladder and repository rules. Run broader controls only when current authority, repository policy, or concrete evidence requires them.

## Resume from remote truth

1. Read policy, Issue, PR, checks, review threads, and remote branch state again.
2. Fetch refs and verify the recorded full SHA exists on the intended remote branch.
3. Compare remote head, Issue checkpoint, evidence identity, PR head, current base, and local checkout.
4. If local state is disposable and remote state is authoritative, create a fresh worktree from the remote SHA.
5. If states diverge or authorship is unknown, do not overwrite either side. Report the candidates and request resolution.
6. Continue from the Issue's recorded next action only after evidence agrees.

## Deliver a consolidated candidate

For one track, validate and push the Issue branch. For multiple tracks, use one delivery branch and one integrator; merge or cherry-pick in dependency order, preserve source SHAs, run relevant tests after each integration, then run the full gate. The human-facing PR must contain the complete candidate.
