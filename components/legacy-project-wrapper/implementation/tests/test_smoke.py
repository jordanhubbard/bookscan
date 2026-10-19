"""One camera-independent desktop session, using only disposable books and files."""
import os
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication, QFileDialog

from bookscan.app import ScanWindow
from bookscan.library import Library


@pytest.fixture(scope='session')
def smoke_app():
    return QApplication.instance() or QApplication([])


def test_desktop_session_smoke(smoke_app, tmp_path, monkeypatch):
    # Disable physical-device discovery; input is a real PNG in a temporary folder.
    monkeypatch.setattr(ScanWindow, 'refresh_cameras', lambda self: None)
    library = Library(tmp_path / 'library')
    window = ScanWindow(library)
    window.show()
    try:
        smoke_app.processEvents()
        assert window.book_form.isVisible()
        assert QApplication.activeModalWidget() is None
        window.book_form.title.setText('First smoke book')
        window.book_form.folder.setText(str(tmp_path / 'scans'))
        window.book_form.submit_button.click()
        first = window.book
        assert first['title'] == 'First smoke book'
        image = QImage(240, 320, QImage.Format.Format_RGB32)
        image.fill('white')
        incoming = tmp_path / 'incoming.png'
        assert image.save(str(incoming))
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(incoming), 'Images'))
        for _ in range(2):
            window.import_button.click()
            assert window.capture_button.text() == 'Save'
            window.capture_button.click()
            assert window.capture_button.text() == 'Capture'
        window.pages.setCurrentRow(0)
        window.edit_page_button.click()
        window.rotate_button.click()
        window.capture_button.click()
        assert len(first['pages']) == 2
        window.new_book_button.click()
        window.book_form.title.setText('Second smoke book')
        assert window.book_form.destination.name == 'second-smoke-book'
        assert not window.book_form.destination.exists()
        window.book_form.submit_button.click()
        assert window.book['folder_name'] == 'second-smoke-book'
        window.import_button.click()
        window.capture_button.click()
        output = tmp_path / 'first-book.pdf'
        window.books.setCurrentRow(0)
        assert window.book is first
        monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: pytest.fail('Selected book already has an image folder'))
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (str(output), 'PDF files (*.pdf)'))
        window.export_button.click()
        assert 'all 2 pages' in window.status.text()
        reopened = Library(library.root)
        assert [len(book['pages']) for book in reopened.books] == [2, 1]
        document = QPdfDocument()
        assert document.load(str(output)) == QPdfDocument.Error.None_
        assert document.pageCount() == 2
        assert document.pagePointSize(0).width() > document.pagePointSize(0).height()
        document.close()
        assert list(tmp_path.glob('*.pdf')) == [output]
        assert len(list((tmp_path / 'scans').glob('*.png'))) == 2
        window.done_button.click()
        assert not window.isVisible()
    finally:
        window.pending = QImage()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_cli_entrypoint_smoke():
    result = subprocess.run([sys.executable, '-m', 'bookscan', '--help'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--library' in result.stdout
