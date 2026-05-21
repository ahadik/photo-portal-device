# Photo Portal Hardware Wiring Guide

This document describes the physical hardware components required for the Photo Portal device and how to wire them to a Raspberry Pi.

## Prerequisites

- Raspberry Pi 4 or 5 running Raspberry Pi OS (64-bit)
- Basic soldering skills (recommended) or breadboard for prototyping
- Basic understanding of GPIO pinouts

## Hardware Components

### Required Components

1. **LED Push Button** - Arcade-style push button with built-in LED (e.g., [Adafruit Arcade Button with LED - 30mm](https://www.adafruit.com/product/3491))
   - Has built-in 200Ω resistor for LED, so no external resistor needed
   - Includes both switch contacts (for button functionality) and LED contacts (for LED control)
   - **Note:** This single component serves multiple purposes:
     - LED contacts are wired to GPIO 17 for visual message indicator
     - Button switch contacts are wired to GPIO 18 for Select/Message button functionality
     - In Slideshow Mode: Shows the most recent message when pressed
     - In Map View: Sets the current map viewport as a boundary filter for the slideshow when pressed
2. **Map Toggle Switch** - SPDT (Single Pole Double Throw) toggle switch
3. **Metadata Toggle Switch** - SPDT toggle switch
4. **ADS1115 ADC Module** - 16-bit analog-to-digital converter breakout board
5. **Potentiometer** - 10kΩ linear potentiometer (for zoom control)

**Note:** If you prefer to use a separate LED and button instead of an LED push button, you'll need:
- Standard 5mm LED (any color)
- 330Ω Resistor - For LED current limiting (required for separate LED)

## GPIO Pin Assignments

| Component | GPIO Pin | Physical Pin | Description |
|-----------|----------|--------------|-------------|
| LED Push Button (LED contacts) | 17 | 11 | Message indicator (PWM output, built-in 200Ω resistor) |
| LED Push Button (button contacts) | 18 | 12 | Select/Message button (input) |
| Map Toggle | 27 | 13 | SPDT switch (input) |
| Metadata Toggle | 22 | 15 | SPDT switch (input) |
| ADS1115 SDA | 2 | 3 | I2C data line |
| ADS1115 SCL | 3 | 5 | I2C clock line |

**Note:** Physical pin numbers refer to the Raspberry Pi GPIO header pinout. GPIO pins use BCM numbering.

## Wiring Instructions

### LED Push Button (GPIO 17 for LED, GPIO 18 for Button)

The LED push button is a single component that serves dual purposes: it provides both a visual LED indicator and a push button switch. The LED and button switch have separate contacts that are wired independently.

**Wiring for LED Contacts (GPIO 17):**
1. Connect the **LED positive** contact (usually marked or one of the LED terminals) to **GPIO 17** (physical pin 11)
2. Connect the **LED negative** contact (the other LED terminal) to **GND** (any ground pin, e.g., physical pin 6, 9, 14, 20, 25, 30, 34, or 39)

**Circuit Diagram for LED:**
```
GPIO 17 (Pin 11) → [LED Push Button LED+] → [Built-in 200Ω Resistor] → [LED Push Button LED-] → GND
```

**Wiring for Button Switch Contacts (GPIO 18 - Select Button):**
1. Connect one **switch terminal** of the button to **GPIO 18** (physical pin 12)
2. Connect the other **switch terminal** of the button to **GND**

**Circuit Diagram for Button:**
```
GPIO 18 (Pin 12) → [LED Push Button Switch Terminal 1] → [LED Push Button Switch Terminal 2] → GND
```

**Notes:**
- The LED uses PWM (Pulse Width Modulation) for brightness control
- The built-in 200Ω resistor limits current to protect both the LED and GPIO pin
- The LED will fade in and out when a new message is waiting
- At 5V, the LED draws approximately 10mA; at 3.3V, it draws approximately 2mA (dimmer)
- The button switch contacts are wired separately to GPIO 18 and function as the Select button
- The button uses an internal pull-up resistor (configured in software)
- When pressed, the GPIO pin is pulled LOW (active LOW)

**Alternative: Using a Separate LED and Button**

If you prefer to use a separate LED and button instead of an LED push button:

**Wiring for Separate LED:**
1. Connect the **anode** (longer leg, positive) of the LED to one end of a **330Ω resistor**
2. Connect the other end of the resistor to **GPIO 17** (physical pin 11)
3. Connect the **cathode** (shorter leg, negative) of the LED to **GND**

**Circuit Diagram for Separate LED:**
```
GPIO 17 (Pin 11) → [330Ω Resistor] → [LED Anode] → [LED Cathode] → GND
```

**Notes for Separate LED:**
- Always use a current-limiting resistor (330Ω recommended) to protect the LED and GPIO pin
- The LED with 330Ω resistor draws approximately 10mA at full brightness

### Select/Message Button Functionality

The button switch contacts of the LED push button (wired to GPIO 18) function as both the Select button and Message button with context-dependent behavior:
- **In Slideshow Mode:** Shows the most recent message when pressed
- **In Map View:** Sets the current map viewport as a boundary filter for the slideshow when pressed

**Note:** The wiring for the Select/Message button is described in the LED Push Button section above, as they are part of the same physical component.

### Map Toggle Switch (GPIO 27)

An SPDT toggle switch to show/hide the map overlay.

**Wiring:**
1. Connect the **common** (center) terminal of the switch to **GPIO 27** (physical pin 13)
2. Connect one of the **outer** terminals to **GND**
3. Leave the other outer terminal unconnected (or connect to 3.3V if you want inverted logic)

**Circuit Diagram:**
```
GPIO 27 (Pin 13) → [Switch Common Terminal]
                    ↓
              [Terminal 1] → GND
              [Terminal 2] → (unconnected or 3.3V)
```

**Notes:**
- The switch uses an internal pull-up resistor (configured in software)
- When switched to GND position: GPIO reads LOW (ON state)
- When switched to other position: GPIO reads HIGH (OFF state)
- The switch state is tracked and sent to the webapp

### Metadata Toggle Switch (GPIO 22)

An SPDT toggle switch to show/hide the metadata overlay.

**Wiring:**
1. Connect the **common** (center) terminal of the switch to **GPIO 22** (physical pin 15)
2. Connect one of the **outer** terminals to **GND**
3. Leave the other outer terminal unconnected (or connect to 3.3V if you want inverted logic)

**Circuit Diagram:**
```
GPIO 22 (Pin 15) → [Switch Common Terminal]
                     ↓
               [Terminal 1] → GND
               [Terminal 2] → (unconnected or 3.3V)
```

**Notes:**
- Same configuration as Map Toggle Switch
- Uses internal pull-up resistor
- Sends toggle events to the webapp

### ADS1115 ADC Module (for Potentiometer)

The ADS1115 is a 16-bit analog-to-digital converter that allows reading analog values from a potentiometer for zoom control.

**Wiring:**
1. **VDD** (power) → **3.3V** (physical pin 1 or 17)
2. **GND** → **GND** (any ground pin)
3. **SDA** (data) → **GPIO 2** (physical pin 3) - This is the I2C data line
4. **SCL** (clock) → **GPIO 3** (physical pin 5) - This is the I2C clock line

**Potentiometer Wiring (if using):**
1. Connect one outer terminal of the potentiometer to **3.3V**
2. Connect the other outer terminal to **GND**
3. Connect the **wiper** (center terminal) to **A0** on the ADS1115

**Circuit Diagram:**
```
Raspberry Pi:
  3.3V (Pin 1) → ADS1115 VDD
  GND (Pin 6)  → ADS1115 GND
  GPIO 2 (Pin 3) → ADS1115 SDA
  GPIO 3 (Pin 5) → ADS1115 SCL

Potentiometer:
  3.3V → [Pot Terminal 1]
  GND  → [Pot Terminal 2]
  [Pot Wiper] → ADS1115 A0
```

**Notes:**
- I2C must be enabled on the Raspberry Pi (use `raspi-config`)
- Default I2C address for ADS1115 is `0x48`
- The ADC reads values from 0.0 to 1.0 (normalized)
- The potentiometer provides zoom control for the photo display

## Complete Wiring Diagram

```
                    Raspberry Pi GPIO Header
                    ┌─────────────────────┐
                    │ 1  2  3  4  5  6   │
                    │ 7  8  9 10 11 12   │
                    │13 14 15 16 17 18   │
                    │19 20 21 22 23 24   │
                    │25 26 27 28 29 30   │
                    │31 32 33 34 35 36   │
                    │37 38 39 40         │
                    └─────────────────────┘

Connections:
  Pin 1  (3.3V)  → ADS1115 VDD
  Pin 3  (GPIO 2/SDA) → ADS1115 SDA
  Pin 5  (GPIO 3/SCL) → ADS1115 SCL
  Pin 6  (GND)   → Common ground for all components
  Pin 11 (GPIO 17) → LED Push Button LED+ → [Built-in 200Ω] → LED Push Button LED- → GND
  Pin 12 (GPIO 18) → LED Push Button Switch Terminal 1 → LED Push Button Switch Terminal 2 → GND
  Pin 13 (GPIO 27) → Map Toggle (common) → (terminal 1 → GND)
  Pin 15 (GPIO 22) → Metadata Toggle (common) → (terminal 1 → GND)
```

## Power Considerations

- All GPIO pins operate at **3.3V** logic levels
- Maximum current per GPIO pin: **16mA** (recommended: <10mA)
- The LED push button with built-in 200Ω resistor draws approximately **10mA** at 5V or **2mA** at 3.3V (dimmer) at full brightness
- If using a separate LED with 330Ω resistor, it draws approximately **10mA** at full brightness
- Buttons and switches draw minimal current (microamps) when not pressed
- The ADS1115 draws approximately **150µA** in normal operation

## Testing Your Wiring

After completing the wiring, use the diagnostic script to verify all connections:

```bash
cd /path/to/photo-portal-device
source venv/bin/activate
python3 diagnostic.py
```

The diagnostic script will:
- Test LED PWM output (fades when Select button is pressed)
- Monitor all button and switch inputs
- Read ADC potentiometer values (if connected)
- Log all state changes with timestamps

## Troubleshooting

### LED Not Working
- **For LED Push Button:**
  - Verify the LED contacts are connected correctly (LED+ to GPIO, LED- to GND)
  - The built-in 200Ω resistor is already included, so no external resistor is needed
  - Test LED with a multimeter or by connecting directly to 3.3V or 5V
- **For Separate LED:**
  - Verify the LED polarity (anode to GPIO, cathode to GND)
  - Check that the resistor is connected (330Ω recommended)
  - Test LED with a multimeter or by connecting directly to 3.3V (with resistor)

### Buttons/Switches Not Responding
- Verify connections to correct GPIO pins
- Check that one terminal connects to GND
- Ensure buttons/switches are making good contact
- Use a multimeter to test continuity

### ADC Not Detected
- Verify I2C is enabled: `sudo raspi-config` → Interface Options → I2C
- Check I2C device detection: `sudo i2cdetect -y 1` (should show `0x48`)
- Verify wiring: SDA to GPIO 2, SCL to GPIO 3, VDD to 3.3V, GND to GND
- Ensure ADS1115 is powered (check VDD connection)

### GPIO Permission Errors
- Add user to gpio group: `sudo usermod -a -G gpio $USER`
- Log out and back in, or run: `newgrp gpio`

## Safety Notes

⚠️ **Important Safety Warnings:**

1. **Never connect more than 3.3V to any GPIO pin** - Higher voltages will damage the Raspberry Pi
2. **Always use current-limiting resistors** for LEDs and other components
   - LED push buttons with built-in resistors (like the Adafruit model) don't need external resistors
   - Separate LEDs require external current-limiting resistors (330Ω recommended)
3. **Double-check all connections** before powering on the Raspberry Pi
4. **Use proper wire gauge** - 22-24 AWG is recommended for breadboard/prototyping
5. **Avoid short circuits** - Ensure no bare wires can touch each other
6. **Power off the Raspberry Pi** before making or changing connections

## Additional Resources

- [Raspberry Pi GPIO Pinout](https://pinout.xyz/)
- [gpiozero Documentation](https://gpiozero.readthedocs.io/)
- [ADS1115 Datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf)
- [Raspberry Pi GPIO Electrical Specifications](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header)

