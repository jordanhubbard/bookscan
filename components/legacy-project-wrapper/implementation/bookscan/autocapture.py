"""Decide when a page has been placed under the camera and has stopped moving."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

SAMPLE_WIDTH, SAMPLE_HEIGHT = 64, 48


def sample_frame(image):
    """Reduce a frame to a small grayscale byte string for cheap comparison."""
    small = image.scaled(SAMPLE_WIDTH, SAMPLE_HEIGHT, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    stride = small.bytesPerLine()
    data = bytes(small.constBits())
    return b"".join(data[y * stride:y * stride + SAMPLE_WIDTH] for y in range(SAMPLE_HEIGHT))


class AutoCaptureDetector:
    """Fire once when non-black content stays still, then wait for the mat to clear.

    Frames are compared with the first frame of the current still period, so slow
    drift and sensor noise cannot keep the timer alive or reset it indefinitely.
    """

    DEFAULTS = {"hold_seconds": 3.0, "bright_level": 45, "min_content": 0.08, "motion_level": 4.0}

    def __init__(self, **settings):
        self.reset_settings()
        for name, value in settings.items():
            setattr(self, name, value)
        self.reset()

    def reset_settings(self):
        for name, value in self.DEFAULTS.items():
            setattr(self, name, value)

    def reset(self):
        self.armed = True
        self.anchor = None
        self.still_since = None
        self.content = self.motion = self.held = 0.0

    def pause(self):
        """Forget the current hold without re-arming, e.g. while a capture is in progress."""
        self.anchor = self.still_since = None

    def feed(self, frame, now):
        """Return True when the frame completes a still hold. `frame` is sample_frame() bytes."""
        self.content = sum(1 for value in frame if value > self.bright_level) / len(frame)
        self.motion = self.difference(frame, self.anchor) if self.anchor is not None else 0.0
        self.held = now - self.still_since if self.still_since is not None else 0.0
        if self.content < self.min_content:
            self.armed = True
            self.anchor = self.still_since = None
            self.held = 0.0
            return False
        if not self.armed:
            return False
        if self.anchor is None or self.motion > self.motion_level:
            self.anchor, self.still_since = frame, now
            self.held = 0.0
            return False
        if now - self.still_since >= self.hold_seconds:
            self.armed = False
            self.anchor = self.still_since = None
            return True
        return False

    @staticmethod
    def difference(a, b):
        return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

    @property
    def state(self):
        if self.anchor is None:
            return "waiting for a page" if self.armed else "remove the page to re-arm"
        return "holding still"
