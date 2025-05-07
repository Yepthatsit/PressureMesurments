import os
from Mesurment.PressureMeasurementv2 import PressureMeasurement
from Stabilization.Stabilisation_atomic_jsonv2 import MeasurementConfig

if __name__ == "__main__":
    # Build a single config dict matching MeasurementConfig
    cfg: MeasurementConfig = {
        "lakeshore_address":    "GPIB::12::INSTR",
        "lockin_address":       "GPIB::8::INSTR",
        "slope_tolerance":      0.1,
        "intercept_tolerance":  0.1,
        "stabilization_points": 10,
        "sampling_interval":    5,
    }

    # Instantiate and enter the context manager
    with PressureMeasurement(cfg) as pm:
        # Ramp to 310 K (uses default ramp_rate=4.0 K/min)
        pm.go_to_temperature("freecooldown.dat", target_temp=300,ramp_rate=0)

        #pm.stabilization_measurement(file_path="test5.csv",start_temp=300,end_temp=310.0,points=10)
