"""
Metrics service for collecting and storing performance metrics.
"""

import time
import uuid
from typing import Dict, Any, Optional
from contextlib import contextmanager
from sqlalchemy.orm import Session
from ..models.database_models import JobStep
from .logging_service import logging_service

class MetricsService:
    """Service for collecting and storing performance metrics."""
    
    def __init__(self):
        self.metrics_cache = {}
    
    @contextmanager
    def measure_time(self, operation_name: str, context: Optional[Dict[str, Any]] = None):
        """Context manager for measuring operation duration."""
        start_time = time.time()
        operation_context = context or {}
        
        try:
            yield
            duration_ms = int((time.time() - start_time) * 1000)
            
            logging_service.logger.info(
                f"Operation completed: {operation_name}",
                operation=operation_name,
                duration_ms=duration_ms,
                **operation_context
            )
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            logging_service.logger.error(
                f"Operation failed: {operation_name}",
                operation=operation_name,
                duration_ms=duration_ms,
                error=str(e),
                **operation_context
            )
            raise
    
    def record_step_metrics(self, db: Session, step_id: uuid.UUID, 
                           metrics: Dict[str, Any]):
        """Record metrics for a job step."""
        try:
            step = db.query(JobStep).filter(JobStep.id == step_id).first()
            if step:
                # Merge with existing metrics
                existing_metrics = step.metrics or {}
                existing_metrics.update(metrics)
                step.metrics = existing_metrics
                db.commit()
                
                logging_service.logger.info(
                    "Step metrics recorded",
                    step_id=str(step_id),
                    step_name=step.step_name,
                    metrics=metrics
                )
        except Exception as e:
            logging_service.logger.error(
                "Failed to record step metrics",
                step_id=str(step_id),
                error=str(e)
            )
    
    def record_processing_metrics(self, job_id: uuid.UUID, step_name: str,
                                 entities_processed: int, entities_failed: int,
                                 processing_time_ms: int, memory_usage_mb: Optional[float] = None):
        """Record processing metrics for a pipeline step."""
        metrics = {
            'entities_processed': entities_processed,
            'entities_failed': entities_failed,
            'processing_time_ms': processing_time_ms,
            'processing_rate_per_second': (entities_processed / max(processing_time_ms / 1000, 0.001)),
            'success_rate_percent': (entities_processed / max(entities_processed + entities_failed, 1)) * 100
        }
        
        if memory_usage_mb is not None:
            metrics['memory_usage_mb'] = memory_usage_mb
        
        # Cache metrics for later persistence
        cache_key = f"{job_id}_{step_name}"
        self.metrics_cache[cache_key] = metrics
        
        logging_service.logger.info(
            "Processing metrics recorded",
            job_id=str(job_id),
            step_name=step_name,
            **metrics
        )
    
    def record_geometry_metrics(self, job_id: uuid.UUID, step_name: str,
                               lines_count: int, polylines_count: int, blocks_count: int,
                               duplicates_removed: int, validation_errors: int):
        """Record geometry-specific metrics."""
        total_entities = lines_count + polylines_count + blocks_count
        
        metrics = {
            'total_entities': total_entities,
            'lines_count': lines_count,
            'polylines_count': polylines_count,
            'blocks_count': blocks_count,
            'duplicates_removed': duplicates_removed,
            'validation_errors': validation_errors,
            'duplicate_rate_percent': (duplicates_removed / max(total_entities, 1)) * 100,
            'error_rate_percent': (validation_errors / max(total_entities, 1)) * 100
        }
        
        # Cache metrics for later persistence
        cache_key = f"{job_id}_{step_name}_geometry"
        self.metrics_cache[cache_key] = metrics
        
        logging_service.logger.info(
            "Geometry metrics recorded",
            job_id=str(job_id),
            step_name=step_name,
            **metrics
        )
    
    def record_wall_detection_metrics(self, job_id: uuid.UUID, 
                                    wall_candidates: int, wall_segments: int,
                                    total_wall_length: float, intersection_count: int,
                                    average_confidence: float):
        """Record wall detection metrics."""
        metrics = {
            'wall_candidates': wall_candidates,
            'wall_segments': wall_segments,
            'total_wall_length': total_wall_length,
            'intersection_count': intersection_count,
            'average_confidence': average_confidence,
            'segments_per_candidate': wall_segments / max(wall_candidates, 1),
            'intersections_per_segment': intersection_count / max(wall_segments, 1)
        }
        
        # Cache metrics for later persistence
        cache_key = f"{job_id}_wall_detection"
        self.metrics_cache[cache_key] = metrics
        
        logging_service.logger.info(
            "Wall detection metrics recorded",
            job_id=str(job_id),
            **metrics
        )
    
    def flush_cached_metrics(self, db: Session, job_id: uuid.UUID):
        """Flush cached metrics to database."""
        try:
            # Get all job steps
            steps = db.query(JobStep).filter(JobStep.job_id == job_id).all()
            step_lookup = {step.step_name: step for step in steps}
            
            # Process cached metrics
            for cache_key, metrics in self.metrics_cache.items():
                if str(job_id) in cache_key:
                    # Extract step name from cache key
                    parts = cache_key.split('_')
                    if len(parts) >= 2:
                        step_name = '_'.join(parts[1:-1]) if 'geometry' in cache_key or 'wall_detection' in cache_key else '_'.join(parts[1:])
                        
                        if step_name in step_lookup:
                            step = step_lookup[step_name]
                            existing_metrics = step.metrics or {}
                            existing_metrics.update(metrics)
                            step.metrics = existing_metrics
            
            db.commit()
            
            # Clear cached metrics for this job
            keys_to_remove = [key for key in self.metrics_cache.keys() if str(job_id) in key]
            for key in keys_to_remove:
                del self.metrics_cache[key]
                
            logging_service.logger.info(
                "Cached metrics flushed to database",
                job_id=str(job_id),
                metrics_count=len(keys_to_remove)
            )
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to flush cached metrics",
                job_id=str(job_id),
                error=str(e)
            )
    
    def get_job_metrics_summary(self, db: Session, job_id: uuid.UUID) -> Dict[str, Any]:
        """Get aggregated metrics summary for a job."""
        try:
            steps = db.query(JobStep).filter(JobStep.job_id == job_id).all()
            
            summary = {
                'total_steps': len(steps),
                'completed_steps': len([s for s in steps if s.status == 'completed']),
                'failed_steps': len([s for s in steps if s.status == 'failed']),
                'total_duration_ms': sum(s.duration_ms or 0 for s in steps),
                'step_metrics': {}
            }
            
            # Aggregate step metrics
            for step in steps:
                if step.metrics:
                    summary['step_metrics'][step.step_name] = step.metrics
            
            return summary
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to get job metrics summary",
                job_id=str(job_id),
                error=str(e)
            )
            return {}
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system-wide metrics."""
        import psutil
        
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'cached_metrics_count': len(self.metrics_cache)
            }
        except Exception as e:
            logging_service.logger.error(
                "Failed to get system metrics",
                error=str(e)
            )
            return {}

# Global metrics service instance
metrics_service = MetricsService()