"""Durable book collections. Only explicitly accepted images are stored."""
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSaveFile, QIODevice, QSizeF, QRectF, QMarginsF, QFile
from PySide6.QtGui import QImage, QPageSize, QPainter, QPdfWriter


_WINDOWS_DEVICE_NAMES = {'con', 'prn', 'aux', 'nul'} | {
    f'{prefix}{number}' for prefix in ('com', 'lpt') for number in range(1, 10)
}


def portable_book_name(title):
    """A bounded ASCII folder component safe on Windows and Unix."""
    text = ''.join(character for character in unicodedata.normalize('NFKD', title)
                   if not unicodedata.combining(character))
    name = re.sub(r'[^a-zA-Z0-9]+', '-', text).strip('-').lower()[:64].rstrip('-') or 'book'
    if name in _WINDOWS_DEVICE_NAMES:
        name = f'book-{name}'
    return name


class Library:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "library.json"
        self.data = {"version": 1, "books": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if self.data.get("version") != 1 or not isinstance(self.data.get("books"), list):
                raise ValueError("Unsupported or invalid library manifest")
            for book in self.books:
                if not isinstance(book.get("title"), str) or not isinstance(book.get("pages"), list):
                    raise ValueError("Invalid book metadata")
                if "image_folder" in book and (not isinstance(book["image_folder"], str) or
                                                not Path(book["image_folder"]).is_absolute()):
                    raise ValueError("Invalid book image folder")
                if 'folder_name' in book and (not isinstance(book['folder_name'], str) or
                                               portable_book_name(book['folder_name']) != book['folder_name']):
                    raise ValueError("Invalid book subfolder name")
                for page in book["pages"]:
                    self.page_path(page)

    @property
    def books(self):
        return self.data["books"]

    def save(self):
        target = QSaveFile(str(self.path))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        payload = json.dumps(self.data, ensure_ascii=False, indent=2).encode("utf-8")
        if target.write(payload) != len(payload) or not target.commit():
            raise OSError(target.errorString())

    def new_book_folder(self, title):
        """Preview only: never create directories while the user types."""
        base = self.root / 'books'
        if not base.resolve().is_relative_to(self.root):
            raise ValueError("The default books folder must be inside the library")
        used = {entry.name.casefold() for entry in base.iterdir()} if base.exists() else set()
        used.update(self.image_folder(book).name.casefold() for book in self.books
                    if self.image_folder(book).parent == base)
        stem = portable_book_name(title)
        name, counter = stem, 2
        while name.casefold() in used:
            suffix = f'-{counter}'
            name = stem[:64 - len(suffix)].rstrip('-') + suffix
            counter += 1
        return base / name

    def add_book(self, title, kind="Other", author="", image_folder=None, expected_folder=None):
        title = title.strip()
        if not title:
            raise ValueError("Enter a book title")
        book = {"id": uuid4().hex, "title": title, "kind": kind,
                "author": author.strip(), "pages": []}
        custom = image_folder and str(image_folder).strip()
        created = False
        if custom:
            folder = Path(image_folder).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            book['image_folder'] = str(folder)
        else:
            folder = self.new_book_folder(title)
            if expected_folder is not None and Path(expected_folder) != folder:
                raise ValueError("That default folder is no longer available. Review the updated destination and create the book again.")
            # Reserve the previewed name without merging into an existing folder.
            try:
                folder.mkdir(parents=True, exist_ok=False)
            except FileExistsError as exc:
                raise ValueError("The destination was just created elsewhere. Review the updated destination and retry.") from exc
            created = True
            book['folder_name'] = folder.name
        try:
            with tempfile.TemporaryFile(dir=folder):
                pass
            self.books.append(book)
            try:
                self.save()
            except Exception:
                self.books.remove(book)
                raise
        except Exception:
            if created:
                try:
                    folder.rmdir()
                except OSError:
                    pass
            raise
        return book

    def page_path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            allowed = Path(relative).is_absolute() and any(
                path.is_relative_to(Path(book["image_folder"]).resolve())
                for book in self.books if book.get("image_folder"))
            if not allowed:
                raise ValueError("Page path is outside the library and its book folders")
        return path

    def image_folder(self, book):
        return Path(book["image_folder"]) if book.get("image_folder") else self.root / "books" / book.get('folder_name', book["id"])

    def update_book(self, book, title, kind, author):
        if book not in self.books:
            raise ValueError("This book is no longer in the library")
        if not title.strip():
            raise ValueError("Enter a book title")
        previous = dict(book)
        book.update(title=title.strip(), kind=kind, author=author.strip())
        try:
            self.save()
        except Exception:
            book.clear()
            book.update(previous)
            raise

    def remove_book(self, book, delete_images=False):
        index = self.books.index(book)
        images = {self.page_path(page) for page in book['pages']} if delete_images else set()
        shared = {self.page_path(page) for other in self.books if other is not book for page in other['pages']}
        self.books.pop(index)
        try:
            self.save()
        except Exception:
            self.books.insert(index, book)
            raise
        # Only touch images after the manifest commits. A failed metadata save
        # leaves both the book and all original files intact.
        report = {'deleted': 0, 'shared': len(images & shared), 'failed': []}
        for path in sorted(images - shared):
            if not path.exists():
                continue
            try:
                result = QFile.moveToTrash(str(path))
                success = result[0] if isinstance(result, tuple) else result
                if not success:
                    raise OSError('Could not move image to Trash')
                report['deleted'] += 1
            except Exception as exc:
                report['failed'].append((str(path), str(exc)))
        return report

    def remove_page(self, book, index):
        if book not in self.books:
            raise ValueError("This book is no longer in the library")
        page = book['pages'].pop(index)
        try:
            self.save()
        except Exception:
            book['pages'].insert(index, page)
            raise

    def update_page(self, book, index, image):
        if book not in self.books:
            raise ValueError("This book is no longer in the library")
        if image.isNull():
            raise ValueError("The page image is empty")
        path = self.page_path(book['pages'][index])
        if not path.is_file():
            raise OSError("The original page image is unavailable")
        target = QSaveFile(str(path))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        if not image.save(target, "PNG") or not target.commit():
            raise OSError("Could not update the page image")

    def accept(self, book, image):
        if image.isNull():
            raise ValueError("The snapshot is empty")
        folder = self.image_folder(book)
        if book.get("image_folder") or book.get('folder_name'):
            if not folder.is_dir():
                raise OSError(f"The book's image folder is unavailable: {folder}. Reconnect it and retry Save.")
        else:
            folder.mkdir(parents=True, exist_ok=True)
        filename = f"page-{len(book['pages']) + 1:04d}-{uuid4().hex}.png"
        relative = str(folder / filename) if book.get("image_folder") else (folder / filename).relative_to(self.root).as_posix()
        target = QSaveFile(str(self.page_path(relative)))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        if not image.save(target, "PNG") or not target.commit():
            raise OSError("Could not save the page image")
        book["pages"].append(relative)
        try:
            self.save()
        except Exception:
            book["pages"].pop()
            self.page_path(relative).unlink(missing_ok=True)
            raise
        return relative

    def pdf_exports(self, folder):
        """Plan distinct, stable filenames for every nonempty book."""
        folder = Path(folder).expanduser().resolve()
        if folder.is_relative_to(self.root / "books"):
            raise ValueError("Choose an export folder outside the stored page images")
        exports = []
        used = set()
        for book in self.books:
            if not book["pages"]:
                continue
            title = re.sub(r'[^\w .()-]', '_', book['title']).strip(' .')[:100] or 'Book'
            identity = re.sub(r'[^a-zA-Z0-9]', '', book['id'])[:8] or 'book'
            stem = f"{title} - {identity}"
            name = f"{stem}.pdf"
            counter = 2
            while name.casefold() in used:
                name = f"{stem} ({counter}).pdf"
                counter += 1
            used.add(name.casefold())
            exports.append((book, folder / name))
        return exports

    def export_books(self, folder, overwrite=False):
        exports = self.pdf_exports(folder)
        if not overwrite:
            for _book, path in exports:
                if path.exists():
                    raise FileExistsError(f"PDF already exists: {path.name}")
        Path(folder).expanduser().mkdir(parents=True, exist_ok=True)
        saved, failed = [], []
        for book, path in exports:
            try:
                self.export_pdf(book, path)
                saved.append(path)
            except Exception as exc:
                failed.append((book['title'], str(exc)))
        return saved, failed

    def export_pdf(self, book, destination):
        if not book["pages"]:
            raise ValueError("Save at least one page before exporting")
        destination = Path(destination).resolve()
        source_images = {self.page_path(page) for item in self.books for page in item["pages"]}
        if destination == self.path or destination in source_images:
            raise ValueError("Choose a PDF filename different from the library metadata and page images")
        # Write to a sibling temp file; failed exports never replace an existing PDF.
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        painter = QPainter()
        writer = None
        try:
            writer = QPdfWriter(str(temporary))
            writer.setTitle(book["title"])
            writer.setCreator("BookScan")
            writer.setResolution(150)
            for index, relative in enumerate(book["pages"]):
                image = QImage(str(self.page_path(relative)))
                if image.isNull():
                    raise ValueError(f"Page {index + 1} is missing or unreadable")
                size = QSizeF(image.width() * 25.4 / 150, image.height() * 25.4 / 150)
                writer.setPageSize(QPageSize(size, QPageSize.Unit.Millimeter))
                writer.setPageMargins(QMarginsF(0, 0, 0, 0))
                if index == 0:
                    if not painter.begin(writer):
                        raise OSError("Could not create the PDF")
                elif not writer.newPage():
                    raise OSError("Could not add a PDF page")
                painter.drawImage(QRectF(0, 0, writer.width(), writer.height()), image)
            painter.end()
            writer = None
            os.replace(temporary, destination)
        finally:
            if painter.isActive():
                painter.end()
            writer = None
            temporary.unlink(missing_ok=True)
