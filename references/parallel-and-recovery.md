# Parallel work and recovery

Load this reference only for multi-agent work, takeover, ambiguous failures, sensitive changes, migrations, or high-risk delivery.

## Parallel tracks

Parallelize only when tracks have disjoint owned paths, explicit interfaces, ordered dependencies, and one named integrator. Assign shared files to one owner or extract a prerequisite Issue. Record each track's branch, owner, owned paths, baseline, remote checkpoint SHA, validation, blocker, and next action.

Every track must push before integration. The integrator verifies source SHAs, integrates in dependency order, resolves conflicts with the owning track's intent, and records an integration map in the consolidated PR. Do not ask the reviewer to assemble branches.

## Takeover

Treat an absent Agent, unknown local worktree, or stale comment as insufficient evidence for takeover. Inspect the remote branch, Issue checkpoint, PR, Actions, and recent activity. Obtain explicit approval when ownership is assigned or the state is ambiguous. Create a new branch from the last trusted remote SHA, preserve lineage, and never rewrite the claimant's branch.

## Ambiguous API or push result

A successful command with a complete structured object belongs to normal write verification, not this recovery path. If the success output is only a URL or lacks repository, object, parent/actor, content, or head/base identity, perform one bounded readback and verify that object. Enter ambiguous reconciliation only when the write outcome cannot be determined.

After timeout, connection loss, interruption, or 5xx:

1. Stop mutation retries.
2. Search by repository, operation marker, Issue relation, head/base, branch ref, and full SHA.
3. Classify the result as `present`, `absent`, `conflict`, or `unknown`.
4. Continue only for `present`; create once only for proven `absent`; stop for `conflict` or `unknown`.

The unique operation marker must already be present in the original non-idempotent request; never add one only after failure. Bind a comment search to the canonical repository and parent Issue/PR number, require one exact standalone hidden marker, and treat duplicate bodies or multiple matching objects as conflict/unknown rather than absence. For a push, require the remote branch to equal the expected 40-character SHA; a same-name branch at another SHA is a conflict, not success.

Do not infer absence from malformed pagination, partial data, rate limiting, or any degraded GitHub read. Only a healthy authoritative empty result proves absence, and only that result permits one create attempt.

## High-risk escalation

Add frozen ownership, exact dependency digests, replacement lineage, approval checkpoints, and recovery evidence for:

- schema or data migrations and irreversible external effects;
- security, permissions, rulesets, Actions trust, or supply-chain changes;
- cross-repository exact-version dependencies;
- release, publish, or high-value deployment;
- multiple Agents across sessions with takeover risk.

For security incidents, stop public writes and follow private reporting. For a GitHub trust failure, stop all collaboration writes until a human restores a trusted anchor out of band.
