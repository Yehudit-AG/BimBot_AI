"""
WALL_CANDIDATES_B processor - Second wall candidate detection logic (Logic B).

Purpose: find pairs of line-like segments that can represent wall faces (two parallel
lines at a typical wall thickness). Used to verify why some lines never get paired.

--- Core principle ---
A pair is formed ONLY from existing geometry. The pair is EXACTLY the overlap region
(100%) — no added lines, no extended lines. Only the portion of each line that lies
in the longitudinal overlap is emitted; precision is mandatory.

--- Criteria (see wall_candidate_constants) ---
- Parallelism: directions within ANGULAR_TOLERANCE_DEG (default 5°).
- Perpendicular distance: between MIN_DISTANCE and MAX_DISTANCE (e.g. 20–450 mm).
- Longitudinal overlap: length along the line direction >= MIN_OVERLAP_LENGTH (e.g. 1 mm).
- Trimmed segments: strictly the overlap interval on each line; if either line's
  overlap would fall outside [0,1] in its parameterization, the pair is rejected
  (no clamping that could extend geometry).
- Non-duplicate pairs; deterministic ordering.

--- Input (from pipeline) ---
Reads pipeline_data["parallel_naive_results"]["entities"]["parallel_ready_entities"].
Expects entities with entity_type LINE or POLYLINE; POLYLINE is expanded into
one virtual LINE per segment. Entities must have normalized_data with Start/End
(or Vertices for POLYLINE) and will have entity_hash after clean_dedup.

--- Output ---
- wall_candidate_pairs: list of pair dicts (trimmed geometry, distances, etc.).
- detection_stats: counts (entities_analyzed, candidate_pairs, total_pairs_checked).
- unpaired_entity_hashes: list of entity_hash that do not appear in any pair (for debugging).
- rejection_stats: counts of why candidate pairs were rejected (not_parallel, distance, overlap_*, duplicate).
"""

import sys
import time
import math
import uuid
from typing import Dict, Any, List, Tuple, Optional
from .base_processor import BaseProcessor
from .wall_candidate_constants import (
    ANGULAR_TOLERANCE_DEG,
    MIN_DISTANCE,
    MAX_DISTANCE,
    MIN_OVERLAP_LENGTH,
)

# When True, log every (i, j) pair rejection with hashes and reason (can be very noisy).
VERBOSE_PAIR_LOGGING = False

# Reasons for which we log numeric decision values (to pinpoint exact failure without guessing).
REJECTION_REASONS_WITH_NUMERICS = frozenset({
    "s_out_of_range",
    "distance_out_of_range",
    "overlap_too_short",
    "span2_zero",
})
# Max number of focused logs per reason per run (avoids flood; 1–2 examples usually enough).
MAX_NUMERICS_LOGS_PER_REASON = 3

# When set, Logic B logs every step only when this exact pair (unordered) is being checked.
DEBUG_PAIR_HASHES: Optional[frozenset] = frozenset({
    "5ba60ec18c5551d6e94c076314e1662d822460824673da9fc4ef81de67b19af6",
    "a74a32881f187ae2a2be9ed53f5bbd12434670aeac47ca19c1ca174a81fb17fc",
})


class WallCandidatesProcessorB(BaseProcessor):
    """Processor for wall candidate detection Logic B: trimmed segments; same units as Logic A."""

    ANGULAR_TOLERANCE = ANGULAR_TOLERANCE_DEG
    MIN_DISTANCE = MIN_DISTANCE
    MAX_DISTANCE = MAX_DISTANCE

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Logic B wall candidate detection on LINE entities and polyline segments.
        Reads parallel_naive_results, builds line-like list, detects pairs, and
        computes unpaired entities + rejection stats for debugging.
        """
        self.log_info("[LogicB] Starting")
        start_time = time.time()

        parallel_results = pipeline_data.get("parallel_naive_results", {})
        entities_data = parallel_results.get("entities", {})
        parallel_ready_entities = entities_data.get("parallel_ready_entities", [])

        line_like_entities = self._build_line_like_entities(parallel_ready_entities)
        n_line_like = len(line_like_entities)
        total_pairs_checked = n_line_like * (n_line_like - 1) // 2 if n_line_like > 1 else 0
        debug_pair_indices = None
        if DEBUG_PAIR_HASHES:
            pair_indices = {
                (e.get("entity_hash") or ""): idx
                for idx, e in enumerate(line_like_entities)
                if (e.get("entity_hash") or "") in DEBUG_PAIR_HASHES
            }
            if len(pair_indices) == 2:
                debug_pair_indices = dict(pair_indices)
                self.log_info(
                    "[LogicB-DEBUG] debug pair both present (IDs as on canvas)",
                    id_1=list(DEBUG_PAIR_HASHES)[0],
                    id_2=list(DEBUG_PAIR_HASHES)[1],
                    position_1=debug_pair_indices.get(list(DEBUG_PAIR_HASHES)[0]),
                    position_2=debug_pair_indices.get(list(DEBUG_PAIR_HASHES)[1]),
                    total_line_like=n_line_like,
                )
        self.log_info(
            "[LogicB] Input",
            line_like=n_line_like,
            pairs_to_check=total_pairs_checked,
        )

        rejection_stats: Dict[str, int] = {}
        wall_candidate_pairs = self._detect_wall_candidate_pairs(
            line_like_entities, rejection_stats, debug_pair_indices=debug_pair_indices
        )

        n = len(line_like_entities)
        detection_stats = {
            "entities_analyzed": n,
            "candidate_pairs": len(wall_candidate_pairs),
            "total_pairs_checked": total_pairs_checked,
        }

        # Unpaired: entity_hashes that never appear in any pair
        paired_hashes = set()
        for p in wall_candidate_pairs:
            paired_hashes.add(p["line1"].get("entity_hash", ""))
            paired_hashes.add(p["line2"].get("entity_hash", ""))
        all_hashes = [e.get("entity_hash") or "" for e in line_like_entities]
        unpaired_entity_hashes = [h for h in all_hashes if h and h not in paired_hashes]
        n_unpaired = len(unpaired_entity_hashes)
        detection_stats["unpaired_count"] = n_unpaired
        detection_stats["paired_count"] = len(paired_hashes)

        self.log_info(
            "[LogicB] Summary",
            pairs=len(wall_candidate_pairs),
            paired_entities=len(paired_hashes),
            unpaired=n_unpaired,
            sample_unpaired=unpaired_entity_hashes[:5] if n_unpaired else [],
        )
        self.log_info("[LogicB] Rejection stats", **rejection_stats)

        total_length = 0.0
        avg_distance = 0.0
        avg_overlap_mm = 0.0
        if wall_candidate_pairs:
            total_length = sum(
                p["geometric_properties"]["average_length"] for p in wall_candidate_pairs
            )
            avg_distance = (
                sum(
                    p["geometric_properties"]["perpendicular_distance"]
                    for p in wall_candidate_pairs
                )
                / len(wall_candidate_pairs)
            )
            avg_overlap_mm = (
                sum(
                    p["geometric_properties"].get("overlap_length_mm", 0.0)
                    for p in wall_candidate_pairs
                )
                / len(wall_candidate_pairs)
            )

        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            entities_analyzed=detection_stats["entities_analyzed"],
            candidate_pairs=detection_stats["candidate_pairs"],
            total_pairs_checked=detection_stats["total_pairs_checked"],
            average_distance=avg_distance,
            average_overlap_mm=avg_overlap_mm,
            total_length=total_length,
            unpaired_count=n_unpaired,
        )

        self.log_info(
            "[LogicB] Done",
            pairs=len(wall_candidate_pairs),
            unpaired=n_unpaired,
            ms=duration_ms,
        )

        return {
            "wall_candidate_pairs": wall_candidate_pairs,
            "detection_stats": detection_stats,
            "unpaired_entity_hashes": unpaired_entity_hashes,
            "rejection_stats": rejection_stats,
            "algorithm_config": {
                "angular_tolerance": self.ANGULAR_TOLERANCE,
                "min_distance": self.MIN_DISTANCE,
                "max_distance": self.MAX_DISTANCE,
                "min_overlap_length": MIN_OVERLAP_LENGTH,
            },
            "totals": {
                "candidate_pairs": len(wall_candidate_pairs),
                "total_length": total_length,
                "average_distance": avg_distance,
                "average_overlap_mm": avg_overlap_mm,
                "unpaired_count": n_unpaired,
            },
        }

    def _detect_wall_candidate_pairs(
        self,
        line_entities: List[Dict[str, Any]],
        rejection_stats: Optional[Dict[str, int]] = None,
        debug_pair_indices: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detect pairs: parallel, distance in range, longitudinal overlap >= MIN_OVERLAP_LENGTH;
        trimmed segments; no duplicates. Fills rejection_stats with counts per rejection reason.
        """
        if rejection_stats is None:
            rejection_stats = {}
        pairs: List[Dict[str, Any]] = []
        seen: set = set()
        overlap_reason: List[str] = []  # reused to get rejection reason from _trim
        debug_i, debug_j = None, None
        if debug_pair_indices and len(debug_pair_indices) == 2:
            idx_list = list(debug_pair_indices.values())
            debug_i, debug_j = min(idx_list), max(idx_list)

        # Diagnostic: at entry, where are the debug hashes? (same list we're about to iterate)
        if DEBUG_PAIR_HASHES:
            at_entry: Dict[str, int] = {}
            for idx, e in enumerate(line_entities):
                h = (e.get("entity_hash") or "")
                if h in DEBUG_PAIR_HASHES:
                    at_entry[h] = idx
            if len(at_entry) == 2:
                self.log_info(
                    "[LogicB-DEBUG] at entry to _detect_wall_candidate_pairs (hash -> index)",
                    hash_to_index=at_entry,
                    expected_from_process=debug_pair_indices,
                )
                sys.stderr.flush()

        for i, line1 in enumerate(line_entities):
            for j, line2 in enumerate(line_entities[i + 1 :], i + 1):
                h1 = line1.get("entity_hash") or ""
                h2 = line2.get("entity_hash") or ""
                is_debug_pair = bool(
                    DEBUG_PAIR_HASHES and frozenset([h1, h2]) == DEBUG_PAIR_HASHES
                )
                # Log when we hit (debug_i, debug_j) so we can see if indices match hashes
                if debug_i is not None and i == debug_i and j == debug_j and not is_debug_pair:
                    self.log_info(
                        "[LogicB-DEBUG] at indices (i,j) from process() but hashes do NOT match debug pair",
                        position_i=i,
                        position_j=j,
                        actual_id_at_i=h1,
                        actual_id_at_j=h2,
                        expected_ids=list(DEBUG_PAIR_HASHES) if DEBUG_PAIR_HASHES else [],
                    )
                    sys.stderr.flush()
                if is_debug_pair:
                    nd1 = line1.get("normalized_data", {}) or {}
                    nd2 = line2.get("normalized_data", {}) or {}
                    s1 = nd1.get("Start", {})
                    e1 = nd1.get("End", {})
                    s2 = nd2.get("Start", {})
                    e2 = nd2.get("End", {})
                    self.log_info(
                        "[LogicB-DEBUG] >>> CHECKING PAIR (canvas IDs) positions + outcome below <<<",
                        id_1=h1,
                        id_2=h2,
                        position_i=i,
                        position_j=j,
                        line1_start_XY=(s1.get("X"), s1.get("Y")),
                        line1_end_XY=(e1.get("X"), e1.get("Y")),
                        line2_start_XY=(s2.get("X"), s2.get("Y")),
                        line2_end_XY=(e2.get("X"), e2.get("Y")),
                    )
                    sys.stderr.flush()
                if not self._are_parallel(line1, line2):
                    rejection_stats["not_parallel"] = rejection_stats.get("not_parallel", 0) + 1
                    if is_debug_pair:
                        self.log_info(
                            "[LogicB-DEBUG] pair rejected: not_parallel",
                            outcome_he="לא זוג: לא מקבילים",
                            hash1=h1,
                            hash2=h2,
                            index_i=i,
                            index_j=j,
                        )
                        sys.stderr.flush()
                    if VERBOSE_PAIR_LOGGING:
                        self.log_info(
                            "[LogicB] Pair rejected: not_parallel",
                            hash1=h1,
                            hash2=h2,
                            index_i=i,
                            index_j=j,
                        )
                    continue
                overlap_reason.clear()
                debug_numerics: Dict[str, Any] = {}
                trim_result = self._trim_to_longitudinal_overlap(
                    line1, line2, overlap_reason, debug_numerics
                )
                overlap_mm, trimmed1, trimmed2, overlap_start, overlap_end = (
                    trim_result[0], trim_result[1], trim_result[2], trim_result[3], trim_result[4]
                )
                if overlap_mm is None or overlap_mm < MIN_OVERLAP_LENGTH:
                    reason = overlap_reason[0] if overlap_reason else "overlap_too_short"
                    rejection_stats[reason] = rejection_stats.get(reason, 0) + 1
                    if is_debug_pair:
                        self.log_info(
                            "[LogicB-DEBUG] pair rejected: overlap",
                            outcome_he="לא זוג: חפיפה לא מספיקה או s מחוץ לטווח",
                            hash1=h1,
                            hash2=h2,
                            reason=reason,
                            overlap_mm=overlap_mm,
                            debug_numerics=debug_numerics,
                        )
                        sys.stderr.flush()
                    if (
                        reason in REJECTION_REASONS_WITH_NUMERICS
                        and rejection_stats[reason] <= MAX_NUMERICS_LOGS_PER_REASON
                        and debug_numerics
                    ):
                        self.log_info(
                            "[LogicB] Rejection numerics",
                            reason=reason,
                            **debug_numerics,
                        )
                    if VERBOSE_PAIR_LOGGING:
                        self.log_info(
                            "[LogicB] Pair rejected: overlap",
                            hash1=h1,
                            hash2=h2,
                            reason=reason,
                            overlap_mm=overlap_mm,
                        )
                    continue
                # Distance in overlap region (midpoint) so we don't reject due to line2 start only
                dist_at_mid = self._perpendicular_distance_at_overlap_midpoint(
                    line1, line2, overlap_start, overlap_end
                )
                if not (self.MIN_DISTANCE <= dist_at_mid <= self.MAX_DISTANCE):
                    rejection_stats["distance_out_of_range"] = (
                        rejection_stats.get("distance_out_of_range", 0) + 1
                    )
                    if is_debug_pair:
                        self.log_info(
                            "[LogicB-DEBUG] pair rejected: distance_out_of_range",
                            outcome_he="לא זוג: מרחק אנכי מחוץ לטווח",
                            hash1=h1,
                            hash2=h2,
                            dist_at_mid=dist_at_mid,
                            min_d=self.MIN_DISTANCE,
                            max_d=self.MAX_DISTANCE,
                        )
                        sys.stderr.flush()
                    if (
                        rejection_stats["distance_out_of_range"]
                        <= MAX_NUMERICS_LOGS_PER_REASON
                        and debug_numerics
                    ):
                        log_data = {**debug_numerics, "distance": dist_at_mid}
                        self.log_info(
                            "[LogicB] Rejection numerics",
                            reason="distance_out_of_range",
                            **log_data,
                        )
                    if VERBOSE_PAIR_LOGGING:
                        self.log_info(
                            "[LogicB] Pair rejected: distance_out_of_range",
                            hash1=h1,
                            hash2=h2,
                            distance=dist_at_mid,
                            min_d=self.MIN_DISTANCE,
                            max_d=self.MAX_DISTANCE,
                        )
                    continue
                key = (min(h1, h2), max(h1, h2))
                if key in seen:
                    rejection_stats["duplicate_pair"] = (
                        rejection_stats.get("duplicate_pair", 0) + 1
                    )
                    if is_debug_pair:
                        self.log_info(
                            "[LogicB-DEBUG] pair rejected: duplicate_pair",
                            outcome_he="לא זוג: זוג כפול",
                            hash1=h1,
                            hash2=h2,
                        )
                        sys.stderr.flush()
                    continue
                seen.add(key)
                if h2 < h1:
                    line1, line2 = line2, line1
                    trimmed1, trimmed2 = trimmed2, trimmed1
                pair = self._create_candidate_pair(
                    line1, line2, trimmed1, trimmed2, overlap_mm, perpendicular_distance=dist_at_mid
                )
                if pair:
                    pairs.append(pair)
                    if is_debug_pair:
                        self.log_info(
                            "[LogicB-DEBUG] pair ACCEPTED",
                            outcome_he="זוג אושר",
                            hash1=h1,
                            hash2=h2,
                            overlap_mm=overlap_mm,
                            dist_at_mid=dist_at_mid,
                            pair_id=pair.get("pair_id"),
                        )
                        sys.stderr.flush()

        # Deterministic order by bounding box centroid then area
        def sort_key(p: Dict[str, Any]) -> Tuple[float, float, float]:
            br = p.get("geometric_properties", {}).get("bounding_rectangle", {})
            cx = (br.get("minX", 0) + br.get("maxX", 0)) / 2
            cy = (br.get("minY", 0) + br.get("maxY", 0)) / 2
            area = (br.get("maxX", 0) - br.get("minX", 0)) * (
                br.get("maxY", 0) - br.get("minY", 0)
            )
            return (cx, cy, area)

        pairs.sort(key=sort_key)
        return pairs

    def _build_line_like_entities(
        self, parallel_ready_entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Build line-like list for pairing: all LINE entities plus each segment of
        POLYLINE as a virtual LINE (entity_hash = base_hash + "_seg_{i}").
        BLOCK entities are skipped. Ensures walls drawn as polylines are still paired.
        """
        out: List[Dict[str, Any]] = []
        for entity in parallel_ready_entities:
            etype = entity.get("entity_type")
            if etype == "LINE":
                out.append(entity)
            elif etype == "POLYLINE":
                nd = entity.get("normalized_data", {})
                vertices = nd.get("Vertices", [])
                base_hash = entity.get("entity_hash") or ""
                layer_name = entity.get("layer_name", "")
                for i in range(len(vertices) - 1):
                    seg = {
                        "entity_type": "LINE",
                        "entity_hash": f"{base_hash}_seg_{i}",
                        "layer_name": layer_name,
                        "normalized_data": {
                            "Start": vertices[i],
                            "End": vertices[i + 1],
                        },
                    }
                    out.append(seg)
        return out

    def _are_parallel(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> bool:
        """True if direction vectors are within ANGULAR_TOLERANCE (degrees). Returns False for zero-length lines."""
        line1_data = line1.get("normalized_data", {})
        line2_data = line2.get("normalized_data", {})

        s1 = line1_data.get("Start", {})
        e1 = line1_data.get("End", {})
        s2 = line2_data.get("Start", {})
        e2 = line2_data.get("End", {})

        dx1 = e1.get("X", 0) - s1.get("X", 0)
        dy1 = e1.get("Y", 0) - s1.get("Y", 0)
        dx2 = e2.get("X", 0) - s2.get("X", 0)
        dy2 = e2.get("Y", 0) - s2.get("Y", 0)

        len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
        if len1 == 0 or len2 == 0:
            if VERBOSE_PAIR_LOGGING and (len1 == 0 or len2 == 0):
                self.log_info(
                    "[LogicB] Zero-length line in _are_parallel",
                    hash1=line1.get("entity_hash", ""),
                    hash2=line2.get("entity_hash", ""),
                    len1=len1,
                    len2=len2,
                )
            return False

        dx1 /= len1
        dy1 /= len1
        dx2 /= len2
        dy2 /= len2
        dot = abs(dx1 * dx2 + dy1 * dy2)
        cos_tol = math.cos(math.radians(self.ANGULAR_TOLERANCE))
        return dot >= cos_tol

    def _check_distance_constraint(
        self, line1: Dict[str, Any], line2: Dict[str, Any]
    ) -> bool:
        """True if perpendicular distance between the two lines is in [MIN_DISTANCE, MAX_DISTANCE] (drawing units)."""
        d = self._perpendicular_distance(line1, line2)
        return self.MIN_DISTANCE <= d <= self.MAX_DISTANCE

    def _perpendicular_distance(
        self, line1: Dict[str, Any], line2: Dict[str, Any]
    ) -> float:
        """Perpendicular distance from line2's start to line1 (drawing units). Assumes lines are parallel."""
        line1_data = line1.get("normalized_data", {})
        line2_data = line2.get("normalized_data", {})

        s1 = line1_data.get("Start", {})
        e1 = line1_data.get("End", {})
        s2 = line2_data.get("Start", {})

        dx = e1.get("X", 0) - s1.get("X", 0)
        dy = e1.get("Y", 0) - s1.get("Y", 0)
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return float("inf")
        dx /= length
        dy /= length
        perp_x = -dy
        perp_y = dx
        to2_x = s2.get("X", 0) - s1.get("X", 0)
        to2_y = s2.get("Y", 0) - s1.get("Y", 0)
        return abs(to2_x * perp_x + to2_y * perp_y)

    def _perpendicular_distance_at_overlap_midpoint(
        self,
        line1: Dict[str, Any],
        line2: Dict[str, Any],
        overlap_start: float,
        overlap_end: float,
    ) -> float:
        """
        Perpendicular distance from the midpoint of the overlap (on line1) to line2.
        Used so distance is representative of the overlapping region, not just line2's start.
        """
        line1_data = line1.get("normalized_data", {})
        line2_data = line2.get("normalized_data", {})
        s1 = line1_data.get("Start", {})
        e1 = line1_data.get("End", {})
        s2 = line2_data.get("Start", {})
        e2 = line2_data.get("End", {})

        dx1 = e1.get("X", 0) - s1.get("X", 0)
        dy1 = e1.get("Y", 0) - s1.get("Y", 0)
        length1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        if length1 == 0:
            return float("inf")
        ux = dx1 / length1
        uy = dy1 / length1
        t_mid = 0.5 * (overlap_start + overlap_end)
        px = s1.get("X", 0) + ux * t_mid
        py = s1.get("Y", 0) + uy * t_mid

        # Distance from point (px,py) to line2
        ax = s2.get("X", 0)
        ay = s2.get("Y", 0)
        bx = e2.get("X", 0)
        by = e2.get("Y", 0)
        dx2 = bx - ax
        dy2 = by - ay
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
        if len2 == 0:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
        dx2 /= len2
        dy2 /= len2
        perp_x = -dy2
        perp_y = dx2
        to_p_x = px - ax
        to_p_y = py - ay
        return abs(to_p_x * perp_x + to_p_y * perp_y)

    def _trim_to_longitudinal_overlap(
        self,
        line1: Dict[str, Any],
        line2: Dict[str, Any],
        rejection_reason: Optional[List[str]] = None,
        debug_numerics: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[float], Optional[Dict], Optional[Dict], Optional[float], Optional[float]]:
        """
        Symmetric longitudinal overlap: project both lines onto line1's direction,
        take overlap = intersect([t1_min,t1_max], [t2_min,t2_max]). For line2 we clamp s to [0,1];
        overlap length is computed after clamping as (s_hi - s_lo) * length2. We reject only when
        that length is below MIN_OVERLAP_LENGTH (avoids false negatives from floating point at endpoints).

        Returns (overlap_length_mm, trimmed1, trimmed2, overlap_start, overlap_end) or (None, None, None, None, None).
        overlap_start/overlap_end are on line1's axis (for distance-at-midpoint).
        If debug_numerics dict is provided, it is filled with numeric decision values for focused rejection logging.
        """
        line1_data = line1.get("normalized_data", {})
        line2_data = line2.get("normalized_data", {})

        s1 = line1_data.get("Start", {})
        e1 = line1_data.get("End", {})
        s2 = line2_data.get("Start", {})
        e2 = line2_data.get("End", {})

        x1a, y1a = s1.get("X", 0), s1.get("Y", 0)
        x1b, y1b = e1.get("X", 0), e1.get("Y", 0)
        x2a, y2a = s2.get("X", 0), s2.get("Y", 0)
        x2b, y2b = e2.get("X", 0), e2.get("Y", 0)

        dx1 = x1b - x1a
        dy1 = y1b - y1a
        length1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        if length1 == 0:
            if rejection_reason is not None:
                rejection_reason.append("line1_zero_length")
            return (None, None, None, None, None)

        ux = dx1 / length1
        uy = dy1 / length1

        # Optional: fill debug numerics for focused rejection logging
        if debug_numerics is not None:
            dx2 = x2b - x2a
            dy2 = y2b - y2a
            length2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
            dot = abs(ux * (dx2 / length2) + uy * (dy2 / length2)) if length2 else 0.0
            angle_rad = math.acos(min(1.0, dot))
            angle_difference_deg = math.degrees(angle_rad)
            debug_numerics["angle_difference"] = angle_difference_deg
            debug_numerics["dot"] = dot
            debug_numerics["distance"] = self._perpendicular_distance(line1, line2)

        t1a = 0.0
        t1b = length1

        t2a = (x2a - x1a) * ux + (y2a - y1a) * uy
        t2b = (x2b - x1a) * ux + (y2b - y1a) * uy
        t2_min = min(t2a, t2b)
        t2_max = max(t2a, t2b)

        overlap_start = max(t1a, t2_min)
        overlap_end = min(t1b, t2_max)
        overlap_length_mm = max(0.0, overlap_end - overlap_start)

        if debug_numerics is not None:
            debug_numerics["t1_range"] = [t1a, t1b]
            debug_numerics["t2_range"] = [t2_min, t2_max]
            debug_numerics["overlap_range"] = [overlap_start, overlap_end]
            debug_numerics["overlap_length"] = overlap_length_mm

        if overlap_length_mm < MIN_OVERLAP_LENGTH:
            if rejection_reason is not None:
                rejection_reason.append("overlap_too_short")
            return (None, None, None, None, None)

        trim1_start = {
            "X": x1a + ux * overlap_start,
            "Y": y1a + uy * overlap_start,
            "Z": s1.get("Z", 0),
        }
        trim1_end = {
            "X": x1a + ux * overlap_end,
            "Y": y1a + uy * overlap_end,
            "Z": e1.get("Z", 0),
        }
        trimmed1 = {"start_point": trim1_start, "end_point": trim1_end}

        span2 = t2_max - t2_min
        if span2 == 0:
            if rejection_reason is not None:
                rejection_reason.append("span2_zero")
            return (None, None, None, None, None)
        length2 = math.sqrt((x2b - x2a) ** 2 + (y2b - y2a) ** 2)
        # Map overlap [overlap_start, overlap_end] to line2 parameter s; clamp to [0,1] (no reject on s)
        denom = t2b - t2a
        s_start_raw = (overlap_start - t2a) / denom if denom != 0 else 0.0
        s_end_raw = (overlap_end - t2a) / denom if denom != 0 else 0.0
        if debug_numerics is not None:
            debug_numerics["s_start"] = s_start_raw
            debug_numerics["s_end"] = s_end_raw
        s_lo = max(0.0, min(1.0, min(s_start_raw, s_end_raw)))
        s_hi = max(0.0, min(1.0, max(s_start_raw, s_end_raw)))
        x2_start = x2a + (x2b - x2a) * s_lo
        y2_start = y2a + (y2b - y2a) * s_lo
        x2_end = x2a + (x2b - x2a) * s_hi
        y2_end = y2a + (y2b - y2a) * s_hi
        trimmed2 = {
            "start_point": {"X": x2_start, "Y": y2_start, "Z": s2.get("Z", 0)},
            "end_point": {"X": x2_end, "Y": y2_end, "Z": e2.get("Z", 0)},
        }
        overlap_length_after_trim = (s_hi - s_lo) * length2
        if overlap_length_after_trim < MIN_OVERLAP_LENGTH:
            if rejection_reason is not None:
                rejection_reason.append("overlap_too_short")
            return (None, None, None, None, None)
        overlap_length_mm = overlap_length_after_trim
        return (overlap_length_mm, trimmed1, trimmed2, overlap_start, overlap_end)

    def _create_candidate_pair(
        self,
        line1: Dict[str, Any],
        line2: Dict[str, Any],
        trimmed1: Dict[str, Any],
        trimmed2: Dict[str, Any],
        overlap_length_mm: float,
        perpendicular_distance: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Build one wall-candidate pair payload. Geometry is the trimmed overlap only.
        bounding_rectangle is AABB of the four trimmed endpoints (for rendering/hit-testing).
        If perpendicular_distance is provided (e.g. at overlap midpoint), use it; else compute from line starts.
        """
        try:
            perp_dist = (
                perpendicular_distance
                if perpendicular_distance is not None
                else self._perpendicular_distance(line1, line2)
            )

            s1 = trimmed1["start_point"]
            e1 = trimmed1["end_point"]
            s2 = trimmed2["start_point"]
            e2 = trimmed2["end_point"]

            dx1 = e1["X"] - s1["X"]
            dy1 = e1["Y"] - s1["Y"]
            dx2 = e2["X"] - s2["X"]
            dy2 = e2["Y"] - s2["Y"]
            len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
            len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
            avg_length = (len1 + len2) / 2

            angle1 = math.atan2(dy1, dx1)
            angle2 = math.atan2(dy2, dx2)
            angle_diff = abs(angle1 - angle2)
            angle_diff = min(angle_diff, math.pi - angle_diff)
            angle_diff_degrees = math.degrees(angle_diff)

            all_x = [s1["X"], e1["X"], s2["X"], e2["X"]]
            all_y = [s1["Y"], e1["Y"], s2["Y"], e2["Y"]]
            bounding_rectangle = {
                "minX": min(all_x),
                "maxX": max(all_x),
                "minY": min(all_y),
                "maxY": max(all_y),
            }

            longer = max(len1, len2)
            overlap_percentage = (
                (overlap_length_mm / longer) * 100.0 if longer > 0 else 0.0
            )

            return {
                "pair_id": str(uuid.uuid4()),
                "line1": {
                    "entity_hash": line1.get("entity_hash", ""),
                    "start_point": s1,
                    "end_point": e1,
                    "layer_name": line1.get("layer_name", ""),
                },
                "line2": {
                    "entity_hash": line2.get("entity_hash", ""),
                    "start_point": s2,
                    "end_point": e2,
                    "layer_name": line2.get("layer_name", ""),
                },
                "geometric_properties": {
                    "perpendicular_distance": perp_dist,
                    "overlap_percentage": overlap_percentage,
                    "overlap_length_mm": overlap_length_mm,
                    "angle_difference": angle_diff_degrees,
                    "average_length": avg_length,
                    "bounding_rectangle": bounding_rectangle,
                },
            }
        except Exception as e:
            self.log_error(f"Error creating candidate pair: {e}")
            return None
