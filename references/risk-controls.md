# Risk-specific design controls

Read only the section linked by the Issue routing index. Do not require unrelated controls.

## Security and privacy

For `security` or `privacy`, add `### Threat model` under `Risks, migration, and rollback`. Identify protected assets or data, trust boundaries, abuse or disclosure paths, mitigations, residual risk, and private reporting needs.

## Persistent data, transactions, and migrations

For `persistence`, `transaction`, or `migration`, add `### Data invariants and recovery` under `Risks, migration, and rollback`. Define invariants, compatibility, partial-failure behavior, recovery, rollback, and migration ordering. New storage maps to `persistence`; new transaction and migration primitives use their matching triggers.

## Concurrency

For `concurrency`, add `### Concurrency model` under `Design basis and approach`. Define ownership, ordering, synchronization, cancellation, retry, and failure behavior.

## High-risk design audit

For `Risk class: high`, add `### Pre-implementation design audit` under `Design basis and approach`. Record an independent audit of the matched risk materials, acceptance criteria, and test matrix before coding. This gate is not a GitHub PR approval and never replaces final exact-SHA implementation review.
