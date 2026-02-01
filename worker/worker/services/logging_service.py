"""
Logging service for worker (simplified version of backend service).
"""

import structlog
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..database_models import JobLog

class LoggingService:
    """Service for structured logging with database persistence."""
    
    def __init__(self):
        self.logger = structlog.get_logger()
    
    def log_job_event(self, db: Session, job_id: uuid.UUID, level: str, 
                     message: str, context: Optional[Dict[str, Any]] = None,
                     step_id: Optional[uuid.UUID] = None,
                     drawing_id: Optional[uuid.UUID] = None,
                     request_id: Optional[str] = None):
        """Log a job-related event to both structured logs and database."""
        
        # Log to structured logger
        log_context = {
            'job_id': str(job_id),
            'level': level,
            'message': message
        }
        
        if step_id:
            log_context['step_id'] = str(step_id)
        if drawing_id:
            log_context['drawing_id'] = str(drawing_id)
        if request_id:
            log_context['request_id'] = request_id
        if context:
            log_context.update(context)
        
        # Log to structured logger based on level
        if level.upper() == 'ERROR':
            self.logger.error(message, **log_context)
        elif level.upper() == 'WARNING':
            self.logger.warning(message, **log_context)
        elif level.upper() == 'INFO':
            self.logger.info(message, **log_context)
        elif level.upper() == 'DEBUG':
            self.logger.debug(message, **log_context)
        else:
            self.logger.info(message, **log_context)
        
        # Persist to database
        try:
            log_entry = JobLog(
                job_id=job_id,
                step_id=step_id,
                request_id=request_id,
                drawing_id=drawing_id,
                level=level.upper(),
                message=message,
                context=context or {}
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            # Don't let logging failures break the application
            self.logger.error(
                "Failed to persist log to database",
                error=str(e),
                original_message=message
            )