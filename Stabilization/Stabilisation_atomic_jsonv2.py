import os
import json
import time
import logging
import tempfile
from typing import List, Tuple, Optional, Dict, Any, TypedDict
from typing_extensions import Required

import numpy as np
import pyvisa.errors as visa_errors
from pymeasure.instruments.lakeshore import LakeShore331



# Base directory for resolving relative file paths in this module
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MeasurementConfig(TypedDict):
    """
    Configuration for a pressure measurement run.
    """
    lakeshore_address:      Required[str]
    lockin_address:         Required[str]
    slope_tolerance:        Required[float]
    intercept_tolerance:    Required[float]
    stabilization_points:   Required[int]
    sampling_interval:      Required[float]



def configure_class_logger(name: str) -> logging.Logger:
    """
    Create or retrieve a class‐named logger with a single StreamHandler.
    Avoids duplicate handlers when called multiple times.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


class TemperatureStabilizer:
    """
    Encapsulates the process of measuring temperature until it stabilizes
    according to linear-fit criteria, with robust error handling,
    atomic JSON writes, cycle history, and optional limits.
    """

    def __init__(
        self,
        instrument: Required[LakeShore331],
        config: MeasurementConfig,
        json_filepath: str,
        setpoint: float,
        max_cycles: Optional[int] = None,
    ):
        """
        Initialize the TemperatureStabilizer.

        :param instrument: An already-opened LakeShore331 instance for querying/setting temperature.
        :param config: MeasurementConfig dict providing:
            - slope_tolerance: float
              Maximum allowed absolute slope (dT/dt) in K per sample_interval for the regression
              line to be considered “flat” (i.e. stabilized).
            - intercept_tolerance: float
              Maximum allowed difference (in K) between the regression-line intercept and the
              desired setpoint temperature.
            - stabilization_points: int
              Number of consecutive temperature readings used in each linear regression cycle.
            - sampling_interval: float
              Delay between each temperature reading, in seconds.
        :param json_filepath: Path (absolute or relative to BASE_DIR) for atomic JSON status updates.
        :param setpoint: Initial target temperature in Kelvin.
        :param max_cycles: Optional cap on total regression cycles before giving up.
        """

        # pull stabilization parameters from config
        self.tolerance_A = config["slope_tolerance"]
        self.tolerance_B = config["intercept_tolerance"]
        self.nb_points   = config["stabilization_points"]
        self.sampling_time = config["sampling_interval"]
        self.max_cycles  = max_cycles
        self.setpoint    = setpoint

        # resolve to absolute path before storing
        if not os.path.isabs(json_filepath):
            json_filepath = os.path.join(BASE_DIR, json_filepath)
        self.json_filepath = json_filepath

        # history of cycles
        self.cycles_history: List[Dict[str, Any]] = []

        # use shared logger config
        self.logger = configure_class_logger(self.__class__.__name__)

        # ensure parent directory for JSON exists
        json_dir = os.path.dirname(self.json_filepath)
        if json_dir:
            os.makedirs(json_dir, exist_ok=True)

        # initialize the JSON file atomically with empty structure
        init_data = {
            "tolerance_A": self.tolerance_A,
            "tolerance_B": self.tolerance_B,
            "setpoint": self.setpoint,
            "cycles_history": []
        }
        self._write_json_atomic(init_data)
        self.logger.debug(f"Initialized JSON file at {self.json_filepath}")

        # Use the provided Lakeshore instance without re-opening or closing it here
        self.lakeshore = instrument
        self.logger.info("Using provided Lakeshore instance")

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit context manager.

        :param exc_type: Exception type if any.
        :param exc_val: Exception instance if any.
        :param exc_tb: Traceback if exception raised.
        """
        self.close()

    def close(self) -> None:
        """
        Cleanup after stabilization, without closing the Lakeshore instrument.
        """
        self.logger.debug("TemperatureStabilizer closed (instrument remains open).")

    def _write_json_atomic(self, data: Dict[str, Any]) -> None:
        """
        Atomically write JSON data to the configured filepath.

        :param data: Dictionary payload to write.
        """
        json_dir = os.path.dirname(self.json_filepath)
        with tempfile.NamedTemporaryFile(
            mode='w', dir=json_dir or './'
        ) as tmp:
            json.dump(data, tmp, indent=4)
            temp_name = tmp.name
        os.replace(temp_name, self.json_filepath)

    def _measure_temperature(self) -> float:
        """
        Query the Lakeshore for the current temperature on channel B.

        :returns: Measured temperature [K].
        :raises: VisaIOError if communication fails.
        """
        try:
            response = self.lakeshore.ask("KRDG? B")
            temp = float(response)
            self.logger.debug(f"Measured temperature: {temp:.4f} K")
            return temp
        except visa_errors.VisaIOError as err:
            self.logger.error(f"Lakeshore communication error: {err}")
            raise

    def _update_json(self) -> None:
        """
        Atomically overwrite the JSON file with the latest state,
        including robust cycle history.
        """
        payload = {
            "tolerance_A": self.tolerance_A,
            "tolerance_B": self.tolerance_B,
            "setpoint": self.setpoint,
            "cycles_history": self.cycles_history,
        }
        try:
            self._write_json_atomic(payload)
            self.logger.debug(f"Updated JSON file: {self.json_filepath}")
        except Exception as e:
            self.logger.error(f"Failed to write JSON file: {e}")

    def _perform_regression(self) -> Tuple[float, float]:
        """
        Perform a linear regression (y = A*x + B) on the collected measurements.

        :returns: Tuple containing (slope A, intercept B).
        """
        # validate data: remove nan or inf
        arr = np.array(self.current_measurements, dtype=float)
        mask = np.isfinite(arr)
        if not mask.all():
            invalid = np.where(~mask)[0]
            self.logger.warning(f"Dropping invalid measurements at indices {invalid}")
            arr = arr[mask]
        x = np.arange(len(arr))
        A, B = np.polyfit(x, arr, 1)
        self.logger.info(f"Regression result: A = {A:.6f}, B = {B:.6f}")
        return A, B

    def set_setpoint(self, new_setpoint: float) -> None:
        """
        Change the target setpoint, clear previous cycles,
        and reinitialize the JSON file for the new setpoint.

        :param new_setpoint: New temperature setpoint [K].
        """
        self.setpoint = new_setpoint
        self.cycles_history.clear()
        init_data = {
            "tolerance_A": self.tolerance_A,
            "tolerance_B": self.tolerance_B,
            "setpoint": self.setpoint,
            "cycles_history": []
        }
        try:
            self._write_json_atomic(init_data)
            self.logger.info(f"JSON reinitialized for new setpoint: {self.setpoint} K")
        except Exception as e:
            self.logger.error(f"Failed to reinitialize JSON: {e}")

    def check_stabilisation(self) -> bool:
        """
        Continuously perform measurement cycles until stabilization criteria are met,
        or abort on communication error or exceed max_cycles.

        :returns: True if stabilized; False otherwise.
        """
        cycle_count = 0
        while True:
            cycle_count += 1
            if self.max_cycles is not None and cycle_count > self.max_cycles:
                self.logger.error(f"Exceeded maximum cycles: {self.max_cycles}")
                return False

            # collect measurements for this cycle
            self.current_measurements = []
            for _ in range(self.nb_points):
                try:
                    temp = self._measure_temperature()
                    self.current_measurements.append(temp)
                    # atomic write after each new point
                    self._update_json()
                    time.sleep(self.sampling_time)
                except visa_errors.VisaIOError as e:
                    self.logger.error(f"Communication error during measurement: {e}")
                    return False


            # perform regression
            A, B = self._perform_regression()

            # record cycle data
            cycle = {
                "measurements": self.current_measurements.copy(),
                "slope_A": A,
                "intercept_B": B,
            }
            self.cycles_history.append(cycle)
            self._update_json()

            # stabilization check: slope ≈ 0 and intercept within tolerance_B
            if abs(A) <= self.tolerance_A and abs(B - self.setpoint) <= self.tolerance_B:
                self.logger.info("Stabilization criteria met.")
                return True

            self.logger.warning(f"Cycle {cycle_count} not stable (A={A:.6f} K/s, B={B:.6f} K); retrying...")
            time.sleep(self.sampling_time)
