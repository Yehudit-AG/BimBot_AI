# BimBot AI Wall - Troubleshooting Guide

This guide covers common issues and their solutions for the BimBot AI Wall system.

## 🚨 Quick Diagnostics

### System Health Check
```bash
# Check all services status
docker-compose ps

# Check service health endpoints
curl http://localhost:<backend-port>/health
curl http://localhost:<frontend-port>

# Check logs for errors
docker-compose logs --tail=50 bimbot_backend
docker-compose logs --tail=50 bimbot_worker
```

### Resource Usage
```bash
# Check container resource usage
docker stats

# Check disk space
df -h
du -sh ./artifacts/
du -sh ./uploads/
```

## 🔧 Service-Specific Issues

### Backend API Issues

#### Issue: Backend won't start
**Symptoms:**
- Container exits immediately
- "Connection refused" errors
- Health check fails

**Diagnosis:**
```bash
# Check backend logs
docker-compose logs bimbot_backend

# Check database connection
docker-compose exec bimbot_postgres psql -U bimbot_user -d bimbot_ai_wall -c "SELECT 1;"
```

**Solutions:**
1. **Database not ready:**
   ```bash
   # Wait for database to be ready
   docker-compose up bimbot_postgres
   # Wait 30 seconds, then start backend
   docker-compose up bimbot_backend
   ```

2. **Port conflicts:**
   ```bash
   # Check what's using the port
   netstat -tulpn | grep :8000
   # Kill the process or use different port
   ```

3. **Environment variables:**
   ```bash
   # Check environment file
   cat .env
   # Ensure DATABASE_URL and REDIS_URL are correct
   ```

#### Issue: File upload fails
**Symptoms:**
- "413 Request Entity Too Large"
- Upload timeout
- "Invalid file format" errors

**Solutions:**
1. **File size limit:**
   ```bash
   # Increase MAX_FILE_SIZE in .env
   MAX_FILE_SIZE=500MB
   ```

2. **Nginx proxy (if used):**
   ```nginx
   client_max_body_size 500M;
   proxy_read_timeout 300s;
   ```

3. **File format validation:**
   - Ensure file has .json extension
   - Validate JSON structure matches expected schema

### Worker Issues

#### Issue: Jobs stuck in "pending" status
**Symptoms:**
- Jobs created but never start processing
- Worker logs show no activity
- Redis queue has jobs but they're not processed

**Diagnosis:**
```bash
# Check worker logs
docker-compose logs bimbot_worker

# Check Redis connection
docker-compose exec bimbot_redis redis-cli ping

# Check job queue
docker-compose exec bimbot_redis redis-cli llen rq:queue:bimbot_jobs
```

**Solutions:**
1. **Worker not running:**
   ```bash
   # Restart worker
   docker-compose restart bimbot_worker
   
   # Check worker health
   docker-compose exec bimbot_worker python -c "import redis; r=redis.Redis(host='bimbot_redis'); print(r.ping())"
   ```

2. **Redis connection issues:**
   ```bash
   # Check Redis logs
   docker-compose logs bimbot_redis
   
   # Restart Redis
   docker-compose restart bimbot_redis
   ```

3. **Queue corruption:**
   ```bash
   # Clear failed jobs
   docker-compose exec bimbot_redis redis-cli flushall
   ```

#### Issue: Jobs fail during processing
**Symptoms:**
- Jobs start but fail at specific steps
- Error messages in job logs
- Incomplete artifacts

**Diagnosis:**
```bash
# Check specific job logs via API
curl http://localhost:<backend-port>/jobs/<job-id>/logs

# Check worker logs for detailed errors
docker-compose logs bimbot_worker | grep ERROR

# Check job artifacts
curl http://localhost:<backend-port>/jobs/<job-id>/artifacts
```

**Solutions:**
1. **Memory issues:**
   ```bash
   # Increase worker memory limit
   # In docker-compose.yml:
   deploy:
     resources:
       limits:
         memory: 4G
   ```

2. **File processing errors:**
   - Validate input JSON structure
   - Check for Unicode/encoding issues
   - Verify file permissions

3. **Database connection timeout:**
   ```bash
   # Increase database timeout in worker config
   DATABASE_POOL_TIMEOUT=30
   ```

### Database Issues

#### Issue: PostgreSQL connection failures
**Symptoms:**
- "Connection refused" errors
- "Too many connections" errors
- Slow query performance

**Diagnosis:**
```bash
# Check PostgreSQL logs
docker-compose logs bimbot_postgres

# Check connection count
docker-compose exec bimbot_postgres psql -U bimbot_user -d bimbot_ai_wall -c "SELECT count(*) FROM pg_stat_activity;"

# Check database size
docker-compose exec bimbot_postgres psql -U bimbot_user -d bimbot_ai_wall -c "SELECT pg_size_pretty(pg_database_size('bimbot_ai_wall'));"
```

**Solutions:**
1. **Connection limit reached:**
   ```sql
   -- Increase max_connections in postgresql.conf
   max_connections = 200
   ```

2. **Database corruption:**
   ```bash
   # Reset database
   docker-compose down
   docker volume rm bimbot_ai_wall_bimbot_postgres_data
   docker-compose up --build
   ```

3. **Performance issues:**
   ```sql
   -- Analyze slow queries
   SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;
   
   -- Rebuild indexes
   REINDEX DATABASE bimbot_ai_wall;
   ```

### Frontend Issues

#### Issue: Frontend won't load
**Symptoms:**
- Blank page
- "Cannot connect to server" errors
- API calls failing

**Diagnosis:**
```bash
# Check frontend logs
docker-compose logs bimbot_frontend

# Check if backend is accessible
curl http://localhost:<backend-port>/health

# Check browser console for errors
```

**Solutions:**
1. **API URL misconfiguration:**
   ```bash
   # Check REACT_APP_API_URL in frontend environment
   REACT_APP_API_URL=http://localhost:<backend-port>
   ```

2. **CORS issues:**
   ```python
   # In backend main.py, ensure CORS is configured
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:3000"],  # Add your frontend URL
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

3. **Build issues:**
   ```bash
   # Rebuild frontend
   docker-compose build bimbot_frontend
   docker-compose up bimbot_frontend
   ```

## 📊 Performance Issues

### Slow Job Processing

#### Symptoms:
- Jobs take much longer than expected
- High CPU/memory usage
- Worker timeouts

#### Diagnosis:
```bash
# Check resource usage
docker stats

# Check job step timing
curl http://localhost:<backend-port>/jobs/<job-id> | jq '.steps[].duration_ms'

# Check worker concurrency
docker-compose logs bimbot_worker | grep "worker started"
```

#### Solutions:
1. **Increase worker resources:**
   ```yaml
   # docker-compose.yml
   bimbot_worker:
     deploy:
       resources:
         limits:
           memory: 4G
           cpus: '2.0'
   ```

2. **Optimize worker concurrency:**
   ```bash
   # Adjust based on available CPU cores
   WORKER_CONCURRENCY=4
   ```

3. **Scale workers horizontally:**
   ```bash
   docker-compose up -d --scale bimbot_worker=3
   ```

### High Memory Usage

#### Symptoms:
- Out of memory errors
- Container restarts
- System becomes unresponsive

#### Solutions:
1. **Add swap space:**
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

2. **Implement memory limits:**
   ```yaml
   # docker-compose.yml
   services:
     bimbot_worker:
       deploy:
         resources:
           limits:
             memory: 2G
   ```

3. **Optimize processing:**
   - Process smaller batches
   - Implement streaming for large files
   - Clear intermediate data more frequently

## 🗄️ Data Issues

### Corrupted Artifacts

#### Symptoms:
- Download errors
- Invalid JSON in artifacts
- Missing artifact files

#### Solutions:
1. **Regenerate artifacts:**
   ```bash
   # Re-run failed job
   curl -X POST http://localhost:<backend-port>/drawings/<drawing-id>/jobs
   ```

2. **Check file permissions:**
   ```bash
   ls -la ./artifacts/
   chmod -R 755 ./artifacts/
   ```

3. **Verify disk space:**
   ```bash
   df -h
   # Clean up old artifacts if needed
   ```

### Database Inconsistencies

#### Symptoms:
- Foreign key errors
- Missing records
- Inconsistent job states

#### Solutions:
1. **Database integrity check:**
   ```sql
   -- Check for orphaned records
   SELECT * FROM job_steps WHERE job_id NOT IN (SELECT id FROM jobs);
   
   -- Check for missing references
   SELECT * FROM artifacts WHERE job_id NOT IN (SELECT id FROM jobs);
   ```

2. **Clean up orphaned data:**
   ```sql
   -- Remove orphaned job steps
   DELETE FROM job_steps WHERE job_id NOT IN (SELECT id FROM jobs);
   
   -- Remove orphaned artifacts
   DELETE FROM artifacts WHERE job_id NOT IN (SELECT id FROM jobs);
   ```

## 🔐 Security Issues

### File Upload Security

#### Issue: Malicious file uploads
**Prevention:**
```python
# Implement strict file validation
ALLOWED_EXTENSIONS = {'.json'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

def validate_file(file):
    # Check extension
    if not file.filename.lower().endswith('.json'):
        raise ValueError("Only JSON files allowed")
    
    # Check size
    if len(file.read()) > MAX_FILE_SIZE:
        raise ValueError("File too large")
    
    # Validate JSON structure
    try:
        json.loads(file.read())
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON format")
```

### Database Security

#### Issue: SQL injection attempts
**Prevention:**
- Always use SQLAlchemy ORM
- Never construct raw SQL with user input
- Use parameterized queries

```python
# Good - using ORM
job = db.query(Job).filter(Job.id == job_id).first()

# Bad - raw SQL with user input
# db.execute(f"SELECT * FROM jobs WHERE id = '{job_id}'")
```

## 🔄 Recovery Procedures

### Complete System Recovery

#### When to use:
- Multiple services failing
- Database corruption
- System-wide issues

#### Steps:
1. **Stop all services:**
   ```bash
   docker-compose down
   ```

2. **Backup current data:**
   ```bash
   cp -r ./uploads ./uploads.backup
   cp -r ./artifacts ./artifacts.backup
   ```

3. **Reset volumes (if needed):**
   ```bash
   docker-compose down -v
   ```

4. **Rebuild and restart:**
   ```bash
   docker-compose build --no-cache
   docker-compose up -d
   ```

5. **Restore data:**
   ```bash
   cp -r ./uploads.backup/* ./uploads/
   cp -r ./artifacts.backup/* ./artifacts/
   ```

### Partial Recovery

#### Database only:
```bash
# Stop services that use database
docker-compose stop bimbot_backend bimbot_worker

# Reset database
docker-compose down bimbot_postgres
docker volume rm bimbot_ai_wall_bimbot_postgres_data
docker-compose up -d bimbot_postgres

# Wait for database to be ready, then start other services
sleep 30
docker-compose up -d bimbot_backend bimbot_worker
```

#### Worker only:
```bash
# Clear Redis queue
docker-compose exec bimbot_redis redis-cli flushall

# Restart worker
docker-compose restart bimbot_worker
```

## 📞 Getting Help

### Log Collection
Before seeking help, collect relevant logs:

```bash
#!/bin/bash
# collect_logs.sh
mkdir -p debug_logs
docker-compose logs bimbot_backend > debug_logs/backend.log
docker-compose logs bimbot_worker > debug_logs/worker.log
docker-compose logs bimbot_postgres > debug_logs/postgres.log
docker-compose logs bimbot_redis > debug_logs/redis.log
docker-compose logs bimbot_frontend > debug_logs/frontend.log
docker-compose ps > debug_logs/services_status.txt
docker stats --no-stream > debug_logs/resource_usage.txt
tar -czf debug_logs.tar.gz debug_logs/
```

### System Information
```bash
# System info
uname -a > system_info.txt
docker --version >> system_info.txt
docker-compose --version >> system_info.txt
df -h >> system_info.txt
free -h >> system_info.txt
```

### Common Error Patterns

#### Pattern: "Connection refused"
- Check if service is running
- Verify port configuration
- Check firewall rules

#### Pattern: "Permission denied"
- Check file permissions
- Verify user/group ownership
- Check Docker socket permissions

#### Pattern: "Out of memory"
- Check available memory
- Review container limits
- Consider adding swap

#### Pattern: "Timeout"
- Increase timeout values
- Check network connectivity
- Review resource constraints

---

This troubleshooting guide covers the most common issues you may encounter. For complex issues, collect logs and system information before investigating further.