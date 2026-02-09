"""
Unit tests for LOGIC F processor: L-junction extension (H↔V only, center-line
intersection X, extend at most once, MAX_EXTENSION_MM / MAX_JUNCTION_DISTANCE_MM).

Run from project root with worker on PYTHONPATH, or from worker/ with:
  python -m tests.test_logic_f_l_junctions_processor
"""

import math
import unittest
from unittest.mock import Mock

from worker.pipeline.processors.logic_f_l_junctions_processor import (
    LogicFProcessor,
    _process_l_junctions,
    _wall_representation,
)
from worker.pipeline.processors.wall_candidate_constants import (
    LOGIC_F_ANGLE_TOL_DEG,
    LOGIC_F_ANGLE_DOT_TOL,
    LOGIC_F_MAX_EXTENSION_MM,
    LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
)


def _rect(ax1: float, ay1: float, ax2: float, ay2: float,
          bx1: float, by1: float, bx2: float, by2: float) -> dict:
    """One band rectangle: trimmedSegmentA p1=(ax1,ay1) p2=(ax2,ay2), trimmedSegmentB p1=(bx1,by1) p2=(bx2,by2)."""
    xs = [ax1, ax2, bx1, bx2]
    ys = [ay1, ay2, by1, by2]
    return {
        "trimmedSegmentA": {"p1": {"X": ax1, "Y": ay1}, "p2": {"X": ax2, "Y": ay2}},
        "trimmedSegmentB": {"p1": {"X": bx1, "Y": by1}, "p2": {"X": bx2, "Y": by2}},
        "bounding_rectangle": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)},
    }


def _center_line(rect: dict):
    """Return (c1, c2) center line endpoints for a rectangle."""
    w = _wall_representation(rect)
    if w is None:
        return None
    return (w["c1"], w["c2"])


class TestLogicFLJunctionsProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = LogicFProcessor(job_id=Mock(), db=Mock())
        self.processor.log_info = Mock()
        self.processor.log_error = Mock()
        self.processor.update_metrics = Mock()

    # 5.1 Constants exist
    def test_constants_exist(self):
        """LOGIC_F_* constants are defined."""
        self.assertIsNotNone(LOGIC_F_ANGLE_TOL_DEG)
        self.assertIsNotNone(LOGIC_F_ANGLE_DOT_TOL)
        self.assertIsNotNone(LOGIC_F_MAX_EXTENSION_MM)
        self.assertIsNotNone(LOGIC_F_MAX_JUNCTION_DISTANCE_MM)
        self.assertEqual(LOGIC_F_ANGLE_TOL_DEG, 25.0)
        self.assertLessEqual(LOGIC_F_ANGLE_DOT_TOL, 1.0)
        self.assertGreater(LOGIC_F_ANGLE_DOT_TOL, 0)
        self.assertGreater(LOGIC_F_MAX_EXTENSION_MM, 0)
        self.assertGreater(LOGIC_F_MAX_JUNCTION_DISTANCE_MM, 0)

    def test_l_junction_two_walls_output_length_unchanged(self):
        """Two walls forming L: output length equals input length."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        inp = [r1, r2]
        out, _, _ = _process_l_junctions(
            inp,
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        self.assertEqual(len(out), len(inp), "output length must equal input length")

    def test_l_junction_at_least_two_extended(self):
        """Two walls forming L: both participants get extended True."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        out, _, num_accepted = _process_l_junctions(
            [r1, r2],
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        extended = [r for r in out if r.get("extended") is True]
        self.assertGreaterEqual(len(extended), 2, "both L-junction participants should be extended")
        self.assertEqual(num_accepted, 1)

    def test_l_junction_metadata_strict(self):
        """Extended rects have extended True, junction_type L, junction_point; non-extended have extended False, no junction_point."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        out, _, _ = _process_l_junctions(
            [r1, r2],
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        for r in out:
            if r.get("extended") is True:
                self.assertEqual(r.get("junction_type"), "L")
                self.assertIn("junction_point", r)
                jp = r["junction_point"]
                self.assertIsInstance(jp, list)
                self.assertEqual(len(jp), 2)
            else:
                self.assertFalse(r.get("extended", False))
                self.assertNotIn("junction_point", r)

    def test_l_junction_modified_walls_remain_parallel(self):
        """Modified walls: segment A and B remain parallel."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        out, _, _ = _process_l_junctions(
            [r1, r2],
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        for rect in out:
            a = rect.get("trimmedSegmentA") or {}
            b = rect.get("trimmedSegmentB") or {}
            p1 = a.get("p1") or {}
            p2 = a.get("p2") or {}
            q1 = b.get("p1") or {}
            q2 = b.get("p2") or {}
            dx_a = (p2.get("X", 0) - p1.get("X", 0), p2.get("Y", 0) - p1.get("Y", 0))
            dx_b = (q2.get("X", 0) - q1.get("X", 0), q2.get("Y", 0) - q1.get("Y", 0))
            dot = dx_a[0] * dx_b[0] + dx_a[1] * dx_b[1]
            len_a = (dx_a[0] ** 2 + dx_a[1] ** 2) ** 0.5
            len_b = (dx_b[0] ** 2 + dx_b[1] ** 2) ** 0.5
            if len_a > 1e-6 and len_b > 1e-6:
                cos = dot / (len_a * len_b)
                self.assertGreaterEqual(abs(cos), 0.99, msg="A and B should remain nearly parallel after extension")

    # 5.2 At-most-once
    def test_at_most_once_per_rectangle(self):
        """One vertical with two horizontals: each rectangle has extended True at most once; accepted pairs = extended/2."""
        # Horizontal band 1: y in [0, 50], x in [0, 400]
        r1 = _rect(0, 0, 400, 0, 0, 50, 400, 50)
        # Vertical: x in [0, 50], y in [0, 500] – can form L with both r1 and r2
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        # Horizontal band 2: y in [100, 150], x in [0, 400]
        r3 = _rect(0, 100, 400, 100, 0, 150, 400, 150)
        inp = [r1, r2, r3]
        out, _num_candidates, num_accepted_pairs = _process_l_junctions(
            inp,
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        extended_count = sum(1 for r in out if r.get("extended") is True)
        self.assertLessEqual(extended_count, 3, "at most 3 rects extended")
        self.assertEqual(extended_count, num_accepted_pairs * 2, "each accepted pair extends exactly 2 rects")
        for r in out:
            self.assertIn(r.get("extended"), (True, False))
            if r.get("extended") is True:
                self.assertIsInstance(r.get("junction_point"), list)

    # 5.3 Feasibility rejection
    def test_feasibility_rejection_extension_too_long(self):
        """Junction requiring extension > LOGIC_F_MAX_EXTENSION_MM: no rectangle extended."""
        max_ext = 50.0  # very small
        # Horizontal far to the right; vertical on the left. Intersection far from horizontal end.
        r1 = _rect(500, 0, 2000, 0, 500, 50, 2000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        out, _, num_accepted = _process_l_junctions(
            [r1, r2],
            max_extension_mm=max_ext,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        extended = [r for r in out if r.get("extended") is True]
        self.assertEqual(len(extended), 0, "extension exceeds max: no extension")
        self.assertEqual(num_accepted, 0)

    def test_feasibility_rejection_junction_too_far(self):
        """Junction with dist_to_rect > LOGIC_F_MAX_JUNCTION_DISTANCE_MM: no extension."""
        max_dist = 10.0  # very small – junction point must be very close to rects
        # Two bands that would meet at intersection far from both
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(2000, 0, 2000, 500, 2050, 0, 2050, 500)
        out, _, num_accepted = _process_l_junctions(
            [r1, r2],
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=max_dist,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        extended = [r for r in out if r.get("extended") is True]
        self.assertEqual(len(extended), 0, "junction too far: no extension")
        self.assertEqual(num_accepted, 0)

    # 5.4 Junction correctness
    def test_junction_correctness_center_lines_meet_at_junction_point(self):
        """For each extended rectangle, center line intersects partner at junction_point within epsilon."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        out, _, _ = _process_l_junctions(
            [r1, r2],
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        eps = 0.5  # mm
        extended_with_jp = [(i, r) for i, r in enumerate(out) if r.get("extended") and r.get("junction_point")]
        self.assertGreaterEqual(len(extended_with_jp), 2)
        jp = extended_with_jp[0][1]["junction_point"]
        X = (jp[0], jp[1])
        cl1 = _center_line(out[0])
        cl2 = _center_line(out[1])
        self.assertIsNotNone(cl1)
        self.assertIsNotNone(cl2)
        # Distance from X to infinite line through c1-c2
        def dist_pt_line(pt, a, b):
            ax, ay = a[0], a[1]
            bx, by = b[0], b[1]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 <= 0:
                return math.hypot(pt[0] - ax, pt[1] - ay)
            t = ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / L2
            qx, qy = ax + t * dx, ay + t * dy
            return math.hypot(pt[0] - qx, pt[1] - qy)
        d1 = dist_pt_line(X, cl1[0], cl1[1])
        d2 = dist_pt_line(X, cl2[0], cl2[1])
        self.assertLess(d1, eps, "junction_point on first center line")
        self.assertLess(d2, eps, "junction_point on second center line")

    # 5.5 Unchanged non-participants
    def test_unchanged_non_participants_bit_identical(self):
        """Rectangles not in any accepted junction remain bit-identical (same trimmedSegmentA/B)."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        r3 = _rect(500, 200, 1000, 200, 500, 250, 1000, 250)  # horizontal, no L with r1/r2 at same junction
        inp = [r1, r2, r3]
        out, _, _ = _process_l_junctions(
            inp,
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        # r3 is not part of the single L (r1,r2); should be unchanged
        a_in = inp[2].get("trimmedSegmentA") or {}
        b_in = inp[2].get("trimmedSegmentB") or {}
        a_out = out[2].get("trimmedSegmentA") or {}
        b_out = out[2].get("trimmedSegmentB") or {}
        self.assertAlmostEqual(a_out.get("p1", {}).get("X"), a_in.get("p1", {}).get("X"), places=6)
        self.assertAlmostEqual(a_out.get("p1", {}).get("Y"), a_in.get("p1", {}).get("Y"), places=6)
        self.assertAlmostEqual(a_out.get("p2", {}).get("X"), a_in.get("p2", {}).get("X"), places=6)
        self.assertAlmostEqual(a_out.get("p2", {}).get("Y"), a_in.get("p2", {}).get("Y"), places=6)
        self.assertAlmostEqual(b_out.get("p1", {}).get("X"), b_in.get("p1", {}).get("X"), places=6)
        self.assertAlmostEqual(b_out.get("p1", {}).get("Y"), b_in.get("p1", {}).get("Y"), places=6)
        self.assertAlmostEqual(b_out.get("p2", {}).get("X"), b_in.get("p2", {}).get("X"), places=6)
        self.assertAlmostEqual(b_out.get("p2", {}).get("Y"), b_in.get("p2", {}).get("Y"), places=6)
        self.assertFalse(out[2].get("extended", False))

    def test_no_l_junction_output_unchanged_all_not_extended(self):
        """No L-junction (parallel or far): all extended False, geometry unchanged."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 200, 1000, 200, 0, 250, 1000, 250)
        inp = [r1, r2]
        out, _, _ = _process_l_junctions(
            inp,
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        self.assertEqual(len(out), len(inp))
        for r in out:
            self.assertFalse(r.get("extended", False))
        for i, rect in enumerate(out):
            a_in = inp[i].get("trimmedSegmentA") or {}
            a_out = rect.get("trimmedSegmentA") or {}
            self.assertAlmostEqual(a_out.get("p1", {}).get("X"), a_in.get("p1", {}).get("X"), places=6)
            self.assertAlmostEqual(a_out.get("p1", {}).get("Y"), a_in.get("p1", {}).get("Y"), places=6)
            self.assertAlmostEqual(a_out.get("p2", {}).get("X"), a_in.get("p2", {}).get("X"), places=6)
            self.assertAlmostEqual(a_out.get("p2", {}).get("Y"), a_in.get("p2", {}).get("Y"), places=6)

    def test_process_empty_input(self):
        """process() with no logic_e_rectangles returns empty logic_f_rectangles."""
        out = self.processor.process({"logic_e_results": {}})
        self.assertEqual(out.get("logic_f_rectangles"), [])
        self.assertIn("totals", out)
        self.assertEqual(out["totals"]["num_input"], 0)
        self.processor.update_metrics.assert_called()

    def test_process_returns_config_and_totals(self):
        """process() returns logic_f_rectangles, algorithm_config (LOGIC_F_*), totals."""
        r1 = _rect(0, 0, 1000, 0, 0, 50, 1000, 50)
        r2 = _rect(0, 0, 0, 500, 50, 0, 50, 500)
        pipeline_data = {"logic_e_results": {"logic_e_rectangles": [r1, r2]}}
        out = self.processor.process(pipeline_data)
        self.assertIn("logic_f_rectangles", out)
        self.assertEqual(len(out["logic_f_rectangles"]), 2)
        self.assertIn("algorithm_config", out)
        self.assertEqual(out["algorithm_config"].get("logic_f_angle_tol_deg"), LOGIC_F_ANGLE_TOL_DEG)
        self.assertEqual(out["algorithm_config"].get("logic_f_max_extension_mm"), LOGIC_F_MAX_EXTENSION_MM)
        self.assertIn("totals", out)
        self.assertIn("num_input", out["totals"])
        self.assertIn("num_candidates", out["totals"])
        self.assertIn("num_accepted_pairs", out["totals"])
        self.assertIn("num_extended_rectangles", out["totals"])


if __name__ == "__main__":
    unittest.main()
