"""
Logging service for structured logging with correlation IDs.
"""

import structlog
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..models.database_models import JobLog

class LoggingService:
    """Service for structured logging with database persistence."""
    
    def __init__(self):
        # Configure structured logging
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
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
    
    def get_logger_with_context(self, **context) -> structlog.BoundLogger:
        """Get a logger bound with specific context."""
        return self.logger.bind(**context)
    
    def log_api_request(self, request_id: str, method: str, path: str, 
                       user_agent: Optional[str] = None, 
                       ip_address: Optional[str] = None):
        """Log API request with correlation ID."""
        self.logger.info(
            "API request",
            request_id=request_id,
            method=method,
            path=path,
            user_agent=user_agent,
            ip_address=ip_address
        )
    
    def log_api_response(self, request_id: str, status_code: int, 
                        duration_ms: int, response_size: Optional[int] = None):
        """Log API response with timing metrics."""
        self.logger.info(
            "API response",
            request_id=request_id,
            status_code=status_code,
            duration_ms=duration_ms,
            response_size=response_size
        )
    
    def log_database_operation(self, operation: str, table: str, 
                              record_id: Optional[str] = None,
                              duration_ms: Optional[int] = None,
                              error: Optional[str] = None):
        """Log database operations for monitoring."""
        log_data = {
            'operation': operation,
            'table': table
        }
        
        if record_id:
            log_data['record_id'] = record_id
        if duration_ms:
            log_data['duration_ms'] = duration_ms
        
        if error:
            log_data['error'] = error
            self.logger.error("Database operation failed", **log_data)
        else:
            self.logger.debug("Database operation", **log_data)
    
    def log_file_operation(self, operation: str, file_path: str,
                          file_size: Optional[int] = None,
                          duration_ms: Optional[int] = None,
                          error: Optional[str] = None):
        """Log file operations for monitoring."""
        log_data = {
            'operation': operation,
            'file_path': file_path
        }
        
        if file_size:
            log_data['file_size'] = file_size
        if duration_ms:
            log_data['duration_ms'] = duration_ms
        
        if error:
            log_data['error'] = error
            self.logger.error("File operation failed", **log_data)
        else:
            self.logger.info("File operation", **log_data)

# Global logging service instance
logging_service = LoggingService()