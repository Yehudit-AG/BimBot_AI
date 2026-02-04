"""
Shared constants for wall candidate detection.

All distance and length thresholds use the same units as the pipeline coordinates
(drawing units). For typical CAD/DWG exports these are millimeters (mm).
"""

# Parallelism: max angle difference in degrees (lines within this are considered parallel)
# Increased to allow slightly diagonal walls (e.g. 10° catches "almost horizontal/vertical")
ANGULAR_TOLERANCE_DEG = 10.0

# Perpendicular distance between pair of lines (same unit as drawing coordinates, typically mm)
MIN_DISTANCE = 10.0   # e.g. 10 mm (inclusive)
MAX_DISTANCE = 450.0  # e.g. 450 mm (inclusive)

# Minimum overlap as percentage of longer segment (pair-based detection)
MIN_OVERLAP_PERCENTAGE = 90.0  # percent

# Minimum longitudinal overlap length (same unit as drawing, typically mm)
# Can be used by overlap-based logic to avoid ghost pairs from near-zero overlap
MIN_OVERLAP_LENGTH = 1.0  # e.g. 1.0 mm

# Mock mode only (same drawing units)
MOCK_MIN_WALL_LENGTH = 500.0
MOCK_PROXIMITY_THRESHOLD = 200.0
MOCK_AVERAGE_WALL_THICKNESS = 150.0

# ---------------------------------------------------------------------------
# LOGIC B (overlap-only wall pair detection)
# ---------------------------------------------------------------------------
# Angular tolerance for "parallel enough" (degrees). Parallel test:
# abs(cross2(d1, d2)) <= sin(radians(LOGIC_B_ANGULAR_TOLERANCE_DEG))
LOGIC_B_ANGULAR_TOLERANCE_DEG = 2.0
