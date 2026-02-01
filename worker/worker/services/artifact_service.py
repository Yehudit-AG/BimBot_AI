"""
Artifact service for worker (simplified version of backend service).
"""

import os
import json
import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from ..database_models import Artifact
from ..config import settings
from ..config import settings

class ArtifactService:
    """Service for managing job artifacts and intermediate results."""
    
    def __init__(self):
        self.artifacts_dir = settings.artifacts_dir
        os.makedirs(self.artifacts_dir, exist_ok=True)
    
    def create_artifact(self, db: Session, job_id: uuid.UUID, 
                       artifact_type: str, artifact_name: str,
                       content: Any, content_type: str = "application/json",
                       step_id: Optional[uuid.UUID] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> Optional[Artifact]:
        """Create and store a job artifact."""
        try:
            # Create job-specific directory
            job_dir = os.path.join(self.artifacts_dir, str(job_id))
            os.makedirs(job_dir, exist_ok=True)
            
            # Generate file path
            safe_name = self._sanitize_filename(artifact_name)
            file_path = os.path.join(job_dir, safe_name)
            
            # Serialize content based on type
            if content_type == "application/json":
                content_bytes = json.dumps(content, indent=2, ensure_ascii=False).encode('utf-8')
            elif isinstance(content, str):
                content_bytes = content.encode('utf-8')
            elif isinstance(content, bytes):
                content_bytes = content
            else:
                # Try to serialize as JSON
                content_bytes = json.dumps(content, indent=2, default=str).encode('utf-8')
            
            # Write file
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
            
            # Create database record
            artifact = Artifact(
                job_id=job_id,
                step_id=step_id,
                artifact_type=artifact_type,
                artifact_name=artifact_name,
                file_path=file_path,
                file_size=len(content_bytes),
                content_type=content_type,
                artifact_metadata=metadata or {}
            )
            
            db.add(artifact)
            db.commit()
            
            return artifact
            
        except Exception:
            return None  # Don't let artifact failures break the application
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:190] + ext
        
        return filename