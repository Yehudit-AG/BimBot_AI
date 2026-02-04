"""
Unit conversion and epsilon constants for pipeline geometry.

Internal drawing units are millimeters (mm). All distance/length comparisons
and LOGIC B thresholds use this module for consistency.
"""

# Epsilon in mm (unit-aware)
# Strict comparisons (parallel, length, point-on-segment)
EPS_MM = 1e-3  # 0.001 mm
# Overlap emptiness check (overlapMax <= overlapMin + EPS_OVERLAP_MM -> no pair)
EPS_OVERLAP_MM = 1e-2  # 0.01 mm (bump to 0.1 if geometry is noisy)
# Dedup: round overlap scalars to this precision (mm) for key
DEDUP_OVERLAP_PRECISION_MM = 0.1  # 0.1 mm

# LOGIC B distance range in cm (converted to internal mm)
LOGIC_B_MIN_CM = 1.0
LOGIC_B_MAX_CM = 45.0


def cm_to_internal(cm: float) -> float:
    """Convert centimeters to internal units (mm). Single source of truth."""
    return float(cm * 10.0)
