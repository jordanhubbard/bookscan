# BookScan application icon

The final asset is
`components/legacy-project-wrapper/implementation/bookscan/assets/bookscan.png`.
It is a 1280 × 1280 RGBA PNG with transparent pixels outside the rounded tile.
The same source asset is packaged in Python wheels, used by Qt windows, and
installed with the Linux desktop launcher through `make install`.

Generated with the built-in `image_gen` tool on 2026-10-19, with
`transparent_background=true`. This was generation, not a CLI/API fallback or an
edit of third-party artwork. No subsequent visual editing was applied.

## Final generation prompt

Create one final production application icon for BookScan, a native desktop application for photographing book pages, trimming them, organizing books, and exporting PDFs. Deliver a single square high-resolution 1024x1024 PNG icon, not a presentation sheet or mockup. Design: a bold, beautifully simplified open book with warm ivory pages and a clear center fold, enclosed by four generous mint/teal document-scanner corner brackets. A single subtle teal scanning band crosses the book. Ground the symbol on a deep ink/navy rounded-square tile, with a transparent exterior outside the tile. The tile occupies about 90% of the square. Crisp graphic silhouettes, precise balanced geometry, handsome restrained depth and a subtle soft edge highlight; professional desktop application icon quality. Large readable forms; recognizable as a book being scanned at 32 pixels. No text, letters, words, numbers, tiny writing, camera lens, badge, or decorative objects. Avoid busy page lines, photographic textures, dramatic shadow, and fine details. Center the mark with ample consistent padding, strong contrast, and well-defined edges. Transparent pixels beyond the rounded-square tile. This is the actual icon asset, isolated, without a surrounding screen, preview frame, or sample sizes.

The tool returned a 1280-pixel image; that original is preserved. Qt performs
runtime icon scaling. The Linux launcher uses the same asset under the user's
XDG data directory and sets the desktop ID to `bookscan` for Wayland grouping.
Launcher quoting follows the [Desktop Entry specification](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html).
