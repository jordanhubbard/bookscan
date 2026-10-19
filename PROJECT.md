# BookScan

## Goals

Provide a Qt desktop workflow for scanning and organizing books: capture/review/save,
optional black-background trimming, image editing, book folders, page and book
management, and one complete PDF per book. Preserve user scans across sessions.

## Dependencies

Literate AI manages retained application source and its test evidence. The desktop
runtime requires Python and Qt (PySide6). CodeGraph is an explicit project tooling
dependency for source navigation, not a prerequisite for running the desktop app.

## Completeness

The existing Python application implements the scanning workflow, inline book forms,
rotation/cropping/zoom, folders, deletion confirmations and PDF export. Its regression
suite currently contains 52 checks. End-to-end smoke and Literate AI adoption are in
progress; hardware coverage is limited to the previously tested NETUM USB camera.

## Current work

See [active work](docs/roadmap/active-work.md).

## Completed work

See [changelog](CHANGELOG.md).
