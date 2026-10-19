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

### [x] BOOKSCAN-003 — BookScan application icon and desktop integration

- **Priority:** medium
- **Owner:** components/legacy-project-wrapper
- **Direction:** Create a good application icon for BookScan.
- **Conclusion:** Create one distinctive book-and-scanner icon, package it with the application, use it in Qt windows and provide a desktop launcher using the same asset.
- **Depends on:** none
- **Implementation:**
  - [x] Generate and inspect the application icon and save it inside the package.
  - [x] Wire the packaged icon into Qt and installable desktop integration.
  - [x] Verify icon inclusion, smoke tests and refreshed retained-source evidence.
- **Evidence:**
  - [x] Icon is legible at small sizes and packaged application/window/desktop references resolve.
  - [x] Regression/smoke checks and litai verification pass.

- **Results:** Built-in image generation produced the final transparent PNG; its
  source, exact prompt, and provenance are documented in `docs/design/icon.md`.
  The icon was inspected at 32/64/128 px on light and dark backgrounds. The built
  wheel includes both the PNG and desktop integration module. Qt icon sizes,
  display-free installation, desktop entry validation and quoting pass; a native
  Gio launch probe succeeds with an executable path containing spaces. The full
  regression suite and retained harness each pass 83 tests. The desktop launcher
  is installed for the current user; `litai verify` passes all four configured gates.

### [x] BOOKSCAN-004 — One-step capture and keyboard operation

- **Priority:** high
- **Owner:** components/legacy-project-wrapper
- **Direction:** Combine capture and save; provide keyboard accelerators for button actions.
- **Conclusion:** Camera captures save immediately after optional auto-trim; saved-page editing and imports retain explicit Save, and failed saves retain retryable images. Provide visible shortcut help, button hints and keyboard navigation without unmodified typing keys.
- **Depends on:** none
- **Implementation:**
  - [x] Implement automatic camera save and update workflow guidance.
  - [x] Add shortcuts for every button action and keyboard navigation/help.
  - [x] Update regression coverage and retained-source evidence.
- **Evidence:**
  - [x] Single-step captures, cancellation, failed-save recovery and keyboard interactions pass regression/smoke checks.
  - [x] Retained harness, CodeGraph source intelligence and litai verify pass.

- **Results:** The full regression/smoke suite and disposable retained harness each
  pass 90 tests. Coverage includes full-resolution automatic capture persistence,
  optional trimming, duplicate/late results, cancelled captures, failed-save retry,
  keyboard-only book creation and page editing, both capture accelerators, and
  unique button shortcuts. The 1180×800 Qt layout was inspected. CodeGraph is
  current and `litai verify` passes all four configured gates; HTML observability
  is not configured. This change uses simulated camera callbacks; a fresh hardware
  capture was not performed. `verification/current.json` records current evidence.

### [x] BOOKSCAN-005 — Portable shortcuts and single-book PDF export

- **Priority:** high
- **Owner:** components/legacy-project-wrapper
- **Direction:** Avoid requiring function keys; export one chosen book folder to one chosen PDF file including all pages.
- **Conclusion:** Use Ctrl+S for capture/save, Ctrl+Shift+R for camera refresh and Ctrl+H for shortcut help. Replace batch UI export with a book-folder chooser and PDF Save As dialog, resolving registered books by their exact image folder and preserving manifest page order.
- **Depends on:** none
- **Implementation:**
  - [x] Replace function-key-only shortcuts and update UI hints/help.
  - [x] Implement single-book folder selection and PDF output file selection with overwrite protection.
  - [x] Verify keyboard operation, folder resolution, complete PDF contents and cancellation/failure paths; refresh retained evidence.
- **Evidence:**
  - [x] Regression and smoke tests pass including actual PDF page count/order and no export of other books.
  - [x] CodeGraph, current retained receipt and litai verify pass.

- **Results:** Regression/smoke and disposable retained harness each pass 98
  tests. Keyboard events verify Ctrl+S capture and page-edit saving, Ctrl+H help,
  Ctrl+Shift+R refresh, and shortcut preservation across dynamic button labels.
  PDF fixtures verify exact chosen-book page count/order, selection of a different
  book than the current sidebar selection, custom folders, extension handling,
  overwrite approval/cancellation, both chooser cancellations, invalid/empty/shared
  folders, and safe output alongside images. Source images remain protected.
  CodeGraph is current; `verification/current.json` records current evidence and
  `litai verify` passes all four configured gates (HTML is not configured).

### [x] BOOKSCAN-006 — Derive PDF export source from selected book

- **Priority:** high
- **Owner:** components/legacy-project-wrapper
- **Direction:** Screenshot shows selected book folder is not used by PDF export.
- **Conclusion:** The selected sidebar book already owns an exact image folder and ordered pages. Export must use that book directly, skip redundant source-folder selection, and ask only for the PDF output filename/location. Require a nonempty selected book.
- **Depends on:** none
- **Implementation:**
  - [x] Use selected book as export authority and derive PDF default path from its folder.
  - [x] Update export UI tests, smoke workflow and user documentation.
- **Evidence:**
  - [x] Selected-book export, full ordered contents, disabled empty selection, cancellation and overwrite tests pass.
  - [x] Current retained receipt, CodeGraph and litai verify pass.

- **Results:** A native desktop screenshot confirmed the selected book's correct
  image folder was already displayed while the redundant export folder chooser
  caused the error. Export now uses the sidebar selection, including shared
  image folders, and suggests `<image-folder>/<safe-title>.pdf`. Full regression,
  smoke and disposable retained harness each pass 97 checks. Tests cover default
  and custom image folders, sidebar selection changes, ordered complete PDFs,
  shared folders without cross-book inclusion, disabled empty selection, Save As
  cancellation and overwrite confirmation. CodeGraph is current and `litai verify`
  passes all four configured gates; HTML observability is not configured.
