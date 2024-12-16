import serial
import time
import dearpygui.dearpygui as dpg
import threading
from serial.tools import list_ports
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Logging Configuration
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SerialPlotter")
logger.setLevel(logging.DEBUG)

file_handler = RotatingFileHandler("serial_plotter.log", maxBytes=1_000_000, backupCount=5)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# Global variables
selected_port = None
selected_baud_rate = 9600
channel_data = {}  # Store data for each channel
channel_values = {}  # Latest channel values for display
non_numeric_data = []
stop_thread = False
serial_connection = None
selected_channels = []
max_points = 100  # Limit points displayed in the graph


def detect_serial_ports():
    """Detect available serial ports."""
    logger.info("Detecting available serial ports.")
    return [port.device for port in list_ports.comports()]


def refresh_ports():
    """Refresh the list of available serial ports."""
    ports = detect_serial_ports()
    if ports:
        dpg.configure_item("port_combo", items=ports, default_value=ports[0])
        dpg.configure_item("start_button", enabled=True)
        update_status("Select a serial port to connect.", (255, 255, 0))
    else:
        dpg.configure_item("port_combo", items=["No ports available"], default_value="No ports available")
        dpg.configure_item("start_button", enabled=False)
        update_status("No ports detected. Refresh to try again.", (255, 0, 0))


def update_status(status, color):
    """Update status message and color."""
    dpg.set_value("status_label", status)
    dpg.configure_item("status_label", color=color)


def on_port_selected(sender, app_data):
    global selected_port
    selected_port = app_data
    logger.info(f"Port selected: {selected_port}")


def on_baud_rate_selected(sender, app_data):
    global selected_baud_rate
    selected_baud_rate = int(app_data)
    logger.info(f"Baud rate selected: {selected_baud_rate}")


def on_channel_selection(sender, app_data):
    global selected_channels
    selected_channels = app_data
    logger.info(f"Channels selected: {selected_channels}")


def start_reading_data():
    """Start the thread for reading serial data."""
    global stop_thread, serial_connection

    if not selected_port:
        update_status("No serial port selected!", (255, 0, 0))
        return

    stop_thread = False
    threading.Thread(target=read_from_arduino, daemon=True).start()


def stop_reading_data():
    """Stop reading data."""
    global stop_thread, serial_connection
    stop_thread = True
    if serial_connection:
        serial_connection.close()
    update_status("Disconnected", (255, 0, 0))


def read_from_arduino():
    """Read serial data and update GUI."""
    global stop_thread, serial_connection, channel_data, non_numeric_data

    try:
        serial_connection = serial.Serial(selected_port, selected_baud_rate, timeout=1)
        update_status(f"Connected to {selected_port} at {selected_baud_rate} baud", (0, 255, 0))
        logger.info(f"Connected to {selected_port}")

        while not stop_thread:
            if serial_connection.in_waiting > 0:
                line = serial_connection.readline().decode('utf-8').strip()
                logger.debug(f"Received data: {line}")

                if line:  # Ignore empty lines
                    process_received_data(line)

    except serial.SerialException as e:
        logger.error(f"Serial error: {e}")
    finally:
        if serial_connection:
            serial_connection.close()
        update_status("Disconnected", (255, 0, 0))


def process_received_data(line):
    """Process incoming serial data."""
    global channel_data, non_numeric_data, channel_values

    try:
        parts = line.split(",")

        # Parse numeric channels
        for i, value in enumerate(parts):
            if value.replace(".", "", 1).isdigit():
                channel_name = f"Channel {i + 1}"
                if channel_name not in channel_data:
                    channel_data[channel_name] = []

                channel_data[channel_name].append(float(value))
                channel_values[channel_name] = value

                # Limit points to max_points
                if len(channel_data[channel_name]) > max_points:
                    channel_data[channel_name].pop(0)

                # Update plot data
                if channel_name in selected_channels:
                    x_data = list(range(len(channel_data[channel_name])))
                    y_data = channel_data[channel_name]
                    dpg.set_value(f"{channel_name}_series", (x_data, y_data))

                # Update latest value
                dpg.set_value(f"{channel_name}_value", f"{channel_name}: {value}")

            else:  # Non-numeric data
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                non_numeric_data.append(f"[{timestamp}] {value}")
                if len(non_numeric_data) > 10:  # Limit visible non-numeric entries
                    non_numeric_data.pop(0)
                dpg.set_value("non_numeric_data_box", "\n".join(non_numeric_data))

    except Exception as e:
        logger.warning(f"Error processing data: {line} -> {e}")


def exit_application():
    stop_reading_data()
    dpg.stop_dearpygui()


def start_gui():
    dpg.create_context()

    with dpg.window(label="Arduino Multi-Channel Monitor", width=700, height=800):
        dpg.add_combo(detect_serial_ports(), label="Serial Port", callback=on_port_selected, tag="port_combo")
        dpg.add_combo([9600, 19200, 38400, 57600, 115200], label="Baud Rate", callback=on_baud_rate_selected)
        dpg.add_button(label="Start Reading", callback=start_reading_data, tag="start_button")
        dpg.add_button(label="Stop Reading", callback=stop_reading_data)
        dpg.add_text("Status: Not Connected", tag="status_label", color=(255, 0, 0))

        dpg.add_listbox(["Channel 1", "Channel 2", "Channel 3"], label="Channels", callback=on_channel_selection,
                        tag="channel_listbox", width=400, num_items=3)

        with dpg.plot(label="Multi-Channel Data Plot", height=400, width=600):
            dpg.add_plot_axis(dpg.mvXAxis, label="Time")
            dpg.add_plot_axis(dpg.mvYAxis, label="Value", tag="y_axis")
            for i in range(5):
                dpg.add_line_series([], [], parent="y_axis", label=f"Channel {i + 1}", tag=f"Channel {i + 1}_series")

        dpg.add_text("Channel Values:")
        for i in range(5):
            dpg.add_text(f"Channel {i + 1}: 0", tag=f"Channel {i + 1}_value")

        dpg.add_separator()
        dpg.add_text("Non-Numeric Data:")
        dpg.add_input_text(tag="non_numeric_data_box", multiline=True, width=600, height=150, readonly=True)

    dpg.create_viewport(title="Arduino Multi-Channel Serial Monitor", width=700, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    start_gui()
