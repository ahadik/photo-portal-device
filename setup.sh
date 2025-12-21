#!/bin/bash
# Setup script for Photo Portal GPIO service
# Creates virtual environment and installs dependencies

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Photo Portal GPIO Service Setup"
echo "================================"
echo " "

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.7 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $(python3 --version)"

# Check for build dependencies needed for lgpio
echo ""
echo "Checking for build dependencies..."
MISSING_DEPS=()

if ! command -v swig &> /dev/null; then
    MISSING_DEPS+=("swig")
fi

if ! dpkg -l | grep -q "^ii.*build-essential"; then
    MISSING_DEPS+=("build-essential")
fi

if ! dpkg -l | grep -q "^ii.*python3-dev"; then
    MISSING_DEPS+=("python3-dev")
fi

# Check for lgpio C library (required for Python lgpio package)
if ! ldconfig -p | grep -q liblgpio; then
    # Try to find the package that provides liblgpio
    if ! dpkg -l | grep -qE "^ii.*(lgpio|liblgpio)"; then
        MISSING_DEPS+=("liblgpio-dev")
    fi
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "WARNING: Missing build dependencies: ${MISSING_DEPS[*]}"
    echo "These are required to build the lgpio package from source."
    echo ""
    echo "To install them, run:"
    echo "  sudo apt update"
    echo "  sudo apt install -y ${MISSING_DEPS[*]}"
    echo ""
    read -p "Do you want to install them now? (requires sudo) [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo apt update
        sudo apt install -y "${MISSING_DEPS[@]}"
        echo "Build dependencies installed."
    else
        echo "Skipping build dependency installation."
        echo "You may encounter errors when installing lgpio."
    fi
    echo ""
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo ""
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "================================"
echo "Setup complete!"
echo ""
echo "To activate the virtual environment manually, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the diagnostic script:"
echo "  source venv/bin/activate"
echo "  python3 diagnostic.py"
echo ""
echo "To run the GPIO service:"
echo "  source venv/bin/activate"
echo "  python3 gpio_service.py"
echo ""
echo "The systemd service is configured to use the virtual environment automatically."
