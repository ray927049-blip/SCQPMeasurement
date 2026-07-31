from __future__ import annotations

import numpy as np

from scqp_qblox.config import ConfigError, assert_execute, check_duty_cycle, require_verified_sample_connectors
from scqp_qblox.data import create_run_dir, save_frequency_sweep, save_run_metadata
from scqp_qblox.hardware import cluster_session
from scqp_qblox.measurements import transmission_sweep
from scqp_qblox.sequences import qrm_rf_acquisition_sequence

from ._common import load, parser, print_plan


def main() -> None:
    cli = parser("Relative complex S21 sweep through the SCQP microwave transmission line")
    cli.add_argument("--start-hz", type=float)
    cli.add_argument("--stop-hz", type=float)
    cli.add_argument("--points", type=int)
    cli.add_argument("--averages", type=int)
    args = cli.parse_args()
    config = load(args)
    defaults = config["defaults"]
    start_hz = float(args.start_hz or defaults["probe_start_hz"])
    stop_hz = float(args.stop_hz or defaults["probe_stop_hz"])
    points = int(args.points or defaults["probe_points"])
    averages = int(args.averages or defaults["averages"])
    if points < 2 or stop_hz <= start_hz:
        raise ConfigError("Frequency sweep needs points >= 2 and stop > start")
    amplitude = min(float(defaults["waveform_amplitude"]), float(config["safety"]["max_qrm_rf_output_amplitude"]))
    parameters = {
        "measurement": "relative, uncalibrated S21",
        "start_hz": start_hz,
        "stop_hz": stop_hz,
        "points": points,
        "averages": averages,
        "amplitude": amplitude,
        "acquisition_length_ns": int(defaults["acquisition_length_ns"]),
    }
    sequence_dict = qrm_rf_acquisition_sequence(
        pulse_length_ns=int(defaults["waveform_length_ns"]),
        acquisition_length_ns=int(defaults["acquisition_length_ns"]),
        amplitude=amplitude,
        averages=averages,
        period_ns=int(defaults["repeat_period_ns"]),
    )
    check_duty_cycle(
        config,
        active_ns=int(defaults["acquisition_length_ns"]),
        period_ns=int(defaults["repeat_period_ns"]),
    )
    print_plan("Microwave transmission sweep plan", parameters, execute=args.execute)
    if not args.execute:
        return
    assert_execute(args.execute)
    require_verified_sample_connectors(config)
    chain = config["microwave_chain"]
    if chain.get("source_to_sample_attenuation_db") is None or chain.get("max_device_input_dbm") is None:
        raise ConfigError("Fill source_to_sample_attenuation_db and max_device_input_dbm before connecting the sample")

    frequency_hz = np.linspace(start_hz, stop_hz, points)
    with cluster_session(config, reset=args.reset, output_capable=True) as cluster:
        i_values, q_values, statuses, _ = transmission_sweep(
            cluster,
            config,
            frequencies_hz=frequency_hz,
            sequence_dict=sequence_dict,
            acquisition_length_ns=int(defaults["acquisition_length_ns"]),
        )

    run_dir = create_run_dir(args.data_root, "microwave_spectroscopy")
    save_run_metadata(
        run_dir,
        config=config,
        parameters=parameters,
        status={"points_completed": len(statuses), "last_sequencer_status": statuses[-1]},
    )
    save_frequency_sweep(
        run_dir,
        frequency_hz=frequency_hz,
        i_values=i_values,
        q_values=q_values,
    )
    print(f"Saved relative S21 data to {run_dir}")


if __name__ == "__main__":
    main()
