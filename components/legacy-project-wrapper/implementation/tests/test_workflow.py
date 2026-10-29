import json
import os
import sys
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
    assert window.pending.isNull()
    assert len(window.book["pages"]) == 1
    stored = QImage(str(window.library.page_path(window.book["pages"][0])))
    assert stored == image


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


@pytest.mark.parametrize('custom_folder', [False, True])
def test_export_uses_selected_book_and_derived_default_path(window, image, tmp_path, monkeypatch, custom_folder):
    from PySide6.QtWidgets import QFileDialog
    first = window.library.add_book('First', image_folder=tmp_path / 'custom-scans' if custom_folder else None)
    second = window.library.add_book('Second')
    window.library.accept(first, image)
    image.fill('blue')
    window.library.accept(first, image)
    window.library.accept(second, image)
    window.book = first  # The sidebar selection alone determines the export.
    window.refresh_books()
    window.update_controls()
    folder = window.library.image_folder(first)
    destination = tmp_path / 'chosen-name.pdf'
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: pytest.fail('Source folder is already known'))
    prompts = []
    def choose_file(*args, **kwargs):
        prompts.append(args)
        return str(destination.with_suffix('')), 'PDF files (*.pdf)'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', choose_file)
    window.export_button.click()
    assert 'all 2 pages' in prompts[0][1]
    assert Path(prompts[0][2]) == folder / 'first.pdf'
    assert list(tmp_path.glob('*.pdf')) == [destination]
    document = QPdfDocument()
    assert document.load(str(destination)) == QPdfDocument.Error.None_
    assert document.pageCount() == 2
    assert document.render(0, QSize(60, 80)).pixelColor(30, 40).red() > 240
    assert document.render(1, QSize(60, 80)).pixelColor(30, 40).blue() > 240
    assert document.render(1, QSize(60, 80)).pixelColor(30, 40).red() < 10
    document.close()
    assert 'First: all 2 pages' in window.status.text()
    contents = destination.read_bytes()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Cancel)
    window.export_button.click()
    assert contents == destination.read_bytes()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window.export_button.click()
    assert destination.read_bytes().startswith(b'%PDF')


def test_export_folder_cannot_contain_source_images(library, image):
    book = library.add_book('Test')
    library.accept(book, image)
    with pytest.raises(ValueError, match='outside'):
        library.export_books(library.root / 'books' / book['id'])


def test_one_click_captures_and_saves(window, image, tmp_path, monkeypatch):
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
    assert window.pending.isNull()
    assert len(window.book['pages']) == 1
    assert button.text() == 'Capture'
    assert button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert len(calls) == 1  # No second click is needed to save.


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


def test_edit_book_moves_folder_and_images(window, image, tmp_path):
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
    assert saved['pages'] == [str(tmp_path / 'renamed' / Path(page).name)]
    assert saved['image_folder'] == str(tmp_path / 'renamed')
    assert not (tmp_path / 'Scans').exists()
    assert QImage(saved['pages'][0]) == image
    assert str(tmp_path / 'renamed') in window.location.text()
    window.pages.setCurrentRow(0)
    assert window.preview.image == image


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
    assert library.image_folder(book).name == 'new-title'
    assert not (library.root / 'books' / ('a' * 32)).exists()
    assert book['folder_name'] == 'new-title'
    assert QImage(str(library.page_path(book['pages'][0]))) == image


def test_new_named_folder_failure_rolls_back_reservation(library, monkeypatch):
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(library, 'save', fail)
    with pytest.raises(OSError, match='disk full'):
        library.add_book('Do not reserve forever')
    assert not library.books
    assert not (library.root / 'books' / 'do-not-reserve-forever').exists()


def test_packaged_application_icon_is_transparent_and_visible_at_small_sizes(window):
    from bookscan.desktop import ICON_PATH
    image = QImage(str(ICON_PATH))
    assert not image.isNull()
    assert image.width() == image.height() and image.width() >= 512
    assert image.hasAlphaChannel()
    assert image.pixelColor(0, 0).alpha() == 0
    assert not window.windowIcon().isNull()
    for size in (16, 32, 48, 128, 256):
        pixmap = window.windowIcon().pixmap(size, size)
        assert not pixmap.isNull()
        assert pixmap.width() == size and pixmap.height() == size


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux desktop integration')
def test_linux_desktop_install_uses_packaged_icon_and_active_python(tmp_path):
    from bookscan.desktop import ICON_PATH, install_desktop
    import shutil
    import subprocess
    destination = tmp_path / 'Application data'
    interpreter = tmp_path / 'Python environment' / 'bin' / 'python'
    desktop = install_desktop(destination, interpreter)
    contents = desktop.read_text()
    assert desktop == destination / 'applications' / 'bookscan.desktop'
    assert f'Exec="{interpreter}" -m bookscan' in contents
    installed_icon = destination / 'pixmaps' / 'bookscan.png'
    assert f'Icon={installed_icon}' in contents
    assert installed_icon.read_bytes() == ICON_PATH.read_bytes()
    assert 'Terminal=false' in contents
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate', str(desktop)], check=True,
                       capture_output=True, text=True)


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux desktop integration')
def test_desktop_install_cli_does_not_require_a_display(tmp_path):
    import subprocess
    import sys
    environment = os.environ.copy()
    environment.pop('DISPLAY', None)
    environment.pop('WAYLAND_DISPLAY', None)
    environment['XDG_DATA_HOME'] = str(tmp_path / 'user-data')
    result = subprocess.run([sys.executable, '-m', 'bookscan', '--install-desktop'],
                            capture_output=True, text=True, env=environment, timeout=15)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'user-data/applications/bookscan.desktop').exists()
    assert str(tmp_path / 'user-data/applications/bookscan.desktop') in result.stdout


def test_desktop_quote_rejects_injected_lines_and_escapes_literals():
    from bookscan.desktop import desktop_exec_argument
    with pytest.raises(ValueError):
        desktop_exec_argument('/tmp/python\nExec=other-command')
    quoted = desktop_exec_argument('/tmp/with space/$quote"percent%/python')
    assert quoted.startswith('"') and quoted.endswith('"')
    assert '%%' in quoted
    assert '\\\\$' in quoted and '\\\\"' in quoted


@pytest.mark.parametrize("trim", [False, True])
def test_capture_autosaves_with_optional_trim(window, black_mat_image, tmp_path, trim):
    from bookscan.imaging import black_background_rect
    window.book = window.library.add_book("Automatic camera save")
    window.auto_trim.setChecked(trim)
    path = tmp_path / "still.png"
    black_mat_image.save(str(path))
    window.capture_id = 41
    window.snapshot_saved(41, str(path))
    assert window.pending.isNull()
    assert len(window.book['pages']) == 1
    stored = QImage(str(window.library.page_path(window.book['pages'][0])))
    expected = black_mat_image.copy(black_background_rect(black_mat_image)) if trim else black_mat_image
    assert stored == expected
    assert len(Library(window.library.root).books[0]['pages']) == 1
    window.snapshot_saved(41, str(path))  # Duplicate result cannot save twice.
    assert len(window.book['pages']) == 1


def test_capture_save_failure_can_retry_without_recapture(window, image, tmp_path, monkeypatch):
    window.book = window.library.add_book("Retry")
    path = tmp_path / "still.png"
    image.save(str(path))
    accept = window.library.accept
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(window.library, "accept", fail)
    errors = []
    monkeypatch.setattr(window, "error", errors.append)
    window.capture_id = 42
    window.snapshot_saved(42, str(path))
    assert 'disk full' in errors[0]
    assert window.pending == image
    assert not window.book['pages']
    assert window.capture_button.text() == 'Save'
    monkeypatch.setattr(window.library, 'accept', accept)
    window.capture_button.click()
    assert len(window.book['pages']) == 1
    assert window.pending.isNull()


def test_keyboard_book_create_page_edit_save_and_navigation(window, image):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    def press(key, modifiers=Qt.KeyboardModifier.ControlModifier):
        QTest.keyClick(QApplication.focusWidget() or window, key, modifiers)
        QTest.qWait(180)  # Qt animates shortcut-triggered button clicks.
    press(Qt.Key.Key_N)
    assert window.book_form.isVisible()
    QTest.keyClicks(window.book_form.title, "Keyboard book")
    press(Qt.Key.Key_Return, Qt.KeyboardModifier.AltModifier)
    assert window.book['title'] == 'Keyboard book'
    assert window.book_form.isHidden()
    window.library.accept(window.book, image)
    window.refresh_books()
    press(Qt.Key.Key_P, Qt.KeyboardModifier.AltModifier)
    assert window.pages.hasFocus()
    press(Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    assert window.pages.currentRow() == 0
    press(Qt.Key.Key_E)
    assert window.editing_page == 0
    press(Qt.Key.Key_BracketRight)
    assert window.pending.size() == QSize(800, 600)
    press(Qt.Key.Key_S)
    assert window.pending.isNull()
    assert len(window.book['pages']) == 1
    assert QImage(str(window.library.page_path(window.book['pages'][0]))).size() == QSize(800, 600)
    press(Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert window.book_form.isVisible()
    press(Qt.Key.Key_C, Qt.KeyboardModifier.AltModifier)
    assert window.book_form.isHidden()


def test_all_buttons_have_unique_accelerators_and_disabled_capture_is_safe(window, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    buttons = window.findChildren(QPushButton)
    shortcuts = [button.shortcut().toString() for button in buttons]
    assert all(shortcuts)
    assert len(set(shortcuts)) == len(shortcuts)
    assert all(button.toolTip() for button in buttons)
    calls = []
    monkeypatch.setattr(window, 'take_snapshot', lambda: calls.append('capture'))
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(window, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(180)
    assert not calls  # No selected book / ready camera.


@pytest.mark.parametrize('key,control', [('S', True)])
def test_keyboard_capture_saves_without_second_press(window, image, tmp_path, monkeypatch, key, control):
    from types import SimpleNamespace
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.book = window.library.add_book('Keyboard capture')
    window.camera = SimpleNamespace(stop=lambda: None)
    monkeypatch.setattr(window.capture, 'isReadyForCapture', lambda: True)
    path = tmp_path / 'camera.png'
    image.save(str(path))
    def capture(filename):
        QTimer.singleShot(0, lambda: window.snapshot_saved(73, str(path)))
        return 73
    monkeypatch.setattr(window.capture, 'captureToFile', capture)
    window.update_controls()
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(window, Qt.Key.Key_S if control else Qt.Key.Key_F6,
                   Qt.KeyboardModifier.ControlModifier if control else Qt.KeyboardModifier.NoModifier)
    QTest.qWait(200)
    assert len(window.book['pages']) == 1
    assert window.pending.isNull()
    assert window.capture_id is None


def test_selected_export_save_dialog_cancellation(window, image, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    window.book = window.library.add_book('Cancel export')
    window.library.accept(window.book, image)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: pytest.fail('No source chooser'))
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: ('', ''))
    window.export_pdf()
    assert not list(tmp_path.rglob('*.pdf'))


def test_single_pdf_can_be_saved_in_book_folder_without_overwriting_pages(library, image):
    book = library.add_book('Book')
    page = library.accept(book, image)
    output = library.image_folder(book) / 'book.pdf'
    library.export_pdf(book, output)
    assert output.read_bytes().startswith(b'%PDF')
    with pytest.raises(ValueError, match='different'):
        library.export_pdf(book, library.page_path(page))
    assert QImage(str(library.page_path(page))) == image


def test_all_shortcuts_work_without_function_keys(window, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    assert all(not button.shortcut().toString().startswith('F') for button in window.findChildren(QPushButton))
    assert all(not shortcut.key().toString().startswith('F') for shortcut in window.keyboard_shortcuts)
    calls = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: calls.append('help'))
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(window, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(180)
    assert calls == ['help']
    refreshes = []
    window.refresh_button.clicked.disconnect()
    window.refresh_button.clicked.connect(lambda: refreshes.append(True))
    QTest.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    QTest.qWait(180)
    assert refreshes == [True]


@pytest.mark.parametrize('selection', ['none', 'empty'])
def test_export_requires_nonempty_selected_book(window, image, monkeypatch, selection):
    from PySide6.QtWidgets import QFileDialog
    other = window.library.add_book('Other book with pages')
    window.library.accept(other, image)
    if selection == 'empty':
        window.book = window.library.add_book('Empty selection')
    window.update_controls()
    assert not window.export_button.isEnabled()
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: pytest.fail('No exportable book selected'))
    window.export_pdf()
    assert 'Select a book' in window.status.text()


def test_export_selection_changes_source_even_for_shared_image_folder(window, image, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    folder = tmp_path / 'shared-scans'
    first = window.library.add_book('First', image_folder=folder)
    second = window.library.add_book('Second', image_folder=folder)
    window.library.accept(first, image)
    window.library.accept(first, image)
    window.library.accept(second, image)
    window.refresh_books()
    outputs = []
    def choose_file(*args, **kwargs):
        outputs.append(Path(args[2]))
        return args[2], 'PDF files (*.pdf)'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', choose_file)
    for row, book in enumerate([first, second]):
        window.books.setCurrentRow(row)
        assert window.book is book
        assert window.export_button.isEnabled()
        window.export_button.click()
        document = QPdfDocument()
        assert document.load(str(outputs[-1])) == QPdfDocument.Error.None_
        assert document.pageCount() == len(book['pages'])
        document.close()
    assert outputs == [folder / 'first.pdf', folder / 'second.pdf']


def test_dynamic_button_labels_preserve_shortcuts(window, image):
    window.book = window.library.add_book('Shortcuts')
    window.present(image)
    assert window.capture_button.shortcut().toString() == 'Ctrl+S'
    window.crop_button.click()
    assert window.crop_button.shortcut().toString() == 'Ctrl+R'
    window.crop_button.click()
    assert window.crop_button.shortcut().toString() == 'Ctrl+R'
    window.cancel_snapshot()
    assert window.capture_button.shortcut().toString() == 'Ctrl+S'
    window.book_form.populate(window.book)
    assert window.book_form.submit_button.shortcut().toString() == 'Alt+Return'
    window.book_form.populate()
    assert window.book_form.submit_button.shortcut().toString() == 'Alt+Return'


@pytest.mark.parametrize('custom', [False, True])
def test_reorder_persists_numbered_files_and_images(library, image, tmp_path, custom):
    book = library.add_book('Reorder', image_folder=str(tmp_path / 'scans') if custom else None)
    old = []
    for color in ['red', 'green', 'blue']:
        image.fill(color)
        old.append(library.accept(book, image))
    unrelated = library.image_folder(book) / 'notes.txt'
    unrelated.write_text('keep')
    library.reorder_pages(book, [2, 0, 1])
    reopened = Library(library.root)
    assert reopened.books[0]['pages'] == book['pages']
    assert [library.page_path(p).name[:10] for p in book['pages']] == [
        'page-0001-', 'page-0002-', 'page-0003-']
    assert [QImage(str(library.page_path(p))).pixelColor(0, 0).name() for p in book['pages']] == [
        '#0000ff', '#ff0000', '#008000']
    assert not any(library.page_path(p).exists() for p in old)
    assert len(list(library.image_folder(book).glob('*.png'))) == 3
    assert unrelated.read_text() == 'keep'
    library.accept(book, image)
    assert library.page_path(book['pages'][-1]).name.startswith('page-0004-')


@pytest.mark.parametrize('failure', ['save', 'copy', 'missing'])
def test_reorder_failure_keeps_originals(library, image, monkeypatch, failure):
    import bookscan.library as module
    book = library.add_book('Failure')
    for _ in range(3):
        library.accept(book, image)
    old = book['pages'][:]
    manifest = library.path.read_bytes()
    if failure == 'missing':
        library.page_path(old[0]).unlink()
    before = {p.name: p.read_bytes() for p in library.image_folder(book).glob('*.png')}
    def fail(*args):
        raise OSError('disk failure')
    if failure == 'save':
        monkeypatch.setattr(library, 'save', fail)
    elif failure == 'copy':
        original = module.shutil.copyfileobj
        count = 0
        def copy(source, target):
            nonlocal count
            count += 1
            if count == 2:
                target.write(b'partial')
                fail()
            original(source, target)
        monkeypatch.setattr(module.shutil, 'copyfileobj', copy)
    with pytest.raises(OSError):
        library.reorder_pages(book, [2, 0, 1])
    assert book['pages'] == old
    assert library.path.read_bytes() == manifest
    assert {p.name: p.read_bytes() for p in library.image_folder(book).glob('*.png')} == before


def test_reorder_preserves_shared_and_legacy_images(library, image):
    book = library.add_book('Legacy')
    old = [library.accept(book, image), library.accept(book, image)]
    legacy = library.page_path(old[0]).with_name('scan.png')
    library.page_path(old[0]).rename(legacy)
    book['pages'][0] = legacy.relative_to(library.root).as_posix()
    other = library.add_book('Shared')
    other['pages'] = [book['pages'][0]]
    library.save()
    library.reorder_pages(book, [1, 0])
    assert legacy.is_file()
    assert Library(library.root).books[1]['pages'] == other['pages']
    assert library.page_path(book['pages'][1]).name.startswith('page-0002-')
    assert QImage(str(library.page_path(other['pages'][0]))) == image


@pytest.mark.parametrize('order', [[0, 0], [0], [1, 2], [True, 0]])
def test_reorder_rejects_invalid_permutations(library, image, order):
    book = library.add_book('Invalid')
    library.accept(book, image)
    library.accept(book, image)
    old = book['pages'][:]
    with pytest.raises(ValueError):
        library.reorder_pages(book, order)
    assert book['pages'] == old


def test_sidebar_move_buttons_selection_preview_and_busy(window, image):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    window.book = window.library.add_book('Sidebar')
    for color in ['red', 'blue', 'green']:
        image.fill(color)
        window.library.accept(window.book, image)
    window.refresh_books()
    window.pages.setCurrentRow(0)
    assert not window.move_up_button.isEnabled()
    assert window.move_down_button.isEnabled()
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(window, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    QTest.qWait(180)  # Qt animates shortcut-triggered button clicks.
    assert window.pages.currentRow() == 1
    assert window.preview.image.pixelColor(0, 0).name() == '#ff0000'
    assert [window.pages.item(i).text() for i in range(3)] == ['Page 1', 'Page 2', 'Page 3']
    window.move_down_button.click()
    assert window.pages.currentRow() == 2
    assert not window.move_down_button.isEnabled()
    window.edit_selected_page()
    assert not window.move_up_button.isEnabled()
    old = window.book['pages'][:]
    window.move_page(-1)
    assert window.book['pages'] == old
    window.cancel_snapshot()
    window.capture_id = 123
    window.update_controls()
    assert not window.move_up_button.isEnabled()


def test_sidebar_drop_order_and_failure_recovery(window, image, monkeypatch):
    window.book = window.library.add_book('Drop')
    for color in ['red', 'blue', 'green']:
        image.fill(color)
        window.library.accept(window.book, image)
    window.refresh_books()
    # Model movement is the operation performed by Qt's internal drop handling.
    assert window.pages.model().moveRow(window.pages.rootIndex(), 0, window.pages.rootIndex(), 3)
    window.pages.setCurrentRow(2)
    window.pages_dropped()
    assert window.preview.image.pixelColor(0, 0).name() == '#ff0000'
    assert window.pages.currentRow() == 2
    old = window.book['pages'][:]
    monkeypatch.setattr(window.library, 'save', lambda: (_ for _ in ()).throw(OSError('disk full')))
    errors = []
    monkeypatch.setattr(window, 'error', errors.append)
    window.move_page(-1)
    assert window.book['pages'] == old
    assert window.pages.currentRow() == 2
    assert window.preview.image.pixelColor(0, 0).name() == '#ff0000'
    assert 'Original order' in errors[0]


def test_reordered_pdf_uses_sidebar_order(window, image):
    window.book = window.library.add_book('Reordered PDF')
    for color in ['red', 'blue', 'green']:
        image.fill(color)
        window.library.accept(window.book, image)
    window.refresh_books()
    window.pages.setCurrentRow(0)
    window.move_page(1)
    window.move_page(1)
    destination = window.library.root / 'reordered.pdf'
    window.library.export_pdf(window.book, destination)
    document = QPdfDocument()
    assert document.load(str(destination)) == QPdfDocument.Error.None_
    assert document.pageCount() == 3
    # PDF image encoding/rendering may round a channel by a few levels.
    for i, expected in enumerate([(0, 0, 255), (0, 128, 0), (255, 0, 0)]):
        color = document.render(i, image.size()).pixelColor(300, 400)
        assert all(abs(actual - target) <= 3 for actual, target in
                   zip((color.red(), color.green(), color.blue()), expected))
    document.close()


@pytest.mark.parametrize('custom', [False, True])
@pytest.mark.parametrize('with_pages', [False, True])
def test_rename_moves_whole_directory_and_reopens(library, image, tmp_path, custom, with_pages):
    book = library.add_book('Original', image_folder=tmp_path / 'Custom scans' if custom else None)
    folder = library.image_folder(book)
    if with_pages:
        library.accept(book, image)
        image.fill('blue')
        library.accept(book, image)
    old = book['pages'][:]
    before = [library.page_path(page).read_bytes() for page in old]
    (folder / 'extras').mkdir()
    (folder / 'extras' / 'notes.txt').write_text('Keep all folder contents')
    (folder / 'export.pdf').write_bytes(b'Existing PDF')
    destination = folder.with_name('new-book')
    assert library.renamed_book_folder(book, 'New Book') == destination
    assert not destination.exists()
    assert library.update_book(book, ' New Book ', 'Notebook', ' Author ') is None
    assert not folder.exists()
    assert library.image_folder(book) == destination
    assert [library.page_path(page).read_bytes() for page in book['pages']] == before
    assert all(Path(page).is_absolute() == custom for page in book['pages'])
    assert [Path(page).name for page in book['pages']] == [Path(page).name for page in old]
    assert (destination / 'extras' / 'notes.txt').read_text() == 'Keep all folder contents'
    assert (destination / 'export.pdf').read_bytes() == b'Existing PDF'
    reopened = Library(library.root)
    assert reopened.books[0] == book
    assert reopened.image_folder(reopened.books[0]) == destination
    library.accept(book, image)
    assert library.page_path(book['pages'][-1]).parent == destination
    output = destination / 'new-book.pdf'
    library.export_pdf(book, output)
    assert output.read_bytes().startswith(b'%PDF')


def test_rename_preview_cancel_and_metadata_only_save(window, image, monkeypatch):
    window.book = window.library.add_book('Original')
    page = window.library.accept(window.book, image)
    folder = window.library.image_folder(window.book)
    window.refresh_books()
    window.edit_book()
    form = window.book_form
    form.title.setText('New title')
    assert form.destination == folder.with_name('new-title')
    assert form.folder.text() == str(form.destination)
    assert 'will move' in form.folder_preview.text()
    assert folder.is_dir() and not form.destination.exists()
    form.cancel_button.click()
    assert window.book['title'] == 'Original'
    assert window.book['pages'] == [page]
    window.edit_book()
    form.author.setText('New author')
    form.kind.setCurrentText('Magazine')
    monkeypatch.setattr('bookscan.library.shutil.copytree', lambda *args, **kwargs: pytest.fail('Unchanged name must not move files'))
    form.submit_button.click()
    assert window.book['title'] == 'Original'
    assert window.book['author'] == 'New author'
    assert window.book['kind'] == 'Magazine'
    assert window.library.image_folder(window.book) == folder
    assert window.book['pages'] == [page]


def test_rename_uses_portable_collision_safe_preview(window, image):
    window.book = window.library.add_book('Original')
    window.library.accept(window.book, image)
    parent = window.library.image_folder(window.book).parent
    (parent / 'BOOK-CON').mkdir()
    (parent / 'BOOK-CON' / 'keep.txt').write_text('keep')
    window.edit_book()
    form = window.book_form
    form.title.setText('CON')
    assert form.destination == parent / 'book-con-2'
    # A folder appears after preview; saving must require review of a new path.
    form.destination.mkdir()
    (form.destination / 'keep.txt').write_text('also keep')
    form.submit_button.click()
    assert window.book['title'] == 'Original'
    assert form.destination == parent / 'book-con-3'
    assert form.error_label.isVisibleTo(form)
    form.submit_button.click()
    assert window.book['title'] == 'CON'
    assert window.library.image_folder(window.book) == parent / 'book-con-3'
    assert (parent / 'BOOK-CON' / 'keep.txt').read_text() == 'keep'
    assert (parent / 'book-con-2' / 'keep.txt').read_text() == 'also keep'


@pytest.mark.parametrize('failure', ['copy', 'save', 'missing', 'race'])
def test_failed_book_rename_preserves_originals_and_edit_form(window, image, monkeypatch, failure):
    import bookscan.library as module
    window.book = window.library.add_book('Original')
    page = window.library.accept(window.book, image)
    folder = window.library.image_folder(window.book)
    contents = window.library.page_path(page).read_bytes()
    manifest = window.library.path.read_bytes()
    window.refresh_books()
    window.edit_book()
    form = window.book_form
    form.title.setText('Renamed')
    destination = form.destination
    if failure == 'copy':
        def fail_copy(source, target, **kwargs):
            (target / 'partial').write_bytes(b'partial')
            raise OSError('disk full')
        monkeypatch.setattr(module.shutil, 'copytree', fail_copy)
    elif failure == 'save':
        monkeypatch.setattr(window.library, 'save', lambda: (_ for _ in ()).throw(OSError('disk full')))
    elif failure == 'missing':
        folder.rename(folder.with_name('disconnected'))
    else:
        original_mkdir = Path.mkdir
        def race(path, *args, **kwargs):
            if path == destination:
                original_mkdir(path)
                (path / 'keep').write_text('external contents')
                raise FileExistsError('just created elsewhere')
            return original_mkdir(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'mkdir', race)
    form.submit_button.click()
    assert window.book['title'] == 'Original'
    assert window.book['pages'] == [page]
    assert window.library.path.read_bytes() == manifest
    assert form.title.text() == 'Renamed'
    assert not form.isHidden() and not form.error_label.isHidden()
    if failure != 'missing':
        assert window.library.page_path(page).read_bytes() == contents
    if failure == 'race':
        assert (destination / 'keep').read_text() == 'external contents'
    else:
        assert not destination.exists()
    monkeypatch.undo()  # Window teardown must be able to save normally.


@pytest.mark.parametrize('sharing', ['folder', 'page', 'nested'])
def test_rename_refuses_to_move_another_books_files(library, image, tmp_path, sharing):
    folder = tmp_path / 'shared'
    book = library.add_book('First', image_folder=folder)
    page = library.accept(book, image)
    other = library.add_book('Other', image_folder=folder if sharing == 'folder' else
                             folder / 'nested' if sharing == 'nested' else None)
    if sharing == 'page':
        other['pages'].append(page)
        library.save()
    before = library.path.read_bytes()
    with pytest.raises(ValueError, match='shared'):
        library.update_book(book, 'Renamed', 'Other', '')
    assert library.path.read_bytes() == before
    assert Path(page).exists()
    assert folder.exists() and not folder.with_name('renamed').exists()


def test_rename_refuses_library_root_folder(library, image):
    book = library.add_book('Root', image_folder=library.root)
    library.accept(book, image)
    before = library.path.read_bytes()
    with pytest.raises(ValueError, match='dedicated'):
        library.update_book(book, 'Renamed', 'Other', '')
    assert library.path.read_bytes() == before


def test_title_change_with_identical_portable_name_keeps_files(library, image, monkeypatch):
    book = library.add_book('My Book')
    page = library.accept(book, image)
    monkeypatch.setattr('bookscan.library.shutil.copytree', lambda *args, **kwargs: pytest.fail('Same path must not be copied'))
    library.update_book(book, 'MY BOOK!', 'Other', '')
    assert book['title'] == 'MY BOOK!'
    assert book['pages'] == [page]
    assert library.image_folder(book).name == 'my-book'


def test_rename_reports_old_folder_cleanup_failure(library, image, monkeypatch):
    import bookscan.library as module
    book = library.add_book('Original')
    library.accept(book, image)
    folder = library.image_folder(book)
    original_rmtree = module.shutil.rmtree
    def fail_cleanup(path, *args, **kwargs):
        if path == folder:
            raise OSError('permission denied')
        return original_rmtree(path, *args, **kwargs)
    monkeypatch.setattr(module.shutil, 'rmtree', fail_cleanup)
    notice = library.update_book(book, 'Renamed', 'Other', '')
    assert str(folder) in notice and 'old files remain' in notice
    assert Library(library.root).books[0] == book
    assert book['title'] == 'Renamed'
    assert QImage(str(library.page_path(book['pages'][0]))) == image


def test_rescan_replaces_selected_page_in_place(window, image, tmp_path):
    window.book = window.library.add_book("Rescan")
    for color in ("red", "green", "blue"):
        page = QImage(image)
        page.fill(color)
        window.library.accept(window.book, page)
    window.refresh_pages()
    window.camera = object()  # Stand-in: rescan needs a live camera, not real frames.
    window.pages.setCurrentRow(1)
    old = window.book['pages'][:]
    assert window.rescan_button.shortcut().toString()
    window.update_controls()
    assert window.rescan_button.isEnabled()
    window.start_rescan()
    assert window.rescan_row == 1
    assert window.cancel_button.isEnabled()
    fresh = QImage(image)
    fresh.fill("yellow")
    capture_path = tmp_path / "rescan.png"
    fresh.save(str(capture_path))
    window.capture_id = 51
    window.snapshot_saved(51, str(capture_path))
    assert window.rescan_row is None
    assert len(window.book['pages']) == 3
    assert window.book['pages'] == old
    assert [QImage(str(window.library.page_path(p))).pixelColor(0, 0).name() for p in window.book['pages']] == ['#ff0000', '#ffff00', '#0000ff']
    assert "Page 2 replaced" in window.status.text()
    window.camera = None


def test_rescan_cancel_and_page_selection_leave_rescan_mode(window, image):
    window.book = window.library.add_book("Rescan cancel")
    window.library.accept(window.book, image)
    window.library.accept(window.book, image)
    window.refresh_pages()
    window.camera = object()
    window.pages.setCurrentRow(0)
    window.start_rescan()
    window.cancel_snapshot()
    assert window.rescan_row is None
    window.pages.setCurrentRow(0)
    window.start_rescan()
    window.pages.setCurrentRow(1)
    assert window.rescan_row is None
    window.camera = None


def test_selecting_a_book_shows_its_first_page(window, image):
    book = window.library.add_book("Has pages")
    window.library.accept(book, image)
    window.library.accept(book, image)
    empty = window.library.add_book("No pages")
    window.refresh_books()
    window.select_book(window.library.books.index(book))
    assert window.pages.currentRow() == 0
    assert window.stack.currentWidget() is window.preview
    window.select_book(window.library.books.index(empty))
    assert window.pages.currentRow() == -1
