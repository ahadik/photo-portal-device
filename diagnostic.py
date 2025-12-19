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
from datetime import datetime

try:
    from gpiozero import DigitalInputDevice  # type: ignore
except ImportError:
    print("ERROR: gpiozero library not found.")
    print("This script requires gpiozero, which is only available on Raspberry Pi.")
    print("Install it with: pip3 install gpiozero")
    sys.exit(1)

# GPIO Pin Assignments (from technical_architecture.md)
GPIO_LIKE_BUTTON = 18
GPIO_MAP_TOGGLE = 27
GPIO_METADATA_TOGGLE = 22
GPIO_MESSAGE_BUTTON = 23

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


def create_activated_handler(name, pin, input_type):
    """Create handler for when input becomes active (pressed/on)."""
    def handler():
        log_state_change(name, pin, True, input_type)  # True = pressed/on
    return handler


def create_deactivated_handler(name, pin, input_type):
    """Create handler for when input becomes inactive (released/off)."""
    def handler():
        log_state_change(name, pin, False, input_type)  # False = released/off
    return handler


def setup_inputs():
    """Initialize all GPIO inputs with pull-up resistors."""
    print("=" * 70)
    print("Photo Portal GPIO Diagnostic Tool")
    print("=" * 70)
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
    try:
        setup_inputs()
        
        # Keep the script running and monitor inputs
        while True:
            time.sleep(0.1)  # Small sleep to prevent CPU spinning
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("Shutting down...")
        print("=" * 70)
        
        # Clean up GPIO resources
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
