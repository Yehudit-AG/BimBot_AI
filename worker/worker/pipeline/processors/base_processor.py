"""
Base processor class for pipeline steps.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any
from sqlalchemy.orm import Session
import structlog

logger = structlog.get_logger()

class BaseProcessor(ABC):
    """Base class for all pipeline processors."""
    
    def __init__(self, job_id: uuid.UUID, db: Session):
        self.job_id = job_id
        self.db = db
        self.metrics = {}
        self.start_time = None
        self.end_time = None
    
    @abstractmethod
    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the pipeline data and return results."""
        pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get processing metrics."""
        return self.metrics.copy()
    
    def log_info(self, message: str, **context):
        """Log info message with job context."""
        logger.info(
            message,
            job_id=str(self.job_id),
            processor=self.__class__.__name__,
            **context
        )
    
    def log_error(self, message: str, **context):
        """Log error message with job context."""
        logger.error(
            message,
            job_id=str(self.job_id),
            processor=self.__class__.__name__,
            **context
        )
    
    def update_metrics(self, **metrics):
        """Update processor metrics."""
        self.metrics.update(metrics)