import os
import json
import time
import logging
import tempfile
from typing import List, Tuple, Optional, Dict, Any, Required

import numpy as np
import pyvisa.errors as visa_errors
from pymeasure.instruments.lakeshore import LakeShore331


class TemperatureStabilizer:
    """
    Encapsulates the process of measuring temperature until it stabilizes
    according to linear-fit criteria, with robust error handling,
    atomic JSON writes, cycle history, and optional limits.
    """

    def __init__(
        self,
        instrument: Required[LakeShore331],
        json_filepath: str,
        setpoint: float,
        nb_points_stabilisation: int,
        sampling_time: float,
        tolerance_A: float,
        tolerance_B: float,
        max_cycles: Optional[int] = None,
    ):
        """
        Initialize the TemperatureStabilizer.

        :param instrument_address: VISA address of the Lakeshore instrument.
        :param json_filepath: Path to the JSON file for live updates.
        :param setpoint: Target temperature set point [K].
        :param nb_points_stabilisation: Number of points to collect before regression.
        :param sampling_time: Time between measurements [s].
        :param tolerance_A: Allowed tolerance on slope A.
        :param tolerance_B: Allowed tolerance on intercept B.
        :param max_cycles: Optional maximum number of measurement cycles before abort.
        """
        self.json_filepath = json_filepath
        self.setpoint = setpoint
        self.nb_points = nb_points_stabilisation
        self.sampling_time = sampling_time
        self.tolerance_A = tolerance_A
        self.tolerance_B = tolerance_B
        self.max_cycles = max_cycles

        # history of measurement cycles
        self.cycles_history: List[Dict[str, Any]] = []

        # configure a class-specific logger, avoid duplicate handlers
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            ))
            self.logger.addHandler(stream_handler)
        self.logger.setLevel(logging.DEBUG)

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

        # connect to the Lakeshore instrument
        try:
            self.lakeshore = instrument
            self.logger.info(f"Connected to Lakeshore")
        except Exception as e:
            self.logger.error(f"Failed to connect to Lakeshore: {e}")
            raise
        

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        """
        Close the connection to the Lakeshore instrument.
        """
        try:
            self.lakeshore.close()
            self.logger.info("Closed Lakeshore connection.")
        except Exception:
            pass

    def _write_json_atomic(self, data: Dict[str, Any]) -> None:
        """
        Atomically write JSON data to the configured filepath.
        """
        json_dir = os.path.dirname(self.json_filepath)
        with tempfile.NamedTemporaryFile(
            mode='w', dir=json_dir or '.', delete=False
        ) as tmp:
            json.dump(data, tmp, indent=4)
            temp_name = tmp.name
        os.replace(temp_name, self.json_filepath)

    def _measure_temperature(self) -> float:
        """
        Query the Lakeshore for the current temperature on channel B,
        using ask() with an explicit 200 ms query delay.

        :returns: Measured temperature [K].
        :raises: VisaIOError if communication fails.
        """
        try:
            response = self.lakeshore.ask(command="KRDG? B")
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

        :returns: Tuple containing (A, B).
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

            self.logger.warning(f"Cycle {cycle_count} not stable (A={A:.6f}, B={B:.6f} K); retrying...")
            time.sleep(self.sampling_time)


if __name__ == "__main__":
    # Example usage with context manager and optional max_cycles
    with TemperatureStabilizer(
        instrument_address="GPIB::12::INSTR",
        json_filepath="temperature_stabilization.json",
        setpoint=100.0,
        nb_points_stabilisation=200,
        sampling_time=0.1,
        tolerance_A=0.15,
        tolerance_B=0.15,
        max_cycles=10,
    ) as stabilizer:

        # assume get_next_setpoints() exists elsewhere
        for sp in get_next_setpoints():
            stabilizer.set_setpoint(sp)
            stable = stabilizer.check_stabilisation()
            print(f"Stabilization at {sp} K achieved? {stable}")
