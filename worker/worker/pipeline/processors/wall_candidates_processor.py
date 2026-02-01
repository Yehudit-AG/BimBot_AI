"""
WALL_CANDIDATES_PLACEHOLDER processor - Mock wall detection and pair-based detection.
"""

import time
import random
import math
import uuid
from typing import Dict, Any, List, Tuple, Optional
from .base_processor import BaseProcessor

class WallCandidatesProcessor(BaseProcessor):
    """Processor for wall candidate detection with mock and pair-based algorithms."""
    
    # Configuration constants
    ANGULAR_TOLERANCE = 5.0  # degrees
    MIN_DISTANCE = 20.0  # mm (2cm)
    MAX_DISTANCE = 450.0  # mm (45cm)
    MIN_OVERLAP_PERCENTAGE = 90.0  # percent
    DETECTION_MODE = "pair_based"  # "mock" or "pair_based"
    
    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Wall detection algorithm with configurable mode."""
        mode = self.DETECTION_MODE
        self.log_info(f"Starting wall candidate detection ({mode} mode)")
        
        # #region agent log
        import json
        with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"A,C","location":"wall_candidates_processor.py:22","message":"Wall candidates processor started","data":{"mode":mode,"pipeline_data_keys":list(pipeline_data.keys())},"timestamp":int(time.time()*1000)}) + '\n')
        # #endregion
        
        start_time = time.time()
        
        # Get parallel processing results from previous step
        parallel_results = pipeline_data.get('parallel_naive_results', {})
        entities_data = parallel_results.get('entities', {})
        parallel_ready_entities = entities_data.get('parallel_ready_entities', [])
        
        # Filter to only LINE entities
        line_entities = [entity for entity in parallel_ready_entities if entity['entity_type'] == 'LINE']
        
        if mode == "pair_based":
            return self._process_pair_based_detection(line_entities, start_time)
        else:
            return self._process_mock_detection(line_entities, start_time)
    
    def _analyze_line_for_wall(self, line_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze if a line could be a wall (mock implementation)."""
        normalized_data = line_entity.get('normalized_data', {})
        start = normalized_data.get('Start', {})
        end = normalized_data.get('End', {})
        
        # Calculate line properties
        dx = end.get('X', 0) - start.get('X', 0)
        dy = end.get('Y', 0) - start.get('Y', 0)
        length = (dx**2 + dy**2)**0.5
        
        # Mock criteria for wall detection
        min_wall_length = 500.0  # Minimum 500mm
        
        if length < min_wall_length:
            return None
        
        # Determine if line is horizontal or vertical (potential wall)
        epsilon = 1e-6
        is_horizontal = abs(dy) <= epsilon
        is_vertical = abs(dx) <= epsilon
        
        if not (is_horizontal or is_vertical):
            # For Phase 1, only consider horizontal/vertical lines as potential walls
            return None
        
        # Mock confidence calculation
        confidence = min(0.9, length / 2000.0)  # Higher confidence for longer lines
        confidence += random.uniform(0.05, 0.15)  # Add some randomness for demo
        confidence = min(1.0, confidence)
        
        return {
            'entity_hash': line_entity.get('entity_hash', ''),
            'layer_name': line_entity['layer_name'],
            'start_point': start,
            'end_point': end,
            'length': length,
            'orientation': 'horizontal' if is_horizontal else 'vertical',
            'confidence': confidence,
            'wall_type': 'exterior' if 'WALL' in line_entity['layer_name'].upper() else 'interior'
        }
    
    def _group_lines_into_segments(self, wall_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group nearby wall candidates into segments (mock implementation)."""
        if not wall_candidates:
            return []
        
        # Simple grouping by proximity (mock algorithm)
        segments = []
        proximity_threshold = 200.0  # 200mm
        
        for candidate in wall_candidates:
            # For Phase 1, each candidate becomes its own segment
            segment = {
                'segment_id': f"seg_{len(segments) + 1}",
                'candidates': [candidate],
                'length': candidate['length'],
                'orientation': candidate['orientation'],
                'layer_name': candidate['layer_name'],
                'confidence': candidate['confidence'],
                'start_point': candidate['start_point'],
                'end_point': candidate['end_point']
            }
            segments.append(segment)
        
        return segments
    
    def _analyze_wall_orientations(self, wall_segments: List[Dict[str, Any]]) -> Dict[str, int]:
        """Analyze wall orientations (mock implementation)."""
        orientations = {'horizontal': 0, 'vertical': 0, 'diagonal': 0}
        
        for segment in wall_segments:
            orientation = segment.get('orientation', 'diagonal')
            if orientation in orientations:
                orientations[orientation] += 1
            else:
                orientations['diagonal'] += 1
        
        return orientations
    
    def _find_mock_intersections(self, wall_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find wall intersections (mock implementation)."""
        intersections = []
        
        # Mock intersection detection
        for i, segment1 in enumerate(wall_segments):
            for j, segment2 in enumerate(wall_segments[i+1:], i+1):
                # Simple mock: if segments have different orientations, they might intersect
                if segment1['orientation'] != segment2['orientation']:
                    # Create mock intersection point
                    intersection = {
                        'intersection_id': f"int_{len(intersections) + 1}",
                        'segment1_id': segment1['segment_id'],
                        'segment2_id': segment2['segment_id'],
                        'point': {
                            'X': (segment1['start_point']['X'] + segment2['start_point']['X']) / 2,
                            'Y': (segment1['start_point']['Y'] + segment2['start_point']['Y']) / 2,
                            'Z': 0.0
                        },
                        'intersection_type': 'T-junction',  # Mock type
                        'confidence': random.uniform(0.6, 0.9)
                    }
                    intersections.append(intersection)
        
        return intersections[:10]  # Limit to 10 mock intersections
    
    def _process_pair_based_detection(self, line_entities: List[Dict[str, Any]], start_time: float) -> Dict[str, Any]:
        """Process wall candidate detection using pair-based algorithm."""
        # Detect wall candidate pairs
        wall_candidate_pairs = self._detect_wall_candidate_pairs(line_entities)
        
        # Calculate statistics
        detection_stats = {
            'entities_analyzed': len(line_entities),
            'candidate_pairs': len(wall_candidate_pairs),
            'total_pairs_checked': len(line_entities) * (len(line_entities) - 1) // 2
        }
        
        # Calculate metrics for pairs
        total_length = 0
        avg_distance = 0
        avg_overlap = 0
        
        if wall_candidate_pairs:
            total_length = sum(pair['geometric_properties']['average_length'] for pair in wall_candidate_pairs)
            avg_distance = sum(pair['geometric_properties']['perpendicular_distance'] for pair in wall_candidate_pairs) / len(wall_candidate_pairs)
            avg_overlap = sum(pair['geometric_properties']['overlap_percentage'] for pair in wall_candidate_pairs) / len(wall_candidate_pairs)
        
        # Update metrics
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            entities_analyzed=detection_stats['entities_analyzed'],
            candidate_pairs=detection_stats['candidate_pairs'],
            total_pairs_checked=detection_stats['total_pairs_checked'],
            average_distance=avg_distance,
            average_overlap=avg_overlap,
            total_length=total_length
        )
        
        self.log_info(
            "Wall candidate detection completed (pair-based)",
            entities_analyzed=detection_stats['entities_analyzed'],
            candidate_pairs=detection_stats['candidate_pairs'],
            total_pairs_checked=detection_stats['total_pairs_checked'],
            average_distance=round(avg_distance, 2),
            average_overlap=round(avg_overlap, 2),
            duration_ms=duration_ms
        )
        
        result = {
            'wall_candidate_pairs': wall_candidate_pairs,
            'detection_stats': detection_stats,
            'algorithm_config': {
                'angular_tolerance': self.ANGULAR_TOLERANCE,
                'min_distance': self.MIN_DISTANCE,
                'max_distance': self.MAX_DISTANCE,
                'min_overlap_percentage': self.MIN_OVERLAP_PERCENTAGE
            },
            'totals': {
                'candidate_pairs': len(wall_candidate_pairs),
                'total_length': total_length,
                'average_distance': avg_distance,
                'average_overlap': avg_overlap
            }
        }
        
        # #region agent log
        import json
        with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"A,C","location":"wall_candidates_processor.py:207","message":"Wall candidates processor completed","data":{"pairs_count":len(wall_candidate_pairs),"result_keys":list(result.keys())},"timestamp":int(time.time()*1000)}) + '\n')
        # #endregion
        
        return result
    
    def _process_mock_detection(self, line_entities: List[Dict[str, Any]], start_time: float) -> Dict[str, Any]:
        """Process wall candidate detection using mock algorithm."""
        # Mock wall detection algorithm
        wall_candidates = []
        detection_stats = {
            'entities_analyzed': len(line_entities),
            'potential_walls': 0,
            'wall_segments': 0,
            'confidence_scores': []
        }
        
        # Simple heuristic: look for horizontal and vertical lines that could be walls
        for entity in line_entities:
            wall_candidate = self._analyze_line_for_wall(entity)
            if wall_candidate:
                wall_candidates.append(wall_candidate)
                detection_stats['potential_walls'] += 1
                detection_stats['confidence_scores'].append(wall_candidate['confidence'])
        
        # Group nearby lines into wall segments (mock implementation)
        wall_segments = self._group_lines_into_segments(wall_candidates)
        detection_stats['wall_segments'] = len(wall_segments)
        
        # Calculate average confidence
        avg_confidence = 0.0
        if detection_stats['confidence_scores']:
            avg_confidence = sum(detection_stats['confidence_scores']) / len(detection_stats['confidence_scores'])
        
        # Mock wall properties analysis
        wall_analysis = {
            'total_wall_length': sum(segment['length'] for segment in wall_segments),
            'average_wall_thickness': 150.0,  # Mock value in mm
            'wall_orientations': self._analyze_wall_orientations(wall_segments),
            'intersection_points': self._find_mock_intersections(wall_segments)
        }
        
        # Update metrics
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            entities_analyzed=detection_stats['entities_analyzed'],
            potential_walls=detection_stats['potential_walls'],
            wall_segments=detection_stats['wall_segments'],
            average_confidence=avg_confidence,
            total_wall_length=wall_analysis['total_wall_length'],
            intersection_count=len(wall_analysis['intersection_points'])
        )
        
        self.log_info(
            "Wall candidate detection completed (mock)",
            entities_analyzed=detection_stats['entities_analyzed'],
            potential_walls=detection_stats['potential_walls'],
            wall_segments=detection_stats['wall_segments'],
            average_confidence=round(avg_confidence, 2),
            duration_ms=duration_ms
        )
        
        return {
            'wall_candidates': wall_candidates,
            'wall_segments': wall_segments,
            'detection_stats': detection_stats,
            'wall_analysis': wall_analysis,
            'totals': {
                'candidates': len(wall_candidates),
                'segments': len(wall_segments),
                'total_length': wall_analysis['total_wall_length']
            }
        }
    
    def _detect_wall_candidate_pairs(self, line_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect wall candidate pairs using the three core conditions."""
        pairs = []
        
        for i, line1 in enumerate(line_entities):
            for j, line2 in enumerate(line_entities[i+1:], i+1):
                if (self._are_parallel(line1, line2) and 
                    self._check_distance_constraint(line1, line2) and 
                    self._check_overlap_requirement(line1, line2)):
                    
                    pair = self._create_candidate_pair(line1, line2)
                    if pair:
                        pairs.append(pair)
        
        return pairs
    
    def _are_parallel(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> bool:
        """Check if two lines are parallel within angular tolerance."""
        # Get normalized data
        line1_data = line1.get('normalized_data', {})
        line2_data = line2.get('normalized_data', {})
        
        # Calculate direction vectors
        start1 = line1_data.get('Start', {})
        end1 = line1_data.get('End', {})
        start2 = line2_data.get('Start', {})
        end2 = line2_data.get('End', {})
        
        dx1 = end1.get('X', 0) - start1.get('X', 0)
        dy1 = end1.get('Y', 0) - start1.get('Y', 0)
        dx2 = end2.get('X', 0) - start2.get('X', 0)
        dy2 = end2.get('Y', 0) - start2.get('Y', 0)
        
        # Calculate lengths
        len1 = math.sqrt(dx1*dx1 + dy1*dy1)
        len2 = math.sqrt(dx2*dx2 + dy2*dy2)
        
        if len1 == 0 or len2 == 0:
            return False
        
        # Normalize direction vectors
        dx1 /= len1
        dy1 /= len1
        dx2 /= len2
        dy2 /= len2
        
        # Calculate dot product (cosine of angle between vectors)
        dot_product = abs(dx1*dx2 + dy1*dy2)
        
        # Convert angular tolerance to cosine
        tolerance_rad = math.radians(self.ANGULAR_TOLERANCE)
        cos_tolerance = math.cos(tolerance_rad)
        
        # Lines are parallel if dot product is close to 1 (angle close to 0 or 180 degrees)
        return dot_product >= cos_tolerance
    
    def _check_distance_constraint(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> bool:
        """Check if perpendicular distance between lines is within range."""
        distance = self._calculate_perpendicular_distance(line1, line2)
        return self.MIN_DISTANCE <= distance <= self.MAX_DISTANCE
    
    def _calculate_perpendicular_distance(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> float:
        """Calculate perpendicular distance between two parallel lines."""
        line1_data = line1.get('normalized_data', {})
        line2_data = line2.get('normalized_data', {})
        
        # Get points from line1
        start1 = line1_data.get('Start', {})
        end1 = line1_data.get('End', {})
        
        # Get points from line2
        start2 = line2_data.get('Start', {})
        
        # Calculate line1 direction vector
        dx = end1.get('X', 0) - start1.get('X', 0)
        dy = end1.get('Y', 0) - start1.get('Y', 0)
        length = math.sqrt(dx*dx + dy*dy)
        
        if length == 0:
            return float('inf')
        
        # Normalize direction vector
        dx /= length
        dy /= length
        
        # Calculate perpendicular vector
        perp_dx = -dy
        perp_dy = dx
        
        # Vector from line1 start to line2 start
        to_line2_x = start2.get('X', 0) - start1.get('X', 0)
        to_line2_y = start2.get('Y', 0) - start1.get('Y', 0)
        
        # Project onto perpendicular direction to get distance
        distance = abs(to_line2_x * perp_dx + to_line2_y * perp_dy)
        
        return distance
    
    def _check_overlap_requirement(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> bool:
        """Check if overlap between lines meets minimum requirement."""
        overlap_percentage = self._calculate_overlap_percentage(line1, line2)
        return overlap_percentage >= self.MIN_OVERLAP_PERCENTAGE
    
    def _calculate_overlap_percentage(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> float:
        """Calculate overlap percentage between two parallel lines."""
        line1_data = line1.get('normalized_data', {})
        line2_data = line2.get('normalized_data', {})
        
        # Get line endpoints
        start1 = line1_data.get('Start', {})
        end1 = line1_data.get('End', {})
        start2 = line2_data.get('Start', {})
        end2 = line2_data.get('End', {})
        
        # Project both lines onto their main axis (determine if more horizontal or vertical)
        dx1 = end1.get('X', 0) - start1.get('X', 0)
        dy1 = end1.get('Y', 0) - start1.get('Y', 0)
        
        # Choose projection axis based on line1's orientation
        if abs(dx1) >= abs(dy1):
            # More horizontal, project onto X axis
            line1_min = min(start1.get('X', 0), end1.get('X', 0))
            line1_max = max(start1.get('X', 0), end1.get('X', 0))
            line2_min = min(start2.get('X', 0), end2.get('X', 0))
            line2_max = max(start2.get('X', 0), end2.get('X', 0))
        else:
            # More vertical, project onto Y axis
            line1_min = min(start1.get('Y', 0), end1.get('Y', 0))
            line1_max = max(start1.get('Y', 0), end1.get('Y', 0))
            line2_min = min(start2.get('Y', 0), end2.get('Y', 0))
            line2_max = max(start2.get('Y', 0), end2.get('Y', 0))
        
        # Calculate overlap
        overlap_start = max(line1_min, line2_min)
        overlap_end = min(line1_max, line2_max)
        overlap_length = max(0, overlap_end - overlap_start)
        
        # Calculate lengths (overlap % = fraction of the longer line covered by overlap)
        line1_length = line1_max - line1_min
        line2_length = line2_max - line2_min
        longer_length = max(line1_length, line2_length)
        
        if longer_length == 0:
            return 0.0
        
        return (overlap_length / longer_length) * 100.0
    
    def _create_candidate_pair(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a wall candidate pair with all geometric data."""
        try:
            line1_data = line1.get('normalized_data', {})
            line2_data = line2.get('normalized_data', {})
            
            # Calculate geometric properties
            perpendicular_distance = self._calculate_perpendicular_distance(line1, line2)
            overlap_percentage = self._calculate_overlap_percentage(line1, line2)
            
            # Calculate angle difference for reference
            start1 = line1_data.get('Start', {})
            end1 = line1_data.get('End', {})
            start2 = line2_data.get('Start', {})
            end2 = line2_data.get('End', {})
            
            dx1 = end1.get('X', 0) - start1.get('X', 0)
            dy1 = end1.get('Y', 0) - start1.get('Y', 0)
            dx2 = end2.get('X', 0) - start2.get('X', 0)
            dy2 = end2.get('Y', 0) - start2.get('Y', 0)
            
            angle1 = math.atan2(dy1, dx1)
            angle2 = math.atan2(dy2, dx2)
            angle_diff = abs(angle1 - angle2)
            angle_diff = min(angle_diff, math.pi - angle_diff)  # Take smaller angle
            angle_diff_degrees = math.degrees(angle_diff)
            
            # Calculate average length
            len1 = math.sqrt(dx1*dx1 + dy1*dy1)
            len2 = math.sqrt(dx2*dx2 + dy2*dy2)
            avg_length = (len1 + len2) / 2
            
            # Calculate bounding rectangle
            all_x = [start1.get('X', 0), end1.get('X', 0), start2.get('X', 0), end2.get('X', 0)]
            all_y = [start1.get('Y', 0), end1.get('Y', 0), start2.get('Y', 0), end2.get('Y', 0)]
            
            bounding_rectangle = {
                'minX': min(all_x),
                'maxX': max(all_x),
                'minY': min(all_y),
                'maxY': max(all_y)
            }
            
            return {
                'pair_id': str(uuid.uuid4()),
                'line1': {
                    'entity_hash': line1.get('entity_hash', ''),
                    'start_point': start1,
                    'end_point': end1,
                    'layer_name': line1.get('layer_name', '')
                },
                'line2': {
                    'entity_hash': line2.get('entity_hash', ''),
                    'start_point': start2,
                    'end_point': end2,
                    'layer_name': line2.get('layer_name', '')
                },
                'geometric_properties': {
                    'perpendicular_distance': perpendicular_distance,
                    'overlap_percentage': overlap_percentage,
                    'angle_difference': angle_diff_degrees,
                    'average_length': avg_length,
                    'bounding_rectangle': bounding_rectangle
                }
            }
        except Exception as e:
            self.log_error(f"Error creating candidate pair: {str(e)}")
            return None