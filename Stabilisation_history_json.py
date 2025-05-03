import os
import json
import time
import logging
from typing import List, Tuple, Dict, Any
import numpy as np
import pyvisa.errors as visa_errors
from pymeasure.instruments.lakeshore import LakeShore331


class TemperatureStabilizer:
    """
    Encapsulates the process of measuring temperature until it stabilizes
    according to linear‐fit criteria, while logging and dumping state to JSON.
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
        Initialize the TemperatureStabilizer.

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

        # history of measurement cycles
        self.cycles_history: List[Dict[str, Any]] = []

        # configure a class‐specific logger
        self.logger = logging.getLogger(self.__class__.__name__)
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

        # initialize the JSON file with the full empty structure
        try:
            with open(self.json_filepath, "w") as f:
                json.dump({
                    "tolerance_A":    self.tolerance_A,
                    "tolerance_B":    self.tolerance_B,
                    "setpoint":       self.setpoint,
                    "cycles_history": []
                }, f, indent=4)
            self.logger.debug(f"Initialized JSON file at {self.json_filepath}")
        except Exception as e:
            self.logger.error(f"Could not initialize JSON file: {e}")

        # connect to the Lakeshore instrument
        try:
            self.lakeshore = LakeShore331(instrument_address)
            self.logger.info(f"Connected to Lakeshore at {instrument_address}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Lakeshore: {e}")
            raise

    def _measure_temperature(self) -> float:
        """
        Query the Lakeshore for the current temperature on channel B,
        using ask() with an explicit 200 ms query delay.

        :returns: Measured temperature [K].
        :raises: VisaIOError if communication fails.
        """
        try:
            response = self.lakeshore.ask("KRDG? B", query_delay=0.2)
            temp = float(response)
            self.logger.debug(f"Measured temperature: {temp:.4f} K")
            return temp
        except visa_errors.VisaIOError as err:
            self.logger.error(f"Lakeshore communication error: {err}")
            raise

    def _update_json(self) -> None:
        """
        Overwrite the JSON file with the latest state,
        including the full history of measurement cycles.
        """
        data = {
            "tolerance_A":    self.tolerance_A,
            "tolerance_B":    self.tolerance_B,
            "setpoint":       self.setpoint,
            "cycles_history": self.cycles_history,
        }
        try:
            with open(self.json_filepath, "w") as f:
                json.dump(data, f, indent=4)
            self.logger.debug(f"Updated JSON file: {self.json_filepath}")
        except Exception as e:
            self.logger.error(f"Failed to write JSON file: {e}")

    def _perform_regression(self) -> Tuple[float, float]:
        """
        Perform a linear regression (y = A*x + B) on the collected measurements.

        :returns: Tuple containing (A, B).
        """
        x = np.arange(len(self.current_measurements))
        A, B = np.polyfit(x, self.current_measurements, 1)
        self.logger.info(f"Regression result: A = {A:.6f}, B = {B:.6f}")
        return A, B

    def set_setpoint(self, new_setpoint: float) -> None:
        """
        Change the target setpoint, clear any previous cycles,
        and reinitialize the JSON file for the new setpoint.
        """
        self.setpoint = new_setpoint

        # clear history of previous measurement cycles
        self.cycles_history.clear()

        # rewrite JSON with fresh structure for the new setpoint
        try:
            with open(self.json_filepath, "w") as f:
                json.dump({
                    "tolerance_A":    self.tolerance_A,
                    "tolerance_B":    self.tolerance_B,
                    "setpoint":       self.setpoint,
                    "cycles_history": []
                }, f, indent=4)
            self.logger.info(f"JSON reinitialized for new setpoint: {self.setpoint} K")
        except Exception as e:
            self.logger.error(f"Failed to reinitialize JSON for new setpoint: {e}")


    def check_stabilisation(self) -> bool:
        """
        Continuously perform measurement cycles until stabilization criteria are met,
        or abort on communication error.

        :returns: True if stabilized; False on any communication failure.
        """
        while True:
            # collect nb_points measurements
            self.current_measurements = []
            for _ in range(self.nb_points):
                try:
                    temp = self._measure_temperature()
                    self.current_measurements.append(temp)
                    self._update_json()
                    time.sleep(self.sampling_time)
                except visa_errors.VisaIOError as e:
                    self.logger.error(f"Communication error during measurement: {e}")
                    return False


            # perform regression on this batch
            A, B = self._perform_regression()

            # record this cycle’s data
            cycle = {
                "measurements":   self.current_measurements.copy(),
                "slope_A":        A,
                "intercept_B":    B,
            }
            self.cycles_history.append(cycle)

            # persist full history to JSON
            self._update_json()

            # intersection criterion: slope ≈ 0 AND intercept within ±tolerance_B of setpoint
            if abs(A) <= self.tolerance_A and abs(B - self.setpoint) <= self.tolerance_B:
                self.logger.info("Stabilization criteria met.")
                return True
            else:
                self.logger.warning(
                    f"Stabilization not reached (A={A:.6f}, B={B:.6f} K). "
                    "Restarting measurement cycle."
                )
                time.sleep(self.sampling_time)


if __name__ == "__main__":
    # Example usage
    stabilizer = TemperatureStabilizer(
        instrument_address="GPIB::12::INSTR",
        json_filepath="temperature_stabilization.json",
        setpoint=100.0,
        nb_points_stabilisation=200,
        sampling_time=0.1,
        tolerance_A=0.15,
        tolerance_B=0.15,
    )

    # Assume get_next_setpoints() is defined elsewhere and yields each new setpoint
    for new_setpoint in get_next_setpoints():
        # apply the new setpoint and reset history
        stabilizer.set_setpoint(new_setpoint)

        # perform stabilization sequence
        is_stable = stabilizer.check_stabilisation()

        # the print adapts automatically to the current setpoint
        print(f"Stabilization at {new_setpoint} K achieved? {is_stable}")
