#!/bin/bash
# Setup script for Photo Portal GPIO service
# Creates virtual environment and installs dependencies

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Photo Portal GPIO Service Setup"
echo "================================"
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.7 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $(python3 --version)"

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
