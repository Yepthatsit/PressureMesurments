import os
from Mesurment.PressureMeasurementv3 import PressureMeasurement
from Stabilization.Stabilisation_atomic_jsonv2 import MeasurementConfig

if __name__ == "__main__":
    # Build a single config dict matching MeasurementConfig
    cfg: MeasurementConfig = {
        "lakeshore_address":    "GPIB::12::INSTR",
        "lockin_address":       "GPIB::4::INSTR",
        "slope_tolerance":      0.1,
        "intercept_tolerance":  0.1,
        "stabilization_points": 10,
        "sampling_interval":    1,
    }

    # Instantiate and enter the context manager
    with PressureMeasurement(cfg) as pm:
        # Ramp to 310 K (uses default ramp_rate=4.0 K/min)
        pm.go_to_temperature("D:/_Uniaxial_Pressure_measurements/Probe_2/Sr214_100_spl2/Sr214_100_spl2_0deg3/Sr214_100_spl2_0deg3_resistivity_testplotly.dat", target_temp=300,ramp_rate=4,interval=1)

        #pm.stabilization_measurement(file_path="test5.csv",start_temp=300,end_temp=310.0,points=10)
