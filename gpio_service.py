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
from typing import Any, Callable, Dict, Optional, Set, Union

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

# Import GPIO configuration from shared config file
from gpio_config import (
    GPIO_LED,
    GPIO_SELECT_BUTTON,
    GPIO_MAP_TOGGLE,
    GPIO_METADATA_TOGGLE,
    ADC_I2C_ADDRESS,
    ADC_POLL_RATE,
    ADC_CHANGE_THRESHOLD
)

# WebSocket configuration
WS_HOST = "localhost"
WS_PORT = 8765
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
message_waiting: bool = False  # Track if there's a new message waiting (for button glowing state)
fade_active = False  # Controls LED fade when message is waiting
fade_lock = threading.Lock()  # Lock for fade_active access
fade_thread: Optional[threading.Thread] = None  # LED fade thread


def broadcast_event(event: Dict[str, Any]) -> None:
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
            logger.debug("Queued event: %s", event.get('type'))
        else:
            logger.warning("WebSocket loop not running, cannot queue event")
    except Exception as e:
        logger.warning("Error queuing event: %s", e, exc_info=True)


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
                        logger.warning("Error sending message to client: %s", e)
                        disconnected.add(client)
                
                # Remove disconnected clients
                connected_clients -= disconnected
                
        except Exception as e:
            logger.error("Error in broadcast worker: %s", e)


def create_gpio_event_handler(input_name: str, event_type: str) -> Callable[[], None]:
    """Create an event handler for GPIO inputs that broadcasts WebSocket events."""
    def handler():
        if input_name in ('MAP_TOGGLE', 'METADATA_TOGGLE'):
            # Switches: track position and send ON/OFF so the webapp can mirror state directly
            device = input_devices.get(input_name)
            if device:
                # device.value is False when active, True when inactive
                state = "OFF" if device.value else "ON"
                switch_states[input_name] = state
                event = {"type": event_type, "value": state}
                logger.info("GPIO event: %s -> %s", input_name, state)
                broadcast_event(event)
        else:
            event = {"type": event_type}
            logger.info("GPIO event: %s triggered", input_name)
            broadcast_event(event)
    
    return handler


def setup_led() -> bool:
    """Initialize LED with PWM output."""
    global led_device
    
    try:
        led_device = PWMOutputDevice(GPIO_LED, initial_value=0.0, frequency=1000)
        logger.info("LED (GPIO %d) initialized with PWM", GPIO_LED)
        return True
    except Exception as e:
        error_msg = str(e)
        if "busy" in error_msg.lower():
            logger.error("Failed to initialize LED on GPIO %d: %s", GPIO_LED, e)
            logger.error("  GPIO pin is already in use. Another process may be using it.")
            logger.error("  Try: sudo lsof | grep gpio  or  sudo fuser /dev/gpiochip*")
            logger.error("  Or restart the service: sudo systemctl restart photoportal-gpio.service")
        else:
            logger.error("Failed to initialize LED on GPIO %d: %s", GPIO_LED, e)
        return False


def fade_led_loop() -> None:
    """Fade LED in and out continuously while fade_active is True."""
    
    fade_duration = 2.0  # seconds for full fade in/out cycle
    steps = 100  # number of steps in fade
    step_delay = fade_duration / steps
    
    while True:
        with fade_lock:
            should_fade = fade_active
        
        if not should_fade:
            # Turn off LED when not fading
            if led_device:
                try:
                    led_device.value = 0
                except Exception as e:
                    logger.error("Error setting LED value in fade loop: %s", e)
            time.sleep(0.1)
            continue
        
        # Fade in
        for i in range(steps + 1):
            with fade_lock:
                if not fade_active:
                    break
                if led_device:
                    try:
                        # PWM value from 0.0 to 1.0
                        led_device.value = i / steps
                    except Exception as e:
                        logger.error("Error setting LED value in fade loop: %s", e)
            time.sleep(step_delay)
        
        # Fade out
        for i in range(steps, -1, -1):
            with fade_lock:
                if not fade_active:
                    break
                if led_device:
                    try:
                        led_device.value = i / steps
                    except Exception as e:
                        logger.error("Error setting LED value in fade loop: %s", e)
            time.sleep(step_delay)


def set_led_state(value: str) -> None:
    """Set LED state (ON or OFF). Only works when not fading."""
    
    if not led_device:
        logger.warning("LED device not initialized")
        return
    
    # Don't override LED state if fading is active
    with fade_lock:
        if fade_active:
            logger.debug("LED fade is active, ignoring manual LED state change")
            return
    
    try:
        if value.upper() == "ON":
            led_device.value = 1.0
            logger.info("LED turned ON")
        elif value.upper() == "OFF":
            led_device.value = 0.0
            logger.info("LED turned OFF")
        else:
            logger.warning("Invalid LED value: %s", value)
    except Exception as e:
        logger.error("Error setting LED state: %s", e)


def start_led_fade_thread() -> None:
    """Start LED fade thread in background."""
    global fade_thread
    
    fade_thread = threading.Thread(target=fade_led_loop, daemon=True)
    fade_thread.start()
    logger.info("LED fade thread started")


def setup_gpio_inputs() -> None:
    """Initialize all GPIO inputs with pull-up resistors."""
    input_configs = {
        'SELECT_BUTTON': {
            'pin': GPIO_SELECT_BUTTON,
            'type': 'button',
            'event_type': 'SELECT_BUTTON'
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
        }
    }
    
    for name, config in input_configs.items():
        pin = config['pin']
        event_type: str = str(config['event_type'])
        
        try:
            # Create DigitalInputDevice with pull-up (pull_up=True)
            # With pull-up: False = active/pressed, True = inactive/released
            device = DigitalInputDevice(pin, pull_up=True, bounce_time=0.05)
            input_devices[name] = device
            
            # Set up event handlers
            # when_activated fires when pin becomes False (pressed/on)
            # when_deactivated fires when pin becomes True (released/off)
            device.when_activated = create_gpio_event_handler(name, event_type)
            
            # For switches, also handle deactivation so both positions emit an event
            if name in ('MAP_TOGGLE', 'METADATA_TOGGLE'):
                device.when_deactivated = create_gpio_event_handler(name, event_type)

                # Initialize switch state
                state = "OFF" if device.value else "ON"
                switch_states[name] = state
                logger.info("%s (GPIO %d) initial state: %s", name, pin, state)
            else:
                logger.info("%s (GPIO %d) initialized", name, pin)
            
        except Exception as e:
            error_msg = str(e)
            if "busy" in error_msg.lower():
                logger.error("Failed to initialize %s on GPIO %d: %s", name, pin, e)
                # Print help message only for the first error
                if name == list(input_configs.keys())[0]:
                    logger.error("  GPIO pins are already in use. Another process may be using them.")
                    logger.error("  Try: sudo lsof | grep gpio  or  sudo fuser /dev/gpiochip*")
                    logger.error("  Or restart the service: sudo systemctl restart photoportal-gpio.service")
                    logger.error("  Or stop any other GPIO services/scripts that might be running.")
            elif "SOC peripheral base address" in error_msg or "lgpio" in error_msg.lower():
                logger.error("Failed to initialize %s on GPIO %d: %s", name, pin, e)
                # Print help message only for the first error
                if name == list(input_configs.keys())[0]:
                    logger.error("  This usually means you're not running on a Raspberry Pi, or GPIO libraries aren't configured.")
                    logger.error("  This script must be run on a Raspberry Pi with proper GPIO access.")
                    logger.error("  If you are on a Raspberry Pi, try: sudo apt install python3-lgpio")
            else:
                logger.error("Failed to initialize %s on GPIO %d: %s", name, pin, e)
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
        logger.info("ADC initial value: %.3f (raw: %d)", initial_normalized, initial_raw)
        
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
                        logger.info("ADC change detected: %.3f (change: %.3f, raw: %d)", normalized_value, change, raw_value)
                        broadcast_event(event)
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error("Error reading ADC: %s", e, exc_info=True)
                time.sleep(poll_interval)
                
    except Exception as e:
        logger.error("Failed to initialize ADC: %s", e, exc_info=True)
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
    # Send switch initial states
    for switch_name in ('MAP_TOGGLE', 'METADATA_TOGGLE'):
        if switch_name in switch_states:
            state = switch_states[switch_name]
            event = {"type": switch_name, "value": state}
            await websocket.send(json.dumps(event))
            logger.debug("Sent initial %s state: %s", switch_name, state)
    
    # Send ADC initial value if ADC is available
    # Note: last_adc_value starts at 0.0, which is a valid initial state
    if ADC_AVAILABLE:
        with adc_lock:
            zoom_event: Dict[str, Union[str, float]] = {"type": "ZOOM_DIAL", "value": last_adc_value}
            await websocket.send(json.dumps(zoom_event))
            logger.debug("Sent initial ZOOM_DIAL value: %.3f", last_adc_value)


async def handle_client(websocket) -> None:
    """Handle a WebSocket client connection."""
    global connected_clients, message_waiting, fade_active
    
    if not clients_lock:
        logger.error("clients_lock not initialized")
        return
    
    async with clients_lock:
        connected_clients.add(websocket)
    logger.info("Client connected (total clients: %d)", len(connected_clients))
    
    # Send initial states to the newly connected client
    try:
        await send_initial_states(websocket)
    except Exception as e:
        logger.warning("Error sending initial states to client: %s", e)
    
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
                        logger.warning("Invalid LED value: %s", value)
                # Handle MESSAGE_WAITING event
                elif data.get("type") == "MESSAGE_WAITING":
                    value = data.get("value")
                    message_waiting = bool(value) if value is not None else True
                    with fade_lock:
                        fade_active = message_waiting
                    logger.info("Message waiting state updated: %s, fade_active: %s", message_waiting, fade_active)
                # Handle MESSAGE_READ event
                elif data.get("type") == "MESSAGE_READ":
                    message_waiting = False
                    with fade_lock:
                        fade_active = False
                    logger.info("Message read - clearing waiting state and stopping fade")
                else:
                    logger.warning("Unknown command type: %s", data.get('type'))
                    
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received: %s", message)
            except Exception as e:
                logger.error("Error handling client message: %s", e)
                
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error("Error in client handler: %s", e)
    finally:
        if clients_lock:
            async with clients_lock:
                connected_clients.discard(websocket)
            logger.info("Client removed (remaining clients: %d)", len(connected_clients))


async def websocket_server() -> None:
    """Run the WebSocket server."""
    global event_queue, websocket_loop, clients_lock
    
    websocket_loop = asyncio.get_event_loop()
    event_queue = asyncio.Queue()
    clients_lock = asyncio.Lock()
    
    # Start broadcast worker
    asyncio.create_task(broadcast_worker())
    
    logger.info("Starting WebSocket server on %s:%d", WS_HOST, WS_PORT)
    
    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        logger.info("WebSocket server started")
        # Keep server running
        await asyncio.Future()  # Run forever


def cleanup() -> None:
    """Clean up GPIO resources."""
    global adc_running, fade_active
    
    logger.info("Cleaning up resources...")
    
    # Stop LED fade
    with fade_lock:
        fade_active = False
    
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
            logger.error("Error closing LED: %s", e)
    
    # Close all GPIO inputs
    for name, device in input_devices.items():
        if device:
            try:
                device.close()
                logger.info("%s closed", name)
            except Exception as e:
                logger.error("Error closing %s: %s", name, e)


def signal_handler(signum, _frame) -> None:
    """Handle shutdown signals."""
    logger.info("Received signal %d, shutting down...", signum)
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
        start_led_fade_thread()
        
        # Run WebSocket server (blocks forever)
        asyncio.run(websocket_server())
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
    finally:
        cleanup()


if __name__ == '__main__':
    main()
