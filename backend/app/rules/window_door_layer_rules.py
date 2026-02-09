"""
Window and door layer identification rules.
Single source of truth for "is this layer a window/door layer?" (case-insensitive substring match).
"""

from typing import Optional

# Keywords: substring match case-insensitive (English + Hebrew)
KEYWORDS_WINDOW = ("window", "חלון")
KEYWORDS_DOOR = ("door", "דלת")
KEYWORDS = KEYWORDS_WINDOW + KEYWORDS_DOOR

# Explicit layer names (substring match, case-insensitive). Authoritative list from requirement.
WINDOW_LAYER_NAMES = (
    "A-WINDOW",
    "A-WIN",
    "ARCH-WINDOW",
    "WIN",
    "WINDOWS",
    "A-OPENING-WIN",
    "A-WIN-OPEN",
    "A-WIN-CLOSED",
    "A-WIN-SLIDING",
    "A-WIN-FIXED",
    "A-WIN-TILT",
    "A-WIN-SECTION",
    "A-WIN-ELEVATION",
    "A-WIN-PLAN",
    "A-GLAZ",
    "A-OPEN",
    "A-FENST",
    "A-WIND-FRM",
    "A-WIND-GLS",
)

DOOR_LAYER_NAMES = (
    "A-DOO R",  # exact as in spec (with space)
    "A-DR",
    "ARCH-DOOR",
    "DOOR",
    "DOORS",
    "A-OPENING-DOOR",
    "A-DOOR-SWING",
    "A-DOOR-SLIDING",
    "A-DOOR-FOLDING",
    "A-DOOR-REVOLVING",
    "A-DOOR-AUTOMATIC",
    "A-DOOR-ROLLING",
    "A-DOOR-FIXED",
    "A-DOOR-OPEN",
    "A-DOOR-CLOSED",
    "A-DOOR-PLAN",
    "A-DOOR-ELEVATION",
    "A-DOOR-SECTION",
)

WINDOW_NAMES_UPPER = tuple(n.upper() for n in WINDOW_LAYER_NAMES)
DOOR_NAMES_UPPER = tuple(n.upper() for n in DOOR_LAYER_NAMES)
EXPLICIT_NAMES = WINDOW_NAMES_UPPER + DOOR_NAMES_UPPER


def get_window_door_type(layer_name: str) -> Optional[str]:
    """
    Return "window", "door", or None for the given layer name.
    Uses the same rules as is_window_or_door_layer but distinguishes window vs door.
    """
    if not layer_name or not isinstance(layer_name, str):
        return None
    name_upper = layer_name.upper()
    name_lower = layer_name.lower()

    # Explicit window names first
    for explicit in WINDOW_NAMES_UPPER:
        if explicit in name_upper:
            return "window"
    # Explicit door names
    for explicit in DOOR_NAMES_UPPER:
        if explicit in name_upper:
            return "door"
    # Keywords: window / חלון
    for kw in KEYWORDS_WINDOW:
        if kw in name_lower or kw in layer_name:
            return "window"
    # Keywords: door / דלת
    for kw in KEYWORDS_DOOR:
        if kw in name_lower or kw in layer_name:
            return "door"
    return None


def is_window_or_door_layer(layer_name: str) -> bool:
    """
    Return True if the layer name identifies a window or door layer.

    Matching (all case-insensitive):
    - Substring of English keywords: window, door
    - Substring of Hebrew keywords: חלון, דלת
    - Substring of any explicit name from the requirement list.

    Args:
        layer_name: The layer name from the drawing JSON (LayerName field).

    Returns:
        True if the layer should be included as window/door for block collection.
    """
    if not layer_name or not isinstance(layer_name, str):
        return False
    name_upper = layer_name.upper()
    name_lower = layer_name.lower()

    for kw in KEYWORDS:
        if kw in name_lower or kw in layer_name:
            return True

    for explicit in EXPLICIT_NAMES:
        if explicit in name_upper:
            return True

    return False
