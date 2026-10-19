import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer, QCoreApplication, QEvent, QPoint, QRectF, QSize
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from bookscan.app import BookForm, ScanWindow
from bookscan.library import Library


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def library(tmp_path, app):
    return Library(tmp_path / "library")


@pytest.fixture
def image():
    page = QImage(600, 800, QImage.Format.Format_RGB32)
    page.fill("white")
    return page


@pytest.fixture
def window(library, monkeypatch):
    monkeypatch.setattr(ScanWindow, "refresh_cameras", lambda self: None)
    window = ScanWindow(library, prompt=False)
    yield window
    window.pending = QImage()
    window.capture_id = None
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_durable_books_and_page_order(library, image):
    book = library.add_book("A / title?", "Hardcover", "An Author")
    first = library.accept(book, image)
    image.fill("blue")
    second = library.accept(book, image)
    other = library.add_book("Another book", "Notebook")
    library.accept(other, image)
    reopened = Library(library.root)
    assert len(reopened.books) == 2
    assert reopened.books[0]["pages"] == [first, second]
    assert QImage(str(library.page_path(first))).pixelColor(0, 0).name() == "#ffffff"
    assert QImage(str(library.page_path(second))).pixelColor(0, 0).name() == "#0000ff"
    assert reopened.books[0]["author"] == "An Author"


def test_accept_failure_preserves_manifest_and_no_orphan(library, image, monkeypatch):
    book = library.add_book("Test")
    def fail():
        raise OSError("disk full")
    monkeypatch.setattr(library, "save", fail)
    with pytest.raises(OSError, match="disk full"):
        library.accept(book, image)
    assert book["pages"] == []
    assert list((library.root / "books").rglob("*.png")) == []
    assert Library(library.root).books[0]["pages"] == []


def test_reject_invalid_input(library):
    with pytest.raises(ValueError):
        library.add_book("   ")
    book = library.add_book("Test")
    with pytest.raises(ValueError):
        library.accept(book, QImage())
    with pytest.raises(ValueError):
        library.page_path("../outside.png")


def test_corrupt_manifest_is_not_overwritten(library):
    library.path.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        Library(library.root)
    assert library.path.read_text() == "not json"


def test_pdf_page_order_and_sizes(library, image):
    book = library.add_book("PDF test")
    library.accept(book, image)
    second = QImage(800, 600, QImage.Format.Format_RGB32)
    second.fill("blue")
    library.accept(book, second)
    destination = library.root / "test.pdf"
    library.export_pdf(book, destination)
    document = QPdfDocument()
    assert document.load(str(destination)) == QPdfDocument.Error.None_
    assert document.pageCount() == 2
    assert document.pagePointSize(0).height() > document.pagePointSize(0).width()
    assert document.pagePointSize(1).width() > document.pagePointSize(1).height()
    assert document.render(1, second.size()).pixelColor(400, 300).blue() > 240
    document.close()


def test_failed_pdf_preserves_existing_export(library, image):
    book = library.add_book("Missing page")
    path = library.accept(book, image)
    library.page_path(path).unlink()
    destination = library.root / "existing.pdf"
    destination.write_bytes(b"keep me")
    with pytest.raises(ValueError, match="missing"):
        library.export_pdf(book, destination)
    assert destination.read_bytes() == b"keep me"
    assert list(library.root.glob("*.tmp")) == []


def test_preview_retake_and_accept(window, image, monkeypatch):
    window.book = window.library.add_book("Book one")
    window.refresh_books()
    window.present(image)
    assert window.book["pages"] == []
    assert window.capture_button.isEnabled()
    assert not window.books.isEnabled()
    # Re-take imports a replacement; the original never enters the book.
    window.source = "import"
    replacement = QImage(200, 300, QImage.Format.Format_RGB32)
    replacement.fill("blue")
    monkeypatch.setattr(window, "import_image", lambda: window.present(replacement))
    window.cancel_button.click()
    assert window.pending.isNull()
    assert window.capture_button.text() == "Capture"
    window.import_image()
    assert window.book["pages"] == []
    assert window.pending.size() == replacement.size()
    window.capture_button.click()
    assert len(window.book["pages"]) == 1
    assert window.pending.isNull()
    assert window.books.isEnabled()
    saved = QImage(str(window.library.page_path(window.book["pages"][0])))
    assert saved.size() == replacement.size()
    window.present(image)
    window.rotate_button.click()
    assert window.pending.width() == image.height()
    window.capture_button.click()
    assert len(Library(window.library.root).books[0]["pages"]) == 2
    window.review_page(0)
    assert window.stack.currentWidget() is window.preview
    assert not window.capture_button.isEnabled()


def test_switch_book_keeps_pages_separate(window, image):
    first = window.library.add_book("First")
    second = window.library.add_book("Second")
    window.refresh_books()
    window.select_book(0)
    window.present(image)
    window.accept_page()
    window.select_book(1)
    window.present(image)
    window.accept_page()
    assert len(first["pages"]) == len(second["pages"]) == 1
    assert first["pages"][0] != second["pages"][0]
    assert window.book == second


def test_failed_accept_keeps_preview(window, image, monkeypatch):
    window.book = window.library.add_book("Test")
    window.present(image)
    monkeypatch.setattr(window, "error", lambda message: None)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(window.library, "accept", fail)
    assert not window.accept_page()
    assert not window.pending.isNull()
    assert window.capture_button.isEnabled()


@pytest.mark.parametrize("choice,accepted,allowed", [("Save and continue", 1, True), ("Discard snapshot", 0, True), ("Cancel", 0, False)])
def test_pending_exit_choices(window, image, choice, accepted, allowed):
    window.book = window.library.add_book("Test")
    window.present(image)
    def click_choice():
        box = QApplication.activeModalWidget()
        button = next(b for b in box.buttons() if b.text().replace("&", "") == choice)
        button.click()
    QTimer.singleShot(0, click_choice)
    assert window.resolve_pending() == allowed
    assert len(window.book["pages"]) == accepted
    assert window.pending.isNull() == allowed


def test_inline_book_form_requires_title(window):
    window.choose_book()
    form = window.book_form
    assert not form.submit_button.isEnabled()
    form.title.setText('New')
    assert form.submit_button.isEnabled()
    form.submit_button.click()
    assert window.book['title'] == 'New'
    assert form.isHidden()
    assert QApplication.activeModalWidget() is None


def test_full_resolution_capture_and_cleanup(window, image, tmp_path):
    window.book = window.library.add_book("Camera test")
    capture_path = tmp_path / "capture.png"
    image.save(str(capture_path))
    window.capture_id = 17
    window.snapshot_saved(17, str(capture_path))
    assert window.capture_id is None
    assert not capture_path.exists()
    assert window.pending.size() == image.size()
    assert not window.book["pages"]


def test_cancel_inflight_capture_ignores_late_image(window, image, tmp_path):
    window.book = window.library.add_book("Camera")
    window.capture_id = 19
    window.timeout.start()
    window.update_controls()
    assert window.cancel_button.isEnabled()
    assert not window.capture_button.isEnabled()
    window.cancel_button.click()
    assert window.capture_id is None
    assert not window.timeout.isActive()
    late_image = tmp_path / "late.png"
    image.save(str(late_image))
    window.snapshot_saved(19, str(late_image))
    assert window.pending.isNull()
    assert not late_image.exists()
    assert not window.book['pages']


@pytest.mark.parametrize('reverse,zoom', [(False, 1), (True, 1), (False, 2)])
def test_drag_crop_saves_full_resolution_region(window, image, reverse, zoom):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter
    painter = QPainter(image)
    painter.fillRect(0, 0, 300, 800, 'blue')
    painter.end()
    window.book = window.library.add_book('Crop test')
    window.present(image)
    window.preview.setFixedSize(400, 300)
    window.show()
    QApplication.processEvents()
    window.preview.set_zoom(zoom)
    window.crop_button.click()
    assert not window.capture_button.isEnabled()
    target = window.preview.image_rect()
    start = QPoint(round(target.center().x() - 50), round(target.center().y() - 60))
    end = QPoint(round(target.center().x() + 70), round(target.center().y() + 50))
    if reverse:
        start, end = end, start
    QTest.mousePress(window.preview, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.preview, end)
    QTest.mouseRelease(window.preview, Qt.MouseButton.LeftButton, pos=end)
    rect = window.preview.crop_rect()
    assert rect.width() > 100 and rect.height() > 100
    assert window.apply_crop_button.isEnabled()
    assert abs(rect.width() - 120 * image.width() / target.width()) < 3
    expected = image.copy(rect)
    window.apply_crop_button.click()
    assert window.pending == expected
    assert not window.preview.cropping
    assert window.capture_button.text() == 'Save'
    window.capture_button.click()
    stored = QImage(str(window.library.page_path(window.book['pages'][0])))
    assert stored == expected
    window.library.export_pdf(window.book, window.library.root / 'cropped.pdf')
    document = QPdfDocument()
    assert document.load(str(window.library.root / 'cropped.pdf')) == QPdfDocument.Error.None_
    size = document.pagePointSize(0)
    assert abs(size.width() / size.height() - expected.width() / expected.height()) < 0.02
    document.close()


def test_crop_cancel_reset_and_both_rotation_directions(window, image):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.book = window.library.add_book('Edit test')
    window.present(image)
    window.rotate_left_button.click()
    assert window.pending.size() == QSize(800, 600)
    window.rotate_button.click()
    assert window.pending == image
    window.crop_button.click()
    window.preview.selection = QRectF(20, 30, 100, 200)
    window.crop_button.click()  # Cancel crop
    assert window.pending == image
    window.crop_button.click()
    window.preview.selection = QRectF(20, 30, 100, 200)
    window.apply_crop()
    assert window.pending.size() == QSize(100, 200)
    window.rotate_button.click()
    window.reset_button.click()
    assert window.pending == image
    assert window.original == image
    assert not window.book['pages']


def test_zoom_pan_fit_preserves_saved_pixels(window, image):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.book = window.library.add_book('Zoom test')
    window.present(image)
    window.show()
    QApplication.processEvents()
    window.zoom_in_button.click()
    window.zoom_in_button.click()
    assert window.preview.zoom == 1.5625
    assert window.zoom_label.text() == '156%'
    rect = window.preview.image_rect()
    center = window.preview.rect().center()
    QTest.mousePress(window.preview, Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseMove(window.preview, center + QPoint(0, 30))
    QTest.mouseRelease(window.preview, Qt.MouseButton.LeftButton, pos=center + QPoint(0, 30))
    assert window.preview.image_rect().y() > rect.y()
    window.zoom_out_button.click()
    assert window.preview.zoom == 1.25
    window.fit_button.click()
    assert window.preview.zoom == 1
    assert window.preview.pan.isNull()
    assert not window.zoom_out_button.isEnabled()
    assert window.pending == image
    window.capture_button.click()
    stored = QImage(str(window.library.page_path(window.book['pages'][0])))
    assert stored == image
    window.review_page(0)
    assert window.zoom_in_button.isEnabled()
    assert not window.crop_button.isEnabled()


def test_batch_pdf_exports_one_complete_pdf_per_book(library, image):
    first = library.add_book('My / Book', 'Hardcover')
    second = library.add_book('My / Book', 'Notebook')
    library.add_book('Empty book')
    colors = [('red', 'blue', 'green'), ('yellow', 'purple')]
    for book, sequence in zip([first, second], colors):
        for color in sequence:
            image.fill(color)
            library.accept(book, image)
    folder = library.root / 'exports'
    saved, failed = library.export_books(folder)
    assert not failed
    assert len(saved) == 2
    assert len(set(saved)) == 2
    assert len(list(folder.glob('*.pdf'))) == 2
    assert all(path.parent == folder for path in saved)
    from PySide6.QtGui import QColor
    for path, sequence in zip(saved, colors):
        document = QPdfDocument()
        assert document.load(str(path)) == QPdfDocument.Error.None_
        assert document.pageCount() == len(sequence)
        for index, color in enumerate(sequence):
            actual = document.render(index, QSize(60, 80)).pixelColor(30, 40)
            expected = QColor(color)
            assert max(abs(a - b) for a, b in zip(actual.getRgb()[:3], expected.getRgb()[:3])) < 8
        document.close()
    assert [path for _book, path in library.pdf_exports(folder)] == saved


def test_batch_export_does_not_overwrite_without_approval(library, image):
    first = library.add_book('First')
    second = library.add_book('Second')
    library.accept(first, image)
    library.accept(second, image)
    folder = library.root / 'exports'
    folder.mkdir()
    plan = library.pdf_exports(folder)
    plan[1][1].write_bytes(b'Existing export')
    with pytest.raises(FileExistsError):
        library.export_books(folder)
    assert not plan[0][1].exists()  # Check conflicts before exporting any books.
    assert plan[1][1].read_bytes() == b'Existing export'
    saved, failed = library.export_books(folder, overwrite=True)
    assert len(saved) == 2 and not failed
    assert plan[1][1].read_bytes().startswith(b'%PDF')


def test_batch_export_reports_failed_book_and_exports_other_books(library, image):
    broken = library.add_book('Missing images')
    path = library.accept(broken, image)
    library.page_path(path).unlink()
    good = library.add_book('Good book')
    library.accept(good, image)
    saved, failed = library.export_books(library.root / 'exports')
    assert len(saved) == 1
    assert len(failed) == 1 and failed[0][0] == broken['title']
    assert 'missing' in failed[0][1]
    assert len(list((library.root / 'exports').glob('*.pdf'))) == 1


def test_export_button_exports_entire_library(window, image, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    first = window.library.add_book('First')
    second = window.library.add_book('Second')
    window.library.accept(first, image)
    window.library.accept(first, image)
    window.library.accept(second, image)
    window.book = second
    window.refresh_books()
    window.update_controls()
    folder = tmp_path / 'pdfs'
    folder.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(folder))
    window.export_button.click()
    assert len(list(folder.glob('*.pdf'))) == 2
    assert 'Exported 2 PDF(s)' in window.status.text()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Cancel)
    contents = {p.name: p.read_bytes() for p in folder.glob('*.pdf')}
    window.export_button.click()
    assert contents == {p.name: p.read_bytes() for p in folder.glob('*.pdf')}


def test_export_folder_cannot_contain_source_images(library, image):
    book = library.add_book('Test')
    library.accept(book, image)
    with pytest.raises(ValueError, match='outside'):
        library.export_books(library.root / 'books' / book['id'])


def test_one_button_captures_then_saves(window, image, tmp_path, monkeypatch):
    from types import SimpleNamespace
    window.book = window.library.add_book('Shared button')
    window.camera = SimpleNamespace(stop=lambda: None)
    monkeypatch.setattr(window.capture, 'isReadyForCapture', lambda: True)
    calls = []
    monkeypatch.setattr(window.capture, 'captureToFile', lambda filename: calls.append(filename) or 7)
    window.update_controls()
    button = window.capture_button
    assert button.text() == 'Capture'
    assert not window.cancel_button.isEnabled()
    button.click()
    assert window.capture_id == 7
    assert len(calls) == 1
    assert not button.isEnabled()
    assert not window.book['pages']
    path = tmp_path / 'camera.png'
    image.save(str(path))
    window.snapshot_saved(7, str(path))
    assert button.text() == 'Save'
    assert button.isEnabled()
    assert window.cancel_button.isEnabled()
    button.click()
    assert len(window.book['pages']) == 1
    assert button.text() == 'Capture'
    assert button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert len(calls) == 1  # The second click saved rather than capturing again.


@pytest.fixture
def black_mat_image():
    from PySide6.QtGui import QPainter
    image = QImage(1920, 1080, QImage.Format.Format_RGB32)
    image.fill('#151515')
    painter = QPainter(image)
    painter.fillRect(300, 100, 1300, 850, '#fff4db')
    painter.end()
    return image


def test_auto_trim_finds_page_at_original_resolution(black_mat_image):
    from bookscan.imaging import black_background_rect
    rect = black_background_rect(black_mat_image)
    assert 285 <= rect.left() <= 300
    assert 85 <= rect.top() <= 100
    assert 1599 <= rect.right() <= 1615
    assert 949 <= rect.bottom() <= 965
    assert rect.contains(300, 100) and rect.contains(1599, 949)
    assert rect.width() > 1300  # Keep a safety margin around the paper.


@pytest.mark.parametrize('color', ['white', 'black', '#202020'])
def test_auto_trim_leaves_uniform_images_unchanged(color):
    from bookscan.imaging import black_background_rect
    image = QImage(900, 1200, QImage.Format.Format_RGB32)
    image.fill(color)
    assert black_background_rect(image) == image.rect()


def test_auto_trim_ignores_sparse_bright_noise(black_mat_image):
    from bookscan.imaging import black_background_rect
    black_mat_image.setPixelColor(1, 1, 'white')
    black_mat_image.setPixelColor(1900, 1050, 'white')
    rect = black_background_rect(black_mat_image)
    assert rect.left() > 280 and rect.top() > 80
    assert rect.right() < 1620 and rect.bottom() < 970


def test_auto_trim_is_optional_reversible_and_saved(window, black_mat_image):
    window.book = window.library.add_book('Trim test')
    assert not window.auto_trim.isChecked()
    window.present(black_mat_image)
    assert window.pending == black_mat_image
    window.cancel_button.click()
    window.auto_trim.setChecked(True)
    window.present(black_mat_image)
    assert window.pending.width() < black_mat_image.width()
    assert window.original == black_mat_image
    assert not window.auto_trim.isEnabled()
    window.reset_button.click()
    assert window.pending == black_mat_image
    window.cancel_button.click()
    assert not window.book['pages']
    assert window.auto_trim.isEnabled()
    window.present(black_mat_image)
    expected = QImage(window.pending)
    window.capture_button.click()
    stored = QImage(str(window.library.page_path(window.book['pages'][0])))
    assert stored == expected
    assert window.capture_button.text() == 'Capture'


def test_book_folder_saves_reopens_and_exports(library, image, tmp_path):
    folder = tmp_path / 'Scanned books' / 'My book'
    book = library.add_book('My book', image_folder=folder)
    first = library.accept(book, image)
    image.fill('blue')
    second = library.accept(book, image)
    assert len(list(folder.glob('*.png'))) == 2
    assert Path(first).parent == folder
    assert Path(first).name.startswith('page-0001-')
    assert Path(second).name.startswith('page-0002-')
    assert not (library.root / 'books' / book['id']).exists()
    reopened = Library(library.root)
    assert reopened.books[0]['image_folder'] == str(folder)
    assert reopened.page_path(second) == Path(second)
    assert QImage(str(reopened.page_path(second))).pixelColor(0, 0).name() == '#0000ff'
    saved, failed = reopened.export_books(tmp_path / 'PDFs')
    assert len(saved) == 1 and not failed
    document = QPdfDocument()
    assert document.load(str(saved[0])) == QPdfDocument.Error.None_
    assert document.pageCount() == 2
    document.close()


def test_book_folder_inline_form_browse_and_create(window, tmp_path):
    folder = tmp_path / 'Selected folder'
    folder.mkdir()
    window.choose_book()
    form = window.book_form
    form.title.setText('Selected book')
    form.browse_folder_button.click()
    assert not form.folder_picker.isModal()
    assert QApplication.activeModalWidget() is None
    form.folder_picker.setDirectory(str(folder))
    form.folder_picker.accept()
    assert form.folder.text() == str(folder)
    form.submit_button.click()
    assert window.book['image_folder'] == str(folder)
    assert str(folder) in window.location.text()
    window.edit_book()
    assert form.folder.isReadOnly()
    assert not form.browse_folder_button.isEnabled()


def test_custom_book_folder_review_and_switch(window, image, tmp_path):
    folder = tmp_path / 'External scans'
    book = window.library.add_book('External', image_folder=folder)
    window.library.accept(book, image)
    other = window.library.add_book('Default')
    window.refresh_books()
    window.select_book(0)
    assert str(folder) in window.location.text()
    window.review_page(0)
    assert window.preview.image == image
    window.select_book(1)
    assert str(window.library.image_folder(other)) in window.location.text()


def test_missing_book_folder_keeps_unsaved_preview(window, image, tmp_path, monkeypatch):
    folder = tmp_path / 'Removable drive'
    window.book = window.library.add_book('Disconnected', image_folder=folder)
    folder.rmdir()
    window.present(image)
    errors = []
    monkeypatch.setattr(window, 'error', errors.append)
    assert not window.accept_page()
    assert 'unavailable' in errors[0]
    assert window.pending == image
    assert not window.book['pages']
    assert not folder.exists()
    folder.mkdir()
    assert window.accept_page()
    assert len(list(folder.glob('*.png'))) == 1


def test_failed_manifest_save_rolls_back_external_image(library, image, tmp_path, monkeypatch):
    folder = tmp_path / 'External'
    book = library.add_book('Rollback', image_folder=folder)
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(library, 'save', fail)
    with pytest.raises(OSError, match='disk full'):
        library.accept(book, image)
    assert not book['pages']
    assert not list(folder.iterdir())


def test_invalid_folder_and_external_source_overwrite_protection(library, image, tmp_path):
    invalid = tmp_path / 'file-not-directory'
    invalid.write_text('keep')
    with pytest.raises(OSError):
        library.add_book('Invalid', image_folder=invalid)
    assert not library.books
    book = library.add_book('External', image_folder=tmp_path / 'External')
    source = library.accept(book, image)
    contents = Path(source).read_bytes()
    with pytest.raises(ValueError):
        library.export_pdf(book, source)
    assert Path(source).read_bytes() == contents


def test_inline_form_draft_does_not_block_other_controls(window, image):
    first = window.library.add_book('First')
    second = window.library.add_book('Second')
    window.library.accept(first, image)
    window.refresh_books()
    window.show()
    window.new_book_button.click()
    window.book_form.title.setText('Unfinished draft')
    window.books.setCurrentRow(0)
    window.pages.setCurrentRow(0)
    assert window.preview.image == image
    assert window.book_form.title.text() == 'Unfinished draft'
    window.books.setCurrentRow(1)
    assert window.book == second
    assert window.book_form.isVisible()
    assert window.import_button.isEnabled()
    assert QApplication.activeModalWidget() is None
    window.present(image)
    assert not window.book_form.submit_button.isEnabled()
    window.cancel_button.click()
    assert window.book_form.submit_button.isEnabled()
    assert window.book_form.title.text() == 'Unfinished draft'


def test_inline_creation_error_preserves_draft(window, tmp_path):
    invalid = tmp_path / 'not-a-folder'
    invalid.write_text('file')
    window.choose_book()
    window.book_form.title.setText('Keep draft')
    window.book_form.folder.setText(str(invalid))
    window.book_form.submit_button.click()
    assert not window.library.books
    assert window.book_form.title.text() == 'Keep draft'
    assert not window.book_form.error_label.isHidden()
    assert QApplication.activeModalWidget() is None


def test_edit_book_metadata_preserves_folder_and_images(window, image, tmp_path):
    book = window.library.add_book('Original', image_folder=tmp_path / 'Scans')
    page = window.library.accept(book, image)
    window.refresh_books()
    window.select_book(0)
    window.edit_book_button.click()
    form = window.book_form
    form.title.setText('Renamed')
    form.author.setText('New author')
    form.kind.setCurrentText('Magazine')
    form.submit_button.click()
    saved = Library(window.library.root).books[0]
    assert saved['title'] == 'Renamed' and saved['author'] == 'New author'
    assert saved['kind'] == 'Magazine'
    assert saved['pages'] == [page]
    assert saved['image_folder'] == str(tmp_path / 'Scans')
    assert QImage(page) == image


def test_edit_saved_page_cancel_then_save_updates_in_place(window, image):
    window.book = window.library.add_book('Page editing')
    original_path = window.library.accept(window.book, image)
    window.refresh_books()
    window.pages.setCurrentRow(0)
    assert window.edit_page_button.isEnabled()
    window.edit_page_button.click()
    assert window.editing_page == 0
    window.rotate_button.click()
    window.cancel_button.click()
    assert QImage(str(window.library.page_path(original_path))) == image
    window.pages.setCurrentRow(-1)
    window.pages.setCurrentRow(0)
    window.edit_page_button.click()
    window.rotate_button.click()
    rotated = QImage(window.pending)
    window.capture_button.click()
    assert window.book['pages'] == [original_path]
    assert QImage(str(window.library.page_path(original_path))) == rotated
    assert window.editing_page is None
    assert len(Library(window.library.root).books[0]['pages']) == 1
    destination = window.library.root / 'updated.pdf'
    window.library.export_pdf(window.book, destination)
    document = QPdfDocument()
    document.load(str(destination))
    assert document.pageCount() == 1
    assert document.pagePointSize(0).width() > document.pagePointSize(0).height()
    document.close()


def answer_delete_popup(confirm=True, delete_images=False, inspect=None):
    def answer():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        if inspect:
            inspect(dialog)
        if dialog.checkBox():
            assert not dialog.checkBox().isChecked()
            dialog.checkBox().setChecked(delete_images)
        button = next(button for button in dialog.buttons()
                      if (button.text().replace('&', '').startswith('Delete') if confirm
                          else button.text().replace('&', '') == 'Cancel'))
        button.click()
    QTimer.singleShot(0, answer)


def test_popup_delete_page_and_book_keeps_files_by_default(window, image):
    book = window.library.add_book('Remove test')
    first = window.library.accept(book, image)
    second = window.library.accept(book, image)
    window.book = book
    window.refresh_books()
    window.pages.setCurrentRow(0)
    answer_delete_popup(confirm=False)
    window.remove_page_button.click()
    assert len(book['pages']) == 2
    answer_delete_popup()
    window.remove_page_button.click()
    assert book['pages'] == [second]
    assert window.library.page_path(first).exists()
    answer_delete_popup()
    window.remove_book_button.click()
    assert window.book is None
    assert not Library(window.library.root).books
    assert (window.library.root / second).exists()
    assert QApplication.activeModalWidget() is None


@pytest.mark.parametrize('operation', ['update_book', 'remove_page', 'remove_book'])
def test_failed_crud_manifest_write_rolls_back(library, image, monkeypatch, operation):
    book = library.add_book('Keep me')
    page = library.accept(book, image)
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(library, 'save', fail)
    with pytest.raises(OSError, match='disk full'):
        if operation == 'update_book':
            library.update_book(book, 'Changed', 'Magazine', 'Author')
        elif operation == 'remove_page':
            library.remove_page(book, 0)
        else:
            library.remove_book(book)
    assert library.books == [book]
    assert book['title'] == 'Keep me'
    assert book['pages'] == [page]
    assert Library(library.root).books[0]['title'] == 'Keep me'


def test_failed_saved_page_update_keeps_preview_and_original(window, image, monkeypatch):
    window.book = window.library.add_book('Failed edit')
    page = window.library.accept(window.book, image)
    window.refresh_books()
    window.pages.setCurrentRow(0)
    window.edit_page_button.click()
    window.rotate_button.click()
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(window.library, 'update_page', fail)
    monkeypatch.setattr(window, 'error', lambda message: None)
    assert not window.accept_page()
    assert window.editing_page == 0
    assert not window.pending.isNull()
    assert QImage(str(window.library.page_path(page))) == image


def test_popup_checked_deletes_only_associated_images(window, image, tmp_path, monkeypatch):
    from bookscan import library as library_module
    folder = tmp_path / 'Book and other files'
    book = window.library.add_book('Delete images', image_folder=folder)
    page = window.library.accept(book, image)
    unrelated = folder / 'unrelated.png'
    image.save(str(unrelated))
    trashed = []
    def trash(filename):
        trashed.append(filename)
        Path(filename).unlink()
        return True
    monkeypatch.setattr(library_module.QFile, 'moveToTrash', trash)
    window.book = book
    window.refresh_books()
    window.update_controls()
    answer_delete_popup(delete_images=True)
    window.remove_book_button.click()
    assert trashed == [page]
    assert not Path(page).exists()
    assert unrelated.exists() and folder.is_dir()
    assert not Library(window.library.root).books
    assert 'Moved 1 image(s) to Trash' in window.status.text()


def test_popup_cancel_checked_keeps_book_and_images(window, image, monkeypatch):
    from bookscan import library as library_module
    window.book = window.library.add_book('Cancel deletion')
    page = window.library.accept(window.book, image)
    window.refresh_books()
    window.update_controls()
    calls = []
    monkeypatch.setattr(library_module.QFile, 'moveToTrash', lambda filename: calls.append(filename) or True)
    answer_delete_popup(confirm=False, delete_images=True)
    window.remove_book_button.click()
    assert len(window.library.books) == 1
    assert window.library.page_path(page).exists()
    assert not calls


def test_delete_images_retains_shared_files(library, image, monkeypatch):
    from bookscan import library as library_module
    first = library.add_book('First')
    page = library.accept(first, image)
    second = library.add_book('Second')
    second['pages'].append(page)
    library.save()
    calls = []
    monkeypatch.setattr(library_module.QFile, 'moveToTrash', lambda filename: calls.append(filename) or True)
    report = library.remove_book(first, delete_images=True)
    assert report['shared'] == 1 and not calls
    assert library.page_path(page).exists()
    assert Library(library.root).books[0]['pages'] == [page]


def test_failed_manifest_save_never_deletes_images(library, image, monkeypatch):
    from bookscan import library as library_module
    book = library.add_book('Keep all')
    page = library.accept(book, image)
    calls = []
    monkeypatch.setattr(library_module.QFile, 'moveToTrash', lambda filename: calls.append(filename) or True)
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(library, 'save', fail)
    with pytest.raises(OSError, match='disk full'):
        library.remove_book(book, delete_images=True)
    assert not calls
    assert library.page_path(page).exists()
    assert Library(library.root).books[0]['title'] == 'Keep all'


def test_failed_trash_operation_reports_retained_images(window, image, monkeypatch):
    from bookscan import library as library_module
    window.book = window.library.add_book('Trash unavailable')
    page = window.library.accept(window.book, image)
    path = window.library.page_path(page)
    window.refresh_books()
    window.update_controls()
    monkeypatch.setattr(library_module.QFile, 'moveToTrash', lambda filename: False)
    answer_delete_popup(delete_images=True)
    window.remove_book_button.click()
    assert not Library(window.library.root).books
    assert path.exists()
    assert 'could not be deleted' in window.status.text()
    assert str(path) in window.status.text()


@pytest.mark.parametrize('title,expected', [
    ('My Book: Volume 1', 'my-book-volume-1'),
    ('  A   Book__Title... ', 'a-book-title'),
    ('../Unsafe/Title\\with:*?"<>|chars', 'unsafe-title-with-chars'),
    ('CON', 'book-con'), ('prn', 'book-prn'), ('AUX', 'book-aux'),
    ('NUL', 'book-nul'), ('COM1', 'book-com1'), ('LPT9', 'book-lpt9'),
    ('COM¹', 'book-com1'), ('LPT²', 'book-lpt2'),
    ('NUL.txt', 'nul-txt'), ('...', 'book'),
    ('Café déjà vu', 'cafe-deja-vu'), ('東京 📚', 'book'),
    ('a\x00b\nc\td', 'a-b-c-d'), ('-Leading', 'leading'),
    ('X' * 200, 'x' * 64),
])
def test_portable_book_folder_names(title, expected):
    from bookscan.library import portable_book_name
    import re
    name = portable_book_name(title)
    assert name == expected
    assert re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name)
    assert len(name) <= 64
    assert '/' not in name and '\\' not in name and '.' not in name


def test_named_default_folder_is_relative_and_survives_library_move(library, image, tmp_path):
    import shutil
    book = library.add_book('Travel Photos: 2026')
    assert library.image_folder(book) == library.root / 'books' / 'travel-photos-2026'
    assert 'image_folder' not in book
    reference = library.accept(book, image)
    assert reference.startswith('books/travel-photos-2026/')
    moved = tmp_path / 'relocated-library'
    shutil.copytree(library.root, moved)
    reopened = Library(moved)
    assert reopened.image_folder(reopened.books[0]) == moved / 'books' / 'travel-photos-2026'
    assert QImage(str(reopened.page_path(reference))) == image


def test_default_folder_collisions_are_case_insensitive_and_do_not_merge(library, image):
    parent = library.root / 'books'
    parent.mkdir()
    (parent / 'MY-BOOK').mkdir()
    first = library.add_book('My Book')
    second = library.add_book('My:Book')
    assert first['folder_name'] == 'my-book-2'
    assert second['folder_name'] == 'my-book-3'
    library.accept(first, image)
    assert not list((parent / 'MY-BOOK').iterdir())
    assert not list(library.image_folder(second).iterdir())
    # A missing folder still belongs to its book and cannot be silently reused.
    library.image_folder(second).rmdir()
    assert library.new_book_folder('My Book').name == 'my-book-4'


def test_live_default_preview_browse_override_and_restore(window, tmp_path):
    window.new_book_button.click()
    form = window.book_form
    form.title.setText('My Book: Volume 1')
    expected = window.library.root / 'books' / 'my-book-volume-1'
    assert form.destination == expected
    assert form.folder.text() == str(expected)
    assert str(expected) in form.folder_preview.text()
    assert not form.folder_overridden
    assert not expected.exists()  # Typing must have no filesystem side effects.
    custom = tmp_path / 'User selected folder'
    custom.mkdir()
    form.browse_folder_button.click()
    form.folder_picker.setDirectory(str(custom))
    form.folder_picker.accept()
    assert form.folder_overridden
    form.title.setText('Changed Book')
    assert form.destination == custom
    assert form.folder.text() == str(custom)
    form.default_folder_button.click()
    expected = window.library.root / 'books' / 'changed-book'
    assert form.destination == expected
    assert not form.folder_overridden
    form.submit_button.click()
    assert window.library.image_folder(window.book) == expected
    assert expected.is_dir()


def test_manual_folder_override_is_exact_and_previewed(window, tmp_path):
    window.choose_book()
    form = window.book_form
    form.title.setText('A Book')
    chosen = tmp_path / 'Chosen folder'
    form.folder.setText(str(chosen))
    form.title.setText('Another title')
    assert form.destination == chosen
    assert str(chosen) in form.folder_preview.text()
    form.submit_button.click()
    assert window.book['image_folder'] == str(chosen)
    assert chosen.is_dir()
    assert not (chosen / 'another-title').exists()


def test_default_folder_race_refreshes_preview_before_retry(window):
    window.choose_book()
    form = window.book_form
    form.title.setText('Collision')
    initial = form.destination
    initial.mkdir(parents=True)
    form.submit_button.click()
    assert not window.library.books
    assert form.destination == initial.with_name('collision-2')
    assert 'updated destination' in form.error_label.text()
    assert not form.destination.exists()
    form.submit_button.click()
    assert window.book['folder_name'] == 'collision-2'


def test_existing_id_based_book_keeps_original_folder(library, image):
    book = {'id': 'a' * 32, 'title': 'Old book', 'kind': 'Other', 'author': '', 'pages': []}
    library.books.append(book)
    library.save()
    reference = library.accept(book, image)
    assert reference.startswith('books/' + 'a' * 32 + '/')
    reopened = Library(library.root)
    assert reopened.image_folder(reopened.books[0]) == library.root / 'books' / ('a' * 32)
    library.update_book(book, 'New title', 'Notebook', '')
    assert library.image_folder(book).name == 'a' * 32


def test_new_named_folder_failure_rolls_back_reservation(library, monkeypatch):
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(library, 'save', fail)
    with pytest.raises(OSError, match='disk full'):
        library.add_book('Do not reserve forever')
    assert not library.books
    assert not (library.root / 'books' / 'do-not-reserve-forever').exists()
