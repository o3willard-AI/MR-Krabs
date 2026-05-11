#!/usr/bin/env bash

# MR-Krabs Installation Script
# This script demonstrates the installation process for MR-Krabs

set -e  # Exit on first error

echo "=== MR-Krabs Installation Script ==="
echo ""
echo "This script demonstrates the installation process for MR-Krabs."
echo "For a full installation, please follow these steps:"
echo ""

# === Step 1: Checking Python ===
echo "=== Step 1: Checking Python ==="
if command -v python3 &> /dev/null; then
    echo "✅ Python3 found"
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo "Python version: $PYTHON_VERSION"
    
    # Check if version is >= 3.11
    if [[ "${PYTHON_VERSION}" < "3.11" ]]; then
        echo "❌ Error: Python version must be 3.11 or higher"
        exit 1
    fi
    echo "✅ Python version is sufficient"
else
    echo "❌ Error: Python3 not found"
    exit 1
fi

# === Step 2: Checking OS ===
echo ""
echo "=== Step 2: Checking OS ==="
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "✅ Linux detected"
    OS="Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "✅ macOS detected"
    OS="Mac"
else
    echo "⚠️ Warning: Unsupported OS, but continuing anyway"
    OS="Unknown"
fi

echo ""
echo "=== Installation Steps ==="
echo "To install MR-Krabs, please:"
echo "1. Create a virtual environment:"
echo "   python3 -m venv .venv"
echo "2. Activate the virtual environment:"
echo "   source .venv/bin/activate  # On Linux/macOS"
echo "   .venv\\Scripts\\activate     # On Windows"
echo "3. Install the core package:"
echo "   pip install cost-orchestrator"
echo "4. Install optional packages (as needed):"
echo "   pip install crewai    # For CrewAI support"
echo "   pip install mcp-server  # For MCP server"

# === Step 3: Verification ===
echo ""
echo "=== Verification ==="
echo "After installation, verify with:"
echo "python3 -c \"import cost_orchestrator\""
echo "python3 -c \"import crewai\"  # if CrewAI was installed"
echo "python3 -c \"import mcp_server\"  # if MCP server was installed"

echo ""
echo "=== Installation Summary ==="
echo "Core package: cost-orchestrator"
echo "Optional extras: crewai, mcp-server"
echo ""
echo "Installation instructions completed! 🎉"