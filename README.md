# Photo Portal Device Scripts

This directory contains Python scripts for managing GPIO hardware on the Raspberry Pi for the Photo Portal device.

## Contents

- **`diagnostic.py`** - Diagnostic tool to test and verify GPIO inputs, ADC, and LED output
- **`gpio_service.py`** - WebSocket service that bridges hardware with the webapp
- **`photoportal-gpio.service`** - systemd unit file for running the GPIO service as a background service
- **`requirements.txt`** - Python package dependencies
- **`setup.sh`** - Automated setup script to create virtual environment and install dependencies
- **`.gitignore`** - Git ignore file to exclude virtual environment and Python artifacts

## Prerequisites

- Raspberry Pi 4 or 5 running Raspberry Pi OS (64-bit)
- Python 3.7 or higher
- Physical hardware connected according to the [technical architecture](../photo-portal-web/docs/technical_architecture.md)

### Hardware Requirements

- LED on GPIO 17 (with 330Ω resistor)
- Like button on GPIO 18 (momentary, pull-up)
- Map toggle switch on GPIO 27 (SPDT, pull-up)
- Metadata toggle switch on GPIO 22 (SPDT, pull-up)
- Message button on GPIO 23 (momentary, pull-up)
- ADS1115 ADC on I2C (GPIO 2/3) for potentiometer (optional)

## Installation

1. **Clone or copy this directory to your Raspberry Pi:**

   ```bash
   # If using git
   git clone <repository-url>
   cd photo-portal/photo-portal-device
   
   # Or copy files directly to:
   # /home/pi/photoportal/
   ```

2. **Run the setup script (Recommended):**

   First, make the setup script executable:

   ```bash
   chmod +x setup.sh
   ```

   Then run the setup script (it will create a virtual environment and install all dependencies):

   ```bash
   ./setup.sh
   ```

   Or run it with bash directly (no chmod needed):

   ```bash
   bash setup.sh
   ```

   If you prefer to set up manually:

   ```bash
   # Create a virtual environment
   python3 -m venv venv
   
   # Activate the virtual environment
   source venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

   The virtual environment keeps dependencies isolated and avoids conflicts with system packages.

   **Note:** You'll need to activate the virtual environment each time you run the scripts manually:
   ```bash
   source venv/bin/activate
   ```

   The systemd service is configured to use the virtual environment automatically.

   **Alternative: Install to user directory (if you prefer not to use venv):**

   ```bash
   pip3 install --user -r requirements.txt
   ```

   If using this method, you'll need to update the systemd service file to use system Python and set PYTHONPATH (see Troubleshooting section).

3. **Enable I2C (for ADC support):**

   ```bash
   sudo raspi-config
   # Navigate to: Interface Options → I2C → Enable
   # Reboot after enabling
   ```

4. **Make scripts executable:**

   ```bash
   chmod +x setup.sh diagnostic.py gpio_service.py
   ```

   **Note:** If you get "permission denied" when running `./setup.sh`, make sure you've run `chmod +x setup.sh` first, or use `bash setup.sh` instead.

## Usage

### Diagnostic Script

The diagnostic script allows you to test all GPIO inputs and outputs to verify hardware wiring.

**Run the diagnostic script:**

First, activate the virtual environment (if not already activated):

```bash
source venv/bin/activate
```

Then run the script:

```bash
python3 diagnostic.py
```

Or if executable:

```bash
./diagnostic.py
```

**Note:** The script's shebang (`#!/usr/bin/env python3`) will use the system Python. To use the venv Python, either activate the venv first or run:

```bash
venv/bin/python3 diagnostic.py
```

**What it does:**

- Monitors all GPIO inputs (buttons and switches) and logs state changes
- Reads ADC potentiometer values and logs changes (when change > 2%)
- Tests LED PWM output with fade effect (fades when Like button is pressed)
- Displays timestamps and detailed state information

**Example output:**

```
======================================================================
Photo Portal GPIO Diagnostic Tool
======================================================================

Initializing GPIO outputs...
LED (GPIO 17) initialized with PWM

Initializing GPIO inputs...
All inputs configured with pull-up resistors (active LOW)

Like Button (GPIO 18) [button] -> RELEASED/OFF (initial state)
Map Toggle (GPIO 27) [switch] -> OFF (initial state)
...

[2024-12-15 10:30:45.123] Like Button (GPIO 18) [button] -> PRESSED/ON
[2024-12-15 10:30:45.456] ADC (Potentiometer) -> 0.523 (raw: 17145)
```

**Exit:** Press `Ctrl+C` to stop the script.

### GPIO Service

The GPIO service runs as a WebSocket server that communicates with the Photo Portal webapp.

**Run the GPIO service manually:**

First, activate the virtual environment (if not already activated):

```bash
source venv/bin/activate
```

Then run the service:

```bash
python3 gpio_service.py
```

Or if executable:

```bash
./gpio_service.py
```

**Note:** The script's shebang (`#!/usr/bin/env python3`) will use the system Python. To use the venv Python, either activate the venv first or run:

```bash
venv/bin/python3 gpio_service.py
```

**What it does:**

- Starts a WebSocket server on `ws://localhost:8765`
- Monitors GPIO inputs and broadcasts events to connected clients
- Reads ADC potentiometer and broadcasts zoom dial changes
- Accepts LED control commands from the webapp
- Sends initial states to newly connected clients

**Check if it's running:**

The service logs to stdout/stderr. You should see:

```
INFO - Photo Portal GPIO Service starting...
INFO - LED (GPIO 17) initialized with PWM
INFO - LIKE_BUTTON (GPIO 18) initialized
...
INFO - Starting WebSocket server on localhost:8765
INFO - WebSocket server started
```

**Exit:** Press `Ctrl+C` or send SIGTERM/SIGINT to stop the service.

### Running as a System Service

To run the GPIO service automatically on boot and keep it running:

1. **Copy the systemd unit file:**

   ```bash
   sudo cp photoportal-gpio.service /etc/systemd/system/
   ```

2. **Edit the service file if needed:**

   ```bash
   sudo nano /etc/systemd/system/photoportal-gpio.service
   ```

   The default service file is configured to use the virtual environment at `/home/pi/photoportal/venv/bin/python3`.

   Update the paths if your installation is in a different location:
   ```
   ExecStart=/home/pi/photoportal/venv/bin/python3 /home/pi/photoportal/gpio_service.py
   WorkingDirectory=/home/pi/photoportal
   ```

   **If you're NOT using a virtual environment** (e.g., using `--user` install), update the service file:
   ```
   ExecStart=/usr/bin/python3 /home/pi/photoportal/gpio_service.py
   Environment="PYTHONPATH=/home/pi/.local/lib/python3.11/site-packages"
   ```

3. **Reload systemd and enable the service:**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable photoportal-gpio.service
   ```

4. **Start the service:**

   ```bash
   sudo systemctl start photoportal-gpio.service
   ```

5. **Check service status:**

   ```bash
   sudo systemctl status photoportal-gpio.service
   ```

6. **View service logs:**

   ```bash
   sudo journalctl -u photoportal-gpio.service -f
   ```

**Service management commands:**

```bash
# Start service
sudo systemctl start photoportal-gpio.service

# Stop service
sudo systemctl stop photoportal-gpio.service

# Restart service
sudo systemctl restart photoportal-gpio.service

# Disable auto-start on boot
sudo systemctl disable photoportal-gpio.service

# Check if service is running
sudo systemctl is-active photoportal-gpio.service
```

## Troubleshooting

### "Externally Managed Environment" Error

If you see an error like:
```
error: externally-managed-environment
× This environment is externally managed
```

This is a safety feature in newer Python installations (PEP 668) that prevents conflicts with system packages.

**Solution: Use a virtual environment (Recommended):**

The installation instructions use a virtual environment by default, which avoids this error:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Alternative: Use `--user` flag:**

If you prefer not to use a virtual environment:

```bash
pip3 install --user -r requirements.txt
```

Note: If using `--user`, you'll need to update the systemd service file to use system Python and set PYTHONPATH (see systemd service setup section).

### GPIO Permission Errors

If you see permission errors accessing GPIO:

```bash
# Add user to gpio group
sudo usermod -a -G gpio pi

# Log out and back in, or:
newgrp gpio
```

### I2C/ADC Not Working

1. **Verify I2C is enabled:**

   ```bash
   lsmod | grep i2c
   ```

   Should show `i2c_dev` and `i2c_bcm2835` (or similar).

2. **Check I2C device detection:**

   ```bash
   sudo i2cdetect -y 1
   ```

   Should show the ADS1115 at address `0x48`.

3. **Verify wiring:**
   - ADS1115 SDA → GPIO 2 (physical pin 3)
   - ADS1115 SCL → GPIO 3 (physical pin 5)
   - ADS1115 VDD → 3.3V
   - ADS1115 GND → GND

### WebSocket Connection Issues

If the webapp can't connect to the GPIO service:

1. **Verify the service is running:**

   ```bash
   sudo systemctl status photoportal-gpio.service
   ```

2. **Check if port 8765 is listening:**

   ```bash
   netstat -tlnp | grep 8765
   # or
   ss -tlnp | grep 8765
   ```

3. **Check firewall settings:**

   ```bash
   sudo ufw status
   ```

   The service runs on localhost only, so firewall shouldn't be an issue, but verify.

4. **Test WebSocket connection manually:**

   ```bash
   # Install wscat for testing
   npm install -g wscat
   
   # Connect to service
   wscat -c ws://localhost:8765
   ```

### Service Won't Start

1. **Check service logs:**

   ```bash
   sudo journalctl -u photoportal-gpio.service -n 50
   ```

2. **Verify Python path and script location:**

   ```bash
   which python3
   ls -l /home/pi/photoportal/gpio_service.py
   ```

3. **Test script manually:**

   ```bash
   python3 /home/pi/photoportal/gpio_service.py
   ```

   This will show any import or runtime errors.

### ADC Library Not Found

If you see "WARNING: adafruit-circuitpython-ads1x15 not available":

```bash
# Install the library
pip3 install adafruit-circuitpython-ads1x15

# Or install all requirements
pip3 install -r requirements.txt
```

### Scripts Exit Immediately

If scripts exit right after starting:

1. **Check for import errors:**

   ```bash
   python3 -c "import gpiozero; import websockets"
   ```

2. **Verify you're running on a Raspberry Pi:**

   ```bash
   cat /proc/cpuinfo | grep Model
   ```

   GPIO libraries only work on Raspberry Pi hardware.

## Hardware Reference

For detailed hardware wiring diagrams and pin assignments, see:
- [Technical Architecture](../photo-portal-web/docs/technical_architecture.md)

**Quick Pin Reference:**

| Component | GPIO Pin | Physical Pin | Description |
|-----------|----------|--------------|-------------|
| LED | 17 | 11 | Message indicator (PWM) |
| Like Button | 18 | 12 | Momentary button |
| Map Toggle | 27 | 13 | SPDT switch |
| Metadata Toggle | 22 | 15 | SPDT switch |
| Message Button | 23 | 16 | Momentary button |
| ADS1115 SDA | 2 | 3 | I2C data |
| ADS1115 SCL | 3 | 5 | I2C clock |

## Development

### Testing Changes

1. **Stop the systemd service (if running):**

   ```bash
   sudo systemctl stop photoportal-gpio.service
   ```

2. **Activate virtual environment and run script manually for testing:**

   ```bash
   source venv/bin/activate
   python3 gpio_service.py
   ```

   Or use the venv Python directly:

   ```bash
   venv/bin/python3 gpio_service.py
   ```

3. **Make changes and test**

4. **Restart service when ready:**

   ```bash
   sudo systemctl restart photoportal-gpio.service
   ```

### Debugging

Enable more verbose logging by modifying the logging level in `gpio_service.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Additional Resources

- [gpiozero Documentation](https://gpiozero.readthedocs.io/)
- [WebSockets Documentation](https://websockets.readthedocs.io/)
- [Adafruit ADS1x15 Documentation](https://learn.adafruit.com/adafruit-4-channel-adc-breakouts)
- [Raspberry Pi GPIO Pinout](https://pinout.xyz/)
