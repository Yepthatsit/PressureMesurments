import os
import json
import time
import logging
from typing import List, Tuple

import numpy as np
import pyvisa.errors as visa_errors
from pymeasure.instruments.lakeshore import LakeShore331


class TemperatureStabilizerLegacy:
    """
    Legacy version: appends all measurements to a single list, and
    records slopes_history and intercepts_history per cycle.
    """

    def __init__(
        self,
        instrument_address: str,
        json_filepath: str,
        setpoint: float,
        nb_points_stabilisation: int,
        sampling_time: float,
        tolerance_A: float,
        tolerance_B: float,
    ):
        """
        :param instrument_address: VISA address of the Lakeshore instrument.
        :param json_filepath: Path to the JSON file for live updates.
        :param setpoint: Target temperature set point [K].
        :param nb_points_stabilisation: Number of points to collect before regression.
        :param sampling_time: Time between measurements [s].
        :param tolerance_A: Allowed tolerance on slope A.
        :param tolerance_B: Allowed tolerance on intercept B.
        """
        self.json_filepath = json_filepath
        self.setpoint = setpoint
        self.nb_points = nb_points_stabilisation
        self.sampling_time = sampling_time
        self.tolerance_A = tolerance_A
        self.tolerance_B = tolerance_B

        # cumulative list of all measurements across cycles
        self.measurements: List[float] = []
        self.slopes_history: List[float] = []
        self.intercepts_history: List[float] = []

        # configure a class-specific logger
        self.logger = logging.getLogger(self.__class__.__name__)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)

        # ensure parent directory exists
        parent = os.path.dirname(self.json_filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # initialize JSON with empty lists
        try:
            with open(self.json_filepath, "w") as json_file:
                json.dump({
                    "tolerance_A":        self.tolerance_A,
                    "tolerance_B":        self.tolerance_B,
                    "setpoint":           self.setpoint,
                    "measurements":       [],
                    "slopes_history":     [],
                    "intercepts_history": []
                }, json_file, indent=4)
            self.logger.debug(f"Initialized JSON at {self.json_filepath}")
        except Exception as e:
            self.logger.error(f"Could not initialize JSON file: {e}")

        # connect to Lakeshore
        try:
            self.lakeshore = LakeShore331(instrument_address)
            self.logger.info(f"Connected to Lakeshore at {instrument_address}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Lakeshore: {e}")
            raise

    def _measure_temperature(self) -> float:
        """
        Read temperature on channel B with a 0.2 s query delay.
        """
        try:
            resp = self.lakeshore.ask("KRDG? B", query_delay=0.2)
            temp = float(resp)
            self.logger.debug(f"Measured temperature: {temp:.4f} K")
            return temp
        except visa_errors.VisaIOError as err:
            self.logger.error(f"Lakeshore communication error: {err}")
            raise

    def _update_json(self) -> None:
        """
        Write current measurements and regression histories to JSON.
        """
        payload = {
            "tolerance_A":        self.tolerance_A,
            "tolerance_B":        self.tolerance_B,
            "setpoint":           self.setpoint,
            "measurements":       self.measurements,
            "slopes_history":     self.slopes_history,
            "intercepts_history": self.intercepts_history,
        }
        try:
            with open(self.json_filepath, "w") as json_file:
                json.dump(payload, json_file, indent=4)
            self.logger.debug("Updated JSON file.")
        except Exception as e:
            self.logger.error(f"Failed to write JSON file: {e}")

    def _perform_regression(self) -> Tuple[float, float]:
        """
        Run a linear fit y = A·x + B on current measurements.
        """
        x = np.arange(len(self.measurements))
        A, B = np.polyfit(x, self.measurements, 1)
        self.logger.info(f"Regression result: A = {A:.6f}, B = {B:.6f}")
        return A, B

    def set_setpoint(self, new_setpoint: float) -> None:
        """
        Overwrite setpoint, clear regression history,
        and reinitialize the JSON file accordingly.
        Measurements list remains cumulative.
        """
        self.setpoint = new_setpoint
        self.slopes_history.clear()
        self.intercepts_history.clear()

        try:
            with open(self.json_filepath, "w") as json_file:
                json.dump({
                    "tolerance_A":        self.tolerance_A,
                    "tolerance_B":        self.tolerance_B,
                    "setpoint":           self.setpoint,
                    "measurements":       self.measurements,
                    "slopes_history":     [],
                    "intercepts_history": []
                }, json_file, indent=4)
            self.logger.info(f"JSON reinitialized for new setpoint: {new_setpoint} K")
        except Exception as e:
            self.logger.error(f"Failed to reinitialize JSON for new setpoint: {e}")

    def check_stabilisation(self) -> bool:
        """
        Loop until stabilization criteria are met, or return False on comms error.
        Measurements list is cumulative across cycles.
        """
        while True:
            # collect the next batch of points
            for _ in range(self.nb_points):
                try:
                    temp = self._measure_temperature()
                    # append to the cumulative measurements list
                    self.measurements.append(temp)
                    self._update_json()
                    time.sleep(self.sampling_time)
                except visa_errors.VisaIOError as e:
                    self.logger.error(f"Communication error during measurement: {e}")
                    return False

            # perform regression on the full cumulative data
            A, B = self._perform_regression()
            self.slopes_history.append(A)
            self.intercepts_history.append(B)
            self._update_json()

            # check intersection criteria
            if abs(A) <= self.tolerance_A and abs(B - self.setpoint) <= self.tolerance_B:
                self.logger.info("Stabilization criteria met.")
                return True
            else:
                self.logger.warning(
                    f"Not stable (A={A:.6f}, B={B:.6f} K); restarting..."
                )
                time.sleep(self.sampling_time)


if __name__ == "__main__":
    stabilizer = TemperatureStabilizerLegacy(
        instrument_address="GPIB::12::INSTR",
        json_filepath="temperature_stabilization.json",
        setpoint=100.0,
        nb_points_stabilisation=200,
        sampling_time=0.1,
        tolerance_A=0.15,
        tolerance_B=0.15,
    )

    # assume get_next_setpoints() exists elsewhere
    for sp in get_next_setpoints():
        stabilizer.set_setpoint(sp)
        stable = stabilizer.check_stabilisation()
        print(f"Stabilization at {sp} K achieved? {stable}")
