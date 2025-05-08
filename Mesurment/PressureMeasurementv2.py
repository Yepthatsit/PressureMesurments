import os
from Stabilization.Stabilisation_atomic_jsonv3 import MeasurementConfig,configure_class_logger,TemperatureStabilizer
import datetime
import time
import numpy as np
import subprocess
from typing import Optional
from typing_extensions import Required

from pymeasure.instruments.lakeshore import LakeShore331
from pymeasure.instruments.srs import SR860


# Base directory for resolving relative file paths in this module
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class PressureMeasurement:
    """
    Handles temperature ramping and stabilization measurements,
    logging readings from Lakeshore and SR860 instruments.
    """

    HEADER: Required[str] = (
        "T_A[K] T_B[K] Setpoint[K] "
        "SR860x[V] SR860y[V] SR860f[Hz] "
        "SR860sin[V] SR860theta[deg] "
        "SR860phase[deg] SR860mag[V] "
        "HTR CNT DateTime"
    )

    def __init__(self, config: MeasurementConfig) -> None:
        """
        Initialize the PressureMeasurement instance.

        :param config: MeasurementConfig dict including:
            - lakeshore_address: VISA/GPIB resource string for Lakeshore331.
            - lockin_address: VISA/GPIB resource string for SR860 lock-in amplifier.
            - slope_tolerance: float
                Maximum allowed slope (dT/dt) per regression cycle (K per sampling_interval).
            - intercept_tolerance: float
                Maximum allowed intercept deviation from setpoint after regression (K).
            - stabilization_points: int
                Number of readings per stabilization regression cycle.
            - sampling_interval: float
                Delay in seconds between successive temperature readings.
        """

        self.config = config

        # Configure per-class logger
        self.logger = configure_class_logger(self.__class__.__name__)

        # Open instrument connections
        self.lakeshore = LakeShore331(config["lakeshore_address"])
        self.lockin    = SR860(config["lockin_address"])

        # Stabilization parameters from config
        self.slope_tolerance      = config["slope_tolerance"]
        self.intercept_tolerance  = config["intercept_tolerance"]
        self.stabilization_points = config["stabilization_points"]
        self.sampling_interval    = config["sampling_interval"]

        self.logger.info(
            f"Config loaded: slope_tolerance={self.slope_tolerance}, "
            f"intercept_tolerance={self.intercept_tolerance}, "
            f"stabilization_points={self.stabilization_points}, "
            f"sampling_interval={self.sampling_interval}s"
        )

    def __enter__(self) -> "PressureMeasurement":
        """Enter context manager (no-op)."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[object]
    ) -> None:
        """
        Exit context manager and close both instruments.

        :param exc_type: Exception type if any occurred.
        :param exc_val: Exception instance if any occurred.
        :param exc_tb: Traceback if an exception occurred.
        """
        for name, inst in (("Lakeshore", self.lakeshore), ("Lock-in", self.lockin)):
            try:
                inst.close()
                self.logger.info(f"Closed {name}.")
            except Exception:
                self.logger.warning(f"Failed closing {name}.")

    def _ensure_file(self, filepath: str) -> str:
        """
        Ensure the output directory exists and the file starts with a header.

        :param filepath: Path (absolute or relative to BASE_DIR) of the data file.
        :returns: Absolute path to the ensured file.
        """
        abs_path = filepath if os.path.isabs(filepath) else os.path.join(BASE_DIR, filepath)
        abs_path = os.path.abspath(abs_path)

        directory = os.path.dirname(abs_path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
            self.logger.debug(f"Created directory: {directory}")

        if not os.path.isfile(abs_path):
            with open(abs_path, "w") as f:
                f.write(self.HEADER + "\n")
            self.logger.debug(f"Created file with header: {abs_path}")

        return abs_path

    @staticmethod
    def _current_timestamp() -> str:
        """
        Return the current timestamp as a formatted string.

        :returns: 'YYYY-MM-DD HH:MM:SS.microseconds'
        """
        return datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S.%f")

    def _get_measurement_record(self, count: int) -> str:
        """
        Query both instruments and format a single-line record.

        :param count: Sequential record index (1-based).
        :returns: Space-separated string of all readings + timestamp.
        """
        # Temperatures from Lakeshore
        tA = float(self.lakeshore.ask("KRDG? A"))
        tB = float(self.lakeshore.ask("KRDG? B"))
        setpt = float(self.lakeshore.ask("SETP? 1"))

        # Lock-in readings
        x     = self.lockin.x
        y     = self.lockin.y
        freq  = self.lockin.frequency
        sin_v = self.lockin.sine_voltage
        theta = self.lockin.theta
        phase = self.lockin.phase
        mag   = self.lockin.magnitude

        # Heater output
        heater_out = self.lakeshore.ask("HTR?")

        fields = [
            f"{tA:.6f}", f"{tB:.6f}", f"{setpt:.6f}",
            f"{x:.6f}", f"{y:.6f}", f"{freq:.2f}",
            f"{sin_v:.6f}", f"{theta:.2f}", f"{phase:.2f}",
            f"{mag:.6f}", heater_out,
            str(count), self._current_timestamp()
        ]
        return " ".join(fields)

    def go_to_temperature(
        self,
        file_path: str,
        target_temp: float,
        ramp_rate: float = 4.0,
        sample_tol: float = 0.5,
        control_tol: float = 0.5,
        interval: float = 5.0,
    ) -> None:
        """
        Ramp to a target temperature and log readings until within tolerances.

        :param file_path: Output data file (abs or relative to BASE_DIR).
        :param target_temp: Desired temperature (K).
        :param ramp_rate: Ramp speed (K/min).
        :param sample_tol: Allowed deviation for sensor A (K).
        :param control_tol: Allowed deviation for sensor B (K).
        :param interval: Time between log cycles (s).
        """
        out_file = self._ensure_file(file_path)
        count = 1

        self.lakeshore.write(f"RAMP 1,1,{ramp_rate}")
        self.lakeshore.write(f"SETP 1,{target_temp}")
        self.logger.info(f"Ramping to {target_temp}K @ {ramp_rate}K/min")
        process = subprocess.Popen(f"py ./Ploting/UniversalPlotter.py {out_file} T_A[K],SR860x[V]")
        while True:
            ctrl = float(self.lakeshore.ask("KRDG? B"))
            if abs(ctrl - target_temp) <= control_tol :
                self.logger.info(f"Reached {target_temp}K within tolerance.")
                break

            record = self._get_measurement_record(count)
            with open(out_file, "a") as f:
                f.write(record + "\n")
            self.logger.debug(record)
            count += 1
            time.sleep(interval)
        process.terminate()

    def stabilization_measurement(
            self,
            file_path: str,
            start_temp: float,
            end_temp: float,
            points: int,
    ) -> None:
        """
        Perform an up-and-down temperature sweep with stabilization at each step.

        :param file_path: Output data file (abs or relative to BASE_DIR).
        :param start_temp: Starting temperature (K).
        :param end_temp: Ending temperature (K).
        :param points: Number of steps in the sweep.
        """
        # Ensure the output directory exists and the file has the header; get its absolute path
        out_file = self._ensure_file(file_path)

        # Generate the ascending list of 'points' temperatures from start_temp to end_temp
        forward = list(np.linspace(start_temp, end_temp, points))
        # Create the full sweep by appending the reverse of 'forward' minus the final point
        sweep = forward + forward[::-1][1:]

        # Build the absolute path to the stabilizer's JSON configuration file
        cfg_path = os.path.join(BASE_DIR,'..', "UtilityFiles", "Stabilization.json")

        # Use the TemperatureStabilizer context manager to handle setup and cleanup
        with TemperatureStabilizer(
                instrument=self.lakeshore,
                config=self.config,
                json_filepath=cfg_path,
                setpoint=start_temp,
                max_cycles=None,
        ) as stabilizer:
            # Loop over each temperature in the sweep, numbering from 1
            LivePlot = subprocess.Popen(f"py ./Ploting/UniversalPlotter.py {out_file} T_A[K],SR860x[V] T_A[K],SR860y[V]")
            JsonPlot = subprocess.Popen(f"py ./Ploting/JsonPlotter.py {cfg_path}")
            for idx, temp in enumerate(sweep, 1):
                # Log the current stabilization step
                self.logger.info(f"Stabilizing at {temp}K (step {idx}/{len(sweep)})")
                # Update the stabilizer's target and send the command to the Lakeshore
                stabilizer.set_setpoint(temp)
                self.lakeshore.write(f"SETP 1,{temp}")
                # Check if the temperature has stabilized; abort on failure
                if not stabilizer.check_stabilisation():
                    self.logger.error(f"Stabilization failed at {temp}K. Aborting.")
                    break
                # Once stable, collect a measurement record
                record = self._get_measurement_record(idx)
                # Append the record to the output file
                with open(out_file, "a") as f:
                    f.write(record + "\n")
                # Log that the record was successfully written
                self.logger.debug(f"Recorded at {temp}K")
            LivePlot.terminate()
            JsonPlot.terminate()

