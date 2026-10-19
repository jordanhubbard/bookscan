# BookScan

## Goals

Provide a Qt desktop workflow for scanning and organizing books: one-step capture and save,
optional black-background trimming, image editing, book folders, page and book
management, and one complete PDF per book. New books use portable title-based
image subfolders with a live destination preview and exact Browse override. Preserve user scans across sessions.

## Dependencies

Literate AI manages retained application source and its test evidence. The desktop
runtime requires Python and Qt (PySide6). CodeGraph is an explicit project tooling
dependency for source navigation, not a prerequisite for running the desktop app.

## Completeness

The existing Python application implements the scanning workflow, inline book forms,
rotation/cropping/zoom, folders, deletion confirmations and PDF export. Its regression and smoke
suite covers capture, editing, keyboard operation and persistence. Literate AI adoption is complete at the retained-source stage, with a current
current retained evidence and four verification gates; hardware coverage is limited to the previously tested NETUM USB camera.

The application icon is packaged for Qt windows and the per-user Linux launcher;
`make install` installs desktop integration.

## Current work

See [active work](docs/roadmap/active-work.md). BOOKSCAN-001 is complete; BOOKSCAN-002 is complete with portable title folders, live preview, and exact Browse overrides. Native
regeneration remains a separate, deferred program; existing source is authoritative.

BOOKSCAN-003 adds the packaged icon and Linux desktop launcher.

## Completed work

See [changelog](CHANGELOG.md).

BOOKSCAN-004 adds immediate capture saving and full button keyboard accelerators.
