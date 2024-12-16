import time
import threading
import logging
from logging.handlers import RotatingFileHandler
import serial
from serial.tools import list_ports
import dearpygui.dearpygui as dpg

# Configure logging
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SerialPlotter")
logger.setLevel(logging.DEBUG)

# File handler with rotation
file_handler = RotatingFileHandler("serial_plotter.log", maxBytes=1_000_000, backupCount=5)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# Global variables
SELECTED_PORT = None  # Stores the user-selected serial port
SELECTED_BAUD_RATE = 9600  # Default baud rate
LATEST_VALUE = 0
PLOT_DATA = []  # Stores data for plotting
MAX_POINTS = 100  # Maximum points to display on the graph
STOP_THREAD = False  # Flag to stop the reading thread
SERIAL_CONNECTION = None  # Global variable to store the serial connection


def detect_serial_ports():
    """Detect available serial ports."""
    logger.info("Detecting available serial ports.")
    return [port.device for port in list_ports.comports()]


def refresh_ports():
    """Refresh the list of available serial ports."""
    available_ports = detect_serial_ports()
    if available_ports:
        logger.info(f"Available ports detected: {available_ports}")
        dpg.configure_item("port_combo", items=available_ports, default_value=available_ports[0])
        dpg.configure_item("start_button", enabled=True)
        update_status("Select a serial port to connect.", (255, 255, 0))  # Yellow
    else:
        logger.warning("No serial ports detected.")
        dpg.configure_item("port_combo", items=["No ports available"], default_value="No ports available")
        dpg.configure_item("start_button", enabled=False)
        update_status("No serial ports detected. Refresh to check again.", (255, 0, 0))  # Red


def update_status(status, color):
    """Update the status text and color."""
    if dpg.does_item_exist("status_label"):
        dpg.set_value("status_label", status)
        dpg.configure_item("status_label", color=color)
    else:
        logger.warning("Status label item not found.")


def start_reading_data():
    """Start the thread for reading data from the selected port."""
    global STOP_THREAD, SELECTED_PORT, SERIAL_CONNECTION

    if not SELECTED_PORT or SELECTED_PORT == "No ports available":
        update_status("No valid serial port selected!", (255, 0, 0))  # Red
        logger.warning("Start reading failed: No valid serial port selected.")
        return

    update_status(f"Connecting to {SELECTED_PORT} at {SELECTED_BAUD_RATE} baud...", (255, 255, 0))  # Yellow
    logger.info("Starting data reading on %s at %d baud.", SELECTED_PORT, SELECTED_BAUD_RATE)
    STOP_THREAD = False
    threading.Thread(target=read_from_arduino, daemon=True).start()


def stop_reading_data():
    """Stop the reading thread."""
    global STOP_THREAD, SERIAL_CONNECTION
    STOP_THREAD = True
    if SERIAL_CONNECTION:
        SERIAL_CONNECTION.close()
        SERIAL_CONNECTION = None
        logger.info("Connection to %s closed.", SELECTED_PORT)
    update_status("Disconnected", (255, 0, 0))  # Red
    logger.info("Reading stopped by user.")


def read_from_arduino():
    """Read data from the selected serial port and update the GUI."""
    global LATEST_VALUE, PLOT_DATA, STOP_THREAD, SERIAL_CONNECTION
    retries = 3  # Number of retries for reconnection
    while retries > 0 and not STOP_THREAD:
        try:
            SERIAL_CONNECTION = serial.Serial(SELECTED_PORT, SELECTED_BAUD_RATE, timeout=1)
            update_status(f"Connected to {SELECTED_PORT} at {SELECTED_BAUD_RATE} baud.", (0, 255, 0))  # Green
            logger.info("Connected to %s at %d baud.", SELECTED_PORT, SELECTED_BAUD_RATE)
            time.sleep(2)  # Allow the serial connection to initialize

            while not STOP_THREAD:
                if SERIAL_CONNECTION.in_waiting > 0:  # Check if data is available
                    line = SERIAL_CONNECTION.readline().decode('utf-8').strip()
                    try:
                        # Convert the received data to a float
                        LATEST_VALUE = float(line)

                        # Update the progress bar and label
                        dpg.set_value("gauge_value", LATEST_VALUE / 100.0)  # Normalize 0-100 to 0.0-1.0
                        dpg.set_value("gauge_label", f"Value: {LATEST_VALUE}")

                        # Add the latest value to plot data
                        PLOT_DATA.append(float(LATEST_VALUE))  # Ensure the value is a float
                        if len(PLOT_DATA) > MAX_POINTS:  # Maintain a fixed number of points
                            PLOT_DATA.pop(0)

                        # Prepare X and Y data
                        x_data = list(range(len(PLOT_DATA)))  # X values are indices of data points
                        y_data = PLOT_DATA  # Y values are the data points

                        # Update the graph with a tuple (X, Y)
                        dpg.set_value("line_series", (x_data, y_data))
                    except ValueError:
                        logger.error("Invalid data received from %s: %s", SELECTED_PORT, line)

        except serial.SerialException as e:
            retries -= 1
            logger.error("Serial connection error: %s. Retries left: %d", e, retries)
            update_status(f"Connection error: {e}. Retrying ({retries})...", (255, 255, 0))  # Yellow
            time.sleep(2)  # Wait before retrying
        finally:
            if SERIAL_CONNECTION:
                SERIAL_CONNECTION.close()
                SERIAL_CONNECTION = None
                logger.info("Disconnected from %s.", SELECTED_PORT)

    if retries == 0 or STOP_THREAD:
        update_status("Failed to connect. Please check the port and try again.", (255, 0, 0))  # Red
        logger.error("Failed to connect after multiple retries.")


def on_port_selected(sender, app_data):
    """Callback for selecting a serial port."""
    global SELECTED_PORT
    SELECTED_PORT = app_data
    logger.info("Serial port selected: %s", SELECTED_PORT)
    update_status(f"Selected Port: {SELECTED_PORT}", (255, 255, 0))  # Yellow


def on_baud_rate_selected(sender, app_data):
    """Callback for selecting a baud rate."""
    global SELECTED_BAUD_RATE
    SELECTED_BAUD_RATE = int(app_data)
    logger.info("Baud rate selected: %d", SELECTED_BAUD_RATE)
    update_status(f"Baud Rate Selected: {SELECTED_BAUD_RATE}", (255, 255, 0))  # Yellow


def exit_application():
    """Handle application exit."""
    stop_reading_data()  # Ensure the thread stops
    logger.info("Application exited.")
    dpg.stop_dearpygui()  # Close the Dear PyGui context


def start_gui():
    """Function to create and start the Dear PyGui interface."""
    logger.info("Application started.")
    dpg.create_context()

    with dpg.window(label="Arduino Gauge and Serial Plotter", width=600, height=600):
        dpg.add_text("Dynamic Serial Port and Baud Rate Selection")

        # Dropdown for serial port selection
        available_ports = detect_serial_ports()
        port_items = available_ports if available_ports else ["No ports available"]
        dpg.add_combo(port_items, label="Select Serial Port", callback=on_port_selected, tag="port_combo")

        # Dropdown for baud rate selection
        dpg.add_combo([9600, 19200, 38400, 57600, 115200], label="Select Baud Rate", callback=on_baud_rate_selected, default_value=9600)

        # Buttons to start, stop, refresh, and exit
        dpg.add_button(label="Start Reading", callback=start_reading_data, tag="start_button", enabled=bool(port_items))
        dpg.add_button(label="Stop Reading", callback=stop_reading_data)
        dpg.add_button(label="Refresh Ports", callback=refresh_ports)
        dpg.add_button(label="Exit", callback=exit_application)

        # Status with color
        dpg.add_text("Status: Not Connected", tag="status_label", color=(255, 0, 0))  # Default to red

        dpg.add_spacing(count=2)
        dpg.add_separator()
        dpg.add_text("Arduino Data Gauge")
        dpg.add_progress_bar(tag="gauge_value", default_value=0.0, width=400)
        dpg.add_text("Value: 0", tag="gauge_label")

        # Add the plot for serial data
        with dpg.plot(label="Serial Plotter", height=300, width=500):
            y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Value")
            dpg.add_line_series([], [], parent=y_axis, label="Data", tag="line_series")

    dpg.set_exit_callback(exit_application)  # Handle window close events

    dpg.create_viewport(title="Arduino Gauge and Serial Plotter", width=600, height=600)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    start_gui()
