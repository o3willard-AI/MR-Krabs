#!/bin/bash
# MR-Krabs MCP Server Test Runner
# Usage: ./tests/run_mcp_tests.sh [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
RUN_ALL=true
SHOW_VERBOSE=false
SHOW_COVERAGE=false
TEST_FILE=""

# Parse arguments
while getopts "avcf:h" opt; do
    case $opt in
        a) RUN_ALL=true ;;
        v) SHOW_VERBOSE=true ;;
        c) SHOW_COVERAGE=true ;;
        f) TEST_FILE="$OPTARG" ;;
        h)
            echo "MR-Krabs MCP Server Test Runner"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -a          Run all tests (default)"
            echo "  -v          Show verbose output"
            echo "  -c          Show coverage report"
            echo "  -f <file>   Run specific test file (e.g., test_mcp_server.py)"
            echo "  -h          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run all tests"
            echo "  $0 -v                 # Run all tests with verbose output"
            echo "  $0 -c                 # Run with coverage report"
            echo "  $0 -f test_mcp_server.py  # Run specific file"
            exit 0
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
    esac
done

# Change to project root
cd "$(dirname "$0")"/../

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE} MR-Krabs MCP Server Test Suite${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}Error: Virtual environment not found.${NC}"
    echo "Please create it with: python3 -m venv .venv"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Install test dependencies if needed
echo -e "${YELLOW}Checking dependencies...${NC}"
python -c "import pytest" 2>/dev/null || {
    echo "Installing pytest..."
    pip install -q pytest pytest-asyncio httpx
}

python -c "import fastapi" 2>/dev/null || {
    echo "Installing FastAPI..."
    pip install -q fastapi uvicorn structlog pydantic
}

echo -e "${GREEN}Dependencies OK${NC}"
echo ""

# Build pytest command
PYTEST_CMD="python -m pytest tests/mcp/"

if [ -n "$TEST_FILE" ]; then
    PYTEST_CMD="python -m pytest tests/mcp/$TEST_FILE"
fi

if [ "$SHOW_VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$SHOW_COVERAGE" = true ]; then
    pip install -q pytest-cov 2>/dev/null || true
    PYTEST_CMD="$PYTEST_CMD --cov=src.mcp --cov-report=term-missing --cov-report=html"
fi

echo -e "${BLUE}Running tests...${NC}"
echo ""

# Run tests
if $SHOW_VERBOSE; then
    eval $PYTEST_CMD
else
    eval $PYTEST_CMD 2>&1 | tail -20
fi

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo -e "${BLUE}======================================${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed${NC}"
fi

echo -e "${BLUE}======================================${NC}"

if [ "$SHOW_COVERAGE" = true ] && [ -d "htmlcov" ]; then
    echo ""
    echo -e "${YELLOW}Coverage report generated:${NC}"
    echo "  Open htmlcov/index.html in your browser"
fi

exit $EXIT_CODE
