from enum import IntEnum


MIN_BAR_HEIGHT = 10     # pixels
MAX_BAR_HEIGHT = 100    # pixels
SCROLL_BAR_HEIGHT = 20  # pixels


class ZoomLevel(IntEnum):
    YEAR = 1
    MONTH = 2
    DAY = 3


DEFAULT_ZOOM_LEVEL = ZoomLevel.MONTH
