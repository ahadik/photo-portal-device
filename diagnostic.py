#!/usr/bin/env python3
"""
Photo Portal GPIO Diagnostic Script

This script monitors all GPIO inputs on the Raspberry Pi and logs their state
changes to the console. Use this to verify physical switches and buttons are
wired correctly.

Based on GPIO pin assignments from technical_architecture.md:
- GPIO 18: Like button (momentary, pull-up)
- GPIO 27: Map view toggle (SPDT, pull-up)
- GPIO 22: Metadata overlay toggle (SPDT, pull-up)
- GPIO 23: Message view button (momentary, pull-up)
- ADS1115 (I2C): Potentiometer (zoom control)
"""

import time
import sys
import threading
from datetime import datetime

try:
    from gpiozero import DigitalInputDevice, PWMOutputDevice  # type: ignore
    import warnings
    # Suppress PinFactoryFallback warnings - we'll handle errors explicitly
    warnings.filterwarnings('ignore', category=UserWarning, module='gpiozero')
except ImportError:
    print("ERROR: gpiozero library not found.")
    print("This script requires gpiozero, which is only available on Raspberry Pi.")
    print("Install it with: pip3 install gpiozero")
    sys.exit(1)

try:
    import board  # type: ignore
    import busio  # type: ignore
    from adafruit_ads1x15 import ADS1115, AnalogIn, ads1x15  # type: ignore
    ADC_AVAILABLE = True
except ImportError:
    ADC_AVAILABLE = False
    print("WARNING: adafruit-circuitpython-ads1x15 not available. ADC functionality disabled.")

# GPIO Pin Assignments (from technical_architecture.md)
GPIO_LED = 17
GPIO_LIKE_BUTTON = 18
GPIO_MAP_TOGGLE = 27
GPIO_METADATA_TOGGLE = 22
GPIO_MESSAGE_BUTTON = 23

# LED fade control
led_device = None
fade_active = False
fade_lock = threading.Lock()

# ADC configuration
ADC_I2C_ADDRESS = 0x48  # Default ADS1115 address
ADC_POLL_RATE = 10  # Hz (10Hz = 100ms interval)
ADC_CHANGE_THRESHOLD = 0.02  # 2% of full range

# ADC state
adc_reader_thread = None
adc_running = False
adc_lock = threading.Lock()
last_adc_value = 0.0

# Input configurations
INPUTS = {
    'Like Button': {
        'pin': GPIO_LIKE_BUTTON,
        'type': 'momentary',
        'device': None
    },
    'Map Toggle': {
        'pin': GPIO_MAP_TOGGLE,
        'type': 'switch',
        'device': None
    },
    'Metadata Toggle': {
        'pin': GPIO_METADATA_TOGGLE,
        'type': 'switch',
        'device': None
    },
    'Message Button': {
        'pin': GPIO_MESSAGE_BUTTON,
        'type': 'momentary',
        'device': None
    }
}


def format_timestamp():
    """Return formatted timestamp for logging."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def log_state_change(name, pin, state, input_type):
    """Log a state change event."""
    state_str = "PRESSED/ON" if state else "RELEASED/OFF"
    type_str = "button" if input_type == 'momentary' else "switch"
    print(f"[{format_timestamp()}] {name} (GPIO {pin:2d}) [{type_str}] -> {state_str}")


def log_initial_state(name, pin, state, input_type):
    """Log initial state on startup."""
    state_str = "PRESSED/ON" if state else "RELEASED/OFF"
    type_str = "button" if input_type == 'momentary' else "switch"
    print(f"[{format_timestamp()}] {name} (GPIO {pin:2d}) [{type_str}] -> {state_str} (initial state)")


def log_adc_change(value, raw_value=None):
    """Log ADC value change."""
    if raw_value is not None:
        print(f"[{format_timestamp()}] ADC (Potentiometer) -> {value:.3f} (raw: {raw_value})")
    else:
        print(f"[{format_timestamp()}] ADC (Potentiometer) -> {value:.3f}")


def fade_led_loop():
    """Fade LED in and out continuously while fade_active is True."""
    global fade_active, led_device
    
    fade_duration = 2.0  # seconds for full fade in/out cycle
    steps = 100  # number of steps in fade
    step_delay = fade_duration / steps
    
    while True:
        with fade_lock:
            should_fade = fade_active
        
        if not should_fade:
            # Turn off LED when not fading
            if led_device:
                led_device.value = 0
            time.sleep(0.1)
            continue
        
        # Fade in
        for i in range(steps + 1):
            with fade_lock:
                if not fade_active:
                    break
                if led_device:
                    # PWM value from 0.0 to 1.0
                    led_device.value = i / steps
            time.sleep(step_delay)
        
        # Fade out
        for i in range(steps, -1, -1):
            with fade_lock:
                if not fade_active:
                    break
                if led_device:
                    led_device.value = i / steps
            time.sleep(step_delay)


def create_activated_handler(name, pin, input_type):
    """Create handler for when input becomes active (pressed/on)."""
    def handler():
        global fade_active
        log_state_change(name, pin, True, input_type)  # True = pressed/on
        
        # Start LED fade when Like button is pressed
        if name == 'Like Button':
            with fade_lock:
                fade_active = True
            print(f"[{format_timestamp()}] LED fade started")
    
    return handler


def create_deactivated_handler(name, pin, input_type):
    """Create handler for when input becomes inactive (released/off)."""
    def handler():
        global fade_active
        log_state_change(name, pin, False, input_type)  # False = released/off
        
        # Stop LED fade when Like button is released
        if name == 'Like Button':
            with fade_lock:
                fade_active = False
            print(f"[{format_timestamp()}] LED fade stopped")
    
    return handler


def setup_led():
    """Initialize LED with PWM output."""
    global led_device
    
    try:
        led_device = PWMOutputDevice(GPIO_LED, initial_value=0.0, frequency=1000)
        print(f"LED (GPIO {GPIO_LED}) initialized with PWM")
        return True
    except Exception as e:
        error_msg = str(e)
        if "SOC peripheral base address" in error_msg or "lgpio" in error_msg.lower():
            print(f"ERROR: Failed to initialize LED on GPIO {GPIO_LED}: {e}")
            print("  This usually means you're not running on a Raspberry Pi, or GPIO libraries aren't configured.")
            print("  This script must be run on a Raspberry Pi with proper GPIO access.")
            print("  If you are on a Raspberry Pi, try: sudo apt install python3-lgpio")
        else:
            print(f"ERROR: Failed to initialize LED on GPIO {GPIO_LED}: {e}")
        return False


def adc_reader_loop():
    """Read ADC potentiometer value continuously and log changes."""
    global last_adc_value, adc_running
    
    if not ADC_AVAILABLE:
        return
    
    try:
        # Initialize I2C and ADS1115
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS1115(i2c, address=ADC_I2C_ADDRESS)
        chan = AnalogIn(ads, ads1x15.Pin.A0)  # Channel A0
        
        print(f"[{format_timestamp()}] ADC (ADS1115) initialized on I2C address 0x{ADC_I2C_ADDRESS:02X}")
        
        # Read and log initial value
        raw_value = chan.value
        normalized_value = raw_value / 32767.0
        with adc_lock:
            last_adc_value = normalized_value
        print(f"[{format_timestamp()}] ADC (Potentiometer) -> {normalized_value:.3f} (raw: {raw_value}) (initial value)")
        
        poll_interval = 1.0 / ADC_POLL_RATE  # 100ms for 10Hz
        
        adc_running = True
        while adc_running:
            try:
                # Read raw ADC value (0-32767 for 16-bit)
                raw_value = chan.value
                
                # Normalize to 0.0-1.0
                normalized_value = raw_value / 32767.0
                
                # Check if change exceeds threshold
                with adc_lock:
                    change = abs(normalized_value - last_adc_value)
                    
                    if change >= ADC_CHANGE_THRESHOLD:
                        last_adc_value = normalized_value
                        log_adc_change(normalized_value, raw_value)
                
                time.sleep(poll_interval)
                
            except Exception as e:
                print(f"[{format_timestamp()}] ERROR: Error reading ADC: {e}")
                time.sleep(poll_interval)
                
    except Exception as e:
        print(f"[{format_timestamp()}] ERROR: Failed to initialize ADC: {e}")
        adc_running = False


def start_adc_reader():
    """Start ADC reader in background thread."""
    global adc_reader_thread
    
    if not ADC_AVAILABLE:
        print("WARNING: ADC not available, skipping ADC reader thread")
        return
    
    adc_reader_thread = threading.Thread(target=adc_reader_loop, daemon=True)
    adc_reader_thread.start()
    print("ADC reader thread started")


def setup_inputs():
    """Initialize all GPIO inputs with pull-up resistors."""
    print("=" * 70)
    print("Photo Portal GPIO Diagnostic Tool")
    print("=" * 70)
    print("\nInitializing GPIO outputs...")
    setup_led()
    print("\nInitializing GPIO inputs...")
    print(f"All inputs configured with pull-up resistors (active LOW)\n")
    
    if ADC_AVAILABLE:
        print("Initializing ADC (ADS1115)...")
        print(f"ADC configured: I2C address 0x{ADC_I2C_ADDRESS:02X}, Channel A0")
        print(f"Poll rate: {ADC_POLL_RATE}Hz, Change threshold: {ADC_CHANGE_THRESHOLD*100:.1f}%\n")
    
    for name, config in INPUTS.items():
        pin = config['pin']
        input_type = config['type']
        
        try:
            # Create DigitalInputDevice with pull-up (pull_up=True)
            # With pull-up: False = active/pressed, True = inactive/released
            device = DigitalInputDevice(pin, pull_up=True, bounce_time=0.05)
            config['device'] = device
            
            # Set up event handlers
            # when_activated fires when pin becomes False (pressed/on)
            # when_deactivated fires when pin becomes True (released/off)
            device.when_activated = create_activated_handler(name, pin, input_type)
            device.when_deactivated = create_deactivated_handler(name, pin, input_type)
            
            # Log initial state
            # device.value is False when pressed/on, True when released/off
            initial_state = not device.value  # Invert: True = pressed/on, False = released/off
            log_initial_state(name, pin, initial_state, input_type)
            
        except Exception as e:
            error_msg = str(e)
            if "SOC peripheral base address" in error_msg or "lgpio" in error_msg.lower():
                print(f"ERROR: Failed to initialize {name} on GPIO {pin}: {e}")
                print(f"  This usually means you're not running on a Raspberry Pi, or GPIO libraries aren't configured.")
                if name == 'Like Button':  # Only print help message once
                    print("  This script must be run on a Raspberry Pi with proper GPIO access.")
                    print("  If you are on a Raspberry Pi, try: sudo apt install python3-lgpio")
            else:
                print(f"ERROR: Failed to initialize {name} on GPIO {pin}: {e}")
            config['device'] = None
    
    print("\n" + "=" * 70)
    print("Monitoring GPIO inputs and ADC... (Press Ctrl+C to exit)")
    print("=" * 70 + "\n")


def main():
    """Main diagnostic loop."""
    global led_device
    
    try:
        setup_inputs()
        
        # Start LED fade loop in background thread
        fade_thread = threading.Thread(target=fade_led_loop, daemon=True)
        fade_thread.start()
        print("LED fade thread started")
        
        # Start ADC reader thread
        start_adc_reader()
        print()
        
        # Keep the script running and monitor inputs
        while True:
            time.sleep(0.1)  # Small sleep to prevent CPU spinning
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("Shutting down...")
        print("=" * 70)
        
        # Stop LED fade
        with fade_lock:
            fade_active = False
        
        # Stop ADC reader
        global adc_running
        adc_running = False
        if adc_reader_thread and adc_reader_thread.is_alive():
            adc_reader_thread.join(timeout=2.0)
            print("ADC reader thread stopped")
        
        # Clean up GPIO resources
        if led_device:
            try:
                led_device.value = 0
                led_device.close()
                print(f"Closed LED (GPIO {GPIO_LED})")
            except Exception as e:
                print(f"Error closing LED: {e}")
        
        for name, config in INPUTS.items():
            if config['device']:
                try:
                    config['device'].close()
                    print(f"Closed {name} (GPIO {config['pin']})")
                except Exception as e:
                    print(f"Error closing {name}: {e}")
        
        print("\nDiagnostic script terminated.")
        
    except Exception as e:
        print(f"\nERROR: Unexpected error occurred: {e}")
        raise


if __name__ == '__main__':
    main()
