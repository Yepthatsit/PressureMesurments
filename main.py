import os
from Mesurment.PressureMeasurementv3 import PressureMeasurement
from Stabilization.Stabilisation_atomic_jsonv2 import MeasurementConfig

# ─── USER CONFIG ─────────────────────────────────────────────────────────────
base_dir        = r"D:\_EXPERIMENTS\Cryocooler\E_110_MK_2"
sample_name     = "E_110_MK"

pressure_angle  = "360_1"     # screw angle in degrees
pressure_cycle  = 4        # 1 = first ever application, 2 = second, etc. (for each pressure set)
file_format     = "dat"

# Which steps to run
RUN_GO_TO_TEMP  = True
RUN_STABILIZE   = False    # True for cooling down, False for warming up

# Go-to-temperature settings
target_temp     = 300    #K 120K if we go down, 300K when you heat up
ramp_rate       = 4.0      # K/min
goto_interval   = 1.0      # s

# Stabilization sweep settings
start_temp      = 120.0     # K
end_temp        = 128.0     # K
sweep_points    = 451

# Run‐counters (only bump these when re-running the *same* measurement settings!)
GO2T_RUN_INDEX  = 3      # 1 for first go-to-temp at these exact settings, 2 for second, …
STAB_RUN_INDEX  = 3 # 1 for first stab sweep at these exact settings, 2 for second, …
# How many times stabilization measurment is looped
n:int = 1

#Determines if stabilization mesurment is cycled
ComeBack = True
# ──────────────────────────────────────────────────────────────────────────────

def build_experiment_folder():
    folder = os.path.join(
        base_dir,
        sample_name,
        f"{sample_name}_{pressure_angle}_PRESS_{pressure_cycle}"
    )
    os.makedirs(folder, exist_ok=True)
    return folder

def main():
    assert n > 0
    assert type(n) == int
    exp_folder = build_experiment_folder()

    # Build file paths only for the steps you’ll run
    if RUN_GO_TO_TEMP:
        go2t_tag  = (f"Ramp{int(ramp_rate)}Kmin_to{int(target_temp)}K"
                     f"_run{GO2T_RUN_INDEX}")
        go2t_file = os.path.join(
            exp_folder,
            f"{sample_name}_{pressure_angle}_deg_{go2t_tag}.{file_format}"
        )


    cfg: MeasurementConfig = {
        "lakeshore_address":    "GPIB::12::INSTR",
        "lockin_address":       "GPIB::8::INSTR",
        "slope_tolerance":      0.001,
        "intercept_tolerance":  0.001,
        "stabilization_points": 10,
        "sampling_interval":    1,
    }

    with PressureMeasurement(cfg) as pm:

        # WhatsApp summary
        steps = []
        if RUN_GO_TO_TEMP:
            steps.append(f"• Go-to-Temp run #{GO2T_RUN_INDEX}: "
                         f"{ramp_rate} K/min → {target_temp} K\n  File: {go2t_file}")
        if RUN_STABILIZE:
            pass

        pm.send_whatsapp_text(
            "📣 Uniaxial pressure run started\n"
            f"Sample: {sample_name}\n"
            f"Angle: {pressure_angle}° (cycle #{pressure_cycle})\n"
            + "\n".join(steps)
        )

        if RUN_GO_TO_TEMP:
            pm.go_to_temperature(
                file_path=go2t_file,
                target_temp=target_temp,
                ramp_rate=ramp_rate,
                interval=goto_interval
            )

        if RUN_STABILIZE:
            for i in range(n):
                stab_tag = (f"STAB_{int(start_temp)}to{int(end_temp)}K_"
                            f"{sweep_points}pts_run{STAB_RUN_INDEX + i}")
                stab_file = os.path.join(
                    exp_folder,
                    f"{sample_name}_{pressure_angle}_deg_{stab_tag}.{file_format}"
                )
                steps.append(f"• Stabilization run #{STAB_RUN_INDEX}: "
                             f"{start_temp}→{end_temp} K over {sweep_points} pts\n  File: {stab_file}")
                pm.stabilization_measurement(
                    file_path=stab_file,
                    start_temp=start_temp,
                    end_temp=end_temp,
                    points=sweep_points,
                    comeBack= ComeBack
                )

if __name__ == "__main__":
    main()
