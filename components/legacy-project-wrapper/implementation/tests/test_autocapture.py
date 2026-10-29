from bookscan.autocapture import AutoCaptureDetector

SIZE = 64 * 48
BLACK = bytes([5]) * SIZE
PAGE = bytes([200]) * SIZE
MOVED = bytes([200] * (SIZE // 2) + [20] * (SIZE // 2))


def run(detector, frames):
    return [detector.feed(frame, t) for t, frame in frames]


def test_black_mat_never_fires():
    detector = AutoCaptureDetector()
    assert not any(run(detector, [(t, BLACK) for t in range(10)]))


def test_fires_once_after_three_still_seconds():
    detector = AutoCaptureDetector()
    results = run(detector, [(t * 0.5, PAGE) for t in range(12)])
    assert results.index(True) == 6 and results.count(True) == 1


def test_movement_restarts_the_hold():
    detector = AutoCaptureDetector()
    frames = [(0, PAGE), (1, PAGE), (2, MOVED), (3, MOVED), (4, MOVED), (4.9, MOVED), (5.1, MOVED)]
    assert run(detector, frames) == [False] * 6 + [True]


def test_rearms_only_after_page_is_removed():
    detector = AutoCaptureDetector()
    assert any(run(detector, [(t, PAGE) for t in range(5)]))
    assert not any(run(detector, [(t, PAGE) for t in range(5, 20)]))
    detector.feed(BLACK, 20)
    assert any(run(detector, [(t, PAGE) for t in range(21, 26)]))


def test_dark_content_is_ignored():
    detector = AutoCaptureDetector()
    assert not any(run(detector, [(t, bytes([30]) * SIZE) for t in range(10)]))


def test_thresholds_are_adjustable_and_readings_exposed():
    detector = AutoCaptureDetector(hold_seconds=1.0, bright_level=100)
    assert not detector.feed(bytes([60]) * SIZE, 0)
    assert detector.content == 0.0
    detector.bright_level = 45
    detector.feed(PAGE, 1)
    assert detector.content == 1.0
    assert detector.feed(PAGE, 2.5)
    detector.reset_settings()
    assert detector.hold_seconds == 3.0
