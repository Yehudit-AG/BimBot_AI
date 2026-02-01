"""
Job service for managing job lifecycle and Redis queue integration.
"""

import redis
from rq import Queue
import uuid
from typing import Optional
from ..config import settings
import structlog

logger = structlog.get_logger()

class JobService:
    """Service for job management and queuing."""
    
    def __init__(self):
        # Initialize Redis connection
        self.redis_client = redis.from_url(settings.redis_url)
        self.queue = Queue('bimbot_jobs', connection=self.redis_client)
    
    def enqueue_job(self, job_id: uuid.UUID) -> str:
        """
        Enqueue a job for processing.
        
        Returns:
            RQ job ID
        """
        try:
            # Enqueue job by referencing the worker function by string
            rq_job = self.queue.enqueue(
                'worker.job_processor.process_job',
                str(job_id),
                job_timeout=settings.job_timeout,
                job_id=str(job_id)
            )
            
            logger.info(
                "Job enqueued successfully",
                job_id=str(job_id),
                rq_job_id=rq_job.id
            )
            
            return rq_job.id
            
        except Exception as e:
            logger.error(
                "Failed to enqueue job",
                job_id=str(job_id),
                error=str(e)
            )
            raise
    
    def get_queue_info(self) -> dict:
        """Get information about the job queue."""
        return {
            'queue_length': len(self.queue),
            'failed_jobs': len(self.queue.failed_job_registry),
            'scheduled_jobs': len(self.queue.scheduled_job_registry),
            'started_jobs': len(self.queue.started_job_registry),
            'finished_jobs': len(self.queue.finished_job_registry)
        }
    
    def get_job_status(self, rq_job_id: str) -> Optional[dict]:
        """Get RQ job status."""
        try:
            from rq.job import Job as RQJob
            
            rq_job = RQJob.fetch(rq_job_id, connection=self.redis_client)
            
            return {
                'id': rq_job.id,
                'status': rq_job.get_status(),
                'created_at': rq_job.created_at,
                'started_at': rq_job.started_at,
                'ended_at': rq_job.ended_at,
                'result': rq_job.result,
                'exc_info': rq_job.exc_info
            }
        except Exception:
            return None
    
    def cancel_job(self, rq_job_id: str) -> bool:
        """Cancel a queued job."""
        try:
            from rq.job import Job as RQJob
            
            rq_job = RQJob.fetch(rq_job_id, connection=self.redis_client)
            rq_job.cancel()
            
            logger.info(
                "Job cancelled",
                rq_job_id=rq_job_id
            )
            
            return True
        except Exception as e:
            logger.error(
                "Failed to cancel job",
                rq_job_id=rq_job_id,
                error=str(e)
            )
            return False
    
    def retry_job(self, rq_job_id: str) -> bool:
        """Retry a failed job."""
        try:
            from rq.job import Job as RQJob
            
            rq_job = RQJob.fetch(rq_job_id, connection=self.redis_client)
            rq_job.retry()
            
            logger.info(
                "Job retried",
                rq_job_id=rq_job_id
            )
            
            return True
        except Exception as e:
            logger.error(
                "Failed to retry job",
                rq_job_id=rq_job_id,
                error=str(e)
            )
            return False