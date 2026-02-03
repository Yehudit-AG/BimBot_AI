"""
BimBot AI Wall Worker - RQ Worker Process
Main worker entry point for processing jobs.
"""

import logging
import os
import sys
import redis
from rq import Worker, Queue, Connection
import structlog

# Add the worker directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker.config import settings
from worker.job_processor import process_job

# Ensure INFO (and below) are printed to stderr so they appear in docker logs
logging.basicConfig(
    level=getattr(logging, (getattr(settings, "log_level", "INFO") or "INFO").upper()),
    format="%(message)s",
    stream=sys.stderr,
)

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

logger = structlog.get_logger()

def main():
    """Main worker process."""
    logger.info(
        "Starting BimBot AI Wall worker",
        redis_url=settings.redis_url,
        concurrency=settings.worker_concurrency
    )
    
    # Connect to Redis
    redis_connection = redis.from_url(settings.redis_url)
    
    # Create queues
    queues = [
        Queue('bimbot_jobs', connection=redis_connection),
        Queue('bimbot_high_priority', connection=redis_connection),
        Queue('bimbot_low_priority', connection=redis_connection)
    ]
    
    # Create worker
    worker = Worker(
        queues,
        connection=redis_connection,
        name=f"bimbot-worker-{os.getpid()}"
    )
    
    logger.info(
        "Worker created successfully",
        worker_name=worker.name,
        queues=[q.name for q in queues]
    )
    
    try:
        # Start worker
        worker.work(with_scheduler=True)
    except KeyboardInterrupt:
        logger.info("Worker interrupted, shutting down gracefully")
    except Exception as e:
        logger.error("Worker error", error=str(e))
        raise
    finally:
        logger.info("Worker shutdown complete")

if __name__ == '__main__':
    main()