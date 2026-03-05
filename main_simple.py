from Mesurment.PressureMeasurementv3 import PressureMeasurement
from Stabilization.Stabilisation_atomic_jsonv2 import MeasurementConfig

if __name__ == "__main__":
    # Build a single config dict matching MeasurementConfig
    cfg: MeasurementConfig = {
        "lakeshore_address":    "GPIB::12::INSTR",
        "lockin_address":       "GPIB::8::INSTR",
        "slope_tolerance":      0.001,
        "intercept_tolerance":  0.01,
        "stabilization_points": 10,
        "sampling_interval":    1,
    }

    with PressureMeasurement(cfg) as pm:
        #pm.go_to_temperature("D:\_EXPERIMENTS\Cryocooler\LSCO_MR2U_AFTER_XAS\LSCO_MR2U_AFTER_XAS_180_PRESS_02\LSCO_MR2U_AFTER_XAS_180_PRESS_03.dat", target_temp=300,ramp_rate=4,interval=1)
        pm.stabilization_measurement(file_path="D:\_EXPERIMENTS\Cryocooler\LSCO_MR2U_AFTER_XAS\LSCO_MR2U_AFTER_XAS_180_PRESS_02\LSCO_MR2U_AFTER_XAS_225_PRESS_test.dat",start_temp=20,end_temp=25,points=45)

