# Changelog

## Unreleased

- Initialized the project with Literate AI's specification-led lifecycle and durable
  user-directed work queue.

- BookScan: added camera-independent Qt workflow and CLI smoke checks; the full
  suite now has 54 tests.
- Adopted the application into Literate AI at the retained-source stage, preserving
  implementation and user content, with a current retained-harness receipt.
- Added CodeGraph 1.6.2 developer provisioning and source-intelligence integration.
- Kept root `make deps`, `make run`, `make check`, and `make smoke` entry points.

- BookScan: new default image folders use portable, collision-safe book titles
  instead of opaque IDs. The destination updates while typing; Browse and manual
  paths override it exactly, and Use default restores automatic naming. Existing
  books keep their image locations.

- BookScan: added an original book-and-scanner application icon, bundled it in
  Python wheels, and applied it to Qt windows. `make install` creates a per-user
  Linux desktop launcher with the same icon and matching Wayland application ID.

- BookScan: Capture now saves immediately after optional trimming; failed saves retain
  the image for retry. Added accelerators for all buttons, keyboard focus navigation,
  shortcut tooltips and F1 help. Saved pages remain editable with explicit Save.
