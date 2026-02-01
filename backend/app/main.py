"""
BimBot AI Wall - FastAPI Backend Application
Main application entry point with all API endpoints.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import json
import uuid
import os
from typing import List, Optional
import structlog

from .database.connection import get_db
from .models.database_models import Drawing, Layer, Job, JobStep, JobLog, Artifact, LayerSelection
from .models.api_models import (
    DrawingResponse, LayerResponse, JobResponse, JobStepResponse,
    LayerSelectionRequest, JobCreateRequest, LogResponse,
    WallCandidatePairsResponse,
)
from .adapters.drawing_adapter import DrawingAdapter
from .services.job_service import JobService
from .services.file_service import FileService
from .services.artifact_service import ArtifactService
from .config import settings

# Configure structured logging
logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="BimBot AI Wall",
    description="AutoCAD DWG export processing with layer-based geometry pipeline",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
file_service = FileService()
job_service = JobService()

@app.get("/health")
async def health_check():
    """Health check endpoint for container monitoring."""
    return {"status": "healthy", "service": "bimbot-backend"}

@app.post("/drawings", response_model=DrawingResponse)
async def upload_drawing(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload and register a DWG export JSON file."""
    request_id = str(uuid.uuid4())
    
    logger.info(
        "Drawing upload started",
        request_id=request_id,
        filename=file.filename,
        content_type=file.content_type
    )
    
    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail="Only JSON files are supported")
        
        # Read and validate JSON content
        content = await file.read()
        try:
            drawing_data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
        
        # Save file
        file_path, file_hash = await file_service.save_uploaded_file(file, content)
        
        # Process drawing with adapter
        drawing_adapter = DrawingAdapter()
        drawing_metadata, layer_inventory = drawing_adapter.process_drawing(drawing_data)
        
        # Create database records
        drawing = Drawing(
            filename=file_path,
            original_filename=file.filename,
            file_size=len(content),
            file_hash=file_hash,
            status="uploaded",
            drawing_metadata=drawing_metadata
        )
        
        try:
            db.add(drawing)
            db.flush()  # Get the drawing ID
        except IntegrityError as e:
            db.rollback()
            if "drawings_file_hash_key" in str(e):
                # Find the existing drawing with this hash
                existing_drawing = db.query(Drawing).filter(Drawing.file_hash == file_hash).first()
                if existing_drawing:
                    logger.info(
                        "Duplicate file detected, returning existing drawing",
                        request_id=request_id,
                        existing_drawing_id=str(existing_drawing.id),
                        original_filename=existing_drawing.original_filename
                    )
                    return DrawingResponse(
                        id=existing_drawing.id,
                        filename=existing_drawing.original_filename,
                        file_size=existing_drawing.file_size,
                        status=existing_drawing.status,
                        upload_timestamp=existing_drawing.created_at,
                        total_layers=db.query(Layer).filter(Layer.drawing_id == existing_drawing.id).count(),
                        total_entities=existing_drawing.drawing_metadata.get('total_entities', 0) if existing_drawing.drawing_metadata else 0,
                        metadata=existing_drawing.drawing_metadata
                    )
            raise HTTPException(
                status_code=409, 
                detail="A file with identical content has already been uploaded. The system detected this as a duplicate based on file content analysis."
            )
        
        # Create layer records
        layers = []
        for layer_info in layer_inventory:
            layer = Layer(
                drawing_id=drawing.id,
                layer_name=layer_info['layer_name'],
                has_lines=layer_info['has_lines'],
                has_polylines=layer_info['has_polylines'],
                has_blocks=layer_info['has_blocks'],
                line_count=layer_info['line_count'],
                polyline_count=layer_info['polyline_count'],
                block_count=layer_info['block_count'],
                total_entities=layer_info['total_entities']
            )
            layers.append(layer)
            db.add(layer)
        
        db.commit()
        
        logger.info(
            "Drawing upload completed",
            request_id=request_id,
            drawing_id=str(drawing.id),
            total_layers=len(layers),
            total_entities=drawing_metadata['total_entities']
        )
        
        return DrawingResponse(
            id=drawing.id,
            filename=drawing.original_filename,
            file_size=drawing.file_size,
            status=drawing.status,
            upload_timestamp=drawing.created_at,
            total_layers=len(layers),
            total_entities=drawing_metadata['total_entities'],
            metadata=drawing.drawing_metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Drawing upload failed",
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/drawings/{drawing_id}/layers", response_model=List[LayerResponse])
async def get_drawing_layers(
    drawing_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Retrieve layer inventory for a drawing."""
    request_id = str(uuid.uuid4())
    
    logger.info(
        "Layer inventory request",
        request_id=request_id,
        drawing_id=str(drawing_id)
    )
    
    # Verify drawing exists
    drawing = db.query(Drawing).filter(Drawing.id == drawing_id).first()
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    
    # Get layers with selection status
    layers = db.query(Layer).filter(Layer.drawing_id == drawing_id).all()
    
    response = []
    for layer in layers:
        # Check if layer is selected (default to False)
        selection = db.query(LayerSelection).filter(
            LayerSelection.layer_id == layer.id
        ).first()
        
        response.append(LayerResponse(
            id=layer.id,
            layer_name=layer.layer_name,
            has_lines=layer.has_lines,
            has_polylines=layer.has_polylines,
            has_blocks=layer.has_blocks,
            line_count=layer.line_count,
            polyline_count=layer.polyline_count,
            block_count=layer.block_count,
            total_entities=layer.total_entities,
            is_selected=selection.is_selected if selection else False
        ))
    
    logger.info(
        "Layer inventory retrieved",
        request_id=request_id,
        drawing_id=str(drawing_id),
        layer_count=len(response)
    )
    
    return response

@app.put("/drawings/{drawing_id}/selection")
async def update_layer_selection(
    drawing_id: uuid.UUID,
    selection_request: LayerSelectionRequest,
    db: Session = Depends(get_db)
):
    """Update layer selections for a drawing."""
    request_id = str(uuid.uuid4())
    
    logger.info(
        "Layer selection update",
        request_id=request_id,
        drawing_id=str(drawing_id),
        selected_layers=len(selection_request.selected_layer_ids)
    )
    
    # Verify drawing exists
    drawing = db.query(Drawing).filter(Drawing.id == drawing_id).first()
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    
    # Get all layers for this drawing
    layers = db.query(Layer).filter(Layer.drawing_id == drawing_id).all()
    layer_ids = {layer.id for layer in layers}
    
    # Validate selected layer IDs
    invalid_ids = set(selection_request.selected_layer_ids) - layer_ids
    if invalid_ids:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid layer IDs: {list(invalid_ids)}"
        )
    
    # Clear existing selections
    db.query(LayerSelection).filter(LayerSelection.drawing_id == drawing_id).delete()
    
    # Create new selections
    for layer in layers:
        selection = LayerSelection(
            drawing_id=drawing_id,
            layer_id=layer.id,
            is_selected=layer.id in selection_request.selected_layer_ids
        )
        db.add(selection)
    
    db.commit()
    
    logger.info(
        "Layer selection updated",
        request_id=request_id,
        drawing_id=str(drawing_id)
    )
    
    return {"message": "Layer selection updated successfully"}

@app.post("/drawings/{drawing_id}/jobs", response_model=JobResponse)
async def create_job(
    drawing_id: uuid.UUID,
    job_request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start processing pipeline for selected layers."""
    request_id = str(uuid.uuid4())
    
    logger.info(
        "Job creation request",
        request_id=request_id,
        drawing_id=str(drawing_id),
        job_type=job_request.job_type
    )
    
    # Verify drawing exists
    drawing = db.query(Drawing).filter(Drawing.id == drawing_id).first()
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    
    # Get selected layers
    selected_layers = db.query(Layer).join(LayerSelection).filter(
        LayerSelection.drawing_id == drawing_id,
        LayerSelection.is_selected == True
    ).all()
    
    if not selected_layers:
        raise HTTPException(status_code=400, detail="No layers selected for processing")
    
    # Create job record
    job = Job(
        drawing_id=drawing_id,
        job_type=job_request.job_type,
        status="pending",
        selected_layers=[str(layer.id) for layer in selected_layers],
        job_metadata=job_request.metadata or {}
    )
    
    db.add(job)
    db.commit()
    
    # Enqueue job for processing
    background_tasks.add_task(job_service.enqueue_job, job.id)
    
    logger.info(
        "Job created and enqueued",
        request_id=request_id,
        drawing_id=str(drawing_id),
        job_id=str(job.id)
    )
    
    return JobResponse(
        id=job.id,
        drawing_id=job.drawing_id,
        job_type=job.job_type,
        status=job.status,
        selected_layers=job.selected_layers,
        created_at=job.created_at,
            metadata=job.job_metadata
    )

@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get job status and progress."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get job steps
    steps = db.query(JobStep).filter(JobStep.job_id == job_id).order_by(JobStep.step_order).all()
    
    step_responses = []
    for step in steps:
        step_responses.append(JobStepResponse(
            id=step.id,
            step_name=step.step_name,
            step_order=step.step_order,
            status=step.status,
            started_at=step.started_at,
            completed_at=step.completed_at,
            duration_ms=step.duration_ms,
            metrics=step.metrics,
            error_message=step.error_message
        ))
    
    return JobResponse(
        id=job.id,
        drawing_id=job.drawing_id,
        job_type=job.job_type,
        status=job.status,
        selected_layers=job.selected_layers,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
            metadata=job.job_metadata,
        steps=step_responses
    )

@app.get("/jobs/{job_id}/logs", response_model=List[LogResponse])
async def get_job_logs(
    job_id: uuid.UUID,
    level: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get searchable log entries for a job."""
    query = db.query(JobLog).filter(JobLog.job_id == job_id)
    
    if level:
        query = query.filter(JobLog.level == level.upper())
    
    logs = query.order_by(JobLog.timestamp.desc()).limit(limit).all()
    
    return [
        LogResponse(
            id=log.id,
            job_id=log.job_id,
            step_id=log.step_id,
            level=log.level,
            message=log.message,
            context=log.context,
            timestamp=log.timestamp
        )
        for log in logs
    ]

@app.get("/jobs/{job_id}/artifacts")
async def get_job_artifacts(
    job_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get pipeline artifacts for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    artifacts = db.query(Artifact).filter(Artifact.job_id == job_id).all()
    
    return [
        {
            "id": artifact.id,
            "artifact_type": artifact.artifact_type,
            "artifact_name": artifact.artifact_name,
            "file_size": artifact.file_size,
            "content_type": artifact.content_type,
            "created_at": artifact.created_at,
            "download_url": f"/artifacts/{artifact.id}/download"
        }
        for artifact in artifacts
    ]

@app.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Download a specific artifact."""
    artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    if not artifact.file_path or not os.path.exists(artifact.file_path):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    
    return FileResponse(
        path=artifact.file_path,
        filename=artifact.artifact_name,
        media_type=artifact.content_type
    )

@app.get("/jobs/{job_id}/canvas-data")
async def get_job_canvas_data(
    job_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get canvas visualization data for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Find canvas_data.json artifact
    canvas_artifact = db.query(Artifact).filter(
        Artifact.job_id == job_id,
        Artifact.artifact_type == "canvas_data",
        Artifact.artifact_name == "canvas_data.json"
    ).first()
    
    if not canvas_artifact:
        raise HTTPException(status_code=404, detail="Canvas data not available for this job")
    
    if not canvas_artifact.file_path or not os.path.exists(canvas_artifact.file_path):
        raise HTTPException(status_code=404, detail="Canvas data file not found")
    
    try:
        # Read and return the canvas data
        with open(canvas_artifact.file_path, 'r', encoding='utf-8') as f:
            canvas_data = json.load(f)
        
        return canvas_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading canvas data: {str(e)}")

@app.get("/jobs/{job_id}/wall-candidate-pairs", response_model=WallCandidatePairsResponse)
async def get_job_wall_candidate_pairs(
    job_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get wall candidate pairs for a job; each pair includes overlap_percentage (אחוזי חפיפה)."""
    # #region agent log
    import json
    import time
    with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"B,D","location":"main.py:494","message":"Wall candidate pairs endpoint called","data":{"job_id":str(job_id)},"timestamp":int(time.time()*1000)}) + '\n')
    # #endregion
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get wall candidate pairs using artifact service
    artifact_service = ArtifactService()
    pairs_data = artifact_service.get_wall_candidate_pairs(db, job_id)
    
    # #region agent log
    with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"B,D","location":"main.py:507","message":"Artifact service result","data":{"pairs_data_found":pairs_data is not None,"pairs_data_type":type(pairs_data).__name__ if pairs_data else None},"timestamp":int(time.time()*1000)}) + '\n')
    # #endregion
    
    if not pairs_data:
        raise HTTPException(status_code=404, detail="Wall candidate pairs data not available for this job")
    
    return pairs_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)