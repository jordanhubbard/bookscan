# BookScan

<img src="bookscan/assets/bookscan.png" alt="BookScan application icon" width="128" />

A native Qt 6 application for scanning and organizing books with a camera or USB
document camera. Built with Python and PySide6; images remain on your computer.

## Run

Requires Python 3.10 or newer, a graphical desktop, and a Qt-compatible camera.
On Linux, allow your user access to the video device; on macOS/Windows, allow
camera access in system privacy settings. A USB document camera must expose a
standard camera feed supported by Qt.

```sh
cd /home/jkh/Src/bookscan
make deps
make run
```

To choose a different library folder:

```sh
.venv/bin/python -m bookscan --library /path/to/my-library
```

## Scan a session

1. Click **New book** (or Ctrl+N) to open the inline book form, or select an
   existing book in the sidebar to continue it. The form opens automatically for
   an empty library and never blocks the rest of the window. Enter a title,
   optionally specify author and type, then click **Create book**. Types include hardcover, paperback, textbook,
   notebook, magazine, and other. Each snapshot is one PDF page: a photographed
   two-page spread remains one image. As you type a new book title, **Images folder**
   and the destination preview update to a safe title-based subfolder in the library.
   For example, `My Book: Volume 1` becomes `books/my-book-volume-1/`. Spaces and
   punctuation become hyphens, accents are simplified, names use lowercase ASCII,
   and Windows device names receive a safe prefix. Names are limited to 64 characters;
   case-insensitive collisions receive `-2`, `-3`, and so on. Typing creates no folders.
   **Browse…** (or a manually entered path) overrides the exact destination; changing
   the title then leaves your choice alone. **Use default** restores the automatic
   destination. The app remembers the actual folder when you resume the book.
2. Select your camera and position the page in the live view. Click **Capture**
   (F6 or Ctrl+S) to capture and save immediately, then turn the page and repeat.
   Optional auto-trim runs before saving. **Cancel** (Escape) can abandon an
   in-progress capture; late camera results are discarded.
3. Select a saved page and use **Edit page** (Ctrl+E) to rotate or crop it, then
   **Save** (Ctrl+S). **Import image** (Ctrl+O) opens an existing photograph for
   review and editing before Save. If automatic saving fails, the image stays
   available so Save retries without taking another picture.
4. Use **Crop**, drag around the area to keep, then **Apply crop**. **Cancel crop**
   leaves the snapshot unchanged. **Reset edits** restores the original snapshot,
   including any area removed by cropping, until you save or cancel it.
5. **+**, **−**, and **Fit** adjust the preview zoom. You can also use the mouse
   wheel to zoom and drag to pan. While cropping, drag with the middle mouse button
   to pan. Zoom works on saved-page previews too; it does not change saved pixels.
6. Optionally enable **Auto-trim black background** before capturing or importing.
   It detects the nonblack page area, removes surrounding black mat, and keeps a
   small margin. Trimming uses original-resolution pixels. Camera captures save the trimmed
   result immediately. For imported images and unsaved edits, **Reset edits**
   restores the image from the start of that editing session. Detection requires a mostly black
   outer border and leaves ambiguous images unchanged. Dark pages, shadows, or
   uneven backgrounds may need manual cropping. This is rectangular trimming;
   it does not straighten perspective or curved pages.
7. Turn the page and repeat. Saved pages appear in order in the sidebar; click
   one to review it and use **Back to camera** to return to scanning.
8. **Next book** opens the inline form for another book. You can also select an
   existing book in the sidebar. **Done — save and quit** saves the
   library and exits. If a snapshot is awaiting review, choose whether to save,
   discard, or cancel. Saved pages remain on disk even if the app crashes.
9. **Export books to PDF** asks for a destination folder and generates one PDF
   per book in the library. Each PDF contains all saved images for that book in
   page order, one image per PDF page. Empty books are skipped. Filenames include
   the book title and an identifier so books with the same title stay separate.
   Exporting again asks before replacing existing PDFs. If a book cannot be
   exported, the app identifies it and still exports the other books. You can
   reopen BookScan later to resume scanning or export again.

The default library is `Documents/BookScan` (using Qt's platform Documents
location). `library.json` holds book metadata and ordered page references;
`books/<safe-title>/` holds saved PNG images for new books using default storage.
Existing books keep their prior folders, including older `books/<id>/` paths; editing
or renaming a book never relocates its images. Books with
an **Images folder** store PNGs there instead, with numbered unique filenames;
the library stores their folder and image references. Back up both the library
folder and any separately chosen image folders. Keep those folders at the same
paths when reopening a library with external image folders. Default title folders
and their page references remain relative to the library, so moving the entire
library together preserves them. If a folder is unavailable, reconnect it and
retry Save; the unsaved preview is retained. The footer shows the current book's
image folder.
Titles are metadata, so duplicate names and filesystem punctuation are safe.
A lock prevents two app instances from editing the same library simultaneously.

Camera snapshots use Qt's saved still image, preserving the full captured
resolution rather than saving the viewfinder thumbnail. Resolution and camera
compatibility depend on the device and Qt backend. Camera capture temporarily
writes the still image to the system temporary directory; it is deleted after
loading or on a normal exit. Captured pages are saved as PNG without
additional JPEG recompression. If a camera itself returns JPEG, that original
compression remains. Import also honors image orientation metadata.

This first version supports manual capture, rotation, rectangular cropping, zoom, book organization, and
image-based PDF export. It does not yet provide OCR, perspective correction,
curvature correction, spread splitting, page reordering, or voice
commands. “Next book” and “Done” are onscreen buttons. Book types are organizational
metadata; they do not apply different image processing.


## Manage books and pages

- Select a book and click **Edit** to change its title, author, or type in the
  inline form. Its image folder remains the one selected when the book was
  created. Click **Save book** to apply changes, or **Cancel** to discard them.
- Select a saved page and click **Edit page** to rotate or crop it. **Save**
  atomically updates that page's image in place, preserving its position and page
  count. **Cancel** leaves the saved image unchanged. Exported PDFs use the edited
  images.
- **Delete** beside the books and **Delete page** below the pages show popup
  confirmations with **Cancel** selected by default. Deleting a page removes it
  from the book and future exports while keeping its image file on disk.
- When deleting a book, the **Also delete this book's image files** checkbox is
  unchecked by default. Leave it unchecked to keep the images. If checked, the
  book's associated image files move to the system Trash; unrelated files, the
  folder itself, exported PDFs, and images referenced by other books are kept.
  If an image cannot be moved to Trash, the app identifies it as remaining on
  disk. Cancelling the popup changes nothing.
- Opening the book form preserves your draft while you use other controls. Save
  or cancel a pending snapshot before submitting book changes. Book creation
  errors appear in the form, preserving entered values for retry.
- The folder browser is also nonmodal. Form labels have keyboard mnemonics and
  controls follow the desktop palette, focus handling, and disabled-state style.

## Check

```sh
make check
make smoke
```

Tests exercise Qt widgets offscreen, Capture/Save/Cancel state, auto-trim, book isolation,
reopening, save failures, PDF page order/orientation, crop selection at different
zoom levels, rotation/reset, zoom/pan, saving edited pixels, and unfinished-review exit
choices. The attached NETUM USB camera was also checked end to end at 1920×1080:
capture, preview, immediate re-take, replacement capture, accept, reopen, PDF
export, and exit. That hardware check used Qt's offscreen platform; the window
layout was inspected separately with a rendered screenshot. Visible desktop
interaction and other cameras/platforms have not been verified.

Camera integration follows Qt's [QImageCapture](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QImageCapture.html)
and [QMediaCaptureSession](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QMediaCaptureSession.html) APIs.

The smoke target runs a complete camera-independent Qt session against temporary
books and files: create two books, import/save pages, edit a saved page, export one
PDF per book, reopen the library, and close cleanly. It also checks the CLI entry
point. It never opens your real library or claims to qualify physical camera input.

Developer setup includes the pinned CodeGraph 1.6.2 source-intelligence tool through
`make deps-tools` (also part of `make deps`). It installs into the user-local npm
prefix by default; keep its `bin` directory on PATH. CodeGraph is development
tooling, not a runtime dependency of the scanning application.

Generated folder components follow the conservative subset of Microsoft's
[Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
rules described above. A Browse override preserves the selected existing folder
exactly; the application does not rename its parent directories.

On Linux, `make install` installs the application icon and a per-user desktop
launcher. BookScan then appears in the desktop applications menu. The same icon
is bundled with the Python package and used for Qt application windows.

## Keyboard operation

Press **F1** or open **Help → Keyboard shortcuts** for the full list. Each button
also shows its accelerator in its tooltip. Tab / Shift+Tab moves between controls;
Space activates the focused button. Alt+B focuses books, Alt+P focuses pages,
and Alt+M focuses the camera selector; arrow keys change the selection.

| Action | Shortcut |
| --- | --- |
| Capture and save; save edits / retry | F6 or Ctrl+S |
| Cancel snapshot / edits; back to camera | Escape; Ctrl+L |
| New book; next book | Ctrl+N; Ctrl+Shift+N |
| Create / save book form; cancel form | Alt+Enter; Alt+C |
| Browse folder; restore default | Alt+O; Alt+D |
| Edit book; delete book | Ctrl+Shift+E; Ctrl+Shift+Delete |
| Edit page; delete page | Ctrl+E; Ctrl+Delete |
| Import; refresh cameras | Ctrl+O; F5 |
| Toggle auto-trim | Ctrl+T |
| Rotate left / right | Ctrl+[ / Ctrl+] |
| Crop / cancel crop; apply crop | Ctrl+R; Ctrl+Enter |
| Reset edits | Ctrl+Backspace |
| Zoom in / out; fit | Ctrl+= / Ctrl+-; Ctrl+0 |
| Export PDFs; save and quit | Ctrl+P; Ctrl+Q |

Crop selection and dragging to pan use the mouse. Deletion still requires
confirmation, and unavailable actions stay disabled for keyboard use too.
