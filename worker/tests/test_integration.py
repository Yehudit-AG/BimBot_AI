"""
Integration tests for wall candidates detection pipeline.
"""

import unittest
from unittest.mock import Mock, patch
from worker.pipeline.processors.wall_candidates_processor import WallCandidatesProcessor


class TestWallCandidatesIntegration(unittest.TestCase):
    """Integration tests for the complete wall candidates detection flow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.processor = WallCandidatesProcessor()
        
        # Mock base processor methods
        self.processor.log_info = Mock()
        self.processor.log_error = Mock()
        self.processor.update_metrics = Mock()
    
    def create_pipeline_data(self, line_entities):
        """Create mock pipeline data structure."""
        return {
            'parallel_naive_results': {
                'entities': {
                    'parallel_ready_entities': line_entities
                }
            }
        }
    
    def create_line_entity(self, start_x, start_y, end_x, end_y, layer_name="WALLS", entity_hash=None):
        """Helper to create a line entity for testing."""
        if entity_hash is None:
            entity_hash = f"hash_{start_x}_{start_y}_{end_x}_{end_y}"
        
        return {
            'entity_type': 'LINE',
            'entity_hash': entity_hash,
            'layer_name': layer_name,
            'normalized_data': {
                'Start': {'X': start_x, 'Y': start_y, 'Z': 0.0},
                'End': {'X': end_x, 'Y': end_y, 'Z': 0.0}
            }
        }
    
    def test_pair_based_detection_complete_flow(self):
        """Test complete pair-based detection flow."""
        # Create test data with valid wall candidate pairs
        line_entities = [
            self.create_line_entity(0, 0, 1000, 0, entity_hash="wall1_line1"),      # Horizontal wall line 1
            self.create_line_entity(0, 200, 1000, 200, entity_hash="wall1_line2"),  # Horizontal wall line 2 (200mm apart)
            self.create_line_entity(500, -100, 500, 300, entity_hash="wall2_line1"), # Vertical wall line 1
            self.create_line_entity(650, -100, 650, 300, entity_hash="wall2_line2"), # Vertical wall line 2 (150mm apart)
            self.create_line_entity(2000, 0, 2100, 0, entity_hash="short_line"),    # Too short to be relevant
            self.create_line_entity(0, 1000, 1000, 1000, entity_hash="isolated"),   # Too far from others
        ]
        
        pipeline_data = self.create_pipeline_data(line_entities)
        
        # Set processor to pair-based mode
        self.processor.DETECTION_MODE = "pair_based"
        
        # Process the data
        result = self.processor.process(pipeline_data)
        
        # Verify result structure
        self.assertIn('wall_candidate_pairs', result)
        self.assertIn('detection_stats', result)
        self.assertIn('algorithm_config', result)
        self.assertIn('totals', result)
        
        # Verify we found the expected pairs
        pairs = result['wall_candidate_pairs']
        self.assertEqual(len(pairs), 2)  # Should find 2 valid pairs
        
        # Verify detection stats
        stats = result['detection_stats']
        self.assertEqual(stats['entities_analyzed'], 6)
        self.assertEqual(stats['candidate_pairs'], 2)
        
        # Verify algorithm configuration is included
        config = result['algorithm_config']
        self.assertEqual(config['angular_tolerance'], self.processor.ANGULAR_TOLERANCE)
        self.assertEqual(config['min_distance'], self.processor.MIN_DISTANCE)
        self.assertEqual(config['max_distance'], self.processor.MAX_DISTANCE)
        self.assertEqual(config['min_overlap_percentage'], self.processor.MIN_OVERLAP_PERCENTAGE)
        
        # Verify totals
        totals = result['totals']
        self.assertEqual(totals['candidate_pairs'], 2)
        self.assertGreater(totals['total_length'], 0)
    
    def test_mock_detection_complete_flow(self):
        """Test complete mock detection flow."""
        # Create test data
        line_entities = [
            self.create_line_entity(0, 0, 1000, 0),      # Horizontal line (valid)
            self.create_line_entity(0, 0, 0, 1000),      # Vertical line (valid)
            self.create_line_entity(0, 0, 100, 100),     # Diagonal line (invalid in mock mode)
            self.create_line_entity(0, 0, 200, 0),       # Short line (invalid)
        ]
        
        pipeline_data = self.create_pipeline_data(line_entities)
        
        # Set processor to mock mode
        self.processor.DETECTION_MODE = "mock"
        
        # Process the data
        result = self.processor.process(pipeline_data)
        
        # Verify result structure
        self.assertIn('wall_candidates', result)
        self.assertIn('wall_segments', result)
        self.assertIn('detection_stats', result)
        self.assertIn('wall_analysis', result)
        self.assertIn('totals', result)
        
        # Verify we found some candidates (horizontal and vertical lines >= 500mm)
        candidates = result['wall_candidates']
        self.assertEqual(len(candidates), 2)  # Should find 2 valid candidates
        
        # Verify detection stats
        stats = result['detection_stats']
        self.assertEqual(stats['entities_analyzed'], 4)
        self.assertEqual(stats['potential_walls'], 2)
    
    def test_empty_input_handling(self):
        """Test handling of empty input data."""
        pipeline_data = self.create_pipeline_data([])
        
        result = self.processor.process(pipeline_data)
        
        # Should handle empty input gracefully
        if self.processor.DETECTION_MODE == "pair_based":
            self.assertEqual(len(result['wall_candidate_pairs']), 0)
        else:
            self.assertEqual(len(result['wall_candidates']), 0)
    
    def test_no_valid_pairs_scenario(self):
        """Test scenario where no valid pairs exist."""
        # Create lines that don't meet the criteria
        line_entities = [
            self.create_line_entity(0, 0, 1000, 0),      # Line 1
            self.create_line_entity(0, 1000, 1000, 1000), # Too far (1000mm > 450mm max)
            self.create_line_entity(0, 0, 0, 1000),      # Perpendicular to line 1
            self.create_line_entity(2000, 0, 2100, 0),   # No overlap with others
        ]
        
        pipeline_data = self.create_pipeline_data(line_entities)
        self.processor.DETECTION_MODE = "pair_based"
        
        result = self.processor.process(pipeline_data)
        
        # Should find no valid pairs
        self.assertEqual(len(result['wall_candidate_pairs']), 0)
        self.assertEqual(result['totals']['candidate_pairs'], 0)
    
    def test_edge_case_minimum_distance(self):
        """Test edge case with minimum distance constraint."""
        # Create lines exactly at minimum distance (20mm)
        line_entities = [
            self.create_line_entity(0, 0, 1000, 0),
            self.create_line_entity(0, 20, 1000, 20),  # Exactly 20mm apart
        ]
        
        pipeline_data = self.create_pipeline_data(line_entities)
        self.processor.DETECTION_MODE = "pair_based"
        
        result = self.processor.process(pipeline_data)
        
        # Should find one valid pair at minimum distance
        self.assertEqual(len(result['wall_candidate_pairs']), 1)
        self.assertAlmostEqual(
            result['wall_candidate_pairs'][0]['geometric_properties']['perpendicular_distance'],
            20.0,
            places=1
        )
    
    def test_edge_case_maximum_distance(self):
        """Test edge case with maximum distance constraint."""
        # Create lines exactly at maximum distance (450mm)
        line_entities = [
            self.create_line_entity(0, 0, 1000, 0),
            self.create_line_entity(0, 450, 1000, 450),  # Exactly 450mm apart
        ]
        
        pipeline_data = self.create_pipeline_data(line_entities)
        self.processor.DETECTION_MODE = "pair_based"
        
        result = self.processor.process(pipeline_data)
        
        # Should find one valid pair at maximum distance
        self.assertEqual(len(result['wall_candidate_pairs']), 1)
        self.assertAlmostEqual(
            result['wall_candidate_pairs'][0]['geometric_properties']['perpendicular_distance'],
            450.0,
            places=1
        )
    
    def test_edge_case_minimum_overlap(self):
        """Test edge case with minimum overlap requirement."""
        # Create lines with exactly 90% overlap (1000mm line, 900mm overlap)
        line_entities = [
            self.create_line_entity(0, 0, 1000, 0),       # 1000mm line
            self.create_line_entity(100, 100, 1100, 100),  # 1000mm line, 900mm overlap = 90%
        ]
        
        pipeline_data = self.create_pipeline_data(line_entities)
        self.processor.DETECTION_MODE = "pair_based"
        
        result = self.processor.process(pipeline_data)
        
        # Should find one valid pair with minimum overlap
        self.assertEqual(len(result['wall_candidate_pairs']), 1)
        self.assertAlmostEqual(
            result['wall_candidate_pairs'][0]['geometric_properties']['overlap_percentage'],
            90.0,
            places=1
        )


if __name__ == '__main__':
    unittest.main()