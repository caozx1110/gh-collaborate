# Complexity, drift, and decomposition

Read only the section linked by the Issue routing index. Ordinary work does not gain another GitHub write, reviewer, or full-suite run.

## Budget and drift

The default re-evaluation budget is more than 10 production files or 500 net production lines. Exclude generated files, vendored code, tests, and documentation. New storage, transaction, migration, or concurrency primitives also trigger re-evaluation through their risk controls.

A repository may replace the numeric defaults in tracked policy. Keep the override in the same screening field: `budget override=<relative policy path>; production file budget=<n>; net production line budget=<n>`. The validator compares the estimate with those cited effective caps; the reference does not grant an unlimited budget.

Crossing the applicable budget pauses expansion for an explicit continue, reduce, split, or replace decision—it does not automatically split or terminate the Issue. Add `### Scope and budget decision` under `Design basis and approach` when the `budget` trigger applies.

Re-evaluate when implementation discovers a new primitive or independently deliverable outcome, changes an interface/security/rollback boundary, or moves the current estimate past its applicable caps. Use the existing `blocked` stage with `Blocker` and `Next action` while the decision is unresolved; do not invent a compound stage, periodic time checkpoint, or implementation diary.

## Shared paths and internal tracks

For `shared-paths`, add `### Ownership and integration plan` under `Dependencies and ownership`. Record the path owner, interfaces, dependency order, integrator, and conflict plan.

When tracks have value only after combined integration, keep one Atomic Issue. Assign disjoint paths and interfaces, use one integrator and one consolidated delivery PR, and never make the reviewer assemble track branches.

## Parent/child delivery

Use parent/child Atomic Issues only when every child is independently reviewable, mergeable, acceptable, and reversible. Add `### Parent/child delivery plan` under `Dependencies and ownership` with the parent, children, dependencies, exact baselines, merge order, and closure authority.

The parent owns the global outcome, interfaces, dependency graph, cross-child risks, integration tests, and global definition of done. Each child records only its design delta, dependency and exact baseline, acceptance, rollback, PR, and actual merge SHA; do not copy the parent's full risk material or test matrix. Give each child one Issue branch and one consolidated PR.

Accept and close in three levels:

1. **Child level:** validate the child's acceptance on its exact candidate, merge under normal human authority, verify default-branch smoke, and record the actual merge SHA.
2. **Integration level:** validate cross-child interfaces, migrations, ordering, compatibility, and parent integration tests on the current default branch. A green child cannot override failed integration.
3. **Parent level:** verify every required child and the global definition of done. An unfinished optional child must be explicitly removed from required scope or tracked as a follow-up; it cannot be silently ignored.

Close a child only after its post-merge evidence is recorded. Close the parent last, after integration and global acceptance pass and closure authority exists. Fix integration failures through an atomic fix-forward Issue; never rewrite merged history.
