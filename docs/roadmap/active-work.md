# Active work

This file is the durable resumption queue for user-directed and discovered work. Before
implementation, follow `skills/agent/record-user-directed-work/SKILL.md`.
Keep detailed designs in focused roadmap documents and link them here.

## Detailed-roadmap lifecycle

This file is the sole resumable queue. Create a supporting file beneath `docs/roadmap/`
only when one item cannot keep a program's rationale, ordering, and acceptance contract
readable. Put this visible header immediately after the detailed document's title:

```markdown
- **Status:** active
- **Owning queue item:** [AREA-NNN](active-work.md#area-nnn-heading)
- **Completion / archival evidence:** pending while AREA-NNN remains open
```

Status is exactly `active`, `partial`, `deferred`, `completed`, or `historical`. The
owner must resolve to a checkbox or named program heading in this file. A terminal state
requires linked evidence. Keep a completed plan here only when doing so preserves useful
inbound links; move substantial closed programs beneath `docs/history/roadmap/`, retain
their owner, and mark them `historical`. Do not create a separate file for an ordinary
queue item or let `docs/roadmap/` become a plan archive.

## P0

<a id="adopt-002"></a>
### [ ] ADOPT-002 — Native Literate AI rewrite

- **Owner:** project architecture / Components / Flavors / skills / assets
- **Direction:** Execute
  [ADR 0002](../decisions/0002-native-literate-ai-rewrite.md) through the
  [native rewrite program](native-rewrite-program.md), preserving retained source
  authority until each boundary independently qualifies.
- **Status:** deferred; native regeneration is outside the requested retained-source adoption.
- **Next action when authorized:** Produce the evidence-linked boundary inventory for
  `components/legacy-project-wrapper/implementation`.
- **Evidence:** Phase 1.2 lift-and-shift identity `sha256:2d136efee330f2f7e2ee39ade7cb0d8c6deb00ba473db8004b3dcf642f2f5bb4`.

### [x] BOOKSCAN-001 — Smoke-test and adopt BookScan into Literate AI

- **Priority:** high
- **Owner:** components/legacy-project-wrapper
- **Direction:** Add smoke coverage and manage BookScan with Literate AI and installed CodeGraph tooling.
- **Conclusion:** Preserve original-source authority at the retained stage, qualify the admitted harness, and keep the desktop application runnable.
- **Depends on:** none
- **Implementation:**
  - [x] Add isolated Qt-session and CLI smoke tests and declare pinned CodeGraph provisioning.
  - [x] Adopt the source tree and preserve user content through the official conversion harness.
  - [x] Restore root developer commands, publish current retained test evidence, and advance to retained.
- **Evidence:**
  - [x] 54 regression and smoke tests pass.
  - [x] Current retained harness receipt and conversion admission pass.
  - [x] litai verify and CodeGraph source-intelligence checks pass.

- **Results:** `make smoke` passes both isolated desktop/CLI smoke cases; the full
  regression suite and admitted retained harness each pass 54 tests.
  `verification/current.json` is current; `.literate/conversion-authority.json`
  records `retained` with original-source release authority. `litai verify` passes
  all four configured gates (HTML observability is not configured). CodeGraph
  1.6.2 observes eight source files and reports the project index current. Root
  developer commands and the installed desktop CLI still resolve after adoption.
- **Tracker:** Local Git repository; no forge remote is configured, so hosted issue
  and review reconciliation is unavailable. No remote publication was requested.

### [x] BOOKSCAN-002 — Portable title-based book folders with live path preview

- **Priority:** high
- **Owner:** components/legacy-project-wrapper
- **Direction:** Use the book title as a safe Windows/Unix-compatible image subfolder and show the default destination while typing.
- **Conclusion:** New books use an ASCII-normalized, collision-safe title subfolder beneath default storage. Browse or manual path entry overrides the exact destination and remains fixed through title changes; Use default restores automatic naming. Preserve all existing book paths and preview the destination before creation.
- **Depends on:** none
- **Implementation:**
  - [x] Implement portable title normalization and deterministic collision handling.
  - [x] Preview the exact image destination live in the inline form and update folder labels.
  - [x] Update regression and smoke coverage, retained-source evidence and documentation.
- **Evidence:**
  - [x] Normalization, path preview, collision, existing-library compatibility and full smoke/regression checks pass.
  - [x] Current retained harness receipt, CodeGraph index and litai verify pass.

- **Results:** The regression/smoke suite and current retained harness pass 79
  checks, including safe ASCII names, Windows reserved devices, case-insensitive
  collisions, default path previews, exact Browse/manual overrides, reservation
  races, rollback, and existing-library compatibility. The rendered inline form
  was inspected at 1180×800. `verification/current.json` is current; `litai verify`
  passes authority, locks, source intelligence, and receipt gates. Native Windows
  execution was not performed; portable-name rules have explicit fixtures.
