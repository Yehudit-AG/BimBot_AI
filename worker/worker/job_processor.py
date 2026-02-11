"""
Job processor for executing the geometry processing pipeline.
"""

import json
import uuid
import time
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import structlog

from .config import settings
from .pipeline.pipeline_executor import PipelineExecutor
from .database_models import Job, JobStep, JobLog, Drawing, Layer, LayerSelection
from .services.logging_service import LoggingService
from .services.metrics_service import MetricsService
from .services.artifact_service import ArtifactService

logger = structlog.get_logger()

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def process_job(job_id_str: str) -> Dict[str, Any]:
    """
    Main job processing function called by RQ worker.
    
    Args:
        job_id_str: String representation of job UUID
        
    Returns:
        Job processing results
    """
    job_id = uuid.UUID(job_id_str)
    
    logger.info(
        "Job processing started",
        job_id=job_id_str
    )
    
    db = SessionLocal()
    job = None

    try:
        # Get job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # Update job status
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
        
        # Log job start
        log_entry = JobLog(
            job_id=job.id,
            drawing_id=job.drawing_id,
            level="INFO",
            message="Job processing started",
            context={"job_type": job.job_type}
        )
        db.add(log_entry)
        db.commit()
        
        # Get drawing and selected layers
        drawing = db.query(Drawing).filter(Drawing.id == job.drawing_id).first()
        if not drawing:
            raise ValueError(f"Drawing {job.drawing_id} not found")
        
        # Get selected layers
        selected_layer_ids = [uuid.UUID(lid) for lid in job.selected_layers]
        selected_layers = db.query(Layer).filter(Layer.id.in_(selected_layer_ids)).all()
        
        if not selected_layers:
            raise ValueError("No selected layers found")
        
        # Initialize pipeline executor
        executor = PipelineExecutor(job_id, db)
        
        # Execute pipeline
        results = executor.execute_pipeline(drawing, selected_layers)
        
        # Store final results as artifacts
        artifact_service = ArtifactService()
        artifacts = []
        
        # Store each pipeline step result as artifact
        for step_name, step_result in results.items():
            if step_result:
                artifact = artifact_service.create_artifact(
                    db=db,
                    job_id=job_id,
                    artifact_type=f"{step_name.lower()}_results",
                    artifact_name=f"{step_name.lower()}_results.json",
                    content=step_result,
                    metadata={"step_name": step_name, "result_type": "pipeline_step"}
                )
                if artifact:
                    artifacts.append(artifact)

        # Create dedicated wall_candidate_pairs artifact (single source of truth)
        final_artifacts = artifact_service.store_final_results(db, job_id, results)
        artifacts.extend(final_artifacts)
        
        # Update job status
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.job_metadata = {
            **(job.job_metadata or {}),
            "processing_results": results,
            "artifacts_created": len(artifacts)
        }
        db.commit()
        
        # Build a short summary for logs (do not log full results - too large)
        def _results_summary(res: Dict[str, Any]) -> Dict[str, Any]:
            out = {}
            for step_name, step_result in (res or {}).items():
                if not isinstance(step_result, dict):
                    continue
                n_pairs = len(step_result.get("wall_candidate_pairs") or [])
                stats = step_result.get("detection_stats") or {}
                out[step_name] = {"pairs": n_pairs, "unpaired": stats.get("unpaired_count"), "entities": stats.get("entities_analyzed")}
            return out

        summary = _results_summary(results)
        log_entry = JobLog(
            job_id=job.id,
            drawing_id=job.drawing_id,
            level="INFO",
            message="Job processing completed successfully",
            context={"summary": summary, "artifacts": len(artifacts)}
        )
        db.add(log_entry)
        db.commit()
        
        logger.info(
            "Job completed",
            job_id=job_id_str,
            summary=summary,
            artifacts=len(artifacts)
        )
        
        return results
        
    except Exception as e:
        # Update job status only if we successfully loaded the job
        if job is not None:
            job.status = "failed"
            job.failed_at = datetime.utcnow()
            job.error_message = str(e)
            db.commit()

            log_entry = JobLog(
                job_id=job.id,
                drawing_id=job.drawing_id,
                level="ERROR",
                message=f"Job processing failed: {str(e)}",
                context={"error_type": type(e).__name__}
            )
            db.add(log_entry)
            db.commit()

        logger.error(
            "Job processing failed",
            job_id=job_id_str,
            error=str(e)
        )

        raise
        
    finally:
        db.close()