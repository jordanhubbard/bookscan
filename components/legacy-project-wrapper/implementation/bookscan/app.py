"""Qt desktop book scanning with immediate capture storage and page editing."""
import argparse
import math
from pathlib import Path
import sys
import time
import tempfile
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer, QStandardPaths, QSize, QPointF, QRectF, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap, QTransform, QIcon, QPainter, QColor, QPen, QFont, QShortcut, QKeySequence
from PySide6.QtMultimedia import QCamera, QImageCapture, QMediaCaptureSession, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QStyle, QSizePolicy, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .library import Library, portable_book_name
from .autocapture import AutoCaptureDetector, sample_frame
from .autocapture_dialog import AutoCaptureSettings
from .imaging import black_background_rect
from .desktop import ICON_PATH, install_desktop


def set_button_text(button, text):
    """Qt resets a button's explicit shortcut when its label changes."""
    shortcut = button.shortcut()
    button.setText(text)
    button.setShortcut(shortcut)


class PageList(QListWidget):
    reordered = Signal()

    def dropEvent(self, event):
        if event.source() is not self or not self.isEnabled():
            event.ignore()
            return
        previous = self.blockSignals(True)
        try:
            super().dropEvent(event)
        finally:
            self.blockSignals(previous)
        if event.isAccepted():
            self.reordered.emit()


class BookForm(QGroupBox):
    submitted = Signal()
    cancelled = Signal()

    def __init__(self, library, parent=None):
        super().__init__("New book", parent)
        self.library = library
        self.folder_overridden = False
        self._setting_folder = False
        self.destination = None
        self.editing_book = None
        self.busy = False
        self.folder_picker = None
        layout = QVBoxLayout(self)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Book title (required)")
        self.author = QLineEdit()
        self.author.setPlaceholderText("Optional")
        self.kind = QComboBox()
        self.kind.addItems(["Hardcover", "Paperback", "Textbook", "Notebook", "Magazine", "Other"])
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Automatic folder from book title")
        self.browse_folder_button = QPushButton("&Browse…")
        self.browse_folder_button.clicked.connect(self.browse_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.browse_folder_button)
        self.default_folder_button = QPushButton("Use default")
        self.default_folder_button.clicked.connect(self.use_default_folder)
        folder_row.addWidget(self.default_folder_button)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("&Title", self.title)
        author_row = QHBoxLayout()
        author_row.addWidget(self.author, 2)
        type_label = QLabel("T&ype")
        type_label.setBuddy(self.kind)
        author_row.addWidget(type_label)
        author_row.addWidget(self.kind, 1)
        author_label = QLabel("&Author")
        author_label.setBuddy(self.author)
        form.addRow(author_label, author_row)
        folder_label = QLabel("Images &folder")
        folder_label.setBuddy(self.folder)
        form.addRow(folder_label, folder_row)
        layout.addLayout(form)
        self.folder_preview = QLabel()
        self.folder_preview.setWordWrap(True)
        self.folder_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.folder_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.folder_preview)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        actions = QHBoxLayout()
        self.submit_button = QPushButton("Create book")
        self.submit_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.submit_button.clicked.connect(self.submitted.emit)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.submit_button)
        layout.addLayout(actions)
        self.title.textChanged.connect(self.update_state)
        self.folder.textChanged.connect(self.folder_changed)
        self.title.returnPressed.connect(lambda: self.submitted.emit() if self.submit_button.isEnabled() else None)
        self.update_state()

    def set_folder_text(self, text):
        self._setting_folder = True
        try:
            self.folder.setText(text)
            self.folder.setCursorPosition(len(text))
        finally:
            self._setting_folder = False

    def folder_changed(self):
        if self._setting_folder:
            return
        self.folder_overridden = bool(self.folder.text().strip())
        self.update_state()

    def use_default_folder(self):
        self.folder_overridden = False
        self.update_state()

    def update_state(self):
        valid = True
        try:
            if self.editing_book is not None:
                self.destination = self.library.renamed_book_folder(self.editing_book, self.title.text())
                self.set_folder_text(str(self.destination))
            elif self.folder_overridden:
                self.destination = Path(self.folder.text().strip()).expanduser().resolve()
            else:
                self.destination = self.library.new_book_folder(self.title.text())
                self.set_folder_text(str(self.destination))
            moving = self.editing_book is not None and self.destination != self.library.image_folder(self.editing_book)
            self.folder_preview.setText(("Save book will move the image folder to: " if moving else
                                        "Images will be saved to: ") + str(self.destination))
            self.folder.setToolTip(str(self.destination))
        except (OSError, ValueError) as exc:
            valid = False
            self.destination = None
            self.folder_preview.setText(f"Choose another images folder: {exc}")
        self.default_folder_button.setEnabled(self.editing_book is None and self.folder_overridden)
        self.submit_button.setEnabled(bool(self.title.text().strip()) and not self.busy and valid)

    def set_busy(self, busy):
        self.busy = busy
        self.submit_button.setToolTip("Save or cancel the current snapshot first" if busy else "Create book / save book details (Alt+Enter)")
        self.update_state()

    def populate(self, book=None):
        self.editing_book = book
        self.folder_overridden = book is not None
        self.setTitle("Edit book" if book else "New book")
        set_button_text(self.submit_button, "Save book" if book else "Create book")
        self.title.blockSignals(True)
        self.title.setText(book['title'] if book else '')
        self.title.blockSignals(False)
        self.author.setText(book.get('author', '') if book else '')
        self.kind.setCurrentText(book.get('kind', 'Other') if book else 'Hardcover')
        if book:
            self.set_folder_text(str(self.library.image_folder(book)))
        self.folder.setReadOnly(book is not None)
        self.browse_folder_button.setEnabled(book is None)
        self.error_label.hide()
        self.update_state()

    def show_error(self, message):
        self.error_label.setText(str(message))
        self.error_label.show()

    def browse_folder(self):
        if self.folder_picker is None:
            picker = QFileDialog(self, "Choose folder for scanned images")
            picker.setFileMode(QFileDialog.FileMode.Directory)
            picker.setOption(QFileDialog.Option.ShowDirsOnly)
            picker.setOption(QFileDialog.Option.DontUseNativeDialog)
            picker.setWindowModality(Qt.WindowModality.NonModal)
            picker.accepted.connect(lambda: self.folder.setText(picker.selectedFiles()[0]) if picker.selectedFiles() else None)
            self.folder_picker = picker
        start = self.destination or self.library.root
        while not start.is_dir() and start != start.parent:
            start = start.parent
        self.folder_picker.setDirectory(str(start))
        self.folder_picker.show()
        self.folder_picker.raise_()

    def hideEvent(self, event):
        if self.folder_picker:
            self.folder_picker.hide()
        super().hideEvent(event)


class ImageView(QWidget):
    selectionChanged = Signal()
    viewChanged = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(160, 160)
        self.image = QImage()
        self.cropping = False
        self.anchor = None
        self.selection = QRectF()
        self.zoom = 1.0
        self.pan = QPointF()
        self.pan_anchor = None

    def show_image(self, image):
        self.image = image
        self.selection = QRectF()
        self.anchor = None
        self.fit_image()
        self.update()
        self.selectionChanged.emit()

    def image_rect(self):
        if self.image.isNull():
            return QRectF()
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        width, height = size.width() * self.zoom, size.height() * self.zoom
        return QRectF((self.width() - width) / 2 + self.pan.x(),
                      (self.height() - height) / 2 + self.pan.y(), width, height)

    def clamp_pan(self):
        if self.image.isNull():
            return
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x_limit = max(0, (size.width() * self.zoom - self.width()) / 2)
        y_limit = max(0, (size.height() * self.zoom - self.height()) / 2)
        self.pan = QPointF(max(-x_limit, min(x_limit, self.pan.x())),
                           max(-y_limit, min(y_limit, self.pan.y())))

    def update_cursor(self):
        self.setCursor(Qt.CursorShape.CrossCursor if self.cropping else
                       Qt.CursorShape.OpenHandCursor if self.zoom > 1 else Qt.CursorShape.ArrowCursor)

    def set_zoom(self, value):
        value = max(1.0, min(8.0, value))
        self.pan *= value / self.zoom
        self.zoom = value
        self.clamp_pan()
        self.update_cursor()
        self.update()
        self.viewChanged.emit()

    def fit_image(self):
        self.pan = QPointF()
        self.set_zoom(1.0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.clamp_pan()

    def wheelEvent(self, event):
        if not self.image.isNull():
            self.set_zoom(self.zoom * (1.25 if event.angleDelta().y() > 0 else 0.8))
            event.accept()

    def set_cropping(self, enabled):
        self.cropping = enabled
        self.anchor = None
        self.selection = QRectF()
        self.update_cursor()
        self.update()
        self.selectionChanged.emit()

    def image_point(self, position):
        rect = self.image_rect()
        return QPointF(max(0, min(self.image.width(), (position.x() - rect.x()) * self.image.width() / rect.width())),
                       max(0, min(self.image.height(), (position.y() - rect.y()) * self.image.height() / rect.height())))

    def crop_rect(self):
        # Floor the leading edges and ceil the trailing edges to retain selected pixels.
        rect = self.selection
        if rect.width() < 1 or rect.height() < 1:
            return QRectF().toRect()
        return QRectF(math.floor(rect.left()), math.floor(rect.top()),
                      math.ceil(rect.right()) - math.floor(rect.left()),
                      math.ceil(rect.bottom()) - math.floor(rect.top())).toRect().intersected(self.image.rect())

    def mousePressEvent(self, event):
        if self.cropping and event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self.anchor = self.image_point(event.position())
            self.selection = QRectF()
            self.update()
            self.selectionChanged.emit()
        elif not self.image.isNull() and self.zoom > 1 and (
                event.button() == Qt.MouseButton.MiddleButton or
                (not self.cropping and event.button() == Qt.MouseButton.LeftButton)):
            self.pan_anchor = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.pan_anchor is not None:
            self.pan += event.position() - self.pan_anchor
            self.pan_anchor = event.position()
            self.clamp_pan()
            self.update()
        elif self.cropping and self.anchor is not None:
            self.selection = QRectF(self.anchor, self.image_point(event.position())).normalized()
            self.update()
            self.selectionChanged.emit()

    def mouseReleaseEvent(self, event):
        if self.pan_anchor is not None:
            self.mouseMoveEvent(event)
            self.pan_anchor = None
            self.update_cursor()
        if event.button() == Qt.MouseButton.LeftButton and self.anchor is not None:
            self.mouseMoveEvent(event)
            self.anchor = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#15202b"))
        if self.image.isNull():
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = self.image_rect()
        painter.drawImage(target, self.image)
        if self.cropping and not self.selection.isEmpty():
            scale_x, scale_y = target.width() / self.image.width(), target.height() / self.image.height()
            selected = QRectF(target.x() + self.selection.x() * scale_x,
                              target.y() + self.selection.y() * scale_y,
                              self.selection.width() * scale_x, self.selection.height() * scale_y)
            shade = QColor(0, 0, 0, 135)
            for area in (QRectF(target.left(), target.top(), target.width(), selected.top() - target.top()),
                         QRectF(target.left(), selected.bottom(), target.width(), target.bottom() - selected.bottom()),
                         QRectF(target.left(), selected.top(), selected.left() - target.left(), selected.height()),
                         QRectF(selected.right(), selected.top(), target.right() - selected.right(), selected.height())):
                painter.fillRect(area, shade)
            painter.setPen(QPen(QColor("#63ecd0"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(selected)


class ScanWindow(QMainWindow):
    def __init__(self, library, prompt=True):
        super().__init__()
        self.library = library
        self.book = None
        self.editing_page = None
        self.pending = QImage()
        self.original = QImage()
        self.source = None
        self.capture_id = None
        self.camera = None
        self.thumbnails = {}
        self.temp = tempfile.TemporaryDirectory(prefix="bookscan-")
        self.setWindowTitle("BookScan — Scan your library")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1180, 800)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel("BookScan")
        title_font = QFont(self.font())
        title_font.setPointSizeF(title_font.pointSizeF() * 1.65)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.heading = QLabel("Select a book or create a new one")
        heading_font = QFont(self.font())
        heading_font.setBold(True)
        self.heading.setFont(heading_font)
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        sidebar = QWidget()
        left = QVBoxLayout(sidebar)
        left.addWidget(QLabel("Books"))
        book_actions = QHBoxLayout()
        self.new_book_button = self.button("New book", self.choose_book, book_actions)
        self.edit_book_button = self.button("Edit", self.edit_book, book_actions)
        self.remove_book_button = self.button("Delete", self.request_remove_book, book_actions)
        left.addLayout(book_actions)
        self.books = QListWidget()
        self.books.setAccessibleName("Books")
        self.books.currentRowChanged.connect(self.select_book)
        left.addWidget(self.books)
        left.addWidget(QLabel("Saved pages"))
        self.pages = PageList()
        self.pages.setAccessibleName("Saved pages")
        self.pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.pages.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.pages.setToolTip("Drag saved pages to reorder them, or use Move up / Move down. Image filenames follow page order.")
        self.pages.reordered.connect(self.pages_dropped)
        self.pages.currentRowChanged.connect(self.review_page)
        left.addWidget(self.pages, 2)
        page_actions = QHBoxLayout()
        self.edit_page_button = self.button("Edit page", self.edit_selected_page, page_actions)
        self.remove_page_button = self.button("Delete page", self.request_remove_page, page_actions)
        left.addLayout(page_actions)
        move_actions = QHBoxLayout()
        self.move_up_button = self.button("Move up", lambda: self.move_page(-1), move_actions)
        self.move_down_button = self.button("Move down", lambda: self.move_page(1), move_actions)
        left.addLayout(move_actions)
        splitter.addWidget(sidebar)
        workspace = QWidget()
        right = QVBoxLayout(workspace)
        right.setSpacing(10)
        self.book_form = BookForm(library, self)
        self.book_form.submitted.connect(self.submit_book)
        self.book_form.cancelled.connect(self.cancel_book_form)
        self.book_form.hide()
        right.addWidget(self.book_form)
        source_row = QHBoxLayout()
        self.devices = QComboBox()
        self.devices.currentIndexChanged.connect(self.change_camera)
        source_row.addWidget(QLabel("Camera"))
        source_row.addWidget(self.devices, 1)
        self.refresh_button = QPushButton("Refresh cameras")
        self.refresh_button.clicked.connect(self.refresh_cameras)
        source_row.addWidget(self.refresh_button)
        right.addLayout(source_row)
        self.stack = QStackedWidget()
        self.video = QVideoWidget()
        self.preview = ImageView()
        self.empty = QLabel("Connect a camera or import an image to start.\nCapture saves each page immediately. Select a saved page to edit it.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (self.empty, self.video, self.preview):
            self.stack.addWidget(widget)
        right.addWidget(self.stack, 1)
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        controls = QHBoxLayout()
        self.capture_button = self.button("Capture", self.capture_or_save, controls)
        self.cancel_button = self.button("Cancel", self.cancel_snapshot, controls)
        self.import_button = self.button("Import image…", self.import_image, controls)
        self.live_button = self.button("Back to camera", self.show_live, controls)
        right.addLayout(controls)
        zoom_controls = QHBoxLayout()
        zoom_controls.addWidget(QLabel("Zoom"))
        self.zoom_out_button = self.button("−", lambda: self.preview.set_zoom(self.preview.zoom / 1.25), zoom_controls)
        self.zoom_in_button = self.button("+", lambda: self.preview.set_zoom(self.preview.zoom * 1.25), zoom_controls)
        self.fit_button = self.button("Fit", self.preview.fit_image, zoom_controls)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setToolTip("Zoom relative to the fitted view. Drag to pan; while cropping, use the middle mouse button to pan.")
        zoom_controls.addWidget(self.zoom_label)
        zoom_controls.addStretch()
        self.auto_trim = QCheckBox("Auto-trim black background")
        self.auto_trim.setToolTip("Automatically trim new snapshots against a black background. Reset edits restores the original image.")
        zoom_controls.addWidget(self.auto_trim)
        self.auto_capture = QCheckBox("Auto-capture")
        self.auto_capture.setToolTip("Capture automatically when a page is placed on the black background and stays still for 3 seconds. Remove the page to re-arm.")
        self.auto_capture.toggled.connect(self.toggle_auto_capture)
        zoom_controls.addWidget(self.auto_capture)
        self.auto_settings_button = self.button("Tune…", self.show_auto_settings, zoom_controls)
        self.auto_settings_button.setToolTip("Tune auto-capture thresholds and preview detection without saving pages")
        self.preview.viewChanged.connect(self.update_controls)
        right.addLayout(zoom_controls)
        edits = QHBoxLayout()
        self.rotate_left_button = self.button("Rotate left ↶", lambda: self.rotate(-90), edits)
        self.rotate_button = self.button("Rotate right ↻", lambda: self.rotate(90), edits)
        self.crop_button = self.button("Crop", self.toggle_crop, edits)
        self.crop_button.setCheckable(True)
        self.apply_crop_button = self.button("Apply crop", self.apply_crop, edits)
        self.reset_button = self.button("Reset edits", self.reset_edits, edits)
        self.preview.selectionChanged.connect(self.update_controls)
        right.addLayout(edits)
        splitter.addWidget(workspace)
        splitter.setSizes([250, 900])
        footer = QHBoxLayout()
        self.location = QLabel(f"Saved in {library.root}")
        self.location.setWordWrap(True)
        self.location.setMinimumWidth(0)
        self.location.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer.addWidget(self.location, 1)
        self.export_button = self.button("Export book to PDF…", self.export_pdf, footer)
        self.export_button.setToolTip("Export all saved pages of the selected book; choose the output PDF file")
        self.next_button = self.button("Next book", self.choose_book, footer)
        self.done_button = self.button("Done — save and quit", self.close, footer)
        layout.addLayout(footer)
        self.setStyleSheet("QPushButton { padding: 6px 10px; } QLineEdit, QComboBox { padding: 4px; } QGroupBox { font-weight: bold; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; } QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QPushButton { font-weight: normal; }")
        self.capture_button.setStyleSheet("QPushButton:enabled { background: palette(highlight); color: palette(highlighted-text); font-weight: bold; }")
        self.zoom_in_button.setAccessibleName("Zoom in")
        self.zoom_out_button.setAccessibleName("Zoom out")
        self.install_shortcuts()
        self.session = QMediaCaptureSession(self)
        self.session.setVideoOutput(self.video)
        self.detector = AutoCaptureDetector()
        self.auto_settings = AutoCaptureSettings(self.detector, self)
        self.last_sample = 0.0
        self.video.videoSink().videoFrameChanged.connect(self.watch_frame)
        self.capture = QImageCapture(self)
        self.session.setImageCapture(self.capture)
        self.capture.imageSaved.connect(self.snapshot_saved)
        self.capture.errorOccurred.connect(self.capture_error)
        self.capture.readyForCaptureChanged.connect(self.update_controls)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(20000)
        self.timeout.timeout.connect(self.capture_timeout)
        self.media = QMediaDevices(self)
        self.media.videoInputsChanged.connect(self.refresh_cameras)
        self.refresh_books()
        self.refresh_cameras()
        self.update_controls()
        if prompt and not self.library.books:
            self.choose_book()

    def install_shortcuts(self):
        bindings = [
            (self.capture_button, "Ctrl+S", "Capture and save / save edits or retry"),
            (self.cancel_button, "Escape", "Cancel snapshot or page edits"),
            (self.import_button, "Ctrl+O", "Import image"),
            (self.live_button, "Ctrl+L", "Back to camera"),
            (self.new_book_button, "Ctrl+N", "New book"),
            (self.edit_book_button, "Ctrl+Shift+E", "Edit book"),
            (self.remove_book_button, "Ctrl+Shift+Delete", "Delete book"),
            (self.edit_page_button, "Ctrl+E", "Edit selected page"),
            (self.remove_page_button, "Ctrl+Delete", "Delete selected page"),
            (self.move_up_button, "Ctrl+Shift+Up", "Move selected page up"),
            (self.move_down_button, "Ctrl+Shift+Down", "Move selected page down"),
            (self.refresh_button, "Ctrl+Shift+R", "Refresh cameras"),
            (self.zoom_in_button, "Ctrl+=", "Zoom in"),
            (self.zoom_out_button, "Ctrl+-", "Zoom out"),
            (self.fit_button, "Ctrl+0", "Fit image"),
            (self.rotate_left_button, "Ctrl+[", "Rotate left"),
            (self.rotate_button, "Ctrl+]", "Rotate right"),
            (self.crop_button, "Ctrl+R", "Start or cancel crop"),
            (self.apply_crop_button, "Ctrl+Return", "Apply crop"),
            (self.reset_button, "Ctrl+Backspace", "Reset edits"),
            (self.export_button, "Ctrl+P", "Export book to PDF"),
            (self.next_button, "Ctrl+Shift+N", "Next book"),
            (self.done_button, "Ctrl+Q", "Save and quit"),
            (self.auto_trim, "Ctrl+T", "Toggle auto-trim"),
            (self.auto_capture, "Ctrl+Shift+A", "Toggle auto-capture"),
            (self.auto_settings_button, "Ctrl+Shift+T", "Tune auto-capture"),
            (self.book_form.submit_button, "Alt+Return", "Create book / save book details"),
            (self.book_form.cancel_button, "Alt+C", "Cancel book form"),
            (self.book_form.browse_folder_button, "Alt+O", "Browse image folder"),
            (self.book_form.default_folder_button, "Alt+D", "Use default folder"),
        ]
        self.shortcut_help = []
        for button, keys, description in bindings:
            button.setShortcut(QKeySequence(keys))
            hint = f"{description} ({QKeySequence(keys).toString(QKeySequence.SequenceFormat.NativeText)})"
            button.setToolTip(button.toolTip() + "\n" + hint if button.toolTip() else hint)
            self.shortcut_help.append(f"{keys}: {description}")
        self.keyboard_shortcuts = []
        for keys, callback, description in [
            ("Alt+B", self.books.setFocus, "Focus books; use arrow keys"),
            ("Alt+P", self.pages.setFocus, "Focus pages; use arrow keys"),
            ("Alt+M", self.devices.setFocus, "Focus camera selector"),
            ("Ctrl+H", self.show_shortcuts, "Show keyboard shortcuts"),
        ]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(callback)
            self.keyboard_shortcuts.append(shortcut)
            self.shortcut_help.append(f"{keys}: {description}")
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("Keyboard shortcuts (Ctrl+H)", self.show_shortcuts)

    def show_shortcuts(self):
        QMessageBox.information(self, "Keyboard shortcuts", "\n".join(self.shortcut_help) +
                                "\n\nTab / Shift+Tab: move between controls. Arrow keys: select books and pages."
                                "\nDrag with the mouse to select a crop or pan a zoomed image.")

    @staticmethod
    def button(text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def error(self, message):
        self.status.setText(str(message))
        QMessageBox.warning(self, "BookScan", str(message))

    def refresh_books(self):
        self.books.blockSignals(True)
        self.books.clear()
        for book in self.library.books:
            self.books.addItem(f"{book['title']}  ({len(book['pages'])})")
        if self.book:
            self.books.setCurrentRow(self.library.books.index(self.book))
        self.books.blockSignals(False)
        self.refresh_pages()

    def refresh_pages(self):
        self.pages.blockSignals(True)
        self.pages.clear()
        if self.book:
            self.location.setText(f"Images: {self.library.image_folder(self.book)}")
            self.location.setToolTip(f"Book metadata: {self.library.path}")
            count = len(self.book["pages"])
            self.heading.setText(f"{self.book['title']} · {self.book['kind']} · {count} saved {'page' if count == 1 else 'pages'}")
            for number, path in enumerate(self.book["pages"], 1):
                if path not in self.thumbnails:
                    reader = QImageReader(str(self.library.page_path(path)))
                    reader.setAutoTransform(True)
                    if reader.size().isValid():
                        reader.setScaledSize(reader.size().scaled(QSize(80, 100), Qt.AspectRatioMode.KeepAspectRatio))
                    self.thumbnails[path] = QIcon(QPixmap.fromImage(reader.read()))
                item = QListWidgetItem(self.thumbnails[path], f"Page {number}")
                item.setData(Qt.ItemDataRole.UserRole, number - 1)
                self.pages.addItem(item)
        else:
            self.heading.setText("Select a book or create a new one")
            self.location.setText(f"Library: {self.library.root}")
        self.pages.blockSignals(False)

    def select_book(self, row):
        if row < 0 or row >= len(self.library.books):
            return
        self.book = self.library.books[row]
        self.refresh_pages()
        self.show_live()

    def choose_book(self):
        if self.book_form.editing_book is not None:
            self.book_form.populate()
        self.book_form.update_state()
        self.book_form.show()
        self.book_form.title.setFocus()
        self.update_controls()

    def cancel_book_form(self):
        self.book_form.hide()
        self.book_form.populate()

    def submit_book(self):
        form = self.book_form
        if not form.submit_button.isEnabled():
            return
        notice = None
        editing = form.editing_book is not None
        try:
            if form.editing_book is not None:
                notice = self.library.update_book(form.editing_book, form.title.text(), form.kind.currentText(),
                                                  form.author.text(), expected_folder=form.destination)
                self.book = form.editing_book
            else:
                self.book = self.library.add_book(form.title.text(), form.kind.currentText(), form.author.text(),
                                                  form.folder.text().strip() if form.folder_overridden else None,
                                                  expected_folder=form.destination if not form.folder_overridden else None)
        except Exception as exc:
            form.update_state()
            form.show_error(exc)
            return
        self.cancel_book_form()
        if editing:
            self.thumbnails.clear()
        self.refresh_books()
        self.show_live()
        if editing:
            self.status.setText(notice or f"Book details saved. Images: {self.library.image_folder(self.book)}")

    def edit_book(self):
        if self.book and self.pending.isNull() and self.capture_id is None:
            self.book_form.populate(self.book)
            self.book_form.show()
            self.book_form.title.setFocus()

    def move_page(self, direction):
        row = self.pages.currentRow()
        if not self.book or row < 0 or not 0 <= row + direction < len(self.book['pages']):
            return
        order = list(range(len(self.book['pages'])))
        order.insert(row + direction, order.pop(row))
        self.reorder_pages(order, row)

    def pages_dropped(self):
        item = self.pages.currentItem()
        selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        order = [self.pages.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.pages.count())]
        self.reorder_pages(order, selected)

    def reorder_pages(self, order, selected):
        if not self.book or not self.pending.isNull() or self.capture_id is not None:
            return
        try:
            self.library.reorder_pages(self.book, order)
        except Exception as exc:
            self.refresh_pages()
            if selected is not None:
                self.pages.setCurrentRow(selected)
            self.error(f"Pages were not reordered: {exc}. Original order and images were kept.")
            return
        self.thumbnails.clear()
        self.refresh_pages()
        if selected is not None:
            self.pages.setCurrentRow(order.index(selected))
        self.status.setText("Page order saved. Image filenames now follow the sidebar order.")
        self.update_controls()

    def edit_selected_page(self):
        row = self.pages.currentRow()
        if not self.book or row < 0 or not self.pending.isNull() or self.capture_id is not None:
            return
        image = QImage(str(self.library.page_path(self.book['pages'][row])))
        if image.isNull():
            self.status.setText("This page's image is unavailable.")
            return
        # Editing starts from the stored image, without automatically trimming it again.
        trim = self.auto_trim.isChecked()
        self.auto_trim.setChecked(False)
        self.present(image)
        self.auto_trim.setChecked(trim)
        self.editing_page = row
        self.review_status()

    def request_remove_book(self):
        if self.book:
            self.show_removal(self.book, None)

    def request_remove_page(self):
        if self.book and self.pages.currentRow() >= 0:
            self.show_removal(self.book, self.pages.currentRow())

    def show_removal(self, book, row):
        if not self.pending.isNull() or self.capture_id is not None:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Delete book" if row is None else "Delete page")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        item = f"book '{book['title']}'" if row is None else f"page {row + 1} from '{book['title']}'"
        dialog.setText(f"Delete {item} from the library?")
        checkbox = None
        if row is None:
            checkbox = QCheckBox("Also delete this book's image files")
            checkbox.setChecked(False)
            checkbox.setToolTip("Move associated images to Trash; keep unrelated files and images used by other books")
            dialog.setCheckBox(checkbox)
            dialog.setInformativeText("Images stay on disk unless checked. Deleted images move to Trash; other files in the folder are kept.")
        else:
            dialog.setInformativeText("The image file will be kept on disk. This page will no longer appear in the book or its PDF.")
        delete_button = dialog.addButton("Delete book" if row is None else "Delete page", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() != delete_button:
            return
        delete_images = checkbox is not None and checkbox.isChecked()
        report = None
        try:
            if row is None:
                report = self.library.remove_book(book, delete_images=delete_images)
                if self.book_form.editing_book is book:
                    self.cancel_book_form()
                if self.book is book:
                    self.book = None
            else:
                self.library.remove_page(book, row)
        except Exception as exc:
            self.status.setText(f"Deletion failed: {exc}")
            return
        self.refresh_books()
        self.show_live()
        if not delete_images:
            self.status.setText("Deleted from the library. Image files were kept on disk.")
        else:
            message = f"Book deleted. Moved {report['deleted']} image(s) to Trash."
            if report['shared']:
                message += f" Kept {report['shared']} image(s) used by other books."
            if report['failed']:
                message += " Some images could not be deleted and remain on disk: " + "; ".join(f"{path}: {reason}" for path, reason in report['failed'])
            self.status.setText(message)

    def refresh_cameras(self):
        if self.capture_id is not None or not self.pending.isNull():
            return
        current = self.devices.currentData()
        current_id = current.id() if current else None
        self.devices.blockSignals(True)
        self.devices.clear()
        inputs = QMediaDevices.videoInputs()
        for device in inputs:
            self.devices.addItem(device.description(), device)
        if not inputs:
            self.devices.addItem("No camera detected", None)
        for index, device in enumerate(inputs):
            if device.id() == current_id:
                self.devices.setCurrentIndex(index)
        self.devices.blockSignals(False)
        self.change_camera()

    def change_camera(self):
        if self.camera:
            self.camera.stop()
            self.session.setCamera(None)
            self.camera.deleteLater()
            self.camera = None
        device = self.devices.currentData()
        if device:
            self.camera = QCamera(device, self)
            self.camera.errorOccurred.connect(lambda _code, message: self.status.setText(f"Camera: {message}. Check permissions or import an image."))
            self.session.setCamera(self.camera)
            self.camera.start()
        self.show_live()

    def show_live(self):
        if not self.pending.isNull():
            return
        self.pages.clearSelection()
        self.stack.setCurrentWidget(self.video if self.camera else self.empty)
        self.status.setText("Position a page, then Capture (Ctrl+S) to save it immediately." if self.book else "Select a book or click New book to begin.")
        self.update_controls()

    def update_controls(self, *_args):
        pending = not self.pending.isNull()
        busy = self.capture_id is not None
        ready = self.book is not None and not pending and not busy
        cropping = self.preview.cropping
        set_button_text(self.capture_button, "Save" if pending else "Capture")
        self.capture_button.setEnabled(not busy and ((pending and not cropping) or
                                       (ready and self.camera is not None and self.capture.isReadyForCapture())))
        self.cancel_button.setEnabled(pending or busy)
        self.auto_trim.setEnabled(not pending and not busy)
        self.import_button.setEnabled(ready)
        self.rotate_button.setEnabled(pending and not cropping)
        self.rotate_left_button.setEnabled(pending and not cropping)
        self.crop_button.setEnabled(pending)
        self.apply_crop_button.setEnabled(pending and cropping and not self.preview.crop_rect().isEmpty())
        self.reset_button.setEnabled(pending)
        viewing = self.stack.currentWidget() is self.preview
        self.zoom_in_button.setEnabled(viewing and self.preview.zoom < 8)
        self.zoom_out_button.setEnabled(viewing and self.preview.zoom > 1)
        self.fit_button.setEnabled(viewing)
        self.zoom_label.setText(f"{self.preview.zoom * 100:.0f}%")
        self.live_button.setEnabled(not pending and not busy)
        self.books.setEnabled(not pending and not busy)
        self.pages.setEnabled(not pending and not busy)
        self.devices.setEnabled(not pending and not busy)
        self.refresh_button.setEnabled(not pending and not busy)
        self.next_button.setEnabled(True)
        self.book_form.set_busy(pending or busy)
        self.edit_book_button.setEnabled(self.book is not None and not pending and not busy)
        self.remove_book_button.setEnabled(self.book is not None and not pending and not busy)
        page_selected = self.book is not None and self.pages.currentRow() >= 0
        self.edit_page_button.setEnabled(page_selected and not pending and not busy)
        self.remove_page_button.setEnabled(page_selected and not pending and not busy)
        row = self.pages.currentRow()
        self.move_up_button.setEnabled(ready and page_selected and row > 0)
        self.move_down_button.setEnabled(ready and page_selected and row + 1 < len(self.book['pages']))
        self.done_button.setEnabled(not busy)
        self.export_button.setEnabled(bool(self.book and self.book["pages"]) and not busy and not pending)

    def toggle_auto_capture(self, enabled):
        self.detector.reset()
        self.status.setText("Auto-capture on: place a page on the black background and hold it still." if enabled else "Auto-capture off.")

    def show_auto_settings(self):
        self.auto_settings.show()
        self.auto_settings.raise_()

    def watch_frame(self, frame):
        previewing = self.auto_settings.isVisible() and self.auto_settings.preview.isChecked()
        now = time.monotonic()
        if not (self.auto_capture.isChecked() or self.auto_settings.isVisible()) or now - self.last_sample < 0.2:
            return
        self.last_sample = now
        live = (self.camera is not None and self.pending.isNull() and self.capture_id is None
                and self.stack.currentWidget() is self.video)
        if not previewing:
            live = live and self.auto_capture.isChecked() and self.book is not None and self.capture.isReadyForCapture()
        if not live:
            self.detector.pause()
            return
        image = frame.toImage()
        if image.isNull():
            return
        fired = self.detector.feed(sample_frame(image), now)
        self.auto_settings.show_readings()
        if fired and previewing:
            self.status.setText("Auto-capture preview: a page would be captured now (nothing saved). Remove the page to re-arm.")
        elif fired:
            self.take_snapshot()
        elif not fired:
            self.status.setText(f"Auto-capture{' preview' if previewing else ''}: {self.detector.state}")

    def capture_or_save(self):
        if self.capture_id is not None:
            return
        if not self.pending.isNull():
            if not self.preview.cropping:
                self.accept_page()
        else:
            self.take_snapshot()

    def cancel_snapshot(self):
        # Late imageSaved callbacks are ignored and their temporary files deleted.
        self.capture_id = None
        self.timeout.stop()
        self.end_crop()
        self.pending = QImage()
        self.original = QImage()
        self.editing_page = None
        self.show_live()
        self.status.setText("Snapshot cancelled. Position the page, then Capture again.")

    def take_snapshot(self):
        if not self.book or not self.pending.isNull() or self.capture_id is not None:
            return
        if not self.capture.isReadyForCapture():
            self.status.setText("Camera is not ready. Wait for a live picture, then capture.")
            return
        self.source = "camera"
        # imageCaptured is only a preview on some devices. Read imageSaved for full resolution.
        self.capture_id = self.capture.captureToFile(str(Path(self.temp.name) / f"{uuid4().hex}.jpg"))
        if self.capture_id < 0:
            self.capture_id = None
            self.status.setText("Capture failed. Check the camera and try again.")
        else:
            self.timeout.start()
            self.status.setText("Capturing full-resolution page…")
        self.update_controls()

    def snapshot_saved(self, capture_id, filename):
        if capture_id != self.capture_id:
            Path(filename).unlink(missing_ok=True)
            return
        self.timeout.stop()
        self.capture_id = None
        reader = QImageReader(filename)
        reader.setAutoTransform(True)
        image = reader.read()
        Path(filename).unlink(missing_ok=True)
        self.present(image)
        if not self.pending.isNull():
            self.accept_page()

    def capture_error(self, capture_id, _code, message):
        if capture_id == self.capture_id:
            self.timeout.stop()
            self.capture_id = None
            self.update_controls()
        self.status.setText(f"Capture failed: {message}. Try again or import an image.")

    def capture_timeout(self):
        self.capture_id = None
        self.status.setText("The camera did not return an image. Reconnect or refresh the camera, then try again.")
        self.update_controls()

    def import_image(self):
        if not self.book or not self.pending.isNull():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Select a page image", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;All files (*)")
        if filename:
            reader = QImageReader(filename)
            reader.setAutoTransform(True)
            self.source = "import"
            self.present(reader.read())

    def present(self, image):
        if image.isNull():
            self.error("Could not read the snapshot. Please capture or import another image.")
            self.update_controls()
            return
        self.end_crop()
        self.editing_page = None
        self.original = QImage(image)
        self.pending = QImage(image)
        trimmed = False
        if self.auto_trim.isChecked():
            bounds = black_background_rect(image)
            if bounds != image.rect():
                self.pending = image.copy(bounds)
                trimmed = True
        self.preview.show_image(self.pending)
        self.stack.setCurrentWidget(self.preview)
        self.review_status()
        if self.auto_trim.isChecked():
            self.status.setText(("Black background trimmed. " if trimmed else "No clear black border found; image unchanged. ") + self.status.text())
        self.update_controls()

    def accept_page(self):
        if self.pending.isNull() or not self.book:
            return False
        try:
            if self.editing_page is None:
                self.library.accept(self.book, self.pending)
            else:
                path = self.book['pages'][self.editing_page]
                self.library.update_page(self.book, self.editing_page, self.pending)
                self.thumbnails.pop(path, None)
        except Exception as exc:
            self.error(f"Page was not saved: {exc}. Your preview is still available to retry.")
            return False
        self.pending = QImage()
        self.original = QImage()
        self.editing_page = None
        self.refresh_books()
        self.show_live()
        self.status.setText("Page saved. Turn the page and capture again, or choose Next book / Done.")
        return True

    def review_status(self):
        number = self.editing_page + 1 if self.editing_page is not None else len(self.book['pages']) + 1
        self.status.setText(f"Review page {number} · {self.pending.width()} × {self.pending.height()} · Save or Cancel.")

    def end_crop(self):
        self.crop_button.setChecked(False)
        set_button_text(self.crop_button, "Crop")
        self.preview.set_cropping(False)

    def rotate(self, angle=90):
        if not self.pending.isNull() and not self.preview.cropping:
            self.pending = self.pending.transformed(QTransform().rotate(angle))
            self.preview.show_image(self.pending)
            self.review_status()

    def toggle_crop(self, enabled):
        if self.pending.isNull():
            self.end_crop()
            return
        self.preview.set_cropping(enabled)
        set_button_text(self.crop_button, "Cancel crop" if enabled else "Crop")
        if enabled:
            self.status.setText("Drag around the area to keep, then Apply crop. Use the wheel to zoom; middle-drag to pan. Cancel crop keeps the image unchanged.")
        else:
            self.review_status()
        self.update_controls()

    def apply_crop(self):
        rect = self.preview.crop_rect()
        if self.pending.isNull() or not self.preview.cropping or rect.isEmpty():
            return
        self.pending = self.pending.copy(rect)
        self.end_crop()
        self.preview.show_image(self.pending)
        self.review_status()

    def reset_edits(self):
        if not self.pending.isNull():
            self.end_crop()
            self.pending = QImage(self.original)
            self.preview.show_image(self.pending)
            self.review_status()

    def review_page(self, row):
        if self.book and 0 <= row < len(self.book["pages"]):
            image = QImage(str(self.library.page_path(self.book["pages"][row])))
            if image.isNull():
                self.error(f"Page {row + 1} is missing or unreadable")
                return
            self.preview.show_image(image)
            self.stack.setCurrentWidget(self.preview)
            self.status.setText(f"Saved page {row + 1}. Use Back to camera to continue scanning.")
            self.update_controls()

    def resolve_pending(self):
        if self.pending.isNull():
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Review unfinished snapshot")
        box.setText("This snapshot has not been saved. What should happen to it?")
        accept = box.addButton("Save and continue", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard snapshot", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() == accept:
            if self.preview.cropping and not self.preview.crop_rect().isEmpty():
                self.apply_crop()
            else:
                self.end_crop()
            return self.accept_page()
        if box.clickedButton() == discard:
            self.end_crop()
            self.pending = QImage()
            self.original = QImage()
            self.editing_page = None
            self.show_live()
            return True
        return False

    def export_pdf(self):
        if not self.pending.isNull() or self.capture_id is not None:
            return
        book = self.book
        if book is None or not book['pages']:
            self.status.setText("Select a book with saved pages to export.")
            return
        try:
            default = self.library.image_folder(book) / f"{portable_book_name(book['title'])}.pdf"
            filename, _ = QFileDialog.getSaveFileName(
                self, f"Export {book['title']} — all {len(book['pages'])} pages", str(default),
                "PDF files (*.pdf)", options=QFileDialog.Option.DontConfirmOverwrite)
            if not filename:
                return
            destination = Path(filename)
            if destination.suffix.lower() != '.pdf':
                destination = destination.with_name(destination.name + '.pdf')
            if destination.exists():
                answer = QMessageBox.question(
                    self, "Replace PDF?", f"Replace {destination}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.library.export_pdf(book, destination)
            self.status.setText(f"Exported {book['title']}: all {len(book['pages'])} pages to {destination}.")
        except Exception as exc:
            self.error(exc)

    def closeEvent(self, event):
        if self.capture_id is not None:
            self.status.setText("Wait for the current capture to finish before closing.")
            event.ignore()
            return
        if not self.resolve_pending():
            event.ignore()
            return
        try:
            self.library.save()
        except Exception as exc:
            self.error(f"Could not save the library: {exc}")
            event.ignore()
            return
        if self.camera:
            self.camera.stop()
        self.temp.cleanup()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="Scan and organize books with a camera and Qt")
    parser.add_argument("--library", type=Path, help="Library folder (default: Documents/BookScan)")
    parser.add_argument("--install-desktop", action="store_true", help="Install the application icon and launcher for this Linux user")
    args = parser.parse_args()
    if args.install_desktop:
        try:
            print(install_desktop())
            return 0
        except (OSError, ValueError) as exc:
            print(f"Cannot install BookScan desktop launcher: {exc}", file=sys.stderr)
            return 1
    app = QApplication(sys.argv[:1])
    app.setApplicationName("BookScan")
    app.setDesktopFileName("bookscan")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setOrganizationName("BookScan")
    root = args.library or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)) / "BookScan"
    try:
        # Prevent two application instances from overwriting the same manifest.
        from PySide6.QtCore import QLockFile
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(root / ".bookscan.lock"))
        if not lock.tryLock(0):
            raise OSError("This library is already open in another BookScan window")
        library = Library(root)
    except Exception as exc:
        QMessageBox.critical(None, "Cannot open library", str(exc))
        return 1
    window = ScanWindow(library)
    window.show()
    app.aboutToQuit.connect(window.deleteLater)
    return app.exec()
