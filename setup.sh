#!/bin/bash
# Setup script for Photo Portal GPIO service
# Creates virtual environment and installs dependencies
# Optionally sets up systemd service for auto-start on boot

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

INSTALL_DIR="$SCRIPT_DIR"
SERVICE_NAME="photoportal-gpio.service"

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

# Determine Python installation method at the beginning
echo ""
echo "Python Installation Method"
echo "--------------------------"
read -p "Use virtual environment? (y/n) [y]: " USE_VENV
USE_VENV=${USE_VENV:-y}

if [[ "$USE_VENV" =~ ^[Yy]$ ]]; then
    # Use virtual environment
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
    
    # Set paths for venv
    PYTHON_PATH="$INSTALL_DIR/venv/bin/python3"
    PIP_CMD="pip"
    PYTHON_CMD="python3"
    PYTHON_ENV=""
else
    # Use system Python
    echo ""
    read -p "Enter full path to Python executable (e.g., /usr/bin/python3): " PYTHON_PATH
    if [ -z "$PYTHON_PATH" ]; then
        echo "ERROR: Python path cannot be empty."
        exit 1
    fi
    if [ ! -f "$PYTHON_PATH" ]; then
        echo "ERROR: Python path '$PYTHON_PATH' does not exist."
        exit 1
    fi
    
    # Verify Python works
    if ! "$PYTHON_PATH" --version &> /dev/null; then
        echo "ERROR: Python at '$PYTHON_PATH' is not executable or not a valid Python installation."
        exit 1
    fi
    
    echo "Using Python: $PYTHON_PATH"
    
    # Determine pip command
    PIP_CMD="$PYTHON_PATH -m pip"
    PYTHON_CMD="$PYTHON_PATH"
    
    # Ask about PYTHONPATH for systemd (but not needed for installation)
    echo ""
    read -p "Enter PYTHONPATH environment variable for systemd service (optional, press Enter to skip): " PYTHON_ENV_INPUT
    if [ -n "$PYTHON_ENV_INPUT" ]; then
        PYTHON_ENV="Environment=\"PYTHONPATH=$PYTHON_ENV_INPUT\""
    else
        PYTHON_ENV=""
    fi
fi

# Check for GPIO system packages (gpiozero will use these automatically)
echo ""
echo "Checking for GPIO system packages..."
MISSING_GPIO=()

# Check for python3-gpiozero (optional, but helpful)
if ! dpkg -l | grep -q "^ii.*python3-gpiozero"; then
    # Not critical - we install via pip
    echo "Note: python3-gpiozero not installed (will use pip version)"
fi

# Check for python3-lgpio or python3-rpi.gpio (gpiozero will use these if available)
if ! dpkg -l | grep -qE "^ii.*python3-(lgpio|rpi\.gpio)"; then
    echo "Note: No GPIO pin factory system packages found."
    echo "      gpiozero will use its native Python implementation."
    echo "      For better performance, you can install: sudo apt install python3-lgpio"
fi
echo ""

# Upgrade pip
echo ""
echo "Upgrading pip..."
$PIP_CMD install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies from requirements.txt..."
$PIP_CMD install -r requirements.txt

# Verify installation by testing imports
echo ""
echo "Verifying installation..."
if ! $PYTHON_CMD -c "import gpiozero; import websockets" 2>/dev/null; then
    echo "ERROR: Failed to import required modules. Installation may have failed."
    exit 1
fi
echo "Installation verified successfully."

echo ""
echo "================================"
echo "Dependencies installed successfully!"
echo ""

# Ask if user wants to set up systemd service (only after successful installation)
echo ""
read -p "Would you like to set up the systemd service for auto-start on boot? (y/n) [y]: " SETUP_SERVICE
SETUP_SERVICE=${SETUP_SERVICE:-y}

if [[ "$SETUP_SERVICE" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Setting up systemd service..."
    echo "Using Python: $PYTHON_PATH"
    
    # Get current user (default to 'pi' if running as root)
    CURRENT_USER=${SUDO_USER:-$USER}
    if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
        CURRENT_USER="pi"
    fi
    
    # Generate systemd service file
    echo ""
    echo "Generating systemd service file..."
    SERVICE_FILE="/tmp/$SERVICE_NAME"
    
    # Make sure the update script is executable so ExecStartPre can run it
    chmod +x "$INSTALL_DIR/update.sh" 2>/dev/null || true

    # Generate systemd service file.
    # ExecStartPre runs update.sh to pull the latest changes from the tracked
    # remote branch before launching the service. It is best-effort and never
    # blocks startup (the script always exits 0).
    if [ -n "$PYTHON_ENV" ]; then
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Photo Portal GPIO Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/bash $INSTALL_DIR/update.sh
ExecStart=$PYTHON_PATH $INSTALL_DIR/gpio_service.py
Restart=always
RestartSec=10
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
$PYTHON_ENV
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    else
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Photo Portal GPIO Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/bash $INSTALL_DIR/update.sh
ExecStart=$PYTHON_PATH $INSTALL_DIR/gpio_service.py
Restart=always
RestartSec=10
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    fi
    
    echo "Service file generated:"
    echo "  Python: $PYTHON_PATH"
    echo "  Working Directory: $INSTALL_DIR"
    echo "  User: $CURRENT_USER"
    if [ -n "$PYTHON_ENV" ]; then
        echo "  PYTHONPATH: $(echo $PYTHON_ENV | cut -d'=' -f2 | tr -d '"')"
    fi
    echo ""
    
    # Copy service file to systemd directory
    echo "Copying service file to /etc/systemd/system/..."
    sudo cp "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME"
    echo "Service file installed."
    
    # Reload systemd
    echo ""
    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload
    echo "Systemd daemon reloaded."
    
    # Ask if user wants to enable and start the service
    echo ""
    read -p "Enable service to start on boot? (y/n) [y]: " ENABLE_SERVICE
    ENABLE_SERVICE=${ENABLE_SERVICE:-y}
    
    if [[ "$ENABLE_SERVICE" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Enabling service..."
        sudo systemctl enable "$SERVICE_NAME"
        echo "Service enabled for auto-start on boot."
        
        echo ""
        read -p "Start the service now? (y/n) [y]: " START_SERVICE
        START_SERVICE=${START_SERVICE:-y}
        
        if [[ "$START_SERVICE" =~ ^[Yy]$ ]]; then
            echo ""
            echo "Starting service..."
            sudo systemctl start "$SERVICE_NAME"
            sleep 2
            if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
                echo "Service started successfully!"
            else
                echo "WARNING: Service may not have started correctly. Check status with:"
                echo "  sudo systemctl status $SERVICE_NAME"
            fi
        fi
    fi
    
    echo ""
    echo "================================"
    echo "Systemd service setup complete!"
    echo ""
    echo "Service management commands:"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo "  sudo systemctl start $SERVICE_NAME"
    echo "  sudo systemctl stop $SERVICE_NAME"
    echo "  sudo systemctl restart $SERVICE_NAME"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
    echo ""
fi

# Ask if user wants to set up Chromium kiosk mode
echo ""
read -p "Would you like to set up Chromium to launch in kiosk mode on boot? (y/n) [y]: " SETUP_KIOSK
SETUP_KIOSK=${SETUP_KIOSK:-y}

if [[ "$SETUP_KIOSK" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Setting up Chromium kiosk mode..."
    
    # Check if Chromium is installed
    if ! command -v chromium-browser &> /dev/null && ! command -v chromium &> /dev/null; then
        echo ""
        echo "WARNING: Chromium is not installed."
        read -p "Would you like to install Chromium now? (y/n) [y]: " INSTALL_CHROMIUM
        INSTALL_CHROMIUM=${INSTALL_CHROMIUM:-y}
        
        if [[ "$INSTALL_CHROMIUM" =~ ^[Yy]$ ]]; then
            echo ""
            echo "Installing Chromium..."
            sudo apt update
            sudo apt install -y chromium-browser
            echo "Chromium installed."
        else
            echo "Skipping kiosk setup. Chromium must be installed for kiosk mode to work."
            echo "You can install it later with: sudo apt install -y chromium-browser"
            SETUP_KIOSK="n"
        fi
    fi
    
    if [[ "$SETUP_KIOSK" =~ ^[Yy]$ ]]; then
        # Get current user (default to 'pi' if running as root)
        CURRENT_USER=${SUDO_USER:-$USER}
        if [ -z "$CURRENT_USER" ] || [ "$CURRENT_USER" = "root" ]; then
            CURRENT_USER="pi"
        fi
        
        # Determine Chromium command (chromium-browser on Debian/Ubuntu, chromium on some systems)
        if command -v chromium-browser &> /dev/null; then
            CHROMIUM_CMD="/usr/bin/chromium-browser"
        elif command -v chromium &> /dev/null; then
            CHROMIUM_CMD="/usr/bin/chromium"
        else
            CHROMIUM_CMD="/usr/bin/chromium-browser"
        fi
        
        # Create autostart directory if it doesn't exist
        AUTOSTART_DIR="/home/$CURRENT_USER/.config/autostart"
        echo "Creating autostart directory: $AUTOSTART_DIR"
        sudo -u "$CURRENT_USER" mkdir -p "$AUTOSTART_DIR"
        
        # Create Chromium kiosk autostart file
        KIOSK_FILE="$AUTOSTART_DIR/photoportal-kiosk.desktop"
        echo "Creating kiosk autostart file: $KIOSK_FILE"
        
        cat > /tmp/photoportal-kiosk.desktop << EOF
[Desktop Entry]
Type=Application
Name=Photo Portal Kiosk
Exec=$CHROMIUM_CMD --kiosk --noerrdialogs --disable-infobars --autoplay-policy=no-user-gesture-required https://photoportal.alexhadik.com/device
X-GNOME-Autostart-enabled=true
EOF
        
        sudo -u "$CURRENT_USER" cp /tmp/photoportal-kiosk.desktop "$KIOSK_FILE"
        sudo -u "$CURRENT_USER" chmod +x "$KIOSK_FILE"
        
        echo "Chromium kiosk mode configured!"
        echo ""
        echo "Chromium will automatically launch in kiosk mode on boot."
        echo "To disable kiosk mode, remove or disable the autostart file:"
        echo "  rm $KIOSK_FILE"
        echo ""
        echo "To test kiosk mode manually (without rebooting):"
        echo "  $CHROMIUM_CMD --kiosk --noerrdialogs --disable-infobars --autoplay-policy=no-user-gesture-required https://photoportal.alexhadik.com/device"
        echo ""
    fi
fi

echo "================================"
echo "Setup complete!"
echo ""

if [[ "$USE_VENV" =~ ^[Yy]$ ]]; then
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
else
    echo "To run the diagnostic script:"
    echo "  $PYTHON_CMD diagnostic.py"
    echo ""
    echo "To run the GPIO service:"
    echo "  $PYTHON_CMD gpio_service.py"
fi
echo ""
