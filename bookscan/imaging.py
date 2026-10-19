"""Conservative rectangular trimming of a page against a black camera mat."""
import math

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage


def black_background_rect(image):
    """Find nonblack page bounds, leaving a small safety margin.

    Inspect a reduced grayscale copy, then map bounds back to original pixels.
    Require a mostly black perimeter and ignore sparse bright noise. Ambiguous,
    empty, and uniformly dark images retain their original bounds.
    """
    if image.isNull():
        return QRect()
    original = image.rect()
    if min(image.width(), image.height()) < 16:
        return original
    sample = image.scaled(640, 640, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    width, height = sample.width(), sample.height()
    stride = sample.bytesPerLine()
    pixels = sample.constBits()
    rows, columns = [0] * height, [0] * width
    border_count = border_bright = 0
    border = max(1, min(width, height) // 50)
    for y in range(height):
        for x in range(width):
            bright = pixels[y * stride + x] > 45
            if bright:
                rows[y] += 1
                columns[x] += 1
            if x < border or y < border or x >= width - border or y >= height - border:
                border_count += 1
                border_bright += bright
    if border_bright > border_count * 0.2:
        return original
    ys = [y for y, count in enumerate(rows) if count >= max(3, width * 0.025)]
    xs = [x for x, count in enumerate(columns) if count >= max(3, height * 0.025)]
    if not xs or not ys:
        return original
    left, right, top, bottom = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    # Avoid interpreting a few bright marks on a dark book as the page itself.
    if (right - left) * (bottom - top) < width * height * 0.08:
        return original
    foreground = sum(rows[top:bottom])
    if foreground < (right - left) * (bottom - top) * 0.25:
        return original
    margin = 2
    x0 = max(0, math.floor((left - margin) * image.width() / width))
    y0 = max(0, math.floor((top - margin) * image.height() / height))
    x1 = min(image.width(), math.ceil((right + margin) * image.width() / width))
    y1 = min(image.height(), math.ceil((bottom + margin) * image.height() / height))
    return QRect(x0, y0, x1 - x0, y1 - y0)
