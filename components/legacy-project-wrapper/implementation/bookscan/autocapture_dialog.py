"""Tuning panel for auto-capture, with a preview mode that never saves pages."""
from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout

from .autocapture import AutoCaptureDetector


class AutoCaptureSettings(QDialog):
    """Edits a detector's thresholds live and shows the readings it is judging."""
    changed = Signal()

    def __init__(self, detector, parent=None):
        super().__init__(parent)
        self.detector = detector
        self.setWindowTitle("Auto-capture settings")
        layout = QVBoxLayout(self)
        self.preview = QCheckBox("Preview only — detect and report, but do not capture or save")
        self.preview.setChecked(True)
        self.preview.toggled.connect(self.changed)
        layout.addWidget(self.preview)
        form = QFormLayout()
        self.hold = self.add(form, QDoubleSpinBox(), "hold_seconds", "Hold still for (seconds)", (0.5, 30), 0.5, 1,
                             "How long the page must stay still before capturing.")
        self.bright = self.add(form, QSpinBox(), "bright_level", "Brightness above black (0–255)", (1, 254), 1, 0,
                               "Pixels brighter than this count as page, not the black background.")
        self.content = self.add(form, QDoubleSpinBox(), "min_content", "Minimum page coverage (%)", (1, 100), 1, 0,
                                "Share of the picture that must be non-black to count as a page.", scale=100)
        self.motion = self.add(form, QDoubleSpinBox(), "motion_level", "Motion tolerance (gray levels)", (0.5, 50), 0.5, 1,
                               "Average pixel change that counts as movement. Raise it if noise keeps restarting the timer.")
        layout.addLayout(form)
        self.readout = QLabel("No live readings yet.")
        self.readout.setWordWrap(True)
        layout.addWidget(self.readout)
        reset = QPushButton("Reset to defaults")
        reset.setShortcut("Ctrl+Shift+D")
        reset.setToolTip("Reset to defaults (Ctrl+Shift+D)")
        reset.clicked.connect(self.reset)
        layout.addWidget(reset)
        self.load()

    def add(self, form, box, name, label, limits, step, decimals, tip, scale=1):
        box.setRange(*limits)
        box.setSingleStep(step)
        if decimals:
            box.setDecimals(decimals)
        box.setToolTip(tip)
        box.setValue(getattr(self.detector, name) * scale)
        box.valueChanged.connect(lambda value, n=name, k=scale: self.apply(n, value / k))
        box.name = name
        form.addRow(label, box)
        return box

    def apply(self, name, value):
        setattr(self.detector, name, value)
        QSettings("bookscan", "bookscan").setValue(f"autocapture/{name}", value)
        self.changed.emit()

    def load(self):
        stored = QSettings("bookscan", "bookscan")
        for box in (self.hold, self.bright, self.content, self.motion):
            value = stored.value(f"autocapture/{box.name}", None)
            if value is not None:
                setattr(self.detector, box.name, float(value))
                box.blockSignals(True)
                box.setValue(float(value) * (100 if box is self.content else 1))
                box.blockSignals(False)

    def reset(self):
        defaults = AutoCaptureDetector.DEFAULTS
        for box, scale in ((self.hold, 1), (self.bright, 1), (self.content, 100), (self.motion, 1)):
            box.setValue(defaults[box.name] * scale)

    def show_readings(self):
        d = self.detector
        self.readout.setText(
            f"Page coverage {d.content * 100:.0f}% (needs {d.min_content * 100:.0f}%) · "
            f"motion {d.motion:.1f} (limit {d.motion_level:.1f}) · "
            f"still {d.held:.1f}s of {d.hold_seconds:.1f}s — {d.state}")
