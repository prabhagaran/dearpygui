import serial
import time
import dearpygui.dearpygui as dpg
import threading
from serial.tools import list_ports
import logging
from logging.handlers import RotatingFileHandler

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
selected_port = None  # Stores the user-selected serial port
selected_baud_rate = 9600  # Default baud rate
latest_value = 0
plot_data = []  # Stores data for plotting
max_points = 100  # Maximum points to display on the graph
stop_thread = False  # Flag to stop the reading thread
serial_connection = None  # Global variable to store the serial connection


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
    dpg.set_value("status_label", status)
    dpg.configure_item("status_label", color=color)


def start_reading_data():
    """Start the thread for reading data from the selected port."""
    global stop_thread, selected_port, serial_connection

    if not selected_port or selected_port == "No ports available":
        update_status("No valid serial port selected!", (255, 0, 0))  # Red
        logger.warning("Start reading failed: No valid serial port selected.")
        return

    update_status(f"Connecting to {selected_port} at {selected_baud_rate} baud...", (255, 255, 0))  # Yellow
    logger.info(f"Starting data reading on {selected_port} at {selected_baud_rate} baud.")
    stop_thread = False
    threading.Thread(target=read_from_arduino, daemon=True).start()


def stop_reading_data():
    """Stop the reading thread."""
    global stop_thread, serial_connection
    stop_thread = True
    if serial_connection:
        serial_connection.close()
        serial_connection = None
        logger.info(f"Connection to {selected_port} closed.")
    update_status("Disconnected", (255, 0, 0))  # Red
    logger.info("Reading stopped by user.")


def read_from_arduino():
    """Read data from the selected serial port and update the GUI."""
    global latest_value, plot_data, stop_thread, serial_connection
    retries = 3  # Number of retries for reconnection
    while retries > 0 and not stop_thread:
        try:
            serial_connection = serial.Serial(selected_port, selected_baud_rate, timeout=1)
            update_status(f"Connected to {selected_port} at {selected_baud_rate} baud.", (0, 255, 0))  # Green
            logger.info(f"Connected to {selected_port} at {selected_baud_rate} baud.")
            time.sleep(2)  # Allow the serial connection to initialize

            while not stop_thread:
                if serial_connection.in_waiting > 0:  # Check if data is available
                    line = serial_connection.readline().decode('utf-8').strip()
                    try:
                        # Convert the received data to a float
                        latest_value = float(line)

                        # Update the progress bar and label
                        dpg.set_value("gauge_value", latest_value / 100.0)  # Normalize 0-100 to 0.0-1.0
                        dpg.set_value("gauge_label", f"Value: {latest_value}")

                        # Add the latest value to plot data
                        plot_data.append(float(latest_value))  # Ensure the value is a float
                        if len(plot_data) > max_points:  # Maintain a fixed number of points
                            plot_data.pop(0)

                        # Prepare X and Y data
                        x_data = list(range(len(plot_data)))  # X values are indices of data points
                        y_data = plot_data  # Y values are the data points

                        # Update the graph with a tuple (X, Y)
                        dpg.set_value("line_series", (x_data, y_data))
                    except ValueError:
                        logger.error(f"Invalid data received from {selected_port}: {line}")

        except serial.SerialException as e:
            retries -= 1
            logger.error(f"Serial connection error: {e}. Retries left: {retries}")
            update_status(f"Connection error: {e}. Retrying ({retries})...", (255, 255, 0))  # Yellow
            time.sleep(2)  # Wait before retrying
        finally:
            if serial_connection:
                serial_connection.close()
                serial_connection = None
                logger.info(f"Disconnected from {selected_port}.")

    if retries == 0 or stop_thread:
        update_status("Failed to connect. Please check the port and try again.", (255, 0, 0))  # Red
        logger.error("Failed to connect after multiple retries.")


def on_port_selected(sender, app_data):
    """Callback for selecting a serial port."""
    global selected_port
    selected_port = app_data
    logger.info(f"Serial port selected: {selected_port}")
    update_status(f"Selected Port: {selected_port}", (255, 255, 0))  # Yellow


def on_baud_rate_selected(sender, app_data):
    """Callback for selecting a baud rate."""
    global selected_baud_rate
    selected_baud_rate = int(app_data)
    logger.info(f"Baud rate selected: {selected_baud_rate}")
    update_status(f"Baud Rate Selected: {selected_baud_rate}", (255, 255, 0))  # Yellow


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
            x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Time")
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
