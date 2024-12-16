import serial
import time
import dearpygui.dearpygui as dpg
import threading
from serial.tools import list_ports
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

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
selected_port = None
selected_baud_rate = 9600
plot_data = []  # Stores numeric data for plotting
non_numeric_data = []  # Stores received non-numeric data with timestamps
max_points = 100  # Maximum points to display on the graph
stop_thread = False
serial_connection = None


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
    global plot_data, non_numeric_data, stop_thread, serial_connection
    retries = 3
    while retries > 0 and not stop_thread:
        try:
            serial_connection = serial.Serial(selected_port, selected_baud_rate, timeout=1)
            update_status(f"Connected to {selected_port} at {selected_baud_rate} baud.", (0, 255, 0))  # Green
            logger.info(f"Connected to {selected_port} at {selected_baud_rate} baud.")
            time.sleep(2)

            while not stop_thread:
                if serial_connection.in_waiting > 0:
                    line = serial_connection.readline().decode('utf-8').strip()
                    try:
                        # Attempt to parse numeric data
                        numeric_value = float(line)

                        # Update progress bar and plot
                        dpg.set_value("gauge_value", numeric_value / 100.0)  # Normalize to 0-1
                        dpg.set_value("gauge_label", f"Value: {numeric_value}")
                        plot_data.append(numeric_value)
                        if len(plot_data) > max_points:
                            plot_data.pop(0)

                        x_data = list(range(len(plot_data)))
                        y_data = plot_data
                        dpg.set_value("line_series", (x_data, y_data))

                    except ValueError:
                        # Handle non-numeric data
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        entry = f"{timestamp}: {line}"
                        non_numeric_data.append(entry)
                        logger.info(f"Received non-numeric data: {entry}")

                        # Update text box with non-numeric data
                        dpg.set_value("non_numeric_textbox", "\n".join(non_numeric_data))

        except serial.SerialException as e:
            retries -= 1
            logger.error(f"Serial connection error: {e}. Retries left: {retries}")
            update_status(f"Connection error: {e}. Retrying ({retries})...", (255, 255, 0))  # Yellow
            time.sleep(2)
        finally:
            if serial_connection:
                serial_connection.close()
                serial_connection = None
                logger.info(f"Disconnected from {selected_port}.")

    if retries == 0 or stop_thread:
        update_status("Failed to connect. Please check the port and try again.", (255, 0, 0))  # Red
        logger.error("Failed to connect after multiple retries.")


def exit_application():
    """Handle application exit."""
    stop_reading_data()
    logger.info("Application exited.")
    dpg.stop_dearpygui()


def start_gui():
    """Create and start the Dear PyGui interface."""
    logger.info("Application started.")
    dpg.create_context()

    with dpg.window(label="Arduino Serial Monitor", width=700, height=800):
        dpg.add_text("Dynamic Serial Port and Baud Rate Selection")
        available_ports = detect_serial_ports()
        port_items = available_ports if available_ports else ["No ports available"]
        dpg.add_combo(port_items, label="Select Serial Port", callback=on_port_selected, tag="port_combo")
        dpg.add_combo([9600, 19200, 38400, 57600, 115200], label="Select Baud Rate", callback=on_baud_rate_selected, default_value=9600)
        dpg.add_button(label="Start Reading", callback=start_reading_data, tag="start_button", enabled=bool(port_items))
        dpg.add_button(label="Stop Reading", callback=stop_reading_data)
        dpg.add_button(label="Refresh Ports", callback=refresh_ports)
        dpg.add_button(label="Exit", callback=exit_application)

        # Status with color
        dpg.add_text("Status: Not Connected", tag="status_label", color=(255, 0, 0))

        dpg.add_separator()

        # Numeric data section
        dpg.add_text("Arduino Data Gauge")
        dpg.add_progress_bar(tag="gauge_value", default_value=0.0, width=400)
        dpg.add_text("Value: 0", tag="gauge_label")

        dpg.add_separator()

        # Non-numeric data section
        dpg.add_text("Non-Numeric Data (With Timestamps):")
        dpg.add_input_text(tag="non_numeric_textbox", multiline=True, width=600, height=300, readonly=True)

        dpg.add_separator()

        # Add the plot for numeric data
        with dpg.plot(label="Numeric Data Plot", height=300, width=600):
            x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Time")
            y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Value")
            dpg.add_line_series([], [], parent=y_axis, label="Data", tag="line_series")

    dpg.set_exit_callback(exit_application)
    dpg.create_viewport(title="Arduino Serial Monitor", width=700, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    start_gui()
