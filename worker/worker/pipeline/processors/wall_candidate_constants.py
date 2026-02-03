"""
Shared constants for wall candidate detection (Logic A and Logic B).

All distance and length thresholds use the same units as the pipeline coordinates
(drawing units). For typical CAD/DWG exports these are millimeters (mm).
Logic A and Logic B use the same MIN_DISTANCE, MAX_DISTANCE, and ANGULAR_TOLERANCE
so that both algorithms measure in the same unit system.
"""

# Parallelism: max angle difference in degrees (lines within this are considered parallel)
# Increased to allow slightly diagonal walls (e.g. 10° catches "almost horizontal/vertical")
ANGULAR_TOLERANCE_DEG = 10.0

# Perpendicular distance between pair of lines (same unit as drawing coordinates, typically mm)
MIN_DISTANCE = 10.0   # e.g. 10 mm (inclusive)
MAX_DISTANCE = 450.0  # e.g. 450 mm (inclusive)

# Logic A: minimum overlap as percentage of longer segment
MIN_OVERLAP_PERCENTAGE = 90.0  # percent

# Logic B: minimum longitudinal overlap length (same unit as drawing, typically mm)
# Avoids ghost pairs from near-zero overlap due to floating point noise
MIN_OVERLAP_LENGTH = 1.0  # e.g. 1.0 mm

# Logic A mock mode only (same drawing units)
MOCK_MIN_WALL_LENGTH = 500.0
MOCK_PROXIMITY_THRESHOLD = 200.0
MOCK_AVERAGE_WALL_THICKNESS = 150.0
