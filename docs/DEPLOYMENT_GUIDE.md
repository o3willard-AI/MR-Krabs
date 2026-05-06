# Production Deployment Guide

**MR-Krabs MCP Server - Native Python Deployment**

---

## 🎯 Quick Start (1-minute deployment)

```bash
# Clone the repository
git clone https://github.com/your-org/mrkrabs.git
cd mrkrabs

# Install dependencies
pip install fastapi uvicorn pydantic structlog requests crewai

# Start the server
python -m uvicorn src.mcp.server:create_app --host 0.0.0.0 --port 8000
```

**That's it!** Your MR-Krabs server is now running at `http://localhost:8000`

---

## 📋 Prerequisites

### Required Software

- **Python 3.10+** (3.12 recommended)
- **pip** or **poetry** for package management
- **curl** for testing (optional)

### Verify Python Installation

```bash
python3 --version  # Should show 3.10 or higher
pip3 --version     # pip should be available
```

---

## 🚀 Deployment Options

### Option 1: Development Mode (Fastest)

Perfect for testing, local development, and rapid iteration.

```bash
# Activate virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn pydantic structlog requests crewai pytest

# Run with auto-reload
uvicorn src.mcp.server:create_app --host 127.0.0.1 --port 8000 --reload
```

**Features:**
- ✅ Auto-reload on code changes
- ✅ Detailed logging
- ✅ Error traces in responses
- ⚠️ Not suitable for production (single worker)

### Option 2: Production Mode (Recommended)

Use the provided deployment script for reliable production deployments.

```bash
# Make script executable
chmod +x scripts/deploy.sh

# Deploy to production
./scripts/deploy.sh deploy prod

# Check status
./scripts/deploy.sh status

# View logs
./scripts/deploy.sh logs
```

**Features:**
- ✅ Multiple worker processes (4 by default)
- ✅ Graceful shutdown handling
- ✅ Background process management
- ✅ Logging to files
- ✅ Health check monitoring

### Option 3: Manual Production Deployment

For more control over the deployment process.

```bash
# Install production dependencies
pip install fastapi uvicorn pydantic structlog requests crewai

# Set environment variables
export ENVIRONMENT="production"
export LOG_LEVEL="warning"
export HOST="0.0.0.0"
export PORT="8000"

# Start server with multiple workers (nohup for background)
nohup uvicorn src.mcp.server:create_app \
  --host $HOST \
  --port $PORT \
  --workers 4 \
  --access-log \
  --log-level $LOG_LEVEL \
  > server.log 2>&1 &

echo $! > server.pid
```

---

## 🧪 Testing Your Deployment

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "MR-Krabs MCP Server"
}
```

### Test All Endpoints

```bash
# Session management
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_session_init \
  -H "Content-Type: application/json" \
  -d '{"budget_limit": 50.0, "enforcement_mode": "notify_only"}'

# Analytics summary
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_analytics_summary \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}'

# Cost trends with ASCII chart
curl -X POST http://localhost:8000/tools/mcp_mrkrabs_cost_trends \
  -H "Content-Type: application/json" \
  -d '{"period_days": 7}' | jq -r '.data.ascii_chart'
```

### Run Full Test Suite

```bash
# Unit tests
pytest tests/ -v --timeout=30

# Integration tests (requires running server)
MCP_TEST_URL="http://localhost:8000" pytest tests/integration_test.py -v --timeout=30
```

---

## 🔧 Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address (use `127.0.0.1` for local only) |
| `PORT` | `8000` | Server port |
| `WORKERS` | `4` | Number of worker processes (prod only) |
| `LOG_LEVEL` | `info` | Logging level: debug, info, warning, error |
| `ENVIRONMENT` | `development` | deployment environment identifier |
| `MCP_API_KEY` | *(none)* | API key for authentication (optional) |

### FastAPI Configuration

The server is highly configurable via uvicorn arguments:

```bash
uvicorn src.mcp.server:create_app \
  --host 0.0.0.0 \              # Bind to all interfaces
  --port 8000 \                 # Port number
  --workers 4 \                 # Number of workers (prod)
  --reload \                    # Auto-reload (dev only)
  --log-level info \            # Log level
  --access-log \                # Show access logs
  --timeout-keep-alive 65 \     # HTTP keep-alive timeout
  --backlog 2048 \              # Connection backlog
  --limit-concurrency 100       # Max concurrent requests
```

---

## 🐳 Docker (Coming in Phase 5)

Docker support will be added in Phase 5. For now, use native Python deployment as shown above.

**Preview - Future Docker Command:**
```bash
docker build -t mrkrabs:latest .
docker run -p 8000:8000 -e HOST=0.0.0.0 mrkrabs:latest
```

---

## 📊 Monitoring and Logs

### View Live Logs

```bash
# Using the deploy script
./scripts/deploy.sh logs

# Or tail the log file directly
tail -f /home/sblanken/working/code/MR-Krabs/scripts/deploy.log
```

### Log Format

Logs include timestamp, level, and message:

```
2026-05-05 14:32:15 - INFO - Request: POST /tools/mcp_mrkrabs_analytics_summary
2026-05-05 14:32:15.123 - INFO - 127.0.0.1:45678 - "POST /health HTTP/1.1" 200 OK
2026-05-05 14:32:16 - WARNING - Budget warning for session abc123 (85% used)
```

### Error Logs

Check error logs separately:

```bash
grep "ERROR\|Exception" /home/sblanken/working/code/MR-Krabs/scripts/deploy.log
```

---

## 🔒 Security Considerations

### Current State (Phase 4)

- **Authentication:** Optional (disabled by default)
- **Authorization:** Not implemented
- **Transport:** HTTP (upgrade to HTTPS in Phase 5)

### Best Practices for Production

1. **Run behind a reverse proxy** (nginx, traefik):
   ```nginx
   # Example nginx config
   server {
       listen 80;
       server_name mrkrabs.example.com;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

2. **Bind to localhost** if running behind a proxy:
   ```bash
   uvicorn src.mcp.server:create_app --host 127.0.0.1 --port 8000
   ```

3. **Use firewall rules** to restrict access:
   ```bash
   # Allow only specific IPs (example with ufw)
   sudo ufw allow from 10.0.0.0/8 to any port 8000
   ```

4. **Set up API key authentication** when enabled in Phase 5:
   ```bash
   export MCP_API_KEY="your-secret-api-key"
   ```

---

## 🔄 Updating Your Deployment

### Pull New Code

```bash
cd /home/sblanken/working/code/MR-Krabs

# Stop server
./scripts/deploy.sh stop

# Pull latest code
git pull origin main

# Install any new dependencies
pip install -r requirements.txt

# Restart server
./scripts/deploy.sh start prod
```

### Rollback

If an update causes issues, quickly rollback:

```bash
# Stop current version
./scripts/deploy.sh stop

# Get last working commit
git log --oneline -5  # Find good commit hash

# Revert
git reset --hard <good-commit-hash>

# Restart
./scripts/deploy.sh start prod
```

---

## 🚨 Troubleshooting

### Server Won't Start

**Check if port is already in use:**
```bash
lsof -i :8000
netstat -tlnp | grep 8000
```

**Change the port:**
```bash
uvicorn src.mcp.server:create_app --port 8001
```

### Missing Dependencies

**Reinstall dependencies:**
```bash
pip install --upgrade fastapi uvicorn pydantic structlog requests crewai
```

### Permission Denied Errors

**Fix file permissions:**
```bash
chmod +x scripts/deploy.sh
sudo chown -R $USER:$USER /home/sblanken/working/code/MR-Krabs
```

### Connection Refused

**Check if server is running:**
```bash
ps aux | grep uvicorn
./scripts/deploy.sh status
```

**Check logs for errors:**
```bash
./scripts/deploy.sh logs
```

---

## 📈 Performance Tuning

### Optimize Worker Count

Use multiple workers based on CPU cores:

```bash
# For a 4-core machine
uvicorn src.mcp.server:create_app --workers 8  # 2x core count

# Formula: (CPU cores * 2) + 1
# For 4 cores: (4 * 2) + 1 = 9 workers max
```

### Enable HTTP/2 (with nginx)

Install and configure nginx for HTTP/2 support:

```nginx
server {
    listen 443 ssl http2;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
    }
}
```

### Connection Pooling

For high-traffic deployments, add connection pooling in your reverse proxy configuration.

---

## 🎓 Next Steps

### For Developers

1. **Set up development environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn src.mcp.server:create_app --reload
   ```

2. **Run the test suite:**
   ```bash
   pytest tests/ -v
   ```

3. **Check API documentation:**
   Visit `http://localhost:8000/docs` in your browser

### For DevOps

1. **Set up CI/CD pipeline** (see `.github/workflows/ci.yml`)
2. **Configure monitoring** (Prometheus, Grafana coming in Phase 5)
3. **Plan HTTPS/TLS setup** for production (Phase 5)
4. **Review security requirements** and plan auth implementation

---

## 📞 Support & Resources

### Documentation

- **API Reference:** `docs/PHASE_3_COMPLETE.md`
- **Implementation Summary:** `docs/PHASE_3_IMPLEMENTATION_SUMMARY.md`
- **Deployment Guide:** This file (`DEPLOYMENT_GUIDE.md`)

### Quick Links

| Resource | URL |
|----------|-----|
| API Docs (dev) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| Tools List | http://localhost:8000/tools |

### Getting Help

1. Check the logs (`./scripts/deploy.sh logs`)
2. Run the test suite to verify installation
3. Review error messages in the console output
4. Check GitHub issues for known problems

---

**Status:** ✅ Ready for production deployment  
**Last Updated:** May 5, 2026  
**Version:** Phase 4 (without auth)
