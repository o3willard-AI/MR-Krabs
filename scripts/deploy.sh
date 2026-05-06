#!/bin/bash
# MR-Krabs MCP Server Deployment Script
# Deploys the server as a native Python application (no Docker required)
#
# Usage:
#   ./deploy.sh [dev|prod]
#
# Examples:
#   ./deploy.sh dev    # Development deployment
#   ./deploy.sh prod   # Production deployment

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/deploy.log"
PID_FILE="$SCRIPT_DIR/server.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_success() {
    log "${GREEN}✓ SUCCESS: $1${NC}"
}

log_error() {
    log "${RED}✗ ERROR: $1${NC}"
}

log_warning() {
    log "${YELLOW}⚠ WARNING: $1${NC}"
}

# Check if command exists
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is not installed. Please install it and try again."
        exit 1
    fi
}

# Validate Python version
validate_python() {
    log "Validating Python environment..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        log_error "Python is not installed or not in PATH"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
    log "Using: $PYTHON_VERSION"
    
    # Check for required packages
    log "Checking required packages..."
    for package in fastapi uvicorn pydantic structlog requests; do
        if ! $PYTHON_CMD -c "import ${package//-/_}" 2>/dev/null; then
            log_warning "Package '$package' not found. Installing..."
            pip3 install "$package" || pip install "$package"
        fi
    done
    
    log_success "Python environment validated"
}

# Install dependencies
install_dependencies() {
    log "Installing project dependencies..."
    
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        pip3 install -r "$PROJECT_ROOT/requirements.txt" || pip install -r "$PROJECT_ROOT/requirements.txt"
    fi
    
    # Install additional dev tools if needed
    if [ "$1" == "dev" ]; then
        log "Installing development dependencies..."
        pip3 install pytest pytest-timeout pytest-cov requests || true
    fi
    
    log_success "Dependencies installed"
}

# Run tests before deployment
run_tests() {
    log "Running test suite..."
    
    # Run unit tests
    if [ -d "$PROJECT_ROOT/tests" ]; then
        cd "$PROJECT_ROOT"
        
        # Check pytest availability
        if ! command -v pytest &> /dev/null; then
            log_warning "pytest not found, skipping tests"
            return 0
        fi
        
        # Run tests with coverage
        log "Running unit tests..."
        if pytest tests/ -v --tb=short --timeout=30 -q; then
            log_success "All tests passed"
        else
            log_error "Some tests failed. Continuing anyway..."
        fi
    fi
    
    cd "$SCRIPT_DIR"
}

# Start the server
start_server() {
    local mode="$1"
    local host="0.0.0.0"
    local port="8000"
    
    log "Starting MR-Krabs MCP Server in $mode mode..."
    
    # Set environment variables based on mode
    if [ "$mode" == "prod" ]; then
        export ENVIRONMENT="production"
        export LOG_LEVEL="warning"
        
        # Production should have auth enabled (but optional)
        if [ -z "$MCP_API_KEY" ]; then
            log_warning "No MCP_API_KEY set. Authentication will be disabled in production."
        fi
    else
        export ENVIRONMENT="development"
        export LOG_LEVEL="info"
        
        # Development defaults
        host="127.0.0.1"
    fi
    
    export HOST=$host
    export PORT=$port
    
    log "Configuration:"
    log "  Mode: $mode"
    log "  Host: $host:$port"
    log "  Environment: $ENVIRONMENT"
    log "  Log Level: $LOG_LEVEL"
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    # Start server using uvicorn
    if [ "$mode" == "prod" ]; then
        # Production: run in background with systemd-style logging
        log "Starting server in production mode (background)..."
        
        nohup $PYTHON_CMD -m uvicorn src.mcp.server:create_app \
            --host "$host" \
            --port "$port" \
            --workers 4 \
            --access-log \
            --log-level "$LOG_LEVEL" \
            > "$LOG_FILE" 2>&1 &
        
        SERVER_PID=$!
        echo $SERVER_PID > "$PID_FILE"
        
        log "Server started with PID: $SERVER_PID"
        log "Logs available at: $LOG_FILE"
    else
        # Development: run in foreground with detailed logging
        log "Starting server in development mode (foreground)..."
        log "Press Ctrl+C to stop"
        
        $PYTHON_CMD -m uvicorn src.mcp.server:create_app \
            --host "$host" \
            --port "$port" \
            --reload \
            --log-level "$LOG_LEVEL"
    fi
    
    # Wait for server to be ready (dev mode only)
    if [ "$mode" == "dev" ]; then
        log_success "Server is running at http://$host:$port"
        log "API Documentation: http://$host:$port/docs"
    else
        log "Waiting for server to be ready..."
        
        # Health check loop
        MAX_RETRIES=30
        RETRY_COUNT=0
        
        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if curl -s http://"$host":"$port"/health > /dev/null 2>&1; then
                log_success "Server is ready!"
                return 0
            fi
            
            sleep 1
            RETRY_COUNT=$((RETRY_COUNT + 1))
            
            if [ $((RETRY_COUNT % 5)) -eq 0 ]; then
                log "Still starting... ($RETRY_COUNT/$MAX_RETRIES)"
            fi
        done
        
        log_error "Server failed to start within ${MAX_RETRIES}s"
        return 1
    fi
}

# Stop the server
stop_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        
        if ps -p "$PID" > /dev/null 2>&1; then
            log "Stopping server (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            
            # Wait for process to terminate
            sleep 2
            
            if ps -p "$PID" > /dev/null 2>&1; then
                log_warning "Process did not stop gracefully, forcing..."
                kill -9 "$PID" 2>/dev/null || true
            fi
            
            rm -f "$PID_FILE"
            log_success "Server stopped"
        else
            log_warning "No running process found for PID file"
            rm -f "$PID_FILE"
        fi
    else
        log_warning "No PID file found. Server may not be running."
        
        # Try to find and kill any MR-Krabs processes
        pkill -f "mrkrabs" || true
        log "Killed any existing MR-Krabs processes"
    fi
}

# Check server status
check_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        
        if ps -p "$PID" > /dev/null 2>&1; then
            log "Server is running (PID: $PID)"
            
            # Get server health
            HEALTH_RESPONSE=$(curl -s http://0.0.0.0:8000/health 2>/dev/null || echo "{}")
            
            if [ -n "$HEALTH_RESPONSE" ]; then
                echo "Health Check:"
                echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"
            fi
            
            return 0
        else
            log_warning "PID file exists but process not running (stale PID file)"
            rm -f "$PID_FILE"
            return 1
        fi
    else
        log "Server is not running (no PID file)"
        
        # Check if anything is listening on port 8000
        if command -v lsof &> /dev/null; then
            PORT_USAGE=$(lsof -i :8000 2>/dev/null | grep LISTEN || true)
            if [ -n "$PORT_USAGE" ]; then
                log_warning "Port 8000 is in use by another process"
                echo "$PORT_USAGE"
            fi
        fi
        
        return 1
    fi
}

# Display usage
usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start [dev|prod]   Start the server (default: dev)"
    echo "  stop               Stop the running server"
    echo "  restart            Restart the server"
    echo "  status             Check server status"
    echo "  logs               View server logs"
    echo "  test               Run tests only"
    echo "  deploy [dev|prod]  Full deployment (install + test + start)"
    echo ""
    echo "Examples:"
    echo "  $0 start dev       # Start in development mode"
    echo "  $0 deploy prod     # Deploy to production"
    echo "  $0 status          # Check if server is running"
    echo ""
}

# View logs
view_logs() {
    if [ -f "$LOG_FILE" ]; then
        log "Viewing last 50 lines of logs..."
        tail -50 "$LOG_FILE"
    else
        log_warning "No log file found yet"
    fi
}

# Main entry point
main() {
    local command="${1:-start}"
    local mode="${2:-dev}"
    
    log "=== MR-Krabs MCP Server Deployment ==="
    log "Command: $command"
    log "Mode: $mode"
    echo ""
    
    case "$command" in
        start)
            validate_python
            start_server "$mode"
            ;;
        
        stop)
            stop_server
            ;;
        
        restart)
            stop_server
            sleep 2
            validate_python
            start_server "$mode"
            ;;
        
        status)
            check_status
            ;;
        
        logs)
            view_logs
            ;;
        
        test)
            validate_python
            run_tests
            ;;
        
        deploy)
            validate_python
            install_dependencies "$mode"
            run_tests
            start_server "$mode"
            log_success "Deployment complete!"
            ;;
        
        help|--help|-h)
            usage
            exit 0
            ;;
        
        *)
            log_error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

# Trap signals for cleanup
trap stop_server SIGINT SIGTERM

# Run main function
main "$@"
