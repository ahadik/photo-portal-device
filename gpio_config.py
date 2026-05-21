#!/usr/bin/env python3
"""
Photo Portal GPIO Configuration

Centralized GPIO pin assignments and hardware configuration.
All GPIO pin assignments match hardware-wiring.md.

This module should be imported by both diagnostic.py and gpio_service.py
to ensure consistent pin assignments across all scripts.
"""

# GPIO Pin Assignments (from hardware-wiring.md)
GPIO_LED = 17  # LED Push Button LED contacts (PWM output)
GPIO_SELECT_BUTTON = 18  # LED Push Button button contacts (input)
GPIO_MAP_TOGGLE = 27  # Map Toggle Switch (SPDT, input)
GPIO_METADATA_TOGGLE = 22  # Metadata Toggle Switch (SPDT, input)

# ADC Configuration (ADS1115)
ADC_I2C_ADDRESS = 0x48  # Default ADS1115 I2C address
ADC_POLL_RATE = 10  # Hz (10Hz = 100ms interval)
ADC_CHANGE_THRESHOLD = 0.02  # 2% of full range (0.0-1.0)

