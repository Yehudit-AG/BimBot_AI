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

    def store_final_results(self, db: Session, job_id: uuid.UUID,
                            final_results: Dict[str, Any]) -> List[Artifact]:
        """Create dedicated wall_candidate_pairs artifact from pipeline results (single source of truth)."""
        artifacts: List[Artifact] = []
        try:
            if 'LOGIC_B' in final_results:
                logic_b_data = final_results['LOGIC_B']
                if isinstance(logic_b_data, dict) and logic_b_data.get('logic_b_pairs') is not None:
                    a = self.create_artifact(
                        db=db,
                        job_id=job_id,
                        artifact_type="logic_b_pairs",
                        artifact_name="logic_b_pairs.json",
                        content={
                            'pairs': logic_b_data['logic_b_pairs'],
                            'algorithm_config': logic_b_data.get('algorithm_config', {}),
                            'totals': logic_b_data.get('totals', {}),
                        },
                        metadata={"result_type": "logic_b_pairs", "pair_count": len(logic_b_data['logic_b_pairs'])}
                    )
                    if a:
                        artifacts.append(a)
            if 'WALL_CANDIDATES_PLACEHOLDER' in final_results:
                wall_data = final_results['WALL_CANDIDATES_PLACEHOLDER']
                if isinstance(wall_data, dict) and wall_data.get('wall_candidate_pairs') is not None:
                    a = self.create_artifact(
                        db=db,
                        job_id=job_id,
                        artifact_type="wall_candidate_pairs",
                        artifact_name="wall_candidate_pairs.json",
                        content={
                            'pairs': wall_data['wall_candidate_pairs'],
                            'detection_stats': wall_data.get('detection_stats', {}),
                            'algorithm_config': wall_data.get('algorithm_config', {}),
                            'totals': wall_data.get('totals', {})
                        },
                        metadata={"result_type": "wall_candidate_pairs", "pair_count": len(wall_data['wall_candidate_pairs'])}
                    )
                    if a:
                        artifacts.append(a)
        except Exception:
            pass
        return artifacts

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