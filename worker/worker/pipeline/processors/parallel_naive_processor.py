"""
PARALLEL_NAIVE processor - Parallel processing preparation.
"""

import time
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base_processor import BaseProcessor

class ParallelNaiveProcessor(BaseProcessor):
    """Processor for parallel processing preparation and basic analysis."""
    
    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare entities for parallel processing and perform basic analysis."""
        self.log_info("Starting parallel processing preparation")
        
        start_time = time.time()
        
        # Get deduplicated entities from previous step
        dedup_results = pipeline_data.get('clean_dedup_results', {})
        entities = dedup_results.get('entities', {})
        
        # Prepare entities for parallel processing
        all_entities = []
        all_entities.extend(entities.get('lines', []))
        all_entities.extend(entities.get('polylines', []))
        all_entities.extend(entities.get('blocks', []))
        
        # Group entities by layer for parallel processing
        layer_groups = {}
        for entity in all_entities:
            layer_name = entity['layer_name']
            if layer_name not in layer_groups:
                layer_groups[layer_name] = []
            layer_groups[layer_name].append(entity)
        
        # Process layers in parallel
        processed_results = {}
        processing_stats = {
            'layers_processed': 0,
            'entities_analyzed': 0,
            'processing_errors': 0,
            'parallel_tasks': len(layer_groups)
        }
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit tasks for each layer
            future_to_layer = {
                executor.submit(self._process_layer_entities, layer_name, layer_entities): layer_name
                for layer_name, layer_entities in layer_groups.items()
            }
            
            # Collect results
            for future in as_completed(future_to_layer):
                layer_name = future_to_layer[future]
                try:
                    layer_result = future.result()
                    processed_results[layer_name] = layer_result
                    processing_stats['layers_processed'] += 1
                    processing_stats['entities_analyzed'] += layer_result['entity_count']
                except Exception as e:
                    processing_stats['processing_errors'] += 1
                    self.log_error(f"Layer processing error for {layer_name}: {str(e)}")
        
        # Calculate overall statistics
        total_entities = sum(result['entity_count'] for result in processed_results.values())
        
        # Prepare output structure
        parallel_results = {
            'layer_groups': layer_groups,
            'processed_layers': processed_results,
            'parallel_ready_entities': all_entities
        }
        
        # Update metrics
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            total_entities=total_entities,
            layers_processed=processing_stats['layers_processed'],
            parallel_tasks=processing_stats['parallel_tasks'],
            processing_errors=processing_stats['processing_errors'],
            entities_per_layer=len(all_entities) / max(len(layer_groups), 1)
        )
        
        self.log_info(
            "Parallel processing preparation completed",
            total_entities=total_entities,
            layers_processed=processing_stats['layers_processed'],
            parallel_tasks=processing_stats['parallel_tasks'],
            processing_errors=processing_stats['processing_errors'],
            duration_ms=duration_ms
        )
        
        return {
            'entities': parallel_results,
            'processing_stats': processing_stats,
            'totals': {
                'total_entities': total_entities,
                'layer_groups': len(layer_groups),
                'processed_layers': processing_stats['layers_processed']
            }
        }
    
    def _process_layer_entities(self, layer_name: str, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process entities for a single layer."""
        layer_stats = {
            'layer_name': layer_name,
            'entity_count': len(entities),
            'entity_types': {},
            'bounding_box': None,
            'analysis_results': {}
        }
        
        # Count entity types
        for entity in entities:
            entity_type = entity['entity_type']
            if entity_type not in layer_stats['entity_types']:
                layer_stats['entity_types'][entity_type] = 0
            layer_stats['entity_types'][entity_type] += 1
        
        # Calculate layer bounding box
        layer_stats['bounding_box'] = self._calculate_layer_bounds(entities)
        
        # Perform basic geometric analysis
        layer_stats['analysis_results'] = self._analyze_layer_geometry(entities)
        
        return layer_stats
    
    def _calculate_layer_bounds(self, entities: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate bounding box for layer entities."""
        if not entities:
            return None
        
        all_points = []
        
        for entity in entities:
            normalized_data = entity.get('normalized_data', {})
            
            if entity['entity_type'] == 'LINE':
                all_points.extend([normalized_data.get('Start'), normalized_data.get('End')])
            elif entity['entity_type'] == 'POLYLINE':
                all_points.extend(normalized_data.get('Vertices', []))
            elif entity['entity_type'] == 'BLOCK':
                all_points.append(normalized_data.get('Position'))
                if 'BoundingBox' in normalized_data:
                    bbox = normalized_data['BoundingBox']
                    all_points.extend([bbox.get('MinPoint'), bbox.get('MaxPoint')])
        
        # Filter out None points
        valid_points = [p for p in all_points if p is not None]
        
        if not valid_points:
            return None
        
        # Calculate bounds
        x_coords = [p.get('X', 0) for p in valid_points]
        y_coords = [p.get('Y', 0) for p in valid_points]
        z_coords = [p.get('Z', 0) for p in valid_points]
        
        return {
            'MinPoint': {
                'X': min(x_coords),
                'Y': min(y_coords),
                'Z': min(z_coords)
            },
            'MaxPoint': {
                'X': max(x_coords),
                'Y': max(y_coords),
                'Z': max(z_coords)
            }
        }
    
    def _analyze_layer_geometry(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Perform basic geometric analysis on layer entities."""
        analysis = {
            'horizontal_lines': 0,
            'vertical_lines': 0,
            'diagonal_lines': 0,
            'closed_polylines': 0,
            'open_polylines': 0,
            'scaled_blocks': 0,
            'rotated_blocks': 0
        }
        
        epsilon = 1e-6
        
        for entity in entities:
            normalized_data = entity.get('normalized_data', {})
            
            if entity['entity_type'] == 'LINE':
                start = normalized_data.get('Start', {})
                end = normalized_data.get('End', {})
                
                dx = abs(end.get('X', 0) - start.get('X', 0))
                dy = abs(end.get('Y', 0) - start.get('Y', 0))
                
                if dy <= epsilon:
                    analysis['horizontal_lines'] += 1
                elif dx <= epsilon:
                    analysis['vertical_lines'] += 1
                else:
                    analysis['diagonal_lines'] += 1
            
            elif entity['entity_type'] == 'POLYLINE':
                if normalized_data.get('IsClosed', False):
                    analysis['closed_polylines'] += 1
                else:
                    analysis['open_polylines'] += 1
            
            elif entity['entity_type'] == 'BLOCK':
                scale_x = normalized_data.get('ScaleX', 1.0)
                scale_y = normalized_data.get('ScaleY', 1.0)
                rotation = normalized_data.get('Rotation', 0.0)
                
                if abs(scale_x - 1.0) > epsilon or abs(scale_y - 1.0) > epsilon:
                    analysis['scaled_blocks'] += 1
                
                if abs(rotation) > epsilon:
                    analysis['rotated_blocks'] += 1
        
        return analysis