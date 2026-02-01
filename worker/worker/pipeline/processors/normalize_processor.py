"""
NORMALIZE processor - Apply coordinate normalization and validation.
"""

import time
from typing import Dict, Any, List
from .base_processor import BaseProcessor

class NormalizeProcessor(BaseProcessor):
    """Processor for normalizing geometry coordinates."""
    
    EPSILON = 1e-6  # Fixed epsilon for normalization
    
    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize entity coordinates and validate geometry."""
        self.log_info("Starting coordinate normalization")
        
        start_time = time.time()
        
        # Get extracted entities from previous step
        extract_results = pipeline_data.get('extract_results', {})
        entities = extract_results.get('entities', {})
        
        normalized_entities = {
            'lines': [],
            'polylines': [],
            'blocks': []
        }
        
        validation_stats = {
            'valid_entities': 0,
            'invalid_entities': 0,
            'normalization_errors': 0
        }
        
        # Normalize lines
        for line_entity in entities.get('lines', []):
            try:
                normalized_line = self._normalize_line(line_entity)
                if self._validate_line(normalized_line):
                    normalized_entities['lines'].append(normalized_line)
                    validation_stats['valid_entities'] += 1
                else:
                    validation_stats['invalid_entities'] += 1
            except Exception as e:
                validation_stats['normalization_errors'] += 1
                self.log_error(f"Line normalization error: {str(e)}")
        
        # Normalize polylines
        for polyline_entity in entities.get('polylines', []):
            try:
                normalized_polyline = self._normalize_polyline(polyline_entity)
                if self._validate_polyline(normalized_polyline):
                    normalized_entities['polylines'].append(normalized_polyline)
                    validation_stats['valid_entities'] += 1
                else:
                    validation_stats['invalid_entities'] += 1
            except Exception as e:
                validation_stats['normalization_errors'] += 1
                self.log_error(f"Polyline normalization error: {str(e)}")
        
        # Normalize blocks
        for block_entity in entities.get('blocks', []):
            try:
                normalized_block = self._normalize_block(block_entity)
                if self._validate_block(normalized_block):
                    normalized_entities['blocks'].append(normalized_block)
                    validation_stats['valid_entities'] += 1
                else:
                    validation_stats['invalid_entities'] += 1
            except Exception as e:
                validation_stats['normalization_errors'] += 1
                self.log_error(f"Block normalization error: {str(e)}")
        
        # Calculate totals
        total_normalized = (
            len(normalized_entities['lines']) +
            len(normalized_entities['polylines']) +
            len(normalized_entities['blocks'])
        )
        
        # Update metrics
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            total_normalized=total_normalized,
            valid_entities=validation_stats['valid_entities'],
            invalid_entities=validation_stats['invalid_entities'],
            normalization_errors=validation_stats['normalization_errors'],
            epsilon=self.EPSILON
        )
        
        self.log_info(
            "Coordinate normalization completed",
            total_normalized=total_normalized,
            valid_entities=validation_stats['valid_entities'],
            invalid_entities=validation_stats['invalid_entities'],
            normalization_errors=validation_stats['normalization_errors'],
            duration_ms=duration_ms
        )
        
        return {
            'entities': normalized_entities,
            'validation_stats': validation_stats,
            'totals': {
                'lines': len(normalized_entities['lines']),
                'polylines': len(normalized_entities['polylines']),
                'blocks': len(normalized_entities['blocks']),
                'total': total_normalized
            }
        }
    
    def _normalize_coordinate(self, value: float) -> float:
        """Normalize a coordinate value using fixed epsilon."""
        return round(value / self.EPSILON) * self.EPSILON
    
    def _normalize_point(self, point: Dict[str, float]) -> Dict[str, float]:
        """Normalize a 3D point."""
        return {
            'X': self._normalize_coordinate(point.get('X', 0.0)),
            'Y': self._normalize_coordinate(point.get('Y', 0.0)),
            'Z': self._normalize_coordinate(point.get('Z', 0.0))
        }
    
    def _normalize_line(self, line_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a line entity."""
        line_data = line_entity['data']
        
        normalized_data = {
            'Start': self._normalize_point(line_data['Start']),
            'End': self._normalize_point(line_data['End'])
        }
        
        return {
            'layer_name': line_entity['layer_name'],
            'entity_type': line_entity['entity_type'],
            'original_data': line_data,
            'normalized_data': normalized_data
        }
    
    def _normalize_polyline(self, polyline_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a polyline entity."""
        polyline_data = polyline_entity['data']
        
        normalized_vertices = []
        for vertex in polyline_data.get('Vertices', []):
            normalized_vertices.append(self._normalize_point(vertex))
        
        normalized_data = {
            'Vertices': normalized_vertices,
            'IsClosed': polyline_data.get('IsClosed', False)
        }
        
        return {
            'layer_name': polyline_entity['layer_name'],
            'entity_type': polyline_entity['entity_type'],
            'original_data': polyline_data,
            'normalized_data': normalized_data
        }
    
    def _normalize_block(self, block_entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a block entity."""
        block_data = block_entity['data']
        
        normalized_data = {
            'Position': self._normalize_point(block_data['Position']),
            'Rotation': block_data.get('Rotation', 0.0),
            'ScaleX': block_data.get('ScaleX', 1.0),
            'ScaleY': block_data.get('ScaleY', 1.0)
        }
        
        # Normalize bounding box if present
        if 'BoundingBox' in block_data:
            bbox = block_data['BoundingBox']
            normalized_data['BoundingBox'] = {
                'MinPoint': self._normalize_point(bbox['MinPoint']),
                'MaxPoint': self._normalize_point(bbox['MaxPoint'])
            }
        
        return {
            'layer_name': block_entity['layer_name'],
            'entity_type': block_entity['entity_type'],
            'original_data': block_data,
            'normalized_data': normalized_data,
            'block_name': block_data.get('Name', '')
        }
    
    def _validate_line(self, line_entity: Dict[str, Any]) -> bool:
        """Validate normalized line entity."""
        try:
            data = line_entity['normalized_data']
            start = data['Start']
            end = data['End']
            
            # Check if start and end are different
            dx = abs(end['X'] - start['X'])
            dy = abs(end['Y'] - start['Y'])
            dz = abs(end.get('Z', 0) - start.get('Z', 0))
            
            return (dx + dy + dz) > self.EPSILON
        except Exception:
            return False
    
    def _validate_polyline(self, polyline_entity: Dict[str, Any]) -> bool:
        """Validate normalized polyline entity."""
        try:
            data = polyline_entity['normalized_data']
            vertices = data.get('Vertices', [])
            
            # Must have at least 2 vertices
            return len(vertices) >= 2
        except Exception:
            return False
    
    def _validate_block(self, block_entity: Dict[str, Any]) -> bool:
        """Validate normalized block entity."""
        try:
            data = block_entity['normalized_data']
            
            # Must have position
            return 'Position' in data
        except Exception:
            return False