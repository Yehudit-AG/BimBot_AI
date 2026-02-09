"""
Pipeline executor for the 5-stage geometry processing pipeline.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
import structlog

from ..database_models import Job, JobStep, JobLog, Artifact, Drawing, Layer, DrawingWindowDoorBlocks
from .processors.extract_processor import ExtractProcessor
from .processors.normalize_processor import NormalizeProcessor
from .processors.clean_dedup_processor import CleanDedupProcessor
from .processors.parallel_naive_processor import ParallelNaiveProcessor
from .processors.logic_b_processor import LogicBProcessor
from .processors.logic_c_processor import LogicCProcessor
from .processors.containment_pruning_processor import LogicDProcessor
from .processors.logic_e_adjacent_merge_processor import LogicEProcessor
from .processors.wall_candidates_processor import WallCandidatesProcessor

logger = structlog.get_logger()

class PipelineExecutor:
    """Executes the geometry processing pipeline (wall candidate detection)."""
    
    PIPELINE_STEPS = [
        ("EXTRACT", ExtractProcessor),
        ("NORMALIZE", NormalizeProcessor),
        ("CLEAN_DEDUP", CleanDedupProcessor),
        ("PARALLEL_NAIVE", ParallelNaiveProcessor),
        ("LOGIC_B", LogicBProcessor),
        ("LOGIC_C", LogicCProcessor),
        ("LOGIC_D", LogicDProcessor),
        ("LOGIC_E", LogicEProcessor),
        ("WALL_CANDIDATES_PLACEHOLDER", WallCandidatesProcessor),
    ]
    
    def __init__(self, job_id: uuid.UUID, db: Session):
        self.job_id = job_id
        self.db = db
        self.processors = {}
        
        # Initialize processors
        for step_name, processor_class in self.PIPELINE_STEPS:
            self.processors[step_name] = processor_class(job_id, db)
    
    def execute_pipeline(self, drawing: Drawing, selected_layers: List[Layer]) -> Dict[str, Any]:
        """
        Execute the complete pipeline for selected layers.
        
        Args:
            drawing: Drawing database record
            selected_layers: List of selected layer records
            
        Returns:
            Pipeline execution results
        """
        logger.info(
            "Pipeline execution started",
            job_id=str(self.job_id),
            drawing_id=str(drawing.id),
            selected_layers=[layer.layer_name for layer in selected_layers]
        )
        
        # Create job steps
        self._create_job_steps()
        
        # Load drawing data
        drawing_data = self._load_drawing_data(drawing)
        
        # Load collected window/door blocks for this drawing (if any)
        window_door_record = self.db.query(DrawingWindowDoorBlocks).filter(
            DrawingWindowDoorBlocks.drawing_id == drawing.id
        ).first()
        window_door_blocks = list(window_door_record.blocks) if window_door_record and window_door_record.blocks else []
        
        # Initialize pipeline data
        pipeline_data = {
            'drawing': drawing_data,
            'selected_layers': selected_layers,
            'layer_names': [layer.layer_name for layer in selected_layers],
            'window_door_blocks': window_door_blocks
        }
        
        results = {}
        
        # Execute each pipeline step
        for step_order, (step_name, _) in enumerate(self.PIPELINE_STEPS, 1):
            try:
                # #region agent log
                import json
                import time
                with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"C,E","location":"pipeline_executor.py:76","message":"Executing pipeline step","data":{"step_name":step_name,"step_order":step_order},"timestamp":int(time.time()*1000)}) + '\n')
                # #endregion
                
                step_result = self._execute_step(
                    step_name, 
                    step_order, 
                    pipeline_data
                )
                results[step_name] = step_result
                
                # #region agent log
                with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    has_pairs = 'wall_candidate_pairs' in step_result if isinstance(step_result, dict) else False
                    f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"C,E","location":"pipeline_executor.py:85","message":"Pipeline step completed","data":{"step_name":step_name,"step_result_type":type(step_result).__name__,"has_wall_candidate_pairs":has_pairs},"timestamp":int(time.time()*1000)}) + '\n')
                # #endregion
                
                # Update pipeline data with step results
                pipeline_data[f'{step_name.lower()}_results'] = step_result
                
            except Exception as e:
                logger.error(
                    "Pipeline step failed",
                    job_id=str(self.job_id),
                    step_name=step_name,
                    error=str(e)
                )
                
                # Mark step as failed
                self._mark_step_failed(step_name, str(e))
                
                # Stop pipeline execution
                raise
        
        logger.info(
            "Pipeline execution completed",
            job_id=str(self.job_id),
            results_summary={
                step: len(result.get('entities', [])) if isinstance(result, dict) else str(result)
                for step, result in results.items()
            }
        )
        
        return results
    
    def _create_job_steps(self):
        """Create job step records in database."""
        for step_order, (step_name, _) in enumerate(self.PIPELINE_STEPS, 1):
            step = JobStep(
                job_id=self.job_id,
                step_name=step_name,
                step_order=step_order,
                status='pending'
            )
            self.db.add(step)
        
        self.db.commit()
    
    def _load_drawing_data(self, drawing: Drawing) -> Dict[str, Any]:
        """Load drawing JSON data from file."""
        try:
            with open(drawing.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(
                "Failed to load drawing data",
                job_id=str(self.job_id),
                drawing_file=drawing.filename,
                error=str(e)
            )
            raise
    
    def _execute_step(self, step_name: str, step_order: int, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single pipeline step."""
        # Get step record
        step = self.db.query(JobStep).filter(
            JobStep.job_id == self.job_id,
            JobStep.step_name == step_name
        ).first()
        
        if not step:
            raise ValueError(f"Step {step_name} not found")
        
        # Mark step as running
        step.status = 'running'
        step.started_at = datetime.utcnow()
        self.db.commit()
        
        # Log step start
        log_entry = JobLog(
            job_id=self.job_id,
            step_id=step.id,
            level="INFO",
            message=f"Step {step_name} started",
            context={"step_order": step_order}
        )
        self.db.add(log_entry)
        self.db.commit()
        
        start_time = time.time()
        
        try:
            # Execute processor
            processor = self.processors[step_name]
            result = processor.process(pipeline_data)
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Mark step as completed
            step.status = 'completed'
            step.completed_at = datetime.utcnow()
            step.duration_ms = duration_ms
            step.output_data = result if isinstance(result, dict) else {"result": str(result)}
            step.metrics = processor.get_metrics()
            self.db.commit()
            
            # Log step completion
            log_entry = JobLog(
                job_id=self.job_id,
                step_id=step.id,
                level="INFO",
                message=f"Step {step_name} completed successfully",
                context={
                    "duration_ms": duration_ms,
                    "metrics": processor.get_metrics()
                }
            )
            self.db.add(log_entry)
            self.db.commit()
            
            logger.info(
                "Pipeline step completed",
                job_id=str(self.job_id),
                step_name=step_name,
                duration_ms=duration_ms,
                metrics=processor.get_metrics()
            )
            
            return result
            
        except Exception as e:
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Mark step as failed
            step.status = 'failed'
            step.failed_at = datetime.utcnow()
            step.duration_ms = duration_ms
            step.error_message = str(e)
            self.db.commit()
            
            # Log step failure
            log_entry = JobLog(
                job_id=self.job_id,
                step_id=step.id,
                level="ERROR",
                message=f"Step {step_name} failed: {str(e)}",
                context={
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__
                }
            )
            self.db.add(log_entry)
            self.db.commit()
            
            raise
    
    def _mark_step_failed(self, step_name: str, error_message: str):
        """Mark a step as failed."""
        step = self.db.query(JobStep).filter(
            JobStep.job_id == self.job_id,
            JobStep.step_name == step_name
        ).first()
        
        if step:
            step.status = 'failed'
            step.failed_at = datetime.utcnow()
            step.error_message = error_message
            self.db.commit()