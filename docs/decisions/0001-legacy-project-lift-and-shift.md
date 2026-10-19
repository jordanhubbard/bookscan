# ADR 0001: Retain Legacy Source Authority During Lift-and-Shift

- Status: Accepted for adoption
- Date: 2026-10-19
- Decision owners: project maintainers
- Baseline evidence: `sha256:d9bf60368ae29370364815c1f1fea4db6fa57a6a37e0a4627a9ed3bed37b58a9`
- Shim parity evidence: `sha256:d73ccd3206a68af570606f3926adb27b342a0397b8133f51d9e4d4b34b256b2d`

## Context

Phase 1 proved the original project end-to-end. Phase 1.1 proved that Literate AI can
drive the same build, test, package, and CI stages through first-class wrapper
source-to-specification transfer has occurred.

## Decision

Move the complete original tree, preserving its internal taxonomy, from quarantine to
`components/legacy-project-wrapper/implementation`. The wrapper Component owns this retained implementation
and `litai.harness.mk` invokes it at its new location. Each move uses `git mv` when the
entry is tracked and plain filesystem move otherwise.

The move is admitted only when the post-move wrapper workflow has the same successful
exit and source-authority tree identity as the Phase 1 direct baseline. Only then is
the empty quarantine directory removed. The retained implementation is not generated
source, not a cache, and not a specification; it remains release authority until a
separate Phase 2 ADR qualifies native Components, Flavors, skills, and assets.

## Consequences

- `components/legacy-project-wrapper/implementation/` is intentionally load-bearing
  retained source and may not be cleaned as a build product.
- Build products still belong outside authority and remain fungible.
- Future migration items replace one retained surface at a time, prove parity, then
  remove its pre-adoption implementation with `git rm` or `rm`.
- Phase 2 owns source-to-specification and native rewrite; this ADR makes no semantic
  equivalence claim beyond E2E parity.
