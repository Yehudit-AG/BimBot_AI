"""
Metrics service for worker (simplified version of backend service).
"""

import uuid
from typing import Dict, Any
from sqlalchemy.orm import Session
from ..database_models import JobStep

class MetricsService:
    """Service for collecting and storing performance metrics."""
    
    def __init__(self):
        self.metrics_cache = {}
    
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
        except Exception:
            pass  # Don't let metrics failures break the application