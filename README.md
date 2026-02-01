# BimBot AI Wall - Phase 1

A production-ready Dockerized system for processing AutoCAD DWG exports with layer-based geometry processing, featuring a 4-service architecture with full observability and deterministic pipeline execution.

## 🏗️ Architecture Overview

```mermaid
graph TB
    subgraph "Frontend Service"
        UI[React UI]
        LayerMgmt[Layer Management]
        JobDash[Job Dashboard]
    end
    
    subgraph "Backend API Service"
        API[FastAPI Server]
        FileUpload[File Upload]
        JobOrch[Job Orchestration]
    end
    
    subgraph "Worker Service"
        Worker[RQ Worker]
        Pipeline[5-Stage Pipeline]
        Artifacts[Artifact Storage]
    end
    
    subgraph "Database Services"
        PostgreSQL[(PostgreSQL)]
        Redis[(Redis Queue)]
    end
    
    UI --> API
    API --> PostgreSQL
    API --> Redis
    Worker --> Redis
    Worker --> PostgreSQL
    Pipeline --> Artifacts
```

### Service Components

- **Backend API**: FastAPI server for validation, persistence, and orchestration
- **Worker**: Asynchronous job execution with 5-stage geometry processing pipeline
- **Frontend**: React-based UI for layer management and job monitoring
- **Database**: PostgreSQL for persistence and Redis for job queuing

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- At least 4GB RAM available
- 2GB free disk space

### 1. Setup Environment
```bash
cd BimBot_AI_Wall
cp env.example .env
# Edit .env with your configuration if needed
```

### 2. Build and Run
```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up --build -d
```

### 3. Access Services
Check dynamically assigned ports:
```bash
docker-compose ps
```

- **Frontend**: `http://localhost:<frontend-port>`
- **Backend API**: `http://localhost:<backend-port>`
- **API Documentation**: `http://localhost:<backend-port>/docs`

## 📊 Data Flow & Processing Pipeline

### 1. Upload & Inventory
1. User uploads DWG export JSON file via frontend
2. Backend validates and parses file structure
3. System builds persistent layer inventory with entity counts
4. Frontend displays layers with toggles (no client-side geometry parsing)

### 2. Layer Selection & Job Creation
1. User selects layers for processing
2. Backend creates job record and enqueues for processing
3. Worker picks up job from Redis queue

### 3. 5-Stage Processing Pipeline
```
EXTRACT → NORMALIZE → CLEAN_DEDUP → PARALLEL_NAIVE → WALL_CANDIDATES_PLACEHOLDER
```

#### Pipeline Details:
- **EXTRACT**: Parse selected layers from JSON, extract entities by type
- **NORMALIZE**: Apply coordinate normalization (ε=1e-6) and validation
- **CLEAN_DEDUP**: Remove duplicates using deterministic hash-based comparison
- **PARALLEL_NAIVE**: Prepare entities for parallel processing, basic geometric analysis
- **WALL_CANDIDATES_PLACEHOLDER**: Mock wall detection algorithm (Phase 1 scope)

### 4. Results & Artifacts
- All intermediate results stored as downloadable artifacts
- Full traceability with correlation IDs
- Step-level metrics and timing data
- Structured JSON logging for debugging

## 🔧 Development Guide

### Service Architecture

#### Backend API (`/backend`)
- **Framework**: FastAPI with async support
- **Database**: SQLAlchemy ORM with PostgreSQL
- **Key Features**: File upload, layer inventory, job orchestration
- **Endpoints**: `/drawings`, `/jobs`, `/artifacts`, `/health`

#### Worker (`/worker`)
- **Framework**: RQ (Redis Queue) for job processing
- **Pipeline**: 5-stage deterministic geometry processing
- **Key Features**: Idempotent steps, artifact generation, metrics collection

#### Frontend (`/frontend`)
- **Framework**: React with React Query for state management
- **Key Features**: File upload, layer selection, job monitoring
- **Pages**: Upload, Layer Management, Job Dashboard

### Local Development

#### Running Individual Services
```bash
# Backend only
cd backend && python -m uvicorn app.main:app --reload

# Worker only
cd worker && python worker/main.py

# Frontend only
cd frontend && npm start
```

#### Database Operations
```bash
# Access PostgreSQL
docker-compose exec bimbot_postgres psql -U bimbot_user -d bimbot_ai_wall

# View Redis queue
docker-compose exec bimbot_redis redis-cli
```

### Environment Configuration

Key environment variables in `.env`:
```bash
# Database
DATABASE_URL=postgresql://bimbot_user:bimbot_password@bimbot_postgres:5432/bimbot_ai_wall

# Redis
REDIS_URL=redis://bimbot_redis:6379/0

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO

# File Storage
UPLOAD_DIR=/app/uploads
ARTIFACTS_DIR=/app/artifacts
MAX_FILE_SIZE=100MB
```

## 📈 Observability & Monitoring

### Logging
- **Structured JSON logging** with correlation IDs
- **Database persistence** of job logs
- **API endpoint** for searchable log retrieval
- **Log levels**: DEBUG, INFO, WARNING, ERROR

### Metrics
- **Step-level timing** and performance metrics
- **Entity processing statistics** (processed, failed, duplicated)
- **Geometry analysis metrics** (lines, polylines, blocks)
- **System resource monitoring** (CPU, memory, disk)

### Artifacts
- **Intermediate results** stored as downloadable files
- **Step outputs** preserved for debugging
- **Final results** with summary reports
- **Automatic cleanup** on job deletion

### Health Checks
All services include health endpoints:
```bash
# Check service health
curl http://localhost:<port>/health

# Monitor with Docker
docker-compose ps
```

## 🐛 Troubleshooting

### Common Issues

#### Port Conflicts
The system uses dynamic port allocation to avoid conflicts:
```bash
# Check assigned ports
docker-compose ps

# If you need specific ports, modify docker-compose.yml
```

#### Database Connection Issues
```bash
# Reset database completely
docker-compose down -v
docker-compose up --build

# Check database logs
docker-compose logs bimbot_postgres
```

#### Worker Not Processing Jobs
```bash
# Check worker logs
docker-compose logs -f bimbot_worker

# Check Redis connection
docker-compose exec bimbot_redis redis-cli ping

# Restart worker
docker-compose restart bimbot_worker
```

#### Frontend API Connection Issues
```bash
# Check backend logs
docker-compose logs -f bimbot_backend

# Verify API is accessible
curl http://localhost:<backend-port>/health

# Check CORS configuration in backend
```

### Performance Tuning

#### For Large Files (>50MB)
```bash
# Increase worker timeout
WORKER_TIMEOUT=7200  # 2 hours

# Increase max file size
MAX_FILE_SIZE=500MB

# Increase worker concurrency
WORKER_CONCURRENCY=8
```

#### For High Load
```bash
# Scale workers
docker-compose up --scale bimbot_worker=3

# Monitor resource usage
docker stats
```

### Debugging Pipeline Issues

#### Step Failures
1. Check job logs via API: `GET /jobs/{id}/logs`
2. Download step artifacts: `GET /jobs/{id}/artifacts`
3. Review step metrics in job details
4. Check worker logs for detailed error traces

#### Data Quality Issues
1. Review layer inventory for unexpected entity counts
2. Check normalization step metrics for validation errors
3. Examine deduplication statistics
4. Validate input JSON structure

## 🔒 Security Considerations

### File Upload Security
- File type validation (JSON only)
- File size limits (configurable)
- Content validation before processing
- Isolated file storage

### Database Security
- Parameterized queries (SQLAlchemy ORM)
- Connection pooling with timeouts
- Isolated database containers

### Network Security
- Internal Docker network isolation
- CORS configuration for frontend
- Health check endpoints only expose status

## 📋 API Reference

### Core Endpoints

#### Drawings
- `POST /drawings` - Upload DWG export JSON
- `GET /drawings/{id}/layers` - Get layer inventory
- `PUT /drawings/{id}/selection` - Update layer selection

#### Jobs
- `POST /drawings/{id}/jobs` - Create processing job
- `GET /jobs/{id}` - Get job status and progress
- `GET /jobs/{id}/logs` - Get job logs (filterable)
- `GET /jobs/{id}/artifacts` - List job artifacts

#### Artifacts
- `GET /artifacts/{id}/download` - Download artifact file

#### System
- `GET /health` - Service health check

### Response Formats

All API responses use consistent JSON structure:
```json
{
  "id": "uuid",
  "status": "completed|running|failed|pending",
  "created_at": "2024-01-01T00:00:00Z",
  "metadata": {...}
}
```

## 🧪 Testing

### Manual Testing Flow
1. Upload sample JSON file
2. Verify layer inventory display
3. Select layers and start job
4. Monitor job progress in real-time
5. Download and verify artifacts
6. Check logs for any errors

### Sample Test Data
Use the provided sample file:
`ASH-AG-PLP-T3-F6-Standart - Floor Plan - קומה 6_export.json`

Expected results:
- Multiple layers with Hebrew names
- Mix of lines, polylines, and blocks
- Successful processing through all pipeline steps

## 🔄 Maintenance

### Regular Tasks
```bash
# Update containers
docker-compose pull
docker-compose up --build

# Clean up old artifacts (manual)
# Artifacts are stored in ./artifacts/ directory

# Database maintenance
docker-compose exec bimbot_postgres pg_dump -U bimbot_user bimbot_ai_wall > backup.sql
```

### Monitoring
- Check service health regularly
- Monitor disk space for artifacts
- Review error logs weekly
- Validate processing accuracy with sample files

## 🚀 Production Deployment

### Recommended Configuration
```yaml
# docker-compose.prod.yml
services:
  bimbot_postgres:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
  
  bimbot_backend:
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

### Environment Variables for Production
```bash
ENVIRONMENT=production
LOG_LEVEL=INFO
SECRET_KEY=<strong-random-key>
DATABASE_URL=<production-db-url>
REDIS_URL=<production-redis-url>
```

---

## 📞 Support

For issues and questions:
1. Check this documentation
2. Review service logs
3. Examine job artifacts and metrics
4. Verify input data format

This system provides a solid foundation for Phase 1 while maintaining extensibility for advanced wall detection algorithms in future phases.