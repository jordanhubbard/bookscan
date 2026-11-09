# Getting started

[Project guide](../README.md) → getting started

BookScan scans books using a camera, supports page editing and reordering, and
exports one selected book to PDF. It stores library metadata and PNG images on
your computer. It needs Python 3.10 or later, a graphical desktop, and PySide6.
A camera is optional when importing existing images.

## Installation

On Ubuntu/Debian, install Python environment support and Qt's native runtime
libraries before installing the Python package:

```sh
sudo apt-get install python3-venv libegl1 libopengl0 libgl1 libxkbcommon0 libpulse0 libxcb-cursor0 libxkbcommon-x11-0
```

`libpulse0` is required by Qt Multimedia even when scanning without audio.
A normal desktop usually already supplies these libraries. From a checkout on Linux:

```sh
make install
```

The command bootstraps the developer environment when absent, builds wheel and
source artifacts, installs the wheel and dependencies into
`~/.local/share/bookscan/venv`, and registers BookScan in the applications menu.
Install Python's venv support first if your distribution packages it separately.
Package installation needs access to PyPI; ordinary scanning needs no account or
network connection. Run `make deps` to repair an old developer environment after
an interpreter upgrade. `make deps-tools` installs optional CodeGraph tooling.

Launch **BookScan** from the applications menu; on GNOME, use **Add to Favorites**
to pin it to the dock. The window should show books, camera selection and capture
controls. The default library is `Documents/BookScan`; custom image directories
remain where you chose them. Allow camera access in desktop privacy settings and
ensure your Linux user can access the video device.

To upgrade, close BookScan, update the checkout, and rerun `make install`.
To roll back, install a previous release wheel into the same application environment.
To uninstall, remove `~/.local/share/bookscan/venv`,
`~/.local/share/applications/bookscan.desktop`, and
`~/.local/share/pixmaps/bookscan.png`, then remove its dock favorite.
Keep the library and external image folders unless you intend to delete scans.

## Usage

Create or select a book. Capture with Ctrl+S, or import an existing image with
Ctrl+O and save it. Select a saved page to review, edit, or reorder it. Export the
selected book with Ctrl+P and choose the output PDF filename. Reopen the library
to confirm saved pages persist. See the root `README.md` application guide for
shortcuts, image folder rules, and recovery behavior.

## Development workflow

Application source remains authoritative under
`components/legacy-project-wrapper/implementation`. Run `make check` for the
regression suite and `make build` for distributions. `litai verify` checks project
authority and retained test evidence. See the [framework flow](framework-flow.md)
for the adopted project lifecycle.
