"""
CLEAN_DEDUP processor - Remove duplicates using epsilon-based comparison.
"""

import time
import hashlib
import json
import random
from typing import Dict, Any, List, Set
from .base_processor import BaseProcessor
from ...services.artifact_service import ArtifactService

class CleanDedupProcessor(BaseProcessor):
    """Processor for cleaning and deduplicating entities."""
    
    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove duplicate entities using deterministic hashing."""
        self.log_info("Starting entity deduplication")
        
        start_time = time.time()
        
        # Get normalized entities from previous step
        normalize_results = pipeline_data.get('normalize_results', {})
        entities = normalize_results.get('entities', {})
        
        deduplicated_entities = {
            'lines': [],
            'polylines': [],
            'blocks': []
        }
        
        dedup_stats = {
            'original_count': 0,
            'duplicate_count': 0,
            'final_count': 0,
            'hash_collisions': 0
        }
        
        # Deduplicate lines
        line_hashes = set()
        for line_entity in entities.get('lines', []):
            dedup_stats['original_count'] += 1
            
            entity_hash = self._generate_entity_hash(line_entity)
            
            if entity_hash not in line_hashes:
                line_hashes.add(entity_hash)
                line_entity['entity_hash'] = entity_hash
                deduplicated_entities['lines'].append(line_entity)
                dedup_stats['final_count'] += 1
            else:
                dedup_stats['duplicate_count'] += 1
        
        # Deduplicate polylines
        polyline_hashes = set()
        for polyline_entity in entities.get('polylines', []):
            dedup_stats['original_count'] += 1
            
            entity_hash = self._generate_entity_hash(polyline_entity)
            
            if entity_hash not in polyline_hashes:
                polyline_hashes.add(entity_hash)
                polyline_entity['entity_hash'] = entity_hash
                deduplicated_entities['polylines'].append(polyline_entity)
                dedup_stats['final_count'] += 1
            else:
                dedup_stats['duplicate_count'] += 1
        
        # Deduplicate blocks
        block_hashes = set()
        for block_entity in entities.get('blocks', []):
            dedup_stats['original_count'] += 1
            
            entity_hash = self._generate_entity_hash(block_entity)
            
            if entity_hash not in block_hashes:
                block_hashes.add(entity_hash)
                block_entity['entity_hash'] = entity_hash
                deduplicated_entities['blocks'].append(block_entity)
                dedup_stats['final_count'] += 1
            else:
                dedup_stats['duplicate_count'] += 1
        
        # Calculate deduplication efficiency
        dedup_efficiency = 0.0
        if dedup_stats['original_count'] > 0:
            dedup_efficiency = (dedup_stats['duplicate_count'] / dedup_stats['original_count']) * 100
        
        # Update metrics
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            original_count=dedup_stats['original_count'],
            duplicate_count=dedup_stats['duplicate_count'],
            final_count=dedup_stats['final_count'],
            dedup_efficiency_percent=dedup_efficiency,
            unique_line_hashes=len(line_hashes),
            unique_polyline_hashes=len(polyline_hashes),
            unique_block_hashes=len(block_hashes)
        )
        
        # Generate canvas data artifact
        canvas_data = self._generate_canvas_data(deduplicated_entities)
        self._create_canvas_artifact(canvas_data)
        
        self.log_info(
            "Entity deduplication completed",
            original_count=dedup_stats['original_count'],
            duplicate_count=dedup_stats['duplicate_count'],
            final_count=dedup_stats['final_count'],
            dedup_efficiency_percent=round(dedup_efficiency, 2),
            duration_ms=duration_ms
        )
        
        return {
            'entities': deduplicated_entities,
            'dedup_stats': dedup_stats,
            'totals': {
                'lines': len(deduplicated_entities['lines']),
                'polylines': len(deduplicated_entities['polylines']),
                'blocks': len(deduplicated_entities['blocks']),
                'total': dedup_stats['final_count']
            }
        }
    
    def _generate_entity_hash(self, entity: Dict[str, Any]) -> str:
        """Generate deterministic hash for entity."""
        # Create hash components
        hash_components = [
            entity['layer_name'],
            entity['entity_type'],
            json.dumps(entity['normalized_data'], sort_keys=True)
        ]
        
        # Add block name if present
        if 'block_name' in entity:
            hash_components.append(entity['block_name'])
        
        # Create hash
        hash_string = '|'.join(hash_components)
        return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
    
    def _clean_entity_data(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Clean entity data by removing unnecessary fields."""
        cleaned_entity = entity.copy()
        
        # Remove fields that shouldn't be included in final output
        fields_to_remove = ['original_data']  # Keep normalized_data only
        
        for field in fields_to_remove:
            if field in cleaned_entity:
                del cleaned_entity[field]
        
        return cleaned_entity
    
    def _generate_canvas_data(self, entities: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Generate canvas visualization data from cleaned entities."""
        # Calculate drawing bounds
        drawing_bounds = self._calculate_drawing_bounds(entities)
        
        # Group entities by layer and prepare canvas format
        layers = {}
        layer_colors = self._generate_layer_colors(entities)
        
        for line_entity in entities.get('lines', []):
            layer_name = line_entity['layer_name']
            
            if layer_name not in layers:
                layers[layer_name] = {
                    'lines': [],
                    'color': layer_colors.get(layer_name, '#000000'),
                    'visible': True
                }
            
            # Convert normalized coordinates to canvas format
            normalized_data = line_entity['normalized_data']
            start = normalized_data['Start']
            end = normalized_data['End']
            
            canvas_line = {
                'id': line_entity['entity_hash'],
                'start': {'x': start['X'], 'y': start['Y'], 'z': start.get('Z', 0)},
                'end': {'x': end['X'], 'y': end['Y'], 'z': end.get('Z', 0)},
                'length': self._calculate_line_length(start, end)
            }
            
            layers[layer_name]['lines'].append(canvas_line)
        
        # Add polylines as connected line segments
        for polyline_entity in entities.get('polylines', []):
            layer_name = polyline_entity['layer_name']
            
            if layer_name not in layers:
                layers[layer_name] = {
                    'lines': [],
                    'color': layer_colors.get(layer_name, '#000000'),
                    'visible': True
                }
            
            # Convert polyline vertices to line segments
            normalized_data = polyline_entity['normalized_data']
            vertices = normalized_data.get('Vertices', [])
            
            for i in range(len(vertices) - 1):
                start = vertices[i]
                end = vertices[i + 1]
                
                canvas_line = {
                    'id': f"{polyline_entity['entity_hash']}_seg_{i}",
                    'start': {'x': start['X'], 'y': start['Y'], 'z': start.get('Z', 0)},
                    'end': {'x': end['X'], 'y': end['Y'], 'z': end.get('Z', 0)},
                    'length': self._calculate_line_length(start, end)
                }
                
                layers[layer_name]['lines'].append(canvas_line)
        
        # Calculate statistics
        total_lines = sum(len(layer['lines']) for layer in layers.values())
        
        return {
            'drawing_bounds': drawing_bounds,
            'layers': layers,
            'statistics': {
                'total_lines': total_lines,
                'total_layers': len(layers),
                'layer_names': list(layers.keys())
            }
        }
    
    def _calculate_drawing_bounds(self, entities: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
        """Calculate the bounding box of all entities."""
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        # Process lines
        for line_entity in entities.get('lines', []):
            normalized_data = line_entity['normalized_data']
            start = normalized_data['Start']
            end = normalized_data['End']
            
            min_x = min(min_x, start['X'], end['X'])
            max_x = max(max_x, start['X'], end['X'])
            min_y = min(min_y, start['Y'], end['Y'])
            max_y = max(max_y, start['Y'], end['Y'])
        
        # Process polylines
        for polyline_entity in entities.get('polylines', []):
            normalized_data = polyline_entity['normalized_data']
            vertices = normalized_data.get('Vertices', [])
            
            for vertex in vertices:
                min_x = min(min_x, vertex['X'])
                max_x = max(max_x, vertex['X'])
                min_y = min(min_y, vertex['Y'])
                max_y = max(max_y, vertex['Y'])
        
        # Handle case where no entities exist
        if min_x == float('inf'):
            return {'min_x': 0, 'max_x': 1000, 'min_y': 0, 'max_y': 1000}
        
        # Add padding (5% of drawing size)
        width = max_x - min_x
        height = max_y - min_y
        padding_x = width * 0.05
        padding_y = height * 0.05
        
        return {
            'min_x': min_x - padding_x,
            'max_x': max_x + padding_x,
            'min_y': min_y - padding_y,
            'max_y': max_y + padding_y
        }
    
    def _generate_layer_colors(self, entities: Dict[str, List[Dict[str, Any]]]) -> Dict[str, str]:
        """Generate distinct colors for each layer."""
        layer_names = set()
        
        # Collect all unique layer names
        for entity_list in entities.values():
            for entity in entity_list:
                layer_names.add(entity['layer_name'])
        
        # Predefined color palette for better visual distinction
        colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
            '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
            '#F8C471', '#82E0AA', '#F1948A', '#85C1E9', '#D7BDE2',
            '#A3E4D7', '#F9E79F', '#D5A6BD', '#AED6F1', '#A9DFBF'
        ]
        
        layer_colors = {}
        sorted_layers = sorted(layer_names)
        
        for i, layer_name in enumerate(sorted_layers):
            # Use predefined colors, cycling if more layers than colors
            layer_colors[layer_name] = colors[i % len(colors)]
        
        return layer_colors
    
    def _calculate_line_length(self, start: Dict[str, float], end: Dict[str, float]) -> float:
        """Calculate the length of a line segment."""
        dx = end['X'] - start['X']
        dy = end['Y'] - start['Y']
        dz = end.get('Z', 0) - start.get('Z', 0)
        return (dx**2 + dy**2 + dz**2)**0.5
    
    def _create_canvas_artifact(self, canvas_data: Dict[str, Any]) -> None:
        """Create and save canvas data artifact."""
        try:
            artifact_service = ArtifactService()
            artifact_service.create_artifact(
                db=self.db,
                job_id=self.job_id,
                artifact_type="canvas_data",
                artifact_name="canvas_data.json",
                content=canvas_data,
                content_type="application/json",
                metadata={
                    "description": "Canvas visualization data for line debugging",
                    "total_lines": canvas_data['statistics']['total_lines'],
                    "total_layers": canvas_data['statistics']['total_layers']
                }
            )
            
            self.log_info(
                "Canvas data artifact created",
                total_lines=canvas_data['statistics']['total_lines'],
                total_layers=canvas_data['statistics']['total_layers']
            )
            
        except Exception as e:
            self.log_error(f"Failed to create canvas artifact: {str(e)}")
            # Don't fail the entire step if artifact creation fails