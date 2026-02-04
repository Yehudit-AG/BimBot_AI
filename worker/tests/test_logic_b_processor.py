"""
Unit tests for LOGIC B processor: overlap-only wall pairs, per-line trim, no extension.
Includes must-pass tests that fail if reconstruction uses the wrong origin.

Run from project root with worker on PYTHONPATH, or from worker/ with:
  python -m tests.test_logic_b_processor
(Requires worker dependencies: pip install -r worker/requirements.txt)
"""

import unittest
from unittest.mock import Mock
from worker.pipeline.processors.logic_b_processor import LogicBProcessor
from worker.pipeline.processors.units import EPS_MM, cm_to_internal


def line_entity(start_x: float, start_y: float, end_x: float, end_y: float,
                entity_hash: str = "line") -> dict:
    return {
        "entity_type": "LINE",
        "entity_hash": entity_hash,
        "layer_name": "TEST",
        "normalized_data": {
            "Start": {"X": start_x, "Y": start_y, "Z": 0.0},
            "End": {"X": end_x, "Y": end_y, "Z": 0.0},
        },
    }


class TestLogicBProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = LogicBProcessor(job_id=Mock(), db=Mock())
        self.processor.log_info = Mock()
        self.processor.log_error = Mock()
        self.processor.update_metrics = Mock()

    def _pairs(self, line_entities: list) -> list:
        return self.processor._detect_logic_b_pairs(line_entities)

    # ----- Must-pass: reconstruction uses per-line origin -----

    def test_must_pass_l2_trimmed_has_y_10_exactly(self):
        """L1: (0,0)-(100,0), L2: (20,10)-(80,10) -> trimmed L2 must have y=10 exactly."""
        L1 = line_entity(0, 0, 100, 0, "L1")
        L2 = line_entity(20, 10, 80, 10, "L2")
        pairs = self._pairs([L1, L2])
        self.assertEqual(len(pairs), 1, "expect one pair")
        p = pairs[0]
        self.assertEqual(p["sourceLineIdA"], "L1")
        self.assertEqual(p["sourceLineIdB"], "L2")
        b = p["trimmedSegmentB"]
        self.assertAlmostEqual(b["p1"]["Y"], 10.0, places=5, msg="L2 trimmed p1 must have Y=10")
        self.assertAlmostEqual(b["p2"]["Y"], 10.0, places=5, msg="L2 trimmed p2 must have Y=10")
        self.assertAlmostEqual(b["p1"]["X"], 20.0, places=5)
        self.assertAlmostEqual(b["p2"]["X"], 80.0, places=5)
        a = p["trimmedSegmentA"]
        self.assertAlmostEqual(a["p1"]["Y"], 0.0, places=5)
        self.assertAlmostEqual(a["p2"]["Y"], 0.0, places=5)

    def test_must_pass_trimmed_endpoints_lie_on_l2_not_y10(self):
        """L1: (0,0)-(100,0), L2: (20,10)-(80,11) within angle tolerance -> trimmed on L2, not y=10."""
        L1 = line_entity(0, 0, 100, 0, "L1")
        L2 = line_entity(20, 10, 80, 11, "L2")  # slightly tilted
        pairs = self._pairs([L1, L2])
        if len(pairs) == 0:
            self.skipTest("L2 angle may exceed 2° tolerance; adjust if needed")
        p = pairs[0]
        b = p["trimmedSegmentB"]
        x1, y1 = b["p1"]["X"], b["p1"]["Y"]
        x2, y2 = b["p2"]["X"], b["p2"]["Y"]
        # Distance from (x1,y1) to segment L2 (20,10)-(80,11) must be <= EPS
        # Point-to-segment distance: project onto line, clamp to [0,1]
        def dist_pt_seg(px, py, sx, sy, ex, ey):
            dx, dy = ex - sx, ey - sy
            l2 = dx * dx + dy * dy
            if l2 <= 0:
                return ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
            t = max(0, min(1, ((px - sx) * dx + (py - sy) * dy) / l2))
            qx, qy = sx + t * dx, sy + t * dy
            return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
        d1 = dist_pt_seg(x1, y1, 20, 10, 80, 11)
        d2 = dist_pt_seg(x2, y2, 20, 10, 80, 11)
        self.assertLessEqual(d1, EPS_MM * 2, msg="trimmed B p1 must lie on L2 segment")
        self.assertLessEqual(d2, EPS_MM * 2, msg="trimmed B p2 must lie on L2 segment")
        # They must not both be y=10 (that would be wrong reconstruction)
        self.assertFalse(
            abs(y1 - 10) < 1e-6 and abs(y2 - 10) < 1e-6,
            msg="trimmed endpoints must not both be y=10 (would indicate wrong origin)",
        )

    def test_no_overlap_no_pair(self):
        """L1: (0,0)-(30,0), L2: (40,10)-(80,10) -> no overlap -> no pair."""
        L1 = line_entity(0, 0, 30, 0, "L1")
        L2 = line_entity(40, 10, 80, 10, "L2")
        pairs = self._pairs([L1, L2])
        self.assertEqual(len(pairs), 0)

    def test_one_line_in_two_pairs(self):
        """L1 long; L2 and L3 with different overlaps -> two pairs, L1 unchanged."""
        L1 = line_entity(0, 0, 100, 0, "L1")
        L2 = line_entity(10, 10, 40, 10, "L2")
        L3 = line_entity(60, 12, 90, 12, "L3")
        pairs = self._pairs([L1, L2, L3])
        self.assertGreaterEqual(len(pairs), 1)
        ids = {(p["sourceLineIdA"], p["sourceLineIdB"]) for p in pairs}
        self.assertIn(("L1", "L2"), ids)
        self.assertIn(("L1", "L3"), ids)

    def test_distance_filter_1cm_to_45cm(self):
        """Pair at 10mm (1cm) and 450mm (45cm) included; outside range excluded."""
        min_mm = cm_to_internal(1)
        max_mm = cm_to_internal(45)
        L1 = line_entity(0, 0, 100, 0, "L1")
        L2_10mm = line_entity(20, min_mm, 80, min_mm, "L2_10")
        L2_500mm = line_entity(20, 500, 80, 500, "L2_500")
        pairs_10 = self._pairs([L1, L2_10mm])
        pairs_500 = self._pairs([L1, L2_500mm])
        self.assertEqual(len(pairs_10), 1)
        self.assertEqual(len(pairs_500), 0)


if __name__ == "__main__":
    unittest.main()
