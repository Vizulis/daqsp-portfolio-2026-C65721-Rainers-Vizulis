import os

os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

import tkinter as tk
import cv2
import csv
import threading
import time
from collections import deque
from datetime import datetime
import nidaqmx
from nidaqmx.constants import (
    Edge,
    AcquisitionType,
    TerminalConfiguration,
    LineGrouping,
    READ_ALL_AVAILABLE,
)

from setup_camera import init_camera

# CONSTANTS
# Creates a subdirectory where to store catured data
SAVE_DIR = "data_dir"

# Specifies the amount of time before and after the trigger we capture/keep data
# Takes integer seconds for simplicity, for example, 1 gives us a total capture time of 2 seconds
CAMERA_BUFFER_TIME_SECONDS = ...
CAMERA_WIDTH = ... # Find it from video modes
CAMERA_HEIGHT = ... # Find it from video modes
FPS = ...  # Find the maximum fps from video modes
CAMERA_INDEX = 0  # Change to correct camera with trial and error
EXPOSURE = ...
FOCUS = ...

DEVICE_NAME = ""  # DAQ device name from NI MAX, for example "Dev2", use it in all channel names
TRIGGER_CHANNEL = f"/{DEVICE_NAME}/..." # For example "/Dev2/PFI4"
DAQ_TIMEOUT = 10  # Timeout for DAQ tasks, in seconds

ANALOG_CHANNEL = ""
ANALOG_RANGE = ...  # +- value of the measurement range
ANALOG_PRETRIGGER_SAMPLES = ...
ANALOG_SAMPLE_RATE = ...
ANALOG_TOTAL_SAMPLES = ...

# GLOBAL VARIABLES
# Circular buffer for camera frames
frame_buffer = deque(maxlen=FPS * CAMERA_BUFFER_TIME_SECONDS * 2)
triggered = threading.Event()  # Flag to sync threads if a trigger signal is detected
stop_flag = threading.Event()  # Flag to kill threads if a stop is issued
camera = init_camera(
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, FPS, EXPOSURE, FOCUS
)  # Camera object


def save_images(data, trigger_time=datetime.now()):
    image_save_dir = os.path.join(
        SAVE_DIR, f"images_{trigger_time.strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(image_save_dir, exist_ok=True)
    # TASK 1: implement saving images from the buffer
    for i in ...:
        filename = os.path.join(image_save_dir, ...)
        cv2.imwrite(..., ...)
    print(f"Images saved in {image_save_dir}")


def save_analog_data(data, trigger_time=datetime.now()):
    csv_filename = os.path.join(
        SAVE_DIR, f"analog_data_{trigger_time.strftime('%Y%m%d_%H%M%S')}.csv"
    )
    with open(csv_filename, mode="w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["Voltage"])
        for voltage in data:
            csv_writer.writerow([voltage])
    print(f"Analog data saved in {csv_filename}")


def analog_capture():
    with nidaqmx.Task() as task:
        # TASK 3: implement the analog capture thread
        # Find an example from the nidaqmx-python repository
        task.start()
        data = task.read(number_of_samples_per_channel=..., timeout=...)
        print("All analog data acquired!")
        task.stop()
        save_analog_data(...)


def quit_requested():
    """Return True if 'q' was pressed in the live feed window or the window was closed from X."""
    if cv2.waitKey(1) & 0xFF == ord("q"):
        return True
    return cv2.getWindowProperty("Live Feed", cv2.WND_PROP_VISIBLE) < 1


def show_status(text):
    """Show the latest frame with a status text on it, so the user knows the program has not frozen."""
    if frame_buffer:
        frame = frame_buffer[-1][1].copy()
        cv2.putText(frame, text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.imshow("Live Feed", frame)
    if quit_requested():
        stop_flag.set()


def camera_capture():
    """ "Camera capture thread. Capture images and store in circular buffer."""
    while not triggered.is_set() and not stop_flag.is_set():
        ret, frame = camera.read()
        if ret:
            frame_buffer.append((time.time(), frame))

            cv2.imshow("Live Feed", frame)

            if quit_requested():
                stop_flag.set()
                print("Stopping the image display...")
                break
        else:
            # A failed read means the camera did not send a frame within ~10 s
            print(f"ERROR: Camera unavailable (no frames from camera index {CAMERA_INDEX}). "
                  "Check that USB Device Tree Viewer or another program (Camera app, OBS, Teams) "
                  "is not using the camera, or replug it.")
            stop_flag.set()
            break

    if triggered.is_set() and not stop_flag.is_set():
        print("Capturing images...")

        trigger_time = time.time()
        end_time = trigger_time + CAMERA_BUFFER_TIME_SECONDS
        next_status_time = 0
        while time.time() < end_time and not stop_flag.is_set():
            current_time = time.time()
            ret, frame = camera.read()
            if ret:
                frame_buffer.append((time.time(), frame))

            if current_time >= next_status_time:
                next_status_time = current_time + 0.5
                show_status(f"CAPTURING IMAGES... {end_time - current_time:.0f} s")

        if not stop_flag.is_set():
            show_status("SAVING IMAGES...")
            save_images(list(frame_buffer))


def wait_for_hw_trigger():
    """Configure trigger signal capture and return True on a trigger."""
    with nidaqmx.Task() as task:
        # TASK 2: implement the hardware trigger function in the while loop
        # Find an example from the nidaqmx-python repository, return True on a FALLING edge
        start_time = time.time()
        while time.time() - start_time < DAQ_TIMEOUT:
            if stop_flag.is_set():
                return False
    return False


def create_software_trigger_gui(camera_thread):
    """Create a simple GUI with a button to simulate the trigger."""
    root = tk.Tk()
    root.title("Trigger Simulation")
    root.configure(padx=30, pady=15)
    root.resizable(False, False)
    trigger_end_time = None

    def stop():
        """Stop the whole program ('q', Exit button or closing the window from X)."""
        stop_flag.set()
        root.destroy()

    def simulate_trigger():
        nonlocal trigger_end_time
        trigger_end_time = time.time() + CAMERA_BUFFER_TIME_SECONDS
        triggered.set()
        trigger_button.config(state="disabled", bg="gray")

    def update():
        """Runs every 250 ms: update the status text and close the GUI when the camera thread is done."""
        if stop_flag.is_set() or not camera_thread.is_alive():
            root.destroy()
            return
        if trigger_end_time is not None:
            remaining = trigger_end_time - time.time()
            if remaining > 0:
                status_label.config(text=f"● Capturing images... {remaining:.0f} s", fg="orange red")
            else:
                status_label.config(text="● Saving images, please wait...", fg="orange red")
        root.after(250, update)

    # Button to trigger the event
    trigger_button = tk.Button(
        root,
        text="Simulate Trigger",
        command=simulate_trigger,
        bg="green",
        fg="white",
        font=("Helvetica", 16),
        width=16,
    )
    trigger_button.pack(pady=10)

    # Exit button
    exit_button = tk.Button(
        root,
        text="Exit",
        command=stop,
        bg="red",
        fg="white",
        font=("Helvetica", 16),
        width=16,
    )
    exit_button.pack(pady=10)

    # Status indicator, the program closes by itself after the images are saved
    status_label = tk.Label(root, text="Waiting for trigger  (q = quit)", font=("Helvetica", 12), fg="gray25")
    status_label.pack(pady=(10, 0))

    root.bind("q", lambda event: stop())
    root.protocol("WM_DELETE_WINDOW", stop)
    root.after(250, update)
    root.mainloop()


def main():
    print("Press 'q' or close any window to stop the program.")

    # Make sure the output dir exists
    os.makedirs(SAVE_DIR, exist_ok=True)

    # Define capture threads
    camera_thread = threading.Thread(target=camera_capture)
    analog_thread = threading.Thread(target=analog_capture)

    # Start the capture threads
    camera_thread.start()

    # UNCOMMENT THIS FOR TASK 3
    # analog_thread.start()

    # Create the GUI
    # You only need this for the first task, you can comment it out afterwards
    create_software_trigger_gui(camera_thread)

    # UNCOMMENT THIS FOR TASK 2
    # if wait_for_hw_trigger():
    #     print("Trigger detected!")
    #     triggered.set()
    # else:
    #     stop_flag.set()  # No trigger (timeout or 'q'), stop the capture threads

    # Wait for threads to finish their capture and saving
    camera_thread.join()

    # UNCOMMENT THIS FOR TASK 3
    # analog_thread.join()

    # Clean up
    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
