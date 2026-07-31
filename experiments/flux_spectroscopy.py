from __future__ import annotations

import numpy as np
import xarray as xr

from scqp_qblox.config import ConfigError, assert_execute, check_duty_cycle, require_verified_sample_connectors
from scqp_qblox.data import create_run_dir, save_run_metadata
from scqp_qblox.hardware import cluster_session, module_for, ramp_qcm_offset
from scqp_qblox.measurements import transmission_sweep
from scqp_qblox.sequences import qrm_rf_acquisition_sequence

from ._common import load, parser, print_plan


def main() -> None:
    cli = parser("One-axis static-flux spectroscopy of the SCQP transmission response")
    cli.add_argument("--side", choices=("left", "right"), required=True)
    cli.add_argument("--flux-start-v", type=float)
    cli.add_argument("--flux-stop-v", type=float)
    cli.add_argument("--flux-points", type=int, default=21)
    cli.add_argument("--probe-start-hz", type=float)
    cli.add_argument("--probe-stop-hz", type=float)
    cli.add_argument("--probe-points", type=int, default=101)
    args = cli.parse_args()
    config = load(args)
    defaults = config["defaults"]
    flux_cfg = config["flux"]
    side = args.side
    low = float(flux_cfg[f"{side}_min_voltage_v"])
    high = float(flux_cfg[f"{side}_max_voltage_v"])
    start_v = low if args.flux_start_v is None else float(args.flux_start_v)
    stop_v = high if args.flux_stop_v is None else float(args.flux_stop_v)
    if not low <= start_v < stop_v <= high:
        raise ConfigError(f"Requested {side} flux sweep must stay within [{low}, {high}] V")
    if args.flux_points < 2 or args.probe_points < 2:
        raise ConfigError("Both flux-points and probe-points must be >= 2")

    probe_start = float(args.probe_start_hz or defaults["probe_start_hz"])
    probe_stop = float(args.probe_stop_hz or defaults["probe_stop_hz"])
    amplitude = min(float(defaults["waveform_amplitude"]), float(config["safety"]["max_qrm_rf_output_amplitude"]))
    parameters = {
        "side": side,
        "flux_start_v": start_v,
        "flux_stop_v": stop_v,
        "flux_points": args.flux_points,
        "probe_start_hz": probe_start,
        "probe_stop_hz": probe_stop,
        "probe_points": args.probe_points,
        "other_side_voltage_v": float(flux_cfg[f"{'right' if side == 'left' else 'left'}_idle_voltage_v"]),
        "measurement": "relative, uncalibrated S21",
    }
    print_plan("Static-flux spectroscopy plan", parameters, execute=args.execute)
    if not args.execute:
        return
    assert_execute(args.execute)
    require_verified_sample_connectors(config)
    chain = config["microwave_chain"]
    if chain.get("source_to_sample_attenuation_db") is None or chain.get("max_device_input_dbm") is None:
        raise ConfigError("Fill microwave-chain attenuation and device input limit first")

    flux_values = np.linspace(start_v, stop_v, args.flux_points)
    probe_values = np.linspace(probe_start, probe_stop, args.probe_points)
    i_data = np.empty((len(flux_values), len(probe_values)))
    q_data = np.empty_like(i_data)
    sequence_dict = qrm_rf_acquisition_sequence(
        pulse_length_ns=int(defaults["waveform_length_ns"]),
        acquisition_length_ns=int(defaults["acquisition_length_ns"]),
        amplitude=amplitude,
        averages=int(defaults["averages"]),
        period_ns=int(defaults["repeat_period_ns"]),
    )
    check_duty_cycle(
        config,
        active_ns=int(defaults["acquisition_length_ns"]),
        period_ns=int(defaults["repeat_period_ns"]),
    )
    completed = 0
    last_status = "not started"
    with cluster_session(config, reset=args.reset, output_capable=True, restore_flux_idle=True) as cluster:
        qcm = module_for(cluster, config, "qcm")
        qcm_cfg = config["modules"]["qcm"]
        output = int(qcm_cfg[f"{side}_flux_output"])
        other_side = "right" if side == "left" else "left"
        ramp_qcm_offset(
            qcm,
            int(qcm_cfg[f"{other_side}_flux_output"]),
            float(flux_cfg[f"{other_side}_idle_voltage_v"]),
            step_v=float(flux_cfg["ramp_step_v"]),
            delay_s=float(flux_cfg["ramp_delay_s"]),
        )
        for row, voltage in enumerate(flux_values):
            ramp_qcm_offset(
                qcm,
                output,
                float(voltage),
                step_v=float(flux_cfg["ramp_step_v"]),
                delay_s=float(flux_cfg["ramp_delay_s"]),
            )
            i_values, q_values, statuses, _ = transmission_sweep(
                cluster,
                config,
                frequencies_hz=probe_values,
                sequence_dict=sequence_dict,
                acquisition_length_ns=int(defaults["acquisition_length_ns"]),
            )
            i_data[row] = i_values
            q_data[row] = q_values
            completed += len(statuses)
            last_status = statuses[-1]

    amplitude_data = np.hypot(i_data, q_data)
    phase_data = np.unwrap(np.arctan2(q_data, i_data), axis=1)
    dataset = xr.Dataset(
        data_vars={
            "I": (("flux_command_v", "probe_frequency_hz"), i_data),
            "Q": (("flux_command_v", "probe_frequency_hz"), q_data),
            "amplitude": (("flux_command_v", "probe_frequency_hz"), amplitude_data),
            "phase_rad": (("flux_command_v", "probe_frequency_hz"), phase_data),
        },
        coords={"flux_command_v": flux_values, "probe_frequency_hz": probe_values},
        attrs={"flux_side": side, "calibration": "command voltage; volts_per_phi0 is not calibrated"},
    )
    run_dir = create_run_dir(args.data_root, f"{side}_flux_spectroscopy")
    dataset.to_netcdf(run_dir / "flux_spectroscopy.nc", engine="h5netcdf")
    save_run_metadata(
        run_dir,
        config=config,
        parameters=parameters,
        status={"points_completed": completed, "last_sequencer_status": last_status},
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axis = plt.subplots(constrained_layout=True)
    mesh = axis.pcolormesh(probe_values / 1e9, flux_values, amplitude_data, shading="auto")
    axis.set(xlabel="Probe frequency (GHz)", ylabel=f"{side.title()} flux command (V)")
    fig.colorbar(mesh, ax=axis, label="Relative amplitude")
    fig.savefig(run_dir / "amplitude.png", dpi=180)
    plt.close(fig)
    print(f"Saved flux spectroscopy to {run_dir}")


if __name__ == "__main__":
    main()
