"""
Unit tests for WallCandidatesProcessorB (Logic B: trimmed segments, overlap in mm).
"""

import unittest
import math
import uuid
from unittest.mock import Mock
from worker.pipeline.processors.wall_candidates_processor_b import WallCandidatesProcessorB
from worker.pipeline.processors.wall_candidate_constants import MIN_OVERLAP_LENGTH


def make_line(sx, sy, ex, ey, layer="LAYER", entity_hash=None):
    h = entity_hash or f"{sx}_{sy}_{ex}_{ey}"
    return {
        "entity_type": "LINE",
        "entity_hash": h,
        "layer_name": layer,
        "normalized_data": {
            "Start": {"X": sx, "Y": sy, "Z": 0.0},
            "End": {"X": ex, "Y": ey, "Z": 0.0},
        },
    }


class TestWallCandidatesProcessorB(unittest.TestCase):
    def setUp(self):
        self.job_id = uuid.uuid4()
        self.db = Mock()
        self.processor = WallCandidatesProcessorB(self.job_id, self.db)
        self.processor.log_info = Mock()
        self.processor.log_error = Mock()
        self.processor.update_metrics = Mock()

    def test_are_parallel_horizontal(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(0, 50, 100, 50)
        self.assertTrue(self.processor._are_parallel(line1, line2))

    def test_are_parallel_vertical(self):
        line1 = make_line(0, 0, 0, 100)
        line2 = make_line(30, 0, 30, 100)
        self.assertTrue(self.processor._are_parallel(line1, line2))

    def test_are_not_parallel_perpendicular(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(0, 0, 0, 100)
        self.assertFalse(self.processor._are_parallel(line1, line2))

    def test_perpendicular_distance_horizontal(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(0, 50, 100, 50)
        d = self.processor._perpendicular_distance(line1, line2)
        self.assertAlmostEqual(d, 50.0, places=5)

    def test_check_distance_constraint_in_range(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(0, 100, 100, 100)  # 100 mm apart
        self.assertTrue(self.processor._check_distance_constraint(line1, line2))

    def test_trim_to_longitudinal_overlap_full_overlap(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(0, 30, 100, 30)
        overlap_mm, t1, t2, _, _ = self.processor._trim_to_longitudinal_overlap(line1, line2)
        self.assertIsNotNone(overlap_mm)
        self.assertGreaterEqual(overlap_mm, MIN_OVERLAP_LENGTH)
        self.assertAlmostEqual(overlap_mm, 100.0, places=2)
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertIn("start_point", t1)
        self.assertIn("end_point", t1)

    def test_trim_to_longitudinal_overlap_partial(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(50, 30, 150, 30)  # overlap on [50,100] = 50 mm
        overlap_mm, t1, t2, _, _ = self.processor._trim_to_longitudinal_overlap(line1, line2)
        self.assertIsNotNone(overlap_mm)
        self.assertGreaterEqual(overlap_mm, MIN_OVERLAP_LENGTH)
        self.assertAlmostEqual(overlap_mm, 50.0, places=2)

    def test_trim_to_longitudinal_overlap_no_overlap(self):
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(200, 30, 300, 30)
        overlap_mm, t1, t2, _, _ = self.processor._trim_to_longitudinal_overlap(line1, line2)
        self.assertIsNone(overlap_mm)
        self.assertIsNone(t1)
        self.assertIsNone(t2)

    def test_trim_to_longitudinal_overlap_endpoint_aligned(self):
        """Overlap touches line2 endpoints; post-clamp overlap length is used (no reject on s_hi<=s_lo)."""
        line1 = make_line(0, 0, 100, 0)
        line2 = make_line(80, 30, 100, 30)  # line2 length 20; overlap [80,100] = 20
        overlap_mm, t1, t2, _, _ = self.processor._trim_to_longitudinal_overlap(line1, line2)
        self.assertIsNotNone(overlap_mm)
        self.assertGreaterEqual(overlap_mm, MIN_OVERLAP_LENGTH)
        self.assertAlmostEqual(overlap_mm, 20.0, places=2)
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)

    def test_process_returns_structure(self):
        line1 = make_line(0, 0, 500, 0, entity_hash="a")
        line2 = make_line(0, 100, 500, 100, entity_hash="b")
        pipeline_data = {
            "parallel_naive_results": {
                "entities": {
                    "parallel_ready_entities": [line1, line2],
                }
            }
        }
        result = self.processor.process(pipeline_data)
        self.assertIn("wall_candidate_pairs", result)
        self.assertIn("detection_stats", result)
        self.assertIn("unpaired_entity_hashes", result)
        self.assertIn("rejection_stats", result)
        self.assertIn("algorithm_config", result)
        self.assertIn("totals", result)
        self.assertIn("min_overlap_length", result["algorithm_config"])
        pairs = result["wall_candidate_pairs"]
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        self.assertIn("line1", pair)
        self.assertIn("line2", pair)
        self.assertIn("geometric_properties", pair)
        gp = pair["geometric_properties"]
        self.assertIn("bounding_rectangle", gp)
        self.assertIn("overlap_length_mm", gp)
        self.assertGreaterEqual(gp["overlap_length_mm"], MIN_OVERLAP_LENGTH)
        self.assertIn("overlap_percentage", gp)

    def test_process_no_lines(self):
        pipeline_data = {
            "parallel_naive_results": {
                "entities": {"parallel_ready_entities": []},
            }
        }
        result = self.processor.process(pipeline_data)
        self.assertEqual(result["wall_candidate_pairs"], [])
        self.assertEqual(result["detection_stats"]["candidate_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
