# BimBot AI Wall - Deployment Guide

This guide covers deployment scenarios from development to production.

## 🏗️ Deployment Architecture

### Development Environment
- Single machine deployment
- Dynamic port allocation
- File-based artifact storage
- Basic logging to stdout

### Production Environment
- Multi-container orchestration
- Load balancing for API services
- Persistent volume storage
- Centralized logging and monitoring

## 🚀 Quick Deployment

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- Minimum 4GB RAM
- 10GB available disk space

### 1. Clone and Configure
```bash
git clone <repository>
cd BimBot_AI_Wall

# Copy and customize environment
cp env.example .env
```

### 2. Environment Configuration

#### Basic Configuration (.env)
```bash
# Database
POSTGRES_DB=bimbot_ai_wall
POSTGRES_USER=bimbot_user
POSTGRES_PASSWORD=secure_password_here

# Redis
REDIS_URL=redis://bimbot_redis:6379/0

# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
SECRET_KEY=your-very-secure-secret-key-here

# File Storage
UPLOAD_DIR=/app/uploads
ARTIFACTS_DIR=/app/artifacts
MAX_FILE_SIZE=100MB

# Worker
WORKER_CONCURRENCY=4
JOB_TIMEOUT=3600
```

### 3. Deploy Services
```bash
# Production deployment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Development deployment
docker-compose up -d
```

## 🔧 Production Configuration

### docker-compose.prod.yml
```yaml
version: '3.8'

services:
  bimbot_postgres:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    restart: unless-stopped
    
  bimbot_redis:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
    restart: unless-stopped
    
  bimbot_backend:
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - WORKERS=4
    
  bimbot_worker:
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 1G
          cpus: '1.0'
    restart: unless-stopped
    environment:
      - WORKER_CONCURRENCY=6
      - JOB_TIMEOUT=7200
    
  bimbot_frontend:
    restart: unless-stopped
    environment:
      - NODE_ENV=production

  # Load balancer (optional)
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl/certs
    depends_on:
      - bimbot_backend
      - bimbot_frontend
    restart: unless-stopped
```

### Nginx Configuration (nginx.conf)
```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server bimbot_backend:8000;
    }
    
    upstream frontend {
        server bimbot_frontend:3000;
    }
    
    server {
        listen 80;
        server_name your-domain.com;
        
        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }
    
    server {
        listen 443 ssl;
        server_name your-domain.com;
        
        ssl_certificate /etc/ssl/certs/cert.pem;
        ssl_certificate_key /etc/ssl/certs/key.pem;
        
        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Backend API
        location /api/ {
            proxy_pass http://backend/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # Handle large file uploads
            client_max_body_size 500M;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }
    }
}
```

## 🗄️ Persistent Storage

### Volume Configuration
```yaml
volumes:
  bimbot_postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/bimbot/postgres_data
      
  bimbot_redis_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/bimbot/redis_data
      
  bimbot_uploads:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/bimbot/uploads
      
  bimbot_artifacts:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/bimbot/artifacts
```

### Directory Setup
```bash
# Create persistent directories
sudo mkdir -p /opt/bimbot/{postgres_data,redis_data,uploads,artifacts}
sudo chown -R 1000:1000 /opt/bimbot/
sudo chmod -R 755 /opt/bimbot/
```

## 🔐 Security Configuration

### SSL/TLS Setup
```bash
# Generate self-signed certificate (development)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem

# Or use Let's Encrypt (production)
certbot certonly --webroot -w /var/www/html -d your-domain.com
```

### Environment Security
```bash
# Generate secure secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate secure database password
openssl rand -base64 32
```

### Firewall Configuration
```bash
# Allow only necessary ports
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable
```

## 📊 Monitoring & Logging

### Centralized Logging with ELK Stack
```yaml
# docker-compose.monitoring.yml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.5.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    
  logstash:
    image: docker.elastic.co/logstash/logstash:8.5.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    depends_on:
      - elasticsearch
    
  kibana:
    image: docker.elastic.co/kibana/kibana:8.5.0
    ports:
      - "5601:5601"
    depends_on:
      - elasticsearch
```

### Prometheus Monitoring
```yaml
# docker-compose.monitoring.yml (continued)
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    
  grafana:
    image: grafana/grafana
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
```

## 🔄 Backup & Recovery

### Database Backup
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/bimbot/backups"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker-compose exec -T bimbot_postgres pg_dump \
  -U bimbot_user bimbot_ai_wall > $BACKUP_DIR/postgres_$DATE.sql

# Backup Redis
docker-compose exec -T bimbot_redis redis-cli BGSAVE
docker cp bimbot_redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# Backup artifacts
tar -czf $BACKUP_DIR/artifacts_$DATE.tar.gz /opt/bimbot/artifacts/

# Cleanup old backups (keep last 7 days)
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.rdb" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

### Automated Backup with Cron
```bash
# Add to crontab
0 2 * * * /opt/bimbot/backup.sh >> /var/log/bimbot_backup.log 2>&1
```

### Recovery Process
```bash
# Stop services
docker-compose down

# Restore PostgreSQL
docker-compose up -d bimbot_postgres
docker-compose exec -T bimbot_postgres psql -U bimbot_user -d bimbot_ai_wall < backup.sql

# Restore Redis
docker cp backup.rdb bimbot_redis:/data/dump.rdb
docker-compose restart bimbot_redis

# Restore artifacts
tar -xzf artifacts_backup.tar.gz -C /

# Start all services
docker-compose up -d
```

## 🚀 Scaling & Performance

### Horizontal Scaling
```bash
# Scale backend API
docker-compose up -d --scale bimbot_backend=3

# Scale workers
docker-compose up -d --scale bimbot_worker=5

# Scale with resource limits
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Performance Tuning

#### PostgreSQL Optimization
```sql
-- postgresql.conf optimizations
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
```

#### Redis Optimization
```conf
# redis.conf optimizations
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

#### Worker Optimization
```bash
# Environment variables for high-performance workers
WORKER_CONCURRENCY=8
JOB_TIMEOUT=7200
REDIS_CONNECTION_POOL_SIZE=20
DATABASE_POOL_SIZE=20
```

## 🔍 Health Checks & Monitoring

### Health Check Endpoints
```bash
# Check all services
curl http://localhost/api/health
curl http://localhost:5432  # PostgreSQL
curl http://localhost:6379  # Redis
```

### Monitoring Script
```bash
#!/bin/bash
# monitor.sh
SERVICES=("bimbot_backend" "bimbot_worker" "bimbot_frontend" "bimbot_postgres" "bimbot_redis")

for service in "${SERVICES[@]}"; do
    if docker-compose ps $service | grep -q "Up"; then
        echo "✅ $service is running"
    else
        echo "❌ $service is down"
        # Optional: restart service
        # docker-compose restart $service
    fi
done

# Check disk space
df -h /opt/bimbot/
```

## 🐛 Troubleshooting

### Common Deployment Issues

#### Port Conflicts
```bash
# Check port usage
netstat -tulpn | grep :80
netstat -tulpn | grep :443

# Use different ports if needed
docker-compose -f docker-compose.yml -f docker-compose.custom-ports.yml up -d
```

#### Memory Issues
```bash
# Check memory usage
docker stats

# Increase swap if needed
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

#### Database Connection Issues
```bash
# Check PostgreSQL logs
docker-compose logs bimbot_postgres

# Test connection
docker-compose exec bimbot_postgres psql -U bimbot_user -d bimbot_ai_wall -c "SELECT 1;"
```

### Performance Issues

#### Slow Job Processing
1. Check worker logs for bottlenecks
2. Increase worker concurrency
3. Scale worker instances
4. Optimize database queries

#### High Memory Usage
1. Monitor container memory usage
2. Adjust worker concurrency
3. Implement memory limits
4. Consider worker restart policies

## 📋 Deployment Checklist

### Pre-Deployment
- [ ] Environment variables configured
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Backup strategy implemented
- [ ] Monitoring setup complete

### Deployment
- [ ] Services start successfully
- [ ] Health checks pass
- [ ] Database migrations applied
- [ ] Frontend accessible
- [ ] API endpoints responding

### Post-Deployment
- [ ] Upload test file
- [ ] Process test job
- [ ] Verify artifacts generated
- [ ] Check logs for errors
- [ ] Monitor resource usage

### Maintenance
- [ ] Regular backups scheduled
- [ ] Log rotation configured
- [ ] Update strategy defined
- [ ] Monitoring alerts configured
- [ ] Documentation updated

---

This deployment guide provides comprehensive coverage for deploying BimBot AI Wall in various environments, from development to production scale.