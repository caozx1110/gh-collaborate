# Parallel work and recovery

Load this reference only for multi-agent work, takeover, ambiguous failures, sensitive changes, migrations, or high-risk delivery.

## Parallel tracks

Parallelize only when tracks have disjoint owned paths, explicit interfaces, ordered dependencies, and one named integrator. Assign shared files to one owner or extract a prerequisite Issue. Record each track's branch, owner, owned paths, baseline, remote checkpoint SHA, validation, blocker, and next action.

Every track must push before integration. The integrator verifies source SHAs, integrates in dependency order, resolves conflicts with the owning track's intent, and records an integration map in the consolidated PR. Do not ask the reviewer to assemble branches.

## Takeover

Treat an absent Agent, unknown local worktree, or stale comment as insufficient evidence for takeover. Inspect the remote branch, Issue checkpoint, PR, Actions, and recent activity. Obtain explicit approval when ownership is assigned or the state is ambiguous. Create a new branch from the last trusted remote SHA, preserve lineage, and never rewrite the claimant's branch.

## Ambiguous API or push result

After timeout, connection loss, interruption, or 5xx:

1. Stop mutation retries.
2. Search by repository, operation marker, Issue relation, head/base, branch ref, and full SHA.
3. Classify the result as `present`, `absent`, `conflict`, or `unknown`.
4. Continue only for `present`; create once only for proven `absent`; stop for `conflict` or `unknown`.

Do not infer absence from a single empty search when GitHub reads are degraded.

## High-risk escalation

Add frozen ownership, exact dependency digests, replacement lineage, approval checkpoints, and recovery evidence for:

- schema or data migrations and irreversible external effects;
- security, permissions, rulesets, Actions trust, or supply-chain changes;
- cross-repository exact-version dependencies;
- release, publish, or high-value deployment;
- multiple Agents across sessions with takeover risk.

For security incidents, stop public writes and follow private reporting. For a GitHub trust failure, stop all collaboration writes until a human restores a trusted anchor out of band.
