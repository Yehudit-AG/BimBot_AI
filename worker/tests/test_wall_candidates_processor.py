"""
Unit tests for WallCandidatesProcessor geometric calculations.
"""

import unittest
import math
from unittest.mock import Mock, patch
from worker.pipeline.processors.wall_candidates_processor import WallCandidatesProcessor


class TestWallCandidatesProcessor(unittest.TestCase):
    """Test cases for WallCandidatesProcessor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.processor = WallCandidatesProcessor()
        
        # Mock base processor methods
        self.processor.log_info = Mock()
        self.processor.log_error = Mock()
        self.processor.update_metrics = Mock()
    
    def create_line_entity(self, start_x, start_y, end_x, end_y, layer_name="TEST_LAYER", entity_hash="test_hash"):
        """Helper to create a line entity for testing."""
        return {
            'entity_type': 'LINE',
            'entity_hash': entity_hash,
            'layer_name': layer_name,
            'normalized_data': {
                'Start': {'X': start_x, 'Y': start_y, 'Z': 0.0},
                'End': {'X': end_x, 'Y': end_y, 'Z': 0.0}
            }
        }
    
    def test_are_parallel_horizontal_lines(self):
        """Test parallel detection for horizontal lines."""
        line1 = self.create_line_entity(0, 0, 100, 0)  # Horizontal
        line2 = self.create_line_entity(0, 50, 100, 50)  # Parallel horizontal
        
        self.assertTrue(self.processor._are_parallel(line1, line2))
    
    def test_are_parallel_vertical_lines(self):
        """Test parallel detection for vertical lines."""
        line1 = self.create_line_entity(0, 0, 0, 100)  # Vertical
        line2 = self.create_line_entity(50, 0, 50, 100)  # Parallel vertical
        
        self.assertTrue(self.processor._are_parallel(line1, line2))
    
    def test_are_parallel_diagonal_lines(self):
        """Test parallel detection for diagonal lines."""
        line1 = self.create_line_entity(0, 0, 100, 100)  # 45 degree diagonal
        line2 = self.create_line_entity(0, 50, 100, 150)  # Parallel diagonal
        
        self.assertTrue(self.processor._are_parallel(line1, line2))
    
    def test_are_not_parallel_perpendicular_lines(self):
        """Test that perpendicular lines are not detected as parallel."""
        line1 = self.create_line_entity(0, 0, 100, 0)  # Horizontal
        line2 = self.create_line_entity(0, 0, 0, 100)  # Vertical
        
        self.assertFalse(self.processor._are_parallel(line1, line2))
    
    def test_are_not_parallel_different_angles(self):
        """Test that lines with different angles are not parallel."""
        line1 = self.create_line_entity(0, 0, 100, 0)  # Horizontal
        line2 = self.create_line_entity(0, 0, 100, 50)  # 26.57 degree angle
        
        self.assertFalse(self.processor._are_parallel(line1, line2))
    
    def test_calculate_perpendicular_distance_horizontal(self):
        """Test perpendicular distance calculation for horizontal lines."""
        line1 = self.create_line_entity(0, 0, 100, 0)  # Y = 0
        line2 = self.create_line_entity(0, 50, 100, 50)  # Y = 50
        
        distance = self.processor._calculate_perpendicular_distance(line1, line2)
        self.assertAlmostEqual(distance, 50.0, places=2)
    
    def test_calculate_perpendicular_distance_vertical(self):
        """Test perpendicular distance calculation for vertical lines."""
        line1 = self.create_line_entity(0, 0, 0, 100)  # X = 0
        line2 = self.create_line_entity(30, 0, 30, 100)  # X = 30
        
        distance = self.processor._calculate_perpendicular_distance(line1, line2)
        self.assertAlmostEqual(distance, 30.0, places=2)
    
    def test_calculate_perpendicular_distance_diagonal(self):
        """Test perpendicular distance calculation for diagonal lines."""
        # Two parallel diagonal lines at 45 degrees
        line1 = self.create_line_entity(0, 0, 100, 100)
        line2 = self.create_line_entity(0, 50, 100, 150)
        
        distance = self.processor._calculate_perpendicular_distance(line1, line2)
        # Distance should be 50 / sqrt(2) ≈ 35.36
        expected_distance = 50 / math.sqrt(2)
        self.assertAlmostEqual(distance, expected_distance, places=1)
    
    def test_calculate_overlap_percentage_full_overlap(self):
        """Test overlap calculation for fully overlapping lines."""
        line1 = self.create_line_entity(0, 0, 100, 0)
        line2 = self.create_line_entity(0, 50, 100, 50)
        
        overlap = self.processor._calculate_overlap_percentage(line1, line2)
        self.assertAlmostEqual(overlap, 100.0, places=1)
    
    def test_calculate_overlap_percentage_partial_overlap(self):
        """Test overlap calculation for partially overlapping lines."""
        line1 = self.create_line_entity(0, 0, 100, 0)  # Length 100
        line2 = self.create_line_entity(50, 50, 150, 50)  # Length 100, overlap 50
        
        overlap = self.processor._calculate_overlap_percentage(line1, line2)
        self.assertAlmostEqual(overlap, 50.0, places=1)
    
    def test_calculate_overlap_percentage_no_overlap(self):
        """Test overlap calculation for non-overlapping lines."""
        line1 = self.create_line_entity(0, 0, 50, 0)
        line2 = self.create_line_entity(100, 50, 150, 50)
        
        overlap = self.processor._calculate_overlap_percentage(line1, line2)
        self.assertAlmostEqual(overlap, 0.0, places=1)
    
    def test_calculate_overlap_percentage_vertical_lines(self):
        """Test overlap calculation for vertical lines."""
        line1 = self.create_line_entity(0, 0, 0, 100)  # Y: 0-100, length 100
        line2 = self.create_line_entity(50, 25, 50, 75)  # Y: 25-75, length 50, overlap 50
        
        overlap = self.processor._calculate_overlap_percentage(line1, line2)
        # Longer line is 100, overlap is 50, so 50%
        self.assertAlmostEqual(overlap, 50.0, places=1)
    
    def test_check_distance_constraint_within_range(self):
        """Test distance constraint check for valid distances."""
        line1 = self.create_line_entity(0, 0, 100, 0)
        line2 = self.create_line_entity(0, 100, 100, 100)  # 100mm apart
        
        self.assertTrue(self.processor._check_distance_constraint(line1, line2))
    
    def test_check_distance_constraint_too_close(self):
        """Test distance constraint check for too close lines."""
        line1 = self.create_line_entity(0, 0, 100, 0)
        line2 = self.create_line_entity(0, 10, 100, 10)  # 10mm apart (< 20mm min)
        
        self.assertFalse(self.processor._check_distance_constraint(line1, line2))
    
    def test_check_distance_constraint_too_far(self):
        """Test distance constraint check for too far lines."""
        line1 = self.create_line_entity(0, 0, 100, 0)
        line2 = self.create_line_entity(0, 500, 100, 500)  # 500mm apart (> 450mm max)
        
        self.assertFalse(self.processor._check_distance_constraint(line1, line2))
    
    def test_check_overlap_requirement_sufficient(self):
        """Test overlap requirement check for sufficient overlap (≥90% of longer line)."""
        line1 = self.create_line_entity(0, 0, 100, 0)   # length 100
        line2 = self.create_line_entity(0, 50, 90, 50)  # length 90, overlap 90 → 90/100=90%
        
        self.assertTrue(self.processor._check_overlap_requirement(line1, line2))
    
    def test_check_overlap_requirement_insufficient(self):
        """Test overlap requirement check for insufficient overlap."""
        line1 = self.create_line_entity(0, 0, 100, 0)
        line2 = self.create_line_entity(60, 50, 100, 50)  # 40% overlap (< 90% min)
        
        self.assertFalse(self.processor._check_overlap_requirement(line1, line2))
    
    def test_create_candidate_pair_valid(self):
        """Test creation of valid wall candidate pair."""
        line1 = self.create_line_entity(0, 0, 100, 0, entity_hash="hash1")
        line2 = self.create_line_entity(0, 50, 100, 50, entity_hash="hash2")
        
        pair = self.processor._create_candidate_pair(line1, line2)
        
        self.assertIsNotNone(pair)
        self.assertIn('pair_id', pair)
        self.assertIn('line1', pair)
        self.assertIn('line2', pair)
        self.assertIn('geometric_properties', pair)
        
        # Check geometric properties
        props = pair['geometric_properties']
        self.assertAlmostEqual(props['perpendicular_distance'], 50.0, places=1)
        self.assertAlmostEqual(props['overlap_percentage'], 100.0, places=1)
        self.assertLess(props['angle_difference'], 5.0)  # Should be very small
        
        # Check bounding rectangle
        bounds = props['bounding_rectangle']
        self.assertEqual(bounds['minX'], 0)
        self.assertEqual(bounds['maxX'], 100)
        self.assertEqual(bounds['minY'], 0)
        self.assertEqual(bounds['maxY'], 50)
    
    def test_detect_wall_candidate_pairs_valid_pair(self):
        """Test detection of valid wall candidate pairs."""
        line_entities = [
            self.create_line_entity(0, 0, 100, 0, entity_hash="hash1"),
            self.create_line_entity(0, 50, 100, 50, entity_hash="hash2"),
            self.create_line_entity(200, 0, 200, 100, entity_hash="hash3")  # Different orientation
        ]
        
        pairs = self.processor._detect_wall_candidate_pairs(line_entities)
        
        self.assertEqual(len(pairs), 1)  # Only one valid pair
        self.assertEqual(pairs[0]['line1']['entity_hash'], "hash1")
        self.assertEqual(pairs[0]['line2']['entity_hash'], "hash2")
    
    def test_detect_wall_candidate_pairs_no_valid_pairs(self):
        """Test detection when no valid pairs exist."""
        line_entities = [
            self.create_line_entity(0, 0, 100, 0, entity_hash="hash1"),
            self.create_line_entity(0, 500, 100, 500, entity_hash="hash2"),  # Too far
            self.create_line_entity(0, 0, 0, 100, entity_hash="hash3")  # Perpendicular
        ]
        
        pairs = self.processor._detect_wall_candidate_pairs(line_entities)
        
        self.assertEqual(len(pairs), 0)
    
    def test_angular_tolerance_configuration(self):
        """Test that angular tolerance configuration works."""
        # Create lines with small angle difference
        line1 = self.create_line_entity(0, 0, 100, 0)  # Horizontal
        line2 = self.create_line_entity(0, 50, 100, 3)  # Slightly angled (~1.7 degrees)
        
        # Should be parallel with default 5-degree tolerance
        self.assertTrue(self.processor._are_parallel(line1, line2))
        
        # Change tolerance to 1 degree
        original_tolerance = self.processor.ANGULAR_TOLERANCE
        self.processor.ANGULAR_TOLERANCE = 1.0
        
        # Should not be parallel with 1-degree tolerance
        self.assertFalse(self.processor._are_parallel(line1, line2))
        
        # Restore original tolerance
        self.processor.ANGULAR_TOLERANCE = original_tolerance


if __name__ == '__main__':
    unittest.main()