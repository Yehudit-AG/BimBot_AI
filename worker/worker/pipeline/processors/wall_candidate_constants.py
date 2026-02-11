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

# ---------------------------------------------------------------------------
# LOGIC C (pair filtering by intervening lines)
# ---------------------------------------------------------------------------
# Minimum intersection length (mm) with strip interior to count as "blocking".
# Do not reuse EPS for this; EPS is for numeric robustness only.
MIN_BLOCKING_LENGTH_MM = 1.0

# ---------------------------------------------------------------------------
# LOGIC D (containment pruning)
# ---------------------------------------------------------------------------
# Tolerance for containment (mm). B is contained in A if A.buffer(TOL_MM).covers(B).
# Use max(EPS_MM, 0.1) at runtime; 0.1 mm default.
CONTAINMENT_TOL_MM = 0.1
# Minimum area difference (mm²) so that A is considered strictly larger than B: area(A) > area(B) + AREA_EPS.
CONTAINMENT_AREA_EPS_MM2 = 1e-6

# ---------------------------------------------------------------------------
# LOGIC E (band-based adjacency merge)
# ---------------------------------------------------------------------------
# Perpendicular thickness range (mm) for eligibility to merge.
THICKNESS_MIN_MM = 20.0
THICKNESS_MAX_MM = 450.0
# Band line matching: quantize coordinates to this tolerance (mm).
LINE_COORD_TOL_MM = 0.5
# Adjacency gap along run axis (mm); intervals within this are mergeable.
GAP_TOL_MM = 1.0

# ---------------------------------------------------------------------------
# LOGIC F (L-junction extension)
# ---------------------------------------------------------------------------
# Angle tolerance (degrees) for "approximately perpendicular" L-junctions.
LOGIC_F_ANGLE_TOL_DEG = 25.0
# Dot-product tolerance: |dot(u1,u2)| <= this for perpendicular (0 = exact 90°).
LOGIC_F_ANGLE_DOT_TOL = 0.3
# Maximum extension length (mm) per rectangle when closing L-junction gap.
LOGIC_F_MAX_EXTENSION_MM = 300.0
# Max distance (mm) from rectangle centerline to junction center to consider extending.
LOGIC_F_MAX_JUNCTION_DISTANCE_MM = 400.0
