# Photo Portal Device Scripts

This directory contains Python scripts for managing GPIO hardware on the Raspberry Pi for the Photo Portal device.

## Contents

- **`diagnostic.py`** - Diagnostic tool to test and verify GPIO inputs, ADC, and LED output
- **`gpio_service.py`** - WebSocket service that bridges hardware with the webapp
- **`requirements.txt`** - Python package dependencies
- **`setup.sh`** - Automated setup script to create virtual environment, install dependencies, and optionally configure systemd service (generates systemd service file automatically)
- **`.gitignore`** - Git ignore file to exclude virtual environment and Python artifacts

## Prerequisites

- Raspberry Pi 4 or 5 running Raspberry Pi OS (64-bit)
- Python 3.7 or higher
- Physical hardware connected according to the [hardware wiring guide](docs/hardware-wiring.md)

### Hardware Requirements

- LED push button (acts as LED indicator, Select button, and Message button)
  - LED contacts wired to GPIO 17 (built-in 200Ω resistor, no external resistor needed)
  - Button switch contacts wired to GPIO 18 (momentary, pull-up)
  - Functionality: In Slideshow Mode, shows the most recent message; in Map View, sets the boundary filter
  - Recommended: [Adafruit Arcade Button with LED - 30mm](https://www.adafruit.com/product/3491)
  - Alternative: Separate LED with 330Ω external resistor and separate button if not using LED push button
- Map toggle switch on GPIO 27 (SPDT, pull-up)
- Metadata toggle switch on GPIO 22 (SPDT, pull-up)
- ADS1115 ADC on I2C (GPIO 2/3) for potentiometer
- Potentiometer - 10kΩ linear potentiometer (for zoom control)

## Installation

1. **Clone or copy this directory to your Raspberry Pi:**

   ```bash
   # If using git
   git clone <repository-url>
   cd photo-portal-device
   
   # Or copy files directly to:
   # /home/pi/photo-portal-device/
   ```

2. **Install build dependencies and C library (Required for lgpio):**

   The `lgpio` Python package is a wrapper around the `lgpio` C library. You need both:

   ```bash
   sudo apt update
   sudo apt install -y swig build-essential python3-dev liblgpio-dev
   ```

   **Note:** The `liblgpio-dev` package provides the C library that the Python package links against. Without it, the build will fail with "cannot find -llgpio".

   **Note:** The setup script will prompt you to install these if they're missing.

3. **Run the setup script (Recommended):**

   The scripts are already executable in the repository, so you can run them directly:

   ```bash
   ./setup.sh
   ```

   Or run it with bash directly:

   ```bash
   bash setup.sh
   ```

   **Note:** If you get "permission denied" when running `./setup.sh`, the executable permissions may not have been preserved. In that case, run `chmod +x setup.sh` or use `bash setup.sh` instead.

   The setup script will:
   - Ask you to choose Python installation method (venv or custom) at the beginning
   - Check for build dependencies and offer to install them automatically
   - Create a virtual environment (if chosen) and install Python dependencies using the selected Python
   - Verify installation by testing imports
   - Optionally set up the systemd service for auto-start on boot (only after successful installation)

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

4. **Enable I2C (for ADC support):**

   ```bash
   sudo raspi-config
   # Navigate to: Interface Options → I2C → Enable
   # Reboot after enabling
   ```

5. **Set up systemd service for auto-start on boot (Optional but Recommended):**

   The GPIO service can be configured as a systemd service that automatically starts when your Raspberry Pi boots up. This ensures the service is always running, even after reboots or power cycles.

   **Automated Setup (Recommended):**

   If you used the `setup.sh` script, it will prompt you to set up the systemd service after successfully installing dependencies. The script will:

   - Prompt whether to set up systemd service (default: yes)
   - Generate a service file using the Python path determined at the beginning
   - Detect the current user automatically
   - Copy the service file to `/etc/systemd/system/`
   - Reload systemd daemon
   - Optionally enable and start the service

   **Example interaction during setup.sh:**

   ```bash
   $ ./setup.sh
   ...
   ================================
   Dependencies installed successfully!

   Would you like to set up the systemd service for auto-start on boot? (y/n) [y]: y

   Setting up systemd service...
   Using Python: /home/pi/photo-portal-device/venv/bin/python3

   Generating systemd service file...
     Python: /home/pi/photo-portal-device/venv/bin/python3
     Working Directory: /home/pi/photo-portal-device
     User: pi

   Copying service file to /etc/systemd/system/...
   Service file installed.

   Reloading systemd daemon...
   Systemd daemon reloaded.

   Enable service to start on boot? (y/n) [y]: y
   Enabling service...
   Service enabled for auto-start on boot.

   Start the service now? (y/n) [y]: y
   Starting service...
   Service started successfully!
   ```

   **Note:** The systemd service setup only occurs after all dependencies are successfully installed and verified. This ensures the service will work correctly when started.

   **Manual Setup (Alternative):**

   If you prefer to set up the systemd service manually, or need to modify an existing setup:

   1. **Navigate to the device scripts directory:**

      ```bash
      cd /home/pi/photo-portal-device
      ```

   2. **Create or edit the systemd service file:**

      ```bash
      sudo nano /etc/systemd/system/photoportal-gpio.service
      ```

      **Example configuration using virtual environment (default):**

      ```
      [Unit]
      Description=Photo Portal GPIO Service
      After=network.target

      [Service]
      Type=simple
      ExecStart=/home/pi/photo-portal-device/venv/bin/python3 /home/pi/photo-portal-device/gpio_service.py
      Restart=always
      RestartSec=10
      User=pi
      WorkingDirectory=/home/pi/photo-portal-device
      StandardOutput=journal
      StandardError=journal

      [Install]
      WantedBy=multi-user.target
      ```

      **If your installation is in a different location**, update the paths accordingly.

      **If you're NOT using a virtual environment** (e.g., installed with `--user` flag), use:
      ```
      ExecStart=/usr/bin/python3 /home/pi/photo-portal-device/gpio_service.py
      Environment="PYTHONPATH=/home/pi/.local/lib/python3.11/site-packages"
      WorkingDirectory=/home/pi/photo-portal-device
      User=pi
      ```

      Save and exit the editor (in nano: `Ctrl+X`, then `Y`, then `Enter`).

   3. **Reload systemd and enable the service:**

      ```bash
      sudo systemctl daemon-reload
      sudo systemctl enable photoportal-gpio.service
      sudo systemctl start photoportal-gpio.service
      ```

   4. **Verify the service is running:**

      ```bash
      sudo systemctl status photoportal-gpio.service
      ```

   **Service Management Commands:**

   Once the service is set up, you can manage it with these commands:

   ```bash
   # Start the service
   sudo systemctl start photoportal-gpio.service

   # Stop the service
   sudo systemctl stop photoportal-gpio.service

   # Restart the service (useful after making code changes)
   sudo systemctl restart photoportal-gpio.service

   # Check if service is currently running
   sudo systemctl is-active photoportal-gpio.service

   # Check if service is enabled to start on boot
   sudo systemctl is-enabled photoportal-gpio.service

   # View recent service logs
   sudo journalctl -u photoportal-gpio.service -n 100

   # Follow service logs in real-time
   sudo journalctl -u photoportal-gpio.service -f
   ```

6. **Set up Chromium kiosk mode for auto-launch on boot (Optional but Recommended):**

   The Photo Portal device is designed to run as a kiosk, automatically launching Chromium in full-screen mode when the Raspberry Pi boots up.

   **Automated Setup (Recommended):**

   If you used the `setup.sh` script, it will prompt you to set up Chromium kiosk mode after configuring the systemd service. The script will:

   - Prompt whether to set up kiosk mode (default: yes)
   - Check if Chromium is installed and offer to install it if missing
   - Create an autostart file that launches Chromium in kiosk mode
   - Configure Chromium to navigate to `https://photoportal.alexhadik.com/device`
   - Set up full-screen kiosk mode with appropriate flags

   **Example interaction during setup.sh:**

   ```bash
   Would you like to set up Chromium to launch in kiosk mode on boot? (y/n) [y]: y

   Setting up Chromium kiosk mode...
   Creating autostart directory: /home/pi/.config/autostart
   Creating kiosk autostart file: /home/pi/.config/autostart/photoportal-kiosk.desktop
   Chromium kiosk mode configured!

   Chromium will automatically launch in kiosk mode on boot.
   ```

   **Manual Setup (Alternative):**

   If you prefer to set up kiosk mode manually:

   1. **Create the autostart directory (if it doesn't exist):**

      ```bash
      mkdir -p ~/.config/autostart
      ```

   2. **Create the kiosk autostart file:**

      ```bash
      nano ~/.config/autostart/photoportal-kiosk.desktop
      ```

   3. **Add the following content:**

      ```
      [Desktop Entry]
      Type=Application
      Name=Photo Portal Kiosk
      Exec=/usr/bin/chromium-browser --kiosk --noerrdialogs --disable-infobars --autoplay-policy=no-user-gesture-required https://photoportal.alexhadik.com/device
      X-GNOME-Autostart-enabled=true
      ```

   4. **Make the file executable:**

      ```bash
      chmod +x ~/.config/autostart/photoportal-kiosk.desktop
      ```

   5. **Test kiosk mode (without rebooting):**

      ```bash
      /usr/bin/chromium-browser --kiosk --noerrdialogs --disable-infobars --autoplay-policy=no-user-gesture-required https://photoportal.alexhadik.com/device
      ```

   **Disabling Kiosk Mode:**

   To disable kiosk mode, remove or rename the autostart file:

   ```bash
   rm ~/.config/autostart/photoportal-kiosk.desktop
   ```

   **Note:** Chromium must be installed for kiosk mode to work. On Raspberry Pi OS, Chromium is typically pre-installed. If it's not installed, you can install it with:

   ```bash
   sudo apt update
   sudo apt install -y chromium-browser
   ```

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
- Tests LED PWM output with fade effect (fades when Select button is pressed)
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

Select Button (GPIO 18) [button] -> RELEASED/OFF (initial state)
Map Toggle (GPIO 27) [switch] -> OFF (initial state)
...

[2024-12-15 10:30:45.123] Select Button (GPIO 18) [button] -> PRESSED/ON
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
INFO - SELECT_BUTTON (GPIO 18) initialized
...
INFO - Starting WebSocket server on localhost:8765
INFO - WebSocket server started
```

**Exit:** Press `Ctrl+C` or send SIGTERM/SIGINT to stop the service.

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

### "Cannot determine SOC peripheral base address" Error

If you see errors like:
```
ERROR: Failed to initialize LED on GPIO 17: Cannot determine SOC peripheral base address
PinFactoryFallback: Falling back from lgpio: No module named 'lgpio'
```

This means the GPIO libraries aren't properly configured. **This script must be run on a Raspberry Pi.**

**Solutions:**

1. **Verify you're on a Raspberry Pi:**

   ```bash
   cat /proc/cpuinfo | grep Model
   ```

   Should show "Raspberry Pi" model information.

2. **Install GPIO system packages (Recommended):**

   `gpiozero` automatically selects the best available pin factory. For best performance, install the system package:

   ```bash
   sudo apt update
   sudo apt install -y python3-lgpio
   ```

   **Why this is simpler:**

   - No compilation needed (pre-built package)
   - Works with virtual environments (gpiozero can use system packages)
   - Better performance than pure Python implementation
   - No build tools required

   **Note:** `gpiozero` will automatically use `python3-lgpio` if available, or fall back to other options (RPi.GPIO, pigpio, or native Python) if not. You don't need to install anything in the virtual environment for GPIO functionality.

3. **If using a virtual environment, reinstall gpiozero:**

   ```bash
   source venv/bin/activate
   pip install --upgrade --force-reinstall gpiozero
   ```

4. **Verify GPIO access:**

   ```bash
   # Check if gpio group exists
   groups
   
   # Add user to gpio group if needed
   sudo usermod -a -G gpio $USER
   # Log out and back in for changes to take effect
   ```

5. **If running on a non-Raspberry Pi system:**

   This script requires actual Raspberry Pi hardware. It cannot run on:
   - macOS
   - Windows
   - Linux systems without Raspberry Pi hardware
   - Virtual machines (unless specifically configured for GPIO passthrough)

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
   ls -l /home/pi/photo-portal-device/gpio_service.py
   ```

3. **Test script manually:**

   ```bash
   python3 /home/pi/photo-portal-device/gpio_service.py
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
- [Hardware Wiring Guide](docs/hardware-wiring.md)

**Quick Pin Reference:**

| Component | GPIO Pin | Physical Pin | Description |
|-----------|----------|--------------|-------------|
| LED Push Button (LED contacts) | 17 | 11 | Message indicator (PWM, built-in 200Ω resistor) |
| LED Push Button (button contacts) | 18 | 12 | Select/Message button (shows message in Slideshow Mode, sets boundary filter in Map View) |
| Map Toggle | 27 | 13 | SPDT switch |
| Metadata Toggle | 22 | 15 | SPDT switch |
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
