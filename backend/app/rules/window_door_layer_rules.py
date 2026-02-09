"""
Window and door layer identification rules.
Single source of truth for "is this layer a window/door layer?" (case-insensitive substring match).
"""

# Keywords: substring match case-insensitive (English + Hebrew)
KEYWORDS = (
    "window",
    "door",
    "חלון",  # window (Hebrew)
    "דלת",   # door (Hebrew)
)

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

EXPLICIT_NAMES = tuple(n.upper() for n in (*WINDOW_LAYER_NAMES, *DOOR_LAYER_NAMES))


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
