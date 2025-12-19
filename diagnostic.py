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
"""

import time
import sys
import threading
from datetime import datetime

try:
    from gpiozero import DigitalInputDevice, PWMOutputDevice  # type: ignore
except ImportError:
    print("ERROR: gpiozero library not found.")
    print("This script requires gpiozero, which is only available on Raspberry Pi.")
    print("Install it with: pip3 install gpiozero")
    sys.exit(1)

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
        print(f"ERROR: Failed to initialize LED on GPIO {GPIO_LED}: {e}")
        return False


def setup_inputs():
    """Initialize all GPIO inputs with pull-up resistors."""
    print("=" * 70)
    print("Photo Portal GPIO Diagnostic Tool")
    print("=" * 70)
    print("\nInitializing GPIO outputs...")
    setup_led()
    print("\nInitializing GPIO inputs...")
    print(f"All inputs configured with pull-up resistors (active LOW)\n")
    
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
            print(f"ERROR: Failed to initialize {name} on GPIO {pin}: {e}")
            config['device'] = None
    
    print("\n" + "=" * 70)
    print("Monitoring GPIO inputs... (Press Ctrl+C to exit)")
    print("=" * 70 + "\n")


def main():
    """Main diagnostic loop."""
    global led_device
    
    try:
        setup_inputs()
        
        # Start LED fade loop in background thread
        fade_thread = threading.Thread(target=fade_led_loop, daemon=True)
        fade_thread.start()
        print("LED fade thread started\n")
        
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
