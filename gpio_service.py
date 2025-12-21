#!/usr/bin/env python3
"""
Photo Portal GPIO Service

WebSocket service that bridges physical hardware (GPIO pins, ADC) with the
React webapp. Monitors hardware inputs, reads analog values, controls the LED,
and communicates bidirectional events via WebSocket.
"""

import asyncio
import json
import logging
import signal
import sys
import threading
import time
from typing import Dict, Optional, Set

try:
    from gpiozero import DigitalInputDevice, PWMOutputDevice  # type: ignore
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

try:
    import websockets  # type: ignore
except ImportError:
    print("ERROR: websockets library not found.")
    print("Install it with: pip3 install websockets")
    sys.exit(1)

# GPIO Pin Assignments (from technical_architecture.md)
GPIO_LED = 17
GPIO_LIKE_BUTTON = 18
GPIO_MAP_TOGGLE = 27
GPIO_METADATA_TOGGLE = 22
GPIO_MESSAGE_BUTTON = 23

# WebSocket configuration
WS_HOST = "localhost"
WS_PORT = 8765

# ADC configuration
ADC_I2C_ADDRESS = 0x48  # Default ADS1115 address
ADC_POLL_RATE = 10  # Hz (10Hz = 100ms interval)
ADC_CHANGE_THRESHOLD = 0.02  # 2% of full range
# Note: ADC_CHANNEL will be set after imports are available

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
led_device: Optional[PWMOutputDevice] = None
input_devices: Dict[str, Optional[DigitalInputDevice]] = {}
adc_reader_thread: Optional[threading.Thread] = None
adc_running = False
adc_lock = threading.Lock()
last_adc_value = 0.0
connected_clients: Set = set()  # Set of WebSocket connections
clients_lock: Optional[asyncio.Lock] = None  # Will be initialized in websocket_server
event_queue: Optional[asyncio.Queue] = None  # Queue for events from threads
websocket_loop: Optional[asyncio.AbstractEventLoop] = None  # Store reference to event loop
switch_states: Dict[str, str] = {}  # Track switch states for MAP_TOGGLE and METADATA_TOGGLE


def broadcast_event(event: dict) -> None:
    """Broadcast a GPIO event to all connected WebSocket clients (called from thread context)."""
    if not event_queue:
        logger.debug("Event queue not initialized, skipping broadcast")
        return
    
    if not connected_clients:
        logger.debug("No connected clients, skipping broadcast")
        return
    
    message = json.dumps(event)
    
    # Put message in queue (thread-safe)
    try:
        if websocket_loop and websocket_loop.is_running():
            asyncio.run_coroutine_threadsafe(event_queue.put(message), websocket_loop)
            logger.debug(f"Queued event: {event.get('type')}")
        else:
            logger.warning("WebSocket loop not running, cannot queue event")
    except Exception as e:
        logger.warning(f"Error queuing event: {e}", exc_info=True)


async def broadcast_worker() -> None:
    """Worker coroutine that processes events from queue and broadcasts to clients."""
    global connected_clients
    
    while True:
        try:
            if not event_queue:
                await asyncio.sleep(0.1)
                continue
                
            message = await event_queue.get()
            
            # Send to all connected clients
            if not clients_lock:
                continue
                
            disconnected = set()
            async with clients_lock:
                for client in connected_clients.copy():
                    try:
                        await client.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(client)
                    except Exception as e:
                        logger.warning(f"Error sending message to client: {e}")
                        disconnected.add(client)
                
                # Remove disconnected clients
                connected_clients -= disconnected
                
        except Exception as e:
            logger.error(f"Error in broadcast worker: {e}")


def create_gpio_event_handler(input_name: str, event_type: str) -> callable:
    """Create an event handler for GPIO inputs that broadcasts WebSocket events."""
    def handler():
        if input_name == 'MAP_TOGGLE':
            # For MAP_TOGGLE switch, track state and send ON/OFF
            device = input_devices.get(input_name)
            if device:
                # device.value is False when active, True when inactive
                state = "OFF" if device.value else "ON"
                switch_states[input_name] = state
                event = {"type": event_type, "value": state}
                logger.info(f"GPIO event: {input_name} -> {state}")
                broadcast_event(event)
        else:
            # For buttons and METADATA_TOGGLE, just send the event (no state value)
            # Note: METADATA_TOGGLE is a switch but sends toggle events without value
            event = {"type": event_type}
            logger.info(f"GPIO event: {input_name} triggered")
            broadcast_event(event)
    
    return handler


def setup_led() -> bool:
    """Initialize LED with PWM output."""
    global led_device
    
    try:
        led_device = PWMOutputDevice(GPIO_LED, initial_value=0.0, frequency=1000)
        logger.info(f"LED (GPIO {GPIO_LED}) initialized with PWM")
        return True
    except Exception as e:
        error_msg = str(e)
        if "busy" in error_msg.lower():
            logger.error(f"Failed to initialize LED on GPIO {GPIO_LED}: {e}")
            logger.error("  GPIO pin is already in use. Another process may be using it.")
            logger.error("  Try: sudo lsof | grep gpio  or  sudo fuser /dev/gpiochip*")
            logger.error("  Or restart the service: sudo systemctl restart photoportal-gpio.service")
        else:
            logger.error(f"Failed to initialize LED on GPIO {GPIO_LED}: {e}")
        return False


def set_led_state(value: str) -> None:
    """Set LED state (ON or OFF)."""
    global led_device
    
    if not led_device:
        logger.warning("LED device not initialized")
        return
    
    try:
        if value.upper() == "ON":
            led_device.value = 1.0
            logger.info("LED turned ON")
        elif value.upper() == "OFF":
            led_device.value = 0.0
            logger.info("LED turned OFF")
        else:
            logger.warning(f"Invalid LED value: {value}")
    except Exception as e:
        logger.error(f"Error setting LED state: {e}")


def setup_gpio_inputs() -> None:
    """Initialize all GPIO inputs with pull-up resistors."""
    input_configs = {
        'LIKE_BUTTON': {
            'pin': GPIO_LIKE_BUTTON,
            'type': 'button',
            'event_type': 'LIKE_BUTTON'
        },
        'MAP_TOGGLE': {
            'pin': GPIO_MAP_TOGGLE,
            'type': 'switch',
            'event_type': 'MAP_TOGGLE'
        },
        'METADATA_TOGGLE': {
            'pin': GPIO_METADATA_TOGGLE,
            'type': 'switch',
            'event_type': 'METADATA_TOGGLE'
        },
        'MESSAGE_BUTTON': {
            'pin': GPIO_MESSAGE_BUTTON,
            'type': 'button',
            'event_type': 'MESSAGE_BUTTON'
        }
    }
    
    for name, config in input_configs.items():
        pin = config['pin']
        event_type = config['event_type']
        
        try:
            # Create DigitalInputDevice with pull-up (pull_up=True)
            # With pull-up: False = active/pressed, True = inactive/released
            device = DigitalInputDevice(pin, pull_up=True, bounce_time=0.05)
            input_devices[name] = device
            
            # Set up event handlers
            # when_activated fires when pin becomes False (pressed/on)
            # when_deactivated fires when pin becomes True (released/off)
            device.when_activated = create_gpio_event_handler(name, event_type)
            
            # For MAP_TOGGLE switch, also handle deactivation to track state changes
            if name == 'MAP_TOGGLE':
                device.when_deactivated = create_gpio_event_handler(name, event_type)
                
                # Initialize switch state
                state = "OFF" if device.value else "ON"
                switch_states[name] = state
                logger.info(f"{name} (GPIO {pin}) initial state: {state}")
            else:
                logger.info(f"{name} (GPIO {pin}) initialized")
            
        except Exception as e:
            error_msg = str(e)
            if "busy" in error_msg.lower():
                logger.error(f"Failed to initialize {name} on GPIO {pin}: {e}")
                if name == 'LIKE_BUTTON':  # Only print help message once
                    logger.error("  GPIO pins are already in use. Another process may be using them.")
                    logger.error("  Try: sudo lsof | grep gpio  or  sudo fuser /dev/gpiochip*")
                    logger.error("  Or restart the service: sudo systemctl restart photoportal-gpio.service")
                    logger.error("  Or stop any other GPIO services/scripts that might be running.")
            elif "SOC peripheral base address" in error_msg or "lgpio" in error_msg.lower():
                logger.error(f"Failed to initialize {name} on GPIO {pin}: {e}")
                if name == 'LIKE_BUTTON':  # Only print help message once
                    logger.error("  This usually means you're not running on a Raspberry Pi, or GPIO libraries aren't configured.")
                    logger.error("  This script must be run on a Raspberry Pi with proper GPIO access.")
                    logger.error("  If you are on a Raspberry Pi, try: sudo apt install python3-lgpio")
            else:
                logger.error(f"Failed to initialize {name} on GPIO {pin}: {e}")
            input_devices[name] = None


def adc_reader_loop() -> None:
    """Read ADC potentiometer value continuously and broadcast changes."""
    global last_adc_value, adc_running
    
    if not ADC_AVAILABLE:
        logger.warning("ADC not available, ADC reader thread exiting")
        return
    
    try:
        # Initialize I2C and ADS1115
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS1115(i2c, address=ADC_I2C_ADDRESS)
        chan = AnalogIn(ads, ads1x15.Pin.A0)  # Channel A0
        
        logger.info("ADC (ADS1115) initialized")
        
        # Read and set initial value
        initial_raw = chan.value
        initial_normalized = initial_raw / 32767.0
        with adc_lock:
            last_adc_value = initial_normalized
        logger.info(f"ADC initial value: {initial_normalized:.3f} (raw: {initial_raw})")
        
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
                        
                        # Broadcast ZOOM_DIAL event
                        event = {"type": "ZOOM_DIAL", "value": normalized_value}
                        logger.info(f"ADC change detected: {normalized_value:.3f} (change: {change:.3f}, raw: {raw_value})")
                        broadcast_event(event)
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error reading ADC: {e}", exc_info=True)
                time.sleep(poll_interval)
                
    except Exception as e:
        logger.error(f"Failed to initialize ADC: {e}", exc_info=True)
        adc_running = False


def start_adc_reader() -> None:
    """Start ADC reader in background thread."""
    global adc_reader_thread
    
    if not ADC_AVAILABLE:
        logger.warning("ADC not available, skipping ADC reader thread")
        return
    
    adc_reader_thread = threading.Thread(target=adc_reader_loop, daemon=True)
    adc_reader_thread.start()
    logger.info("ADC reader thread started")


async def send_initial_states(websocket) -> None:
    """Send initial states of all inputs to a newly connected client."""
    # Send MAP_TOGGLE initial state
    if 'MAP_TOGGLE' in switch_states:
        state = switch_states['MAP_TOGGLE']
        event = {"type": "MAP_TOGGLE", "value": state}
        await websocket.send(json.dumps(event))
        logger.debug(f"Sent initial MAP_TOGGLE state: {state}")
    
    # Send ADC initial value if ADC is available
    # Note: last_adc_value starts at 0.0, which is a valid initial state
    if ADC_AVAILABLE:
        with adc_lock:
            event = {"type": "ZOOM_DIAL", "value": last_adc_value}
            await websocket.send(json.dumps(event))
            logger.debug(f"Sent initial ZOOM_DIAL value: {last_adc_value:.3f}")


async def handle_client(websocket) -> None:
    """Handle a WebSocket client connection."""
    global connected_clients
    
    async with clients_lock:
        connected_clients.add(websocket)
    logger.info(f"Client connected (total clients: {len(connected_clients)})")
    
    # Send initial states to the newly connected client
    try:
        await send_initial_states(websocket)
    except Exception as e:
        logger.warning(f"Error sending initial states to client: {e}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle LED command
                if data.get("type") == "LED":
                    value = data.get("value")
                    if value in ("ON", "OFF"):
                        # Set LED state (runs in thread-safe context)
                        set_led_state(value)
                    else:
                        logger.warning(f"Invalid LED value: {value}")
                else:
                    logger.warning(f"Unknown command type: {data.get('type')}")
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {message}")
            except Exception as e:
                logger.error(f"Error handling client message: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error in client handler: {e}")
    finally:
        async with clients_lock:
            connected_clients.discard(websocket)
        logger.info(f"Client removed (remaining clients: {len(connected_clients)})")


async def websocket_server() -> None:
    """Run the WebSocket server."""
    global event_queue, websocket_loop, clients_lock
    
    websocket_loop = asyncio.get_event_loop()
    event_queue = asyncio.Queue()
    clients_lock = asyncio.Lock()
    
    # Start broadcast worker
    asyncio.create_task(broadcast_worker())
    
    logger.info(f"Starting WebSocket server on {WS_HOST}:{WS_PORT}")
    
    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        logger.info("WebSocket server started")
        # Keep server running
        await asyncio.Future()  # Run forever


def cleanup() -> None:
    """Clean up GPIO resources."""
    global adc_running, led_device
    
    logger.info("Cleaning up resources...")
    
    # Stop ADC reader
    adc_running = False
    if adc_reader_thread and adc_reader_thread.is_alive():
        adc_reader_thread.join(timeout=2.0)
    
    # Turn off LED
    if led_device:
        try:
            led_device.value = 0.0
            led_device.close()
            logger.info("LED closed")
        except Exception as e:
            logger.error(f"Error closing LED: {e}")
    
    # Close all GPIO inputs
    for name, device in input_devices.items():
        if device:
            try:
                device.close()
                logger.info(f"{name} closed")
            except Exception as e:
                logger.error(f"Error closing {name}: {e}")


def signal_handler(signum, frame) -> None:
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    cleanup()
    sys.exit(0)


def main() -> None:
    """Main entry point."""
    logger.info("Photo Portal GPIO Service starting...")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Setup hardware
        setup_led()
        setup_gpio_inputs()
        start_adc_reader()
        
        # Run WebSocket server (blocks forever)
        asyncio.run(websocket_server())
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        cleanup()


if __name__ == '__main__':
    main()
